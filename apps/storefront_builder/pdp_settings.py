"""PDP presentation settings — the ONE authority for the generic design controls of ``product_main`` and ``product_description``.

Both sections stay single, unified Sections of the one R4 engine. This module only owns the *presentation* vocabulary:

* a closed table of choices / switches per section (each default is EXACTLY what the storefront rendered before these controls
  existed, so a Store that never touched them looks and behaves identically);
* a lenient write-time cleaner (the Section's legacy validator; schema cleaning already rejects out-of-vocabulary input) and a lenient
  render-time resolver that can never raise — a stale / hand-edited stored value falls back to its default, it never breaks a page;
* the data-attribute projection the shared stylesheet reads (``product_detail.css``) — attributes are emitted ONLY when a value differs
  from its default, so default Stores render byte-for-byte what they rendered before.

Nothing here reads prices, stock, variants, reviews or any other business data: those always come from their own models through the
existing page context (``render_service._product_main_context`` / ``_product_description_context``). The settings can only change how
the real data is arranged and styled, never what it is. No section key, Ready Template key or store brand is named anywhere.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------------------------------------------------
# product_main
# --------------------------------------------------------------------------------------------------------------------------------

#: ``(key, merchant label, ((value, label), ...), default)`` — the default is always the first-rendered, pre-existing behaviour.
PRODUCT_MAIN_CHOICES = (
    ("layout_variant", "مدل کلی چیدمان", (
        ("standard", "استاندارد"),
        ("fashion", "فشن — تصاویر کوچک عمودی کنار عکس اصلی"),
    ), "standard"),
    ("gallery_position", "جای گالری نسبت به اطلاعات خرید", (
        ("start", "سمت شروع (راست در صفحهٔ فارسی)"),
        ("end", "سمت پایان (چپ در صفحهٔ فارسی)"),
    ), "start"),
    ("gallery_split", "نسبت عرض گالری و اطلاعات", (
        ("equal", "برابر"),
        ("gallery_wide", "گالری عریض‌تر"),
        ("info_wide", "اطلاعات عریض‌تر"),
    ), "equal"),
    ("thumbs_position", "جای تصاویر کوچک گالری", (
        ("auto", "خودکار (مطابق مدل کلی چیدمان)"),
        ("below", "زیر عکس اصلی"),
        ("side", "کنار عکس اصلی"),
        ("hidden", "نمایش داده نشود"),
    ), "auto"),
    ("info_panel", "قاب پنل اطلاعات و خرید", (
        ("plain", "بدون قاب"),
        ("card", "کارت با حاشیهٔ ملایم"),
        ("outlined", "کادر پررنگ با رنگ اصلی"),
    ), "plain"),
    ("price_layout", "نمایش قیمت", (
        ("box", "داخل کادر قیمت"),
        ("plain", "ساده و بدون کادر"),
    ), "box"),
    ("price_position", "جای قیمت", (
        ("after_options", "بعد از انتخاب تنوع"),
        ("before_options", "قبل از انتخاب تنوع"),
    ), "after_options"),
    ("qty_layout", "چیدمان تعداد و دکمهٔ خرید", (
        ("stacked", "تعداد بالای دکمه"),
        ("inline", "تعداد کنار دکمه، در یک ردیف"),
    ), "stacked"),
    ("option_style", "ظاهر انتخاب تنوع", (
        ("auto", "خودکار (رنگ‌ها به‌صورت دایره)"),
        ("chips", "همیشه دکمه‌های متنی"),
    ), "auto"),
    ("option_shape", "شکل گزینه‌های تنوع", (
        ("rounded", "گوشه‌گرد"),
        ("square", "تقریباً مربعی"),
        ("pill", "قرصی"),
    ), "rounded"),
    ("cta_width", "عرض دکمهٔ افزودن به سبد", (
        ("full", "تمام عرض ردیف"),
        ("auto", "به اندازهٔ متن"),
    ), "full"),
    ("cta_size", "اندازهٔ دکمهٔ افزودن به سبد", (
        ("compact", "کوچک"),
        ("normal", "معمولی"),
        ("large", "بزرگ"),
    ), "normal"),
    ("cta_shape", "شکل دکمهٔ افزودن به سبد", (
        ("rounded", "گوشه‌گرد"),
        ("square", "تقریباً مربعی"),
        ("pill", "قرصی"),
    ), "rounded"),
    # typography (V5 six-site kit): the product title and the price are the two type roles a product page tunes per brand
    ("title_size", "اندازهٔ عنوان محصول", (
        ("normal", "معمولی"),
        ("large", "بزرگ"),
        ("xlarge", "خیلی بزرگ"),
    ), "normal"),
    ("price_size", "اندازهٔ قیمت", (
        ("small", "کوچک"),
        ("normal", "معمولی"),
        ("large", "بزرگ"),
        ("xlarge", "خیلی بزرگ"),
    ), "normal"),
)

#: ``(key, merchant label, default)`` — switches (all ``True``: everything the page showed before stays shown).
PRODUCT_MAIN_SWITCHES = (
    ("gallery_sticky", "گالری هنگام اسکرول بالای صفحه بماند", True),
    ("show_breadcrumb", "نمایش مسیر صفحه (خانه ‹ دسته ‹ محصول)", True),
    ("show_discount_badge", "نمایش نشان درصد تخفیف روی عکس", True),
    ("show_topline", "نمایش برند، امتیاز، تعداد نظر و تعداد فروش", True),
    ("show_sku", "نمایش کد کالا", True),
    ("show_quantity", "نمایش انتخاب تعداد (در غیر این صورت همیشه ۱ عدد)", True),
    ("show_wishlist", "نمایش دکمهٔ علاقه‌مندی", True),
    ("show_mobile_sticky_bar", "نوار خرید ثابت پایین صفحه در موبایل", True),
)

#: choice value -> data attribute name the stylesheet reads (the three that already exist keep their historical name)
_PRODUCT_MAIN_ATTRIBUTE_NAMES = {
    "gallery_position": "gallery-pos",
    "gallery_split": "gallery-split",
    "thumbs_position": "thumbs",
    "info_panel": "info-panel",
    "price_layout": "price-layout",
    "price_position": "price-pos",
    "qty_layout": "qty-layout",
    "option_style": "option-style",
    "option_shape": "option-shape",
    "cta_width": "cta-width",
    "cta_size": "cta-size",
    "cta_shape": "cta-shape",
    "title_size": "title-size",
    "price_size": "price-size",
}

PRODUCT_MAIN_SETTING_KEYS = tuple(key for key, *_rest in PRODUCT_MAIN_CHOICES) + tuple(key for key, *_rest in PRODUCT_MAIN_SWITCHES)


def _flag(value, default: bool) -> bool:
    """Lenient boolean: only an explicit, recognised value changes the default (never Python truthiness of a string)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
    return default


