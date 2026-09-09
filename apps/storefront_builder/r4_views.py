import json

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Brand, Category, MerchantCollection
from apps.catalog.services.collection_service import searchable_products
from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import appearance_registry, global_region_registry, resource_source, section_registry, variant_contract
from .models import StorefrontLayoutVersion, StorefrontPage, StorefrontSection
from .services import (
    container_service,
    edit_history_service,
    layout_service,
    r4_mutation_service,
    section_structure_service,
)

#: Phase 0/1 R4 Inspector renderer capability — deliberately narrower than
#: SettingsSchema's own ALLOWED_FIELD_TYPES. A schema field of another
#: otherwise-valid schema type (e.g. "color") reaching this Inspector is a
#: developer contract failure, not a merchant free-text fallback.
_INSPECTOR_SUPPORTED_FIELD_TYPES = frozenset({
    "text",
    "rich_text",
    "integer",
    "boolean",
    "choice",
    "appearance_override",
    "resource_source",
    "repeater",
})

#: R4 Task 7 — merchant-facing Persian labels for the existing curated
#: type-scale enum (appearance_registry.TYPE_SCALE_CHOICES). Stored values
#: remain the existing enum strings; only the label shown is translated.
_TYPE_SCALE_LABELS_FA = {
    "compact": "فشرده",
    "normal": "معمولی",
    "large": "بزرگ",
}

#: R4 Task 9 — merchant-facing Persian labels for the generic
#: resource_source READ-ONLY summary. Task 9 renders a summary only (no
#: Picker yet — see r4_views.py's Task 9 section); these labels never
#: leave this presentation layer, resource_source.py itself stays UI-agnostic.
_RESOURCE_SOURCE_KIND_LABELS_FA = {
    "product": "محصول",
    "brand": "برند",
    "category": "دسته‌بندی",
    "collection": "کالکشن",
}
_RESOURCE_SOURCE_MODE_LABELS_FA = {
    "auto": "خودکار",
    "manual": "دستی",
}
_RESOURCE_SOURCE_AUTO_RULE_LABELS_FA = {
    "newest": "جدیدترین",
    "discounted": "تخفیف‌دار",
    "best_sellers": "پرفروش‌ترین",
    "most_viewed": "پربازدیدترین",
    "by_category": "بر اساس دسته‌بندی",
    "by_brand": "بر اساس برند",
    "by_collection": "بر اساس کالکشن",
    "all_active": "همه‌ی موارد فعال",
}

#: R4 Task 10 — the ONE shared Resource Picker's UI-exposed kinds. Every
#: valid ResourceSource kind (Task 9) is exposed here; any value outside
#: this tuple is a controlled 400, not a new picker lifecycle.
_PICKER_UI_KINDS = ("product", "brand", "collection", "category")
_PICKER_SEARCH_RESULT_LIMIT = 20

#: Task 10 Phase 1's directly-interactive auto rules per kind — the only
#: automatic behaviours the Picker itself can set. Product's by_category/
#: by_brand/by_collection stay valid ResourceSource states (still readable/
#: preserved, per Section 17) but are not offered as a Picker control here.
_PICKER_PRODUCT_AUTO_RULES = tuple(
    (rule, _RESOURCE_SOURCE_AUTO_RULE_LABELS_FA[rule])
    for rule in ("newest", "discounted", "best_sellers", "most_viewed")
)
_PICKER_BRAND_AUTO_RULES = (("all_active", _RESOURCE_SOURCE_AUTO_RULE_LABELS_FA["all_active"]),)
_PICKER_COLLECTION_AUTO_RULES = (("all_active", _RESOURCE_SOURCE_AUTO_RULE_LABELS_FA["all_active"]),)
_PICKER_CATEGORY_AUTO_RULES = (("all_active", _RESOURCE_SOURCE_AUTO_RULE_LABELS_FA["all_active"]),)

#: One explicit per-kind map for the Picker's directly-settable auto rules —
#: no per-kind ternary chain in the view.
_PICKER_AUTO_RULES_BY_KIND = {
    "product": _PICKER_PRODUCT_AUTO_RULES,
    "brand": _PICKER_BRAND_AUTO_RULES,
    "collection": _PICKER_COLLECTION_AUTO_RULES,
    "category": _PICKER_CATEGORY_AUTO_RULES,
}


def _search_products(store, query):
    # Deliberately NOT reimplemented: the exact same Store-scoped,
    # placeholder-excluding, name/SKU search the rest of the merchant admin
    # already uses for Product selection.
    return list(searchable_products(store, query=query)[:_PICKER_SEARCH_RESULT_LIMIT])


