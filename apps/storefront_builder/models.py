"""مدل‌های سازنده بصری صفحه فروشگاه — معماری هیبرید (سند نسخه‌بندی‌شده + ارجاع نرمال‌شده).

این معماری دقیقاً مطابق گزینه C توصیه‌شده در
``docs/reports/STOREFRONT_VISUAL_BUILDER_AUDIT.md`` (بخش ۱۰) است و
تصمیمات باز آن گزارش (بخش ۳۲) به این صورت حل شده‌اند:

- هدر، فوتر و بخش‌های صفحه اصلی همگی به یک ``StorefrontLayoutVersion``
  واحد تعلق دارند و یک چرخه‌ی واحدِ Draft/Preview/Publish را به اشتراک
  می‌گذارند (نه یک سیستم نسخه‌بندی جدا برای هدر/فوتر).
- بازگردانی یک نسخه‌ی قدیمی هرگز مستقیماً منتشر نمی‌شود؛ همیشه یک
  Draft جدید می‌سازد (سرویس ``layout_service.restore_version``).
- پرچم فعال‌سازی تدریجی per-store (``uses_visual_storefront_layout``)
  عمداً روی خودِ ``StorefrontLayout`` قرار گرفته، نه روی ``Store`` —
  مدل ``Store`` طبق ADR مستندشده در ``apps/stores/models.py`` عمداً
  حداقلی نگه داشته می‌شود (بدون فیلد تم/ویژگی)؛ این پرچم دقیقاً همان
  الگوی ``ShopSettings``/``FooterSettings`` را دنبال می‌کند: یک مدل
  تنظیمات جداگانه به‌ازای هر Store، نه فیلد مستقیم روی Store.
- نوع هر بخش (``section_key``) در دیتابیس allowlist نمی‌شود؛ اعتبارسنجی
  در برابر Section Registry (``apps/storefront_builder/section_registry.py``)
  همیشه در لایه سرویس انجام می‌شود — مطابق قرارداد کل کدبیس که
  اعتبارسنجی JSONField را همیشه در سرویس انجام می‌دهد نه در ``clean()``.
"""

import hashlib
import json
import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel

#: کلیدهای toggle هدر/فوتر و مقادیر پیش‌فرض‌شان — تک‌منبع حقیقت، هم برای
#: فرم‌های ویرایشگر (views.py) و هم برای رندر (preview/صفحه عمومی). اینجا
#: تعریف شده‌اند (نه فقط در views.py) دقیقاً برای اینکه
#: ``StorefrontLayoutVersion.effective_header_config``/``effective_footer_config``
#: همیشه یک دیکشنری کاملاً پر برگردانند — هرگز کلید ناقص، تا در تمپلیت‌ها
#: هرگز نیازی به ``|default:True`` (که مقدار صریح ``False`` را هم به اشتباه
#: falsy می‌گیرد و override می‌کند) نباشد.
HEADER_TOGGLE_FIELDS = ["show_search", "show_account", "show_cart", "show_wishlist", "sticky", "announcement_enabled"]

#: زیرمجموعه‌یِ HEADER_TOGGLE_FIELDS که «نمایش در دستگاه‌ها» (Phase 4)
#: برایشان معنا دارد — عمداً یک allowlist صریح، نه همه‌یِ ۶ فیلد:
#: ``show_cart`` عمداً کنار گذاشته شده چون ``validate_header_config``
#: از قبل تضمین می‌کند سبد خرید هرگز از هدر غیرقابل‌دسترس نشود (تنها
#: مسیرِ فعلیِ سبد خرید)؛ اجازه‌دادن به «پنهان در موبایل» دقیقاً همان
#: نقضِ همان قانون را از یک لایه‌ی دیگر ممکن می‌کرد. ``sticky`` هم یک
#: رفتار است نه یک المانِ قابل‌مشاهده‌یِ مستقل، پس «نمایش در دستگاه‌ها»
#: برایش بی‌معناست.
HEADER_RESPONSIVE_AWARE_KEYS = ["show_search", "show_account", "show_wishlist", "announcement_enabled"]

#: پیش‌فرضِ «نمایش در دستگاه‌ها»یِ هر کامپوننتِ هدر — همیشه نمایان
#: (دقیقاً معادلِ رفتارِ قبل از Phase 4، برایِ نسخه‌هایی که هنوز این
#: بلوک را ندارند). فقط تبلت/موبایل — دسکتاپ همیشه خط‌مبناست (نگاه
#: کنید به ``STOREFRONT_BUILDER_V2_PHASE_4_AUDIT.md``، بخش ۱۳).
HEADER_RESPONSIVE_DEFAULTS = {
    key: {"hide_on_tablet": False, "hide_on_mobile": False} for key in HEADER_RESPONSIVE_AWARE_KEYS
}

#: Phase 8 P0-3 — بلوک‌هایِ اختیاریِ قابل‌افزودن/حذف/بازچینیِ ردیفِ اصلیِ
#: هدر (تلفن/شبکه‌ی اجتماعی/دکمه‌ی CTA/فاصله) — علاوه بر ۴ آیکونِ ثابتِ
#: بالا (جستجو/حساب/علاقه‌مندی/سبد)، نه جایگزینِ آن‌ها. هر مورد یک
#: دیکشنری با کلیدِ ``type`` (از ``HEADER_EXTRA_BLOCK_TYPES`` در
#: layout_service.py) است؛ ``cta`` علاوه‌بر آن ``label``/``url`` هم دارد.
ANNOUNCEMENT_LINK_DEFAULTS = (
    {"label": "پیگیری سفارش", "url": "#"},
    {"label": "سوالات متداول", "url": "#"},
)

HEADER_CONFIG_DEFAULTS = (
    {f: True for f in HEADER_TOGGLE_FIELDS}
    | {
        "announcement_text": "",
        "announcement_links": ANNOUNCEMENT_LINK_DEFAULTS,
        "announcement_show_phone": True,
        "responsive": HEADER_RESPONSIVE_DEFAULTS,
        "extra_blocks": [],
        #: U2A — کدامیک از ۵ Variantِ ثبت‌شده‌یِ ``global_region_registry
        #: .GLOBAL_HEADER_REGION`` باید رندر شود؛ پیش‌فرض دقیقاً همان
        #: کلیدِ ``default_variant``ی آن Region است (``"legacy_default"``)
        #: — یعنی نسخه‌هایِ قدیمی/بدونِ این کلید دقیقاً همان هدرِ فعلی را
        #: بدونِ کوچک‌ترین تغییرِ بصری می‌بینند (نگاه کنید به
        #: ``effective_header_config`` پایین — merge با این پیش‌فرض،
        #: نه یک مهاجرتِ دیتابیسی).
        "header_variant": "legacy_default",
    }
)

FOOTER_TOGGLE_FIELDS = [
    "show_about", "show_contact", "show_quick_links", "show_categories",
    "show_social", "show_trust_badges", "show_payment_logos", "show_newsletter", "show_copyright",
]

