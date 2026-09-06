"""مدل‌های پایه‌ی محتوای مدیریت‌شده — مقصد امن برای لینک‌های فروشگاه.

این ماژول زیرساخت اشتراکی «مقصد امن» را فراهم می‌کند. هر مدلی که بخواهد به یک
صفحه‌ی داخلی (محصول، دسته‌بندی، برند) یا یک آدرس خارجی لینک بدهد، از این
مدل انتزاعی ارث‌بری می‌کند.

تصمیمات معماری:
- GenericForeignKey استفاده نشد (عدم ایمنی ارجاعی)
- مسیرهای خام داخلی ذخیره نمی‌شود (شکنندگی URL)
- هر رکورد دقیقاً یک مقصد معتبر دارد (اعتبارسنجی در سطح مدل)
- حذف مقصد داخلی: SET_NULL → resolver بازمی‌گرداند None
- طرح‌های URL خطرناک (javascript:, data:, //) رد می‌شوند
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from apps.core.models import TimeStampedModel

# ---------------------------------------------------------------- محدودیت حجم تصویر

HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB

# فرمت‌های تصویر مجاز (تشخیص توسط Pillow)
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image_size(value):
    """اعتبارسنجی حجم فایل تصویر — حداکثر ۵ مگابایت."""
    if value and hasattr(value, 'size') and value.size > HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES:
        limit_mb = HOMEPAGE_MEDIA_MAX_UPLOAD_BYTES / (1024 * 1024)
        raise ValidationError(
            f"حجم تصویر نباید بیشتر از {limit_mb:.0f} مگابایت باشد. "
            f"حجم فعلی: {value.size / (1024 * 1024):.1f} مگابایت."
        )


def validate_image_content(value):
    """اعتبارسنجی محتوای واقعی فایل تصویر — باز کردن و verify با Pillow.

    تضمین می‌کند:
    - فایل یک تصویر واقعی قابل decode است (نه HTML/JS/SVG/text)
    - فرمت تشخیص‌داده‌شده در لیست مجاز قرار دارد
    - فایل خراب یا ناقص رد می‌شود
    """
    if not value:
        return

    from PIL import Image, UnidentifiedImageError

    # ذخیره‌ی موقعیت فعلی stream
    original_position = None
    if hasattr(value, 'tell'):
        original_position = value.tell()
    if hasattr(value, 'seek'):
        value.seek(0)

    try:
        img = Image.open(value)
        detected_format = img.format
        img.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Exception) as exc:
        raise ValidationError("فایل بارگذاری‌شده یک تصویر معتبر نیست.") from exc
    finally:
        if original_position is not None and hasattr(value, 'seek'):
            value.seek(original_position)

    if detected_format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(
            f"فرمت تصویر «{detected_format}» مجاز نیست. "
            f"فرمت‌های مجاز: {', '.join(sorted(ALLOWED_IMAGE_FORMATS))}"
        )

# طرح‌های مجاز برای لینک خارجی
ALLOWED_SCHEMES = ["https", "http", "mailto", "tel"]

# الگوی تشخیص URL نسبی پروتکل (protocol-relative)
PROTOCOL_RELATIVE_RE = re.compile(r"^//")

# طرح‌های خطرناک
DANGEROUS_SCHEME_RE = re.compile(r"^(javascript|data|vbscript):", re.IGNORECASE)


def validate_external_url(value: str) -> None:
    """اعتبارسنجی URL خارجی: فقط طرح‌های مجاز، بدون URL خطرناک."""
    value = value.strip()

    if not value:
        raise ValidationError("آدرس لینک خارجی الزامی است")

    if DANGEROUS_SCHEME_RE.match(value):
        raise ValidationError("طرح URL غیرمجاز است (javascript/data)")

    if PROTOCOL_RELATIVE_RE.match(value):
        raise ValidationError("آدرس نسبی پروتکل (//...) مجاز نیست")

    # اعتبارسنجی با طرح‌های مجاز
    validator = URLValidator(schemes=ALLOWED_SCHEMES)
    try:
        validator(value)
    except ValidationError:
        # mailto و tel ممکن است URLValidator استاندارد پشتیبانی نکند
        if value.startswith("mailto:") or value.startswith("tel:"):
            return  # مجاز
        raise ValidationError("آدرس URL معتبر نیست")


class DestinationType(models.TextChoices):
    """انواع مقصد ممکن برای لینک‌های مدیریت‌شده‌ی فروشگاه."""
    NONE = "none", "بدون مقصد"
    CATEGORY = "category", "دسته‌بندی"
    PRODUCT = "product", "محصول"
    BRAND = "brand", "برند"
    COLLECTION = "collection", "کالکشن"
    #: Phase 3 (کتابخانه‌ی بلوک‌های صفحه اصلی) — دو مقصدِ بدون-پارامتر
    #: (مثلِ NONE/EXTERNAL: نه destination_id نیاز دارند نه URL خارجی)
    #: که در طرح اصلیِ کار به‌عنوان مقصدهای استانداردِ لینک/دکمه خواسته
    #: شده بودند اما پیاده نشده بودند.
    SEARCH = "search", "جستجو"
    CART = "cart", "سبد خرید"
    EXTERNAL = "external", "لینک خارجی"


class DestinationMixin(models.Model):
    """مدل انتزاعی مقصد امن — هر مدل محتوایی که نیاز به لینک دارد از این ارث‌بری می‌کند.

    اعتبارسنجی تضمین می‌کند:
    - دقیقاً یک مقصد بر اساس نوع انتخاب‌شده تنظیم شده
    - هیچ ترکیب متناقضی از مقاصد وجود ندارد
    - URL خارجی فقط طرح‌های امن را می‌پذیرد
    """

    destination_type = models.CharField(
        "نوع مقصد", max_length=20,
        choices=DestinationType.choices, default=DestinationType.NONE,
    )
    destination_category = models.ForeignKey(
        "catalog.Category", verbose_name="دسته‌بندی مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_product = models.ForeignKey(
        "catalog.Product", verbose_name="محصول مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_brand = models.ForeignKey(
        "catalog.Brand", verbose_name="برند مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_collection = models.ForeignKey(
        "catalog.MerchantCollection", verbose_name="کالکشن مقصد",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    destination_external_url = models.CharField(
        "آدرس لینک خارجی", max_length=500, blank=True,
    )
    open_in_new_tab = models.BooleanField("باز شدن در تب جدید", default=False)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        self._validate_destination_coherence()
        self._validate_destination_store_ownership()

    def _destination_owner_store_id(self):
        """شناسه‌ی Storeیی که مقصدهای این رکورد باید متعلق به آن باشند —
        پیش‌فرض از فیلدِ مستقیمِ ``store`` خوانده می‌شود؛ زیرکلاس‌هایی که
        Store را از طریقِ یک رابطه‌ی غیرمستقیم دارند (مثلاً ``MenuItem``
        که فقط ``menu.store`` را دارد) این متد را override می‌کنند. اگر
        هنوز نامشخص است (مثلاً هنگامِ ساختِ رکورد پیش از تنظیمِ رابطه)،
        ``None`` برمی‌گردد و بررسیِ مالکیت رد می‌شود — بررسیِ کوهرنسِ نوعِ
        مقصد در ``_validate_destination_coherence`` هم‌چنان مستقل اجرا
        می‌شود."""
        return getattr(self, "store_id", None)

    def _validate_destination_store_ownership(self):
        """دفاعِ لایه‌ی دوم — حتی اگر یک مسیرِ ورودی (مثلاً فرمی که هنوز
        شناسه‌ی خام می‌گیرد) بررسیِ مالکیت را در UI انجام نداده باشد، این
        سطح هرگز اجازه نمی‌دهد مقصدی از یک Store دیگر ذخیره شود."""
        store_id = self._destination_owner_store_id()
        if store_id is None:
            return
        from apps.catalog.models import Brand, Category, MerchantCollection, Product

        checks = (
            (self.destination_category_id, Category, "دسته‌بندی مقصد"),
            (self.destination_product_id, Product, "محصول مقصد"),
            (self.destination_brand_id, Brand, "برند مقصد"),
            (self.destination_collection_id, MerchantCollection, "کالکشن مقصد"),
        )
        for ref_id, model, label in checks:
            if ref_id and not model.objects.filter(pk=ref_id, store_id=store_id).exists():
                raise ValidationError(f"{label} متعلق به این فروشگاه نیست")

    def _validate_destination_coherence(self):
        """اعتبارسنجی انسجام مقصد: دقیقاً یک مقصد مطابق نوع انتخاب‌شده."""
        dtype = self.destination_type
        cat = self.destination_category_id
        prod = self.destination_product_id
        brand = self.destination_brand_id
        collection = self.destination_collection_id
        ext = (self.destination_external_url or "").strip()

        internal_set = [f for f in [cat, prod, brand, collection] if f]
        has_ext = bool(ext)

        if dtype == DestinationType.NONE:
            if internal_set or has_ext:
                raise ValidationError("وقتی نوع مقصد «بدون مقصد» است، نباید مقصدی انتخاب شود")

        elif dtype in (DestinationType.SEARCH, DestinationType.CART):
            # هر دو بدون-پارامترند — درست مثلِ NONE، هیچ FK/URL خارجی‌ای
            # نباید همراهشان ذخیره شده باشد.
            if internal_set or has_ext:
                raise ValidationError("این نوع مقصد پارامتر نمی‌پذیرد — نباید مقصد دیگری انتخاب شود")

        elif dtype == DestinationType.CATEGORY:
            if not cat:
                raise ValidationError("دسته‌بندی مقصد باید انتخاب شود")
            if prod or brand or collection or has_ext:
                raise ValidationError("فقط دسته‌بندی باید انتخاب شود")

        elif dtype == DestinationType.PRODUCT:
            if not prod:
                raise ValidationError("محصول مقصد باید انتخاب شود")
            if cat or brand or collection or has_ext:
                raise ValidationError("فقط محصول باید انتخاب شود")

        elif dtype == DestinationType.BRAND:
            if not brand:
                raise ValidationError("برند مقصد باید انتخاب شود")
            if cat or prod or collection or has_ext:
                raise ValidationError("فقط برند باید انتخاب شود")

        elif dtype == DestinationType.COLLECTION:
            if not collection:
                raise ValidationError("کالکشن مقصد باید انتخاب شود")
            if cat or prod or brand or has_ext:
                raise ValidationError("فقط کالکشن باید انتخاب شود")

        elif dtype == DestinationType.EXTERNAL:
            if not has_ext:
                raise ValidationError("آدرس لینک خارجی الزامی است")
            if internal_set:
                raise ValidationError("وقتی مقصد خارجی است، نباید مقصد داخلی انتخاب شود")
            validate_external_url(ext)

    def save(self, *args, **kwargs):
        # نرمال‌سازی URL خارجی
        if self.destination_external_url:
            self.destination_external_url = self.destination_external_url.strip()
        super().save(*args, **kwargs)



# ---------------------------------------------------------------- صفحات محتوا

RESERVED_SLUGS = frozenset([
    "admin", "admin-panel", "admin-portal", "products", "cart", "checkout", "account",
    "pages", "media", "static", "api", "blog", "home",
])


class ContentPage(TimeStampedModel):
    """صفحه‌ی محتوایی مدیریت‌شده — حریم خصوصی، قوانین، درباره ما و..."""

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"

    class FooterColumn(models.TextChoices):
        QUICK_ACCESS = "quick_access", "دسترسی سریع"
        CUSTOMER_SERVICE = "customer_service", "خدمات مشتریان"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="content_pages", null=True, blank=True,
        help_text="خالی یعنی رکورد قدیمی که هنوز به هیچ فروشگاهی نسبت داده نشده — در هیچ فروشگاهی نمایش داده نمی‌شود.",
    )
    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField("اسلاگ", max_length=220, allow_unicode=True)
    body = models.TextField("متن صفحه", blank=True)
    summary = models.CharField("خلاصه", max_length=300, blank=True)

    status = models.CharField(
        "وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT
    )
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="منتشرکننده",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="published_pages",
    )

    seo_title = models.CharField("عنوان SEO", max_length=200, blank=True)
    seo_description = models.CharField("توضیحات SEO", max_length=300, blank=True)

    show_in_footer = models.BooleanField("نمایش در فوتر", default=False)
    footer_column = models.CharField(
        "ستون فوتر", max_length=20, choices=FooterColumn.choices,
        blank=True, default="",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "صفحه‌ی محتوایی"
        verbose_name_plural = "صفحات محتوایی"
        ordering = ["display_order", "title"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(status="draft")
                    | models.Q(status="published", published_at__isnull=False)
                ),
                name="content_page_published_requires_timestamp",
            ),
            models.UniqueConstraint(
                fields=["store", "slug"], name="content_page_unique_slug_per_store",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def effective_seo_title(self):
        return self.seo_title or self.title

    @property
    def effective_seo_description(self):
        return self.seo_description or self.summary or ""

    def clean(self):
        super().clean()
        if self.slug and self.slug.lower() in RESERVED_SLUGS:
            raise ValidationError({"slug": "این اسلاگ رزرو شده و قابل استفاده نیست"})

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("content:page-detail", args=[self.slug])



# ---------------------------------------------------------------- Media Asset (Phase 0.5)


def _resolve_placement_media_url(asset, legacy_field):
    """G2.2 — نقطه‌ی *واحدِ* حلِ آدرسِ رسانه برای Placementهایِ
    section-scoped (HeroSlide/PromotionalBanner/StoryRailItem).

    ترتیبِ حلِ متعارف (تصمیمِ معماریِ Phase 0.5 — ``MediaAsset`` منبعِ
    فیزیکیِ متعارف است، ``ImageField``هایِ legacy فقط برایِ سازگاریِ
    گذشته باقی مانده‌اند):

        ۱) تصویرِ ``MediaAsset``ِ متعارف (اگر موجود و دارایِ فایل)
        ۲) در غیرِ این‌صورت، ``ImageField``ِ legacy (اگر دارایِ فایل)
        ۳) در غیرِ این‌صورت، رشته‌ی خالی — **هرگز** ``ValueError``

    چرا این لازم است: مسیرِ کلونِ نسخه (``layout_service.
    _clone_section_scoped_media``) عمداً فقط FKِ ``MediaAsset`` را کلون
    می‌کند، نه بایتِ فایلِ legacy را (تصمیمِ مالک ۵). پس یک Placementِ
    کلون‌شده‌یِ Draft می‌تواند asset-backed باشد ولی ``ImageField``ِ
    legacyِ آن خالی؛ دسترسیِ مستقیمِ قدیمیِ تمپلیت‌ها به
    ``legacy_field.url`` در آن حالت ``ValueError`` می‌داد (باگِ ۵۰۰ِ
    پیش‌نمایش). این helper همان معنایِ حل را برایِ **هردو**یِ پیش‌نمایشِ
    Builder و ویترینِ عمومی فراهم می‌کند (بدونِ فورک)."""
    if asset is not None:
        asset_image = getattr(asset, "image", None)
        if asset_image:
            return asset_image.url
    if legacy_field:
        return legacy_field.url
    return ""


class MediaAsset(TimeStampedModel):
    """فایلِ فیزیکیِ رسانه — مالکیتِ آن مستقل از هر Placementِ خاص (Section/
    نسخه/صفحه) است.

    هدف (Phase 0.5 — تصمیمِ مالک ۵): جداکردنِ «فایلِ فیزیکی» از «محلِ
    استفاده‌ی نسخه/section-ایِ آن». یک ``MediaAsset`` می‌تواند همزمان توسط
    چند Placement (مثلاً یک HeroPlacementِ Published و یک HeroPlacementِ
    Draft) ارجاع شود — حذفِ یک Placement هرگز این ردیف را حذف نمی‌کند
    (نگاه کنید به ``on_delete=PROTECT`` روی فیلدهایِ asset در HeroSlide/
    PromotionalBanner/StoryRailItem).

    عمداً حداقلی نگه داشته شده — بدونِ فیلدهایِ اضافیِ «شاید بعداً لازم
    شود» (caption، تگ، دسته‌بندی و ...). اگر آینده به آن‌ها نیاز داشت،
    می‌توان بعداً افزود؛ بدونِ فیلدهایِ حدسی، ریسکِ Migration/معنایِ
    نامشخص حذف می‌شود."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="media_assets",
    )
    image = models.ImageField(
        "تصویر", upload_to="media-assets/",
        validators=[validate_image_size, validate_image_content],
    )

    class Meta:
        verbose_name = "فایل رسانه"
        verbose_name_plural = "فایل‌های رسانه"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"رسانه #{self.pk}"

    def is_referenced(self) -> bool:
        """آیا هنوز حداقل یک Placement (در هر نسخه‌ای — Published، Draft یا
        بایگانی‌شده) به این asset ارجاع می‌دهد؟

        این تنها راهِ امنِ بررسیِ «آیا حذفِ فیزیکیِ این فایل امن است؟» است —
        هرگز فرض نکنید یک asset بدون‌ارجاع است صرفاً چون یک Placementِ
        خاص حذف شده؛ ممکن است Placementِ دیگری (نسخه‌ی دیگر) هنوز به همین
        ردیف اشاره کند.

        L07 / A05 — علاوه بر پنج رابطه‌یِ مستقیمِ FKِ Placement (Hero/Banner
        دسکتاپ+موبایل/Story)، این بررسی حالا دو کلاسِ ارجاعِ زنده‌یِ دیگر را
        هم می‌بیند (نگاه کنید به ``apps.content.media_reachability``):
          * کلاس #۲ — پس‌زمینه‌یِ JSON:
            ``StorefrontSection.settings["background"]["media_asset_id"]``.
          * کلاس #۴ — عکسِ بازیابی: idِ asset ذخیره‌شده در
            ``StorefrontEditHistoryEntry.before_state``/``after_state`` یا
            ``StorefrontLayoutVersion.template_baseline_snapshot``.
        هر دو اسکن **tenant-scoped** (فقط فروشگاهِ خودِ asset) و
        **fail-closed** (خطا/ابهام → «ارجاع‌شده») هستند. ابتدا FK (ارزان،
        رفتارِ موجود) بررسی می‌شود و در صورتِ True کوتاه‌مدار می‌شود؛ فقط
        وقتی هیچ FKای نبود اسکنِ گران‌ترِ JSON/عکس اجرا می‌شود."""
        if (
            self.hero_placements.exists()
            or self.banner_desktop_placements.exists()
            or self.banner_mobile_placements.exists()
            or self.hero_mobile_placements.exists()
            or self.story_placements.exists()
        ):
            return True

        from .media_reachability import is_reachable_via_json_or_snapshots

        return is_reachable_via_json_or_snapshots(self)


