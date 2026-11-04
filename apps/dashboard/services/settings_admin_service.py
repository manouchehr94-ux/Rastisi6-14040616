"""سرویس پنل مدیریت برای صفحه‌ی تنظیمات.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. تغییر نرخ مالیات/آستانه‌ی
ارسال رایگان همان رکورد apps.core.models.ShopSettings را می‌نویسد که سرویس
pricing (مرحله‌ی ۲) و context processor سراسری سایت می‌خوانند؛ فعال/غیرفعال
کردن درگاه یا روش ارسال همان فیلد is_active واقعی را تغییر می‌دهد که
apps.orders.services.checkout_service برای فهرست گزینه‌های تسویه‌حساب استفاده
می‌کند — هیچ مقدار جدا و بی‌اثری اینجا ساخته نشده.
"""

import re

from django.shortcuts import get_object_or_404

from apps.orders.models import PaymentGateway, ShippingMethod


def active_gateways_context(*, store):
    return PaymentGateway.objects.filter(store=store).order_by("name")


def shipping_methods_context(*, store):
    return ShippingMethod.objects.filter(store=store).order_by("cost")


def toggle_gateway(pk: int, *, store) -> PaymentGateway:
    """۴۰۴ استاندارد (نه استثنای بدون‌مدیریت) برای درگاه متعلق به Store دیگر."""
    gateway = get_object_or_404(PaymentGateway, pk=pk, store=store)
    gateway.is_active = not gateway.is_active
    gateway.save(update_fields=["is_active", "updated_at"])
    return gateway


class ShippingMethodIncomplete(ValueError):
    """روشِ ارسال به‌دلیلِ نامعتبر/ناقص بودن فعال نشد."""


