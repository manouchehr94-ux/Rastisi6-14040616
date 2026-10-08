"""Neutral, read-only projection of the ONE Ready Template catalog into display cards.

Shared by every surface that shows Ready Templates (Merchant Admin Template Gallery, the R4
Design Studio gallery and the owner-onboarding Template step). It owns no catalog and no
thumbnail logic of its own: presets come from ``layout_preset_registry.list_ready_templates()``
and screenshots/thumbnails from ``template_preview_service`` (``resolve_real_screenshot`` with the
canonical SVG fallback). Pure reads — never writes.
"""

from django.templatetags.static import static

from .. import appearance_registry, global_region_registry, layout_preset_registry
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


def build_ready_template_cards(draft, *, current_template_key, current_template_version):
    """Read projection of the ONE Ready Template catalog for merchant-facing
    galleries. Pure read — never a second catalog/registry: every card comes
    from ``layout_preset_registry.list_ready_templates()`` (the latest
    merchant-facing version per key).

    A card is "current" only for the Draft's EXACT applied template identity
    (key AND version from its provenance). A Draft on an older historical
    version of the same key therefore never marks the newer catalog card as
    current; that card stays available for an explicit switch."""
    return [
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
        for preset in layout_preset_registry.list_ready_templates()
    ]


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