class HeroSlide(TimeStampedModel, DestinationMixin):
    """اسلاید اصلی صفحه اول — تصویر + متن + دکمه‌ی CTA."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="hero_slides", null=True, blank=True,
        help_text="خالی یعنی رکورد قدیمی که هنوز به هیچ فروشگاهی نسبت داده نشده — در هیچ فروشگاهی نمایش داده نمی‌شود.",
    )
    section = models.ForeignKey(
        "storefront_builder.StorefrontSection", verbose_name="بخشِ سازنده بصری",
        on_delete=models.CASCADE, null=True, blank=True, related_name="hero_slides",
        help_text=(
            "خالی یعنی اسلایدِ سراسریِ فروشگاه (رفتارِ قدیمی، پیش از سازنده بصری) — "
            "هر section از نوع hero_banner/image_slider که خودش هیچ اسلایدِ اختصاصی "
            "ندارد، همچنان همین اسلایدهای سراسری را نشان می‌دهد (سازگاریِ کامل با گذشته). "
            "وقتی مرچنت از داخلِ سازنده بصری اسلاید اضافه می‌کند، این فیلد به همان section "
            "مقداردهی می‌شود تا هر نمونه از این section بتواند اسلایدهای مستقلِ خودش را داشته باشد."
        ),
    )
    title = models.CharField("عنوان", max_length=200, blank=True)
    subtitle = models.CharField("زیرعنوان", max_length=300, blank=True)
    desktop_image = models.ImageField("تصویر دسکتاپ", upload_to="homepage/hero/", validators=[validate_image_size, validate_image_content])
    mobile_image = models.ImageField("تصویر موبایل", upload_to="homepage/hero/", blank=True, validators=[validate_image_size, validate_image_content])
    desktop_asset = models.ForeignKey(
        "MediaAsset", verbose_name="فایلِ رسانه — دسکتاپ",
        on_delete=models.PROTECT, null=True, blank=True, related_name="hero_placements",
        help_text=(
            "Phase 0.5 — ارجاع به فایلِ فیزیکیِ به‌اشتراک‌گذاشته‌شده. خالی یعنی "
            "این ردیفِ قدیمی‌تر از این فیلد است (هنوز فقط desktop_image مستقیم "
            "دارد) — رندر همچنان از desktop_image استفاده می‌کند تا زمانی که "
            "همه‌ی مسیرهای مصرف‌کننده به‌طورِ کامل به این فیلد منتقل شوند. "
            "``on_delete=PROTECT``: حذفِ این Placement هرگز نباید بی‌درنگ اجازه‌ی "
            "حذفِ فایلِ فیزیکیِ زیرِ آن را بدهد اگر Placementِ دیگری (مثلاً "
            "نسخه‌ی Published) هنوز به همان asset اشاره می‌کند."
        ),
    )
    mobile_asset = models.ForeignKey(
        "MediaAsset", verbose_name="فایلِ رسانه — موبایل",
        on_delete=models.PROTECT, null=True, blank=True, related_name="hero_mobile_placements",
    )
    button_label = models.CharField("متن دکمه", max_length=60, blank=True)
    show_button = models.BooleanField("نمایش دکمه", default=False)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "اسلاید اصلی"
        verbose_name_plural = "اسلایدهای اصلی"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title or f"اسلاید #{self.pk}"

    def clean(self):
        super().clean()
        if self.show_button and not self.button_label:
            raise ValidationError({"button_label": "وقتی دکمه فعال است، متن دکمه الزامی است"})
        if self.show_button and self.destination_type == DestinationType.NONE:
            raise ValidationError({"destination_type": "وقتی دکمه فعال است، مقصد باید انتخاب شود"})
        self._validate_asset_store_ownership()

    def _validate_asset_store_ownership(self):
        """Phase 0.5 — تصمیمِ مالک ۵ (ایمنیِ ارجاع): یک Placement نمی‌تواند
        به ``MediaAsset``ی متعلق به فروشگاهِ دیگر ارجاع بدهد — همان الگویِ
        ``MerchantCollectionItem.clean()`` برایِ رد‌کردنِ محصولِ فروشگاهِ
        دیگر."""
        for field_name in ("desktop_asset", "mobile_asset"):
            asset = getattr(self, field_name, None)
            if asset is not None and self.store_id is not None and asset.store_id != self.store_id:
                raise ValidationError({field_name: "فایلِ رسانه‌ی انتخاب‌شده متعلق به فروشگاهِ دیگری است"})

    @property
    def desktop_image_url(self):
        """G2.2 — آدرسِ تصویرِ دسکتاپ با ترتیبِ متعارف: MediaAsset →
        ImageFieldِ legacy → خالی (بدونِ ``ValueError``)."""
        return _resolve_placement_media_url(self.desktop_asset, self.desktop_image)

    @property
    def mobile_image_url(self):
        """G2.2 — همتایِ موبایلِ ``desktop_image_url``."""
        return _resolve_placement_media_url(self.mobile_asset, self.mobile_image)


class PromotionalBanner(TimeStampedModel, DestinationMixin):
    """بنر تبلیغاتی صفحه اصلی."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="promotional_banners", null=True, blank=True,
        help_text="خالی یعنی رکورد قدیمی که هنوز به هیچ فروشگاهی نسبت داده نشده — در هیچ فروشگاهی نمایش داده نمی‌شود.",
    )
    section = models.ForeignKey(
        "storefront_builder.StorefrontSection", verbose_name="بخشِ سازنده بصری",
        on_delete=models.CASCADE, null=True, blank=True, related_name="banners",
        help_text=(
            "خالی یعنی بنرِ سراسریِ فروشگاه (رفتارِ قدیمی) — هر section از نوع "
            "single_banner/multi_banner که خودش هیچ بنرِ اختصاصی ندارد، همچنان "
            "همین بنرهای سراسری را نشان می‌دهد."
        ),
    )
    title = models.CharField("عنوان", max_length=200, blank=True)
    description = models.CharField("توضیحات", max_length=500, blank=True)
    desktop_image = models.ImageField("تصویر دسکتاپ", upload_to="homepage/banners/", validators=[validate_image_size, validate_image_content])
    mobile_image = models.ImageField("تصویر موبایل", upload_to="homepage/banners/", blank=True, validators=[validate_image_size, validate_image_content])
    desktop_asset = models.ForeignKey(
        "MediaAsset", verbose_name="فایلِ رسانه — دسکتاپ",
        on_delete=models.PROTECT, null=True, blank=True, related_name="banner_desktop_placements",
        help_text=(
            "Phase 0.5 — همان الگویِ HeroSlide.desktop_asset. خالی یعنی این "
            "ردیف قدیمی‌تر از این فیلد است؛ رندر همچنان از desktop_image استفاده "
            "می‌کند."
        ),
    )
    mobile_asset = models.ForeignKey(
        "MediaAsset", verbose_name="فایلِ رسانه — موبایل",
        on_delete=models.PROTECT, null=True, blank=True, related_name="banner_mobile_placements",
    )
    button_label = models.CharField("متن دکمه", max_length=60, blank=True)
    show_button = models.BooleanField("نمایش دکمه", default=False)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "بنر تبلیغاتی"
        verbose_name_plural = "بنرهای تبلیغاتی"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title or f"بنر #{self.pk}"

    def clean(self):
        super().clean()
        if self.show_button and not self.button_label:
            raise ValidationError({"button_label": "وقتی دکمه فعال است، متن دکمه الزامی است"})
        if self.show_button and self.destination_type == DestinationType.NONE:
            raise ValidationError({"destination_type": "وقتی دکمه فعال است، مقصد باید انتخاب شود"})
        self._validate_asset_store_ownership()

    def _validate_asset_store_ownership(self):
        """Phase 0.5 — همان الگویِ ``HeroSlide._validate_asset_store_ownership``."""
        for field_name in ("desktop_asset", "mobile_asset"):
            asset = getattr(self, field_name, None)
            if asset is not None and self.store_id is not None and asset.store_id != self.store_id:
                raise ValidationError({field_name: "فایلِ رسانه‌ی انتخاب‌شده متعلق به فروشگاهِ دیگری است"})

    @property
    def desktop_image_url(self):
        """G2.2 — همان معنایِ ``HeroSlide.desktop_image_url`` برای بنر."""
        return _resolve_placement_media_url(self.desktop_asset, self.desktop_image)

    @property
    def mobile_image_url(self):
        """G2.2 — همتایِ موبایلِ ``desktop_image_url``."""
        return _resolve_placement_media_url(self.mobile_asset, self.mobile_image)




