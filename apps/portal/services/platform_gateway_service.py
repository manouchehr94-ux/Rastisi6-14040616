"""مدیریتِ درگاه‌هایِ پرداختِ **خودِ پلتفرم** (راستیسی) برای دریافتِ پول از صاحبانِ فروشگاه.

اصولِ جداسازی (مالی، بدونِ استثنا):
- اعتبارنامه‌یِ پلتفرم فقط در ``PlatformGatewayConfig`` (و برای زیبالِ قدیمی، فیلدهایِ
  ``PlatformConfiguration``) نگهداری می‌شود — هرگز در ``orders.PaymentGatewayConfig``.
- هیچ کدِ پرداختِ سفارشِ فروشگاه این ماژول را نمی‌خواند، و هیچ کدِ پرداختِ پلتفرم
  ``PaymentGatewayConfig`` را نمی‌خواند (تستِ AST این را قفل می‌کند).
- فقط آداپترهایی که قراردادِ رسمی‌شان تأیید شده (``documentation_blocked=False``)، آنلاین،
  و دارایِ عملیاتِ CREATE+VERIFY هستند و در فهرستِ سفیدِ ``ELIGIBLE_CODES`` آمده‌اند قابلِ
  انتخاب‌اند. BNPL و آداپترهایِ مسدود هرگز.
- «فعال» = اجازه‌یِ مدیر؛ «آماده» = فعال + اعتبارنامه‌یِ کامل + آداپترِ تأییدشده. فقط
  درگاهِ *آماده* در تسویه‌یِ پلتفرم عرضه می‌شود.
- هیچ رازی در خروجیِ این ماژول، پیام‌هایِ خطا، حسابرسی یا لاگ نیست."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.billing.providers.base import BillingProviderError
from apps.orders.gateways.base import GatewayCategory, GatewayError, GatewayUnsupportedOperationError, PaymentOperation
from apps.orders.gateways.registry import get_adapter, is_online_gateway, registered_codes
from apps.portal.models import PlatformAuditLogEntry, PlatformConfiguration, PlatformGatewayConfig
from apps.portal.services import platform_gateway_matrix as matrix
from apps.portal.services.platform_config_service import (
    get_platform_configuration,
    record_platform_audit_event,
)

MANUAL_CODE = "manual"

#: درگاه‌هایی که برای پرداختِ پلتفرم مجازند — مشتق از ماتریسِ شواهد (``platform_gateway_matrix``)، نه یک فهرستِ
#: جداگانه؛ افزودنِ یک کد یعنی ثبتِ مدرکِ قراردادی در ماتریس.
ELIGIBLE_CODES = matrix.APPROVED_CODES

_CONFIG_CACHE_KEY = "portal:platform_configuration"

# ---- وضعیت‌های قابلِ‌نمایش (هر کدام یک معنای متفاوت؛ پیامِ عمومیِ یکسان ممنوع) --------------------------------------
READY = "ready"
DISABLED = "disabled_by_admin"
MISSING_CREDENTIALS = "missing_credentials"
MISSING_CONFIG = "missing_configuration"
PENDING_CONTRACT = "pending_contract"
NOT_IMPLEMENTED = "not_implemented"
NOT_ELIGIBLE = "not_eligible"

STATUS_LABELS = {
    READY: "آماده",
    DISABLED: "غیرفعال‌شده توسط مدیر",
    MISSING_CREDENTIALS: "اعتبارنامه‌ی پذیرنده ناقص است",
    MISSING_CONFIG: "پیکربندیِ لازم ناقص است",
    PENDING_CONTRACT: "در انتظارِ تأییدِ قرارداد/تأیید",
    NOT_IMPLEMENTED: "پیاده‌سازیِ فنی وجود ندارد",
    NOT_ELIGIBLE: "برای پرداختِ پلتفرم مجاز نیست",
}
#: severity برای رنگ‌بندیِ نشان: ok | info | warn | off
STATUS_TONE = {
    READY: "ok", DISABLED: "off", MISSING_CREDENTIALS: "warn", MISSING_CONFIG: "warn",
    PENDING_CONTRACT: "info", NOT_IMPLEMENTED: "off", NOT_ELIGIBLE: "off",
}


class PlatformGatewayError(Exception):
    """خطای قابل‌نمایش به مدیرِ پلتفرم (بدونِ راز)."""


@dataclass(frozen=True)
class GatewayState:
    code: str
    label: str
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
    errors: tuple = ()               # خطاهای اعتبارنامه (بدونِ مقدار)
    config_problems: tuple = ()      # پیکربندیِ ناقص غیر از اعتبارنامه
    onboarding_help: str = ""
    fields: tuple = ()               # ({name,label,configured}) — هرگز مقدار
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


# ----------------------------------------------------------------------------- eligibility

def _adapter(code):
    try:
        return get_adapter(code)
    except KeyError:
        return None


def platform_status_of(code: str) -> str:
    """وضعیتِ «اجازه‌ی استفاده برای پرداختِ پلتفرم» (مستقل از اعتبارنامه): approved یا یکی از چهار وضعیتِ مسدود."""
    facts = matrix.facts_for(code)
    adapter = _adapter(code)
    if adapter is None:
        return NOT_ELIGIBLE
    if facts is None:
        return NOT_ELIGIBLE
    return {
        matrix.APPROVED: READY, matrix.PENDING_CONTRACT: PENDING_CONTRACT,
        matrix.NOT_IMPLEMENTED: NOT_IMPLEMENTED, matrix.NOT_ELIGIBLE: NOT_ELIGIBLE,
    }[facts.platform]


def ineligibility_reason(code: str) -> str:
    """دلیلِ دقیقِ نامجاز‌بودنِ یک درگاه برای پرداختِ پلتفرم؛ رشته‌یِ خالی = مجاز. هم ماتریسِ شواهد و هم
    ادعاهای خودِ آداپتر باید با هم بخوانند (دفاعِ دوگانه)."""
    adapter = _adapter(code)
    if adapter is None:
        return "درگاهِ ناشناخته."
    facts = matrix.facts_for(code)
    if facts is None:
        return "این درگاه در ماتریسِ شواهدِ پلتفرم ثبت نشده است."
    if facts.platform != matrix.APPROVED:
        return facts.blocker or "این درگاه برای پرداختِ پلتفرم تأیید نشده است."
    if not adapter.is_online:
        return "درگاهِ آنلاین نیست."
    if adapter.documentation_blocked:
        return "قراردادِ رسمیِ این درگاه هنوز تأیید نشده است."
    if adapter.category not in (GatewayCategory.PSP, GatewayCategory.FACILITATOR):
        return "این دسته از درگاه‌ها برای پرداختِ پلتفرم مجاز نیست."
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
    ``PlatformConfiguration`` خوانده می‌شود (سازگاری با دادهٔ QA موجود)."""
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


