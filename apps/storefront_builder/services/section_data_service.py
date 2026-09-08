"""حلِ منبعِ داده‌یِ «بخشِ محصول» (فازِ C) — تنها نقطه‌ی ورودیِ مجاز برایِ
تبدیلِ تنظیماتِ اعتبارسنجی‌شده‌یِ یک section (خروجیِ
``section_registry._validate_product_section_settings``) به فهرستِ واقعیِ
Product برایِ رندر.

اعتبارسنجیِ مالکیتِ Store برایِ ارجاعات (``source_id``/``product_ids``) —
که در ``section_registry.py`` عمداً انجام نشده (به مستندسازیِ بالایِ آن
فایل مراجعه شود) — همینجا انجام می‌شود: هر ارجاعِ حذف‌شده/غیرفعال/متعلق
به فروشگاهِ دیگر بی‌صدا به «بدون کالا» تبدیل می‌شود (fail closed، بدون
کرش) — دقیقاً همان فلسفه‌ای که ``build_render_items`` برایِ section_key
ناشناخته دارد: صفحه هرگز نباید به‌خاطرِ یک ارجاعِ کهنه/نامعتبر خراب شود."""

from __future__ import annotations

from urllib.parse import urlencode

from django.db.models import Q
from django.urls import reverse

from apps.catalog.models import Brand, Category, MerchantCollection
from apps.catalog.services import collection_service
from apps.catalog.services.collection_service import searchable_products
from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.orders.services import best_seller_service
from apps.storefront_builder import resource_source


class ResourceSourceOwnershipError(ValueError):
    """A ``ResourceSource``'s manual id(s) or auto-rule ``source_id`` do not
    belong to the current Store — raised before anything is persisted."""


def _require_owned_resource(model, *, store, source_id: int) -> None:
    """Fail closed: a foreign-Store id and a nonexistent id both simply fail
    this single Store-scoped ``exists()`` check — never a second query
    against another Store to tell them apart (never leaks *which* reason)."""
    if not model.objects.filter(store=store, pk=source_id).exists():
        raise ResourceSourceOwnershipError("invalid_resource_ownership")


def validate_resource_source_ownership(*, store, source: "resource_source.ResourceSource") -> None:
    """Phase 4 (Task 2) — the ONE shared, DB-backed Store-ownership check for
    a ``ResourceSource``, used by BOTH the legacy settings-save view and the
    R4 mutation service. Every manual id / auto-rule ``source_id`` a
    ``source`` actually references must belong to the current Store BEFORE
    the settings are persisted — a Store-scoped Picker/search endpoint alone
    does not stop a client from POSTing an arbitrary foreign-Store id
    straight to a save endpoint.

    ``resource_source.py`` itself stays a pure, DB-free domain module (its
    own hard rule) — every DB lookup this check needs lives only here, in
    this service, which already owns Store-ownership resolution for the
    same resource kinds at render time (see the module docstring above).
    """
    if source.kind == "product":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_ids = set(
                searchable_products(store).filter(pk__in=source.manual_ids).values_list("pk", flat=True)
            )
            if owned_ids != set(source.manual_ids):
                raise ResourceSourceOwnershipError("invalid_resource_ownership")
            return
        if source.auto_rule == "by_category":
            _require_owned_resource(Category, store=store, source_id=source.auto_parameters["source_id"])
        elif source.auto_rule == "by_brand":
            _require_owned_resource(Brand, store=store, source_id=source.auto_parameters["source_id"])
        elif source.auto_rule == "by_collection":
            _require_owned_resource(MerchantCollection, store=store, source_id=source.auto_parameters["source_id"])
        # newest/discounted/best_sellers/most_viewed reference no specific
        # resource id — nothing to own-check.
        return

    if source.kind == "brand":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_count = Brand.objects.filter(store=store, pk__in=source.manual_ids).count()
            if owned_count != len(set(source.manual_ids)):
                raise ResourceSourceOwnershipError("invalid_resource_ownership")
        # auto_rule == "all_active" references no specific resource id.
        return

    if source.kind == "collection":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_count = MerchantCollection.objects.filter(
                store=store, pk__in=source.manual_ids,
            ).count()
            if owned_count != len(set(source.manual_ids)):
                raise ResourceSourceOwnershipError("invalid_resource_ownership")
        # auto_rule == "all_active" references no specific resource id.
        return

    if source.kind == "category":
        if source.mode == "manual":
            if not source.manual_ids:
                return
            owned_count = Category.objects.filter(store=store, pk__in=source.manual_ids).count()
            if owned_count != len(set(source.manual_ids)):
                raise ResourceSourceOwnershipError("invalid_resource_ownership")
        # auto_rule == "all_active" references no specific resource id.
        return


