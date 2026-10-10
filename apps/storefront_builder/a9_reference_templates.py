"""Reference-fidelity Ready Templates 51, 52 and 53.

Three official Ready Templates authored from three reference storefront
screenshots, as pure recipe data over the one Universal Storefront Engine:

* ``stationery_spectrum``       (51) — coloured-band marketplace for stationery
                                        and art supplies.
* ``magenta_beauty_retail``     (52) — cosmetics / perfume retail with
                                        campaign bands and category columns.
* ``pastel_kawaii_stationery``  (53) — flat pastel-tile stationery catalogue.

Like the retained hand-built recipes in ``layout_preset_registry`` these are
registered through ``register_layout_preset`` and therefore inherit the same
fail-closed import-time validation. They are deliberately NOT part of
``a8_ready_templates.A8_READY_TEMPLATES`` (that tuple is the token-built
catalog of exactly 50); the merchant-facing catalog is
``layout_preset_registry.list_ready_templates()`` which now lists 53.

No renderer, partial or CSS selector in the engine knows these template keys:
every visual difference is selected by registered section variants, card
styles, global header/footer variants and palettes, all reusable by any Store.
"""

from __future__ import annotations

from .appearance_registry import PaletteDefinition, register_palette
from .layout_preset_registry import (
    LayoutPresetDefinition,
    PresetSectionEntry,
    _BEAUTY_RETAIL_CARD,
    _BEAUTY_WALL_ROW,
    _RETAIL_LIST_CARD,
    _complete_store_appearance,
    _u10_standard_non_home_pages,
    authored_legacy_home,
    get_layout_preset,
    register_layout_preset,
)

# ==================================================================
# 51 — stationery_spectrum
# ==================================================================

# Tones are the five coloured bands of the reference in order (red, green, amber, indigo, blue);
# the dark footer role and the white card tiles come from the same palette. Merchant-selectable
# like every palette; text/fill pairs are derived by the accessible-colour layer.
register_palette(PaletteDefinition(
    slug="spectrum-stationery",
    name_fa="طیف لوازم تحریر",
    group_fa="پرفروش",
    colors={
        "primary": "#169B48", "secondary": "#48484E", "accent": "#E5334B",
        "background": "#F4F5F9", "surface": "#FFFFFF", "text": "#262A30",
        "muted": "#5F6670", "border": "#E1E4EA",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#262A30",
        "nav_bg": "#FFFFFF", "nav_text": "#262A30",
        "card_bg": "#FFFFFF", "footer_bg": "#48484E",
        "footer_text": "#FFFFFF", "price": "#169B48",
    },
    section_tones=("#EA364E", "#18BA60", "#BA6600", "#301890", "#005496"),
))

_SPECTRUM_VERSION = "1"

_SPECTRUM_CARD = {
    "card_style": "center_stepper", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_quick_add": True, "show_badge": True,
    "show_price": True, "card_border": True, "image_ratio": "square",
    "quick_add_reveal": "always", "show_quick_view": False,
}
_SPECTRUM_OFFER_CARD = {**_SPECTRUM_CARD, "card_style": "compact", "show_quick_add": False}
_SPECTRUM_SPACING = {"vertical_spacing": "small"}


def _spectrum_band(title: str, data_source: str, tone: str) -> PresetSectionEntry:
    """A coloured, doodle-patterned six-card rail (palette tone 1..5)."""
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "item_limit": 6,
        "display_mode": "carousel", "show_view_all": True,
        "responsive": {"desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2},
        "card": _SPECTRUM_CARD,
        "background": {"mode": "palette_pattern", "pattern_slug": "commerce-doodle", "palette_role": tone},
        "spacing": _SPECTRUM_SPACING,
    })


def _spectrum_pair(row_key: str, title: str, data_source: str, *, first: bool) -> PresetSectionEntry:
    """One half of a 6/6 pair of white three-card rails."""
    return PresetSectionEntry(
        "product_section", row_key=row_key, row_span=6,
        container_settings=({"gap": 12, "mobile_mode": "stack", "height_mode": "equal"} if first else None),
        settings={
            "title": title, "data_source": data_source, "item_limit": 6,
            "display_mode": "carousel", "show_view_all": True,
            "responsive": {"desktop_columns": 3, "tablet_columns": 3, "mobile_columns": 2},
            "card": {**_SPECTRUM_CARD, "card_border": False},
            "spacing": _SPECTRUM_SPACING,
        },
    )


