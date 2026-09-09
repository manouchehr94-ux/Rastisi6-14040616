"""Section Registry — allowlist سرور-محورِ انواع بخش قابل استفاده در سازنده بصری.

طبق بخش ۱۲ گزارش ممیزی (``docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md``):
این یک دیکشنری **ثابت پایتونی** است، نه دیتابیس — بارگذاری template همیشه از
همین نگاشت ثابت انجام می‌شود، هرگز از رشته‌ای که کاربر کنترل می‌کند. این
دقیقاً همان چیزی است که از موارد زیر جلوگیری می‌کند:

- بارگذاری template دلخواه (``template_name`` همیشه هارد‌کد همین‌جاست)
- import پویا/``eval`` بر اساس داده کاربر (هیچ‌کدام استفاده نمی‌شود)
- ثبت نوع section نامعتبر (``StorefrontSection.section_key`` همیشه در
  سرویس در برابر ``SECTION_REGISTRY`` چک می‌شود، نه صرفاً در دیتابیس)

هر ``SectionDefinition`` یک نوع settings schema (تابع اعتبارسنجی) دارد که
شکل JSON را چک می‌کند؛ اعتبارسنجی مالکیت Store برای ارجاعات (محصول/دسته/
برند/بنر) در ``services/section_data_service.py`` انجام می‌شود، نه اینجا.
"""

from __future__ import annotations

import dataclasses
from typing import Callable

from . import resource_source as resource_source_module
from .settings_schema import (
    VARIANT_EXPLICIT_OVERRIDE_KEY,
    SettingsField,
    SettingsSchema,
    validate_appearance_overrides,
)
from .variant_contract import VariantDefinition, validate_variant_selection, validate_variants

#: شش نوعِ صفحه — دقیقاً همان رشته‌های ``StorefrontPage.PageType.values``
#: (``apps/storefront_builder/models.py``)، اینجا به‌شکلِ ثابتِ رشته‌ای
#: تکرار شده‌اند تا این ماژول (طبقِ فلسفه‌یِ صریحِ خودش در docstring بالا:
#: «دیکشنری ثابت پایتونی»، بدونِ وابستگی به مدل/دیتابیس) به ``models.py``
#: وابسته نشود — هماهنگی با enum واقعی توسطِ
#: ``test_section_registry.py::PageTypeConstantsMatchModelTests`` تضمین
#: می‌شود، نه import مستقیم.
PAGE_TYPE_HOME = "home"
PAGE_TYPE_PRODUCT_DETAIL = "product_detail"
PAGE_TYPE_LISTING = "listing"
PAGE_TYPE_COLLECTION = "collection"
PAGE_TYPE_SEARCH = "search"
PAGE_TYPE_CART = "cart"
ALL_PAGE_TYPES: frozenset[str] = frozenset({
    PAGE_TYPE_HOME, PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_LISTING,
    PAGE_TYPE_COLLECTION, PAGE_TYPE_SEARCH, PAGE_TYPE_CART,
})


@dataclasses.dataclass(frozen=True)
class SectionDefinition:
    key: str
    label_fa: str
    icon: str
    template_name: str
    validate_settings: Callable[[dict], dict]
    default_settings: Callable[[], dict]
    min_instances: int = 0
    max_instances: int | None = None
    duplicable: bool = True
    removable: bool = True
    #: Phase 5: این نوع section روی کدام نوع(های) صفحه قابلِ افزودن است.
    #: پیش‌فرض یعنی «همه‌جا» — ۱۷ نوعِ محتواییِ عمومیِ موجود از پیش
    #: (hero/banner/rich_text/faq/...) بدونِ تغییرِ رفتار همین پیش‌فرض
    #: را نگه می‌دارند (طبقِ الزامِ صریحِ کار: «Home-only sections may be
    #: reusable where appropriate»). فقط انواعِ جدیدِ context-aware
    #: (``product_main``، ``cart_items``، ...) این را صریحاً به یک/دو
    #: نوعِ صفحه محدود می‌کنند.
    page_types: frozenset[str] = ALL_PAGE_TYPES
    #: آیا این نوع بخش تنظیمات قابل‌ویرایش (فرم) دارد؟ تا فازِ C فقط
    #: انواعی که واقعاً محتوای قابل‌تنظیم داشتند (rich_text، image_text،
    #: product_section) این پرچم را True داشتند. از فازِ D به بعد **همه‌ی**
    #: انواع True هستند — چون همه اکنون حداقل بلوکِ «تنظیماتِ نمایش در
    #: دستگاه‌ها» (``responsive``) را دارند؛ این پرچم دیگر توسطِ کدِ
    #: دستی در registry تنظیم نمی‌شود، بلکه توسطِ ``_finalize_registry``
    #: پایینِ همین فایل، یکنواخت روی True قرار می‌گیرد.
    has_settings_form: bool = False
    #: اگر True، این نوع در کتابخانه‌ی «افزودن بخش جدید» نمایش داده
    #: نمی‌شود (نمونه‌های موجود دست‌نخورده می‌مانند — رندر/تنظیمات/حذف
    #: کاملاً کار می‌کنند، فقط امکانِ ساختنِ نمونه‌ی *جدید* پنهان است).
    #: مورد استفاده: وقتی یک نوعِ دیگر (اینجا: تنظیماتِ نوارِ اعلانِ هدر)
    #: دقیقاً همان قابلیت را به‌شکلِ واقعاً قابل‌تنظیم پوشش می‌دهد — طبقِ
    #: الزامِ صریحِ کار «هرگز کنترلی که اثری ندارد نشان داده نشود».
    hidden_from_library: bool = False
    #: دسته‌بندیِ کسب‌وکاریِ کتابخانه‌ی «افزودن بخش جدید» (چکپوینتِ ۱۰) —
    #: پنج گروهِ ثابت (نگاه کنید به ``SECTION_LIBRARY_CATEGORIES``)، نه
    #: اصطلاحِ فنی/مدل. هر ورودی در ``_BASE_SECTION_REGISTRY`` صراحتاً
    #: مقدار می‌دهد — پیش‌فرض اینجا صرفاً محدودیتِ dataclass را دور می‌زند.
    category_fa: str = "محتوا"
    #: توضیح کوتاه و merchant-facing برای کارت Library.  اختیاری است تا
    #: Registry همچنان تنها منبع حقیقت نام/توضیح Block باقی بماند و Template
    #: مجبور به شرط‌های section-specific نشود.
    description_fa: str = ""

    # --------------------------------------------------- U1A metadata contract
    # همه‌ی فیلدهای زیر اضافیِ صرف‌اند — هیچ‌کدام هیچ رفتارِ رندر/اعتبارسنجیِ
    # موجود را عوض نمی‌کنند و هیچ‌کدام برایِ ۳۱ نوعِ باقی‌مانده (از ۳۴ نوعِ
    # SECTION_REGISTRY) نیاز به مقداردهی ندارند — پیش‌فرضِ خالی/None دقیقاً
    # هم‌ارزِ «این قابلیت هنوز برای این نوع اعلام نشده» است، نه یک تغییرِ
    # رفتار. نگاه کنید به ``variant_contract.py`` برای شکلِ کاملِ ``VariantDefinition``
    # و کمک‌تابع‌هایِ resolve.
    #: مجموعه‌یِ صریحِ capabilityهای این نوع section — در ``_finalize_registry``
    #: با نتیجه‌یِ استنتاج‌شده از allowlistهایِ فعلی (CARD_AWARE_SECTION_KEYS و...)
    #: یکی می‌شود (اجتماع، نه جایگزینی) — پس هیچ کدِ دستیِ اینجا لازم نیست فعلاً
    #: چیزی اعلام کند.
    capabilities: frozenset[str] = frozenset()
    #: دادهٔ لازمِ رندرِ این section (مثلاً «کوئری محصول»، «دسترسی به کالکشن») —
    #: طبقِ الزامِ کار، فعلاً برای هیچ‌کدام از ۳۴ نوعِ موجود مقداردهی نمی‌شود؛
    #: قرارداد فقط resolve/تست می‌شود.
    required_data: frozenset[str] = frozenset()
    #: اگر ``None``، یعنی «همه‌ی کلیدهایِ تنظیماتِ موجود پشتیبانی می‌شوند»
    #: (رفتارِ فعلیِ همه‌یِ ۳۴ نوع، بدونِ تغییر).
    supported_settings: frozenset[str] | None = None
    #: Variantهایِ ثبت‌شده‌یِ این section — تاپلِ خالی (پیش‌فرض) یعنی «این
    #: section هنوز هیچ Variantِ رسمی‌ای ندارد» (فallback امن، نگاه کنید به
    #: ``variant_contract.resolve_active_variant``). فقط سه نوعِ اثبات‌شده
    #: (``category_grid``/``brand_carousel``/``product_section``) در U1A این
    #: تاپل را پر می‌کنند — بدونِ تغییرِ ``validate_settings``/``default_settings``
    #: خودشان.
    variants: tuple[VariantDefinition, ...] = ()
    #: کلیدِ Variantِ پیش‌فرض — باید (اگر ``None`` نیست) به یکی از
    #: ``variants`` اشاره کند؛ ``_finalize_registry`` این را در زمانِ import
    #: چک می‌کند.
    default_variant: str | None = None
    #: کدام کلیدِ *موجودِ* ``settings`` انتخاب‌کننده‌یِ Variant است — طبقِ
    #: الزامِ صریحِ کارِ U1A: کلیدهایِ persisted شده‌یِ فعلی (مثلاً
    #: ``display_mode``) نباید به ``"variant"`` تغییرِ نام بدهند. ``None``
    #: یعنی (اگر روزی این section Variant پیدا کند) پیش‌فرض ``"variant"``
    #: خوانده می‌شود — نگاه کنید به ``variant_contract.resolve_active_variant``.
    variant_setting_key: str | None = None
    #: R4 Task 3 — اختیاریِ صرف: ``SettingsSchema`` اعلامیِ این section برایِ
    #: لایه‌ی Inspector جدید (``settings_schema.py``). ``None`` (پیش‌فرض،
    #: رفتارِ فعلیِ هر ۳۴ نوعِ موجود) یعنی «این section هنوز schema اعلام
    #: نکرده» — ``validate_settings``/``default_settings`` دستیِ موجود
    #: همچنان تنها مرجعِ معتبرسازی می‌مانند؛ Task 3 فقط زیرساخت را اضافه
    #: می‌کند، هیچ سکشنی را اینجا schema-enabled نمی‌کند.
    settings_schema: SettingsSchema | None = None

    def __post_init__(self) -> None:
        """External-review correction (U1A pre-commit pass, item 1) — same
        rationale as ``VariantDefinition.__post_init__``
        (``variant_contract.py``): ``frozen=True`` alone does not stop a
        caller passing a mutable ``set``/``list`` into a field this
        contract treats as immutable. Normalize at construction time via
        ``object.__setattr__`` — ``supported_settings=None`` is preserved
        exactly (never coerced away; see
        ``variant_contract.resolve_supported_settings``), every other
        collection field becomes a genuine ``frozenset``/``tuple``."""
        object.__setattr__(self, "capabilities", frozenset(self.capabilities or ()))
        object.__setattr__(self, "required_data", frozenset(self.required_data or ()))
        if self.supported_settings is not None:
            object.__setattr__(self, "supported_settings", frozenset(self.supported_settings))
        object.__setattr__(self, "variants", tuple(self.variants or ()))

    def supports_capability(self, name: str, *, variant: "VariantDefinition | None" = None) -> bool:
        """U1B2 — the single query editor/server-side gating code should use
        instead of importing and checking membership in one of the
        module-level ``*_AWARE_SECTION_KEYS`` frozensets directly. Backed by
        ``self.capabilities``, which ``_finalize_registry`` already derives
        from those exact frozensets (see ``_derived_capabilities``) — so
        this is provably the same answer, just asked through the
        authoritative metadata contract instead of a raw constant import.

        ``variant`` is optional: pass the section's currently active
        ``VariantDefinition`` (e.g. from ``variant_contract.resolve_active_variant``)
        to check the *effective* capability set (section capabilities
        unioned with that variant's own) — matches
        ``variant_contract.resolve_capabilities``'s semantics exactly. Every
        current production variant declares no capabilities of its own, so
        passing a real variant today never changes the answer versus
        omitting it; the parameter exists so future variant-specific
        capability differences do not require a second query method.

        Current production editor gating (``views.py``) and server-side
        settings validation (this module's ``_with_*`` wrappers) both call
        this method without ``variant``, i.e. they gate on base
        ``SectionDefinition`` capabilities only — variant-specific
        capabilities are supported by this metadata API but must not be
        introduced into production ``VariantDefinition``s until
        variant-aware editor and validation gating is implemented (see
        ``tests.test_u1b2_capability_metadata_wiring.NoProductionVariantDeclaresCapabilitiesTests``)."""
        if variant is not None:
            return name in (self.capabilities | variant.capabilities)
        return name in self.capabilities


def _passthrough_dict(raw: dict) -> dict:
    """اعتبارسنجی placeholder — با اعتبارسنجی دقیق در چکپوینت‌های بعدی جایگزین می‌شود."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    return raw


def _empty_defaults() -> dict:
    return {}


_MAX_RICH_TEXT_LENGTH = 20_000
_MAX_IMAGE_TEXT_TITLE_LENGTH = 200


def _validate_rich_text_settings(raw: dict) -> dict:
    """``body_html`` — خودِ رشته در سرویس ذخیره می‌شود؛ پاک‌سازیِ HTML واقعی
    در زمان رندر توسط ``sanitize_rich_text`` (همان ساینیتایزر allowlist
    توضیحات کالا) انجام می‌شود، نه اینجا — اینجا فقط شکل/طول ورودی چک
    می‌شود."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    body_html = str(raw.get("body_html", ""))
    if len(body_html) > _MAX_RICH_TEXT_LENGTH:
        raise ValueError(f"متن نباید بیشتر از {_MAX_RICH_TEXT_LENGTH} نویسه باشد")
    return {"body_html": body_html}


#: R4 Task 4 — the declarative counterpart of ``_validate_rich_text_settings``
#: above, for the new Inspector layer only. ``_validate_rich_text_settings``
#: remains the authoritative post-validation step (see
#: ``settings_schema.clean_section_schema_patch``); this schema exists only
#: to describe the same single field declaratively.
RICH_TEXT_SCHEMA = SettingsSchema(fields=(
    SettingsField(
        key="body_html",
        label="متن",
        field_type="rich_text",
        group="basic",
        default="",
        max_length=_MAX_RICH_TEXT_LENGTH,
        widget_hint="merchant_rich_text",
    ),
))


#: منابع مجازِ داده‌یِ بخشِ محصول (فاز C) — enum بسته؛ هر مقدارِ دیگر رد
#: می‌شود. این تنها لیستِ مجاز در کل کدبیس است — مصرف‌کننده‌ها (فرم
#: ادیتور، ``section_data_service``) باید همین ثابت را import کنند، نه
#: رشته را جای دیگری تکرار کنند.
PRODUCT_SECTION_DATA_SOURCES = (
    "collection", "category", "brand", "manual",
    "newest", "discounted", "best_sellers", "most_viewed",
)
#: منابعی که به یک شیءِ واحدِ دیگر (کالکشن/دسته/برند) ارجاع می‌دهند —
#: این‌ها به ``source_id`` نیاز دارند.
_SINGLE_REFERENCE_SOURCES = {"collection", "category", "brand"}

PRODUCT_SECTION_DISPLAY_MODES = ("carousel", "grid", "campaign_band")

_PRODUCT_SECTION_MIN_LIMIT = 2
_PRODUCT_SECTION_MAX_LIMIT = 24
_PRODUCT_SECTION_DEFAULT_LIMIT = 8
_MAX_PRODUCT_SECTION_TITLE_LENGTH = 60
_MAX_PRODUCT_SECTION_SUBTITLE_LENGTH = 150
#: سقفِ تعدادِ کالای دستی — به‌قدرِ کافی بزرگ‌تر از بیشینه‌یِ item_limit
#: تا مرچنت بتواند بیش از حدِ نمایش، کالا انتخاب کند (مثلاً برایِ چرخشِ
#: بعدی)، اما نه نامحدود.
_MAX_MANUAL_PRODUCT_IDS = 60


class ProductSectionSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ بخشِ محصول نامعتبر است (فقط اعتبارسنجیِ شکل/enum/
    بازه — مالکیتِ Store برایِ ``source_id``/``product_ids`` در
    ``services/section_data_service.py`` چک می‌شود، نه اینجا)."""


def _clean_positive_int_list(raw_list, *, max_len: int, error_cls=None, error_message: str | None = None) -> list[int]:
    """دِدوپ + پاک‌سازیِ یک فهرستِ شناسه (کالای دستی/دسته‌بندی/برند) —
    ترتیبِ ورودی حفظ می‌شود (ترتیبِ انتخابِ مرچنت، نه ترتیبِ دیتابیس)."""
    error_cls = error_cls or ProductSectionSettingsError
    if not isinstance(raw_list, list):
        raise error_cls(error_message or "فهرستِ شناسه‌ها باید یک آرایه باشد")
    cleaned: list[int] = []
    seen = set()
    for value in raw_list:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            raise error_cls(error_message or "شناسه نامعتبر است") from None
        if int_value <= 0 or int_value in seen:
            continue
        seen.add(int_value)
        cleaned.append(int_value)
    return cleaned[:max_len]


def _validate_product_section_settings(raw: dict) -> dict:
    """قراردادِ تنظیماتِ «بخشِ محصول» (فازِ C) — تنها اعتبارسنجیِ شکل/
    enum/بازه‌یِ ایمن؛ هیچ کوئریِ دیتابیس/چکِ مالکیتِ Store اینجا انجام
    نمی‌شود (طبقِ همان تفکیکِ مسئولیتی که مستندسازیِ بالایِ فایل توصیف
    می‌کند). خروجی همیشه دقیقاً همین ۸ کلید را دارد — کلیدِ ناشناخته‌یِ
    ورودی بی‌صدا حذف می‌شود."""
    if not isinstance(raw, dict):
        raise ProductSectionSettingsError("تنظیمات باید یک شیء JSON باشد")

    data_source = raw.get("data_source")
    if data_source not in PRODUCT_SECTION_DATA_SOURCES:
        raise ProductSectionSettingsError("منبعِ داده‌یِ انتخاب‌شده نامعتبر است")

    display_mode = raw.get("display_mode")
    if display_mode not in PRODUCT_SECTION_DISPLAY_MODES:
        display_mode = "carousel"

    try:
        item_limit = int(raw.get("item_limit", _PRODUCT_SECTION_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        raise ProductSectionSettingsError("تعدادِ کالا باید عدد باشد") from None
    item_limit = max(_PRODUCT_SECTION_MIN_LIMIT, min(_PRODUCT_SECTION_MAX_LIMIT, item_limit))

    show_view_all = raw.get("show_view_all", True)
    if not isinstance(show_view_all, bool):
        show_view_all = bool(show_view_all)

    title = str(raw.get("title", "")).strip()[:_MAX_PRODUCT_SECTION_TITLE_LENGTH]
    subtitle = str(raw.get("subtitle", "")).strip()[:_MAX_PRODUCT_SECTION_SUBTITLE_LENGTH]

    # رفتارِ کاروسل کاملاً عمومی و data-driven است.  پیش‌فرض خاموش می‌ماند
    # تا sectionهای قدیمی دقیقاً همان اسکرول افقی قبلی را حفظ کنند؛ preset
    # یا merchant می‌تواند برای هر product_section مستقل آن را روشن کند.
    carousel_autoplay = raw.get("carousel_autoplay", False)
    if not isinstance(carousel_autoplay, bool):
        carousel_autoplay = bool(carousel_autoplay)
    carousel_show_arrows = raw.get("carousel_show_arrows", True)
    if not isinstance(carousel_show_arrows, bool):
        carousel_show_arrows = bool(carousel_show_arrows)
    try:
        carousel_interval_ms = int(raw.get("carousel_interval_ms", 3500))
    except (TypeError, ValueError):
        raise ProductSectionSettingsError("فاصله‌ی پخش خودکار باید عدد باشد") from None
    carousel_interval_ms = max(2000, min(10000, carousel_interval_ms))

    header_position = raw.get("header_position", "above")
    if header_position not in ("above", "inside"):
        header_position = "above"

    # source_id/product_ids فقط برایِ منبعِ متناظرشان معنا دارند — برایِ
    # بقیه همیشه به مقدارِ خنثی (None/[]) بازنشانی می‌شوند تا تنظیماتِ
    # ذخیره‌شده هرگز حاویِ ارجاعِ یتیمِ بی‌ربط به data_source فعلی نباشد.
    source_id = None
    if data_source in _SINGLE_REFERENCE_SOURCES:
        raw_source_id = raw.get("source_id")
        try:
            source_id = int(raw_source_id)
        except (TypeError, ValueError):
            raise ProductSectionSettingsError("مقصدِ انتخاب‌شده نامعتبر است") from None
        if source_id <= 0:
            raise ProductSectionSettingsError("مقصدِ انتخاب‌شده نامعتبر است")

    product_ids: list[int] = []
    if data_source == "manual":
        product_ids = _clean_positive_int_list(raw.get("product_ids", []), max_len=_MAX_MANUAL_PRODUCT_IDS)
        if not product_ids:
            raise ProductSectionSettingsError("برایِ «کالاهایِ دستی» باید حداقل یک کالا انتخاب شود")

    return {
        "data_source": data_source,
        "source_id": source_id,
        "product_ids": product_ids,
        "item_limit": item_limit,
        "display_mode": display_mode,
        "show_view_all": show_view_all,
        "title": title,
        "subtitle": subtitle,
        "carousel_autoplay": carousel_autoplay,
        "carousel_interval_ms": carousel_interval_ms,
        "carousel_show_arrows": carousel_show_arrows,
        "header_position": header_position,
    }


def _product_section_defaults() -> dict:
    return {
        "data_source": "newest",
        "source_id": None,
        "product_ids": [],
        "item_limit": _PRODUCT_SECTION_DEFAULT_LIMIT,
        "display_mode": "carousel",
        "show_view_all": True,
        "title": "",
        "subtitle": "",
        "carousel_autoplay": False,
        "carousel_interval_ms": 3500,
        "carousel_show_arrows": True,
        "header_position": "above",
    }


#: R4 Task 9 — the declarative Inspector-facing schema for "بخش محصولات".
#: ``source`` is the ONE typed ``resource_source`` field; ``product_ids``/
#: ``source_id``/``data_source`` are deliberately NOT schema-registered —
#: they are compatibility persistence details hidden behind ``source`` (see
#: ``_with_resource_source`` below). Labels reuse the section's own
#: registered variant labels for ``display_mode`` for consistency.
PRODUCT_SECTION_SCHEMA = SettingsSchema(fields=(
    SettingsField(
        "title", "عنوان بخش", "text", "basic",
        default="", max_length=_MAX_PRODUCT_SECTION_TITLE_LENGTH,
    ),
    SettingsField(
        "source", "منبع محصولات", "resource_source", "basic",
        default=resource_source_module.serialize_resource_source(
            resource_source_module.ResourceSource(kind="product", mode="auto", auto_rule="newest"),
        ),
    ),
    SettingsField(
        "item_limit", "تعداد کالا", "integer", "basic",
        default=_PRODUCT_SECTION_DEFAULT_LIMIT,
        min_value=_PRODUCT_SECTION_MIN_LIMIT, max_value=_PRODUCT_SECTION_MAX_LIMIT,
    ),
    SettingsField(
        "display_mode", "نوع نمایش", "choice", "basic", default="carousel",
        choices=(
            ("carousel", "کاروسل"),
            ("grid", "گرید"),
            ("campaign_band", "نوار کمپینی کنار محصولات"),
        ),
    ),
    SettingsField("show_view_all", "نمایش دکمه «مشاهده همه»", "boolean", "basic", default=True),
    SettingsField(
        "subtitle", "زیرعنوان", "text", "advanced",
        default="", max_length=_MAX_PRODUCT_SECTION_SUBTITLE_LENGTH,
    ),
    SettingsField("carousel_autoplay", "پخش خودکار کاروسل", "boolean", "advanced", default=False),
    SettingsField(
        "carousel_interval_ms", "فاصله پخش خودکار (میلی‌ثانیه)", "integer", "advanced",
        default=3500, min_value=2000, max_value=10000,
    ),
    SettingsField("carousel_show_arrows", "نمایش فلش‌های کاروسل", "boolean", "advanced", default=True),
    SettingsField(
        "header_position", "جایگاه عنوان", "choice", "advanced", default="above",
        choices=(("above", "بالای بخش"), ("inside", "داخل بخش")),
    ),
))


class CatalogProductWallSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ ``catalog_product_wall`` نامعتبر است — پیامِ
    فارسیِ قابل‌نمایشِ مستقیم به تاجر."""


#: Site-target-overhaul Part 2D — generic, ID-free multi-row merchandising
#: wall. Part 2C's own product rows were capped at the 4 ID-free
#: ``product_section`` data sources (newest/discounted/best_sellers/
#: most_viewed) because "category"/"collection" data sources require a
#: real per-Store numeric ``source_id`` (see ``_SINGLE_REFERENCE_SOURCES``
#: above) that a generic, reusable Ready Template preset cannot safely
#: hardcode without leaking one Store's IDs into every other merchant's
#: copy of that Template. This section closes that gap the correct way:
#: it never stores an ID at all — at RENDER time (``render_service.
#: _catalog_product_wall_context``) it resolves whichever categories/
#: collections the CURRENT Store actually has (the exact same
#: ``Category.objects.filter(store=store, parent__isnull=True,
#: is_active=True)`` auto-pick ``category_grid`` already uses when its own
#: ``category_ids`` is empty), and renders one compact product row per
#: real group it finds — genuinely Store-agnostic, safe for ANY merchant
#: who applies a Ready Template that selects this section.
CATALOG_PRODUCT_WALL_SOURCE_MODES = ("visible_categories", "visible_collections", "categories_then_collections")
# Generic structural presentations for the Store-resolved product wall.
# ``rows`` preserves the Part 2D renderer byte-for-byte; ``group_columns``
# and ``featured_row`` are reusable retail compositions introduced by the
# laleRokh family, selected by settings rather than by Ready Template key.
CATALOG_PRODUCT_WALL_LAYOUT_MODES = ("rows", "group_columns", "featured_row")

_CATALOG_PRODUCT_WALL_MIN_GROUPS = 1
_CATALOG_PRODUCT_WALL_MAX_GROUPS = 12
_CATALOG_PRODUCT_WALL_DEFAULT_GROUPS = 6

_CATALOG_PRODUCT_WALL_MIN_PER_GROUP = 2
_CATALOG_PRODUCT_WALL_MAX_PER_GROUP = 24
_CATALOG_PRODUCT_WALL_DEFAULT_PER_GROUP = 10

_CATALOG_PRODUCT_WALL_MIN_MINIMUM_PRODUCTS = 1
_CATALOG_PRODUCT_WALL_MAX_MINIMUM_PRODUCTS = 12
_CATALOG_PRODUCT_WALL_DEFAULT_MINIMUM_PRODUCTS = 3


def _validate_catalog_product_wall_settings(raw: dict) -> dict:
    """چکپوینتِ Part 2D — بلوکِ خودِ این section (منابعِ ``card``/
    ``responsive`` را لایه‌یِ عمومیِ ``_with_card``/``_with_responsive``
    در ``_finalize_registry`` جدا اضافه می‌کند، دقیقاً همان الگویِ
    ``product_section``). هیچ ``source_id``ای اینجا وجود ندارد — این
    خودِ نکته‌یِ اصلیِ معماری است؛ منابع همیشه در زمانِ رندر، از رویِ
    Storeِ واقعیِ جاری resolve می‌شوند."""
    if not isinstance(raw, dict):
        raise CatalogProductWallSettingsError("تنظیمات باید یک شیء JSON باشد")

    source_mode = raw.get("source_mode")
    if source_mode not in CATALOG_PRODUCT_WALL_SOURCE_MODES:
        source_mode = "categories_then_collections"

    layout_mode = raw.get("layout_mode")
    if layout_mode not in CATALOG_PRODUCT_WALL_LAYOUT_MODES:
        layout_mode = "rows"
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]

    def _clamped_int(key, default, lo, hi, error_message):
        try:
            value = int(raw.get(key, default))
        except (TypeError, ValueError):
            raise CatalogProductWallSettingsError(error_message) from None
        return max(lo, min(hi, value))

    max_groups = _clamped_int(
        "max_groups", _CATALOG_PRODUCT_WALL_DEFAULT_GROUPS,
        _CATALOG_PRODUCT_WALL_MIN_GROUPS, _CATALOG_PRODUCT_WALL_MAX_GROUPS,
        "تعدادِ گروه باید عدد باشد",
    )
    products_per_group = _clamped_int(
        "products_per_group", _CATALOG_PRODUCT_WALL_DEFAULT_PER_GROUP,
        _CATALOG_PRODUCT_WALL_MIN_PER_GROUP, _CATALOG_PRODUCT_WALL_MAX_PER_GROUP,
        "تعدادِ کالا در هر گروه باید عدد باشد",
    )
    minimum_products = _clamped_int(
        "minimum_products", _CATALOG_PRODUCT_WALL_DEFAULT_MINIMUM_PRODUCTS,
        _CATALOG_PRODUCT_WALL_MIN_MINIMUM_PRODUCTS, _CATALOG_PRODUCT_WALL_MAX_MINIMUM_PRODUCTS,
        "حداقلِ کالای هر گروه باید عدد باشد",
    )

    skip_empty_groups = raw.get("skip_empty_groups", True)
    if not isinstance(skip_empty_groups, bool):
        skip_empty_groups = bool(skip_empty_groups)
    show_view_all = raw.get("show_view_all", True)
    if not isinstance(show_view_all, bool):
        show_view_all = bool(show_view_all)

    return {
        "source_mode": source_mode,
        "layout_mode": layout_mode,
        "title": title,
        "max_groups": max_groups,
        "products_per_group": products_per_group,
        "skip_empty_groups": skip_empty_groups,
        "minimum_products": minimum_products,
        "show_view_all": show_view_all,
    }


def default_catalog_product_wall_settings() -> dict:
    return _validate_catalog_product_wall_settings({})


#: انواعی که «ستون» به‌عنوان مفهوم قراردادی/دیتایی معنا دارد — تعدادِ
#: ستون برایِ این‌ها اعتبارسنجی و ذخیره می‌شود (قراردادِ عمداً
#: آینده‌نگر و عمومی، طبقِ بخشِ ۵ مشخصاتِ فیکسِ فازِ D: «Keep the
#: responsive contract generic internally for future expansion»).
#: **این ثابت هرگز مستقیماً برایِ تصمیمِ نمایش/عدم‌نمایشِ کنترلِ UI
#: استفاده نشود** — سه نوعِ باقی‌مانده‌یِ ``category_grid``/
#: ``promo_cards``/``brand_carousel`` مقدار را ذخیره می‌کنند اما
#: چیدمانِ ثابتِ فعلی‌شان (tiles/auto-fill) اصلاً آن را در رندر
#: نمی‌خواند — نمایشِ کنترل به تاجر برایِ این سه نوع صرفاً گمراه‌کننده
#: است (تغییرِ عدد هیچ اثرِ بصری‌ای ندارد). برایِ آن تصمیم از
#: ``COLUMN_VISUAL_SECTION_KEYS`` پایین استفاده کنید.
COLUMN_AWARE_SECTION_KEYS = frozenset({
    "product_section", "category_grid", "multi_banner", "promo_cards", "brand_carousel",
    "featured_products", "newest_products", "best_sellers", "discounted_products",
    "related_products", "product_listing", "collection_products",
    # Site-target-overhaul Part 2D — ``catalog_product_wall``'s per-group
    # rows reuse the exact same ``.pcarousel.rsec-cols`` column-count
    # mechanism ``product_section`` already uses.
    "catalog_product_wall",
})

#: زیرمجموعه‌یِ ``COLUMN_AWARE_SECTION_KEYS`` که تغییرِ تعدادِ ستون
#: واقعاً چیدمانِ رندرشده را عوض می‌کند (فیکسِ فازِ D، پس از گزارشِ
#: تستِ دستیِ کاربر روی Brand Carousel: تغییرِ ستونِ موبایل هیچ اثرِ
#: بصری‌ای نداشت). فقط همین مجموعه باید کنترلِ «تعدادِ ستون‌ها» را در
#: فرمِ تنظیماتِ ادیتور نشان دهد — نه ``COLUMN_AWARE_SECTION_KEYS``ی
#: بالا. ``product_section`` از قبل یک grid/carousel پارامتری دارد
#: (``.rsec-cols`` در ``product_card.css``)؛ ``multi_banner`` در Phase 3
#: (کتابخانه‌ی بلوک‌هایِ صفحه‌ی اصلی — بستنِ شکافِ «Two-Banner Row»/
#: «Multi-Banner Grid») به همین مجموعه اضافه شد و از همان کلاسِ
#: ``.grid.rsec-cols``یِ موجود استفاده می‌کند (کدِ CSSِ تازه‌ای نساخته
#: شد). وقتی چیدمانِ ``category_grid``/``promo_cards``/``brand_carousel``
#: هم در آینده بازطراحی شد، همان کلید را از ``COLUMN_AWARE_SECTION_KEYS``
#: به اینجا هم منتقل کنید.
#: Phase 8 P0-2 — این ۶ نوعِ دیگر هم اکنون از همان کلاسِ ``.grid.rsec-cols``
#: استفاده می‌کنند (templateهایِ مربوطه به‌روزرسانی شدند)، پس دیگر
#: «گمراه‌کننده» نیستند — تعدادِ ستونِ انتخابیِ تاجر واقعاً چیدمانِ
#: رندرشده را تغییر می‌دهد.
COLUMN_VISUAL_SECTION_KEYS = frozenset({
    "product_section", "multi_banner", "featured_products", "newest_products",
    "best_sellers", "discounted_products", "related_products", "collection_products",
    "product_listing",
    # Part 2D — same reason as COLUMN_AWARE_SECTION_KEYS above.
    "catalog_product_wall",
})

#: مقادیرِ مجازِ enum بستهٔ تعدادِ ستون به‌ازای هر دستگاه — طبقِ بخشِ ۴
#: مشخصات؛ هیچ عددِ دلخواهی پذیرفته نمی‌شود.
MOBILE_COLUMN_CHOICES = (1, 2)
TABLET_COLUMN_CHOICES = (1, 2, 3)
DESKTOP_COLUMN_CHOICES = (1, 2, 3, 4, 5, 6)

_DEFAULT_MOBILE_COLUMNS = 2
_DEFAULT_TABLET_COLUMNS = 3
_DEFAULT_DESKTOP_COLUMNS = 4


class ResponsiveSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``responsive`` نامعتبر است — پیامِ فارسیِ
    قابل‌نمایشِ مستقیم به تاجر."""


def _closed_column_choice(raw_value, choices: tuple[int, ...], *, default: int, field_label: str) -> int:
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise ResponsiveSettingsError(f"تعدادِ ستونِ «{field_label}» نامعتبر است") from None
    if value not in choices:
        raise ResponsiveSettingsError(f"تعدادِ ستونِ «{field_label}» باید یکی از مقادیرِ مجاز باشد")
    return value


def validate_responsive_settings(raw, *, supports_columns: bool) -> dict:
    """قراردادِ مشترکِ «تنظیماتِ نمایش در دستگاه‌ها» — یک بار نوشته شده و
    توسطِ همه‌یِ ۱۷ نوعِ section (نه فقط ``product_section``) استفاده
    می‌شود (بخشِ ۶ مشخصات: «Use one shared helper where possible»).

    غایب بودنِ کلیدِ ``responsive`` (سکشن‌هایِ از‌قبل‌موجود که هرگز از
    این فرم عبور نکرده‌اند) دقیقاً هم‌ارزِ خروجیِ پیش‌فرضِ این تابع
    است — یعنی «نمایان در همه‌یِ دستگاه‌ها»، رفتارِ فعلیِ بدونِ تغییر.
    کلیدِ ناشناخته بی‌صدا حذف می‌شود (همان قراردادِ
    ``layout_service.validate_header_config``/``validate_footer_config``)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ResponsiveSettingsError("تنظیماتِ نمایش در دستگاه‌ها باید یک شیء باشد")

    cleaned = {
        "hide_on_desktop": bool(raw.get("hide_on_desktop", False)),
        "hide_on_tablet": bool(raw.get("hide_on_tablet", False)),
        "hide_on_mobile": bool(raw.get("hide_on_mobile", False)),
    }
    if supports_columns:
        cleaned["desktop_columns"] = _closed_column_choice(
            raw.get("desktop_columns"), DESKTOP_COLUMN_CHOICES, default=_DEFAULT_DESKTOP_COLUMNS, field_label="دسکتاپ",
        )
        cleaned["tablet_columns"] = _closed_column_choice(
            raw.get("tablet_columns"), TABLET_COLUMN_CHOICES, default=_DEFAULT_TABLET_COLUMNS, field_label="تبلت",
        )
        cleaned["mobile_columns"] = _closed_column_choice(
            raw.get("mobile_columns"), MOBILE_COLUMN_CHOICES, default=_DEFAULT_MOBILE_COLUMNS, field_label="موبایل",
        )
    return cleaned


