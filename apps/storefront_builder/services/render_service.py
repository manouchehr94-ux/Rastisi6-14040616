"""رندر یک نسخه‌ی چیدمان (Draft یا منتشرشده) به فهرستی از بخش‌های آماده‌ی نمایش.

این ماژول تنها نقطه‌ی مشترک بین پیش‌نمایش ادیتور (Draft) و صفحه اصلی عمومی
(نسخه‌ی منتشرشده) است — دقیقاً همان چیزی که تصمیم کاربر می‌خواهد: «Public
storefront must never read the editable draft» یعنی هر دو مسیر از همین
رندرکننده استفاده می‌کنند اما همیشه با یک ``StorefrontLayoutVersion`` مشخص
که فراخوان (view) آن را انتخاب کرده — پیش‌نمایش version=draft، صفحه‌ی عمومی
version=published — نه خودِ این سرویس هرگز تصمیم نمی‌گیرد کدام نسخه.

هر بخش با استفاده از سرویس‌های *موجود* catalog/content داده می‌گیرد — نه
بازنویسیِ قوانینِ «قابل‌مشاهده بودن» — دقیقاً همان الگویی که
``apps.catalog.views.home`` از قبل استفاده می‌کند.
"""

from __future__ import annotations

from copy import copy

from apps.catalog.models import Brand, Category
from apps.catalog.services.product_publish_service import storefront_listing_products
from apps.content.models import HeroSlide, PromotionalBanner
from apps.orders.services import best_seller_service

from .. import appearance_registry
from ..section_registry import (
    CARD_AWARE_SECTION_KEYS,
    UnknownSectionTypeError,
    default_brand_carousel_settings,
    default_category_grid_settings,
    default_quick_links_settings,
    get_definition,
)
from ..storefront_appearance.rendering import (
    ResolvedStoreAppearance,
    badge_settings_for,
    card_settings_for,
    global_renderer_template as store_appearance_global_renderer_template,
    resolve_store_appearance_render_state,
    section_variant_for as store_appearance_section_variant_for,
)
from ..variant_contract import resolve_active_variant, resolve_renderer_template
from . import section_appearance_service, section_data_service

TILE_CLASSES = ["t1", "t2", "t3"]


_DESTINATION_SELECT_RELATED = (
    "destination_category", "destination_product", "destination_brand", "destination_collection",
)


def _scoped_hero_slides(store, section):
    """اسلایدهای *مخصوصِ همین نمونه* section (اگر مرچنت از داخل سازنده
    بصری برایِ آن اسلاید اضافه کرده) — اگر این section هیچ اسلایدِ
    اختصاصی نداشت، به اسلایدهای سراسریِ فروشگاه (section=None، رفتارِ
    قدیمیِ پیش از این چکپوینت) برمی‌گردد. این دقیقاً همان مکانیزمی است که
    اجازه می‌دهد دو نمونه‌ی اسلایدر مستقل (با اسلایدهای متفاوت) وجود
    داشته باشند، بدون این‌که فروشگاه‌های قدیمی که هرگز این ویژگی را لمس
    نکرده‌اند رفتارشان تغییر کند."""
    # Phase 5, Task 1 — an unsaved (``pk=None``) candidate-preview section
    # (``preset_service.resolve_preset_candidate``) can never have its own
    # scoped slides yet (nothing merchant-authored can reference a row that
    # was never persisted) — this is exactly the same "no scoped slides"
    # case the store-wide fallback below already exists for, just reached
    # without first attempting an FK filter Django rejects for an unsaved
    # instance. Behavior for a real, saved section is completely unchanged.
    if section.pk is not None:
        scoped = HeroSlide.objects.filter(section=section, is_active=True).select_related(
            *_DESTINATION_SELECT_RELATED,
        ).order_by("display_order", "id")
        if scoped.exists():
            return scoped
    else:
        # Phase 5, Task 2 (browser-QA finding) — the store-wide
        # (``section=None``) fallback right below only helps a candidate
        # preview if the store has genuinely UNSCOPED Hero content. Real
        # seeded stores (e.g. the canonical ``rasti-mode-demo``) scope ALL
        # their Hero content to whichever real section the currently-applied
        # Ready Template actually created — there is no unscoped row to fall
        # back to, so a candidate preview of a DIFFERENT template showed no
        # Hero content at all, even though the store plainly owns some. This
        # third tier reuses the store's own real Hero content from ANY of
        # its non-archived ``hero_banner`` sections (Draft or Published —
        # never a stale archived version) before giving up to the
        # store-wide fallback — the same "show what the store really owns"
        # principle the store-wide tier already embodies, just not blocked
        # by an exact (impossible, for an unsaved section) pk match.
        from ..models import StorefrontLayoutVersion

        same_key_scoped = HeroSlide.objects.filter(
            section__section_key=section.section_key,
            section__page__version__layout__store=store,
            section__page__version__status__in=(
                StorefrontLayoutVersion.Status.DRAFT, StorefrontLayoutVersion.Status.PUBLISHED,
            ),
            is_active=True,
        ).select_related(*_DESTINATION_SELECT_RELATED).order_by("display_order", "id")
        if same_key_scoped.exists():
            return same_key_scoped
    return HeroSlide.objects.filter(store=store, section__isnull=True, is_active=True).select_related(
        *_DESTINATION_SELECT_RELATED,
    ).order_by("display_order", "id")


def _hero_banner_context(store, section):
    from ..section_registry import default_slider_settings

    slider_settings = {**default_slider_settings(), **(section.settings or {})}
    return {
        "hero_slides": _scoped_hero_slides(store, section),
        "slider_settings": slider_settings,
        # فقط مصرف‌شونده توسط Familyهایی که زیرِ Hero یک ردیفِ بنرِ کوچک
        # می‌خواهند (مثلِ modern_fashion — نگاه کنید به گزارشِ
        # 11_REFERENCE_FIDELITY_GAP_ANALYSIS.md)؛ برای بقیه بی‌اثر است.
        "banners": _scoped_banners(store, section),
    }


def _image_slider_context(store, section):
    return _hero_banner_context(store, section)


def _scoped_banners(store, section):
    # Phase 5, Task 1 — same unsaved-candidate-section guard as
    # ``_scoped_hero_slides`` above; identical reasoning.
    if section.pk is not None:
        scoped = PromotionalBanner.objects.filter(section=section, is_active=True).select_related(
            *_DESTINATION_SELECT_RELATED,
        ).order_by("display_order", "id")
        if scoped.exists():
            return scoped
    else:
        # Phase 5, Task 2 (browser-QA finding) — same third fallback tier as
        # ``_scoped_hero_slides`` above; identical reasoning (the Demo
        # Store's real Banner content is scoped to whichever real section
        # the currently-applied Ready Template created, not to
        # ``section=None``).
        from ..models import StorefrontLayoutVersion

        same_key_scoped = PromotionalBanner.objects.filter(
            section__section_key=section.section_key,
            section__page__version__layout__store=store,
            section__page__version__status__in=(
                StorefrontLayoutVersion.Status.DRAFT, StorefrontLayoutVersion.Status.PUBLISHED,
            ),
            is_active=True,
        ).select_related(*_DESTINATION_SELECT_RELATED).order_by("display_order", "id")
        if same_key_scoped.exists():
            return same_key_scoped
    return PromotionalBanner.objects.filter(store=store, section__isnull=True, is_active=True).select_related(
        *_DESTINATION_SELECT_RELATED,
    ).order_by("display_order", "id")


