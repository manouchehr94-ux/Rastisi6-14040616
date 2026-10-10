"""The generic, sparse ``design`` block — the merchant-editable look of a section.

``settings["design"]`` is a closed dictionary of design properties. Every key is
OPTIONAL and written only when the merchant (or a Ready Template recipe) sets it,
so a section without the block renders exactly as before. Which properties a
section type exposes is declared once in ``DESIGN_APPLICABLE`` — the validator, the
Design Studio Inspector widget and the renderer all read the same registry, so a
control exists if and only if the renderer consumes it (and vice versa).

Rendering is token driven: the renderer turns the block into CSS custom properties
(``--d-*``) plus a ``data-d`` flag list on the section wrapper. The generic CSS in
``storefront_builder.css`` only acts on the flags that are present. Colours are
semantic (see ``semantic_colors``), never raw CSS.
"""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_colors import (
    SemanticColorError,
    clean_semantic_color,
    semantic_color_css,
    semantic_foreground_css,
)


class DesignSettingsError(ValueError):
    """The raw ``design`` block has an invalid shape or value (merchant-facing Persian message)."""


@dataclass(frozen=True)
class DesignProperty:
    key: str
    label_fa: str
    kind: str  # "color" | "int" | "choice"
    group: str
    min_value: int = 0
    max_value: int = 0
    choices: tuple[tuple[str, str], ...] = ()


_SHADOW_CHOICES = (("", "پیش‌فرض"), ("on", "سایه دارد"), ("off", "بدون سایه"))
_ALIGN_CHOICES = (("", "پیش‌فرض"), ("start", "ابتدا"), ("center", "وسط"), ("end", "انتها"))
_VISIBILITY_CHOICES = (("", "نمایش داده شود"), ("hidden", "مخفی باشد"))
_RATIO_CHOICES = (("", "پیش‌فرض"), ("square", "مربع"), ("portrait", "عمودی"), ("landscape", "افقی"))
_FIT_CHOICES = (("", "پیش‌فرض"), ("cover", "پوشش کامل"), ("contain", "کامل دیده شود"))
_POSITION_CHOICES = (
    ("", "پیش‌فرض"), ("center", "وسط"), ("top", "بالا"), ("bottom", "پایین"), ("left", "چپ"), ("right", "راست"),
)

DESIGN_PROPERTIES: dict[str, DesignProperty] = {p.key: p for p in (
    DesignProperty("text_color", "رنگ متن", "color", "colors"),
    DesignProperty("heading_color", "رنگ عنوان", "color", "colors"),
    DesignProperty("accent_color", "رنگ تأکید (خط و نشانِ عنوان)", "color", "colors"),
    DesignProperty("surface_color", "رنگ سطح (پنل/کارت)", "color", "colors"),
    DesignProperty("border_color", "رنگ حاشیه", "color", "border"),
    DesignProperty("border_width", "ضخامت حاشیه (px)", "int", "border", 0, 8),
    DesignProperty("radius", "گردیِ گوشه‌ها (px)", "int", "border", 0, 40),
    DesignProperty("shadow", "سایه", "choice", "shadow", choices=_SHADOW_CHOICES),
    DesignProperty("shadow_color", "رنگ سایه", "color", "shadow"),
    DesignProperty("shadow_blur", "شدت پخش سایه (px)", "int", "shadow", 0, 60),
    DesignProperty("padding_top", "فاصله داخلی بالا (px)", "int", "spacing", 0, 200),
    DesignProperty("padding_bottom", "فاصله داخلی پایین (px)", "int", "spacing", 0, 200),
    DesignProperty("margin_top", "فاصله بیرونی بالا (px)", "int", "spacing", 0, 200),
    DesignProperty("margin_bottom", "فاصله بیرونی پایین (px)", "int", "spacing", 0, 200),
    DesignProperty("min_height", "حداقل ارتفاع (px)", "int", "layout", 0, 800),
    DesignProperty("align", "تراز عنوان/محتوا", "choice", "layout", choices=_ALIGN_CHOICES),
    DesignProperty("gap", "فاصله بین آیتم‌ها (px)", "int", "layout", 0, 60),
    DesignProperty("columns_desktop", "ستون‌ها در دسکتاپ", "int", "layout", 1, 8),
    DesignProperty("columns_tablet", "ستون‌ها در تبلت", "int", "layout", 1, 6),
    DesignProperty("columns_mobile", "ستون‌ها در موبایل", "int", "layout", 1, 4),
    DesignProperty("item_width", "عرض هر آیتم/کارت (px)", "int", "layout", 60, 420),
    DesignProperty("image_ratio", "نسبت تصویر", "choice", "image", choices=_RATIO_CHOICES),
    DesignProperty("image_fit", "نحوه جاگیری تصویر", "choice", "image", choices=_FIT_CHOICES),
    DesignProperty("image_position", "موقعیت تصویر", "choice", "image", choices=_POSITION_CHOICES),
    DesignProperty("hide_desktop", "نمایش در دسکتاپ", "choice", "visibility", choices=_VISIBILITY_CHOICES),
    DesignProperty("hide_tablet", "نمایش در تبلت", "choice", "visibility", choices=_VISIBILITY_CHOICES),
    DesignProperty("hide_mobile", "نمایش در موبایل", "choice", "visibility", choices=_VISIBILITY_CHOICES),
    DesignProperty("price_color", "رنگ قیمت", "color", "actions"),
    DesignProperty("button_fill", "پس‌زمینه دکمه", "color", "actions"),
    DesignProperty("button_text", "رنگ متن دکمه", "color", "actions"),
    DesignProperty("button_border", "رنگ حاشیه دکمه", "color", "actions"),
)}

