"""لایه‌ی سرویس سفارش‌ها — ساخت سفارش از سبد و مدیریت گردش وضعیت.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶، قواعد ۷ تا ۹.
"""

import random

from django.db import IntegrityError, transaction

from apps.cart.services.pricing import cart_totals
from apps.catalog.models import Product, ProductVariant
from apps.catalog.services.inventory_service import InsufficientStockError, restock_order
from apps.catalog.services.pricing_service import resolve_effective_price
from apps.catalog.services.reservation_service import (
    ReservationError,
    consume_inventory_reservation,
    reserve_inventory,
)
from apps.core.services.audit_service import record_audit_event
from apps.core.utils import format_toman
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.orders.services import shipping_service
from apps.sms.events import SmsEvent
from apps.sms.services.sms_service import send_event_sms

ORDER_CODE_PREFIX = "DM"

# رویداد پیامکی متناظر با هر وضعیت مقصد سفارش (پردازش/ارسال/تحویل/لغو).
STATUS_SMS_EVENTS = {
    Order.Status.PROCESSING: SmsEvent.ORDER_PROCESSING,
    Order.Status.SHIPPED: SmsEvent.ORDER_SHIPPED,
    Order.Status.DELIVERED: SmsEvent.ORDER_DELIVERED,
    Order.Status.CANCELED: SmsEvent.ORDER_CANCELED,
}


def _order_sms_context(order: Order) -> dict:
    return {
        "customer_name": order.customer.full_name,
        "order_code": order.code,
        "amount": format_toman(order.grand_total, with_unit=False),
        "tracking_code": order.tracking_code,
    }

ALLOWED_TRANSITIONS = {
    Order.Status.PENDING: {Order.Status.PROCESSING, Order.Status.CANCELED},
    Order.Status.PROCESSING: {Order.Status.SHIPPED, Order.Status.CANCELED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED, Order.Status.CANCELED},
    Order.Status.DELIVERED: set(),
    Order.Status.CANCELED: set(),
}

FINAL_STATUSES = {Order.Status.DELIVERED, Order.Status.CANCELED}


class LivePriceChangedError(ValueError):
    """CAT-002 (Blocker A) — قیمتِ زنده‌ی کاتالوگ در فاصله‌ی میانِ
    ``cart_service.reprice_cart_items`` (که مشتری آخرین‌بار آن را دید و
    تأیید کرد) و قفلِ نهاییِ ``CartItem`` در همینِ فراخوانیِ
    ``create_order_from_cart`` دوباره تغییر کرده است.

    این فراخوانی هرگز نباید در این حالت بی‌صدا با قیمتِ تازه‌تر سفارش
    بسازد — حتی اگر آن قیمتِ تازه‌تر «درست»‌تر باشد — چون مشتری هنوز آن را
    تأیید نکرده. فراخوانِ بالاتر (``checkout_service.finalize_order``) این
    خطا را می‌گیرد، سبد را دوباره با آخرین قیمت به‌روز می‌کند و از مشتری
    می‌خواهد صریحاً «دوباره پرداخت» را تأیید کند — دقیقاً همان قرارداد
    ``PriceChangeReviewRequired``. هیچ Order/Address/موجودی/کدِ تخفیفی در
    این مسیر لمس نشده (کل تراکنشِ اتمیکِ این تابع، و تراکنشِ بیرونی‌ترِ
    ``checkout_service``، رول‌بک می‌شوند)."""


class CartMembershipChangedError(ValueError):
    """CAT-002 (Blocker B) — مجموعه‌ی اقلامِ این سبد بینِ کشفِ اولیه
    (``cart.items`` در ابتدایِ ``create_order_from_cart``) و قفلِ نهاییِ
    ``CartItem`` (``select_for_update``) تغییر کرده — یک قلم اضافه یا حذف
    شده. به‌جایِ ساختِ یک Order ناقص (که یک قلمِ تازه‌اضافه‌شده را نادیده
    بگیرد یا برایِ قلمی که دیگر وجود ندارد ردیف بسازد)، این فراخوانی متوقف
    می‌شود — بدون هیچ Order/Address/موجودی/کدِ تخفیفی."""


