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

from .a9_reference_templates import _gap
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
                "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 1},
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


# ==================================================================
# 55 — rose_beauty_store (reference: Lilika)
# ==================================================================

register_palette(PaletteDefinition(
    slug="rose-cream",
    name_fa="رز و کرم",
    group_fa="آرام",
    colors={
        "primary": "#AF726D", "secondary": "#363636", "accent": "#AF726D",
        "background": "#F6EDE8", "surface": "#FFFFFF", "text": "#302E2D",
        "muted": "#74696A", "border": "#E4D6CF",
    },
    theme_roles={
        "header_bg": "#F6EDE8", "header_text": "#302E2D",
        "nav_bg": "#363636", "nav_text": "#FFFFFF",
        "card_bg": "#FFFFFF", "footer_bg": "#363636",
        "footer_text": "#F1ECE9", "price": "#9A5D58",
    },
    section_tones=("#EBCEC6", "#2A2A2A", "#363636", "#AF726D", "#F6EDE8"),
))

_ROSE_CARD = {
    "card_style": "outline_plain", "image_ratio": "square", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": False, "show_quick_add": False, "show_quick_view": False, "card_border": False,
}
_ROSE_WIDTH = {"width_pct": 81}


_ROSE_PDP = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={
        "info_panel": "card", "gallery_split": "info_wide", "price_layout": "plain", "qty_layout": "inline",
        "cta_width": "auto", "cta_shape": "square", "cta_size": "normal", "title_size": "normal", "price_size": "large",
        "show_sku": False, "show_discount_badge": False, "show_topline": False, "thumbs_position": "below",
    }),
    PresetSectionEntry("product_description", semantic_slot_key="product.description", settings={
        "layout_mode": "tabs", "tab_style": "underline", "tab_align": "start", "panel_style": "plain",
    }),
    PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={
        "title": "محصولات مشابه", "display_mode": "carousel", "carousel_navigation": "dots", "card": _ROSE_CARD,
        "responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2},
    }),
)


def _rose_shelf(title: str, tabs: str) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": "newest", "display_mode": "carousel", "item_limit": 10,
        "tabs_source": tabs, "tabs_count": 4, "carousel_navigation": "arrows", "card": _ROSE_CARD, "design": _ROSE_WIDTH,
        "show_view_all": False, "spacing": _gap(40, pad_top=0, pad_bottom=70),
        "responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2},
    })


def _rose_icon_band(source: str) -> PresetSectionEntry:
    return PresetSectionEntry("category_grid", settings={
        "title": "", "display_mode": "icon_rail", "item_limit": 5, "category_source": source,
        "background": {"mode": "palette", "palette_role": "tone-1", "bleed": True},
        "spacing": _gap(0, pad_top=46, pad_bottom=44),
    })