# ---------------------------------------------------------------- شبکه‌های اجتماعی

# نگاشت پلتفرم → نام آیکون امن (بدون HTML/SVG/CSS خام)
SOCIAL_ICON_MAP = {
    "instagram": "instagram",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "linkedin": "linkedin",
    "x": "x",
    "youtube": "youtube",
    "aparat": "aparat",
    "facebook": "facebook",
    "custom": "link",
}

# طرح‌های مجاز برای لینک‌های شبکه اجتماعی
SOCIAL_LINK_ALLOWED_SCHEMES = ["https", "http"]

# الگوی شناسایی URL نسبی پروتکل
_PROTOCOL_RELATIVE_RE = re.compile(r"^//")

# طرح‌های خطرناک
_DANGEROUS_SCHEME_RE = re.compile(r"^(javascript|data|vbscript):", re.IGNORECASE)


def validate_social_url(value: str) -> None:
    """اعتبارسنجی URL شبکه اجتماعی — فقط http/https، بدون طرح خطرناک."""
    value = (value or "").strip()
    if not value:
        raise ValidationError("آدرس لینک شبکه اجتماعی الزامی است")

    if _DANGEROUS_SCHEME_RE.match(value):
        raise ValidationError("طرح URL غیرمجاز است (javascript/data/vbscript)")

    if _PROTOCOL_RELATIVE_RE.match(value):
        raise ValidationError("آدرس نسبی پروتکل (//...) مجاز نیست")

    validator = URLValidator(schemes=SOCIAL_LINK_ALLOWED_SCHEMES)
    try:
        validator(value)
    except ValidationError:
        raise ValidationError("آدرس URL معتبر نیست — فقط http و https مجاز هستند")