#: برخلافِ هدر، همه‌یِ ۹ بخشِ فوتر کاندیدِ معقولِ «نمایش در دستگاه‌ها»
#: هستند — هیچ‌کدام مثلِ سبدِ خرید تنها مسیرِ دسترسی به یک قابلیتِ
#: حیاتی نیستند (``validate_footer_config`` همچنان تضمین می‌کند خودِ
#: toggleِ سطحِ بالا نمی‌تواند همه‌شان را همزمان خاموش کند؛ این بلوک
#: فقط نمایش/عدمِ‌نمایشِ per-device را کنترل می‌کند، نه فعال/غیرفعالِ
#: کلی).
FOOTER_RESPONSIVE_AWARE_KEYS = list(FOOTER_TOGGLE_FIELDS)

FOOTER_RESPONSIVE_DEFAULTS = {
    key: {"hide_on_tablet": False, "hide_on_mobile": False} for key in FOOTER_RESPONSIVE_AWARE_KEYS
}

#: Phase 8 P0-4 — ستون‌هایِ اضافیِ قابل‌افزودن/حذف/بازچینیِ فوتر (متنِ
#: دلخواه/لینکِ تکی/شبکه‌ی اجتماعیِ تکراری) — علاوه بر ۹ بخشِ ثابتِ بالا،
#: نه جایگزینِ آن‌ها. هر مورد یک دیکشنری با کلیدِ ``type`` (از
#: ``FOOTER_EXTRA_BLOCK_TYPES`` در layout_service.py) است.
FOOTER_CONFIG_DEFAULTS = (
    {f: True for f in FOOTER_TOGGLE_FIELDS}
    | {
        "responsive": FOOTER_RESPONSIVE_DEFAULTS, "extra_blocks": [],
        #: U2B — کدامیک از ۵ Variantِ ثبت‌شده‌یِ ``global_region_registry
        #: .GLOBAL_FOOTER_REGION`` باید رندر شود؛ پیش‌فرض دقیقاً همان
        #: کلیدِ ``default_variant``ی آن Region است (``"legacy_default"``)
        #: — یعنی نسخه‌هایِ قدیمی/بدونِ این کلید دقیقاً همان فوترِ فعلی را
        #: بدونِ کوچک‌ترین تغییرِ بصری می‌بینند (نگاه کنید به
        #: ``effective_footer_config`` پایین — merge با این پیش‌فرض،
        #: نه یک مهاجرتِ دیتابیسی؛ دقیقاً همان الگویِ ``header_variant``یِ
        #: U2A در ``HEADER_CONFIG_DEFAULTS``).
        "footer_variant": "legacy_default",
        #: Mobile-only persistent storefront navigation. ``hidden`` preserves
        #: every existing Store until a Ready Template or merchant explicitly
        #: opts into a registered mobile-navigation variant.
        "mobile_nav_variant": "hidden",
    }
)

#: کلیدهایِ رنگِ توکنِ ظاهر — دقیقاً همان مجموعه‌ای که ``tokens.css``ی
#: موجود از قبل به‌عنوانِ ``--brand-*`` مصرف می‌کند (audit شده قبل از
#: نهایی‌کردن؛ نگاه کنید به گزارشِ ممیزی، بخشِ «Site Appearance»)، به‌علاوه
#: ``border`` که امروز فقط derived است (``mix_hex(text, surface)``) و
#: اینجا برایِ اولین‌بار به یک توکنِ قابلِ‌override واقعی تبدیل می‌شود.
APPEARANCE_COLOR_KEYS = ["primary", "secondary", "accent", "background", "surface", "text", "muted", "border"]

#: پیش‌فرض‌هایِ ظاهر — عمداً دقیقاً برابرِ مقادیرِ پیش‌فرضِ فعلیِ
#: ``ShopSettings`` (``apps/core/models.py``) هستند تا فروشگاه‌هایی که
#: هنوز به سیستمِ ظاهرِ نسخه‌بندی‌شده دست نزده‌اند، هیچ تغییرِ بصری‌ای
#: نبینند — دقیقاً همان الزامِ سازگاریِ کاملِ با گذشته که برایِ
#: header_config/footer_config هم رعایت شده.
APPEARANCE_CONFIG_DEFAULTS = {
    "template_slug": "modern",
    "palette_slug": None,
    "color_overrides": {},
    # Part 2B (ibolak Home rebuild) — distinguishes a genuine merchant color
    # edit from ``bootstrap_service.bootstrap_appearance_config``'s
    # migration-safety mirror of a Store's live ShopSettings colors into
    # ``color_overrides`` at first-Draft-creation. ``False`` means whatever
    # is in ``color_overrides`` (if anything) is that bootstrap carryover,
    # not a deliberate choice made in this editor — so an explicit Ready
    # Template apply/reset is free to clear it and let the template's own
    # palette actually render. Flipped to ``True`` only by the dashboard's
    # own color-editing view, the moment the merchant sets a real override
    # that differs from the active palette (see ``views.py``). Never reset
    # to ``False`` automatically — only a merchant action does that
    # (resetting all colors, or an explicit palette switch there).
    "color_overrides_customized": False,
    # Overrideهای نقش‌های ناحیه‌ای (هدر/منو/کارت/فوتر/قیمت).
    # داخل همان JSON نسخه ذخیره می‌شود؛ Model field جدید و migration ندارد.
    "theme_overrides": {},
    "font": "Vazirmatn",
    "radius": 18,
    "button_radius": 12,
    "density": "normal",
    "motion": "subtle",
    "type_scale": "normal",
    "button_style": "filled",
    "image_fit": "cover",
    "image_hover": "zoom",
    # تنظیماتِ مستقلِ تصویرِ کارتِ محصول (تصمیمِ مالک: crossfade و zoom
    # باید مستقل باشند — یکی دیگری را فعال/غیرفعال نمی‌کند):
    "card_image_crossfade": False,   # نمایشِ تصویرِ دوم هنگامِ hover
    "card_image_zoom": True,         # بزرگ‌نماییِ تصویر هنگامِ hover
    # Phase 7: family_slug/preset_slug (سیستمِ منجمدِ Family/Legacy-Preset)
    # از اینجا حذف شده‌اند — دیگر هیچ اثرِ رندریِ فعالی نداشتند؛ نگاه
    # کنید به docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md.
    # Phase 6: کلیدِ آخرین Preset ساختاریِ V2 اعمال‌شده (``layout_preset_registry``)
    # — کاملاً مستقل از ``family_slug``/``preset_slug`` بالا (سیستمِ منجمدِ
    # قدیمی). فقط برایِ نمایش «کدام Preset فعال است» در ادیتور و
    # idempotency؛ اعمالِ دوباره‌ی همان Preset هیچ محدودیتی ندارد و مرچنت
    # پس از اعمال هنوز کاملاً آزاد است هر بخش را دستی تغییر دهد — این
    # کلید صرفاً یک برچسبِ آخرین‌اعمال‌شده است، نه یک قفل.
    "layout_preset_key": None,
}