# Section order follows the reference top to bottom (strip banner, hero + side offer, category circles, service
# strip, four tiles, five coloured bands interleaved with the amazing-offer block and the white paired rails,
# brands, blog).  The two blank white panel pairs of the capture are lazy-load gaps, so those slots carry the
# same paired-rail component the page uses elsewhere.
_SPECTRUM_HOME = (
    PresetSectionEntry("multi_banner", settings={
        "item_limit": 1, "offset": 0, "layout_variant": "strip-art",
        "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
        "spacing": _SPECTRUM_SPACING,
    }),
    PresetSectionEntry(
        "product_section", row_key="spectrum-hero-row", row_span=3,
        container_settings={"gap": 8, "mobile_mode": "stack", "vertical_align": "start", "height_mode": "equal"},
        settings={
            "title": "پیشنهادهای لحظه‌ای", "data_source": "discounted", "item_limit": 4,
            "display_mode": "carousel", "show_view_all": False,
            "carousel_autoplay": True, "carousel_interval_ms": 3500,
            "carousel_show_arrows": True, "header_position": "inside",
            "responsive": {"desktop_columns": 1, "tablet_columns": 1, "mobile_columns": 1},
            "card": _SPECTRUM_OFFER_CARD, "spacing": _SPECTRUM_SPACING,
        },
    ),
    PresetSectionEntry("hero_banner", row_key="spectrum-hero-row", row_span=9, settings={
        "hero_style": "overlay", "text_position": "start", "layout": {"height": "standard"}, "spacing": _SPECTRUM_SPACING,
    }),
    PresetSectionEntry("category_grid", settings={
        "title": "", "display_mode": "grey_circles", "item_limit": 6,
        "spacing": _SPECTRUM_SPACING,
    }),
    PresetSectionEntry("trust_features", settings={
        "items": [
            {"icon": "↙", "title": "تضمین بهترین قیمت", "subtitle": "خرید مطمئن"},
            {"icon": "◎", "title": "ضمانت اصالت کالا", "subtitle": "کالای اصل"},
            {"icon": "▣", "title": "پرداخت امن", "subtitle": "درگاه و کارت"},
            {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت آسان"},
            {"icon": "⇢", "title": "ارسال سریع", "subtitle": "به سراسر کشور"},
        ],
        "spacing": _SPECTRUM_SPACING,
    }),
    PresetSectionEntry("multi_banner", settings={
        "item_limit": 4, "offset": 0, "layout_variant": "tile-4",
        "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
        "spacing": _SPECTRUM_SPACING,
    }),
    _spectrum_band("لوازم‌التحریر و اداری", "most_viewed", "tone-1"),
    PresetSectionEntry("amazing_offers", settings={
        "item_limit": 4, "deadline_hours": 8, "title": "پیشنهاد شگفت‌انگیز",
        "spacing": _SPECTRUM_SPACING,
    }),
    _spectrum_band("هنر، نقاشی و کاردستی", "newest", "tone-2"),
    _spectrum_pair("spectrum-pair-a", "پیشنهادهای منتخب", "newest", first=True),
    _spectrum_pair("spectrum-pair-a", "محبوب‌ترین انتخاب‌ها", "most_viewed", first=False),
    _spectrum_band("دفتر و کاغذ", "discounted", "tone-3"),
    _spectrum_pair("spectrum-pair-b", "انتخاب روز", "discounted", first=True),
    _spectrum_pair("spectrum-pair-b", "بیشتر دیده‌شده‌ها", "most_viewed", first=False),
    _spectrum_pair("spectrum-pair-c", "ابزار کار هنری، ترکیبی و دستی", "newest", first=True),
    _spectrum_pair("spectrum-pair-c", "انواع روبان", "most_viewed", first=False),
    _spectrum_band("چراغ، کابل و لوازم برقی", "best_sellers", "tone-4"),
    _spectrum_pair("spectrum-pair-d", "برچسب فانتزی و آموزشی", "most_viewed", first=True),
    _spectrum_pair("spectrum-pair-d", "کتاب، پوستر و فلش‌کارت", "newest", first=False),
    _spectrum_band("بازی و آموزش", "newest", "tone-5"),
    PresetSectionEntry("brand_carousel", settings={
        "title": "بهترین برندهای فروشگاه", "display_mode": "carousel", "show_view_all": False,
        "spacing": _SPECTRUM_SPACING,
    }),
    PresetSectionEntry("blog_posts", settings={"title": "مجله فروشگاه", "item_limit": 6}),
)
_SPECTRUM_NAMES = (
    "banner_strip", "offer_flash", "hero", "categories", "trust", "banner_tiles",
    "products_band_1", "amazing_offers", "products_band_2",
    "products_pair_a1", "products_pair_a2", "products_band_3",
    "products_pair_b1", "products_pair_b2", "products_pair_c1", "products_pair_c2",
    "products_band_4", "products_pair_d1", "products_pair_d2", "products_band_5",
    "brands", "blog",
)

register_layout_preset(LayoutPresetDefinition(
    key="stationery_spectrum",
    version=_SPECTRUM_VERSION,
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="stationery_search", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="none",
        footer="stationery_dark", bottom_nav="hidden",
    ),
    label_fa="تحریر رنگی",
    description_fa="بازارگاه رنگی لوازم تحریر و هنر با نوار تصویری، Hero و پیشنهاد جانبی، دایره‌های دسته‌بندی، ردیف‌های رنگیِ طرح‌دار و فوتر تجاری کامل.",
    appearance={
        "font": "Vazirmatn", "radius": 7, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1500, "grid_density": 6,
        "card_shadow": "none", "card_hover": "none", "hero_style": "wide",
    },
    default_palette_slug="spectrum-stationery",
    header={
        "sticky": False, "announcement_enabled": False,
        "show_search": True, "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "stationery_search",
    },
    footer={
        "show_about": True, "show_contact": True, "show_categories": True,
        "show_quick_links": True, "show_social": True,
        "show_trust_badges": True, "show_payment_logos": True,
        "show_newsletter": False, "show_copyright": True,
        "footer_variant": "stationery_dark",
        "extra_blocks": [
            {"type": "custom_text", "title": "خدمات فروشگاه", "text": "ارسال سریع • ضمانت اصالت • پرداخت امن • پشتیبانی خرید"},
        ],
    },
    pages={
        "home": authored_legacy_home("stationery_spectrum", _SPECTRUM_HOME, _SPECTRUM_NAMES),
        **_u10_standard_non_home_pages(),
    },
))