class SocialLink(TimeStampedModel):
    """لینک شبکه‌ی اجتماعی فروشگاه — قابل مدیریت از داشبورد."""

    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "اینستاگرام"
        TELEGRAM = "telegram", "تلگرام"
        WHATSAPP = "whatsapp", "واتساپ"
        LINKEDIN = "linkedin", "لینکدین"
        X = "x", "ایکس / توییتر"
        YOUTUBE = "youtube", "یوتیوب"
        APARAT = "aparat", "آپارات"
        FACEBOOK = "facebook", "فیسبوک"
        CUSTOM = "custom", "سفارشی"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="social_links", null=True, blank=True,
        help_text="خالی یعنی رکورد قدیمی که هنوز به هیچ فروشگاهی نسبت داده نشده — در هیچ فروشگاهی نمایش داده نمی‌شود.",
    )
    platform = models.CharField(
        "پلتفرم", max_length=20, choices=Platform.choices, default=Platform.CUSTOM,
    )
    title = models.CharField("عنوان (برچسب دسترسی‌پذیری)", max_length=100)
    url = models.URLField("آدرس", max_length=500, validators=[validate_social_url])
    icon_name = models.CharField(
        "نام آیکون", max_length=30, blank=True,
        help_text="اگر خالی باشد، آیکون پیش‌فرض پلتفرم استفاده می‌شود",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)
    show_in_header = models.BooleanField("نمایش در هدر", default=False)
    show_in_footer = models.BooleanField("نمایش در فوتر", default=True)

    class Meta:
        verbose_name = "لینک شبکه اجتماعی"
        verbose_name_plural = "لینک‌های شبکه‌های اجتماعی"
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.get_platform_display()} — {self.title}"

    @property
    def effective_icon_name(self) -> str:
        """نام آیکون مؤثر — برای پلتفرم‌های استاندارد همیشه از نگاشت پلتفرم."""
        if self.platform != self.Platform.CUSTOM:
            return SOCIAL_ICON_MAP.get(self.platform, "link")
        if self.icon_name and self.icon_name in SOCIAL_ICON_MAP.values():
            return self.icon_name
        return "link"

    def clean(self):
        super().clean()
        # نرمال‌سازی URL
        if self.url:
            self.url = self.url.strip()
        # اعتبارسنجی icon_name — فقط برای CUSTOM مهم است
        if self.platform == self.Platform.CUSTOM and self.icon_name:
            allowed = set(SOCIAL_ICON_MAP.values())
            if self.icon_name not in allowed:
                raise ValidationError({
                    "icon_name": f"نام آیکون «{self.icon_name}» مجاز نیست. "
                                 f"مقادیر مجاز: {', '.join(sorted(allowed))}"
                })

    def save(self, *args, **kwargs):
        if self.url:
            self.url = self.url.strip()
        # پلتفرم‌های استاندارد: همیشه icon از نگاشت (نرمال‌سازی قطعی)
        if self.platform != self.Platform.CUSTOM:
            self.icon_name = SOCIAL_ICON_MAP.get(self.platform, "link")
        else:
            # CUSTOM: اگر خالی یا نامعتبر → link
            allowed = set(SOCIAL_ICON_MAP.values())
            if not self.icon_name or self.icon_name not in allowed:
                self.icon_name = "link"
        super().save(*args, **kwargs)



