import json

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Brand, Category, MerchantCollection
from apps.catalog.services.collection_service import searchable_products
from apps.content.models import Menu
from apps.core.services.rate_limit import RateLimitExceeded
from apps.dashboard.decorators import permission_required, staff_required
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.resolution import resolve_store_for_service

from . import (
    appearance_registry,
    global_region_registry,
    layout_preset_registry,
    media_views,
    resource_source,
    section_registry,
    variant_contract,
)
from .models import (
    FOOTER_RESPONSIVE_AWARE_KEYS,
    FOOTER_TOGGLE_FIELDS,
    HEADER_RESPONSIVE_AWARE_KEYS,
    HEADER_TOGGLE_FIELDS,
    StorefrontLayoutVersion,
    StorefrontPage,
    StorefrontSection,
)
from .services import (
    container_service,
    edit_history_service,
    layout_service,
    r4_mutation_service,
    section_structure_service,
)
from .services.layout_service import FOOTER_EXTRA_BLOCK_TYPES, HEADER_EXTRA_BLOCK_TYPES

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
    "menu_picker",
    #: Phase 5 Task 4B — the generic per-section background picker widget
    #: (mode/color/pattern/palette-role/media-asset). Rendered generically in
    #: settings_field.html and saved through the existing section.update_settings
    #: mutation; never a section-name branch, never a second media authority.
    "background",
})

#: Phase 5 Task 6 — the "Storefront Showcase" R4 CREATION FACADE.
#:
#: Showcase is merchant-facing UX terminology ONLY. It is NOT a persisted
#: section_key, renderer, schema, or resource-source contract. This is a small
#: presentation-layer mapping from a merchant-facing content type to the ONE
#: EXISTING canonical section it creates via the normal ``section.add`` mutation
#: (ONE CONCEPT = ONE CANONICAL OWNER). The type is chosen at add time and is
#: immutable afterward. Order is the approved merchant order.
#:
#: This constant defines the four approved choices and their canonical target
#: only — it duplicates NO validator/schema/page_type/layout/resource rule.
#: Page legality is NEVER decided here: ``_build_showcase_choices`` emits a
#: choice only if its canonical section is already present in the current,
#: server-owned, page-filtered ``structure_library`` — so future changes to a
#: canonical section's ``page_types`` automatically govern Showcase too, with
#: no second rule set. FORBIDDEN: a ``storefront_showcase`` section key.
_SHOWCASE_FACADE = (
    ("products", "product_section", "محصولات", "نمایش محصولات جدید، منتخب، پرفروش یا انتخابی"),
    ("categories", "category_grid", "دسته‌بندی‌ها", "نمایش دسته‌های فروشگاه"),
    ("collections", "collection_tiles", "کالکشن‌ها", "نمایش مجموعه‌های فروشگاه"),
    ("brands", "brand_carousel", "برندها", "نمایش برندهای فروشگاه"),
)


def _build_showcase_choices(structure_library) -> list[dict]:
    """Project the approved Showcase choices, keeping ONLY those whose canonical
    section is already in the current legal ``structure_library`` (the existing
    server-owned, page-filtered, hidden-aware projection). Never a second
    legality authority; never emits a ``storefront_showcase`` key."""
    legal_keys = {
        item["key"]
        for group in structure_library
        for item in group["items"]
    }
    choices = []
    for content_type, section_key, label, description in _SHOWCASE_FACADE:
        if section_key in legal_keys:
            choices.append({
                "content_type": content_type,
                "section_key": section_key,
                "label": label,
                "description": description,
            })
    return choices


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