def _credential_errors(code: str, creds: dict, sandbox: bool) -> list[str]:
    adapter = _adapter(code)
    if adapter is None:
        return ["درگاهِ ناشناخته."]
    if sandbox and code == "zibal":
        return []                                   # Sandbox زیبال مرچنتِ ثابت دارد
    return list(adapter.validate_credentials(creds))


def config_problems(code: str, *, sandbox: bool = False) -> list[str]:
    """پیکربندیِ لازمِ غیرِ اعتبارنامه: دامنه‌ی بازگشتِ canonical باید واقعی باشد (درگاه فقط به دامنه‌ی ثبت‌شده برمی‌گرداند).
    حالتِ آزمایشی (Sandbox) پول جابه‌جا نمی‌کند ⇒ دامنه‌ی محلی (لپ‌تاپِ QA) مجاز است."""
    from django.conf import settings

    problems = []
    host = (getattr(settings, "RASTISI_PLATFORM_PRIMARY_HOST", "") or "").strip().lower()
    override = (getattr(settings, "RASTISI_BILLING_CALLBACK_BASE_URL", "") or "").strip()
    if not host and not override:
        problems.append("دامنه‌ی اصلیِ پلتفرم (RASTISI_PLATFORM_PRIMARY_HOST) تنظیم نشده است.")
    elif not sandbox and not settings.DEBUG and not override and (host == "localhost" or host.endswith(".localhost")):
        problems.append("دامنه‌ی بازگشتِ پلتفرم هنوز یک دامنه‌ی محلی (localhost) است؛ درگاهِ واقعی به آن برنمی‌گردد.")
    return problems


def _status_for(code, *, eligible, configured, enabled, problems):
    if not eligible:
        base = platform_status_of(code)
        return base if base != READY else NOT_ELIGIBLE
    if not configured:
        return MISSING_CREDENTIALS
    if problems:
        return MISSING_CONFIG
    if not enabled:
        return DISABLED
    return READY


def _status_detail(status, *, code, errors, problems, reason, facts):
    if status == READY:
        return "فعال است و به صاحبانِ فروشگاه در تسویه نمایش داده می‌شود."
    if status == DISABLED:
        return "اعتبارنامه کامل است امّا مدیر آن را غیرفعال کرده؛ برای عرضه «فعال» را بزنید."
    if status == MISSING_CREDENTIALS:
        return "؛ ".join(errors) if errors else "اعتبارنامه‌ی پذیرنده وارد نشده است."
    if status == MISSING_CONFIG:
        return "؛ ".join(problems)
    return reason or (facts.blocker if facts else "")


