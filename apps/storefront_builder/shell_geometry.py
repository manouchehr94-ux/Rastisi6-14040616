"""Merchant-editable GEOMETRY and colour of the global header / footer variants.

A header/footer config may carry a sparse ``geometry`` dictionary (key -> value). Which properties a
variant genuinely consumes is declared once in ``SHELL_GEOMETRY`` (``variants`` per property); the
validator, the Design Studio controls and the renderer all read this registry, so a control exists only
where a variant draws it. Values are rendered as ``--gh-*`` / ``--gf-*`` custom properties on the
region root; variant CSS reads them with its historical value as the fallback, so a store that never
sets the block renders exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_colors import (
    SemanticColorError,
    clean_semantic_color,
    semantic_color_css,
    semantic_foreground_css,
)


class ShellGeometryError(ValueError):
    """Invalid geometry block (Persian merchant-facing message)."""


@dataclass(frozen=True)
class ShellGeometryProperty:
    key: str
    region: str  # "header" | "footer"
    label_fa: str
    kind: str  # "int" | "color"
    min_value: int = 0
    max_value: int = 0
    default: int | None = None  # the variant's built-in value (shown as the control's placeholder)
    css_var: str = ""  # int properties: ``--x`` custom property (px); colours: ``--x`` (+ ``--x-fg`` when derived)
    unit: str = "px"
    variants: tuple[str, ...] = ()


#: ``"*"`` in ``variants`` = every variant (the announcement strip is the same shared element in all of them).
_ALL = "*"
_H = "stationery_search"
_F = "stationery_dark"
_FC = "floating_card"
_B = "beauty_search_nav"
#: every footer variant whose root element carries the geometry style (the legacy footer is inline in the shell and draws none)
_FOOTER_GRID_VARIANTS = ("stationery_dark", "marketplace_dense", "premium_columns", "beauty_retail_columns", "chocolate_dark_columns", "dark_tech", "promo_columns")
_FOOTER_VARIANTS_WITH_ROOT_GEOMETRY = ("marketplace_dense", "premium_columns", "boutique_editorial", "dark_tech", "promo_columns",
                                       "beauty_retail_columns", "chocolate_dark_columns", "stationery_dark", "kawaii_minimal", "centered_contact")

SHELL_GEOMETRY: dict[tuple[str, str], ShellGeometryProperty] = {(p.region, p.key): p for p in (
    ShellGeometryProperty("util_height", "header", "ارتفاع نوار بالایی (px)", "int", 24, 80, 40, "--gh-util-h", variants=(_H,)),
    ShellGeometryProperty("main_height", "header", "ارتفاع ردیف اصلی (px)", "int", 40, 140, 50, "--gh-main-h", variants=(_H, _B)),
    ShellGeometryProperty("nav_height", "header", "ارتفاع ردیف ناوبری (px)", "int", 30, 120, 73, "--gh-nav-h", variants=(_H, _B)),
    ShellGeometryProperty("search_max_width", "header", "حداکثر عرض جستجو (px)", "int", 240, 900, 655, "--gh-search-max", variants=(_H, _B)),
    ShellGeometryProperty("search_height", "header", "ارتفاع کادر جستجو (px)", "int", 30, 64, 40, "--gh-search-h", variants=(_H, _B)),
    ShellGeometryProperty("row_gap", "header", "فاصله بین اجزای ردیف اصلی (px)", "int", 0, 40, 18, "--gh-row-gap", variants=(_H,)),
    ShellGeometryProperty("nav_gap", "header", "فاصله بین لینک‌های ناوبری (px)", "int", 0, 40, 8, "--gh-nav-gap", variants=(_H,)),
    ShellGeometryProperty("nav_item_limit", "header", "حداکثر لینک‌های ناوبری (۰ = همه)", "int", 0, 24, 0, "", unit="", variants=(_H,)),
    ShellGeometryProperty("chip_count", "header", "تعداد دکمه‌های برجسته انتهای ناوبری", "int", 0, 4, 2, "", unit="", variants=(_H,)),
    ShellGeometryProperty("chip_radius", "header", "گردیِ دکمه‌های برجسته (px)", "int", 0, 40, 4, "--gh-chip-r", variants=(_H,)),
    ShellGeometryProperty("chip_padding", "header", "فاصله افقی داخل دکمه برجسته (px)", "int", 6, 90, 18, "--gh-chip-pad", variants=(_H,)),
    ShellGeometryProperty("chip_alt_padding", "header", "فاصله افقی داخل دکمه برجسته دوم (px)", "int", 6, 120, 56, "--gh-chip-pad-alt", variants=(_H,)),
    ShellGeometryProperty("chip_fill", "header", "رنگ دکمه برجسته", "color", css_var="--gh-chip-fill", variants=(_H,)),
    ShellGeometryProperty("chip_fill_alt", "header", "رنگ دکمه برجسته دوم", "color", css_var="--gh-chip-fill-alt", variants=(_H,)),
    ShellGeometryProperty("chip_text", "header", "رنگ متن دکمه‌های برجسته", "color", css_var="--gh-chip-text", variants=(_H,)),
    ShellGeometryProperty("card_height", "header", "حداقل ارتفاع کارت هدر (px)", "int", 60, 260, 110, "--gh-fc-card-h", variants=(_FC,)),
    ShellGeometryProperty("card_padding", "header", "فاصلهٔ عمودیِ داخل کارت (px)", "int", 0, 60, 18, "--gh-fc-pad-y", variants=(_FC,)),
    ShellGeometryProperty("card_radius", "header", "گردیِ کارت هدر (px)", "int", 0, 40, 12, "--gh-fc-radius", variants=(_FC,)),
    ShellGeometryProperty("band_height", "header", "ارتفاع نوار رنگیِ پشت کارت (px)", "int", 0, 320, 150, "--gh-fc-band-h", variants=(_FC,)),
    ShellGeometryProperty("band_fill", "header", "رنگ نوار پشت کارت", "color", css_var="--gh-fc-band", variants=(_FC,)),
    ShellGeometryProperty("logo_height", "header", "حداکثر ارتفاع لوگو (px)", "int", 24, 220, 90, "--gh-fc-logo-h", variants=(_FC, _B)),
    # V5 announcement strip (every header variant): colours + the size of the small picture beside the text
    ShellGeometryProperty("announce_bg", "header", "رنگ پس‌زمینهٔ نوار اطلاعیه", "color", css_var="--gh-announce-bg", variants=(_ALL,)),
    ShellGeometryProperty("announce_fg", "header", "رنگ متن نوار اطلاعیه", "color", css_var="--gh-announce-fg", variants=(_ALL,)),
    ShellGeometryProperty("announce_image_size", "header", "اندازهٔ تصویر کنار متن (px)", "int", 16, 64, 24, "--gh-announce-img", variants=(_ALL,)),
    ShellGeometryProperty("announce_height", "header", "حداقل ارتفاع نوار (px)", "int", 32, 120, 32, "--gh-announce-h", variants=(_ALL,)),
    ShellGeometryProperty("announce_padding", "header", "فاصلهٔ عمودیِ داخل نوار (px)", "int", 0, 16, 4, "--gh-announce-py", variants=(_ALL,)),
    # V5 mobile header: 1 = the phone shows a search icon that opens the search bar instead of an always-visible search row
    ShellGeometryProperty("mobile_search_icon", "header", "جست‌وجوی موبایل به‌صورت آیکن (۰ = نوار، ۱ = آیکن)", "int", 0, 1, 0, "", unit="",
                          variants=("promo_search_nav", "marketplace_search_first")),
    # V5 spacious footer (every footer variant): vertical padding and the base text size of the whole footer
    ShellGeometryProperty("pad_y", "footer", "فاصلهٔ عمودی بالا و پایین فوتر (px)", "int", 0, 160, 0, "--gf-pad-y", variants=_FOOTER_VARIANTS_WITH_ROOT_GEOMETRY),
    ShellGeometryProperty("text_size", "footer", "اندازهٔ متن فوتر (px)", "int", 11, 22, 13, "--gf-text", variants=_FOOTER_VARIANTS_WITH_ROOT_GEOMETRY),
    # Column order of the footer grid (1 = first). Only the columns a merchant numbers move; the rest keep the variant's own order.
    ShellGeometryProperty("order_about", "footer", "ترتیب ستون «درباره فروشگاه»", "int", 1, 9, 1, "--gf-o-about", unit="", variants=_FOOTER_GRID_VARIANTS),
    ShellGeometryProperty("order_links", "footer", "ترتیب ستون «لینک‌های مفید»", "int", 1, 9, 2, "--gf-o-links", unit="", variants=_FOOTER_GRID_VARIANTS),
    ShellGeometryProperty("order_categories", "footer", "ترتیب ستون «دسته‌بندی‌ها»", "int", 1, 9, 3, "--gf-o-categories", unit="", variants=_FOOTER_GRID_VARIANTS),
    ShellGeometryProperty("order_contact", "footer", "ترتیب ستون «تماس»", "int", 1, 9, 4, "--gf-o-contact", unit="", variants=_FOOTER_GRID_VARIANTS),
    ShellGeometryProperty("bar_height", "footer", "ارتفاع نوار پیوندها (px، ۰ = خودکار)", "int", 0, 200, 0, "--gf-bar-h", variants=(_F,)),
    ShellGeometryProperty("grid_min_height", "footer", "حداقل ارتفاع بلوک ستون‌ها (px)", "int", 0, 800, 440, "--gf-grid-h", variants=(_F,)),
    ShellGeometryProperty("column_count", "footer", "تعداد ستون‌ها", "int", 2, 6, 4, "--gf-cols", unit="", variants=_FOOTER_GRID_VARIANTS),
    ShellGeometryProperty("column_gap", "footer", "فاصله ستون‌ها (px)", "int", 0, 80, 34, "--gf-col-gap", variants=_FOOTER_GRID_VARIANTS),
    ShellGeometryProperty("divider_spacing", "footer", "فاصله بالای جداکننده و هویت برند (px)", "int", 0, 120, 44, "--gf-divider-gap", variants=(_F,)),
    ShellGeometryProperty("brand_spacing", "footer", "فاصله پایین ناحیه برند (px)", "int", 0, 120, 40, "--gf-brand-gap", variants=(_F,)),
    ShellGeometryProperty("badge_size", "footer", "اندازه نشان‌ها (px)", "int", 32, 120, 64, "--gf-badge-size", variants=(_F,)),
    ShellGeometryProperty("badge_gap", "footer", "فاصله بین نشان‌ها (px)", "int", 0, 40, 14, "--gf-badge-gap", variants=(_F,)),
    ShellGeometryProperty("badge_row_padding", "footer", "فاصله عمودی ردیف نشان‌ها (px)", "int", 0, 60, 20, "--gf-badge-row-pad", variants=(_F,)),
    ShellGeometryProperty("badge_fill", "footer", "رنگ زمینه نشان‌ها", "color", css_var="--gf-badge-bg", variants=(_F,)),
    ShellGeometryProperty("legal_height", "footer", "حداقل ارتفاع ردیف حقوقی (px)", "int", 0, 120, 0, "--gf-legal-h", variants=(_F,)),
)}

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def properties_for(region: str, variant: str | None = None) -> list[ShellGeometryProperty]:
    return [p for (r, _k), p in SHELL_GEOMETRY.items() if r == region and (variant is None or _ALL in p.variants or variant in p.variants)]


def validate_geometry(raw: object, region: str) -> dict:
    """Clean a raw geometry block. Unknown keys are rejected; empty values reset a property; the result is sparse."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ShellGeometryError("تنظیمات ابعاد باید یک شیء باشد")
    cleaned: dict = {}
    for key, value in raw.items():
        prop = SHELL_GEOMETRY.get((region, key))
        if prop is None:
            raise ShellGeometryError(f"ویژگی «{key}» برای این بخش قابل‌تنظیم نیست")
        if value is None or value == "":
            continue
        if prop.kind == "color":
            try:
                color = clean_semantic_color(value)
            except SemanticColorError as exc:
                raise ShellGeometryError(str(exc)) from exc
            if color:
                cleaned[key] = color
            continue
        try:
            number = int(str(value).translate(_DIGITS))
        except (TypeError, ValueError):
            raise ShellGeometryError(f"مقدار «{prop.label_fa}» باید عدد باشد") from None
        cleaned[key] = max(prop.min_value, min(prop.max_value, number))
    return cleaned


