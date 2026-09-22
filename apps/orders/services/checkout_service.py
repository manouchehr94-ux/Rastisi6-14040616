"""لایه‌ی سرویس تسویه‌حساب — مرحله‌ی ۱ (سبد و آدرس).

انتخاب روش ارسال/پرداخت، کد تخفیف و اطلاعات گیرنده برای کاربر مهمان یا واردشده
در session نگه‌داری می‌شود (سفارش واقعی در مرحله‌ی بعد از روی همین داده ساخته
می‌شود). محاسبه‌ی مبالغ همیشه از طریق apps.cart.services.pricing.cart_totals
انجام می‌گیرد؛ این ماژول فقط انتخاب‌های کاربر را حل و کانتکست صفحه را می‌سازد.
"""

import logging
import secrets
from decimal import Decimal

from django.db import transaction

from apps.cart.models import Coupon
from apps.cart.services.cart_service import reprice_cart_items
from apps.cart.services.pricing import cart_totals, coupon_is_applicable
from apps.catalog.services.pricing_service import resolve_regular_price
from apps.customers.models import Address
from apps.orders.models import Order, PaymentGateway
from apps.orders.services import shipping_service
from apps.stores.resolution import resolve_store_for_service

logger = logging.getLogger(__name__)

CHECKOUT_TOKEN_BYTES = 32

SESSION_KEY = "checkout"

ADDRESS_FIELDS = ["receiver_name", "phone", "province", "city", "postal_code", "full_address", "note"]

EMPTY_TOTALS = {
    "items_total": Decimal("0"),
    "product_discount": Decimal("0"),
    "coupon_discount": Decimal("0"),
    "shipping_cost": Decimal("0"),
    "shipping_zone": None,
    "shipping_rate_rule": None,
    "free_shipping": False,
    "tax": Decimal("0"),
    "shipping_tax": Decimal("0"),
    "tax_lines": [],
    "prices_include_tax": False,
    "tax_rounding_policy": "",
    "grand_total": Decimal("0"),
    "coupon_applied": False,
}


def _state(request) -> dict:
    return request.session.setdefault(SESSION_KEY, {})


def get_address(request) -> dict:
    return _state(request).get("address", {})


def save_address(request, cleaned_data) -> None:
    state = _state(request)
    state["address"] = {field: cleaned_data.get(field, "") for field in ADDRESS_FIELDS}
    request.session.modified = True


def active_shipping_methods(*, store, address: dict | None = None):
    """روش‌های ارسالِ فعالِ این Store — اگر ``address`` داده شود (یا از قبل
    در نشست ذخیره شده باشد)، روش‌های محدود به یک منطقه (``zone``) فقط وقتی
    برگردانده می‌شوند که آدرس با همان منطقه تطبیق داشته باشد؛ روش‌های بدونِ
    منطقه (``zone=None`` — هر ردیفِ موجود پیش از checkpoint 3B) همیشه
    سراسری‌اند، مستقل از آدرس (نگاه کنید به ADR-41)."""
    address = address or {}
    return shipping_service.get_available_shipping_methods(
        store,
        province=address.get("province", ""), city=address.get("city", ""),
        postal_code=address.get("postal_code", ""),
    )


def active_payment_gateways(*, store):
    return list(PaymentGateway.objects.filter(is_active=True, store=store))


def get_selected_shipping_method(request):
    store = resolve_store_for_service(request)
    methods = active_shipping_methods(store=store, address=get_address(request))
    if not methods:
        return None
    selected_id = _state(request).get("shipping_method_id")
    for method in methods:
        if method.pk == selected_id:
            return method
    return methods[0]


def set_shipping_method(request, method_id) -> None:
    """یک POST دستکاری‌شده هرگز نمی‌تواند روش ارسال متعلق به Store دیگری یا
    خارج از منطقه‌ی آدرسِ فعلی را انتخاب کند — استخر گزینه‌های مجاز همیشه
    با ``store``/منطقه فیلتر می‌شود."""
    store = resolve_store_for_service(request)
    methods = active_shipping_methods(store=store, address=get_address(request))
    method = next((m for m in methods if m.pk == method_id), None)
    if method:
        _state(request)["shipping_method_id"] = method.pk
        request.session.modified = True


def get_selected_payment_gateway(request):
    store = resolve_store_for_service(request)
    gateways = active_payment_gateways(store=store)
    if not gateways:
        return None
    selected_id = _state(request).get("payment_gateway_id")
    for gateway in gateways:
        if gateway.pk == selected_id:
            return gateway
    return gateways[0]


def set_payment_gateway(request, gateway_id) -> None:
    """یک POST دستکاری‌شده هرگز نمی‌تواند درگاه پرداخت متعلق به Store دیگری
    را انتخاب کند — استخر گزینه‌های مجاز همیشه با ``store`` فعلی فیلتر می‌شود."""
    store = resolve_store_for_service(request)
    gateway = PaymentGateway.objects.filter(pk=gateway_id, is_active=True, store=store).first()
    if gateway:
        _state(request)["payment_gateway_id"] = gateway.pk
        request.session.modified = True