def _choice(raw: dict, key: str, choices, default: str) -> str:
    value = raw.get(key)
    return value if any(value == allowed for allowed, _label in choices) else default


def clean_product_main_settings(raw: dict) -> dict:
    """Write-time cleaner (the section's legacy validator). Keeps EVERY other stored key untouched — the shared wrappers
    (design / background / spacing / responsive …) and any legacy value travel through exactly as before — and only normalises
    the keys this module owns when they are present: an absent key stays absent (a Store is never rewritten by a bare save)."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    cleaned = dict(raw)
    for key, _label, choices, default in PRODUCT_MAIN_CHOICES:
        if key in raw:
            cleaned[key] = _choice(raw, key, choices, default)
    for key, _label, default in PRODUCT_MAIN_SWITCHES:
        if key in raw:
            cleaned[key] = _flag(raw[key], default)
    return cleaned


def resolve_product_main_view(raw) -> dict:
    """Render-time resolution — never raises. ``view[key]`` is always a valid value; ``view["attrs"]`` is the ordered list of
    ``(attribute-name, value)`` pairs that differ from the default (what the template writes as ``data-<name>="<value>"``)."""
    source = raw if isinstance(raw, dict) else {}
    view: dict = {}
    attrs: list[tuple[str, str]] = []
    for key, _label, choices, default in PRODUCT_MAIN_CHOICES:
        value = _choice(source, key, choices, default)
        view[key] = value
        name = _PRODUCT_MAIN_ATTRIBUTE_NAMES.get(key)
        if name and value != default:
            attrs.append((name, value))
    for key, _label, default in PRODUCT_MAIN_SWITCHES:
        view[key] = _flag(source.get(key), default)
    if not view["gallery_sticky"]:
        attrs.append(("gallery-sticky", "off"))
    view["attrs"] = attrs
    return view


# --------------------------------------------------------------------------------------------------------------------------------
# product_description
# --------------------------------------------------------------------------------------------------------------------------------

PRODUCT_DESCRIPTION_CHOICES = (
    ("layout_mode", "چیدمان بخش‌های اطلاعات", (
        ("tabs", "تب افقی (در موبایل آکاردئون)"),
        ("tabs_vertical", "تب عمودی کنار محتوا (در موبایل آکاردئون)"),
        ("accordion", "آکاردئون در همهٔ اندازه‌ها"),
        ("stacked", "پشت‌سرهم، همه باز و بدون تب"),
    ), "tabs"),
    ("tab_style", "ظاهر سربرگ‌ها", (
        ("underline", "خط زیر سربرگ فعال"),
        ("pills", "قرص رنگی"),
        ("boxed", "جعبه‌ای"),
    ), "underline"),
    ("tab_align", "تراز سربرگ‌ها", (
        ("start", "از ابتدا"),
        ("center", "وسط"),
        ("stretch", "هم‌عرض و تمام‌عرض"),
    ), "start"),
    ("panel_style", "قاب محتوای هر بخش", (
        ("plain", "بدون قاب"),
        ("boxed", "قاب با حاشیه"),
        ("soft", "زمینهٔ ملایم"),
    ), "plain"),
)

#: Sections the page can really supply. ``brand`` is real data too (``Product.brand``: name, name_en, logo, description, country,
#: website) but it did not exist before, so it is OFF unless the merchant lists it — an existing Store never gains it.
PRODUCT_DESCRIPTION_SECTION_KEYS = ("desc", "spec", "review", "brand")
PRODUCT_DESCRIPTION_DEFAULT_LABELS = {
    "desc": "توضیحات محصول",
    "spec": "مشخصات فنی",
    "review": "نظرات کاربران",
    "brand": "دربارهٔ برند",
}
PRODUCT_DESCRIPTION_SECTION_CHOICE_LABELS = (
    ("desc", "توضیحات محصول"),
    ("spec", "مشخصات فنی"),
    ("review", "نظرات کاربران"),
    ("brand", "برند (فقط اگر محصول برند دارد)"),
)
_DEFAULT_VISIBLE = {"desc": True, "spec": True, "review": True, "brand": False}
PRODUCT_DESCRIPTION_MAX_ITEMS = len(PRODUCT_DESCRIPTION_SECTION_KEYS)
PRODUCT_DESCRIPTION_MAX_LABEL = 40

#: the data attribute each non-default choice is written as on ``.pdp-tabs``
_PRODUCT_DESCRIPTION_ATTRIBUTE_NAMES = {
    "layout_mode": "tabs-mode",
    "tab_style": "tab-style",
    "tab_align": "tab-align",
    "panel_style": "panel-style",
}


def _clean_section_rows(raw) -> list[dict]:
    """The ordered rows the merchant listed: valid keys only, first occurrence wins, label trimmed, ``visible`` lenient."""
    rows: list[dict] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key not in PRODUCT_DESCRIPTION_SECTION_KEYS or key in seen:
            continue
        seen.add(key)
        label = item.get("label")
        label = label.strip()[:PRODUCT_DESCRIPTION_MAX_LABEL] if isinstance(label, str) else ""
        rows.append({"key": key, "label": label, "visible": _flag(item.get("visible"), True)})
    return rows


def clean_product_description_settings(raw: dict) -> dict:
    """Write-time cleaner — same contract as ``clean_product_main_settings`` (other keys untouched, absent keys stay absent)."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    cleaned = dict(raw)
    for key, _label, choices, default in PRODUCT_DESCRIPTION_CHOICES:
        if key in raw:
            cleaned[key] = _choice(raw, key, choices, default)
    if "sections" in raw:
        cleaned["sections"] = _clean_section_rows(raw["sections"])
    return cleaned