class StorefrontLayout(TimeStampedModel):
    """لنگر یک‌به‌یک هر فروشگاه — اشاره‌گر به نسخه‌ی منتشرشده و نسخه‌ی پیش‌نویس.

    انتشار یک عملیات اتمیک است چون فقط همین اشاره‌گرها عوض می‌شوند؛
    محتوای خودِ نسخه از قبل کامل و معتبر است (بخش ۱۴ گزارش ممیزی).
    """

    store = models.OneToOneField(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="storefront_layout",
    )
    uses_visual_storefront_layout = models.BooleanField(
        "استفاده از سازنده بصری", default=False,
        help_text="تا وقتی این فروشگاه اولین نسخه را منتشر نکرده، صفحه اصلی قدیمی (hard-coded) بدون تغییر رندر می‌شود.",
    )
    published_version = models.ForeignKey(
        "StorefrontLayoutVersion", verbose_name="نسخه منتشرشده",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    draft_version = models.ForeignKey(
        "StorefrontLayoutVersion", verbose_name="نسخه پیش‌نویس",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    r4_editor_enabled = models.BooleanField(
        default=False,
        help_text="Feature gate for the R4 storefront-builder editor shell.",
    )

    class Meta:
        verbose_name = "چیدمان صفحه فروشگاه"
        verbose_name_plural = "چیدمان‌های صفحه فروشگاه"

    def __str__(self):
        return f"چیدمان {self.store.name}"

    @classmethod
    def provision_for(cls, store) -> "StorefrontLayout":
        """رکورد ``StorefrontLayout`` یک Store را می‌سازد؛ اگر از قبل وجود
        داشته باشد دست‌نخورده برمی‌گردد (idempotent) — همان قرارداد
        ``ShopSettings.provision_for``/``FooterSettings.provision_for``."""
        obj, _ = cls.objects.get_or_create(store=store)
        return obj


class StorefrontLayoutVersion(TimeStampedModel):
    """یک نسخه‌ی immutable-پس‌از-انتشار از کل چیدمان (هدر + فوتر + بخش‌ها).

    الگوی نسخه‌بندی دقیقاً مطابق جفت ``IndustryTemplate``/``StoreTemplateUpdate``
    (تنها الگوی rollback-capable موجود در کدبیس پیش از این کار) است:
    هر نسخه پس از publish هرگز mutate نمی‌شود؛ ویرایش بعدی یعنی ساخت
    یک نسخه Draft جدید.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"
        ARCHIVED = "archived", "بایگانی‌شده"

    class Source(models.TextChoices):
        MANUAL = "manual", "ویرایش دستی"
        LEGACY_BOOTSTRAP = "legacy_bootstrap", "برخاسته از صفحه اصلی قدیمی"
        INDUSTRY_TEMPLATE = "industry_template", "قالب صنعتی"
        RESTORED = "restored", "بازگردانی از نسخه قبلی"

    layout = models.ForeignKey(
        StorefrontLayout, verbose_name="چیدمان", on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField("شماره نسخه")
    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT,
    )
    source = models.CharField(
        "منشأ", max_length=20, choices=Source.choices, default=Source.MANUAL,
    )
    label = models.CharField("برچسب", max_length=150, blank=True)

    header_config = models.JSONField("پیکربندی هدر", default=dict, blank=True)
    footer_config = models.JSONField("پیکربندی فوتر", default=dict, blank=True)
    appearance_config = models.JSONField(
        "پیکربندی ظاهر", default=dict, blank=True,
        help_text=(
            "قالب/پالت/فونت/گردی/تراکم/حرکت — دقیقاً همان الگویِ header_config/"
            "footer_config (JSON روی خودِ نسخه) تا تغییراتِ ظاهری هم از همان "
            "چرخه‌ی Draft/Preview/Publish/Restore عبور کنند، نه یک مسیرِ زنده‌ی جدا."
        ),
    )

    content_fingerprint = models.CharField(
        "اثر انگشت محتوا", max_length=64, blank=True,
        help_text="هش SHA-256 محتوای سریالایز‌شده — برای تشخیص drift.",
    )
    template_provenance = models.JSONField(
        "منشأِ Ready Template", default=dict, blank=True,
        help_text=(
            "U7 — شکلِ ``variant_contract.build_template_provenance`` (کلید/نسخه‌یِ "
            "Ready Templateای که آخرین‌بار روی این Draft اعمال شده — نگاه کنید به "
            "``preset_service.apply_preset``). دیکشنریِ خالی یعنی «هرگز یک Ready "
            "Template اعمال نشده» (فروشگاه‌هایِ قدیمی/Draftهایِ دستی) — یک حالتِ "
            "کاملاً معتبر، نه یک خطا."
        ),
    )
    template_baseline_snapshot = models.JSONField(
        "عکسِ Baselineِ Ready Template", default=dict, blank=True,
        help_text=(
            "Acceptance Batch 2 (post-U11) — عکسِ نرمال‌شده و immutable از "
            "دقیقاً همان baselineِ Ready Templateای که در لحظه‌یِ اعمال، واقعاً "
            "روی این Draft نوشته شد (پالتِ پیش‌فرض، appearance/header/footerِ "
            "نهایی‌شده، ترکیبِ هر صفحه با کلیدِ اسلاتِ پایدارِ هر section) — "
            "نگاه کنید به ``preset_service.apply_preset``/``build_template_baseline_snapshot``. "
            "برخلافِ ``template_provenance`` (فقط کلید/نسخه)، بازنشانی از رویِ "
            "این فیلد هرگز به تعریفِ *فعلیِ* Presetِ همان کلید در Registry "
            "وابسته نیست — حتی اگر آن تعریفِ پایتونی بعداً (بدونِ افزایشِ "
            "نسخه) تغییر کند، این عکس دقیقاً همان چیزی می‌ماند که مرچنت واقعاً "
            "انتخاب کرده بود. دیکشنریِ خالی (پیش‌فرض) یعنی «این نسخه هرگز یک "
            "Ready Template اعمال‌شده ندارد، یا قبل از این Batch ساخته شده و "
            "فقط ``template_provenance``یِ قدیمی را دارد» — یک حالتِ کاملاً "
            "معتبر و سازگار با گذشته (نگاه کنید به مسیرِ جایگزینِ "
            "``reset_storefront_to_baseline`` برایِ این حالت)، نه یک خطا. "
            "هرگز مسیرِ فایلِ renderer را ذخیره نمی‌کند — فقط کلیدهایِ پایدارِ "
            "Registry و پیکربندیِ نرمال‌شده."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ایجادکننده",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)
    edit_revision = models.PositiveBigIntegerField(
        default=0,
        help_text="Monotonic optimistic-concurrency token for Draft mutations.",
    )

    class Meta:
        verbose_name = "نسخه چیدمان"
        verbose_name_plural = "نسخه‌های چیدمان"
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["layout", "version_number"],
                name="storefront_layout_version_unique_number_per_layout",
            ),
        ]

    def __str__(self):
        return f"نسخه {self.version_number} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        """Phase 1A (تصمیمِ مالک، «Page Creation For New Versions»): این
        override تنها نقطه‌یِ *واقعاً* مرکزیِ ساختِ صفحات است — الزامِ
        صریحِ کار می‌گوید «Centralize this behavior. Do NOT scatter
        page-creation logic across views»، و بهترین راهِ تضمینِ اینکه
        **هیچ** مسیرِ ساختِ نسخه (چه ``layout_service``یِ رسمی، چه هر
        تستِ موجود/آینده‌ای که مستقیماً ``StorefrontLayoutVersion.objects
        .create(...)`` صدا می‌زند) هرگز بدونِ شش صفحه باقی نماند، این
        است که ساختِ صفحه به خودِ عملِ «ذخیره‌ی اولین‌بارِ یک نسخه‌ی
        جدید» گره بخورد، نه به یک تابعِ کمکیِ جداگانه که ممکن است در یک
        فراخوانِ فراموش‌شود.

        ``StorefrontPage.ensure_version_pages`` خودش idempotent است، پس
        صدازدنِ اضافیِ آن (مثلاً اگر لایه‌یِ سرویس هم صریحاً صدایش بزند)
        کاملاً امن است — نه خطا، نه ردیفِ تکراری."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            StorefrontPage.ensure_version_pages(self)

    def effective_header_config(self) -> dict:
        """پیکربندی هدر با پیش‌فرض‌های کامل — کلید ذخیره‌نشده True است، کلید
        صریحاً ``False`` همان ``False`` باقی می‌ماند (بر خلاف فیلتر
        Django ``|default:True`` که مقدار صریح False را هم falsy می‌گیرد)."""
        return {**HEADER_CONFIG_DEFAULTS, **(self.header_config or {})}

    def effective_footer_config(self) -> dict:
        return {**FOOTER_CONFIG_DEFAULTS, **(self.footer_config or {})}

    def home_page(self) -> "StorefrontPage":
        """دسترسیِ صریح/explicit به صفحه‌یِ اصلیِ همین نسخه — Phase 1A:
        استفاده‌شده توسط تمامِ کدِ *جدید*ی که می‌داند دقیقاً منظورش
        «فقط صفحه اصلی» است (رندرِ Storefront، ادیتورِ فعلیِ فقط‌
        صفحه‌اصلی، بوت‌استرپِ محتوایِ اولیه) — به‌جایِ اتکا به property
        تجمیعیِ ``.sections`` (که رویِ *همه‌یِ* صفحات کار می‌کند و فقط
        برایِ سازگاریِ کدِ تستِ قدیمی نگه داشته شده). طبقِ الزامِ صریحِ
        کار: «Prefer an explicit page-aware contract»."""
        return self.pages.get(page_type=StorefrontPage.PageType.HOME)

    def get_page(self, page_type: str) -> "StorefrontPage":
        """دسترسیِ صریح به یک ``StorefrontPage`` مشخص از همین نسخه —
        Phase 2 (سازنده‌ی تک‌صفحه‌ای): تعمیمِ ``home_page()`` برایِ هر
        شش نوعِ صفحه. ``page_type`` نامعتبر همان ``DoesNotExist``یِ
        Djangoِ استاندارد را پرتاب می‌کند — فراخوان‌ها (ویوها) مسئولِ
        عبورِ یک مقدارِ از‌قبل‌اعتبارسنجی‌شده (یکی از
        ``StorefrontPage.PageType.values``) هستند، دقیقاً همان تفکیکِ
        مسئولیتی که ``ensure_version_pages`` برایِ ساختنِ هر شش صفحه
        دارد."""
        return self.pages.get(page_type=page_type)

    def effective_appearance_config(self) -> dict:
        """پیکربندیِ ظاهر با پیش‌فرض‌هایِ کامل — همان الگویِ
        ``effective_header_config``. کلیدِ ``color_overrides`` عمداً به
        شکلِ shallow merge نمی‌شود (یک دیکشنریِ تودرتو است) — اگر مقداری
        ذخیره شده باشد، دقیقاً همان مقدار استفاده می‌شود؛ حل‌کردنِ نهاییِ
        رنگ‌ها (پالت پایه + override) وظیفه‌ی ``appearance_service`` است،
        نه این متد (که فقط defaults را کامل می‌کند، دقیقاً مثلِ
        header/footer)."""
        return {**APPEARANCE_CONFIG_DEFAULTS, **(self.appearance_config or {})}

    def effective_store_appearance_manifest(self):
        """Return the typed Design Engine manifest for this exact version.

        The local import keeps the persistence adapter outside the Django
        model import graph while presenting callers with one logical boundary.
        """

        from .storefront_appearance.persistence import (
            load_store_appearance_manifest,
        )

        return load_store_appearance_manifest(self)

    def compute_fingerprint(self) -> str:
        """هش SHA-256 قطعی از هدر/فوتر/ظاهر/بخش‌ها (روی **همه‌ی صفحات**، نه
        فقط صفحه اصلی — Phase 1A: یک نسخه یعنی یک عکسِ کاملِ چیدمانِ کلِ
        فروشگاه، پس اثرِ انگشتِ drift باید کلِ آن را پوشش دهد، نه فقط
        صفحه اصلی) — مستقل از ترتیب ذخیره‌سازی ردیف‌ها یا اینکه کدام
        صفحه اول پردازش شود.

        ``select_related("page")`` تا خواندنِ ``s.page.page_type`` کوئریِ
        اضافه‌ای per-row ایجاد نکند؛ ``order_by("page__page_type", "order",
        "id")`` تا اثرِ انگشت مستقل از ترتیبِ فیزیکیِ درجِ ردیف‌ها در چند
        صفحه‌ی مختلف هم قطعی/deterministic بماند.

        Phase 1 correction: ``row_key``/``row_span`` صراحتاً به این فهرست
        اضافه شدند — این دو خروجیِ رندرِ عمومی را واقعاً تغییر می‌دهند
        (کدام section در کدام ردیف/با چه عرضی نمایش داده می‌شود)، پس باید
        بخشی از drift-detection باشند، دقیقاً مثلِ ``order``/``is_active``.
        ``is_locked`` عمداً **اضافه نشده** — تصمیمِ صریح: قفل فقط رفتارِ
        ادیتور را کنترل می‌کند (منعِ حذف/جابه‌جایی)، هیچ اثری روی HTMLِ
        منتشرشده/عمومی ندارد، پس تغییرِ آن نباید یک نسخه‌ی جدید را از نظرِ
        محتوا «متفاوت» نشان دهد — دقیقاً همان استدلالی که
        ``collapsed_in_editor`` را هم از قبل از این فهرست کنار گذاشته بود.

        Phase 2B: هر Cell علاوه بر ``section_stable_id`` قدیمی (بدون تغییر)
        اکنون یک فهرستِ ``blocks`` هم دارد (بلاک‌های چندگانه‌یِ مرتب‌شده‌یِ
        همان Cell، از رویِ FKِ جدیدِ ``StorefrontSection.cell``/``cell_order``)
        — چیدمانِ چند-بلاکی و ترتیبِ آن‌ها خروجیِ عمومی/منتشرشده را واقعاً
        تغییر می‌دهند، پس باید بخشی از drift-detection باشند، دقیقاً همان
        استدلالِ row_key/row_span بالا."""
        sections = [
            {
                "page_type": s.page.page_type, "section_key": s.section_key,
                "order": s.order, "is_active": s.is_active, "settings": s.settings,
                "row_key": s.row_key, "row_span": s.row_span,
            }
            for s in self.sections.select_related("page").order_by("page__page_type", "order", "id")
        ]
        containers = []
        for container in StorefrontContainer.objects.filter(page__version=self).select_related(
            "page"
        ).prefetch_related("cells__section", "cells__blocks").order_by("page__page_type", "order", "id"):
            containers.append({
                "page_type": container.page.page_type,
                "order": container.order,
                "layout_key": container.layout_key,
                "settings": container.settings,
                "cells": [
                    {
                        "order": cell.order,
                        "span": cell.span,
                        "settings": cell.settings,
                        "section_stable_id": (
                            str(cell.section.stable_id) if cell.section_id else None
                        ),
                        # Phase 2B: a Cell's multi-block composition and
                        # ordering are real, published-visible content —
                        # ``[Heading, Text]`` must fingerprint differently
                        # from ``[Text, Heading]``, and ``[Heading]`` must
                        # fingerprint differently from ``[Heading, Button]``
                        # (both required outcomes are a direct consequence of
                        # this list being both order-sensitive, since it's a
                        # plain Python list not a set, and length-sensitive).
                        # A Cell with zero or one Block via the new FK
                        # produces an empty or one-item list respectively —
                        # no special-casing needed relative to before this
                        # phase, since the legacy ``section_stable_id`` key
                        # above is left completely unchanged either way.
                        "blocks": [
                            {"section_stable_id": str(block.stable_id), "cell_order": block.cell_order}
                            for block in cell.blocks.order_by("cell_order", "id")
                        ],
                    }
                    for cell in container.cells.all().order_by("order", "id")
                ],
            })

        payload = {
            "header_config": self.header_config,
            "footer_config": self.footer_config,
            "appearance_config": self.appearance_config,
            "sections": sections,
            "containers": containers,
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def sections(self):
        """دسترسیِ محاسبه‌شده به **همه‌ی** ``StorefrontSection``هایِ همه‌یِ
        شش صفحه‌یِ این نسخه — Phase 1A: از وقتی ``StorefrontSection`` به
        ``StorefrontPage`` تعلق دارد (نه مستقیماً به این نسخه)، دیگر
        ``related_name="sections"``یِ واقعیِ Djangoای اینجا وجود ندارد؛
        این property همان API قدیمی (``version.sections.all/.filter/
        .order_by/.values_list/.count/.exists/.get/.delete``) را حفظ
        می‌کند — دقیقاً کافی برایِ اینکه کلِ مجموعه‌یِ تست‌هایِ موجودِ
        پیش‌ازاین (که همیشه فقط صفحه‌یِ اصلی را پر می‌کردند، پس این تجمیع
        برایِ آن‌ها دقیقاً معادلِ «فقط صفحه‌یِ اصلی» است) بدونِ هیچ تغییری
        همچنان درست کار کنند.

        **مهم برایِ کدِ جدید:** این property همیشه رویِ *همه‌یِ* صفحات
        تجمیع می‌کند، نه فقط صفحه‌یِ اصلی — هرجایی که منظور واقعاً «فقط
        صفحه‌ی اصلی» است (رندرِ Storefront، افزودن/بازچینیِ section از
        داخلِ ادیتورِ فعلیِ فقط‌صفحه‌اصلی، بوت‌استرپِ محتوایِ اولیه)، کدِ
        فراخوان باید صریحاً
        ``version.pages.get(page_type=StorefrontPage.PageType.HOME).sections``
        را به‌کار ببرد — نه این property — دقیقاً همان الگویی که در
        ``services/render_service.py``، ``services/bootstrap_service.py``
        و ``views.py`` این چکپوینت استفاده شده."""
        return StorefrontSection.objects.filter(page__version=self)


class StorefrontPage(TimeStampedModel):
    """یک نوعِ صفحه‌یِ خاص (صفحه اصلی، جزئیاتِ محصول، لیست، کالکشن، جستجو،
    سبدِ خرید) درونِ یک نسخه‌یِ چیدمان — Phase 1A (تصمیمِ مالک ۲/۳):

    ``StorefrontLayout`` تنها ریشه‌یِ سطحِ Store باقی می‌ماند (بدونِ
    تغییر — همچنان ``OneToOneField``)؛ ``StorefrontLayoutVersion``
    همچنان تنها snapshotِ اتمیکِ کلِ طراحیِ فروشگاه است (هدر/فوتر/ظاهرِ
    سراسری + همه‌یِ صفحات، با هم منتشر می‌شوند — نه یک اشاره‌گرِ انتشارِ
    مستقل برایِ هر صفحه). ``StorefrontPage`` فقط یک لایه‌یِ میانیِ *جدید*
    است که زیرِ همان نسخه‌یِ واحد قرار می‌گیرد — نه یک ریشه‌یِ جدید، نه
    یک چرخه‌یِ Draft/Publish جداگانه‌یِ per-page.

    هویتِ هر صفحه دقیقاً ``(نسخه، نوعِ صفحه)`` است — نه یک ``stable_id``یِ
    جداگانه، چون صفحات اسلاتِ typed هستند (شش نوعِ ثابت)، نه آبجکتِ
    آزادانه‌ساخته‌شده‌یِ مرچنت مثلِ section."""

    class PageType(models.TextChoices):
        HOME = "home", "صفحه اصلی"
        PRODUCT_DETAIL = "product_detail", "جزئیات محصول"
        LISTING = "listing", "لیست محصولات"
        COLLECTION = "collection", "کالکشن"
        SEARCH = "search", "نتایج جستجو"
        CART = "cart", "سبد خرید"

    version = models.ForeignKey(
        StorefrontLayoutVersion, verbose_name="نسخه چیدمان",
        on_delete=models.CASCADE, related_name="pages",
    )
    page_type = models.CharField("نوع صفحه", max_length=20, choices=PageType.choices)

    class Meta:
        verbose_name = "صفحه چیدمان فروشگاه"
        verbose_name_plural = "صفحات چیدمان فروشگاه"
        constraints = [
            models.UniqueConstraint(
                fields=["version", "page_type"],
                name="storefront_page_unique_type_per_version",
            ),
        ]

    def __str__(self):
        return f"{self.get_page_type_display()} — نسخه {self.version_id}"

    @classmethod
    def resolve_page_type(cls, raw: object) -> str:
        """Phase 4 (Task 3B) — the ONE validated PageType input, extracted
        from the legacy editor's own ``views.py::_resolve_page_type`` (a
        single-caller private helper before this task) so R4's editor uses
        the exact same resolution instead of a second, copy-pasted branch
        chain. A missing/invalid raw value silently resolves to ``HOME`` —
        never an error — so an old link/bookmark/request without this
        parameter keeps behaving exactly as before this generalization."""
        if raw in cls.PageType.values:
            return raw
        return cls.PageType.HOME

    @classmethod
    def ensure_version_pages(cls, version: "StorefrontLayoutVersion") -> None:
        """اطمینان از اینکه ``version`` هر شش نوعِ صفحه را دارد — idempotent
        (اگر همه از قبل وجود داشته باشند، هیچ ردیفِ جدیدی ساخته نمی‌شود؛
        اگر بعضی وجود نداشته باشند، فقط همان‌ها ساخته می‌شوند). این تنها
        نقطه‌یِ مرکزیِ ساختِ صفحه است — طبقِ الزامِ صریحِ کار («centralize
        this behavior... do NOT scatter page-creation logic across
        views»)؛ هر جایی که یک ``StorefrontLayoutVersion`` جدید ساخته
        می‌شود (``layout_service.get_or_create_draft``/``restore_version``/
        ``apply_industry_layout``) باید بی‌درنگ همین متد را صدا بزند."""
        existing = set(version.pages.values_list("page_type", flat=True))
        missing = [pt for pt in cls.PageType.values if pt not in existing]
        if missing:
            cls.objects.bulk_create([cls(version=version, page_type=pt) for pt in missing], ignore_conflicts=True)


class StorefrontSection(TimeStampedModel):
    """یک بخش صفحه درون یک صفحه‌یِ چیدمان — نوع، ترتیب، وضعیت، تنظیمات JSON.

    ``section_key`` در برابر Section Registry اعتبارسنجی می‌شود (سرویس،
    نه اینجا) — همان الگویی که مانع بارگذاری template دلخواه یا ارجاع
    نامعتبر می‌شود (بخش ۱۲ گزارش ممیزی).

    Phase 1A (تصمیمِ مالک ۵): مالکیتِ واقعی/تنهایِ این مدل اکنون
    ``StorefrontPage`` است (نه مستقیماً ``StorefrontLayoutVersion``) —
    ``page`` تنها ستونِ FKِ واقعی در دیتابیس است؛ **هیچ ستونِ ``version``ی
    دیگر در schema وجود ندارد** (طبقِ الزامِ صریحِ کار: «Do NOT leave two
    long-term competing ownership sources»). برایِ اینکه صدها فراخوانیِ
    موجودِ ``StorefrontSection(version=X, ...)``/
    ``StorefrontSection.objects.create(version=X, ...)`` در کدِ تست
    (که همگی از پیش، از دوره‌یِ پیش از این چکپوینت، وجود داشتند و بدونِ
    اجرایِ واقعیِ Django در این sandbox قابلِ ویرایشِ دستیِ ایمن نبودند —
    نگاه کنید به گزارشِ Phase 1A، بخشِ «Compatibility blocker») بدونِ
    تغییر همچنان کار کنند، ``__init__`` این کلاس یک **شیمِ Python-level
    (نه schema-level)** فراهم می‌کند: ``version=`` را می‌پذیرد و آن را
    بی‌درنگ به ``page = version.pages.get(page_type=HOME)`` حل می‌کند.
    این یک منبعِ مالکیتِ دومِ رقیب *در دیتابیس* نیست — فقط یک راحتیِ
    ساختِ شیءِ در سطحِ پایتون است؛ تنها منبعِ حقیقتِ پایدارشده همیشه
    ``page_id`` است."""

    page = models.ForeignKey(
        StorefrontPage, verbose_name="صفحه",
        on_delete=models.CASCADE, related_name="sections",
    )
    section_key = models.CharField("نوع بخش", max_length=50)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)
    settings = models.JSONField("تنظیمات", default=dict, blank=True)
    collapsed_in_editor = models.BooleanField(
        "جمع‌شده در ادیتور", default=False,
        help_text=(
            "فقط نمایش فشرده/باز کارت این بخش داخل سازنده بصری را کنترل می‌کند — "
            "مستقل از is_active؛ هیچ اثری روی نمایش عمومی Storefront ندارد."
        ),
    )
    stable_id = models.UUIDField(
        "شناسه منطقی پایدار", default=uuid.uuid4, editable=False, db_index=True,
        help_text=(
            "هویتِ منطقیِ این بخش که مستقل از PK پایگاه‌داده است — طیِ کلونِ "
            "نسخه (Published → Draft جدید، Restore) دقیقاً همان مقدار حفظ "
            "می‌شود (چون همان بخشِ منطقی است، فقط در نسخه‌ی دیگری). طیِ "
            "تکرار (Duplicate) عمداً یک UUID تازه می‌گیرد (چون یک بخشِ "
            "منطقیِ *جدید* است). این فیلد اجازه می‌دهد ردیف‌های رسانه‌ی "
            "مقیّد به section (HeroSlide/PromotionalBanner/StoryRailItem) "
            "طیِ کلون بتوانند section مقابلِ خودشان را در نسخه‌ی جدید پیدا "
            "کنند — بدون اینکه هرگز به PKِ بخشِ منتشرشده دست بزنند "
            "(Phase 0.5 — نگاه کنید به layout_service._clone_version_content). "
            "Phase 1A: محدوده‌یِ یکتاییِ این فیلد از (نسخه، stable_id) به "
            "(صفحه، stable_id) تغییر کرده — همان معنایِ منطقی، فقط یک سطح "
            "دقیق‌تر (چون اکنون یک نسخه می‌تواند چند صفحه داشته باشد)."
        ),
    )
    template_slot_key = models.CharField(
        "کلیدِ اسلاتِ Baseline", max_length=160, blank=True, default="",
        help_text=(
            "Acceptance Batch 2 (post-U11) — هویتِ منطقیِ *جایگاهِ این section "
            "درونِ ترکیبِ baselineِ Ready Templateای* که آن را ساخته (نه یک "
            "بخشِ منطقیِ خاص مثلِ ``stable_id`` — آن UUID طیِ کلونِ نسخه حفظ "
            "می‌شود، این کلید هرگز طیِ کلون تغییر نمی‌کند اما طیِ Duplicate "
            "عمداً *کپی نمی‌شود* چون نسخه‌یِ تکرارشده دیگر «همان جایگاهِ "
            "baseline» نیست). فرمت پایدار و بدونِ وابستگی به Store/مرچنت: "
            "``<template_key>:v<template_version>:<page_type>:<index>``. "
            "رشته‌ی خالی (پیش‌فرض) یعنی این section هرگز از یک Ready Template "
            "اعمال نشده — یعنی محتوایِ دستیِ مرچنت (بازنشانیِ section/field/"
            "component هرگز رویِ آن قابلِ‌اجرا نیست، نه اینکه بی‌صدا نادیده "
            "گرفته شود؛ نگاه کنید به ``preset_service.reset_section_to_baseline``). "
            "مستقل از ``order`` — بازچینیِ section توسطِ مرچنت هرگز این کلید "
            "را تغییر نمی‌دهد، پس بازنشانیِ granular حتی پس از بازچینی/درجِ/"
            "حذفِ sectionهایِ دیگر همچنان section درستِ baseline را پیدا "
            "می‌کند."
        ),
    )
    row_key = models.CharField(
        "کلید ردیف", max_length=40, blank=True, default="",
        help_text=(
            "Phase 1 (معماریِ Universal Block/Data): خالی یعنی این section به‌تنهایی و "
            "با عرضِ کامل در ردیفِ خودش نمایش داده می‌شود — رفتارِ فعلی، بدونِ تغییر. "
            "اگر مقدار داشته باشد، این section با دیگر sectionهایی که دقیقاً همین "
            "مقدار را دارند (در همان صفحه) در یک «ردیفِ ترکیبی» (Layout Group) قرار "
            "می‌گیرند — مثلاً پیوستنِ Hero و Instant Offer در یک ردیف با عرض‌های نامساوی. "
            "شکلِ این‌که ۲/۳/۴ بلوک واقعاً چطور یک ردیف را می‌سازند در "
            "``services/row_service.py`` اعتبارسنجی می‌شود، نه اینجا — همان تفکیکِ "
            "مسئولیتیِ section_key/SECTION_REGISTRY."
        ),
    )
    row_span = models.PositiveSmallIntegerField(
        "عرض در ردیف (از ۱۲)", default=12,
        help_text=(
            "فقط وقتی row_key خالی نیست معنا دارد — تعدادِ واحد از ۱۲ واحدِ عرضِ ردیف "
            "که این section اشغال می‌کند (مثلاً ۴ برای یک‌سوم، ۸ برای دو‌سوم، ۶ برای "
            "نصف). مجموعِ row_span همه‌ی اعضایِ یک row_key باید دقیقاً ۱۲ شود — "
            "``row_service.validate_page_row_layout`` این را چک می‌کند. پیش‌فرضِ ۱۲ "
            "برایِ sectionهایِ بدونِ row_key (اکثریتِ قریب‌به‌اتفاق) بی‌اثر است — همیشه "
            "«عرضِ کامل» به‌همان‌شکلِ امروز باقی می‌ماند."
        ),
    )
    is_locked = models.BooleanField(
        "قفل‌شده", default=False,
        help_text=(
            "بخشِ قفل‌شده قابلِ جابه‌جایی (بالا/پایین) یا حذف نیست — تا وقتی که ابتدا "
            "باز قفل شود (spec §37: «It cannot be moved / It cannot be deleted»). "
            "مستقل از is_active (پنهان/نمایان) و duplicable/removable (که نوعِ خودِ "
            "section را محدود می‌کنند، نه یک نمونه‌یِ خاص را)."
        ),
    )
    cell = models.ForeignKey(
        "StorefrontCell", verbose_name="خانه (Cell)",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blocks",
        help_text=(
            "Phase 2A (پایه‌یِ چندبلاکیِ Cell — نگاه کنید به گزارشِ ممیزیِ "
            "V3، بخشِ ۵/۹): ارجاعِ **موازی و انتقالی** به Cellی که این section "
            "در آن قرار گرفته — مکملِ (نه جایگزینِ) رابطه‌یِ قدیمیِ "
            "``StorefrontCell.section`` (OneToOne) که همچنان تنها منبعِ "
            "حقیقتِ *اجراییِ* امروز است. در Phase 2A این فیلد فقط با "
            "بک‌فیلِ مهاجرت پر می‌شود و هیچ سرویس/ویو/تمپلیتِ رندر از آن "
            "نمی‌خوانَد — معماریِ آماده‌برایِ‌آینده برایِ Phase 2B (چند بلاکِ "
            "مرتب‌شده در یک Cell)، نه یک مسیرِ رندرِ فعال. NULL یعنی این "
            "section هرگز داخلِ هیچ Cellی قرار نگرفته (اکثریتِ قریب‌به‌اتفاقِ "
            "sectionهایِ امروز)."
        ),
    )
    cell_order = models.PositiveIntegerField(
        "ترتیب داخلِ Cell", default=0,
        help_text=(
            "فقط وقتی cell خالی (NULL) نباشد معنا دارد — ترتیبِ این section "
            "در میانِ بلاک‌هایِ همان Cell (Phase 2B: چند section در یک Cell). "
            "**عمداً جدا از فیلدِ ``order`` بالاست** — ``order`` معنایِ "
            "قدیمیِ/سطحِ‌صفحه‌ایِ خودش را (ترتیبِ این section در میانِ همه‌یِ "
            "sectionهایِ همان Page) کاملاً بدونِ تغییر حفظ می‌کند؛ استفاده‌یِ "
            "دوباره از ``order`` برایِ این معنایِ دوم (به‌شرطِ NULL/غیر-NULL "
            "بودنِ cell) دقیقاً همان الگویِ «فیلدِ دوپهلو/دو-معنایی» است که "
            "گزارشِ ممیزی (بخشِ ۵) صریحاً رد کرده — از جمله چون "
            "``Meta.ordering = ['order', 'id']`` رویِ کوئری‌هایِ ترکیبی "
            "(section هایِ داخلِ Cell و بیرونِ Cell در یک صفحه) نتیجه‌یِ "
            "نادرست می‌داد. پیش‌فرضِ ۰ برایِ همه‌یِ sectionهایِ بدونِ cell "
            "(اکثریتِ قریب‌به‌اتفاق) بی‌اثر است."
        ),
    )

    class Meta:
        verbose_name = "بخش صفحه فروشگاه"
        verbose_name_plural = "بخش‌های صفحه فروشگاه"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["page", "stable_id"],
                name="storefront_section_unique_stable_id_per_page",
            ),
            models.UniqueConstraint(
                fields=["cell", "cell_order"],
                condition=models.Q(cell__isnull=False),
                name="storefront_section_unique_cell_order_per_cell",
            ),
        ]

    def __init__(self, *args, **kwargs):
        """شیمِ سازگاریِ Phase 1A — نگاه کنید به docstringِ کلاس بالا.
        ``version=`` را (اگر ``page=`` صریحاً پاس داده نشده) به
        ``page = version.pages.get(page_type=HOME)`` حل می‌کند. اگر هر دو
        همزمان پاس داده شوند و با هم ناسازگار باشند (page متعلق به نسخه‌یِ
        دیگری)، بی‌صدا رد نمی‌شود — خطای صریح می‌دهد تا هیچ باگِ خاموشی
        از تركیبِ ناسازگار پیش نیاید."""
        version = kwargs.pop("version", None)
        if version is not None:
            if "page" in kwargs and kwargs["page"] is not None and kwargs["page"].version_id != version.pk:
                raise ValueError(
                    "هم‌زمان version= و page= ناسازگار پاس داده شده‌اند — "
                    "page متعلق به نسخه‌ی دیگری است."
                )
            if kwargs.get("page") is None:
                kwargs["page"] = version.pages.get(page_type=StorefrontPage.PageType.HOME)
        super().__init__(*args, **kwargs)

    @property
    def version(self) -> StorefrontLayoutVersion:
        """دسترسیِ فقط-خوانا و کاملاً مشتق‌شده (نه یک ستونِ ذخیره‌شده‌ی
        دیگر) به نسخه‌ای که این section (از طریقِ ``page``) به آن تعلق
        دارد — نگاه کنید به docstringِ کلاس برایِ توضیحِ کاملِ این تصمیم."""
        return self.page.version

    def __str__(self):
        return f"{self.section_key} (#{self.order})"