DESIGN_GROUP_LABELS_FA = {
    "colors": "رنگ‌ها", "border": "حاشیه و گوشه", "shadow": "سایه", "spacing": "فاصله‌ها",
    "layout": "چیدمان", "image": "تصویر", "visibility": "نمایش در دستگاه‌ها", "actions": "قیمت و دکمه‌ها",
}
DESIGN_GROUP_ORDER = ("colors", "border", "shadow", "spacing", "layout", "image", "visibility", "actions")

_FRAME = ("surface_color", "border_color", "border_width", "radius", "shadow", "shadow_color", "shadow_blur",
          "padding_top", "padding_bottom", "margin_top", "margin_bottom")
_TEXT = ("text_color", "heading_color", "accent_color")
_BUTTONS = ("button_fill", "button_text", "button_border")
_VISIBILITY = ("hide_desktop", "hide_tablet", "hide_mobile")

#: section_key -> design properties that section genuinely consumes.
DESIGN_APPLICABLE: dict[str, tuple[str, ...]] = {
    "surface_panel": (*_FRAME, *_VISIBILITY),
    "product_section": (*_TEXT, *_FRAME, "min_height", "align", "item_width", "image_ratio", "image_fit",
                        "image_position", "price_color", *_BUTTONS, *_VISIBILITY),
    "category_grid": (*_TEXT, *_FRAME, "min_height", "align", "gap", "columns_desktop", "columns_tablet",
                      "columns_mobile", "item_width", "image_fit", "image_position", *_VISIBILITY),
    "brand_carousel": (*_TEXT, *_FRAME, "min_height", "align", "gap", "item_width", *_VISIBILITY),
    "blog_posts": (*_TEXT, *_FRAME, "min_height", "align", "gap", "columns_desktop", "columns_tablet",
                   "columns_mobile", "image_ratio", "image_fit", *_BUTTONS, *_VISIBILITY),
    "amazing_offers": (*_TEXT, *_FRAME, "min_height", *_BUTTONS, *_VISIBILITY),
    # decorative_strip owns its look through its own flat schema; only its place in the page rhythm is shared.
    "decorative_strip": ("padding_top", "padding_bottom", "margin_top", "margin_bottom"),
}


def applicable_properties(section_key: str) -> tuple[str, ...]:
    return DESIGN_APPLICABLE.get(section_key, ())