def _generate_order_code() -> str:
    while True:
        code = f"{ORDER_CODE_PREFIX}-{random.randint(10000, 99999)}"
        if not Order.objects.filter(code=code).exists():
            return code


def _snapshot_address(address) -> dict:
    return {
        "receiver_name": address.receiver_name,
        "phone": address.phone,
        "province": address.province,
        "city": address.city,
        "postal_code": address.postal_code,
        "full_address": address.full_address,
    }


def _variant_label(variant) -> str:
    if variant is None:
        return ""
    return f"{variant.attribute}: {variant.value}"


def _resolve_fulfillment_warehouse(store):
    """انبارِ پیش‌فرضِ فعلیِ Store — همان انباری که ``_sync_warehouse_balance``
    برای این سفارش هدف گرفته (نگاه کنید به ADR-38/ADR-48). ``idempotent``
    است (اگر از قبل وجود داشته باشد چیزی نمی‌سازد)، پس فراخوانیِ دوباره
    بعد از این‌که رزرو همین انبار را در ``decrement_stock_for_order_item``
    استفاده کرده، هیچ اثرِ جانبی‌ای ندارد."""
    from apps.catalog.services.warehouse_service import provision_default_warehouse

    return provision_default_warehouse(store)


def _lock_and_revalidate_items(items, *, store):
    """قفل و بازاعتبارسنجی نهاییِ هر قلم سبد، درست پیش از ساخت سفارش (بخش ۷/۹).

    فقط بررسی cart_add (زمان افزودن به سبد) کافی نیست — بین افزودن به سبد و
    نهایی‌شدن سفارش ممکن است کالا/تنوع غیرفعال یا حذف شده باشد، یا موجودی
    توسط سفارش‌های هم‌زمان دیگر مصرف شده باشد. ``select_for_update()`` روی
    ردیف‌های Product/ProductVariant را به ترتیب پایدار (بر اساس pk) قفل
    می‌کند — هم برای جلوگیری از race شرط موجودی (بخش ۹) و هم برای این‌که دو
    تراکنش هم‌زمان با محصولات مشترک هرگز در ترتیب متفاوتی قفل نگیرند
    (کاهش ریسک deadlock). روی SQLite هم بدون خطا اجرا می‌شود (قفل واقعیِ
    سطح ردیف روی SQLite معنایی ندارد چون کل دیتابیس هنگام نوشتن قفل
    می‌شود، اما این تابع همان رفتار/تست را روی هر دو backend حفظ می‌کند —
    رفتار concurrency واقعی فقط روی PostgreSQL معتبر است، نه SQLite).
    """
    product_ids = sorted({item.product_id for item in items})
    locked_products = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk")
    }

    variant_ids = sorted({item.variant_id for item in items if item.variant_id})
    locked_variants = {
        v.pk: v
        for v in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")
    } if variant_ids else {}

    for item in items:
        product = locked_products.get(item.product_id)
        if product is None:
            raise ValueError("یکی از کالاهای سبد خرید دیگر موجود نیست")
        if product.store_id != store.pk:
            # هرگز نباید پیش بیاید — cart_add کالا را با همان Store scope
            # می‌کند — اما این‌جا هم به‌عنوان خط دفاعی آخر بررسی می‌شود تا
            # سفارشی هرگز از قلم‌های چندین Store مختلط ساخته نشود.
            raise ValueError(f"کالای «{product.name}» متعلق به این فروشگاه نیست")
        if product.status != Product.Status.ACTIVE:
            raise ValueError(f"کالای «{product.name}» دیگر برای فروش موجود نیست")

        variant = None
        if item.variant_id:
            variant = locked_variants.get(item.variant_id)
            if (
                variant is None
                or variant.product_id != product.pk
                or not variant.is_active
                or variant.store_id != store.pk
            ):
                raise ValueError(f"تنوع انتخاب‌شده برای «{product.name}» دیگر معتبر نیست")

        # موجودیِ مرجع برای اقلامِ دارای تنوع، موجودیِ خودِ تنوع است، نه
        # موجودیِ کالای والد — کالای دارای تنوع می‌تواند Product.stock صفر و
        # ProductVariant.stock مثبت داشته باشد (یا برعکس)؛ نگاه کنید به
        # ADR-31.
        available_stock = variant.stock if variant is not None else product.stock
        if item.quantity > available_stock:
            raise ValueError(f"موجودی «{product.name}» کافی نیست")

    return locked_products, locked_variants


