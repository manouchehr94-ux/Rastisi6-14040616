"""لایه‌ی سرویس سبد خرید — دسترسی/ساخت سبد برای کاربر مهمان (session) و
کاربر واردشده، و افزودن قلم به سبد.
"""

from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.cart.services.gift_wrap_service import (
    DEFAULT_OPTION_CODE, clean_gift_message, resolve_gift_wrap_selection,
)
from apps.catalog.models import Product, ProductVariant
from apps.catalog.services.pricing_service import resolve_effective_price


class UnavailableStockError(Exception):
    """کالا/تنوعِ درخواستی موجودیِ کافی برای افزودن (یا افزایشِ) به سبد ندارد.

    این فقط یک پیشْ‌بررسیِ سریع در لحظه‌ی افزودن به سبد است — مرجعِ نهایی و
    اتمیکِ کاهشِ موجودی همچنان در لحظه‌ی ثبتِ سفارش
    (``apps.orders.services.order_service`` + ``inventory_service``، با
    ``select_for_update``) اجرا می‌شود؛ چون بین لحظه‌ی افزودن به سبد و
    لحظه‌ی پرداخت ممکن است موجودی توسط سفارش‌های دیگر تغییر کند. این
    بررسی فقط تجربه‌ی کاربری را بهبود می‌دهد و از ثبتِ آشکارِ یک کالای
    ناموجود در سبد جلوگیری می‌کند؛ به‌تنهایی ضامنِ نهاییِ عدم-فروش‌بیش‌از-موجودی
    نیست.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _customer_or_none(request):
    if request.user.is_authenticated:
        return getattr(request.user, "customer_profile", None)
    return None


def get_cart(request, create=False):
    """سبد فعلی کاربر (مهمان بر اساس session یا کاربر واردشده) را برمی‌گرداند.

    اگر create=True باشد و سبدی موجود نباشد، یکی ساخته می‌شود (و در صورت
    نیاز، یک session جدید برای مهمان ایجاد می‌شود).
    """
    customer = _customer_or_none(request)
    if customer is not None:
        if create:
            cart, _ = Cart.objects.get_or_create(customer=customer)
            return cart
        return Cart.objects.filter(customer=customer).first()

    session_key = request.session.session_key
    if not session_key:
        if not create:
            return None
        request.session.create()
        session_key = request.session.session_key

    if create:
        cart, _ = Cart.objects.get_or_create(session_key=session_key, customer=None)
        return cart
    return Cart.objects.filter(session_key=session_key, customer=None).first()


def add_item_to_cart(cart, product, variant, quantity, *, gift_wrap_requested=False, gift_message=""):
    """محصول (و در صورت وجود، تنوع) را به سبد اضافه می‌کند یا تعداد را افزایش می‌دهد.

    قیمتِ واحد همیشه از ``pricing_service.resolve_effective_price`` محاسبه
    می‌شود (نه ``product.final_price`` ساده) تا قیمتِ تنوعِ انتخاب‌شده — چه
    delta-based قدیمی، چه مستقلِ جدید — درست اعمال شود؛ دقیقاً همان تابعی
    که فروشگاه برای نمایشِ قیمت استفاده می‌کند.

    اعتبارسنجیِ موجودی (Checkpoint — server-side stock enforcement):
    ``quantity`` باید یک عددِ صحیحِ مثبت باشد و مجموعِ تعدادِ درخواستی +
    تعدادِ از قبل موجودِ همینِ کالا/تنوع در همینِ سبد نباید از موجودیِ
    در دسترس (``variant.stock`` اگر تنوع انتخاب شده، وگرنه ``product.stock``)
    بیشتر شود. کالای غیرفعال/بدون‌موجودی هرگز به سبد اضافه نمی‌شود؛ به‌جای
    سکوت یا کِلَمپ‌کردنِ بی‌صدا، ``UnavailableStockError`` صادر می‌شود تا
    فراخواننده (view) بتواند خطا را صریحاً به کاربر نشان دهد.

    ``select_for_update`` روی ردیفِ کالا/تنوع گرفته می‌شود تا دو درخواستِ
    همزمان (مثلاً دو تبِ باز یا دو کاربر) نتوانند مجموعاً بیش از موجودیِ
    واقعی را در سبدهای خودشان رزرو کنند — چون این تابع همیشه باید در یک
    تراکنش (``transaction.atomic``) اجرا شود.

    ``gift_wrap_requested`` — درخواستِ کلاینت برایِ کادوپیچیِ همین قلم
    (toranj_gifting: ``optional_addon_checkbox_updates_total``). همیشه با
    ``gift_wrap_service.resolve_gift_wrap_selection`` طبقِ پیکربندیِ واقعیِ
    Store (``ShopSettings.gift_wrap_available``/``gift_wrap_price``) تطبیق
    داده می‌شود — یک Storeای که کادوپیچی را فعال نکرده، هرگز حتی اگر
    کلاینت درخواست کند، هزینه‌ای برای آن ثبت نمی‌کند.
    """
    if not isinstance(quantity, int) or quantity <= 0:
        raise UnavailableStockError("تعداد درخواستی نامعتبر است.")

    with transaction.atomic():
        # قفلِ ردیفِ کالا/تنوع — از race condition میانِ دو افزودنِ همزمان به
        # سبدهای مختلف جلوگیری می‌کند تا خوانشِ stock هرگز stale نباشد.
        if variant is not None:
            variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)
            is_purchasable = variant.is_active and variant.stock > 0
            available_stock = variant.stock
        else:
            product = Product.objects.select_for_update().get(pk=product.pk)
            is_purchasable = product.status == Product.Status.ACTIVE and product.stock > 0
            available_stock = product.stock

        if not is_purchasable:
            raise UnavailableStockError("این کالا در حال حاضر موجود نیست.")

        item = cart.items.select_for_update().filter(product=product, variant=variant).first()
        existing_quantity = item.quantity if item else 0
        requested_total = existing_quantity + quantity

        if requested_total > available_stock:
            raise UnavailableStockError(
                f"موجودیِ «{product.name}» کافی نیست. حداکثرِ قابل‌افزودن: "
                f"{max(available_stock - existing_quantity, 0)}"
            )

        unit_price = resolve_effective_price(product, variant)
        gift_wrap_selected, gift_wrap_unit_price = resolve_gift_wrap_selection(
            product.store, requested=gift_wrap_requested, product=product,
        )
        gift_message = clean_gift_message(gift_message, store=product.store) if gift_wrap_selected else ""
        if item:
            item.quantity = requested_total
            item.unit_price = unit_price
            # کادوپیچی فقط وقتی این افزودنِ صریح آن را درخواست کرده به‌روز
            # می‌شود — یک افزودنِ دومِ «بدونِ» چک‌باکس، انتخابِ قبلیِ کادوپیچی
            # را بی‌صدا لغو نمی‌کند؛ فقط یک درخواستِ صریحِ «لغوِ کادوپیچی»
            # (که از مسیرِ دیگری، مثلاً ویرایشِ قلمِ سبد، می‌آید) آن را عوض
            # می‌کند.
            if gift_wrap_requested:
                item.gift_wrap_selected = gift_wrap_selected
                item.gift_wrap_unit_price = gift_wrap_unit_price
                item.gift_wrap_option_code = DEFAULT_OPTION_CODE if gift_wrap_selected else ""
                item.gift_message = gift_message
                item.save(update_fields=[
                    "quantity", "unit_price", "gift_wrap_selected", "gift_wrap_unit_price",
                    "gift_wrap_option_code", "gift_message", "updated_at",
                ])
            else:
                item.save(update_fields=["quantity", "unit_price", "updated_at"])
        else:
            item = CartItem.objects.create(
                cart=cart, product=product, variant=variant, quantity=quantity, unit_price=unit_price,
                gift_wrap_selected=gift_wrap_selected, gift_wrap_unit_price=gift_wrap_unit_price,
                gift_wrap_option_code=DEFAULT_OPTION_CODE if gift_wrap_selected else "",
                gift_message=gift_message,
            )
        return item


def set_item_gift_wrap(item, *, selected: bool, message: str = "") -> bool:
    """انتخاب/لغوِ کادوپیچی (و پیامِ کارت) برایِ یک قلمِ موجود در سبد — همیشه با
    پیکربندیِ واقعیِ Store/کالا تطبیق داده می‌شود (قیمت از سرور). نتیجه:
    ``True`` اگر کادوپیچی در پایان روشن است."""
    sel, price = resolve_gift_wrap_selection(item.product.store, requested=selected, product=item.product)
    item.gift_wrap_selected = sel
    item.gift_wrap_unit_price = price
    item.gift_wrap_option_code = DEFAULT_OPTION_CODE if sel else ""
    item.gift_message = clean_gift_message(message, store=item.product.store) if sel else ""
    item.save(update_fields=[
        "gift_wrap_selected", "gift_wrap_unit_price", "gift_wrap_option_code", "gift_message", "updated_at",
    ])
    return sel