def validate_design_settings(raw: object, applicable: tuple[str, ...]) -> dict:
    """Clean a raw ``design`` block against the properties a section exposes.

    Unknown or inapplicable keys are rejected (never silently stored), invalid values
    raise ``DesignSettingsError``, and neutral values (empty / ``None``) are dropped so
    the stored block stays sparse."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise DesignSettingsError("تنظیمات ظاهر باید یک شیء باشد")
    cleaned: dict = {}
    for key, value in raw.items():
        prop = DESIGN_PROPERTIES.get(key)
        if prop is None or key not in applicable:
            raise DesignSettingsError(f"ویژگی «{key}» برای این بخش قابل‌تنظیم نیست")
        if value is None or value == "":
            continue
        if prop.kind == "color":
            try:
                color = clean_semantic_color(value)
            except SemanticColorError as exc:
                raise DesignSettingsError(str(exc)) from exc
            if color:
                cleaned[key] = color
        elif prop.kind == "int":
            try:
                number = int(str(value).translate(_DIGITS))
            except (TypeError, ValueError):
                raise DesignSettingsError(f"مقدار «{prop.label_fa}» باید عدد باشد") from None
            cleaned[key] = max(prop.min_value, min(prop.max_value, number))
        else:
            allowed = {choice for choice, _label in prop.choices if choice}
            if value not in allowed:
                raise DesignSettingsError(f"مقدار «{prop.label_fa}» نامعتبر است")
            cleaned[key] = value
    return cleaned


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_POSITION_CSS = {"center": "center", "top": "center top", "bottom": "center bottom", "left": "left center",
                 "right": "right center"}
_RATIO_CSS = {"square": "1 / 1", "portrait": "3 / 4", "landscape": "4 / 3"}
_ALIGN_CSS = {"start": "start", "center": "center", "end": "end"}
_DEFAULT_SHADOW_COLOR = "color-mix(in srgb, var(--brand-text, #222) 16%, transparent)"


def render_attributes(design: object) -> dict:
    """``{"flags": "<space separated data-d flags>", "style": ";--d-…:…"}`` for a cleaned block.

    Pure and side-effect free; an empty/absent block yields empty strings so the wrapper
    markup of every section without a ``design`` block is unchanged."""
    if not isinstance(design, dict) or not design:
        return {"flags": "", "style": "", "hide_desktop": False, "hide_tablet": False, "hide_mobile": False}
    flags: list[str] = []
    css: list[str] = []

    def put(var: str, value) -> None:
        css.append(f"--d-{var}:{value}")

    def color(key: str) -> str:
        return semantic_color_css(design.get(key))

    if design.get("surface_color"):
        flags.append("surface")
        put("surface", color("surface_color"))
        put("surface-fg", semantic_foreground_css(design["surface_color"]))
    if design.get("text_color"):
        flags.append("text")
        put("text", color("text_color"))
    if design.get("heading_color"):
        flags.append("heading")
        put("heading", color("heading_color"))
    if design.get("accent_color"):
        flags.append("accent")
        put("accent", color("accent_color"))
    if design.get("border_color") or "border_width" in design:
        flags.append("border")
        put("border-c", color("border_color") or "var(--brand-border, #e5e7eb)")
        put("border-w", f"{design.get('border_width', 1)}px")
    if "radius" in design:
        flags.append("radius")
        put("radius", f"{design['radius']}px")
    shadow = design.get("shadow")
    if shadow == "off":
        flags.append("shadow")
        put("shadow", "none")
    elif shadow == "on" or design.get("shadow_color") or "shadow_blur" in design:
        flags.append("shadow")
        base = color("shadow_color")
        shadow_color = f"color-mix(in srgb, {base} 38%, transparent)" if base else _DEFAULT_SHADOW_COLOR
        blur = design.get("shadow_blur", 14)
        put("shadow", f"0 {max(1, blur // 4)}px {blur}px {shadow_color}")
    for key in ("padding_top", "padding_bottom", "margin_top", "margin_bottom"):
        if key in design:
            css.append(f"{key.replace('_', '-')}:{design[key]}px")
    if "min_height" in design:
        flags.append("minh")
        put("minh", f"{design['min_height']}px")
    if design.get("align") in _ALIGN_CSS:
        flags.append("align")
        put("align", _ALIGN_CSS[design["align"]])
        put("text-align", {"start": "start", "center": "center", "end": "end"}[design["align"]])
    if "gap" in design:
        flags.append("gap")
        put("gap", f"{design['gap']}px")
    for key, var in (("columns_desktop", "cols-desktop"), ("columns_tablet", "cols-tablet"),
                     ("columns_mobile", "cols-mobile")):
        if key in design:
            if "cols" not in flags:
                flags.append("cols")
            css.append(f"--{var}:{design[key]}")
    if "item_width" in design:
        flags.append("itemw")
        put("itemw", f"{design['item_width']}px")
    if design.get("image_ratio") in _RATIO_CSS:
        flags.append("ratio")
        put("ratio", _RATIO_CSS[design["image_ratio"]])
    if design.get("image_fit"):
        flags.append("fit")
        put("fit", design["image_fit"])
    if design.get("image_position") in _POSITION_CSS:
        flags.append("pos")
        put("pos", _POSITION_CSS[design["image_position"]])
    if design.get("price_color"):
        flags.append("price")
        put("price", color("price_color"))
    if design.get("button_fill"):
        flags.append("btnfill")
        put("btn-bg", color("button_fill"))
        if not design.get("button_text"):
            put("btn-fg", semantic_foreground_css(design["button_fill"]))
    if design.get("button_text"):
        flags.append("btntext")
        put("btn-fg", color("button_text"))
    if design.get("button_border"):
        flags.append("btnborder")
        put("btn-bd", color("button_border"))
    return {
        "flags": " ".join(flags), "style": ";" + ";".join(css) if css else "",
        "hide_desktop": design.get("hide_desktop") == "hidden",
        "hide_tablet": design.get("hide_tablet") == "hidden",
        "hide_mobile": design.get("hide_mobile") == "hidden",
    }


def serialize_registry_for_inspector(section_key: str) -> list[dict]:
    """Ordered, JSON-safe control metadata for the Inspector widget of ``section_key``."""
    props = [DESIGN_PROPERTIES[k] for k in applicable_properties(section_key)]
    out = []
    for group in DESIGN_GROUP_ORDER:
        members = [p for p in props if p.group == group]
        if not members:
            continue
        out.append({
            "group": group, "label": DESIGN_GROUP_LABELS_FA[group],
            "properties": [{
                "key": p.key, "label": p.label_fa, "kind": p.kind, "min": p.min_value, "max": p.max_value,
                "choices": [list(c) for c in p.choices],
            } for p in members],
        })
    return out