register_layout_preset(LayoutPresetDefinition(
    key="rose_beauty_store",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="beauty_search_nav", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="marketplace_dense", bottom_nav="four_item",
    ),
    label_fa="رز کرمی (آرایشی و بهداشتی)",
    description_fa="فروشگاه لوازم آرایشی با هدر روشن و نوار ناوبری تیره، نوارهای آیکنی صورتی، قفسه‌های محصول با زبانهٔ دسته‌بندی، نوار دعوت تیره و مجلهٔ فروشگاه.",
    appearance={
        "font": "Estedad", "radius": 3, "button_radius": 4,
        "density": "relaxed", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1800, "card_shadow": "soft", "card_hover": "none",
    },
    default_palette_slug="rose-cream",
    header={
        "sticky": False, "announcement_enabled": False, "show_search": True,
        "show_account": True, "show_wishlist": True, "show_cart": True,
        "header_variant": "beauty_search_nav", "extra_blocks": [{"type": "category_menu"}],
        "geometry": {"main_height": 128, "nav_height": 56, "search_max_width": 960, "search_height": 40, "logo_height": 100},
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True, "footer_variant": "marketplace_dense",
        "mobile_nav_variant": "four_item",
    },
    pages={
        "home": authored_legacy_home("rose_beauty_store", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "clean_slider", "text_position": "center", "autoplay": True, "interval_ms": 5000,
                "show_arrows": False, "show_dots": True, "slider_ratio": "2.76", "slider_ratio_mobile": "1.78", "slider_width": "full",
                "spacing": _gap(0, pad_top=0, pad_bottom=0, first=True),
            }),
            _rose_icon_band("top_level"),
            _rose_shelf("جدیدترین محصولات", "categories"),
            _rose_icon_band("subcategories"),
            _rose_shelf("محصولات آرایشی", "subcategories"),
            PresetSectionEntry("decorative_strip", settings={
                "background_mode": "solid", "background_color": "#0E0E0E", "gradient_to": "token:tone-4", "bleed": True,
                "desktop_height": 264, "tablet_height": 220, "mobile_height": 200, "alignment": "start", "radius": 0,
                "optional_text": "کارشناسان ما آماده پاسخگویی به سوالات شما هستند.", "text_size": 32,
                "link_url": "/products/", "button_label": "مشاهده همه",
                "spacing": _gap(0),
            }),
            PresetSectionEntry("image_text", settings={
                "title": "عنوان بخش معرفی فروشگاه", "block_style": "plain", "image_position": "left",
                "feature_items": [
                    {"icon": "award", "title": "عنوان ویژگی اول", "text": "توضیح کوتاه این ویژگی را اینجا بنویسید."},
                    {"icon": "refresh", "title": "عنوان ویژگی دوم", "text": "توضیح کوتاه این ویژگی را اینجا بنویسید."},
                    {"icon": "headset", "title": "عنوان ویژگی سوم", "text": "توضیح کوتاه این ویژگی را اینجا بنویسید."},
                ],
                "design": {"width_pct": 82}, "spacing": _gap(60, pad_top=0, pad_bottom=60),
            }),
            PresetSectionEntry("blog_posts", settings={
                "title": "مجله آنلاین فروشگاه", "item_limit": 4, "style": "editorial_cards",
                "background": {"mode": "palette", "palette_role": "tone-2", "bleed": True}, "design": {"width_pct": 82},
                "spacing": _gap(0, pad_top=64, pad_bottom=64),
            }),
            _rose_shelf("ترین‌های فروشگاه", "sorts"),
        ), ("hero", "categories_top", "products_new_tabs", "categories_sub", "products_makeup_tabs", "cta_band", "story", "journal", "products_tabs_sorts")),
        **{**_u10_standard_non_home_pages(), "product_detail": _ROSE_PDP},
    },
))


# ==================================================================
# 56 — pink_beauty_gallery (reference: Lilium)
# ==================================================================

register_palette(PaletteDefinition(
    slug="fuchsia-gallery",
    name_fa="فوشیا و سفید",
    group_fa="پرانرژی",
    colors={
        "primary": "#D4197A", "secondary": "#0F172A", "accent": "#D4197A",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#0F172A",
        "muted": "#64748B", "border": "#E2E8F0",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#0F172A",
        "nav_bg": "#D4197A", "nav_text": "#FFFFFF",
        "card_bg": "#FFFFFF", "footer_bg": "#FAFAFA",
        "footer_text": "#334155", "price": "#0F172A",
    },
    section_tones=("#D4197A", "#FDF2F8", "#0F172A", "#F8E1EE", "#FCE7F3"),
))

_GALLERY_CARD = {
    "card_style": "gallery_pink", "image_ratio": "square", "show_brand": True, "show_rating": False,
    "show_wishlist": False, "show_badge": True, "show_quick_add": False, "show_quick_view": False, "card_border": False,
}


def _gallery_shelf(title: str, subtitle: str, source: str, limit: int = 8) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "subtitle": subtitle, "data_source": source, "display_mode": "carousel", "item_limit": limit,
        "heading_style": "plain_link", "show_view_all": True, "row_backdrop": "glow", "carousel_navigation": "arrows",
        "card": _GALLERY_CARD, "design": {"width_pct": 84}, "spacing": _gap(40, pad_top=0, pad_bottom=24),
        "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
    })


