"""Neutral, read-only projection of the ONE Ready Template catalog into display cards.

Shared by every surface that shows Ready Templates (Merchant Admin Template Gallery, the R4
Design Studio gallery and the owner-onboarding Template step). It owns no catalog and no
thumbnail logic of its own: presets come from ``layout_preset_registry.list_selectable_templates()``
(seller-facing galleries, ``SCOPE_GALLERY``) or ``list_ready_templates()`` (the public landing site's
display catalog, ``SCOPE_PUBLIC``) and screenshots/thumbnails from ``template_preview_service``
(``resolve_real_screenshot`` with the canonical SVG fallback). Pure reads — never writes.
"""

from django.templatetags.static import static

from .. import appearance_registry, global_region_registry, layout_preset_registry, template_gallery_policy
from . import template_preview_service


def preset_would_replace_content(draft, preset) -> bool:
    """آیا اعمالِ این Preset، محتوایِ section-محورِ موجودِ Draft را برایِ حداقل یکی از
    صفحاتی که Preset پوشش می‌دهد جایگزین می‌کند — همان شرطِ
    ``storefront_apply_layout_preset`` (یک تابعِ مشترک، نه یک محاسبه‌ی دوم). بدونِ Draft
    (مثلاً گالریِ آنبوردینگ) همیشه ``False``."""
    if draft is None:
        return False
    return any(draft.get_page(page_type).sections.exists() for page_type in preset.pages)


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
    screenshot_relpath = template_preview_service.resolve_real_screenshot(preset)
    if screenshot_relpath is not None:
        return {"thumbnail_kind": "screenshot", "thumbnail_url": static(screenshot_relpath), "thumbnail_svg": ""}
    return {
        "thumbnail_kind": "svg", "thumbnail_url": "",
        "thumbnail_svg": template_preview_service.resolve_gallery_thumbnail(preset),
    }


def build_ready_template_card(draft, preset, *, is_current):
    """One merchant-facing Ready Template card for an exact registered preset
    version: its real preview thumbnail, default palette swatch and global
    region labels. Pure read. ``draft`` may be ``None`` (display-only surfaces)."""
    return {
        "preset": preset,
        "is_current": is_current,
        "would_replace_existing_content": preset_would_replace_content(draft, preset),
        "palette_swatch": _palette_swatch(preset),
        **_thumbnail_fields(preset),
        "header_variant_label": _variant_label(
            global_region_registry.GLOBAL_HEADER_REGION, (preset.header or {}).get("header_variant"),
        ),
        "footer_variant_label": _variant_label(
            global_region_registry.GLOBAL_FOOTER_REGION, (preset.footer or {}).get("footer_variant"),
        ),
    }


#: Two DIFFERENT questions that must never control each other:
#:  * SCOPE_PUBLIC  — "which Ready Templates does the platform DISPLAY?" (the public landing site's catalog). Every registered Ready Template,
#:    display-only: nothing can be chosen from it, so the seller-choice restriction does not apply. This is the DEFAULT, because the public
#:    landing site calls this builder without a scope.
#:  * SCOPE_GALLERY — "which Ready Templates may a seller CHOOSE?" (onboarding gallery, Studio gallery). The owner-restricted subset
#:    (``template_gallery_policy``) plus the pinned «current» card. EVERY seller-facing caller must pass this explicitly — enforced by
#:    ``test_template_catalog_scope`` (an AST guard over all production call sites).
SCOPE_PUBLIC = "public"
SCOPE_GALLERY = "gallery"


def build_ready_template_cards(draft, *, current_template_key, current_template_version, scope=SCOPE_PUBLIC):
    """Read projection of the ONE Ready Template catalog. Pure read — never a second catalog/registry.

    ``scope=SCOPE_GALLERY`` (seller-facing galleries): every card comes from ``layout_preset_registry.list_selectable_templates()`` (the
    owner-approved subset of the latest merchant-facing versions, ``template_gallery_policy``).
    ``scope=SCOPE_PUBLIC`` (default; the public landing site): every registered Ready Template via ``list_ready_templates()`` — the gallery
    restriction limits what a seller may CHOOSE, never what the platform shows publicly.

    A card is "current" only for the Draft's EXACT applied template identity
    (key AND version from its provenance). A Draft on an older historical
    version of the same key therefore never marks the newer catalog card as
    current; that card stays available for an explicit switch.

    A Store whose applied template is NOT in the selectable subset keeps its identity: the exact applied
    version is pinned as an extra «current» card (``is_hidden_current``) — it is shown, never replaced and never
    offered to anyone else (gallery scope only; the public display catalog has no seller choice and no pinned card)."""
    if scope not in (SCOPE_PUBLIC, SCOPE_GALLERY):
        raise ValueError(f"unknown catalog scope: {scope!r}")
    presets = layout_preset_registry.list_selectable_templates() if scope == SCOPE_GALLERY else layout_preset_registry.list_ready_templates()
    cards = [
        build_ready_template_card(
            draft,
            preset,
            is_current=bool(
                current_template_key
                and current_template_version
                and preset.key == current_template_key
                and preset.version == current_template_version
            ),
        )
        for preset in presets
    ]
    if scope == SCOPE_GALLERY and current_template_key and current_template_version and not any(card["is_current"] for card in cards):
        applied = layout_preset_registry.get_layout_preset_version(current_template_key, current_template_version)
        if applied is not None and applied.is_ready_template and not template_gallery_policy.is_selectable_key(applied.key):
            pinned = build_ready_template_card(draft, applied, is_current=True)
            pinned["is_hidden_current"] = True
            cards.append(pinned)
    return cards


def resolve_applied_template_card(draft, cards, *, current_template_key, current_template_version):
    """The Draft's applied Ready Template as a display card, resolved by its
    EXACT provenance identity: the current catalog card when the Draft is on
    the latest version, otherwise the exact historical version from the
    canonical ``get_layout_preset_version``. ``None`` when no template is
    applied or the exact version cannot be resolved — never guesses that the
    latest version is the applied one. Pure read; never repairs the Draft."""
    current_card = next((card for card in cards if card["is_current"]), None)
    if current_card is not None:
        return current_card
    if not (current_template_key and current_template_version):
        return None
    historical = layout_preset_registry.get_layout_preset_version(
        current_template_key, current_template_version,
    )
    if historical is None:
        return None
    return build_ready_template_card(draft, historical, is_current=True)