#: Phase 5 Task 4B — merchant-facing Persian labels for the existing
#: background-mode / palette-role enums (section_registry.BACKGROUND_MODE_CHOICES
#: / BACKGROUND_PALETTE_ROLE_CHOICES). Stored values remain the existing enum
#: strings; only the label shown is translated. These never leave this
#: presentation layer — section_registry stays UI-agnostic.
_BACKGROUND_MODE_LABELS_FA = {
    "theme": "پیش‌فرض قالب",
    "palette": "رنگ از پالت فروشگاه",
    "palette_pattern": "رنگ پالت + الگو",
    "color": "رنگ دلخواه",
    "image": "تصویر",
    "pattern": "رنگ + الگو",
}
_BACKGROUND_PALETTE_ROLE_LABELS_FA = {
    "tone-1": "طیف ۱",
    "tone-2": "طیف ۲",
    "tone-3": "طیف ۳",
    "tone-4": "طیف ۴",
    "tone-5": "طیف ۵",
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


#: Pre-Task-10 remediation — the same Persian labels the legacy Appearance
#: form uses (``storefront_appearance_editor``'s ``color_field_labels``/
#: ``theme_field_labels``), reused verbatim rather than re-invented, so a
#: merchant sees the identical wording in either editor.
_COLOR_FIELD_LABELS_FA = (
    ("primary", "رنگ اصلی و دکمه‌ها"),
    ("secondary", "رنگ مکمل"),
    ("accent", "رنگ تأکیدی و تخفیف"),
    ("background", "پس‌زمینه کل سایت"),
    ("surface", "سطح عمومی و پنل‌ها"),
    ("text", "رنگ متن اصلی کل سایت"),
    ("muted", "متن کم‌رنگ"),
    ("border", "خطوط و حاشیه‌ها"),
)
_THEME_FIELD_LABELS_FA = (
    ("header_bg", "پس‌زمینه هدر"),
    ("header_text", "متن هدر"),
    ("nav_bg", "پس‌زمینه منو"),
    ("nav_text", "متن منو"),
    ("card_bg", "پس‌زمینه کارت محصول"),
    ("footer_bg", "پس‌زمینه فوتر"),
    ("footer_text", "متن فوتر"),
    ("price", "رنگ قیمت"),
)
_HEADER_TOGGLE_LABELS_FA = {
    "show_search": "نمایش جستجو",
    "show_account": "نمایش حساب کاربری",
    "show_cart": "نمایش سبد خرید",
    "show_wishlist": "نمایش علاقه‌مندی‌ها",
    "sticky": "هدر چسبان",
    "announcement_enabled": "نمایش نوار اعلان",
}
_FOOTER_TOGGLE_LABELS_FA = {
    "show_about": "درباره فروشگاه",
    "show_contact": "تماس با ما",
    "show_quick_links": "لینک‌های مفید",
    "show_categories": "دسته‌بندی‌ها",
    "show_social": "شبکه‌های اجتماعی",
    "show_trust_badges": "نشان‌های اعتماد",
    "show_payment_logos": "لوگوهای پرداخت",
    "show_newsletter": "خبرنامه",
    "show_copyright": "کپی‌رایت",
}

#: Pre-Task-10 final remediation (Gap 1) — labels for the two remaining
#: compound Header/Footer fields (extra_blocks' allowed ``type`` values).
#: ``responsive`` needs no new label dict: HEADER_RESPONSIVE_AWARE_KEYS is a
#: subset of HEADER_TOGGLE_FIELDS and FOOTER_RESPONSIVE_AWARE_KEYS equals
#: FOOTER_TOGGLE_FIELDS exactly (see models.py) — the existing toggle label
#: dicts above already cover every key.
_HEADER_EXTRA_BLOCK_TYPE_LABELS_FA = {
    "phone": "شماره تلفن",
    "social": "شبکه‌های اجتماعی",
    "cta": "دکمه فراخوان (متن + لینک)",
    "spacer": "فاصله‌گذار",
    "tagline": "شعار/تگ‌لاین",
}
_FOOTER_EXTRA_BLOCK_TYPE_LABELS_FA = {
    "custom_text": "متن دلخواه (عنوان + متن)",
    "link": "لینک تکی (برچسب + آدرس)",
    "social": "شبکه‌های اجتماعی",
}


def _build_global_design_context(draft: StorefrontLayoutVersion) -> dict:
    """R4 Task 11 (Section 23) — the Global Design panel's ENTIRE read
    projection: server-authoritative current config + registry-driven
    choice lists. No DB-backed duplicate design-option table; Templates/
    Palettes come from appearance_registry, Header/Footer variants from
    global_region_registry — never a hardcoded list here or in JS/HTML.

    Pre-Task-10 remediation — extended with the field-parity closure's
    REQUIRED EXISTING CAPABILITY fields (colors/theme overrides, structural
    appearance fields, header/footer toggles) so the Global Design panel can
    render controls for them; resolved current colors reuse the exact same
    ``appearance_registry.resolve_colors``/``resolve_theme_roles`` the public
    storefront render already uses, never a second color-resolution path."""
    appearance = draft.effective_appearance_config()
    header = draft.effective_header_config()
    footer = draft.effective_footer_config()
    return {
        "appearance": appearance,
        "header": header,
        "footer": footer,
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
        "density_choices": appearance_registry.DENSITY_CHOICES,
        "image_fit_choices": appearance_registry.IMAGE_FIT_CHOICES,
        "image_hover_choices": appearance_registry.IMAGE_HOVER_CHOICES,
        "site_content_width_choices": appearance_registry.SITE_CONTENT_WIDTH_CHOICES,
        "site_grid_density_choices": appearance_registry.SITE_GRID_DENSITY_CHOICES,
        "site_card_shadow_choices": appearance_registry.SITE_CARD_SHADOW_CHOICES,
        "site_card_hover_choices": appearance_registry.SITE_CARD_HOVER_CHOICES,
        "site_hero_style_choices": appearance_registry.SITE_HERO_STYLE_CHOICES,
        "resolved_colors": appearance_registry.resolve_colors(appearance),
        "resolved_theme_roles": appearance_registry.resolve_theme_roles(appearance),
        "color_field_labels": _COLOR_FIELD_LABELS_FA,
        "theme_field_labels": _THEME_FIELD_LABELS_FA,
        "header_toggle_fields": [
            (key, _HEADER_TOGGLE_LABELS_FA[key]) for key in HEADER_TOGGLE_FIELDS
        ],
        "footer_toggle_fields": [
            (key, _FOOTER_TOGGLE_LABELS_FA[key]) for key in FOOTER_TOGGLE_FIELDS
        ],
        #: Pre-Task-10 final remediation (Gap 1) — REQUIRED EXISTING
        #: CAPABILITY closure: announcement_links/extra_blocks (repeater) and
        #: responsive hide-on-tablet/hide-on-mobile (per-component toggle
        #: pair) for both Header and Footer. Values themselves already live
        #: in ``header``/``footer`` above (effective_header_config()/
        #: effective_footer_config() always return the full canonical shape,
        #: see models.py) — only the label/choice metadata is new here.
        "header_responsive_fields": [
            (key, _HEADER_TOGGLE_LABELS_FA[key]) for key in HEADER_RESPONSIVE_AWARE_KEYS
        ],
        "footer_responsive_fields": [
            (key, _FOOTER_TOGGLE_LABELS_FA[key]) for key in FOOTER_RESPONSIVE_AWARE_KEYS
        ],
        "header_extra_block_type_choices": [
            (block_type, _HEADER_EXTRA_BLOCK_TYPE_LABELS_FA[block_type]) for block_type in HEADER_EXTRA_BLOCK_TYPES
        ],
        "footer_extra_block_type_choices": [
            (block_type, _FOOTER_EXTRA_BLOCK_TYPE_LABELS_FA[block_type]) for block_type in FOOTER_EXTRA_BLOCK_TYPES
        ],
        # P5-W2 — occasion Theme controls. Options come from the single
        # ``theme_catalog`` authority; the current selection/intensity are read
        # from the draft's canonical manifest (never a second source).
        "theme": _build_theme_design_context(draft),
    }


def _build_theme_design_context(draft: StorefrontLayoutVersion) -> dict:
    """P5-W2 — the Theme panel's read projection. Occasions come ONLY from
    ``theme_catalog``; the active occasion/intensity come from the draft's
    canonical Store-Appearance manifest."""
    from apps.storefront_builder import theme_catalog
    from apps.storefront_builder.storefront_appearance.persistence import (
        load_store_appearance_manifest,
    )

    manifest = load_store_appearance_manifest(draft)
    current_component = manifest.selections.get("theme", "theme.none.v1")
    current_intensity = (
        (manifest.settings.get("theme") or {}).get(
            "intensity", theme_catalog.DEFAULT_THEME_INTENSITY
        )
    )
    return {
        "current_component": current_component,
        "current_intensity": current_intensity,
        "occasions": [
            {
                "occasion_key": entry.occasion_key,
                "component_key": entry.component_key,
                "label_fa": entry.label_fa,
                "tone": entry.tone,
                "is_noop": entry.is_noop,
            }
            for entry in theme_catalog.list_theme_occasions()
        ],
        "intensity_choices": list(theme_catalog.THEME_INTENSITY_CHOICES),
    }


def _build_design_lab_design_context(draft: StorefrontLayoutVersion) -> dict:
    """P5-W3 — the Design Lab panel's read projection. The randomizable family
    list + their merchant-facing Persian labels come ONLY from the canonical
    ``COMPONENT_FAMILIES`` catalog and ``design_lab_service``; the current
    per-family selection labels come from the draft's canonical manifest (never
    a second source). No component keys or seeds are surfaced to the merchant.
    """
    from apps.storefront_builder.services import design_lab_service
    from apps.storefront_builder.storefront_appearance.families import (
        COMPONENT_FAMILIES,
    )
    from apps.storefront_builder.storefront_appearance.persistence import (
        load_store_appearance_manifest,
    )
    from apps.storefront_builder.storefront_appearance.registry import get_component

    manifest = load_store_appearance_manifest(draft)

    def _label(component_key):
        component = get_component(component_key)
        return (component.label_fa if component else component_key) or component_key

    families = []
    for family_key in COMPONENT_FAMILIES:
        if family_key not in design_lab_service.DESIGN_LAB_RANDOMIZABLE_FAMILIES:
            continue
        current_key = manifest.selections.get(family_key, "")
        families.append(
            {
                "family": family_key,
                "label_fa": COMPONENT_FAMILIES[family_key].label_fa or family_key,
                "current_label": _label(current_key) if current_key else "",
            }
        )
    return {
        "families": families,
        "endpoint_url": reverse("dashboard:storefront-builder-r4-design-lab"),
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
        container_obj = item["container"]
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
            "is_active": section_obj.is_active,
            # R4 Task 7 (Batch 2) — a manually-added section (never
            # originated from a Ready Template slot) has no baseline to
            # reset to; ``preset_service.reset_section_to_baseline`` itself
            # already rejects this (``NotABaselineSectionError``), so the
            # Structure panel disables the control instead of always
            # offering a button that errors.
            "has_baseline": bool(section_obj.template_slot_key),
            # R4 Task 7 (Batch 1) — container_id/layout_key let the Structure
            # panel render ONE layout-preset control per Container (not per
            # Section) via ``{% ifchanged %}`` on container_id; None (an
            # unplaced legacy Section — should not exist after
            # ``ensure_page_containers`` above, same compatibility fallback
            # ``build_structure_projection`` itself documents) simply never
            # renders a layout control for that row.
            "container_id": container_obj.pk if container_obj is not None else None,
            "container_layout_key": container_obj.layout_key if container_obj is not None else None,
            "container_is_locked": bool(container_obj.is_locked) if container_obj is not None else False,
            # Pre-Task-10 remediation (composition parity closure) — the
            # Structure panel's per-Container settings controls read
            # projection, reusing the exact same
            # ``container_service.effective_container_settings`` the legacy
            # ``storefront_container_settings`` view already uses.
            "container_settings": (
                container_service.effective_container_settings(container_obj.settings)
                if container_obj is not None else None
            ),
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

    # Phase 5 Task 6 — the "Storefront Showcase" creation facade choices,
    # projected from the SAME legal structure_library above (never a second
    # legality/registry authority). Each choice creates one EXISTING canonical
    # section via the normal section.add mutation; no storefront_showcase key.
    showcase_choices = _build_showcase_choices(structure_library)

    # R4 Task 7 (final-review fix, IMPORTANT-2) — an empty Cell (e.g. a
    # freshly-grown container.change_layout column) has no Block, so
    # ``build_structure_projection`` above never emits a row for it —
    # without this, such a Cell would be permanently unreachable from R4.
    # A pure read, same "prefetch once, never re-query per Cell" shape as
    # ``build_structure_projection`` itself.
    empty_cells = []
    for container_obj in page.containers.order_by("order", "id").prefetch_related("cells__section", "cells__blocks"):
        if container_obj.is_locked:
            continue
        for cell_obj in sorted(container_obj.cells.all(), key=lambda c: (c.order, c.id)):
            if not container_service.blocks_from_prefetched_cell(cell_obj):
                empty_cells.append({"container_id": container_obj.pk, "cell_id": cell_obj.pk})

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
            # Phase 5 Task 6 — Storefront Showcase creation-facade choices
            # (see _build_showcase_choices): merchant-facing UX over the four
            # existing canonical sections, no new section_key.
            "showcase_choices": showcase_choices,
            "empty_cells": empty_cells,
            # R4 Task 7 (Batch 1; final-review fix, MINOR-7) — the SAME
            # preset registry AND the SAME Persian ratio labels the legacy
            # editor's layout-preset picker already uses, never a second
            # list/translation.
            "container_layout_presets": [
                (key, container_service.LAYOUT_PRESET_LABELS_FA.get(key, key))
                for key in container_service.LAYOUT_PRESETS
            ],
            # R4 Task 7 (Batch 2) — same gating condition the legacy editor's
            # own "Reset page/storefront to Template" buttons already use
            # (``editor.html``: ``draft.template_baseline_snapshot.pages|
            # dictget:page_type`` / ``draft.template_baseline_snapshot``):
            # a Draft that never had a Ready Template applied has nothing
            # to reset to, and ``preset_service`` itself already rejects
            # that case (``NoTemplateBaselineError``/``UnknownBaselinePageError``)
            # — these flags just keep the button from always erroring.
            "page_has_baseline": bool((draft.template_baseline_snapshot or {}).get("pages", {}).get(page_type)),
            "storefront_has_baseline": bool(draft.template_baseline_snapshot),
            # R4 Task 8 (Batch 1) — the content-preserving Template Switch
            # picker's data source: the SAME Ready Template registry the
            # legacy Template Gallery (``storefront_template_gallery``)
            # already lists from, never a second catalog. Each entry
            # carries key+version together (never a bare key) since
            # ``switch_template`` validates both, exactly like
            # ``appearance.template.apply`` already does for the same
            # stale-definition-under-a-client reason.
            "ready_templates": [
                {"key": preset.key, "version": preset.version, "label": preset.label_fa}
                for preset in layout_preset_registry.list_ready_templates()
            ],
            "current_template_key": variant_contract.validate_template_provenance(
                draft.template_provenance,
            )["template"]["key"],
            "global_design": _build_global_design_context(draft),
            # P5-W3 — Design Lab / Random Mix panel read projection.
            "design_lab": _build_design_lab_design_context(draft),
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


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_design_lab(request):
    """P5-W3 — the transient Design Lab operations endpoint. READ-ONLY: it never
    writes anything (no draft.save, no history, no revision change). It runs the
    canonical ``design_lab_service`` server-side (locks and family eligibility
    are enforced HERE, not just in JS) and returns:

      * an opaque preview ``token`` for the EXISTING ``storefront_preview``
        ``?design_lab=`` route (never a component key the client fabricated);
      * the server-computed Compare-with-Base ``diffs`` (Persian labels);
      * the current ``locked_families`` and ``base_revision``.

    The real persistence happens ONLY on the separate explicit Apply, through
    the ONE canonical ``design_lab.apply_candidate`` mutation. Store identity is
    resolved from the request (tenant boundary), never from client input.
    """
    from apps.storefront_builder.services import design_lab_service

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

    action = payload.get("action")
    if action not in (
        "random_mix",
        "randomize_one",
        "compare",
        "return_to_dna",
        "reset",
        "remove_theme",
        "apply_payload",
    ):
        return JsonResponse({"ok": False, "code": "invalid_action"}, status=400)

    draft = layout_service.get_or_create_draft(store, user=request.user)

    # apply_payload: materialise the ONE canonical design_lab.apply_candidate
    # mutation from the current transient token, server-side, so the client
    # never has to hold or transmit component keys. This still WRITES NOTHING —
    # the actual persistence happens only when the client enqueues the returned
    # mutation through the canonical mutation endpoint (apply_mutation).
    if action == "apply_payload":
        from apps.storefront_builder.storefront_appearance.contracts import (
            InvalidStoreAppearanceContract,
        )

        token = payload.get("candidate_token")
        if not token:
            return JsonResponse({"ok": False, "code": "no_candidate"}, status=400)
        # Precise decode/validation exceptions only (MINOR): a malformed/tampered
        # token or a canonical contract violation is a controlled 400; any other
        # (programming) error propagates and fails loudly, never masked as
        # "invalid_candidate".
        try:
            candidate = design_lab_service.decode_candidate_token(token)
        except ValueError:
            return JsonResponse({"ok": False, "code": "invalid_candidate"}, status=400)
        # Real-flow stale preflight (Architect IMPORTANT 3): the candidate is
        # bound to the Draft + revision it was generated against. If the Draft
        # moved, reject as stale BEFORE producing the mutation — never silently
        # rebase the old candidate onto the newer Draft. (The canonical
        # apply_mutation boundary remains the final transactional enforcement.)
        if design_lab_service.candidate_is_stale(draft, candidate):
            return JsonResponse(
                {
                    "ok": False,
                    "code": "stale_candidate",
                    "current_revision": draft.edit_revision,
                },
                status=409,
            )
        try:
            design_lab_service.resolve_candidate_appearance(draft, candidate)
        except InvalidStoreAppearanceContract:
            return JsonResponse({"ok": False, "code": "invalid_candidate"}, status=400)
        return JsonResponse(
            {
                "ok": True,
                "mutation": design_lab_service.candidate_apply_mutation(
                    candidate, draft_id=draft.pk
                ),
                "base_revision": candidate.base_revision,
            }
        )

    # Locked families are transient exploration locks (client-supplied list of
    # family keys) — never persisted, never a DB field. Only eligible families
    # can be locked/randomized; unknown keys are ignored (fail-safe).
    raw_locked = payload.get("locked_families") or []
    if not isinstance(raw_locked, list):
        return JsonResponse({"ok": False, "code": "invalid_locked_families"}, status=400)
    locked_families = {
        f
        for f in raw_locked
        if isinstance(f, str)
        and f in design_lab_service.DESIGN_LAB_RANDOMIZABLE_FAMILIES
    }

    # Rebuild the prior candidate (if any) purely from its opaque token so
    # repeated actions accumulate transiently without any server state.
    from apps.storefront_builder.storefront_appearance.contracts import (
        InvalidStoreAppearanceContract,
    )

    # Rebuild the prior candidate (if any) purely from its signed token, so
    # chained actions evolve the CURRENT candidate transiently with no server
    # state. A tampered/expired token is rejected loudly rather than silently
    # discarded (it carries correctness-critical Base/revision truth).
    prior_token = payload.get("candidate_token")
    prior_candidate = None
    if prior_token:
        try:
            prior_candidate = design_lab_service.decode_candidate_token(prior_token)
        except ValueError:
            return JsonResponse({"ok": False, "code": "invalid_candidate"}, status=400)

    if action == "randomize_one":
        family = payload.get("family")
        if (
            not isinstance(family, str)
            or family not in design_lab_service.DESIGN_LAB_RANDOMIZABLE_FAMILIES
        ):
            return JsonResponse({"ok": False, "code": "invalid_family"}, status=400)

    try:
        if action == "reset":
            candidate = design_lab_service.reset_candidate(draft)
        elif action == "return_to_dna":
            base = prior_candidate or design_lab_service.reset_candidate(draft)
            candidate = design_lab_service.return_to_original_dna(draft, base)
        elif action == "remove_theme":
            base = prior_candidate or design_lab_service.reset_candidate(draft)
            candidate = design_lab_service.remove_theme(base)
        elif action == "compare":
            candidate = prior_candidate or design_lab_service.reset_candidate(draft)
        elif action == "randomize_one":
            # Chain from the CURRENT candidate (IMPORTANT 2): only the requested
            # family may change; all other candidate families are preserved.
            candidate = design_lab_service.generate_candidate(
                draft,
                current_candidate=prior_candidate,
                randomize_families={payload["family"]},
                locked_families=locked_families,
                seed=_random_design_lab_seed(),
            )
        else:  # random_mix
            # Chain from the CURRENT candidate: re-randomize all UNLOCKED
            # eligible families of the current candidate; locked families keep
            # their CURRENT candidate value.
            candidate = design_lab_service.generate_candidate(
                draft,
                current_candidate=prior_candidate,
                randomize_families=set(
                    design_lab_service.DESIGN_LAB_RANDOMIZABLE_FAMILIES
                ),
                locked_families=locked_families,
                seed=_random_design_lab_seed(),
            )
        # Server-authoritative validation of the resolved candidate (fail
        # closed): a candidate that cannot resolve through the canonical
        # contract is never returned to the client. Only the canonical contract
        # violation becomes a 400; unexpected errors propagate (fail loudly).
        design_lab_service.resolve_candidate_appearance(draft, candidate)
    except InvalidStoreAppearanceContract:
        return JsonResponse({"ok": False, "code": "invalid_candidate"}, status=400)

    diffs = design_lab_service.compare_with_base(candidate)
    family_labels = design_lab_service.all_family_labels(candidate)
    return JsonResponse(
        {
            "ok": True,
            "token": design_lab_service.encode_candidate_token(candidate),
            "diffs": diffs,
            "locked_families": sorted(candidate.locked_families),
            "base_revision": candidate.base_revision,
            "draft_id": candidate.draft_id,
            # Merchant-facing Persian labels for EVERY family (Architect
            # IMPORTANT 2) — never raw component keys. The client refreshes
            # ALL rows from these, not just the ones present in ``diffs``, so a
            # family that returns to its Base value still gets a correct
            # current label instead of a stale one.
            "candidate_labels": {
                family: value["candidate_label"] for family, value in family_labels.items()
            },
            "base_labels": {
                family: value["base_label"] for family, value in family_labels.items()
            },
        }
    )


def _random_design_lab_seed() -> int:
    """A fresh nondeterministic seed for an interactive merchant Randomize
    click. Deterministic seeding is used only in tests (which pass an explicit
    seed into ``generate_candidate``); the merchant never sees it."""
    import secrets

    return secrets.randbelow(2**31)


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

    # R4 Task 7 (Batch 3) — section media CRUD reachability. The generic
    # media system (``media_views.py``) is real, shared, and already
    # canonical — the R4 Inspector previously had NO link to it anywhere,
    # so a merchant editing hero_banner/image_slider/multi_banner/
    # single_banner/story_rail in R4 had no way to manage the underlying
    # slides/banners/story items without already knowing the legacy URL.
    # Never a new media UI/authority — this only ever links to the
    # existing, unmodified legacy management screens.
    media_kind = media_views.media_kind_for_section_key(section.section_key)
    media_manage_url = None
    media_config = None
    media_items = None
    if media_kind is not None:
        media_manage_url = reverse(
            "dashboard:storefront-builder-section-media-list",
            kwargs={"pk": section.pk, "kind": media_kind},
        )
        media_label_plural = media_views.media_label_for_kind(media_kind)
        # Phase 5 Task 4 (remediation R1a) — R4-native media editing. Instead of
        # only linking out to the legacy screen, the Inspector embeds the
        # canonical media manager inline (the same media_views models/CRUD/
        # authority; never a second media system). The add/edit form and every
        # CRUD reswap happen through the existing media endpoints via htmx,
        # staying inside R4.
        media_config = media_views.media_config_for_kind(media_kind)
        media_items = list(
            media_config["model"].objects.filter(section=section).order_by("display_order", "id")
        )
    else:
        media_label_plural = None

    schema = definition.settings_schema
    if schema is None:
        # A media-only family (story_rail/single_banner today) has nothing
        # for the normal schema-driven Inspector to render at all — render
        # the minimal media-only partial instead of 404ing the whole
        # Inspector. A section with neither a schema NOR a media kind
        # (context-aware/domain-owned families like product_main) still
        # correctly 404s: there is genuinely nothing to show.
        if media_manage_url is None:
            raise Http404
        return render(
            request,
            "dashboard/storefront_builder/r4/partials/section_inspector_media_only.html",
            {
                "section": section,
                "definition": definition,
                "media_manage_url": media_manage_url,
                "media_label_plural": media_label_plural,
                # Names the shared media manager body partial expects directly.
                "kind": media_kind,
                "config": media_config,
                "items": media_items,
            },
        )

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

    # Pre-Task-10 corrective closure — a menu_picker field's dropdown is
    # ALWAYS Store-scoped at render time, exactly like the legacy settings
    # form's own ``all_menus`` context helper (``views.py``) — never a
    # foreign Store's Menu is offered to pick from. Computed generically for
    # any schema (menu_picker is not quick_links-specific in principle),
    # same "only if this field type is present" pattern resource_source
    # uses above.
    menu_choices = None
    for field in schema.fields:
        if field.field_type != "menu_picker":
            continue
        menu_choices = list(
            Menu.objects.filter(store=store, is_active=True).order_by("title")
        )

    # Phase 5 Task 4B — a ``background`` field's picker needs the SAME
    # Store-scoped substrate the legacy background control already used:
    # the shared pattern registry and the merchant's own Media Library
    # assets. Reuse the canonical ``views._background_picker_context`` (never
    # a second media library / upload system); mode/palette-role choices come
    # straight from ``section_registry`` with only the label translated. Built
    # once, only when a background field is actually present — the same
    # "only if this field type is present" pattern resource_source/menu_picker
    # use above. The CURRENT value is projected the same way every other field
    # is (``field_values`` above already resolved it from the section's
    # validated settings, which always carry a ``background`` block via the
    # ``_with_background`` wrapper).
    background_context = None
    if any(field.field_type == "background" for field in schema.fields):
        from .views import _background_picker_context

        picker_context = _background_picker_context(request, section)
        background_context = {
            "mode_choices": [
                (value, _BACKGROUND_MODE_LABELS_FA.get(value, value))
                for value in section_registry.BACKGROUND_MODE_CHOICES
            ],
            "palette_role_choices": [
                (value, _BACKGROUND_PALETTE_ROLE_LABELS_FA.get(value, value))
                for value in section_registry.BACKGROUND_PALETTE_ROLE_CHOICES
            ],
            "patterns": picker_context["background_patterns"],
            "media_assets": picker_context["background_media_assets"],
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
            "media_manage_url": media_manage_url,
            "media_label_plural": media_label_plural,
            "media_kind": media_kind,
            "media_config": media_config,
            "media_items": media_items,
            "menu_choices": menu_choices,
            "background_context": background_context,
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


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_discard(request):
    """R4 Task 7 (Batch 2) — discard the entire Draft. Same JSON contract
    shape as ``storefront_r4_publish`` (base_revision-gated, ``{ok: true}``
    on success) — the client reloads on success exactly like Publish/Undo/
    Redo already do, since discarding replaces the Draft's identity."""
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
        r4_mutation_service.discard_draft(store=store, actor=request.user, base_revision=base_revision)
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True})


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_reset_page(request):
    """R4 Task 7 (Batch 2) — RESET PAGE (checkpoint-then-replace). Same
    contract shape as Publish/Discard above; the replaced page_type comes
    from the request body, validated the same way ``section.add`` already
    validates one."""
    from .models import StorefrontPage

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

    page_type = payload.get("page_type")
    if page_type not in StorefrontPage.PageType.values:
        return JsonResponse({"ok": False, "code": "invalid_page_type"}, status=400)

    try:
        r4_mutation_service.reset_page(
            store=store, actor=request.user, base_revision=base_revision, page_type=page_type,
        )
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True})


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_reset_storefront(request):
    """R4 Task 7 (Batch 2) — RESET STOREFRONT (checkpoint-then-replace the
    whole Draft). Same contract shape as ``storefront_r4_reset_page``."""
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
        r4_mutation_service.reset_storefront(store=store, actor=request.user, base_revision=base_revision)
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True})