_GALLERY_PDP = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={
        "price_layout": "plain", "qty_layout": "inline", "cta_width": "auto", "cta_shape": "rounded", "cta_size": "large",
        "title_size": "large", "price_size": "xlarge", "info_panel": "plain",
        "show_low_stock_alert": True, "show_free_shipping_notice": True, "show_contact_buttons": True,
    }),
    PresetSectionEntry("product_description", semantic_slot_key="product.description", settings={
        "layout_mode": "tabs", "tab_style": "underline", "tab_align": "start", "panel_style": "plain",
        "sections": [
            {"key": "desc", "label": "توضیحات", "visible": True},
            {"key": "spec", "label": "توضیحات تکمیلی", "visible": True},
            {"key": "brand", "label": "برند", "visible": True},
            {"key": "review", "label": "نظرات", "visible": True},
        ],
    }),
    PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={
        "title": "محصولات مرتبط", "display_mode": "carousel", "carousel_navigation": "arrows", "card": _GALLERY_CARD,
        "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
    }),
)

register_layout_preset(LayoutPresetDefinition(
    key="pink_beauty_gallery",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="beauty_search_nav", hero="legacy_default", layout="quarters",
        product_view="carousel", card="legacy_default", badge="none", motion="subtle",
        footer="premium_columns", bottom_nav="hidden",
    ),
    label_fa="گالری فوشیا (زیبایی)",
    description_fa="گالری آنلاین زیبایی با هدر دو‌ردیفه و نوار ناوبری فوشیا، اسلایدر تمام‌عرض، ردیف مزایا، قفسه‌های محصول با درخشش ملایم و صفحهٔ محصول غنی با هشدار موجودی و دکمه‌های مشاوره.",
    appearance={
        "font": "Vazirmatn", "radius": 14, "button_radius": 12,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1800, "card_shadow": "soft", "card_hover": "lift",
    },
    default_palette_slug="fuchsia-gallery",
    header={
        "sticky": True, "announcement_enabled": True, "show_search": True,
        "show_account": True, "show_wishlist": True, "show_cart": True,
        "header_variant": "beauty_search_nav",
        "geometry": {"main_height": 96, "nav_height": 50, "search_max_width": 760, "search_height": 46, "logo_height": 52,
                     "announce_height": 36},
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": False, "show_quick_links": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True, "footer_variant": "premium_columns",
        "floating_whatsapp": True, "floating_back_to_top": True,
    },
    pages={
        "home": authored_legacy_home("pink_beauty_gallery", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "clean_slider", "text_position": "center", "autoplay": True, "interval_ms": 5000,
                "show_arrows": False, "show_dots": True, "slider_ratio": "2.5", "slider_ratio_mobile": "1.78",
                "slider_width": "full", "spacing": _gap(0, pad_top=0, pad_bottom=0, first=True),
            }),
            PresetSectionEntry("trust_features", settings={
                "items": [
                    {"icon": "◎", "title": "پرداخت امن", "subtitle": "درگاه فعال فروشگاه", "claim": "payment"},
                    {"icon": "⇢", "title": "ارسال سفارش", "subtitle": "روش‌های ارسال فروشگاه", "claim": "shipping"},
                    {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت از فروشگاه", "claim": "pickup"},
                ],
                "spacing": _gap(30, size="small"), "design": {"width_pct": 84},
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 2, "offset": 0, "layout_variant": "duo-round",
                "spacing": _gap(30), "design": {"width_pct": 84},
            }),
            _gallery_shelf("جدیدترین محصولات", "تازه‌ترین محصولات فروشگاه", "newest"),
            _gallery_shelf("محصولات تخفیف خورده", "جدیدترین تخفیف‌های فروشگاه", "discounted"),
            PresetSectionEntry("linked_image", settings={"design": {"width_pct": 84, "radius": 16}, "spacing": _gap(40)}),
            _gallery_shelf("پرفروش‌ترین‌ها", "محبوب‌ترین انتخاب مشتریان", "best_sellers"),
        ), ("hero", "services", "banners", "products_new", "products_discounted", "banner_wide", "products_bestsellers")),
        **{**_u10_standard_non_home_pages(), "product_detail": _GALLERY_PDP},
    },
))


# ==================================================================
# 57 — campaign_beauty_hub (reference: AsalBanoo)
# ==================================================================

register_palette(PaletteDefinition(
    slug="honey-orange",
    name_fa="عسلی و نارنجی",
    group_fa="پرانرژی",
    colors={
        "primary": "#EDB51F", "secondary": "#4C9A2A", "accent": "#FF6E1E",
        "background": "#F8F9FC", "surface": "#FFFFFF", "text": "#1F2937",
        "muted": "#6B7280", "border": "#E5E7EB",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#1F2937",
        "nav_bg": "#FFFFFF", "nav_text": "#1F2937",
        "card_bg": "#FFFFFF", "footer_bg": "#FCEFC2",
        "footer_text": "#3B2F12", "price": "#1F2937",
    },
    section_tones=("#FF6E1E", "#F5EBC3", "#FCE588", "#A5DDFF", "#FFF2CC"),
))

