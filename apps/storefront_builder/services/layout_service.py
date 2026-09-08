"""چرخه حیات چیدمان صفحه فروشگاه — Draft / Preview / Publish / Discard / Restore.

قوانین معماری (طبق تصمیمات حل‌شده کاربر، بخش ۳۲ گزارش ممیزی):

- هر عملیات با ``store`` (نه ``layout_id``/``version_id`` خام از ورودی
  کاربر) شروع می‌شود؛ تمام lookupهای بعدی transitively به همان Store
  محدود می‌شوند — این همان تفکیک مستأجر دوگانه (view + سرویس) است که در
  کل کدبیس رعایت شده.
- انتشار (``publish``) کاملاً اتمیک است: تنها کاری که انجام می‌شود عوض
  کردن دو اشاره‌گر (``published_version``/``draft_version``) روی
  ``StorefrontLayout`` است — محتوای نسخه از قبل کامل/معتبر است، پس
  انتشار ناموفق هرگز نمی‌تواند نیمه‌کاره storefront زنده را جایگزین کند.
- بازگردانی (``restore_version``) هرگز مستقیماً منتشر نمی‌شود — همیشه
  یک Draft جدید می‌سازد که باید جداگانه publish شود.
- Rate limiting فقط روی عملیات حساس (publish/restore/ساخت نسخه جدید)
  اعمال می‌شود، نه روی بازچینش معمولی — با استفاده مجدد از
  ``apps.core.services.rate_limit`` موجود، نه یک مکانیزم جدید.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.services.rate_limit import enforce_rate_limit

from .. import appearance_registry, global_region_registry, layout_preset_registry
from . import container_service
from ..models import (
    APPEARANCE_COLOR_KEYS,
    APPEARANCE_CONFIG_DEFAULTS,
    ANNOUNCEMENT_LINK_DEFAULTS,
    FOOTER_CONFIG_DEFAULTS,
    FOOTER_RESPONSIVE_AWARE_KEYS,
    FOOTER_TOGGLE_FIELDS,
    HEADER_CONFIG_DEFAULTS,
    HEADER_RESPONSIVE_AWARE_KEYS,
    HEADER_TOGGLE_FIELDS,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from ..storefront_appearance.contracts import InvalidStoreAppearanceContract
from ..storefront_appearance.families import DEFAULT_STORE_APPEARANCE_MANIFEST
from ..storefront_appearance.persistence import STORE_APPEARANCE_CONFIG_KEY
from ..storefront_appearance.validation import (
    manifest_to_primitive,
    normalize_persisted_manifest,
)

_PUBLISH_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
_RESTORE_RATE_LIMIT = dict(max_attempts=20, window_seconds=3600)
_NEW_DRAFT_RATE_LIMIT = dict(max_attempts=30, window_seconds=3600)


class NoDraftToPublishError(Exception):
    """چیزی برای انتشار وجود ندارد — هیچ Draft فعالی برای این فروشگاه نیست."""


class CrossStoreVersionError(Exception):
    """نسخه‌ی درخواست‌شده متعلق به این فروشگاه نیست."""


class StorefrontAlreadyPublishedError(Exception):
    """این فروشگاه از قبل یک نسخه‌ی منتشرشده (سفارشی‌سازی‌شده) دارد — اعمال
    چیدمان پیشنهادی صنف بدون تأیید صریح کاربر مجاز نیست (تصمیم کاربر:
    «هرگز storefront سفارشی‌سازی‌شده و منتشرشده را بدون تأیید صریح رونویسی
    نکن»)."""


class HeaderConfigValidationError(Exception):
    """پیکربندی پیشنهادی هدر نامعتبر است — نباید ذخیره شود (پیام فارسی
    قابل‌نمایش مستقیم به کاربر)."""


class AppearanceConfigValidationError(Exception):
    """پیکربندی پیشنهادی ظاهر نامعتبر است — نباید ذخیره شود (پیام فارسی
    قابل‌نمایش مستقیم به کاربر)."""


class FooterConfigValidationError(Exception):
    """پیکربندی پیشنهادی فوتر نامعتبر است — نباید ذخیره شود (پیام فارسی
    قابل‌نمایش مستقیم به کاربر)."""


def _validate_shell_component_responsive(raw, allowed_keys: list[str]) -> dict:
    """قراردادِ مشترکِ «نمایش در دستگاه‌ها» برایِ کامپوننت‌هایِ هدر/فوتر
    (Phase 4) — دقیقاً همان الگویِ ``section_registry.validate_responsive_settings``
    (بخشِ سازنده بصری برایِ section‌ها): کلیدِ غایب/شکلِ نامعتبر یعنی
    «نمایان در همه‌جا» (بی‌صدا، نه خطا)؛ فقط کلیدهایِ عضوِ ``allowed_keys``
    خوانده می‌شوند — بقیه‌یِ کلیدهایِ ورودی (حتی اگر تاجر چیزِ دیگری
    فرستاده باشد) بی‌صدا نادیده گرفته می‌شوند."""
    if not isinstance(raw, dict):
        raw = {}
    cleaned = {}
    for key in allowed_keys:
        component_raw = raw.get(key)
        if not isinstance(component_raw, dict):
            component_raw = {}
        cleaned[key] = {
            "hide_on_tablet": bool(component_raw.get("hide_on_tablet", False)),
            "hide_on_mobile": bool(component_raw.get("hide_on_mobile", False)),
        }
    return cleaned


#: Phase 8 P0-3 — انواعِ مجازِ بلوکِ اختیاریِ هدر؛ allowlist صریح، دقیقاً
#: همان الگویِ section_registry (هیچ نوعِ دلخواه/آزادِ دیگری پذیرفته
#: نمی‌شود). ``phone``/``social`` دوباره از داده‌ی هویتِ زنده‌یِ موجودِ
#: فروشگاه می‌خوانند (``SHOP_CONTACT_PHONE``/``SOCIAL_LINKS_HEADER`` —
#: از پیش در context processorها موجود بودند، بدونِ مصرف‌کننده)، نه
#: یک کپیِ تازه‌یِ آن داده در پیکربندیِ Draft.
HEADER_EXTRA_BLOCK_TYPES = ("phone", "social", "cta", "spacer", "tagline")
_MAX_HEADER_EXTRA_BLOCKS = 6
_MAX_HEADER_CTA_LABEL_LENGTH = 30


class ShellBlockError(Exception):
    """شکلِ خامِ یک بلوکِ اختیاریِ هدر نامعتبر است."""


_MAX_ANNOUNCEMENT_LINKS = 4
_MAX_ANNOUNCEMENT_LINK_LABEL_LENGTH = 50
_MAX_ANNOUNCEMENT_LINK_URL_LENGTH = 500


def _validate_announcement_links(raw) -> list[dict]:
    """لینک‌های کوچک نوار اعلان را بدون اجازه‌دادن به scheme خطرناک پاک‌سازی می‌کند."""
    if raw is None:
        raw = [dict(item) for item in ANNOUNCEMENT_LINK_DEFAULTS]
    if not isinstance(raw, (list, tuple)):
        raise ShellBlockError("فهرست لینک‌های نوار اعلان نامعتبر است")
    if len(raw) > _MAX_ANNOUNCEMENT_LINKS:
        raise ShellBlockError(f"حداکثر {_MAX_ANNOUNCEMENT_LINKS} لینک در نوار اعلان مجاز است")

    from django.core.exceptions import ValidationError as DjangoValidationError
    from apps.content.models import validate_external_url

    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ShellBlockError("شکل یکی از لینک‌های نوار اعلان نامعتبر است")
        label = str(entry.get("label", "")).strip()[:_MAX_ANNOUNCEMENT_LINK_LABEL_LENGTH]
        url = str(entry.get("url", "")).strip()[:_MAX_ANNOUNCEMENT_LINK_URL_LENGTH]
        if not label:
            continue
        if not url:
            url = "#"

        is_fragment = url.startswith("#")
        is_internal = url.startswith("/") and not url.startswith("//")
        if not is_fragment and not is_internal:
            try:
                validate_external_url(url)
            except DjangoValidationError as exc:
                raise ShellBlockError("; ".join(exc.messages)) from exc

        cleaned.append({"label": label, "url": url})
    return cleaned


def _validate_header_extra_blocks(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ShellBlockError("فهرستِ بلوک‌هایِ هدر نامعتبر است")
    if len(raw) > _MAX_HEADER_EXTRA_BLOCKS:
        raise ShellBlockError(f"حداکثر {_MAX_HEADER_EXTRA_BLOCKS} بلوکِ اضافی در هدر مجاز است")

    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.content.models import validate_external_url

    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ShellBlockError("شکلِ یکی از بلوک‌هایِ هدر نامعتبر است")
        block_type = entry.get("type")
        if block_type not in HEADER_EXTRA_BLOCK_TYPES:
            raise ShellBlockError("نوعِ یکی از بلوک‌هایِ هدر نامعتبر است")
        block = {"type": block_type}
        if block_type == "cta":
            block["label"] = str(entry.get("label", "")).strip()[:_MAX_HEADER_CTA_LABEL_LENGTH]
            url = str(entry.get("url", "")).strip()
            if url:
                try:
                    validate_external_url(url)
                except DjangoValidationError as exc:
                    raise ShellBlockError("; ".join(exc.messages)) from exc
            block["url"] = url
        cleaned.append(block)
    return cleaned


def validate_header_config(config: dict) -> dict:
    """پیکربندی خام هدر (خروجی فرم ادیتور) را اعتبارسنجی و پاک‌سازی می‌کند.

    قوانین بر اساس بررسی مستقیم قرارداد فعلی (نه فرض‌های سند معماری):
    ``HEADER_TOGGLE_FIELDS`` (``models.py``) و دو تمپلیت مصرف‌کننده
    (``page_shell_header.html``، مشترک بین Preview و Storefront، فاز A1).

    - فقط کلیدهای شناخته‌شده (``HEADER_TOGGLE_FIELDS`` + ``announcement_text``)
      وارد پیکربندی نهایی می‌شوند — کلید ناشناخته بی‌صدا حذف می‌شود.
    - هر toggle باید دقیقاً بولی باشد.
    - ``show_cart``: در معماری فعلی، آیکون سبد خرید در هدر تنها مسیر
      موجود به سبد خرید است — نه در فوتر، نه در ناوبری. غیرفعال کردن آن
      یعنی مشتری هیچ راهی برای رسیدن به سبد خرید ندارد؛ رد می‌شود.
    - بازگشت به صفحه اصلی (لوگو) در هیچ تمپلیتی پشت هیچ toggle‌ای نیست —
      همیشه بدون قید رندر می‌شود، پس نیازی به قانون جداگانه ندارد.
    """
    cleaned = dict(HEADER_CONFIG_DEFAULTS)
    for field in HEADER_TOGGLE_FIELDS:
        value = config.get(field, True)
        if not isinstance(value, bool):
            raise HeaderConfigValidationError(f"مقدار فیلد «{field}» باید درست/نادرست باشد")
        cleaned[field] = value

    announcement_text = config.get("announcement_text", "")
    if not isinstance(announcement_text, str):
        raise HeaderConfigValidationError("متن نوار اعلان نامعتبر است")
    cleaned["announcement_text"] = announcement_text[:300]

    try:
        cleaned["announcement_links"] = _validate_announcement_links(config.get("announcement_links"))
    except ShellBlockError as exc:
        raise HeaderConfigValidationError(str(exc)) from exc

    announcement_show_phone = config.get("announcement_show_phone", True)
    if not isinstance(announcement_show_phone, bool):
        raise HeaderConfigValidationError("تنظیم نمایش تلفن در نوار اعلان نامعتبر است")
    cleaned["announcement_show_phone"] = announcement_show_phone

    cleaned["responsive"] = _validate_shell_component_responsive(
        config.get("responsive"), HEADER_RESPONSIVE_AWARE_KEYS,
    )

    try:
        cleaned["extra_blocks"] = _validate_header_extra_blocks(config.get("extra_blocks"))
    except ShellBlockError as exc:
        raise HeaderConfigValidationError(str(exc)) from exc

    try:
        cleaned["header_variant"] = global_region_registry.validate_global_variant_selection(
            global_region_registry.GLOBAL_HEADER_REGION, config.get("header_variant"),
        )
    except global_region_registry.UnknownGlobalVariantSelectionError as exc:
        raise HeaderConfigValidationError(str(exc)) from exc

    if not cleaned["show_cart"]:
        raise HeaderConfigValidationError(
            "دسترسی به سبد خرید نمی‌تواند از هدر حذف شود — در حال حاضر هیچ مسیر "
            "جایگزینی برای رسیدن مشتری به سبد خرید در ناوبری فروشگاه وجود ندارد."
        )
    return cleaned


#: Phase 8 P0-4 — انواعِ مجازِ ستونِ اضافیِ فوتر؛ همان الگویِ
#: HEADER_EXTRA_BLOCK_TYPES بالا. ``social`` دوباره از همان دادهٔ
#: هویتِ زنده (``SOCIAL_LINKS_FOOTER``) می‌خواند که ``show_social``ی
#: موجود هم استفاده می‌کند — تکرارِ همان بلوک، مثلاً برایِ نمایشِ آن در
#: هر دو انتهای فوتر.
FOOTER_EXTRA_BLOCK_TYPES = ("custom_text", "link", "social")
_MAX_FOOTER_EXTRA_BLOCKS = 4
_MAX_FOOTER_BLOCK_TITLE_LENGTH = 40
_MAX_FOOTER_BLOCK_TEXT_LENGTH = 400


def _validate_footer_extra_blocks(raw) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ShellBlockError("فهرستِ ستون‌هایِ اضافیِ فوتر نامعتبر است")
    if len(raw) > _MAX_FOOTER_EXTRA_BLOCKS:
        raise ShellBlockError(f"حداکثر {_MAX_FOOTER_EXTRA_BLOCKS} ستونِ اضافی در فوتر مجاز است")

    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.content.models import validate_external_url

    cleaned = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ShellBlockError("شکلِ یکی از ستون‌هایِ فوتر نامعتبر است")
        block_type = entry.get("type")
        if block_type not in FOOTER_EXTRA_BLOCK_TYPES:
            raise ShellBlockError("نوعِ یکی از ستون‌هایِ فوتر نامعتبر است")
        block = {"type": block_type}
        if block_type == "custom_text":
            block["title"] = str(entry.get("title", "")).strip()[:_MAX_FOOTER_BLOCK_TITLE_LENGTH]
            block["text"] = str(entry.get("text", "")).strip()[:_MAX_FOOTER_BLOCK_TEXT_LENGTH]
        elif block_type == "link":
            block["label"] = str(entry.get("label", "")).strip()[:_MAX_FOOTER_BLOCK_TITLE_LENGTH]
            url = str(entry.get("url", "")).strip()
            if url:
                try:
                    validate_external_url(url)
                except DjangoValidationError as exc:
                    raise ShellBlockError("; ".join(exc.messages)) from exc
            block["url"] = url
        cleaned.append(block)
    return cleaned


def validate_footer_config(config: dict) -> dict:
    """پیکربندی خام فوتر را اعتبارسنجی و پاک‌سازی می‌کند.

    قانون: فوتر نباید کاملاً خالی منتشر شود — طبق تصمیم محصولی این فاز،
    حداقل یکی از ۹ بخش قابل‌تنظیم فوتر (``FOOTER_TOGGLE_FIELDS``) باید
    فعال بماند. هیچ محتوای اضافه‌ای که معماری فعلی اجازه‌ی غیابش را
    می‌دهد (مثلاً محتوای هر ستون) اینجا اجباری نشده — فقط از یک نوار
    فوتر کاملاً نامرئی/تهی جلوگیری می‌شود.
    """
    cleaned = dict(FOOTER_CONFIG_DEFAULTS)
    for field in FOOTER_TOGGLE_FIELDS:
        value = config.get(field, True)
        if not isinstance(value, bool):
            raise FooterConfigValidationError(f"مقدار فیلد «{field}» باید درست/نادرست باشد")
        cleaned[field] = value

    cleaned["responsive"] = _validate_shell_component_responsive(
        config.get("responsive"), FOOTER_RESPONSIVE_AWARE_KEYS,
    )

    try:
        cleaned["extra_blocks"] = _validate_footer_extra_blocks(config.get("extra_blocks"))
    except ShellBlockError as exc:
        raise FooterConfigValidationError(str(exc)) from exc

    try:
        cleaned["footer_variant"] = global_region_registry.validate_global_variant_selection(
            global_region_registry.GLOBAL_FOOTER_REGION, config.get("footer_variant"),
        )
        cleaned["mobile_nav_variant"] = global_region_registry.validate_global_variant_selection(
            global_region_registry.GLOBAL_MOBILE_NAV_REGION, config.get("mobile_nav_variant"),
        )
    except global_region_registry.UnknownGlobalVariantSelectionError as exc:
        raise FooterConfigValidationError(str(exc)) from exc

    if not any(cleaned[field] for field in FOOTER_TOGGLE_FIELDS):
        raise FooterConfigValidationError(
            "فوتر نمی‌تواند کاملاً خالی باشد — حداقل یکی از بخش‌های فوتر "
            "(درباره فروشگاه، تماس، لینک‌های مفید، دسته‌بندی‌ها، شبکه‌های اجتماعی، "
            "نشان‌های اعتماد، لوگوهای پرداخت، خبرنامه یا کپی‌رایت) باید فعال بماند."
        )
    return cleaned


def validate_appearance_config(config: dict) -> dict:
    """پیکربندی خامِ ظاهر (Template/Palette/Override/فونت/گردی/تراکم/حرکت)
    را اعتبارسنجی و پاک‌سازی می‌کند — دقیقاً همان الگویِ
    ``validate_header_config``: کلیدِ ناشناخته بی‌صدا حذف می‌شود، هر
    مقدار در برابرِ یک enum بسته/بازه‌ی معقول چک می‌شود.

    ``template_slug``/``palette_slug`` در برابرِ ``appearance_registry``
    (نه یک لیستِ رشته‌ایِ تکراری اینجا) چک می‌شوند — همان الگویی که
    ``StorefrontSection.section_key`` در برابرِ ``SECTION_REGISTRY`` چک
    می‌شود. ``palette_slug=None`` مجاز است (یعنی «بدونِ پالتِ نام‌دار،
    فقط رنگ‌هایِ دستی») — دقیقاً حالتِ فروشگاه‌هایی که هنوز به این سیستم
    مهاجرت نکرده‌اند."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.core.models import validate_hex_color

    if not isinstance(config, dict):
        raise AppearanceConfigValidationError("تنظیمات ظاهر باید یک شیء باشد")

    cleaned = dict(APPEARANCE_CONFIG_DEFAULTS)

    template_slug = config.get("template_slug", APPEARANCE_CONFIG_DEFAULTS["template_slug"])
    if appearance_registry.get_template(template_slug) is None:
        raise AppearanceConfigValidationError(f"قالبِ «{template_slug}» در دسترس نیست")
    cleaned["template_slug"] = template_slug

    palette_slug = config.get("palette_slug")
    if palette_slug is not None:
        if appearance_registry.get_palette(palette_slug) is None:
            raise AppearanceConfigValidationError(f"پالتِ «{palette_slug}» در دسترس نیست")
    cleaned["palette_slug"] = palette_slug

    raw_overrides = config.get("color_overrides") or {}
    if not isinstance(raw_overrides, dict):
        raise AppearanceConfigValidationError("رنگ‌های سفارشی باید یک شیء باشد")
    cleaned_overrides = {}
    for key, value in raw_overrides.items():
        if key not in APPEARANCE_COLOR_KEYS:
            continue
        if not isinstance(value, str):
            raise AppearanceConfigValidationError(f"رنگِ «{key}» نامعتبر است")
        try:
            validate_hex_color(value)
        except DjangoValidationError as exc:
            raise AppearanceConfigValidationError("; ".join(exc.messages)) from exc
        cleaned_overrides[key] = value
    cleaned["color_overrides"] = cleaned_overrides
    cleaned["color_overrides_customized"] = bool(config.get("color_overrides_customized", False))

    raw_theme_overrides = config.get("theme_overrides") or {}
    if not isinstance(raw_theme_overrides, dict):
        raise AppearanceConfigValidationError("رنگ‌های ناحیه‌ای سفارشی باید یک شیء باشد")
    cleaned_theme_overrides = {}
    for key, value in raw_theme_overrides.items():
        if key not in appearance_registry.THEME_ROLE_KEYS:
            continue
        if not isinstance(value, str):
            raise AppearanceConfigValidationError(f"رنگ ناحیه‌ای «{key}» نامعتبر است")
        try:
            validate_hex_color(value)
        except DjangoValidationError as exc:
            raise AppearanceConfigValidationError("; ".join(exc.messages)) from exc
        cleaned_theme_overrides[key] = value
    cleaned["theme_overrides"] = cleaned_theme_overrides

    font = config.get("font", APPEARANCE_CONFIG_DEFAULTS["font"])
    if font not in appearance_registry.FONT_CHOICES:
        raise AppearanceConfigValidationError("فونتِ انتخاب‌شده در فهرستِ فونت‌های مجاز نیست")
    cleaned["font"] = font

    for field, min_v, max_v in (("radius", 0, 32), ("button_radius", 0, 32)):
        try:
            value = int(config.get(field, APPEARANCE_CONFIG_DEFAULTS[field]))
        except (TypeError, ValueError):
            raise AppearanceConfigValidationError(f"مقدار «{field}» باید عدد باشد") from None
        cleaned[field] = max(min_v, min(max_v, value))

    density = config.get("density", APPEARANCE_CONFIG_DEFAULTS["density"])
    if density not in appearance_registry.DENSITY_CHOICES:
        raise AppearanceConfigValidationError("تراکمِ انتخاب‌شده نامعتبر است")
    cleaned["density"] = density

    motion = config.get("motion", APPEARANCE_CONFIG_DEFAULTS["motion"])
    if motion not in appearance_registry.MOTION_CHOICES:
        raise AppearanceConfigValidationError("سبکِ حرکتِ انتخاب‌شده نامعتبر است")
    cleaned["motion"] = motion

    type_scale = config.get("type_scale", APPEARANCE_CONFIG_DEFAULTS["type_scale"])
    if type_scale not in appearance_registry.TYPE_SCALE_CHOICES:
        raise AppearanceConfigValidationError("اندازه‌ی متنِ انتخاب‌شده نامعتبر است")
    cleaned["type_scale"] = type_scale

    button_style = config.get("button_style", APPEARANCE_CONFIG_DEFAULTS["button_style"])
    if button_style not in appearance_registry.BUTTON_STYLE_CHOICES:
        raise AppearanceConfigValidationError("سبکِ دکمه‌یِ انتخاب‌شده نامعتبر است")
    cleaned["button_style"] = button_style

    image_fit = config.get("image_fit", APPEARANCE_CONFIG_DEFAULTS["image_fit"])
    if image_fit not in appearance_registry.IMAGE_FIT_CHOICES:
        raise AppearanceConfigValidationError("نوعِ نمایشِ تصویرِ انتخاب‌شده نامعتبر است")
    cleaned["image_fit"] = image_fit

    image_hover = config.get("image_hover", APPEARANCE_CONFIG_DEFAULTS["image_hover"])
    if image_hover not in appearance_registry.IMAGE_HOVER_CHOICES:
        raise AppearanceConfigValidationError("افکتِ هاورِ تصویرِ انتخاب‌شده نامعتبر است")
    cleaned["image_hover"] = image_hover

    # رفعِ باگ — این دو کلید قبلاً هرگز از ``config`` ورودی خوانده
    # نمی‌شدند؛ خروجی همیشه فقط پیش‌فرضِ ``APPEARANCE_CONFIG_DEFAULTS``
    # (False/True) بود، حتی وقتی مرچنت صریحاً چک‌باکسِ مربوطه را در فرم
    # عوض می‌کرد — یعنی این دو تنظیم عملاً هرگز قابلِ تغییر نبودند.
    cleaned["card_image_crossfade"] = bool(config.get("card_image_crossfade", APPEARANCE_CONFIG_DEFAULTS["card_image_crossfade"]))
    cleaned["card_image_zoom"] = bool(config.get("card_image_zoom", APPEARANCE_CONFIG_DEFAULTS["card_image_zoom"]))

    # Phase 7: family_slug/preset_slug (سیستمِ منجمدِ قدیمیِ Family) از
    # اینجا و از APPEARANCE_CONFIG_DEFAULTS حذف شده‌اند — دیگر هیچ اثرِ
    # رندریِ فعالی نداشتند (نگاه کنید به Phase 7 Retirement Map). کلیدِ
    # باقی‌مانده‌یِ احتمالی در appearance_configِ ذخیره‌شده‌یِ قدیمی
    # بی‌صدا نادیده گرفته می‌شود (همان الگویِ «کلیدِ ناشناخته حذف
    # می‌شود» که این تابع همیشه داشته).
    layout_preset_key = config.get("layout_preset_key", APPEARANCE_CONFIG_DEFAULTS["layout_preset_key"])
    if layout_preset_key is not None and layout_preset_registry.get_layout_preset(layout_preset_key) is None:
        raise AppearanceConfigValidationError(f"پیش‌تنظیمِ «{layout_preset_key}» در دسترس نیست")
    cleaned["layout_preset_key"] = layout_preset_key

    if STORE_APPEARANCE_CONFIG_KEY in config:
        try:
            manifest = normalize_persisted_manifest(
                config[STORE_APPEARANCE_CONFIG_KEY]
            )
        except InvalidStoreAppearanceContract as exc:
            raise AppearanceConfigValidationError(
                "پیکربندی موتور طراحی فروشگاه نامعتبر است"
            ) from exc
        cleaned[STORE_APPEARANCE_CONFIG_KEY] = manifest_to_primitive(manifest)

    # Phase 8 P0-7 — این ۵ فیلدِ *ساختاری* قبلاً فقط از طریقِ انتخابِ یک
    # Template به‌طورِ غیرمستقیم قابلِ‌تغییر بودند (نگاه کنید به
    # appearance_registry.TemplateDefinition). حالا مستقیماً در پنلِ
    # «تنظیماتِ بیشتر» قابلِ‌ویرایش‌اند — عمداً *در APPEARANCE_CONFIG_DEFAULTS
    # نیستند* و فقط وقتی مقدارِ معتبر و غیرِخالی پست شده باشد در خروجی
    # ذخیره می‌شوند؛ غیابشان یعنی «هنوز صراحتاً تغییر نکرده» — در آن حالت
    # apps.core.context_processors هم‌چنان از Templateِ ذخیره‌شده (که
    # خودش دیگر توسطِ مرچنت از طریقِ UI عوض نمی‌شود، اما در دیتابیسِ
    # فروشگاه‌هایِ قدیمی‌تر ممکن است غیرِ «modern» باشد) به‌عنوانِ fallback
    # می‌خواند — یعنی صفر تغییرِ بصری برایِ فروشگاه‌هایی که این پنلِ جدید
    # را هرگز لمس نکرده‌اند.
    #
    # Phase 4 (Task 3C) — this exact sparse-by-design shape (absence means
    # "inherit", never a fabricated default) is why these 5 fields, and only
    # these 5, were chosen as the Page Appearance tier's allowed key set
    # (see PAGE_APPEARANCE_KEYS / validate_page_appearance_overrides below):
    # they are already architecturally distinct from the core brand-identity
    # tokens (colors/font/button_style/motion/type_scale) that
    # apps.core.context_processors._global_identity_version's own docstring
    # explicitly requires stay Store-global/never page-varying (a customer
    # must see the same brand on product-detail as on Home) — extracted into
    # a standalone helper so the page-scoped validator below reuses the
    # exact same per-field choice-set checks, never a second copy.
    _apply_structural_page_fields(config, cleaned)

    return cleaned