def _single_banner_context(store, section):
    return {"banners": _scoped_banners(store, section)[:1]}


def _multi_banner_context(store, section):
    """Resolve a reusable slice of active promotional banners.

    ``offset``/``item_limit`` live in the section JSON so several independent
    banner blocks can compose different parts of the same Store-owned banner
    pool without hard-coded banner IDs.  Values are clamped defensively; old
    sections without either key keep the legacy behaviour (all banners).
    """
    settings = section.settings or {}
    try:
        offset = max(0, min(50, int(settings.get("offset", 0))))
    except (TypeError, ValueError):
        offset = 0
    raw_limit = settings.get("item_limit")
    if raw_limit in (None, ""):
        return {"banners": _scoped_banners(store, section)}
    try:
        limit = max(1, min(24, int(raw_limit)))
    except (TypeError, ValueError):
        limit = 24
    return {"banners": _scoped_banners(store, section)[offset:offset + limit]}


def _category_grid_context(store, section):
    """چکپوینتِ ۱۱: اگر مرچنت صراحتاً دسته‌بندی انتخاب کرده باشد
    (``category_ids``)، دقیقاً همان‌ها به همان ترتیب نمایش داده می‌شوند —
    وگرنه (فروشگاهی که هنوز این تنظیمات را لمس نکرده) دقیقاً همان
    رفتارِ auto-pick قبل از این چکپوینت (۳+۱ دسته‌ی اولِ فعالِ سطحِ اول)
    بازتولید می‌شود. ``pk__in`` ترتیب را حفظ نمی‌کند، پس فهرستِ
    انتخاب‌شده دستی طبقِ همان ترتیبِ ذخیره‌شده بازسازی می‌شود (همان الگویِ
    ``_best_sellers_context``)."""
    category_ids = (section.settings or {}).get("category_ids") or []
    if category_ids:
        by_id = {
            c.pk: c for c in Category.objects.filter(store=store, pk__in=category_ids, is_active=True)
        }
        categories = [by_id[cid] for cid in category_ids if cid in by_id]
    else:
        categories = list(
            Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
        )
    settings = {**default_category_grid_settings(), **(section.settings or {})}
    try:
        item_limit = max(2, min(12, int(settings.get("item_limit", 12))))
    except (TypeError, ValueError):
        item_limit = 12
    top_categories = categories[:item_limit]
    # Micro-fix pass — merchant: fashion_mosaic tiles must show the image
    # edge-to-edge, but ``category.image`` is a deliberately composed
    # thumbnail with large baked-in colored margins (see
    # ``section_data_service.resolve_category_representative_media``'s own
    # docstring for the full root-cause). Only the two media-first display
    # modes that explicitly need uncropped representative photography pay
    # for the extra per-category product lookup; every other category_grid
    # variant keeps reading ``category.image`` exactly as before.
    if settings.get("display_mode") in {"fashion_mosaic", "beauty_icons", "atelier_mosaic", "luxury_shortcuts"}:
        for category in top_categories:
            category.representative_media = section_data_service.resolve_category_representative_media(category)
    return {
        "tiles": list(zip(categories[:3], TILE_CLASSES)),
        "cream_category": categories[3] if len(categories) > 3 else None,
        "top_categories": top_categories,
        "category_grid_settings": settings,
    }


def _catalog_product_wall_context(store, section):
    """Site-target-overhaul Part 2D — the generic, ID-free multi-row
    merchandising wall (see ``section_registry.CATALOG_PRODUCT_WALL_
    SOURCE_MODES``'s own docstring for the full architecture rationale).

    Resolves the CURRENT Store's own real, visible top-level categories
    and/or merchant collections — the exact same auto-pick query
    ``_category_grid_context`` above already uses when its own
    ``category_ids`` is empty, plus the equivalent for
    ``MerchantCollection`` — and returns one compact product group per
    real, non-empty result, up to ``max_groups``. No ``source_id``, no
    Store slug, no ``if template_key ==`` branch: this function is a pure
    function of ``store`` and this section's own generic settings, so any
    Ready Template may select this section for any Store."""
    from ..section_registry import default_catalog_product_wall_settings

    settings = {**default_catalog_product_wall_settings(), **(section.settings or {})}
    source_mode = settings["source_mode"]
    max_groups = settings["max_groups"]
    products_per_group = settings["products_per_group"]
    minimum_products = settings["minimum_products"] if settings["skip_empty_groups"] else 0
    show_view_all = settings["show_view_all"]

    from urllib.parse import urlencode

    from django.urls import reverse

    # Part 2D — with a modest catalog, a per-category/collection group can
    # end up showing the exact same handful of products (just reordered)
    # as one of this page's own generic ``product_section`` rows
    # (discounted/newest/best_sellers/most_viewed, or a merchant-added
    # one) — a real "duplicate merchandising row" a reviewer would spot
    # immediately. Excluding whatever a SIBLING ``product_section`` on
    # this same page already shows keeps every group here genuinely
    # additive. Generic (any sibling instance, not a hardcoded data
    # source) and fully local to this function — no shared render-pipeline
    # state needs threading through ``build_page_render_items`` for it.
    sibling_product_ids = set()
    for sibling in section.page.sections.filter(section_key="product_section", is_active=True):
        sibling_products, _ = section_data_service.resolve_products(store, sibling.settings or {})
        sibling_product_ids.update(product.pk for product in sibling_products)

    #: Over-fetch before filtering out sibling-shown products, so a group
    #: can still reach ``products_per_group`` items when some of its
    #: natural top results were already used elsewhere on the page.
    _FETCH_MULTIPLIER = 3

    groups = []

    def _add_category(category):
        if len(groups) >= max_groups:
            return
        candidates = section_data_service.products_in_category(store, category, products_per_group * _FETCH_MULTIPLIER)
        products = [p for p in candidates if p.pk not in sibling_product_ids][:products_per_group]
        if len(products) < minimum_products:
            return
        view_all_url = None
        if show_view_all:
            view_all_url = reverse("catalog:product-list") + "?" + urlencode({"category": category.slug})
        groups.append({"title": category.name, "products": products, "view_all_url": view_all_url})

    def _add_collection(collection):
        if len(groups) >= max_groups:
            return
        candidates = section_data_service.products_in_collection(store, collection, products_per_group * _FETCH_MULTIPLIER)
        products = [p for p in candidates if p.pk not in sibling_product_ids][:products_per_group]
        if len(products) < minimum_products:
            return
        view_all_url = reverse("catalog:collection-detail", args=[collection.slug]) if show_view_all else None
        groups.append({"title": collection.name, "products": products, "view_all_url": view_all_url})

    if source_mode in ("visible_categories", "categories_then_collections") and len(groups) < max_groups:
        categories = Category.objects.filter(
            store=store, parent__isnull=True, is_active=True,
        ).order_by("order", "name")
        for category in categories:
            _add_category(category)

    if source_mode in ("visible_collections", "categories_then_collections") and len(groups) < max_groups:
        from apps.catalog.models import MerchantCollection

        collections = MerchantCollection.objects.filter(store=store, is_active=True).order_by("-created_at")
        for collection in collections:
            _add_collection(collection)

    return {"catalog_product_wall_groups": groups, "catalog_product_wall_settings": settings}


def _newest_products_context(store, section):
    item_limit = (section.settings or {}).get("item_limit", 8)
    products = (
        storefront_listing_products(store).select_related("brand").prefetch_related("images", "metafields")
        .order_by("-created_at")[:item_limit]
    )
    return {"products": products}