_HONEY_CARD = {
    "card_style": "campaign_round", "image_ratio": "square", "show_brand": False, "show_rating": True,
    "show_wishlist": False, "show_badge": True, "show_quick_add": False, "show_quick_view": False, "card_border": False,
}


def _honey_shelf(title: str, source: str, icon: str, *, background: dict | None = None, limit: int = 10) -> PresetSectionEntry:
    settings = {
        "title": title, "data_source": source, "display_mode": "carousel", "item_limit": limit, "heading_style": "icon_chip",
        "heading_icon": icon, "show_view_all": True, "carousel_navigation": "dots", "card": _HONEY_CARD,
        "design": {"width_pct": 82}, "responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2},
    }
    if background:
        settings["background"] = background
        settings["spacing"] = _gap(0, pad_top=56, pad_bottom=56)
    else:
        settings["spacing"] = _gap(40, pad_top=0, pad_bottom=20)
    return PresetSectionEntry("product_section", settings=settings)


_HONEY_BAND = {"mode": "palette", "palette_role": "tone-1", "bleed": True}

_HONEY_PDP = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={
        "price_layout": "plain", "qty_layout": "inline", "cta_width": "auto", "cta_shape": "rounded", "cta_size": "large",
        "cta_tone": "secondary", "title_size": "large", "info_panel": "plain", "show_low_stock_alert": True, "show_free_shipping_notice": True,
        "show_contact_buttons": True, "show_mobile_sticky_bar": True,
    }),
    PresetSectionEntry("product_description", semantic_slot_key="product.description", settings={
        "layout_mode": "tabs", "tab_style": "underline", "tab_align": "start", "panel_style": "plain",
    }),
    PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={
        "title": "محصولات مشابه", "display_mode": "carousel", "carousel_navigation": "dots", "card": _HONEY_CARD,
        "responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2},
    }),
)

register_layout_preset(LayoutPresetDefinition(
    key="campaign_beauty_hub",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="promo_search_nav", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="premium_columns", bottom_nav="hidden",
    ),
    label_fa="هاب کمپینی عسلی (آرایشی)",
    description_fa="فروشگاه آرایشی کمپینی با نوار اعلان، دسته‌بندی‌های دایره‌ای، نوارهای نارنجی و عسلی، کارت‌های گرد، کارت مشاوران، ویدیو و مجله.",
    appearance={
        "font": "Estedad", "radius": 14, "button_radius": 10,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1800, "card_shadow": "soft", "card_hover": "none",
    },
    default_palette_slug="honey-orange",
    header={
        "sticky": True, "announcement_enabled": True, "show_search": True,
        "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "promo_search_nav",
        "geometry": {"announce_bg": "token:tone-4", "announce_height": 44},
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True, "footer_variant": "premium_columns",
    },
    pages={
        "home": authored_legacy_home("campaign_beauty_hub", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "clean_slider", "text_position": "start", "autoplay": True, "interval_ms": 5000,
                "show_arrows": False, "show_dots": True, "slider_ratio": "2.5", "slider_ratio_mobile": "1.33",
                "slider_width": "full", "spacing": _gap(0, pad_top=0, pad_bottom=0, first=True),
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "", "display_mode": "ring_circles", "item_limit": 8, "design": {"width_pct": 82}, "spacing": _gap(30),
            }),
            _honey_shelf("تخفیفات شگفت‌انگیز", "discounted", "percent", background=_HONEY_BAND),
            PresetSectionEntry("category_grid", settings={
                "title": "", "display_mode": "photo_cards", "item_limit": 4, "design": {"width_pct": 82},
                "background": {"mode": "palette", "palette_role": "tone-2", "bleed": True}, "spacing": _gap(0, pad_top=40, pad_bottom=40),
            }),
            _honey_shelf("محصولات پرفروش", "best_sellers", "crown"),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 3, "offset": 0, "layout_variant": "trio-round", "design": {"width_pct": 82}, "spacing": _gap(30),
            }),
            PresetSectionEntry("multi_banner", settings={
                "title": "مشاوران حرفه‌ای فروشگاه", "heading_icon": "headset", "item_limit": 4, "offset": 3, "layout_variant": "people-4",
                "background": {"mode": "palette", "palette_role": "tone-3", "bleed": True},
                "design": {"width_pct": 82}, "spacing": _gap(0, pad_top=48, pad_bottom=48),
            }),
            _honey_shelf("جدیدترین محصولات", "newest", "sparkles"),
            PresetSectionEntry("video_section", settings={
                "title": "ویدیوهای فروشگاه", "background": _HONEY_BAND, "design": {"width_pct": 82},
                "spacing": _gap(0, pad_top=48, pad_bottom=48),
            }),
            PresetSectionEntry("trust_features", settings={
                "items": [
                    {"icon": "◎", "title": "پرداخت امن", "subtitle": "درگاه فعال فروشگاه", "claim": "payment"},
                    {"icon": "⇢", "title": "ارسال سفارش", "subtitle": "روش‌های ارسال فروشگاه", "claim": "shipping"},
                    {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت از فروشگاه", "claim": "pickup"},
                ],
                "spacing": _gap(40, size="small"), "design": {"width_pct": 82},
            }),
            PresetSectionEntry("blog_posts", settings={
                "title": "مجله زیبایی", "item_limit": 4, "style": "editorial_cards", "design": {"width_pct": 82},
                "spacing": _gap(40, pad_top=0, pad_bottom=40),
            }),
        ), ("hero", "categories_circles", "products_deals", "categories_tiles", "products_bestsellers", "banners",
            "advisors", "products_new", "videos", "services", "journal")),
        **{**_u10_standard_non_home_pages(), "product_detail": _HONEY_PDP},
    },
))


