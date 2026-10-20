"""The ONE public storefront context — shell + page body — for every page type.

Every public storefront page (home, listing, product detail, collection, search, cart, and the domain-owned ``shell_only``
pages) is rendered from the Store's PUBLISHED engine layout. A Store that has never published gets the engine's own
deterministic default (``layout_service.ensure_default_published_layout``) — there is no second, hard-coded page body and
no "unpublished" rendering path. The Draft is never read here.

The returned dict always has the same keys:

    storefront_version / storefront_page   the published ``StorefrontLayoutVersion`` / ``StorefrontPage`` (page is ``None``
                                           for ``shell_only`` pages)
    page_type, layout_header_config, layout_footer_config, store_appearance,
    header_variant_template, footer_variant_template, mobile_bottom_nav_template
    render_items / rows / render_containers / use_container_layout   the page body, from the shared render pipeline
    top_level_categories

Views ``context.update(...)`` it; they never duplicate this logic. Business content of a page (catalog, cart, orders) stays
owned by its domain view; ``page_context`` hands that already-resolved data to context-aware sections."""

from __future__ import annotations

from . import first_run_placeholder_service
from . import layout_service
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


def build_universal_storefront_context(
    request, store, page_type: str, page_context: dict | None = None,
    *, shell_only: bool = False,
) -> dict:
    """Context for ``store`` / ``page_type`` from the Store's published engine layout.

    Side effect (intended, same as the old ``home()``): ``request.storefront_appearance_version`` is set to the published
    version so the theme context processor reuses it instead of resolving it again.

    ``page_context``: the data the calling domain view already built (current product / collection / cart); passed unchanged to
    ``render_service.build_page_render_items`` for context-aware sections.

    ``shell_only``: an EXPLICIT opt-in for domain-owned public pages that match no ``StorefrontPage`` (wishlist, CMS pages):
    only the shell (header / footer / bottom nav / appearance) is built, with ``storefront_page=None`` and an empty body.
    A typo'd ``page_type`` is never inferred to be ``shell_only``."""
    # ONE rendering authority: every Store has a published engine layout (a never-published Store gets the engine's own
    # deterministic default, see ``layout_service.ensure_default_published_layout``) — there is no second, hard-coded body.
    layout = layout_service.ensure_default_published_layout(store)
    published = layout.published_version
    if shell_only:
        return _build_published_shell_context(
            request, store, published, page=None, page_type=page_type, page_context=page_context,
        )
    page = published.pages.filter(page_type=page_type).first()
    if page is None:  # an unknown ``page_type`` is a programming error, never a silent fallback to another body
        raise ValueError(f"unknown storefront page type {page_type!r}")
    return _build_published_shell_context(
        request, store, published, page=page, page_type=page_type, page_context=page_context,
    )


def _build_published_shell_context(
    request, store, version, page, page_type: str, page_context: dict | None,
) -> dict:
    """صورتِ ثابتِ «منتشرشده» — مشترک بینِ شش نوعِ صفحه‌یِ واقعی (``page``
    یک ``StorefrontPage`` واقعی) و صفحاتِ domain-owned با ``shell_only=True``
    (``page=None``). استخراج‌شده از بدنه‌یِ قدیمیِ تابعِ بالا — بدونِ تغییرِ
    رفتار برایِ مسیرِ ``page`` واقعی؛ تنها یک اسمبلیِ واحد برایِ هر دو مسیر،
    نه دو نسخه‌یِ کپی‌شده (نگاه کنید به سندِ معماریِ P5-W4A §۱۱)."""
    # نگاه کنید به توضیحِ docstringِ تابعِ صدازننده — این تنها نقطه‌ای غیر از
    # ``home()``یِ قدیمی است که این attribute را ست می‌کند؛ اکنون برایِ هر شش
    # نوعِ صفحه‌یِ واقعی و هر صفحه‌یِ ``shell_only`` یکسان است.
    request.storefront_appearance_version = version
    # Phase 4 (Task 3C) — the SAME pattern, for the current StorefrontPage,
    # so apps.core.context_processors._versioned_appearance can resolve the
    # Page Appearance tier (Store Global merged with this page's own sparse
    # override) identically for Preview and Public — both routes reach this
    # exact function, so both set this attribute exactly the same way.
    # P5-W4A: a ``shell_only`` page has no per-page Page Appearance tier of
    # its own (no ``StorefrontPage`` row backs it), so this is explicitly
    # ``None`` — never a foreign page's own tier.
    request.storefront_appearance_page = page

    # P5-W2 Repair A — resolve the canonical appearance ONCE per request and
    # cache it on the request, so the shell context processor
    # (apps.core.context_processors.shop_settings) reuses this exact resolved
    # state for its Theme projection instead of resolving the same Version a
    # second time.
    store_appearance = render_service.resolved_store_appearance_for_request(
        request, version
    )
    header_config = version.effective_header_config()
    footer_config = version.effective_footer_config()

    if page is None:
        # P5-W4A shell_only: no StorefrontPage row backs this domain-owned
        # page, so there is nothing to resolve sections for — the domain
        # view supplies 100% of its own body markup. Never fabricate a page
        # or borrow another page type's render_items.
        items: list[dict] = []
        rows: list[dict] = []
        render_containers: list[dict] = []
        use_container_layout = False
    else:
        items = render_service.build_page_render_items(
            page,
            store,
            page_context=page_context,
            store_appearance=store_appearance,
        )
        # A brand-new modern-portal Store with no catalog yet keeps its selected Ready Template's
        # composition visible through neutral, non-persistent placeholders (first_run_placeholder_service);
        # every other Store is unaffected.
        items = first_run_placeholder_service.apply_first_run_placeholders(
            items, store, page_type=page_type,
        )
        # Acceptance Batch 1 (post-U11) — see the note on the unresolved-store
        # branch above.
        items = render_service.hide_empty_public_sections(items)
        rows = render_service.group_items_into_rows(items)
        render_containers = render_service.build_container_render_items(page, items)
        use_container_layout = page.containers.exists()

    return {
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
        "rows": rows,
        "render_containers": render_containers,
        "use_container_layout": use_container_layout,
        "top_level_categories": _top_level_categories(store),
    }


def render_domain_page(request, template_name: str, context: dict | None = None, *, page_type: str = "domain_page"):
    """Render a DOMAIN-OWNED storefront page (checkout, payment result, customer account …) inside the engine shell.

    The page body stays owned by its domain view/template — commerce behaviour is never turned into design settings — while the
    shell (header, footer, bottom nav, appearance tokens) comes from the same published engine layout as every other
    storefront page. There is no separate hard-coded header / footer for any storefront page."""
    from django.shortcuts import render

    from apps.stores.resolution import resolve_store_for_service

    page_context = dict(context or {})
    page_context.update(build_universal_storefront_context(
        request, resolve_store_for_service(request), page_type, page_context=page_context, shell_only=True,
    ))
    return render(request, template_name, page_context)
