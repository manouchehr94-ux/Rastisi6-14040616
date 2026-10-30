"""Hero Stage Ready Templates 60-63 — four official recipes over the ONE generic ``hero_stage`` section.

* ``dual_atelier``      (60) — two-picture atelier hero, the real header drawn inside the stage, a glass panel in the centre.
* ``editorial_noir``    (61) — magazine cover: dark picture, masthead header inside the hero, bottom-start headline and a floating
  product card that is a real product of the Store.
* ``glass_commerce``    (62) — picture-first commerce hero with a glass category bar (real Store categories) at its foot.
* ``asymmetric_canvas`` (63) — 70/30 two-picture canvas, floating transparent header over the picture, bottom-start headline.

Like every Ready Template they register through ``register_layout_preset`` and inherit its fail-closed import-time validation.
They are pure data: every visual difference is a setting of a registered, reusable engine feature (``hero_stage`` settings, global
header/footer variants, card styles, palette tokens). No renderer, partial or CSS selector knows these template keys, so a merchant can
re-combine any of their parts (e.g. the header of one with the stage of another) from the Studio. The recipes carry structure and neutral
copy only; the Store supplies its own pictures (until it does, the stage shows its fallback colour — never a stock photo).
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

_STAGE_COPY = {"title": "کالکشن تازه رسید", "subtitle": "انتخاب‌های دقیق برای سبک شما", "button_label": "مشاهده محصولات"}


def _stage(**settings) -> PresetSectionEntry:
    return PresetSectionEntry("hero_stage", settings={**_STAGE_COPY, **settings})


def _shelf(title: str, source: str, mode: str, card: dict, columns: int, **extra) -> PresetSectionEntry:
    return PresetSectionEntry("product_section", settings={
        "title": title, "data_source": source, "display_mode": mode, "item_limit": extra.pop("item_limit", 8), "card": card,
        "responsive": {"desktop_columns": columns, "tablet_columns": min(columns, 3), "mobile_columns": 2},
        **extra,
    })


# ==================================================================
# 60 — dual_atelier
# ==================================================================

register_palette(PaletteDefinition(
    slug="atelier-linen",
    name_fa="کتان آتلیه",
    group_fa="آرام",
    colors={
        "primary": "#3B3A36", "secondary": "#2B2825", "accent": "#B08D57", "background": "#F6F1E9", "surface": "#FFFFFF",
        "text": "#26231F", "muted": "#6E675D", "border": "#DDD5C8",
    },
    theme_roles={
        "header_bg": "#F6F1E9", "header_text": "#26231F", "nav_bg": "#F6F1E9", "nav_text": "#26231F",
        "card_bg": "#FFFFFF", "footer_bg": "#2B2825", "footer_text": "#EFE9DF", "price": "#6B4F24",
    },
    section_tones=("#E9DFCF", "#CBB892", "#2B2825", "#B08D57", "#F6F1E9"),
))

_LINEN_CARD = {
    "card_style": "outline_plain", "image_ratio": "portrait", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": False, "show_quick_add": False, "show_quick_view": False, "card_border": False,
}

register_layout_preset(LayoutPresetDefinition(
    key="dual_atelier",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="atelier_nav", hero="legacy_default", layout="quarters", product_view="legacy_default", card="legacy_default",
        badge="none", motion="subtle", footer="centered_contact", bottom_nav="hidden",
    ),
    label_fa="آتلیه دوپنل (هدر یکپارچه با دو تصویر)",
    description_fa="بوم هیروی دوپنلی با دو تصویر مستقل، هدر واقعی فروشگاه داخل همان بوم و پنل شیشه‌ای وسط؛ مناسب مد و پوشاک.",
    appearance={
        "font": "Estedad", "radius": 4, "button_radius": 4, "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "filled", "image_fit": "cover", "image_hover": "none", "card_image_crossfade": False,
        "card_image_zoom": False, "content_width": 1200, "card_shadow": "none", "card_hover": "none", "heading_style": "centered_rule",
    },
    default_palette_slug="atelier-linen",
    header={"sticky": False, "announcement_enabled": False, "show_search": True, "show_account": True, "show_wishlist": False,
            "show_cart": True, "header_variant": "atelier_nav"},
    footer={"show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": True, "show_social": True,
            "show_trust_badges": False, "show_payment_logos": True, "show_newsletter": False, "show_copyright": True,
            "footer_variant": "centered_contact"},
    pages={
        "home": authored_legacy_home("dual_atelier", (
            _stage(
                header_mode="merged", bg_layout="dual", bg_split="equal", mobile_dual="stack", text_tone="light",
                content_align="center", content_valign="middle", scrim_style="both", scrim_strength=52,
                content_frame="glass", frame_opacity=38, frame_blur=14, frame_radius=4, frame_border="thin", frame_shadow="off",
                title_size="lg", title_weight="black", height_desktop=88, height_tablet=78, height_mobile=74,
                eyebrow="کالکشن جدید", fallback_color="token:secondary",
                slots=[{"key": "eyebrow"}, {"key": "title"}, {"key": "subtitle"}, {"key": "cta"}],
            ),
            PresetSectionEntry("category_grid", settings={"title": "دسته‌بندی‌ها", "display_mode": "label_tiles", "item_limit": 4}),
            _shelf("تازه‌ها", "newest", "grid", _LINEN_CARD, 4),
            PresetSectionEntry("image_text", settings={"title": "داستان برند", "body_html": "<p>اینجا داستان برند و فرایند ساخت محصولات را بنویسید.</p>"}),
            _shelf("پرفروش‌ها", "best_sellers", "carousel", _LINEN_CARD, 4, carousel_navigation="arrows"),
        ), ("hero", "categories", "products_newest", "brand_story", "products_bestsellers")),
        **_u10_standard_non_home_pages(),
    },
))


# ==================================================================
# 61 — editorial_noir
# ==================================================================

register_palette(PaletteDefinition(
    slug="noir-gold",
    name_fa="سیاه و زر",
    group_fa="تیره",
    colors={
        "primary": "#E2B94A", "secondary": "#15151A", "accent": "#E2B94A", "background": "#0F0F13", "surface": "#1A1A21",
        "text": "#F3F1EC", "muted": "#B4B0A6", "border": "#2E2E38",
    },
    theme_roles={
        "header_bg": "#0F0F13", "header_text": "#F3F1EC", "nav_bg": "#0F0F13", "nav_text": "#F3F1EC",
        "card_bg": "#1A1A21", "footer_bg": "#0A0A0D", "footer_text": "#E9E6DF", "price": "#E2B94A",
    },
    section_tones=("#1A1A21", "#2E2E38", "#E2B94A", "#0A0A0D", "#3A3A46"),
))

_NOIR_CARD = {
    "card_style": "outline_plain", "image_ratio": "portrait", "show_brand": True, "show_rating": False,
    "show_wishlist": False, "show_badge": True, "show_quick_add": False, "show_quick_view": False, "card_border": True,
}

register_layout_preset(LayoutPresetDefinition(
    key="editorial_noir",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="editorial_masthead", hero="legacy_default", layout="three_column", product_view="legacy_default",
        card="legacy_default", badge="none", motion="subtle", footer="dark_tech", bottom_nav="hidden",
    ),
    label_fa="نشریهٔ نوآر (هیروی مجله‌ای با کارت محصول)",
    description_fa="هیروی مجله‌ای تیره با هدر سربرگی داخل تصویر، تیتر بزرگ پایین‌-شروع و یک کارت محصول شناورِ واقعی از همین فروشگاه.",
    appearance={
        "font": "Vazirmatn", "radius": 0, "button_radius": 0, "density": "normal", "motion": "subtle", "type_scale": "large",
        "button_style": "outline", "image_fit": "cover", "image_hover": "zoom", "card_image_crossfade": False,
        "card_image_zoom": True, "content_width": 1320, "card_shadow": "none", "card_hover": "lift", "heading_style": "underline",
    },
    default_palette_slug="noir-gold",
    header={"sticky": False, "announcement_enabled": False, "show_search": True, "show_account": True, "show_wishlist": False,
            "show_cart": True, "header_variant": "editorial_masthead"},
    footer={"show_about": True, "show_contact": True, "show_categories": False, "show_quick_links": True, "show_social": True,
            "show_trust_badges": False, "show_payment_logos": False, "show_newsletter": True, "show_copyright": True,
            "footer_variant": "dark_tech"},
    pages={
        "home": authored_legacy_home("editorial_noir", (
            _stage(
                header_mode="merged", bg_layout="single", text_tone="light", content_align="start", content_valign="bottom",
                scrim_style="both", scrim_strength=62, content_frame="none", frame_radius=0, frame_border="thin", frame_shadow="on",
                title_size="xl", title_weight="black", button_style="solid", card_position="side", product_source="newest",
                height_desktop=90, height_tablet=80, height_mobile=78, eyebrow="شمارهٔ ویژه", fallback_color="token:secondary",
                title="سایه‌های نقره‌ای شب", content_align_mobile="start", title_size_mobile="lg",
                slots=[{"key": "eyebrow"}, {"key": "title"}, {"key": "subtitle", "hide_mobile": True}, {"key": "cta"}, {"key": "product_card"}],
            ),
            _shelf("جدیدترین آثار", "newest", "grid", _NOIR_CARD, 3, item_limit=6),
            PresetSectionEntry("image_text", settings={"title": "سرمقاله", "body_html": "<p>یادداشت سردبیر یا معرفی کالکشن را اینجا بنویسید.</p>"}),
            _shelf("پیشنهادهای ویژه", "discounted", "carousel", _NOIR_CARD, 4, carousel_navigation="arrows"),
        ), ("hero", "products_newest", "editorial", "products_offers")),
        **_u10_standard_non_home_pages(),
    },
))


# ==================================================================
# 62 — glass_commerce
# ==================================================================

register_palette(PaletteDefinition(
    slug="glass-ocean",
    name_fa="اقیانوس شیشه‌ای",
    group_fa="روشن",
    colors={
        "primary": "#0E7C86", "secondary": "#0B3C49", "accent": "#E8923B", "background": "#F2F8F9", "surface": "#FFFFFF",
        "text": "#12262B", "muted": "#56707A", "border": "#D3E3E7",
    },
    theme_roles={
        "header_bg": "#FFFFFF", "header_text": "#12262B", "nav_bg": "#FFFFFF", "nav_text": "#12262B",
        "card_bg": "#FFFFFF", "footer_bg": "#0B3C49", "footer_text": "#E3F1F4", "price": "#0E7C86",
    },
    section_tones=("#D9EEF1", "#9FD2D9", "#0B3C49", "#E8923B", "#F2F8F9"),
))

_OCEAN_CARD = {
    "card_style": "lifestyle_cart", "image_ratio": "square", "show_brand": False, "show_rating": False,
    "show_wishlist": False, "show_badge": True, "show_quick_add": True, "show_quick_view": False, "card_border": False,
}

register_layout_preset(LayoutPresetDefinition(
    key="glass_commerce",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="centered_brand", hero="legacy_default", layout="four_column", product_view="legacy_default",
        card="legacy_default", badge="none", motion="subtle", footer="premium_columns", bottom_nav="hidden",
    ),
    label_fa="تجارت شیشه‌ای (هیرو با نوار دسته‌بندی)",
    description_fa="هیروی تصویرمحور با هدر یکپارچه و نوار دسته‌بندیِ شیشه‌ای در پایین تصویر که به دسته‌های واقعی فروشگاه وصل است.",
    appearance={
        "font": "Vazirmatn", "radius": 18, "button_radius": 14, "density": "normal", "motion": "subtle", "type_scale": "normal",
        "button_style": "filled", "image_fit": "cover", "image_hover": "zoom", "card_image_crossfade": True,
        "card_image_zoom": True, "content_width": 1200, "card_shadow": "soft", "card_hover": "lift", "heading_style": "default",
    },
    default_palette_slug="glass-ocean",
    header={"sticky": False, "announcement_enabled": False, "show_search": True, "show_account": True, "show_wishlist": True,
            "show_cart": True, "header_variant": "centered_brand"},
    footer={"show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": True, "show_social": True,
            "show_trust_badges": True, "show_payment_logos": True, "show_newsletter": True, "show_copyright": True,
            "footer_variant": "premium_columns"},
    pages={
        "home": authored_legacy_home("glass_commerce", (
            _stage(
                header_mode="merged", bg_layout="single", text_tone="light", content_align="center", content_valign="bottom",
                scrim_style="bottom", scrim_strength=58, content_frame="none", frame_radius=18, frame_border="thin", frame_shadow="off",
                title_size="lg", title_weight="bold", button_style="glass", category_limit=6, height_desktop=82, height_tablet=74,
                height_mobile=72, fallback_color="token:secondary", title="تابستان روشن", subtitle="همه چیز برای خانه و سبک زندگی",
                slots=[{"key": "title"}, {"key": "subtitle"}, {"key": "cta"}, {"key": "categories"}],
            ),
            _shelf("پرفروش‌ها", "best_sellers", "carousel", _OCEAN_CARD, 5, carousel_navigation="arrows", item_limit=10),
            PresetSectionEntry("category_grid", settings={"title": "خرید بر اساس دسته", "display_mode": "label_tiles", "item_limit": 6}),
            _shelf("تازه‌ها", "newest", "grid", _OCEAN_CARD, 4),
            PresetSectionEntry("trust_features"),
        ), ("hero", "products_bestsellers", "categories", "products_newest", "trust")),
        **_u10_standard_non_home_pages(),
    },
))


# ==================================================================
# 63 — asymmetric_canvas
# ==================================================================

register_palette(PaletteDefinition(
    slug="canvas-terracotta",
    name_fa="بوم تراکوتا",
    group_fa="گرم",
    colors={
        "primary": "#C0503A", "secondary": "#2B2830", "accent": "#E9B48A", "background": "#FBF6F1", "surface": "#FFFFFF",
        "text": "#2A2420", "muted": "#74655C", "border": "#EADCCF",
    },
    theme_roles={
        "header_bg": "#FBF6F1", "header_text": "#2A2420", "nav_bg": "#FBF6F1", "nav_text": "#2A2420",
        "card_bg": "#FFFFFF", "footer_bg": "#2B2830", "footer_text": "#F2E9E0", "price": "#A23F2B",
    },
    section_tones=("#F3DCCB", "#E9B48A", "#2B2830", "#C0503A", "#FBF6F1"),
))

_CANVAS_CARD = {
    "card_style": "outline_plain", "image_ratio": "portrait", "show_brand": False, "show_rating": False,
    "show_wishlist": True, "show_badge": True, "show_quick_add": False, "show_quick_view": False, "card_border": False,
}

register_layout_preset(LayoutPresetDefinition(
    key="asymmetric_canvas",
    version="1",
    is_ready_template=True,
    store_appearance=_complete_store_appearance(
        header="floating_compact", hero="legacy_default", layout="two_column", product_view="legacy_default",
        card="legacy_default", badge="none", motion="subtle", footer="boutique_editorial", bottom_nav="hidden",
    ),
    label_fa="بوم نامتقارن (هدر شناور روی تصویر)",
    description_fa="هیروی دو تصویری با نسبت ۷۰ به ۳۰، هدر شفافِ شناور روی تصویر و تیتر بزرگ پایین‌-شروع؛ ترازِ موبایل جدا قابل تنظیم است.",
    appearance={
        "font": "Estedad", "radius": 10, "button_radius": 0, "density": "relaxed", "motion": "subtle", "type_scale": "large",
        "button_style": "outline", "image_fit": "cover", "image_hover": "zoom", "card_image_crossfade": False,
        "card_image_zoom": True, "content_width": 1320, "card_shadow": "none", "card_hover": "zoom", "heading_style": "plain",
    },
    default_palette_slug="canvas-terracotta",
    header={"sticky": False, "announcement_enabled": False, "show_search": True, "show_account": True, "show_wishlist": False,
            "show_cart": True, "header_variant": "floating_compact"},
    footer={"show_about": True, "show_contact": True, "show_categories": True, "show_quick_links": False, "show_social": True,
            "show_trust_badges": False, "show_payment_logos": False, "show_newsletter": True, "show_copyright": True,
            "footer_variant": "boutique_editorial"},
    pages={
        "home": authored_legacy_home("asymmetric_canvas", (
            _stage(
                header_mode="overlay", bg_layout="dual", bg_split="first_dominant", mobile_dual="first_only", text_tone="light",
                content_align="start", content_valign="bottom", content_align_tablet="start", content_align_mobile="start",
                scrim_style="bottom", scrim_strength=55, content_frame="none", frame_radius=10, frame_border="none",
                title_size="xl", title_weight="bold", button_style="outline", height_desktop=92, height_tablet=82, height_mobile=78,
                eyebrow="مجموعهٔ تازه", fallback_color="token:secondary", title="فرم، رنگ، حرکت", title_size_mobile="lg",
                slots=[{"key": "eyebrow"}, {"key": "title"}, {"key": "subtitle", "hide_mobile": True}, {"key": "cta"}],
            ),
            _shelf("پیشنهاد امروز", "newest", "grid", _CANVAS_CARD, 3, item_limit=6),
            PresetSectionEntry("image_text", settings={"title": "دربارهٔ ما", "body_html": "<p>معرفی کوتاه برند و روش کار شما.</p>"}),
            PresetSectionEntry("category_grid", settings={"title": "دسته‌بندی‌ها", "display_mode": "label_tiles", "item_limit": 6}),
            _shelf("پرفروش‌ها", "best_sellers", "carousel", _CANVAS_CARD, 4, carousel_navigation="dots"),
        ), ("hero", "products_newest", "brand_story", "categories", "products_bestsellers")),
        **_u10_standard_non_home_pages(),
    },
))
