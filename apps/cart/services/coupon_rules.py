"""اعتبارسنجی و محاسبه‌ی کد تخفیف — تنها منبعِ حقیقتِ «این کد برای این سبد
چقدر تخفیف می‌دهد؟» (سمتِ سرور؛ هیچ مقداری از کلاینت اعتماد نمی‌شود).

``evaluate_coupon`` یک تابعِ خالص (بدونِ نوشتن در دیتابیس) است: همه‌ی
شرط‌ها (فعال‌بودن، بازه‌ی زمانی، مالکیتِ مشتری، سقفِ کل/هر مشتری، حداقل/
حداکثرِ سبد و تعداد، محدودیتِ کالا/دسته/برند، روشِ پرداخت/ارسال، روز/ساعت)
را بررسی و تخفیف را با سقفِ ``max_discount`` محاسبه می‌کند. تخفیف هرگز از
پایه‌ی مشمول بیشتر نمی‌شود، پس مبلغِ سفارش هرگز منفی نخواهد شد.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.cart.models import Coupon
from apps.core.jalali_utils import store_timezone

ZERO = Decimal("0")

# کدهای دلیلِ رد — پایدار؛ UI/لاگ/تست به این‌ها تکیه می‌کنند.
INACTIVE = "inactive"
NOT_STARTED = "not_started"
EXPIRED = "expired"
WRONG_CUSTOMER = "wrong_customer"
LOGIN_REQUIRED = "login_required"
USAGE_LIMIT = "usage_limit_reached"
PER_CUSTOMER_LIMIT = "per_customer_limit_reached"
MIN_ORDER = "min_order"
MAX_ORDER = "max_order"
MIN_ITEMS = "min_items"
MAX_ITEMS = "max_items"
NO_ELIGIBLE_ITEMS = "no_eligible_items"
PAYMENT_METHOD = "payment_method_not_allowed"
SHIPPING_METHOD = "shipping_method_not_allowed"
TIME_WINDOW = "time_window"

MESSAGES = {
    INACTIVE: "این کد تخفیف فعال نیست.",
    NOT_STARTED: "زمان فعال‌سازی این کد تخفیف هنوز فرا نرسیده است.",
    EXPIRED: "این کد تخفیف منقضی شده است.",
    WRONG_CUSTOMER: "این کد تخفیف برای حساب کاربری شما صادر نشده است.",
    LOGIN_REQUIRED: "برای استفاده از این کد تخفیف ابتدا وارد حساب کاربری خود شوید.",
    USAGE_LIMIT: "ظرفیت استفاده از این کد تخفیف تکمیل شده است.",
    PER_CUSTOMER_LIMIT: "شما بیش از سقفِ مجاز از این کد استفاده کرده‌اید.",
    MIN_ORDER: "مبلغ سبد خرید کمتر از حداقلِ لازم برای این کد است.",
    MAX_ORDER: "مبلغ سبد خرید بیشتر از حداکثرِ مجاز برای این کد است.",
    MIN_ITEMS: "تعداد اقلام سبد کمتر از حداقلِ لازم برای این کد است.",
    MAX_ITEMS: "تعداد اقلام سبد بیشتر از حداکثرِ مجاز برای این کد است.",
    NO_ELIGIBLE_ITEMS: "این کد روی هیچ‌یک از کالاهای سبد قابل اعمال نیست.",
    PAYMENT_METHOD: "این کد با روشِ پرداختِ انتخاب‌شده قابل استفاده نیست.",
    SHIPPING_METHOD: "این کد با روشِ ارسالِ انتخاب‌شده قابل استفاده نیست.",
    TIME_WINDOW: "این کد در این روز/ساعت قابل استفاده نیست.",
}

RESTRICTION_ID_KEYS = (
    "product_ids", "category_ids", "brand_ids",
    "excluded_product_ids", "excluded_category_ids", "excluded_brand_ids",
    "payment_gateway_ids", "shipping_method_ids",
)
RESTRICTION_KEYS = RESTRICTION_ID_KEYS + ("weekdays", "hours")


class CouponRestrictionError(ValueError):
    """ساختارِ ``restrictions`` نامعتبر است."""


def validate_restrictions(raw) -> dict:
    """ساختارِ محدودیت‌ها را اعتبارسنجی و نرمال می‌کند — فقط کلیدهایِ مجاز،
    لیستِ اعدادِ صحیح؛ ``weekdays`` اعداد ۰..۶ (۰=دوشنبه، پایتون)؛ ``hours``
    جفتِ ``[شروع, پایان)`` بینِ ۰ تا ۲۴."""
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise CouponRestrictionError("محدودیت‌ها باید یک شیء باشند.")
    unknown = set(raw) - set(RESTRICTION_KEYS)
    if unknown:
        raise CouponRestrictionError(f"کلیدِ محدودیتِ نامعتبر: {', '.join(sorted(unknown))}")
    clean: dict = {}
    for key in RESTRICTION_ID_KEYS:
        values = raw.get(key)
        if not values:
            continue
        if not isinstance(values, (list, tuple)) or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in values):
            raise CouponRestrictionError(f"«{key}» باید فهرستی از شناسه‌هایِ عددی باشد.")
        clean[key] = sorted(set(values))
    weekdays = raw.get("weekdays")
    if weekdays:
        if not isinstance(weekdays, (list, tuple)) or not all(isinstance(v, int) and 0 <= v <= 6 for v in weekdays):
            raise CouponRestrictionError("روزهای هفته باید اعدادِ ۰ تا ۶ باشند.")
        clean["weekdays"] = sorted(set(weekdays))
    hours = raw.get("hours")
    if hours:
        if (not isinstance(hours, (list, tuple)) or len(hours) != 2
                or not all(isinstance(v, int) and 0 <= v <= 24 for v in hours) or hours[0] >= hours[1]):
            raise CouponRestrictionError("بازه‌ی ساعت باید جفتِ [شروع, پایان) بینِ ۰ تا ۲۴ باشد.")
        clean["hours"] = list(hours)
    return clean


@dataclass(frozen=True)
class CouponLine:
    """نمایِ خالصِ یک قلمِ سبد برایِ ارزیابی."""
    key: object
    product_id: int
    category_ids: frozenset
    brand_id: int | None
    unit_price: Decimal
    quantity: int
    regular_price: Decimal

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def has_product_discount(self) -> bool:
        return self.unit_price < self.regular_price


@dataclass
class CouponEvaluation:
    ok: bool
    code: str = ""
    message: str = ""
    discount: Decimal = ZERO
    item_discount: Decimal = ZERO
    gift_wrap_discount: Decimal = ZERO
    free_shipping: bool = False
    eligible_keys: frozenset = field(default_factory=frozenset)


def _fail(code: str) -> CouponEvaluation:
    return CouponEvaluation(ok=False, code=code, message=MESSAGES[code])


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def validity_failure(coupon: Coupon, *, now: dt.datetime | None = None) -> str:
    """فعال‌بودن و بازه‌ی زمانیِ کد → کدِ دلیلِ رد یا ``""``. تنها پیاده‌سازیِ
    این قواعد؛ همه‌ی مصرف‌کنندگان (سبد، چک‌اوت، سفارش، «کدهایِ من»،
    ``coupon_is_applicable``، ابزارِ تشخیصی) از همین تابع می‌گذرند."""
    now = now or timezone.now()
    if not coupon.is_active:
        return INACTIVE
    if coupon.starts_at and coupon.starts_at > now:
        return NOT_STARTED
    if coupon.expires_at and coupon.expires_at <= now:
        return EXPIRED
    return ""


def ownership_failure(coupon: Coupon, customer) -> str:
    if coupon.customer_id is None:
        return ""
    if customer is None:
        return LOGIN_REQUIRED
    if customer.pk != coupon.customer_id:
        return WRONG_CUSTOMER
    return ""


def capacity_failure(coupon: Coupon) -> str:
    """سقفِ کلِ استفاده (روی ``used_count`` که با ledger همگام نگه داشته می‌شود)."""
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return USAGE_LIMIT
    return ""


def per_customer_used(coupon: Coupon, customer, *, now: dt.datetime | None = None) -> int:
    """تعدادِ استفاده‌ی شمارش‌شده‌ی مشتری از این کد (در پنجره‌ی ``per_customer_period_days`` اگر باشد)."""
    from apps.orders.models import CouponRedemption

    now = now or timezone.now()
    qs = CouponRedemption.objects.filter(
        coupon=coupon, customer=customer, status__in=CouponRedemption.COUNTED_STATUSES,
    )
    if coupon.per_customer_period_days:
        qs = qs.filter(created_at__gt=now - dt.timedelta(days=coupon.per_customer_period_days))
    return qs.count()


def availability_failure(coupon: Coupon, *, customer=None, now: dt.datetime | None = None, check_usage: bool = True) -> str:
    """همه‌ی بررسی‌هایِ مستقل از محتوایِ سبد، به‌ترتیبِ ثابت: اعتبار/زمان ← مالکیت ←
    ظرفیتِ کل ← سقفِ هر مشتری. → کدِ دلیلِ رد یا ``""``."""
    now = now or timezone.now()
    for failure in (validity_failure(coupon, now=now), ownership_failure(coupon, customer)):
        if failure:
            return failure
    if check_usage:
        if capacity_failure(coupon):
            return USAGE_LIMIT
        if coupon.per_customer_limit is not None and customer is not None:
            if per_customer_used(coupon, customer, now=now) >= coupon.per_customer_limit:
                return PER_CUSTOMER_LIMIT
    return ""


#: نگاشتِ کدِ دلیل → وضعیتِ نمایشیِ «کدهایِ من»
DISPLAY_STATE = {
    INACTIVE: "inactive", NOT_STARTED: "upcoming", EXPIRED: "expired",
    USAGE_LIMIT: "used", PER_CUSTOMER_LIMIT: "used",
}


def display_state(coupon: Coupon, customer=None, *, now: dt.datetime | None = None) -> str:
    """وضعیتِ نمایشیِ یک کد برایِ صاحبش: ``active/inactive/upcoming/expired/used``."""
    failure = availability_failure(coupon, customer=customer, now=now)
    return DISPLAY_STATE.get(failure, "active") if failure not in (WRONG_CUSTOMER, LOGIN_REQUIRED) else "inactive"


def line_is_eligible(coupon: Coupon, line: CouponLine) -> bool:
    r = coupon.restrictions or {}
    include_product = set(r.get("product_ids", ()))
    include_category = set(r.get("category_ids", ()))
    include_brand = set(r.get("brand_ids", ()))
    if include_product or include_category or include_brand:
        matched = (
            line.product_id in include_product
            or bool(include_category & line.category_ids)
            or (line.brand_id is not None and line.brand_id in include_brand)
        )
        if not matched:
            return False
    if line.product_id in set(r.get("excluded_product_ids", ())):
        return False
    if set(r.get("excluded_category_ids", ())) & line.category_ids:
        return False
    if line.brand_id is not None and line.brand_id in set(r.get("excluded_brand_ids", ())):
        return False
    if not coupon.stacks_with_product_discount and line.has_product_discount:
        return False
    return True


def evaluate_coupon(
    coupon: Coupon | None, *, lines: list[CouponLine], customer=None, gift_wrap_total: Decimal = ZERO,
    payment_gateway=None, shipping_method=None, now: dt.datetime | None = None,
    check_usage: bool = True,
) -> CouponEvaluation:
    """ارزیابیِ کامل. ``customer=None`` (مهمان) برایِ کدِ اختصاصی همیشه رد می‌شود.

    ``check_usage=False`` فقط برایِ دوباره‌محاسبه‌ی مبلغِ سفارشی که همین
    کد را از قبل رزرو کرده به کار می‌رود (نه ورودیِ کاربر)."""
    if coupon is None:
        return _fail(INACTIVE)
    now = now or timezone.now()

    failure = availability_failure(coupon, customer=customer, now=now, check_usage=check_usage)
    if failure:
        return _fail(failure)

    items_total = sum((line.total for line in lines), ZERO)
    items_count = sum(line.quantity for line in lines)
    if items_total < coupon.min_order:
        return _fail(MIN_ORDER)
    if coupon.max_order is not None and items_total > coupon.max_order:
        return _fail(MAX_ORDER)
    if coupon.min_items is not None and items_count < coupon.min_items:
        return _fail(MIN_ITEMS)
    if coupon.max_items is not None and items_count > coupon.max_items:
        return _fail(MAX_ITEMS)

    r = coupon.restrictions or {}
    gateway_ids = r.get("payment_gateway_ids")
    if gateway_ids and payment_gateway is not None and payment_gateway.pk not in gateway_ids:
        return _fail(PAYMENT_METHOD)
    method_ids = r.get("shipping_method_ids")
    if method_ids and shipping_method is not None and shipping_method.pk not in method_ids:
        return _fail(SHIPPING_METHOD)
    local_now = now.astimezone(store_timezone())
    if r.get("weekdays") and local_now.weekday() not in r["weekdays"]:
        return _fail(TIME_WINDOW)
    if r.get("hours") and not (r["hours"][0] <= local_now.hour < r["hours"][1]):
        return _fail(TIME_WINDOW)

    eligible = [line for line in lines if line_is_eligible(coupon, line)]
    if not eligible:
        return _fail(NO_ELIGIBLE_ITEMS)
    eligible_keys = frozenset(line.key for line in eligible)

    if coupon.type == Coupon.Type.FREE_SHIP:
        return CouponEvaluation(ok=True, free_shipping=True, eligible_keys=eligible_keys)

    items_base = sum((line.total for line in eligible), ZERO)
    wrap_base = gift_wrap_total if coupon.applies_to_gift_wrap else ZERO
    base = items_base + wrap_base

    if coupon.type == Coupon.Type.PERCENT:
        discount = _round(base * coupon.value / Decimal("100"))
    else:
        discount = min(coupon.value, base)
    if coupon.max_discount is not None:
        discount = min(discount, coupon.max_discount)
    discount = max(ZERO, min(discount, base))

    gift_wrap_discount = ZERO
    if wrap_base > 0 and base > 0:
        gift_wrap_discount = min(wrap_base, _round(discount * wrap_base / base))
    item_discount = discount - gift_wrap_discount

    return CouponEvaluation(
        ok=True, discount=discount, item_discount=item_discount,
        gift_wrap_discount=gift_wrap_discount, eligible_keys=eligible_keys,
    )