# ==================================================================
# 58 — cocoa_gift_shop (reference: khanehshokolati)
# ==================================================================

register_palette(PaletteDefinition(
    slug="cocoa-gold",
    name_fa="کاکائو و طلایی",
    group_fa="گرم",
    colors={
        "primary": "#704012", "secondary": "#24170E", "accent": "#F5224C",
        "background": "#EAF3FB", "surface": "#FFFFFF", "text": "#24170E",
        "muted": "#6B5B4E", "border": "#E2D7CB",
    },
    theme_roles={
        "header_bg": "#704012", "header_text": "#FFFFFF",
        "nav_bg": "#FFFFFF", "nav_text": "#24170E",
        "card_bg": "#FFFFFF", "footer_bg": "#090909",
        "footer_text": "#F1ECE9", "price": "#24170E",
    },
    section_tones=("#704012", "#FBCB60", "#F5224C", "#090909", "#EAF3FB"),
))

_COCOA_CARD = {
    "card_style": "cocoa_gift", "image_ratio": "square", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": True, "show_quick_add": True, "show_quick_view": False, "card_border": False,
}


def _cocoa_shelf(title: str, source: str, *, tabs: str = "", pills: bool = False, limit: int = 4) -> PresetSectionEntry:
    settings = {
        "title": title, "data_source": source, "display_mode": "grid", "item_limit": limit, "card": _COCOA_CARD,
        "show_view_all": True, "view_all_placement": "bottom", "design": {"width_pct": 90},
        "background": {"mode": "surface"}, "spacing": _gap(30, pad_top=30, pad_bottom=30),
        "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
    }
    if tabs:
        settings.update({"tabs_source": tabs, "tabs_count": 4, "tabs_style": "pills" if pills else ""})
    return PresetSectionEntry("product_section", settings=settings)


_COCOA_PDP = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={
        "info_panel": "outlined", "gallery_split": "equal", "price_layout": "box", "qty_layout": "inline", "cta_width": "auto",
        "cta_shape": "rounded", "cta_size": "large", "option_shape": "square", "title_size": "large",
        "show_low_stock_alert": True, "show_free_shipping_notice": True, "show_mobile_sticky_bar": True,
    }),
    PresetSectionEntry("product_description", semantic_slot_key="product.description", settings={
        "layout_mode": "tabs", "tab_style": "boxed", "tab_align": "start", "panel_style": "boxed",
    }),
    PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={
        "title": "محصولات مرتبط", "display_mode": "grid", "card": _COCOA_CARD,
        "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
    }),
)