def get_or_create_checkout_token(cart) -> str:
    """کلید idempotency ثبت سفارش برای این سبد — سرور‌محور، بدون نیاز به
    مشارکت کاربر (نه فیلد مخفی فرم، نه ورودی جدا). چون هر درخواست تسویه‌حساب
    (اعم از کلیک دوم/retry شبکه) همان Cart را دوباره resolve می‌کند
    (``apps.cart.services.cart_service.get_cart``)، همین یک کلید ذخیره‌شده
    روی خودِ Cart برای تمام تلاش‌های متوالی/هم‌زمانِ همان کاربر یکسان
    می‌ماند — بدون این‌که کلاینت هیچ مقداری بفرستد یا کنترل کند."""
    if not cart.checkout_token:
        cart.checkout_token = secrets.token_urlsafe(CHECKOUT_TOKEN_BYTES)
        cart.save(update_fields=["checkout_token", "updated_at"])
    return cart.checkout_token


def get_applied_coupon(request, cart):
    """کد تخفیف فعلی نشست را برمی‌گرداند؛ اگر دیگر معتبر نباشد از نشست پاک می‌شود.

    جست‌وجو همیشه با ``store`` فعلی فیلتر می‌شود (ADR-32) — یک کدِ ذخیره‌شده
    در نشست که به کد تخفیفِ فروشگاه دیگری اشاره کند هرگز نباید در این
    Store اعمال شود، حتی اگر رشته‌ی کد به‌طور تصادفی یکسان باشد."""
    code = _state(request).get("coupon_code")
    if not code:
        return None
    store = resolve_store_for_service(request)
    coupon = Coupon.objects.filter(code=code, store=store).first()
    totals = cart_totals(cart, store=store)
    if coupon is None or not coupon_is_applicable(coupon, totals["items_total"]):
        _state(request).pop("coupon_code", None)
        request.session.modified = True
        return None
    return coupon


def apply_coupon(request, cart, code: str) -> tuple[bool, str]:
    code = (code or "").strip().upper()
    if not code:
        return False, "لطفاً کد تخفیف را وارد کنید"
    store = resolve_store_for_service(request)
    coupon = Coupon.objects.filter(code=code, store=store).first()
    totals = cart_totals(cart, store=store)
    if coupon is None or not coupon_is_applicable(coupon, totals["items_total"]):
        return False, "کد تخفیف نامعتبر است یا منقضی شده"
    _state(request)["coupon_code"] = coupon.code
    request.session.modified = True
    label = coupon.label or coupon.get_type_display()
    return True, f"کد «{coupon.code}» با موفقیت اعمال شد — {label}"


def remove_coupon(request) -> None:
    _state(request).pop("coupon_code", None)
    request.session.modified = True


class CheckoutError(Exception):
    """خطای قابل‌نمایش به کاربر هنگام نهایی‌سازی سفارش."""


# متنِ دقیقاً الزامی — یک تصمیمِ محصولیِ binding (CAT-002) است؛ این رشته را
# تغییر ندهید.
PRICE_CHANGED_MESSAGE = (
    "قیمت یک یا چند کالا از زمان افزودن به سبد تغییر کرده است. "
    "مبلغ نهایی به‌روزرسانی شد؛ لطفاً مبلغ جدید را بررسی و دوباره پرداخت را تأیید کنید."
)


class PriceChangeReviewRequired(CheckoutError):
    """قیمتِ زنده‌ی کاتالوگ با اسنپ‌شاتِ سبد فرق دارد (CAT-002) — سفارشی
    ساخته نشده، موجودی/کدِ تخفیف/سبد/نشست دست‌نخورده مانده‌اند. سبد با
    قیمتِ تازه به‌روز شده (نگاه کنید به ``reprice_cart_items``)؛ کاربر باید
    مبلغِ جدید را ببیند و صریحاً «دوباره پرداخت» را تأیید کند."""

    def __init__(self):
        super().__init__(PRICE_CHANGED_MESSAGE)


def _resolve_or_create_address(customer, address_data: dict) -> Address:
    is_first = not customer.addresses.exists()
    return Address.objects.create(
        customer=customer,
        receiver_name=address_data["receiver_name"],
        phone=address_data["phone"],
        province=address_data["province"],
        city=address_data["city"],
        postal_code=address_data.get("postal_code", ""),
        full_address=address_data["full_address"],
        is_default=is_first,
    )


