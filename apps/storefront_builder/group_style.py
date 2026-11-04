"""The merchant-editable look of a V5 «Group» (a Container, top-level or nested) — sparse, validated, token driven.

A Group is a real R4 Container (``StorefrontContainer``), so its presentation lives in ``Container.settings`` next to the layout settings that
already exist there (``gap``, ``mobile_mode``, ``mobile_order``, ``vertical_align``, ``height_mode``, ``background_*``). This module owns only the
NEW, sparse keys:

* content of the frame:  ``title`` · ``description`` · ``title_visible``
* ``style`` (a closed dictionary, every key optional): alignment, font, text / title sizes and colours, padding, margins, border, radius,
  shadow, minimum height, per-device visibility

A Container without any of these keys renders byte-identically to before (the renderer writes the group frame only when something is set or the
Container is nested). Colours are semantic (palette token or hex, see ``semantic_colors``) — never raw CSS; fonts are the curated
``appearance_registry.FONT_CHOICES``; numbers are clamped. ``render_attributes`` turns a cleaned dictionary into ``--g-*`` custom properties and
a ``data-g`` flag list; the generic CSS in ``storefront_builder.css`` only acts on flags that are present.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import appearance_registry
from .semantic_colors import SemanticColorError, clean_semantic_color, semantic_color_css, semantic_foreground_css


class GroupStyleError(ValueError):
    """The raw group settings have an invalid shape or value (merchant-facing Persian message)."""


@dataclass(frozen=True)
class GroupProperty:
    key: str
    label_fa: str
    kind: str  # "color" | "int" | "choice"
    group: str
    min_value: int = 0
    max_value: int = 0
    choices: tuple[tuple[str, str], ...] = ()


_ALIGN = (("", "پیش‌فرض (راست‌چین)"), ("start", "راست‌چین"), ("center", "وسط‌چین"), ("end", "چپ‌چین"))
_WEIGHT = (("", "پیش‌فرض"), ("normal", "معمولی"), ("bold", "پررنگ"), ("black", "خیلی پررنگ"))
_SHADOW = (("", "بدون سایه"), ("soft", "سایه ملایم"), ("strong", "سایه پررنگ"))
_VISIBILITY = (("", "نمایش داده شود"), ("hidden", "مخفی باشد"))
_FONT = (("", "فونت سراسری فروشگاه"),) + tuple((name, name) for name in appearance_registry.FONT_CHOICES)

GROUP_STYLE_PROPERTIES: dict[str, GroupProperty] = {p.key: p for p in (
    GroupProperty("text_align", "تراز عنوان و متن", "choice", "text", choices=_ALIGN),
    GroupProperty("font", "فونت این گروه", "choice", "text", choices=_FONT),
    GroupProperty("font_size", "اندازه متن (px)", "int", "text", 11, 42),
    GroupProperty("title_size", "اندازه عنوان (px)", "int", "text", 11, 58),
    GroupProperty("title_weight", "وزن عنوان", "choice", "text", choices=_WEIGHT),
    GroupProperty("text_color", "رنگ نوشته‌ها", "color", "colors"),
    GroupProperty("title_color", "رنگ عنوان", "color", "colors"),
    GroupProperty("pad", "فاصله داخلی (px)", "int", "spacing", 0, 90),
    GroupProperty("margin_top", "فاصله بیرونی بالا (px)", "int", "spacing", 0, 120),
    GroupProperty("margin_bottom", "فاصله بیرونی پایین (px)", "int", "spacing", 0, 120),
    GroupProperty("border_width", "ضخامت حاشیه (px)", "int", "border", 0, 8),
    GroupProperty("border_color", "رنگ حاشیه", "color", "border"),
    GroupProperty("radius", "گردی گوشه‌ها (px)", "int", "border", 0, 60),
    GroupProperty("shadow", "سایه", "choice", "border", choices=_SHADOW),
    GroupProperty("min_height", "حداقل ارتفاع (px)", "int", "size", 0, 1200),
    GroupProperty("hide_desktop", "نمایش در دسکتاپ", "choice", "visibility", choices=_VISIBILITY),
    GroupProperty("hide_tablet", "نمایش در تبلت", "choice", "visibility", choices=_VISIBILITY),
    GroupProperty("hide_mobile", "نمایش در موبایل", "choice", "visibility", choices=_VISIBILITY),
)}

GROUP_STYLE_GROUP_LABELS_FA = {
    "text": "متن و فونت", "colors": "رنگ‌ها", "spacing": "فاصله‌ها", "border": "حاشیه، گوشه و سایه", "size": "اندازه", "visibility": "نمایش در دستگاه‌ها",
}
GROUP_STYLE_GROUP_ORDER = ("text", "colors", "spacing", "border", "size", "visibility")

MAX_TITLE_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 300

#: curated font stacks (the same names the global appearance offers); the page's own font loading is unchanged
_FONT_STACKS = {
    "Vazirmatn": "Vazirmatn,Tahoma,Arial,sans-serif", "Estedad": "Estedad,Tahoma,Arial,sans-serif",
    "Noto Sans Arabic": "'Noto Sans Arabic',Tahoma,Arial,sans-serif", "Lalezar": "Lalezar,Tahoma,Arial,sans-serif",
    "Tahoma": "Tahoma,Arial,sans-serif", "Arial": "Arial,sans-serif", "Georgia": "Georgia,serif",
}
_TEXT_ALIGN_CSS = {"start": "right", "center": "center", "end": "left"}      # RTL: the inline start is the right edge
_TITLE_WEIGHT_CSS = {"normal": "400", "bold": "700", "black": "900"}
_SHADOW_CSS = {"soft": "0 10px 32px rgba(24,56,75,.10)", "strong": "0 16px 44px rgba(24,56,75,.22)"}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def validate_style(raw: object) -> dict:
    """Clean a raw ``style`` dictionary. Unknown keys / invalid values raise; empty values reset a key; the result is sparse."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GroupStyleError("ظاهر گروه باید یک شیء باشد")
    cleaned: dict = {}
    for key, value in raw.items():
        prop = GROUP_STYLE_PROPERTIES.get(key)
        if prop is None:
            raise GroupStyleError(f"ویژگی «{key}» برای گروه قابل‌تنظیم نیست")
        if value is None or value == "":
            continue
        if prop.kind == "color":
            try:
                color = clean_semantic_color(value)
            except SemanticColorError as exc:
                raise GroupStyleError(str(exc)) from exc
            if color:
                cleaned[key] = color
        elif prop.kind == "int":
            try:
                number = int(str(value).translate(_DIGITS))
            except (TypeError, ValueError):
                raise GroupStyleError(f"مقدار «{prop.label_fa}» باید عدد باشد") from None
            cleaned[key] = max(prop.min_value, min(prop.max_value, number))
        else:
            if value not in {choice for choice, _label in prop.choices if choice}:
                raise GroupStyleError(f"مقدار «{prop.label_fa}» نامعتبر است")
            cleaned[key] = value
    return cleaned