register_layout_preset(LayoutPresetDefinition(
    key="cocoa_gift_shop",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="chocolate_centered_search", hero="chocolate_carousel", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="chocolate_dark_columns", bottom_nav="four_item",
    ),
    label_fa="هدیه و ماگ کاکائویی",
    description_fa="فروشگاه ماگ، فلاسک و هدیه با هدر قهوه‌ای، ریل داستان، اسلایدر دوتایی، کاشی‌های بریده‌شدهٔ دسته‌بندی، موزاییک بنر و کارت‌های سفید با دکمهٔ قهوه‌ای.",
    appearance={
        "font": "Estedad", "radius": 14, "button_radius": 12,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1800, "card_shadow": "soft", "card_hover": "none",
    },
    default_palette_slug="cocoa-gold",
    header={
        "sticky": True, "announcement_enabled": False, "show_search": True,
        "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "chocolate_centered_search",
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True, "footer_variant": "chocolate_dark_columns",
        "floating_whatsapp": True, "floating_back_to_top": True, "mobile_nav_variant": "four_item",
    },
    pages={
        "home": authored_legacy_home("cocoa_gift_shop", (
            PresetSectionEntry("category_grid", settings={"title": "", "display_mode": "chocolate_story", "item_limit": 10}),
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "chocolate_carousel", "text_position": "center", "autoplay": True, "interval_ms": 4800,
                "show_arrows": True, "show_dots": True,
            }),
            PresetSectionEntry("category_grid", settings={"title": "", "display_mode": "chocolate_badges", "item_limit": 12}),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 1, "offset": 0, "layout_variant": "wide-single", "design": {"width_pct": 90},
            }),
            _cocoa_shelf("جدیدترین محصولات", "newest", tabs="categories", pills=True),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 5, "offset": 1, "layout_variant": "mosaic-5", "design": {"width_pct": 90}, "spacing": _gap(30),
            }),
            PresetSectionEntry("product_section", settings={
                "title": "پیشنهاد شگفت‌انگیز", "data_source": "discounted", "display_mode": "grid", "item_limit": 4,
                "heading_style": "icon_chip", "heading_icon": "fire", "show_view_all": False, "card": _COCOA_CARD,
                "design": {"width_pct": 90}, "background": {"mode": "surface"}, "spacing": _gap(30, pad_top=26, pad_bottom=26),
                "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
            }),
            _cocoa_shelf("جدیدترین محصولات", "newest", tabs="sorts", pills=True),
            PresetSectionEntry("blog_posts", settings={
                "title": "مجله اینترنتی فروشگاه", "item_limit": 3, "style": "editorial_cards", "design": {"width_pct": 90},
                "spacing": _gap(30, pad_top=0, pad_bottom=30),
            }),
        ), ("categories_story", "hero", "categories_cutouts", "banner_wide", "products_tabs", "banner_mosaic", "products_offers",
            "products_sorts", "journal")),
        **{**_u10_standard_non_home_pages(), "product_detail": _COCOA_PDP},
    },
))


# ==================================================================
# 59 — neon_digital_store (reference: zhimunplus)
# ==================================================================

register_palette(PaletteDefinition(
    slug="neon-navy",
    name_fa="نیلی نئونی",
    group_fa="تیره",
    colors={
        "primary": "#3355FF", "secondary": "#03BFAC", "accent": "#3355FF",
        "background": "#070E1C", "surface": "#151B2D", "text": "#F8FAFC",
        "muted": "#BABFC4", "border": "#2A3350",
    },
    theme_roles={
        "header_bg": "#0B1324", "header_text": "#F8FAFC",
        "nav_bg": "#0B1324", "nav_text": "#E2E8F0",
        "card_bg": "#151B2D", "footer_bg": "#0B1324",
        "footer_text": "#E2E8F0", "price": "#D9F99D",
    },
    section_tones=("#E5487F", "#F26D3D", "#2F6BFF", "#1FA866", "#151B2D"),
))

_NEON_CARD = {
    "card_style": "tech_neon", "image_ratio": "square", "show_brand": False, "show_rating": True,
    "show_wishlist": False, "show_badge": True, "show_quick_add": True, "show_quick_view": False, "card_border": True,
}
_NEON_ROW_CARD = {
    "card_style": "retail_row", "image_ratio": "square", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": False, "show_quick_add": False, "show_quick_view": False, "card_border": True,
}