def default_responsive_settings(*, supports_columns: bool) -> dict:
    """پیش‌فرضِ بلوکِ ``responsive`` — دقیقاً معادلِ عبور از
    ``validate_responsive_settings(None, ...)`` (نمایان همه‌جا، ستونِ
    پیش‌فرض)، جدا نوشته شده فقط تا ``default_settings`` نیازی به
    اعتبارسنجیِ یک دیکشنریِ خالی نداشته باشد."""
    return validate_responsive_settings(None, supports_columns=supports_columns)


def _with_responsive(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``responsive`` می‌پوشاند — منطقِ خودِ نوع (rich_text/image_text/
    product_section/passthrough) کاملاً دست‌نخورده و بی‌خبر از این پوشش
    باقی می‌ماند؛ کلیدِ ``responsive`` قبل از رسیدن به تابعِ اصلی جدا
    می‌شود و بعد از آن دوباره به نتیجه اضافه می‌شود."""
    supports_columns = section_key in COLUMN_AWARE_SECTION_KEYS

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            # اجازه بده تابعِ اصلیِ همان نوع خطایِ تایپ‌شده‌یِ خودش را
            # برایِ ورودیِ غیر-dict پرتاب کند (مثلاً ProductSectionSettingsError)
            # — این wrapper یک نوعِ خطایِ عمومی‌تر را جایگزینِ آن نمی‌کند.
            return validate_fn(raw)
        responsive_raw = raw.get("responsive")
        base_raw = {k: v for k, v in raw.items() if k != "responsive"}
        cleaned = validate_fn(base_raw)
        cleaned["responsive"] = validate_responsive_settings(responsive_raw, supports_columns=supports_columns)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "responsive": default_responsive_settings(supports_columns=supports_columns)}

    return wrapped_validate, wrapped_default


#: انواعی که یک بلوکِ «لینک/مقصد» استاندارد (چکپوینتِ استانداردسازیِ لینک)
#: در تنظیماتشان دارند — معادلِ JSON-شکلِ ``apps.content.models.DestinationMixin``
#: برایِ محتوایِ ذخیره‌شده در ``StorefrontSection.settings`` (نه یک ردیفِ
#: مدلِ جدا). عمداً مثلِ ``COLUMN_AWARE_SECTION_KEYS`` یک allowlist صریح
#: است، نه پیش‌فرضِ همه‌ی انواع — چون بعضی انواع (rich_text، trust_features)
#: اصلاً معنایِ «لینکِ سطحِ section» ندارند، و بعضیِ دیگر (hero_banner،
#: single_banner/multi_banner) لینکشان per-slide/per-banner است، نه
#: per-section (نگاه کنید به مدلِ ``HeroSlide``/``PromotionalBanner`` که
#: خودشان از قبل ``DestinationMixin`` واقعی دارند). برایِ ``product_section``
#: این بلوک معنایِ «override دستیِ لینکِ "مشاهده همه"» را دارد؛ برایِ
#: ``image_text`` معنایِ «لینکِ تصویر/دکمه» را دارد.
DESTINATION_AWARE_SECTION_KEYS = frozenset({"image_text", "product_section", "brand_carousel"})

_DEFAULT_DESTINATION_SETTINGS = {
    "destination_type": "none",
    "destination_id": None,
    "destination_external_url": "",
    "open_in_new_tab": False,
}


class DestinationSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``destination`` نامعتبر است — پیامِ فارسیِ
    قابل‌نمایشِ مستقیم به تاجر."""


def validate_destination_settings(raw) -> dict:
    """قراردادِ مشترکِ «لینک/مقصد» — معادلِ JSON بلوکِ ``DestinationMixin``
    برایِ تنظیماتِ یک section (نه یک ردیفِ مدلِ جدا). فقط شکل/enum را چک
    می‌کند — مالکیتِ Store برایِ ``destination_id`` (دسته/محصول/برند/کالکشن)
    عمداً اینجا چک نمی‌شود، دقیقاً همان تفکیکِ مسئولیتی که
    ``_validate_product_section_settings`` برایِ ``source_id`` دارد؛ چکِ
    واقعی در ``apps.content.services.resolve_destination_setting`` انجام
    می‌شود.

    غایب بودنِ کلیدِ ``destination`` (سکشن‌هایِ از‌قبل‌موجود که هرگز از این
    فرم عبور نکرده‌اند) دقیقاً هم‌ارزِ «بدون مقصد» است."""
    from apps.content.models import DestinationType, validate_external_url
    from django.core.exceptions import ValidationError as DjangoValidationError

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise DestinationSettingsError("تنظیماتِ لینک باید یک شیء باشد")

    valid_types = {choice.value for choice in DestinationType}
    dtype = raw.get("destination_type") or "none"
    if dtype not in valid_types:
        raise DestinationSettingsError("نوع مقصدِ انتخاب‌شده نامعتبر است")

    cleaned = dict(_DEFAULT_DESTINATION_SETTINGS)
    cleaned["destination_type"] = dtype
    cleaned["open_in_new_tab"] = bool(raw.get("open_in_new_tab", False))

    if dtype in ("category", "product", "brand", "collection"):
        try:
            destination_id = int(raw.get("destination_id"))
        except (TypeError, ValueError):
            raise DestinationSettingsError("مقصدِ انتخاب‌شده نامعتبر است") from None
        if destination_id <= 0:
            raise DestinationSettingsError("مقصدِ انتخاب‌شده نامعتبر است")
        cleaned["destination_id"] = destination_id
    elif dtype == "external":
        external_url = str(raw.get("destination_external_url", "")).strip()
        try:
            validate_external_url(external_url)
        except DjangoValidationError as exc:
            raise DestinationSettingsError("; ".join(exc.messages)) from exc
        cleaned["destination_external_url"] = external_url

    return cleaned


def default_destination_settings() -> dict:
    return dict(_DEFAULT_DESTINATION_SETTINGS)


#: R4 Task 9 — sections whose Basic schema exposes a typed ``source``
#: (resource_source) field. ``settings_schema.clean_section_schema_patch``
#: already schema-cleans ``source`` into the generic typed shape (see
#: settings_schema.py's ``_clean_field_value``), but that cleaned key would
#: otherwise be silently DROPPED by the legacy validator — no existing
#: wrapper here knows about it. This wrapper is deliberately the
#: INNERMOST one (applied directly to the raw validator, before
#: destination/responsive/motion/card/layout/background/spacing/...) so
#: every outer wrapper's own key-stripping still runs on a dict that
#: already carries only legacy-shaped keys.
_RESOURCE_SOURCE_AWARE_SECTION_KEYS = frozenset({
    "product_section", "brand_carousel", "collection_tiles", "category_grid",
})


def _with_resource_source(section_key: str, validate_fn, default_fn):
    if section_key not in _RESOURCE_SOURCE_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    # The existing section-specific error class each wrapped section already
    # raises for an invalid raw settings shape — reused here so an invalid
    # typed ``source`` surfaces through the exact same error contract as
    # every other invalid field on that section (never a new/different
    # exception type the caller has to additionally handle). Looked up
    # lazily (inside the function body, not at module scope) because
    # ``BrandCarouselSettingsError`` is declared further down this file,
    # after this function — this call only ever happens from
    # ``_finalize_registry`` at the bottom of the module, by which point
    # every class below is already defined.
    error_cls = {
        "product_section": ProductSectionSettingsError,
        "brand_carousel": BrandCarouselSettingsError,
        "collection_tiles": CollectionTilesSettingsError,
        "category_grid": CategoryGridSettingsError,
    }[section_key]

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict) or "source" not in raw:
            # No "source" key present — preserve current legacy behaviour
            # exactly (including whatever data_source/source_id/product_ids
            # or brand_ids the raw payload already carries).
            return validate_fn(raw)

        source_raw = raw["source"]
        base_raw = {key: value for key, value in raw.items() if key != "source"}
        try:
            typed_source = resource_source_module.deserialize_resource_source(source_raw)
            legacy_patch = resource_source_module.resource_source_to_legacy_patch(section_key, typed_source)
        except resource_source_module.ResourceSourceError as exc:
            raise error_cls(str(exc)) from exc

        # The typed source is the merchant's INTENT for this patch — it must
        # win over any stale legacy keys still sitting in ``base_raw`` from
        # the section's previous persisted settings.
        merged_raw = {**base_raw, **legacy_patch}
        return validate_fn(merged_raw)

    # default_fn is intentionally NOT wrapped: the default settings shape
    # must remain exactly legacy-shaped (data_source/source_id/product_ids
    # or brand_ids) — it must never begin persisting a "source" key.
    return wrapped_validate, default_fn


