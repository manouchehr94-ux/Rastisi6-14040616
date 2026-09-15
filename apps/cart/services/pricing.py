"""قواعد کسب‌وکار قیمت‌گذاری — سبد خرید، کد تخفیف، ارسال رایگان، مالیات.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶. هیچ‌کدام از این محاسبات نباید در
ویو یا تمپلیت تکرار شود؛ همیشه از طریق این توابع خالص انجام شوند.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.cart.models import Coupon
from apps.catalog.services.pricing_service import resolve_regular_price
from apps.core.models import ShopSettings
from apps.orders.services import shipping_service, tax_service


def product_final_price(product) -> Decimal:
    """قیمت نهایی کالا = price * (1 - discount_percent/100)، گرد شده — بدونِ
    درنظرگرفتنِ تنوع؛ برایِ جمعِ سبد از ``item.unit_price`` (اسنپ‌شاتِ آگاه از
    تنوع) استفاده کنید، نه این تابع."""
    return product.final_price


def _free_shipping_threshold(store) -> Decimal:
    """آستانه‌ی ارسال رایگان همان Store — از apps.core.models.ShopSettings."""
    return ShopSettings.load(store=store).free_shipping_threshold


def _tax_percent(store) -> Decimal:
    """نرخ مالیات همان Store — از apps.core.models.ShopSettings."""
    return ShopSettings.load(store=store).tax_percent


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def coupon_is_applicable(coupon: Coupon, items_total: Decimal) -> bool:
    """آیا این کد تخفیف در حال حاضر قابل اعمال است (فعال، منقضی‌نشده، سقف استفاده و حداقل سفارش رعایت‌شده)."""
    if coupon is None:
        return False
    if not coupon.is_active:
        return False
    if coupon.expires_at and coupon.expires_at <= timezone.now():
        return False
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return False
    if items_total < coupon.min_order:
        return False
    return True


def _allocate_coupon_discount(items, *, items_total: Decimal, coupon_discount: Decimal) -> list[Decimal]:
    """سهمِ هر قلم از ``coupon_discount`` را تناسبی تخصیص می‌دهد — آخرین قلم
    باقیمانده را می‌گیرد تا مجموعِ دقیقِ تخصیص‌ها همیشه با ``coupon_discount``
    برابر باشد (بدونِ اختلافِ گردکردن)، چون این مجموع دقیقاً همان چیزی است
    که مسیرِ قدیمیِ محاسبه‌ی مالیات به آن نیاز دارد تا با فرمولِ پیشین
    (پیش از checkpoint 3B) کاملاً یکسان بماند."""
    if not items or coupon_discount == 0 or items_total == 0:
        return [Decimal("0") for _ in items]

    allocations = []
    allocated_so_far = Decimal("0")
    for item in items[:-1]:
        line_total = item.unit_price * item.quantity
        share = _round(coupon_discount * line_total / items_total)
        allocations.append(share)
        allocated_so_far += share
    allocations.append(coupon_discount - allocated_so_far)
    return allocations


def cart_totals(
    cart, *, store, coupon: Coupon | None = None, shipping_method=None,
    province: str = "", city: str = "", postal_code: str = "",
) -> dict:
    """جمع کامل سبد خرید را طبق قواعد کسب‌وکار محاسبه می‌کند.

    ``store`` الزامی و صریح است — تنظیمات مالیات/ارسال رایگان همیشه از همان
    Store خوانده می‌شود که فراخوان (view/سرویس) از قبل resolve کرده؛ این تابع
    هرگز خودش از روی Host یا حالت سازگاری Store را حدس نمی‌زند.

    ``province``/``city``/``postal_code`` اختیاری‌اند (پیش‌فرض خالی) — برای
    تطبیقِ منطقه‌ی ارسال و نرخِ مالیاتِ استانی (checkpoint 3B). خالی‌گذاشتنشان
    یعنی هیچ منطقه/نرخِ استانی‌ای تطبیق نمی‌یابد و محاسبه به رفتارِ کاملاً
    قدیمی (پیش از checkpoint 3B) بازمی‌گردد — نگاه کنید به ADR-41/ADR-45.

    خروجی: items_total, product_discount, coupon_discount, shipping_cost,
    shipping_zone، shipping_rate_rule، free_shipping (bool)، tax،
    shipping_tax، grand_total، coupon_applied (bool)
    """
    if store is None:
        raise ValueError(
            "cart_totals() requires an explicit store; callers must resolve "
            "it via apps.stores.resolution.resolve_store_for_service(request) "
            "or an equivalent authoritative source before pricing a cart."
        )
    items = list(cart.items.select_related("product", "variant").all())

    raw_total = Decimal("0")
    items_total = Decimal("0")
    for item in items:
        # ``item.unit_price`` اسنپ‌شاتِ آگاه از تنوع است (مستقیماً یا delta) —
        # نه product_final_price(item.product) که تنوع را کاملاً نادیده
        # می‌گرفت (مثلاً برایِ قیچیِ ایتالیایی، جمعِ سبد را با قیمتِ پایه‌ی
        # کالا، نه ۸۰۰,۰۰۰، محاسبه می‌کرد).
        raw_total += resolve_regular_price(item.product, item.variant) * item.quantity
        items_total += item.unit_price * item.quantity

    product_discount = raw_total - items_total

    coupon_applied = coupon_is_applicable(coupon, items_total)
    coupon_discount = Decimal("0")
    free_shipping_by_coupon = False
    if coupon_applied:
        if coupon.type == Coupon.Type.PERCENT:
            coupon_discount = _round(items_total * coupon.value / Decimal("100"))
        elif coupon.type == Coupon.Type.FIXED:
            coupon_discount = min(coupon.value, items_total)
        elif coupon.type == Coupon.Type.FREE_SHIP:
            free_shipping_by_coupon = True

    after_coupon = items_total - coupon_discount

    # ارسالِ رایگان — همان محاسبه‌ی قبلی، فقط آستانه یک‌بار خوانده می‌شود و
    # بازاستفاده می‌شود (P5-W1: منبعِ آستانه دوباره در view/template خوانده
    # نمی‌شود).
    free_shipping_threshold = _free_shipping_threshold(store)
    free_by_threshold = items_total >= free_shipping_threshold
    free_shipping = free_by_threshold or free_shipping_by_coupon

    # P5-W1 — «هدفِ ارسالِ رایگان»: مقادیرِ آماده‌یِ نمایش که *همین‌جا* (منبعِ
    # کانونیِ قیمت‌گذاری) محاسبه می‌شوند؛ view/render_service/template/JS هیچ
    # محاسبه‌ای انجام نمی‌دهند. مبلغِ واجدِ مقایسه همان ``items_total`` کانونی
    # است. «باقی‌مانده» هرگز منفی نمی‌شود و «درصدِ پیشرفت» در بازه‌ی [۰،۱۰۰]
    # مقیّد می‌شود. «applicable» فقط وقتی درست است که سبد حداقل یک کالای
    # فیزیکیِ نیازمندِ ارسال داشته باشد — از همان مرجعِ کانونیِ
    # ``shipping_service.cart_requires_shipping(items)`` (بدونِ قاعده‌ی
    # جداگانه). سبدِ کاملاً دیجیتال هدفِ ارسالِ فیزیکی را نمایش نمی‌دهد.
    free_shipping_goal_applicable = shipping_service.cart_requires_shipping(items)
    free_shipping_goal_remaining = max(Decimal("0"), free_shipping_threshold - items_total)
    # درصدِ پیشرفت — «۱۰۰٪» فقط و فقط برایِ حالتِ *رسیدن به آستانه* رزرو شده
    # است. یک سبدِ زیرِ آستانه (باقی‌مانده > ۰) هرگز نباید نوارِ پُر (۱۰۰٪) نشان
    # دهد؛ برایِ همین در حالتِ زیرِ آستانه به‌جایِ گِردکردن (که ۴۹۹۰۰۰/۵۰۰۰۰۰ =
    # ۹۹٫۸٪ را به ۱۰۰ می‌رساند) به سمتِ پایین trunc می‌شود (ROUND_DOWN) و
    # سقفِ ۹۹ اعمال می‌گردد.
    if free_shipping_threshold <= 0 or items_total <= 0:
        # آستانه‌ی غیرقابل‌استفاده (صفر/منفی) یا سبدِ خالی: هرگز ۱۰۰٪ نمی‌شود —
        # این شرط *پیش از* free_by_threshold می‌آید چون برایِ آستانه‌ی صفر،
        # ``items_total >= 0`` مقدارِ free_by_threshold را True می‌کند ولی
        # قراردادِ نمایش می‌گوید آستانه‌ی ناموجود = ۰٪.
        free_shipping_goal_progress_percent = 0
    elif free_by_threshold:
        free_shipping_goal_progress_percent = 100
    else:
        free_shipping_goal_progress_percent = min(
            99, int((items_total * 100 / free_shipping_threshold).to_integral_value(rounding=ROUND_DOWN))
        )

    shipping_zone = None
    shipping_rate_rule = None
    if shipping_method is not None:
        # منطقه همیشه حل می‌شود (حتی وقتی ارسال رایگان است) چون گزارش‌گیریِ
        # مرچنت و اسنپ‌شاتِ سفارش به آن نیاز دارند، مستقل از این‌که هزینه‌ی
        # نهایی صفر شده یا نه.
        shipping_zone = shipping_service.resolve_shipping_zone(store, province=province, city=city, postal_code=postal_code)
        weight_grams = shipping_service.cart_shippable_weight_grams(items)
        shipping_rate_rule = shipping_service.resolve_best_rate_rule(
            shipping_method, subtotal=after_coupon, weight_grams=weight_grams,
        )

    if free_shipping or shipping_method is None:
        shipping_cost = Decimal("0")
    else:
        shipping_cost = shipping_service.calculate_shipping_rate(
            shipping_method, subtotal=after_coupon, weight_grams=weight_grams,
        )

    discount_allocations = _allocate_coupon_discount(items, items_total=items_total, coupon_discount=coupon_discount)
    tax_line_items = [
        {
            "item_ref": item.pk,
            "unit_price": item.unit_price, "quantity": item.quantity,
            "discount_allocation": allocation,
            "tax_class": (item.variant.tax_class if item.variant_id and item.variant.tax_class_id
                          else getattr(item.product, "tax_class", None)),
        }
        for item, allocation in zip(items, discount_allocations)
    ]
    tax_result = tax_service.calculate_order_taxes(
        store, items=tax_line_items, shipping_amount=shipping_cost, province=province,
    )
    tax = tax_result["line_tax_total"]
    shipping_tax = tax_result["shipping_tax"]

    # کادوپیچی (toranj_gifting: optional_addon_checkbox_updates_total) — جمعِ
    # هزینه‌ی کادوپیچیِ همه‌ی اقلامِ سبد. عمداً هیچ تخفیف/کدِ تخفیفی روی این
    # مبلغ اعمال نمی‌شود (یک افزونه‌ی خدماتی است، نه بخشی از قیمتِ کالا) و
    # مالیات هم روی آن محاسبه نمی‌شود — این یک تصمیمِ سکوپِ محدودِ همین
    # افزونه است، نه یک قاعده‌ی مالیاتیِ جدیدِ عمومی.
    gift_wrap_total = sum((item.gift_wrap_line_total for item in items), Decimal("0"))

    # وقتی قیمت‌ها inclusive باشند، مالیاتِ کالا از قبل داخلِ items_total
    # نشسته و نباید دوباره افزوده شود — نگاه کنید به ADR-45 و
    # ``tax_service``'s ``tax_added_to_grand_total``.
    grand_total = after_coupon + shipping_cost + tax_result["tax_added_to_grand_total"] + gift_wrap_total

    return {
        "items_total": items_total,
        "product_discount": product_discount,
        "coupon_discount": coupon_discount,
        "shipping_cost": shipping_cost,
        "shipping_zone": shipping_zone,
        "shipping_rate_rule": shipping_rate_rule,
        "free_shipping": free_shipping,
        # P5-W1 — presentation-ready Free-Shipping Goal state (all computed here).
        "free_shipping_threshold": free_shipping_threshold,
        "free_shipping_by_threshold": free_by_threshold,
        "free_shipping_by_coupon": free_shipping_by_coupon,
        "free_shipping_goal_applicable": free_shipping_goal_applicable,
        "free_shipping_goal_remaining": free_shipping_goal_remaining,
        "free_shipping_goal_progress_percent": free_shipping_goal_progress_percent,
        "tax": tax,
        "shipping_tax": shipping_tax,
        "tax_lines": tax_result["lines"],
        "prices_include_tax": tax_result["prices_include_tax"],
        "tax_rounding_policy": tax_result["tax_rounding_policy"],
        "gift_wrap_total": gift_wrap_total,
        "grand_total": grand_total,
        "coupon_applied": coupon_applied,
    }
