import json
from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Avg, F, Max, Prefetch, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.blog.models import BlogPost
from apps.content.models import HeroSlide, PromotionalBanner
from apps.content.services import resolve_destination_url
from apps.customers.models import Customer
from apps.stores.resolution import resolve_store_for_storefront

from .models import Brand, Category, Product, Review
from .services import collection_service
from apps.cart.services.gift_wrap_service import is_gift_wrap_available, resolve_gift_wrap_price

from .services.product_publish_service import storefront_listing_products, storefront_visible_products
from .services.product_video_service import ProductVideoError
from .services.storefront_variant_service import build_variant_selector_context

BEST_SORT_OPTIONS = {
    "sold": ("-sold_count", "پرفروش‌ترین"),
    "new": ("-created_at", "جدیدترین"),
    "view": ("-views_count", "پربازدید"),
    "disc": ("-discount_percent", "تخفیف‌دار"),
}
DEFAULT_SORT = "sold"

TILE_CLASSES = ["t1", "t2", "t3"]


def _best_products(store, sort_key):
    order_field, _ = BEST_SORT_OPTIONS.get(sort_key, BEST_SORT_OPTIONS[DEFAULT_SORT])
    qs = (
        storefront_listing_products(store)
        .select_related("brand").prefetch_related("images")
    )
    if sort_key == "disc":
        qs = qs.filter(discount_percent__gt=0)
    return qs.order_by(order_field)[:8]


def home(request):
    store = resolve_store_for_storefront(request)

    # اگر این فروشگاه سازنده بصری صفحه اصلی را منتشر کرده (تصمیم ۳ کاربر:
    # فعال‌سازی تدریجی per-store)، مسیر قدیمی هارد‌کد این پایین اجرا
    # نمی‌شود — به‌جایش همان نسخه‌ی منتشرشده رندر می‌شود (هرگز Draft،
    # تصمیم ۱۱ کاربر). Import محلی برای جلوگیری از وابستگی حلقوی
    # ماژول‌سطح با apps.storefront_builder (که خودش از apps.catalog
    # استفاده می‌کند).
    #
    # Phase 1B: منطقِ تشخیص/ساختِ کانتکست دیگر اینجا تکرار نمی‌شود —
    # ``build_universal_storefront_context`` تنها نقطه‌ی این تصمیم برایِ
    # هر شش نوع صفحه است (نگاه کنید به گزارشِ Phase 1B).
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.storefront_builder.models import StorefrontPage

    universal_context = build_universal_storefront_context(
        request, store, StorefrontPage.PageType.HOME,
    )
    if universal_context["uses_universal_shell"]:
        # ``top_level_categories`` از قبل توسطِ ``build_universal_storefront_context``
        # محاسبه شده (نگاه کنید به ``storefront_context_service._top_level_categories``)
        # — دیگر نیازی به کوئریِ جداگانه‌یِ اینجا نیست.
        return render(request, "catalog/home_visual.html", universal_context)

    active_products = storefront_listing_products(store)

    top_categories = list(
        Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
    )
    icon_categories = (
        Category.objects.filter(store=store, parent__isnull=False, is_active=True)
        .select_related("parent")
        .order_by("order", "name")
    )

    new_products = active_products.select_related("brand").prefetch_related("images").order_by("-created_at")[:8]
    discounted_products = (
        active_products.select_related("brand").prefetch_related("images")
        .filter(discount_percent__gt=0).order_by("-discount_percent")[:6]
    )
    highlight_product = discounted_products.first()
    most_viewed_product = active_products.order_by("-views_count").first()

    stats = active_products.aggregate(avg_rating=Avg("rating"), max_discount=Max("discount_percent"))

    context = {
        "sort_key": DEFAULT_SORT,
        "best_sort_options": BEST_SORT_OPTIONS,
        "best_products": _best_products(store, DEFAULT_SORT),
        "top_categories": top_categories,
        "tiles": list(zip(top_categories[:3], TILE_CLASSES)),
        "cream_category": top_categories[3] if len(top_categories) > 3 else None,
        "icon_categories": icon_categories,
        "new_products": new_products,
        "discounted_products": discounted_products,
        "highlight_product": highlight_product,
        "most_viewed_product": most_viewed_product,
        "customers_count": Customer.objects.count(),
        "avg_rating": stats["avg_rating"] or 0,
        "max_discount": stats["max_discount"] or 0,
        "blog_posts": BlogPost.objects.order_by("-published_at")[:5],
        "special_offer_deadline": (timezone.now() + timedelta(hours=8)).isoformat(),
        "hero_slides": HeroSlide.objects.filter(is_active=True, store=store).select_related(
            "destination_category", "destination_product", "destination_brand"
        ),
        "promo_banners": PromotionalBanner.objects.filter(is_active=True, store=store).select_related(
            "destination_category", "destination_product", "destination_brand"
        ),
    }
    return render(request, "catalog/home.html", context)