def _best_sellers_context(store, section):
    """پرفروش‌ترین‌هایِ واقعی — از ``best_seller_service`` (محاسبه‌ی زنده
    از OrderItem)، **نه** ``Product.sold_count`` که هیچ writer‌ای ندارد
    (به مستندسازیِ ``best_seller_service`` مراجعه شود). ``pk__in`` ترتیبِ
    رتبه را حفظ نمی‌کند، پس فهرست دستی طبقِ همان ترتیبِ رتبه‌بندی بازسازی
    می‌شود (همان الگویِ ``collection_products_add``ی فازِ B)."""
    item_limit = (section.settings or {}).get("item_limit", 8)
    product_ids = best_seller_service.best_selling_product_ids(store, limit=item_limit)
    if not product_ids:
        return {"products": []}
    products_by_id = {
        p.pk: p
        for p in storefront_listing_products(store).filter(pk__in=product_ids)
        .select_related("brand").prefetch_related("images", "metafields")
    }
    products = [products_by_id[pid] for pid in product_ids if pid in products_by_id]
    return {"products": products}


def _discounted_products_context(store, section):
    item_limit = (section.settings or {}).get("item_limit", 6)
    products = (
        storefront_listing_products(store).select_related("brand").prefetch_related("images", "metafields")
        .filter(discount_percent__gt=0).order_by("-discount_percent")[:item_limit]
    )
    return {"products": products}


def _amazing_offers_context(store, section):
    from django.utils import timezone
    from datetime import timedelta

    settings = section.settings or {}
    item_limit = settings.get("item_limit", 1)
    deadline_hours = settings.get("deadline_hours", 8)
    products = list(
        storefront_listing_products(store).filter(discount_percent__gt=0)
        .select_related("brand").prefetch_related("images", "metafields")
        .order_by("-discount_percent")[:item_limit]
    )
    return {
        "products": products,
        "product": products[0] if products else None,
        "deadline": (timezone.now() + timedelta(hours=deadline_hours)).isoformat(),
    }


def _blog_posts_context(store, section):
    """مطالبِ وبلاگ سراسریِ پلتفرم است (بدونِ FK به Store — واقعیتی از
    قبل موجود در ``apps.blog.models.BlogPost``، نه فیلترِ تنانتی که این
    تابع اضافه می‌کند)؛ دقیقاً همان کوئری‌ای که ``apps.catalog.views.home``
    از قبل استفاده می‌کند."""
    from apps.blog.models import BlogPost

    item_limit = (section.settings or {}).get("item_limit", 5)
    posts = list(BlogPost.objects.order_by("-published_at")[:item_limit])
    return {"posts": posts}


def _featured_products_context(store, section):
    # هیچ فیلد is_featured‌ای در Product وجود ندارد (شکاف تأییدشده در گزارش
    # ممیزی) — تا زمانی که آن قابلیت واقعاً ساخته شود، این بخش از جدیدترین‌ها
    # استفاده می‌کند تا هرگز داده‌ی جعلی/ثابت نشان ندهد.
    return _newest_products_context(store, section)


def _brand_carousel_context(store, section):
    """چکپوینتِ ۱۱: همان الگویِ ``_category_grid_context`` — ``brand_ids``
    خالی یعنی رفتارِ auto (همه‌ی برندهایِ فعال) دست‌نخورده می‌ماند."""
    settings = {**default_brand_carousel_settings(), **(section.settings or {})}
    brand_ids = settings["brand_ids"]
    if brand_ids:
        by_id = {b.pk: b for b in Brand.objects.filter(store=store, pk__in=brand_ids, is_active=True)}
        brands = [by_id[bid] for bid in brand_ids if bid in by_id]
    else:
        brands = list(Brand.objects.filter(store=store, is_active=True).order_by("sort_order", "name"))

    view_all_url = None
    if settings["show_view_all"]:
        destination = (section.settings or {}).get("destination") or {}
        if destination.get("destination_type", "none") != "none":
            from apps.content.services import resolve_destination_setting

            resolved = resolve_destination_setting(store, destination)
            view_all_url = resolved["url"]

    return {"brands": brands, "brand_carousel_settings": settings, "view_all_url": view_all_url}


def _collection_tiles_context(store, section):
    """چکپوینتِ ۱۲: بخشِ جدید — خودِ MerchantCollectionها را نشان می‌دهد
    (نه کالاهایِ داخلشان). ``collection_ids`` خالی = همه‌ی کالکشن‌های
    فعال (ترتیبِ ایجاد، جدیدترین اول)."""
    from apps.catalog.models import MerchantCollection

    collection_ids = (section.settings or {}).get("collection_ids") or []
    if collection_ids:
        by_id = {
            c.pk: c for c in MerchantCollection.objects.filter(store=store, pk__in=collection_ids, is_active=True)
        }
        collections = [by_id[cid] for cid in collection_ids if cid in by_id]
    else:
        collections = list(
            MerchantCollection.objects.filter(store=store, is_active=True).order_by("-created_at")
        )
    # شمارشِ کالا با یک کوئریِ جمعی (annotate)، نه N+1 در تمپلیت
    from django.db.models import Count

    counts_qs = MerchantCollection.objects.filter(pk__in=[c.pk for c in collections]).annotate(item_count=Count("items"))
    counts_by_id = {row.pk: row.item_count for row in counts_qs}
    tiles = [{"collection": c, "item_count": counts_by_id.get(c.pk, 0)} for c in collections]
    return {"collection_tiles": tiles}


def _quick_links_context(store, section):
    """چکپوینتِ ۱۲: «دسترسی سریع» — یک Menuِ موجود (همان زیرساختِ
    Menu/MenuItem/Destinationِ ناوبریِ هدر/فوتر) را به‌شکلِ کارت‌هایِ
    بصری نشان می‌دهد؛ هیچ مدلِ لینکِ جدیدی ساخته نشده.

    ``Prefetch`` با یک queryset از پیش‌فیلترشده (نه ``prefetch_related``یِ
    ساده + یک ``.filter()`` دیگر رویِ ``menu.items`` بعداً) — وگرنه آن
    فیلترِ دوم یک کوئریِ کاملاً جدا اجرا می‌کرد و کشِ prefetch را بی‌اثر
    می‌گذاشت (همان الگویِ ``apps.content.context_processors.navigation_menus``)."""
    from django.db.models import Prefetch

    from apps.content.models import Menu, MenuItem
    from apps.content.services import resolve_destination_url

    settings = {**default_quick_links_settings(), **(section.settings or {})}
    menu_id = settings["menu_id"]
    items = []
    menu = None
    if menu_id:
        items_qs = MenuItem.objects.filter(is_active=True, parent__isnull=True).select_related(
            "destination_category", "destination_product", "destination_brand",
        ).order_by("display_order", "id")
        menu = Menu.objects.filter(store=store, pk=menu_id, is_active=True).prefetch_related(
            Prefetch("items", queryset=items_qs),
        ).first()
    if menu is not None:
        for menu_item in menu.items.all():
            url = resolve_destination_url(menu_item)
            if url:
                items.append({"title": menu_item.title, "url": url, "open_in_new_tab": menu_item.open_in_new_tab})
    return {"quick_link_items": items}


