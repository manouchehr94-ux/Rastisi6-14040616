"""مرجعِ واحدِ «استعلام قیمت» (Price Inquiry).

مرچنت می‌تواند «استعلام قیمت» را برای یک کالا (``Product.price_mode_override``)،
یک گروه/دسته (``Category.price_mode``، شاملِ زیرگروه‌ها) یا یک کالکشنِ
انتخابی (``MerchantCollection.price_mode``) فعال کند. قاعده‌ی تقدم (رسمی و
تست‌شده):

1. انتخابِ صریحِ کالا (``standard`` یا ``inquiry``) همیشه برنده است؛
2. وگرنه اگر دسته‌ی کالا یا یکی از والدهایش، یا هر کالکشنِ *فعالِ* حاویِ آن،
   ``inquiry`` باشد ⇒ استعلامی؛
3. وگرنه قیمتِ عادی.

مقدارِ مؤثر در ``Product.is_price_inquiry`` ذخیره می‌شود تا کارت، فیلتر، سبد و
سفارش بدونِ N+1 از آن بخوانند. این ماژول تنها نویسنده‌ی آن فیلد است. قیمتِ
عددیِ کالا، تخفیف و موجودی هرگز تغییر نمی‌کنند — فقط *نمایش* و *قابلیتِ خرید*.
"""

from django.db.models import Q

from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, PriceMode, Product

INQUIRY_LABEL_FA = "استعلام قیمت"
INQUIRY_REFUSAL_FA = "قیمت این کالا با استعلام تعیین می‌شود و امکان خرید مستقیم ندارد."


def _category_chain_ids(category) -> list:
    ids, seen, node = [], set(), category
    while node is not None and node.pk not in seen:
        ids.append(node.pk)
        seen.add(node.pk)
        node = node.parent
    return ids


def effective_is_inquiry(product) -> bool:
    """مقدارِ مؤثرِ استعلام برایِ یک کالا — مستقیماً از دیتابیس (بدونِ کش)."""
    override = product.price_mode_override
    if override == PriceMode.STANDARD:
        return False
    if override == PriceMode.INQUIRY:
        return True
    if product.category_id:
        category = Category.objects.select_related("parent__parent").filter(pk=product.category_id).first()
        if category is not None and Category.objects.filter(
            pk__in=_category_chain_ids(category), price_mode=PriceMode.INQUIRY,
        ).exists():
            return True
    if product.pk and MerchantCollectionItem.objects.filter(
        product_id=product.pk, collection__is_active=True, collection__price_mode=PriceMode.INQUIRY,
    ).exists():
        return True
    return False


def recompute_product(product) -> bool:
    """مقدارِ مؤثر را روی نمونه و دیتابیس همگام می‌کند؛ ``True`` اگر عوض شد."""
    value = effective_is_inquiry(product)
    changed = product.is_price_inquiry != value
    product.is_price_inquiry = value
    if changed and product.pk:
        Product.objects.filter(pk=product.pk).update(is_price_inquiry=value)
    return changed


def recompute_store(store) -> int:
    """بازمحاسبه‌ی دسته‌جمعیِ همه‌ی کالاهایِ یک فروشگاه (چند کوئریِ ثابت).
    تعدادِ کالاهایی که مقدارشان عوض شد را برمی‌گرداند."""
    inquiry_categories = set(
        Category.objects.filter(store=store, price_mode=PriceMode.INQUIRY).values_list("pk", flat=True)
    )
    # هر دسته‌ای که خودش یا یکی از والدهایش استعلامی است.
    parent_of = dict(Category.objects.filter(store=store).values_list("pk", "parent_id"))
    affected_categories = set()
    for cat_id in parent_of:
        node, seen = cat_id, set()
        while node is not None and node not in seen:
            if node in inquiry_categories:
                affected_categories.add(cat_id)
                break
            seen.add(node)
            node = parent_of.get(node)
    in_inquiry_collection = set(
        MerchantCollectionItem.objects.filter(
            collection__store=store, collection__is_active=True, collection__price_mode=PriceMode.INQUIRY,
        ).values_list("product_id", flat=True)
    )

    products = Product.objects.filter(store=store)
    inherited = Q(price_mode_override="") & (
        Q(category_id__in=affected_categories) | Q(pk__in=in_inquiry_collection)
    )
    should_be_true = products.filter(Q(price_mode_override=PriceMode.INQUIRY) | inherited)
    should_be_false = products.exclude(pk__in=should_be_true.values("pk"))
    changed = should_be_true.filter(is_price_inquiry=False).update(is_price_inquiry=True)
    changed += should_be_false.filter(is_price_inquiry=True).update(is_price_inquiry=False)
    return changed


def set_product_mode(product, mode) -> None:
    """مرچنت: انتخابِ صریحِ حالتِ یک کالا ('' برایِ ارث‌بری). مقدارِ مؤثر را هم همگام می‌کند."""
    if mode not in ("", PriceMode.STANDARD, PriceMode.INQUIRY):
        raise ValueError("حالت قیمت‌گذاری نامعتبر است.")
    product.price_mode_override = mode
    product.save(update_fields=["price_mode_override"])
    recompute_product(product)


def bulk_set_product_mode(store, products, mode) -> int:
    """همان انتخابِ صریح برایِ چند کالا؛ کالای فروشگاهِ دیگر هرگز لمس نمی‌شود."""
    if mode not in ("", PriceMode.STANDARD, PriceMode.INQUIRY):
        raise ValueError("حالت قیمت‌گذاری نامعتبر است.")
    ids = [p.pk for p in products if p.store_id == store.pk]
    updated = Product.objects.filter(store=store, pk__in=ids).update(price_mode_override=mode)
    recompute_store(store)
    return updated


def inquiry_destination_url(store) -> str | None:
    """مقصدِ دکمه‌ی «استعلام قیمت»: صفحه‌ی «درباره ما»ی *همین* فروشگاه
    (طبقِ خواسته‌ی مالک). صفحه‌ی انتخاب‌شده در تنظیمات، وگرنه صفحه‌ی منتشرشده با
    اسلاگ ``about-us``. اگر نبود ``None`` — کلیک هیچ جا نمی‌رود و هیچ مقصدِ ساختگی
    ساخته نمی‌شود. توجه: باز شدنِ این صفحه *درخواستی ثبت یا ارسال نمی‌کند*."""
    from apps.content.models import ContentPage
    from apps.core.models import ShopSettings

    published = ContentPage.objects.filter(store=store, status=ContentPage.Status.PUBLISHED)
    try:
        configured = ShopSettings.load(store=store).price_inquiry_page_id
    except Exception:  # noqa: BLE001 — فروشگاهِ بدونِ ShopSettings: به fallback برو
        configured = None
    page = published.filter(pk=configured).first() if configured else None
    if page is None:
        page = published.filter(slug="about-us").first()
    return page.get_absolute_url() if page is not None else None
