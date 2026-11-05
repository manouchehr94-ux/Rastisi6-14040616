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

from django.core.cache import cache
from django.db import transaction

from apps.orders.gateways.base import GatewayCategory, PaymentOperation
from apps.orders.gateways.registry import get_adapter, is_online_gateway, registered_codes
from apps.portal.models import PlatformAuditLogEntry, PlatformConfiguration, PlatformGatewayConfig
from apps.portal.services.platform_config_service import (
    get_platform_configuration,
    record_platform_audit_event,
)

MANUAL_CODE = "manual"

#: فهرستِ سفیدِ صریحِ درگاه‌هایی که برای پرداختِ پلتفرم مجازند. افزودنِ هر کدِ تازه یک تصمیمِ
#: صریحِ کد/بازبینی است، نه نتیجه‌یِ خودکارِ ثبتِ یک آداپتر.
ELIGIBLE_CODES = ("zibal", "zarinpal")

_CONFIG_CACHE_KEY = "portal:platform_configuration"


class PlatformGatewayError(Exception):
    """خطای قابل‌نمایش به مدیرِ پلتفرم (بدونِ راز)."""


@dataclass(frozen=True)
class GatewayState:
    code: str
    label: str
    eligible: bool
    configured: bool
    enabled: bool
    ready: bool
    sandbox: bool
    supports_sandbox: bool
    is_default: bool
    source: str                      # "row" | "legacy" | "none"
    errors: tuple = ()
    onboarding_help: str = ""
    fields: tuple = ()               # ({name,label,configured}) — هرگز مقدار
    blocked_reason: str = ""


# ----------------------------------------------------------------------------- eligibility

def _adapter(code):
    try:
        return get_adapter(code)
    except KeyError:
        return None


def ineligibility_reason(code: str) -> str:
    """دلیلِ نامجاز‌بودنِ یک درگاه برای پرداختِ پلتفرم؛ رشته‌یِ خالی = مجاز."""
    adapter = _adapter(code)
    if adapter is None:
        return "درگاهِ ناشناخته."
    if code not in ELIGIBLE_CODES:
        return "این درگاه برای پرداختِ پلتفرم تأیید نشده است."
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


def gateway_state(code: str) -> GatewayState:
    config = get_platform_configuration()
    adapter = _adapter(code)
    reason = ineligibility_reason(code)
    creds, sandbox, source = credentials_and_mode(code)
    enabled, _src = _is_enabled(code, config)
    errors = tuple(_credential_errors(code, creds, sandbox)) if adapter is not None and not reason else ()
    configured = adapter is not None and not reason and not errors
    labels = adapter.credential_labels if adapter is not None else {}
    required = list(adapter.required_credentials) if adapter is not None else []
    fields = tuple(
        {"name": name, "label": labels.get(name, name), "configured": bool((creds.get(name) or "").strip())}
        for name in required
    )
    return GatewayState(
        code=code, label=adapter.display_name if adapter is not None else code,
        eligible=not reason, configured=configured, enabled=enabled and not reason,
        ready=bool(not reason and enabled and configured), sandbox=sandbox,
        supports_sandbox=bool(adapter is not None and (adapter.supports_sandbox or code == "zibal")),
        is_default=config.default_payment_provider == code,
        source=source, errors=errors,
        onboarding_help=adapter.onboarding_help if adapter is not None else "",
        fields=fields, blocked_reason=reason,
    )


def catalog() -> list[GatewayState]:
    """همه‌یِ درگاه‌هایِ مجازِ پلتفرم + (برایِ شفافیت) درگاه‌هایِ مسدود/تأییدنشده، فقط‌خواندنی."""
    eligible = [gateway_state(code) for code in ELIGIBLE_CODES]
    others = [
        gateway_state(code) for code in registered_codes()
        if code not in ELIGIBLE_CODES and is_online_gateway(code)
    ]
    return eligible + others


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
    config = PlatformConfiguration.objects.filter(pk=1).first() or get_platform_configuration()
    config.zibal_sandbox_mode = row.sandbox_mode
    creds = row.get_credentials()
    config.encrypted_zibal_credentials = ""
    config.set_zibal_credentials(**{k: v for k, v in creds.items() if v})
    config.save(update_fields=["zibal_sandbox_mode", "encrypted_zibal_credentials", "updated_at"])


def _fix_default_after_change(code, row, actor):
    """اگر درگاهِ پیش‌فرض غیرفعال/ناقص شد، پیش‌فرض به درگاهِ آماده‌یِ دیگر (یا manual) برمی‌گردد."""
    config = PlatformConfiguration.objects.filter(pk=1).first() or get_platform_configuration()
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
    config = PlatformConfiguration.objects.select_for_update().filter(pk=1).first() or get_platform_configuration()
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