#: Phase 4 (Task 3C) — the Page Appearance tier's bounded, typed, sparse
#: override key set. Deliberately exactly these 5 pre-existing "structural,
#: non-identity" fields (see the comment above) — never colors/font/
#: button_style/motion/type_scale/palette_slug/template_slug, which must
#: stay Store-global per the explicit architecture decision in
#: apps.core.context_processors._global_identity_version.
PAGE_APPEARANCE_KEYS = frozenset({"content_width", "grid_density", "card_shadow", "card_hover", "hero_style"})


def _apply_structural_page_fields(config: dict, cleaned: dict) -> None:
    """Mutates ``cleaned`` in place with any of the 5 ``PAGE_APPEARANCE_KEYS``
    present (non-empty) in ``config`` — shared by ``validate_appearance_config``
    (Store-global, full-defaulted) and ``validate_page_appearance_overrides``
    (Page-scoped, sparse) so the exact same choice-set validation is never
    duplicated between the two tiers."""
    content_width = config.get("content_width")
    if content_width:
        try:
            content_width = int(content_width)
        except (TypeError, ValueError):
            raise AppearanceConfigValidationError("مقدارِ «عرضِ محتوایِ سایت» نامعتبر است") from None
        if content_width not in appearance_registry.SITE_CONTENT_WIDTH_CHOICES:
            raise AppearanceConfigValidationError("عرضِ محتوایِ سایتِ انتخاب‌شده نامعتبر است")
        cleaned["content_width"] = content_width

    grid_density = config.get("grid_density")
    if grid_density:
        try:
            grid_density = int(grid_density)
        except (TypeError, ValueError):
            raise AppearanceConfigValidationError("مقدارِ «تعدادِ ستونِ گریدِ محصول» نامعتبر است") from None
        if grid_density not in appearance_registry.SITE_GRID_DENSITY_CHOICES:
            raise AppearanceConfigValidationError("تعدادِ ستونِ گریدِ محصولِ انتخاب‌شده نامعتبر است")
        cleaned["grid_density"] = grid_density

    card_shadow = config.get("card_shadow")
    if card_shadow:
        if card_shadow not in appearance_registry.SITE_CARD_SHADOW_CHOICES:
            raise AppearanceConfigValidationError("سایه‌یِ کارتِ انتخاب‌شده نامعتبر است")
        cleaned["card_shadow"] = card_shadow

    card_hover = config.get("card_hover")
    if card_hover:
        if card_hover not in appearance_registry.SITE_CARD_HOVER_CHOICES:
            raise AppearanceConfigValidationError("هاورِ کارتِ انتخاب‌شده نامعتبر است")
        cleaned["card_hover"] = card_hover

    hero_style = config.get("hero_style")
    if hero_style:
        if hero_style not in appearance_registry.SITE_HERO_STYLE_CHOICES:
            raise AppearanceConfigValidationError("سبکِ هیرویِ انتخاب‌شده نامعتبر است")
        cleaned["hero_style"] = hero_style