def _video_section_context(store, section):
    """چکپوینتِ ۱۲: از همان تشخیصِ ارائه‌دهنده/محاسبه‌ی embed_url که برایِ
    ویدیویِ کالا استفاده می‌شود عبور می‌کند (نه بازنویسیِ دوباره) — یک
    نمونه‌ی موقتِ (ذخیره‌نشده‌یِ) ``ProductVideo`` فقط برایِ عبور از همان
    منطق ساخته می‌شود."""
    video_url = (section.settings or {}).get("video_url") or ""
    if not video_url:
        return {"video_embed_url": None, "video_is_instagram": False, "video_permalink": None}

    from apps.catalog.models import ProductVideo
    from apps.catalog.services import product_video_service

    try:
        provider, _external_id = product_video_service.detect_provider_and_id(video_url)
    except product_video_service.ProductVideoError:
        return {"video_embed_url": None, "video_is_instagram": False, "video_permalink": None}

    temp_video = ProductVideo(provider=provider, url=video_url)
    if provider == ProductVideo.Provider.INSTAGRAM:
        return {"video_embed_url": None, "video_is_instagram": True,
                "video_permalink": product_video_service.instagram_permalink(temp_video)}
    return {"video_embed_url": product_video_service.embed_url(temp_video), "video_is_instagram": False, "video_permalink": None}


def _category_context_for_promo_cards(store, section):
    item_limit = (section.settings or {}).get("item_limit", 4)
    categories = Category.objects.filter(store=store, is_active=True).order_by("order", "name")[:item_limit]
    return {"categories": categories}


def _static_context(store, section):
    return {}


def _resolved_destination_context(store, section):
    """بلوکِ ``destination`` این section (اگر داشته باشد) را به URL/تب‌جدید
    واقعی حل می‌کند — برایِ انواعی که در ``DESTINATION_AWARE_SECTION_KEYS``
    عضوند و لینکشان واقعاً «سطحِ خودِ section» است (نه per-slide/per-banner
    مثلِ hero/banner که مقصدشان داخلِ خودِ مدلِ ``HeroSlide``/
    ``PromotionalBanner`` است)."""
    destination = (section.settings or {}).get("destination") or {}
    if destination.get("destination_type", "none") == "none":
        return {"destination": {"url": None, "open_new_tab": False, "rel": ""}}

    from apps.content.services import resolve_destination_setting

    return {"destination": resolve_destination_setting(store, destination)}


def _product_section_context(store, section):
    """برخلافِ همه‌ی builderهایِ دیگرِ این فایل، این یکی به تنظیماتِ
    خاصِ همین section (``data_source``/``source_id``/``product_ids``)
    وابسته است — پس در ``PER_INSTANCE_SECTION_KEYS`` زیر ثبت شده تا
    ``build_render_items`` آن را برایِ هر نمونه جداگانه محاسبه کند، نه
    یک‌بار برایِ کلِ section_key (بازنویسی‌شدن با کش، دقیقاً همان باگی
    که این پرچم برایِ جلوگیری از آن اضافه شده)."""
    products, view_all_url = section_data_service.resolve_products(store, section.settings or {})
    destination = (section.settings or {}).get("destination") or {}
    if destination.get("destination_type", "none") != "none":
        from apps.content.services import resolve_destination_setting

        resolved = resolve_destination_setting(store, destination)
        if resolved["url"]:
            view_all_url = resolved["url"]
    return {"products": products, "view_all_url": view_all_url}


#: کلیدهایی که context builder‌شان به تنظیماتِ خودِ همان نمونه‌ی section
#: وابسته است (نه فقط به store) — برایِ این‌ها، کشِ سطح-تابعِ
#: ``build_render_items`` باید per-instance باشد، وگرنه دو نمونه‌ی
#: تکرارشده (duplicable) با تنظیماتِ متفاوت (مثلاً دو کالکشنِ متفاوت)
#: محتوایِ یکسان (نمونه‌ی اول) نشان می‌دهند.
PER_INSTANCE_SECTION_KEYS = {
    "product_section", "image_text", "hero_banner", "image_slider", "single_banner", "multi_banner",
    "category_grid", "brand_carousel", "collection_tiles", "quick_links", "video_section", "story_rail",
    #: Part 2D — same reason as ``product_section``/``category_grid``
    #: above: this builder's output depends on the section's own
    #: ``source_mode``/``max_groups``/etc. settings, not just the Store.
    "catalog_product_wall",
    #: Phase 3 — این دو context builder هم اکنون به تنظیماتِ خودِ همان
    #: نمونه (``item_limit``/``deadline_hours``) وابسته‌اند، دقیقاً همان
    #: دلیلِ بالا (``product_section``).
    "amazing_offers", "blog_posts",
    #: Task 6 (Group B) — همین دلیل: از این چکپوینت به بعد،
    #: ``_newest_products_context``/``_best_sellers_context``/
    #: ``_discounted_products_context``/``_category_context_for_promo_cards``
    #: هم به ``item_limit``ی خودِ همان نمونه وابسته‌اند (پیش از این
    #: چکپوینت، این چهار context builder اصلاً به ``section.settings``
    #: نگاه نمی‌کردند — یک مقدارِ ثابتِ hardcode‌شده داشتند).
    "newest_products", "best_sellers", "discounted_products", "promo_cards",
}


def _story_rail_context(store, section):
    """ریلِ استوری — آیتم‌هایِ فعالِ همین Section (یا سراسریِ فروشگاه اگر
    section-specific نداشته باشد). همان الگویِ hero_slides."""
    from apps.content.models import StoryRailItem

    # Phase 5, Task 1 — same unsaved-candidate-section guard as
    # ``_scoped_hero_slides``/``_scoped_banners`` above; identical reasoning.
    # (Independent review, Task 1 — found missing here: ``story_rail`` is a
    # real registered section, used by the Ready Templates
    # ``playful_lifestyle``/``premium_boutique``, so a candidate preview of
    # either would otherwise raise on this exact FK filter.)
    if section.pk is not None:
        scoped = StoryRailItem.objects.filter(section=section, is_active=True).order_by("display_order", "id")
        if scoped.exists():
            return {"story_items": scoped}
    else:
        # Phase 5, Task 2 (browser-QA finding) — same third fallback tier as
        # ``_scoped_hero_slides``/``_scoped_banners`` above; identical
        # reasoning (the Demo Store's real StoryRailItem content is scoped
        # to whichever real section the currently-applied Ready Template
        # created, not to ``section=None``).
        from ..models import StorefrontLayoutVersion

        same_key_scoped = StoryRailItem.objects.filter(
            section__section_key=section.section_key,
            section__page__version__layout__store=store,
            section__page__version__status__in=(
                StorefrontLayoutVersion.Status.DRAFT, StorefrontLayoutVersion.Status.PUBLISHED,
            ),
            is_active=True,
        ).order_by("display_order", "id")
        if same_key_scoped.exists():
            return {"story_items": same_key_scoped}
    # Fallback: آیتم‌هایِ سراسریِ فروشگاه (section__isnull=True)
    return {"story_items": StoryRailItem.objects.filter(store=store, section__isnull=True, is_active=True).order_by("display_order", "id")}


#: Phase 5: توابعِ context-aware — امضایِ ``(store, section, page_context)``،
#: نه ``(store, section)``یِ معمولِ بالا. ``page_context`` همان دیکشنریِ
#: کاملی است که ویوِ مسیرِ عمومی (یا Preview، با یک نمونه‌یِ نماینده) از
#: قبل برایِ رندرِ سخت‌کدشده‌ی خودِ صفحه ساخته — یعنی محصول/کالکشن/جستجو/
#: سبدِ «جاری» هرگز از رویِ IDای که در ``settings`` ذخیره شده resolve
#: نمی‌شود (که مسیرِ Draft/Publish را می‌شکست و تفکیکِ Store را به خطر
#: می‌انداخت)، بلکه همیشه از همان کوئریِ موجود و از قبل تفکیک‌شده‌یِ Store
#: که ویو خودش زده resolve می‌شود — صفر کوئریِ اضافه، صفر منطقِ تکراری.