def gateway_state(code: str) -> GatewayState:
    config = get_platform_configuration()
    adapter = _adapter(code)
    facts = matrix.facts_for(code)
    reason = ineligibility_reason(code)
    eligible = not reason
    row = _row(code)
    creds, sandbox, source = credentials_and_mode(code)
    enabled_raw, _src = _is_enabled(code, config)
    errors = tuple(_credential_errors(code, creds, sandbox)) if adapter is not None and eligible else ()
    configured = adapter is not None and eligible and not errors
    problems = tuple(config_problems(code, sandbox=sandbox)) if eligible else ()
    status = _status_for(code, eligible=eligible, configured=configured, enabled=enabled_raw, problems=problems)
    labels = adapter.credential_labels if adapter is not None else {}
    required = list(adapter.required_credentials) if adapter is not None else []
    fields = tuple(
        {"name": name, "label": labels.get(name, name), "configured": bool((creds.get(name) or "").strip())}
        for name in required
    ) if eligible else ()
    return GatewayState(
        code=code, label=adapter.display_name if adapter is not None else code,
        status=status, status_label=STATUS_LABELS[status],
        status_detail=_status_detail(status, code=code, errors=errors, problems=problems, reason=reason, facts=facts),
        tone=STATUS_TONE[status], eligible=eligible, configured=configured,
        enabled=bool(enabled_raw and eligible), ready=status == READY, sandbox=sandbox,
        supports_sandbox=bool(eligible and adapter is not None and (adapter.supports_sandbox or code == "zibal")),
        is_default=config.default_payment_provider == code,
        source=source, errors=errors, config_problems=problems,
        onboarding_help=adapter.onboarding_help if (adapter is not None and eligible) else "",
        fields=fields, blocked_reason=reason,
        setup_steps=facts.setup_steps if facts else (), prerequisites=facts.prerequisites if facts else (),
        sandbox_note=facts.sandbox_note if facts else "", verify_note=facts.verify if facts else "",
        reconciliation_note=facts.reconciliation if facts else "", refund_mode=facts.refund if facts else "",
        evidence=facts.evidence if facts else "",
        can_test=bool(eligible and configured and row is not None or (eligible and configured and source == "legacy")),
        last_test_at=row.last_test_at if row else None, last_test_ok=row.last_test_ok if row else None,
        last_test_message=row.last_test_message if row else "",
    )


def catalog() -> list[GatewayState]:
    """همه‌ی درگاه‌ها به ترتیبِ معنادار: مجازها، سپس در انتظارِ قرارداد، پیاده‌سازی‌نشده و نامجاز — هر کدام با وضعیتِ
    اختصاصیِ خودش (نه یک پیامِ عمومی)."""
    order = {matrix.APPROVED: 0, matrix.PENDING_CONTRACT: 1, matrix.NOT_IMPLEMENTED: 2, matrix.NOT_ELIGIBLE: 3}
    codes = [c for c in registered_codes() if c in matrix.MATRIX or is_online_gateway(c)]
    codes.sort(key=lambda c: (order.get(matrix.MATRIX[c].platform if c in matrix.MATRIX else matrix.NOT_ELIGIBLE, 9), c))
    return [gateway_state(code) for code in codes]


def ready_codes() -> list[str]:
    rows = {r.gateway_code: r.display_order for r in PlatformGatewayConfig.objects.all()}
    ready = [code for code in ELIGIBLE_CODES if gateway_state(code).ready]
    return sorted(ready, key=lambda c: (rows.get(c, 99), ELIGIBLE_CODES.index(c)))


def default_code() -> str:
    """درگاهِ پیش‌فرضِ تسویه: انتخابِ مدیر اگر آماده است، وگرنه اولین درگاهِ آماده، وگرنه manual."""
    ready = ready_codes()
    chosen = get_platform_configuration().default_payment_provider
    if chosen in ready:
        return chosen
    return ready[0] if ready else MANUAL_CODE


def checkout_options() -> list[dict]:
    """درگاه‌هایی که صاحبِ فروشگاه در تسویه می‌بیند (فقط آماده‌ها؛ هرگز اعتبارنامه)."""
    default = default_code()
    return [
        {"code": code, "label": gateway_state(code).label, "is_default": code == default}
        for code in ready_codes()
    ]