def home_best_products(request):
    store = resolve_store_for_storefront(request)
    sort_key = request.GET.get("sort", DEFAULT_SORT)
    if sort_key not in BEST_SORT_OPTIONS:
        sort_key = DEFAULT_SORT
    context = {"products": _best_products(store, sort_key)}
    return render(request, "catalog/partials/product_grid.html", context)


PRODUCTS_PER_PAGE = 12

LIST_SORT_OPTIONS = {
    "newest": ("-created_at", "جدیدترین"),
    "price_asc": ("price", "ارزان‌ترین"),
    "price_desc": ("-price", "گران‌ترین"),
    "popular": ("-sold_count", "محبوب‌ترین"),
    "rating": ("-rating", "بیشترین امتیاز"),
}
DEFAULT_LIST_SORT = "newest"


def _filtered_products(request, store):
    qs = (
        storefront_listing_products(store)
        .select_related("brand", "category")
        .prefetch_related("images")
    )

    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(brand__name__icontains=query) | Q(category__name__icontains=query)
        ).distinct()

    category_slug = request.GET.get("category", "").strip()
    if category_slug:
        qs = qs.filter(Q(category__slug=category_slug) | Q(category__parent__slug=category_slug))

    brand_slug = request.GET.get("brand", "").strip()
    if brand_slug:
        qs = qs.filter(brand__slug=brand_slug)

    min_price = request.GET.get("min_price", "").strip()
    if min_price.isdigit():
        qs = qs.filter(price__gte=int(min_price))

    max_price = request.GET.get("max_price", "").strip()
    if max_price.isdigit():
        qs = qs.filter(price__lte=int(max_price))

    if request.GET.get("discounted") == "1":
        qs = qs.filter(discount_percent__gt=0)

    # U5 — availability facet, real stock data (no fabricated "in stock"
    # claim): ``Product.stock`` is already the single source of truth used
    # by the card resolver's ``is_out_of_stock`` (U3) and by
    # ``inventory_service`` — reusing the same field here, not a new one.
    if request.GET.get("in_stock") == "1":
        qs = qs.filter(stock__gt=0)

    sort_key = request.GET.get("sort", DEFAULT_LIST_SORT)
    if sort_key not in LIST_SORT_OPTIONS:
        sort_key = DEFAULT_LIST_SORT
    order_field, _ = LIST_SORT_OPTIONS[sort_key]
    qs = qs.order_by(order_field, "id")

    return qs, sort_key, query


def _querystring_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


# --- G2 (Golden Search/Category/Listing) — dynamic location context + chips ---
# All derived server-side from data the view already resolves, so the full page
# and the HTMX partial stay consistent and query-canonical. Tenant-scoped: the
# resolved ``Category``/``Brand`` objects are already ``store=store`` filtered.