def _read_class_c_precondition(payload):
    """P5-W5A Independent-Review repair — Class C's precondition binds to
    BOTH the expected Draft identity (``base_draft_id``) and its revision
    (``base_revision``), never revision alone: ``edit_revision`` defaults
    to 0 on every newly created Draft row, so a revision-only check is
    vulnerable to an ABA hazard where a stale client's captured revision
    coincidentally matches a DIFFERENT Draft that replaced the one it
    actually observed. Valid shapes:

    - ``base_draft_id=null`` AND ``base_revision=null`` — the client
      believes no Draft is currently active.
    - ``base_draft_id=<positive int>`` AND ``base_revision=<non-negative
      int>`` — the client believes exactly that Draft is active at
      exactly that revision.

    Any other combination (one null paired with a non-null, a negative or
    non-integer id/revision) is an invalid precondition shape. Returns
    ``(True, draft_id, base_revision)`` on a valid shape, ``(False, None,
    None)`` otherwise."""
    if "base_draft_id" not in payload or "base_revision" not in payload:
        return False, None, None
    draft_id = payload["base_draft_id"]
    base_revision = payload["base_revision"]
    if draft_id is None and base_revision is None:
        return True, None, None
    if draft_id is None or base_revision is None:
        return False, None, None
    if not _is_strict_int(draft_id) or draft_id <= 0:
        return False, None, None
    if not _is_strict_int(base_revision) or base_revision < 0:
        return False, None, None
    return True, draft_id, base_revision


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_restore(request, pk):
    """P5-W5A Class C — the canonical R4-safe Restore Version entry point.
    Same contract shape as every other whole-Draft-identity-replacing R4
    action above; delegates to ``r4_mutation_service.restore_version_safe``,
    which itself delegates to the existing, unmodified ``layout_service.
    restore_version()`` — never a second restore implementation. The
    legacy ``storefront_restore`` POST remains the rollback path for a
    Store explicitly pinned to ``r4_editor_enabled=False`` only."""
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

    valid, base_draft_id, base_revision = _read_class_c_precondition(payload)
    if not valid:
        return JsonResponse({"ok": False, "code": "invalid_precondition"}, status=400)

    try:
        r4_mutation_service.restore_version_safe(
            store=store, actor=request.user,
            base_draft_id=base_draft_id, base_revision=base_revision, version_id=pk,
        )
    except RateLimitExceeded:
        # P5-W5A Independent-Review repair — the existing, unmodified
        # ``storefront_layout.restore`` limit (enforced inside
        # ``layout_service.restore_version()``, before any Draft row is
        # touched) previously escaped this JSON endpoint as an
        # unhandled 500; translated to a controlled 429, no new limiter.
        return JsonResponse({"ok": False, "code": "rate_limited"}, status=429)
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {
                "ok": False, "code": "stale_revision",
                "current_revision": exc.current_revision,
                "current_draft_id": exc.current_draft_id,
            },
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True})


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_apply_industry_layout(request):
    """P5-W5A Class C — the canonical R4-safe Apply Industry Layout entry
    point. Delegates to ``r4_mutation_service.apply_industry_layout_safe``,
    which itself delegates to the existing, unmodified ``layout_service.
    apply_industry_layout()`` — never a second implementation. The legacy
    ``storefront_apply_industry_layout`` POST remains the rollback path
    for a Store explicitly pinned to ``r4_editor_enabled=False`` only."""
    store = resolve_store_for_service(request)
    layout = layout_service.get_or_create_layout(store)
    if not layout.r4_editor_enabled:
        raise Http404
    if getattr(store, "industry_installation", None) is None:
        # Same convention the legacy ``storefront_apply_industry_layout``
        # already uses for this exact condition — a Store with no
        # installation of its own has nothing to apply, tenant-scoped.
        raise Http404

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "code": "malformed_json"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "code": "invalid_request_shape"}, status=400)

    valid, base_draft_id, base_revision = _read_class_c_precondition(payload)
    if not valid:
        return JsonResponse({"ok": False, "code": "invalid_precondition"}, status=400)

    # Strict JSON-boolean check — never a truthy-string coercion. A client
    # explicitly confirming "never silently overwrite" must send the JSON
    # boolean ``true``; anything else (including the string "false", which
    # ``bool(...)`` would otherwise coerce to True) is rejected outright.
    force_raw = payload.get("force", False)
    if not isinstance(force_raw, bool):
        return JsonResponse({"ok": False, "code": "invalid_force"}, status=400)
    force = force_raw

    try:
        r4_mutation_service.apply_industry_layout_safe(
            store=store, actor=request.user,
            base_draft_id=base_draft_id, base_revision=base_revision, force=force,
        )
    except RateLimitExceeded:
        # P5-W5A Independent-Review repair — the existing, unmodified
        # ``storefront_layout.new_draft`` limit (enforced inside
        # ``layout_service.apply_industry_layout()``, before any Draft
        # row is touched) previously escaped this JSON endpoint as an
        # unhandled 500; translated to a controlled 429, no new limiter.
        return JsonResponse({"ok": False, "code": "rate_limited"}, status=429)
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {
                "ok": False, "code": "stale_revision",
                "current_revision": exc.current_revision,
                "current_draft_id": exc.current_draft_id,
            },
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True})


