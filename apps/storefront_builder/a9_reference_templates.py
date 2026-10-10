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

_SPECTRUM_VERSION = "1"

_SPECTRUM_CARD = {
    "card_style": "center_stepper", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_quick_add": True, "show_badge": True,
    "show_price": True, "card_border": True, "image_ratio": "square",
    "quick_add_reveal": "always",
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


_SPECTRUM_HOME = (
    PresetSectionEntry("multi_banner", settings={
        "item_limit": 1, "offset": 0, "layout_variant": "strip",
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
        "title": "", "display_mode": "grey_circles", "category_ids": [], "item_limit": 6,
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
        "item_limit": 4, "offset": 0, "layout_variant": "promo-4",
        "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
        "spacing": _SPECTRUM_SPACING,
    }),
    _spectrum_band("لوازم‌التحریر و اداری", "most_viewed", "tone-1"),
    PresetSectionEntry("amazing_offers", settings={
        "item_limit": 4, "deadline_hours": 8, "title": "پیشنهاد شگفت‌انگیز",
        "spacing": _SPECTRUM_SPACING,
    }),
    _spectrum_band("هنر، نقاشی و کاردستی", "newest", "tone-2"),
    _spectrum_pair("spectrum-pair-a", "ابزار کار هنری و دستی", "discounted", first=True),
    _spectrum_pair("spectrum-pair-a", "انواع روبان", "most_viewed", first=False),
    _spectrum_band("دفتر و کاغذ", "most_viewed", "tone-3"),
    _spectrum_pair("spectrum-pair-b", "ابزار دقیق و کارگاهی", "newest", first=True),
    _spectrum_pair("spectrum-pair-b", "نخ و پارچه", "most_viewed", first=False),
    _spectrum_band("چراغ، کابل و لوازم برقی", "discounted", "tone-4"),
    _spectrum_pair("spectrum-pair-c", "برچسب فانتزی و آموزشی", "most_viewed", first=True),
    _spectrum_pair("spectrum-pair-c", "کتاب، پوستر و فلش‌کارت", "newest", first=False),
    PresetSectionEntry("multi_banner", settings={
        "item_limit": 4, "offset": 2, "layout_variant": "mini-4",
        "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
        "spacing": _SPECTRUM_SPACING,
    }),
    _spectrum_band("بازی و آموزش", "newest", "tone-5"),
    PresetSectionEntry("brand_carousel", settings={
        "title": "بهترین برندهای فروشگاه", "display_mode": "carousel", "show_view_all": False, "brand_ids": [],
        "spacing": _SPECTRUM_SPACING,
    }),
    PresetSectionEntry("blog_posts", settings={"title": "مجله فروشگاه", "item_limit": 6}),
)
_SPECTRUM_NAMES = (
    "banner_strip", "offer_flash", "hero", "categories", "trust", "banner_promo",
    "products_band_1", "amazing_offers", "products_band_2",
    "products_pair_a1", "products_pair_a2", "products_band_3",
    "products_pair_b1", "products_pair_b2", "products_band_4",
    "products_pair_c1", "products_pair_c2", "banner_mini", "products_band_5",
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
    description_fa="بازارگاه رنگی لوازم تحریر و هنر با Hero تبلیغاتی، پیشنهاد لحظه‌ای، ردیف‌های رنگی محصول و فوتر تجاری کامل.",
    appearance={
        "font": "Vazirmatn", "radius": 7, "button_radius": 4,
        "density": "compact", "motion": "none", "type_scale": "normal",
        "button_style": "filled", "image_fit": "contain", "image_hover": "none",
        "card_image_crossfade": False, "card_image_zoom": False,
        "content_width": 1500, "grid_density": 6,
        "card_shadow": "none", "card_hover": "none", "hero_style": "wide",
    },
    default_palette_slug="marketplace-spectrum",
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

# Orchid retail palette: the beauty-magenta identity with the price/footer
# roles carried by the brand purple (green stays reserved for commerce
# actions). Generic and merchant-selectable like every other palette.
register_palette(PaletteDefinition(
    slug="orchid-retail",
    name_fa="ارکیده فروشگاهی",
    group_fa="زیبایی",
    colors={
        "primary": "#8A007A", "secondary": "#C90A8B", "accent": "#63CF70",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#26212A",
        "muted": "#77717B", "border": "#E8E3E9",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#26212A",
        "nav_bg": "#FFFFFF", "nav_text": "#26212A",
        "card_bg": "#FFFFFF", "footer_bg": "#FFFFFF",
        "footer_text": "#4A4350", "price": "#8A007A",
    },
    section_tones=("#C90A8B", "#8A007A", "#63CF70", "#F7D6E9", "#F2EAF6"),
))

_ORCHID_CARD = {**_BEAUTY_RETAIL_CARD, "show_rating": False}
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
    description_fa="فروشگاه آرایشی و عطر با جستجوی برجسته، دسته‌بندی آیکنی، ردیف‌های کمپینی رنگی و ستون‌های ویژه دسته‌بندی.",
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
                "title": "دسته‌بندی محصولات", "display_mode": "beauty_icons", "item_limit": 6,
            }),
            _orchid_row("شگفت‌انگیزهای فروشگاه", "discounted", background={
                "mode": "palette_pattern", "palette_role": "tone-1", "pattern_slug": "commerce-doodle",
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 4, "offset": 0, "layout_variant": "promo-4",
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
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
            PresetSectionEntry("product_section", settings={
                "title": "آخرین محصولات مشاهده شده", "data_source": "most_viewed",
                "display_mode": "carousel", "item_limit": 10,
                "card": _ORCHID_CARD, **_ORCHID_WALL_ROW,
            }),
            PresetSectionEntry("newsletter", settings={
                "title": "افسون لاله رخ",
                "subtitle": "اولین نفری باشید که از جدیدترین محصولات، جشنواره‌ها و فروش‌های ویژه مطلع می‌شود.",
                "button_label": "ثبت نام",
                "background": {"mode": "color", "color": "#F6F6F6"},
            }),
            PresetSectionEntry("trust_features"),
        ), (
            "hero", "categories", "products_campaign_discounted", "banner_promo4",
            "products_campaign_newest", "brands", "wall_category_groups", "banner_pair",
            "wall_collections", "products_recently_viewed", "newsletter", "trust",
        )),
        **_u10_standard_non_home_pages(),
    },
))