def _listing_querystring_without(request, *drop_keys):
    """The current query string with ``page`` and the given keys removed —
    used to build a chip's "remove just this filter" URL (preserving the rest)."""
    params = request.GET.copy()
    params.pop("page", None)
    for key in drop_keys:
        params.pop(key, None)
    return params.urlencode()


def _resolve_listing_location(store, *, query, selected_category, selected_brand):
    """Return ``(heading, breadcrumbs)`` for the listing/search page.

    ``breadcrumbs`` is a list of ``{"label", "url"}`` (final crumb has ``url=None``).
    Category resolution is tenant-scoped (``store=store``) and includes the
    parent→child trail for a subcategory.
    """
    home = {"label": "خانه", "url": "/"}
    shop = {"label": "فروشگاه", "url": reverse("catalog:product-list")}

    if query:
        heading = f"نتایج جستجو برای «{query}»"
        return heading, [home, shop, {"label": heading, "url": None}]

    if selected_category:
        category = (
            Category.objects.filter(store=store, slug=selected_category, is_active=True)
            .select_related("parent")
            .first()
        )
        if category is not None:
            crumbs = [home, shop]
            if category.parent_id is not None and getattr(category.parent, "is_active", True):
                parent_qs = urlencode({"category": category.parent.slug})
                crumbs.append({
                    "label": category.parent.name,
                    "url": f"{reverse('catalog:product-list')}?{parent_qs}",
                })
            crumbs.append({"label": category.name, "url": None})
            return category.name, crumbs

    if selected_brand:
        brand = Brand.objects.filter(store=store, slug=selected_brand, is_active=True).first()
        if brand is not None:
            return brand.name, [home, shop, {"label": brand.name, "url": None}]

    heading = "همه‌ی محصولات"
    return heading, [home, {"label": heading, "url": None}]


def _build_active_filter_chips(request, store, *, query, selected_category, selected_brand,
                               min_price, max_price, discounted_only, in_stock_only):
    """Visible, removable active-filter chips. Each chip is
    ``{"kind", "label", "remove_url"}`` where ``remove_url`` drops only that
    filter and preserves the rest (server/query canonical)."""
    base = reverse("catalog:product-list")
    chips = []

    def add(kind, label, *drop_keys):
        qs = _listing_querystring_without(request, *drop_keys)
        chips.append({
            "kind": kind,
            "label": label,
            "remove_url": f"{base}?{qs}" if qs else base,
        })

    if query:
        add("q", f"جستجو: {query}", "q")
    if selected_category:
        category = Category.objects.filter(store=store, slug=selected_category, is_active=True).first()
        if category is not None:
            add("category", category.name, "category")
    if selected_brand:
        brand = Brand.objects.filter(store=store, slug=selected_brand, is_active=True).first()
        if brand is not None:
            add("brand", brand.name, "brand")
    # Gate the price chip on the SAME predicate the queryset uses (.isdigit()),
    # so a non-numeric ?min_price=abc never shows a chip for a filter that is
    # not actually applied.
    price_min = min_price if min_price.isdigit() else ""
    price_max = max_price if max_price.isdigit() else ""
    if price_min or price_max:
        if price_min and price_max:
            label = f"قیمت: {price_min} تا {price_max}"
        elif price_min:
            label = f"قیمت: از {price_min}"
        else:
            label = f"قیمت: تا {price_max}"
        add("price", label, "min_price", "max_price")
    if discounted_only:
        add("discounted", "فقط تخفیف‌دار", "discounted")
    if in_stock_only:
        add("in_stock", "فقط موجود", "in_stock")

    return chips