def effective_description_sections(raw_sections) -> list[dict]:
    """Every section the page can supply, in effective order: the merchant's listed rows first (in their order), then each
    remaining section at its default place and visibility. ``label`` is never empty (blank = the default label)."""
    rows = _clean_section_rows(raw_sections)
    listed = {row["key"] for row in rows}
    for key in PRODUCT_DESCRIPTION_SECTION_KEYS:
        if key not in listed:
            rows.append({"key": key, "label": "", "visible": _DEFAULT_VISIBLE[key]})
    return [
        {**row, "label": row["label"] or PRODUCT_DESCRIPTION_DEFAULT_LABELS[row["key"]]}
        for row in rows
    ]


def project_description_sections_for_inspector(settings: dict) -> dict:
    """What the Inspector's list shows for the stored value: the effective rows (so a never-edited Store shows the three real
    sections instead of an empty list). A label equal to its default is shown blank — blank always means «default label»."""
    rows = effective_description_sections((settings or {}).get("sections"))
    return {"sections": [
        {"key": row["key"], "label": "" if row["label"] == PRODUCT_DESCRIPTION_DEFAULT_LABELS[row["key"]] else row["label"],
         "visible": row["visible"]}
        for row in rows
    ]}


def resolve_product_description_view(raw, *, brand_available: bool = False) -> dict:
    """Render-time resolution — never raises. ``sections`` holds ONLY what is visible and really available: a hidden section,
    or ``brand`` for a product without brand content, is dropped, so no tab/heading is ever empty or decorative."""
    source = raw if isinstance(raw, dict) else {}
    view: dict = {}
    attrs: list[tuple[str, str]] = []
    for key, _label, choices, default in PRODUCT_DESCRIPTION_CHOICES:
        value = _choice(source, key, choices, default)
        view[key] = value
        if value != default:
            attrs.append((_PRODUCT_DESCRIPTION_ATTRIBUTE_NAMES[key], value))
    sections = [
        row for row in effective_description_sections(source.get("sections"))
        if row["visible"] and (row["key"] != "brand" or brand_available)
    ]
    view["sections"] = sections
    view["attrs"] = attrs
    view["first_key"] = sections[0]["key"] if sections else ""
    view["stacked"] = view["layout_mode"] == "stacked"
    # Built only from the closed key vocabulary above (never from merchant text), so it is safe inside an x-data attribute.
    view["keys_js"] = "[" + ", ".join(f"'{row['key']}'" for row in sections) + "]"
    view["count"] = len(sections)
    return view
