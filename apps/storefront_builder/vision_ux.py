"""Vision Studio presentation data that is NOT engine data: where the model thumbnails live, whether they are still valid, and the plain
Persian wording shown next to registry models and settings.

Everything about a model (key, Persian name, capabilities, renderer) is read from ``global_region_registry`` - nothing is re-declared here.
This module only adds (a) the path / freshness rules of the pre-rendered thumbnails, (b) one-sentence descriptions keyed by the registry's own
variant keys, and (c) the polarity of switches by their REAL field key. ``test_vision_studio`` fails when a registry variant has no
description, no thumbnail or a stale thumbnail, so a new model can never silently ship without them."""

import hashlib
import json
import re
from pathlib import Path

from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.templatetags.static import static

from . import global_region_registry

STATIC_DIR = Path(__file__).resolve().parent / "static"
PREVIEWS_SUBDIR = "storefront_builder/vision/region_previews"
PREVIEWS_DIR = STATIC_DIR / PREVIEWS_SUBDIR
MANIFEST_PATH = PREVIEWS_DIR / "manifest.json"
MANIFEST_VERSION = 1
PREVIEW_TEMPLATE = "dashboard/vision/region_preview.html"

REGIONS = {
    "header": global_region_registry.GLOBAL_HEADER_REGION,
    "footer": global_region_registry.GLOBAL_FOOTER_REGION,
}
DEVICES = ("desktop", "mobile")

_INCLUDE_RE = re.compile(r"""{%\s*(?:include|extends)\s+["']([^"']+)["']""")


def _template_source(name):
    try:
        origin = get_template(name).origin
        return Path(origin.name).read_text(encoding="utf-8")
    except (TemplateDoesNotExist, OSError):
        return None


def _closure(name, seen):
    """The template and every literally-included / extended template below it (a model is often a thin wrapper around another one)."""
    if name in seen:
        return
    source = _template_source(name)
    if source is None:
        return
    seen[name] = source
    for child in _INCLUDE_RE.findall(source):
        if child.startswith("storefront_builder/partials/"):
            _closure(child, seen)