def clean_text(value: object, limit: int, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GroupStyleError(f"«{label}» باید متن باشد")
    text = " ".join(value.split())
    if len(text) > limit:
        raise GroupStyleError(f"«{label}» حداکثر {limit} نویسه است")
    return text


def merge_style_patch(current: object, posted: object) -> dict:
    """Merge a posted partial ``style`` patch onto the stored one (``None`` / ``""`` clears a key)."""
    merged = dict(current) if isinstance(current, dict) else {}
    if isinstance(posted, dict):
        for key, value in posted.items():
            if value is None or value == "":
                merged.pop(key, None)
            else:
                merged[key] = value
    return merged


def render_attributes(style: object) -> dict:
    """``{"flags": "<data-g flags>", "style": "--g-…:…;…", "hide": {...}}`` for a cleaned ``style``; empty when nothing is set."""
    out = {"flags": "", "style": "", "hide_desktop": False, "hide_tablet": False, "hide_mobile": False}
    if not isinstance(style, dict) or not style:
        return out
    flags: list[str] = []
    css: list[str] = []

    def put(flag: str, var: str, value) -> None:
        flags.append(flag)
        css.append(f"--g-{var}:{value}")

    if style.get("text_align") in _TEXT_ALIGN_CSS:
        put("align", "align", _TEXT_ALIGN_CSS[style["text_align"]])
    if style.get("font") in _FONT_STACKS:
        put("font", "font", _FONT_STACKS[style["font"]])
    if style.get("font_size"):
        put("fz", "fz", f"{int(style['font_size'])}px")
    if style.get("title_size"):
        put("hfz", "hfz", f"{int(style['title_size'])}px")
    if style.get("title_weight") in _TITLE_WEIGHT_CSS:
        put("hw", "hw", _TITLE_WEIGHT_CSS[style["title_weight"]])
    if style.get("text_color"):
        put("ink", "ink", semantic_color_css(style["text_color"]))
    if style.get("title_color"):
        put("tink", "tink", semantic_color_css(style["title_color"]))
    elif style.get("text_color"):
        css.append(f"--g-tink:{semantic_color_css(style['text_color'])}")
    if style.get("pad") is not None:
        put("pad", "pad", f"{int(style['pad'])}px")
    if style.get("margin_top") is not None:
        put("mt", "mt", f"{int(style['margin_top'])}px")
    if style.get("margin_bottom") is not None:
        put("mb", "mb", f"{int(style['margin_bottom'])}px")
    if style.get("border_width"):
        put("bw", "bw", f"{int(style['border_width'])}px")
        css.append(f"--g-bc:{semantic_color_css(style['border_color']) if style.get('border_color') else 'currentColor'}")
    if style.get("radius") is not None:
        put("radius", "radius", f"{int(style['radius'])}px")
    if style.get("shadow") in _SHADOW_CSS:
        put("shadow", "shadow", _SHADOW_CSS[style["shadow"]])
    if style.get("min_height"):
        put("minh", "minh", f"{int(style['min_height'])}px")
    out.update(flags=" ".join(flags), style=";".join(css),
               hide_desktop=style.get("hide_desktop") == "hidden", hide_tablet=style.get("hide_tablet") == "hidden",
               hide_mobile=style.get("hide_mobile") == "hidden")
    return out


def background_css(settings: dict, media_url: str = "") -> str:
    """Inline ``background`` declarations of a Group from its (already cleaned) container settings: colour, two-colour gradient or picture.

    ``color`` / ``pattern`` keep their pre-existing rendering elsewhere (``background-color`` on the container); this only covers the new
    ``gradient`` and ``image`` modes so a Container that never used them is untouched."""
    mode = settings.get("background_mode")
    if mode == "gradient":
        first = semantic_color_css(settings.get("background_color")) or "#FFFFFF"
        second = semantic_color_css(settings.get("background_color2")) or "#DDF4EC"
        ink = semantic_foreground_css(settings.get("background_color")) if settings.get("background_color") else ""
        extra = f";--g-auto-ink:{ink}" if ink else ""
        return f"background:linear-gradient(135deg,{first},{second}){extra}"
    if mode == "image" and media_url:
        return f"background-image:url('{media_url}');background-size:cover;background-position:center"
    return ""


def inspector_groups() -> list[dict]:
    """The Group Inspector's control list, from this ONE registry (so a control exists iff the renderer consumes it)."""
    groups: dict[str, list[dict]] = {}
    for prop in GROUP_STYLE_PROPERTIES.values():
        groups.setdefault(prop.group, []).append({
            "key": prop.key, "label": prop.label_fa, "kind": prop.kind, "min": prop.min_value, "max": prop.max_value,
            "choices": [{"value": value, "label": label} for value, label in prop.choices],
        })
    return [{"key": key, "label": GROUP_STYLE_GROUP_LABELS_FA[key], "properties": groups[key]} for key in GROUP_STYLE_GROUP_ORDER if key in groups]