def validate_page_appearance_overrides(raw: dict) -> dict:
    """Phase 4 (Task 3C) — the Page Appearance tier's own validator: a
    BOUNDED, TYPED, SPARSE override (never a fully-defaulted dict like
    ``validate_appearance_config`` produces) — only keys genuinely present
    in ``raw`` are validated and kept; everything else is absent, meaning
    "inherit from Store Global" (never a fabricated value). Unknown keys are
    silently dropped (the same "unknown key ignored" convention every other
    appearance validator in this module already uses)."""
    if not isinstance(raw, dict):
        raise AppearanceConfigValidationError("پیکربندیِ ظاهرِ صفحه باید یک شیء باشد")
    cleaned: dict = {}
    _apply_structural_page_fields(
        {key: value for key, value in raw.items() if key in PAGE_APPEARANCE_KEYS}, cleaned,
    )
    return cleaned


def get_or_create_layout(store) -> StorefrontLayout:
    return StorefrontLayout.provision_for(store)


def _next_version_number(layout: StorefrontLayout) -> int:
    last = layout.versions.order_by("-version_number").first()
    return (last.version_number + 1) if last else 1


#: نگاشتِ نوعِ رسانه‌یِ مقیّد به section → (نامِ related_name رویِ
#: StorefrontSection، لیستِ فیلدهایی که مستقیماً کپی می‌شوند بدونِ تغییرِ
#: معنا). ``asset`` فیلدهای FKِ اشاره‌گر به ``MediaAsset`` عمداً از این
#: لیست جدا نگه داشته شده‌اند (نگاه کنید به ``_ASSET_FK_FIELDS`` پایین) —
#: تصمیمِ مالک ۴/۵: کلون‌کردنِ Placement هرگز نباید Placementِ منبع (که
#: معمولاً به نسخه‌ی Published تعلق دارد) را تغییر دهد؛ فقط یک ردیفِ
#: **جدید** با همان اشاره‌گرِ MediaAsset ساخته می‌شود.
_SCOPED_MEDIA_MODELS = ("hero_slides", "banners", "story_items")

