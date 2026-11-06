"""مدیریتِ روش‌هایِ پرداختِ **خودِ پلتفرم** (راستیسی) برای دریافتِ پول از صاحبانِ فروشگاه.

اصولِ جداسازی (مالی، بدونِ استثنا):
- اعتبارنامه‌یِ پلتفرم فقط در ``PlatformGatewayConfig`` (و برای زیبالِ قدیمی، فیلدهایِ
  ``PlatformConfiguration``) نگهداری می‌شود — هرگز در ``orders.PaymentGatewayConfig``، و هرگز به‌عنوانِ fallback.
- هیچ کدِ پرداختِ سفارشِ فروشگاه این ماژول را نمی‌خواند، و هیچ کدِ پرداختِ پلتفرم
  ``PaymentGatewayConfig`` را نمی‌خواند (تستِ AST این را قفل می‌کند).
- کارت‌به‌کارتِ پلتفرم (``platform_card``) یک روشِ دستیِ درجه‌یک با ردیف و کدِ جدا از ``card_to_card`` فروشگاه است.
- پرداخت در محل (COD) و کارت‌به‌کارتِ فروشگاه **اصلاً روشِ پلتفرم نیستند** (``matrix.STORE_ONLY``).

ابعادِ آمادگی (هرگز با هم خلط نمی‌شوند):
  پیاده‌سازیِ فنی (ماتریس/آداپتر) ← پیکربندی (اعتبارنامه کامل) ← فعال‌شده توسطِ مدیر ← گیت‌هایِ گواهی
  (تأییدِ ارائه‌دهنده برای نوعِ خرید · تأییدِ قرارداد فنی · تستِ واقعیِ مجاز) ← مجاز بودن برای **نوعِ خریدِ** مشخص.
  فقط وقتی همه برقرارند «آماده» است؛ تست‌هایِ mock هرگز هیچ گیتی را باز نمی‌کنند.
- هیچ رازی در خروجیِ این ماژول، پیام‌هایِ خطا، حسابرسی یا لاگ نیست."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.billing.providers.base import BillingProviderError
from apps.orders.gateways.base import GatewayError, GatewayUnsupportedOperationError
from apps.orders.gateways.registry import get_adapter
from apps.portal.models import PlatformAuditLogEntry, PlatformConfiguration, PlatformGatewayConfig
from apps.portal.services import platform_gateway_matrix as matrix
from apps.portal.services.platform_config_service import (
    get_platform_configuration,
    record_platform_audit_event,
)

MANUAL_CODE = "manual"                                  # «بدونِ درگاهِ آنلاین» (رفتارِ قدیمیِ تأییدِ دستیِ مدیر)
PLATFORM_CARD = matrix.PLATFORM_CARD

#: روش‌هایی که پیاده‌سازیِ کارکردی دارند (approved + gated) — مشتق از ماتریسِ شواهد.
ELIGIBLE_CODES = matrix.IMPLEMENTED_CODES

PURCHASE_SUBSCRIPTION = matrix.PURCHASE_SUBSCRIPTION
PURCHASE_SMS = matrix.PURCHASE_SMS
PURCHASE_TYPES = matrix.PURCHASE_TYPES
GATE_LABELS = {
    matrix.GATE_PROVIDER_APPROVAL: "تأییدِ کتبیِ ارائه‌دهنده برای این نوعِ خرید",
    matrix.GATE_CONTRACT_VERIFICATION: "تأییدِ قرارداد فنی (تطبیق با مستندِ رسمیِ جاری)",
    matrix.GATE_LIVE_VERIFICATION: "تستِ واقعیِ مجاز (verify/settle موفق)",
}

_CONFIG_CACHE_KEY = "portal:platform_configuration"

# ---- وضعیت‌هایِ قابلِ‌نمایش (هر کدام یک معنایِ متفاوت؛ پیامِ عمومیِ یکسان ممنوع) --------------------------------------
READY = "ready"
DISABLED = "disabled_by_admin"
MISSING_CREDENTIALS = "missing_credentials"
MISSING_CONFIG = "missing_configuration"
PENDING_CONTRACT = "pending_contract"
PENDING_VERIFICATION = "pending_verification"
NOT_IMPLEMENTED = "not_implemented"
NOT_ELIGIBLE = "not_eligible"

STATUS_LABELS = {
    READY: "آماده",
    DISABLED: "غیرفعال‌شده توسط مدیر",
    MISSING_CREDENTIALS: "اعتبارنامه/پیکربندیِ پذیرنده ناقص است",
    MISSING_CONFIG: "پیکربندیِ لازم ناقص است",
    PENDING_CONTRACT: "در انتظارِ تأییدِ قرارداد/مجوزِ ارائه‌دهنده",
    PENDING_VERIFICATION: "در انتظارِ تستِ واقعیِ مجاز",
    NOT_IMPLEMENTED: "پیاده‌سازیِ فنی وجود ندارد",
    NOT_ELIGIBLE: "برای پرداختِ پلتفرم مجاز نیست",
}
#: severity برای رنگ‌بندیِ نشان: ok | info | warn | off
STATUS_TONE = {
    READY: "ok", DISABLED: "off", MISSING_CREDENTIALS: "warn", MISSING_CONFIG: "warn",
    PENDING_CONTRACT: "info", PENDING_VERIFICATION: "info", NOT_IMPLEMENTED: "off", NOT_ELIGIBLE: "off",
}


class PlatformGatewayError(Exception):
    """خطای قابل‌نمایش به مدیرِ پلتفرم (بدونِ راز)."""


@dataclass(frozen=True)
class GatewayState:
    code: str
    label: str
    kind: str
    status: str
    status_label: str
    status_detail: str
    tone: str
    eligible: bool
    configured: bool
    enabled: bool
    ready: bool
    sandbox: bool
    supports_sandbox: bool
    is_default: bool
    source: str                      # "row" | "legacy" | "none"
    errors: tuple = ()               # خطاهایِ اعتبارنامه (بدونِ مقدار)
    config_problems: tuple = ()      # پیکربندیِ ناقص غیر از اعتبارنامه
    onboarding_help: str = ""
    fields: tuple = ()               # ({name,label,configured[,value,public]}) — برای رازها هرگز مقدار
    blocked_reason: str = ""
    setup_steps: tuple = ()
    prerequisites: tuple = ()
    sandbox_note: str = ""
    verify_note: str = ""
    reconciliation_note: str = ""
    refund_mode: str = ""
    evidence: str = ""
    can_test: bool = False
    last_test_at: object = None
    last_test_ok: object = None
    last_test_message: str = ""
    gates: tuple = ()                # ({gate,label,ok,reference,at,purchase_types})
    allowed_types: tuple = ()        # نوع‌هایِ خریدِ انتخاب‌شده توسطِ مدیر
    approved_types: tuple = ()       # نوع‌هایِ خریدِ تأییدشده توسطِ ارائه‌دهنده (گیتِ تأیید)
    effective_types: tuple = ()      # اشتراکِ مجاز و تأییدشده
    pilot_possible: bool = False     # فقط گیتِ «تستِ واقعی» باز نیست ⇒ فروشگاهِ مدیرِ پلتفرم می‌تواند آزمایش کند


# ----------------------------------------------------------------------------- eligibility

def _adapter(code):
    try:
        return get_adapter(code)
    except KeyError:
        return None


def is_manual(code: str) -> bool:
    facts = matrix.facts_for(code)
    return bool(facts and facts.kind == matrix.KIND_MANUAL)


def platform_status_of(code: str) -> str:
    """وضعیتِ «اجازه‌ی استفاده برای پرداختِ پلتفرم» (مستقل از اعتبارنامه) برای روش‌هایی که پیاده‌سازی ندارند/ناشناخته‌اند."""
    facts = matrix.facts_for(code)
    if facts is None:
        return NOT_ELIGIBLE
    if facts.platform == matrix.NOT_IMPLEMENTED:
        return NOT_IMPLEMENTED
    return READY


def ineligibility_reason(code: str) -> str:
    """دلیلِ دقیقِ نامجاز‌بودنِ یک روش برای پرداختِ پلتفرم؛ رشته‌یِ خالی = پیاده‌شده و قابلِ پیکربندی. هم ماتریسِ شواهد و
    هم ادعاهایِ خودِ آداپتر باید با هم بخوانند (دفاعِ دوگانه). COD/کارت‌به‌کارتِ فروشگاه هرگز مجاز نیستند."""
    if code in matrix.STORE_ONLY:
        return "این روش فقط برای سفارشِ فروشگاه است و روشِ پرداختِ پلتفرم نیست."
    facts = matrix.facts_for(code)
    if facts is None:
        return "این روش در ماتریسِ شواهدِ پلتفرم ثبت نشده است."
    if facts.platform == matrix.NOT_IMPLEMENTED:
        return facts.blocker or "پیاده‌سازیِ فنی وجود ندارد."
    if facts.kind == matrix.KIND_MANUAL:
        return ""
    adapter = _adapter(code)
    if adapter is None:
        return "آداپترِ این درگاه ثبت نشده است."
    from apps.orders.gateways.base import PaymentOperation

    if not adapter.is_online:
        return "درگاهِ آنلاین نیست."
    # گیتِ «تأییدِ قرارداد فنی» یعنی آداپتر عمداً documentation_blocked مانده تا مدیر آن را با مستندِ رسمی تطبیق دهد.
    if adapter.documentation_blocked and matrix.GATE_CONTRACT_VERIFICATION not in facts.gates:
        return "قراردادِ رسمیِ این درگاه هنوز تأیید نشده است."
    if not (adapter.supports(PaymentOperation.CREATE) and adapter.supports(PaymentOperation.VERIFY)):
        return "درگاه عملیاتِ ایجاد و تأییدِ پرداخت را اعلام نکرده است."
    return ""


def is_eligible(code: str) -> bool:
    return not ineligibility_reason(code)


# ----------------------------------------------------------------------------- storage

def _row(code):
    return PlatformGatewayConfig.objects.filter(gateway_code=code).first()


def _legacy_zibal(config):
    return config.get_zibal_credentials(), bool(config.zibal_sandbox_mode)


def credentials_and_mode(code: str):
    """``(credentials, sandbox, source)`` — فقط برای مصرفِ Providerهایِ پرداختِ پلتفرم.
    ردیفِ ``PlatformGatewayConfig`` اولویت دارد؛ برای زیبال، در نبودِ ردیف، فیلدهایِ قدیمیِ
    ``PlatformConfiguration`` خوانده می‌شود (سازگاری با دادهٔ QA موجود). هرگز از تنظیماتِ فروشگاه."""
    row = _row(code)
    if row is not None:
        return row.get_credentials(), bool(row.sandbox_mode), "row"
    if code == "zibal":
        creds, sandbox = _legacy_zibal(get_platform_configuration())
        return creds, sandbox, "legacy" if (creds or sandbox) else "none"
    return {}, False, "none"


def _is_enabled(code: str, config) -> tuple[bool, str]:
    row = _row(code)
    if row is not None:
        return row.is_enabled, "row"
    if code == "zibal" and config.default_payment_provider == "zibal":
        return True, "legacy"                      # رفتارِ پیش از این تغییر: انتخابِ پیش‌فرض = فعال
    return False, "none"


def _manual_errors(code: str, creds: dict) -> list[str]:
    """اعتبارسنجیِ فیلدهایِ روشِ دستی (کارت‌به‌کارتِ پلتفرم) — با همان توابعِ خالصِ اعتبارسنجیِ کارتِ فروشگاه، امّا
    داده‌ی جدا."""
    from apps.orders.gateways.card_to_card import card_number_error

    errors = []
    message = card_number_error(creds.get("destination_card", ""))
    if message:
        errors.append(message)
    if not (creds.get("holder_name") or "").strip():
        errors.append("نامِ دارنده‌ی کارت الزامی است.")
    sheba = (creds.get("sheba") or "").strip()
    if sheba and not re.fullmatch(r"IR\d{24}", sheba):
        errors.append("شماره‌ی شبا باید با IR و ۲۴ رقم باشد.")
    return errors


def _credential_errors(code: str, creds: dict, sandbox: bool) -> list[str]:
    if is_manual(code):
        return _manual_errors(code, creds)
    adapter = _adapter(code)
    if adapter is None:
        return ["درگاهِ ناشناخته."]
    if sandbox and code == "zibal":
        return []                                   # Sandbox زیبال مرچنتِ ثابت دارد
    errors = list(adapter.validate_credentials(creds))
    api_base = (creds.get("api_base") or "").strip()
    if api_base and not _safe_api_base(api_base):
        errors.append("آدرسِ api_base باید یک URLِ https با نامِ دامنه (نه IP/localhost) باشد.")
    return errors


def _safe_api_base(url: str) -> bool:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    if host == "localhost" or host.endswith(".localhost") or re.fullmatch(r"[\d.]+|[0-9a-f:]+", host):
        return False
    return "." in host


def config_problems(code: str, *, sandbox: bool = False, creds: dict | None = None) -> list[str]:
    """پیکربندیِ لازمِ غیرِ اعتبارنامه: دامنه‌ی بازگشتِ canonical باید واقعی باشد (درگاه فقط به دامنه‌ی ثبت‌شده برمی‌گردد)؛
    برای روشِ دستی: حداقل یک نوعِ خرید باید مجاز شده باشد. حالتِ آزمایشی (Sandbox) پول جابه‌جا نمی‌کند ⇒ دامنه‌ی محلی مجاز است."""
    from django.conf import settings

    problems = []
    if is_manual(code):
        if not allowed_types(code):
            problems.append("هیچ نوعِ خریدی برای این روش مجاز نشده است.")
        return problems
    host = (getattr(settings, "RASTISI_PLATFORM_PRIMARY_HOST", "") or "").strip().lower()
    override = (getattr(settings, "RASTISI_BILLING_CALLBACK_BASE_URL", "") or "").strip()
    if not host and not override:
        problems.append("دامنه‌ی اصلیِ پلتفرم (RASTISI_PLATFORM_PRIMARY_HOST) تنظیم نشده است.")
    elif not sandbox and not settings.DEBUG and not override and (host == "localhost" or host.endswith(".localhost")):
        problems.append("دامنه‌ی بازگشتِ پلتفرم هنوز یک دامنه‌ی محلی (localhost) است؛ درگاهِ واقعی به آن برنمی‌گردد.")
    return problems


# ----------------------------------------------------------------------------- purchase types + gates

def allowed_types(code: str) -> tuple:
    """نوع‌هایِ خریدی که مدیر برایِ این روش انتخاب کرده؛ در نبودِ انتخاب، پیش‌فرضِ ماتریس."""
    facts = matrix.facts_for(code)
    if facts is None:
        return ()
    row = _row(code)
    chosen = [t for t in ((row.purchase_types if row else None) or []) if t in PURCHASE_TYPES]
    if row is not None and row.purchase_types is not None and chosen:
        return tuple(chosen)
    return tuple(facts.default_purchase_types)


def _attestations(code: str) -> dict:
    row = _row(code)
    return dict((row.attestations if row else None) or {})


def approved_types(code: str) -> tuple:
    """نوع‌هایِ خریدی که ارائه‌دهنده کتباً تأیید کرده (گیتِ ``provider_approval``). بدونِ این گیت: همه‌ی نوع‌ها."""
    facts = matrix.facts_for(code)
    if facts is None:
        return ()
    if matrix.GATE_PROVIDER_APPROVAL not in facts.gates:
        return PURCHASE_TYPES
    att = _attestations(code).get(matrix.GATE_PROVIDER_APPROVAL) or {}
    return tuple(t for t in att.get("purchase_types", []) if t in PURCHASE_TYPES)


def effective_types(code: str) -> tuple:
    approved = set(approved_types(code))
    return tuple(t for t in allowed_types(code) if t in approved)


def gate_states(code: str) -> tuple:
    facts = matrix.facts_for(code)
    atts = _attestations(code)
    out = []
    for gate in (facts.gates if facts else ()):
        att = atts.get(gate) or {}
        out.append({
            "gate": gate, "label": GATE_LABELS[gate], "ok": bool(att), "reference": att.get("reference", ""),
            "at": att.get("at", ""), "purchase_types": tuple(att.get("purchase_types", ())),
        })
    return tuple(out)


def _gate_ok(code: str, gate: str) -> bool:
    return bool((_attestations(code).get(gate) or {}))


def _contract_gates_open(code: str) -> bool:
    facts = matrix.facts_for(code)
    return all(_gate_ok(code, g) for g in (facts.gates if facts else ()) if g != matrix.GATE_LIVE_VERIFICATION)


def _all_gates_open(code: str) -> bool:
    facts = matrix.facts_for(code)
    return all(_gate_ok(code, g) for g in (facts.gates if facts else ()))


def _is_pilot_store(store) -> bool:
    """فروشگاهی که مالکِ فعالش مدیرِ پلتفرم (superuser) است — تنها مجاز به آزمایشِ واقعیِ روشی که فقط گیتِ «تستِ واقعی» ندارد."""
    if store is None:
        return False
    from apps.stores.models import StoreMembership

    return StoreMembership.objects.filter(
        store=store, role=StoreMembership.Role.OWNER, status=StoreMembership.MembershipStatus.ACTIVE,
        user__is_superuser=True,
    ).exists()


# ----------------------------------------------------------------------------- state

def _status_for(code, *, eligible, configured, enabled, problems):
    if not eligible:
        return platform_status_of(code) if platform_status_of(code) != READY else NOT_ELIGIBLE
    if not configured:
        return MISSING_CREDENTIALS
    if problems:
        return MISSING_CONFIG
    if not _contract_gates_open(code):
        return PENDING_CONTRACT
    if not _all_gates_open(code):
        return PENDING_VERIFICATION
    if not enabled:
        return DISABLED
    return READY


def _status_detail(status, *, code, errors, problems, reason, facts):
    if status == READY:
        return "فعال است و برای نوع‌هایِ خریدِ مجاز به صاحبانِ فروشگاه نمایش داده می‌شود."
    if status == DISABLED:
        return "همه‌ی شرایط برقرار است امّا مدیر آن را غیرفعال کرده؛ برای عرضه «فعال» را بزنید."
    if status == MISSING_CREDENTIALS:
        return "؛ ".join(errors) if errors else "اعتبارنامه‌ی پذیرنده وارد نشده است."
    if status == MISSING_CONFIG:
        return "؛ ".join(problems)
    if status == PENDING_CONTRACT:
        missing = [GATE_LABELS[g["gate"]] for g in gate_states(code) if not g["ok"] and g["gate"] != matrix.GATE_LIVE_VERIFICATION]
        return ("گیتِ ثبت‌نشده: " + "؛ ".join(missing) + ". ") + (facts.blocker if facts else "")
    if status == PENDING_VERIFICATION:
        return ("گیت‌هایِ قراردادی ثبت شده‌اند. برای فعال‌سازیِ عمومی باید یک تراکنشِ واقعیِ حداقلی و مجاز موفق شود و گیتِ «تستِ واقعی» "
                "ثبت گردد (فروشگاهِ مدیرِ پلتفرم می‌تواند آزمایش کند).")
    return reason or (facts.blocker if facts else "")


def _fields(code, creds, eligible):
    if not eligible:
        return ()
    facts = matrix.facts_for(code)
    if facts and facts.kind == matrix.KIND_MANUAL:
        out = []
        for f in facts.manual_fields:
            value = (creds.get(f["name"]) or "").strip()
            out.append({**f, "configured": bool(value), "value": value if f.get("public") else ""})
        return tuple(out)
    adapter = _adapter(code)
    labels = adapter.credential_labels if adapter is not None else {}
    required = list(adapter.required_credentials) if adapter is not None else []
    out = [{"name": n, "label": labels.get(n, n), "configured": bool((creds.get(n) or "").strip())} for n in required]
    if facts and matrix.GATE_PROVIDER_APPROVAL in facts.gates or code in ("snappay", "torobpay"):
        out.append({"name": "api_base", "label": "آدرسِ پایه‌ی API (محیطِ stage/production که ارائه‌دهنده می‌دهد — اختیاری)",
                    "configured": bool((creds.get("api_base") or "").strip()), "optional": True, "value": (creds.get("api_base") or "").strip(), "public": True})
    return tuple(out)


def gateway_state(code: str) -> GatewayState:
    config = get_platform_configuration()
    adapter = _adapter(code)
    facts = matrix.facts_for(code)
    manual = is_manual(code)
    reason = ineligibility_reason(code)
    eligible = not reason
    row = _row(code)
    creds, sandbox, source = credentials_and_mode(code)
    enabled_raw, _src = _is_enabled(code, config)
    errors = tuple(_credential_errors(code, creds, sandbox)) if eligible else ()
    configured = eligible and not errors
    problems = tuple(config_problems(code, sandbox=sandbox, creds=creds)) if eligible else ()
    status = _status_for(code, eligible=eligible, configured=configured, enabled=enabled_raw, problems=problems)
    gates = gate_states(code) if eligible else ()
    supports_sandbox = bool(eligible and not manual and adapter is not None and (adapter.supports_sandbox or code == "zibal"))
    label = adapter.display_name if adapter is not None else (facts.summary.split("—")[0].strip() if facts else code)
    pilot_possible = bool(
        eligible and configured and not problems and not manual and facts and facts.gates
        and _contract_gates_open(code) and not _all_gates_open(code)
    )
    return GatewayState(
        code=code, label=label, kind=facts.kind if facts else matrix.KIND_ONLINE,
        status=status, status_label=STATUS_LABELS[status],
        status_detail=_status_detail(status, code=code, errors=errors, problems=problems, reason=reason, facts=facts),
        tone=STATUS_TONE[status], eligible=eligible, configured=configured,
        enabled=bool(enabled_raw and eligible), ready=status == READY, sandbox=sandbox,
        supports_sandbox=supports_sandbox, is_default=config.default_payment_provider == code,
        source=source, errors=errors, config_problems=problems,
        onboarding_help=adapter.onboarding_help if (adapter is not None and eligible) else "",
        fields=_fields(code, creds, eligible), blocked_reason=reason,
        setup_steps=facts.setup_steps if facts else (), prerequisites=facts.prerequisites if facts else (),
        sandbox_note=facts.sandbox_note if facts else "", verify_note=facts.verify if facts else "",
        reconciliation_note=facts.reconciliation if facts else "", refund_mode=facts.refund if facts else "",
        evidence=facts.evidence if facts else "",
        can_test=bool(eligible and configured and not manual and (row is not None or source == "legacy")),
        last_test_at=row.last_test_at if row else None, last_test_ok=row.last_test_ok if row else None,
        last_test_message=row.last_test_message if row else "",
        gates=gates, allowed_types=allowed_types(code) if eligible else (), approved_types=approved_types(code) if eligible else (),
        effective_types=effective_types(code) if eligible else (), pilot_possible=pilot_possible,
    )


def catalog() -> list[GatewayState]:
    """همه‌ی روش‌ها به ترتیبِ معنادار: پیاده‌شده‌هایِ بدونِ گیت، سپس دارایِ گیت، سپس پیاده‌سازی‌نشده — هر کدام با وضعیتِ
    اختصاصیِ خودش. COD و کارت‌به‌کارتِ فروشگاه اصلاً در فهرستِ پلتفرم نیستند."""
    rank = {matrix.APPROVED: 0, matrix.GATED: 1, matrix.NOT_IMPLEMENTED: 2}
    codes = sorted(matrix.MATRIX, key=lambda c: (rank[matrix.MATRIX[c].platform], matrix.MATRIX[c].kind != matrix.KIND_ONLINE, list(matrix.MATRIX).index(c)))
    return [gateway_state(code) for code in codes]


# ----------------------------------------------------------------------------- readiness / selection

def _order_key(rows):
    return lambda c: (rows.get(c, 99), matrix.ONLINE_CODES.index(c))


def ready_codes(purchase_type: str | None = None, *, store=None, include_pilot: bool = False) -> list[str]:
    """روش‌هایِ **آنلاینِ** آماده (برای نوعِ خریدِ داده‌شده). ``include_pilot``: روش‌هایی که فقط گیتِ «تستِ واقعی» ندارند —
    فقط برای فروشگاهِ مالک‌-مدیرِ پلتفرم. کارت‌به‌کارتِ دستی اینجا نیست (``manual_option``)."""
    rows = {r.gateway_code: r.display_order for r in PlatformGatewayConfig.objects.all()}
    pilot_ok = include_pilot and _is_pilot_store(store)
    out = []
    for code in matrix.ONLINE_CODES:
        state = gateway_state(code)
        types = state.effective_types
        if purchase_type is not None and purchase_type not in types:
            continue
        if state.ready:
            out.append(code)
        elif pilot_ok and state.pilot_possible and state.enabled:
            out.append(code)
    return sorted(out, key=_order_key(rows))


def usable_for(code: str, purchase_type: str, store=None) -> bool:
    """آیا این روشِ آنلاین هم‌اکنون برای این نوعِ خرید (و این فروشگاه) قابلِ استفاده است؟ — تنها منبعِ تصمیم؛ هم برای انتخابِ
    گزینه‌ها و هم برای لایه‌ی دفاعیِ Provider."""
    return code in ready_codes(purchase_type, store=store, include_pilot=True)


def default_code(purchase_type: str | None = None) -> str:
    """درگاهِ آنلاینِ پیش‌فرضِ تسویه: انتخابِ مدیر اگر برایِ این نوعِ خرید آماده است، وگرنه اولین درگاهِ آماده، وگرنه manual."""
    ready = ready_codes(purchase_type)
    chosen = get_platform_configuration().default_payment_provider
    if chosen in ready:
        return chosen
    return ready[0] if ready else MANUAL_CODE


def manual_option(purchase_type: str) -> dict | None:
    """گزینه‌ی کارت‌به‌کارتِ پلتفرم برای یک نوعِ خرید (اگر فعال و مجاز است) — هرگز جزئیاتِ کارت را برنمی‌گرداند."""
    state = gateway_state(PLATFORM_CARD)
    if state.ready and purchase_type in state.allowed_types:
        return {"code": PLATFORM_CARD, "label": "کارت‌به‌کارت (بررسیِ دستی)", "is_default": False, "manual": True}
    return None


def checkout_options(purchase_type: str | None = None, *, store=None) -> list[dict]:
    """روش‌هایی که صاحبِ فروشگاه برایِ **این نوعِ خرید** در تسویه می‌بیند (فقط واجدِ شرایط‌ها؛ هرگز اعتبارنامه)."""
    default = default_code(purchase_type)
    options = []
    ready = ready_codes(purchase_type)
    for code in ready_codes(purchase_type, store=store, include_pilot=True):
        options.append({"code": code, "label": gateway_state(code).label, "is_default": code == default,
                        "manual": False, "pilot": code not in ready})
    if purchase_type is not None:
        extra = manual_option(purchase_type)
        if extra:
            options.append(extra)
    return options


def resolve_checkout_provider(requested: str = "", purchase_type: str | None = None, *, store=None) -> str:
    """کدِ Providerِ آنلاینِ مجاز برای یک پرداختِ تازه. ورودیِ کاربر فقط اگر دقیقاً یکی از روش‌هایِ واجدِ شرایطِ همین نوعِ
    خرید باشد پذیرفته می‌شود؛ هرگز یک کدِ دلخواه. روشِ دستی را فراخواننده جدا مدیریت می‌کند (``is_manual``)."""
    requested = (requested or "").strip()
    allowed = ready_codes(purchase_type, store=store, include_pilot=True)
    if requested:
        if requested not in allowed:
            raise PlatformGatewayError("درگاهِ انتخاب‌شده برای این خرید در دسترس نیست.")
        return requested
    return default_code(purchase_type)


def callback_base_url(request) -> str:
    """Origin (``scheme://host/``) the platform gateway redirects the browser back to: ALWAYS the canonical
    platform host (the domain registered with the gateway merchant), never a store/admin host. Overridable with
    ``settings.RASTISI_BILLING_CALLBACK_BASE_URL`` (full origin) for unusual deployments."""
    from django.conf import settings

    from apps.stores.hostnames import build_cross_host_url

    override = (getattr(settings, "RASTISI_BILLING_CALLBACK_BASE_URL", "") or "").strip()
    if override:
        return override.rstrip("/") + "/"
    return build_cross_host_url(request, hostname=settings.RASTISI_PLATFORM_PRIMARY_HOST, path="/")


# ----------------------------------------------------------------------------- manual card public config

def manual_card_instructions() -> dict:
    """جزئیاتِ کارتِ مقصدِ **پلتفرم** برای نمایش به مالکِ فروشگاه — فقط وقتی روش فعال و کامل است."""
    if not gateway_state(PLATFORM_CARD).ready:
        return {}
    creds, _s, _src = credentials_and_mode(PLATFORM_CARD)
    from apps.orders.gateways.card_to_card import clean_card_number

    digits = clean_card_number(creds.get("destination_card", ""))
    return {
        "card_number": digits, "card_display": " ".join(digits[i:i + 4] for i in range(0, len(digits), 4)),
        "holder_name": (creds.get("holder_name") or "").strip(), "bank_name": (creds.get("bank_name") or "").strip(),
        "sheba": (creds.get("sheba") or "").strip(), "instructions": (creds.get("instructions") or "").strip(),
    }


# ----------------------------------------------------------------------------- mutation

def _invalidate_config_cache():
    cache.delete(_CONFIG_CACHE_KEY)


def _config_row(*, lock=False):
    """ردیفِ singleton ``PlatformConfiguration`` که **حتماً در پایگاه‌داده وجود دارد** (نه نمونه‌ی پیش‌فرضِ ذخیره‌نشده)."""
    queryset = PlatformConfiguration.objects.select_for_update() if lock else PlatformConfiguration.objects
    config = queryset.filter(pk=1).first()
    if config is None:
        config, _created = PlatformConfiguration.objects.get_or_create(pk=1)
    return config


def _credential_fields_for(code: str) -> set:
    facts = matrix.facts_for(code)
    if facts and facts.kind == matrix.KIND_MANUAL:
        return {f["name"] for f in facts.manual_fields}
    adapter = _adapter(code)
    names = set(adapter.required_credentials) if adapter is not None else set()
    if code in ("snappay", "torobpay"):
        names.add("api_base")
    return names


@transaction.atomic
def save_gateway(code: str, *, credentials: dict, sandbox: bool, enabled: bool, actor=None, display_order=None,
                 purchase_types=None):
    """ذخیره/به‌روزرسانیِ یک روشِ پلتفرم. مقدارِ خالیِ راز = «بدون تغییر». فعال‌کردن فقط وقتی که اعتبارنامه کامل باشد؛ «فعال» بودن
    به‌تنهایی «آماده» نیست — گیت‌هایِ گواهی و نوعِ خرید جدا ارزیابی می‌شوند. بدونِ هیچ رازی در حسابرسی. تغییرِ اعتبارنامه گواهیِ «تستِ واقعی» را باطل می‌کند."""
    reason = ineligibility_reason(code)
    if reason:
        raise PlatformGatewayError(reason)
    facts = matrix.facts_for(code)
    manual = facts.kind == matrix.KIND_MANUAL
    adapter = None if manual else _adapter(code)
    allowed = _credential_fields_for(code)
    row = PlatformGatewayConfig.objects.select_for_update().filter(gateway_code=code).first()
    created = row is None
    if created:
        row = PlatformGatewayConfig(gateway_code=code)
        if code == "zibal":                      # ورودیِ زیبالِ قدیمی را حفظ کن تا ذخیره‌یِ جزئی چیزی را از دست ندهد.
            legacy_creds, legacy_sandbox = _legacy_zibal(get_platform_configuration())
            row.sandbox_mode = legacy_sandbox
            row.set_credentials(**{k: v for k, v in legacy_creds.items() if k in allowed})
    before = {"enabled": row.is_enabled, "sandbox": row.sandbox_mode,
              "configured": bool(row.get_credentials())} if not created else None

    cleaned = {}
    for key, value in (credentials or {}).items():
        if key not in allowed:
            continue
        value = (value or "").strip()
        if key == "destination_card" and value:
            from apps.orders.gateways.card_to_card import clean_card_number

            value = clean_card_number(value)
        if key == "sheba" and value:
            from apps.orders.gateways.card_to_card import clean_sheba

            value = clean_sheba(value)
        cleaned[key] = value
    changed_secret = any(v for v in cleaned.values())
    row.set_credentials(**cleaned)
    new_sandbox = bool(sandbox) and bool(adapter is not None and (adapter.supports_sandbox or code == "zibal"))
    if new_sandbox != row.sandbox_mode or changed_secret:
        atts = dict(row.attestations or {})
        if atts.pop(matrix.GATE_LIVE_VERIFICATION, None) is not None:
            row.attestations = atts                # اعتبارنامه/محیط عوض شد ⇒ گواهیِ تستِ واقعی دیگر معتبر نیست
    row.sandbox_mode = new_sandbox
    if display_order is not None:
        row.display_order = int(display_order)
    if purchase_types is not None:
        if any(t not in PURCHASE_TYPES for t in purchase_types):
            raise PlatformGatewayError("نوعِ خریدِ نامعتبر.")
        row.purchase_types = list(purchase_types)

    errors = _credential_errors(code, row.get_credentials(), row.sandbox_mode)
    if enabled and errors:
        raise PlatformGatewayError("برای فعال‌سازی ابتدا اعتبارنامه را کامل کنید: " + "؛ ".join(errors))
    row.is_enabled = bool(enabled)
    row.last_test_at, row.last_test_ok, row.last_test_message = None, None, ""     # تغییرِ پیکربندی ⇒ نتیجه‌ی تست کهنه
    row.save()
    _fix_default_after_change(code, row, actor)
    _invalidate_config_cache()
    record_platform_audit_event(
        actor=actor, action_code="platform_gateway.saved", object_type="PlatformGatewayConfig",
        object_id=row.pk, object_label=code, before=before,
        after={"enabled": row.is_enabled, "sandbox": row.sandbox_mode, "purchase_types": list(allowed_types(code))},
        metadata={"credentials_configured": not errors, "created": created},
    )
    return row


@transaction.atomic
def record_attestation(code: str, gate: str, *, reference: str, actor, purchase_types=None, revoke: bool = False):
    """ثبت/ابطالِ یک گیتِ آمادگی. فقط مدیرِ پلتفرم (superuser) و با ارجاعِ صریح؛ هر ثبت در حسابرسی است. ثبتِ گیت هرگز
    خودکار نیست و با تست‌هایِ mock باز نمی‌شود. فعال‌سازیِ روش پس از آن یک اقدامِ جدا است."""
    if not (actor is not None and getattr(actor, "is_superuser", False)):
        raise PlatformGatewayError("فقط مدیرِ پلتفرم می‌تواند گیتِ آمادگی را ثبت کند.")
    facts = matrix.facts_for(code)
    if facts is None or gate not in facts.gates:
        raise PlatformGatewayError("این گیت برای این روش تعریف نشده است.")
    reference = (reference or "").strip()
    row = PlatformGatewayConfig.objects.select_for_update().filter(gateway_code=code).first()
    if row is None:
        row = PlatformGatewayConfig.objects.create(gateway_code=code)
    atts = dict(row.attestations or {})
    if revoke:
        atts.pop(gate, None)
    else:
        if len(reference) < 6:
            raise PlatformGatewayError("ارجاعِ مستند (شماره‌ی نامه/تیکت/سند، حداقل ۶ نویسه) الزامی است.")
        entry = {"at": timezone.now().isoformat(timespec="seconds"), "by": actor.pk, "reference": reference[:200]}
        if gate == matrix.GATE_PROVIDER_APPROVAL:
            chosen = [t for t in (purchase_types or []) if t in PURCHASE_TYPES]
            if not chosen:
                raise PlatformGatewayError("برای تأییدِ ارائه‌دهنده، نوع‌هایِ خریدِ تأییدشده را مشخص کنید.")
            entry["purchase_types"] = chosen
        atts[gate] = entry
    row.attestations = atts
    row.save(update_fields=["attestations", "updated_at"])
    if revoke or not _all_gates_open(code):
        # با باطل‌شدنِ یک گیت، روش باید از عرضه خارج شود (فعال می‌ماند امّا آماده نیست)؛ پیش‌فرض اصلاح می‌شود.
        _fix_default_after_change(code, row, actor)
    _invalidate_config_cache()
    record_platform_audit_event(
        actor=actor, action_code="platform_gateway.gate_revoked" if revoke else "platform_gateway.gate_recorded",
        object_type="PlatformGatewayConfig", object_id=row.pk, object_label=f"{code}:{gate}",
        after={"gate": gate, "reference": "" if revoke else reference[:200], "purchase_types": list(purchase_types or [])},
    )
    return row


def _fix_default_after_change(code, row, actor):
    """اگر درگاهِ پیش‌فرض غیرفعال/ناقص شد، پیش‌فرض به درگاهِ آماده‌یِ دیگر (یا manual) برمی‌گردد."""
    config = _config_row()
    if config.default_payment_provider != code:
        return
    if gateway_state(code).ready:
        return
    others = [c for c in ready_codes() if c != code]
    new_default = others[0] if others else MANUAL_CODE
    config.default_payment_provider = new_default
    config.save(update_fields=["default_payment_provider", "updated_at"])
    record_platform_audit_event(
        actor=actor, action_code="platform_gateway.default_reassigned", object_type="PlatformConfiguration",
        object_id=1, before={"default": code}, after={"default": new_default},
    )


@transaction.atomic
def set_default(code: str, *, actor=None):
    """درگاهِ آنلاینِ پیش‌فرض. فقط یک روشِ آنلاینِ **آماده** (یا manual=بدونِ درگاه). کارت‌به‌کارتِ دستی پیش‌فرض نمی‌شود."""
    if code != MANUAL_CODE and code not in ready_codes():
        raise PlatformGatewayError("فقط درگاهِ آنلاینِ فعال و آماده می‌تواند پیش‌فرض شود.")
    config = _config_row(lock=True)
    before = config.default_payment_provider
    config.default_payment_provider = code
    config.save(update_fields=["default_payment_provider", "updated_at"])
    _invalidate_config_cache()
    record_platform_audit_event(
        actor=actor, action_code="platform_gateway.default_changed", object_type="PlatformConfiguration",
        object_id=1, before={"default": before}, after={"default": code},
    )


def audit_trail(limit: int = 50):
    return PlatformAuditLogEntry.objects.filter(action_code__startswith="platform_gateway.").order_by("-id")[:limit]


# ----------------------------------------------------------------------------- secure configuration test

@dataclass(frozen=True)
class ConnectionTestResult:
    ok: bool
    message: str
    steps: tuple = field(default_factory=tuple)     # ({label, ok, code})


_SAFE_FAILURE_MESSAGES = {
    "not_configured": "اعتبارنامه ناقص یا نامعتبر است.",
    "connection_error": "اتصال به درگاه برقرار نشد.",
    "timeout": "پاسخِ درگاه در زمانِ مقرر نرسید.",
}


def _safe_message(exc) -> str:
    """پیامِ امن برای مدیر: فقط کدِ خطا + جمله‌ی عمومی؛ هیچ مقدارِ اعتبارنامه/پاسخِ خامِ درگاهی نشان داده نمی‌شود."""
    code = getattr(exc, "code", "") or type(exc).__name__
    return f"{_SAFE_FAILURE_MESSAGES.get(code, 'درگاه درخواست را رد کرد یا پاسخِ نامعتبر داد.')} (کد: {code})"


class _ConfigTestAttempt:
    """نمونه‌ی گذرا (ذخیره‌نشده) برای تستِ پیکربندی — از همان مسیرِ کدِ واقعیِ Providerِ پلتفرم عبور می‌کند، امّا
    هیچ ردیفِ پرداختی ساخته نمی‌شود. ``pk`` در فضای نامِ ``9…`` است تا با تلاش‌هایِ واقعی (``1…``/``2…``) برخورد نکند."""

    def __init__(self):
        import secrets as _s

        self.pk = int("".join(_s.choice("0123456789") for _ in range(9)))
        self.public_token = f"rstest{_s.token_hex(8)}"
        self.amount = Decimal(10000)
        self.currency = "IRT"
        self.provider_extra = {}
        self.provider_session_id = ""


class _ConfigTestInvoice:
    number = "TEST"
    payment_description = "تست پیکربندی راستیسی (بدون پرداخت)"
    lines = ()


def _dry_run_session(code: str, callback_base: str) -> bool:
    from apps.billing.providers import registry as billing_registry

    attempt = _ConfigTestAttempt()
    callback = callback_base.rstrip("/") + "/billing/return/test/"
    billing_registry.get_provider(code).create_payment_session(attempt=attempt, invoice=_ConfigTestInvoice(), return_url=callback)
    return True


def _ensure_row(code: str) -> PlatformGatewayConfig:
    """ردیفِ درگاه را (در صورتِ نبودن، با حفظِ اعتبارنامه/وضعیتِ legacy) می‌سازد تا نتیجه‌ی تست ذخیره شود."""
    row = _row(code)
    if row is not None:
        return row
    config = get_platform_configuration()
    creds, sandbox, _src = credentials_and_mode(code)
    enabled, _s = _is_enabled(code, config)
    row = PlatformGatewayConfig(gateway_code=code, is_enabled=enabled, sandbox_mode=sandbox)
    row.set_credentials(**creds)
    row.save()
    return row


def run_connection_test(code: str, *, callback_base: str, actor=None) -> ConnectionTestResult:
    """«تستِ پیکربندی» — بدونِ حرکتِ پول و بدونِ هیچ ردیفِ پرداخت:
    ۱) اعتبارنامه کامل است؛ ۲) (اگر مستندِ درگاه یک احرازِ بی‌اثر دارد) احرازِ هویت؛ ۳) یک درخواستِ پرداختِ آزمایشیِ
    پرداخت‌نشده ساخته می‌شود و هرگز به مشتری ریدایرکت یا ذخیره نمی‌شود. فقط کد/جمله‌یِ امن برمی‌گردد.
    موفقیتِ این تست **هیچ گیتی را باز نمی‌کند**."""
    reason = ineligibility_reason(code)
    if reason:
        raise PlatformGatewayError(reason)
    if is_manual(code):
        raise PlatformGatewayError("روشِ دستی تستِ اتصال ندارد.")
    state = gateway_state(code)
    if not state.configured:
        raise PlatformGatewayError("برای تست ابتدا اعتبارنامه را کامل کنید.")
    adapter = _adapter(code)
    creds, sandbox, _source = credentials_and_mode(code)
    steps = []
    ok = True
    message = "پیکربندی سالم است؛ هیچ پولی جابه‌جا نشد."
    try:
        try:
            adapter.check_connection(credentials=creds, sandbox=sandbox)
            steps.append({"label": "احرازِ هویت", "ok": True, "code": ""})
        except GatewayUnsupportedOperationError:
            pass                                      # این درگاه احرازِ بی‌اثر ندارد؛ فقط درخواستِ آزمایشی
        if adapter.supports_dry_run_session:
            steps.append({"label": "ساختِ درخواستِ پرداختِ آزمایشی", "ok": _dry_run_session(code, callback_base), "code": ""})
    except (GatewayError, BillingProviderError) as exc:
        ok = False
        message = _safe_message(exc)
        steps.append({"label": "ارتباط با درگاه", "ok": False, "code": getattr(exc, "code", "") or type(exc).__name__})

    row = _ensure_row(code)
    row.last_test_at, row.last_test_ok, row.last_test_message = timezone.now(), ok, message[:300]
    row.save(update_fields=["last_test_at", "last_test_ok", "last_test_message", "updated_at"])
    record_platform_audit_event(
        actor=actor, action_code="platform_gateway.tested", object_type="PlatformGatewayConfig", object_id=row.pk,
        object_label=code, after={"ok": ok}, metadata={"steps": [{"ok": s["ok"], "code": s["code"]} for s in steps]},
    )
    return ConnectionTestResult(ok=ok, message=message, steps=tuple(steps))
