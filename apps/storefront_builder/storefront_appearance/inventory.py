"""Deterministic A8 Ready Template diversity and component-coverage inventory."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from .families import COMPONENT_FAMILIES


A8_ADVERTISED_COMPONENTS_BY_FAMILY = {
    "header": (
        "header.editorial_row.v1",
        "header.marketplace_search.v1",
        "header.centered_brand.v1",
        "header.floating_compact.v1",
        "header.compact_drawer.v1",
        "header.promo_bar.v1",
        "header.community_shortcuts.v1",
        "header.overlay_transparent.v1",
        "header.editorial_masthead.v1",
        "header.compact_menu.v1",
        "header.category_tabs.v1",
        "header.playful_canopy.v1",
    ),
    "mega_menu": ("mega_menu.none.v1",),
    "hero": (
        "hero.none.v1",
        "hero.immersive.v1",
        "hero.editorial_split.v1",
        "hero.promo_bento.v1",
        "hero.typographic.v1",
        "hero.product_focus.v1",
        "hero.image_collage.v1",
        "hero.side_offer_slider.v1",
        "hero.media_feature.v1",
        "hero.quiet.v1",
        "hero.search_first.v1",
        "hero.campaign_mosaic.v1",
        "hero.social_gallery.v1",
    ),
    "layout": (
        "layout.two_column.v1",
        "layout.three_column.v1",
        "layout.four_column.v1",
        "layout.dense_five.v1",
        "layout.horizontal_rail.v1",
        "layout.catalog_list.v1",
        "layout.bento_grid.v1",
        "layout.featured_split.v1",
        "layout.editorial_zigzag.v1",
    ),
    "product_view": (
        "product_view.standard_grid.v1",
        "product_view.carousel.v1",
        "product_view.dense_grid.v1",
        "product_view.editorial_grid.v1",
        "product_view.catalog_list.v1",
        "product_view.bento.v1",
        "product_view.featured_wall.v1",
    ),
    "card": (
        "card.standard.v1",
        "card.marketplace_price.v1",
        "card.editorial_minimal.v1",
        "card.retail_row.v1",
        "card.luxury_dark.v1",
        "card.soft_capsule.v1",
        "card.beauty_glass.v1",
        "card.paper_frame.v1",
        "card.price_first.v1",
        "card.portrait_round.v1",
        "card.catalog_index.v1",
        "card.shipping_label.v1",
        "card.shelf_editorial.v1",
        "card.technical_spec.v1",
        "card.tech_neon.v1",
        "card.bold_outline.v1",
    ),
    "badge": ("badge.none.v1", "badge.sale.v1"),
    "motion": ("motion.none.v1", "motion.subtle.v1", "motion.dynamic.v1"),
    "footer": (
        "footer.minimal.v1",
        "footer.marketplace_columns.v1",
        "footer.editorial_wordmark.v1",
        "footer.brand_story.v1",
        "footer.bold_columns.v1",
        "footer.centered.v1",
        "footer.app_download.v1",
        "footer.playful_wave.v1",
    ),
    "bottom_nav": (
        "bottom_nav.four_item.v1",
        "bottom_nav.five_item.v1",
        "bottom_nav.raised_cart.v1",
        "bottom_nav.floating_dock.v1",
        "bottom_nav.glass_dock.v1",
        "bottom_nav.minimal_icons.v1",
        "bottom_nav.wide_cart.v1",
    ),
    # P5-W2 — Ready Templates advertise (and use) only the Theme no-op:
    # occasion themes are merchant-selected and independent of the template
    # catalog, so no Ready Template auto-assigns an occasion. The occasion
    # components still live in the central registry via the theme_catalog
    # adapter; they are simply not part of the A8 recipe coverage surface.
    "theme": ("theme.none.v1",),
}

A8_ADVERTISED_COMPONENT_KEYS = frozenset(
    component_key
    for component_keys in A8_ADVERTISED_COMPONENTS_BY_FAMILY.values()
    for component_key in component_keys
)
A8_COMPONENT_COVERAGE_EXCEPTIONS: tuple[str, ...] = ()


def _freeze(value):
    if isinstance(value, Mapping):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_freeze(item) for item in value))
    return value


def recipe_signature(preset) -> tuple:
    """Return palette/font-independent structural DNA for one recipe."""

    selections = preset.store_appearance["selections"]
    component_axes = tuple(selections[family_key] for family_key in COMPONENT_FAMILIES)
    home = tuple(
        (
            entry.section_key,
            _freeze(entry.settings or {}),
            entry.row_key,
            entry.row_span,
            _freeze(entry.container_settings or {}),
        )
        for entry in preset.pages.get("home", ())
    )
    return component_axes + (home,)


def component_coverage(presets: Iterable) -> dict[str, dict[str, int]]:
    """Count recipe selections per family/component in stable registry order."""

    counters = {
        family_key: Counter(
            {component_key: 0 for component_key in A8_ADVERTISED_COMPONENTS_BY_FAMILY[family_key]}
        )
        for family_key in COMPONENT_FAMILIES
    }
    for preset in presets:
        for family_key, component_key in preset.store_appearance["selections"].items():
            counters[family_key][component_key] += 1
    return {
        family_key: {
            component_key: counters[family_key][component_key]
            for component_key in sorted(counters[family_key])
        }
        for family_key in COMPONENT_FAMILIES
    }


def duplicate_recipe_signatures(presets: Iterable) -> tuple[tuple[str, ...], ...]:
    grouped: dict[tuple, list[str]] = {}
    for preset in presets:
        grouped.setdefault(recipe_signature(preset), []).append(preset.key)
    return tuple(
        tuple(keys)
        for keys in grouped.values()
        if len(keys) > 1
    )