def _search_brands(store, query):
    qs = Brand.objects.filter(store=store)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(name_en__icontains=query))
    return list(qs.order_by("sort_order", "name", "id")[:_PICKER_SEARCH_RESULT_LIMIT])


def _search_collections(store, query):
    # Store-scoped + active-only, ordered by name (MerchantCollection has no
    # name_en — only ``name``). Fail-closed to the same active/own-store set
    # the public storefront and legacy ownership check use.
    qs = MerchantCollection.objects.filter(store=store, is_active=True)
    if query:
        qs = qs.filter(name__icontains=query)
    return list(qs.order_by("name", "id")[:_PICKER_SEARCH_RESULT_LIMIT])


def _search_categories(store, query):
    # Store-scoped + active-only, ordered by (order, name) — the exact same
    # active/own-store set category_grid's own auto-pick already uses
    # (section_registry._validate_category_grid_settings / render_service).
    qs = Category.objects.filter(store=store, is_active=True)
    if query:
        qs = qs.filter(name__icontains=query)
    return list(qs.order_by("order", "name", "id")[:_PICKER_SEARCH_RESULT_LIMIT])


#: One explicit, server-owned map — no getattr/dynamic import/eval on
#: user-supplied ``kind``, no separate Product/Brand/Collection/Category
#: picker lifecycle.
_RESOURCE_SEARCHERS = {
    "product": _search_products,
    "brand": _search_brands,
    "collection": _search_collections,
    "category": _search_categories,
}


def _serialize_picker_item(kind, obj):
    if kind == "product":
        return {"id": obj.pk, "label": obj.name, "sublabel": obj.sku}
    # Collection/Category are dispatched EXPLICITLY before the brand
    # fall-through: neither has a ``name_en`` attribute, so they must never
    # reach the brand branch below.
    if kind == "collection":
        return {"id": obj.pk, "label": obj.name, "sublabel": obj.slug}
    if kind == "category":
        return {"id": obj.pk, "label": obj.name, "sublabel": obj.slug}
    return {"id": obj.pk, "label": obj.name, "sublabel": obj.name_en}


def _parse_selected_ids(request) -> list[int]:
    """Strictly positive integers only, deduplicated preserving first-seen
    order — a malformed value is simply dropped, never a 400 (fail closed,
    exactly like an unresolvable foreign/nonexistent id below)."""
    ordered_ids: list[int] = []
    seen: set[int] = set()
    for raw in request.GET.getlist("selected"):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        ordered_ids.append(value)
    return ordered_ids


def _resolve_selected_items(store, kind, ordered_ids):
    """Fail closed, order-preserving: an id belonging to another Store and
    an id that plain doesn't exist both simply fail to resolve here — never
    a second query that would tell the two apart."""
    if not ordered_ids:
        return []
    if kind == "product":
        found = {obj.pk: obj for obj in searchable_products(store).filter(pk__in=ordered_ids)}
    elif kind == "collection":
        # all_active + same-store + fail-closed: an inactive or foreign id
        # simply fails to resolve here (never a second query to tell apart).
        found = {
            obj.pk: obj
            for obj in MerchantCollection.objects.filter(store=store, is_active=True, pk__in=ordered_ids)
        }
    elif kind == "category":
        # Same all_active + same-store + fail-closed contract as collection.
        found = {
            obj.pk: obj
            for obj in Category.objects.filter(store=store, is_active=True, pk__in=ordered_ids)
        }
    else:
        found = {obj.pk: obj for obj in Brand.objects.filter(store=store, pk__in=ordered_ids)}
    return [found[value] for value in ordered_ids if value in found]


def _build_global_design_context(draft: StorefrontLayoutVersion) -> dict:
    """R4 Task 11 (Section 23) — the Global Design panel's ENTIRE read
    projection: server-authoritative current config + registry-driven
    choice lists. No DB-backed duplicate design-option table; Templates/
    Palettes come from appearance_registry, Header/Footer variants from
    global_region_registry — never a hardcoded list here or in JS/HTML."""
    return {
        "appearance": draft.effective_appearance_config(),
        "header": draft.effective_header_config(),
        "footer": draft.effective_footer_config(),
        "templates": [
            {"slug": t.slug, "label_fa": t.name_fa, "group_fa": t.group_fa}
            for t in appearance_registry.list_templates()
        ],
        "palettes": [
            {"slug": p.slug, "label_fa": p.name_fa, "group_fa": p.group_fa}
            for p in appearance_registry.list_palettes()
        ],
        "font_choices": appearance_registry.FONT_CHOICES,
        "type_scale_choices": [
            (value, _TYPE_SCALE_LABELS_FA.get(value, value))
            for value in appearance_registry.TYPE_SCALE_CHOICES
        ],
        "motion_choices": appearance_registry.MOTION_CHOICES,
        "button_style_choices": appearance_registry.BUTTON_STYLE_CHOICES,
        "header_variants": [
            {"key": v.key, "label_fa": v.label_fa}
            for v in global_region_registry.list_global_variants(global_region_registry.GLOBAL_HEADER_REGION)
        ],
        "footer_variants": [
            {"key": v.key, "label_fa": v.label_fa}
            for v in global_region_registry.list_global_variants(global_region_registry.GLOBAL_FOOTER_REGION)
        ],
    }


