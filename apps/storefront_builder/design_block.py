"""The generic, sparse ``design`` block — the merchant-editable look of a section.

``settings["design"]`` is a closed dictionary of design properties. Every key is
OPTIONAL and written only when the merchant (or a Ready Template recipe) sets it,
so a section without the block renders exactly as before. Which properties a
section type exposes is derived from the capabilities that section REGISTERS on its
``SectionDefinition`` (``section_registry``; see ``DESIGN_CAPABILITIES`` below) — the validator, the
Design Studio Inspector widget and the renderer all read that one registry, so a
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
    #: one short Persian sentence under the control: WHICH rectangle it paints (shown by the Inspector)
    hint_fa: str = ""


_SHADOW_CHOICES = (("", "پیش‌فرض"), ("on", "سایه دارد"), ("off", "بدون سایه"))
_ALIGN_CHOICES = (("", "پیش‌فرض"), ("start", "ابتدا"), ("center", "وسط"), ("end", "انتها"))
_VISIBILITY_CHOICES = (("", "نمایش داده شود"), ("hidden", "مخفی باشد"))
_RATIO_CHOICES = (
    ("", "خودکار (مناسب این بخش)"), ("square", "مربع"), ("portrait", "عمودی"), ("landscape", "افقی"),
    ("photo", "عکس ۳:۲"), ("wide", "عریض ۱۶:۹"), ("ultrawide", "خیلی عریض ۲۱:۹"), ("panel", "پنل افقی ۲٫۴:۱"), ("tall", "بلند ۹:۱۶"),
)
#: how a row of cards behaves on a phone: as on the desktop (default), one card at a time, two at a time, or a plain single column
_MOBILE_LAYOUT_CHOICES = (
    ("", "مثل دسکتاپ (پیش‌فرض)"), ("slider", "اسلایدر — هر بار یک کارت"), ("slider2", "اسلایدر — دو کارت"), ("stack", "زیر هم (یک ستون)"),
)
#: where the content of a section with a minimum height sits vertically
_VALIGN_CHOICES = (("", "بالا (پیش‌فرض)"), ("center", "وسط"), ("end", "پایین"))
_FIT_CHOICES = (("", "خودکار (مناسب این بخش)"), ("contain", "نمایش کامل تصویر"), ("cover", "پر کردن قاب"))
#: V5-RESIZE — where a section narrower than its Cell sits inside it (RTL: «راست» = the inline start).
_WIDTH_ALIGN_CHOICES = (("", "وسط"), ("start", "راست"), ("center", "وسط"), ("end", "چپ"))
_ZOOM_CHOICES = (("", "بدون بزرگ‌نمایی"), ("110", "۱۱۰٪"), ("125", "۱۲۵٪"), ("150", "۱۵۰٪"), ("175", "۱۷۵٪"))
_POSITION_CHOICES = (
    ("", "خودکار (وسط)"), ("center", "وسط"), ("top", "بالا"), ("bottom", "پایین"), ("left", "چپ"), ("right", "راست"),
)

DESIGN_PROPERTIES: dict[str, DesignProperty] = {p.key: p for p in (
    DesignProperty("text_color", "رنگ متن", "color", "colors"),
    DesignProperty("heading_color", "رنگ عنوان", "color", "colors"),
    DesignProperty("accent_color", "رنگ تأکید (خط و نشانِ عنوان)", "color", "colors"),
    DesignProperty("surface_color", "رنگ سطح (پنل/کارت)", "color", "colors",
                   hint_fa="رنگ کارت‌ها یا پنل‌های داخلی این بخش. رنگ پشت کل بخش را «پس‌زمینه» تعیین می‌کند."),
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
    DesignProperty("min_height", "حداقل ارتفاع (px)", "int", "layout", 0, 1600,
                   hint_fa="خالی = ارتفاع خودکار. این مقدار «حداقل» است: اگر محتوا بیشتر جا بخواهد، بخش بلندتر می‌شود و هیچ چیز بریده نمی‌شود."),
    DesignProperty("align", "تراز عنوان/محتوا", "choice", "layout", choices=_ALIGN_CHOICES),
    DesignProperty("valign", "جای عمودی محتوا", "choice", "layout", choices=_VALIGN_CHOICES,
                   hint_fa="وقتی «حداقل ارتفاع» از محتوا بلندتر است، محتوا بالا، وسط یا پایین قرار می‌گیرد."),
    DesignProperty("mobile_layout", "چیدمان موبایل ردیف کارت‌ها", "choice", "layout", choices=_MOBILE_LAYOUT_CHOICES,
                   hint_fa="فقط روی گوشی اثر دارد؛ دسکتاپ و تبلت دست‌نخورده می‌ماند."),
    DesignProperty("gap", "فاصله بین آیتم‌ها (px)", "int", "layout", 0, 60),
    DesignProperty("columns_desktop", "ستون‌ها در دسکتاپ", "int", "layout", 1, 8),
    DesignProperty("columns_tablet", "ستون‌ها در تبلت", "int", "layout", 1, 6),
    DesignProperty("columns_mobile", "ستون‌ها در موبایل", "int", "layout", 1, 4),
    DesignProperty("item_width", "عرض هر آیتم/کارت (px)", "int", "layout", 60, 420),
    DesignProperty("image_ratio", "نسبت قاب تصویر", "choice", "image", choices=_RATIO_CHOICES,
                   hint_fa="شکل قاب تصویر در همهٔ کارت‌های این بخش؛ خودِ تصویر آپلودشده هرگز تغییر نمی‌کند."),
    DesignProperty("image_fit", "نحوه جاگیری تصویر", "choice", "image", choices=_FIT_CHOICES,
                   hint_fa="«نمایش کامل» هیچ بخشی از تصویر را نمی‌برد؛ «پر کردن قاب» قاب را پر می‌کند و ممکن است لبه‌ها بریده شود. عکس محصول و لوگو به‌طور خودکار کامل نمایش داده می‌شوند."),
    DesignProperty("image_position", "کانون تصویر (هنگام برش)", "choice", "image", choices=_POSITION_CHOICES,
                   hint_fa="وقتی تصویر قاب را پر می‌کند و برش لازم است، بخشی که نزدیک‌تر به این سمت است دیده می‌شود."),
    DesignProperty("image_zoom", "بزرگ‌نمایی تصویر", "choice", "image", choices=_ZOOM_CHOICES,
                   hint_fa="لبهٔ خالی یا پس‌زمینهٔ خودِ عکس را از قاب بیرون می‌برد؛ فایل اصلی تغییر نمی‌کند و فقط در همین بخش اثر دارد. کانون تصویر تعیین می‌کند کدام سمت بزرگ شود."),
    DesignProperty("hide_desktop", "نمایش در دسکتاپ", "choice", "visibility", choices=_VISIBILITY_CHOICES),
    DesignProperty("hide_tablet", "نمایش در تبلت", "choice", "visibility", choices=_VISIBILITY_CHOICES),
    DesignProperty("hide_mobile", "نمایش در موبایل", "choice", "visibility", choices=_VISIBILITY_CHOICES),
    DesignProperty("price_color", "رنگ قیمت", "color", "actions"),
    DesignProperty("button_fill", "پس‌زمینه دکمه", "color", "actions"),
    DesignProperty("button_text", "رنگ متن دکمه", "color", "actions"),
    DesignProperty("button_border", "رنگ حاشیه دکمه", "color", "actions"),
)}

#: V5-RESIZE — properties driven ON THE CANVAS (drag handles) only: validated, stored and rendered like every design key, but never listed in
#: the Inspector's «ظاهر و استایل» panel, so ``DESIGN_PROPERTIES`` (the Inspector contract) is unchanged.
CANVAS_PROPERTIES: dict[str, DesignProperty] = {p.key: p for p in (
    DesignProperty("width_pct", "عرض بخش (٪ از عرض خانه)", "int", "layout", 30, 100,
                   hint_fa="خالی = عرض کامل خانه. فقط عرض خودِ بخش را درون خانهٔ خودش تغییر می‌دهد؛ عرض ستون‌ها را مرز بین خانه‌ها تعیین می‌کند."),
    DesignProperty("width_align", "جایگاه بخش در خانه", "choice", "layout", choices=_WIDTH_ALIGN_CHOICES,
                   hint_fa="وقتی عرض بخش کمتر از خانه است، بخش کجای خانه قرار بگیرد."),
)}
_ALL_PROPERTIES: dict[str, DesignProperty] = {**DESIGN_PROPERTIES, **CANVAS_PROPERTIES}

DESIGN_GROUP_LABELS_FA = {
    "colors": "رنگ‌ها", "border": "حاشیه و گوشه", "shadow": "سایه", "spacing": "فاصله‌ها",
    "layout": "چیدمان", "image": "تصویر", "visibility": "نمایش در دستگاه‌ها", "actions": "قیمت و دکمه‌ها",
}
DESIGN_GROUP_ORDER = ("colors", "border", "shadow", "spacing", "layout", "image", "visibility", "actions")

_FRAME = ("border_color", "border_width", "radius", "shadow", "shadow_color", "shadow_blur",
          "padding_top", "padding_bottom", "margin_top", "margin_bottom")
_TEXT = ("text_color", "heading_color", "accent_color")
#: «رنگ سطح» paints INTERNAL surfaces (cards / panels) and never the section canvas — that is «پس‌زمینه این بخش» alone, so
#: the two controls can never compete for one rectangle. Only a section that really HAS an internal surface offers it.
_SURFACE = ("surface_color",)
_BUTTONS = ("button_fill", "button_text", "button_border")
_VISIBILITY = ("hide_desktop", "hide_tablet", "hide_mobile")

_SPACING = ("padding_top", "padding_bottom", "margin_top", "margin_bottom")
_COLUMNS = ("columns_desktop", "columns_tablet", "columns_mobile")

#: design capability -> (design properties it grants, display modes that restrict them — ``()`` = always).
#: A section type REGISTERS these names in ``SectionDefinition.capabilities`` (the existing capability registry,
#: ``section_registry.SectionDefinition.supports_capability``); this table only says what each capability MEANS.
#: Nothing here names a section: adding a section type means declaring capabilities on ITS definition.
#:
#: ``internal_surface`` — the section has INTERNAL surfaces (cards / panels, marked ``data-sfb-card-surface`` or
#: ``data-sfb-section-surface`` in its markup). «رنگ سطح» paints exactly those and never the section canvas (that is
#: «پس‌زمینه این بخش» alone), so a section without internal surfaces does not offer the control.
DESIGN_CAPABILITIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "design_text": (_TEXT, ()),
    "internal_surface": (_SURFACE, ()),
    "design_frame": (_FRAME, ()),
    "design_spacing": (_SPACING, ()),
    "design_buttons": (_BUTTONS, ()),
    "design_visibility": (_VISIBILITY, ()),
    "design_min_height": (("min_height",), ()),
    "design_align": (("align",), ()),
    "design_gap": (("gap",), ()),
    #: V5 composition: phone behaviour of a row of cards / vertical placement of content inside a taller section
    "design_mobile_layout": (("mobile_layout",), ()),
    "design_valign": (("valign",), ()),
    "design_columns": (_COLUMNS, ()),
    "design_item_width": (("item_width",), ()),
    #: ``item_width`` sizes carousel cards only: a grid / campaign / catalog composition has nothing to size
    "design_item_width_carousel": (("item_width",), ("carousel",)),
    "design_image_ratio": (("image_ratio",), ()),
    "design_image_fit": (("image_fit",), ()),
    "design_image_position": (("image_position",), ()),
    "design_image_zoom": (("image_zoom",), ()),
    "design_price": (("price_color",), ()),
}

#: V5-RESIZE — the universal visual-resize contract (height / width / placement). Granted to EVERY section type by
#: ``section_registry._finalize_registry`` (the same way ``responsive`` is). Canvas-only: it grants storage / validation / rendering of the size
#: keys but no Inspector control, so ``DESIGN_CAPABILITIES`` and the Inspector surface are exactly what they were.
CANVAS_CAPABILITIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "canvas_size": (("min_height", "width_pct", "width_align"), ()),
}


def all_properties_for_capabilities(capabilities) -> tuple[str, ...]:
    """EVERY design property a section with these capabilities may carry (Inspector set + canvas-only keys): the validator, the renderer and the
    resize mutation use this."""
    table = {**DESIGN_CAPABILITIES, **CANVAS_CAPABILITIES}
    granted = {prop for name in capabilities if name in table for prop in table[name][0]}
    return tuple(key for key in _ALL_PROPERTIES if key in granted)


def properties_for_capabilities(capabilities) -> tuple[str, ...]:
    """The Inspector-visible design properties a section with these registered capabilities consumes, in canonical order."""
    granted = {prop for name in capabilities if name in DESIGN_CAPABILITIES for prop in DESIGN_CAPABILITIES[name][0]}
    return tuple(key for key in DESIGN_PROPERTIES if key in granted)


inspector_properties_for_capabilities = properties_for_capabilities


def display_modes_for_capabilities(capabilities) -> dict[str, tuple[str, ...]]:
    """``{property: display modes}`` for properties that only exist in some display types.

    A property granted unrestricted by ANY registered capability has no mode restriction."""
    unrestricted: set[str] = set()
    restricted: dict[str, set[str]] = {}
    for name in capabilities:
        if name not in DESIGN_CAPABILITIES:
            continue
        props, modes = DESIGN_CAPABILITIES[name]
        for prop in props:
            if modes:
                restricted.setdefault(prop, set()).update(modes)
            else:
                unrestricted.add(prop)
    return {prop: tuple(sorted(modes)) for prop, modes in restricted.items() if prop not in unrestricted}


def design_capability_names() -> frozenset[str]:
    return frozenset(DESIGN_CAPABILITIES) | frozenset(CANVAS_CAPABILITIES)


def _registered_capabilities(section_key: str) -> frozenset[str]:
    from . import section_registry  # lazy: the registry imports this module

    try:
        return section_registry.get_definition(section_key).capabilities
    except ValueError:
        return frozenset()


def applicable_properties(section_key: str) -> tuple[str, ...]:
    """Inspector-visible properties for a REGISTERED section type — read from its ``SectionDefinition.capabilities`` (canvas-only size keys
    excluded; see ``all_properties``)."""
    return properties_for_capabilities(_registered_capabilities(section_key))


def all_properties(section_key: str) -> tuple[str, ...]:
    """EVERY property a section's wrapper may carry — the Inspector set plus the canvas-only size keys. Rendering and the resize
    mutation use this; ``applicable_properties`` stays the Inspector contract."""
    return all_properties_for_capabilities(_registered_capabilities(section_key))


def inspector_properties(section_key: str) -> tuple[str, ...]:
    """Properties the Inspector offers for a REGISTERED section type (``applicable_properties`` minus the canvas-only size keys)."""
    return properties_for_capabilities(_registered_capabilities(section_key))


def design_capable_section_keys() -> tuple[str, ...]:
    """Every registered section type that registers at least one Inspector-visible design capability."""
    from . import section_registry

    return tuple(key for key, definition in section_registry.SECTION_REGISTRY.items()
                 if any(name in DESIGN_CAPABILITIES for name in definition.capabilities))


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
        prop = _ALL_PROPERTIES.get(key)
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


def dormant_design_keys(stored: object, applicable: tuple[str, ...]) -> dict:
    """Design keys ALREADY STORED on a section that its registered capabilities no longer grant.

    A capability change (an engine release that stops offering a property for a section type) must never strand a
    merchant's earlier setting: such keys are *dormant* — kept in storage verbatim, inert in rendering, hidden in the
    Inspector, and carried through every later write untouched. Only known design properties qualify (junk keys were
    never valid and stay rejected). A key that is NEWLY submitted for a section that does not grant it is rejected by
    ``validate_design_settings`` exactly as before."""
    if not isinstance(stored, dict):
        return {}
    return {key: value for key, value in stored.items() if key in _ALL_PROPERTIES and key not in applicable}


def split_resubmitted_dormant(design: object, dormant: dict) -> object:
    """``design`` without the dormant keys it merely carries over unchanged (so validation sees only live keys).

    A dormant key whose value was CHANGED stays in, and is therefore rejected as a new unsupported write."""
    if not isinstance(design, dict) or not dormant:
        return design
    return {key: value for key, value in design.items() if not (key in dormant and value == dormant[key])}


def restore_dormant(cleaned_design: dict | None, dormant: dict) -> dict:
    """The validated block plus the dormant keys carried forward (stored order: live keys first)."""
    if not dormant:
        return cleaned_design or {}
    return {**(cleaned_design or {}), **dormant}


def surface_keeps_brand_inks(surface: object) -> bool:
    """True when the engine's own accessible inks (price / accent, already contrast-ensured by the theme against the
    page surfaces) stay correct on this internal surface: a custom LIGHT colour, or the theme's own surface / background
    token. Any other surface (dark custom colour, palette tones, brand colours …) re-inks to its accessible foreground."""
    value = clean_semantic_color(surface) if surface else ""
    if not value:
        return True
    if value.startswith("token:"):
        return value[len("token:"):] in ("surface", "background")
    from apps.core.color_utils import best_foreground

    return best_foreground(value) == "#000000"


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_POSITION_CSS = {"center": "center", "top": "center top", "bottom": "center bottom", "left": "left center",
                 "right": "right center"}
_ZOOM_CSS = {"110": "1.1", "125": "1.25", "150": "1.5", "175": "1.75"}
_RATIO_CSS = {"square": "1 / 1", "portrait": "3 / 4", "landscape": "4 / 3", "photo": "3 / 2", "wide": "16 / 9",
              "ultrawide": "21 / 9", "panel": "2.4 / 1", "tall": "9 / 16"}
_VALIGN_CSS = {"center": "center", "end": "flex-end"}
_ALIGN_CSS = {"start": "start", "center": "center", "end": "end"}
_DEFAULT_SHADOW_COLOR = "color-mix(in srgb, var(--brand-text, #222) 16%, transparent)"


def render_attributes(design: object, applicable: tuple[str, ...] | None = None) -> dict:
    """``{"flags": "<space separated data-d flags>", "style": ";--d-…:…"}`` for a cleaned block.

    ``applicable`` (the section's registered design properties) makes DORMANT stored keys inert: only properties the
    section's capabilities grant are rendered. ``None`` renders every key (pure-function use / tests).

    Pure and side-effect free; an empty/absent block yields empty strings so the wrapper
    markup of every section without a ``design`` block is unchanged."""
    if isinstance(design, dict) and applicable is not None:
        design = {key: value for key, value in design.items() if key in applicable}
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
        if surface_keeps_brand_inks(design["surface_color"]):
            flags.append("surface-brand")
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
    if "width_pct" in design and int(design["width_pct"]) < 100:
        flags.append("w")
        put("w", f"{design['width_pct']}%")
        flags.append("wa-" + (design.get("width_align") or "center"))
    if design.get("align") in _ALIGN_CSS:
        flags.append("align")
        put("align", _ALIGN_CSS[design["align"]])
        put("text-align", {"start": "start", "center": "center", "end": "end"}[design["align"]])
    if design.get("mobile_layout") in ("slider", "slider2", "stack"):
        flags.append("m-" + design["mobile_layout"])
    if design.get("valign") in _VALIGN_CSS:
        flags.append("valign")
        put("valign", _VALIGN_CSS[design["valign"]])
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
        if design["image_fit"] == "cover":
            flags.append("fill")
    if design.get("image_position") in _POSITION_CSS:
        flags.append("pos")
        put("pos", _POSITION_CSS[design["image_position"]])
    if design.get("image_zoom") in _ZOOM_CSS:
        flags.append("zoom")
        put("zoom", _ZOOM_CSS[design["image_zoom"]])
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


#: Properties that style the section's own BOX (the filled rectangle). When the section's background bleeds edge to edge
#: the fill is the full-width layer and the box has nothing to round, outline or shadow, so the Inspector does not offer
#: these (a control with no visible effect is never shown); a stored value stays dormant.
BOX_PROPERTIES = frozenset({"border_color", "border_width", "radius", "shadow", "shadow_color", "shadow_blur"})


def serialize_registry_for_inspector(section_key: str) -> list[dict]:
    """Ordered, JSON-safe control metadata for the Inspector widget of ``section_key``."""
    capabilities = _registered_capabilities(section_key)
    props = [DESIGN_PROPERTIES[k] for k in inspector_properties_for_capabilities(capabilities)]
    modes_by_property = display_modes_for_capabilities(capabilities)
    out = []
    for group in DESIGN_GROUP_ORDER:
        members = [p for p in props if p.group == group]
        if not members:
            continue
        out.append({
            "group": group, "label": DESIGN_GROUP_LABELS_FA[group],
            "properties": [{
                "key": p.key, "label": p.label_fa, "kind": p.kind, "min": p.min_value, "max": p.max_value,
                "choices": [list(c) for c in p.choices], "box": p.key in BOX_PROPERTIES, "hint": p.hint_fa,
                "modes": list(modes_by_property.get(p.key, ())),
            } for p in members],
        })
    return out