# ==================================================================
# 52 — magenta_beauty_retail
# ==================================================================

# Orchid retail palette: magenta campaign band, mint campaign band and the deep-purple category
# wall are tones 1-3; the price/footer roles carry the brand purple (green stays reserved for
# commerce actions). Generic and merchant-selectable like every other palette.
register_palette(PaletteDefinition(
    slug="orchid-retail",
    name_fa="ارکیده فروشگاهی",
    group_fa="زیبایی",
    colors={
        "primary": "#8A007A", "secondary": "#C00C8A", "accent": "#63CF70",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#26212A",
        "muted": "#6B656F", "border": "#E8E3E9",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#26212A",
        "nav_bg": "#FFFFFF", "nav_text": "#26212A",
        "card_bg": "#FFFFFF", "footer_bg": "#FFFFFF",
        "footer_text": "#4A4350", "price": "#8A007A",
    },
    section_tones=("#C00C8A", "#7E006C", "#6CCC6C", "#F7D6E9", "#F2EAF6"),
))

_ORCHID_CARD = {**_BEAUTY_RETAIL_CARD, "show_rating": False, "show_quick_view": False, "image_ratio": "landscape"}
_ORCHID_WALL_ROW = _BEAUTY_WALL_ROW


def _orchid_row(title: str, data_source: str, *, background: dict) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "display_mode": "campaign_band",
        "item_limit": 4, "card": _ORCHID_CARD,
        "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
        "background": background,
    })