def _product_main_context(store, section, page_context):
    product = page_context.get("product")
    if product is None:
        return {}
    return {
        "product": product,
        "variant_selector": page_context.get("variant_selector"),
        "product_price_json": page_context.get("product_price_json"),
        "gallery_slides": page_context.get("gallery_slides"),
        "review_count": page_context.get("review_count", 0),
    }


def _product_description_context(store, section, page_context):
    product = page_context.get("product")
    if product is None:
        return {}
    return {
        "product": product,
        "spec_variant_summary": page_context.get("spec_variant_summary", {}),
        "approved_reviews": page_context.get("approved_reviews"),
        "review_count": page_context.get("review_count", 0),
        "rating_breakdown": page_context.get("rating_breakdown", []),
        "can_review": page_context.get("can_review", False),
    }


def _product_video_context(store, section, page_context):
    if page_context.get("product") is None:
        return {}
    return {"product_videos": page_context.get("product_videos") or []}


def _related_products_context(store, section, page_context):
    if page_context.get("product") is None:
        return {}
    return {"related_products": page_context.get("related_products")}


def _product_listing_context(store, section, page_context):
    """listing و search هر دو همین را استفاده می‌کنند — بدونِ «محصولِ
    جاری»ای که فقدانش باید fail-safe شود؛ حتی صفحه‌ای که Preview هنوز
    هیچ کوئری‌ای برایش نساخته (کلیدها غایب) با مقادیرِ خنثی رندر می‌شود،
    نه crash."""
    return {
        "page_obj": page_context.get("page_obj"),
        "products": page_context.get("products"),
        "query": page_context.get("query", ""),
        "sort_key": page_context.get("sort_key"),
        "sort_options": page_context.get("sort_options"),
        "filter_categories": page_context.get("filter_categories"),
        "brands": page_context.get("brands"),
        "selected_category": page_context.get("selected_category", ""),
        "selected_brand": page_context.get("selected_brand", ""),
        "min_price": page_context.get("min_price", ""),
        "max_price": page_context.get("max_price", ""),
        "discounted_only": page_context.get("discounted_only", False),
        "querystring": page_context.get("querystring", ""),
    }


def _collection_header_context(store, section, page_context):
    collection = page_context.get("collection")
    if collection is None:
        return {}
    return {"collection": collection}


def _collection_products_context(store, section, page_context):
    collection = page_context.get("collection")
    if collection is None:
        return {}
    return {
        "collection": collection,
        "products": page_context.get("products"),
        "page_obj": page_context.get("page_obj"),
    }


def _cart_items_context(store, section, page_context):
    return {
        "cart": page_context.get("cart"),
        "cart_items": page_context.get("cart_items") or [],
        "item_count": page_context.get("item_count", 0),
    }


def _cart_summary_context(store, section, page_context):
    return {
        "cart": page_context.get("cart"),
        "item_count": page_context.get("item_count", 0),
        "totals": page_context.get("totals"),
    }


_CONTEXT_AWARE_BUILDERS: dict = {
    "product_main": _product_main_context,
    "product_description": _product_description_context,
    "product_video": _product_video_context,
    "related_products": _related_products_context,
    "product_listing": _product_listing_context,
    "collection_header": _collection_header_context,
    "collection_products": _collection_products_context,
    "cart_items": _cart_items_context,
    "cart_summary": _cart_summary_context,
}


_CONTEXT_BUILDERS = {
    "announcement_bar": _static_context,
    "hero_banner": _hero_banner_context,
    "image_slider": _image_slider_context,
    "single_banner": _single_banner_context,
    "multi_banner": _multi_banner_context,
    "category_grid": _category_grid_context,
    "featured_products": _featured_products_context,
    "newest_products": _newest_products_context,
    "best_sellers": _best_sellers_context,
    "discounted_products": _discounted_products_context,
    "amazing_offers": _amazing_offers_context,
    "brand_carousel": _brand_carousel_context,
    "promo_cards": _category_context_for_promo_cards,
    "rich_text": _static_context,
    "image_text": _resolved_destination_context,
    "blog_posts": _blog_posts_context,
    "product_section": _product_section_context,
    "catalog_product_wall": _catalog_product_wall_context,
    "trust_features": _static_context,
    "collection_tiles": _collection_tiles_context,
    "quick_links": _quick_links_context,
    "faq": _static_context,
    "testimonials": _static_context,
    "video_section": _video_section_context,
    "story_rail": _story_rail_context,
}


def build_page_render_items(
    page,
    store,
    page_context: dict | None = None,
    *,
    store_appearance: ResolvedStoreAppearance | None = None,
) -> list[dict]:
    """فهرست بخش‌های فعالِ **یک ``StorefrontPage`` مشخص**، هرکدام با
    template_name + context آماده — Phase 1B: نسخه‌یِ صفحه‌آگاهِ عمومیِ
    این تابع؛ ``build_render_items(version, store)`` (پایین) اکنون فقط
    یک wrapperِ سازگاریِ نازک است که ``version.home_page()`` را حل کرده و
    به همینجا صدا می‌زند — پیاده‌سازیِ واقعی همیشه اینجا زندگی می‌کند، نه
    دوباره‌نویسیِ آن برایِ هر صفحه.

    برایِ صفحه‌ای که هنوز هیچ Section‌ای ندارد (Phase 1A/1B: همه‌یِ
    صفحاتِ غیرِ اصلی امروز عمداً خالی‌اند)، این تابع بدونِ خطا فقط یک
    فهرستِ خالی برمی‌گرداند — نه محتوایِ ساختگی، نه crash؛ دقیقاً همان
    الزامِ صریحِ کار («Do NOT auto-create arbitrary visual blocks»).

    بخش‌هایی با section_key ناشناخته (مثلاً از یک نسخه‌ی قدیمی‌تر که آن نوع
    را دیگر پشتیبانی نمی‌کند) بی‌صدا حذف می‌شوند — پیش‌نمایش/صفحه هرگز crash
    نمی‌کند.

    بهینه‌سازی کوئری: اکثرِ توابعِ ``_CONTEXT_BUILDERS`` به تنظیماتِ
    نمونه‌ی خاصِ یک section وابسته نیستند (فقط به ``store``) — پس اگر
    تاجر یک نوع section را چند بار تکرار کند (قابلیت پشتیبانی‌شده،
    ``duplicable=True``)، نتیجه‌ی کوئری برای همان section_key در یک بار
    رندر همیشه یکسان است و کش سطح-تابع زیر این کوئری‌های تکراری را در یک
    درخواست حذف می‌کند. استثنا: کلیدهایِ ``PER_INSTANCE_SECTION_KEYS``
    (فعلاً فقط ``product_section``) که تنظیماتِ per-instance دارند
    (مثلاً کالکشنِ متفاوت در هر نمونه) — برایِ این‌ها کش با
    ``(section_key, section.pk)`` کلیددهی می‌شود، نه فقط section_key، تا
    نمونه‌ی دوم محتوایِ نمونه‌ی اول را «قرض» نگیرد. این یک لایه‌ی کش
    خارجی/persistent نیست (که برای این ویو، همیشه باید Draft زنده را
    نشان دهد، خطر بازگشت داده‌ی کهنه دارد) — فقط حذفِ کوئریِ تکراری در
    یک درخواست."""
    page_context = page_context or {}
    sections = page.sections.filter(is_active=True).order_by("order", "id")
    # A7 — resolve the typed Store Appearance state once for the exact
    # version already selected by the caller. Public/Preview callers may
    # pre-resolve and pass the same immutable state so global regions and
    # section items share one resolution for the whole response.
    if store_appearance is None:
        store_appearance = resolve_store_appearance_render_state(page.version)
    elif store_appearance.version_id != page.version_id:
        raise ValueError("Store Appearance state belongs to another layout version")

    # Existing typography/palette overrides remain sourced from the same
    # physical version. Store Appearance augments this boundary; it does not
    # duplicate or replace the existing appearance-token service.
    global_appearance = page.version.effective_appearance_config()
    return _build_items_from_sections(
        sections,
        store,
        page_context,
        global_appearance=global_appearance,
        store_appearance=store_appearance,
    )