@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_editor(request):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    draft = layout_service.get_or_create_draft(store, user=request.user)
    # Phase 4 (Task 3B) — the exact same validated PageType input the legacy
    # editor uses (StorefrontPage.resolve_page_type): an absent/invalid
    # ``?page=`` silently resolves to Home, so every existing bookmark/link
    # to this route keeps working unchanged.
    page_type = StorefrontPage.resolve_page_type(request.GET.get("page"))
    page = draft.get_page(page_type)
    container_service.ensure_page_containers(page)
    sections = page.sections.select_related("cell", "cell__container").order_by("order", "id")

    # R4 Task 8 — the Structure panel's read projection: the exact visual
    # order Preview renders (Container.order -> Cell.order -> Block.cell_order),
    # not the flat page-level `order`. A pure read — no additional placement
    # mutation beyond the `ensure_page_containers` call already above.
    structure_items = []
    for item in section_structure_service.build_structure_projection(page):
        section_obj = item["section"]
        try:
            item_definition = section_registry.get_definition(section_obj.section_key)
        except section_registry.UnknownSectionTypeError:
            item_definition = None
        structure_items.append({
            "id": section_obj.pk,
            "label": item_definition.label_fa if item_definition else section_obj.section_key,
            "duplicable": bool(item_definition and item_definition.duplicable),
            "removable": bool(item_definition and item_definition.removable),
            "is_locked": section_obj.is_locked,
        })

    # The safe "Add Section" library projection: only definitions allowed on
    # the CURRENT page_type and not hidden_from_library — Registry stays the
    # single source of truth, never duplicated into JS. Phase 4 (Task 3B):
    # generalized from a hardcoded Home to the resolved page_type above.
    structure_library = [
        {
            "category": category,
            "items": [{"key": d.key, "label": d.label_fa} for d in members],
        }
        for category, members in section_registry.list_library_groups(
            page_type=page_type,
        )
    ]

    # The shell has no <form>/{% csrf_token %} of its own, so the browser
    # mutation client (r4_editor.js) has no other trigger to guarantee a
    # csrftoken cookie exists before its first POST to the Task 5 endpoint.
    get_token(request)

    return render(
        request,
        "dashboard/storefront_builder/r4/editor.html",
        {
            "active_page": "storefront_builder",
            "layout": layout,
            "draft": draft,
            "page": page,
            "page_type": page_type,
            # Phase 4 (Task 3B) — the page switcher's data source: the exact
            # same 6 registered PageType choices the legacy editor's own
            # switcher already uses (``StorefrontPage.PageType.choices``),
            # never a second hardcoded list.
            "page_types": StorefrontPage.PageType.choices,
            "sections": sections,
            "r4_edit_revision": draft.edit_revision,
            "structure_items": structure_items,
            "structure_library": structure_library,
            "global_design": _build_global_design_context(draft),
            "history": edit_history_service.history_state(draft),
        },
    )


def _is_strict_int(value: object) -> bool:
    return type(value) is int


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_mutation(request):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "code": "malformed_json"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "code": "invalid_request_shape"}, status=400)

    base_revision = payload.get("base_revision")
    if not _is_strict_int(base_revision) or base_revision < 0:
        return JsonResponse({"ok": False, "code": "invalid_base_revision"}, status=400)

    mutation = payload.get("mutation")
    if not isinstance(mutation, dict):
        return JsonResponse({"ok": False, "code": "invalid_mutation"}, status=400)

    mutation_type = mutation.get("type")
    if not isinstance(mutation_type, str) or not mutation_type:
        return JsonResponse({"ok": False, "code": "invalid_mutation_type"}, status=400)

    try:
        new_revision = r4_mutation_service.apply_mutation(
            store=store, actor=request.user, base_revision=base_revision, mutation=mutation,
        )
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True, "new_revision": new_revision, "mutation_type": mutation_type})