# ---------------------------------------------------------------- مدیریت منوها


class Menu(TimeStampedModel):
    """منوی ناوبری فروشگاه — هر مکان (header/footer/mobile) حداکثر یک منوی فعال."""

    class Location(models.TextChoices):
        HEADER = "header", "منوی اصلی"
        FOOTER_1 = "footer_1", "ستون اول فوتر"
        FOOTER_2 = "footer_2", "ستون دوم فوتر"
        FOOTER_3 = "footer_3", "ستون سوم فوتر"
        MOBILE = "mobile", "منوی موبایل"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="menus", null=True, blank=True,
        help_text="خالی یعنی رکورد قدیمی که هنوز به هیچ فروشگاهی نسبت داده نشده — در هیچ فروشگاهی نمایش داده نمی‌شود.",
    )
    title = models.CharField("عنوان منو", max_length=150)
    location = models.CharField(
        "مکان نمایش", max_length=20, choices=Location.choices,
    )
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "منو"
        verbose_name_plural = "منوها"
        ordering = ["location"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "location"], name="menu_unique_location_per_store",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_location_display()})"


class MenuItem(DestinationMixin, TimeStampedModel):
    """آیتم منوی ناوبری — حداکثر ۲ سطح (والد + فرزند).

    اعتبارسنجی تضمین می‌کند:
    - والد باید به همان منو تعلق داشته باشد
    - آیتم نمی‌تواند والد خودش باشد
    - فرزند نمی‌تواند خودش فرزند داشته باشد (حداکثر ۲ سطح)
    - روابط حلقوی رد می‌شوند
    """

    menu = models.ForeignKey(
        Menu, verbose_name="منو", on_delete=models.PROTECT, related_name="items",
    )
    parent = models.ForeignKey(
        "self", verbose_name="آیتم والد", on_delete=models.PROTECT,
        null=True, blank=True, related_name="children",
    )
    title = models.CharField("عنوان", max_length=200)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "آیتم منو"
        verbose_name_plural = "آیتم‌های منو"
        ordering = ["display_order", "id"]

    def __str__(self):
        prefix = f"  └─ " if self.parent_id else ""
        return f"{prefix}{self.title}"

    def clean(self):
        super().clean()
        self._validate_hierarchy()
        self._validate_destination_requirement()

    def _destination_owner_store_id(self):
        return self.menu.store_id if self.menu_id else None

    def _validate_destination_requirement(self):
        """سیاست مقصد آیتم‌های منو.

        - فرزند (child): الزاماً باید مقصد معتبر (غیر none) داشته باشد
        - آیتم سطح اول (top-level): مقصد اختیاری
          - با مقصد: لینک مستقیم
          - بدون مقصد و با فرزندان فعال: heading زیرمنو (رندر)
          - بدون مقصد و بدون فرزند: والد موقت (ذخیره مجاز، رندر نمی‌شود)
        """
        is_child = bool(self.parent_id)

        # فرزندان الزاماً باید مقصد داشته باشند
        if is_child and self.destination_type == DestinationType.NONE:
            raise ValidationError({
                "destination_type": "آیتم فرزند باید مقصد معتبر داشته باشد"
            })

    def _validate_hierarchy(self):
        """اعتبارسنجی سلسله‌مراتب: حداکثر ۲ سطح، بدون حلقه."""
        # آیتم نمی‌تواند والد خودش باشد
        if self.parent_id and self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "آیتم نمی‌تواند والد خودش باشد"})

        if self.parent:
            # والد باید به همان منو تعلق داشته باشد
            if self.parent.menu_id != self.menu_id:
                raise ValidationError({"parent": "آیتم والد باید به همان منو تعلق داشته باشد"})

            # والد نباید خودش فرزند باشد (حداکثر ۲ سطح)
            if self.parent.parent_id is not None:
                raise ValidationError({"parent": "حداکثر ۲ سطح مجاز است — والد انتخاب‌شده خودش فرزند است"})

        # اگر این آیتم قبلاً فرزند دارد، نمی‌تواند والد بگیرد
        if self.pk and self.parent_id:
            if self.children.exists():
                raise ValidationError({
                    "parent": "این آیتم دارای فرزند است و نمی‌تواند خودش فرزند شود"
                })