class StorefrontContainer(TimeStampedModel):
    """Layout container for one page in the visual builder.

    A container owns one to four ordered cells.  Content remains a
    ``StorefrontSection`` (so the existing registry/settings/media system stays
    intact); a cell only places at most one section.  Empty cells are valid and
    are the key difference from the legacy ``row_key``/``row_span`` model: the
    merchant can create the layout first and choose content afterwards.

    ``layout_key`` is a merchant-facing preset hint (``single``, ``half``,
    ``quarter_left`` ...).  Cell ``span`` values are the actual layout source of
    truth, which leaves room for a future custom divider without a schema change.
    """

    page = models.ForeignKey(
        StorefrontPage,
        verbose_name="صفحه",
        on_delete=models.CASCADE,
        related_name="containers",
    )
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    stable_id = models.UUIDField(
        "شناسه منطقی پایدار",
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="در Clone/Restore حفظ می‌شود تا هویت Container بین نسخه‌ها پایدار بماند.",
    )
    layout_key = models.CharField(
        "چینش",
        max_length=32,
        default="single",
        help_text="برچسب Preset رابط کاربری؛ عرض واقعی هر خانه در StorefrontCell.span ذخیره می‌شود.",
    )
    settings = models.JSONField(
        "تنظیمات Container",
        default=dict,
        blank=True,
        help_text="فاصله ستون‌ها، رفتار موبایل، عرض محتوا و تنظیمات توسعه‌پذیر آینده.",
    )
    is_locked = models.BooleanField(
        "قفل‌شده",
        default=False,
        help_text="قفل Container مستقل از قفل محتوای داخل Cellها است.",
    )

    class Meta:
        verbose_name = "کانتینر چیدمان فروشگاه"
        verbose_name_plural = "کانتینرهای چیدمان فروشگاه"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["page", "stable_id"],
                name="storefront_container_unique_stable_id_per_page",
            ),
        ]
        indexes = [
            models.Index(fields=["page", "order"], name="sfb_container_page_order_idx"),
        ]

    def __str__(self):
        return f"{self.page_id} / {self.layout_key} / #{self.order}"