#: Phase 3 (V02) — mirror of r4_mutation_service._BRAND_VIEW_ALL_SUPPORTING_VARIANTS
#: for the read-only inspector filtering path (grid/carousel emit the anchor,
#: beauty_tabs never does).
_BRAND_VIEW_ALL_SUPPORTING_VARIANTS = frozenset({"grid", "carousel"})


def _brand_view_all_control_offered(store, definition, current_settings: dict) -> bool:
    """True IFF the brand_carousel "مشاهده همه" control should be shown for
    the CURRENT persisted state: a supporting active variant AND a trusted
    stored destination that resolves to a non-None URL for this store. Pure
    read — never mutates ``current_settings``."""
    active = variant_contract.resolve_active_variant(definition, current_settings)
    if active is None or active.key not in _BRAND_VIEW_ALL_SUPPORTING_VARIANTS:
        return False
    destination = (current_settings or {}).get("destination") or {}
    from apps.content.services import resolve_destination_setting

    return resolve_destination_setting(store, destination).get("url") is not None


@require_GET
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_section_inspector(request, pk):
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    # The currently active Draft pointer only — never resolved/switched
    # here (see r4_mutation_service.apply_mutation for the same rule).
    draft = layout.draft_version
    if draft is None or draft.status != StorefrontLayoutVersion.Status.DRAFT:
        raise Http404

    try:
        section = StorefrontSection.objects.select_related("page__version").get(
            pk=pk, page__version=draft,
        )
    except StorefrontSection.DoesNotExist:
        raise Http404

    try:
        definition = section_registry.get_definition(section.section_key)
    except ValueError:
        raise Http404

    schema = definition.settings_schema
    if schema is None:
        raise Http404

    for field in schema.fields:
        if field.field_type not in _INSPECTOR_SUPPORTED_FIELD_TYPES:
            raise ImproperlyConfigured(
                f"R4 Inspector (Phase 0) cannot render field_type={field.field_type!r} "
                f"for key={field.key!r} on section_key={section.section_key!r}"
            )

    basic_fields = tuple(field for field in schema.fields if field.group == "basic")
    advanced_fields = tuple(field for field in schema.fields if field.group == "advanced")
    current_settings = section.settings or {}

    # Phase 3 (V02) — the brand_carousel "مشاهده همه" (``show_view_all``)
    # control is only offered when the active variant/destination could
    # actually render an actionable anchor: a supporting variant (grid/
    # carousel, never beauty_tabs) AND a trusted destination that resolves to
    # a non-None URL for this store. This is READ-ONLY field filtering — a
    # dormant stored ``show_view_all``/``destination`` is left untouched in
    # settings; we only hide the control so the merchant is not shown a toggle
    # that cannot take effect. The DB-backed resolution stays at this
    # store-scoped boundary, never inside the schema.
    if section.section_key == "brand_carousel" and not _brand_view_all_control_offered(
        store, definition, current_settings
    ):
        basic_fields = tuple(f for f in basic_fields if f.key != "show_view_all")
        advanced_fields = tuple(f for f in advanced_fields if f.key != "show_view_all")
    field_values = {
        field.key: current_settings.get(field.key, field.default)
        for field in schema.fields
    }

    # R4 Task 7 — the Inspector needs to show what an appearance_override
    # field would inherit while disabled. Pass only the safe typed
    # projection the widget actually renders (font/type_scale), never the
    # whole arbitrary appearance_config.
    global_appearance = draft.effective_appearance_config()
    inherited_appearance_by_field = {
        field.key: {
            "font": global_appearance.get("font"),
            "type_scale": global_appearance.get("type_scale"),
        }
        for field in schema.fields
        if field.field_type == "appearance_override"
    }

    # R4 Task 9 — a resource_source field's CURRENT value must be projected
    # from the real legacy Section.settings (data_source/source_id/
    # product_ids, or brand_ids) through the compatibility adapter, never
    # blindly shown as the schema default — a Product already configured
    # as manual/(7, 3) must project as exactly that, not "auto/newest".
    # Task 9 renders a clean READ-ONLY summary only (no Picker yet).
    resource_source_summary = None
    for field in schema.fields:
        if field.field_type != "resource_source":
            continue
        try:
            projected_source = resource_source.resource_source_from_section_settings(
                section.section_key, current_settings,
            )
        except resource_source.ResourceSourceError:
            continue
        field_values[field.key] = resource_source.serialize_resource_source(projected_source)
        resource_source_summary = {
            "kind_label": _RESOURCE_SOURCE_KIND_LABELS_FA.get(projected_source.kind, projected_source.kind),
            "mode_label": _RESOURCE_SOURCE_MODE_LABELS_FA.get(projected_source.mode, projected_source.mode),
            "auto_rule_label": (
                _RESOURCE_SOURCE_AUTO_RULE_LABELS_FA.get(projected_source.auto_rule, projected_source.auto_rule)
                if projected_source.auto_rule else None
            ),
            "manual_count": len(projected_source.manual_ids),
        }

    return render(
        request,
        "dashboard/storefront_builder/r4/partials/section_inspector.html",
        {
            "section": section,
            "definition": definition,
            "basic_fields": basic_fields,
            "advanced_fields": advanced_fields,
            "field_values": field_values,
            "appearance_font_choices": appearance_registry.FONT_CHOICES,
            "appearance_type_scale_choices": [
                (value, _TYPE_SCALE_LABELS_FA.get(value, value))
                for value in appearance_registry.TYPE_SCALE_CHOICES
            ],
            "inherited_appearance_by_field": inherited_appearance_by_field,
            "resource_source_summary": resource_source_summary,
        },
    )