#: هر مدلِ Placement کدام فیلدهایِ FKِ اشاره‌گر به ``MediaAsset`` دارد —
#: این‌ها هم دقیقاً مثلِ بقیه‌ی فیلدها کپی می‌شوند (همان مقدارِ
#: asset_id، نه ساختنِ asset تازه) چون تصمیمِ مالک ۵ صریحاً می‌گوید
#: Placementِ کلون‌شده باید به **همان** ``MediaAsset`` اشاره کند، نه یک
#: کپیِ تازه از فایل.
_ASSET_FK_FIELDS = {
    "hero_slides": ("desktop_asset_id", "mobile_asset_id"),
    "banners": ("desktop_asset_id", "mobile_asset_id"),
    "story_items": ("image_asset_id",),
}

#: فیلدهایِ محتواییِ غیرِ FK هر مدلِ Placement — کپی می‌شوند دقیقاً همان‌طور
#: که هستند (بدونِ منطقِ خاص).
_PLACEMENT_CONTENT_FIELDS = {
    "hero_slides": (
        "title", "subtitle", "button_label", "show_button", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
    "banners": (
        "title", "description", "button_label", "show_button", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
    "story_items": (
        "title", "is_active", "display_order",
        "destination_type", "destination_category_id", "destination_product_id",
        "destination_brand_id", "destination_collection_id", "destination_external_url",
        "open_in_new_tab",
    ),
}


def _clone_section_scoped_media(source_section: StorefrontSection, target_section: StorefrontSection) -> None:
    """برایِ ``source_section`` (متعلق به نسخه‌ی منبع — معمولاً Published)،
    هر ردیفِ رسانه‌یِ section-scoped (``HeroSlide``/``PromotionalBanner``/
    ``StoryRailItem`` که ``section == source_section``) را روی
    ``target_section`` (بخشِ تازه‌کلون‌شده، متعلق به نسخه‌ی جدید) **کلون
    می‌کند** — یعنی یک ردیفِ کاملاً جدید می‌سازد، هرگز ردیفِ منبع را
    UPDATE یا MOVE نمی‌کند (تصمیمِ مالک ۴: «Published و Draft باید همزمان
    و مستقل قابل‌رندر باشند»).

    ردیفِ جدید دقیقاً همان فیلدهایِ FKِ MediaAsset را کپی می‌کند (همان
    asset_id — بدونِ ساختنِ asset تازه، بدونِ کپیِ بایتِ فایل؛ تصمیمِ
    مالک ۵) — پس اگر Placementِ منبع به یک ``MediaAsset`` مشترک اشاره
    می‌کند، Placementِ جدیدِ کلون‌شده هم به **همان** ردیفِ ``MediaAsset``
    اشاره می‌کند."""
    from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem

    model_by_related_name = {
        "hero_slides": HeroSlide, "banners": PromotionalBanner, "story_items": StoryRailItem,
    }
    for related_name in _SCOPED_MEDIA_MODELS:
        model = model_by_related_name[related_name]
        source_rows = getattr(source_section, related_name).all()
        clones = []
        for row in source_rows:
            kwargs = {"store_id": row.store_id, "section": target_section}
            for field in _PLACEMENT_CONTENT_FIELDS[related_name]:
                kwargs[field] = getattr(row, field)
            for field in _ASSET_FK_FIELDS[related_name]:
                kwargs[field] = getattr(row, field)
            # فیلدهایِ فایلِ legacy (desktop_image/mobile_image/image) عمداً
            # کپی نمی‌شوند — این کلون فقط برایِ Placementهایی معنا دارد که
            # از قبل به یک MediaAsset منتقل شده‌اند (نگاه کنید به
            # STOREFRONT_BUILDER_V2_PHASE_0_5_REPORT.md، محدودیت‌ها). یک
            # Placementِ section-scoped که هنوز asset FK ندارد (خیلی
            # قدیمی، از قبلِ Phase 0.5 و هرگز ازطریقِ فرمِ ویرایش لمس‌
            # نشده) در این کلون نادیده گرفته می‌شود — نه خطا، نه کرش؛ فقط
            # در نسخه‌ی جدید ظاهر نمی‌شود، دقیقاً همان رفتاری که پیش از
            # این Fix هم برایِ *همه‌ی* Placementهایِ section-scoped وجود
            # داشت (نگاه کنید به بخشِ «محدودیت‌های باقی‌مانده» در گزارش).
            has_any_asset = any(kwargs[f] for f in _ASSET_FK_FIELDS[related_name])
            if not has_any_asset:
                continue
            clones.append(model(**kwargs))
        if clones:
            model.objects.bulk_create(clones)


def _clone_version_content(source: StorefrontLayoutVersion | None, target: StorefrontLayoutVersion) -> None:
    """کپی هدر/فوتر/تمامِ صفحات/بخش‌های ``source`` روی ``target``.

    Phase 1A (تصمیمِ مالک ۲/۳/۵ — ارتقاءِ کلون از «فقط صفحه اصلی» به
    «همه‌یِ شش صفحه»):
    - ``target`` از قبل هر شش ``StorefrontPage`` را دارد (خودکار، از
      طریقِ ``StorefrontLayoutVersion.save()`` — نگاه کنید به
      ``models.py``) — این تابع فقط بخش‌هایِ **موجودِ** هر صفحه‌یِ منبع
      را رویِ صفحه‌یِ متناظرِ همان نوع در ``target`` کلون می‌کند؛ صفحاتی
      که هنوز هیچ بخشی ندارند (فعلاً همه‌یِ صفحات غیرِ صفحه‌اصلی، چون
      Builder UI هنوز فقط صفحه‌اصلی را ویرایش می‌کند) دقیقاً خالی
      می‌مانند — نه محتوایِ ساختگی.
    - هر ``StorefrontSection`` کلون‌شده ``stable_id`` را دقیقاً حفظ می‌کند
      (همان بخشِ منطقی است، فقط در نسخه‌ی دیگر) — نه یک UUID تازه.
    - برایِ هر بخشِ کلون‌شده، رسانه‌یِ section-scoped (HeroSlide/
      PromotionalBanner/StoryRailItem) هم کلون می‌شود — هرگز از بخشِ منبع
      حذف/جابه‌جا نمی‌شود، فقط یک ردیفِ جدید با همان ارجاعِ MediaAsset
      ساخته می‌شود. Placementِ منبع (که معمولاً به نسخه‌ی Published تعلق
      دارد) کاملاً دست‌نخورده می‌ماند — Phase 0.5's مدل رسانه بدونِ هیچ
      تغییری اینجا دوباره استفاده می‌شود (نه بازنویسی)."""
    if source is None:
        return
    target.header_config = dict(source.header_config or {})
    target.footer_config = dict(source.footer_config or {})
    target.appearance_config = dict(source.appearance_config or {})
    # Acceptance Batch 2 (post-U11) — a cloned version is, logically, the
    # exact same Ready Template baseline the source had (Published→Draft
    # bootstrap, Restore, or a pre-switch/pre-reset checkpoint clone) —
    # without copying these two, a Draft produced by any of those paths
    # would silently lose "which Template it's built from" and its
    # immutable baseline snapshot, breaking a later reset for no reason
    # a merchant caused.
    target.template_provenance = dict(source.template_provenance or {})
    target.template_baseline_snapshot = dict(source.template_baseline_snapshot or {})
    target.save(update_fields=[
        "header_config", "footer_config", "appearance_config",
        "template_provenance", "template_baseline_snapshot",
    ])

    target_pages_by_type = {p.page_type: p for p in target.pages.all()}
    for source_page in source.pages.all():
        target_page = target_pages_by_type.get(source_page.page_type)
        if target_page is None:
            # نباید هرگز رخ دهد — ``StorefrontLayoutVersion.save()`` همیشه
            # هر شش صفحه را می‌سازد — اما به‌جایِ کرش، defensive skip
            # (همان الگویِ section_key ناشناخته در render_service).
            continue

        # Phase 4 (Task 3C) — the Page Appearance tier must survive exactly
        # like header/footer/appearance_config above: a Draft spun off a
        # Published version (the normal post-publish "resume editing" flow)
        # must start from that version's actual effective state, not
        # silently drop a merchant's page-level override the moment they
        # publish and reopen the editor.
        if target_page.page_appearance_overrides != source_page.page_appearance_overrides:
            target_page.page_appearance_overrides = dict(source_page.page_appearance_overrides or {})
            target_page.save(update_fields=["page_appearance_overrides"])

        source_sections = list(source_page.sections.order_by("order", "id"))
        cloned_sections = [
            StorefrontSection(
                page=target_page, section_key=s.section_key, order=s.order,
                is_active=s.is_active, settings=dict(s.settings or {}),
                collapsed_in_editor=s.collapsed_in_editor,
                stable_id=s.stable_id,
                row_key=s.row_key, row_span=s.row_span,
                is_locked=s.is_locked,
                # Acceptance Batch 2 (post-U11) — the same logical section
                # keeps the same Template-baseline slot identity across a
                # clone (Published→Draft bootstrap, Restore, checkpoint);
                # only Duplicate (a genuinely new section) omits it.
                template_slot_key=s.template_slot_key,
            )
            for s in source_sections
        ]
        if cloned_sections:
            StorefrontSection.objects.bulk_create(cloned_sections)

        # stable_id is the only reliable logical mapping across versions.
        cloned_by_stable_id = {
            row.stable_id: row for row in target_page.sections.all()
        }
        for source_section in source_sections:
            target_section = cloned_by_stable_id.get(source_section.stable_id)
            if target_section is None:
                continue
            _clone_section_scoped_media(source_section, target_section)

        # Phase 3.0 — layout placement is cloned independently from content.
        # Empty Cells therefore survive Draft creation/Restore too.
        container_service.clone_page_containers(
            source_page, target_page, cloned_by_stable_id,
        )


@transaction.atomic
def get_or_create_draft(store, *, user=None) -> StorefrontLayoutVersion:
    """Draft فعلی فروشگاه را برمی‌گرداند؛ اگر وجود نداشته باشد، یکی می‌سازد.

    اگر این فروشگاه هرگز هیچ نسخه‌ای نداشته (نه Draft، نه منتشرشده، نه
    بایگانی‌شده) — یعنی اولین بار است که ویرایشگر باز می‌شود — Draft از
    محتوای صفحه اصلی قدیمی (hard-coded) همین فروشگاه بوت‌استرپ می‌شود
    (``bootstrap_service``) تا هرگز بومِ خالی نشان داده نشود. در غیر این
    صورت از روی نسخه‌ی منتشرشده‌ی فعلی کپی می‌شود — تا ویرایشگر همیشه از
    وضعیت فعلیِ زنده شروع شود.
    """
    layout = get_or_create_layout(store)
    if layout.draft_version_id:
        container_service.ensure_version_containers(layout.draft_version)
        return layout.draft_version

    enforce_rate_limit("storefront_layout.new_draft", str(store.pk), **_NEW_DRAFT_RATE_LIMIT)

    is_first_ever_version = not layout.versions.exists()
    draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=(
            StorefrontLayoutVersion.Source.LEGACY_BOOTSTRAP
            if is_first_ever_version else StorefrontLayoutVersion.Source.MANUAL
        ),
        created_by=user if (user and user.is_authenticated) else None,
    )
    if is_first_ever_version:
        from . import bootstrap_service
        bootstrap_service.apply_bootstrap_content(draft, store)
        container_service.ensure_version_containers(draft)
    else:
        _clone_version_content(layout.published_version, draft)
    layout.draft_version = draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return draft


@transaction.atomic
def discard_draft(store) -> None:
    """Draft فعلی را (اگر وجود دارد) حذف می‌کند — بدون اثر روی نسخه منتشرشده."""
    layout = get_or_create_layout(store)
    if not layout.draft_version_id:
        return
    draft = layout.draft_version
    layout.draft_version = None
    layout.save(update_fields=["draft_version", "updated_at"])
    draft.delete()


@transaction.atomic
def publish(store, *, user=None) -> StorefrontLayoutVersion:
    """Draft فعلی را منتشر می‌کند — عملیات اتمیک، فقط تعویض اشاره‌گر.

    نسخه‌ی منتشرشده‌ی قبلی (اگر وجود داشت) به ARCHIVED منتقل می‌شود؛
    Storefront عمومی از این لحظه به بعد نسخه جدید را می‌بیند.
    """
    enforce_rate_limit("storefront_layout.publish", str(store.pk), **_PUBLISH_RATE_LIMIT)

    layout = get_or_create_layout(store)
    draft = layout.draft_version
    if draft is None:
        raise NoDraftToPublishError("هیچ پیش‌نویسی برای انتشار وجود ندارد")

    # Phase 3.5A — publication boundary invariant.
    #
    # Container/Cell is the public layout source of truth. A Section that
    # belongs to a page but has no Cell must never silently disappear from the
    # published storefront. Older internal callers/importers may still create
    # StorefrontSection directly instead of going through the visual Builder.
    #
    # This helper is deliberately conservative: existing Containers and empty
    # Cells stay exactly as the merchant designed them; each genuinely
    # unplaced Section is appended in its own new single-column Container.
    container_service.ensure_version_containers(draft)

    # Undo/Redo is an editor-session concern and must never cross the publish
    # boundary or accumulate forever on immutable release versions.
    draft.edit_history_entries.all().delete()

    draft.content_fingerprint = draft.compute_fingerprint()
    draft.status = StorefrontLayoutVersion.Status.PUBLISHED
    draft.published_at = timezone.now()
    draft.save(update_fields=["content_fingerprint", "status", "published_at", "updated_at"])

    previous_published = layout.published_version
    if previous_published is not None:
        previous_published.status = StorefrontLayoutVersion.Status.ARCHIVED
        previous_published.save(update_fields=["status", "updated_at"])

    layout.published_version = draft
    layout.draft_version = None
    layout.uses_visual_storefront_layout = True
    layout.save(update_fields=["published_version", "draft_version", "uses_visual_storefront_layout", "updated_at"])
    return draft


def list_versions(store):
    """تاریخچه‌ی کامل نسخه‌ها (منتشرشده + بایگانی‌شده + پیش‌نویس فعلی، اگر باشد)."""
    layout = get_or_create_layout(store)
    return layout.versions.order_by("-version_number")


@transaction.atomic
def restore_version(store, version_id, *, user=None) -> StorefrontLayoutVersion:
    """محتوای یک نسخه‌ی قدیمی را در یک Draft **جدید** بازمی‌گرداند — هرگز
    مستقیماً منتشر نمی‌شود. اگر Draft فعلی از قبل وجود دارد، جایگزین می‌شود
    (تأیید/هشدار «تغییرات ذخیره‌نشده» مسئولیت لایه UI است، نه این سرویس)."""
    enforce_rate_limit("storefront_layout.restore", str(store.pk), **_RESTORE_RATE_LIMIT)

    layout = get_or_create_layout(store)
    try:
        source = layout.versions.get(pk=version_id)
    except StorefrontLayoutVersion.DoesNotExist:
        raise CrossStoreVersionError(f"نسخه {version_id} متعلق به این فروشگاه نیست") from None

    if layout.draft_version_id:
        old_draft = layout.draft_version
        layout.draft_version = None
        layout.save(update_fields=["draft_version", "updated_at"])
        old_draft.delete()

    new_draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=StorefrontLayoutVersion.Source.RESTORED,
        label=f"بازگردانی از نسخه {source.version_number}",
        created_by=user if (user and user.is_authenticated) else None,
    )
    _clone_version_content(source, new_draft)
    layout.draft_version = new_draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return new_draft