def _neon_shelf(title: str, source: str, *, subtitle: str = "") -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "subtitle": subtitle, "data_source": source, "display_mode": "carousel", "item_limit": 10,
        "heading_style": "plain_link", "show_view_all": True, "carousel_navigation": "dots", "card": _NEON_CARD,
        "design": {"width_pct": 86}, "spacing": _gap(40, pad_top=0, pad_bottom=20),
        "responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2},
    })


_NEON_PDP = (
    PresetSectionEntry("product_main", semantic_slot_key="product.main", settings={
        "info_panel": "card", "gallery_split": "equal", "price_layout": "box", "qty_layout": "inline", "cta_width": "full",
        "cta_shape": "rounded", "cta_size": "large", "title_size": "large", "price_size": "large",
        "show_discount_badge": True, "show_low_stock_alert": False, "show_mobile_sticky_bar": True,
    }),
    PresetSectionEntry("product_description", semantic_slot_key="product.description", settings={
        "layout_mode": "tabs", "tab_style": "pills", "tab_align": "start", "panel_style": "soft",
    }),
    PresetSectionEntry("related_products", semantic_slot_key="product.related", settings={
        "title": "سرویس‌های مرتبط", "display_mode": "carousel", "carousel_navigation": "dots", "card": _NEON_CARD,
        "responsive": {"desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2},
    }),
)

register_layout_preset(LayoutPresetDefinition(
    key="neon_digital_store",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="marketplace_search_first", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="dark_tech", bottom_nav="hidden",
    ),
    label_fa="فروشگاه دیجیتال نئونی",
    description_fa="فروشگاه خدمات و اشتراک‌های دیجیتال با پوستهٔ نیلی تیره، هیرو دوستونه با پنل‌های رنگی، فهرست محصولات سه‌ستونه، قفسه‌های تیره و نظرات مشتریان.",
    appearance={
        "font": "Estedad", "radius": 16, "button_radius": 12,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1800, "card_shadow": "none", "card_hover": "lift",
    },
    default_palette_slug="neon-navy",
    header={
        "sticky": True, "announcement_enabled": False, "show_search": True,
        "show_account": True, "show_wishlist": True, "show_cart": True,
        "header_variant": "marketplace_search_first",
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": True,
        "show_social": True, "show_trust_badges": True, "show_payment_logos": False,
        "show_newsletter": False, "show_copyright": True, "footer_variant": "dark_tech",
        "floating_back_to_top": True,
    },
    pages={
        "home": authored_legacy_home("neon_digital_store", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "split", "text_position": "start", "autoplay": False, "show_arrows": False, "show_dots": False,
                "design": {"width_pct": 86}, "spacing": _gap(30, first=True),
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 4, "offset": 0, "layout_variant": "panel-4", "design": {"width_pct": 86}, "spacing": _gap(10),
            }),
            PresetSectionEntry("product_section", settings={
                "title": "آخرین محصولات", "data_source": "newest", "display_mode": "grid", "item_limit": 9,
                "heading_style": "plain_link", "show_view_all": True, "card": _NEON_ROW_CARD, "design": {"width_pct": 86},
                "spacing": _gap(40, pad_top=0, pad_bottom=20),
                "responsive": {"desktop_columns": 3, "tablet_columns": 2, "mobile_columns": 1},
            }),
            _neon_shelf("پرفروش‌ترین‌های فروشگاه", "best_sellers"),
            PresetSectionEntry("category_grid", settings={
                "title": "دسته‌بندی‌ها", "display_mode": "icon_tiles", "item_limit": 7, "design": {"width_pct": 86},
                "spacing": _gap(40),
            }),
            _neon_shelf("پیشنهاد فروشگاه", "discounted"),
            _neon_shelf("جدیدترین سرویس‌ها", "newest"),
            PresetSectionEntry("testimonials", settings={
                "title": "نظرات مشتریان", "items": [], "design": {"width_pct": 86}, "spacing": _gap(40),
            }),
        ), ("hero", "highlights", "products_latest_rows", "products_bestsellers", "categories_icons", "products_offers",
            "products_new", "testimonials")),
        **{**_u10_standard_non_home_pages(), "product_detail": _NEON_PDP},
    },
))