register_layout_preset(LayoutPresetDefinition(
    key="magenta_beauty_retail",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="beauty_search_nav", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="beauty_retail_columns", bottom_nav="hidden",
    ),
    label_fa="زیبایی ارغوانی",
    description_fa="فروشگاه آرایشی و عطر با جستجوی برجسته، کاشی‌های آیکنی دسته‌بندی، ردیف‌های کمپینی رنگی، کاشی‌های گرادیانی بزرگ و ستون‌های ویژه دسته‌بندی.",
    appearance={
        "font": "Vazirmatn", "radius": 10, "button_radius": 6,
        "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "zoom",
        "card_image_crossfade": True, "card_image_zoom": True,
        "content_width": 1500,
    },
    default_palette_slug="orchid-retail",
    header={
        "sticky": True, "announcement_enabled": False, "show_search": True,
        "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "beauty_search_nav",
    },
    footer={
        "show_newsletter": False, "show_trust_badges": True,
        "show_payment_logos": True, "footer_variant": "beauty_retail_columns",
    },
    pages={
        "home": authored_legacy_home("magenta_beauty_retail", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "beauty_editorial", "text_position": "start",
                "autoplay": True, "interval_ms": 4500,
                "show_arrows": False, "show_dots": True,
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "دسته‌بندی محصولات", "display_mode": "icon_tiles", "item_limit": 6,
            }),
            _orchid_row("شگفت‌انگیزهای فروشگاه", "discounted", background={
                "mode": "palette_pattern", "palette_role": "tone-1", "pattern_slug": "commerce-doodle",
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "", "display_mode": "gradient_tiles", "item_limit": 4,
            }),
            _orchid_row("جدیدترین‌های فروشگاه", "newest", background={
                "mode": "palette", "palette_role": "tone-3",
            }),
            PresetSectionEntry("brand_carousel", settings={
                "title": "محبوب‌ترین برندها", "display_mode": "beauty_tabs", "show_view_all": False,
            }),
            PresetSectionEntry("catalog_product_wall", settings={
                "title": "فروش ویژه محصولات بر اساس دسته‌بندی",
                "layout_mode": "group_columns",
                "source_mode": "categories_then_collections", "max_groups": 3,
                "products_per_group": 3, "minimum_products": 2, "skip_empty_groups": True,
                "show_view_all": True, "card": _RETAIL_LIST_CARD,
                "background": {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": "commerce-doodle"},
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 2, "offset": 4, "layout_variant": "wide-single",
                "responsive": {"desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1},
            }),
            PresetSectionEntry("catalog_product_wall", settings={
                "title": "دسته‌بندی محصولات پیشنهادی",
                "layout_mode": "featured_row",
                "source_mode": "visible_collections", "max_groups": 1,
                "products_per_group": 10, "minimum_products": 3, "skip_empty_groups": True,
                "show_view_all": True, "card": _ORCHID_CARD, **_ORCHID_WALL_ROW,
                "background": {"mode": "palette_pattern", "palette_role": "tone-2", "pattern_slug": "commerce-doodle"},
            }),
            PresetSectionEntry("newsletter", settings={
                "title": "عضویت در خبرنامه",
                "subtitle": "ایمیل خود را ثبت کنید تا پیشنهادها و محصولات تازه را از دست ندهید.",
                "button_label": "ثبت نام",
                "background": {"mode": "color", "color": "#F6F6F6"},
            }),
            PresetSectionEntry("trust_features"),
        ), (
            "hero", "categories_icons", "products_campaign_discounted", "categories_gradient",
            "products_campaign_newest", "brands", "wall_category_groups", "banner_pair",
            "wall_collections", "newsletter", "trust",
        )),
        **_u10_standard_non_home_pages(),
    },
))

# ==================================================================
# 53 — pastel_kawaii_stationery
# ==================================================================

# Soft lilac / signal-red stationery palette: neutral white page, lilac action colour, red
# announcement band (tones 1-2). Generic and merchant-selectable.
register_palette(PaletteDefinition(
    slug="pastel-lilac",
    name_fa="یاسی پاستلی",
    group_fa="نرم",
    colors={
        "primary": "#8D50C4", "secondary": "#22222A", "accent": "#EE1941",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#2A2A34",
        "muted": "#6C6C7B", "border": "#ECECF0",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#2A2A34",
        "nav_bg": "#F6F6F6", "nav_text": "#4A4A55",
        "card_bg": "#FFFFFF", "footer_bg": "#FFFFFF",
        "footer_text": "#55556A", "price": "#6C6C7B",
    },
    section_tones=("#EA1842", "#A20000", "#D7F3DC", "#FDE6D2", "#D8F0FB"),
))

_PASTEL_CARD = {
    "card_style": "pastel_flat", "image_ratio": "square",
    "show_brand": False, "show_rating": False, "show_wishlist": False,
    "show_badge": True, "show_quick_add": False, "card_border": False,
    "show_quick_view": False,
}