def _cart_membership_signature(items):
    """امضایِ پایدارِ عضویتِ سبد — چندتاییِ مرتبِ ``(item.pk, product_id,
    variant_id, quantity)`` برایِ همه‌ی اقلام. اگر بینِ کشفِ اولیه و قفلِ
    نهایی هر قلمی اضافه/حذف شود یا هویتِ کالا/تنوع/تعدادِ یک قلم عوض شود،
    این امضا تغییر می‌کند (CAT-002 Blocker B/بخش ۳)."""
    return tuple(
        sorted(
            (item.pk, item.product_id, item.variant_id, item.quantity)
            for item in items
        )
    )


def _lock_cart_items_and_resolve_final_prices(
    items, *, locked_products, locked_variants, require_confirmed_prices=False,
):
    """CAT-002 — «یک اسنپ‌شاتِ نهایی»: بعد از قفلِ Product/ProductVariant
    (``_lock_and_revalidate_items``)، ردیف‌های CartItem را هم قفل می‌کند و
    برایِ هر قلم، قیمتِ نهایی را *فقط یک‌بار* از رویِ همان Product/Variant
    قفل‌شده با ``resolve_effective_price`` (تنها مرجعِ کانونی) محاسبه
    می‌کند.

    ردیف‌های قفل‌شده‌ی ``CartItem`` (نه شیءهای pre-lockِ ``items``) خودشان
    اسنپ‌شاتِ کانونی‌اند — این تابع همان ردیف‌های قفل‌شده را (به همراهِ
    قیمتِ نهاییِ هر کدام) برمی‌گرداند تا فراخوانِ بالاتر، هم برایِ
    اعتبارسنجیِ موجودی و هم برایِ ساختِ ``OrderItem``، از عضویت/کالا/تنوع/
    تعداد/قیمتِ همین ردیف‌های قفل‌شده استفاده کند — نه از شیءهای قدیمیِ
    pre-lock که ممکن است تعداد/عضویتِ stale داشته باشند (CAT-002 Blocker B).

    این تابع قلبِ رفعِ CAT-002 است: پیش از این PR، سرِ سفارش
    (``cart_totals`` که از ``item.unit_price`` می‌خواند) و هر ردیفِ سفارش
    (که با یک فراخوانیِ *مستقلِ دومِ* ``resolve_effective_price`` محاسبه
    می‌شد) می‌توانستند دو مقدارِ متفاوت ببینند — اگر بین «افزودن به سبد» و
    «قفل‌گیریِ نهایی» قیمتِ کاتالوگ تغییر کرده باشد.

    ``require_confirmed_prices`` (CAT-002 Blocker A):

    * ``False`` (پیش‌فرض — فراخوان‌های مستقیمِ سرویس/تست/seed): رفتارِ
      «auto-reprice» — اگر قیمتِ زنده با اسنپ‌شاتِ ``CartItem.unit_price``
      فرق داشت، همان‌جا ``CartItem`` به‌روزرسانی می‌شود تا Order نهایی هرگز
      داخلی ناهم‌خوان نباشد (header == lines).
    * ``True`` (مسیرِ مشتری‌محورِ HTTP از ``checkout_service.finalize_order``):
      اگر قیمتِ زنده با آخرین قیمتی که مشتری «دید و تأیید کرد»
      (``CartItem.unit_price``) فرق داشت، ``LivePriceChangedError`` صادر
      می‌شود — Order هرگز با قیمتِ تأییدنشده ساخته نمی‌شود؛ فراخوانِ بالاتر
      رول‌بک می‌کند، سبد را دوباره reprice می‌کند و از مشتری تأییدِ دوباره
      می‌خواهد (نگاه کنید به ``LivePriceChangedError``/
      ``checkout_service.PriceChangeReviewRequired``).

    خروجی: لیستِ چندتایی‌هایِ ``(locked_item, final_unit_price)`` — به
    ترتیبِ pk (همان ترتیبِ قفل).
    """
    from apps.cart.models import Cart, CartItem

    if not items:
        return []

    initial_signature = _cart_membership_signature(items)

    # CAT-002 Blocker B/بخش ۳ — قفلِ ردیفِ Cart به‌عنوان «حصارِ عضویت»
    # (membership fence). قفلِ سطحِ ردیفِ CartItem به‌تنهایی کافی نیست:
    # PostgreSQL می‌تواند یک CartItemِ *کاملاً جدید* را حتی پس از اجرایِ
    # ``SELECT ... FOR UPDATE`` روی ردیف‌های موجود درج کند (ردیفِ جدید هیچ
    # قفلِ ازپیش‌موجودی ندارد که روی آن منتظر بماند). با قفلِ خودِ ردیفِ Cart
    # پیش از خواندنِ اقلام، هر مسیرِ تولیدی‌ای که عضویتِ این Cart را عوض
    # می‌کند (``add_item_to_cart``ِ درج، ``merge_guest_cart``ِ انتقال) تا
    # پایانِ این تراکنش پشتِ همین قفل مسدود می‌ماند — پس هیچ درجِ/انتقالِ
    # هم‌زمانی نمی‌تواند بینِ اسنپ‌شاتِ نهایی و commit وارد شود.
    #
    # ترتیبِ قفل: Product/ProductVariant (در ``_lock_and_revalidate_items``)
    # → Cart → CartItem. تنها نویسنده‌های تولیدیِ عضویتِ CartItem
    # (``cart_service.add_item_to_cart``، ``cart_service.reprice_cart_items``،
    # ``auth_service.merge_guest_cart``) همگی همین ترتیب را رعایت می‌کنند،
    # پس وارونگیِ بن‌بست (Cart→Product در برابر Product→Cart) رخ نمی‌دهد.
    cart_id = items[0].cart_id
    # قفلِ حصارِ عضویت روی خودِ ردیفِ Cart — هویتِ معتبرِ Cart از همین‌جا
    # می‌آید، نه صرفاً ``items[0].cart_id`` بی‌قفل.
    locked_cart = Cart.objects.select_for_update().get(pk=cart_id)

    locked_items = list(
        CartItem.objects.select_for_update()
        .filter(cart_id=locked_cart.pk)
        .select_related("product", "variant")
        .order_by("pk")
    )

    locked_signature = _cart_membership_signature(locked_items)
    if locked_signature != initial_signature:
        raise CartMembershipChangedError(
            "اقلام سبد خرید حین نهایی‌سازی سفارش تغییر کرد؛ لطفاً دوباره تلاش کنید"
        )

    resolved = []
    for locked_item in locked_items:
        product = locked_products[locked_item.product_id]
        variant = locked_variants.get(locked_item.variant_id) if locked_item.variant_id else None
        # با pricing_service (نه product.final_price ساده) تا قیمتِ مستقلِ
        # تنوع (یا delta قدیمیِ آن) درست اعمال شود.
        fresh_price = resolve_effective_price(product, variant)

        if fresh_price != locked_item.unit_price:
            if require_confirmed_prices:
                # CAT-002 Blocker A — قیمتِ زنده با آخرین قیمتِ تأییدشده‌ی
                # مشتری فرق دارد؛ هرگز Order را با قیمتِ تأییدنشده نساز.
                raise LivePriceChangedError(
                    "قیمتِ زنده‌ی کاتالوگ با آخرین قیمتِ تأییدشده‌ی سبد فرق دارد"
                )
            locked_item.unit_price = fresh_price
            locked_item.save(update_fields=["unit_price", "updated_at"])

        resolved.append((locked_item, fresh_price))

    return resolved