# ---------------------------------------------------------------- تنظیمات فوتر

_PHONE_ALLOWED_RE = re.compile(r'^[\d\s+\-()]+$')
_CONTROL_CHAR_RE = re.compile(r'[\x00-\x1f\x7f]')


def validate_phone(value: str) -> None:
    """اعتبارسنجی شماره تلفن — ارقام، فاصله، +، -، پرانتز مجاز."""
    value = (value or "").strip()
    if not value:
        return  # blank is OK (field is optional)
    if _CONTROL_CHAR_RE.search(value):
        raise ValidationError("شماره تلفن نمی‌تواند شامل کاراکترهای کنترلی باشد")
    if '<' in value or '>' in value or '&' in value:
        raise ValidationError("شماره تلفن نمی‌تواند شامل نشانه‌گذاری HTML باشد")
    if not _PHONE_ALLOWED_RE.match(value):
        raise ValidationError("شماره تلفن فقط می‌تواند شامل ارقام، فاصله، +، - و پرانتز باشد")
    if len(value) > 50:
        raise ValidationError("شماره تلفن بسیار طولانی است")


class FooterSettingsNotProvisionedError(Exception):
    """Raised by ``FooterSettings.load(store=...)`` when the given Store has
    no ``FooterSettings`` row yet. See ``apps.core.models.ShopSettingsNotProvisionedError``
    for the same rationale: provisioning is explicit, never a read-time side effect.
    """