def _reorder_by_ids(products_by_id: dict, ordered_ids: list) -> list:
    return [products_by_id[pid] for pid in ordered_ids if pid in products_by_id]


def products_in_collection(store, collection, limit: int) -> list:
    """Real products for an already-resolved ``MerchantCollection`` object
    — the ID-free half of ``_resolve_collection`` below, extracted so
    Part 2D's ``catalog_product_wall`` (which resolves the Store's own
    real collections directly, never by a stored ``source_id``) can reuse
    the exact same product query."""
    items = collection_service.collection_visible_items(collection, store)[:limit]
    return [item.product for item in items]


def products_in_category(store, category, limit: int) -> list:
    """Real products for an already-resolved ``Category`` object — the
    ID-free half of ``_resolve_category`` below, reused by Part 2D's
    ``catalog_product_wall``. Same exact filter as
    ``catalog.views._filtered_products``: a parent category also includes
    its children's products."""
    return list(
        storefront_listing_products(store)
        .filter(Q(category=category) | Q(category__parent=category))
        .select_related("brand").prefetch_related("images")
        .order_by("-created_at", "id")[:limit]
    )


def resolve_category_representative_media(category):
    """Generic, ID-free, Store-agnostic: the cover image of a real,
    currently active product in this category (or its subcategories) —
    reuses ``Product.cover_image``, the same N+1-safe cover-image
    convention every product card already uses.

    Root-cause note (mission: category mosaic "colored frame around a
    small photo" complaint): ``Category.image`` is NOT a raw product
    photo — it is a deliberately composed 800x600 canvas (a colored/
    gradient background with the product pasted at ~86% height, centered
    in its own narrower slot; see ``seed_ready_template_fashion_demo.
    _composite_visual_bytes``/``_seed_category_images``). That framing is
    baked into the image bytes themselves, so no CSS crop/object-fit
    treatment can ever make it read as edge-to-edge — cropping a
    fixed-margin image only removes a fraction of the margin before
    cutting into the product itself. A real product photo has no such
    guaranteed margin, so it is the correct source for an edge-to-edge
    tile treatment. Returns ``None`` (never raises) if the category has
    no active product with any image at all — callers must fall back
    (e.g. to ``category.image`` or an icon), matching this module's own
    fail-closed convention."""
    product = (
        storefront_listing_products(category.store)
        .filter(Q(category=category) | Q(category__parent=category))
        .prefetch_related("images")
        .order_by("-created_at", "id")
        .first()
    )
    if product is None:
        return None
    return product.cover_image


def _resolve_collection(store, settings: dict):
    source_id = settings.get("source_id")
    if not source_id:
        return [], None
    try:
        collection = collection_service.get_scoped_collection(store, source_id)
    except collection_service.CollectionNotFoundError:
        return [], None
    if not collection.is_active:
        return [], None

    products = products_in_collection(store, collection, settings["item_limit"])
    view_all_url = reverse("catalog:collection-detail", args=[collection.slug])
    return products, view_all_url


def _resolve_category(store, settings: dict):
    source_id = settings.get("source_id")
    if not source_id:
        return [], None
    try:
        category = Category.objects.get(pk=source_id, store=store, is_active=True)
    except Category.DoesNotExist:
        return [], None

    products = products_in_category(store, category, settings["item_limit"])
    view_all_url = reverse("catalog:product-list") + "?" + urlencode({"category": category.slug})
    return products, view_all_url


def _resolve_brand(store, settings: dict):
    source_id = settings.get("source_id")
    if not source_id:
        return [], None
    try:
        brand = Brand.objects.get(pk=source_id, store=store, is_active=True)
    except Brand.DoesNotExist:
        return [], None

    limit = settings["item_limit"]
    products = list(
        storefront_listing_products(store).filter(brand=brand)
        .select_related("brand").prefetch_related("images")
        .order_by("-created_at", "id")[:limit]
    )
    view_all_url = reverse("catalog:product-list") + "?" + urlencode({"brand": brand.slug})
    return products, view_all_url