@transaction.atomic
def create_order_from_cart(
    cart, *, customer, vendor, address, shipping_method, payment_gateway,
    coupon=None, note="", store, idempotency_key="", require_confirmed_prices=False,
):
    """سفارش را از روی سبد خرید می‌سازد و همه‌ی مبالغ را اسنپ‌شات می‌کند.

    ``store`` الزامی است — همان Store که فراخوان (معمولاً
    ``checkout_service.finalize_order``) از ``request.store`` resolve کرده؛
    برای قیمت‌گذاری (``cart_totals``) و پیامک ثبت سفارش استفاده می‌شود.

    ``require_confirmed_prices`` (CAT-002 Blocker A) — وقتی ``True`` (مسیرِ
    مشتری‌محورِ HTTP)، اگر قیمتِ زنده‌ی کاتالوگ زیرِ قفلِ نهایی با آخرین
    قیمتی که مشتری تأیید کرده فرق داشته باشد، ``LivePriceChangedError``
    صادر می‌شود و هیچ Orderی ساخته نمی‌شود. فراخوان‌های مستقیمِ سرویس/تست
    (پیش‌فرض ``False``) رفتارِ auto-repriceِ منسجم را نگه می‌دارند.

    ``idempotency_key`` اختیاری است (خالی یعنی بدون کنترل idempotency — برای
    فراخوان‌های مستقیم/تست). وقتی مقدار دارد (معمولاً
    ``Cart.checkout_token`` — نگاه کنید به
    ``checkout_service.get_or_create_checkout_token``)، این تابع:

    * ابتدا بررسی می‌کند آیا سفارشی با همین کلید از قبل ساخته شده — اگر بله،
      همان سفارش موجود را برمی‌گرداند (بدون کاهش دوباره‌ی موجودی، بدون قلم
      تکراری) — این حالت «ارسال دوباره‌ی متوالی» (double-click بعد از این‌که
      درخواست اول کامل شده) را می‌پوشاند؛
    * سپس، هنگام درج خودِ Order، به یکتاییِ سطح دیتابیس
      (``uniq_order_idempotency_key_when_set``) تکیه می‌کند: اگر هم‌زمان دو
      درخواست با همین کلید هر دو از بررسی اول عبور کرده باشند (race واقعی)،
      فقط یکی می‌تواند درج را کامل کند؛ درخواستِ بازنده با ``IntegrityError``
      داخل یک savepoint (نه کل تراکنش) مواجه و بلافاصله همان سفارشِ برنده را
      واکشی و برمی‌گرداند — بدون تلاش دوباره برای ساخت قلم‌ها یا کاهش موجودی.
    """
    if idempotency_key:
        existing = Order.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    if vendor.store_id != store.pk:
        # حفظ عدم‌تطابق Order.store/Order.vendor.store در همان مسیر تولید
        # Production (بخش ۱ — این تنها مسیر ساخت Order در Production است).
        raise ValueError("این فروشنده متعلق به این فروشگاه نیست")

    if coupon is not None and coupon.store_id != store.pk:
        # نگاه کنید به ADR-32 — کد تخفیف اکنون Store-owned است؛ این خط
        # دفاعی آخر تضمین می‌کند حتی اگر لایه‌ی بالاتر (checkout_service)
        # قبلاً کوپن را با store فیلتر کرده باشد، هیچ سفارشی با کوپنِ
        # فروشگاه دیگری ساخته نمی‌شود.
        raise ValueError("این کد تخفیف متعلق به این فروشگاه نیست")

    if shipping_method.store_id != store.pk:
        # نگاه کنید به ADR-43 — یک POST دستکاری‌شده هرگز نمی‌تواند روشِ
        # ارسالِ فروشگاه دیگری را بنشاند، حتی اگر لایه‌ی بالاتر
        # (checkout_service) قبلاً همین بررسی را انجام داده باشد.
        raise ValueError("این روش ارسال متعلق به این فروشگاه نیست")
    if not shipping_method.is_active:
        raise ValueError("این روش ارسال دیگر فعال نیست")

    items = list(cart.items.select_related("product", "variant"))
    if not items:
        raise ValueError("سبد خرید خالی است")

    locked_products, locked_variants = _lock_and_revalidate_items(items, store=store)

    # CAT-002 — یک اسنپ‌شاتِ نهاییِ منسجم: زیرِ همان قفلِ Product/Variant
    # بالا، ردیف‌های ``CartItem`` قفل می‌شوند و *همان ردیف‌های قفل‌شده*
    # (Blocker B) برایِ عضویت/کالا/تنوع/تعداد/قیمت به‌عنوان اسنپ‌شاتِ
    # کانونی برگردانده می‌شوند. ``require_confirmed_prices`` (Blocker A):
    # در مسیرِ مشتری‌محور، اگر قیمتِ زنده با قیمتِ تأییدشده فرق داشته باشد،
    # ``LivePriceChangedError`` صادر می‌شود — نگاه کنید به
    # ``_lock_cart_items_and_resolve_final_prices`` برایِ توضیحِ کامل.
    locked_lines = _lock_cart_items_and_resolve_final_prices(
        items, locked_products=locked_products, locked_variants=locked_variants,
        require_confirmed_prices=require_confirmed_prices,
    )
    # پس از این نقطه، هیچ‌کس به شیءهای pre-lockِ ``items`` تکیه نمی‌کند —
    # ``locked_lines`` تنها اسنپ‌شاتِ معتبر است (Blocker B).

    province = address.province if address is not None else ""
    city = address.city if address is not None else ""
    postal_code = address.postal_code if address is not None else ""

    if not shipping_method.is_pickup:
        # بازمحاسبه‌ی سمتِ سرورِ در دسترس‌بودنِ روشِ ارسال برای این مقصد —
        # هرگز به گزینه‌ی ارسال‌شده‌ی کلاینت اعتماد نمی‌شود (ADR-43). روشِ
        # تحویلِ حضوری از این بررسیِ منطقه‌ای معاف است چون به آدرسِ مقصد
        # وابسته نیست.
        available = shipping_service.get_available_shipping_methods(
            store, province=province, city=city, postal_code=postal_code,
        )
        if shipping_method not in available:
            raise ValueError("این روش ارسال برای مقصدِ انتخاب‌شده در دسترس نیست")

    totals = cart_totals(
        cart, store=store, coupon=coupon, shipping_method=shipping_method,
        province=province, city=city, postal_code=postal_code,
    )
    tax_lines_by_item = {line["item_ref"]: line for line in totals["tax_lines"]}
    shipping_zone = totals["shipping_zone"]
    shipping_rate_rule = totals["shipping_rate_rule"]

    try:
        with transaction.atomic():
            order = Order.objects.create(
                code=_generate_order_code(),
                store=store,
                customer=customer,
                vendor=vendor,
                idempotency_key=idempotency_key,
                address=_snapshot_address(address),
                shipping_method=shipping_method,
                payment_gateway=payment_gateway,
                coupon=coupon,
                items_total=totals["items_total"],
                product_discount=totals["product_discount"],
                coupon_discount=totals["coupon_discount"],
                shipping_cost=totals["shipping_cost"],
                tax=totals["tax"],
                grand_total=totals["grand_total"],
                note=note,
                shipping_method_name=shipping_method.name,
                shipping_method_code=shipping_method.slug,
                shipping_zone_name=shipping_zone.name if shipping_zone else "",
                shipping_zone_code=shipping_zone.code if shipping_zone else "",
                shipping_rate_rule_label=shipping_rate_rule.name if shipping_rate_rule else "",
                min_delivery_days=shipping_method.min_delivery_days,
                max_delivery_days=shipping_method.max_delivery_days,
                is_pickup=shipping_method.is_pickup,
                pickup_warehouse_name=(
                    shipping_method.pickup_warehouse.name if shipping_method.pickup_warehouse_id else ""
                ),
                pickup_address=(
                    shipping_method.pickup_warehouse.address if shipping_method.pickup_warehouse_id else ""
                ),
                prices_include_tax=totals["prices_include_tax"],
                tax_rounding_policy=totals["tax_rounding_policy"],
                shipping_tax=totals["shipping_tax"],
            )
    except IntegrityError:
        if idempotency_key:
            existing = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing
        raise

    for locked_item, unit_price in locked_lines:
        product = locked_products[locked_item.product_id]
        variant = locked_variants.get(locked_item.variant_id) if locked_item.variant_id else None
        # CAT-002 Blocker B — همه‌ی مقادیرِ این ردیف از خودِ ردیفِ *قفل‌شده‌ی*
        # ``CartItem`` می‌آید (تعداد، هویتِ کالا/تنوع، قیمتِ واحد) — نه از شیءِ
        # pre-lockِ ``items`` که ممکن است تعدادِ stale داشته باشد. قیمتِ واحد
        # همان مقداری است که چند سطر بالاتر (پیش از ``cart_totals``) *یک‌بار*
        # زیرِ همان قفل محاسبه شد؛ سرِ سفارش (``cart_totals`` از رویِ همین
        # ``CartItem.unit_price`` قفل‌شده) و این ردیف تضمیناً یکی‌اند.
        tax_line = tax_lines_by_item.get(locked_item.pk, {})
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            product_name=product.name,
            sku=product.sku,
            variant_label=_variant_label(variant),
            quantity=locked_item.quantity,
            unit_price=unit_price,
            line_total=unit_price * locked_item.quantity,
            discount_allocation=tax_line.get("discount_allocation", 0) or 0,
            taxable_amount=tax_line.get("taxable_amount", 0) or 0,
            tax_class_code=tax_line.get("tax_class_code", ""),
            tax_class_name=tax_line.get("tax_class_name", ""),
            tax_rate_percent=tax_line.get("tax_rate_percent"),
            unit_tax=tax_line.get("unit_tax") or 0,
            total_tax=tax_line.get("total_tax") or 0,
            # کادوپیچی — دقیقاً همان اسنپ‌شاتِ سطحِ قلمِ سبدِ قفل‌شده (نه
            # بازخوانیِ دوباره‌ی ShopSettings) تا اگر مدیر بین افزودن به سبد و
            # ثبتِ سفارش قیمتِ کادوپیچی را تغییر دهد، این ردیفِ تاریخی
            # دست‌نخورده بماند — دقیقاً همان استدلالِ unit_price بالا.
            gift_wrap_selected=locked_item.gift_wrap_selected,
            gift_wrap_unit_price=locked_item.gift_wrap_unit_price,
        )
        # با قفلِ قبلی (_lock_and_revalidate_items)، شکستِ رزرو/مصرف عملاً
        # نباید پیش بیاید — reserve_inventory همچنان دوباره (به‌صورت اتمیک،
        # با قفلِ ردیف) موجودیِ در دسترس را بررسی می‌کند تا موجودی هرگز
        # منفی نشود. رزرو بلافاصله در همین تراکنش مصرف می‌شود (نگاه کنید
        # به ADR-39) — کلیدِ idempotency به‌ازای هر قلمِ سبد (نه کلِ سفارش)
        # است تا تلاشِ دوباره‌ی همان درخواست هرگز دوبار رزرو/مصرف نکند.
        try:
            reservation = reserve_inventory(
                store=store, product=product, variant=variant, quantity=locked_item.quantity,
                cart=cart, source="order",
                idempotency_key=f"{idempotency_key}:{locked_item.pk}" if idempotency_key else "",
                ttl_minutes=None,
            )
            consume_inventory_reservation(reservation, order=order)
        except (InsufficientStockError, ReservationError) as exc:
            raise ValueError(str(exc)) from exc

        # اسنپ‌شاتِ انبارِ تأمین‌کننده — همان انبارِ پیش‌فرضِ فعلی (نگاه کنید
        # به ADR-38: همه‌ی عملیاتِ موجودیِ ناشی از سفارش همیشه انبارِ
        # پیش‌فرض را هدف می‌گیرند) — نگاه کنید به ADR-48.
        order_item.fulfillment_warehouse = _resolve_fulfillment_warehouse(store)
        order_item.save(update_fields=["fulfillment_warehouse", "updated_at"])

    OrderStatusHistory.objects.create(
        order=order, from_status="", to_status=order.status, note="سفارش ثبت شد"
    )

    if coupon is not None and totals["coupon_applied"]:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count"])

    transaction.on_commit(
        lambda: send_event_sms(
            SmsEvent.ORDER_PLACED, order.customer.phone, _order_sms_context(order), store=store
        )
    )

    return order


