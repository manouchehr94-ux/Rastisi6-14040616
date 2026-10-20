"""مرجعِ واحدِ «قابل‌سفارش بودنِ کالا» در سطحِ کوئری.

همان تعریفِ ``inventory_service.get_available_quantity`` (موجودی − رزروهای
فعال) را برایِ یک مجموعه‌ی کالا بدونِ N+1 محاسبه می‌کند:

* کالایِ ساده: ``stock − رزروِ فعالِ خودِ کالا > ۰``؛
* کالایِ دارایِ تنوع (``VARIABLE``): حداقل یک تنوعِ *فعال* با
  ``stock − رزروِ فعالِ همان تنوع > ۰``؛ اگر کالایِ ``VARIABLE`` هیچ ردیفِ تنوعی
  ندارد (هنوز تنوعی تعریف نشده)، مثلِ کالایِ ساده با موجودیِ خودش سنجیده می‌شود.

قاعده‌ی مالک: در صفحه‌ی اصلی کالایِ ناموجود انتخاب نمی‌شود (جایش با کالایِ
ناموجود پر نمی‌شود — بخش می‌ماند و Empty State دارد)؛ در فهرست/مجموعه، کالاهایِ
ناموجود (اگر به هر دلیل شامل شوند) *بعد از* موجودها می‌آیند، با حفظِ ترتیب و
فیلترِ انتخابیِ کاربر در هر گروه.
"""

from django.db.models import (
    BooleanField,
    Case,
    Exists,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from apps.catalog.models import InventoryReservation, Product, ProductVariant

_ACTIVE = InventoryReservation.Status.ACTIVE


def _reserved_for(*, variant_ref=None):
    base = InventoryReservation.objects.filter(status=_ACTIVE)
    if variant_ref is None:
        base = base.filter(product=OuterRef("pk"), variant__isnull=True)
    else:
        base = base.filter(variant=OuterRef("pk"))
    return Coalesce(
        Subquery(
            base.order_by().values("product").annotate(total=Sum("quantity")).values("total"),
            output_field=IntegerField(),
        ),
        Value(0),
    )


def annotate_availability(queryset: QuerySet) -> QuerySet:
    """افزودنِ ``is_available_for_sale`` (bool) به هر کالا."""
    variants = ProductVariant.objects.filter(product=OuterRef("pk"), is_active=True).annotate(
        _variant_reserved=_reserved_for(variant_ref=True),
    ).filter(stock__gt=F("_variant_reserved"))
    return queryset.annotate(
        _simple_reserved=_reserved_for(),
        _has_sellable_variant=Exists(variants),
        _has_any_variant=Exists(ProductVariant.objects.filter(product=OuterRef("pk"))),
    ).annotate(
        is_available_for_sale=Case(
            When(
                product_type=Product.ProductType.VARIABLE,
                _has_any_variant=True,
                then=F("_has_sellable_variant"),
            ),
            default=ExpressionWrapper(Q(stock__gt=F("_simple_reserved")), output_field=BooleanField()),
            output_field=BooleanField(),
        )
    )


def available_only(queryset: QuerySet) -> QuerySet:
    """فقط کالاهایِ قابل‌سفارش (صفحه‌ی اصلی)."""
    return annotate_availability(queryset).filter(is_available_for_sale=True)


def order_available_first(queryset: QuerySet, *ordering: str) -> QuerySet:
    """قابل‌سفارش‌ها اول، سپس همان ترتیبِ درخواستیِ کاربر در هر گروه."""
    return annotate_availability(queryset).order_by("-is_available_for_sale", *ordering)


def available_product_ids(product_ids) -> set:
    """زیرمجموعه‌ی قابل‌سفارشِ یک فهرستِ مشخص از شناسه‌ها (یک کوئری)."""
    ids = list(product_ids)
    if not ids:
        return set()
    return set(available_only(Product.objects.filter(pk__in=ids)).values_list("pk", flat=True))


def partition_available_first(products: list) -> list:
    """جابه‌جاییِ پایدار: قابل‌سفارش‌ها اول؛ ترتیبِ نسبیِ هر گروه حفظ می‌شود."""
    available = available_product_ids(p.pk for p in products)
    return [p for p in products if p.pk in available] + [p for p in products if p.pk not in available]


def only_available(products: list) -> list:
    available = available_product_ids(p.pk for p in products)
    return [p for p in products if p.pk in available]


def order_items_available_first(items: QuerySet, *ordering: str) -> QuerySet:
    """همان قاعده برایِ قلم‌هایِ یک کالکشن (``items.product``): قابل‌سفارش‌ها اول،
    سپس ترتیبِ دستیِ کالکشن. صفحه‌بندی روی همین QuerySet انجام می‌شود."""
    product_ids = list(items.values_list("product_id", flat=True))
    available = available_product_ids(product_ids)
    if not available:
        return items.order_by(*ordering)
    return items.annotate(
        _item_available=Case(
            When(product_id__in=available, then=Value(0)), default=Value(1), output_field=IntegerField(),
        )
    ).order_by("_item_available", *ordering)


def is_available(product) -> bool:
    """قابل‌سفارش بودنِ *یک* کالا با همان تعریفِ بالا. اگر کالا از کوئریِ
    ``annotate_availability`` آمده باشد همان مقدارِ محاسبه‌شده خوانده می‌شود (بدونِ
    کوئری)؛ وگرنه برایِ کالایِ ساده همان ``stock > 0`` (مثلِ قبل) و برایِ کالایِ
    دارایِ تنوع، یک کوئریِ کوتاه — تا نشانِ «ناموجود» هرگز با قاعده‌ی مرتب‌سازی/
    حذفِ صفحه‌ی اصلی در تناقض نباشد (کالایِ دارایِ تنوعِ موجود، با موجودیِ صفرِ والد، «موجود» است)."""
    annotated = getattr(product, "is_available_for_sale", None)
    if annotated is not None:
        return bool(annotated)
    if product.product_type == Product.ProductType.VARIABLE:
        return product.pk in available_product_ids([product.pk])
    return product.stock > 0
