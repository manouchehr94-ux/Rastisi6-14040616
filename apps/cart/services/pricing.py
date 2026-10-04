"""قواعد کسب‌وکار قیمت‌گذاری — سبد خرید، کد تخفیف، ارسال رایگان، مالیات.

مطابق docs/spec/01-PROJECT-SPEC.md بخش ۶. هیچ‌کدام از این محاسبات نباید در
ویو یا تمپلیت تکرار شود؛ همیشه از طریق این توابع خالص انجام شوند.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal


from apps.cart.models import Coupon
from apps.cart.services import coupon_rules, gift_wrap_service
from apps.catalog.models import Category
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
    """سازگاریِ رو‌به‌عقب: آیا کد فعال/در بازه/دارایِ ظرفیت است و حداقل سفارش رعایت شده.
    منطق فقط در ``coupon_rules`` است؛ ارزیابیِ کامل (مالکیت، محدودیت‌ها) ``evaluate_coupon``."""
    if coupon is None:
        return False
    if coupon_rules.validity_failure(coupon) or coupon_rules.capacity_failure(coupon):
        return False
    return items_total >= coupon.min_order


def _allocate_coupon_discount(items, *, items_total: Decimal, coupon_discount: Decimal, eligible_keys=None) -> list[Decimal]:
    """سهمِ هر قلم از ``coupon_discount`` را تناسبی تخصیص می‌دهد — آخرین قلمِ
    مشمول باقیمانده را می‌گیرد تا مجموعِ دقیقِ تخصیص‌ها همیشه با
    ``coupon_discount`` برابر باشد (بدونِ اختلافِ گردکردن). اگر
    ``eligible_keys`` داده شود فقط اقلامِ مشمول سهم می‌گیرند (کدِ مخصوصِ
    کالا/دسته/برند) و ``items_total`` جمعِ همان اقلامِ مشمول است."""
    if not items or coupon_discount == 0 or items_total == 0:
        return [Decimal("0") for _ in items]

    eligible = [i for i, item in enumerate(items) if eligible_keys is None or item.pk in eligible_keys]
    allocations = [Decimal("0") for _ in items]
    allocated_so_far = Decimal("0")
    for idx in eligible[:-1]:
        line_total = items[idx].unit_price * items[idx].quantity
        share = _round(coupon_discount * line_total / items_total)
        allocations[idx] = share
        allocated_so_far += share
    if eligible:
        allocations[eligible[-1]] = coupon_discount - allocated_so_far
    return allocations


def build_coupon_lines(items, coupon: Coupon | None) -> list[coupon_rules.CouponLine]:
    """اقلامِ سبد را به ``CouponLine`` تبدیل می‌کند. زنجیره‌ی دسته‌ها فقط وقتی
    کد محدودیتِ دسته دارد (یک کوئری) بارگذاری می‌شود."""
    restrictions = (coupon.restrictions or {}) if coupon is not None else {}
    needs_categories = bool(restrictions.get("category_ids") or restrictions.get("excluded_category_ids"))
    parent_of = {}
    if needs_categories and items:
        parent_of = dict(Category.objects.filter(store_id=items[0].product.store_id).values_list("id", "parent_id"))

    def chain(category_id):
        ids, seen = set(), set()
        while category_id and category_id not in seen:
            seen.add(category_id)
            ids.add(category_id)
            category_id = parent_of.get(category_id)
        return frozenset(ids)

    return [
        coupon_rules.CouponLine(
            key=item.pk, product_id=item.product_id,
            category_ids=chain(item.product.category_id) if needs_categories else frozenset(
                {item.product.category_id} if item.product.category_id else ()
            ),
            brand_id=item.product.brand_id, unit_price=item.unit_price, quantity=item.quantity,
            regular_price=resolve_regular_price(item.product, item.variant),
        )
        for item in items
    ]


def cart_totals(
    cart, *, store, coupon: Coupon | None = None, shipping_method=None,
    province: str = "", city: str = "", postal_code: str = "",
    customer=None, payment_gateway=None, enforce_coupon_usage: bool = True,
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

    shop = ShopSettings.load(store=store)
    gift_wrap_lines = gift_wrap_service.cart_gift_wrap_lines(items, shop)
    gift_wrap_total = gift_wrap_service.gift_wrap_charge(gift_wrap_lines, shop.gift_wrap_pricing_scope)

    coupon_error_code = ""
    coupon_error_message = ""
    coupon_discount = Decimal("0")
    coupon_item_discount = Decimal("0")
    coupon_gift_wrap_discount = Decimal("0")
    free_shipping_by_coupon = False
    eligible_keys = None
    coupon_applied = False
    if coupon is not None:
        evaluation = coupon_rules.evaluate_coupon(
            coupon, lines=build_coupon_lines(items, coupon), customer=customer,
            gift_wrap_total=gift_wrap_total, payment_gateway=payment_gateway,
            shipping_method=shipping_method, check_usage=enforce_coupon_usage,
        )
        coupon_applied = evaluation.ok
        if evaluation.ok:
            coupon_discount = evaluation.discount
            coupon_item_discount = evaluation.item_discount
            coupon_gift_wrap_discount = evaluation.gift_wrap_discount
            free_shipping_by_coupon = evaluation.free_shipping
            eligible_keys = evaluation.eligible_keys
        else:
            coupon_error_code, coupon_error_message = evaluation.code, evaluation.message

    after_coupon = items_total - coupon_item_discount

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

    eligible_total = items_total if eligible_keys is None else sum(
        (i.unit_price * i.quantity for i in items if i.pk in eligible_keys), Decimal("0"),
    )
    discount_allocations = _allocate_coupon_discount(
        items, items_total=eligible_total, coupon_discount=coupon_item_discount, eligible_keys=eligible_keys,
    )
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

    # کادوپیچی (gift_wrap_total بالاتر محاسبه شد): مالیات روی آن محاسبه
    # نمی‌شود؛ تخفیفِ کد فقط وقتی روی آن اعمال می‌شود که
    # ``Coupon.applies_to_gift_wrap`` روشن باشد (``coupon_gift_wrap_discount``).

    # وقتی قیمت‌ها inclusive باشند، مالیاتِ کالا از قبل داخلِ items_total
    # نشسته و نباید دوباره افزوده شود — نگاه کنید به ADR-45 و
    # ``tax_service``'s ``tax_added_to_grand_total``.
    grand_total = (
        after_coupon + shipping_cost + tax_result["tax_added_to_grand_total"]
        + gift_wrap_total - coupon_gift_wrap_discount
    )

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
        "gift_wrap_discount": coupon_gift_wrap_discount,
        "gift_wrap_scope": shop.gift_wrap_pricing_scope,
        "gift_wrap_allocations": gift_wrap_service.gift_wrap_allocations(gift_wrap_lines, shop.gift_wrap_pricing_scope),
        "coupon_item_discount": coupon_item_discount,
        "coupon_allocations": {item.pk: alloc for item, alloc in zip(items, discount_allocations)},
        "grand_total": grand_total,
        "coupon_applied": coupon_applied,
        "coupon_error_code": coupon_error_code,
        "coupon_error_message": coupon_error_message,
    }