def _build_items_from_sections(
    sections,
    store,
    page_context: dict,
    global_appearance: dict | None = None,
    store_appearance: ResolvedStoreAppearance | None = None,
) -> list[dict]:
    """پیاده‌سازیِ مشترکِ واقعی — رویِ هر iterableای از آبجکت‌هایِ
    ``StorefrontSection``-شکل کار می‌کند، نه فقط یک QuerySetِ ذخیره‌شده در
    دیتابیس. ``build_page_render_items`` (بالا) این را با سطرهایِ واقعیِ
    یک ``StorefrontPage`` صدا می‌زند؛ ``build_default_render_items``
    (پایین) با نمونه‌هایِ **ذخیره‌نشده** (in-memory) برایِ Storeهایی که
    هنوز اصلاً یک Storefront V2 منتشر نکرده‌اند — دقیقاً همان قراردادِ
    context/cache/skip-unknown-key اینجا برایِ هر دو مسیر یکسان می‌ماند."""
    from apps.content.services import resolve_background_media_url

    items = []
    context_cache: dict = {}
    for section in sections:
        try:
            definition = get_definition(section.section_key)
        except UnknownSectionTypeError:
            continue

        # A7 — a non-default Store Appearance section component is a
        # render-time selection over the existing registered Variant axis.
        # The persisted Section itself is never rewritten here. The explicit
        # safe ``legacy_default`` component deliberately defers to the
        # Section's own saved setting, preserving every pre-engine template.
        appearance_variant = (
            store_appearance_section_variant_for(store_appearance, section.section_key)
            if store_appearance is not None
            else None
        )
        effective_settings = dict(section.settings or {})
        render_section = section
        # Phase 1 (Task 6) / Phase 4 (Task 6, Group F correction) — approved
        # precedence: an EXPLICIT local override (stamped
        # ``appearance_overrides.variant_explicit``/``card_style_explicit``
        # by a genuine merchant edit) is the strongest normal override and
        # wins over the inherited Store-level family default. Historical rows
        # WITHOUT a marker keep the current inherited/global overlay behavior,
        # so existing stores do not visually flip. The Store manifest
        # selection itself is unchanged; only whether it overlays the local
        # value differs. Computed here (before the card/badge overlay below)
        # so both overlays can honor their own marker.
        _local_overrides = effective_settings.get("appearance_overrides") or {}
        _variant_explicit = bool(_local_overrides.get("variant_explicit"))
        _card_style_explicit = bool(_local_overrides.get("card_style_explicit"))
        if store_appearance is not None and section.section_key in CARD_AWARE_SECTION_KEYS:
            presentation_overlay = dict(badge_settings_for(store_appearance))
            # ``badge`` has no merchant-facing local write path anywhere, so
            # its overlay always applies. ``card_style`` does (the legacy
            # card-settings form) — an explicit local choice must survive a
            # conflicting Store-level card family selection, exactly like the
            # variant axis below.
            if not _card_style_explicit:
                presentation_overlay.update(card_settings_for(store_appearance))
            if presentation_overlay:
                effective_card_settings = dict(effective_settings.get("card") or {})
                effective_card_settings.update(presentation_overlay)
                effective_settings["card"] = effective_card_settings
        # When the local variant is explicit, the manifest variant no longer
        # overlays the section for this render (neither the settings mirror nor
        # the resolved ``active_variant`` below), so the saved local variant wins.
        effective_appearance_variant = (
            None if _variant_explicit else appearance_variant
        )
        if effective_appearance_variant is not None:
            variant_setting_key = definition.variant_setting_key or "variant"
            effective_settings[variant_setting_key] = effective_appearance_variant.key
            # Context builders consistently read ``section.settings``. A
            # shallow model copy preserves PK/FK identity for Store-scoped
            # queries while keeping this overlay strictly in-memory.
        if effective_settings != (section.settings or {}):
            render_section = copy(section)
            render_section.settings = effective_settings

        cache_key = (
            (section.section_key, section.pk)
            if section.section_key in PER_INSTANCE_SECTION_KEYS
            else section.section_key
        )
        if cache_key not in context_cache:
            if section.section_key in _CONTEXT_AWARE_BUILDERS:
                builder = _CONTEXT_AWARE_BUILDERS[section.section_key]
                context_cache[cache_key] = builder(store, render_section, page_context)
            else:
                builder = _CONTEXT_BUILDERS.get(section.section_key, _static_context)
                context_cache[cache_key] = builder(store, render_section)
        context = dict(context_cache[cache_key])
        context["section"] = render_section
        context["settings"] = effective_settings
        if store_appearance is not None:
            context["store_appearance"] = store_appearance
        # R4 Task 7 — computed AFTER copying the (possibly shared/cached)
        # context, from THIS Section's own settings only, so one Hero's
        # local override can never leak into a sibling instance's context,
        # even when they share a cached context dict above. No DB access
        # here — global_appearance was already resolved once for the
        # whole page. Absent entirely for build_default_render_items's
        # unsaved-section legacy path (global_appearance is None there —
        # no persisted version to derive it from, and never fabricated).
        if global_appearance is not None:
            effective_appearance = section_appearance_service.resolve_section_appearance(
                global_appearance, context["settings"],
            )
            context["effective_section_appearance"] = effective_appearance
            context["effective_section_typography"] = appearance_registry.resolve_typography(
                effective_appearance.get("type_scale", "normal"),
            )
        # Phase 2: حلِ Store-scopedِ رسانه‌یِ پس‌زمینه (Phase 1:
        # ``background.media_asset_id``) — همینجا (نه در template) چون
        # نیازمندِ یک کوئریِ دیتابیسِ store-scoped است؛ همان تفکیکِ
        # مسئولیتی که ``_resolved_destination_context`` برایِ ``destination``
        # دارد. per-instance (نه context_cache) چون دو نمونه از یک
        # section_key می‌توانند رسانه‌های متفاوت داشته باشند. ``None`` برایِ
        # هر چیزی غیر از mode="image" یا هر ارجاعِ نامعتبر/خارجی — هرگز کرش.
        context["background_media_url"] = resolve_background_media_url(
            store, context["settings"].get("background"),
        )
        # U1B1 — variant runtime wiring (variant_contract.py). Pure metadata
        # lookup, no DB query, no mutation of ``section.settings``. For the
        # 31 section types with no registered ``variants`` (the overwhelming
        # majority today), ``resolve_active_variant`` short-circuits to
        # ``None`` and ``resolve_renderer_template`` returns exactly
        # ``definition.template_name`` — byte-identical to the pre-U1B1
        # line this replaces. For the three proven precedents
        # (category_grid/brand_carousel/product_section), every currently
        # registered variant declares ``renderer=None`` (Pattern A), so the
        # resolved template is still ``definition.template_name`` — no
        # production render output changes. An unrecognized/legacy
        # persisted value fails safely to ``default_variant`` here (never
        # raises, never rewrites the stored Section) — see
        # ``variant_contract.resolve_active_variant``'s own contract.
        active_variant = effective_appearance_variant or resolve_active_variant(
            definition, effective_settings
        )
        items.append({
            "section": render_section,
            "definition": definition,
            "template_name": resolve_renderer_template(definition, active_variant),
            "label_fa": definition.label_fa,
            "context": context,
            # A7 — one immutable typed state is threaded through every item
            # and its context. Existing templates may ignore it; component
            # families added in later phases consume this same object rather
            # than creating a Design-Lab-only renderer contract.
            "store_appearance": store_appearance,
            # Exposed for testability/observability (U1B1 §4) and for a
            # future consumer (U1B2+) — no current template/consumer reads
            # this key, so adding it changes nothing for existing callers.
            "active_variant": active_variant,
        })
    return items


