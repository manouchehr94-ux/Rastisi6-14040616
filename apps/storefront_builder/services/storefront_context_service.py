"""Phase 1B — کانتکستِ سراسریِ عمومیِ Storefront، متمرکز در یک تابع.

هدفِ صریحِ این ماژول (طبقِ الزامِ کار، بخشِ B): «Create a central
service/helper that builds the global storefront context for public
rendering... Do not duplicate this logic across six views». پیش از این
فاز، فقط ``apps.catalog.views.home()`` این منطق را داشت (و فقط برایِ صفحه‌ی
اصلی)؛ این تابع همان منطق را به هر شش نوع صفحه تعمیم می‌دهد — بدونِ
بازنویسیِ منطقِ تجاریِ کاتالوگ/سبد/سفارش (که کاملاً دست‌نخورده می‌ماند؛ این
تابع فقط پوسته‌یِ سراسری را می‌سازد، نه محتوایِ خاصِ خودِ هر صفحه).

قراردادِ برگشتی — همیشه یک دیکشنریِ کاملاً پیش‌بینی‌پذیر با همین کلیدها،
چه Store منتشرشده داشته باشد چه نه (طبقِ الزامِ کار: «Do NOT auto-create
arbitrary visual blocks» برایِ صفحاتِ خالی؛ اینجا معادلش «همیشه یک شکلِ
یکسان برگردان، حتی برایِ Storeای که هنوز چیزی منتشر نکرده» است):

    {
        "uses_universal_shell": bool,       # آیا این Store یک نسخه‌ی
                                             # منتشرشده‌یِ V2 دارد؟
        "storefront_version": StorefrontLayoutVersion | None,
        "storefront_page": StorefrontPage | None,
        "page_type": str,                   # همیشه پر است — حتی وقتی
                                             # uses_universal_shell=False
        "layout_header_config": dict | None,
        "layout_footer_config": dict | None,
        "render_items": list[dict],         # همیشه [] اگر صفحه هنوز
                                             # Sectionای ندارد یا Store
                                             # اصلاً منتشر نکرده
        "rows": list[dict],                 # Phase 2: همان render_items
                                             # بالا، گروه‌بندی‌شده به ردیف —
                                             # نگاه کنید به
                                             # render_service.group_items_into_rows
    }

فراخوان (view) این دیکشنری را مستقیماً به کانتکستِ template اضافه
می‌کند (``context.update(build_universal_storefront_context(...))``) —
هرگز کدِ این ماژول را کپی نمی‌کند."""

from __future__ import annotations

from . import page_resolution_service
from . import render_service


def _top_level_categories(store):
    """دسته‌بندی‌هایِ سطحِ اولِ فعالِ همین Store — طبقِ خودِ partialِ
    ``page_shell_footer.html`` (بخشِ ``fc.show_categories``)، این یک
    نیازِ *پوسته‌ی سراسری* است (هر شش صفحه، نه فقط صفحه اصلی) — پیش از
    Phase 1B فقط ``home()`` این کوئری را می‌زد (چون فقط صفحه‌ی اصلی از
    این partial استفاده می‌کرد)؛ اکنون که پوسته به هر شش صفحه می‌رسد،
    همینجا (نه دوباره در هر ویو) محاسبه می‌شود."""
    from apps.catalog.models import Category

    return Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")


