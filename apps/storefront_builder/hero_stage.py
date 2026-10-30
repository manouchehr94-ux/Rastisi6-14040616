"""Hero Stage — the ONE authority for the settings vocabulary of the ``hero_stage`` section (header + hero in one canvas).

``hero_stage`` is a normal registered Section of the one R4 engine: it is saved in the Draft, copied on publish, shown in the Studio
library, edited through the schema-driven Inspector and covered by Undo/Redo like every other section. This module only owns:

* the closed vocabulary (choices / bounded integers / short texts / the ordered ``slots`` list) and the matching ``SettingsField``
  definitions (``section_registry`` builds ``HERO_STAGE_SCHEMA`` from the tables below, so a control exists if and only if the
  renderer consumes it);
* a lenient write-time cleaner (the Section's legacy validator — the schema already rejects out-of-vocabulary input) and a lenient
  render-time resolver that can never raise: a stale or hand-edited stored value falls back to its default, it never breaks a page;
* the projection the shared stylesheet reads: ``data-hs-*`` attributes + ``--hs-*`` custom properties built ONLY from validated
  choices and clamped integers (no merchant text is ever placed in CSS or markup unescaped).

Header embedding is a *composition* decision (``header_mode``): ``independent`` keeps today's shell header, ``merged`` renders the Store's
global header INSIDE the stage in normal flow over the shared background, ``overlay`` renders it floating over the top of the stage.
The decision itself (is this stage the first top-level item of the page?) lives in ``render_service.header_embedded_for``.

Nothing here names a Ready Template, a section key other than its own, a Store or a brand.
"""

from __future__ import annotations

from .semantic_colors import SemanticColorError, clean_semantic_color, semantic_color_css

SECTION_KEY = "hero_stage"
SETTINGS_VERSION = 1

#: slot keys the merchant can order / hide per device (the stage renders exactly these, in this order)
SLOT_LABELS = (
    ("eyebrow", "عنوان کوچک (بالای تیتر)"),
    ("title", "تیتر اصلی"),
    ("subtitle", "زیرعنوان"),
    ("cta", "دکمهٔ اقدام"),
    ("categories", "نوار دسته‌بندی‌ها"),
    ("product_card", "کارت محصول شناور"),
)
SLOT_KEYS = tuple(key for key, _ in SLOT_LABELS)
DEFAULT_SLOTS = ("eyebrow", "title", "subtitle", "cta")
MAX_SLOTS = len(SLOT_KEYS)

_ALIGN = (("start", "ابتدا (راست در صفحهٔ فارسی)"), ("center", "وسط"), ("end", "انتها (چپ در صفحهٔ فارسی)"))
_ALIGN_INHERIT = (("", "مثل دسکتاپ"),) + _ALIGN
_VALIGN = (("top", "بالا"), ("middle", "وسط"), ("bottom", "پایین"))
_VALIGN_INHERIT = (("", "مثل دسکتاپ"),) + _VALIGN
_TITLE_SIZE = (("sm", "کوچک"), ("md", "متوسط"), ("lg", "بزرگ"), ("xl", "خیلی بزرگ"))
_TITLE_SIZE_INHERIT = (("", "مثل دسکتاپ"),) + _TITLE_SIZE