def _draft_has_any_content(draft: StorefrontLayoutVersion) -> bool:
    """Acceptance Batch 2 (post-U11)، تصحیحِ پستِ‌دمو hardening pass
    (Issue 5) — آیا این Draft محتوایِ «معنادارِ» واقعاً موجودی دارد؟

    نسخه‌ی قبلیِ این تابع فقط ``draft.sections.exists()`` را چک می‌کرد —
    خیلی ضعیف بود: یک Draftِ صفر-Section هنوز می‌تواند appearance_config/
    header_config/footer_config/پالت/منشأِ Ready Template را واقعاً
    تغییر داده باشد (مثلاً مرچنت فقط پالت یا هدر را عوض کرده، بدونِ
    دست‌زدن به هیچ Section)؛ نادیده گرفتنِ آن یعنی اعمالِ یک Presetِ دیگر
    آن تغییراتِ واقعی را بدونِ هیچ چک‌پوینتِ قابل‌بازیابی از بین می‌برد.

    سیاستِ درست: EMPTY + PRISTINE → چک‌پوینتِ زائد نمی‌خواهد. هرگونه
    تغییرِ واقعی در هرکدام از این محورهایِ سراسری (حتی بدونِ هیچ Section)
    → معنادار است و باید چک‌پوینت شود.

    نکته‌یِ ظریف #۱: ``header_config``/``footer_config``/``template_provenance``/
    ``template_baseline_snapshot`` واقعاً از ``{}`` شروع می‌شوند، اما
    ``appearance_config`` این‌طور نیست — ``bootstrap_service.bootstrap_appearance_config``
    از همان لحظه‌یِ ساختِ اولین Draft یک دیکشنریِ غیرِخالی (مثلاً
    ``{"palette_slug": None, "color_overrides": {}}``) در آن می‌نویسد — پس
    چکِ سادهٔ truthiness این فیلد را همیشه «معنادار» می‌دید، حتی برایِ
    Draftی که مرچنت هنوز هیچ تغییرِ ظاهریِ دستی‌ای نداده. به‌جایِ آن با
    ``APPEARANCE_CONFIG_DEFAULTS`` مقایسه می‌شود — فقط انحرافِ *واقعی* از
    پیش‌فرض‌ها معنادار است.

    نکته‌یِ ظریف #۲: ``color_overrides`` عمداً از این مقایسه مستثنا است.
    برایِ فروشگاهی که ``ShopSettings`` واقعاً provision شده،
    ``bootstrap_appearance_config`` رنگ‌هایِ *زنده‌یِ فعلیِ* آن فروشگاه را
    (نه یک پیش‌فرضِ خنثی) در همان لحظه‌یِ ساختِ اولین Draft داخلِ
    ``color_overrides`` کپی می‌کند — این یک انتخابِ صریحِ مرچنت در همین
    ادیتور نیست، صرفاً یک migration-safety carryover است، پس نباید به‌تنهایی
    یک Draftِ دست‌نخورده را «معنادار» نشان دهد. یک تغییرِ واقعیِ ظاهر همیشه
    حداقل یکی از کلیدهایِ دیگر (``palette_slug``، ``font``، ``density``، ...)
    را هم عوض می‌کند، پس این استثنا هیچ تغییرِ واقعی‌ای را پنهان نمی‌کند."""
    if draft.sections.exists():
        return True
    if draft.header_config or draft.footer_config or draft.template_provenance or draft.template_baseline_snapshot:
        return True
    return not _appearance_config_is_pristine(draft.appearance_config)


