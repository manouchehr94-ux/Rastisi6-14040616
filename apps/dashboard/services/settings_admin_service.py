"""سرویس پنل مدیریت برای صفحه‌ی تنظیمات.

مطابق docs/spec/02-BUILD-INSTRUCTIONS.md مرحله‌ی ۱۴. تغییر نرخ مالیات/آستانه‌ی
ارسال رایگان همان رکورد apps.core.models.ShopSettings را می‌نویسد که سرویس
pricing (مرحله‌ی ۲) و context processor سراسری سایت می‌خوانند؛ فعال/غیرفعال
کردن درگاه یا روش ارسال همان فیلد is_active واقعی را تغییر می‌دهد که
apps.orders.services.checkout_service برای فهرست گزینه‌های تسویه‌حساب استفاده
می‌کند — هیچ مقدار جدا و بی‌اثری اینجا ساخته نشده.
"""

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




def gateway_configs_context(*, store):
    """پیکربندی‌های درگاه‌های پرداخت واقعی — برای بخش «پیکربندی درگاه» در تنظیمات."""
    from apps.orders.gateways import GATEWAY_CHOICES, get_adapter
    from apps.orders.models import PaymentGatewayConfig

    configs = {
        c.gateway_code: c
        for c in PaymentGatewayConfig.objects.filter(store=store)
    }

    result = []
    for code, label in GATEWAY_CHOICES:
        adapter = get_adapter(code)
        config = configs.get(code)
        result.append({
            "code": code,
            "label": label,
            "adapter": adapter,
            "config": config,
            "is_active": config.is_active if config else False,
            "is_configured": config.is_configured if config else False,
            "is_online": adapter.is_online,
            "required_credentials": adapter.required_credentials,
            "credential_fields": [
                {**f, "value": (config.get_credentials().get(f["name"], "") if (config and not f.get("secret", True)) else "")}
                for f in adapter.credential_fields
            ],
            "manual": adapter.requires_manual_confirmation,
            "display_order": config.display_order if config else 0,
            "display_title": config.display_title if config else "",
            "is_sandbox": config.is_sandbox if config else False,
        })
    return result