def _with_destination(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``destination`` می‌پوشاند — فقط برایِ کلیدهایِ
    ``DESTINATION_AWARE_SECTION_KEYS``. دقیقاً همان الگویِ ``_with_responsive``
    بالا: منطقِ خودِ نوع کاملاً دست‌نخورده می‌ماند."""
    if section_key not in DESTINATION_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        destination_raw = raw.get("destination")
        base_raw = {k: v for k, v in raw.items() if k != "destination"}
        cleaned = validate_fn(base_raw)
        cleaned["destination"] = validate_destination_settings(destination_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "destination": default_destination_settings()}

    return wrapped_validate, wrapped_default


#: Phase 8 P0-2 — انواعی که واقعاً کارتِ محصول رندر می‌کنند (مستقیم یا از
#: طریقِ ``product_grid.html``) — تنها اینجا بلوکِ ``card`` معنا دارد.
#: عمداً یک allowlist صریح، دقیقاً همان الگویِ بالا (بقیه‌یِ انواع مثلِ
#: rich_text/hero_banner اصلاً کارتِ محصول ندارند).
CARD_AWARE_SECTION_KEYS = frozenset({
    "product_section", "featured_products", "newest_products", "best_sellers",
    "discounted_products", "amazing_offers", "related_products", "product_listing",
    "collection_products",
    # Part 2D — ``catalog_product_wall``'s per-group rows render real
    # product cards via the same ``product_grid.html`` partial.
    "catalog_product_wall",
})

#: enum بستهٔ نسبتِ تصویرِ کارتِ محصول — طبقِ اصلِ «۴-۵ انتخابِ معنادار
#: به‌جایِ عددِ دلخواهِ CSS» (نه aspect-ratio خام).
IMAGE_RATIO_CHOICES = ("square", "portrait", "landscape")

#: Phase 8 P1 — نحوه‌ی نمایانِ دکمه‌ی «افزودنِ سریع». ``hover_slide``
#: دقیقاً رفتارِ فعلیِ از‌پیش‌موجود است (پیش‌فرض، بدونِ تغییرِ بصری برایِ
#: کارت‌هایِ موجود)؛ ``hover_fade``/``always`` گزینه‌هایِ تازه‌اند.
QUICK_ADD_REVEAL_CHOICES = ("hover_slide", "hover_fade", "always")

#: Generic visual treatment for a product card.  This is intentionally a
#: closed, reusable presentation choice -- never a preset/store-specific
#: renderer selector.  ``standard`` preserves the historical card, while
#: ``compact`` is the denser marketplace treatment used by product-heavy
#: storefronts. ``fashion_sale`` is a reusable apparel/campaign treatment
#: (taller portrait image, prominent discount ribbon, two-line title,
#: compare-price hierarchy) -- any future fashion-leaning Ready Template
#: may adopt it, not just the one that introduces it. ``beauty_retail`` is
#: the equivalent commerce-forward cosmetics/perfume treatment: contained
#: product media plus an always-visible, business-rule-aware bottom action.
CARD_STYLE_CHOICES = (
    "standard", "compact", "minimal", "fashion_sale", "beauty_retail",
    "chocolate_retail", "retail_list", "luxury_dark",
    # A8 presentation-only vocabulary.  Every value is consumed by the one
    # shared product-card partial; none is a renderer or template selector.
    "marketplace_price", "editorial_minimal", "retail_row", "soft_capsule", "beauty_glass",
    "paper_frame", "price_first", "portrait_round", "catalog_index",
    "shipping_label", "shelf_editorial", "technical_spec", "tech_neon",
    "bold_outline",
)

BADGE_TREATMENT_CHOICES = ("none", "sale")

_CARD_TOGGLE_FIELDS = (
    "show_brand", "show_price", "show_badge", "show_wishlist",
    "show_quick_add", "show_rating", "card_border",
)


class CardSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``card`` نامعتبر است — پیامِ فارسیِ قابل‌نمایشِ مستقیم به تاجر."""


def validate_card_settings(raw) -> dict:
    """قراردادِ مشترکِ «نمایشِ کارتِ محصول» — غیابِ کلیدِ ``card`` (سکشن‌هایِ
    از‌قبل‌موجود) دقیقاً هم‌ارزِ همه‌چیز-نمایان/نسبتِ مربعی است — رفتارِ
    فعلیِ بدونِ تغییر، بدونِ Migration."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise CardSettingsError("تنظیماتِ کارتِ محصول باید یک شیء باشد")

    cleaned = {field: bool(raw.get(field, True)) for field in _CARD_TOGGLE_FIELDS}
    ratio = raw.get("image_ratio")
    cleaned["image_ratio"] = ratio if ratio in IMAGE_RATIO_CHOICES else "square"
    reveal = raw.get("quick_add_reveal")
    cleaned["quick_add_reveal"] = reveal if reveal in QUICK_ADD_REVEAL_CHOICES else "hover_slide"
    style = raw.get("card_style")
    cleaned["card_style"] = style if style in CARD_STYLE_CHOICES else "standard"
    return cleaned


def default_card_settings() -> dict:
    return validate_card_settings(None)


def _with_card(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``card`` می‌پوشاند — فقط برایِ ``CARD_AWARE_SECTION_KEYS``. دقیقاً
    همان الگویِ ``_with_responsive``/``_with_destination``/``_with_motion``."""
    if section_key not in CARD_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        card_raw = raw.get("card")
        base_raw = {k: v for k, v in raw.items() if k != "card"}
        cleaned = validate_fn(base_raw)
        cleaned["card"] = validate_card_settings(card_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "card": default_card_settings()}

    return wrapped_validate, wrapped_default


#: Phase 1 (معماریِ Universal Block/Data، بخشِ ۹ مشخصات: «Background
#: System» + بخشِ ۱۰.۲: «Custom Color Overrides») — انواعی که یک پس‌زمینه‌یِ
#: مستقل از پالتِ سراسری برایشان معنا دارد. یک allowlist صریح (همان الگویِ
#: بالا)، نه پیش‌فرضِ همه‌ی انواع — عمداً پنج نوعِ context-aware با
#: ``removable=False`` (``product_main``/``product_listing``/``cart_items``/
#: ``cart_summary``/``collection_products`` — محافظت‌شده طبقِ بخشِ ۵۹ مشخصات:
#: «Mandatory Components») و ``announcement_bar`` (نوارِ باریکِ سراسریِ هدر،
#: پس‌زمینه‌یِ مستقل برایش بی‌معناست) کنار گذاشته شده‌اند.
BACKGROUND_AWARE_SECTION_KEYS = frozenset({
    "hero_banner", "image_slider", "single_banner", "multi_banner", "category_grid",
    "featured_products", "newest_products", "best_sellers", "discounted_products",
    "amazing_offers", "brand_carousel", "promo_cards", "rich_text", "image_text",
    "product_section", "catalog_product_wall", "trust_features", "collection_tiles", "quick_links", "faq",
    "testimonials", "video_section", "story_rail", "newsletter",
    "product_description", "product_video", "related_products", "collection_header",
})

#: همان allowlist برایِ «فاصله‌گذاری» (بخشِ ۸ مشخصات) — دقیقاً همان مجموعه،
#: چون هر دو معنایِ «این section چطور در صفحه جا می‌گیرد» دارند، نه محتوایِ
#: خودِ section.
SPACING_AWARE_SECTION_KEYS = BACKGROUND_AWARE_SECTION_KEYS

BACKGROUND_MODE_CHOICES = ("theme", "palette", "palette_pattern", "color", "image", "pattern")
BACKGROUND_PALETTE_ROLE_CHOICES = ("tone-1", "tone-2", "tone-3", "tone-4", "tone-5")

#: G2.3 (Defect C) — وقتی مرچنت «رنگ از پالت» را انتخاب می‌کند اما نقشِ
#: پالت (فیلدِ همراه) خالی/ارسال‌نشده است، به‌جایِ «سقوطِ بی‌صدا به theme»
#: (باگِ «هیچ تغییری دیده نمی‌شد») از نقشِ پیش‌فرضِ ``tone-1`` استفاده
#: می‌شود — همان گزینه‌یِ اولِ selectِ UI، و چون به پالتِ سایت گره خورده
#: هرگز خارج از هویتِ رنگیِ فروشگاه دیده نمی‌شود.
#:
#: برایِ «رنگ دلخواه» عمداً هیچ پیش‌فرضِ رنگِ ثابتی گذاشته نمی‌شود: mode
#: حفظ می‌شود ولی رنگ خالی می‌ماند تا مرچنت خودش انتخاب کند (wrapper بدونِ
#: رنگ چیزی رنگ نمی‌زند) — پیش‌فرض‌کردنِ یک هگزِ ثابت می‌توانست یک
#: پس‌زمینه‌ی ناخواسته/خارج از پالت رنگ بزند. ورودیِ **صریحاً نامعتبر**
#: (نقشِ ناشناخته مثل tone-99 یا هگزِ بدشکل) همچنان امن رد/بازگردانده می‌شود.
BACKGROUND_DEFAULT_PALETTE_ROLE = "tone-1"

#: بخشِ ۹ مشخصات: Patternها دارایی‌هایِ قابل‌استفادهٔ مجددِ سیستم‌اند، نه
#: CSS سفارشیِ یک preset.  V3 اولین مجموعهٔ واقعی را اضافه می‌کند؛ رندر از
#: همان data-pattern عمومیِ wrapper استفاده می‌کند و هیچ renderer/preset
#: خاصی از این اسلاگ‌ها خبر ندارد.
PATTERN_REGISTRY: dict[str, str] = {
    # Pattern identity describes geometry only.  Colour remains an independent
    # section setting so the same reusable system pattern works with any
    # palette or per-block colour override.
    "commerce-doodle": "الگوی تجاری خطی",
}

class BackgroundSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``background`` نامعتبر است — پیامِ فارسیِ قابل‌نمایشِ
    مستقیم به تاجر."""


def validate_background_settings(raw) -> dict:
    """قراردادِ مشترکِ «پس‌زمینه» — بخشِ ۹ مشخصات (رنگ/تصویر/الگو) + بخشِ
    ۱۰.۲ («○ Use Theme Color / ● Custom Color»، اینجا ``mode="theme"`` در
    برابرِ ``mode="color"``). غیابِ کلیدِ ``background`` (sectionهایِ
    از‌قبل‌موجود) دقیقاً هم‌ارزِ ``mode="theme"`` است — رفتارِ فعلی، بدونِ
    تغییر، بدونِ نیاز به Migration دادهٔ JSON.

    Phase 1 correction — تصمیمِ ایمنیِ مستأجر (tenant safety): برایِ
    ``mode="image"`` این تابع یک URL دلخواهِ ذخیره‌شده توسطِ مرچنت را
    قبول/اعتبارسنجی **نمی‌کند**. ذخیره‌ی مستقیمِ یک رشته‌ی URL در تنظیماتِ
    section، مستقل از هرگونه بررسیِ مالکیتِ Store، دقیقاً همان الگویِ
    ناامنی است که این کدبیس همه‌جایِ دیگر آگاهانه رد کرده (نگاه کنید به
    ``source_id``/``destination_id``/``category_ids``/... که همه فقط یک
    شناسه‌ی عدد صحیح ذخیره می‌کنند، نه یک URL خام). به‌جایِ آن، فقط
    ``media_asset_id`` (اشاره‌گر به یک ``apps.content.models.MediaAsset``
    موجود) ذخیره می‌شود — دقیقاً همان قراردادِ «فقط شکل/enum اینجا، مالکیتِ
    Store در لایه‌ی سرویس» که این فایل برایِ بقیه‌ی ارجاعات دارد؛ حلِ
    واقعیِ آن (آیا این ID واقعاً متعلق به همین Store است؟ URLِ نهاییِ
    قابلِ‌رندر چیست؟) در ``apps.content.services.resolve_background_media_url``
    انجام می‌شود — همان محلی که ``resolve_destination_setting`` قبلاً
    همین نقش را برایِ بلوکِ ``destination`` بازی می‌کند. هنوز هیچ
    Media Picker UIای برایِ انتخابِ یک asset موجود ساخته نشده (طبقِ
    محدودیتِ صریحِ کار: بدونِ overbuild) — یعنی این mode امروز از طریقِ
    Builder UI قابلِ‌تنظیم نیست، دقیقاً مثلِ ``mode="pattern"`` (رجیستریِ
    خالی)، اما قرارداد از هم‌اکنون ایمن/آماده است."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from apps.core.models import validate_hex_color

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise BackgroundSettingsError("تنظیماتِ پس‌زمینه باید یک شیء باشد")

    mode = raw.get("mode")
    if mode not in BACKGROUND_MODE_CHOICES:
        mode = "theme"

    palette_role = ""
    if mode in ("palette", "palette_pattern"):
        palette_role = str(raw.get("palette_role", "")).strip()
        # G2.3 (Defect C): یک انتخابِ معتبرِ «رنگ از پالت» نباید فقط به این
        # دلیل که فیلدِ همراه (نقشِ پالت) خالی/ارسال‌نشده است بی‌صدا به
        # theme سقوط کند — پیش‌فرضِ tone-1 (همان گزینه‌یِ اولِ selectِ UI)
        # استفاده می‌شود تا انتخابِ مرچنت محترم بماند. اما یک نقشِ
        # **صریحاً نامعتبر** (مثلِ tone-99) همچنان امن رد و به theme
        # بازگردانده می‌شود (ایمنیِ ورودیِ نامعتبر).
        if not palette_role:
            palette_role = BACKGROUND_DEFAULT_PALETTE_ROLE
        elif palette_role not in BACKGROUND_PALETTE_ROLE_CHOICES:
            mode = "theme"
            palette_role = ""

    color = ""
    if mode in ("color", "pattern"):
        color = str(raw.get("color", "")).strip()
        if color:
            try:
                validate_hex_color(color)
            except DjangoValidationError as exc:
                raise BackgroundSettingsError("; ".join(exc.messages)) from exc
        # G2.3 (Defect C): «رنگ دلخواه»یِ معتبر با فیلدِ رنگِ خالی، mode را
        # حفظ می‌کند (نه سقوطِ بی‌صدا به theme — همان باگِ «هیچ تغییری دیده
        # نمی‌شد») ولی رنگ را خالی نگه می‌دارد. wrapper فقط وقتی
        # ``background-color`` می‌نویسد که ``mode == "color" and color`` باشد،
        # پس رنگِ خالی هیچ پس‌زمینه‌ی ناخواسته‌ای (مثلاً یک قرمزِ ثابت) رنگ
        # نمی‌زند — انتخابِ mode به‌خاطر سپرده می‌شود تا مرچنت رنگ را انتخاب
        # کند. رنگِ **بدشکل** همچنان بالاتر ``BackgroundSettingsError`` می‌دهد.

    media_asset_id = None
    if mode == "image":
        raw_id = raw.get("media_asset_id")
        if raw_id is None:
            mode = "theme"  # هیچ asset‌ای انتخاب نشده — چیزی برای نمایش نیست
        else:
            try:
                media_asset_id = int(raw_id)
            except (TypeError, ValueError):
                raise BackgroundSettingsError("رسانه‌ی انتخاب‌شده نامعتبر است") from None
            if media_asset_id <= 0:
                raise BackgroundSettingsError("رسانه‌ی انتخاب‌شده نامعتبر است")

    pattern_slug = ""
    if mode in ("pattern", "palette_pattern"):
        candidate = str(raw.get("pattern_slug", "")).strip()
        # فقط اسلاگ‌هایِ ثبت‌شدهٔ سیستم پذیرفته می‌شوند؛ مقدار ناشناخته مثل
        # سایر enumهای بصری بی‌صدا به theme برمی‌گردد.
        if candidate in PATTERN_REGISTRY:
            pattern_slug = candidate
        else:
            mode = "theme"

    return {
        "mode": mode, "color": color, "media_asset_id": media_asset_id,
        "pattern_slug": pattern_slug, "palette_role": palette_role,
    }


def default_background_settings() -> dict:
    return {
        "mode": "theme", "color": "", "media_asset_id": None,
        "pattern_slug": "", "palette_role": "",
    }


def _with_background(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``background`` می‌پوشاند — فقط برایِ ``BACKGROUND_AWARE_SECTION_KEYS``.
    دقیقاً همان الگویِ ``_with_card``/``_with_layout`` بالا."""
    if section_key not in BACKGROUND_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        background_raw = raw.get("background")
        base_raw = {k: v for k, v in raw.items() if k != "background"}
        cleaned = validate_fn(base_raw)
        cleaned["background"] = validate_background_settings(background_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "background": default_background_settings()}

    return wrapped_validate, wrapped_default


#: بخشِ ۸ مشخصات: «Basic Mode: Small/Normal/Large» + «Advanced Mode: Padding
#: Top/Bottom, Margin Top/Bottom». enum بستهٔ حالتِ ساده — Advanced اختیاری
#: و فقط اگر تاجر صریحاً واردش شود مقدار می‌گیرد (``None`` یعنی «از حالتِ
#: ساده مشتق کن»، تفسیرِ عددیِ دقیق در Phase 2/CSS انجام می‌شود، نه اینجا).
SPACING_SIZE_CHOICES = ("small", "normal", "large")
_SPACING_ADVANCED_FIELDS = ("padding_top", "padding_bottom", "margin_top", "margin_bottom")
_MAX_SPACING_PX = 200


class SpacingSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``spacing`` نامعتبر است — پیامِ فارسیِ قابل‌نمایشِ
    مستقیم به تاجر."""


def validate_spacing_settings(raw) -> dict:
    """قراردادِ مشترکِ «فاصله‌گذاریِ عمودی» — غیابِ کلیدِ ``spacing``
    (sectionهایِ از‌قبل‌موجود) دقیقاً هم‌ارزِ ``vertical_spacing="normal"``
    و بدونِ override پیشرفته است — رفتارِ فعلی، بدونِ تغییر."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SpacingSettingsError("تنظیماتِ فاصله‌گذاری باید یک شیء باشد")

    size = raw.get("vertical_spacing")
    if size not in SPACING_SIZE_CHOICES:
        size = "normal"

    raw_advanced = raw.get("advanced")
    if raw_advanced is not None and not isinstance(raw_advanced, dict):
        raise SpacingSettingsError("تنظیماتِ پیشرفته‌یِ فاصله‌گذاری باید یک شیء باشد")
    raw_advanced = raw_advanced or {}

    advanced = {}
    for field in _SPACING_ADVANCED_FIELDS:
        value = raw_advanced.get(field)
        if value is None:
            advanced[field] = None
            continue
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            raise SpacingSettingsError(f"مقدارِ «{field}» باید عدد باشد") from None
        advanced[field] = max(0, min(_MAX_SPACING_PX, int_value))

    return {"vertical_spacing": size, "advanced": advanced}


def default_spacing_settings() -> dict:
    return {"vertical_spacing": "normal", "advanced": {field: None for field in _SPACING_ADVANCED_FIELDS}}


def _with_spacing(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``spacing`` می‌پوشاند — فقط برایِ ``SPACING_AWARE_SECTION_KEYS``.
    دقیقاً همان الگویِ ``_with_background`` بالا."""
    if section_key not in SPACING_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        spacing_raw = raw.get("spacing")
        base_raw = {k: v for k, v in raw.items() if k != "spacing"}
        cleaned = validate_fn(base_raw)
        cleaned["spacing"] = validate_spacing_settings(spacing_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "spacing": default_spacing_settings()}

    return wrapped_validate, wrapped_default


#: R4 Task 7 — Phase 1 slice: only ``hero_banner`` gets a local typography
#: override. An explicit allowlist, not a default-for-all-types — the same
#: pattern as ``DESTINATION_AWARE_SECTION_KEYS``/``MOTION_AWARE_SECTION_KEYS``.
APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS = frozenset({
    "hero_banner",
    # Phase 3 (V01) — brand_carousel joins the allowlist so its validator
    # stops silently dropping the ``appearance_overrides`` block. The block
    # it needs to carry is the internal explicit-local-variant marker
    # (``variant_explicit``), NOT the client-writable typography contract —
    # see ``_with_appearance_overrides`` for how the trusted marker is
    # preserved without ever being accepted from raw client payload.
    "brand_carousel",
    # Phase 3 Task 6 -- Collection proves the same server-owned
    # explicit-local-variant preservation contract for tile_style.
    "collection_tiles",
})


def _with_appearance_overrides(section_key: str, validate_fn, default_fn):
    """Wraps (validate_settings, default_settings) with support for the
    ``appearance_overrides`` block — ONLY for
    ``APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS``. Required because
    ``settings_schema.clean_section_schema_patch`` already schema-cleans
    ``appearance_overrides`` (see ``_clean_field_value``), but that cleaned
    key would otherwise be silently dropped by
    ``definition.validate_settings`` — no existing wrapper here knows about
    it.

    Deliberately DIFFERENT from every wrapper above: this one never
    materializes a default block. A Hero settings dict with no
    ``appearance_overrides`` key must stay byte-identical to the
    pre-Task-7 shape — sparse inheritance from Global Design is the whole
    point, not "every Hero secretly carries an empty override forever."
    """
    if section_key not in APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        appearance_overrides_raw = raw.get("appearance_overrides")
        base_raw = {k: v for k, v in raw.items() if k != "appearance_overrides"}
        cleaned = validate_fn(base_raw)
        # Phase 3 (V01) — carry through an already-present, TRUSTED
        # explicit-local-variant marker. ``variant_explicit`` is NOT part of
        # the client-writable ``appearance_overrides`` typography contract
        # (``validate_appearance_overrides`` still rejects it as unknown), so
        # it is extracted here BEFORE that validator runs and re-attached only
        # when the INPUT settings already carried a ``True`` boolean for it.
        # This preserves the marker across an ordinary non-variant edit (a
        # merged dict already holding the trusted persisted marker) on BOTH
        # the R4 schema-patch bridge and the legacy validate_settings path,
        # while never letting a client manufacture the marker: a non-boolean
        # or ``False``/absent value is simply not carried, and a historically
        # unmarked section stays unmarked.
        preserved_marker = False
        if isinstance(appearance_overrides_raw, dict):
            existing = appearance_overrides_raw.get(VARIANT_EXPLICIT_OVERRIDE_KEY)
            preserved_marker = existing is True
        if appearance_overrides_raw is not None:
            cleaned_overrides = validate_appearance_overrides(
                {k: v for k, v in appearance_overrides_raw.items()
                 if k != VARIANT_EXPLICIT_OVERRIDE_KEY}
                if isinstance(appearance_overrides_raw, dict)
                else appearance_overrides_raw
            )
            if cleaned_overrides:
                cleaned["appearance_overrides"] = cleaned_overrides
        if preserved_marker:
            overrides = dict(cleaned.get("appearance_overrides") or {})
            overrides[VARIANT_EXPLICIT_OVERRIDE_KEY] = True
            cleaned["appearance_overrides"] = overrides
        return cleaned

    # default_fn is intentionally NOT wrapped: the default Hero settings
    # shape must remain exactly what it was before Task 7.
    return wrapped_validate, default_fn


#: Phase 8 P0-5 — انواعی که «عرضِ محتوا» برایشان معنایِ بصریِ روشنی
#: دارد (بلوک‌هایِ تصویری/بنری کاملاً عرض‌گیر) — یک allowlist صریح،
#: دقیقاً همان الگویِ بالا.
LAYOUT_WIDTH_AWARE_SECTION_KEYS = frozenset({
    "hero_banner", "image_slider", "image_text", "single_banner", "multi_banner",
})
#: زیرمجموعه‌ای از بالا که «ارتفاع» هم برایشان معنا دارد — فقط
#: اسلایدرها (ارتفاعِ ثابتِ ``.hero-inner``)؛ برایِ بقیه (image_text/
#: بنرها) ارتفاع یک مفهومِ محتوامحورِ متغیر است، نه یک بلوکِ با
#: ارتفاعِ ثابتِ قابلِ‌تنظیم — نمایشِ این کنترل برایِ آن‌ها گمراه‌کننده
#: بود (دقیقاً همان درسِ ``COLUMN_VISUAL_SECTION_KEYS`` در بالا).
LAYOUT_HEIGHT_AWARE_SECTION_KEYS = frozenset({"hero_banner", "image_slider"})

CONTENT_WIDTH_CHOICES = ("narrow", "standard", "full")
HEIGHT_CHOICES = ("compact", "standard", "tall")


class LayoutSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``layout`` نامعتبر است."""


def validate_layout_settings(raw, *, supports_height: bool) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise LayoutSettingsError("تنظیماتِ چیدمان باید یک شیء باشد")
    width = raw.get("content_width")
    cleaned = {"content_width": width if width in CONTENT_WIDTH_CHOICES else "standard"}
    if supports_height:
        height = raw.get("height")
        cleaned["height"] = height if height in HEIGHT_CHOICES else "standard"
    return cleaned


def default_layout_settings(*, supports_height: bool) -> dict:
    return validate_layout_settings(None, supports_height=supports_height)


def _with_layout(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``layout`` می‌پوشاند — فقط برایِ ``LAYOUT_WIDTH_AWARE_SECTION_KEYS``.
    دقیقاً همان الگویِ ``_with_card``/``_with_responsive`` بالا."""
    if section_key not in LAYOUT_WIDTH_AWARE_SECTION_KEYS:
        return validate_fn, default_fn
    supports_height = section_key in LAYOUT_HEIGHT_AWARE_SECTION_KEYS

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        layout_raw = raw.get("layout")
        base_raw = {k: v for k, v in raw.items() if k != "layout"}
        cleaned = validate_fn(base_raw)
        cleaned["layout"] = validate_layout_settings(layout_raw, supports_height=supports_height)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "layout": default_layout_settings(supports_height=supports_height)}

    return wrapped_validate, wrapped_default


#: انواعی که یک بلوکِ «حرکت» (Phase 3: کتابخانه‌ی بلوک‌هایِ صفحه‌ی
#: اصلی) دارند — جلوه‌ی ورود/hover که کاملاً config-محور است (CSS در
#: storefront_builder.css)، نه کدِ Renderer/family. عمداً یک allowlist
#: صریح است (مثلِ ``COLUMN_AWARE_SECTION_KEYS``/``DESTINATION_AWARE_SECTION_KEYS``
#: بالا)، نه پیش‌فرضِ همه‌ی انواع — بعضی انواع (rich_text/faq/testimonials/
#: quick_links/video_section/trust_features/...) معنایِ بصریِ روشنی برایِ
#: hover/ورودِ متحرک ندارند.
MOTION_AWARE_SECTION_KEYS = frozenset({
    "hero_banner", "image_slider", "single_banner", "multi_banner",
    "category_grid", "brand_carousel", "product_section", "collection_tiles",
    "image_text",
})

#: enum بستهٔ سبکِ حرکت — ``none`` پیش‌فرض (رفتارِ فعلی، بدونِ تغییر).
MOTION_CHOICES = ("none", "fade", "slide", "subtle_zoom", "hover_lift")


class MotionSettingsError(ValueError):
    """شکلِ خامِ بلوکِ ``motion`` نامعتبر است."""


def validate_motion_settings(raw) -> dict:
    """قراردادِ مشترکِ «حرکت» — سبکِ نامعتبر/غایب بی‌صدا به ``none``
    بازمی‌گردد (نه خطا)، دقیقاً همان تسامحی که ``validate_responsive_settings``
    برایِ کلیدهایِ ناشناخته/غایب دارد."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MotionSettingsError("تنظیماتِ حرکت باید یک شیء باشد")
    style = raw.get("style")
    if style not in MOTION_CHOICES:
        style = "none"
    return {"style": style}


def default_motion_settings() -> dict:
    return {"style": "none"}


def _with_motion(section_key: str, validate_fn, default_fn):
    """هر جفتِ (validate_settings, default_settings) موجود را با پشتیبانیِ
    بلوکِ ``motion`` می‌پوشاند — فقط برایِ کلیدهایِ ``MOTION_AWARE_SECTION_KEYS``.
    دقیقاً همان الگویِ ``_with_responsive``/``_with_destination`` بالا."""
    if section_key not in MOTION_AWARE_SECTION_KEYS:
        return validate_fn, default_fn

    def wrapped_validate(raw: dict) -> dict:
        if not isinstance(raw, dict):
            return validate_fn(raw)
        motion_raw = raw.get("motion")
        base_raw = {k: v for k, v in raw.items() if k != "motion"}
        cleaned = validate_fn(base_raw)
        cleaned["motion"] = validate_motion_settings(motion_raw)
        return cleaned

    def wrapped_default() -> dict:
        base = default_fn()
        return {**base, "motion": default_motion_settings()}

    return wrapped_validate, wrapped_default


#: بازه‌یِ مجازِ فاصله‌یِ خودکارِ اسلایدر (میلی‌ثانیه) — enum بسته نیست
#: (چون یک بازه‌یِ عددیِ معقول است، نه چند گزینه‌یِ مجزا)، اما clamp
#: می‌شود تا هرگز مقدارِ نامعقول (خیلی سریع/خیلی کند) ذخیره نشود.
_SLIDER_MIN_INTERVAL_MS = 2000
_SLIDER_MAX_INTERVAL_MS = 10000
_SLIDER_DEFAULT_INTERVAL_MS = 4500


#: U4 — the closed set of structural variants ``hero_banner`` registers
#: (see ``_BASE_SECTION_REGISTRY["hero_banner"]`` below). Shared here with
#: ``_validate_slider_settings`` because that validator is the ONE place
#: both ``hero_banner`` and ``image_slider`` clean their settings —
#: ``image_slider`` has no ``variants`` registered, so this key is simply
#: inert/unused there, exactly like ``text_position`` already is for any
#: section that doesn't read it. Keeping the key in one shared validator
#: (rather than forking a second near-identical function) is the same
#: reuse choice already made for every other slider-level field.
HERO_STYLE_CHOICES = ("overlay", "split", "beauty_editorial", "chocolate_carousel", "atelier_triptych", "luxury_showcase")


def _validate_slider_settings(raw: dict) -> dict:
    """قراردادِ تنظیماتِ سطحِ اسلایدر (نه تک‌تکِ اسلایدها — آن‌ها روی خودِ
    ``HeroSlide`` ذخیره می‌شوند) — برایِ ``hero_banner``/``image_slider``.
    اسلایدهایِ خودِ section از طریقِ ``HeroSlide.section`` (نه اینجا)
    مدیریت می‌شوند؛ این فقط رفتارِ نمایشِ اسلایدر را کنترل می‌کند."""
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")

    autoplay = raw.get("autoplay", True)
    if not isinstance(autoplay, bool):
        autoplay = bool(autoplay)

    try:
        interval_ms = int(raw.get("interval_ms", _SLIDER_DEFAULT_INTERVAL_MS))
    except (TypeError, ValueError):
        interval_ms = _SLIDER_DEFAULT_INTERVAL_MS
    interval_ms = max(_SLIDER_MIN_INTERVAL_MS, min(_SLIDER_MAX_INTERVAL_MS, interval_ms))

    show_arrows = raw.get("show_arrows", True)
    if not isinstance(show_arrows, bool):
        show_arrows = bool(show_arrows)

    show_dots = raw.get("show_dots", True)
    if not isinstance(show_dots, bool):
        show_dots = bool(show_dots)

    loop = raw.get("loop", True)
    if not isinstance(loop, bool):
        loop = bool(loop)

    text_position = raw.get("text_position", "end")
    if text_position not in {"start", "center", "end"}:
        text_position = "end"

    # U4 — ``hero_style`` selects the registered structural variant
    # (``overlay``/``split``/``beauty_editorial``, see ``HERO_STYLE_CHOICES``). Coerced here
    # (not left to the generic ``variant_contract`` safety net alone) so an
    # unrecognized/legacy value never round-trips back into storage —
    # exactly the same discipline ``display_mode`` already gets in
    # ``_validate_category_grid_settings``.
    hero_style = raw.get("hero_style", "overlay")
    if hero_style not in HERO_STYLE_CHOICES:
        hero_style = "overlay"

    return {
        "autoplay": autoplay, "interval_ms": interval_ms,
        "show_arrows": show_arrows, "show_dots": show_dots, "loop": loop,
        "text_position": text_position, "hero_style": hero_style,
    }


def default_slider_settings() -> dict:
    return {
        "autoplay": True, "interval_ms": _SLIDER_DEFAULT_INTERVAL_MS,
        "show_arrows": True, "show_dots": True, "loop": True,
        # ``end`` preserves the historical overlay side for existing stores.
        "text_position": "end",
        # ``overlay`` is the historical, only-ever-rendered hero treatment —
        # an existing store with no ``hero_style`` written keeps rendering
        # byte-identically via this default.
        "hero_style": "overlay",
    }


#: R4 Task 4 — declarative counterpart of ``_validate_slider_settings``
#: for ``hero_banner`` only (Phase 0 scope; NOT attached to
#: ``image_slider``, which shares the same legacy validator but has no
#: registered ``variants``). Only the existing high-level slider keys —
#: no wrapper block (responsive/motion/layout/background/spacing) is
#: schema-declared here; those keep surviving via
#: ``SettingsSchema.preserve_unmanaged=True`` and the legacy validator's
#: own post-validation, exactly as the architecture spec requires.
HERO_BANNER_SCHEMA = SettingsSchema(fields=(
    SettingsField(
        "hero_style", "مدل نمایش", "choice", "basic",
        default="overlay",
        choices=tuple((x, x) for x in HERO_STYLE_CHOICES),
    ),
    SettingsField(
        "autoplay", "پخش خودکار", "boolean", "basic",
        default=True,
    ),
    SettingsField(
        "interval_ms", "فاصله اسلاید", "integer", "advanced",
        default=_SLIDER_DEFAULT_INTERVAL_MS,
        min_value=_SLIDER_MIN_INTERVAL_MS,
        max_value=_SLIDER_MAX_INTERVAL_MS,
    ),
    SettingsField(
        "show_arrows", "نمایش فلش‌ها", "boolean", "advanced",
        default=True,
    ),
    SettingsField(
        "show_dots", "نمایش نقاط", "boolean", "advanced",
        default=True,
    ),
    SettingsField(
        "loop", "تکرار", "boolean", "advanced",
        default=True,
    ),
    SettingsField(
        "text_position", "جای متن", "choice", "advanced",
        default="end",
        choices=(("start", "ابتدا"), ("center", "وسط"), ("end", "انتها")),
    ),
    SettingsField(
        "appearance_overrides", "تایپوگرافی این بخش", "appearance_override", "advanced",
        default={},
        widget_hint="typography_override",
    ),
))


#: R4 Task 6 — same declarative counterpart for ``image_slider``, which
#: shares ``_validate_slider_settings``/``default_slider_settings`` with
#: ``hero_banner`` but has no registered variants, so ``hero_style`` is
#: deliberately omitted here (that field only has a rendered control on
#: ``hero_banner``'s settings form). The validator still always returns a
#: ``hero_style`` key for ``image_slider`` too — that key simply survives
#: as an unmanaged, unused value, exactly as it already does today.
#: ``appearance_overrides`` is ALSO deliberately omitted — Task 7 exposed
#: that Inspector field on ``hero_banner`` only (see
#: ``HeroSchemaFieldTests`` in ``test_r4_appearance_overrides.py``, which
#: explicitly asserts ``image_slider`` does not get it); the underlying
#: ``_with_appearance_overrides`` wrapper still applies to every section's
#: legacy validator regardless, so this omission only affects Inspector
#: field exposure, not the actual override capability.
IMAGE_SLIDER_SCHEMA = SettingsSchema(fields=(
    SettingsField(
        "autoplay", "پخش خودکار", "boolean", "basic",
        default=True,
    ),
    SettingsField(
        "interval_ms", "فاصله اسلاید", "integer", "advanced",
        default=_SLIDER_DEFAULT_INTERVAL_MS,
        min_value=_SLIDER_MIN_INTERVAL_MS,
        max_value=_SLIDER_MAX_INTERVAL_MS,
    ),
    SettingsField(
        "show_arrows", "نمایش فلش‌ها", "boolean", "advanced",
        default=True,
    ),
    SettingsField(
        "show_dots", "نمایش نقاط", "boolean", "advanced",
        default=True,
    ),
    SettingsField(
        "loop", "تکرار", "boolean", "advanced",
        default=True,
    ),
    SettingsField(
        "text_position", "جای متن", "choice", "advanced",
        default="end",
        choices=(("start", "ابتدا"), ("center", "وسط"), ("end", "انتها")),
    ),
))


class CategoryGridSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «گرید دسته‌بندی» نامعتبر است (فقط شکل/enum —
    مالکیتِ Storeِ ``category_ids`` در خودِ ``render_service`` چک می‌شود،
    چون یک کوئریِ QuerySet ساده است، نه سرویسِ جداگانه)."""


_MAX_CATEGORY_GRID_IDS = 12
_MAX_SECTION_TITLE_LENGTH = 60
#: ``fashion_flat`` (site-target-overhaul Part 2B, ibolak reference) — a
#: compact flat rail (small image, short label, no card chrome) distinct
#: from ``image_strip``'s own CSS (which ``dense_marketplace`` already
#: uses) so that template's rendering stays completely untouched.
CATEGORY_GRID_DISPLAY_MODES = ("grid", "carousel", "circular", "image_strip", "fashion_flat", "fashion_mosaic", "beauty_icons", "chocolate_story", "chocolate_badges", "atelier_mosaic", "luxury_shortcuts")


def _validate_category_grid_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۱: ``category_grid`` از یک بلوکِ سراسریِ ثابت (۳+۱ دسته‌ی
    اولِ فروشگاه) به یک section واقعاً per-instance ارتقا یافت —
    ``category_ids`` خالی یعنی «هنوز مرچنت انتخاب نکرده»، که در
    ``render_service`` دقیقاً همان رفتارِ قبل از این چکپوینت (auto-pick
    از دسته‌های فعالِ سطحِ اول) را بازتولید می‌کند — سازگاریِ کامل با
    گذشته."""
    if not isinstance(raw, dict):
        raise CategoryGridSettingsError("تنظیمات باید یک شیء JSON باشد")

    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    display_mode = raw.get("display_mode")
    if display_mode not in CATEGORY_GRID_DISPLAY_MODES:
        display_mode = "grid"
    category_ids = _clean_positive_int_list(
        raw.get("category_ids", []), max_len=_MAX_CATEGORY_GRID_IDS,
        error_cls=CategoryGridSettingsError, error_message="شناسه‌ی دسته‌بندی نامعتبر است",
    )
    try:
        item_limit = int(raw.get("item_limit", 12))
    except (TypeError, ValueError):
        raise CategoryGridSettingsError("تعداد دسته‌بندی باید عدد باشد") from None
    item_limit = max(2, min(12, item_limit))
    return {"title": title, "display_mode": display_mode, "category_ids": category_ids, "item_limit": item_limit}


def default_category_grid_settings() -> dict:
    return {"title": "", "display_mode": "grid", "category_ids": [], "item_limit": 12}


#: Task 6 — the declarative Inspector-facing schema for "گرید دسته‌بندی".
#: Exactly analogous to COLLECTION_TILES_SCHEMA: ``category_ids`` is NOT
#: schema-registered directly — it is a compatibility persistence detail
#: hidden behind the typed ``source`` field (see ``_with_resource_source``
#: below, now covering ``category_grid`` too). ``display_mode`` is the
#: variant marker (all 11 CATEGORY_GRID_DISPLAY_MODES, matching the
#: registered ``variants=`` tuple below verbatim — no narrowing).
CATEGORY_GRID_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
    SettingsField(
        "source", "منبع دسته‌بندی‌ها", "resource_source", "basic",
        default=resource_source_module.serialize_resource_source(
            resource_source_module.ResourceSource(kind="category", mode="auto", auto_rule="all_active"),
        ),
    ),
    SettingsField(
        "display_mode", "نوع نمایش", "choice", "basic", default="grid",
        choices=tuple((x, x) for x in CATEGORY_GRID_DISPLAY_MODES),
    ),
    SettingsField(
        "item_limit", "حداکثر تعداد", "integer", "advanced",
        default=12, min_value=2, max_value=12,
    ),
))


#: Phase 3 (Universal Storefront — V5 Golden Homepage) — ``trust_features``
#: تا پیش از این چکپوینت یک بلوکِ کاملاً ثابتِ ۴ آیتمی بود (هیچ کلیدی از
#: ``settings`` خوانده نمی‌شد)، پس واقعاً «تنظیم‌پذیر» نبود — یک شکافِ
#: واقعی نسبت به الزامِ «تعدادِ متغیرِ آیتم، متنِ دلخواه» که V5 نیاز دارد.
#: ``items`` خالی (پیش‌فرض) دقیقاً همان ۴ آیتمِ ثابتِ قبلی را در تمپلیت
#: بدونِ تغییر بازتولید می‌کند — سازگاریِ کامل با گذشته برایِ فروشگاه‌هایی
#: که هنوز شخصی‌سازی نکرده‌اند.
_MAX_TRUST_FEATURE_ITEMS = 6
_MAX_TRUST_FEATURE_ICON_LENGTH = 8
_MAX_TRUST_FEATURE_TEXT_LENGTH = 40


class TrustFeaturesSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ ردیفِ اعتماد نامعتبر است — پیامِ فارسیِ قابل‌نمایشِ مستقیم به تاجر."""


def _validate_trust_feature_item(raw) -> dict:
    if not isinstance(raw, dict):
        raise TrustFeaturesSettingsError("هر آیتمِ ردیفِ اعتماد باید یک شیء باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_TRUST_FEATURE_TEXT_LENGTH]
    if not title:
        raise TrustFeaturesSettingsError("عنوانِ آیتمِ ردیفِ اعتماد نمی‌تواند خالی باشد")
    return {
        "icon": str(raw.get("icon", "")).strip()[:_MAX_TRUST_FEATURE_ICON_LENGTH],
        "title": title,
        "subtitle": str(raw.get("subtitle", "")).strip()[:_MAX_TRUST_FEATURE_TEXT_LENGTH],
    }


def validate_trust_features_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise TrustFeaturesSettingsError("تنظیمات باید یک شیء JSON باشد")
    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raise TrustFeaturesSettingsError("فهرستِ آیتم‌ها نامعتبر است")
    items = [_validate_trust_feature_item(item) for item in raw_items[:_MAX_TRUST_FEATURE_ITEMS]]
    return {"items": items}


def default_trust_features_settings() -> dict:
    return {"items": []}


#: Phase 3 (Universal Storefront — V5 Golden Homepage) — ``amazing_offers``
#: تا پیش از این چکپوینت همیشه دقیقاً یک محصول نمایش می‌داد (تنظیمات اصلاً
#: خوانده نمی‌شد) — «Product Spotlight» یِ V5 چند پیشنهادِ هم‌زمان لازم دارد.
#: ``item_limit`` پیش‌فرضش ۱ است تا رفتارِ فروشگاه‌هایی که پیش از این
#: چکپوینت این بخش را بدونِ تنظیمِ خاصی افزوده‌اند، دقیقاً بدونِ تغییر
#: بماند — فقط با تنظیمِ صریح (مثلِ Preset ی V5) عدد بزرگ‌تر می‌شود.
_MIN_AMAZING_OFFER_ITEMS = 1
_MAX_AMAZING_OFFER_ITEMS = 4
_DEFAULT_AMAZING_OFFER_ITEMS = 1
_MIN_AMAZING_OFFER_HOURS = 1
_MAX_AMAZING_OFFER_HOURS = 168
_DEFAULT_AMAZING_OFFER_HOURS = 8


class AmazingOffersSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «پیشنهادهای شگفت‌انگیز» نامعتبر است — پیامِ فارسیِ قابل‌نمایشِ مستقیم به تاجر."""


def validate_amazing_offers_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise AmazingOffersSettingsError("تنظیمات باید یک شیء JSON باشد")
    try:
        item_limit = int(raw.get("item_limit", _DEFAULT_AMAZING_OFFER_ITEMS))
    except (TypeError, ValueError):
        raise AmazingOffersSettingsError("تعدادِ پیشنهادها باید عدد باشد") from None
    item_limit = max(_MIN_AMAZING_OFFER_ITEMS, min(_MAX_AMAZING_OFFER_ITEMS, item_limit))
    try:
        deadline_hours = int(raw.get("deadline_hours", _DEFAULT_AMAZING_OFFER_HOURS))
    except (TypeError, ValueError):
        raise AmazingOffersSettingsError("مدتِ زمان‌شمار باید عدد باشد") from None
    deadline_hours = max(_MIN_AMAZING_OFFER_HOURS, min(_MAX_AMAZING_OFFER_HOURS, deadline_hours))
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    return {"item_limit": item_limit, "deadline_hours": deadline_hours, "title": title}


def default_amazing_offers_settings() -> dict:
    return {"item_limit": _DEFAULT_AMAZING_OFFER_ITEMS, "deadline_hours": _DEFAULT_AMAZING_OFFER_HOURS, "title": ""}


#: R4 Task 6 (Group D) — declarative counterpart of
#: ``validate_amazing_offers_settings``.
AMAZING_OFFERS_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
    SettingsField(
        "item_limit", "حداکثر تعداد پیشنهاد", "integer", "basic",
        default=_DEFAULT_AMAZING_OFFER_ITEMS,
        min_value=_MIN_AMAZING_OFFER_ITEMS, max_value=_MAX_AMAZING_OFFER_ITEMS,
    ),
    SettingsField(
        "deadline_hours", "مدت زمان‌شمار (ساعت)", "integer", "advanced",
        default=_DEFAULT_AMAZING_OFFER_HOURS,
        min_value=_MIN_AMAZING_OFFER_HOURS, max_value=_MAX_AMAZING_OFFER_HOURS,
    ),
))


#: Phase 3 (Universal Storefront — V5 Golden Homepage) — بلوکِ کاملاً
#: جدید «مطالب وبلاگ» (طبقِ نقشه‌ی V5→Universal Block، ردیفِ «Blog»: نه
#: هیچ بلوکِ موجودی این نقش را پوشش می‌دهد، نه توجیهی برایِ بیش‌سازی
#: هست — طبقِ الزامِ صریحِ کار «keep simple, do not overbuild»).
#: ``apps.blog.models.BlogPost`` سراسریِ پلتفرم است (بدونِ FK به Store —
#: واقعیتی از قبل موجود، نه چیزی که این چکپوینت اصلاح می‌کند)؛ این بخش
#: صرفاً جدیدترین مطالبِ منتشرشده را نمایش می‌دهد. صفحه‌ی جزئیاتِ مطلب
#: هنوز در پروژه وجود ندارد (``apps/blog`` فاقدِ url/view است) — دقیقاً
#: همان محدودیتی که تمپلیتِ قدیمیِ ``catalog/home.html`` هم داشت
#: (``href="#"``)؛ ساختنِ آن صفحه خارج از دامنه‌ی این فاز (Homepage
#: فقط) است.
_MIN_BLOG_POST_ITEMS = 3
_MAX_BLOG_POST_ITEMS = 6
_DEFAULT_BLOG_POST_ITEMS = 5


class BlogPostsSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «مطالبِ وبلاگ» نامعتبر است — پیامِ فارسیِ قابل‌نمایشِ مستقیم به تاجر."""


def validate_blog_posts_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise BlogPostsSettingsError("تنظیمات باید یک شیء JSON باشد")
    try:
        item_limit = int(raw.get("item_limit", _DEFAULT_BLOG_POST_ITEMS))
    except (TypeError, ValueError):
        raise BlogPostsSettingsError("تعدادِ مطالب باید عدد باشد") from None
    item_limit = max(_MIN_BLOG_POST_ITEMS, min(_MAX_BLOG_POST_ITEMS, item_limit))
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    return {"item_limit": item_limit, "title": title}


def default_blog_posts_settings() -> dict:
    return {"item_limit": _DEFAULT_BLOG_POST_ITEMS, "title": ""}


#: R4 Task 6 (Group C) — minimal declarative counterpart of
#: ``validate_blog_posts_settings``, following the same one-field-plus-
#: bounded-integer pattern already used by ``RICH_TEXT_SCHEMA``/
#: ``CATEGORY_GRID_SCHEMA``.
BLOG_POSTS_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
    SettingsField(
        "item_limit", "تعداد مطالب", "integer", "advanced",
        default=_DEFAULT_BLOG_POST_ITEMS,
        min_value=_MIN_BLOG_POST_ITEMS, max_value=_MAX_BLOG_POST_ITEMS,
    ),
))


class BrandCarouselSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «کاروسل برندها» نامعتبر است."""


_MAX_BRAND_CAROUSEL_IDS = 24
BRAND_CAROUSEL_DISPLAY_MODES = ("grid", "carousel", "beauty_tabs")


def _validate_brand_carousel_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۱: همان ارتقایِ ``category_grid`` برایِ ``brand_carousel``
    — ``brand_ids`` خالی یعنی رفتارِ قبل از این چکپوینت (همه‌ی برندهایِ
    فعالِ فروشگاه) دست‌نخورده می‌ماند. ``destination`` (لینکِ اختیاریِ
    «مشاهده همه») از طریقِ ``DESTINATION_AWARE_SECTION_KEYS`` عمومی
    اضافه می‌شود، نه اینجا — دقیقاً همان زیرساختِ لینکِ استانداردِ کارِ
    ۱."""
    if not isinstance(raw, dict):
        raise BrandCarouselSettingsError("تنظیمات باید یک شیء JSON باشد")

    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    display_mode = raw.get("display_mode")
    if display_mode not in BRAND_CAROUSEL_DISPLAY_MODES:
        display_mode = "grid"
    show_view_all = raw.get("show_view_all", False)
    if not isinstance(show_view_all, bool):
        show_view_all = bool(show_view_all)
    brand_ids = _clean_positive_int_list(
        raw.get("brand_ids", []), max_len=_MAX_BRAND_CAROUSEL_IDS,
        error_cls=BrandCarouselSettingsError, error_message="شناسه‌ی برند نامعتبر است",
    )
    return {"title": title, "display_mode": display_mode, "show_view_all": show_view_all, "brand_ids": brand_ids}