#: ``(key, merchant label, ((value, label), ...), default, group, visible_when)``
CHOICES = (
    ("header_mode", "هدر فروشگاه", (
        ("merged", "داخل بوم هیرو — با پس‌زمینهٔ مشترک"),
        ("overlay", "شفاف و شناور روی تصویر"),
        ("independent", "مستقل، بالای هیرو (مثل قبل)"),
    ), "merged", "basic", ()),
    ("bg_layout", "تصویر پس‌زمینه", (
        ("single", "یک تصویر تمام‌عرض"),
        ("dual", "دو پنل (دو تصویر کنار هم)"),
    ), "single", "basic", ()),
    ("bg_split", "نسبت عرض دو پنل", (
        ("equal", "برابر (۵۰ / ۵۰)"),
        ("wide_first", "پنل اول عریض‌تر (۶۰ / ۴۰)"),
        ("wide_second", "پنل دوم عریض‌تر (۴۰ / ۶۰)"),
        ("first_dominant", "پنل اول غالب (۷۰ / ۳۰)"),
    ), "equal", "advanced", (("bg_layout", ("dual",)),)),
    ("text_tone", "رنگ نوشته‌ها روی تصویر", (
        ("light", "روشن (برای تصویر تیره)"),
        ("dark", "تیره (برای تصویر روشن)"),
    ), "light", "basic", ()),
    ("content_align", "تراز محتوا", _ALIGN, "center", "basic", ()),
    ("content_valign", "جای عمودی محتوا", _VALIGN, "middle", "basic", ()),
    ("scrim_style", "لایهٔ تیرگی روی تصویر", (
        ("both", "بالا و پایین"),
        ("top", "فقط بالا"),
        ("bottom", "فقط پایین"),
        ("full", "یکنواخت روی کل تصویر"),
        ("none", "بدون لایه"),
    ), "both", "basic", ()),
    ("button_style", "ظاهر دکمه", (
        ("solid", "توپر"),
        ("outline", "خطی"),
        ("glass", "شیشه‌ای"),
    ), "solid", "basic", ()),
    ("image_fit", "نحوهٔ قرارگیری تصویر", (
        ("cover", "پر کردن کامل قاب"),
        ("contain", "نمایش کامل تصویر"),
    ), "cover", "advanced", ()),
    ("mobile_dual", "دو پنل در موبایل", (
        ("stack", "زیر هم"),
        ("first_only", "فقط پنل اول"),
    ), "stack", "advanced", (("bg_layout", ("dual",)),)),
    ("content_frame", "قاب پشت محتوا", (
        ("none", "بدون قاب"),
        ("glass", "شیشه‌ای"),
        ("solid", "توپر"),
    ), "none", "advanced", ()),
    ("frame_border", "حاشیهٔ قاب و کارت", (
        ("thin", "نازک"),
        ("none", "بدون حاشیه"),
        ("strong", "پررنگ"),
    ), "thin", "advanced", ()),
    ("frame_shadow", "سایهٔ قاب و کارت", (
        ("off", "بدون سایه"),
        ("on", "با سایه"),
    ), "off", "advanced", ()),
    ("title_size", "اندازهٔ تیتر (دسکتاپ)", _TITLE_SIZE, "lg", "advanced", ()),
    ("title_size_tablet", "اندازهٔ تیتر (تبلت)", _TITLE_SIZE_INHERIT, "", "advanced", ()),
    ("title_size_mobile", "اندازهٔ تیتر (موبایل)", _TITLE_SIZE_INHERIT, "", "advanced", ()),
    ("title_weight", "ضخامت تیتر", (("normal", "معمولی"), ("bold", "پررنگ"), ("black", "خیلی پررنگ")), "bold", "advanced", ()),
    ("content_align_tablet", "تراز محتوا (تبلت)", _ALIGN_INHERIT, "", "advanced", ()),
    ("content_align_mobile", "تراز محتوا (موبایل)", _ALIGN_INHERIT, "", "advanced", ()),
    ("content_valign_mobile", "جای عمودی محتوا (موبایل)", _VALIGN_INHERIT, "", "advanced", ()),
    ("card_position", "جای کارت محصول", (
        ("side", "کنار متن (در دسکتاپ)"),
        ("below", "زیر متن"),
    ), "side", "advanced", ()),
    ("product_source", "کارت محصول از کدام فهرست باشد", (
        ("newest", "جدیدترین"),
        ("best_sellers", "پرفروش‌ترین"),
        ("discounted", "دارای تخفیف"),
    ), "newest", "advanced", ()),
)
CHOICE_DEFAULTS = {key: default for key, _l, _c, default, _g, _v in CHOICES}
CHOICE_VALUES = {key: frozenset(value for value, _label in choices) for key, _l, choices, _d, _g, _v in CHOICES}