class FooterSettings(TimeStampedModel):
    """تنظیمات فوتر — دقیقاً یک رکورد به‌ازای هر Store (نه یک رکورد سراسری)."""

    store = models.OneToOneField(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="footer_settings",
    )

    # General
    is_enabled = models.BooleanField("فعال", default=True)
    show_branding = models.BooleanField("نمایش برندینگ", default=True)
    show_logo = models.BooleanField("نمایش لوگو", default=True)
    description = models.TextField("توضیحات فوتر", blank=True, max_length=500)
    # Contact
    show_contact = models.BooleanField("نمایش اطلاعات تماس", default=True)
    address = models.CharField("آدرس", max_length=500, blank=True)
    phone = models.CharField("تلفن", max_length=50, blank=True, validators=[validate_phone])
    secondary_phone = models.CharField("تلفن ثانویه", max_length=50, blank=True, validators=[validate_phone])
    email = models.EmailField("ایمیل", blank=True)
    working_hours = models.CharField("ساعات کاری", max_length=250, blank=True)
    # Sections
    show_navigation = models.BooleanField("نمایش ناوبری", default=True)
    show_social_links = models.BooleanField("نمایش شبکه‌های اجتماعی", default=True)
    # Newsletter
    show_newsletter = models.BooleanField("نمایش خبرنامه", default=False)
    newsletter_title = models.CharField("عنوان خبرنامه", max_length=150, blank=True)
    newsletter_description = models.CharField("توضیح خبرنامه", max_length=300, blank=True)
    # Media
    show_trust_badges = models.BooleanField("نمایش نمادهای اعتماد", default=False)
    show_payment_logos = models.BooleanField("نمایش لوگوهای پرداخت", default=False)
    # Copyright
    copyright_text = models.CharField("متن کپی‌رایت", max_length=300, blank=True)

    class Meta:
        verbose_name = "تنظیمات فوتر"
        verbose_name_plural = "تنظیمات فوتر"

    def __str__(self):
        return "تنظیمات فوتر"

    @classmethod
    def load(cls, store=None):
        """همان قرارداد ``ShopSettings.load()`` — نگاه کنید به آن برای شرح کامل.

        ``store`` مشخص شود: فقط تنظیمات فوتر همان Store. ``store`` مشخص
        نشود: حالت سازگاری موقت (دقیقاً یک Store فعال با اسلاگ
        ``"akhlaghi"``) که در غیر این صورت fail-closed می‌شود.
        """
        if store is not None:
            try:
                return cls.objects.get(store=store)
            except cls.DoesNotExist as exc:
                raise FooterSettingsNotProvisionedError(
                    f"Store {store.slug!r} has no FooterSettings row yet; "
                    "provision it explicitly via FooterSettings.provision_for(store)."
                ) from exc

        from apps.stores.resolution import resolve_compatibility_store

        compat_store = resolve_compatibility_store()
        try:
            return cls.objects.get(store=compat_store)
        except cls.DoesNotExist as exc:
            raise FooterSettingsNotProvisionedError(
                f"Store {compat_store.slug!r} has no FooterSettings row yet; "
                "provision it explicitly via FooterSettings.provision_for(store)."
            ) from exc

    @classmethod
    def provision_for(cls, store):
        """رکورد FooterSettings یک Store را idempotent می‌سازد؛ مقادیر
        موجود را هرگز بازنویسی نمی‌کند."""
        obj, _ = cls.objects.get_or_create(store=store)
        return obj

    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = self.phone.strip()
        if self.secondary_phone:
            self.secondary_phone = self.secondary_phone.strip()
        super().save(*args, **kwargs)