def finalize_order(request, cart, customer):
    """سفارش را از روی سبد و آدرس ذخیره‌شده در session می‌سازد، سبد را خالی و session را پاک می‌کند.

    تمام عملیات دیتابیسی (ساخت آدرس، ساخت سفارش، کاهش موجودی، پاک‌سازی سبد)
    در یک تراکنش اتمیک انجام می‌شود. در صورت هر خطایی، همه‌ی تغییرات دیتابیسی
    رول‌بک می‌شوند و سبد و نشست کاربر حفظ می‌شود.

    idempotency: کلید تسویه‌حساب همین Cart (``get_or_create_checkout_token``)
    پیش از هر بررسیِ خالی/پر بودنِ سبد چک می‌شود — چون یک ارسال دوباره‌ی
    متوالی (کلیک دوم بعد از این‌که درخواست اول موفق شده) دقیقاً همین Cart را
    دوباره resolve می‌کند در حالی که آیتم‌هایش از قبل توسط همان درخواست اول
    پاک شده‌اند؛ اگر بررسی «سبد خالی است» زودتر از بررسی idempotency انجام
    می‌شد، این حالت به‌اشتباه خطا نشان می‌داد به‌جای بازگرداندن سفارشِ همان
    درخواست اول.
    """
    from apps.orders.services.order_service import create_order_from_cart

    if cart is None:
        raise CheckoutError("سبد خرید شما خالی است")

    token = get_or_create_checkout_token(cart)
    existing_order = Order.objects.filter(idempotency_key=token).first()
    if existing_order is not None:
        return existing_order

    if not cart.items.exists():
        raise CheckoutError("سبد خرید شما خالی است")

    # CAT-002 — reprice-at-checkout: قیمتِ اسنپ‌شاتِ هر قلمِ سبد را با قیمتِ
    # زنده‌ی کاتالوگ (تنها مرجعِ کانونی — resolve_effective_price) هم‌راستا
    # می‌کند. این فراخوانی، تراکنشِ خودش را باز/commit می‌کند و *پیش از* هر
    # کارِ Address/Order اجرا می‌شود — اگر قیمتی تغییر کرده باشد، هیچ Order،
    # هیچ Address، هیچ کاهشِ موجودی، هیچ افزایشِ used_count کدِ تخفیف، و هیچ
    # حذفِ آیتمِ سبدی رخ نمی‌دهد؛ فقط سبد (که همین الان با قیمتِ تازه
    # به‌روز شد) دوباره به کاربر نمایش داده می‌شود تا صریحاً «دوباره
    # پرداخت» را تأیید کند.
    if reprice_cart_items(cart):
        raise PriceChangeReviewRequired()

    address_data = get_address(request)
    if not address_data.get("full_address"):
        raise CheckoutError("لطفاً ابتدا اطلاعات گیرنده را تکمیل کنید")

    vendor = cart.items.select_related("product__vendor").first().product.vendor
    shipping_method = get_selected_shipping_method(request)
    payment_gateway = get_selected_payment_gateway(request)
    if shipping_method is None:
        raise CheckoutError("هیچ روش ارسال فعالی موجود نیست")
    if payment_gateway is None:
        raise CheckoutError("هیچ درگاه پرداخت فعالی موجود نیست")

    coupon = get_applied_coupon(request, cart)
    store = resolve_store_for_service(request)

    try:
        with transaction.atomic():
            address = _resolve_or_create_address(customer, address_data)
            order = create_order_from_cart(
                cart, customer=customer, vendor=vendor, address=address,
                shipping_method=shipping_method, payment_gateway=payment_gateway,
                coupon=coupon, note=address_data.get("note", ""), store=store,
                idempotency_key=token,
            )
            cart.items.all().delete()
    except ValueError as exc:
        raise CheckoutError(str(exc)) from exc

    # Session clearing happens AFTER successful database commit
    request.session.pop(SESSION_KEY, None)
    return order


def build_context(request, cart) -> dict:
    """کانتکست کامل صفحه‌ی تسویه‌حساب مرحله‌ی ۱ را می‌سازد."""
    is_empty = cart is None or not cart.items.exists()
    store = resolve_store_for_service(request)
    address = get_address(request)

    shipping_methods = active_shipping_methods(store=store, address=address)
    payment_gateways = active_payment_gateways(store=store)
    selected_shipping = None if is_empty else get_selected_shipping_method(request)
    selected_payment = None if is_empty else get_selected_payment_gateway(request)
    coupon = None if is_empty else get_applied_coupon(request, cart)

    if is_empty:
        totals = dict(EMPTY_TOTALS)
        item_count = 0
        cart_items = []
    else:
        totals = cart_totals(
            cart, store=resolve_store_for_service(request), coupon=coupon, shipping_method=selected_shipping,
            province=address.get("province", ""), city=address.get("city", ""), postal_code=address.get("postal_code", ""),
        )
        cart_items = list(cart.items.select_related("product", "variant").all())
        for item in cart_items:
            item.regular_price = resolve_regular_price(item.product, item.variant)
        item_count = sum(item.quantity for item in cart_items)

    shipping_rows = [
        {
            "method": method,
            "selected": bool(selected_shipping and method.pk == selected_shipping.pk),
            "free": totals["free_shipping"],
        }
        for method in shipping_methods
    ]
    payment_rows = [
        {"gateway": gateway, "selected": bool(selected_payment and gateway.pk == selected_payment.pk)}
        for gateway in payment_gateways
    ]

    return {
        "cart": cart,
        "cart_items": cart_items,
        "is_empty": is_empty,
        "item_count": item_count,
        "address": get_address(request),
        "shipping_rows": shipping_rows,
        "payment_rows": payment_rows,
        "coupon": coupon,
        "totals": totals,
        "savings": totals["product_discount"] + totals["coupon_discount"],
    }