def _pastel_grid(title: str, data_source: str, limit: int, *, pager: bool) -> PresetSectionEntry:
    """A repeated four-column catalogue group; ``pager`` adds the closing bar."""
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "display_mode": "catalog_grid",
        "item_limit": limit, "show_view_all": pager, "card": _PASTEL_CARD,
        "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
    })


def _plain_block(position: str, *, title: str = "عنوان بخش") -> PresetSectionEntry:
    """Editorial split block (picture panel + title/text); copy is an instruction, not marketing text."""
    return PresetSectionEntry("image_text", settings={
        "title": title, "body_html": "<p>متن این بخش را از ویرایشگر وارد کنید.</p>",
        "image_position": position, "block_style": "plain",
    })


register_layout_preset(LayoutPresetDefinition(
    key="pastel_kawaii_stationery",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="kawaii_center", hero="legacy_default", layout="quarters",
        product_view="legacy_default", card="legacy_default", badge="none", motion="subtle",
        footer="kawaii_minimal", bottom_nav="hidden",
    ),
    label_fa="کاغذ پاستلی",
    description_fa="کاتالوگ بلند لوازم تحریر و کاغذ با هدر مرکزی و نوار اعلان دوگانه، پوستر عریض، کاشی‌های پاستلی تخت، گروه‌های چهارستونه با نوار صفحه‌بندی و بلوک‌های محتوایی.",
    appearance={
        "font": "Vazirmatn", "radius": 0, "button_radius": 3,
        "density": "relaxed", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none",
        "card_shadow": "none", "card_hover": "none", "content_width": 1200,
    },
    default_palette_slug="pastel-lilac",
    header={
        "sticky": False, "announcement_enabled": True, "show_search": True,
        "show_account": True, "show_wishlist": False, "show_cart": True,
        "header_variant": "kawaii_center",
    },
    footer={
        "show_about": True, "show_quick_links": True, "show_social": True,
        "show_copyright": True, "show_newsletter": False, "show_trust_badges": False,
        "show_payment_logos": False, "show_contact": False, "show_categories": False,
        "footer_variant": "kawaii_minimal",
    },
    pages={
        "home": authored_legacy_home("pastel_kawaii_stationery", (
            PresetSectionEntry("hero_banner", settings={
                "hero_style": "poster_wide", "autoplay": True, "interval_ms": 5000,
                "show_arrows": True, "show_dots": False, "text_position": "start",
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 4, "offset": 0, "layout_variant": "mini-4",
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "محصولات فروشگاه", "display_mode": "pastel_tiles", "item_limit": 6,
            }),
            _pastel_grid("جدیدترین محصولات", "newest", 12, pager=True),
            _pastel_grid("پرطرفدارترین‌ها", "most_viewed", 24, pager=False),
            _pastel_grid("محصولات ویژه فروشگاه", "newest", 16, pager=True),
            _plain_block("left"),
            _pastel_grid("تخفیف‌های فروشگاه", "discounted", 8, pager=True),
            _pastel_grid("پیشنهادهای منتخب", "newest", 8, pager=True),
            _pastel_grid("محبوب‌ها", "most_viewed", 8, pager=True),
            _pastel_grid("برگزیده‌ها", "newest", 8, pager=True),
            _pastel_grid("تازه‌های فروشگاه", "most_viewed", 4, pager=False),
            _plain_block("left"),
            PresetSectionEntry("blog_posts", settings={"title": "مجله فروشگاه", "item_limit": 6}),
            PresetSectionEntry("testimonials", settings={
                "title": "نظرات مشتریان", "style": "avatar_grid",
                "items": [
                    {"name": "نام مشتری", "quote": "متن نظر مشتری در این بخش نمایش داده می‌شود."},
                    {"name": "نام مشتری", "quote": "متن نظر مشتری در این بخش نمایش داده می‌شود."},
                    {"name": "نام مشتری", "quote": "متن نظر مشتری در این بخش نمایش داده می‌شود."},
                    {"name": "نام مشتری", "quote": "متن نظر مشتری در این بخش نمایش داده می‌شود."},
                ],
            }),
        ), (
            "hero", "banner_strip", "categories", "products_grid_a", "products_grid_b1", "products_grid_b2",
            "about_block_a", "products_grid_c", "products_grid_d", "products_grid_e", "products_grid_f",
            "products_grid_g", "about_block_b", "blog", "reviews",
        )),
        **_u10_standard_non_home_pages(),
    },
))