def variant_fingerprint(region_key, variant):
    """Identity of what a thumbnail depicts: the registry entry + the source of its renderer, of the templates it includes and of the preview page."""
    seen = {}
    _closure(variant.renderer, seen)
    # the thumbnails are photographs of the read-only preview page, so a change to it makes them stale too
    preview = _template_source(PREVIEW_TEMPLATE) or ""
    payload = json.dumps(
        {"region": region_key, "key": variant.key, "label": variant.label_fa, "caps": sorted(variant.capabilities),
         "preview": hashlib.sha256(preview.encode("utf-8")).hexdigest(),
         "templates": {name: hashlib.sha256(src.encode("utf-8")).hexdigest() for name, src in sorted(seen.items())}},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def thumbnail_relpath(region_key, variant_key, device):
    return f"{PREVIEWS_SUBDIR}/{region_key}/{variant_key}.{device}.webp"


def load_manifest():
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("regions", {}) if data.get("version") == MANIFEST_VERSION else {}


def thumbnail_state(region_key, variant, manifest=None):
    """``{"status": "ok"|"missing"|"stale", "desktop": url|None, "mobile": url|None, "same_as": key|None}``.

    Only a thumbnail captured from the CURRENT renderer is offered; a missing or stale one is reported as such (the gallery then says so
    instead of drawing a made-up picture)."""
    manifest = load_manifest() if manifest is None else manifest
    entry = (manifest.get(region_key) or {}).get(variant.key)
    if not entry:
        return {"status": "missing", "desktop": None, "mobile": None, "same_as": None}
    if entry.get("fingerprint") != variant_fingerprint(region_key, variant):
        return {"status": "stale", "desktop": None, "mobile": None, "same_as": None}
    urls = {}
    for device in DEVICES:
        rel = thumbnail_relpath(region_key, variant.key, device)
        urls[device] = static(rel) if (STATIC_DIR / rel).is_file() else None
    status = "ok" if urls["desktop"] else "missing"
    return {"status": status, **urls, "same_as": entry.get("same_as")}


# ---------------------------------------------------------------------------------------------------------------- wording of the models
#: One plain sentence per DISTINCT look, written from the real render (see the thumbnails). Models that render pixel-identically to
#: another one (``same_as`` in the manifest) reuse that model's sentence and are flagged as look-alikes in the gallery.
VARIANT_COPY = {
    "header": {
        "legacy_default": "جست‌وجوی بزرگ کنار نام فروشگاه، آیکن حساب و سبد، و منوی دسته‌بندی با دکمهٔ «دستهٔ کالاها» در ردیف جدا.",
        "marketplace_search_first": "جست‌وجوی عریض در مرکز، نام فروشگاه سمت راست و حساب و سبد سمت چپ؛ منوی دسته‌ها زیر آن.",
        "premium_three_column": "سه بخش در یک ردیف باریک: نام فروشگاه، منوی کوتاه و جست‌وجوی کوچک با آیکن‌ها.",
        "boutique_centered": "نام و لوگوی فروشگاه در مرکز، آیکن‌ها دو طرف آن و منوی دسته‌ها در ردیف جدا.",
        "dark_tech": "سربرگ (هدر) تیره با جست‌وجو و منوی کوتاه در یک نوار؛ مناسب فروشگاه‌های دیجیتال.",
        "promo_search_nav": "نوار پیشنهاد رنگی در بالا، جست‌وجو و دکمه‌های ورود و سبد، و منوی دسته‌ها زیر آن.",
        "beauty_search_nav": "جست‌وجوی عریض با دکمهٔ پررنگ و ردیف ناوبری فروشگاهی زیر آن.",
        "chocolate_centered_search": "نوار رنگی برند با کادر جست‌وجوی سفید در مرکز و منوی دسته‌ها زیر آن.",
        "atelier_nav": "مینیمال: نام فروشگاه و منو در یک ردیف و آیکن‌های جست‌وجو، حساب و سبد در گوشه.",
        "luxury_search": "جست‌وجوی برجستهٔ گرد در مرکز سربرگ (هدر)، آیکن‌های حساب و سبد دو طرف آن.",
        "stationery_search": "جست‌وجوی عریض، نوار اطلاعات تماس در بالا و ردیف ناوبری زیر آن.",
        "kawaii_center": "برند در مرکز با نوار اعلان رنگیِ دوگانه؛ ملایم و بوتیک‌وار.",
        "floating_card": "برند و منو روی یک کارت شناور بزرگ، با دکمه‌های رنگی بالای صفحه.",
        "editorial_row": "ردیف نشریه‌ای: نام فروشگاه و منو در یک خط با آیکن‌های حساب و سبد.",
        "centered_brand": "برند و منو در یک ردیف جمع‌وجور همراه با جست‌وجوی کوچک.",
        "promo_bar": "نوار کمپینی پررنگ بالای سربرگ (هدر) و زیر آن جست‌وجو و دسته‌بندی‌ها.",
    },
    "footer": {
        "legacy_default": "چهار ستون راهنما، دسته‌بندی‌ها، تماس و آدرس؛ زیر آن معرفی فروشگاه، نمادها و کپی‌رایت.",
        "marketplace_dense": "سه ستون فشردهٔ معرفی، راهنما و تماس با کپی‌رایت؛ مناسب کاتالوگ بزرگ.",
        "premium_columns": "دو ستون تمیز (راهنمای خرید و تماس) با فضای باز روی زمینهٔ روشن.",
        "boutique_editorial": "نام و توضیح فروشگاه در مرکز، زیر آن راهنما و تماس؛ حال‌وهوای نشریه.",
        "dark_tech": "فوتر تیره با ستون‌های معرفی، راهنما و تماس؛ مناسب فروشگاه دیجیتال.",
        "promo_columns": "سه ستون ساده روی زمینهٔ روشن با برند در یک سمت.",
        "beauty_retail_columns": "ردیف نشان‌های اعتماد (ارسال، پرداخت، پشتیبانی) بالای ستون‌ها.",
        "chocolate_dark_columns": "فوتر تیره با لبهٔ موجی رنگی و ستون‌های معرفی، راهنما و تماس.",
        "stationery_dark": "فوتر تیره با ستون‌های اطلاعات و نام بزرگ فروشگاه در پایین.",
        "kawaii_minimal": "نوار باریک: پیوندهای کوتاه در بالا، برند و کپی‌رایت روی نوار رنگی.",
        "centered_contact": "همه‌چیز در مرکز: برند، پیوندها و شمارهٔ تماس در یک کادر.",
    },
}
REGION_TITLES = {"header": "سربرگ (هدر)", "footer": "پابرگ (فوتر)"}


def _describe(region_key, variant, same_as_variant):
    copy = VARIANT_COPY[region_key]
    if variant.key in copy:
        return copy[variant.key]
    if same_as_variant is not None and same_as_variant.key in copy:
        return copy[same_as_variant.key]
    return ""


def gallery_data():
    """The model galleries of both regions, straight from the registry + the pre-rendered thumbnails (JSON-serialisable)."""
    manifest = load_manifest()
    data = {}
    for region_key, region in REGIONS.items():
        by_key = {v.key: v for v in region.variants}
        items = []
        for variant in region.variants:
            state = thumbnail_state(region_key, variant, manifest)
            twin = by_key.get(state["same_as"]) if state["same_as"] else None
            items.append({
                "key": variant.key,
                "label": variant.label_fa,
                "description": _describe(region_key, variant, twin),
                "status": state["status"],
                "desktop": state["desktop"],
                "mobile": state["mobile"],
                "same_as": twin.key if twin else None,
                "same_as_label": twin.label_fa if twin else None,
            })
        data[region_key] = {"title": REGION_TITLES[region_key], "default": region.default_variant, "items": items}
    return data


# ------------------------------------------------------------------------------------------------------------------ wording of the settings
#: Plain-language name + one sentence of effect for the controls of the Design modals, keyed by the control's REAL field key (the key R4 stores).
#: Only wording: nothing here changes what a control reads or writes. ``scope`` is where the setting acts (every key here is store-wide).
SETTING_COPY = {
    "palette_slug": ("پالت رنگ فروشگاه", "رنگ اصلی، پس‌زمینه و متن همهٔ صفحه‌ها را یک‌جا عوض می‌کند."),
    "font": ("فونت فروشگاه", "فونت همهٔ نوشته‌های فروشگاه (عنوان‌ها و توضیح‌ها) را تعیین می‌کند."),
    "type_scale": ("اندازهٔ نوشته‌ها", "همهٔ نوشته‌ها را کمی کوچک‌تر یا بزرگ‌تر می‌کند."),
    "motion": ("حرکت و افکت‌ها", "شدت حرکت‌ها و افکت‌های نمایشی فروشگاه؛ «بدون حرکت» همه را خاموش می‌کند."),
    "button_style": ("ظاهر دکمه‌ها", "دکمه‌های فروشگاه توپر، نرم یا فقط دورخط دیده شوند."),
    "radius": ("گردی گوشهٔ کارت‌ها و کادرها", "عدد بزرگ‌تر یعنی گوشه‌های گردتر برای کارت محصول و کادرها."),
    "button_radius": ("گردی گوشهٔ دکمه‌ها", "عدد بزرگ‌تر یعنی دکمه‌ها گردتر (کپسولی) دیده شوند."),
    "density": ("فاصلهٔ اجزا از هم", "فشرده = اجزای بیشتر در یک نگاه؛ باز = فضای خالی بیشتر بین اجزا."),
    "image_fit": ("چیدن عکس در قاب", "عکس قاب را پر کند (ممکن است لبه‌ها بریده شود) یا کامل دیده شود."),
    "image_hover": ("حرکت عکس با رفتن موس", "وقتی موس روی عکس می‌رود، عکس بزرگ‌نمایی شود یا ثابت بماند."),
    "card_image_crossfade": ("نمایش عکس دوم کارت", "با رفتن موس روی کارت محصول، عکس دوم محصول جای عکس اول نمایش داده می‌شود."),
    "card_image_zoom": ("بزرگ‌نمایی عکس کارت", "با رفتن موس روی کارت محصول، عکس کمی بزرگ‌تر می‌شود."),
    "heading_style": ("ظاهر عنوان بخش‌ها", "عنوان بخش‌ها در همهٔ صفحه‌ها: معمولی، وسط‌چین، با خط زیر یا ساده."),
    "content_width": ("حداکثر عرض محتوا", "محتوا در صفحه‌های بزرگ تا چند پیکسل پهن شود؛ عدد کمتر یعنی محتوای باریک‌تر."),
    "grid_density": ("تعداد ستون محصولات", "در فهرست محصولات چند کارت کنار هم دیده شود."),
    "card_shadow": ("سایهٔ کارت‌ها", "کارت‌های محصول با سایهٔ ملایم، پررنگ یا بدون سایه."),
    "card_hover": ("حرکت کارت با رفتن موس", "با رفتن موس، کارت بالا بیاید، بزرگ شود یا ثابت بماند."),
    "hero_style": ("شکل بخش بزرگ بالای صفحه", "اسلایدر یا بنر اصلی عریض، بلند یا دوبخشی نمایش داده شود."),
    "header_variant": ("مدل سربرگ (هدر)", "چیدمان لوگو، جست‌وجو، منو و آیکن‌ها در بالای همهٔ صفحه‌ها."),
    "footer_variant": ("مدل پابرگ (فوتر)", "چیدمان بخش پایین همهٔ صفحه‌ها: لینک‌ها، تماس و نمادها."),
    "mobile_nav_variant": ("مدل نوار پایین موبایل", "نوار میان‌بر ثابت پایین صفحه فقط در گوشی (خانه، دسته‌ها، سبد…)."),
    # header toggles
    "show_search": ("نمایش جست‌وجو", "کادر یا آیکن جست‌وجو در سربرگ (هدر) دیده شود."),
    "show_account": ("نمایش حساب کاربری", "آیکن ورود / حساب کاربر در سربرگ (هدر) دیده شود."),
    "show_cart": ("نمایش سبد خرید", "آیکن سبد خرید در سربرگ (هدر) دیده شود. (سبد از دسترس خارج نمی‌شود: همیشه یک راه رسیدن به آن می‌ماند.)"),
    "show_wishlist": ("نمایش علاقه‌مندی‌ها", "آیکن علاقه‌مندی‌ها در سربرگ (هدر) دیده شود."),
    "sticky": ("چسبان بودن سربرگ (هدر)", "با اسکرول صفحه، سربرگ (هدر) بالای صفحه می‌ماند."),
    "announcement_enabled": ("نمایش نوار اعلان", "نوار اعلان بالای سربرگ (هدر) دیده شود."),
    # footer toggles
    "show_about": ("نمایش معرفی فروشگاه", "توضیح کوتاه دربارهٔ فروشگاه در پابرگ (فوتر) دیده شود."),
    "show_contact": ("نمایش اطلاعات تماس", "تلفن، ایمیل و ساعت کاری در پابرگ (فوتر) دیده شود."),
    "show_quick_links": ("نمایش لینک‌های مفید", "لینک‌های راهنمای خرید در پابرگ (فوتر) دیده شود."),
    "show_categories": ("نمایش دسته‌بندی‌ها", "فهرست دسته‌بندی‌ها در پابرگ (فوتر) دیده شود."),
    "show_social": ("نمایش شبکه‌های اجتماعی", "آیکن شبکه‌های اجتماعی در پابرگ (فوتر) دیده شود."),
    "show_trust_badges": ("نمایش نشان‌های اعتماد", "نمادهای اعتماد (مثل نماد الکترونیکی) در پابرگ (فوتر) دیده شود."),
    "show_payment_logos": ("نمایش لوگوی روش‌های پرداخت", "لوگوی درگاه‌ها و روش‌های پرداخت در پابرگ (فوتر) دیده شود."),
    "show_newsletter": ("نمایش عضویت در خبرنامه", "فرم عضویت خبرنامه در پابرگ (فوتر) دیده شود."),
    "show_copyright": ("نمایش کپی‌رایت", "سطر حقوق و نام فروشگاه در پایین پابرگ (فوتر) دیده شود."),
}
#: Responsive rows: the REAL stored property -> (device title, device word, devices it acts on). ``hide_on_*`` is stored as "hidden", so the
#: control that shows «visible» is the inverse of the stored boolean (the adapter in vision.js keeps R4's checkbox as the one source of truth).
RESPONSIVE_PROPS = {
    "hide_on_tablet": ("نمایش در تبلت", "تبلت"),
    "hide_on_mobile": ("نمایش در موبایل", "موبایل"),
}
SCOPE_STORE = "کل فروشگاه"
SCOPE_ALL_DEVICES = "دسکتاپ، تبلت و موبایل"


def ux_data():
    """Everything vision.js needs about wording and switch polarity, as one JSON-serialisable dict."""
    return {
        "settings": {key: {"title": title, "effect": effect} for key, (title, effect) in SETTING_COPY.items()},
        "responsive": {prop: {"title": title, "device": device} for prop, (title, device) in RESPONSIVE_PROPS.items()},
        # a stored property whose name starts with one of these means "hidden / off when true": shown inverted as «visible»
        "inverted_prefixes": ["hide_"],
        "scope_store": SCOPE_STORE,
        "scope_all_devices": SCOPE_ALL_DEVICES,
    }