@require_GET
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_resource_picker(request):
    """R4 Task 10 — the ONE shared search/selection endpoint behind the
    Product+Brand Resource Picker. GET-only, read-only: it never writes a
    Section. The only Section write remains the existing Task 5 mutation
    endpoint (``section.update_settings`` with a ``source`` patch)."""
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    kind = request.GET.get("kind")
    if kind not in _PICKER_UI_KINDS:
        return JsonResponse({"ok": False, "code": "unsupported_kind"}, status=400)

    query = (request.GET.get("q") or "").strip()
    max_items = resource_source.manual_id_limit(kind)

    # Server-enforced max — never the client's own max_items, and never a
    # silent truncation to "the first N ids": the ResourceSource cap stays
    # authoritative, so an over-cap request is a controlled rejection, not
    # a reinterpreted one. Checked AFTER parse-and-dedup, so duplicates of
    # the same id never falsely trip this.
    ordered_selected_ids = _parse_selected_ids(request)
    if len(ordered_selected_ids) > max_items:
        return JsonResponse({"ok": False, "code": "too_many_selected_resources"}, status=400)

    searcher = _RESOURCE_SEARCHERS[kind]
    results = [_serialize_picker_item(kind, obj) for obj in searcher(store, query)]
    selected_items = [
        _serialize_picker_item(kind, obj)
        for obj in _resolve_selected_items(store, kind, ordered_selected_ids)
    ]

    return render(
        request,
        "dashboard/storefront_builder/r4/partials/resource_picker.html",
        {
            "kind": kind,
            "kind_label": _RESOURCE_SOURCE_KIND_LABELS_FA.get(kind, kind),
            "query": query,
            "max_items": max_items,
            "results": results,
            "selected_items": selected_items,
            "auto_rules": _PICKER_AUTO_RULES_BY_KIND[kind],
        },
    )


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_history_command(request):
    """R4 Task 11 — the ONE Undo/Redo command endpoint. Deliberately
    separate from the normal mutation endpoint (Section 13): Undo/Redo
    never go through ``r4_mutation_service.apply_mutation``'s normal
    record_change path, or Undo itself would become a new undoable edit."""
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "code": "malformed_json"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "code": "invalid_request_shape"}, status=400)

    base_revision = payload.get("base_revision")
    if not _is_strict_int(base_revision) or base_revision < 0:
        return JsonResponse({"ok": False, "code": "invalid_base_revision"}, status=400)

    command = payload.get("command")
    if command not in ("undo", "redo"):
        return JsonResponse({"ok": False, "code": "invalid_command"}, status=400)

    try:
        result = r4_mutation_service.apply_history_command(
            store=store, actor=request.user, base_revision=base_revision, command=command,
        )
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({
        "ok": True,
        "changed": result["changed"],
        "new_revision": result["new_revision"],
        "can_undo": result["can_undo"],
        "can_redo": result["can_redo"],
        "action_label": result["action_label"],
    })


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_publish(request):
    """R4 Task 11 — stale-aware Publish. The entire release lifecycle
    remains owned by ``layout_service.publish``; this view only adds the
    R4 revision check and a JSON contract around it."""
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "code": "malformed_json"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "code": "invalid_request_shape"}, status=400)

    base_revision = payload.get("base_revision")
    if not _is_strict_int(base_revision) or base_revision < 0:
        return JsonResponse({"ok": False, "code": "invalid_base_revision"}, status=400)

    try:
        published = r4_mutation_service.publish_draft(
            store=store, actor=request.user, base_revision=base_revision,
        )
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({
        "ok": True,
        "published_version_id": published.pk,
        "published_version_number": published.version_number,
    })
