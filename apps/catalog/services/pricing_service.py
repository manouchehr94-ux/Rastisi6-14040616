"""سرویس مرجع محاسبه‌ی قیمت نهایی کالا — با/بدون تنوع انتخابی.

تنها منبع حقیقت برای «قیمت نهایی قابل‌پرداخت» یک کالا (با در نظر گرفتن
تغییر قیمت مقدار تنوع و درصد تخفیف کالا). سبد خرید و سفارش باید همیشه از
همین تابع استفاده کنند، نه از محاسبه‌ی مستقل در view/template/جاوااسکریپت.
"""

from decimal import ROUND_HALF_UP, Decimal

from apps.catalog.models import Product, ProductVariant


class PricingError(Exception):
    """خطای قابل‌نمایش هنگام محاسبه‌ی قیمت (مثلاً تنوع متعلق به کالای دیگر)."""


def _check_ownership(product: Product, variant: ProductVariant | None) -> None:
    if variant is not None and variant.product_id != product.pk:
        raise PricingError("این مقدار تنوع متعلق به کالای دیگری است.")


def resolve_effective_price(product: Product, variant: ProductVariant | None = None) -> Decimal:
    """قیمتِ نهایی/قابل‌پرداختِ کالا — با یا بدون تنوعِ انتخابی.

    اگر تنوع، قیمتِ مستقل (``variant.price``) داشته باشد، همان مقدار
    *کاملِ* قیمتِ فروش است (نه افزوده به قیمتِ کالا) — برایِ تنوع‌هایی که
    قیمتِ کاملاً متفاوتی دارند (مثلاً قیچیِ ایرانی/ایتالیایی). در غیرِ این
    صورت، مسیرِ قدیمیِ delta ادامه می‌یابد: (قیمتِ پایه‌ی کالا + تغییرِ
    قیمتِ تنوع) با اعمالِ درصدِ تخفیفِ کالا — این مسیر برایِ کالاها/تنوع‌هایِ
    موجود بدونِ تغییر باقی می‌ماند (سازگاریِ کاملِ رو به عقب).

    اگر ``variant`` داده شود، باید متعلق به همین ``product`` باشد — در غیر
    این صورت PricingError صادر می‌شود تا هرگز تنوع کالای دیگری قیمت‌گذاری نشود.
    """
    _check_ownership(product, variant)

    if variant is not None and variant.price is not None:
        return variant.price

    base = product.price + (variant.extra_price if variant is not None else Decimal("0"))
    # تخفیف فقط داخلِ بازه‌ی اعتبارش اعمال می‌شود؛ سبد/سفارش از همین تابع قیمتِ زنده می‌گیرند،
    # پس تخفیفِ منقضی هرگز در پرداخت پذیرفته نمی‌شود (LivePriceChangedError / تازه‌سازی سبد).
    factor = (Decimal(100) - product.active_discount_percent()) / Decimal(100)
    return (base * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def resolve_regular_price(product: Product, variant: ProductVariant | None = None) -> Decimal:
    """قیمتِ «پیش از تخفیف» برایِ نمایشِ خط‌خورده — همیشه >= قیمتِ نهایی.

    برایِ تنوعِ دارایِ قیمتِ مستقل: ``compare_at_price`` (اگر ثبت شده) یا
    خودِ ``price`` (یعنی بدونِ تخفیف). در غیرِ این صورت، قیمتِ پایه‌ی کالا +
    تغییرِ قیمتِ تنوع (پیش از اعمالِ درصدِ تخفیف).
    """
    _check_ownership(product, variant)

    if variant is not None and variant.price is not None:
        return variant.compare_at_price if variant.compare_at_price is not None else variant.price

    return product.price + (variant.extra_price if variant is not None else Decimal("0"))


def resolve_savings(product: Product, variant: ProductVariant | None = None) -> Decimal:
    """مبلغِ صرفه‌جویی = قیمتِ پیش از تخفیف − قیمتِ نهایی (هرگز منفی نیست)."""
    savings = resolve_regular_price(product, variant) - resolve_effective_price(product, variant)
    return savings if savings > 0 else Decimal("0")


def is_variant_purchasable(variant: ProductVariant) -> bool:
    """آیا این مقدار تنوع قابل‌خرید است (فعال و موجودی مثبت)."""
    return variant.is_active and variant.stock > 0
