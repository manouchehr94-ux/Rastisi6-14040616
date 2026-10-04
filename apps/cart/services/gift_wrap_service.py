"""سرویسِ کادوپیچی — افزونه‌ی اختیاریِ سطحِ قلمِ سبد.

قیمت/در دسترس‌بودن/سیاستِ محاسبه همیشه سمتِ سرور (``ShopSettings`` +
تنظیماتِ هر کالا) حل می‌شود؛ هیچ view/تمپلیتی به قیمتِ ارسال‌شده‌ی کلاینت
اعتماد نمی‌کند. این ماژول تنها منبعِ حقیقتِ «کادوپیچی برای این کالا ممکن
است؟»، «چقدر؟» و «چگونه جمع زده شود؟» است — سبد، صفحه‌ی محصول، تسویه‌حساب
و ثبتِ سفارش همه از همین توابع استفاده می‌کنند.

سیاستِ صریحِ محاسبه (``ShopSettings.gift_wrap_pricing_scope``):

``per_unit``   قیمت × تعدادِ هر ردیفِ انتخاب‌شده (پیش‌فرض، سازگار با گذشته)
``per_line``   قیمت × ۱ به‌ازای هر ردیفِ انتخاب‌شده (مستقل از تعداد)
``per_order``  یک‌بار برای کلِ سفارش: بالاترین قیمتِ میانِ ردیف‌هایِ انتخاب‌شده

کادوپیچی مشمولِ مالیات نیست و فقط وقتی تخفیفِ کد روی آن اعمال می‌شود که
``Coupon.applies_to_gift_wrap`` روشن باشد.
"""

from __future__ import annotations

from decimal import Decimal

from apps.core.models import ShopSettings

SCOPE_PER_UNIT = ShopSettings.GiftWrapScope.PER_UNIT
SCOPE_PER_LINE = ShopSettings.GiftWrapScope.PER_LINE
SCOPE_PER_ORDER = ShopSettings.GiftWrapScope.PER_ORDER
DEFAULT_OPTION_CODE = "standard"
MAX_MESSAGE_LENGTH = 200


def _shop(store, shop=None) -> ShopSettings:
    return shop or ShopSettings.load(store=store)


def is_gift_wrap_available(store) -> bool:
    """آیا مدیرِ این Store کادوپیچی را (به‌صورت سراسری) فعال کرده."""
    return _shop(store).gift_wrap_available


def resolve_gift_wrap_price(store, product=None, *, shop=None) -> Decimal:
    """هزینه‌ی کادوپیچی — قیمتِ اختصاصیِ کالا (در صورت وجود) وگرنه قیمتِ عمومی."""
    shop = _shop(store, shop)
    if product is not None and product.gift_wrap_price is not None:
        return product.gift_wrap_price
    return shop.gift_wrap_price


def is_product_gift_wrap_eligible(product, *, shop=None) -> bool:
    shop = _shop(product.store, shop)
    return bool(shop.gift_wrap_available and product.gift_wrap_enabled)


def resolve_gift_wrap_selection(store, *, requested: bool, product=None) -> tuple[bool, Decimal]:
    """درخواستِ کلاینت را با پیکربندیِ واقعیِ Store و کالا تطبیق می‌دهد.

    اگر کادوپیچی (سراسری یا برایِ این کالا) ممکن نباشد همیشه ``(False, 0)``
    برمی‌گردد — صرف‌نظر از آنچه کلاینت خواسته."""
    if not requested:
        return False, Decimal("0")
    shop = _shop(store)
    if not shop.gift_wrap_available:
        return False, Decimal("0")
    if product is not None and not product.gift_wrap_enabled:
        return False, Decimal("0")
    return True, resolve_gift_wrap_price(store, product, shop=shop)


def clean_gift_message(message: str, *, shop: ShopSettings | None = None, store=None) -> str:
    """پیامِ کارت‌هدیه: برش، حذفِ کاراکترهایِ کنترلی، سقفِ ۲۰۰ نویسه؛ اگر
    Store امکانِ پیام را خاموش کرده باشد همیشه خالی."""
    shop = _shop(store, shop)
    if not shop.gift_wrap_message_enabled:
        return ""
    text = "".join(ch for ch in (message or "") if ch == "\n" or ch >= " ")
    text = " ".join(text.split())
    return text[:MAX_MESSAGE_LENGTH]


