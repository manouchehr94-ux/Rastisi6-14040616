"""Cart preview engine — ارائه‌ی اطلاعاتِ سبدِ خرید برایِ نمایشِ سریعِ
هدر/پنلِ شناور. دو حالت: ``count_link`` (فقط تعداد و لینک) و ``mini_cart``
(خلاصه‌ی اقلام + مجموع + لینک) — خانواده‌ها حالتِ پیش‌فرض را انتخاب
می‌کنند، اما موتور مشترک است.

هرگز Cart جدید نمی‌سازد — فقط سبدِ موجود را می‌خواند."""

from __future__ import annotations

from decimal import Decimal

from apps.cart.models import Cart, CartItem
from apps.cart.services.item_media import CART_ITEM_PREFETCH, cart_item_image


CART_PREVIEW_MODE_COUNT_LINK = "count_link"
CART_PREVIEW_MODE_MINI_CART = "mini_cart"
CART_PREVIEW_MODES = (CART_PREVIEW_MODE_COUNT_LINK, CART_PREVIEW_MODE_MINI_CART)


def get_cart_preview_data(request, *, mode: str = CART_PREVIEW_MODE_COUNT_LINK) -> dict:
    """داده‌ی پیش‌نمایشِ سبد — برایِ هر دو حالت، ``cart_count`` همیشه
    برمی‌گردد. در حالتِ ``mini_cart`` اقلام و مجموع هم اضافه می‌شوند.

    بهینه‌سازی: در ``count_link`` فقط یک aggregate انجام می‌شود (بدونِ
    select_related). در ``mini_cart`` حداکثر ۵ آیتم با محصول/تصویر
    pre-fetch می‌شوند."""
    from django.db.models import Sum

    cart = _resolve_existing_cart(request)
    if cart is None:
        return {
            "cart_preview_mode": mode,
            "cart_count": 0,
            "cart_items_preview": [],
            "cart_total": Decimal("0"),
            "cart_url": "",
            "cart_is_empty": True,
        }

    cart_count = cart.items.aggregate(total=Sum("quantity"))["total"] or 0

    if mode == CART_PREVIEW_MODE_MINI_CART and cart_count > 0:
        items = list(
            cart.items.select_related("product", "variant")
            .prefetch_related(*CART_ITEM_PREFETCH)
            .order_by("-created_at")[:5]
        )
        cart_total = sum(
            (item.unit_price * item.quantity) for item in cart.items.all()
        )
        items_preview = [
            {
                "id": item.pk,
                "product_name": item.product.name,
                "variant_label": _variant_label(item.variant),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.unit_price * item.quantity,
                "image_url": _item_image_url(item),
            }
            for item in items
        ]
    else:
        items_preview = []
        cart_total = Decimal("0")

    return {
        "cart_preview_mode": mode,
        "cart_count": cart_count,
        "cart_items_preview": items_preview,
        "cart_total": cart_total,
        "cart_is_empty": cart_count == 0,
    }


def _resolve_existing_cart(request) -> Cart | None:
    """سبدِ موجود را بدونِ ساختنِ سبدِ جدید برمی‌گرداند."""
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        return Cart.objects.filter(customer=request.user.customer_profile).first()
    session_key = request.session.session_key
    if session_key:
        return Cart.objects.filter(session_key=session_key, customer=None).first()
    return None


def _variant_label(variant) -> str:
    """برچسبِ نمایشیِ تنوع — اگر تنوعی ندارد، رشته‌ی خالی."""
    if variant is None:
        return ""
    parts = []
    for ov in getattr(variant, "_option_values_cache", []) or []:
        parts.append(ov.value)
    if not parts and hasattr(variant, "sku"):
        return variant.sku or ""
    return " / ".join(parts)


def _item_image_url(item) -> str:
    """URL تصویرِ کوچکِ این آیتم با همان مرجعِ واحدِ سبد/تسویه (``item_media``): تصویرِ تنوع ← کاورِ کالا ← بدونِ تصویر."""
    image = cart_item_image(item)
    return image.url if image else ""