def default_brand_carousel_settings() -> dict:
    return {"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": []}


#: R4 Task 9 — the declarative Inspector-facing schema for "کاروسل برندها".
#: ``brand_ids`` is deliberately NOT schema-registered directly — it is a
#: compatibility persistence detail hidden behind the typed ``source`` field
#: (see ``_with_resource_source`` below). No new Brand auto rules.
BRAND_CAROUSEL_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
    SettingsField(
        "source", "منبع برندها", "resource_source", "basic",
        default=resource_source_module.serialize_resource_source(
            resource_source_module.ResourceSource(kind="brand", mode="auto", auto_rule="all_active"),
        ),
    ),
    SettingsField(
        "display_mode", "نوع نمایش", "choice", "basic", default="grid",
        choices=(
            ("grid", "گرید"),
            ("carousel", "کاروسل"),
            ("beauty_tabs", "ردیف برندهای فروشگاهی"),
        ),
    ),
    SettingsField("show_view_all", "نمایش دکمه «مشاهده همه»", "boolean", "basic", default=False),
))


class CollectionTilesSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «کارت‌های کالکشن» نامعتبر است."""


_MAX_COLLECTION_TILES_IDS = 12


#: U4 — the closed set of structural variants ``collection_tiles`` registers
#: (see ``_BASE_SECTION_REGISTRY["collection_tiles"]`` below).
COLLECTION_TILES_STYLE_CHOICES = ("grid", "carousel")


def _validate_collection_tiles_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: بخشِ جدیدِ «کارت‌های کالکشن» — خودِ کالکشن‌ها را نشان
    می‌دهد (تصویر/نام/تعدادِ کالا/لینک به صفحه‌ی کالکشن)، نه کالاهایِ
    *داخلِ* یک کالکشن (که همان ``product_section`` با ``data_source=collection``
    است). ``collection_ids`` خالی = نمایشِ خودکارِ همه‌ی کالکشن‌های فعال.

    U4 اضافه کرد: ``tile_style`` (``grid`` پیش‌فرض / ``carousel``) — همان
    الگویِ Pattern A که ``category_grid``/``brand_carousel`` قبلاً برایِ
    ``display_mode`` دارند؛ همان template، فقط کلاسِ CSSِ کانتینر عوض
    می‌شود."""
    if not isinstance(raw, dict):
        raise CollectionTilesSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    collection_ids = _clean_positive_int_list(
        raw.get("collection_ids", []), max_len=_MAX_COLLECTION_TILES_IDS,
        error_cls=CollectionTilesSettingsError, error_message="شناسه‌ی کالکشن نامعتبر است",
    )
    tile_style = raw.get("tile_style", "grid")
    if tile_style not in COLLECTION_TILES_STYLE_CHOICES:
        tile_style = "grid"
    return {"title": title, "collection_ids": collection_ids, "tile_style": tile_style}


def default_collection_tiles_settings() -> dict:
    return {"title": "", "collection_ids": [], "tile_style": "grid"}


#: R4 Task 4 (V03) — the declarative Inspector-facing schema for "کارت‌های
#: کالکشن". Exactly analogous to BRAND_CAROUSEL_SCHEMA: ``collection_ids`` is
#: NOT schema-registered directly — it is a compatibility persistence detail
#: hidden behind the typed ``source`` field (see ``_with_resource_source``
#: below). No new Collection auto rules. ``tile_style`` is the variant marker.
COLLECTION_TILES_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
    SettingsField(
        "source", "منبع کالکشن‌ها", "resource_source", "basic",
        default=resource_source_module.serialize_resource_source(
            resource_source_module.ResourceSource(kind="collection", mode="auto", auto_rule="all_active"),
        ),
    ),
    SettingsField(
        "tile_style", "نوع نمایش", "choice", "basic", default="grid",
        choices=(
            ("grid", "گرید"),
            ("carousel", "کاروسل"),
        ),
    ),
))


class QuickLinksSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «دسترسی سریع» نامعتبر است."""


def _validate_quick_links_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: «دسترسی سریع» — به‌جایِ اختراعِ یک مدلِ لینکِ جدید،
    مستقیماً یک ``Menu`` موجود (همان زیرساختِ Menu/MenuItem/Destination
    که برایِ ناوبریِ هدر/فوتر استفاده می‌شود) را به‌شکلِ ردیفی از
    کارت‌های بصری نمایش می‌دهد — مالکیتِ Storeِ ``menu_id`` در
    ``render_service`` چک می‌شود."""
    if not isinstance(raw, dict):
        raise QuickLinksSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    menu_id = raw.get("menu_id")
    if menu_id is not None:
        try:
            menu_id = int(menu_id)
        except (TypeError, ValueError):
            raise QuickLinksSettingsError("منویِ انتخاب‌شده نامعتبر است") from None
        if menu_id <= 0:
            menu_id = None
    return {"title": title, "menu_id": menu_id}


def default_quick_links_settings() -> dict:
    return {"title": "", "menu_id": None}


#: R4 Task 6 (Group D) — ``menu_id`` is deliberately NOT declared here:
#: it is an FK into the existing Menu/MenuItem navigation infrastructure
#: (see ``_validate_quick_links_settings`` above), not a catalog
#: ResourceSource kind (``ALLOWED_KINDS`` is product/category/brand/
#: collection only) and none of the other Inspector-supported field
#: types fit an FK picker either. It stays managed exclusively through
#: the legacy settings form's existing Menu picker UI, preserved as an
#: unmanaged key exactly like the responsive/motion/layout/background/
#: spacing wrapper blocks are.
QUICK_LINKS_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
))


class FaqSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «سوالات متداول» نامعتبر است."""


_MAX_FAQ_ITEMS = 20
_MAX_FAQ_QUESTION_LENGTH = 200
_MAX_FAQ_ANSWER_LENGTH = 1000


def _validate_faq_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: هر آیتم فقط دو فیلدِ متنیِ ساده (سوال/پاسخ) — نه HTML
    غنی (سوءاستفاده/XSS از یک بخشِ به‌ظاهر ساده بی‌معناست؛ اگر مرچنت به
    فرمت‌بندیِ غنی نیاز داشت، ``rich_text`` همین حالا برایش هست)."""
    if not isinstance(raw, dict):
        raise FaqSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH] or "سوالات متداول"

    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raise FaqSettingsError("فهرستِ سوالات باید یک آرایه باشد")
    items = []
    for raw_item in raw_items[:_MAX_FAQ_ITEMS]:
        if not isinstance(raw_item, dict):
            continue
        question = str(raw_item.get("question", "")).strip()[:_MAX_FAQ_QUESTION_LENGTH]
        answer = str(raw_item.get("answer", "")).strip()[:_MAX_FAQ_ANSWER_LENGTH]
        if not question or not answer:
            continue
        items.append({"question": question, "answer": answer})
    return {"title": title, "items": items}


def default_faq_settings() -> dict:
    return {"title": "سوالات متداول", "items": []}


class TestimonialsSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «نظرات مشتریان» نامعتبر است."""


_MAX_TESTIMONIAL_ITEMS = 20
_MAX_TESTIMONIAL_NAME_LENGTH = 80
_MAX_TESTIMONIAL_ROLE_LENGTH = 80
_MAX_TESTIMONIAL_QUOTE_LENGTH = 400


def _validate_testimonials_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise TestimonialsSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH] or "نظرات مشتریان"

    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raise TestimonialsSettingsError("فهرستِ نظرات باید یک آرایه باشد")
    items = []
    for raw_item in raw_items[:_MAX_TESTIMONIAL_ITEMS]:
        if not isinstance(raw_item, dict):
            continue
        name = str(raw_item.get("name", "")).strip()[:_MAX_TESTIMONIAL_NAME_LENGTH]
        quote = str(raw_item.get("quote", "")).strip()[:_MAX_TESTIMONIAL_QUOTE_LENGTH]
        role = str(raw_item.get("role", "")).strip()[:_MAX_TESTIMONIAL_ROLE_LENGTH]
        if not name or not quote:
            continue
        items.append({"name": name, "quote": quote, "role": role})
    return {"title": title, "items": items}


def default_testimonials_settings() -> dict:
    return {"title": "نظرات مشتریان", "items": []}


class VideoSectionSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «بخشِ ویدیو» نامعتبر است."""


_MAX_VIDEO_CAPTION_LENGTH = 200


def _validate_video_section_settings(raw: dict) -> dict:
    """چکپوینتِ ۱۲: دقیقاً همان تشخیصِ ارائه‌دهنده/اعتبارسنجیِ URL که
    برایِ ویدیویِ کالا استفاده می‌شود (``product_video_service``) — بدونِ
    بازنویسیِ دوباره‌ی regex/قوانین. آدرسِ نامعتبر رد می‌شود، نه ذخیره‌ی
    بی‌صدا و شکستِ بعدیِ رندر."""
    if not isinstance(raw, dict):
        raise VideoSectionSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_SECTION_TITLE_LENGTH]
    caption = str(raw.get("caption", "")).strip()[:_MAX_VIDEO_CAPTION_LENGTH]

    video_url = str(raw.get("video_url", "")).strip()
    if video_url:
        from apps.catalog.services.product_video_service import ProductVideoError, detect_provider_and_id

        try:
            detect_provider_and_id(video_url)
        except ProductVideoError as exc:
            raise VideoSectionSettingsError(str(exc)) from exc

    return {"title": title, "video_url": video_url, "caption": caption}


def default_video_section_settings() -> dict:
    return {"title": "", "video_url": "", "caption": ""}


#: R4 Task 6 (Group D) — ``video_url`` has no dedicated Inspector field
#: type (there is no ``url`` entry in ``ALLOWED_FIELD_TYPES``), so it is
#: declared as ``text`` here — the schema layer only cleans shape/length,
#: exactly as it does for every other field; the real provider/URL
#: validation in ``_validate_video_section_settings`` above still runs
#: afterward and still rejects an unrecognized URL, unchanged.
VIDEO_SECTION_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="", max_length=_MAX_SECTION_TITLE_LENGTH),
    SettingsField("video_url", "آدرس ویدیو", "text", "basic", default=""),
    SettingsField("caption", "زیرنویس", "text", "advanced", default="", max_length=_MAX_VIDEO_CAPTION_LENGTH),
))


class NewsletterSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «خبرنامه» نامعتبر است."""


_MAX_NEWSLETTER_TITLE_LENGTH = 60
_MAX_NEWSLETTER_SUBTITLE_LENGTH = 150
_MAX_NEWSLETTER_BUTTON_LABEL_LENGTH = 30


def _validate_newsletter_settings(raw: dict) -> dict:
    """Phase 3 (کتابخانه‌ی بلوک‌هایِ صفحه‌ی اصلی) — فقط متنِ نمایشی؛ خودِ
    منطقِ ثبتِ ایمیل (اعتبارسنجی/دی‌دوپ/تنظیمِ ذخیره‌سازی) در
    ``apps.content.services.subscribe_to_newsletter`` است، نه اینجا —
    دقیقاً همان تفکیکِ مسئولیتی که ``_validate_product_section_settings``
    برایِ ``source_id`` دارد."""
    if not isinstance(raw, dict):
        raise NewsletterSettingsError("تنظیمات باید یک شیء JSON باشد")
    title = str(raw.get("title", "")).strip()[:_MAX_NEWSLETTER_TITLE_LENGTH]
    subtitle = str(raw.get("subtitle", "")).strip()[:_MAX_NEWSLETTER_SUBTITLE_LENGTH]
    button_label = str(raw.get("button_label", "")).strip()[:_MAX_NEWSLETTER_BUTTON_LABEL_LENGTH] or "عضویت"
    return {"title": title, "subtitle": subtitle, "button_label": button_label}


def default_newsletter_settings() -> dict:
    return {"title": "عضویت در خبرنامه", "subtitle": "", "button_label": "عضویت"}


#: R4 Task 6 (Group D) — declarative counterpart of
#: ``_validate_newsletter_settings``.
NEWSLETTER_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان بخش", "text", "basic", default="عضویت در خبرنامه", max_length=_MAX_NEWSLETTER_TITLE_LENGTH),
    SettingsField("subtitle", "زیرعنوان", "text", "basic", default="", max_length=_MAX_NEWSLETTER_SUBTITLE_LENGTH),
    SettingsField("button_label", "متن دکمه", "text", "advanced", default="عضویت", max_length=_MAX_NEWSLETTER_BUTTON_LABEL_LENGTH),
))


#: R4 Task 6 (Group C) — declarative counterpart of
#: ``_validate_image_text_settings``. ``image_url`` is deliberately NOT
#: declared here: the Inspector has no "media" field-type widget yet
#: (``_INSPECTOR_SUPPORTED_FIELD_TYPES`` in ``r4_views.py`` covers text/
#: rich_text/integer/boolean/choice/appearance_override/resource_source
#: only), so it stays managed exclusively through the legacy form's
#: existing image-URL input, preserved as an unmanaged key.
IMAGE_TEXT_SCHEMA = SettingsSchema(fields=(
    SettingsField("title", "عنوان", "text", "basic", default="", max_length=_MAX_IMAGE_TEXT_TITLE_LENGTH),
    SettingsField(
        "body_html", "متن", "rich_text", "basic",
        default="", max_length=_MAX_RICH_TEXT_LENGTH,
        widget_hint="merchant_rich_text",
    ),
    SettingsField(
        "image_position", "جای تصویر", "choice", "advanced",
        default="right", choices=(("right", "سمت راست"), ("left", "سمت چپ")),
    ),
))


def _validate_image_text_settings(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("تنظیمات باید یک شیء JSON باشد")
    from django.core.exceptions import ValidationError

    from apps.content.models import validate_external_url

    title = str(raw.get("title", ""))[:_MAX_IMAGE_TEXT_TITLE_LENGTH]
    body_html = str(raw.get("body_html", ""))[:_MAX_RICH_TEXT_LENGTH]
    image_url = str(raw.get("image_url", "")).strip()
    if image_url:
        try:
            validate_external_url(image_url)
        except ValidationError as exc:
            raise ValueError("; ".join(exc.messages)) from exc
    position = raw.get("image_position") if raw.get("image_position") in ("left", "right") else "right"
    return {"title": title, "body_html": body_html, "image_url": image_url, "image_position": position}


# ---------------------------------------------------------------- ثبت انواع بخش

#: Task 6 (Group C) — the U1A finding above (R1 §9) is now RESOLVED into
#: a real closed enum: a fresh full-codebase re-enumeration (every
#: ``layout_preset_registry.py`` preset, every fixture/migration/test —
#: there is still no merchant-facing form control for this key at all)
#: found exactly these six values ever persisted for
#: ``multi_banner.settings.layout_variant``, matching exactly the six
#: ``.promo-grid--*``/``.banner-section--*`` CSS classes that actually
#: exist in ``storefront_builder.css`` (the stale "only four" count
#: predates the ``atelier-duo``/``atelier-wide`` additions). An absent or
#: unrecognized value coerces to ``""`` (the historical "no override"
#: state — Django's ``|default:'default'`` template filter treats an
#: empty string exactly like an absent key, so this is byte-identical to
#: today's un-set behaviour, never a new "promo-4" default).
MULTI_BANNER_KNOWN_LAYOUT_VARIANTS = ("promo-4", "wide-single", "mini-4", "strip", "atelier-duo", "atelier-wide")


class MultiBannerSettingsError(ValueError):
    """شکلِ خامِ تنظیماتِ «ردیف چند بنری» نامعتبر است."""


_MIN_MULTI_BANNER_OFFSET = 0
_MAX_MULTI_BANNER_OFFSET = 50
_MIN_MULTI_BANNER_ITEMS = 1
_MAX_MULTI_BANNER_ITEMS = 24


def _validate_multi_banner_settings(raw: dict) -> dict:
    """دقیقاً همان clampهایی که ``_multi_banner_context`` (render_service)
    از قبل به‌شکلِ دفاعی در زمانِ رندر اعمال می‌کند — اینجا فقط همان
    قرارداد در زمانِ نوشتن هم رسمی می‌شود. ``item_limit`` غایب/خالی یعنی
    «همه‌ی بنرها» (رفتارِ تاریخیِ سکشن‌هایی که هرگز این کلید را لمس
    نکرده‌اند) — این معنا حفظ می‌شود، نه به یک عددِ پیش‌فرض تبدیل می‌شود."""
    if not isinstance(raw, dict):
        raise MultiBannerSettingsError("تنظیمات باید یک شیء JSON باشد")

    try:
        offset = max(_MIN_MULTI_BANNER_OFFSET, min(_MAX_MULTI_BANNER_OFFSET, int(raw.get("offset", 0))))
    except (TypeError, ValueError):
        offset = 0

    raw_limit = raw.get("item_limit")
    if raw_limit in (None, ""):
        item_limit = None
    else:
        try:
            item_limit = max(_MIN_MULTI_BANNER_ITEMS, min(_MAX_MULTI_BANNER_ITEMS, int(raw_limit)))
        except (TypeError, ValueError):
            item_limit = _MAX_MULTI_BANNER_ITEMS

    layout_variant = raw.get("layout_variant", "")
    if layout_variant not in MULTI_BANNER_KNOWN_LAYOUT_VARIANTS:
        layout_variant = ""

    return {"item_limit": item_limit, "offset": offset, "layout_variant": layout_variant}


def default_multi_banner_settings() -> dict:
    return {"item_limit": None, "offset": 0, "layout_variant": ""}


#: R4 Task 6 (Group C) — declarative counterpart of
#: ``_validate_multi_banner_settings``. ``item_limit``'s schema-metadata
#: ``default`` (24) is a display placeholder for the Inspector widget
#: only — it is independent of ``default_multi_banner_settings()`` above,
#: which keeps returning ``None`` (unlimited) for a genuinely new
#: section, exactly as documented there.
MULTI_BANNER_SCHEMA = SettingsSchema(fields=(
    SettingsField(
        "layout_variant", "قالبِ نمایش", "choice", "basic",
        default="",
        choices=(("", "پیش‌فرض (بدون قالبِ خاص)"),) + tuple((x, x) for x in MULTI_BANNER_KNOWN_LAYOUT_VARIANTS),
    ),
    SettingsField(
        "item_limit", "حداکثر تعداد بنر", "integer", "advanced",
        default=_MAX_MULTI_BANNER_ITEMS,
        min_value=_MIN_MULTI_BANNER_ITEMS, max_value=_MAX_MULTI_BANNER_ITEMS,
    ),
    SettingsField(
        "offset", "شروع از بنرِ چندم", "integer", "advanced",
        default=0,
        min_value=_MIN_MULTI_BANNER_OFFSET, max_value=_MAX_MULTI_BANNER_OFFSET,
    ),
))

#: ترتیبِ نمایشِ گروه‌هایِ کتابخانه‌ی «افزودن بخش جدید» (چکپوینتِ ۱۰) —
#: پنج گروهِ کسب‌وکاریِ ثابت، نه اصطلاحِ فنی؛ ``category_fa`` هر
#: ``SectionDefinition`` باید دقیقاً یکی از این‌ها باشد (تست می‌شود).
SECTION_LIBRARY_CATEGORIES = ["محصولات", "تصاویر و تبلیغات", "کشف و خرید", "محتوا", "ساختار"]

# تعاریف کامل settings-schema هر کلید در چکپوینت‌های ۱۱ تا ۱۴ (بنر/دسته/
# محصول/متن غنی) اضافه می‌شود؛ اینجا فقط استخوان‌بندی allowlist با
# اعتبارسنج‌های placeholder ایمن (رد هر چیز غیر-dict) ثبت می‌شود تا خودِ
# Registry از روز اول قابل‌اعتماد و قابل‌تست باشد.
_BASE_SECTION_REGISTRY: dict[str, SectionDefinition] = {
    "announcement_bar": SectionDefinition(
        key="announcement_bar", label_fa="نوار اعلان", icon="megaphone",
        template_name="storefront_builder/sections/announcement_bar.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="ساختار",
        # پنهان از کتابخانه: تنظیماتِ «نوار اعلان» هدر (متن/فعال‌بودن،
        # همیشه بالای صفحه) همین قابلیت را به‌شکلِ واقعاً قابل‌تنظیم
        # پوشش می‌دهد (نگاه کنید به ``storefront_header_editor``) — این
        # نوعِ section هرگز settings واقعی نداشته (فقط متنِ سخت‌کدشده)،
        # پس امکانِ ساختِ نمونه‌ی جدید از آن گمراه‌کننده است. نمونه‌های
        # قدیمیِ موجود کاملاً دست‌نخورده و کارکردی می‌مانند.
        hidden_from_library=True,
    ),
    "hero_banner": SectionDefinition(
        key="hero_banner", label_fa="اسلایدر اصلی", icon="image",
        template_name="storefront_builder/sections/hero_banner.html",
        validate_settings=_validate_slider_settings, default_settings=default_slider_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="تصاویر و تبلیغات",
        # U4 — Pattern B: ``split`` is a genuinely different renderer partial
        # (text beside the image, not overlaid on it), registered only on
        # ``hero_banner`` (not ``image_slider`` — U4 scopes this to the
        # "hero" primitive). Same real Store-scoped ``HeroSlide`` data either
        # way; ``renderer=None`` (``overlay``) keeps every existing store's
        # exact current template/DOM, unchanged.
        variants=(
            VariantDefinition(key="overlay", label_fa="روی تصویر (پیش‌فرض)"),
            VariantDefinition(key="split", label_fa="متن و تصویر جدا", renderer="storefront_builder/sections/hero_banner_split.html"),
            # Full-width, image-first retail hero with dark editorial copy on
            # light campaign photography. Reuses the same Store HeroSlide data
            # and slider body; only a registered visual class is different.
            VariantDefinition(
                key="beauty_editorial", label_fa="کمپین روشن فروشگاهی",
                renderer="storefront_builder/sections/hero_banner_beauty.html",
            ),
            VariantDefinition(
                key="chocolate_carousel", label_fa="کاروسل فروشگاهی شکلاتی",
                renderer="storefront_builder/sections/hero_banner_chocolate.html",
            ),
            # Editorial atelier hero: up to three real Store HeroSlide images
            # are visible together in tall arch frames, with copy sourced from
            # the first slide. It never embeds reference-site imagery or IDs.
            VariantDefinition(
                key="atelier_triptych", label_fa="سه‌قاب قوسی آتلیه",
                renderer="storefront_builder/sections/hero_banner_atelier.html",
            ),
            VariantDefinition(
                key="luxury_showcase", label_fa="ویترین لوکس تیره",
                renderer="storefront_builder/sections/hero_banner_luxury.html",
            ),
        ),
        default_variant="overlay", variant_setting_key="hero_style",
        settings_schema=HERO_BANNER_SCHEMA,
    ),
    # Site-target-overhaul Part 2B (ibolak reference) — a self-contained
    # campaign hero, deliberately independent of the shared Store-wide
    # ``HeroSlide`` model ``hero_banner``/``image_slider`` read from: that
    # model's content is real merchant data shared across every Ready
    # Template, so restructuring it here would have silently changed the
    # other 7 templates' Home too. This section instead reads its
    # background image from a fixed, versioned static asset (a
    # deterministic Pillow composite of real Rasti Mode Demo product
    # photography — see ``fashion_promo_catalog/campaign_hero.webp`` and
    # the script that produced it) plus editable headline/subtitle/CTA
    # text in its own settings — a genuinely different, reusable
    # registered structural variant any future campaign-style Ready
    # Template may also adopt, never a template-key branch.
    "fashion_lifestyle_hero": SectionDefinition(
        key="fashion_lifestyle_hero", label_fa="هیرو کمپینی (سبک زندگی)", icon="image",
        template_name="storefront_builder/sections/fashion_lifestyle_hero.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, has_settings_form=True,
        category_fa="تصاویر و تبلیغات", page_types=frozenset({PAGE_TYPE_HOME}),
    ),
    "image_slider": SectionDefinition(
        key="image_slider", label_fa="اسلایدر تصویر", icon="images",
        template_name="storefront_builder/sections/image_slider.html",
        validate_settings=_validate_slider_settings, default_settings=default_slider_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="تصاویر و تبلیغات",
        settings_schema=IMAGE_SLIDER_SCHEMA,
    ),
    "single_banner": SectionDefinition(
        key="single_banner", label_fa="بنر تکی", icon="image",
        template_name="storefront_builder/sections/single_banner.html",
        # Task 6 (Group C) disposition: FIXED/STATIC, deliberately. Its
        # render context (``_single_banner_context``) reads only the
        # section-scoped ``PromotionalBanner`` pool (via the existing
        # media CRUD — see "بنرهای همین بخش" in the settings-drawer
        # shortcuts) and ignores ``section.settings`` entirely — it always
        # shows exactly the first active banner. There is no field for a
        # schema to declare; ``_passthrough_dict``/``_empty_defaults``
        # stay exactly as they are, now as an explicit, verified
        # disposition rather than an unclassified placeholder.
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="تصاویر و تبلیغات",
    ),
    "multi_banner": SectionDefinition(
        key="multi_banner", label_fa="ردیف چند بنری", icon="layout-grid",
        template_name="storefront_builder/sections/multi_banner.html",
        # Task 6 (Group C) — the U1A finding above is now resolved: see
        # ``_validate_multi_banner_settings``/``MULTI_BANNER_SCHEMA``.
        # ``has_settings_form`` is deliberately left unset (the legacy
        # drawer stays unreachable, exactly as before) — adding it would
        # also need a real POST-parsing branch in
        # ``storefront_section_settings``, since the legacy view's
        # destructive ``else: raw = {}`` fallback would otherwise wipe
        # these fields on Save (the same class of bug Task 6 Group D fixed
        # for trust_features/amazing_offers/blog_posts); the new R4
        # Inspector path does not depend on ``has_settings_form`` at all,
        # so it is unlocked here with zero legacy-path risk.
        validate_settings=_validate_multi_banner_settings, default_settings=default_multi_banner_settings,
        duplicable=True, removable=True, category_fa="تصاویر و تبلیغات",
        settings_schema=MULTI_BANNER_SCHEMA,
    ),
    "category_grid": SectionDefinition(
        key="category_grid", label_fa="گرید دسته‌بندی", icon="grid",
        template_name="storefront_builder/sections/category_grid.html",
        validate_settings=_validate_category_grid_settings, default_settings=default_category_grid_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
        settings_schema=CATEGORY_GRID_SCHEMA,
        # U1A — نگاشتِ الگویِ A (همان template، شاخه‌زنیِ CSS رویِ همان
        # کلیدِ enum بستهٔ از‌قبل‌موجود ``display_mode``؛ نگاه کنید به
        # CATEGORY_GRID_DISPLAY_MODES بالا و category_grid.html) روی
        # قراردادِ Variant — بدونِ تغییرِ کلیدِ ذخیره‌شده یا ظاهرِ رندرشده.
        variants=(
            VariantDefinition(key="grid", label_fa="گرید"),
            VariantDefinition(key="carousel", label_fa="کاروسل"),
            VariantDefinition(key="circular", label_fa="دایره‌ای"),
            VariantDefinition(key="image_strip", label_fa="نوار تصویری"),
            # Site-target-overhaul Part 2B (ibolak reference) — compact
            # flat rail, own CSS (``.category-fashion-rail``), completely
            # independent of ``image_strip``'s CSS so dense_marketplace
            # (which already uses ``image_strip``) stays unaffected.
            VariantDefinition(key="fashion_flat", label_fa="نوار مسطح کمپینی"),
            # Site-target-overhaul Part 2C (ibolak precision pass) — the
            # reference's SECOND, distinct category moment: a larger
            # post-hero mosaic (own CSS, ``.category-fashion-mosaic``),
            # completely independent of ``fashion_flat``'s rail CSS.
            VariantDefinition(key="fashion_mosaic", label_fa="موزاییک دسته‌بندی"),
            # Beauty retail shortcut rail — square brand-colour media tiles
            # with labels below, matching cosmetics/perfume discovery flows
            # while remaining Store-scoped and reusable.
            VariantDefinition(key="beauty_icons", label_fa="آیکن‌های فروشگاه زیبایی"),
            VariantDefinition(key="chocolate_story", label_fa="هایلایت‌های دایره‌ای شکلاتی"),
            VariantDefinition(key="chocolate_badges", label_fa="میانبرهای تصویری شکلاتی"),
            # Editorial image mosaic — real Store category representative
            # media, bold labels over imagery, no card chrome.
            VariantDefinition(key="atelier_mosaic", label_fa="موزاییک تصویری آتلیه"),
            VariantDefinition(key="luxury_shortcuts", label_fa="میانبرهای لوکس تصویری"),
        ),
        default_variant="grid", variant_setting_key="display_mode",
    ),
    "featured_products": SectionDefinition(
        key="featured_products", label_fa="محصولات ویژه", icon="star",
        template_name="storefront_builder/sections/featured_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "newest_products": SectionDefinition(
        key="newest_products", label_fa="جدیدترین محصولات", icon="sparkles",
        template_name="storefront_builder/sections/newest_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "best_sellers": SectionDefinition(
        key="best_sellers", label_fa="پرفروش‌ترین‌ها", icon="trending-up",
        template_name="storefront_builder/sections/best_sellers.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "discounted_products": SectionDefinition(
        key="discounted_products", label_fa="محصولات تخفیف‌دار", icon="percent",
        template_name="storefront_builder/sections/discounted_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="محصولات",
    ),
    "amazing_offers": SectionDefinition(
        key="amazing_offers", label_fa="پیشنهادهای شگفت‌انگیز", icon="zap",
        template_name="storefront_builder/sections/amazing_offers.html",
        validate_settings=validate_amazing_offers_settings, default_settings=default_amazing_offers_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محصولات",
        settings_schema=AMAZING_OFFERS_SCHEMA,
    ),
    "brand_carousel": SectionDefinition(
        key="brand_carousel", label_fa="کاروسل برندها", icon="award",
        template_name="storefront_builder/sections/brand_carousel.html",
        validate_settings=_validate_brand_carousel_settings, default_settings=default_brand_carousel_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
        # U1A — همان الگویِ A؛ نگاه کنید به BRAND_CAROUSEL_DISPLAY_MODES بالا.
        variants=(
            VariantDefinition(key="grid", label_fa="گرید"),
            VariantDefinition(key="carousel", label_fa="کاروسل"),
            # Flat bordered name/logo cells for beauty and specialty retail.
            # Same Brand records and links; presentation only.
            VariantDefinition(key="beauty_tabs", label_fa="ردیف برندهای فروشگاهی"),
        ),
        default_variant="grid", variant_setting_key="display_mode",
        settings_schema=BRAND_CAROUSEL_SCHEMA,
    ),
    "promo_cards": SectionDefinition(
        key="promo_cards", label_fa="کارت‌های تبلیغاتی", icon="layout",
        template_name="storefront_builder/sections/promo_cards.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        duplicable=True, removable=True, category_fa="تصاویر و تبلیغات",
    ),
    "rich_text": SectionDefinition(
        key="rich_text", label_fa="متن", icon="text",
        template_name="storefront_builder/sections/rich_text.html",
        validate_settings=_validate_rich_text_settings, default_settings=lambda: {"body_html": ""},
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
        description_fa="عنوان، پاراگراف، فهرست و لینک؛ بدون نیاز به دیدن کد HTML.",
        settings_schema=RICH_TEXT_SCHEMA,
    ),
    "image_text": SectionDefinition(
        key="image_text", label_fa="متن و تصویر", icon="image-plus",
        template_name="storefront_builder/sections/image_text.html",
        validate_settings=_validate_image_text_settings,
        default_settings=lambda: {"title": "", "body_html": "", "image_url": "", "image_position": "right"},
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
        description_fa="یک تصویر در کنار عنوان و متن؛ مناسب معرفی، داستان برند و بنر محتوایی.",
        # U4 — formalizes the closed enum ``_validate_image_text_settings``
        # already coerces (Pattern A). No template/behavior change: the
        # renderer already branches on ``image_position`` exactly this way.
        variants=(
            VariantDefinition(key="right", label_fa="تصویر سمت راست"),
            VariantDefinition(key="left", label_fa="تصویر سمت چپ"),
        ),
        default_variant="right", variant_setting_key="image_position",
        settings_schema=IMAGE_TEXT_SCHEMA,
    ),
    "blog_posts": SectionDefinition(
        key="blog_posts", label_fa="مطالب وبلاگ", icon="newspaper",
        template_name="storefront_builder/sections/blog_posts.html",
        validate_settings=validate_blog_posts_settings, default_settings=default_blog_posts_settings,
        max_instances=1, duplicable=False, removable=True, has_settings_form=True, category_fa="محتوا",
        settings_schema=BLOG_POSTS_SCHEMA,
    ),
    "product_section": SectionDefinition(
        key="product_section", label_fa="بخش محصولات", icon="shopping-bag",
        template_name="storefront_builder/sections/product_section.html",
        validate_settings=_validate_product_section_settings, default_settings=_product_section_defaults,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محصولات",
        # U1A — همان الگویِ A؛ نگاه کنید به PRODUCT_SECTION_DISPLAY_MODES بالا.
        variants=(
            VariantDefinition(key="carousel", label_fa="کاروسل"),
            VariantDefinition(key="grid", label_fa="گرید"),
            # Reusable retail campaign composition: a compact promotional
            # rail beside a real product grid.  Copy, products and destination
            # remain section data; the renderer contains no Ready Template key.
            VariantDefinition(key="campaign_band", label_fa="نوار کمپینی کنار محصولات"),
        ),
        default_variant="carousel", variant_setting_key="display_mode",
        settings_schema=PRODUCT_SECTION_SCHEMA,
    ),
    # Site-target-overhaul Part 2D — the generic, ID-free, multi-row
    # merchandising wall (see CATALOG_PRODUCT_WALL_SOURCE_MODES's own
    # docstring above for the full architecture rationale). One instance
    # of this section expands into several real category/collection
    # product rows at render time — never a fixed count of registered
    # section entries, never a Store-specific source_id. Restricted to
    # PAGE_TYPE_HOME: it exists specifically to densify a Ready Template's
    # Home merchandising wall, not a general-purpose block for every page.
    "catalog_product_wall": SectionDefinition(
        key="catalog_product_wall", label_fa="دیوار محصولاتِ فروشگاه", icon="grid",
        template_name="storefront_builder/sections/catalog_product_wall.html",
        validate_settings=_validate_catalog_product_wall_settings,
        default_settings=default_catalog_product_wall_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_HOME}),
        variants=(
            VariantDefinition(key="rows", label_fa="ردیف‌های پی‌درپی"),
            VariantDefinition(
                key="group_columns", label_fa="ستون‌های گروهی فشرده",
                renderer="storefront_builder/sections/catalog_product_wall_group_columns.html",
            ),
            VariantDefinition(
                key="featured_row", label_fa="ردیف پیشنهادی قاب‌دار",
                renderer="storefront_builder/sections/catalog_product_wall_featured_row.html",
            ),
        ),
        default_variant="rows", variant_setting_key="layout_mode",
    ),
    "trust_features": SectionDefinition(
        key="trust_features", label_fa="ردیف اعتماد و ویژگی‌ها", icon="shield-check",
        template_name="storefront_builder/sections/trust_features.html",
        validate_settings=validate_trust_features_settings, default_settings=default_trust_features_settings,
        max_instances=1, duplicable=False, removable=True, has_settings_form=True, category_fa="ساختار",
    ),
    # -------------------------------------------------- چکپوینتِ ۱۲: بخش‌های جدید
    "collection_tiles": SectionDefinition(
        key="collection_tiles", label_fa="کارت‌های کالکشن", icon="layers",
        template_name="storefront_builder/sections/collection_tiles.html",
        validate_settings=_validate_collection_tiles_settings, default_settings=default_collection_tiles_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
        # U4 — Pattern A, same convention as category_grid/brand_carousel:
        # same template, CSS branches on ``tile_style``.
        variants=(
            VariantDefinition(key="grid", label_fa="گرید"),
            VariantDefinition(key="carousel", label_fa="کاروسل"),
        ),
        default_variant="grid", variant_setting_key="tile_style",
        settings_schema=COLLECTION_TILES_SCHEMA,
    ),
    "quick_links": SectionDefinition(
        key="quick_links", label_fa="دسترسی سریع", icon="compass",
        template_name="storefront_builder/sections/quick_links.html",
        validate_settings=_validate_quick_links_settings, default_settings=default_quick_links_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="کشف و خرید",
        settings_schema=QUICK_LINKS_SCHEMA,
    ),
    "faq": SectionDefinition(
        key="faq", label_fa="سوالات متداول", icon="help-circle",
        template_name="storefront_builder/sections/faq.html",
        validate_settings=_validate_faq_settings, default_settings=default_faq_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    "testimonials": SectionDefinition(
        key="testimonials", label_fa="نظرات مشتریان", icon="message-circle",
        template_name="storefront_builder/sections/testimonials.html",
        validate_settings=_validate_testimonials_settings, default_settings=default_testimonials_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
    ),
    "video_section": SectionDefinition(
        key="video_section", label_fa="بخش ویدیو", icon="play-circle",
        template_name="storefront_builder/sections/video_section.html",
        validate_settings=_validate_video_section_settings, default_settings=default_video_section_settings,
        duplicable=True, removable=True, has_settings_form=True, category_fa="محتوا",
        settings_schema=VIDEO_SECTION_SCHEMA,
    ),
    # -------------------------------------------------- Story Rail (بخشِ مشترکِ اختیاری)
    "story_rail": SectionDefinition(
        key="story_rail", label_fa="ریلِ استوری", icon="circle",
        template_name="storefront_builder/sections/story_rail.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="کشف و خرید",
    ),
    # -------------------------------------------------- Phase 3: کتابخانه‌ی بلوک‌های صفحه اصلی
    "newsletter": SectionDefinition(
        key="newsletter", label_fa="خبرنامه", icon="mail",
        template_name="storefront_builder/sections/newsletter.html",
        validate_settings=_validate_newsletter_settings, default_settings=default_newsletter_settings,
        # یک بلوکِ ثبتِ ایمیلِ سراسری کافی‌ست — مثلِ trust_features/
        # story_rail، تکرارِ آن (دو فرمِ مستقل روی یک صفحه) گیج‌کننده است.
        max_instances=1, duplicable=False, removable=True, has_settings_form=True, category_fa="محتوا",
        settings_schema=NEWSLETTER_SCHEMA,
    ),
    # -------------------------------------------------- Phase 5: بخش‌های context-aware صفحه محصول
    # هر چهار نوعِ زیر فقط رویِ product_detail قابل‌افزودن‌اند (page_types)
    # و بدونِ تنظیماتِ واقعی هستند (passthrough) — داده‌شان همیشه از
    # ``page_context``ی که ویوِ مسیر پاس می‌دهد resolve می‌شود، هرگز از
    # یک ID ذخیره‌شده در settings؛ نگاه کنید به
    # ``render_service._CONTEXT_AWARE_BUILDERS``.
    "product_main": SectionDefinition(
        key="product_main", label_fa="گالری و خرید محصول", icon="shopping-bag",
        template_name="storefront_builder/sections/product_main.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # گالری/قیمت/انتخابِ تنوع/افزودن‌به‌سبد یک کامپوننتِ Alpine واحد
        # است (``x-data="variantSelector(...)"``) — تجزیه‌ی آن به
        # section‌های کوچک‌تر اسکوپِ آن کامپوننت را می‌شکست؛ حذفِ کاملِ آن
        # هم یعنی صفحه‌ی محصول هیچ راهی برایِ خرید ندارد، پس removable=False
        # (دقیقاً همان استدلالِ ``show_cart`` در هدر).
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    "product_description": SectionDefinition(
        key="product_description", label_fa="توضیحات، مشخصات و نظرات", icon="text",
        template_name="storefront_builder/sections/product_description.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # سه‌تب (توضیحات/مشخصات/نظرات) یک کامپوننتِ Alpine مشترک
        # (``x-data="{ tab: 'desc' }"``) هستند — طبقِ الزامِ صریحِ کار
        # («prefer sensible compositional primitives... may remain one
        # structured block»)، یک بلوکِ واحد می‌مانند، نه سه section جدا.
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    "product_video": SectionDefinition(
        key="product_video", label_fa="ویدئوهای محصول", icon="play-circle",
        template_name="storefront_builder/sections/product_video.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    "related_products": SectionDefinition(
        key="related_products", label_fa="محصولات مرتبط", icon="grid",
        template_name="storefront_builder/sections/related_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_PRODUCT_DETAIL}),
    ),
    # -------------------------------------------------- Phase 5: بخشِ context-aware صفحه لیست/جستجو
    "product_listing": SectionDefinition(
        key="product_listing", label_fa="فیلتر و گرید محصولات", icon="shopping-bag",
        template_name="storefront_builder/sections/product_listing.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # همان دلیلِ product_main: بدونِ این بلوک صفحه‌یِ لیست/جستجو هیچ
        # راهی برایِ دیدنِ کالاها ندارد.
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_LISTING, PAGE_TYPE_SEARCH}),
    ),
    # -------------------------------------------------- Phase 5: بخش‌های context-aware صفحه کالکشن
    "collection_header": SectionDefinition(
        key="collection_header", label_fa="عنوان و توضیح کالکشن", icon="layers",
        template_name="storefront_builder/sections/collection_header.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=True, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_COLLECTION}),
    ),
    "collection_products": SectionDefinition(
        key="collection_products", label_fa="محصولات کالکشن", icon="grid",
        template_name="storefront_builder/sections/collection_products.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_COLLECTION}),
    ),
    # -------------------------------------------------- Phase 5: بخش‌های context-aware صفحه سبد خرید
    "cart_items": SectionDefinition(
        key="cart_items", label_fa="قلم‌های سبد خرید", icon="shopping-cart",
        template_name="storefront_builder/sections/cart_items.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # همان استدلالِ product_main: بدونِ این بلوک سبدِ خرید هیچ راهی
        # برایِ دیدن/ویرایشِ قلم‌ها ندارد.
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_CART}),
    ),
    "cart_summary": SectionDefinition(
        key="cart_summary", label_fa="خلاصه سفارش و تسویه‌حساب", icon="receipt",
        template_name="storefront_builder/sections/cart_summary.html",
        validate_settings=_passthrough_dict, default_settings=_empty_defaults,
        # حذفِ این بلوک یعنی مشتری راهی برایِ رفتن به تسویه‌حساب ندارد —
        # دقیقاً همان استدلالِ show_cart در هدر.
        max_instances=1, duplicable=False, removable=False, category_fa="محصولات",
        page_types=frozenset({PAGE_TYPE_CART}),
    ),
}


#: U1A — نگاشتِ نامِ capability به allowlistِ موجودش؛ فقط برایِ استنتاجِ
#: ``SectionDefinition.capabilities`` در ``_finalize_registry`` استفاده
#: می‌شود. این allowlistها خودشان **حذف نمی‌شوند** و کدِ فعلیِ
#: ادیتور/ویو همچنان مستقیماً از خودِ آن‌ها می‌خواند (طبقِ الزامِ صریحِ
#: کار: «preserve current runtime/editor behavior») — این نگاشت فقط یک
#: آینه‌یِ اضافی می‌سازد تا آزمونِ سازگاری (تستِ زیر) بتواند دو منبع را
#: با هم مقایسه کند، و مسیرِ آینده به‌سویِ «SectionDefinition.capabilities
#: تنها منبعِ حقیقت» باز بماند.
_DERIVED_CAPABILITY_SOURCES: tuple[tuple[str, frozenset[str]], ...] = (
    ("card", CARD_AWARE_SECTION_KEYS),
    ("background", BACKGROUND_AWARE_SECTION_KEYS),
    ("spacing", SPACING_AWARE_SECTION_KEYS),
    ("motion", MOTION_AWARE_SECTION_KEYS),
    ("destination", DESTINATION_AWARE_SECTION_KEYS),
    ("layout_width", LAYOUT_WIDTH_AWARE_SECTION_KEYS),
    ("layout_height", LAYOUT_HEIGHT_AWARE_SECTION_KEYS),
    ("columns", COLUMN_AWARE_SECTION_KEYS),
    ("columns_visual", COLUMN_VISUAL_SECTION_KEYS),
)


def _derived_capabilities(section_key: str) -> frozenset[str]:
    """``capabilities``یِ استنتاج‌شده از allowlistهایِ موجود — ``"responsive"``
    برایِ همه‌ی کلیدها حاضر است چون ``_with_responsive`` بدونِ استثنا رویِ
    همه اعمال می‌شود (نگاه کنید به حلقه‌ی پایین)."""
    caps = {"responsive"}
    for name, keys in _DERIVED_CAPABILITY_SOURCES:
        if section_key in keys:
            caps.add(name)
    return frozenset(caps)


def _with_variant_validation(definition: SectionDefinition, validate_fn):
    """U1B1 §5 — the smallest central write-time validation entry point for
    the generic Variant contract. A pure no-op (returns ``validate_fn``
    completely unwrapped) for the 31 section types with no registered
    ``variants`` — zero added closure/overhead for the common case.

    For a definition WITH variants, wraps ``validate_fn`` so
    ``variant_contract.validate_variant_selection`` runs *after* the
    section's own ``validate_settings`` has already produced its fully
    cleaned dict — never before, and never in place of it. This ordering is
    what makes the wrapper provably backwards-compatible with the three
    proven precedents: their own validators (``_validate_category_grid_settings``
    and siblings) already coerce an invalid ``display_mode`` to a valid one
    *before* this wrapper ever sees the value, so the check below can never
    fire differently for them than it did before U1B1 — it is a redundant,
    inert safety net for those three, and the actual enforcement mechanism
    for any future section that declares ``variants``/``variant_setting_key``
    without its own closed-enum validator. This is intentionally the ONE
    place this rule is enforced — not duplicated into any view/form."""
    if not definition.variants:
        return validate_fn

    def wrapped_validate(raw):
        cleaned = validate_fn(raw)
        if isinstance(cleaned, dict):
            validate_variant_selection(definition, cleaned)
        return cleaned

    return wrapped_validate


def _finalize_registry(base: dict[str, SectionDefinition]) -> dict[str, SectionDefinition]:
    """هر ۱۷ تعریفِ بالا را با پشتیبانیِ ``responsive`` می‌پوشاند و
    ``has_settings_form`` را یکنواخت True می‌کند (فازِ D) — منطقِ
    اختصاصیِ هر نوع (rich_text/image_text/product_section/passthrough)
    در ``_BASE_SECTION_REGISTRY`` بالا کاملاً دست‌نخورده می‌ماند؛ این تابع
    فقط یک لایه‌یِ یکسان روی همه می‌کشد، نه بازنویسیِ تک‌تکِ ۱۷ ورودی.

    U1A: علاوه‌براین، ``capabilities``یِ صریحِ هر تعریف (اگر بود) با
    ``_derived_capabilities`` اجتماع می‌شود (نه جایگزین) و
    ``variants``/``default_variant`` (اگر تعریف شده) اعتبارسنجی می‌شود —
    هیچ‌کدام رفتارِ ``validate_settings``/``default_settings``/رندر را
    تغییر نمی‌دهد.

    U1B1: ``_with_variant_validation`` به‌عنوانِ بیرونی‌ترین لایه اضافه
    می‌شود — یعنی پس از تمامِ لایه‌هایِ بالا (که کلیدهایِ خودشان را
    strip/دوباره اضافه می‌کنند) اجرا می‌شود و رویِ dictِ کاملاً پاک‌شده
    کار می‌کند، نه رویِ ورودیِ خام."""
    finalized = {}
    for key, definition in base.items():
        validate_variants(definition.variants, default_variant=definition.default_variant)
        validate_fn, default_fn = _with_resource_source(key, definition.validate_settings, definition.default_settings)
        validate_fn, default_fn = _with_destination(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_responsive(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_motion(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_card(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_layout(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_background(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_spacing(key, validate_fn, default_fn)
        validate_fn, default_fn = _with_appearance_overrides(key, validate_fn, default_fn)
        validate_fn = _with_variant_validation(definition, validate_fn)
        finalized[key] = dataclasses.replace(
            definition, validate_settings=validate_fn, default_settings=default_fn, has_settings_form=True,
            capabilities=definition.capabilities | _derived_capabilities(key),
        )
    return finalized


SECTION_REGISTRY: dict[str, SectionDefinition] = _finalize_registry(_BASE_SECTION_REGISTRY)


class UnknownSectionTypeError(ValueError):
    def __init__(self, section_key: str):
        super().__init__(f"نوع بخش «{section_key}» در Section Registry ثبت نشده است")
        self.section_key = section_key


def get_definition(section_key: str) -> SectionDefinition:
    """تعریف یک section را برمی‌گرداند؛ اگر کلید نامعتبر باشد رد می‌کند.

    این تنها نقطه‌ورودی مجاز برای resolve کردن یک section_key به template
    است — هرگز مستقیماً از ``SECTION_REGISTRY`` در سرویس‌ها/ویوها resolve
    نکنید، همیشه از این تابع عبور کنید تا کلید ناشناخته همیشه fail-closed رد شود.
    """
    try:
        return SECTION_REGISTRY[section_key]
    except KeyError:
        raise UnknownSectionTypeError(section_key) from None


def list_definitions() -> list[SectionDefinition]:
    return list(SECTION_REGISTRY.values())


def list_library_groups(page_type: str | None = None) -> list[tuple[str, list[SectionDefinition]]]:
    """کتابخانه‌ی «افزودن بخش جدید» (چکپوینتِ ۱۰)، گروه‌بندی‌شده در پنج
    دسته‌ی کسب‌وکاریِ ثابت (``SECTION_LIBRARY_CATEGORIES``) — نوع‌هایِ
    ``hidden_from_library`` هرگز اینجا ظاهر نمی‌شوند (نمونه‌های موجودشان
    هم‌چنان از ``list_definitions()`` کامل resolve می‌شوند). گروه‌هایِ
    خالی حذف می‌شوند تا هرگز یک آکاردئونِ بی‌محتوا نشان داده نشود.

    Phase 5: اگر ``page_type`` داده شود، فقط انواعی که ``page_types``شان
    شاملِ آن صفحه است نمایش داده می‌شوند (مثلاً ``product_main`` هرگز در
    کتابخانه‌ی صفحه‌یِ Cart دیده نمی‌شود) — این فقط لایه‌ی UI است؛ رد
    واقعیِ ترکیبِ نامعتبر همیشه سمتِ سرور در ``is_section_allowed_on_page``
    انجام می‌شود، نه اینجا."""
    groups: list[tuple[str, list[SectionDefinition]]] = []
    for category in SECTION_LIBRARY_CATEGORIES:
        members = [
            d for d in SECTION_REGISTRY.values()
            if d.category_fa == category and not d.hidden_from_library
            and (page_type is None or page_type in d.page_types)
        ]
        if members:
            groups.append((category, members))
    return groups


def is_valid_section_key(section_key: str) -> bool:
    return section_key in SECTION_REGISTRY


def is_section_allowed_on_page(section_key: str, page_type: str) -> bool:
    """تکِ نقطه‌ی ورودیِ اجباریِ سمتِ سرور برایِ اعتبارسنجیِ ترکیبِ
    section/page — Phase 5. کلیدِ ناشناخته همیشه ``False`` برمی‌گرداند
    (fail-closed)، نه پرتاب کردنِ خطا؛ فراخوان (``storefront_section_add``)
    خودش پیش از این تابع کلیدِ نامعتبر را جدا رد می‌کند."""
    definition = SECTION_REGISTRY.get(section_key)
    if definition is None:
        return False
    return page_type in definition.page_types