def resolve_checkout_provider(requested: str = "") -> str:
    """کدِ Providerِ مجاز برای یک پرداختِ تازه. ورودیِ کاربر فقط اگر دقیقاً یکی از درگاه‌هایِ
    آمادهٔ پلتفرم باشد پذیرفته می‌شود؛ هرگز یک کدِ دلخواه."""
    requested = (requested or "").strip()
    ready = ready_codes()
    if requested:
        if requested not in ready:
            raise PlatformGatewayError("درگاهِ انتخاب‌شده در دسترس نیست.")
        return requested
    return default_code()


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


# ----------------------------------------------------------------------------- mutation

def _invalidate_config_cache():
    cache.delete(_CONFIG_CACHE_KEY)


@transaction.atomic
def save_gateway(code: str, *, credentials: dict, sandbox: bool, enabled: bool, actor=None, display_order=None):
    """ذخیره/به‌روزرسانیِ یک درگاهِ پلتفرم. مقدارِ خالیِ راز = «بدون تغییر». فعال‌کردن فقط وقتی
    که اعتبارنامه کامل باشد. بدونِ هیچ رازی در حسابرسی."""
    reason = ineligibility_reason(code)
    if reason:
        raise PlatformGatewayError(reason)
    adapter = _adapter(code)
    allowed = set(adapter.required_credentials)
    row = PlatformGatewayConfig.objects.select_for_update().filter(gateway_code=code).first()
    created = row is None
    if created:
        row = PlatformGatewayConfig(gateway_code=code)
        # ورودیِ زیبالِ قدیمی را حفظ کن تا ذخیره‌یِ جزئی چیزی را از دست ندهد.
        if code == "zibal":
            legacy_creds, legacy_sandbox = _legacy_zibal(get_platform_configuration())
            row.sandbox_mode = legacy_sandbox
            row.set_credentials(**{k: v for k, v in legacy_creds.items() if k in allowed})
    before = {"enabled": row.is_enabled, "sandbox": row.sandbox_mode,
              "configured": bool(row.get_credentials())} if not created else None

    row.set_credentials(**{k: (v or "").strip() for k, v in (credentials or {}).items() if k in allowed})
    row.sandbox_mode = bool(sandbox) and (adapter.supports_sandbox or code == "zibal")
    if display_order is not None:
        row.display_order = int(display_order)

    errors = _credential_errors(code, row.get_credentials(), row.sandbox_mode)
    if enabled and errors:
        raise PlatformGatewayError("برای فعال‌سازی ابتدا اعتبارنامه را کامل کنید: " + "؛ ".join(errors))
    row.is_enabled = bool(enabled)
    row.last_test_at, row.last_test_ok, row.last_test_message = None, None, ""     # تغییرِ پیکربندی ⇒ نتیجه‌ی تست کهنه
    row.save()

    if code == "zibal":                              # آینه برای خوانندگانِ قدیمی (بازگشت‌پذیری)
        _mirror_zibal_to_legacy(row)
    _fix_default_after_change(code, row, actor)
    _invalidate_config_cache()
    record_platform_audit_event(
        actor=actor, action_code="platform_gateway.saved", object_type="PlatformGatewayConfig",
        object_id=row.pk, object_label=code, before=before,
        after={"enabled": row.is_enabled, "sandbox": row.sandbox_mode},
        metadata={"credentials_configured": not errors, "created": created},
    )
    return row


def _mirror_zibal_to_legacy(row):
    config = _config_row()
    config.zibal_sandbox_mode = row.sandbox_mode
    creds = row.get_credentials()
    config.encrypted_zibal_credentials = ""
    config.set_zibal_credentials(**{k: v for k, v in creds.items() if v})
    config.save(update_fields=["zibal_sandbox_mode", "encrypted_zibal_credentials", "updated_at"])


def _config_row(*, lock=False):
    """ردیفِ singleton ``PlatformConfiguration`` که **حتماً در پایگاه‌داده وجود دارد** (نه نمونه‌ی پیش‌فرضِ ذخیره‌نشده)."""
    queryset = PlatformConfiguration.objects.select_for_update() if lock else PlatformConfiguration.objects
    config = queryset.filter(pk=1).first()
    if config is None:
        config, _created = PlatformConfiguration.objects.get_or_create(pk=1)
    return config


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
    if code != MANUAL_CODE and code not in ready_codes():
        raise PlatformGatewayError("فقط درگاهِ فعال و آماده می‌تواند پیش‌فرض شود.")
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


class _ConfigTestInvoice:
    number = "TEST"
    payment_description = "تست پیکربندی راستیسی (بدون پرداخت)"


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
    پرداخت‌نشده ساخته می‌شود و هرگز به مشتری ریدایرکت یا ذخیره نمی‌شود. فقط کد/جمله‌یِ امن برمی‌گردد."""
    reason = ineligibility_reason(code)
    if reason:
        raise PlatformGatewayError(reason)
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