class StorefrontCell(TimeStampedModel):
    """One slot inside a ``StorefrontContainer``.

    A Cell may intentionally be empty.  When populated it points to exactly one
    existing ``StorefrontSection``; deleting that section leaves the Cell empty
    (``SET_NULL``) rather than deleting the layout itself.  This matches the
    builder UX where layout and content are separate concepts.
    """

    container = models.ForeignKey(
        StorefrontContainer,
        verbose_name="کانتینر",
        on_delete=models.CASCADE,
        related_name="cells",
    )
    order = models.PositiveSmallIntegerField("ترتیب خانه", default=0)
    stable_id = models.UUIDField(
        "شناسه منطقی پایدار",
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        help_text="در Clone/Restore حفظ می‌شود تا هویت Cell بین نسخه‌ها پایدار بماند.",
    )
    span = models.PositiveSmallIntegerField(
        "عرض دسکتاپ از ۱۲",
        default=12,
        help_text="عرض واقعی Cell روی گرید ۱۲ واحدی؛ مجموع Cellهای هر Container باید ۱۲ باشد.",
    )
    section = models.OneToOneField(
        StorefrontSection,
        verbose_name="محتوا",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placement_cell",
        help_text="خالی بودن مجاز است؛ محتوا بعداً از کتابخانه داخل این Cell قرار می‌گیرد.",
    )
    settings = models.JSONField(
        "تنظیمات خانه",
        default=dict,
        blank=True,
        help_text="تنظیمات توسعه‌پذیر Cell مانند تراز، رفتار موبایل یا overrideهای آینده.",
    )

    class Meta:
        verbose_name = "خانه کانتینر فروشگاه"
        verbose_name_plural = "خانه‌های کانتینر فروشگاه"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["container", "stable_id"],
                name="storefront_cell_unique_stable_id_per_container",
            ),
            models.CheckConstraint(
                condition=models.Q(span__gte=1, span__lte=12),
                name="storefront_cell_span_between_1_and_12",
            ),
        ]
        indexes = [
            models.Index(fields=["container", "order"], name="sfb_cell_container_order_idx"),
        ]

    def __str__(self):
        return f"{self.container_id} / cell #{self.order} / {self.span}/12"