def merge_patch(current: object, posted: object) -> dict:
    """Merge a posted partial geometry patch onto the stored block (``None``/"" clears one key)."""
    merged = dict(current) if isinstance(current, dict) else {}
    if isinstance(posted, dict):
        for key, value in posted.items():
            if value is None or value == "":
                merged.pop(key, None)
            else:
                merged[key] = value
    return merged


def geometry_style(geometry: object, region: str) -> str:
    """Inline ``style`` fragment (``--x:y;--z:w``) for a validated geometry block, or ``""``."""
    if not isinstance(geometry, dict) or not geometry:
        return ""
    css: list[str] = []
    for key, value in geometry.items():
        prop = SHELL_GEOMETRY.get((region, key))
        if prop is None or not prop.css_var:
            continue
        if prop.kind == "color":
            resolved = semantic_color_css(value)
            if resolved:
                css.append(f"{prop.css_var}:{resolved}")
                if key == "chip_fill" and not geometry.get("chip_text"):
                    css.append(f"--gh-chip-text:{semantic_foreground_css(value)}")
        else:
            css.append(f"{prop.css_var}:{value}{prop.unit}")
    return ";".join(css)


def serialize_for_inspector(region: str, variant: str | None, current: object) -> list[dict]:
    """Control metadata (+ current values) for the Design Studio global panel, only for properties the
    selected variant actually consumes."""
    current = current if isinstance(current, dict) else {}
    return [{
        "key": p.key, "label": p.label_fa, "kind": p.kind, "min": p.min_value, "max": p.max_value,
        "default": p.default, "value": current.get(p.key, ""),
    } for p in properties_for(region, variant)]
