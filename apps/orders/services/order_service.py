"""لایه‌ی سرویس سفارش‌ها — ساخت سفارش از سبد و مدیریت گردش وضعیت.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶، قواعد ۷ تا ۹.
"""

import random
from decimal import Decimal

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
from apps.notifications.services import business_events
from apps.orders.services import shipping_service
from apps.orders.services.coupon_redemption_service import (
    CouponUnavailableError, lock_coupon, release_redemption, reserve_redemption,
)
from apps.orders.services.item_snapshot_service import build_item_snapshot
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


class PriceChangedError(ValueError):
    """مبلغِ نهاییِ معتبر با مبلغی که مشتری دید/تأیید کرد فرق دارد — سفارش ساخته نمی‌شود؛ مشتری باید مبلغِ
    جدید را ببیند و دوباره تأیید کند (هرگز مبلغِ متفاوت بی‌صدا دریافت نمی‌شود)."""

    def __init__(self, *, expected, actual):
        super().__init__("قیمت یا هزینه‌ی سفارش تغییر کرد")
        self.expected, self.actual = expected, actual


@transaction.atomic
def create_order_from_cart(
    cart, *, customer, vendor, address, shipping_method, payment_gateway,
    coupon=None, note="", store, idempotency_key="", expected_total=None,
):
    """سفارش را از روی سبد خرید می‌سازد و همه‌ی مبالغ را اسنپ‌شات می‌کند.

    ``store`` الزامی است — همان Store که فراخوان (معمولاً
    ``checkout_service.finalize_order``) از ``request.store`` resolve کرده؛
    برای قیمت‌گذاری (``cart_totals``) و پیامک ثبت سفارش استفاده می‌شود.

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
    # قیمتِ معتبرِ فعلی زیرِ قفلِ کالا/تنوع (نه اسنپ‌شاتِ کهنه‌ی سبد) — مبنای تنها محاسبه‌ی مبلغ.
    from apps.cart.services.pricing import sync_cart_prices

    sync_cart_prices(items, store=store, products=locked_products, variants=locked_variants)

    if coupon is not None:
        # قفلِ ردیفِ کد تا دو سفارشِ همزمانِ یک کد سریال شوند (Postgres)؛ سقفِ کل
        # علاوه بر این با compare-and-set اتمیک در reserve_redemption تضمین می‌شود.
        coupon = lock_coupon(coupon.pk)

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
        customer=customer, payment_gateway=payment_gateway,
    )
    if expected_total is not None and Decimal(expected_total) != totals["grand_total"]:
        raise PriceChangedError(expected=Decimal(expected_total), actual=totals["grand_total"])
    coupon_applied = totals["coupon_applied"]
    gift_wrap_active = totals["gift_wrap_allocations"]
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
                coupon=coupon if coupon_applied else None,
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
                gift_wrap_total=totals["gift_wrap_total"],
                gift_wrap_discount=totals["gift_wrap_discount"],
                gift_wrap_scope=totals["gift_wrap_scope"] if totals["gift_wrap_total"] else "",
            )
    except IntegrityError:
        if idempotency_key:
            existing = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing
        raise

    for item in items:
        product = locked_products[item.product_id]
        variant = locked_variants.get(item.variant_id) if item.variant_id else None
        # با pricing_service (نه product.final_price ساده) تا قیمتِ مستقلِ
        # تنوع (یا delta قدیمیِ آن) درست اعمال شود — بدونِ این، سفارش با
        # قیمتِ پایه‌ی کالا ثبت می‌شد، نه قیمتِ واقعیِ تنوعِ انتخاب‌شده.
        unit_price = resolve_effective_price(product, variant)
        tax_line = tax_lines_by_item.get(item.pk, {})
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            variant=variant,
            product_name=product.name,
            sku=product.sku,
            variant_label=_variant_label(variant),
            quantity=item.quantity,
            unit_price=unit_price,
            line_total=unit_price * item.quantity,
            discount_allocation=totals["coupon_allocations"].get(item.pk, 0) or 0,
            taxable_amount=tax_line.get("taxable_amount", 0) or 0,
            tax_class_code=tax_line.get("tax_class_code", ""),
            tax_class_name=tax_line.get("tax_class_name", ""),
            tax_rate_percent=tax_line.get("tax_rate_percent"),
            unit_tax=tax_line.get("unit_tax") or 0,
            total_tax=tax_line.get("total_tax") or 0,
            # کادوپیچی — دقیقاً همان اسنپ‌شاتِ سطحِ قلمِ سبد (نه بازخوانیِ
            # دوباره‌ی ShopSettings) تا اگر مدیر بین افزودن به سبد و ثبتِ
            # سفارش قیمتِ کادوپیچی را تغییر دهد، این ردیفِ تاریخی دست‌نخورده
            # بماند — دقیقاً همان استدلالِ unit_price بالا.
            # فقط وقتی کادوپیچی «مؤثر» است (انتخاب‌شده و هنوز مجاز) ثبت می‌شود —
            # همان تصمیمی که cart_totals برایِ مبلغِ سفارش گرفته.
            gift_wrap_selected=item.pk in gift_wrap_active,
            gift_wrap_unit_price=item.gift_wrap_unit_price if item.pk in gift_wrap_active else 0,
            gift_wrap_option_code=item.gift_wrap_option_code if item.pk in gift_wrap_active else "",
            gift_message=item.gift_message if item.pk in gift_wrap_active else "",
            attributes_snapshot=build_item_snapshot(product, variant),
        )
        # با قفلِ قبلی (_lock_and_revalidate_items)، شکستِ رزرو/مصرف عملاً
        # نباید پیش بیاید — reserve_inventory همچنان دوباره (به‌صورت اتمیک،
        # با قفلِ ردیف) موجودیِ در دسترس را بررسی می‌کند تا موجودی هرگز
        # منفی نشود. رزرو بلافاصله در همین تراکنش مصرف می‌شود (نگاه کنید
        # به ADR-39) — کلیدِ idempotency به‌ازای هر قلمِ سبد (نه کلِ سفارش)
        # است تا تلاشِ دوباره‌ی همان درخواست هرگز دوبار رزرو/مصرف نکند.
        try:
            reservation = reserve_inventory(
                store=store, product=product, variant=variant, quantity=item.quantity,
                cart=cart, source="order",
                idempotency_key=f"{idempotency_key}:{item.pk}" if idempotency_key else "",
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

    if coupon is not None and coupon_applied:
        try:
            reserve_redemption(
                coupon=coupon, order=order, customer=customer, discount_amount=totals["coupon_discount"],
            )
        except CouponUnavailableError as exc:
            raise ValueError(str(exc)) from exc

    transaction.on_commit(
        lambda: send_event_sms(
            SmsEvent.ORDER_PLACED, order.customer.phone, _order_sms_context(order), store=store
        )
    )
    business_events.order_created(order)

    return order


@transaction.atomic
def change_order_status(
    order: Order, to_status: str, *, by=None, note: str = "", tracking_code: str = "", store,
    suppress_sms: bool = False,
) -> Order:
    """وضعیت سفارش را تغییر می‌دهد و حتماً یک رکورد OrderStatusHistory می‌سازد.

    tracking_code فقط برای گذار به «ارسال شده» معنا دارد و روی سفارش ذخیره
    می‌شود تا در پیامک اطلاع‌رسانی درج شود. ``store`` الزامی است — همان
    Store که برای پیامکِ تغییر وضعیت استفاده می‌شود؛ این تابع خودش هرگز
    Store را دوباره از Host یا حالت سازگاری حدس نمی‌زند.
    """
    # قفلِ ردیفِ سفارش و خواندنِ وضعیتِ معتبر: لغو/پرداخت/job انقضای همزمان سریال می‌شوند
    # (callback پرداخت نیز همین ردیف را اول قفل می‌کند). شیِ فراخوان با دیتابیس همگام می‌شود.
    locked = Order.objects.select_for_update().only("status", "payment_status").get(pk=order.pk)
    order.status, order.payment_status = locked.status, locked.payment_status
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
        release_redemption(order, reason="order_canceled")
        record_audit_event(
            store=store, actor=by, action_code="order.cancelled",
            object_type="Order", object_id=order.pk, object_label=order.code,
            before={"status": from_status}, after={"status": to_status},
        )

    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=to_status, changed_by=by, note=note
    )

    business_events.order_status_changed(order, to_status)

    sms_event = STATUS_SMS_EVENTS.get(to_status)
    if sms_event and not suppress_sms:
        transaction.on_commit(
            lambda: send_event_sms(
                sms_event, order.customer.phone, _order_sms_context(order), store=store
            )
        )

    return order