def build_default_render_items(page_type: str, store, page_context: dict | None = None) -> list[dict]:
    """معادلِ ``build_page_render_items``، اما برایِ Storeهایی که **هنوز
    هیچ نسخه‌ی Storefront V2ای منتشر نکرده‌اند** (``uses_universal_shell=False``
    — نگاه کنید به ``storefront_context_service.build_universal_storefront_context``)
    — پس اصلاً هیچ ``StorefrontPage``/``StorefrontSection`` واقعی‌ای در
    دیتابیس برایِ آن‌ها وجود ندارد که resolve شود.

    Phase 5: پیش از این چکپوینت، پنج صفحه‌ی محصول/لیست/کالکشن/جستجو/سبد
    همیشه محتوایِ سخت‌کدشده‌ی خودشان را نشان می‌دادند — کاملاً مستقل از
    اینکه Store اصلاً Builder را لمس کرده باشد یا نه (برخلافِ صفحه‌ی
    اصلی که برایِ Storeهایِ منتشرنکرده از یک تمپلیتِ کاملاً جداگانه —
    ``catalog/home.html`` — استفاده می‌کند، نه این مکانیزم). حالا که
    بدنه‌ی این پنج تمپلیت به ``render_items`` منتقل شده، این تابع همان
    محتوایِ پیش‌فرضِ ثابت (``bootstrap_service.build_default_non_home_sections``)
    را با نمونه‌هایِ ``StorefrontSection`` **ذخیره‌نشده** (``pk=None``، هرگز
    در دیتابیس نمی‌نشینند) رندر می‌کند — دقیقاً همان section_keyهایی که
    اولین Draftِ هر Storeِ تازه هم می‌گیرد، پس تجربه‌یِ بصریِ یک فروشگاهِ
    «هرگز منتشرنکرده» با «تازه منتشرکرده» یکسان می‌ماند. برایِ ``home``
    (که در ``_DEFAULT_NON_HOME_SECTION_KEYS`` نیست) بی‌صدا فهرستِ خالی
    برمی‌گرداند — بی‌اثر، چون صفحه‌ی اصلیِ منتشرنشده اصلاً از این تابع
    استفاده نمی‌کند."""
    from .bootstrap_service import build_default_non_home_sections
    from ..models import StorefrontSection

    page_context = page_context or {}
    sections = [
        StorefrontSection(section_key=s["section_key"], order=s["order"], settings=s["settings"], is_active=True)
        for s in build_default_non_home_sections(page_type)
    ]
    return _build_items_from_sections(sections, store, page_context)


def build_candidate_render_items(
    sections,
    store,
    page_context: dict | None = None,
    *,
    global_appearance: dict | None = None,
    store_appearance: ResolvedStoreAppearance | None = None,
) -> list[dict]:
    """Phase 5, Task 1 — render a page's worth of UNSAVED ``StorefrontSection``
    instances (e.g. from ``preset_service.resolve_preset_candidate``) through
    the exact same shared rendering path every other caller of
    ``_build_items_from_sections`` already uses — not a second renderer.

    ``_build_items_from_sections`` is already explicitly designed to accept
    any iterable of StorefrontSection-*shaped* objects, saved or not — see
    ``build_default_render_items`` above, the existing precedent this reuses
    for stores that have never published a Storefront V2. This is a thin
    public wrapper for the candidate-preview case so callers never need the
    private function directly."""
    return _build_items_from_sections(
        sections,
        store,
        page_context or {},
        global_appearance=global_appearance,
        store_appearance=store_appearance,
    )


def build_candidate_container_rows(candidate_page, items: list[dict]) -> list[dict]:
    """Phase 5, Task 2 — the smallest read-only candidate adapter for the
    "container settings must not be ignored" parity requirement (Task-1
    corrective's ``ResolvedPresetCandidatePage.container_settings``).

    Reuses the existing, already-tested ``group_items_into_rows`` — the same
    pure, no-persisted-Container row-grouping path ``preview.html`` already
    falls back to today for any Draft/Published version with no real
    ``StorefrontContainer`` rows yet (``render_rows.html``'s own
    ``{% else %}`` branch). ``build_container_render_items`` (the full
    Container/Cell renderer) genuinely requires persisted rows — see its own
    ``page.containers``/``item["section"].pk`` lookups — so it cannot render
    an unsaved candidate without persisting something, which Task 2 must not
    do. This function does not replace or fork that renderer; it only
    attaches ``candidate_page``'s already-computed per-row-run
    ``container_settings`` onto ``group_items_into_rows``'s output, in the
    same order, so callers receive rows *and* their settings together
    instead of the settings being silently discarded.

    Row/settings order correspondence is structural, not coincidental: both
    ``group_items_into_rows`` (contiguous ``row_key`` adjacency over
    ``items``) and ``candidate_page.container_settings``
    (``preset_service._entry_runs`` over the same, identically-ordered
    preset entries that produced ``items``) group by the same contiguous
    ``row_key`` rule over the same section sequence."""
    rows = group_items_into_rows(items)
    for row, container_settings in zip(rows, candidate_page.container_settings):
        row["container_settings"] = container_settings
    return rows


#: Acceptance Batch 1 (post-U11) — the registry-level distinction the QA
#: fix needs: section types whose whole reason for existing is an
#: optional, auto-populated *product grid* (never static/editorial
#: content), mapped to the context key each one's builder above always
#: sets that grid under. On the public/live storefront, a genuinely empty
#: grid here means "nothing to show" and the whole section is skipped —
#: on the Builder/editor (which never calls ``hide_empty_public_sections``
#: below), it still renders with its own "چیزی برای نمایش نیست" empty
#: state so a merchant understands *why* a section looks empty while
#: composing a page. ``product_listing``/``collection_products`` are
#: deliberately excluded — those ARE the listing/collection/search page's
#: own body, where an empty result set is itself meaningful feedback to a
#: shopper (e.g. "no results for this filter"), not an optional
#: promotional row that should just disappear.
OPTIONAL_PRODUCT_DATA_SECTION_KEYS = {
    "product_section": "products",
    "featured_products": "products",
    "newest_products": "products",
    "best_sellers": "products",
    "discounted_products": "products",
    "amazing_offers": "products",
    "related_products": "related_products",
}