# ==================================================================
# 53 — pastel_kawaii_stationery
# ==================================================================

# Soft lilac / signal-red stationery palette: neutral white page, lilac action
# colour, red announcement accent. Generic and merchant-selectable.
register_palette(PaletteDefinition(
    slug="pastel-lilac",
    name_fa="یاسی پاستلی",
    group_fa="نرم",
    colors={
        "primary": "#B565E6", "secondary": "#22222A", "accent": "#EE1941",
        "background": "#FFFFFF", "surface": "#FFFFFF", "text": "#2A2A34",
        "muted": "#8B8B99", "border": "#ECECF0",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#2A2A34",
        "nav_bg": "#F4F4F6", "nav_text": "#4A4A55",
        "card_bg": "#FFFFFF", "footer_bg": "#FFFFFF",
        "footer_text": "#55556A", "price": "#6C6C7B",
    },
    section_tones=("#F9D8EA", "#E2D4F8", "#D7F3DC", "#FDE6D2", "#D8F0FB"),
))

_PASTEL_CARD = {
    "card_style": "pastel_flat", "image_ratio": "square",
    "show_brand": False, "show_rating": False, "show_wishlist": False,
    "show_badge": True, "show_quick_add": False, "card_border": False,
}


def _pastel_grid(title: str, data_source: str, limit: int = 12) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": data_source, "display_mode": "catalog_grid",
        "item_limit": limit, "show_view_all": True, "card": _PASTEL_CARD,
        "responsive": {"desktop_columns": 4, "tablet_columns": 3, "mobile_columns": 2},
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
    description_fa="کاتالوگ لوازم تحریر و کاغذ با کاشی‌های پاستلی تخت، هدر مرکزی با نوار اعلان دوگانه و شبکهٔ چهارستونه.",
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
                "hero_style": "overlay", "autoplay": True, "interval_ms": 5000,
                "show_arrows": True, "show_dots": False, "text_position": "start",
            }),
            PresetSectionEntry("multi_banner", settings={
                "item_limit": 4, "offset": 0, "layout_variant": "mini-4",
                "responsive": {"desktop_columns": 4, "tablet_columns": 2, "mobile_columns": 2},
            }),
            PresetSectionEntry("category_grid", settings={
                "title": "محصولات فروشگاه", "display_mode": "pastel_tiles", "item_limit": 6,
            }),
            _pastel_grid("لوازم تحریر و کاغذ", "newest", 12),
            _pastel_grid("محصولات ویژه فروشگاه", "most_viewed", 16),
            PresetSectionEntry("image_text", settings={
                "title": "طراحی‌های اختصاصی فروشگاه",
                "body_html": "<p>در این بخش درباره مجموعه‌ها، کیفیت چاپ و مواد به‌کاررفته در محصولات خود بنویسید. این متن نمونه است و از بخش ویرایش قابل تغییر است.</p>",
                "image_position": "right",
            }),
            _pastel_grid("تخفیف‌های فروشگاه", "discounted", 8),
            _pastel_grid("پرطرفدارها", "most_viewed", 8),
            PresetSectionEntry("image_text", settings={
                "title": "درباره فروشگاه",
                "body_html": "<p>معرفی کوتاه فروشگاه، داستان برند و ارزش‌هایی که برای مشتریان خود دارید را در این بخش بنویسید. این متن نمونه است و از بخش ویرایش قابل تغییر است.</p>",
                "image_position": "left",
            }),
            PresetSectionEntry("blog_posts", settings={"title": "مجله فروشگاه", "item_limit": 6}),
            PresetSectionEntry("trust_features", settings={
                "items": [
                    {"icon": "●", "title": "ارسال سفارش", "subtitle": "اطلاعات ارسال را در این بخش بنویسید"},
                    {"icon": "●", "title": "پرداخت", "subtitle": "روش‌های پرداخت فروشگاه"},
                    {"icon": "●", "title": "بازگشت کالا", "subtitle": "شرایط بازگشت کالا"},
                    {"icon": "●", "title": "پشتیبانی", "subtitle": "راه‌های ارتباط با فروشگاه"},
                ],
            }),
        ), (
            "hero", "banner_strip", "categories", "products_grid_a", "products_grid_b",
            "feature_block", "products_grid_c", "products_grid_d", "about_block",
            "blog", "info_boxes",
        )),
        **_u10_standard_non_home_pages(),
    },
))
