"""ویوهای داشبورد سازنده بصری صفحه فروشگاه — همگی پشت
``STOREFRONT_LAYOUT_MANAGE`` (نه ``CONTENT_MANAGE``، طبق تصمیم کاربر)."""

from django.contrib import messages
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import section_registry
from .models import (
    StorefrontContainer,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from .services import (
    layout_service,
    r4_mutation_service,
)
from .services.ready_template_card_service import (
    preset_would_replace_content as _preset_would_replace_content,
)
from .services.render_service import (
    build_candidate_container_rows,
    build_candidate_render_items,
    build_container_render_items,
    build_page_render_items,
    group_items_into_rows,
    resolved_store_appearance_for_request,
    store_appearance_global_renderer_template,
)


def _resolve_store(request):
    return resolve_store_for_service(request)


def _resolve_page_type(raw) -> str:
    """Phase 2 (سازنده‌ی تک‌صفحه‌ای)، Phase 4 (Task 3B) — رشته‌یِ خامِ ``page``
    (از querystring یا فرمِ POST) را به یکی از شش نوعِ معتبرِ
    ``StorefrontPage.PageType`` حل می‌کند. اکنون فقط یک نازک‌لایه‌یِ
    سازگاریِ اسمِ قدیمی روی ``StorefrontPage.resolve_page_type`` است —
    که R4 (``r4_views.py``) هم مستقیماً از همان تابعِ مشترک استفاده
    می‌کند تا دو زنجیره‌یِ اعتبارسنجیِ کپی‌شده وجود نداشته باشد."""
    return StorefrontPage.resolve_page_type(raw)


class _CandidateAppearanceVersion:
    """جای‌گزینِ سبکِ ``StorefrontLayoutVersion`` برایِ پیش‌نمایشِ
    غیرمخربِ یک Templateِ کاندید (چکپوینتِ «پیش‌نمایشِ قبل از اعمال»،
    بخشِ ۱۰ بازبینیِ نهایی) — فقط همان یک متدی را دارد که
    ``apps.core.context_processors`` روی ``request.storefront_appearance_version``
    صدا می‌زند (``effective_appearance_config``)، هرگز به دیتابیس
    نمی‌نویسد. تعویضِ template_slug دقیقاً همان معنایی را دارد که
    ``storefront_appearance_editor`` هنگامِ POSTِ واقعیِ تعویض اعمال
    می‌کند (فیلدهایِ ساختاری به پیش‌فرض‌هایِ همان Template بازنشانی
    می‌شوند) — تا پیش‌نمایش دقیقاً همان چیزی باشد که اعمالِ واقعی تولید
    می‌کند."""

    def __init__(self, base_config, *, template_slug=None):
        from . import appearance_registry

        config = dict(base_config)
        if template_slug is not None:
            config["template_slug"] = template_slug
            template = appearance_registry.get_template(template_slug)
            if template is not None:
                for field in ("font", "radius", "button_radius", "density", "motion", "type_scale"):
                    config[field] = getattr(template, field)
        self._config = config

    def effective_appearance_config(self):
        return self._config


class _ReadyTemplateCandidateAppearanceVersion:
    """Phase 5, Task 2 — same idiom as ``_CandidateAppearanceVersion`` above
    (a minimal read-only stand-in exposing only ``effective_appearance_config()``,
    never touching the database), but backed directly by a Task-1
    ``ResolvedPresetCandidate.appearance_config`` — the candidate's own fully
    resolved appearance, not a ``template_slug``-derived overlay onto a base
    config. Setting this as ``request.storefront_appearance_version`` makes
    ``apps.core.context_processors``' global color/font tokens (consumed by
    ``base.html`` site-wide, not just this view's own content block) reflect
    the previewed Ready Template's own DNA, exactly like
    ``storefront_preview()`` already does for its own candidate-appearance
    case."""

    def __init__(self, appearance_config: dict):
        self._config = appearance_config

    def effective_appearance_config(self):
        return self._config


def _preview_page_context(request, store, page_type: str) -> dict:
    """Phase 5: معادلِ ``page_context``یِ مسیرِ عمومی، اما برایِ Preview که
    هیچ «محصول/کالکشن/جستجویِ جاری» واقعی از URL ندارد — یک نمونه‌یِ
    نماینده (جدیدترین محصول/کالکشن همین Store) با **همان توابعِ** مسیرِ
    عمومی ساخته می‌شود (نه بازنویسیِ منطق)، تا section‌هایِ context-aware
    در پیش‌نمایش هم چیزیِ واقعی و درست-تفکیک‌شده نشان دهند. برایِ سبد،
    دقیقاً همان مسیرِ «سبدِ خالی»یِ ``_cart_context(request, None)`` استفاده
    می‌شود — Preview هرگز نباید سبدِ واقعیِ کاربر را نشان دهد (نگاه کنید
    به ``test_preview_never_shows_real_cart_or_wishlist_count``، Phase 4).
    غیابِ داده (مثلاً فروشگاهی که هنوز هیچ محصولی ندارد) بی‌صدا دیکشنریِ
    خالی برمی‌گرداند — section مربوطه fail-safe چیزی رندر نمی‌کند."""
    if page_type == StorefrontPage.PageType.PRODUCT_DETAIL:
        from apps.catalog.services.product_publish_service import storefront_visible_products
        from apps.catalog.views import build_product_detail_context

        product = storefront_visible_products(store).order_by("-created_at").first()
        return build_product_detail_context(request, product) if product is not None else {}

    if page_type in (StorefrontPage.PageType.LISTING, StorefrontPage.PageType.SEARCH):
        from apps.catalog.views import build_product_listing_context

        return build_product_listing_context(request, store)

    if page_type == StorefrontPage.PageType.COLLECTION:
        from django.core.paginator import Paginator

        from apps.catalog.services import collection_service
        from apps.catalog.views import PRODUCTS_PER_PAGE

        collection = collection_service.public_collection_queryset(store).order_by("-created_at").first()
        if collection is None:
            return {}
        items = collection_service.collection_visible_items(collection, store)
        page_obj = Paginator(items, PRODUCTS_PER_PAGE).get_page(request.GET.get("page"))
        return {"collection": collection, "page_obj": page_obj, "products": [item.product for item in page_obj.object_list]}

    if page_type == StorefrontPage.PageType.CART:
        from apps.cart.views import _cart_context

        return _cart_context(request, None)

    return {}


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_editor(request):
    """The classic builder URL is kept as a stable entry point (links, bookmarks, dashboard buttons): the Studio is the
    one editor, so this only forwards there, keeping the requested page."""
    url = reverse("dashboard:storefront-builder-r4-editor")
    page = request.GET.get("page")
    return redirect(f"{url}?page={page}" if page else url)


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@xframe_options_sameorigin
def storefront_preview(request):
    """پیش‌نمایش تمام‌صفحه‌ی Draft فعلی — فقط برای staff همین فروشگاه؛ هرگز
    برای بازدیدکننده عمومی در دسترس نیست (تصمیم ۱۱ کاربر).

    ``xframe_options_sameorigin`` صراحتاً override می‌کند چون این ویو عمداً
    داخل iframe ادیتور embed می‌شود؛ پیش‌فرض سراسری DENY (میدل‌ور
    XFrameOptionsMiddleware بدون X_FRAME_OPTIONS) برای همه‌ی ویوهای دیگر
    دست‌نخورده باقی می‌ماند."""
    from apps.catalog.models import Category

    from . import appearance_registry

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    # Phase 2: پیش‌نمایش هم باید همان صفحه‌ای را نشان دهد که ادیتور در
    # حالِ ویرایشِ آن است — ``?page=`` دقیقاً همان پارامتری است که
    # ``storefront_editor`` به iframe پاس می‌دهد.
    page_type = _resolve_page_type(request.GET.get("page"))
    page = draft.get_page(page_type)
    # Container/Cell is primary once a page owns any real Container. Legacy
    # direct Section rows still need the documented compatibility renderer;
    # forcing Container mode when none exist makes otherwise valid Draft
    # sections disappear from Preview.
    use_container_layout = page.containers.exists()
    # P5-W2 Repair A (IMPORTANT 1) — resolve the canonical appearance ONCE per
    # request and cache it on the request, so the shell context processor
    # (apps.core.context_processors.shop_settings) reuses this exact resolved
    # state for its Theme projection instead of resolving the same Draft a
    # second time. The ``?preview_template`` candidate branch below sets a
    # transient stand-in (not this Draft) as ``storefront_appearance_version``,
    # which the context processor never passes to the persisted resolver.
    store_appearance = resolved_store_appearance_for_request(request, draft)
    # P5-W3 — transient Design Lab candidate preview. ``?design_lab=<token>``
    # carries an in-memory appearance-DNA candidate (never persisted, never a
    # candidate Draft). It is resolved through the EXACT same canonical
    # resolver + renderer the committed Draft uses; the ONLY difference is
    # which ``ResolvedStoreAppearance`` feeds ``build_page_render_items``. The
    # candidate is ALWAYS re-validated server-side against the canonical
    # registry (untrusted component keys fail closed with 400) — the token is a
    # transport, never an authority, and never a source of truth. Zero writes.
    design_lab_token = request.GET.get("design_lab")
    if design_lab_token:
        from .services import design_lab_service
        from .storefront_appearance.contracts import InvalidStoreAppearanceContract

        try:
            candidate = design_lab_service.decode_candidate_token(design_lab_token)
            store_appearance = design_lab_service.resolve_candidate_appearance(
                draft, candidate
            )
        except (ValueError, InvalidStoreAppearanceContract):
            return HttpResponseBadRequest("کاندید آزمایشگاه طراحی نامعتبر است")
    items = build_page_render_items(
        page,
        store,
        page_context=_preview_page_context(request, store, page_type),
        store_appearance=store_appearance,
    )
    top_level_categories = Category.objects.filter(store=store, parent__isnull=True, is_active=True).order_by("order", "name")
    # تنظیماتِ ظاهر باید از همین Draft خوانده شود، نه ShopSettings زنده —
    # نگاه کنید به ``apps.core.context_processors._versioned_colors``.
    #
    # ``?preview_template=<slug>`` (چکپوینتِ «پیش‌نمایشِ غیرمخربِ قالب»)
    # به مرچنت اجازه می‌دهد ظاهرِ یک Templateِ دیگر را در همین iframe
    # ببیند **بدونِ** ذخیره‌شدن روی Draft — فقط همین رندر، هرگز دیتابیس.
    # اسلاگِ نامعتبر/ناشناخته بی‌صدا نادیده گرفته می‌شود (پیش‌نمایشِ
    # Draftِ واقعی، دقیقاً رفتارِ قبل)."""
    preview_template_slug = request.GET.get("preview_template")
    if preview_template_slug and appearance_registry.get_template(preview_template_slug) is not None:
        request.storefront_appearance_version = _CandidateAppearanceVersion(
            draft.effective_appearance_config(), template_slug=preview_template_slug,
        )
    else:
        request.storefront_appearance_version = draft
    # Phase 4 (Task 3C) — the same pattern as ``storefront_appearance_version``
    # just above: Preview independently sets this request attribute (it does
    # not call ``build_universal_storefront_context``, which is the public-only
    # entry point), so ``apps.core.context_processors._versioned_appearance``
    # resolves the Page Appearance tier identically here.
    request.storefront_appearance_page = page
    header_config = draft.effective_header_config()
    footer_config = draft.effective_footer_config()
    header_variant_template = store_appearance_global_renderer_template(
        store_appearance, "header", header_config,
    )
    footer_variant_template = store_appearance_global_renderer_template(
        store_appearance, "footer", footer_config,
    )
    mobile_bottom_nav_template = store_appearance_global_renderer_template(
        store_appearance, "bottom_nav", footer_config,
    )
    return render(request, "storefront_builder/preview.html", {
        "store": store, "version": draft, "page": page, "page_type": page_type,
        "header_variant_template": header_variant_template,
        "footer_variant_template": footer_variant_template,
        "mobile_bottom_nav_template": mobile_bottom_nav_template,
        "store_appearance": store_appearance,
        "render_items": items,
        # Legacy rows remain as a compatibility fallback; Container/Cell is now
        # the primary Builder composition source. Empty cells are visible only here.
        "rows": group_items_into_rows(items),
        "render_containers": build_container_render_items(page, items, include_empty=True),
        "use_container_layout": use_container_layout,
        "is_preview": True,
        "top_level_categories": top_level_categories,
    })


@never_cache
@require_GET
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_draft_preview(request):
    """«پیش‌نمایش» — the customer view of the Store's current DRAFT (unpublished changes), for a manager of THIS store only.

    Read-only: it renders the Draft through the public pipeline (``build_draft_preview_context`` → the same shell, appearance and section
    renderers as the live storefront, no builder markers, no overlays) and never writes or publishes. ``?page=`` selects the page type the
    Studio is on. ``never_cache`` so a refresh always shows the latest saved Draft. A Store with no Draft has no unpublished changes: the page
    says so explicitly and shows the current published layout (never silently)."""
    from .models import StorefrontLayout
    from .services.storefront_context_service import build_draft_preview_context

    store = _resolve_store(request)
    page_type = _resolve_page_type(request.GET.get("page"))
    layout = StorefrontLayout.objects.filter(store=store).select_related("draft_version", "published_version").first()
    version = layout.draft_version if layout is not None else None
    is_draft = version is not None
    if version is None:
        version = layout_service.ensure_default_published_layout(store).published_version
    context = build_draft_preview_context(
        request, store, version, page_type, page_context=_preview_page_context(request, store, page_type),
    )
    context.update({"store": store, "is_draft_preview": True, "draft_preview_is_draft": is_draft})
    return render(request, "storefront_builder/draft_preview.html", context)


def render_preview_fragment(request, store, draft, *, section_id=None, container_id=None):
    """Canonical server-rendered HTML of ONE section (or ONE container) of the Draft Preview.

    Partial refresh architecture: the Studio never re-implements storefront rendering in JavaScript. After an accepted
    ``section.update_settings`` / ``container.update_settings`` the mutation response carries this fragment — produced by
    the SAME ``build_page_render_items`` / wrapper / container templates as the full Preview, restricted to the affected
    sections — and the Studio swaps only that region inside the Preview iframe.

    Returns ``{"kind", "id", "html"}``, or ``None`` when a fragment cannot be produced faithfully (legacy row layout, a
    hidden/inactive block, an unknown id): the caller then falls back to the atomic full-frame refresh."""
    from django.template.loader import render_to_string

    if section_id is not None:
        section = StorefrontSection.objects.select_related("page").filter(
            pk=section_id, page__version=draft, is_active=True).first()
        if section is None:
            return None
        page = section.page
    elif container_id is not None:
        container = StorefrontContainer.all_objects.select_related("page", "parent_cell__container").filter(pk=container_id, page__version=draft).first()
        if container is None:
            return None
        # V5 Groups: a nested Group is re-rendered as part of its top-level row (the region the preview swaps is that row).
        while container.parent_cell_id is not None:
            container = container.parent_cell.container
            container_id = container.pk
        page = container.page
    else:
        return None
    if not page.containers.exists():
        return None  # legacy direct-row layout: only the full refresh is faithful

    request.storefront_appearance_version = draft
    request.storefront_appearance_page = page
    store_appearance = resolved_store_appearance_for_request(request, draft)
    structure = build_container_render_items(page, [], include_empty=True)
    wanted = None

    def _walk(composition):
        nonlocal wanted
        for cell_entry in composition["cells"]:
            block_ids = {block.pk for block in cell_entry["blocks"]}
            if section_id is not None and section_id in block_ids:
                wanted = (composition, cell_entry)
            if container_id is not None and composition["container"].pk == container_id:
                wanted = (composition, cell_entry)
            if cell_entry.get("group") is not None:
                _walk(cell_entry["group"])

    def _all_block_ids(composition):
        ids = set()
        for entry in composition["cells"]:
            ids.update(block.pk for block in entry["blocks"])
            if entry.get("group") is not None:
                ids |= _all_block_ids(entry["group"])
        return ids

    for composition in structure:
        _walk(composition)
    if wanted is None:
        return None
    if container_id is not None:
        only_ids = _all_block_ids(wanted[0])
    else:
        only_ids = {section_id}
    items = build_page_render_items(
        page, store, page_context=_preview_page_context(request, store, page.page_type),
        store_appearance=store_appearance, only_section_ids=only_ids,
    )
    compositions = build_container_render_items(page, items, include_empty=True)
    context = {"store": store, "version": draft, "page": page, "page_type": page.page_type,
               "store_appearance": store_appearance, "is_preview": True, "is_builder_preview": True}
    if container_id is not None:
        composition = next((c for c in compositions if c["container"].pk == container_id), None)
        if composition is None:
            return None
        html = render_to_string("storefront_builder/partials/render_containers.html",
                                {**context, "render_containers": [composition]}, request=request)
        return {"kind": "container", "id": container_id, "html": html.strip()}
    def _find_composition(pool, container_pk):
        for candidate in pool:
            if candidate["container"].pk == container_pk:
                return candidate
            for entry in candidate["cells"]:
                if entry.get("group") is not None:
                    found = _find_composition([entry["group"]], container_pk)
                    if found is not None:
                        return found
        return None

    composition = _find_composition(compositions, wanted[0]["container"].pk)
    if composition is None:
        return None
    cell_entry = next(ce for ce in composition["cells"] if ce["cell"].pk == wanted[1]["cell"].pk)
    item = next((i for i in cell_entry["items"] if i["section"].pk == section_id), None)
    if item is None:
        return None  # e.g. the block is hidden: the placeholder differs, use the full refresh
    html = render_to_string(
        "storefront_builder/partials/preview_section_fragment.html",
        {**context, "item": item, "placement_cell": cell_entry["cell"], "placement_container": composition["container"]},
        request=request,
    )
    return {"kind": "section", "id": section_id, "html": html.strip()}


def _get_scoped_section(request, pk):
    """Phase 1A: مسیرِ فیلترِ تفکیکِ مستأجر یک لایه‌یِ ``page__`` عمیق‌تر
    شده (``page__version__...`` به‌جایِ ``version__...`` قبلی) — دقیقاً
    همان دو شرط (فروشگاهِ درست، وضعیتِ Draft)، فقط از طریقِ زنجیره‌یِ
    ارجاعِ جدید."""
    store = _resolve_store(request)
    return get_object_or_404(
        StorefrontSection, pk=pk, page__version__layout__store=store,
        page__version__status=StorefrontLayoutVersion.Status.DRAFT,
    )


def _background_picker_context(request, section) -> dict:
    from apps.content.models import MediaAsset

    store = _resolve_store(request)
    return {
        "background_patterns": section_registry.PATTERN_REGISTRY,
        "background_media_assets": MediaAsset.objects.filter(store=store).order_by("-created_at", "-id")[:60],
    }


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_template_gallery(request):
    """ARCH-02 — the Design Studio's own gallery is the ONE official place to browse, preview and apply a
    Ready Template. This stable URL (links, bookmarks, dashboard navigation) only forwards there and opens the
    gallery directly (``?open=templates``). It deliberately renders nothing and writes nothing — not even the
    Draft the old page used to create on every GET; the Studio creates its Draft exactly as it always does when
    it is opened. Access control (staff + ``STOREFRONT_LAYOUT_MANAGE``) is unchanged."""
    url = reverse("dashboard:storefront-builder-r4-editor")
    page = request.GET.get("page")
    query = f"?page={page}&open=templates" if page else "?open=templates"
    return redirect(f"{url}{query}")


#: Phase 5, Task 2 — the ONE canonical Demo Store this live-preview view is
#: allowed to render against. A fixed, server-side, staff-only constant —
#: never taken from a query parameter or any other request-controlled input
#: (see the view's own docstring for the full security rationale). Mirrors
#: the exact same literal every other canonical Demo Store consumer already
#: uses (``capture_ready_template_previews.py``,
#: ``seed_ready_template_fashion_demo.py``, ``golden_reference_service.py``)
#: — this repo's established convention is one small local constant per
#: consumer, not a shared config module; introducing one now would be a
#: second, undiscovered source of truth for a single literal string.
RASTI_MODE_DEMO_STORE_SLUG = "rasti-mode-demo"


@require_GET
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@xframe_options_sameorigin
def storefront_template_live_preview(request, key):
    """Live, non-mutating Ready Template preview for Demo or Merchant data.

    Phase 5 Task 2 established this ONE preview route, Task-1 candidate
    resolution and the shared renderer.  Task 3 keeps that architecture and
    adds only a data-context choice:

    P5-W5C explicitly overrides ``xframe_options_sameorigin`` for the same
    reason ``storefront_preview`` already does: this view is now
    intentionally embedded inside the Ready Template Gallery's own in-page
    preview inside the Design Studio (``r4_studio.js``); the global
    default DENY (no ``X_FRAME_OPTIONS`` set, ``XFrameOptionsMiddleware``'s
    own fallback) remains untouched for every other view.

    P5-W5C Independent Architect repair — ``@require_GET`` makes the
    "GET-only" claim this view already made actually true (a bare POST now
    gets a controlled 405 instead of silently being accepted); and Demo
    mode's candidate resolution was changed from ``get_or_create_draft`` to
    the SAME non-creating ``get_existing_draft`` Merchant mode already
    used, closing a real gap where a GET request could bootstrap a Draft
    for the canonical Demo Store if one didn't exist yet. Both modes now
    share the identical "read an existing Draft or fail closed with 404"
    contract — Preview creates ZERO persistence in either data mode.

    * default: the canonical ``rasti-mode-demo`` Store (Task-2 behavior),
    * ``?data=merchant``: the Store resolved by the existing canonical
      ``resolve_store_for_service`` path via ``_resolve_store(request)``.

    Merchant mode never accepts a Store id/slug from request input and never
    falls back to Demo data.  It also never bootstraps persistence: candidate
    resolution requires an already-existing merchant Draft.  If no Draft
    exists, the request fails closed with 404.  Candidate sections remain
    transient and are rendered by the same shared renderer as Task 2.
    """
    from apps.stores.models import Store

    from . import layout_preset_registry
    from .services import preset_service

    preset = layout_preset_registry.get_layout_preset(key)
    if preset is None or not preset.is_ready_template:
        raise Http404(f"قالبِ آماده‌ی «{key}» یافت نشد.")

    preview_uses_merchant_data = request.GET.get("data") == "merchant"
    if preview_uses_merchant_data:
        # The request/host/membership resolver is the sole tenant authority.
        # Query parameters such as store_id/tenant_id/store are deliberately
        # ignored and are never consulted here.
        preview_store = _resolve_store(request)
        candidate_base_version = layout_service.get_existing_draft(preview_store)
        if candidate_base_version is None:
            raise Http404(
                'برای پیش\u200cنمایش با اطلاعات فروشگاه، ابتدا باید یک پیش\u200cنویس موجود باشد.'
            )
    else:
        # Preserve Task-2 Demo behavior exactly: one fixed server-side Store,
        # never selected from request input.
        try:
            preview_store = Store.objects.get(slug=RASTI_MODE_DEMO_STORE_SLUG)
        except Store.DoesNotExist as exc:
            raise Http404(
                "فروشگاهِ نمایشیِ کانونیِ «rasti-mode-demo» در این محیط وجود ندارد — "
                "ابتدا دستورِ مدیریتیِ seed_ready_template_fashion_demo (یا "
                "apply_golden_reference_storefront) را اجرا کنید."
            ) from exc
        # P5-W5C Independent Architect repair — a read-only Preview must
        # never bootstrap a Draft for the Demo Store either, mirroring
        # Merchant mode exactly: fail closed with 404 if the canonical
        # Demo Store exists but has no active Draft yet, rather than
        # silently creating one via get_or_create_draft.
        candidate_base_version = layout_service.get_existing_draft(preview_store)
        if candidate_base_version is None:
            raise Http404(
                "فروشگاهِ نمایشیِ کانونیِ «rasti-mode-demo» هنوز پیش‌نویسِ "
                "فعالی ندارد — ابتدا دستورِ مدیریتیِ "
                "apply_golden_reference_storefront را اجرا کنید."
            )

    candidate = preset_service.resolve_preset_candidate(candidate_base_version, preset)

    page_type = _resolve_page_type(request.GET.get("page"))
    candidate_page = candidate.pages[page_type]
    page_context = _preview_page_context(request, preview_store, page_type)
    items = build_candidate_render_items(
        candidate_page.sections,
        preview_store,
        page_context=page_context,
        global_appearance=candidate.appearance_config,
        store_appearance=candidate.store_appearance,
    )
    rows = build_candidate_container_rows(candidate_page, items)

    header_variant_template = store_appearance_global_renderer_template(
        candidate.store_appearance, "header", candidate.header_config,
    )
    footer_variant_template = store_appearance_global_renderer_template(
        candidate.store_appearance, "footer", candidate.footer_config,
    )
    mobile_bottom_nav_template = store_appearance_global_renderer_template(
        candidate.store_appearance, "bottom_nav", candidate.footer_config,
    )

    # Same transient appearance idiom established in Task 2.  The request
    # attribute is consumed by the existing context processor only and is
    # never persisted.
    request.storefront_appearance_version = _ReadyTemplateCandidateAppearanceVersion(
        candidate.appearance_config,
    )

    # Explicitly override the dashboard ambient context-processor value so
    # global navigation is scoped to the SAME Store as every section resource.
    from apps.catalog.models import Category

    nav_categories = (
        Category.objects.filter(store=preview_store, parent__isnull=True, is_active=True)
        .prefetch_related("children")
        .order_by("order", "name")
    )

    return render(request, "storefront_builder/ready_template_live_preview.html", {
        "store": preview_store,
        "preset": preset,
        "page_type": page_type,
        "header_config": candidate.header_config,
        "footer_config": candidate.footer_config,
        "header_variant_template": header_variant_template,
        "footer_variant_template": footer_variant_template,
        "mobile_bottom_nav_template": mobile_bottom_nav_template,
        "store_appearance": candidate.store_appearance,
        "rows": rows,
        "nav_categories": nav_categories,
        "preview_uses_merchant_data": preview_uses_merchant_data,
    })

@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_apply_layout_preset(request):
    """ARCH-02 — compatibility endpoint for the old gallery's "apply" form (no UI posts here any more).

    The Design Studio gallery is the only official way to apply a template. This endpoint therefore has exactly
    ONE behaviour, the same one the Studio uses: a READY TEMPLATE is applied to the active Draft through the
    canonical ``r4_mutation_service.switch_template_current`` (the very function behind the Studio's switch —
    EXACT replacement of the template-owned design, an archived snapshot first, one history entry; Published is
    never touched). A NON-READY structural preset is refused without any write: the old, separately destructive
    ``apply_preset_with_checkpoint`` view path was a second, incompatible way to change the Draft and has been
    retired from the UI surface (the service itself is unchanged for the importers/tests that use it directly).

    Permissions/tenant-scoping/editor-surface guards (the decorators and ``_resolve_store``) are unchanged."""
    from . import layout_preset_registry
    from .services import preset_service

    store = _resolve_store(request)

    key = request.POST.get("preset_key")
    preset = layout_preset_registry.get_layout_preset(key)
    if preset is None:
        messages.error(request, "پیش‌تنظیمِ انتخاب‌شده یافت نشد")
        return redirect("dashboard:storefront-builder-editor")

    if preset.is_ready_template:
        # The Studio's own switch (EXACT replacement on the SAME active Draft, archived snapshot first), through the
        # canonical R4 mutation boundary: exactly one history entry / one revision increment (no
        # ``@_record_edit_history`` decorator, which would double-record against ``record_change``). Refusals
        # (confirmation required / locked sections) happen before any write.
        layout_service.get_or_create_draft(store, user=request.user)
        try:
            r4_mutation_service.switch_template_current(
                store=store, actor=request.user,
                template_key=preset.key, template_version=preset.version,
                confirm_replace=request.POST.get("confirm_preset_apply") == "1",
                allow_locked=request.POST.get("allow_locked_replace") == "1",
            )
            messages.success(
                request,
                f"قالبِ «{preset.label_fa}» با ساختارِ کاملِ خودش اعمال شد؛ "
                "نسخه‌ی قبلیِ طراحی در تاریخچه‌ی نسخه‌ها برای بازگشت نگه داشته شد",
            )
        except preset_service.InvalidPresetError as exc:
            messages.error(request, str(exc))
        except r4_mutation_service.R4MutationError as exc:
            body = r4_mutation_service.error_response_body(exc)
            messages.error(request, body.get("message") or str(exc))
        return redirect("dashboard:storefront-builder-editor")

    # NON-Ready structural preset — refused: no second Draft-changing path (see docstring). Nothing is written.
    messages.error(
        request,
        "این پیش‌تنظیم یک «قالب آماده» نیست و از این مسیر اعمال نمی‌شود. قالب‌های آماده را از گالریِ Design Studio انتخاب و اعمال کنید.",
    )
    return redirect("dashboard:storefront-builder-r4-editor")


# Acceptance Batch 2 (post-U11) — Issue 3: granular reset-to-Ready-Template-
# baseline merchant controls. Every view here returns to the same editor
# redirect and reports failure via ``messages`` (matching every other
# write view in this module) — never exposes JSON/registry keys/renderer
# paths/internal baseline IDs to the merchant, only Persian sentences.


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_product_search(request, pk):
    """جست‌وجویِ کالا برایِ ویجتِ «کالاهایِ دستی» تنظیماتِ بخشِ محصول —
    از همان ``collection_service.searchable_products`` فازِ B عبور
    می‌کند (نه پیاده‌سازیِ دوباره‌ی جست‌وجو)."""
    from apps.catalog.services import collection_service

    _get_scoped_section(request, pk)
    store = _resolve_store(request)
    query = (request.GET.get("q") or request.GET.get("q_dest_product") or "").strip()
    results = collection_service.searchable_products(store, query=query)[:20] if query else []
    return render(request, "dashboard/storefront_builder/partials/product_section_search_results.html", {
        "results": results, "query": query, "mode": request.GET.get("mode", ""),
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_history(request):
    store = _resolve_store(request)
    versions = layout_service.list_versions(store)
    layout = layout_service.get_or_create_layout(store)
    # The R4-safe restore endpoint needs the client's expected current-state precondition (Draft identity AND revision
    # — a revision-only capture is an ABA hazard), captured at render time; a race is a handled stale-write 409.
    current_draft_id = layout.draft_version_id
    current_draft_revision = (
        layout.draft_version.edit_revision if current_draft_id else None
    )
    return render(request, "dashboard/storefront_builder/history.html", {
        "active_page": "storefront_builder", "versions": versions, "layout": layout,
        "current_draft_id": current_draft_id,
        "current_draft_revision": current_draft_revision,
    })