def hide_empty_public_sections(items: list[dict]) -> list[dict]:
    """Drop render items for ``OPTIONAL_PRODUCT_DATA_SECTION_KEYS`` whose
    resolved data is empty — called only from the public/live context path
    (``storefront_context_service.build_universal_storefront_context``),
    never from the Builder/editor preview path (``storefront_preview``
    calls ``build_page_render_items`` directly and never sees this
    function), so the two contracts (hide on live, explain in the editor)
    stay physically separate rather than depending on a runtime flag one
    call site could forget to pass. A dropped item never reaches
    ``group_items_into_rows``/``build_container_render_items`` — no empty
    wrapper, heading, or Cell/Container survives for it."""
    visible = []
    for item in items:
        context_key = OPTIONAL_PRODUCT_DATA_SECTION_KEYS.get(item["section"].section_key)
        if context_key is not None and not item["context"].get(context_key):
            continue
        visible.append(item)
    return visible


def build_container_render_items(page, items: list[dict], *, include_empty: bool = False) -> list[dict]:
    """Shape rendered Section items through the real Container/Cell layout.

    ``items`` already contains the expensive, store-scoped Section contexts.
    This helper only maps those items onto Cells. Inactive/unknown Sections are
    treated as empty Cells. Public rendering skips completely empty Containers;
    Builder preview may request ``include_empty=True`` so merchants can see and
    fill an empty layout before content exists.

    Phase 2B: a Cell may now hold more than one ordered Block. Each Cell's
    Blocks are resolved through ``container_service.get_cell_blocks`` — the
    single authoritative read path (new multi-block FK first, transparently
    falling back to the legacy single-``section`` OneToOne only when the new
    relationship is completely empty for that Cell, so a Section is never
    counted/rendered twice — see that function's docstring for the exact
    rule). Every ``cell_entry`` keeps its original, singular ``"item"`` key —
    the *first* visible Block's render item, or ``None`` — exactly the
    pre-Phase-2B contract every existing consumer/test already depends on
    (e.g. ``test_published_context_uses_container_layout_as_source_of_truth``)
    — and gains a new ``"items"`` key: the complete ordered list of visible
    Blocks' render items, for templates that render every Block in a Cell.
    """
    from . import container_service

    items_by_section_id = {
        item["section"].pk: item
        for item in items
        if item.get("section") is not None and item["section"].pk is not None
    }
    rendered = []
    containers = page.containers.prefetch_related(
        "cells__section", "cells__blocks",
    ).order_by("order", "id")
    for container in containers:
        cells = []
        has_content = False
        has_placement = False
        for cell in container.cells.all():
            # U11 — N+1 fix: ``containers`` above was just fetched with
            # ``prefetch_related("cells__section", "cells__blocks")``, so
            # every Cell here is already fresh; ``get_cell_blocks`` would
            # discard that prefetch and issue one live query per Cell (its
            # own docstring documents why it always does that — a
            # guarantee this loop doesn't need, see
            # ``blocks_from_prefetched_cell``'s docstring).
            blocks = container_service.blocks_from_prefetched_cell(cell)
            block_items = []
            for block in blocks:
                has_placement = True
                block_item = items_by_section_id.get(block.pk)
                if block_item is not None:
                    has_content = True
                    block_items.append(block_item)
            cells.append({
                "cell": cell,
                "item": block_items[0] if block_items else None,
                "items": block_items,
                # Raw placed Sections (including inactive/hidden ones) — the
                # builder-only "occupied but all Blocks are hidden" chrome
                # needs this list; ``items`` above only ever contains
                # *visible* Blocks' render contexts.
                "blocks": blocks,
            })
        if not has_content and not include_empty:
            continue
        rendered.append({
            "container": container,
            "settings": container_service.effective_container_settings(container.settings),
            "cells": cells,
            "has_content": has_content,
            # Hidden content has no active render item but still physically owns
            # its Cell.  Builder chrome must distinguish that from a truly empty
            # Container so direct delete never risks hidden data.
            "has_placement": has_placement,
        })
    return rendered



def group_items_into_rows(items: list[dict]) -> list[dict]:
    """تبدیلِ خروجیِ تخت ``build_page_render_items``/``build_render_items`` به
    فهرستی از «ردیف‌ها» — Phase 1 (معماریِ Universal Block/Data)، آماده‌سازیِ
    دادهٔ لازم برایِ Phase 2 (Universal Renderer).

    این تابع **هیچ HTML/templateای رندر نمی‌کند** و هنوز توسطِ هیچ view/
    templateی صدا زده نمی‌شود — یک تبدیلِ دادهٔ خالص است که قراردادِ
    ``StorefrontSection.row_key``/``row_span`` (نگاه کنید به
    ``services/row_service.py``) را به شکلی تبدیل می‌کند که مصرفِ آن توسطِ
    یک الگویِ CSS Grid/Flex در Phase 2 مستقیم باشد، بدونِ اینکه Phase 2
    مجبور باشد دوباره منطقِ گروه‌بندیِ مجاورت را بازنویسی کند.

    ورودی همان فهرستِ ``item`` است (هرکدام حاویِ ``item["section"]``)؛
    خروجی فهرستی از دیکشنری‌هایِ ``{"row_key": str, "items": [item, ...]}``
    — یک section مستقل (row_key خالی) هم به‌شکلِ یک «ردیفِ تک‌عضوی»
    (``row_key=""``) بازگردانده می‌شود، تا فراخوان همیشه یک قراردادِ یکسان
    (فهرستی از ردیف‌ها) داشته باشد، نه دو شکلِ متفاوت برایِ section مستقل/
    عضوِ ردیف.

    گروه‌بندی صرفاً بر اساسِ **مجاورت** در همین فهرستِ ورودی انجام می‌شود
    (نه جست‌وجویِ سراسریِ همه‌ی sectionهایِ هم‌row_key در کلِ صفحه) — دقیقاً
    همان قاعدهٔ ``row_service._grouped_by_row_key``؛ اگر ورودی از قبل با
    ``row_service.validate_page_row_layout`` تأیید شده باشد (که پیش از هر
    ذخیره‌یِ row_key/row_span باید صدا زده شود)، این دو تعریفِ «مجاورت» همیشه
    یکسان نتیجه می‌دهند."""
    rows: list[dict] = []
    for item in items:
        section = item["section"]
        key = section.row_key or ""
        if rows and rows[-1]["row_key"] == key and key != "":
            rows[-1]["items"].append(item)
        else:
            rows.append({"row_key": key, "items": [item]})
    return rows


def build_render_items(version, store) -> list[dict]:
    """فهرست بخش‌های فعالِ **صفحه‌ی اصلیِ** یک نسخه — wrapperِ سازگاریِ
    نازک، حفظ‌شده عمداً برایِ هر دو فراخوانِ تولیدیِ موجودِ پیش از Phase 1B
    (``apps.catalog.views.home()`` و
    ``storefront_builder.views.storefront_preview()``) که همیشه یک
    ``StorefrontLayoutVersion`` پاس می‌دهند، نه یک ``StorefrontPage`` — و
    برایِ کلِ مجموعه‌ی تست‌هایِ موجودِ ``test_render_service.py`` که همین
    امضا را مستقیماً صدا می‌زنند. پیاده‌سازیِ واقعی از Phase 1B به بعد
    ``build_page_render_items`` است؛ این تابع فقط ``version.home_page()``
    را حل می‌کند و به آن تابع صدا می‌زند — تکراریِ منطق نیست."""
    return build_page_render_items(version.home_page(), store)
