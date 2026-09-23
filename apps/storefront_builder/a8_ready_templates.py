"""The platform-owned A8 catalog of exactly 50 complete Ready Templates."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class _RecipeSpec:
    key: str
    version: str
    label_fa: str
    header: str
    hero: str
    layout: str
    product_view: str
    card: str
    badge: str
    motion: str
    footer: str
    bottom_nav: str
    palette: str
    font: str
    density: str
    width: int
    radius: int
    composition: tuple[str, ...]


_HERO_VARIANTS = {
    "none": "overlay",
    "immersive": "luxury_showcase",
    "editorial_split": "split",
    "promo_bento": "chocolate_carousel",
    "typographic": "split",
    "product_focus": "beauty_editorial",
    "image_collage": "atelier_triptych",
    "side_offer_slider": "chocolate_carousel",
    "media_feature": "overlay",
    "quiet": "split",
    "search_first": "split",
    "campaign_mosaic": "atelier_triptych",
    "social_gallery": "atelier_triptych",
}

_CATEGORY_PRESENTATIONS = {
    "circular_categories": "circular",
    "tile_categories": "grid",
    "arch_categories": "atelier_mosaic",
    "chip_categories": "carousel",
    "indexed_categories": "fashion_flat",
}

_STATIC_SECTIONS = {
    "ticker": "announcement_bar",
    "brand_story": "image_text",
    "editorial_note": "rich_text",
    "service_strip": "trust_features",
    "trust_features": "trust_features",
    "brands": "brand_carousel",
    "testimonials": "testimonials",
    "newsletter": "newsletter",
    "community_gallery": "story_rail",
    # P5-W4B — the only genuinely new token this curation pass needs;
    # story_rail/brand_carousel reuse the existing community_gallery/brands
    # rows above instead of gaining a redundant second alias.
    "collection_tiles": "collection_tiles",
}

# ==================================================================
# Architecture Convergence / Phase 1 — RATIFIED SEMANTIC MAPPING.
#
# This is the ONE canonical composition-token -> semantic-role mapping for the
# home page, and the (page_type, section_key) -> role mapping for non-home
# pages. It lives HERE, with the A8 recipe construction authority, and is never
# reproduced independently in a service (the master architectural rule: one
# canonical source of truth per concept). ``_home``/``_common_pages`` below
# stamp each built ``PresetSectionEntry`` with its ratified role, so every A8
# Ready Template (current and every retained historical version) carries an
# explicit, per-page-unique semantic identity.
#
# Note that the same section_key legitimately carries DIFFERENT roles across
# tokens (``product_grid`` -> products.primary vs ``sale_products`` ->
# products.sale, both ``product_section``/``catalog_product_wall``), and several
# tokens legitimately collapse onto ONE role (every category presentation ->
# categories.primary). Identity is the ROLE, never the section_key or the list
# index.
# ==================================================================
HOME_TOKEN_SEMANTIC_ROLE = {
    "hero": "hero.primary",
    "circular_categories": "categories.primary",
    "tile_categories": "categories.primary",
    "arch_categories": "categories.primary",
    "chip_categories": "categories.primary",
    "indexed_categories": "categories.primary",
    "product_grid": "products.primary",
    "product_list": "products.primary",
    "product_rail": "products.primary",
    "bento_products": "products.primary",
    "featured_products": "products.featured",
    "sale_products": "products.sale",
    "ticker": "announcement.primary",
    "brand_story": "brand_story.primary",
    "editorial_note": "editorial_note.primary",
    "service_strip": "trust.primary",
    "trust_features": "trust.primary",
    "brands": "brands.primary",
    "testimonials": "testimonials.primary",
    "newsletter": "newsletter.primary",
    "community_gallery": "community.gallery",
    "collection_tiles": "collection.tiles",
}

NON_HOME_SECTION_SEMANTIC_ROLE = {
    ("product_detail", "product_main"): "product.main",
    ("product_detail", "product_description"): "product.description",
    ("product_detail", "related_products"): "product.related",
    ("listing", "product_listing"): "products.listing",
    ("collection", "collection_header"): "collection.header",
    ("collection", "collection_products"): "collection.products",
    ("search", "product_listing"): "products.search",
    ("cart", "cart_items"): "cart.items",
    ("cart", "cart_summary"): "cart.summary",
}


def _with_role(entry: "PresetSectionEntry", role: str) -> "PresetSectionEntry":
    return dataclasses.replace(entry, semantic_slot_key=role)

def _common_entry(page_type: str, section_key: str, settings: dict | None = None) -> "PresetSectionEntry":
    """Build a non-home recipe row already stamped with its ratified role
    (``NON_HOME_SECTION_SEMANTIC_ROLE``) — the same canonical mapping authority
    used for the home page, so search vs listing (both ``product_listing``)
    resolve to distinct roles by page even though they share a section_key."""
    role = NON_HOME_SECTION_SEMANTIC_ROLE[(page_type, section_key)]
    return PresetSectionEntry(section_key, settings, semantic_slot_key=role)


def _common_pages() -> dict[str, tuple[PresetSectionEntry, ...]]:
    return {
        "product_detail": (
            _common_entry("product_detail", "product_main"),
            _common_entry("product_detail", "product_description"),
            _common_entry("product_detail", "related_products"),
        ),
        "listing": (_common_entry("listing", "product_listing"),),
        "collection": (
            _common_entry("collection", "collection_header"),
            _common_entry("collection", "collection_products"),
        ),
        "search": (_common_entry("search", "product_listing"),),
        "cart": (
            _common_entry("cart", "cart_items"),
            _common_entry("cart", "cart_summary"),
        ),
    }


def _manifest(spec: _RecipeSpec) -> dict:
    return {
        "schema_version": 1,
        "selections": {
            "header": f"header.{spec.header}.v1",
            "mega_menu": "mega_menu.none.v1",
            "hero": f"hero.{spec.hero}.v1",
            "layout": f"layout.{spec.layout}.v1",
            "product_view": f"product_view.{spec.product_view}.v1",
            "card": f"card.{spec.card}.v1",
            "badge": f"badge.{spec.badge}.v1",
            "motion": f"motion.{spec.motion}.v1",
            "footer": f"footer.{spec.footer}.v1",
            "bottom_nav": f"bottom_nav.{spec.bottom_nav}.v1",
            # P5-W2 — every Ready Template must carry a complete manifest now
            # that ``theme`` is a known family. Ready Templates never
            # auto-assign an occasion; Theme is merchant-selected and
            # independent, so all 50 default to the true no-op.
            "theme": "theme.none.v1",
        },
        "settings": {},
    }


def _product_entry(token: str, spec: _RecipeSpec) -> PresetSectionEntry:
    card = {"card_style": spec.card}
    if token == "product_list":
        return PresetSectionEntry(
            "catalog_product_wall", {"layout_mode": "rows", "card": card}
        )
    if token in {"bento_products", "featured_products"}:
        return PresetSectionEntry(
            "catalog_product_wall", {"layout_mode": "featured_row", "card": card}
        )
    if token == "product_grid" and spec.product_view == "dense_grid":
        return PresetSectionEntry(
            "catalog_product_wall", {"layout_mode": "group_columns", "card": card}
        )
    data_source = "discounted" if token == "sale_products" else "newest"
    display_mode = "carousel" if token == "product_rail" else "grid"
    return PresetSectionEntry(
        "product_section",
        {
            "data_source": data_source,
            "display_mode": display_mode,
            "card": card,
        },
    )


def _home(spec: _RecipeSpec) -> tuple[PresetSectionEntry, ...]:
    entries: list[PresetSectionEntry] = []
    for token in spec.composition:
        role = HOME_TOKEN_SEMANTIC_ROLE[token]
        if token == "hero":
            if spec.hero != "none":
                entries.append(
                    _with_role(
                        PresetSectionEntry(
                            "hero_banner", {"hero_style": _HERO_VARIANTS[spec.hero]}
                        ),
                        role,
                    )
                )
        elif token in _CATEGORY_PRESENTATIONS:
            entries.append(
                _with_role(
                    PresetSectionEntry(
                        "category_grid",
                        {"display_mode": _CATEGORY_PRESENTATIONS[token]},
                    ),
                    role,
                )
            )
        elif token in {
            "product_grid",
            "sale_products",
            "product_rail",
            "product_list",
            "bento_products",
            "featured_products",
        }:
            entries.append(_with_role(_product_entry(token, spec), role))
        else:
            entries.append(_with_role(PresetSectionEntry(_STATIC_SECTIONS[token]), role))
    return tuple(entries)


def _appearance(spec: _RecipeSpec) -> dict:
    if spec.layout == "dense_five":
        grid_density = 6
    elif spec.layout == "four_column":
        grid_density = 4
    elif spec.layout in {"two_column", "three_column"}:
        grid_density = 3
    else:
        grid_density = 4
    hero_style = (
        "tall"
        if spec.hero in {"immersive", "image_collage", "campaign_mosaic", "media_feature"}
        else "split"
        if spec.hero in {"editorial_split", "product_focus", "social_gallery"}
        else "wide"
    )
    return {
        "font": spec.font,
        "radius": spec.radius,
        "button_radius": spec.radius,
        "density": spec.density,
        "motion": spec.motion,
        "type_scale": "compact" if spec.density == "compact" else "large" if spec.density == "relaxed" else "normal",
        "button_style": "outline" if spec.radius == 0 else "soft" if spec.radius >= 14 else "filled",
        "image_fit": "contain" if spec.product_view in {"dense_grid", "catalog_list"} else "cover",
        "image_hover": "none" if spec.motion == "none" else "zoom",
        "card_image_crossfade": spec.motion == "dynamic",
        "card_image_zoom": spec.motion != "none",
        "content_width": spec.width,
        "grid_density": grid_density,
        "card_shadow": "none" if spec.radius == 0 else "soft",
        "card_hover": "none" if spec.motion == "none" else "lift",
        "hero_style": hero_style,
    }


def _build(spec: _RecipeSpec) -> LayoutPresetDefinition:
    return LayoutPresetDefinition(
        key=spec.key,
        version=spec.version,
        label_fa=spec.label_fa,
        description_fa=f"قالب آمادهٔ {spec.label_fa} با دی‌ان‌ای کامل طراحی فروشگاه.",
        is_ready_template=True,
        store_appearance=_manifest(spec),
        appearance=_appearance(spec),
        default_palette_slug=spec.palette,
        header={
            "sticky": True,
            "announcement_enabled": False,
            "header_variant": spec.header,
        },
        footer={
            "footer_variant": spec.footer,
            "mobile_nav_variant": spec.bottom_nav,
        },
        pages={"home": _home(spec), **_common_pages()},
    )


_SPECS = (
    _RecipeSpec("editorial_jewelry", "3", "آتلیه نوآر", "editorial_row", "immersive", "three_column", "editorial_grid", "luxury_dark", "none", "none", "minimal", "minimal_icons", "atelier-ivory", "Vazirmatn", "relaxed", 1200, 0, ("hero", "indexed_categories", "product_grid", "brand_story", "editorial_note")),
    _RecipeSpec("dense_marketplace", "3", "بازار مکس", "marketplace_search", "promo_bento", "dense_five", "dense_grid", "marketplace_price", "sale", "dynamic", "marketplace_columns", "five_item", "marketplace-spectrum", "Vazirmatn", "compact", 1500, 8, ("hero", "circular_categories", "sale_products", "product_grid", "service_strip", "brands", "testimonials")),
    _RecipeSpec("warm_boutique", "3", "کارگاه لاله", "compact_menu", "editorial_split", "three_column", "editorial_grid", "paper_frame", "none", "subtle", "brand_story", "floating_dock", "terracotta", "Vazirmatn", "relaxed", 1100, 4, ("hero", "brand_story", "product_grid", "testimonials", "newsletter")),
    _RecipeSpec("premium_leather", "3", "مونو", "editorial_row", "none", "four_column", "standard_grid", "standard", "none", "none", "minimal", "minimal_icons", "mono", "Arial", "normal", 1200, 0, ("ticker", "chip_categories", "product_grid", "editorial_note")),
    _RecipeSpec("dark_digital", "3", "پالس نئون", "floating_compact", "media_feature", "horizontal_rail", "carousel", "tech_neon", "sale", "dynamic", "marketplace_columns", "glass_dock", "theme-purple-neon", "Vazirmatn", "normal", 1200, 10, ("hero", "chip_categories", "product_rail", "sale_products", "newsletter")),
    _RecipeSpec("cedar_home", "2", "سدر", "centered_brand", "editorial_split", "four_column", "standard_grid", "standard", "none", "subtle", "centered", "four_item", "forest", "Vazirmatn", "normal", 1200, 12, ("hero", "tile_categories", "product_grid", "trust_features", "collection_tiles")),
    _RecipeSpec("street_drop", "1", "خیابان", "promo_bar", "typographic", "horizontal_rail", "carousel", "bold_outline", "sale", "dynamic", "bold_columns", "wide_cart", "theme-graphite-orange", "Vazirmatn", "compact", 1320, 0, ("ticker", "hero", "chip_categories", "product_rail", "sale_products")),
    _RecipeSpec("premium_leather_noir", "2", "زر", "centered_brand", "immersive", "two_column", "editorial_grid", "luxury_dark", "none", "none", "editorial_wordmark", "minimal_icons", "theme-black-gold", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story", "brands")),
    _RecipeSpec("search_market", "1", "میدان", "marketplace_search", "search_first", "dense_five", "dense_grid", "price_first", "sale", "subtle", "marketplace_columns", "raised_cart", "theme-cobalt-snow", "Vazirmatn", "compact", 1500, 8, ("hero", "circular_categories", "product_grid", "trust_features")),
    _RecipeSpec("playful_lifestyle", "2", "غنچه", "playful_canopy", "image_collage", "three_column", "standard_grid", "soft_capsule", "none", "dynamic", "playful_wave", "five_item", "mint", "Vazirmatn", "relaxed", 1200, 22, ("hero", "circular_categories", "product_grid", "testimonials", "newsletter")),
    _RecipeSpec("utility_catalog", "2", "نسخه", "marketplace_search", "none", "catalog_list", "catalog_list", "retail_row", "none", "none", "centered", "four_item", "slate", "Arial", "compact", 1320, 4, ("tile_categories", "product_list", "service_strip")),
    _RecipeSpec("artisan_grain", "2", "دانه", "editorial_masthead", "typographic", "two_column", "editorial_grid", "editorial_minimal", "none", "none", "brand_story", "floating_dock", "olive", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_grid", "brand_story", "collection_tiles")),
    _RecipeSpec("pixel_play", "1", "پیکسل", "category_tabs", "promo_bento", "bento_grid", "bento", "soft_capsule", "sale", "dynamic", "minimal", "raised_cart", "violet-pop", "Vazirmatn", "normal", 1200, 14, ("hero", "tile_categories", "bento_products", "newsletter")),
    _RecipeSpec("simorgh_market", "2", "سیمرغ", "centered_brand", "promo_bento", "four_column", "standard_grid", "marketplace_price", "sale", "subtle", "marketplace_columns", "five_item", "royal", "Vazirmatn", "normal", 1320, 8, ("hero", "circular_categories", "product_grid", "trust_features", "brands")),
    _RecipeSpec("coastal_product", "2", "موج", "overlay_transparent", "product_focus", "four_column", "standard_grid", "standard", "none", "subtle", "centered", "wide_cart", "ocean", "Vazirmatn", "normal", 1200, 12, ("hero", "chip_categories", "product_grid", "brand_story", "collection_tiles")),
    _RecipeSpec("literary_catalog", "1", "کتابخانه", "editorial_masthead", "quiet", "catalog_list", "catalog_list", "retail_row", "none", "none", "editorial_wordmark", "minimal_icons", "amber", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_list", "editorial_note")),
    _RecipeSpec("gallery_minimal", "1", "گالری آب", "editorial_row", "immersive", "catalog_list", "catalog_list", "editorial_minimal", "none", "none", "minimal", "minimal_icons", "theme-ice-cyan", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_list", "editorial_note")),
    _RecipeSpec("handmade_luxe", "2", "چرم دست", "editorial_row", "editorial_split", "three_column", "editorial_grid", "luxury_dark", "none", "subtle", "brand_story", "floating_dock", "theme-terracotta-cream", "Vazirmatn", "relaxed", 1100, 10, ("hero", "indexed_categories", "product_grid", "brand_story", "brands")),
    _RecipeSpec("niloufar_glass", "2", "نیلوفر", "floating_compact", "image_collage", "three_column", "standard_grid", "beauty_glass", "none", "subtle", "centered", "raised_cart", "rose", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "collection_tiles", "newsletter")),
    _RecipeSpec("tool_finder", "1", "آچار", "marketplace_search", "none", "four_column", "standard_grid", "technical_spec", "none", "none", "marketplace_columns", "four_item", "navy", "Arial", "compact", 1320, 4, ("tile_categories", "product_grid", "trust_features")),
    # P5-W4C rendered visual distinctness repair -- v2 was materially
    # indistinguishable from pine_eco above the fold (identical header,
    # hero, layout, product_view, bottom_nav). v3 keeps green_workshop's
    # own header/layout/card/footer/bottom_nav/palette/density unchanged
    # and switches only the hero family (editorial_split -> product_focus)
    # -- a genuinely different rendered hero component, not a palette/
    # font/radius change. pine_eco itself is untouched.
    _RecipeSpec("green_workshop", "3", "سبزه", "compact_menu", "product_focus", "three_column", "standard_grid", "standard", "none", "subtle", "brand_story", "floating_dock", "sage", "Vazirmatn", "relaxed", 1100, 16, ("hero", "tile_categories", "product_grid", "brand_story", "brands", "newsletter")),
    _RecipeSpec("tower_department", "1", "برج", "marketplace_search", "campaign_mosaic", "four_column", "standard_grid", "marketplace_price", "sale", "dynamic", "marketplace_columns", "five_item", "theme-crimson-charcoal", "Vazirmatn", "compact", 1500, 8, ("hero", "tile_categories", "product_grid", "sale_products", "trust_features")),
    _RecipeSpec("beauty_dew", "2", "شبنم", "floating_compact", "product_focus", "horizontal_rail", "carousel", "beauty_glass", "none", "subtle", "minimal", "raised_cart", "beauty-magenta", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_rail", "community_gallery", "newsletter")),
    _RecipeSpec("fashion_promo_catalog", "8", "تندر", "promo_bar", "promo_bento", "dense_five", "dense_grid", "price_first", "sale", "dynamic", "marketplace_columns", "raised_cart", "magenta-pop", "Vazirmatn", "compact", 1500, 8, ("hero", "chip_categories", "sale_products", "product_grid")),
    _RecipeSpec("horizon_story", "2", "افق", "overlay_transparent", "side_offer_slider", "two_column", "editorial_grid", "standard", "none", "subtle", "brand_story", "four_item", "peach", "Vazirmatn", "relaxed", 1100, 14, ("hero", "chip_categories", "product_grid", "brand_story", "community_gallery")),
    _RecipeSpec("mina_community", "1", "مینا", "community_shortcuts", "social_gallery", "two_column", "editorial_grid", "soft_capsule", "none", "dynamic", "app_download", "floating_dock", "uupm-social-rose", "Vazirmatn", "relaxed", 1100, 20, ("hero", "circular_categories", "product_grid", "community_gallery")),
    _RecipeSpec("silk_editorial", "2", "ابریشم", "editorial_masthead", "immersive", "two_column", "editorial_grid", "editorial_minimal", "none", "none", "editorial_wordmark", "minimal_icons", "atelier-ivory", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_grid", "brand_story", "collection_tiles")),
    _RecipeSpec("tuska_bento", "1", "توسکا", "compact_menu", "promo_bento", "bento_grid", "bento", "luxury_dark", "sale", "dynamic", "minimal", "four_item", "plum", "Vazirmatn", "normal", 1200, 12, ("hero", "tile_categories", "bento_products", "testimonials")),
    _RecipeSpec("rayan_tech", "2", "رایان", "marketplace_search", "product_focus", "four_column", "standard_grid", "technical_spec", "none", "subtle", "app_download", "four_item", "theme-midnight-electric", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "service_strip", "community_gallery")),
    # P5-W4C rendered visual distinctness repair -- v2 was materially
    # indistinguishable from playful_lifestyle above the fold (identical
    # arch-cutout hero composition/photos/copy, identical header). v3
    # keeps laleh_play's own header/layout/card/footer/bottom_nav/palette
    # unchanged and switches only the hero family (image_collage ->
    # typographic) -- a genuinely different rendered hero, still a bold
    # playful headline treatment. playful_lifestyle itself is untouched.
    _RecipeSpec("laleh_play", "3", "لاله‌زار", "playful_canopy", "typographic", "three_column", "standard_grid", "paper_frame", "none", "dynamic", "playful_wave", "five_item", "sunset", "Vazirmatn", "relaxed", 1200, 22, ("hero", "chip_categories", "product_grid", "brands", "newsletter")),
    _RecipeSpec("city_classic", "2", "شهر", "centered_brand", "editorial_split", "four_column", "standard_grid", "standard", "none", "subtle", "brand_story", "four_item", "uupm-professional-navy", "Vazirmatn", "normal", 1200, 8, ("hero", "circular_categories", "product_grid", "brand_story", "collection_tiles")),
    _RecipeSpec("collection_index", "1", "کلکسیون", "compact_drawer", "none", "catalog_list", "catalog_list", "catalog_index", "none", "none", "minimal", "minimal_icons", "catalog-colorful", "Arial", "compact", 1100, 0, ("indexed_categories", "product_list", "editorial_note")),
    _RecipeSpec("kamand_artisan", "2", "کمند", "overlay_transparent", "editorial_split", "three_column", "editorial_grid", "editorial_minimal", "none", "subtle", "brand_story", "floating_dock", "terracotta", "Vazirmatn", "relaxed", 1100, 6, ("hero", "indexed_categories", "product_grid", "brand_story", "community_gallery")),
    _RecipeSpec("almas_luxury", "2", "الماس", "floating_compact", "product_focus", "three_column", "editorial_grid", "shelf_editorial", "none", "subtle", "marketplace_columns", "glass_dock", "theme-ice-cyan", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "community_gallery", "newsletter")),
    _RecipeSpec("roosta_zigzag", "1", "روستا", "playful_canopy", "image_collage", "editorial_zigzag", "featured_wall", "marketplace_price", "none", "subtle", "brand_story", "four_item", "forest", "Vazirmatn", "relaxed", 1200, 16, ("hero", "circular_categories", "featured_products", "brand_story")),
    _RecipeSpec("mother_utility", "1", "مادر", "compact_drawer", "none", "four_column", "standard_grid", "technical_spec", "none", "none", "minimal", "minimal_icons", "slate", "Arial", "compact", 1200, 4, ("chip_categories", "product_grid", "trust_features")),
    _RecipeSpec("aftab_price", "1", "آفتاب", "category_tabs", "typographic", "four_column", "standard_grid", "price_first", "sale", "dynamic", "minimal", "raised_cart", "amber", "Vazirmatn", "compact", 1320, 8, ("hero", "chip_categories", "product_grid", "sale_products")),
    _RecipeSpec("mist_quiet", "1", "مه", "editorial_row", "quiet", "three_column", "editorial_grid", "standard", "none", "none", "minimal", "minimal_icons", "mono", "Vazirmatn", "relaxed", 1100, 14, ("hero", "chip_categories", "product_grid", "editorial_note")),
    _RecipeSpec("night_catalog", "1", "شبگرد", "compact_drawer", "quiet", "two_column", "editorial_grid", "editorial_minimal", "none", "none", "editorial_wordmark", "minimal_icons", "theme-black-gold", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_grid", "editorial_note")),
    _RecipeSpec("watchmaker_round", "2", "ساعت‌ساز", "centered_brand", "product_focus", "two_column", "editorial_grid", "portrait_round", "none", "subtle", "centered", "minimal_icons", "uupm-gold-purple-tech", "Vazirmatn", "relaxed", 1100, 12, ("hero", "indexed_categories", "product_grid", "brand_story", "brands")),
    _RecipeSpec("kite_playful", "1", "بادبادک", "playful_canopy", "image_collage", "four_column", "standard_grid", "soft_capsule", "none", "dynamic", "playful_wave", "five_item", "uupm-playful-orange", "Vazirmatn", "relaxed", 1200, 22, ("hero", "circular_categories", "product_grid", "testimonials")),
    _RecipeSpec("pine_eco", "2", "کاج", "compact_menu", "editorial_split", "three_column", "standard_grid", "soft_capsule", "none", "subtle", "centered", "floating_dock", "sage", "Vazirmatn", "relaxed", 1200, 16, ("hero", "tile_categories", "product_grid", "brand_story", "collection_tiles", "newsletter")),
    _RecipeSpec("mirror_beauty", "2", "آینه", "floating_compact", "product_focus", "three_column", "standard_grid", "beauty_glass", "none", "subtle", "minimal", "raised_cart", "beauty-magenta", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "brand_story", "community_gallery", "newsletter")),
    _RecipeSpec("charcoal_grill", "1", "زغال", "promo_bar", "product_focus", "four_column", "standard_grid", "bold_outline", "sale", "dynamic", "bold_columns", "wide_cart", "theme-graphite-orange", "Vazirmatn", "compact", 1200, 0, ("hero", "chip_categories", "product_grid", "sale_products")),
    _RecipeSpec("calligraphy_paper", "1", "خط", "compact_drawer", "immersive", "catalog_list", "catalog_list", "editorial_minimal", "none", "none", "editorial_wordmark", "minimal_icons", "mono", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_list", "brand_story")),
    _RecipeSpec("harbor_imports", "2", "بندر", "marketplace_search", "campaign_mosaic", "four_column", "standard_grid", "shipping_label", "sale", "subtle", "marketplace_columns", "four_item", "navy", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "sale_products", "trust_features", "brands")),
    # P5-W4C rendered visual distinctness repair -- v2 was materially
    # indistinguishable from silk_editorial above the fold (identical
    # immersive hero panel/photo/headline/CTA, identical header). v3
    # keeps parnian_editorial's own header/layout/card/footer/bottom_nav/
    # palette unchanged and switches only the hero family (immersive ->
    # product_focus) -- a genuinely different rendered hero, still an
    # editorial/refined treatment. silk_editorial itself is untouched.
    # NOTE: an earlier attempt used "editorial_split" here, but that
    # resolves to the same rendered hero_style ("split") as
    # artisan_grain's "typographic" hero while sharing the same header
    # (editorial_masthead), layout (two_column) and product_view
    # (editorial_grid) -- a code-review finding that would have silently
    # recreated this exact defect against a different, unchecked sibling.
    # product_focus avoids this (verified against all 50).
    _RecipeSpec("parnian_editorial", "3", "پرنیان", "editorial_masthead", "product_focus", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story", "community_gallery")),
    _RecipeSpec("racer_tech", "1", "تک‌سوار", "promo_bar", "media_feature", "horizontal_rail", "carousel", "technical_spec", "sale", "dynamic", "marketplace_columns", "wide_cart", "uupm-gaming-neon", "Vazirmatn", "compact", 1320, 6, ("ticker", "hero", "chip_categories", "product_rail", "sale_products")),
    _RecipeSpec("ferdowsi_department", "1", "فردوسی", "centered_brand", "campaign_mosaic", "featured_split", "featured_wall", "marketplace_price", "sale", "subtle", "marketplace_columns", "five_item", "uupm-burgundy-gold", "Vazirmatn", "normal", 1320, 8, ("hero", "tile_categories", "featured_products", "product_grid", "brands", "trust_features")),
    _RecipeSpec("anniversary_mosaic", "1", "پنجاه", "editorial_row", "promo_bento", "bento_grid", "bento", "catalog_index", "sale", "dynamic", "editorial_wordmark", "floating_dock", "uupm-creative-pink", "Vazirmatn", "normal", 1320, 12, ("ticker", "hero", "circular_categories", "bento_products", "testimonials", "newsletter")),
)


from .layout_preset_registry import (  # noqa: E402
    LayoutPresetDefinition,
    PresetSectionEntry,
    register_layout_preset,
)

A8_READY_TEMPLATES = tuple(_build(spec) for spec in _SPECS)
for _ready_template in A8_READY_TEMPLATES:
    register_layout_preset(_ready_template)

# P5-W4B — 50-Template Curation. Each row below is the exact,
# byte-for-byte outgoing version-1 ``_RecipeSpec`` for a curated key,
# copied verbatim before that key's row above was edited in place to
# version "2". These never feed ``A8_READY_TEMPLATES`` (so the latest
# catalog stays at exactly 50) but are registered through the same
# ``register_layout_preset``/``_build`` authority so the exact
# historical version remains resolvable forever via
# ``get_layout_preset_version(key, "1")`` — mirroring the existing
# pattern already used for the 8 pre-A8 legacy keys in
# ``layout_preset_registry.py``, without touching that file.
_HISTORICAL_SPECS = (
    _RecipeSpec("cedar_home", "1", "سدر", "centered_brand", "editorial_split", "four_column", "standard_grid", "standard", "none", "subtle", "centered", "four_item", "forest", "Vazirmatn", "normal", 1200, 12, ("hero", "tile_categories", "product_grid", "trust_features")),
    _RecipeSpec("premium_leather_noir", "1", "زر", "centered_brand", "immersive", "two_column", "editorial_grid", "luxury_dark", "none", "none", "editorial_wordmark", "minimal_icons", "theme-black-gold", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story")),
    _RecipeSpec("artisan_grain", "1", "دانه", "editorial_masthead", "typographic", "two_column", "editorial_grid", "editorial_minimal", "none", "none", "brand_story", "floating_dock", "olive", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_grid", "brand_story")),
    _RecipeSpec("simorgh_market", "1", "سیمرغ", "centered_brand", "promo_bento", "four_column", "standard_grid", "marketplace_price", "sale", "subtle", "marketplace_columns", "five_item", "royal", "Vazirmatn", "normal", 1320, 8, ("hero", "circular_categories", "product_grid", "trust_features")),
    _RecipeSpec("coastal_product", "1", "موج", "overlay_transparent", "product_focus", "four_column", "standard_grid", "standard", "none", "subtle", "centered", "wide_cart", "ocean", "Vazirmatn", "normal", 1200, 12, ("hero", "chip_categories", "product_grid", "brand_story")),
    _RecipeSpec("handmade_luxe", "1", "چرم دست", "editorial_row", "editorial_split", "three_column", "editorial_grid", "luxury_dark", "none", "subtle", "brand_story", "floating_dock", "theme-terracotta-cream", "Vazirmatn", "relaxed", 1100, 10, ("hero", "indexed_categories", "product_grid", "brand_story")),
    _RecipeSpec("niloufar_glass", "1", "نیلوفر", "floating_compact", "image_collage", "three_column", "standard_grid", "beauty_glass", "none", "subtle", "centered", "raised_cart", "rose", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "newsletter")),
    _RecipeSpec("green_workshop", "1", "سبزه", "compact_menu", "editorial_split", "three_column", "standard_grid", "standard", "none", "subtle", "brand_story", "floating_dock", "sage", "Vazirmatn", "relaxed", 1100, 16, ("hero", "tile_categories", "product_grid", "brand_story", "newsletter")),
    _RecipeSpec("beauty_dew", "1", "شبنم", "floating_compact", "product_focus", "horizontal_rail", "carousel", "beauty_glass", "none", "subtle", "minimal", "raised_cart", "beauty-magenta", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_rail", "newsletter")),
    _RecipeSpec("horizon_story", "1", "افق", "overlay_transparent", "side_offer_slider", "two_column", "editorial_grid", "standard", "none", "subtle", "brand_story", "four_item", "peach", "Vazirmatn", "relaxed", 1100, 14, ("hero", "chip_categories", "product_grid", "brand_story")),
    _RecipeSpec("silk_editorial", "1", "ابریشم", "editorial_masthead", "immersive", "two_column", "editorial_grid", "editorial_minimal", "none", "none", "editorial_wordmark", "minimal_icons", "atelier-ivory", "Vazirmatn", "relaxed", 1100, 0, ("hero", "indexed_categories", "product_grid", "brand_story")),
    _RecipeSpec("rayan_tech", "1", "رایان", "marketplace_search", "product_focus", "four_column", "standard_grid", "technical_spec", "none", "subtle", "app_download", "four_item", "theme-midnight-electric", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "service_strip")),
    _RecipeSpec("laleh_play", "1", "لاله‌زار", "playful_canopy", "image_collage", "three_column", "standard_grid", "paper_frame", "none", "dynamic", "playful_wave", "five_item", "sunset", "Vazirmatn", "relaxed", 1200, 22, ("hero", "chip_categories", "product_grid", "newsletter")),
    _RecipeSpec("city_classic", "1", "شهر", "centered_brand", "editorial_split", "four_column", "standard_grid", "standard", "none", "subtle", "brand_story", "four_item", "uupm-professional-navy", "Vazirmatn", "normal", 1200, 8, ("hero", "circular_categories", "product_grid", "brand_story")),
    _RecipeSpec("kamand_artisan", "1", "کمند", "overlay_transparent", "editorial_split", "three_column", "editorial_grid", "editorial_minimal", "none", "subtle", "brand_story", "floating_dock", "terracotta", "Vazirmatn", "relaxed", 1100, 6, ("hero", "indexed_categories", "product_grid", "brand_story")),
    _RecipeSpec("almas_luxury", "1", "الماس", "floating_compact", "product_focus", "three_column", "editorial_grid", "shelf_editorial", "none", "subtle", "marketplace_columns", "glass_dock", "theme-ice-cyan", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "newsletter")),
    _RecipeSpec("watchmaker_round", "1", "ساعت‌ساز", "centered_brand", "product_focus", "two_column", "editorial_grid", "portrait_round", "none", "subtle", "centered", "minimal_icons", "uupm-gold-purple-tech", "Vazirmatn", "relaxed", 1100, 12, ("hero", "indexed_categories", "product_grid", "brand_story")),
    _RecipeSpec("pine_eco", "1", "کاج", "compact_menu", "editorial_split", "three_column", "standard_grid", "soft_capsule", "none", "subtle", "centered", "floating_dock", "sage", "Vazirmatn", "relaxed", 1200, 16, ("hero", "tile_categories", "product_grid", "brand_story", "newsletter")),
    _RecipeSpec("mirror_beauty", "1", "آینه", "floating_compact", "product_focus", "three_column", "standard_grid", "beauty_glass", "none", "subtle", "minimal", "raised_cart", "beauty-magenta", "Vazirmatn", "relaxed", 1200, 18, ("hero", "circular_categories", "product_grid", "brand_story", "newsletter")),
    _RecipeSpec("harbor_imports", "1", "بندر", "marketplace_search", "campaign_mosaic", "four_column", "standard_grid", "shipping_label", "sale", "subtle", "marketplace_columns", "four_item", "navy", "Vazirmatn", "compact", 1320, 6, ("hero", "tile_categories", "product_grid", "sale_products", "trust_features")),
    _RecipeSpec("parnian_editorial", "1", "پرنیان", "editorial_masthead", "immersive", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story")),
    # P5-W4C rendered visual distinctness repair -- exact, byte-for-byte
    # outgoing version-2 rows for the three keys just moved to version 3
    # above, preserved verbatim through the same register_layout_preset
    # authority so v2 stays resolvable forever via
    # get_layout_preset_version(key, "2") -- mirroring the existing v1
    # preservation pattern already used throughout this tuple.
    _RecipeSpec("green_workshop", "2", "سبزه", "compact_menu", "editorial_split", "three_column", "standard_grid", "standard", "none", "subtle", "brand_story", "floating_dock", "sage", "Vazirmatn", "relaxed", 1100, 16, ("hero", "tile_categories", "product_grid", "brand_story", "brands", "newsletter")),
    _RecipeSpec("laleh_play", "2", "لاله‌زار", "playful_canopy", "image_collage", "three_column", "standard_grid", "paper_frame", "none", "dynamic", "playful_wave", "five_item", "sunset", "Vazirmatn", "relaxed", 1200, 22, ("hero", "chip_categories", "product_grid", "brands", "newsletter")),
    _RecipeSpec("parnian_editorial", "2", "پرنیان", "editorial_masthead", "immersive", "two_column", "editorial_grid", "shelf_editorial", "none", "none", "editorial_wordmark", "minimal_icons", "uupm-bakery-cream", "Vazirmatn", "relaxed", 1100, 0, ("hero", "arch_categories", "product_grid", "brand_story", "community_gallery")),
)

for _historical_spec in _HISTORICAL_SPECS:
    register_layout_preset(_build(_historical_spec))