def effective_cart_line(item, shop: ShopSettings) -> tuple[bool, Decimal]:
    """وضعیتِ مؤثرِ کادوپیچیِ یک قلمِ سبد: انتخاب‌شده *و* هنوز مجاز (سراسری و
    کالا). اگر مدیر بعد از انتخاب، کادوپیچی را خاموش کرده باشد، هزینه حذف
    می‌شود (نه این‌که مشتری برای سرویسِ غیرفعال پول بدهد)."""
    if not item.gift_wrap_selected:
        return False, Decimal("0")
    if not shop.gift_wrap_available or not item.product.gift_wrap_enabled:
        return False, Decimal("0")
    return True, item.gift_wrap_unit_price


def gift_wrap_charge(lines: list[tuple[object, Decimal, int]], scope: str) -> Decimal:
    """جمعِ هزینه‌ی کادوپیچی. ``lines``: فهرستِ ``(کلید، قیمتِ واحد، تعداد)``
    فقط برایِ ردیف‌هایِ *مؤثر* (انتخاب‌شده و مجاز)."""
    if not lines:
        return Decimal("0")
    if scope == SCOPE_PER_ORDER:
        return max(price for _, price, _ in lines)
    if scope == SCOPE_PER_LINE:
        return sum((price for _, price, _ in lines), Decimal("0"))
    return sum((price * qty for _, price, qty in lines), Decimal("0"))


def gift_wrap_allocations(lines: list[tuple[object, Decimal, int]], scope: str) -> dict:
    """سهمِ هر ردیف از هزینه‌ی کادوپیچی (برایِ نمایش/استرداد). در ``per_order``
    کلِ هزینه به ردیفِ با بالاترین قیمت (اولین در تساوی) نسبت داده می‌شود."""
    result = {key: Decimal("0") for key, _, _ in lines}
    if not lines:
        return result
    if scope == SCOPE_PER_ORDER:
        key, price, _ = max(lines, key=lambda row: row[1])
        result[key] = price
        return result
    for key, price, qty in lines:
        result[key] = price if scope == SCOPE_PER_LINE else price * qty
    return result


def cart_gift_wrap_lines(items, shop: ShopSettings) -> list[tuple[object, Decimal, int]]:
    lines = []
    for item in items:
        active, price = effective_cart_line(item, shop)
        if active:
            lines.append((item.pk, price, item.quantity))
    return lines


def order_gift_wrap_lines(order_items) -> list[tuple[object, Decimal, int]]:
    return [
        (item.pk, item.gift_wrap_unit_price, item.quantity)
        for item in order_items if item.gift_wrap_selected
    ]


SCOPE_HINTS = {
    SCOPE_PER_UNIT: "به‌ازای هر عدد",
    SCOPE_PER_LINE: "برای هر ردیف سبد",
    SCOPE_PER_ORDER: "یک‌بار برای کل سفارش",
}


def storefront_context(store) -> dict:
    """داده‌ی نمایشیِ سرویسِ کادوپیچی برایِ تمپلیت‌هایِ سبد/محصول/تسویه‌حساب —
    فقط خواندنی؛ هیچ قیمتی از کلاینت نمی‌آید."""
    shop = ShopSettings.load(store=store)
    return {
        "available": shop.gift_wrap_available,
        "title": shop.gift_wrap_title or "کادوپیچی",
        "description": shop.gift_wrap_description,
        "image_url": shop.gift_wrap_image.url if shop.gift_wrap_image else "",
        "scope": shop.gift_wrap_pricing_scope,
        "scope_hint": SCOPE_HINTS.get(shop.gift_wrap_pricing_scope, ""),
        "message_enabled": shop.gift_wrap_message_enabled,
        "default_price": shop.gift_wrap_price,
    }


def annotate_cart_items(items, store) -> dict:
    """به هر قلمِ سبد ``gift_wrap_eligible`` و ``gift_wrap_price_now`` می‌افزاید و
    ``storefront_context`` را برمی‌گرداند."""
    shop = ShopSettings.load(store=store)
    for item in items:
        item.gift_wrap_eligible = bool(shop.gift_wrap_available and item.product.gift_wrap_enabled)
        item.gift_wrap_price_now = resolve_gift_wrap_price(store, item.product, shop=shop)
    return storefront_context(store)