class FooterTrustBadge(TimeStampedModel):
    """نماد اعتماد فوتر — مالکیت مستقیم Store (بدون رابطه با FooterSettings)."""

    store = models.ForeignKey(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="footer_trust_badges",
    )
    title = models.CharField("عنوان", max_length=150)
    image = models.ImageField("تصویر", upload_to="footer/trust-badges/", validators=[validate_image_size, validate_image_content])
    destination_url = models.URLField("لینک مقصد", blank=True, max_length=500)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "نماد اعتماد"
        verbose_name_plural = "نمادهای اعتماد"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.destination_url:
            self.destination_url = self.destination_url.strip()
            if DANGEROUS_SCHEME_RE.match(self.destination_url):
                raise ValidationError({"destination_url": "طرح URL غیرمجاز است"})
            if PROTOCOL_RELATIVE_RE.match(self.destination_url):
                raise ValidationError({"destination_url": "آدرس نسبی پروتکل مجاز نیست"})


class FooterPaymentLogo(TimeStampedModel):
    """لوگوی روش پرداخت فوتر — مالکیت مستقیم Store (بدون رابطه با FooterSettings)."""

    store = models.ForeignKey(
        "stores.Store",
        verbose_name="فروشگاه",
        on_delete=models.CASCADE,
        related_name="footer_payment_logos",
    )
    title = models.CharField("عنوان", max_length=150)
    image = models.ImageField("تصویر", upload_to="footer/payment-logos/", validators=[validate_image_size, validate_image_content])
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "لوگوی پرداخت"
        verbose_name_plural = "لوگوهای پرداخت"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title




# ---------------------------------------------------------------- Story Rail

class StoryRailItem(TimeStampedModel, DestinationMixin):
    """آیتمِ ریلِ استوری — محتوایِ دایره‌ایِ قابل‌اسکرول (شبیهِ استوریِ
    اینستاگرام) که مرچنت می‌تواند به دسته‌بندی، محصول، کالکشن یا لینکِ
    خارجی پیوند بدهد. مشترک بین تمامِ خانواده‌ها — هر خانواده‌ای
    می‌تواند این Section را اضافه کند.

    مدلِ رسانه‌ای: یک تصویرِ دایره‌ای (thumbnail) + عنوانِ کوتاه.
    بدونِ وابستگی به شبکه‌ی اجتماعی یا APIِ خارجی."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="story_rail_items",
    )
    section = models.ForeignKey(
        "storefront_builder.StorefrontSection", verbose_name="بخشِ سازنده بصری",
        on_delete=models.CASCADE, null=True, blank=True, related_name="story_items",
        help_text="خالی یعنی آیتمِ سراسریِ فروشگاه (مثلِ HeroSlide). وقتی مرچنت استوری را از Builder اضافه می‌کند، به همان section وصل می‌شود.",
    )
    title = models.CharField("عنوان", max_length=60, blank=True)
    image = models.ImageField(
        "تصویر", upload_to="storyrail/",
        validators=[validate_image_size, validate_image_content],
    )
    image_asset = models.ForeignKey(
        "MediaAsset", verbose_name="فایلِ رسانه",
        on_delete=models.PROTECT, null=True, blank=True, related_name="story_placements",
        help_text=(
            "Phase 0.5 — همان الگویِ HeroSlide.desktop_asset (اینجا فقط یک "
            "تصویرِ واحد، نه جفتِ دسکتاپ/موبایل). خالی یعنی این ردیف قدیمی‌تر "
            "از این فیلد است؛ رندر همچنان از image استفاده می‌کند."
        ),
    )
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "آیتم استوری"
        verbose_name_plural = "آیتم‌های استوری"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.title or f"استوری #{self.pk}"

    def clean(self):
        super().clean()
        if self.image_asset is not None and self.store_id is not None and self.image_asset.store_id != self.store_id:
            raise ValidationError({"image_asset": "فایلِ رسانه‌ی انتخاب‌شده متعلق به فروشگاهِ دیگری است"})

    @property
    def image_url(self):
        """G2.2 — تصویرِ استوری با ترتیبِ متعارف: MediaAsset →
        ImageFieldِ legacy → خالی (بدونِ ``ValueError``)."""
        return _resolve_placement_media_url(self.image_asset, self.image)


class NewsletterSubscriber(TimeStampedModel):
    """ایمیلِ ثبت‌شده از بلوکِ «خبرنامه»یِ سازنده بصری (Phase 3 — کتابخانه‌ی
    بلوک‌هایِ صفحه‌ی اصلی).

    عمداً حداقلی — فقط ثبت/دی‌دوپِ ایمیل به‌ازای هر فروشگاه. ارسالِ واقعیِ
    کمپین/خبرنامه، برچسب‌گذاری، لغوِ اشتراک، خروجی/CSV و مدیریتِ رضایتِ
    GDPR-محور به‌عمد اینجا ساخته نشده‌اند — این یک زیرساختِ ثبتِ ایمیلِ
    قابلِ‌اعتماد است، نه یک سیستمِ بازاریابیِ ایمیلی (فراتر از چیزی است که
    این چکپوینت می‌خواهد؛ «یک بنیادِ قوی، نه هر بلوکِ قابلِ‌تصور»)."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="newsletter_subscribers",
    )
    email = models.EmailField("ایمیل")

    class Meta:
        verbose_name = "مشترکِ خبرنامه"
        verbose_name_plural = "مشترکینِ خبرنامه"
        constraints = [
            models.UniqueConstraint(fields=["store", "email"], name="newsletter_subscriber_unique_per_store"),
        ]

    def __str__(self):
        return f"{self.email} — {self.store_id}"