def _appearance_config_is_pristine(appearance_config: dict) -> bool:
    appearance_config = dict(appearance_config or {})

    # A5 persists the canonical typed manifest on every new Draft. That is a
    # platform default, not a merchant edit. A non-default (or malformed)
    # manifest is meaningful and must still be checkpointed before replacement.
    raw_manifest = appearance_config.pop(STORE_APPEARANCE_CONFIG_KEY, None)
    if raw_manifest is not None:
        try:
            manifest = normalize_persisted_manifest(raw_manifest)
        except InvalidStoreAppearanceContract:
            return False
        if manifest_to_primitive(manifest) != manifest_to_primitive(
            DEFAULT_STORE_APPEARANCE_MANIFEST
        ):
            return False

    if not set(appearance_config) <= set(APPEARANCE_CONFIG_DEFAULTS):
        return False
    return all(
        appearance_config.get(key, default) == default
        for key, default in APPEARANCE_CONFIG_DEFAULTS.items()
        if key not in ("color_overrides", "color_overrides_customized")
    )


@transaction.atomic
def checkpoint_draft_before_replacement(store, *, reason_label: str, user=None) -> StorefrontLayoutVersion:
    """Acceptance Batch 2 (post-U11) — پیش از یک جایگزینیِ مخربِ کلِ Draft
    یا یک صفحه‌یِ کامل (اعمالِ Ready Templateِ دیگر، بازنشانیِ کلِ فروشگاه،
    بازنشانیِ یک صفحه)، محتوایِ *فعلیِ* Draft را به‌عنوانِ یک چک‌پوینتِ
    قابل‌بازیابی در همان تاریخچه‌یِ نسخه‌هایِ موجود (``StorefrontLayoutVersion``)
    نگه می‌دارد — دقیقاً همان معماریِ ``restore_version`` (کلون + Draftِ
    جدید)، با یک تفاوتِ عمدی: به‌جایِ حذفِ کاملِ Draftِ قدیمی، آن را
    ``ARCHIVED`` می‌کند تا از طریقِ همان ``restore_version`` بعداً قابلِ
    بازگردانی بماند — هرگز یک سیستمِ تاریخچه‌ی موازیِ جدید نیست.

    اگر Draftِ فعلی هیچ محتوایِ معناداری نداشته باشد (نگاه کنید به
    ``_draft_has_any_content``)، هیچ چک‌پوینتی ساخته نمی‌شود و همان
    Draftِ فعلی بدونِ تغییر برگردانده می‌شود — «بدونِ تغییرِ معنادار،
    بدونِ چک‌پوینتِ زائد» (الزامِ صریحِ Batch 2).

    نسخه‌یِ برگشتی همیشه یک کلونِ **کاملِ** محتوایِ قبلی است (همه‌یِ شش
    صفحه، نه فقط صفحاتی که عملیاتِ بعدی ممکن است لمس کند) — پس فراخوان
    (مثلاً ``preset_service.apply_preset``) که فقط صفحاتِ پوشش‌داده‌شده
    توسطِ Presetِ جدید را بازنویسی می‌کند، صفحاتِ لمس‌نشده را دقیقاً
    همان‌طور که بودند حفظ می‌کند — نه خالی."""
    layout = get_or_create_layout(store)
    current_draft = get_or_create_draft(store, user=user)
    if not _draft_has_any_content(current_draft):
        return current_draft

    enforce_rate_limit("storefront_layout.new_draft", str(store.pk), **_NEW_DRAFT_RATE_LIMIT)
    new_draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=StorefrontLayoutVersion.Source.MANUAL,
        created_by=user if (user and user.is_authenticated) else None,
    )
    _clone_version_content(current_draft, new_draft)

    current_draft.status = StorefrontLayoutVersion.Status.ARCHIVED
    current_draft.label = reason_label[:150]
    current_draft.save(update_fields=["status", "label", "updated_at"])

    layout.draft_version = new_draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return new_draft