#: ``(key, merchant label, min, max, default, group)`` — every integer is clamped, never trusted
INTEGERS = (
    ("height_desktop", "ارتفاع بوم در دسکتاپ (درصد ارتفاع صفحه)", 40, 100, 85, "basic"),
    ("height_tablet", "ارتفاع بوم در تبلت (درصد ارتفاع صفحه)", 40, 100, 75, "advanced"),
    ("height_mobile", "ارتفاع بوم در موبایل (درصد ارتفاع صفحه)", 40, 100, 70, "advanced"),
    ("scrim_strength", "شدت لایهٔ تیرگی (٪)", 0, 90, 45, "basic"),
    ("bg_a_focal_x", "کانون تصویر اول — افقی (٪)", 0, 100, 50, "advanced"),
    ("bg_a_focal_y", "کانون تصویر اول — عمودی (٪)", 0, 100, 50, "advanced"),
    ("bg_b_focal_x", "کانون تصویر دوم — افقی (٪)", 0, 100, 50, "advanced"),
    ("bg_b_focal_y", "کانون تصویر دوم — عمودی (٪)", 0, 100, 50, "advanced"),
    ("frame_opacity", "شفافیت قاب پشت محتوا (٪)", 0, 90, 40, "advanced"),
    ("frame_blur", "محو بودن پشت قاب شیشه‌ای (px)", 0, 30, 12, "advanced"),
    ("frame_radius", "گردی گوشهٔ قاب و کارت (px)", 0, 40, 14, "advanced"),
    ("content_max_width", "حداکثر عرض محتوا (px)", 320, 1200, 720, "advanced"),
    ("category_limit", "تعداد دسته‌بندی در نوار", 2, 10, 6, "advanced"),
)
INTEGER_BOUNDS = {key: (low, high, default) for key, _l, low, high, default, _g in INTEGERS}

#: ``(key, merchant label, max length)``
TEXTS = (
    ("eyebrow", "عنوان کوچک (بالای تیتر)", 60),
    ("title", "تیتر اصلی", 90),
    ("subtitle", "زیرعنوان", 220),
    ("button_label", "متن دکمه", 40),
)
TEXT_MAX = {key: limit for key, _l, limit in TEXTS}

#: semantic colours (``""`` = automatic): fallback behind the image, and the accent (button fill / card accent)
COLORS = (
    ("fallback_color", "رنگ پس‌زمینه وقتی تصویر نیست"),
    ("accent_color", "رنگ دکمه و تأکید"),
)

MEDIA_KEYS = ("bg_a_media_asset_id", "bg_b_media_asset_id")
SLOT_HIDE_KEYS = ("hide_tablet", "hide_mobile")

#: the stage's own keys (everything else — design / responsive / destination / motion … — travels through untouched)
OWNED_KEYS = frozenset(
    {"v", "slots"} | set(CHOICE_DEFAULTS) | set(INTEGER_BOUNDS) | set(TEXT_MAX) | {key for key, _l in COLORS} | set(MEDIA_KEYS)
)


# ----------------------------------------------------------------------------------------------------------------------------
# helpers (all lenient: they coerce, they never raise)
# ----------------------------------------------------------------------------------------------------------------------------

def _choice(raw: dict, key: str) -> str:
    value = raw.get(key, CHOICE_DEFAULTS[key])
    return value if isinstance(value, str) and value in CHOICE_VALUES[key] else CHOICE_DEFAULTS[key]


def _integer(raw: dict, key: str) -> int:
    low, high, default = INTEGER_BOUNDS[key]
    value = raw.get(key, default)
    if isinstance(value, bool):
        return default
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _text(raw: dict, key: str) -> str:
    value = raw.get(key, "")
    return value.strip()[: TEXT_MAX[key]] if isinstance(value, str) else ""


def _color(raw: dict, key: str) -> str:
    try:
        return clean_semantic_color(raw.get(key, ""))
    except SemanticColorError:
        return ""


def _media_id(raw: dict, key: str) -> int | None:
    value = raw.get(key)
    if value in (None, "", "null") or isinstance(value, bool):
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def clean_slots(raw) -> list[dict]:
    """Ordered, de-duplicated list of ``{"key", "hide_tablet", "hide_mobile"}``; unknown keys and duplicates are dropped."""
    if not isinstance(raw, list):
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            entry = {"key": entry}
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not isinstance(key, str) or key not in SLOT_KEYS or key in seen:
            continue
        seen.add(key)
        rows.append({
            "key": key,
            "hide_tablet": entry.get("hide_tablet") is True,
            "hide_mobile": entry.get("hide_mobile") is True,
        })
    return rows


def _default_slot_rows() -> list[dict]:
    return [{"key": key, "hide_tablet": False, "hide_mobile": False} for key in DEFAULT_SLOTS]


def effective_slots(raw) -> list[dict]:
    """The stored list, or the default four text slots when nothing valid is stored (an empty list means «use the default»)."""
    return clean_slots(raw) or _default_slot_rows()


# ----------------------------------------------------------------------------------------------------------------------------
# write-time cleaner (the Section's legacy validator)
# ----------------------------------------------------------------------------------------------------------------------------