def build_product_listing_context(request, store):
    """کانتکستِ کاملِ صفحه‌ی لیست/جستجو — هم برایِ ``product_list`` (مسیرِ
    عمومی) و هم برایِ Preview سازنده (Phase 5، section context-aware
    ``product_listing``) استفاده می‌شود تا فیلتر/مرتب‌سازی/صفحه‌بندی هرگز
    دوباره‌نویسی نشود؛ دقیقاً همان الگویِ ``build_product_detail_context``."""
    qs, sort_key, query = _filtered_products(request, store)

    paginator = Paginator(qs, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    filter_categories = Category.objects.filter(store=store, parent__isnull=True, is_active=True).prefetch_related(
        Prefetch("children", queryset=Category.objects.filter(store=store, is_active=True).order_by("order", "name"))
    ).order_by("order", "name")

    selected_category = request.GET.get("category", "").strip()
    selected_brand = request.GET.get("brand", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    discounted_only = request.GET.get("discounted") == "1"
    in_stock_only = request.GET.get("in_stock") == "1"

    listing_heading, listing_breadcrumbs = _resolve_listing_location(
        store, query=query, selected_category=selected_category, selected_brand=selected_brand,
    )
    active_filter_chips = _build_active_filter_chips(
        request, store, query=query, selected_category=selected_category,
        selected_brand=selected_brand, min_price=min_price, max_price=max_price,
        discounted_only=discounted_only, in_stock_only=in_stock_only,
    )

    return {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "query": query,
        "sort_key": sort_key,
        "sort_options": LIST_SORT_OPTIONS,
        "filter_categories": filter_categories,
        "brands": Brand.objects.filter(store=store, is_active=True).order_by("name"),
        "selected_category": selected_category,
        "selected_brand": selected_brand,
        "min_price": min_price,
        "max_price": max_price,
        "discounted_only": discounted_only,
        "in_stock_only": in_stock_only,
        "querystring": _querystring_without_page(request),
        # G2 — dynamic location context + removable active-filter chips.
        "listing_heading": listing_heading,
        "listing_breadcrumbs": listing_breadcrumbs,
        "active_filter_chips": active_filter_chips,
        "clear_all_url": reverse("catalog:product-list"),
    }


def _product_listing_card_settings(render_items) -> dict:
    """Phase 4 (Task 3E) — extract the ``product_listing`` section's own
    resolved, merchant-overridden card settings (the exact same value the
    full-page render's own section template threads into
    ``product_list_results.html`` via ``settings.card``) out of the shared
    canonical render_items list. Fails safe to ``{}`` (template defaults)
    if the section is somehow missing — never crashes the listing page."""
    for item in render_items:
        if item["section"].section_key == "product_listing":
            return item["context"]["settings"].get("card") or {}
    return {}


def product_list(request):
    store = resolve_store_for_storefront(request)
    context = build_product_listing_context(request, store)

    # Phase 1B: این یک route است که هم «لیست/دسته‌بندی» و هم «جستجو» را
    # پوشش می‌دهد (بدون URL جداگانه‌ی جستجو — نگاه کنید به گزارشِ ممیزیِ
    # این فاز) — نوعِ صفحه‌ی V2 بر اساسِ وجودِ ``q`` انتخاب می‌شود؛ خودِ
    # کوئری/فیلتر/مرتب‌سازیِ کاتالوگ (بالا) کاملاً مستقل از این انتخاب و
    # بدونِ تغییر باقی می‌ماند.
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.storefront_builder.models import StorefrontPage

    page_type = StorefrontPage.PageType.SEARCH if context["query"] else StorefrontPage.PageType.LISTING
    # Phase 4 (Task 3E) — the canonical context builder now runs on BOTH the
    # HTMX fragment path and the full-page path (previously the HTMX branch
    # returned before this ever ran), through the exact same call — no
    # second fragment renderer. Before this fix, an HTMX filter/pagination
    # swap never received the merchant's product_listing card-style
    # override (``card_settings``), so it silently reverted to template
    # defaults until the next full page load.
    universal_context = build_universal_storefront_context(request, store, page_type, page_context=context)
    context.update(universal_context)
    context["card_settings"] = _product_listing_card_settings(universal_context.get("render_items") or [])

    if request.headers.get("HX-Request") == "true":
        # G2: on an HTMX filter/pagination swap, also refresh the breadcrumb +
        # heading (which live outside #product-results) out-of-band so they never
        # go stale relative to the pushed URL/results.
        context["listing_header_oob"] = True
        return render(request, "catalog/partials/product_list_results.html", context)

    return render(request, "catalog/product_list.html", context)


def _variant_groups(product):
    groups = {}
    for variant in product.variants.all().order_by("attribute", "value"):
        groups.setdefault(variant.attribute, []).append(variant)
    return groups


def _gallery_slides(product):
    images = list(product.images.all().order_by("order"))
    if images:
        return [
            {
                "type": "image",
                "url": img.image.url,
                "thumb_url": img.thumbnail.url if img.thumbnail else img.image.url,
                "alt": img.alt or product.name,
                # اگر تصویر به یک تنوعِ خاص اختصاص یافته باشد، با انتخابِ همان
                # تنوع در فروشگاه، گالری خودکار به این تصویر سوییچ می‌کند —
                # نگاه کنید به apps.catalog.services.product_image_service.set_image_variant.
                # وقتی تنوعِ انتخاب‌شده تصویرِ اختصاصی ندارد، گالری به همین
                # تصویرِ کاور برمی‌گردد (نه این‌که رویِ تصویرِ تنوعِ قبلی بماند).
                "variant_id": img.variant_id,
                "is_cover": img.is_cover,
            }
            for img in images
        ]

    base_tint = product.tint or "#eceef3"
    pseudo_tints = [base_tint, "#f7f3fe", "#eef0f6", "#f6efe2"]
    emoji = product.icon or "🛍️"
    return [{"type": "emoji", "tint": tint, "emoji": emoji} for tint in pseudo_tints]


def _can_review(request):
    return request.user.is_authenticated and hasattr(request.user, "customer_profile")


def _product_video_render_data(product):
    """ورودیِ رندرِ ویدیوهایِ کالا برایِ صفحه‌ی عمومیِ محصول — عمداً هر ویدیو
    را همین‌جا (سمتِ سرور، نه در خودِ قالب) به یک دیکشنریِ ایمن تبدیل
    می‌کند: ``embed_url``/``instagram_permalink`` هر دو با تجزیه‌یِ مجددِ
    خودِ ``url`` محاسبه می‌شوند (نگاه کنید به
    ``product_video_service.detect_provider_and_id``)، و اگر یک ردیف —
    مثلاً از راهِ دستکاریِ مستقیمِ دیتابیس یا وارداتِ قدیمی — دیگر با هیچ
    الگویِ پشتیبانی‌شده‌ای تطبیق نداشت، آن ردیف فقط نادیده گرفته می‌شود؛
    اگر این تبدیل مستقیماً در قالب (به‌صورتِ ``{{ video.embed_url }}``)
    انجام می‌شد، همان یک ردیفِ نامعتبر کلِ صفحه‌ی محصول را با خطایِ ۵۰۰
    از کار می‌انداخت."""
    rendered = []
    for video in product.videos.all():
        try:
            embed_url = video.embed_url
            permalink = video.instagram_permalink if embed_url is None else ""
        except ProductVideoError:
            continue
        rendered.append({
            "provider_display": video.get_provider_display(),
            "title": video.title,
            "embed_url": embed_url,
            "permalink": permalink,
        })
    return rendered


def build_product_detail_context(request, product):
    """کانتکستِ کاملِ صفحه‌ی محصول — هم برایِ نمایشِ عمومیِ فروشگاه (``product_detail``)
    و هم برایِ پیش‌نمایشِ مدیرِ فروشگاه (``dashboard:product-preview``، برایِ
    کالاهایِ منتشرنشده) استفاده می‌شود تا منطق هرگز دوباره‌نویسی نشود."""
    store = product.store
    variant_groups = _variant_groups(product)
    spec_variant_summary = {
        attribute: "، ".join(v.value for v in items) for attribute, items in variant_groups.items()
    }

    approved_reviews = product.reviews.filter(is_approved=True).select_related("customer").order_by("-created_at")
    review_count = approved_reviews.count()
    rating_breakdown = []
    for star in range(5, 0, -1):
        count = approved_reviews.filter(rating=star).count()
        pct = round(count * 100 / review_count) if review_count else 0
        rating_breakdown.append({"star": star, "count": count, "pct": pct})

    related_products = (
        storefront_listing_products(store).filter(category=product.category)
        .exclude(pk=product.pk)
        .select_related("brand")
        .prefetch_related("images")[:4]
    )

    savings = product.price - product.final_price
    gift_wrap_available = is_gift_wrap_available(store)
    gift_wrap_price = resolve_gift_wrap_price(store) if gift_wrap_available else 0
    context = {
        "product": product,
        "variant_groups": variant_groups,
        "spec_variant_summary": spec_variant_summary,
        "variant_selector": build_variant_selector_context(product),
        "gift_wrap_available": gift_wrap_available,
        "gift_wrap_price": gift_wrap_price,
        "product_price_json": {
            "price": int(product.final_price), "regular": int(product.price),
            "savings": int(savings), "stock": product.stock, "sku": product.sku,
            "gift_wrap_price": int(gift_wrap_price),
        },
        "gallery_slides": _gallery_slides(product),
        "approved_reviews": approved_reviews,
        "review_count": review_count,
        "rating_breakdown": rating_breakdown,
        "related_products": related_products,
        "can_review": _can_review(request),
        "savings": savings,
        # ``product.videos`` همیشه فقط به همین کالا (و از طریقِ آن، همین
        # Store) محدود است — نگاه کنید به ``ProductVideo.product`` (FK).
        # صفحه‌ی عمومیِ محصول تا پیش از این هرگز این متغیر را در کانتکست
        # نمی‌گذاشت، پس ویدیوهایی که در ادمین با موفقیت ذخیره شده بودند،
        # هرگز در فروشگاه رندر نمی‌شدند — صرف‌نظر از درستیِ خودِ ذخیره‌سازی.
        "product_videos": _product_video_render_data(product),
    }
    return context


def product_detail(request, slug):
    store = resolve_store_for_storefront(request)
    product = get_object_or_404(
        storefront_visible_products(store)
        .select_related("brand", "category", "category__parent", "vendor")
        .prefetch_related("videos"),
        slug=slug,
    )
    Product.objects.filter(pk=product.pk).update(views_count=F("views_count") + 1)
    product.views_count += 1

    # Phase 1B: پوسته‌ی سراسری برایِ Storeهایی که Storefront V2 منتشر
    # کرده‌اند — منطقِ تجاریِ خودِ صفحه‌ی محصول (build_product_detail_context)
    # کاملاً دست‌نخورده می‌ماند؛ فقط هدر/فوتر (از طریقِ
    # ``templates/storefront_shell.html``ی که این تمپلیت اکنون extend
    # می‌کند) با همان نسخه‌یِ منتشرشده‌ای که صفحه‌ی اصلیِ همینِ Store دارد
    # یکسان می‌شود.
    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.storefront_builder.models import StorefrontPage

    context = build_product_detail_context(request, product)
    context.update(build_universal_storefront_context(
        request, store, StorefrontPage.PageType.PRODUCT_DETAIL, page_context=context,
    ))
    return render(request, "catalog/product_detail.html", context)


@require_POST
def product_review_create(request, slug):
    store = resolve_store_for_storefront(request)
    product = get_object_or_404(storefront_visible_products(store), slug=slug)

    context = {"product": product, "can_review": _can_review(request)}

    if not context["can_review"]:
        return render(request, "catalog/partials/review_form.html", context)

    posted_rating = request.POST.get("rating", "")
    text = request.POST.get("text", "").strip()
    errors = []

    rating = None
    try:
        rating = int(posted_rating)
        if not 1 <= rating <= 5:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("امتیاز باید بین ۱ تا ۵ باشد.")

    if not text:
        errors.append("متن نظر را وارد کنید.")

    if errors:
        context.update({"errors": errors, "posted_rating": posted_rating, "posted_text": text})
        return render(request, "catalog/partials/review_form.html", context)

    Review.objects.create(
        product=product, customer=request.user.customer_profile, rating=rating, text=text, is_approved=False
    )
    context["submitted"] = True
    response = render(request, "catalog/partials/review_form.html", context)
    response["HX-Trigger"] = json.dumps(
        {"toast": {"message": "نظر شما ثبت شد و پس از بررسی نمایش داده می‌شود", "type": "ok"}}
    )
    return response


def collection_index(request):
    """فهرستِ کالکشن‌هایِ فعالِ این Store — عمداً فقط ``name``/``image``/
    ``description`` را نشان می‌دهد، بدونِ کالاهایِ داخلِ هرکدام (که در
    ``collection_detail`` است) تا کوئری‌بودجه‌ی این صفحه ثابت بماند.

    U5 — این صفحه پیش از این هیچ صفحه‌بندی‌ای نداشت (شناخته‌شده به‌عنوانِ
    بدهیِ فنی در قرارداد اصلی): یک فروشگاه با کالکشن‌هایِ زیاد کلِ فهرست
    را در یک صفحه‌ی بی‌نهایت‌بلند رندر می‌کرد. همان الگویِ
    ``build_product_listing_context``/``collection_detail`` (``Paginator``
    + ``page_obj``) اینجا هم اعمال می‌شود — بدونِ تغییرِ کوئریِ خودِ
    ``public_collection_queryset`` (هنوز تنانت‌سیف/بدونِ N+1)."""
    store = resolve_store_for_storefront(request)
    paginator = Paginator(collection_service.public_collection_queryset(store), PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.storefront_builder.models import StorefrontPage

    context = {"collections": page_obj.object_list, "page_obj": page_obj}
    context.update(build_universal_storefront_context(request, store, StorefrontPage.PageType.COLLECTION, page_context=context))
    # Phase 4 (Task 3D, Ruling L) — StorefrontPage.PageType.COLLECTION means
    # Collection DETAIL composition; this call above only needs the shared
    # canonical Global Appearance/Header/Footer half of the returned
    # context. Collection Index is intentionally a domain-owned direct
    # listing page — it does NOT introduce a seventh Builder page type, and
    # ``collection_index.html`` must never include ``render_rows.html`` or
    # otherwise render the returned ``render_items``/``rows`` keys, which
    # belong to Collection Detail's section composition (both routes share
    # the same page_type slot, so those keys ARE present in this dict, but
    # consuming them here would silently leak Detail's Builder content onto
    # this page — see test_collection_public_views.CollectionIndexBoundaryTests
    # for the enforced boundary, including an end-to-end leak-proof test).
    return render(request, "catalog/collection_index.html", context)


def collection_detail(request, slug):
    store = resolve_store_for_storefront(request)
    collection = get_object_or_404(collection_service.public_collection_queryset(store), slug=slug)
    items = collection_service.collection_visible_items(collection, store)

    paginator = Paginator(items, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    products = [item.product for item in page_obj.object_list]

    from apps.storefront_builder.services.storefront_context_service import (
        build_universal_storefront_context,
    )
    from apps.storefront_builder.models import StorefrontPage

    context = {"collection": collection, "page_obj": page_obj, "products": products}
    context.update(build_universal_storefront_context(request, store, StorefrontPage.PageType.COLLECTION, page_context=context))
    return render(request, "catalog/collection_detail.html", context)
