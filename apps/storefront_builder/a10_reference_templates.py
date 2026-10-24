"""Reference-fidelity Ready Templates 54-59 (V5 six-site kit).

Six official Ready Templates authored from the six reference storefronts in ``docs/design-references/v5-six-sites`` as pure
recipe data over the one Universal Storefront Engine (R4):

* ``decor_sand_boutique``   (54) — quiet home-decor boutique (photo first, sand/olive palette).
* ``rose_beauty_store``     (55) — rose-gold cosmetics store with a dark navigation bar.
* ``pink_beauty_gallery``   (56) — magenta cosmetics gallery with gradient shelves and a rich product page.
* ``campaign_beauty_hub``   (57) — orange/yellow campaign cosmetics hub.
* ``cocoa_gift_shop``       (58) — brown/gold gift & travel-mug shop.
* ``neon_digital_store``    (59) — dark navy digital-services store.

Like every Ready Template they register through ``register_layout_preset`` and inherit its fail-closed import-time validation.
No renderer, partial or CSS selector in the engine knows these template keys: every visual difference is selected by registered
section variants, card styles, global header/footer variants, appearance tokens and palettes, all reusable by any Store.
No reference logo, photograph, brand name or copy is used: the recipes carry structure only, the Store supplies its own media.
"""

from __future__ import annotations

from .appearance_registry import PaletteDefinition, register_palette
from .layout_preset_registry import (
    LayoutPresetDefinition,
    PresetSectionEntry,
    _complete_store_appearance,
    _u10_standard_non_home_pages,
    authored_legacy_home,
    register_layout_preset,
)

# ==================================================================
# 54 — decor_sand_boutique (reference: Dize)
# ==================================================================

register_palette(PaletteDefinition(
    slug="sand-olive",
    name_fa="شنی و زیتونی",
    group_fa="آرام",
    colors={
        "primary": "#BFB291", "secondary": "#58472E", "accent": "#6AAA56",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#27221C",
        "muted": "#6C655A", "border": "#E3DFD6",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#2F2A22",
        "nav_bg": "#FFFFFF", "nav_text": "#3A342B",
        "card_bg": "#FFFFFF", "footer_bg": "#BFB291",
        "footer_text": "#FFFFFF", "price": "#464136",
    },
    section_tones=("#BFB291", "#D5C9AA", "#58472E", "#E8E4DA", "#6AAA56"),
))

_DECOR_SHELF_CARD = {
    "card_style": "lifestyle_cart", "image_ratio": "portrait", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": False, "show_quick_add": True, "show_quick_view": False, "card_border": False,
}
_DECOR_GRID_CARD = {
    "card_style": "outline_plain", "image_ratio": "portrait", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": False, "show_quick_add": False, "show_quick_view": False,
}

_DECOR_PDP = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={
        "price_layout": "plain", "qty_layout": "inline", "cta_width": "auto", "cta_shape": "square", "show_breadcrumb": False,
        "show_sku": False, "show_wishlist": False, "show_discount_badge": False, "thumbs_position": "below",
        "title_size": "large", "price_size": "small", "show_topline": False,
    }),
    PresetSectionEntry("product_description", semantic_slot_key="product.description", settings={
        "layout_mode": "tabs_vertical", "panel_style": "boxed",
    }),
    PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={
        "title": "محصولات مشابه", "display_mode": "carousel", "carousel_navigation": "arrows", "card": _DECOR_GRID_CARD,
        "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
    }),
)

register_layout_preset(LayoutPresetDefinition(
    key="decor_sand_boutique",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="floating_card", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="centered_contact", bottom_nav="hidden",
    ),
    label_fa="بوتیک شنی (دکور و لوازم خانه)",
    description_fa="فروشگاه آرام دکور و لوازم خانه با عکس‌محوری، هدر کارتی شناور، اسلایدر تمیز، کاشی‌های دسته‌بندی و کارت‌های بدون شلوغی.",
    appearance={
        "font": "Estedad", "radius": 4, "button_radius": 4,
        "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1800, "card_shadow": "none", "card_hover": "none",
        "heading_style": "centered_rule",
    },
    default_palette_slug="sand-olive",
    header={
        "sticky": False, "announcement_enabled": True, "show_search": True,
        "show_account": False, "show_wishlist": False, "show_cart": True,
        "header_variant": "floating_card",
        "geometry": {"announce_height": 100, "announce_image_size": 56, "logo_height": 150, "card_height": 250, "band_height": 300},
    },
    footer={
        "show_about": False, "show_contact": True, "show_categories": False, "show_quick_links": False,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True, "footer_variant": "centered_contact",
        "floating_whatsapp": True, "floating_back_to_top": True,
    },
    pages={
        "home": authored_legacy_home("decor_sand_boutique", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "clean_slider", "text_position": "center", "autoplay": True, "interval_ms": 5000,
                "show_arrows": True, "show_dots": True, "design": {"width_pct": 83},
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "دسته بندی محصولات", "display_mode": "label_tiles", "item_limit": 2,
                "design": {"width_pct": 77},
            }),
            PresetSectionEntry("product_section", settings={
                "title": "پر فروش ترین ها", "data_source": "best_sellers", "display_mode": "carousel", "item_limit": 9,
                "carousel_navigation": "arrows", "card": _DECOR_SHELF_CARD, "design": {"width_pct": 77},
                "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 2},
            }),
            PresetSectionEntry("product_section", settings={
                "title": "محصولات جدید", "data_source": "newest", "display_mode": "grid", "item_limit": 8,
                "card": _DECOR_GRID_CARD, "design": {"width_pct": 82},
                "show_view_all": True, "view_all_placement": "bottom",
                "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
            }),
            PresetSectionEntry("decorative_strip", settings={
                "background_mode": "solid", "background_color": "token:tone-2", "desktop_height": 56, "tablet_height": 52,
                "mobile_height": 48, "radius": 6, "optional_text": "پیج اینستاگرام ما را دنبال کنید", "icon": "instagram",
                "text_size": 24, "link_url": "#", "design": {"width_pct": 80},
            }),
        ), ("hero", "categories", "products_bestsellers", "products_newest", "social_bar")),
        **{**_u10_standard_non_home_pages(), "product_detail": _DECOR_PDP},
    },
))