def toggle_shipping_method(pk: int, *, store) -> ShippingMethod:
    """۴۰۴ استاندارد (نه استثنای بدون‌مدیریت) برای روش ارسال متعلق به Store دیگر."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    method = get_object_or_404(ShippingMethod, pk=pk, store=store)
    method.is_active = not method.is_active
    if method.is_active:
        # FOLLOWUP-09: همان اعتبارسنجیِ صفحهٔ «راه‌اندازیِ ارسال» (یک مرجع)؛ روشِ ناقص/نامعتبر فعال نمی‌شود.
        try:
            method.full_clean()
        except DjangoValidationError as exc:
            raise ShippingMethodIncomplete("؛ ".join(sum(exc.message_dict.values(), []))) from exc
    method.save(update_fields=["is_active", "updated_at"])
    from apps.core.services.audit_service import record_audit_event

    record_audit_event(
        store=store, action_code="shipping_method.updated", object_type="ShippingMethod", object_id=method.pk,
        object_label=method.name, after={"is_active": method.is_active, "via": "settings"},
    )
    return method




def _group_card(value: str) -> str:
    """Display only: 4 groups of 4 for a 16-digit number; anything else is shown in its canonical (formatting-free) form so the merchant sees what will be judged."""
    from apps.orders.gateways.card_to_card import clean_card_number

    digits = clean_card_number(value)
    return " ".join(digits[i:i + 4] for i in range(0, 16, 4)) if re.fullmatch(r"[0-9]{16}", digits) else digits


#: نگاشتِ دسته‌ی کسب‌وکاری درگاه به برچسبِ فارسی (برای نمایش در پنل).
_CATEGORY_LABELS = {
    "psp": "درگاه بانکی (PSP)",
    "facilitator": "واسط پرداخت",
    "bnpl": "پرداخت اقساطی (BNPL)",
    "offline": "آفلاین",
}

#: نگاشتِ وضعیتِ آمادگی به کلاسِ نشان (badge) برای رنگ‌بندی در قالب.
#: ok=سبز، warn=زرد، off=خاکستری، err=قرمز. (هم‌راستا با نشان‌های موجودِ پنل.)
_READINESS_BADGE = {
    "connected": "ok",
    "ready_for_test": "warn",
    "needs_credentials": "warn",
    "not_configured": "off",
    "documentation_blocked": "err",
    "unavailable": "err",
    "error": "err",
}


def _category_value(adapter) -> str:
    """مقدارِ رشته‌ایِ دسته‌ی درگاه (مقاوم در برابرِ Enum یا رشته)."""
    category = getattr(adapter, "category", None)
    return getattr(category, "value", category) or "facilitator"


class GatewayActivationBlocked(ValueError):
    """فعال‌سازیِ درگاه به‌دلیلِ آمادگیِ ناکافی رد شد (پیامِ فارسیِ قابلِ‌نمایش)."""


def gateway_activation_error(config) -> str:
    """اگر فعال‌سازیِ این پیکربندی برای پرداختِ واقعی مجاز نیست، پیامِ فارسی برمی‌گرداند؛ وگرنه «».

    قانون: درگاهی که وضعیتِ آمادگیِ آن DOCUMENTATION_BLOCKED / NEEDS_CREDENTIALS /
    NOT_CONFIGURED / UNAVAILABLE / ERROR است نباید برای پرداختِ *واقعیِ* (غیرِ
    Sandbox) فعال شود. حالتِ READY_FOR_TEST فقط وقتی مجاز است که خودِ پیکربندی
    در حالتِ Sandbox باشد (در تسویه‌حسابِ واقعی هم انتخاب‌پذیر نیست). تمامِ منطق
    از ``readiness_status`` مشتق می‌شود — بدونِ شرطِ خاصِ هر درگاه.
    """
    from apps.orders.models import PaymentGatewayConfig

    R = PaymentGatewayConfig.ReadinessStatus
    status = config.readiness_status
    if status == R.CONNECTED:
        return ""
    if status == R.READY_FOR_TEST and config.is_sandbox:
        return ""
    messages = {
        R.DOCUMENTATION_BLOCKED: (
            "این درگاه به‌دلیلِ تأییدنشدن قرارداد رسمیِ آن هنوز قابلِ فعال‌سازی برای "
            "پرداختِ واقعی نیست."
        ),
        R.NEEDS_CREDENTIALS: "برای فعال‌سازی ابتدا همه‌ی اعتبارنامه‌های لازم را به‌درستی وارد کنید.",
        R.NOT_CONFIGURED: "برای فعال‌سازی ابتدا اعتبارنامه‌ی درگاه را وارد کنید.",
        R.UNAVAILABLE: "این درگاه در دسترس نیست و قابلِ فعال‌سازی نیست.",
        R.ERROR: "به‌دلیلِ خطای پیکربندی، فعال‌سازیِ این درگاه ممکن نیست.",
        R.READY_FOR_TEST: (
            "این درگاه فقط برای حالتِ آزمایشی (Sandbox) آماده است؛ برای فعال‌سازیِ "
            "واقعی باید حالتِ آزمایشی را خاموش و درگاه را به‌طورِ کامل متصل کنید."
        ),
    }
    return messages.get(status, "فعال‌سازیِ این درگاه ممکن نیست.")


def gateway_configs_context(*, store, only: str = "", posted: dict | None = None, errors: dict | None = None, open_code: str = ""):
    """پیکربندی‌های درگاه‌های پرداخت واقعی — برای بخش «پیکربندی درگاه» در تنظیمات.

    ``only`` یک درگاه؛ ``posted`` مقدارهای ارسال‌شده‌ی غیرمحرمانه (برای بازنمایی بعد از خطا)؛ ``errors`` خطای هر فیلد؛
    رمزها/اعتبارنامه‌ی محرمانه هرگز به قالب برنمی‌گردند."""
    from apps.orders.gateways import GATEWAY_CHOICES, get_adapter
    from apps.orders.models import PaymentGatewayConfig

    configs = {c.gateway_code: c for c in PaymentGatewayConfig.objects.filter(store=store)}
    posted, errors = posted or {}, errors or {}
    R = PaymentGatewayConfig.ReadinessStatus
    readiness_display = dict(R.choices)

    R = PaymentGatewayConfig.ReadinessStatus
    readiness_display = dict(R.choices)

    result = []
    for code, label in GATEWAY_CHOICES:
        if only and code != only:
            continue
        adapter = get_adapter(code)
        config = configs.get(code)
        stored = config.get_credentials() if config else {}
        field_errors = errors if code == only else {}
        fields = []
        for f in adapter.credential_fields:
            value = ""
            if not f.get("secret", True):
                value = posted.get(f"credential_{f['name']}", stored.get(f["name"], "")) if code == only else stored.get(f["name"], "")
                if f["name"] == "destination_card":
                    value = _group_card(value)
            fields.append({**f, "value": value, "error": field_errors.get(f["name"], ""),
                           "has_value": bool(stored.get(f["name"]))})
        is_active = bool(config.is_active) if config else False
        is_configured = config.is_configured if config else (not adapter.required_credentials)
        if adapter.required_credentials and not config:
            is_configured = False

        # وضعیتِ آمادگیِ مشتق‌شده (readiness_status) — «آداپتورِ ثبت‌شده» با «اتصالِ واقعی» یکی نیست.
        if config is not None:
            readiness_value = config.readiness_status
        elif getattr(adapter, "documentation_blocked", False):
            readiness_value = R.DOCUMENTATION_BLOCKED
        else:
            readiness_value = R.NOT_CONFIGURED
        readiness_value = getattr(readiness_value, "value", readiness_value)
        category_value = _category_value(adapter)
        result.append({
            "code": code,
            "label": label,
            "adapter": adapter,
            "config": config,
            "is_active": is_active,
            "is_configured": is_configured,
            "needs_info": bool(adapter.required_credentials) and not is_configured,
            "is_online": adapter.is_online,
            "required_credentials": adapter.required_credentials,
            "credential_fields": fields,
            "form_error": field_errors.get("", ""),
            "has_errors": bool(field_errors),
            "open": bool(field_errors) or code == open_code,
            "manual": adapter.requires_manual_confirmation,
            "display_order": config.display_order if config else 0,
            "display_title": config.display_title if config else "",
            "is_sandbox": config.is_sandbox if config else False,
            "category": category_value,
            "category_label": _CATEGORY_LABELS.get(category_value, category_value),
            "supports_sandbox": getattr(adapter, "supports_sandbox", adapter.is_online),
            "documentation_blocked": getattr(adapter, "documentation_blocked", False),
            "onboarding_help": getattr(adapter, "onboarding_help", ""),
            "readiness_status": readiness_value,
            "readiness_label": readiness_display.get(readiness_value, readiness_value),
            "readiness_badge": _READINESS_BADGE.get(readiness_value, "off"),
            "is_selectable_at_checkout": config.is_selectable_at_checkout if config else False,
            # Configuration completeness (above) and externally VERIFIED connectivity are different facts. No authorized live/sandbox
            # verification call exists yet, so connectivity is never reported as verified.
            "connectivity_verified": False,
        })
    return result