def _resolve_manual(store, settings: dict):
    """کالاهایِ دستیِ مرچنت — ``product_ids`` (اعتبارسنجی‌شده در
    section_registry: بدونِ تکرار، حداکثر ۶۰ عدد) به همان ترتیبِ
    انتخابِ مرچنت رندر می‌شود، نه ترتیبِ دلخواهِ دیتابیس. ``pk__in``
    ترتیب را حفظ نمی‌کند، پس فهرست دستی طبقِ ``product_ids`` بازسازی
    می‌شود (همان الگویِ ``collection_products_add``ی فازِ B). کالایِ
    حذف‌شده/متعلق به فروشگاهِ دیگر/دیگر storefront-visible نبودن، بی‌صدا
    از فهرست کنار گذاشته می‌شود — نه خطا."""
    product_ids = settings.get("product_ids") or []
    if not product_ids:
        return [], None
    limit = settings["item_limit"]
    products_by_id = {
        p.pk: p
        for p in storefront_listing_products(store).filter(pk__in=product_ids)
        .select_related("brand").prefetch_related("images")
    }
    products = _reorder_by_ids(products_by_id, product_ids)[:limit]
    return products, None


def _resolve_newest(store, settings: dict):
    limit = settings["item_limit"]
    products = list(
        storefront_listing_products(store).select_related("brand").prefetch_related("images")
        .order_by("-created_at", "id")[:limit]
    )
    return products, None


def _resolve_discounted(store, settings: dict):
    limit = settings["item_limit"]
    products = list(
        storefront_listing_products(store).filter(discount_percent__gt=0)
        .select_related("brand").prefetch_related("images")
        .order_by("-discount_percent", "id")[:limit]
    )
    return products, None


def _resolve_best_sellers(store, settings: dict):
    """پرفروش‌ترین‌هایِ واقعی — از ``best_seller_service`` (محاسبه‌ی زنده
    از OrderItem، تنها الگوریتمِ مجازِ کل کدبیس)، **نه** از
    ``Product.sold_count``."""
    limit = settings["item_limit"]
    product_ids = best_seller_service.best_selling_product_ids(store, limit=limit)
    if not product_ids:
        return [], None
    products_by_id = {
        p.pk: p
        for p in storefront_listing_products(store).filter(pk__in=product_ids)
        .select_related("brand").prefetch_related("images")
    }
    return _reorder_by_ids(products_by_id, product_ids), None


def _resolve_most_viewed(store, settings: dict):
    """``Product.views_count`` — بر خلافِ ``sold_count``، این فیلد واقعاً
    نوشته می‌شود (``apps.catalog.views.product_detail``، هر بازدید)، پس
    مستقیماً قابلِ استفاده است (به مستندسازیِ ممیزیِ فازِ C مراجعه شود)."""
    limit = settings["item_limit"]
    products = list(
        storefront_listing_products(store).select_related("brand").prefetch_related("images")
        .order_by("-views_count", "id")[:limit]
    )
    return products, None


_RESOLVERS = {
    "collection": _resolve_collection,
    "category": _resolve_category,
    "brand": _resolve_brand,
    "manual": _resolve_manual,
    "newest": _resolve_newest,
    "discounted": _resolve_discounted,
    "best_sellers": _resolve_best_sellers,
    "most_viewed": _resolve_most_viewed,
}


def resolve_products(store, settings: dict) -> tuple[list, str | None]:
    """فهرستِ Product نهایی (به ترتیبِ صحیح، حداکثر ``item_limit`` عدد) و
    آدرسِ اختیاریِ «مشاهده همه» را برایِ ``data_source`` این section
    برمی‌گرداند. برایِ منبعِ نامعتبر/هنوز-پیاده‌سازی‌نشده، فهرستِ خالی
    (نه خطا) — همان قراردادِ fail-closedِ بالا."""
    resolver = _RESOLVERS.get(settings.get("data_source"))
    if resolver is None:
        return [], None
    return resolver(store, settings)