@transaction.atomic
def apply_industry_layout(store, industry_template, *, user=None, force: bool = False) -> StorefrontLayoutVersion:
    """چیدمان پیشنهادی یک صنف را در یک Draft **جدید** اعمال می‌کند — هرگز
    مستقیماً منتشر نمی‌شود (همان قانون ``restore_version``).

    اگر فروشگاه از قبل یک نسخه‌ی منتشرشده دارد (یعنی صاحب فروشگاه حداقل
    یک بار storefront بصری را منتشر کرده و ممکن است آن را سفارشی کرده
    باشد)، بدون ``force=True`` رد می‌شود — این دقیقاً همان تأیید صریحی است
    که تصمیم کاربر برای «هرگز رونویسی بی‌صدا» می‌خواهد؛ لایه‌ی View مسئول
    گرفتن تأیید از کاربر (checkbox/confirm) پیش از پاس‌دادن ``force=True``
    است. Draft فعلی (اگر وجود دارد) جایگزین می‌شود، دقیقاً مثل ``restore_version``."""
    enforce_rate_limit("storefront_layout.new_draft", str(store.pk), **_NEW_DRAFT_RATE_LIMIT)

    layout = get_or_create_layout(store)
    if layout.published_version_id and not force:
        raise StorefrontAlreadyPublishedError(
            "این فروشگاه از قبل یک نسخه‌ی منتشرشده دارد — برای اعمال چیدمان صنف، تأیید صریح لازم است"
        )

    if layout.draft_version_id:
        old_draft = layout.draft_version
        layout.draft_version = None
        layout.save(update_fields=["draft_version", "updated_at"])
        old_draft.delete()

    new_draft = StorefrontLayoutVersion.objects.create(
        layout=layout, version_number=_next_version_number(layout),
        status=StorefrontLayoutVersion.Status.DRAFT,
        source=StorefrontLayoutVersion.Source.INDUSTRY_TEMPLATE,
        label=f"چیدمان صنف «{industry_template.name}»",
        created_by=user if (user and user.is_authenticated) else None,
    )
    from . import bootstrap_service
    bootstrap_service.apply_industry_content(new_draft, store, industry_template)
    container_service.ensure_version_containers(new_draft)
    layout.draft_version = new_draft
    layout.save(update_fields=["draft_version", "updated_at"])
    return new_draft