class StorefrontEditHistoryEntry(TimeStampedModel):
    """Bounded server-side Undo/Redo checkpoint for one mutable Draft.

    This is intentionally separate from ``StorefrontLayoutVersion`` history:
    published/archived versions remain merchant-visible release history, while
    these checkpoints are short-lived editor interaction history for the current
    mutable draft only.  Each entry stores the complete draft state before and
    after one successful builder mutation so Undo/Redo never touches Published.
    """

    draft_version = models.ForeignKey(
        StorefrontLayoutVersion,
        verbose_name="پیش‌نویس",
        on_delete=models.CASCADE,
        related_name="edit_history_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="ویرایشگر",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    sequence = models.PositiveIntegerField("شماره عملیات")
    action_label = models.CharField("عنوان عملیات", max_length=120)
    before_state = models.JSONField("وضعیت قبل")
    after_state = models.JSONField("وضعیت بعد")
    is_undone = models.BooleanField("برگشت‌خورده", default=False)

    class Meta:
        verbose_name = "گام تاریخچه ویرایش سازنده"
        verbose_name_plural = "گام‌های تاریخچه ویرایش سازنده"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["draft_version", "sequence"],
                name="storefront_edit_history_unique_sequence_per_draft",
            ),
        ]
        indexes = [
            models.Index(
                fields=["draft_version", "is_undone", "sequence"],
                name="sfb_hist_draft_cursor_idx",
            ),
        ]

    def __str__(self):
        return f"{self.draft_version_id} / {self.sequence} / {self.action_label}"
