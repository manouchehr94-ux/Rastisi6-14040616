"""ویوهای داشبورد سازنده بصری صفحه فروشگاه — همگی پشت
``STOREFRONT_LAYOUT_MANAGE`` (نه ``CONTENT_MANAGE``، طبق تصمیم کاربر)."""

import json
from functools import wraps
from uuid import uuid4

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import global_region_registry, section_registry
from .models import (
    APPEARANCE_CONFIG_DEFAULTS,
    FOOTER_CONFIG_DEFAULTS,
    FOOTER_RESPONSIVE_AWARE_KEYS,
    FOOTER_TOGGLE_FIELDS,
    HEADER_CONFIG_DEFAULTS,
    HEADER_RESPONSIVE_AWARE_KEYS,
    HEADER_TOGGLE_FIELDS,
    StorefrontCell,
    StorefrontContainer,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from .services import (
    appearance_authority_service,
    container_service,
    edit_history_service,
    layout_service,
    row_service,
)
from .services.layout_service import _clone_section_scoped_media
from .services.render_service import (
    build_container_render_items,
    build_page_render_items,
    group_items_into_rows,
    resolve_store_appearance_render_state,
    store_appearance_global_renderer_template,
)


def _resolve_store(request):
    return resolve_store_for_service(request)


def _history_before(draft):
    return edit_history_service.snapshot_draft(draft)


def _history_record(request, draft, before_state, label):
    edit_history_service.record_change(
        draft=draft, actor=request.user, action_label=label, before_state=before_state,
    )


def _record_edit_history(label):
    """Record one successful POST mutation against the current Draft.

    No-op/invalid submissions are filtered by ``record_change`` by comparing
    complete before/after snapshots.  The decorator is deliberately placed
    *inside* permission decorators on write views, so history never becomes a
    bypass around existing tenant/permission checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method != "POST":
                return view_func(request, *args, **kwargs)
            store = _resolve_store(request)
            draft = layout_service.get_or_create_draft(store, user=request.user)
            before_state = _history_before(draft)
            response = view_func(request, *args, **kwargs)
            if StorefrontLayoutVersion.objects.filter(
                pk=draft.pk, status=StorefrontLayoutVersion.Status.DRAFT,
            ).exists():
                _history_record(request, draft, before_state, label)
            return response
        return wrapper
    return decorator


def _resolve_page_type(raw) -> str:
    """Phase 2 (سازنده‌ی تک‌صفحه‌ای): رشته‌یِ خامِ ``page`` (از querystring
    یا فرمِ POST) را به یکی از شش نوعِ معتبرِ ``StorefrontPage.PageType``
    حل می‌کند — مقدارِ غایب/نامعتبر بی‌صدا به ``HOME`` بازمی‌گردد (نه
    خطا) تا لینک/فرمِ قدیمیِ بدونِ این پارامتر (پیش از این چکپوینت)
    دقیقاً همان رفتارِ فعلی را حفظ کند."""
    if raw in StorefrontPage.PageType.values:
        return raw
    return StorefrontPage.PageType.HOME


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    layout = layout_service.get_or_create_layout(store)
    # Phase 2 (سازنده‌ی تک‌صفحه‌ای): صفحه‌یِ در حالِ ویرایش از
    # ``?page=<page_type>`` (وضعیتِ صریح در URL) حل می‌شود — غیاب/نامعتبر
    # بودنِ آن دقیقاً معادلِ رفتارِ قبل از این چکپوینت (همیشه صفحه‌ی
    # اصلی) است.
    page_type = _resolve_page_type(request.GET.get("page"))
    page = draft.get_page(page_type)
    container_service.ensure_page_containers(page)
    sections = page.sections.select_related("cell", "cell__container").order_by("order", "id")
    industry_installation = getattr(store, "industry_installation", None)

    # V3 shell quick-style data.  This is only a read projection of the
    # existing appearance system; palette mutations still go through the
    # established appearance endpoint and Draft/Publish lifecycle.
    from . import appearance_registry

    appearance_config = draft.effective_appearance_config()
    context = {
        "active_page": "storefront_builder",
        "layout": layout,
        "draft": draft,
        "page": page,
        "page_type": page_type,
        "page_types": StorefrontPage.PageType.choices,
        "sections": sections,
        "section_definitions": section_registry.list_definitions(),
        "section_library_groups": section_registry.list_library_groups(page_type=page_type),
        "container_layout_presets": container_service.LAYOUT_PRESETS,
        "containers": page.containers.prefetch_related("cells__section").order_by("order", "id"),
        "versions": layout_service.list_versions(store),
        "industry_installation": industry_installation,
        "edit_history": edit_history_service.history_state(draft),
        "builder_palettes": appearance_registry.list_palettes(),
        "active_palette_slug": appearance_config.get("palette_slug"),
        "builder_resolved_colors": appearance_registry.resolve_colors(appearance_config),
    }
    return render(request, "dashboard/storefront_builder/editor.html", context)


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
    store_appearance = resolve_store_appearance_render_state(draft)
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


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_section_list_partial(request, page_type=None):
    """پارشیال لیست بخش‌ها — برای بازآوری htmx پس از هر تغییر.

    Phase 2: ``page_type`` یا صریحاً توسطِ فراخوانِ Pythonیِ دیگرِ همین
    ماژول پاس داده می‌شود (وقتی آن ویو خودش صفحه‌ی درگیر را از قبل
    می‌داند — مثلاً از رویِ ``section.page``)، یا اگر ``None`` باشد از
    ``page``یِ فرم/querystringِ همینِ درخواست حل می‌شود (وقتی این ویو
    مستقیماً هدفِ یک htmx GET/POST است)."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    if page_type is None:
        page_type = _resolve_page_type(request.POST.get("page") or request.GET.get("page"))
    page = draft.get_page(page_type)
    context = {
        "draft": draft,
        "page_type": page_type,
        "sections": page.sections.select_related("cell", "cell__container").order_by("order", "id"),
        "section_definitions": section_registry.list_definitions(),
    }
    return render(request, "dashboard/storefront_builder/partials/section_list.html", context)


def _get_scoped_container(request, pk):
    store = _resolve_store(request)
    return get_object_or_404(
        StorefrontContainer,
        pk=pk,
        page__version__layout__store=store,
        page__version__status=StorefrontLayoutVersion.Status.DRAFT,
    )


def _get_scoped_cell(request, pk):
    store = _resolve_store(request)
    return get_object_or_404(
        StorefrontCell.objects.select_related("container", "container__page", "section"),
        pk=pk,
        container__page__version__layout__store=store,
        container__page__version__status=StorefrontLayoutVersion.Status.DRAFT,
    )


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_container_state_partial(request, page_type=None):
    """Hidden HTMX state target for real Container/Cell mutations."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    if page_type is None:
        page_type = _resolve_page_type(request.POST.get("page") or request.GET.get("page"))
    page = draft.get_page(page_type)
    container_service.ensure_page_containers(page)
    containers = page.containers.prefetch_related("cells__section", "cells__blocks").order_by("order", "id")
    # Phase 2C: the editor's JS ``placementForSection(sectionId)`` looks up
    # a Section's Cell/Container by querying this hidden state for
    # ``[data-section-id="<id>"]`` — with a real multi-block Cell, EVERY
    # Block placed in it (not just the legacy single one) must be findable
    # this way, or clicking a second/third Block in the Canvas would fail
    # to resolve its Cell/Container. Resolved once here via
    # ``get_cell_blocks`` (the authoritative composition-read path) rather
    # than in the template, to avoid the template issuing its own
    # per-cell composition queries.
    # U11 — N+1 fix: ``containers`` above was just fetched with
    # ``prefetch_related("cells__section", "cells__blocks")``, so every Cell
    # is already fresh; ``blocks_from_prefetched_cell`` trusts that instead
    # of ``get_cell_blocks`` issuing one live query per Cell.
    cell_blocks_by_id = {
        cell.pk: container_service.blocks_from_prefetched_cell(cell)
        for container in containers
        for cell in container.cells.all()
    }
    return render(request, "dashboard/storefront_builder/partials/container_state.html", {
        "page_type": page_type,
        "containers": containers,
        "cell_blocks_by_id": cell_blocks_by_id,
    })


def _container_state_changed_response(request, *, page_type, container_id=None, section_id=None, cell_id=None):
    response = storefront_container_state_partial(request, page_type=page_type)
    payload = {"page": page_type}
    if container_id:
        payload["containerId"] = int(container_id)
    if section_id:
        payload["sectionId"] = int(section_id)
    if cell_id:
        payload["cellId"] = int(cell_id)
    response["HX-Trigger-After-Settle"] = json.dumps({"sfbContainerChanged": payload})
    return response


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("افزودن چیدمان")
def storefront_container_add(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    page_type = _resolve_page_type(request.POST.get("page"))
    page = draft.get_page(page_type)
    layout_key = (request.POST.get("layout_key") or "single").strip()
    try:
        container = container_service.create_empty_container(page, layout_key)
    except container_service.ContainerLayoutError as exc:
        messages.error(request, str(exc))
        return storefront_container_state_partial(request, page_type=page_type)
    messages.success(request, "چیدمان خالی ساخته شد — حالا داخل هر خانه محتوا اضافه کنید")
    response = _container_state_changed_response(
        request, page_type=page_type, container_id=container.pk,
    )
    response["HX-Trigger-After-Settle"] = json.dumps({
        "sfbContainerAdded": {"containerId": container.pk, "page": page_type},
        "sfbContainerChanged": {"containerId": container.pk, "page": page_type},
    })
    return response


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("تنظیم چیدمان")
def storefront_container_settings(request, pk):
    container = _get_scoped_container(request, pk)
    if request.method == "POST":
        if container.is_locked:
            messages.error(request, "این چیدمان قفل است — ابتدا قفل آن را باز کنید")
            return _container_state_changed_response(
                request, page_type=container.page.page_type, container_id=container.pk,
            )
        current_settings = container_service.effective_container_settings(container.settings)
        container.settings = container_service.effective_container_settings({
            "gap": request.POST.get("gap"),
            "mobile_mode": request.POST.get("mobile_mode"),
            # Full-width breakout is intentionally not exposed until the renderer
            # has a family-safe implementation. Preserve the stored value.
            "content_width": current_settings["content_width"],
            "vertical_align": request.POST.get("vertical_align"),
            "height_mode": request.POST.get(
                "height_mode", current_settings["height_mode"]
            ),
            # A Container may own a reusable surface behind multiple Cells.
            # Missing fields preserve the current value for old clients/tests.
            "background_mode": request.POST.get(
                "container_background_mode", current_settings["background_mode"]
            ),
            "background_color": request.POST.get(
                "container_background_color", current_settings["background_color"]
            ),
            "background_pattern": request.POST.get(
                "container_background_pattern", current_settings["background_pattern"]
            ),
        })
        container.save(update_fields=["settings", "updated_at"])
        messages.success(request, "تنظیمات چیدمان ذخیره شد")
        return _container_state_changed_response(
            request, page_type=container.page.page_type, container_id=container.pk,
        )

    cells = list(
        container.cells.select_related("section").prefetch_related("blocks").order_by("order", "id")
    )
    # Phase 2C: occupancy/label for each Cell is resolved HERE via
    # ``get_cell_blocks`` (the single authoritative composition-read path)
    # rather than letting the template branch on ``cell.section_id``/
    # ``cell.section`` directly — a Cell populated only through the new
    # multi-block FK (e.g. after a merge-on-shrink) has a NULL legacy
    # pointer and would otherwise show as incorrectly "empty" here. Passed
    # as a list of ``(cell, blocks)`` pairs so the template issues no
    # additional per-cell composition queries of its own.
    # U11 — N+1 fix: ``cells`` above was just fetched with
    # ``prefetch_related("blocks")``/``select_related("section")``, so
    # ``blocks_from_prefetched_cell`` can trust that instead of
    # ``get_cell_blocks`` issuing one live query per Cell.
    cells_with_blocks = [(cell, container_service.blocks_from_prefetched_cell(cell)) for cell in cells]
    return render(request, "dashboard/storefront_builder/partials/container_settings_form.html", {
        "container": container,
        "cells": cells,
        "cells_with_blocks": cells_with_blocks,
        "settings": container_service.effective_container_settings(container.settings),
        "layout_presets": container_service.LAYOUT_PRESETS,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("تغییر شکل چیدمان")
def storefront_container_layout(request, pk):
    container = _get_scoped_container(request, pk)
    layout_key = (request.POST.get("layout_key") or "").strip()
    try:
        container_service.change_container_layout(container, layout_key)
    except container_service.ContainerLayoutError as exc:
        messages.error(request, str(exc))
        return storefront_container_state_partial(request, page_type=container.page.page_type)
    messages.success(request, "شکل چیدمان تغییر کرد")
    return _container_state_changed_response(
        request, page_type=container.page.page_type, container_id=container.pk,
    )


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("جابه‌جایی چیدمان")
def storefront_container_move(request, pk):
    container = _get_scoped_container(request, pk)
    direction = request.POST.get("direction")
    if direction not in {"up", "down"}:
        return HttpResponseBadRequest("جهت جابه‌جایی نامعتبر است")
    if container.is_locked:
        messages.error(request, "این چیدمان قفل است")
        return storefront_container_state_partial(request, page_type=container.page.page_type)
    siblings = list(container.page.containers.order_by("order", "id"))
    index = next((i for i, item in enumerate(siblings) if item.pk == container.pk), None)
    if index is None:
        raise Http404
    target_index = index - 1 if direction == "up" else index + 1
    if 0 <= target_index < len(siblings):
        other = siblings[target_index]
        if other.is_locked:
            messages.error(request, "چیدمان همسایه قفل است")
            return storefront_container_state_partial(request, page_type=container.page.page_type)
        container.order, other.order = other.order, container.order
        StorefrontContainer.objects.bulk_update([container, other], ["order"])
    return _container_state_changed_response(
        request, page_type=container.page.page_type, container_id=container.pk,
    )


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("حذف چیدمان خالی")
def storefront_container_remove(request, pk):
    container = _get_scoped_container(request, pk)
    page = container.page
    if container.is_locked:
        messages.error(request, "این چیدمان قفل است")
        return storefront_container_state_partial(request, page_type=page.page_type)
    if any(container_service.get_cell_blocks(cell) for cell in container.cells.all()):
        messages.error(request, "برای حذف چیدمان، ابتدا محتوای خانه‌های آن را حذف یا جابه‌جا کنید")
        return storefront_container_state_partial(request, page_type=page.page_type)
    container.delete()
    for index, item in enumerate(page.containers.order_by("order", "id")):
        if item.order != index:
            StorefrontContainer.objects.filter(pk=item.pk).update(order=index)
    messages.success(request, "چیدمان خالی حذف شد")
    return _container_state_changed_response(request, page_type=page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("افزودن محتوا به خانه")
def storefront_cell_add_section(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    page_type = _resolve_page_type(request.POST.get("page"))
    page = draft.get_page(page_type)
    section_key = (request.POST.get("section_key") or "").strip()
    try:
        definition = section_registry.get_definition(section_key)
    except section_registry.UnknownSectionTypeError:
        return HttpResponseBadRequest("نوع بخش نامعتبر است")
    if not section_registry.is_section_allowed_on_page(section_key, page_type):
        return HttpResponseBadRequest("این نوع بخش برای این صفحه مجاز نیست")
    existing_count = page.sections.filter(section_key=section_key).count()
    if definition.max_instances is not None and existing_count >= definition.max_instances:
        messages.error(request, f"«{definition.label_fa}» فقط یک بار قابل افزودن است")
        return storefront_container_state_partial(request, page_type=page_type)

    cell_raw = (request.POST.get("cell_id") or "").strip()
    with transaction.atomic():
        if cell_raw:
            if not cell_raw.isdigit():
                return HttpResponseBadRequest("خانه انتخاب‌شده نامعتبر است")
            cell = _get_scoped_cell(request, int(cell_raw))
            if cell.container.page_id != page.pk:
                return HttpResponseBadRequest("این خانه متعلق به صفحه دیگری است")
            if cell.container.is_locked:
                messages.error(request, "این چیدمان قفل است")
                return storefront_container_state_partial(request, page_type=page_type)
            # V3 Free Layout: a Cell is a real column and may contain 0/1/N
            # Blocks.  The first placement keeps the legacy mirror alive for
            # backward compatibility; subsequent placements use the new FK
            # composition directly and append (or insert) by ``cell_order``.
            existing_blocks = container_service.get_cell_blocks(cell)
        else:
            container = container_service.create_empty_container(page, "single")
            cell = container.cells.get(order=0)
            existing_blocks = []

        at_index_raw = (request.POST.get("at_index") or "").strip()
        at_index = int(at_index_raw) if at_index_raw.isdigit() else None
        last = page.sections.order_by("-order", "-id").first()
        section = StorefrontSection.objects.create(
            page=page,
            section_key=section_key,
            order=(last.order + 1) if last else 0,
            settings=definition.default_settings(),
        )
        if existing_blocks:
            container_service.add_block(cell, section, at_index=at_index)
        else:
            # Keep legacy single-block readers safe while the transitional
            # OneToOne still exists. ``place_section`` also synchronizes the
            # new FK, so the second Block can immediately use ``add_block``.
            container_service.place_section(cell, section)

    messages.success(request, f"«{definition.label_fa}» داخل خانه قرار گرفت")
    response = _container_state_changed_response(
        request, page_type=page_type, container_id=cell.container_id,
        cell_id=cell.pk, section_id=section.pk,
    )
    response["HX-Trigger-After-Settle"] = json.dumps({
        "sfbContentAdded": {
            "containerId": cell.container_id,
            "cellId": cell.pk,
            "sectionId": section.pk,
            "page": page_type,
        },
        "sfbContainerChanged": {"containerId": cell.container_id, "page": page_type},
    })
    return response


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("خالی کردن خانه")
def storefront_cell_clear(request, pk):
    """خالی‌کردنِ کاملِ یک خانه — معنایِ ثابت‌شده‌یِ این endpoint («این
    محتوا برای همیشه حذف شود») بدونِ تغییر باقی می‌ماند؛ فقط قلمروِ آن به
    **همه‌یِ** بلاک‌هایِ واقعیِ این خانه گسترش می‌یابد، نه فقط بلاکِ تکیِ
    قدیمی (Phase 2C).

    از ``container_service.get_cell_blocks`` (تنها منبعِ حقیقتِ ترکیب)
    برایِ خواندنِ فهرستِ کاملِ بلاک‌هایِ این خانه استفاده می‌شود — چه از
    طریقِ OneToOneِ قدیمی، چه از طریقِ FKِ جدیدِ چند-بلاکی (که Phase 2C's
    merge-on-shrink می‌تواند واقعاً بیش از یک بلاک را در یک خانه قرار داده
    باشد، حتی اگر UIِ امروز هنوز مسیرِ افزودنِ بلاکِ دوم را نشان نمی‌دهد).
    عملیات تماماً همه‌یا‌هیچ است: اگر حتیٰ یکی از بلاک‌ها قفل باشد یا نوعِ
    آن ``removable=False`` باشد، کلِ عملیات لغو می‌شود و هیچ بلاکی حذف
    نمی‌شود — دقیقاً همان قاعده‌یِ تک‌بلاکیِ قبلی، فقط تعمیم‌یافته."""
    cell = _get_scoped_cell(request, pk)
    page_type = cell.container.page.page_type
    if cell.container.is_locked:
        messages.error(request, "این چیدمان قفل است")
        return storefront_container_state_partial(request, page_type=page_type)
    blocks = container_service.get_cell_blocks(cell)
    if not blocks:
        return storefront_container_state_partial(request, page_type=page_type)
    if any(block.is_locked for block in blocks):
        messages.error(request, "این محتوا قفل است — ابتدا قفل آن را باز کنید")
        return storefront_container_state_partial(request, page_type=page_type)
    for block in blocks:
        try:
            definition = section_registry.get_definition(block.section_key)
            if not definition.removable:
                messages.error(request, f"«{definition.label_fa}» قابل حذف نیست")
                return storefront_container_state_partial(request, page_type=page_type)
        except section_registry.UnknownSectionTypeError:
            pass
    with transaction.atomic():
        # هر دو رابطه (OneToOneِ قدیمی و FKِ جدید) با حذفِ واقعیِ ردیفِ
        # StorefrontSection به‌طورِ خودکار پاک می‌شوند
        # (StorefrontCell.section از SET_NULL استفاده می‌کند، پس خودِ
        # چیدمان/خانه زنده می‌ماند) — دقیقاً همان مکانیزمِ تک‌بلاکیِ قبلی،
        # فقط برایِ هر بلاک تکرار می‌شود. هیچ Sectionِ بی‌جا/orphan باقی
        # نمی‌ماند چون هر بلاک همینجا واقعاً حذف می‌شود، نه فقط detach.
        for block in blocks:
            block.delete()
    messages.success(request, "خانه خالی شد — می‌توانید محتوای دیگری اضافه کنید")
    return _container_state_changed_response(
        request, page_type=page_type, container_id=cell.container_id, cell_id=cell.pk,
    )


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("افزودن بخش")
def storefront_section_add(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    page_type = _resolve_page_type(request.POST.get("page"))
    page = draft.get_page(page_type)
    section_key = request.POST.get("section_key", "")

    try:
        definition = section_registry.get_definition(section_key)
    except section_registry.UnknownSectionTypeError:
        return HttpResponseBadRequest("نوع بخش نامعتبر است")

    # Phase 5: اجرایِ سمتِ سرورِ allowlistِ نوع‌صفحه — کتابخانه‌ی UI هم
    # صریحاً فیلتر شده (``list_library_groups(page_type=...)``)، اما این
    # چک اینجا تنها نقطه‌ای‌ست که واقعاً رد می‌کند؛ حتی یک POST دستی با
    # section_key معتبر اما نامتناسب با این صفحه باید رد شود.
    if not section_registry.is_section_allowed_on_page(section_key, page_type):
        return HttpResponseBadRequest("این نوع بخش برای این صفحه مجاز نیست")

    existing_count = page.sections.filter(section_key=section_key).count()
    if definition.max_instances is not None and existing_count >= definition.max_instances:
        messages.error(request, f"«{definition.label_fa}» فقط یک بار قابل افزودن است")
        return storefront_section_list_partial(request, page_type=page_type)

    # Phase 2.3 — افزودن در نقطه‌ی دلخواه Canvas. مسیرِ کلیکِ قدیمی
    # هیچ پارامترِ موقعیتی نمی‌فرستد و مثل قبل در انتهای صفحه اضافه می‌کند؛
    # Drag از Library، ``before_section_id`` می‌فرستد تا درج نسبت به یک
    # Section پایدار باشد (نه وابسته به شماره‌ی orderای که ممکن است تغییر کند).
    ordered_sections = list(page.sections.order_by("order", "id"))
    insert_at = len(ordered_sections)
    before_raw = (request.POST.get("before_section_id") or "").strip()
    index_raw = (request.POST.get("insert_at") or "").strip()

    if before_raw:
        if not before_raw.isdigit():
            return HttpResponseBadRequest("محل درج نامعتبر است")
        before_id = int(before_raw)
        insert_at = next((i for i, item in enumerate(ordered_sections) if item.pk == before_id), -1)
        if insert_at < 0:
            return HttpResponseBadRequest("بخش مرجع برای درج پیدا نشد")
    elif index_raw:
        try:
            insert_at = int(index_raw)
        except ValueError:
            return HttpResponseBadRequest("محل درج نامعتبر است")
        if insert_at < 0 or insert_at > len(ordered_sections):
            return HttpResponseBadRequest("محل درج خارج از محدوده است")

    # درج یک Section مستقل در میانه‌ی یک row ترکیبی می‌تواند پیوستگیِ آن row
    # را بشکند. قبل از هر نوشتن، ترتیبِ شبیه‌سازی‌شده با همان validator عمومی
    # موجود بررسی می‌شود؛ در صورت نامعتبر بودن، Draft اصلاً تغییر نمی‌کند.
    preview_section = StorefrontSection(
        page=page, section_key=section_key, order=insert_at,
        settings=definition.default_settings(),
    )
    simulated = list(ordered_sections)
    simulated.insert(insert_at, preview_section)
    try:
        row_service.validate_page_row_layout(simulated)
    except row_service.RowAssignmentError as exc:
        messages.error(request, f"این نقطه برای درج مناسب نیست: {exc}")
        return storefront_section_list_partial(request, page_type=page_type)

    with transaction.atomic():
        # ابتدا در انتها ساخته می‌شود و سپس تمام orderها یک‌بار نرمال می‌شوند؛
        # در schema روی order قید یکتا نداریم، ولی این ترتیب intermediate state
        # را هم ساده و قابل‌فهم نگه می‌دارد.
        new_section = StorefrontSection.objects.create(
            page=page, section_key=section_key, order=len(ordered_sections),
            settings=definition.default_settings(),
        )
        final_order = list(ordered_sections)
        final_order.insert(insert_at, new_section)
        for index, item in enumerate(final_order):
            if item.order != index:
                StorefrontSection.objects.filter(pk=item.pk, page=page).update(order=index)

    # Phase 3.0 foundation: while the legacy Section list is still the active
    # editor, keep the shadow Container/Cell placement in exact sync.
    container_service.rebuild_page_from_legacy_rows(page)

    messages.success(request, f"«{definition.label_fa}» اضافه شد")
    response = storefront_section_list_partial(request, page_type=page_type)
    response["HX-Trigger-After-Swap"] = json.dumps({
        "sfbSectionAdded": {"sectionId": new_section.pk, "insertAt": insert_at},
    })
    return response


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


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("ویرایش تنظیمات بخش")
def storefront_section_settings(request, pk):
    """فرم ویرایش تنظیمات — فقط برای انواعی که واقعاً محتوای قابل‌تنظیم
    دارند (``has_settings_form``)؛ هیچ فیلد JSON/HTML خام به تاجر نشان
    داده نمی‌شود، فقط فیلدهای فرم واقعی (عنوان، متن غنی از طریق CKEditor
    موجود، آدرس تصویر)."""
    section = _get_scoped_section(request, pk)
    try:
        definition = section_registry.get_definition(section.section_key)
    except section_registry.UnknownSectionTypeError:
        raise Http404
    if not definition.has_settings_form:
        raise Http404

    field_errors = {}
    if request.method == "POST":
        if section.section_key == "product_section":
            raw = {
                "data_source": request.POST.get("data_source", ""),
                "source_id": request.POST.get("source_id") or None,
                "product_ids": request.POST.getlist("product_ids"),
                "item_limit": request.POST.get("item_limit", ""),
                "display_mode": request.POST.get("display_mode", ""),
                "show_view_all": request.POST.get("show_view_all") == "on",
                "title": request.POST.get("title", ""),
                "subtitle": request.POST.get("subtitle", ""),
                "carousel_autoplay": request.POST.get("carousel_autoplay") == "on",
                "carousel_interval_ms": request.POST.get("carousel_interval_ms", "3500"),
                "carousel_show_arrows": request.POST.get("carousel_show_arrows") == "on",
                "header_position": request.POST.get("header_position", "above"),
            }
        elif section.section_key == "image_text":
            raw = {
                "title": request.POST.get("title", ""),
                "body_html": request.POST.get("body_html", ""),
                "image_url": request.POST.get("image_url", ""),
                "image_position": request.POST.get("image_position", "right"),
            }
        elif section.section_key == "rich_text":
            raw = {"body_html": request.POST.get("body_html", "")}
        elif section.section_key in ("hero_banner", "image_slider"):
            raw = {
                "autoplay": request.POST.get("autoplay") == "on",
                "interval_ms": request.POST.get("interval_ms", ""),
                "show_arrows": request.POST.get("show_arrows") == "on",
                "show_dots": request.POST.get("show_dots") == "on",
                "loop": request.POST.get("loop") == "on",
                "text_position": request.POST.get("text_position", "end"),
                # U9 — section component variant swap (U4's registered
                # hero_banner variants). The form only shows this control
                # for hero_banner, but reading it here for image_slider too
                # is harmless: image_slider has no registered variants, so
                # the key is simply inert/unused at render time.
                "hero_style": request.POST.get("hero_style", "overlay"),
            }
        elif section.section_key == "category_grid":
            raw = {
                "title": request.POST.get("title", ""),
                "display_mode": request.POST.get("display_mode", ""),
                "category_ids": request.POST.getlist("category_ids"),
                "item_limit": request.POST.get("item_limit", 12),
            }
        elif section.section_key == "brand_carousel":
            raw = {
                "title": request.POST.get("title", ""),
                "display_mode": request.POST.get("display_mode", ""),
                "show_view_all": request.POST.get("show_view_all") == "on",
                "brand_ids": request.POST.getlist("brand_ids"),
            }
        elif section.section_key == "collection_tiles":
            raw = {
                "title": request.POST.get("title", ""),
                "collection_ids": request.POST.getlist("collection_ids"),
                # U9 — section component variant swap (U4's registered
                # collection_tiles variants).
                "tile_style": request.POST.get("tile_style", "grid"),
            }
        elif section.section_key == "quick_links":
            raw = {
                "title": request.POST.get("title", ""),
                "menu_id": request.POST.get("menu_id") or None,
            }
        elif section.section_key == "faq":
            questions = request.POST.getlist("question")
            answers = request.POST.getlist("answer")
            raw = {
                "title": request.POST.get("title", ""),
                "items": [{"question": q, "answer": a} for q, a in zip(questions, answers)],
            }
        elif section.section_key == "testimonials":
            names = request.POST.getlist("t_name")
            quotes = request.POST.getlist("t_quote")
            roles = request.POST.getlist("t_role")
            raw = {
                "title": request.POST.get("title", ""),
                "items": [
                    {"name": n, "quote": q, "role": r}
                    for n, q, r in zip(names, quotes, roles)
                ],
            }
        elif section.section_key == "video_section":
            raw = {
                "title": request.POST.get("title", ""),
                "video_url": request.POST.get("video_url", ""),
                "caption": request.POST.get("caption", ""),
            }
        elif section.section_key == "newsletter":
            raw = {
                "title": request.POST.get("title", ""),
                "subtitle": request.POST.get("subtitle", ""),
                "button_label": request.POST.get("button_label", ""),
            }
        else:
            # انواعی که هیچ فیلدِ اختصاصیِ خودشان را ندارند (فازِ D) —
            # تنها چیزی که این فرم برایشان دارد بلوکِ responsive است.
            raw = {}
        raw["responsive"] = _extract_responsive_raw(request, definition)
        # Reference-fidelity/editability: Background and spacing are generic
        # visual blocks, not section-specific content.  Preserve them for
        # legacy POST callers that do not send the new controls, and accept
        # explicit merchant changes when the section supports backgrounds.
        if definition.supports_capability("background"):
            raw["background"] = _extract_background_raw(request, section)
        if definition.supports_capability("spacing"):
            raw["spacing"] = (section.settings or {}).get("spacing") or {}
        if definition.supports_capability("destination"):
            raw["destination"] = _extract_destination_raw(request)
        if definition.supports_capability("motion"):
            raw["motion"] = {"style": request.POST.get("motion_style", "none")}
        if definition.supports_capability("card"):
            raw["card"] = _extract_card_raw(request)
        if definition.supports_capability("layout_width"):
            raw["layout"] = _extract_layout_raw(request)
        try:
            cleaned = definition.validate_settings(raw)
            _validate_universal_selection_ownership(request, section.section_key, cleaned)
            if definition.supports_capability("background"):
                _validate_background_asset_ownership(request, cleaned.get("background"))
            section.settings = cleaned
            section.save(update_fields=["settings", "updated_at"])
            messages.success(request, "تنظیمات ذخیره شد")
            editor_url = reverse("dashboard:storefront-builder-editor")
            return redirect(f"{editor_url}?page={section.page.page_type}")
        except ValueError as exc:
            field_errors["general"] = str(exc)

    row_members = []
    current_row_mode = "full"
    if section.row_key:
        row_members = list(
            section.page.sections.filter(row_key=section.row_key).order_by("order", "id")
        )
        current_row_mode = {
            (6, 6): "half",
            (3, 9): "quarter_left",
            (9, 3): "quarter_right",
            (4, 8): "third_left",
            (8, 4): "third_right",
            (4, 4, 4): "thirds",
            (3, 3, 3, 3): "quarters",
        }.get(tuple(item.row_span for item in row_members), "custom")

    context = {
        "section": section, "definition": definition, "field_errors": field_errors,
        "row_members": row_members,
        "row_total_span": sum(item.row_span for item in row_members) if row_members else 12,
        "current_row_mode": current_row_mode,
        "row_has_locked": any(item.is_locked for item in row_members),
        # Phase 2C: a Section placed only through the new multi-block FK
        # (``section.cell``) has no legacy ``placement_cell`` reverse
        # relation at all — the new FK is checked FIRST (``select_related``
        # to avoid a second query for the template's own
        # ``placement_cell.container`` accesses) so the Inspector still
        # correctly identifies which Cell/Container this Section belongs
        # to; the legacy reverse-OneToOne lookup remains only as the
        # fallback for a Section whose placement still lives solely
        # through the old relationship.
        "placement_cell": (
            StorefrontCell.objects.select_related("container").filter(pk=section.cell_id).first()
            if section.cell_id
            else StorefrontCell.objects.filter(section=section).select_related("container").first()
        ),
        # فقط انواعی که واقعاً چیدمانِ پارامتری دارند کنترلِ «تعدادِ
        # ستون‌ها» را می‌بینند (COLUMN_VISUAL_SECTION_KEYS، نه
        # COLUMN_AWARE_SECTION_KEYS) — طبقِ فیکسِ فازِ D؛ به مستندسازیِ
        # section_registry.py مراجعه شود.
        "supports_columns": definition.supports_capability("columns_visual"),
        "supports_card": definition.supports_capability("card"),
        "supports_height": definition.supports_capability("layout_height"),
        "supports_background": definition.supports_capability("background"),
    }
    if section.section_key == "product_section":
        context.update(_product_section_picker_context(request, section))
    if section.section_key == "category_grid":
        context.update(_category_grid_picker_context(request, section))
    if section.section_key == "brand_carousel":
        context.update(_brand_carousel_picker_context(request, section))
    if section.section_key == "collection_tiles":
        context.update(_collection_tiles_picker_context(request, section))
    context.update(_universal_selection_context(section, context))
    if section.section_key == "quick_links":
        context.update(_quick_links_picker_context(request, section))
    if definition.supports_capability("destination"):
        context.update(_destination_picker_context(request, section))
    if definition.supports_capability("background"):
        context.update(_background_picker_context(request, section))
    return render(request, "dashboard/storefront_builder/partials/section_settings_form.html", context)



def _universal_selection_context(section, context) -> dict:
    """Normalize the four existing list pickers for one shared merchant UI."""
    specs = {
        "product_section": ("product", "product_ids", 60, "initial_manual_products", None, "کالا", "جستجوی نام یا کد کالا...", "منبع خودکار انتخاب‌شده در پایین استفاده می‌شود."),
        "category_grid": ("category", "category_ids", 12, "initial_selected_categories", "all_categories", "دسته‌بندی", "جستجوی دسته‌بندی...", "دسته‌های اصلی فعال فروشگاه به‌صورت خودکار نمایش داده می‌شوند."),
        "brand_carousel": ("brand", "brand_ids", 24, "initial_selected_brands", "all_brands", "برند", "جستجوی برند...", "همه برندهای فعال فروشگاه به‌صورت خودکار نمایش داده می‌شوند."),
        "collection_tiles": ("collection", "collection_ids", 12, "initial_selected_collections", "all_collections", "کالکشن", "جستجوی کالکشن...", "همه کالکشن‌های فعال فروشگاه به‌صورت خودکار نمایش داده می‌شوند."),
    }
    spec = specs.get(section.section_key)
    if spec is None:
        return {}
    kind, input_name, max_items, selected_key, choices_key, entity_label, placeholder, auto_text = spec
    settings = section.settings or {}
    if section.section_key == "product_section":
        mode = "manual" if settings.get("data_source") == "manual" else "automatic"
    else:
        mode = "manual" if settings.get(input_name) else "automatic"
    return {
        "selection_kind": kind,
        "selection_mode": mode,
        "selection_input_name": input_name,
        "selection_max_items": max_items,
        "selected_items": context.get(selected_key, []),
        "selection_choices": context.get(choices_key, []) if choices_key else [],
        "selection_entity_label": entity_label,
        "selection_search_placeholder": placeholder,
        "selection_auto_text": auto_text,
    }


def _validate_universal_selection_ownership(request, section_key, cleaned) -> None:
    """Reject foreign/nonexistent explicit IDs before they are persisted."""
    from apps.catalog.models import Brand, Category, MerchantCollection, Product

    specs = {
        "product_section": (Product, "product_ids"),
        "category_grid": (Category, "category_ids"),
        "brand_carousel": (Brand, "brand_ids"),
        "collection_tiles": (MerchantCollection, "collection_ids"),
    }
    spec = specs.get(section_key)
    if spec is None:
        return
    model, field = spec
    ids = cleaned.get(field) or []
    if not ids:
        return
    store = _resolve_store(request)
    owned = set(model.objects.filter(store=store, pk__in=ids).values_list("pk", flat=True))
    if any(item_id not in owned for item_id in ids):
        raise ValueError("یک یا چند مورد انتخاب‌شده متعلق به این فروشگاه نیست")

def _extract_background_raw(request, section) -> dict:
    """Read the shared merchant-facing background control.

    Old clients/tests that do not submit ``background_mode`` must preserve the
    existing JSON block instead of silently resetting a reference-preset rail
    back to the theme background.
    """
    if "background_mode" not in request.POST:
        return (section.settings or {}).get("background") or {}

    mode = (request.POST.get("background_mode") or "theme").strip()
    return {
        "mode": mode,
        "color": (request.POST.get("background_color") or "").strip(),
        "pattern_slug": (request.POST.get("background_pattern_slug") or "").strip(),
        "palette_role": (request.POST.get("background_palette_role") or "").strip(),
        "media_asset_id": request.POST.get("background_media_asset_id") or None,
    }


def _validate_background_asset_ownership(request, background: dict | None) -> None:
    """Fail closed if a tampered POST points at another Store's MediaAsset."""
    background = background or {}
    if background.get("mode") != "image" or not background.get("media_asset_id"):
        return
    from apps.content.models import MediaAsset

    store = _resolve_store(request)
    if not MediaAsset.objects.filter(store=store, pk=background["media_asset_id"]).exists():
        raise ValueError("تصویر پس‌زمینه‌ی انتخاب‌شده متعلق به این فروشگاه نیست")


def _background_picker_context(request, section) -> dict:
    from apps.content.models import MediaAsset

    store = _resolve_store(request)
    return {
        "background_patterns": section_registry.PATTERN_REGISTRY,
        "background_media_assets": MediaAsset.objects.filter(store=store).order_by("-created_at", "-id")[:60],
    }


def _category_grid_picker_context(request, section):
    from apps.catalog.models import Category

    store = _resolve_store(request)
    category_ids = (section.settings or {}).get("category_ids") or []
    categories_by_id = {c.pk: c for c in Category.objects.filter(store=store, pk__in=category_ids)}
    return {
        "all_categories": Category.objects.filter(store=store, is_active=True).order_by("name"),
        "initial_selected_categories": [
            {"id": cid, "name": categories_by_id[cid].name} for cid in category_ids if cid in categories_by_id
        ],
    }


def _brand_carousel_picker_context(request, section):
    from apps.catalog.models import Brand

    store = _resolve_store(request)
    brand_ids = (section.settings or {}).get("brand_ids") or []
    brands_by_id = {b.pk: b for b in Brand.objects.filter(store=store, pk__in=brand_ids)}
    return {
        "all_brands": Brand.objects.filter(store=store, is_active=True).order_by("name"),
        "initial_selected_brands": [
            {"id": bid, "name": brands_by_id[bid].name} for bid in brand_ids if bid in brands_by_id
        ],
    }


def _collection_tiles_picker_context(request, section):
    from apps.catalog.models import MerchantCollection

    store = _resolve_store(request)
    collection_ids = (section.settings or {}).get("collection_ids") or []
    collections_by_id = {c.pk: c for c in MerchantCollection.objects.filter(store=store, pk__in=collection_ids)}
    return {
        "all_collections": MerchantCollection.objects.filter(store=store, is_active=True).order_by("name"),
        "initial_selected_collections": [
            {"id": cid, "name": collections_by_id[cid].name} for cid in collection_ids if cid in collections_by_id
        ],
    }


def _quick_links_picker_context(request, section):
    from apps.content.models import Menu

    store = _resolve_store(request)
    return {"all_menus": Menu.objects.filter(store=store, is_active=True).order_by("title")}


def _extract_destination_raw(request) -> dict:
    """بلوکِ خامِ «لینک این بخش» را از POST می‌خواند — یک بار نوشته شده،
    توسطِ هر نوع سکشنِ عضوِ ``DESTINATION_AWARE_SECTION_KEYS`` استفاده
    می‌شود. فرمِ ادیتور یک ``<select name="destination_type">`` مشترک دارد
    و بسته به مقدارش، یکی از چهار فیلدِ ``destination_*_id`` را پر می‌کند —
    اینجا همان یکیِ متناظر با نوعِ انتخاب‌شده به ``destination_id`` عمومی
    نگاشت می‌شود."""
    dtype = request.POST.get("destination_type", "none")
    id_field_by_type = {
        "category": "destination_category_id",
        "brand": "destination_brand_id",
        "collection": "destination_collection_id",
        "product": "destination_product_id",
    }
    destination_id = None
    if dtype in id_field_by_type:
        destination_id = request.POST.get(id_field_by_type[dtype]) or None
    return {
        "destination_type": dtype,
        "destination_id": destination_id,
        "destination_external_url": request.POST.get("destination_external_url", ""),
        "open_in_new_tab": request.POST.get("open_in_new_tab") == "on",
    }


def _destination_picker_context(request, section) -> dict:
    """کالکشن‌ها/دسته‌بندی‌ها/برندهایِ همین Store برایِ کشوهای انتخابِ
    مقصدِ بلوکِ ``destination`` + نامِ محصولِ فعلاً انتخاب‌شده (اگر
    destination_type فعلی «محصول» باشد) برایِ نمایشِ اولیه — دقیقاً همان
    الگویِ ``_product_section_picker_context`` بالا، عمداً جداگانه چون
    قراردادِ ``destination`` عمومی‌تر (برایِ هر نوع section) است."""
    from apps.catalog.models import Brand, Category, MerchantCollection, Product

    store = _resolve_store(request)
    dest = (section.settings or {}).get("destination") or {}
    product_name = ""
    if dest.get("destination_type") == "product" and dest.get("destination_id"):
        product = Product.objects.filter(store=store, pk=dest["destination_id"]).first()
        product_name = product.name if product else ""
    return {
        "collections": MerchantCollection.objects.filter(store=store).order_by("name"),
        "categories": Category.objects.filter(store=store).order_by("name"),
        "brands": Brand.objects.filter(store=store).order_by("name"),
        "destination_product_name": product_name,
    }


def _extract_responsive_raw(request, definition) -> dict:
    """بلوکِ خامِ «تنظیماتِ نمایش در دستگاه‌ها» را از POST می‌خواند —
    یک بار نوشته شده، توسطِ فرمِ تنظیماتِ هر ۱۷ نوعِ section استفاده
    می‌شود (بخشِ ۶ مشخصات: «Use one shared helper where possible»).
    مرچنت در قالبِ مثبت («نمایش در…») تیک می‌زند؛ اینجا به مدلِ
    hide_on_* (منفی، قراردادِ ذخیره‌سازی) تبدیل می‌شود."""
    raw = {
        "hide_on_desktop": request.POST.get("show_on_desktop") != "on",
        "hide_on_tablet": request.POST.get("show_on_tablet") != "on",
        "hide_on_mobile": request.POST.get("show_on_mobile") != "on",
    }
    # عمداً روی capabilityِ عمومی‌ترِ "columns" (نه "columns_visual"ِ
    # محدودترِ بالا) — قراردادِ ذخیره‌سازی باید عمومی/آینده‌نگر بماند؛
    # برایِ چهار نوعی که فعلاً کنترلِ UI ندارند، این فیلدها صرفاً در
    # POST حاضر نیستند و validate_responsive_settings به‌طورِ امن
    # پیش‌فرض را جایگزین می‌کند.
    if definition.supports_capability("columns"):
        raw["desktop_columns"] = request.POST.get("desktop_columns")
        raw["tablet_columns"] = request.POST.get("tablet_columns")
        raw["mobile_columns"] = request.POST.get("mobile_columns")
    return raw


def _extract_card_raw(request) -> dict:
    """Phase 8 P0-2 — بلوکِ خامِ «ظاهرِ کارتِ محصول» را از POST می‌خواند،
    فقط برایِ ``CARD_AWARE_SECTION_KEYS``. دقیقاً همان الگویِ
    ``_extract_responsive_raw``: تیک‌های مثبت («نمایشِ …») مستقیم به
    کلیدهایِ ``show_*`` تبدیل می‌شوند (بدونِ وارونگیِ منفی، چون خودِ
    ``validate_card_settings`` هم مثبت است)."""
    return {
        "show_brand": request.POST.get("card_show_brand") == "on",
        "show_price": request.POST.get("card_show_price") == "on",
        "show_badge": request.POST.get("card_show_badge") == "on",
        "show_wishlist": request.POST.get("card_show_wishlist") == "on",
        "show_quick_add": request.POST.get("card_show_quick_add") == "on",
        "show_rating": request.POST.get("card_show_rating") == "on",
        "card_border": request.POST.get("card_border") == "on",
        "image_ratio": request.POST.get("card_image_ratio", "square"),
        "quick_add_reveal": request.POST.get("card_quick_add_reveal", "hover_slide"),
        "card_style": request.POST.get("card_style", "standard"),
    }


def _extract_layout_raw(request) -> dict:
    """Phase 8 P0-5 — بلوکِ خامِ «اندازه‌ی بخش» (عرض/ارتفاع) را از POST
    می‌خواند، فقط برایِ ``LAYOUT_WIDTH_AWARE_SECTION_KEYS``. کلیدِ
    ``height`` حتی برایِ انواعی که ارتفاع پشتیبانی نمی‌شود بی‌ضرر
    فرستاده می‌شود — ``validate_layout_settings`` آن را بر اساسِ
    ``supports_height`` نادیده می‌گیرد."""
    return {
        "content_width": request.POST.get("layout_content_width", "standard"),
        "height": request.POST.get("layout_height", "standard"),
    }


def _product_section_picker_context(request, section):
    """کالکشن‌ها/دسته‌بندی‌ها/برندهایِ همین Store (برایِ کشوهای انتخابِ
    منبع) + کالاهایِ دستیِ فعلاً انتخاب‌شده (برایِ نمایشِ اولیه‌یِ
    چیپ‌هایِ ادیتور «کالاهایِ دستی» — نه بازسازیِ آن‌ها از صفر در JS)."""
    from apps.catalog.models import Brand, Category, MerchantCollection, Product

    store = _resolve_store(request)
    product_ids = section.settings.get("product_ids") or []
    products_by_id = {p.pk: p for p in Product.objects.filter(store=store, pk__in=product_ids)}
    return {
        "collections": MerchantCollection.objects.filter(store=store).order_by("name"),
        "categories": Category.objects.filter(store=store).order_by("name"),
        "brands": Brand.objects.filter(store=store).order_by("name"),
        "initial_manual_products": [
            {"id": pid, "name": products_by_id[pid].name} for pid in product_ids if pid in products_by_id
        ],
    }


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


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("تغییر چیدمان ردیف")
def storefront_section_row_layout(request, pk):
    """Apply or replace one safe merchant-facing row preset.

    Phase 2.9 keeps flat page order as the single ordering source, but removes
    the old two-step "full width, then choose a new preset" requirement.

    For an existing composite row, any member may be the selected section:
    the whole current row is treated as the editing unit.  Shrinking a row
    releases trailing members back to standalone full-width sections; growing a
    row may consume only the immediate following standalone siblings.  Members
    are never silently stolen from another row, locked sections fail closed,
    and the final simulated page is validated before one atomic bulk update.
    """
    section = _get_scoped_section(request, pk)
    page = section.page
    mode = (request.POST.get("layout_mode") or "").strip()

    presets = {
        "half": (6, 6),
        "quarter_left": (3, 9),
        "quarter_right": (9, 3),
        "third_left": (4, 8),
        "third_right": (8, 4),
        "thirds": (4, 4, 4),
        "quarters": (3, 3, 3, 3),
    }
    preset_labels = {
        "half": "نصف + نصف",
        "quarter_left": "یک‌چهارم + سه‌چهارم",
        "quarter_right": "سه‌چهارم + یک‌چهارم",
        "third_left": "یک‌سوم + دو‌سوم",
        "third_right": "دو‌سوم + یک‌سوم",
        "thirds": "سه‌ستونه",
        "quarters": "چهارستونه",
    }

    if mode == "full":
        if not section.row_key:
            return storefront_section_list_partial(request, page_type=page.page_type)

        members = list(
            page.sections.filter(row_key=section.row_key).order_by("order", "id")
        )
        if any(member.is_locked for member in members):
            messages.error(
                request,
                "برای تمام‌عرض کردن ردیف، ابتدا قفل همه اعضای آن را باز کنید",
            )
            return storefront_section_list_partial(request, page_type=page.page_type)

        for member in members:
            member.row_key = ""
            member.row_span = 12

        with transaction.atomic():
            StorefrontSection.objects.bulk_update(
                members, ["row_key", "row_span"]
            )
        container_service.rebuild_page_from_legacy_rows(page)

        messages.success(request, "بخش‌های این ردیف دوباره تمام‌عرض شدند")
        response = storefront_section_list_partial(
            request, page_type=page.page_type
        )
        response["HX-Trigger-After-Settle"] = json.dumps(
            {"sfbRowLayoutChanged": {"sectionId": section.pk}}
        )
        return response

    spans = presets.get(mode)
    if spans is None:
        return HttpResponseBadRequest("چیدمان ردیف نامعتبر است")

    siblings = list(page.sections.order_by("order", "id"))
    selected_index = next(
        (index for index, item in enumerate(siblings) if item.pk == section.pk),
        None,
    )
    if selected_index is None:
        raise Http404

    # Existing row: edit the row itself, regardless of which member was clicked.
    if section.row_key:
        current_row_key = section.row_key
        row_indices = [
            index for index, item in enumerate(siblings)
            if item.row_key == current_row_key
        ]
        if not row_indices:
            raise Http404

        start = row_indices[0]
        if row_indices != list(range(start, start + len(row_indices))):
            messages.error(
                request,
                "چیدمان فعلی ردیف نامعتبر است و تا اصلاح آن تغییر داده نمی‌شود",
            )
            return storefront_section_list_partial(
                request, page_type=page.page_type
            )

        current_members = [siblings[index] for index in row_indices]
        if any(member.is_locked for member in current_members):
            messages.error(
                request,
                "یکی از اعضای این ردیف قفل است — ابتدا قفل آن را باز کنید",
            )
            return storefront_section_list_partial(
                request, page_type=page.page_type
            )

        target_count = len(spans)
        current_count = len(current_members)
        extras = []

        if target_count > current_count:
            extras = siblings[
                start + current_count : start + target_count
            ]
            if len(extras) != target_count - current_count:
                messages.error(
                    request,
                    "برای این چیدمان، بخش کافی بعد از ردیف فعلی وجود ندارد",
                )
                return storefront_section_list_partial(
                    request, page_type=page.page_type
                )
            if any(item.row_key for item in extras):
                messages.error(
                    request,
                    "برای بزرگ‌تر کردن این ردیف، بخش بعدی باید مستقل باشد",
                )
                return storefront_section_list_partial(
                    request, page_type=page.page_type
                )
            if any(item.is_locked for item in extras):
                messages.error(
                    request,
                    "بخش قفل‌شده را نمی‌توان به این ردیف اضافه کرد",
                )
                return storefront_section_list_partial(
                    request, page_type=page.page_type
                )

        if (
            target_count == current_count
            and tuple(member.row_span for member in current_members) == spans
        ):
            messages.info(request, "این چینش همین حالا فعال است")
            return storefront_section_list_partial(
                request, page_type=page.page_type
            )

        target_members = (current_members + extras)[:target_count]
        released_members = (
            current_members[target_count:] if target_count < current_count else []
        )

        for member in released_members:
            member.row_key = ""
            member.row_span = 12

        for member, span in zip(target_members, spans):
            member.row_key = current_row_key
            member.row_span = span

        try:
            row_service.validate_page_row_layout(siblings)
        except row_service.RowAssignmentError as exc:
            messages.error(request, str(exc))
            return storefront_section_list_partial(
                request, page_type=page.page_type
            )

        affected_by_pk = {
            member.pk: member
            for member in [*current_members, *extras]
        }
        with transaction.atomic():
            StorefrontSection.objects.bulk_update(
                list(affected_by_pk.values()),
                ["row_key", "row_span"],
            )
        container_service.rebuild_page_from_legacy_rows(page)

        messages.success(
            request,
            f"چینش ردیف به «{preset_labels[mode]}» تغییر کرد",
        )
        response = storefront_section_list_partial(
            request, page_type=page.page_type
        )
        response["HX-Trigger-After-Settle"] = json.dumps(
            {"sfbRowLayoutChanged": {"sectionId": section.pk}}
        )
        return response

    # Standalone section: preserve the original safe grouping semantics.
    start = selected_index
    members = siblings[start : start + len(spans)]
    if len(members) != len(spans):
        messages.error(
            request,
            "برای این چیدمان، بخش کافی بعد از بخش انتخاب‌شده وجود ندارد",
        )
        return storefront_section_list_partial(
            request, page_type=page.page_type
        )
    if any(member.row_key for member in members):
        messages.error(
            request,
            "یکی از بخش‌های این محدوده عضو ردیف دیگری است",
        )
        return storefront_section_list_partial(
            request, page_type=page.page_type
        )
    if any(member.is_locked for member in members):
        messages.error(
            request,
            "بخش قفل‌شده را نمی‌توان وارد چیدمان ردیفی کرد",
        )
        return storefront_section_list_partial(
            request, page_type=page.page_type
        )

    row_key = f"row-{uuid4().hex[:12]}"
    for member, span in zip(members, spans):
        member.row_key = row_key
        member.row_span = span

    try:
        row_service.validate_page_row_layout(siblings)
    except row_service.RowAssignmentError as exc:
        messages.error(request, str(exc))
        return storefront_section_list_partial(
            request, page_type=page.page_type
        )

    with transaction.atomic():
        StorefrontSection.objects.bulk_update(
            members, ["row_key", "row_span"]
        )
    container_service.rebuild_page_from_legacy_rows(page)

    messages.success(request, f"چینش «{preset_labels[mode]}» اعمال شد")
    response = storefront_section_list_partial(
        request, page_type=page.page_type
    )
    response["HX-Trigger-After-Settle"] = json.dumps(
        {"sfbRowLayoutChanged": {"sectionId": section.pk}}
    )
    return response


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("حذف بخش")
def storefront_section_remove(request, pk):
    section = _get_scoped_section(request, pk)
    page = section.page
    page_type = page.page_type
    # Phase 1 (spec §37 — Lock): «It cannot be deleted» — چک می‌شود پیش از
    # چکِ removable نوعِ section (اگر هر دو نقض شده باشند، تاجر پیامِ
    # قفل‌بودن را می‌بیند، چون آن یک تصمیمِ per-instance و آگاهانه‌تر است).
    if section.is_locked:
        messages.error(request, "این بخش قفل است — ابتدا قفل آن را باز کنید")
        return storefront_section_list_partial(request, page_type=page_type)
    # Phase 1 correction: حذفِ یک عضوِ ردیف، آن ردیف را نامعتبر می‌کند
    # (کمتر از حداقلِ عضو یا مجموعِ عرضِ ناقص) — باید صریحاً رد شود، نه
    # اینکه یک ردیفِ شکسته در دیتابیس باقی بماند.
    if row_service.is_row_member(section):
        messages.error(
            request,
            "این بخش عضوِ یک ردیفِ ترکیبی است — ابتدا آن را از ردیف خارج کنید",
        )
        return storefront_section_list_partial(request, page_type=page_type)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.removable:
            messages.error(request, f"«{definition.label_fa}» قابل حذف نیست")
            return storefront_section_list_partial(request, page_type=page_type)
    except section_registry.UnknownSectionTypeError:
        pass
    section.delete()
    container_service.rebuild_page_from_legacy_rows(page)
    messages.success(request, "بخش حذف شد")
    return storefront_section_list_partial(request, page_type=page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("نمایش/مخفی کردن بخش")
def storefront_section_toggle(request, pk):
    section = _get_scoped_section(request, pk)
    section.is_active = not section.is_active
    section.save(update_fields=["is_active", "updated_at"])
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("جمع/باز کردن بخش")
def storefront_section_collapse_toggle(request, pk):
    """جمع‌کردن/بازکردن کارت یک بخش داخل ادیتور — فقط UI، مستقل از
    is_active (A3). ``_get_scoped_section`` تضمین می‌کند فقط بخش‌های
    همین فروشگاه و فقط در نسخه Draft قابل تغییرند."""
    section = _get_scoped_section(request, pk)
    section.collapsed_in_editor = not section.collapsed_in_editor
    section.save(update_fields=["collapsed_in_editor", "updated_at"])
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("قفل/بازکردن بخش")
def storefront_section_lock_toggle(request, pk):
    """قفل/بازکردنِ یک بخش — Phase 1 (spec §37). دقیقاً همان الگویِ
    ``storefront_section_collapse_toggle``؛ خودِ اثرِ قفل‌بودن (منعِ حذف/
    جابه‌جایی) در ``storefront_section_remove``/``storefront_section_move``
    اعمال می‌شود، نه اینجا — این view فقط پرچم را toggle می‌کند."""
    section = _get_scoped_section(request, pk)
    section.is_locked = not section.is_locked
    section.save(update_fields=["is_locked", "updated_at"])
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("تکرار بخش")
def storefront_section_duplicate(request, pk):
    """تکرارِ یک بخش — یک بخشِ منطقیِ **جدید** می‌سازد.

    Phase 0.5 (تصمیمِ مالک ۳/۹): برخلافِ کلونِ نسخه (که ``stable_id`` را
    حفظ می‌کند چون همان بخشِ منطقی است)، تکرار عمداً یک ``stable_id`` تازه
    می‌گیرد (پیش‌فرضِ فیلد — ``uuid.uuid4()``، نه چیزی که اینجا صریحاً
    ست شود) — این یک بخشِ منطقیِ کاملاً جدید و مستقل است.

    اگر بخشِ منبع رسانه‌یِ section-scoped (HeroSlide/PromotionalBanner/
    StoryRailItem) داشته باشد، آن هم تکرار می‌شود — Placementهایِ جدید به
    **همان** ``MediaAsset``هایِ منبع اشاره می‌کنند (بدونِ کپیِ بایتِ فایل)،
    اما تنظیماتِ خودشان (عنوان/دکمه/مقصد/ترتیب) به‌طورِ کاملاً مستقل کپی
    می‌شود — ویرایشِ بعدیِ Placementِ تکرارشده هرگز روی Placementِ منبع
    اثر نمی‌گذارد (همان الگویِ استقلالِ ``settings`` که از قبل برایِ خودِ
    section وجود داشت)."""
    section = _get_scoped_section(request, pk)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.duplicable:
            messages.error(request, f"«{definition.label_fa}» قابل تکرار نیست")
            return storefront_section_list_partial(request, page_type=section.page.page_type)
    except section_registry.UnknownSectionTypeError:
        pass
    # Phase 1A: تکرار همیشه رویِ **همان صفحه‌ای** که section بهش تعلق
    # دارد اتفاق می‌افتد (``section.page``، نه ``section.version.home_page()``
    # که اگر section از یک صفحه‌ی غیرِ اصلی باشد اشتباه می‌بود) — از
    # Phase 2 (سازنده‌ی تک‌صفحه‌ای) به بعد، ادیتور واقعاً رویِ هر شش صفحه
    # کار می‌کند، پس این نوشتار دیگر صرفاً یک احتیاطِ آینده‌نگر نیست.
    last = section.page.sections.order_by("-order").first()
    new_order = (last.order + 1) if last else 0
    new_section = StorefrontSection.objects.create(
        page=section.page, section_key=section.section_key,
        order=new_order, is_active=section.is_active, settings=dict(section.settings or {}),
        # stable_id عمداً اینجا پاس داده نمی‌شود — پیش‌فرضِ فیلد
        # (``uuid.uuid4``) خودش یک شناسه‌ی منطقیِ تازه تولید می‌کند.
    )
    _clone_section_scoped_media(section, new_section)
    # V3 Free Layout: duplicating a Block inside a Cell keeps the duplicate in
    # that same Cell, directly after its source.  ``section.cell`` is primary;
    # the legacy reverse relation remains only as a compatibility fallback.
    placement = section.cell
    if placement is None:
        placement = StorefrontCell.objects.filter(section=section).select_related("container").first()
    if placement is not None:
        source_index = section.cell_order if section.cell_id == placement.pk else len(container_service.get_cell_blocks(placement)) - 1
        container_service.add_block(placement, new_section, at_index=max(0, source_index + 1))
    else:
        container_service.rebuild_page_from_legacy_rows(section.page)
    messages.success(request, "بخش تکرار شد")
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("جابه‌جایی بلاک")
def storefront_block_move(request, pk):
    """Move/reorder one V3 Block without touching page-level Section order.

    The visual Builder sends ``target_cell_id`` plus either ``at_index`` from
    drag/drop or ``direction`` from the small selection toolbar.  Composition
    remains exclusively ``Section.cell + cell_order``; tenant/page/lock
    invariants stay centralized in ``container_service.move_block``.
    """
    section = _get_scoped_section(request, pk)
    if section.is_locked:
        messages.error(request, "این محتوا قفل است — ابتدا قفل آن را باز کنید")
        return storefront_container_state_partial(request, page_type=section.page.page_type)

    target_raw = (request.POST.get("target_cell_id") or "").strip()
    target_cell = None
    if target_raw:
        if not target_raw.isdigit():
            return HttpResponseBadRequest("خانه مقصد نامعتبر است")
        target_cell = _get_scoped_cell(request, int(target_raw))
    elif section.cell_id:
        target_cell = _get_scoped_cell(request, section.cell_id)
    if target_cell is None:
        return HttpResponseBadRequest("این محتوا داخل خانه قابل جابه‌جایی نیست")
    if target_cell.container.page_id != section.page_id:
        return HttpResponseBadRequest("خانه مقصد متعلق به صفحه دیگری است")

    direction = (request.POST.get("direction") or "").strip()
    at_index_raw = (request.POST.get("at_index") or "").strip()
    if direction in {"up", "down"} and section.cell_id == target_cell.pk:
        current_blocks = container_service.get_cell_blocks(target_cell)
        current_index = next((i for i, block in enumerate(current_blocks) if block.pk == section.pk), None)
        if current_index is None:
            return HttpResponseBadRequest("جایگاه فعلی محتوا پیدا نشد")
        at_index = current_index - 1 if direction == "up" else current_index + 1
    else:
        at_index = int(at_index_raw) if at_index_raw.isdigit() else None

    try:
        container_service.move_block(section, target_cell, at_index=at_index)
    except container_service.ContainerLayoutError as exc:
        messages.error(request, str(exc))
        return storefront_container_state_partial(request, page_type=section.page.page_type)

    response = _container_state_changed_response(
        request, page_type=section.page.page_type, container_id=target_cell.container_id,
        cell_id=target_cell.pk, section_id=section.pk,
    )
    response["HX-Trigger-After-Settle"] = json.dumps({
        "sfbBlockMoved": {
            "sectionId": section.pk,
            "cellId": target_cell.pk,
            "containerId": target_cell.container_id,
            "page": section.page.page_type,
        },
        "sfbContainerChanged": {"containerId": target_cell.container_id, "page": section.page.page_type},
    })
    return response


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("حذف بلاک")
def storefront_block_remove(request, pk):
    """Delete exactly one Block from a Cell and keep sibling Blocks/layout."""
    section = _get_scoped_section(request, pk)
    page_type = section.page.page_type
    cell = section.cell
    if cell is None:
        # Transitional fallback for a mirrored legacy-only placement.
        cell = StorefrontCell.objects.filter(section=section).select_related("container").first()
    if cell is None:
        return HttpResponseBadRequest("این محتوا داخل هیچ خانه‌ای نیست")
    if cell.container.is_locked or section.is_locked:
        messages.error(request, "این محتوا یا چیدمان قفل است")
        return storefront_container_state_partial(request, page_type=page_type)
    try:
        definition = section_registry.get_definition(section.section_key)
        if not definition.removable:
            messages.error(request, f"«{definition.label_fa}» قابل حذف نیست")
            return storefront_container_state_partial(request, page_type=page_type)
    except section_registry.UnknownSectionTypeError:
        pass

    container_id, cell_id = cell.container_id, cell.pk
    with transaction.atomic():
        container_service.remove_block(section)
        section.delete()
    messages.success(request, "بلاک حذف شد")
    return _container_state_changed_response(
        request, page_type=page_type, container_id=container_id, cell_id=cell_id,
    )


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازچینی بخش‌ها")
def storefront_section_reorder(request):
    """قرارداد یکسان با سایر endpointهای reorder موجود (product-image،
    brand، دسته‌بندی و ...): ``section_ids`` فرم‌رمزی‌شده، سرویس دوباره بر
    اساس تفکیک مستأجر فیلتر می‌کند، شناسه نامعتبر/خارجی بی‌صدا حذف می‌شود،
    ``enumerate()`` ترتیب را از نو ۰..N تنظیم می‌کند.

    A4: شناسه‌ی تکراری کل عملیات را رد می‌کند (هیچ ردیفی تغییر نمی‌کند)؛
    کل حلقه‌ی به‌روزرسانی داخل یک تراکنش است — یا ترتیبِ کامل ذخیره
    می‌شود یا هیچ‌کدام."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    page_type = _resolve_page_type(request.POST.get("page"))
    page = draft.get_page(page_type)
    section_ids = request.POST.getlist("section_ids")

    all_sections = list(page.sections.all())
    sections_by_id = {s.pk: s for s in all_sections}
    ordered_ids = [int(i) for i in section_ids if i.isdigit() and int(i) in sections_by_id]

    if len(set(ordered_ids)) != len(ordered_ids):
        messages.error(request, "فهرست مرتب‌سازی شامل شناسه‌ی تکراری است — ترتیب تغییر نکرد")
        return storefront_section_list_partial(request, page_type=page_type)

    # Phase 1 correction (spec §37 — Lock): موقعیتِ نهاییِ یک section
    # قفل‌شده باید دقیقاً با موقعیتِ فعلی‌اش یکسان بماند — بازچینیِ دسته‌ای
    # نباید بتواند قفل را از این مسیرِ جایگزین دور بزند.
    for index, section_id in enumerate(ordered_ids):
        candidate = sections_by_id[section_id]
        if candidate.is_locked and candidate.order != index:
            messages.error(request, "یک یا چند بخشِ قفل‌شده در این چیدمان است — ترتیب تغییر نکرد")
            return storefront_section_list_partial(request, page_type=page_type)

    # Phase 1 correction: ترکیبِ ردیف — ترتیبِ نهاییِ شبیه‌سازی‌شده (روی
    # همه‌ی sectionهایِ صفحه، نه فقط زیرمجموعه‌ی ارسال‌شده) باید یک چیدمانِ
    # ردیفِ معتبر بماند؛ اگر نه، کلِ بازچینی رد می‌شود — هیچ ردیفی تغییر
    # نمی‌کند (همان قراردادِ «شناسه‌ی تکراری» بالا).
    for index, section_id in enumerate(ordered_ids):
        sections_by_id[section_id].order = index
    try:
        row_service.validate_page_row_layout(sorted(all_sections, key=lambda s: (s.order, s.id)))
    except row_service.RowAssignmentError as exc:
        messages.error(request, str(exc))
        return storefront_section_list_partial(request, page_type=page_type)

    with transaction.atomic():
        for index, section_id in enumerate(ordered_ids):
            StorefrontSection.objects.filter(pk=section_id, page=page).update(order=index)
    container_service.rebuild_page_from_legacy_rows(page)

    return storefront_section_list_partial(request, page_type=page_type)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("جابه‌جایی بخش")
def storefront_section_move(request, pk):
    """جابه‌جایی یک بخش به بالا/پایین — fallback برای موبایل/کیبورد وقتی
    drag-and-drop عملی نیست."""
    direction = request.POST.get("direction")
    section = _get_scoped_section(request, pk)
    # Phase 1 (spec §37 — Lock): «It cannot be moved».
    if section.is_locked:
        messages.error(request, "این بخش قفل است — ابتدا قفل آن را باز کنید")
        return storefront_section_list_partial(request, page_type=section.page.page_type)
    # Phase 1A: جابه‌جایی همیشه بینِ خواهر-وبرادرهایِ **همان صفحه** انجام
    # می‌شود (``section.page.sections``، نه ``section.version.sections``ی
    # تجمیعیِ همه‌ی صفحات که خواهر-وبرادرهایِ صفحاتِ دیگر را هم قاطی
    # می‌کرد).
    siblings = list(section.page.sections.order_by("order", "id"))
    index = next((i for i, s in enumerate(siblings) if s.pk == section.pk), None)
    if index is None:
        return storefront_section_list_partial(request)

    swap_index = index - 1 if direction == "up" else index + 1
    if 0 <= swap_index < len(siblings):
        other = siblings[swap_index]
        # Phase 1 correction: یک section قفل‌نشده هم نباید بتواند یک
        # همسایه‌ی *قفل‌شده* را جابه‌جا کند — swap یعنی هر دو طرف حرکت
        # می‌کنند، پس قفلِ هرکدام باید کلِ عملیات را رد کند، نه فقط قفلِ
        # section مبدأ.
        if other.is_locked:
            messages.error(request, "بخشِ همسایه قفل است — ابتدا قفل آن را باز کنید")
            return storefront_section_list_partial(request, page_type=section.page.page_type)
        section.order, other.order = other.order, section.order
        # ``section`` (از ``_get_scoped_section``) یک کوئریِ *جدا* از
        # ``siblings`` (از ``section.page.sections``) است — یعنی
        # ``siblings[index]`` یک آبجکتِ تکراریِ دیگر برایِ همان ردیف است که
        # هنوز مقدارِ order قدیمی را دارد. برایِ اینکه شبیه‌سازیِ زیر رویِ
        # دادهٔ واقعاً به‌روز کار کند، نسخهٔ به‌روزشدهٔ ``section`` جایگزینِ
        # آن کپیِ قدیمی در فهرست می‌شود (نه یک آبجکتِ سوم/نامتقارن).
        siblings[index] = section
        # Phase 1 correction: یک swap ساده بینِ دو همسایه می‌تواند پیوستگیِ
        # یک ردیفِ ترکیبی را بشکند (اگر فقط یکی از دو طرف عضوِ آن ردیف
        # باشد) — قبل از نوشتن، ترکیبِ شبیه‌سازی‌شده‌ی کلِ صفحه اعتبارسنجی
        # می‌شود؛ نامعتبر بودن یعنی swap اصلاً اتفاق نمی‌افتد (نه نیمه‌انجام).
        try:
            row_service.validate_page_row_layout(sorted(siblings, key=lambda s: (s.order, s.id)))
        except row_service.RowAssignmentError as exc:
            messages.error(request, str(exc))
            return storefront_section_list_partial(request, page_type=section.page.page_type)
        StorefrontSection.objects.bulk_update([section, other], ["order"])
        container_service.rebuild_page_from_legacy_rows(section.page)
    return storefront_section_list_partial(request, page_type=section.page.page_type)


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_edit_history_state(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    return JsonResponse(edit_history_service.history_state(draft))


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_undo(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    entry = edit_history_service.undo(draft)
    payload = edit_history_service.history_state(draft)
    payload.update({"ok": entry is not None, "action_label": entry.action_label if entry else ""})
    return JsonResponse(payload)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_redo(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    entry = edit_history_service.redo(draft)
    payload = edit_history_service.history_state(draft)
    payload.update({"ok": entry is not None, "action_label": entry.action_label if entry else ""})
    return JsonResponse(payload)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_publish(request):
    store = _resolve_store(request)
    try:
        layout_service.publish(store, user=request.user)
        messages.success(request, "چیدمان جدید منتشر شد")
    except layout_service.NoDraftToPublishError:
        messages.error(request, "پیش‌نویسی برای انتشار وجود ندارد")
    except Exception:
        messages.error(request, "محدودیت تعداد انتشار — کمی بعد دوباره تلاش کنید")
    return redirect("dashboard:storefront-builder-editor")


def _preset_would_replace_content(draft, preset) -> bool:
    """آیا اعمالِ این Preset، محتوایِ section-محورِ موجودِ Draft را برایِ
    حداقل یکی از صفحاتی که Preset پوشش می‌دهد جایگزین می‌کند — دقیقاً همان
    شرطی که ``storefront_apply_layout_preset`` قبل از نیازِ تأییدِ صریح
    چک می‌کند؛ در یک تابع مشترک تا گالریِ قالب‌ها (U8) هم دقیقاً همان
    هشدار را، پیش از کلیک، به مرچنت نشان دهد — نه یک محاسبه‌ی دومِ
    ممکن‌است-ناهم‌خوان."""
    return any(draft.get_page(page_type).sections.exists() for page_type in preset.pages)


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_template_gallery(request):
    """U8 — گالریِ Ready Templateها: نقطه‌ی ورودِ ساده/NORMAL-mode برایِ
    مرچنت، پیش از ویرایشگرِ پیشرفته (Free Layout/V3). فقط می‌خواند/نمایش
    می‌دهد — اعمالِ واقعیِ یک Preset همچنان از طریقِ همان
    ``storefront_apply_layout_preset`` (Draft-only، با تأییدِ صریح اگر
    صفحه‌ای از قبل section دارد، هرگز publish خودکار) انجام می‌شود؛ این ویو
    هیچ مسیرِ نوشتنِ جدیدی اضافه نمی‌کند."""
    from . import appearance_registry, global_region_registry, layout_preset_registry
    from .services import template_preview_service
    from .variant_contract import validate_template_provenance

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    provenance = validate_template_provenance(draft.template_provenance)
    current_template_key = provenance["template"]["key"]

    def _variant_label(region, variant_key):
        if not variant_key:
            return ""
        variant = global_region_registry.get_global_variant(region, variant_key)
        return variant.label_fa if variant is not None else ""

    def _palette_swatch(preset):
        if not preset.default_palette_slug:
            return []
        palette = appearance_registry.get_palette(preset.default_palette_slug)
        if palette is None:
            return []
        return [palette.colors[key] for key in ("primary", "secondary", "accent") if key in palette.colors]

    def _thumbnail_fields(preset):
        # Rasti Mode Demo mission (post-Batch-3) — the merchant-rejected
        # abstract SVG schematic is now only the safe fallback. The normal
        # healthy state is a real captured screenshot of the actual public
        # Rasti Mode Demo storefront rendered under this Template — see
        # ``template_preview_service.resolve_real_screenshot``'s own
        # docstring: this is a pure, zero-mutation filesystem check (an
        # existence check plus one small JSON sidecar read), never a
        # browser launch, never a live render, never a data mutation.
        screenshot_relpath = template_preview_service.resolve_real_screenshot(preset)
        if screenshot_relpath is not None:
            return {"thumbnail_kind": "screenshot", "thumbnail_url": static(screenshot_relpath), "thumbnail_svg": ""}
        # Fallback: the always-fresh, zero-I/O SVG schematic from Batch 3 —
        # never raises; any future Preset shape this hasn't been taught yet
        # degrades to a neutral placeholder rather than breaking the page.
        return {"thumbnail_kind": "svg", "thumbnail_url": "", "thumbnail_svg": template_preview_service.resolve_gallery_thumbnail(preset)}

    template_cards = [
        {
            "preset": preset,
            "is_current": preset.key == current_template_key,
            "would_replace_existing_content": _preset_would_replace_content(draft, preset),
            "palette_swatch": _palette_swatch(preset),
            **_thumbnail_fields(preset),
            "header_variant_label": _variant_label(
                global_region_registry.GLOBAL_HEADER_REGION, (preset.header or {}).get("header_variant"),
            ),
            "footer_variant_label": _variant_label(
                global_region_registry.GLOBAL_FOOTER_REGION, (preset.footer or {}).get("footer_variant"),
            ),
        }
        # Acceptance Batch 1 (post-U11) — the merchant-facing Gallery must
        # show only the 8 official Ready Templates, not every registered
        # LayoutPresetDefinition (5 historical/internal presets remain
        # registered and applicable elsewhere — e.g. Advanced mode / the
        # apply-preset endpoint directly — just not surfaced here).
        for preset in layout_preset_registry.list_ready_templates()
    ]

    context = {
        "active_page": "storefront_builder",
        "template_cards": template_cards,
        "has_any_template_applied": bool(current_template_key),
    }
    return render(request, "dashboard/storefront_builder/template_gallery.html", context)


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("اعمال پیش‌تنظیم صفحه‌آرایی")
def storefront_apply_layout_preset(request):
    """اعمالِ یکی از چهار Preset درون‌ساختِ V2 (``layout_preset_registry``)
    روی Draftِ فعلی — Phase 6. کاملاً مستقل از فرمِ Family/Template/Palette
    در ``storefront_appearance_editor`` (همان ویو دست‌نخورده می‌ماند)؛
    عمداً یک ویویِ جدا با همان قراردادِ ``storefront_apply_industry_layout``:
    اگر هرکدام از صفحاتی که این Preset پوشش می‌دهد از قبل Sectionی دارند،
    بدونِ ``confirm_preset_apply=1`` (تأییدِ صریحِ کاربر در UI) رد می‌شود."""
    from . import layout_preset_registry
    from .services import preset_service

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    key = request.POST.get("preset_key")
    preset = layout_preset_registry.get_layout_preset(key)
    if preset is None:
        messages.error(request, "پیش‌تنظیمِ انتخاب‌شده یافت نشد")
        return redirect("dashboard:storefront-builder-editor")

    would_replace = _preset_would_replace_content(draft, preset)
    if would_replace and request.POST.get("confirm_preset_apply") != "1":
        messages.error(
            request,
            "اعمالِ این پیش‌تنظیم، چیدمانِ صفحاتِ پوشش‌داده‌شده در پیش‌نویسِ فعلی را جایگزین می‌کند — "
            "برای ادامه، تأیید صریح لازم است",
        )
        return redirect("dashboard:storefront-builder-editor")

    try:
        # Acceptance Batch 2 (post-U11) — Issue 1: an explicit Template
        # switch/apply must never silently mutate away meaningful existing
        # Draft state; ``apply_preset_with_checkpoint`` preserves it as a
        # recoverable version-history checkpoint first (never auto-publish,
        # published version untouched) whenever there is anything worth
        # preserving.
        preset_service.apply_preset_with_checkpoint(store, preset, user=request.user)
        messages.success(request, f"پیش‌تنظیمِ «{preset.label_fa}» اعمال شد")
    except preset_service.InvalidPresetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


# Acceptance Batch 2 (post-U11) — Issue 3: granular reset-to-Ready-Template-
# baseline merchant controls. Every view here returns to the same editor
# redirect and reports failure via ``messages`` (matching every other
# write view in this module) — never exposes JSON/registry keys/renderer
# paths/internal baseline IDs to the merchant, only Persian sentences.

@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی بخش به قالب")
def storefront_section_reset(request, pk):
    """RESET SECTION — بازنشانیِ یک section به baselineِ Ready Template.

    Proportional history strategy (طبقِ الزامِ صریحِ Batch 2 — «do NOT
    create excessive full-version history spam for tiny resets»): این
    granularityِ کوچک هرگز چک‌پوینتِ نسخه‌یِ جدید نمی‌سازد؛ فقط همان
    Undo/Redoی سبکِ ادیتور (``@_record_edit_history``) کافی است."""
    from .services import preset_service

    section = _get_scoped_section(request, pk)
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    try:
        preset_service.reset_section_to_baseline(draft, section)
        messages.success(request, "بخش به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی فیلد بخش به قالب")
def storefront_section_field_reset(request, pk):
    """RESET FIELD / RESET COMPONENT — یک کلیدِ مشخص از ``settings`` این
    section را به مقدارِ baseline بازمی‌گرداند؛ کلیدِ خواسته‌شده از
    ``field`` در POST خوانده می‌شود (یک کلیدِ ``settings`` واقعی، هرگز
    JSON/مسیر دلخواه)."""
    from .services import preset_service

    section = _get_scoped_section(request, pk)
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    field = request.POST.get("field", "")
    try:
        preset_service.reset_section_setting_to_baseline(draft, section, field)
        messages.success(request, "فیلد به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی تنظیم ظاهر به قالب")
def storefront_appearance_field_reset(request):
    """RESET FIELD برایِ یک کلیدِ سطحِ‌بالایِ appearance_config (مثلاً
    فونت/تراکم/پالت) — دقیقاً همان الگویِ ``storefront_section_field_reset``،
    برایِ ظاهرِ سراسری به‌جایِ یک section."""
    from .services import preset_service

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    field = request.POST.get("field", "")
    try:
        preset_service.reset_appearance_setting_to_baseline(draft, field)
        messages.success(request, "تنظیمِ ظاهر به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی هدر به قالب")
def storefront_header_reset(request):
    """RESET HEADER — فقط هدر؛ فوتر/صفحات دست‌نخورده می‌مانند. Proportional
    history: بدونِ چک‌پوینتِ نسخه‌یِ جدید (یک پیکربندیِ JSON، نه محتوایِ
    section-محور)."""
    from .services import preset_service

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    try:
        preset_service.reset_header_to_baseline(draft)
        messages.success(request, "هدر به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی فوتر به قالب")
def storefront_footer_reset(request):
    """RESET FOOTER — فقط فوتر؛ هدر/صفحات دست‌نخورده می‌مانند."""
    from .services import preset_service

    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)
    try:
        preset_service.reset_footer_to_baseline(draft)
        messages.success(request, "فوتر به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی صفحه به قالب")
def storefront_page_reset(request):
    """RESET PAGE — بازنشانیِ کاملِ ترکیبِ یک صفحه به baseline؛ صفحاتِ
    دیگر و هدر/فوترِ سراسری دست‌نخورده می‌مانند. مخرب/گسترده است (ممکن
    است sectionهایِ دستیِ همان صفحه را هم جایگزین کند) — طبقِ الزامِ
    صریحِ Batch 2، پیش از انجام، وضعیتِ فعلی را به‌عنوانِ یک چک‌پوینتِ
    قابل‌بازیابی در تاریخچه‌یِ نسخه‌ها نگه می‌دارد."""
    from .services import preset_service

    store = _resolve_store(request)
    page_type = _resolve_page_type(request.POST.get("page"))
    try:
        preset_service.reset_page_with_checkpoint(store, page_type, user=request.user)
        messages.success(request, "صفحه به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("بازنشانی کل فروشگاه به قالب")
def storefront_reset_to_baseline(request):
    """RESET STOREFRONT — بازنشانیِ کاملِ فروشگاه (ظاهر + هدر + فوتر + هر
    صفحه‌ای که Ready Template پوشش می‌دهد) به baselineِ ثبت‌شده. مخرب‌ترین
    granularity — پیش از انجام، وضعیتِ فعلی را چک‌پوینت می‌کند (همان
    الگویِ ``storefront_apply_layout_preset``)."""
    from .services import preset_service

    store = _resolve_store(request)
    try:
        preset_service.reset_storefront_with_checkpoint(store, user=request.user)
        messages.success(request, "کل ظاهر فروشگاه به قالب بازنشانی شد")
    except preset_service.BaselineResetError as exc:
        messages.error(request, str(exc))
    except preset_service.InvalidPresetError as exc:
        messages.error(request, str(exc))
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_apply_industry_layout(request):
    """چیدمان پیشنهادیِ صنفِ نصب‌شده‌ی این فروشگاه را در یک Draft جدید اعمال
    می‌کند. اگر فروشگاه از قبل یک نسخه‌ی منتشرشده دارد، بدون
    ``confirm=1`` (تأیید صریح کاربر در UI) رد می‌شود — هرگز بی‌صدا
    storefront منتشرشده را رونویسی نمی‌کند."""
    store = _resolve_store(request)
    installation = getattr(store, "industry_installation", None)
    if installation is None:
        raise Http404
    force = request.POST.get("confirm") == "1"
    try:
        layout_service.apply_industry_layout(
            store, installation.industry_template, user=request.user, force=force,
        )
        messages.success(request, "چیدمان پیشنهادی صنف در یک پیش‌نویس جدید اعمال شد")
    except layout_service.StorefrontAlreadyPublishedError:
        messages.error(
            request,
            "این فروشگاه از قبل یک نسخه‌ی منتشرشده دارد — برای رونویسی آن با چیدمان صنف، "
            "دوباره با تأیید صریح تلاش کنید",
        )
    except Exception:
        messages.error(request, "محدودیت تعداد ساخت نسخه — کمی بعد دوباره تلاش کنید")
    return redirect("dashboard:storefront-builder-editor")


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_discard(request):
    store = _resolve_store(request)
    layout_service.discard_draft(store)
    messages.success(request, "پیش‌نویس رد شد")
    return redirect("dashboard:storefront-builder-editor")


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("ویرایش ظاهر سایت")
def storefront_appearance_editor(request):
    """پنلِ «ظاهر سایت» — هابِ Template/Palette/رنگ‌های سفارشی/فونت و
    گردی/تراکم/حرکت. برخلافِ هدر/فوتر (صفحه‌ی کاملاً جدا)، این پنل به
    htmx داخلِ همان صفحه‌ی سازنده بارگذاری می‌شود (طبقِ الزامِ صریحِ کار:
    «مرچنت نباید مجبور شود از سازنده بصری خارج شود») — نگاه کنید به
    ``editor.html`` (تبِ «ظاهر سایت»)."""
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        from . import appearance_registry

        current = draft.effective_appearance_config()

        new_template_slug = request.POST.get("template_slug", current["template_slug"])
        template_changed = new_template_slug != current.get("template_slug")
        new_template = appearance_registry.get_template(new_template_slug) if template_changed else None

        # تعویضِ Palette یعنی شروعِ تازه — override هایِ پالتِ قبلی روی
        # پالتِ جدید بی‌معنا/گیج‌کننده‌اند (طبقِ الزامِ صریحِ کار: انتخابِ
        # پالت یعنی «تمامِ رنگ‌های هماهنگ با هم تغییر کنند»).
        posted_palette_slug = request.POST.get("palette_slug")
        new_palette_slug = posted_palette_slug if posted_palette_slug else current.get("palette_slug")
        palette_changed = new_palette_slug != current.get("palette_slug")
        color_overrides = {} if palette_changed else dict(current.get("color_overrides") or {})
        theme_overrides = {} if palette_changed else dict(current.get("theme_overrides") or {})

        def _field(name):
            # اولویتِ منبعِ فیلدهایِ ساختاری: Templateِ قدیمی (اگر Template
            # همین الان تغییر کرده) > مقدارِ پست‌شده > مقدارِ فعلی.
            if new_template is not None:
                return getattr(new_template, name)
            return request.POST.get(name, current[name])

        raw = {
            "template_slug": new_template_slug,
            "palette_slug": new_palette_slug,
            "color_overrides": color_overrides,
            "theme_overrides": theme_overrides,
            "font": _field("font"),
            "radius": _field("radius"),
            "button_radius": _field("button_radius"),
            "density": _field("density"),
            "motion": _field("motion"),
            "type_scale": _field("type_scale"),
            "button_style": _field("button_style"),
            # رفتارِ تصویر — همیشه مستقیماً از فرمِ مرچنت خوانده می‌شود،
            # حتی وقتی تعویضِ Template هم در همین POST رخ داده باشد
            # (هیچ Templateای چنین فیلدی ندارد).
            "image_fit": request.POST.get("image_fit", current["image_fit"]),
            "image_hover": request.POST.get("image_hover", current["image_hover"]),
            "card_image_crossfade": (request.POST.get("card_image_crossfade", "") == "1" if "card_image_crossfade" in request.POST else current.get("card_image_crossfade", False)),
            "card_image_zoom": (request.POST.get("card_image_zoom", "") == "1" if "card_image_zoom" in request.POST else current.get("card_image_zoom", True)),
            # Phase 8 P0-7 — این ۵ فیلد اختیاری‌اند (نه بخشی از
            # APPEARANCE_CONFIG_DEFAULTS)؛ اگر فرمِ POSTکننده آن‌ها را
            # حمل نکند (مثلاً یک فرمِ قدیمی‌تر)، به مقدارِ فعلیِ ذخیره‌شده
            # برمی‌گردیم، نه به یک پیش‌فرضِ سخت‌کدشده.
            "content_width": request.POST.get("content_width", current.get("content_width")),
            "grid_density": request.POST.get("grid_density", current.get("grid_density")),
            "card_shadow": request.POST.get("card_shadow", current.get("card_shadow")),
            "card_hover": request.POST.get("card_hover", current.get("card_hover")),
            "hero_style": request.POST.get("hero_style", current.get("hero_style")),
        }
        from .models import APPEARANCE_COLOR_KEYS

        reset_key = request.POST.get("reset_color")
        reset_theme_key = request.POST.get("reset_theme")
        if request.POST.get("reset_all_overrides") == "1":
            # بازگردانیِ کلِ پالت — کلِ override ها پاک می‌شود، حتی اگر
            # فیلدهایِ رنگِ دیگر هم در همین POST حاضر باشند (چون همان
            # فرمِ خودِ صفحه‌ی رنگ‌هاست) — این دکمه عمداً هر ادعایِ دیگری
            # را نادیده می‌گیرد.
            raw["color_overrides"] = {}
            raw["theme_overrides"] = {}
        elif reset_key:
            # بازگردانیِ *فقط یک* رنگ — عمداً بقیه‌ی فیلدهایِ ``color_*``ی
            # همین POST را نادیده می‌گیرد (آن‌ها فقط مقدارِ نمایشیِ فعلیِ
            # input رنگی‌اند، نه تغییرِ واقعیِ مرچنت) وگرنه همان لحظه با
            # مقدارِ فعلی دوباره override می‌شدند و «بازگردانی» بی‌اثر
            # می‌ماند.
            raw["color_overrides"].pop(reset_key, None)
        elif reset_theme_key:
            raw["theme_overrides"].pop(reset_theme_key, None)
        else:
            # فقط مقادیری که واقعاً با پالت پایه فرق دارند Override می‌شوند.
            # بنابراین بازکردن فرم و زدن «اعمال» همه‌ی پالت را بی‌دلیل freeze نمی‌کند.
            base_config = {
                **current,
                "palette_slug": new_palette_slug,
                "color_overrides": {},
                "theme_overrides": {},
            }
            base_colors = appearance_registry.resolve_colors(base_config)
            base_roles = appearance_registry.resolve_theme_roles(base_config)

            for color_key in APPEARANCE_COLOR_KEYS:
                posted = request.POST.get(f"color_{color_key}")
                if posted:
                    if posted.upper() == base_colors[color_key].upper():
                        raw["color_overrides"].pop(color_key, None)
                    else:
                        raw["color_overrides"][color_key] = posted

            for theme_key in appearance_registry.THEME_ROLE_KEYS:
                posted = request.POST.get(f"theme_{theme_key}")
                if posted:
                    if posted.upper() == base_roles[theme_key].upper():
                        raw["theme_overrides"].pop(theme_key, None)
                    else:
                        raw["theme_overrides"][theme_key] = posted
        # Part 2B (ibolak Home rebuild) — this view is the one real place a
        # merchant deliberately customizes colors, so ``color_overrides``'s
        # truthiness *here* (after the palette-switch/reset-all/reset-one/
        # per-key logic above already ran) genuinely reflects merchant
        # intent — unlike ``bootstrap_service.bootstrap_appearance_config``'s
        # automatic migration mirror, which never passes through this view.
        raw["color_overrides_customized"] = bool(raw["color_overrides"])
        try:
            config = layout_service.validate_appearance_config(raw)
        except layout_service.AppearanceConfigValidationError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:storefront-builder-editor")
        # Phase 1 (Task 3) — delegate the validated managed Appearance update to
        # the canonical authority service instead of replacing appearance_config
        # wholesale. This preserves the reserved store_appearance manifest and
        # any other opaque/canonical keys that this legacy form never carries.
        appearance_authority_service.apply_appearance_patch(
            version=draft, patch=config
        )
        messages.success(request, "تنظیمات ظاهر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    from . import appearance_registry, layout_preset_registry

    config = draft.effective_appearance_config()
    color_field_labels = [
        ("primary", "رنگ اصلی و دکمه‌ها"),
        ("secondary", "رنگ مکمل"),
        ("accent", "رنگ تأکیدی و تخفیف"),
        ("background", "پس‌زمینه کل سایت"),
        ("surface", "سطح عمومی و پنل‌ها"),
        ("text", "رنگ متن اصلی کل سایت"),
        ("muted", "متن کم‌رنگ"),
        ("border", "خطوط و حاشیه‌ها"),
    ]
    theme_field_labels = [
        ("header_bg", "پس‌زمینه هدر"),
        ("header_text", "متن هدر"),
        ("nav_bg", "پس‌زمینه منو"),
        ("nav_text", "متن منو"),
        ("card_bg", "پس‌زمینه کارت محصول"),
        ("footer_bg", "پس‌زمینه فوتر"),
        ("footer_text", "متن فوتر"),
        ("price", "رنگ قیمت"),
    ]
    return render(request, "dashboard/storefront_builder/partials/appearance_panel.html", {
        "draft": draft,
        "config": config,
        "resolved_colors": appearance_registry.resolve_colors(config),
        "resolved_theme_roles": appearance_registry.resolve_theme_roles(config),
        "palettes": appearance_registry.list_palettes(),
        "templates": appearance_registry.list_templates(),
        "font_choices": appearance_registry.FONT_CHOICES,
        "density_choices": appearance_registry.DENSITY_CHOICES,
        "motion_choices": appearance_registry.MOTION_CHOICES,
        "type_scale_choices": appearance_registry.TYPE_SCALE_CHOICES,
        "button_style_choices": appearance_registry.BUTTON_STYLE_CHOICES,
        "image_fit_choices": appearance_registry.IMAGE_FIT_CHOICES,
        "image_hover_choices": appearance_registry.IMAGE_HOVER_CHOICES,
        "color_field_labels": color_field_labels,
        "theme_field_labels": theme_field_labels,
        "site_content_width_choices": appearance_registry.SITE_CONTENT_WIDTH_CHOICES,
        "site_grid_density_choices": appearance_registry.SITE_GRID_DENSITY_CHOICES,
        "site_card_shadow_choices": appearance_registry.SITE_CARD_SHADOW_CHOICES,
        "site_card_hover_choices": appearance_registry.SITE_CARD_HOVER_CHOICES,
        "site_hero_style_choices": appearance_registry.SITE_HERO_STYLE_CHOICES,
        # Phase 6 — چهار Preset درون‌ساختِ V2؛ کاملاً مستقل از Family/
        # Template/Palette بالا (نگاه کنید به ``layout_preset_registry.py``).
        "layout_presets": layout_preset_registry.list_layout_presets(),
        "active_layout_preset_key": config.get("layout_preset_key"),
    })


def _extract_shell_responsive_raw(request, keys: list[str]) -> dict:
    """بلوکِ خامِ «نمایش در دستگاه‌ها»یِ هدر/فوتر را از POST می‌خواند —
    Phase 4، معادلِ ``_extract_responsive_raw`` سطحِ section اما با
    قراردادِ نام‌گذاریِ مستقیم (``{key}__hide_on_tablet``) چون چک‌باکسِ
    UI اینجا خودش «پنهان در ...» است، نه «نمایش در ...» (پس نیازی به
    وارونه‌سازیِ مضاعف نیست)."""
    return {
        key: {
            "hide_on_tablet": request.POST.get(f"{key}__hide_on_tablet") == "on",
            "hide_on_mobile": request.POST.get(f"{key}__hide_on_mobile") == "on",
        }
        for key in keys
    }


def _extract_announcement_links_raw(request) -> list[dict]:
    """لینک‌های قابل‌ویرایش نوار اعلان را از دو فهرست موازی فرم می‌خواند."""
    labels = request.POST.getlist("announcement_link_label")
    urls = request.POST.getlist("announcement_link_url")
    return [
        {
            "label": label,
            "url": urls[index] if index < len(urls) else "",
        }
        for index, label in enumerate(labels)
    ]


def _extract_header_extra_blocks_raw(request) -> list[dict]:
    """Phase 8 P0-3 — بلوک‌هایِ اختیاریِ هدر (تلفن/شبکه‌ی اجتماعی/CTA/
    فاصله) را از سه فهرستِ POSTِ موازی می‌خواند — دقیقاً همان الگویِ
    itemRepeaterFormِ از‌قبل‌موجود (FAQ/نظراتِ مشتریان، ``editor.html``):
    ترتیبِ سه فهرست، ترتیبِ بلوک‌هاست."""
    types = request.POST.getlist("block_type")
    labels = request.POST.getlist("block_label")
    urls = request.POST.getlist("block_url")
    blocks = []
    for i, block_type in enumerate(types):
        block = {"type": block_type}
        if block_type == "cta":
            block["label"] = labels[i] if i < len(labels) else ""
            block["url"] = urls[i] if i < len(urls) else ""
        blocks.append(block)
    return blocks


def _extract_footer_extra_blocks_raw(request) -> list[dict]:
    """Phase 8 P0-4 — ستون‌هایِ اضافیِ فوتر (متنِ دلخواه/لینک/شبکه‌ی
    اجتماعیِ تکراری) را از سه فهرستِ POSTِ موازی می‌خواند — همان الگویِ
    ``_extract_header_extra_blocks_raw`` بالا."""
    types = request.POST.getlist("footer_block_type")
    titles = request.POST.getlist("footer_block_title")
    texts = request.POST.getlist("footer_block_text")
    labels = request.POST.getlist("footer_block_label")
    urls = request.POST.getlist("footer_block_url")
    blocks = []
    for i, block_type in enumerate(types):
        block = {"type": block_type}
        if block_type == "custom_text":
            block["title"] = titles[i] if i < len(titles) else ""
            block["text"] = texts[i] if i < len(texts) else ""
        elif block_type == "link":
            block["label"] = labels[i] if i < len(labels) else ""
            block["url"] = urls[i] if i < len(urls) else ""
        blocks.append(block)
    return blocks


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("ویرایش هدر")
def storefront_header_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        raw = {field: request.POST.get(field) == "on" for field in HEADER_TOGGLE_FIELDS}
        raw["announcement_text"] = request.POST.get("announcement_text", "")
        raw["announcement_links"] = _extract_announcement_links_raw(request)
        raw["announcement_show_phone"] = request.POST.get("announcement_show_phone") == "on"
        raw["responsive"] = _extract_shell_responsive_raw(request, HEADER_RESPONSIVE_AWARE_KEYS)
        raw["extra_blocks"] = _extract_header_extra_blocks_raw(request)
        raw["header_variant"] = request.POST.get("header_variant", "")
        try:
            config = layout_service.validate_header_config(raw)
        except layout_service.HeaderConfigValidationError as exc:
            messages.error(request, str(exc))
            return render(request, "dashboard/storefront_builder/header_editor.html", {
                "active_page": "storefront_builder",
                "config": {**HEADER_CONFIG_DEFAULTS, **raw}, "draft": draft, "error": str(exc),
                "header_variants": global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION),
            })
        draft.header_config = config
        draft.save(update_fields=["header_config", "updated_at"])
        # Phase 1 (Task 3) — after persisting the full validated Header config
        # (toggles/announcement/content preserved as before), synchronize the
        # typed Store Appearance manifest header selection with the chosen
        # variant so the legacy selector mirror and the typed manifest agree.
        appearance_authority_service.apply_header_variant(
            version=draft, header_variant=config["header_variant"]
        )
        messages.success(request, "تنظیمات هدر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    template_name = (
        "dashboard/storefront_builder/partials/header_panel.html"
        if request.headers.get("HX-Request") == "true"
        else "dashboard/storefront_builder/header_editor.html"
    )
    return render(request, template_name, {
        "active_page": "storefront_builder", "config": draft.effective_header_config(), "draft": draft,
        "header_variants": global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION),
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
@_record_edit_history("ویرایش فوتر")
def storefront_footer_editor(request):
    store = _resolve_store(request)
    draft = layout_service.get_or_create_draft(store, user=request.user)

    if request.method == "POST":
        current_footer_config = draft.effective_footer_config()
        raw = {field: request.POST.get(field) == "on" for field in FOOTER_TOGGLE_FIELDS}
        raw["responsive"] = _extract_shell_responsive_raw(request, FOOTER_RESPONSIVE_AWARE_KEYS)
        raw["extra_blocks"] = _extract_footer_extra_blocks_raw(request)
        raw["footer_variant"] = request.POST.get("footer_variant", "")
        # The legacy full-page footer form predates mobile bottom navigation and does
        # not submit this field. Preserve the current selection unless the V3 Builder
        # inspector explicitly posts a new variant, otherwise a legacy save would
        # silently reset a template's mobile navigation to ``hidden``.
        raw["mobile_nav_variant"] = request.POST.get(
            "mobile_nav_variant",
            current_footer_config.get("mobile_nav_variant", "hidden"),
        )
        try:
            config = layout_service.validate_footer_config(raw)
        except layout_service.FooterConfigValidationError as exc:
            messages.error(request, str(exc))
            return render(request, "dashboard/storefront_builder/footer_editor.html", {
                "active_page": "storefront_builder",
                "config": {**FOOTER_CONFIG_DEFAULTS, **raw}, "draft": draft, "error": str(exc),
                "footer_variants": global_region_registry.list_global_variants(global_region_registry.GLOBAL_FOOTER_REGION),
                "mobile_nav_variants": global_region_registry.list_global_variants(global_region_registry.GLOBAL_MOBILE_NAV_REGION),
            })
        draft.footer_config = config
        draft.save(update_fields=["footer_config", "updated_at"])
        # Phase 1 (Task 3) — after persisting the full validated Footer config
        # (footer options preserved; live FooterSettings ownership untouched),
        # synchronize the typed Store Appearance manifest footer/bottom_nav
        # selections with the chosen variants so mirror and manifest agree.
        appearance_authority_service.apply_footer_variant(
            version=draft,
            footer_variant=config["footer_variant"],
            mobile_nav_variant=config["mobile_nav_variant"],
        )
        messages.success(request, "تنظیمات فوتر ذخیره شد")
        return redirect("dashboard:storefront-builder-editor")

    template_name = (
        "dashboard/storefront_builder/partials/footer_panel.html"
        if request.headers.get("HX-Request") == "true"
        else "dashboard/storefront_builder/footer_editor.html"
    )
    return render(request, template_name, {
        "active_page": "storefront_builder", "config": draft.effective_footer_config(), "draft": draft,
        "footer_variants": global_region_registry.list_global_variants(global_region_registry.GLOBAL_FOOTER_REGION),
        "mobile_nav_variants": global_region_registry.list_global_variants(global_region_registry.GLOBAL_MOBILE_NAV_REGION),
    })


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_history(request):
    store = _resolve_store(request)
    versions = layout_service.list_versions(store)
    layout = layout_service.get_or_create_layout(store)
    return render(request, "dashboard/storefront_builder/history.html", {
        "active_page": "storefront_builder", "versions": versions, "layout": layout,
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_restore(request, pk):
    store = _resolve_store(request)
    try:
        layout_service.restore_version(store, pk, user=request.user)
        messages.success(request, "نسخه در یک پیش‌نویس جدید بازگردانی شد — برای اعمال آن روی فروشگاه، آن را منتشر کنید")
    except layout_service.CrossStoreVersionError:
        raise Http404
    except Exception:
        messages.error(request, "محدودیت تعداد بازگردانی — کمی بعد دوباره تلاش کنید")
    return redirect("dashboard:storefront-builder-editor")
