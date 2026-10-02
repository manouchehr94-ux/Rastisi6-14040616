"""ساختِ زمینه‌ی (context) متغیرهایِ اعلان از دادهٔ واقعی — فقط فیلدهایِ
امن و صریحاً مجاز؛ هیچ رمز/توکن/اطلاعاتِ پرداختی هرگز وارد نمی‌شود."""

from __future__ import annotations

from apps.core.jalali_utils import format_jalali
from apps.core.utils import format_toman, to_fa_digits


def store_public_base_url(store) -> str:
    from apps.stores.models import StoreDomain

    domain = (
        StoreDomain.objects.filter(store=store, is_primary=True, retired_at__isnull=True)
        .values_list("hostname", flat=True).first()
    )
    return f"https://{domain}" if domain else ""


def order_url(store, order) -> str:
    base = store_public_base_url(store)
    return f"{base}/account/orders/{order.code}/" if base else ""


def customer_context(store, customer) -> dict:
    return {"customer_name": customer.full_name if customer else "", "store_name": store.name}


def order_context(store, order) -> dict:
    url = order_url(store, order)
    return {
        **customer_context(store, order.customer),
        "order_number": order.code,
        "order_total": format_toman(order.grand_total, with_unit=False),
        "order_status": order.get_status_display(),
        "order_url": url,
        "tracking_number": order.tracking_code or "",
        "tracking_url": url,
    }


def discount_amount_label(coupon) -> str:
    if coupon.type == "percent":
        label = f"{to_fa_digits(int(coupon.value))}٪"
        if coupon.max_discount:
            label += f" (حداکثر {format_toman(coupon.max_discount)})"
        return label
    if coupon.type == "fixed":
        return format_toman(coupon.value)
    return "ارسال رایگان"


def coupon_context(store, customer, coupon, *, campaign_name: str = "", occasion_name: str = "") -> dict:
    return {
        **customer_context(store, customer),
        "discount_code": coupon.code,
        "discount_amount": discount_amount_label(coupon),
        "discount_max": format_toman(coupon.max_discount, with_unit=False) if coupon.max_discount else "",
        "discount_expires_at": to_fa_digits(format_jalali(coupon.expires_at)) if coupon.expires_at else "بدون انقضا",
        "campaign_name": campaign_name,
        "occasion_name": occasion_name or campaign_name,
    }