@require_POST
@staff_required
@permission_required(STOREFRONT_LAYOUT_MANAGE)
def storefront_r4_switch_template(request):
    """R4 Task 8 (Batch 1) — content-preserving Template Switch. Same
    contract shape as Publish/Discard/Reset-page/Reset-storefront above
    (base_revision-gated, ``{ok: true}`` on success, client reloads on
    success since this replaces the Draft's identity); the target Ready
    Template comes from the request body, validated the SAME way
    ``appearance.template.apply`` already validates one (exact key+version
    match against the live registry, never a bare key alone — a stale
    client offering a Template whose definition has since changed under
    it must be rejected, not silently applied against a mismatched
    recipe)."""
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

    template_key = payload.get("template_key")
    template_version = payload.get("template_version")

    try:
        r4_mutation_service.switch_template(
            store=store, actor=request.user, base_revision=base_revision,
            template_key=template_key, template_version=template_version,
        )
    except r4_mutation_service.R4StaleRevision as exc:
        return JsonResponse(
            {"ok": False, "code": "stale_revision", "current_revision": exc.current_revision},
            status=409,
        )
    except r4_mutation_service.R4MutationError as exc:
        return JsonResponse({"ok": False, "code": str(exc)}, status=400)

    return JsonResponse({"ok": True})
