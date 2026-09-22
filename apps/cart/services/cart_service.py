"""لایه‌ی سرویس سبد خرید — دسترسی/ساخت سبد برای کاربر مهمان (session) و
کاربر واردشده، و افزودن قلم به سبد.
"""

from django.db import transaction

from apps.cart.models import Cart, CartItem
from apps.cart.services.gift_wrap_service import resolve_gift_wrap_selection
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


def add_item_to_cart(cart, product, variant, quantity, *, gift_wrap_requested=False):
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

        # CAT-002 حصارِ عضویت (membership fence) — پس از قفلِ Product/Variant
        # و *پیش از* هر خواندن/ساختِ CartItem، خودِ ردیفِ Cart را قفل کن.
        # این تضمین می‌کند یک درجِ CartItemِ جدید در این Cart هرگز نمی‌تواند
        # بینِ اسنپ‌شاتِ نهاییِ تسویه‌حساب و commit آن سر بخورد: تسویه‌حساب
        # همین ردیفِ Cart را قفل کرده و این درج تا آزادشدنش منتظر می‌ماند.
        # ترتیبِ قفل عمداً Product/Variant → Cart → CartItem است تا با
        # ``order_service._lock_cart_items_and_resolve_final_prices`` یکی
        # باشد و وارونگیِ بن‌بست (Cart→Product) رخ ندهد.
        Cart.objects.select_for_update().get(pk=cart.pk)

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
            product.store, requested=gift_wrap_requested,
        )
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
                item.save(update_fields=[
                    "quantity", "unit_price", "gift_wrap_selected", "gift_wrap_unit_price", "updated_at",
                ])
            else:
                item.save(update_fields=["quantity", "unit_price", "updated_at"])
        else:
            item = CartItem.objects.create(
                cart=cart, product=product, variant=variant, quantity=quantity, unit_price=unit_price,
                gift_wrap_selected=gift_wrap_selected, gift_wrap_unit_price=gift_wrap_unit_price,
            )
        return item


def reprice_cart_items(cart) -> bool:
    """اسنپ‌شاتِ ``unit_price`` هر قلمِ این سبد را با قیمتِ زنده‌ی کاتالوگ
    (``pricing_service.resolve_effective_price`` — تنها مرجعِ قیمتِ نهایی،
    بدونِ هیچ فرمولِ دومِ موازی) هم‌راستا می‌کند؛ اگر بین «افزودن به سبد» و
    «تسویه‌حساب» قیمتِ کالا/تنوع تغییر کرده باشد (CAT-002)، این تابع همان
    تغییر را روی ``CartItem.unit_price`` می‌نویسد تا هم نمایشِ سبد برای
    مشتری به‌روز شود و هم مرحله‌ی بعدیِ محاسبه‌ی جمعِ سبد
    (``apps.cart.services.pricing.cart_totals``) روی مقدارِ تازه کار کند.

    این تابع Order/Address/موجودی/کدِ تخفیف/سبد را هرگز لمس نمی‌کند — فقط
    اسنپ‌شاتِ نمایشیِ قیمتِ اقلامِ همینِ سبد را به‌روز می‌کند؛ تصمیمِ این‌که
    آیا با این قیمتِ به‌روزشده سفارش ساخته شود یا کاربر باید دوباره تأیید
    کند، به‌عهده‌ی فراخوانِ بالاتر (``checkout_service.finalize_order``) است.

    قفل‌گیری روی Product/ProductVariant سپس CartItem — دقیقاً همان ترتیبِ
    قفلِ ``add_item_to_cart`` (کالا/تنوع، سپس ردیفِ سبد) — تا هیچ‌گاه دو
    تراکنشِ هم‌زمان (این تابع در برابرِ یک افزودنِ هم‌زمانِ دیگر به همین
    کالا) در جهتِ معکوسی قفل نگیرند (کاهشِ ریسکِ deadlock). این تابع تراکنشِ
    خودش را باز/می‌بندد (``transaction.atomic``) و باید پیش از شروعِ
    تراکنشِ اصلیِ ساختِ سفارش (``checkout_service.finalize_order``) کامل و
    commit شده باشد — نه داخلِ همان تراکنش، چون اگر بعداً آن تراکنشِ بیرونی
    شکست بخورد/rollback شود، این اصلاحِ قیمتِ نمایشی هم باید همچنان برای
    کاربر باقی بماند تا صفحه‌ی تسویه‌حساب با قیمتِ درستِ به‌روز رندر شود.

    مثلِ ``order_service._lock_and_revalidate_items``: روی SQLite بدون خطا
    اجرا می‌شود اما معنایِ واقعیِ قفلِ سطحِ ردیف (و بنابراین ایمنیِ کاملِ
    concurrency) فقط روی PostgreSQL معتبر است.

    خروجی: ``True`` اگر حداقل یک قلم تغییر کرده باشد، وگرنه ``False``.
    """
    changed = False
    with transaction.atomic():
        # ابتدا یک خوانشِ بدون‌قفل برای شناساییِ Product/Variantهای درگیر —
        # قفل‌گیریِ واقعی طبقِ همان ترتیبِ ``add_item_to_cart``/
        # ``order_service._lock_and_revalidate_items`` انجام می‌شود: اول
        # Product سپس ProductVariant (به ترتیبِ pk)، و *بعد* ردیف‌های
        # CartItem — تا این تابع هرگز در جهتِ معکوسِ آن دو قفلِ دیگر قفل
        # نگیرد (کاهشِ ریسکِ deadlock بینِ تراکنش‌های هم‌زمان روی همان
        # کالاها).
        unlocked_items = list(cart.items.select_related("product", "variant"))

        product_ids = sorted({item.product_id for item in unlocked_items})
        locked_products = {
            p.pk: p
            for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
        } if product_ids else {}

        variant_ids = sorted({item.variant_id for item in unlocked_items if item.variant_id})
        locked_variants = {
            v.pk: v
            for v in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")
        } if variant_ids else {}

        items = list(
            cart.items.select_for_update().select_related("product", "variant").order_by("pk")
        )

        for item in items:
            product = locked_products.get(item.product_id)
            if product is None:
                # کالا دیگر موجود نیست — این تابع خودش هیچ خطایی صادر
                # نمی‌کند (بازاعتبارسنجیِ کاملِ موجودبودن/فعال‌بودن به‌عهده‌ی
                # ``order_service._lock_and_revalidate_items`` است)؛ فقط از
                # این قلم برای قیمت‌گذاری صرف‌نظر می‌کند.
                continue
            variant = locked_variants.get(item.variant_id) if item.variant_id else None

            fresh_price = resolve_effective_price(product, variant)
            if fresh_price != item.unit_price:
                item.unit_price = fresh_price
                item.save(update_fields=["unit_price", "updated_at"])
                changed = True

    return changed