def clean_hero_stage_settings(raw: dict) -> dict:
    """Keeps EVERY foreign key untouched (design / responsive / destination / motion …) and normalises only the keys this module owns
    when they are present; an absent key stays absent (a bare save never rewrites a section)."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    cleaned = dict(raw)
    for key in CHOICE_DEFAULTS:
        if key in raw:
            cleaned[key] = _choice(raw, key)
    for key in INTEGER_BOUNDS:
        if key in raw:
            cleaned[key] = _integer(raw, key)
    for key in TEXT_MAX:
        if key in raw:
            cleaned[key] = _text(raw, key)
    for key, _label in COLORS:
        if key in raw:
            cleaned[key] = _color(raw, key)
    for key in MEDIA_KEYS:
        if key in raw:
            media_id = _media_id(raw, key)
            if media_id is None:
                if raw[key] not in (None, "", "null"):
                    raise ValueError("رسانهٔ انتخاب‌شده نامعتبر است")        # junk is refused, only «no picture» clears the field
                cleaned.pop(key, None)
            else:
                cleaned[key] = media_id
    if "slots" in raw:
        cleaned["slots"] = clean_slots(raw["slots"])
    cleaned["v"] = SETTINGS_VERSION
    return cleaned


def default_settings() -> dict:
    """What a brand-new stage starts with — a complete, valid, editable composition (never a locked preset)."""
    return {
        "v": SETTINGS_VERSION,
        "header_mode": "merged",
        "bg_layout": "single",
        "text_tone": "light",
        "content_align": "center",
        "content_valign": "middle",
        "scrim_style": "both",
        "scrim_strength": 45,
        "height_desktop": 85,
        "eyebrow": "",
        "title": "تیتر اصلی فروشگاه",
        "subtitle": "",
        "button_label": "مشاهده محصولات",
        "slots": _default_slot_rows(),
    }


# ----------------------------------------------------------------------------------------------------------------------------
# recipes — the LOOK of a stage as data, reusable across Ready Templates (never the merchant's words or pictures)
# ----------------------------------------------------------------------------------------------------------------------------
#: what the merchant wrote / chose for THIS Store: copying another template's look must never overwrite it
CONTENT_KEYS = frozenset({
    *(key for key, _label, _limit in TEXTS), *MEDIA_KEYS,
    "bg_a_focal_x", "bg_a_focal_y", "bg_b_focal_x", "bg_b_focal_y",       # tuned to the merchant's own pictures
})


def layout_recipe_keys() -> tuple[str, ...]:
    """Every design key of the stage (header mode, panels, split, alignment, scrim, frame, heights, slots, …) — i.e. all but the content."""
    keys = [key for key, *_rest in CHOICES] + [key for key, *_rest in INTEGERS] + [key for key, _label in COLORS] + ["slots"]
    return tuple(dict.fromkeys(key for key in keys if key not in CONTENT_KEYS))


def layout_recipe(raw) -> dict:
    """The complete design recipe of ``raw`` (a template's stage settings): absent keys take the engine default, so applying it never leaves
    traces of the stage it replaces. Never raises on garbage (falls back to the defaults)."""
    base = default_settings()
    try:
        cleaned = clean_hero_stage_settings({**base, **(raw if isinstance(raw, dict) else {})})
    except ValueError:
        cleaned = dict(base)
    return {key: cleaned[key] for key in layout_recipe_keys() if key in cleaned}


def apply_layout_recipe(current, recipe: dict) -> dict:
    """``current`` with the recipe's design keys replaced and every content key (texts, pictures, focal points) and foreign key kept."""
    merged = dict(current) if isinstance(current, dict) else {}
    for key in layout_recipe_keys():
        merged.pop(key, None)                  # a key the recipe leaves out returns to the engine default instead of lingering
    merged.update({key: value for key, value in recipe.items() if key in layout_recipe_keys()})
    return clean_hero_stage_settings({**default_settings(), **merged})


# ----------------------------------------------------------------------------------------------------------------------------
# picture guidance — what size / ratio / safe area each picture slot of THIS stage needs (data only; the Studio computes the numbers live)
# ----------------------------------------------------------------------------------------------------------------------------
#: reference screens the sizes are derived from (CSS px): a common desktop and a common phone
GUIDE_VIEWPORTS = {"desktop": [1920, 1080], "mobile": [390, 844]}
#: the grid fractions of the panel split (must mirror the CSS ``data-hs-split`` columns — a test pins both)
GUIDE_SPLITS = {"equal": [1, 1], "wide_first": [3, 2], "wide_second": [2, 3], "first_dominant": [7, 3]}


def media_guide_spec() -> dict:
    """Per picture field: its role and the stage settings that drive its recommended size. The Inspector reads the live values of those
    settings (layout, split, height, fit, text position, header mode) and shows size / ratio / minimum / crop / safe-area advice for
    exactly the composition the merchant has chosen — not one fixed sentence for every template."""
    return {
        "viewports": GUIDE_VIEWPORTS,
        "splits": GUIDE_SPLITS,
        "slots": {
            "bg_a_media_asset_id": {"slot": "a", "focal": ["bg_a_focal_x", "bg_a_focal_y"],
                                    "role_single": "تصویر اصلیِ بوم (تمام‌عرض)", "role_dual": "پنل اول (سمت راست)"},
            "bg_b_media_asset_id": {"slot": "b", "focal": ["bg_b_focal_x", "bg_b_focal_y"],
                                    "role_single": "پنل دوم (فقط در حالتِ «دو پنل» استفاده می‌شود)", "role_dual": "پنل دوم (سمت چپ)"},
        },
        "driven_by": ["bg_layout", "bg_split", "height_desktop", "height_mobile", "mobile_dual", "image_fit",
                      "content_align", "content_valign", "header_mode"],
    }


# ----------------------------------------------------------------------------------------------------------------------------
# render-time projection
# ----------------------------------------------------------------------------------------------------------------------------

def header_mode_of(raw) -> str:
    source = raw if isinstance(raw, dict) else {}
    return _choice(source, "header_mode")


def resolve_stage_view(raw) -> dict:
    """Never raises. ``attrs`` is the ordered ``[(name, value)]`` list the template writes as ``data-hs-<name>``; ``style`` is the
    ``--hs-*`` custom-property declaration string (built only from clamped integers and allowlisted choices / semantic colours)."""
    source = raw if isinstance(raw, dict) else {}
    view: dict = {key: _choice(source, key) for key in CHOICE_DEFAULTS}
    for key in INTEGER_BOUNDS:
        view[key] = _integer(source, key)
    for key in TEXT_MAX:
        view[key] = _text(source, key)
    for key, _label in COLORS:
        view[key] = _color(source, key)

    attrs = [
        ("header", view["header_mode"]), ("layout", view["bg_layout"]), ("fit", view["image_fit"]),
        ("scrim", view["scrim_style"]), ("tone", view["text_tone"]), ("align", view["content_align"]),
        ("valign", view["content_valign"]), ("panel", view["content_frame"]), ("cta", view["button_style"]),
        ("title", view["title_size"]), ("weight", view["title_weight"]), ("border", view["frame_border"]),
        ("shadow", view["frame_shadow"]), ("mobile-dual", view["mobile_dual"]), ("card", view["card_position"]), ("split", view["bg_split"]),
    ]
    for key, name in (
        ("content_align_tablet", "align-t"), ("content_align_mobile", "align-m"), ("content_valign_mobile", "valign-m"),
        ("title_size_tablet", "title-t"), ("title_size_mobile", "title-m"),
    ):
        if view[key]:
            attrs.append((name, view[key]))
    view["attrs"] = attrs

    css = [
        f"--hs-h:{view['height_desktop']}vh", f"--hs-h-t:{view['height_tablet']}vh", f"--hs-h-m:{view['height_mobile']}vh",
        f"--hs-scrim:{view['scrim_strength'] / 100:g}",
        f"--hs-fx-a:{view['bg_a_focal_x']}%", f"--hs-fy-a:{view['bg_a_focal_y']}%",
        f"--hs-fx-b:{view['bg_b_focal_x']}%", f"--hs-fy-b:{view['bg_b_focal_y']}%",
        f"--hs-panel-op:{view['frame_opacity'] / 100:g}", f"--hs-panel-blur:{view['frame_blur']}px",
        f"--hs-radius:{view['frame_radius']}px", f"--hs-maxw:{view['content_max_width']}px",
    ]
    if view["fallback_color"]:
        css.append(f"--hs-fallback:{semantic_color_css(view['fallback_color'])}")
    if view["accent_color"]:
        css.append(f"--hs-accent:{semantic_color_css(view['accent_color'])}")
    view["style"] = ";".join(css)
    view["slots"] = effective_slots(source.get("slots"))
    return view