@transaction.atomic
def change_order_status(
    order: Order, to_status: str, *, by=None, note: str = "", tracking_code: str = "", store
) -> Order:
    """وضعیت سفارش را تغییر می‌دهد و حتماً یک رکورد OrderStatusHistory می‌سازد.

    tracking_code فقط برای گذار به «ارسال شده» معنا دارد و روی سفارش ذخیره
    می‌شود تا در پیامک اطلاع‌رسانی درج شود. ``store`` الزامی است — همان
    Store که برای پیامکِ تغییر وضعیت استفاده می‌شود؛ این تابع خودش هرگز
    Store را دوباره از Host یا حالت سازگاری حدس نمی‌زند.
    """
    from_status = order.status

    if from_status in FINAL_STATUSES:
        raise ValueError(f"سفارش در وضعیت نهایی «{order.get_status_display()}» است و قابل تغییر نیست")

    if to_status == from_status:
        raise ValueError("وضعیت جدید با وضعیت فعلی یکسان است")

    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(f"گذار از «{from_status}» به «{to_status}» مجاز نیست")

    update_fields = ["status", "updated_at"]
    order.status = to_status
    if to_status == Order.Status.SHIPPED and tracking_code:
        order.tracking_code = tracking_code
        update_fields.append("tracking_code")
    order.save(update_fields=update_fields)

    if to_status == Order.Status.CANCELED:
        # لغو یک سفارشِ PENDING/PROCESSING/SHIPPED باید موجودیِ کاهش‌یافته
        # هنگام ثبت را بازگرداند — پیش از این PR، لغو سفارش هرگز موجودی را
        # بازنمی‌گرداند (نگاه کنید به ADR-31). ``CANCELED`` یک وضعیتِ نهاییِ
        # بدونِ گذارِ خروجی است، پس این مسیر برای هر سفارش حداکثر یک‌بار اجرا
        # می‌شود.
        restock_order(store=store, order=order, actor=by)
        record_audit_event(
            store=store, actor=by, action_code="order.cancelled",
            object_type="Order", object_id=order.pk, object_label=order.code,
            before={"status": from_status}, after={"status": to_status},
        )

    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=to_status, changed_by=by, note=note
    )

    sms_event = STATUS_SMS_EVENTS.get(to_status)
    if sms_event:
        transaction.on_commit(
            lambda: send_event_sms(
                sms_event, order.customer.phone, _order_sms_context(order), store=store
            )
        )

    return order