def build_universal_storefront_context(request, store, page_type: str, page_context: dict | None = None) -> dict:
    """کانتکستِ سراسریِ Storefront برایِ ``store`` و ``page_type`` مشخص.

    عوارضِ جانبیِ عمدی (دقیقاً همان الگویِ قبلیِ ``home()``، حالا
    تعمیم‌یافته به هر شش صفحه): اگر Store یک نسخه‌ی منتشرشده دارد،
    ``request.storefront_appearance_version`` روی همان نسخه ست می‌شود —
    این همان attributeای است که
    ``apps.core.context_processors._global_identity_version``/``_versioned_appearance``
    برایِ خواندنِ رنگ/فونت/خانواده/توکن‌هایِ ساختاریِ سراسری از آن استفاده
    می‌کنند؛ بدونِ این ست‌شدن، آن context processor به‌جایِ آن دوباره
    مستقیماً ``get_published_layout_for_store_id`` را صدا می‌زد (که هنوز هم
    نتیجه‌یِ درست را می‌دهد — این فقط یک بهینه‌سازیِ حذفِ کوئریِ تکراری در
    یک درخواست است، نه یک شرطِ صحت). قبل از Phase 1B این attribute فقط
    توسطِ ``home()`` ست می‌شد — اکنون توسطِ هر شش نوع صفحه‌ای که از این
    تابع عبور می‌کند ست می‌شود، دقیقاً همان چیزی که «یک قراردادِ نسخه‌یِ
    واحد برایِ همه‌یِ شش نوعِ صفحه» به آن نیاز دارد.

    ``page_context`` (Phase 5): همان دیکشنریِ کاملی که فراخوان (ویوِ
    مسیرِ عمومی) از قبل برایِ رندرِ سخت‌کدشده‌یِ خودِ صفحه ساخته (مثلاً
    ``build_product_detail_context``یِ ``product_detail``، یا
    ``{"cart": ..., "totals": ...}``یِ سبد) — به‌طورِ کامل و بدونِ تغییر
    به ``render_service.build_page_render_items`` پاس داده می‌شود تا
    section‌هایِ context-aware (محصولِ جاری/کالکشنِ جاری/سبدِ جاری) بتوانند
    بدونِ کوئریِ تکراری و بدونِ ذخیره‌یِ هیچ IDای در ``settings`` به همان
    دادهٔ از پیش تفکیک‌شده‌یِ Store دسترسی داشته باشند. غیابِ آن (``None``)
    دقیقاً معادلِ دیکشنریِ خالی است — صفحاتِ بدونِ section context-aware
    (یا Storeهایی که هنوز منتشر نکرده‌اند) هیچ رفتاری تغییر نمی‌کند."""
    resolved = page_resolution_service.resolve_published_page(store, page_type)

    if not resolved.is_resolved:
        items = render_service.build_default_render_items(page_type, store, page_context=page_context)
        # Acceptance Batch 1 (post-U11) — this function is the single
        # public/live rendering entry point (see module docstring); the
        # Builder/editor preview never calls it (it calls
        # ``build_page_render_items``/``build_default_render_items``
        # directly), so this only ever hides empty optional product
        # sections from real shoppers, never from a merchant composing a
        # page. See ``render_service.hide_empty_public_sections``.
        items = render_service.hide_empty_public_sections(items)
        return {
            "uses_universal_shell": False,
            "storefront_version": None,
            "storefront_page": None,
            "page_type": page_type,
            "layout_header_config": None,
            "layout_footer_config": None,
            "store_appearance": None,
            "mobile_bottom_nav_template": None,
            # Phase 5: پنج صفحه‌ی محصول/لیست/کالکشن/جستجو/سبد پیش از این
            # فاز محتوایِ سخت‌کدشده‌ی خودشان را کاملاً مستقل از انتشارِ V2
            # نشان می‌دادند — این تابع همان تجربه را حفظ می‌کند (نگاه کنید
            # به build_default_render_items). ``home`` بی‌اثر می‌ماند، چون
            # صفحه‌ی اصلیِ منتشرنشده از تمپلیتِ کاملاً جداگانه‌ی
            # ``catalog/home.html`` استفاده می‌کند، نه render_items.
            "render_items": items,
            # Phase 2 (Universal Renderer): فهرستِ تخت بالا را به «ردیف‌ها»
            # گروه‌بندی می‌کند (نگاه کنید به ``render_service.group_items_into_rows``)
            # — تمپلیت‌های عمومی از این کلید برای رندر واقعی استفاده می‌کنند،
            # نه ``render_items`` مستقیم (که فقط برای سازگاریِ عقب‌رو/مصرفِ
            # احتمالیِ دیگر نگه داشته شده).
            "rows": render_service.group_items_into_rows(items),
            "render_containers": [],
            "use_container_layout": False,
            "top_level_categories": _top_level_categories(store),
        }

    version = resolved.version
    page = resolved.page
    # نگاه کنید به توضیحِ بالا — این تنها نقطه‌ای غیر از ``home()``یِ
    # قدیمی است که این attribute را ست می‌کند؛ اکنون برایِ هر شش نوعِ
    # صفحه یکسان است، نه فقط صفحه‌ی اصلی.
    request.storefront_appearance_version = version
    # Phase 4 (Task 3C) — the SAME pattern, for the current StorefrontPage,
    # so apps.core.context_processors._versioned_appearance can resolve the
    # Page Appearance tier (Store Global merged with this page's own sparse
    # override) identically for Preview and Public — both routes reach this
    # exact function, so both set this attribute exactly the same way.
    request.storefront_appearance_page = page

    store_appearance = render_service.resolve_store_appearance_render_state(version)
    items = render_service.build_page_render_items(
        page,
        store,
        page_context=page_context,
        store_appearance=store_appearance,
    )
    # Acceptance Batch 1 (post-U11) — see the note on the unresolved-store
    # branch above.
    items = render_service.hide_empty_public_sections(items)
    header_config = version.effective_header_config()
    footer_config = version.effective_footer_config()
    return {
        "uses_universal_shell": True,
        "storefront_version": version,
        "storefront_page": page,
        "page_type": page_type,
        "layout_header_config": header_config,
        "store_appearance": store_appearance,
        # U2A — رشته‌ی نامِ Templateِ Djangoِ هدرِ فعال، از رویِ Registryِ
        # امن resolve شده (نگاه کنید به ``global_region_registry``)؛ هرگز
        # از JSONِ ذخیره‌شده مستقیماً خوانده نمی‌شود — فقط کلیدِ
        # ``header_variant``یِ آن بررسی می‌شود، خودِ مسیرِ Template همیشه
        # یک رشته‌ی ثابتِ نوشته‌شده در کدِ پایتونِ همان Registry است.
        "header_variant_template": render_service.store_appearance_global_renderer_template(
            store_appearance, "header", header_config,
        ),
        "layout_footer_config": footer_config,
        # U2B — همان الگویِ ``header_variant_template`` بالا، برایِ فوتر.
        "footer_variant_template": render_service.store_appearance_global_renderer_template(
            store_appearance, "footer", footer_config,
        ),
        "mobile_bottom_nav_template": render_service.store_appearance_global_renderer_template(
            store_appearance, "bottom_nav", footer_config,
        ),
        "render_items": items,
        "rows": render_service.group_items_into_rows(items),
        "render_containers": render_service.build_container_render_items(page, items),
        "use_container_layout": page.containers.exists(),
        "top_level_categories": _top_level_categories(store),
    }
