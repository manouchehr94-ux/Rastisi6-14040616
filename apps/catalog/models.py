from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Vendor(TimeStampedModel):
    """فروشنده / فروشگاه — پایه‌ی چند فروشنده‌ای (Multi-Vendor Ready).

    ``store`` مالکیت مستقیم Store است: هر فروشنده دقیقاً متعلق به یک Store
    است (ADR-1 را نگاه کنید — Vendor خودش یک Store/tenant نیست؛ چندفروشنده‌ای
    *درون* یک Store یک ویژگی جداگانه و آینده است، نه بخشی از این مرحله)."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="vendors",
    )
    name = models.CharField("نام فروشنده", max_length=150)
    slug = models.SlugField("اسلاگ", max_length=170, allow_unicode=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="مالک",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendors",
    )
    logo = models.ImageField("لوگو", upload_to="vendors/logos/", null=True, blank=True)
    description = models.TextField("توضیحات", blank=True)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "فروشنده"
        verbose_name_plural = "فروشندگان"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_vendor_slug_per_store"),
        ]

    def __str__(self):
        return self.name


class Category(TimeStampedModel):
    """دسته‌بندی درختی، خودارجاع (حداقل دو سطح) — مالکیت مستقیم Store."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="categories",
    )
    name = models.CharField("نام", max_length=120)
    slug = models.SlugField("اسلاگ", max_length=140, allow_unicode=True)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    image = models.ImageField(
        "تصویر دسته‌بندی", upload_to="categories/images/", null=True, blank=True,
        help_text="تصویر واقعی برای نمایش در کارت/تایلِ دسته‌بندی. اگر خالی باشد، آیکون (ایموجی) به‌عنوان جایگزین نمایش داده می‌شود.",
    )
    parent = models.ForeignKey(
        "self",
        verbose_name="دسته‌ی والد",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    order = models.PositiveIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=True)

    # ردیابی صرفاً اطلاعاتی منشأ نصب صنف (Phase 1E) — نگاه کنید به ADR-22.
    # این دسته پس از نصب کاملاً مالکیت Store را دارد؛ حذف قالب پلتفرم هرگز
    # این دسته یا داده‌ی آن را حذف نمی‌کند (SET_NULL).
    source_template_category = models.ForeignKey(
        "IndustryTemplateCategory", verbose_name="دسته‌ی مبدأ در قالب صنف", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="installed_categories",
    )

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_category_slug_per_store"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.parent_id and self.store_id and self.parent.store_id != self.store_id:
            raise ValidationError({"parent": "دسته‌ی والد متعلق به فروشگاه دیگری است."})


class Brand(TimeStampedModel):
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="brands",
    )
    name = models.CharField("نام برند", max_length=120)
    name_en = models.CharField("نام انگلیسی", max_length=120, blank=True)
    slug = models.SlugField("اسلاگ", max_length=140, allow_unicode=True)
    logo = models.ImageField("لوگو", upload_to="brands/logos/", null=True, blank=True)
    description = models.CharField("توضیح کوتاه", max_length=300, blank=True)
    website = models.URLField("وب‌سایت", max_length=300, blank=True)
    country = models.CharField("کشور", max_length=80, blank=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "برند"
        verbose_name_plural = "برندها"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_brand_slug_per_store"),
        ]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        INACTIVE = "inactive", "غیرفعال"
        DRAFT = "draft", "پیش‌نویس"

    class Tag(models.TextChoices):
        NEW = "new", "جدید"
        HOT = "hot", "پرفروش"
        SALE = "sale", "حراج"

    class ProductType(models.TextChoices):
        SIMPLE = "simple", "کالای ساده"
        VARIABLE = "variable", "کالای دارای تنوع"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "نمایش عمومی"
        LINK_ONLY = "link", "فقط با لینک مستقیم"

    class Unit(models.TextChoices):
        PIECE = "piece", "عدد"
        PACK = "pack", "بسته"
        PAIR = "pair", "جفت"
        SET = "set", "ست"
        METER = "meter", "متر"
        SQUARE_METER = "sqm", "مترمربع"
        LITER = "liter", "لیتر"
        MILLILITER = "ml", "میلی‌لیتر"
        GRAM = "gram", "گرم"
        KILOGRAM = "kg", "کیلوگرم"
        STRAND = "strand", "شاخه"
        ROLL = "roll", "رول"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="products",
    )
    vendor = models.ForeignKey(Vendor, verbose_name="فروشنده", on_delete=models.CASCADE, related_name="products")
    # null=True/blank=True فقط برای پشتیبانی از پیش‌نویسِ داخلیِ در حالِ ساخت
    # (``is_draft_placeholder``) که پیش از انتخابِ دسته‌بندی توسطِ کاربر
    # موقتاً بدونِ دسته‌بندی وجود دارد — نگاه کنید به
    # ``apps.catalog.services.product_draft_service``. ذخیره‌ی نهاییِ کالا
    # (``_save_product``) همچنان از طریقِ ``ProductForm`` دسته‌بندی را
    # الزامی می‌کند؛ این کاملاً یک سطحِ برنامه‌ای است، نه شُلیِ دیتابیس.
    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی", on_delete=models.PROTECT, related_name="products",
        null=True, blank=True,
    )
    brand = models.ForeignKey(
        Brand, verbose_name="برند", on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )

    name = models.CharField("نام کالا", max_length=220)
    slug = models.SlugField("اسلاگ", max_length=240, allow_unicode=True)
    sku = models.CharField("کد کالا (SKU)", max_length=40)
    description = models.TextField("توضیحات", blank=True)

    price = models.DecimalField("قیمت پایه (تومان)", max_digits=12, decimal_places=0)
    discount_percent = models.PositiveSmallIntegerField(
        "درصد تخفیف", default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    # کادوپیچی — فقط وقتی مؤثر است که کادوپیچی در ``ShopSettings`` هم فعال
    # باشد. تنوع‌ها (variants) همیشه از کالای والد ارث می‌برند.
    gift_wrap_enabled = models.BooleanField("امکانِ کادوپیچیِ این کالا", default=True)
    gift_wrap_price = models.DecimalField(
        "هزینه‌ی کادوپیچیِ اختصاصیِ این کالا (تومان)", max_digits=12, decimal_places=0,
        null=True, blank=True, help_text="خالی = استفاده از قیمتِ عمومیِ فروشگاه؛ ۰ = رایگان.",
    )

    stock = models.PositiveIntegerField("موجودی انبار", default=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    product_type = models.CharField(
        "نوع کالا", max_length=10, choices=ProductType.choices, default=ProductType.SIMPLE
    )
    # نمایش (Product Entry rebuild) — «فقط با لینک مستقیم» یعنی صفحه‌ی کالا
    # در دسترس است اما از فهرست/جست‌وجو/سایت‌مپِ فروشگاه کنار گذاشته می‌شود؛
    # مستقل از status (که کنترل می‌کند کالا اصلاً قابل‌فروش هست یا نه).
    visibility = models.CharField(
        "نمایش", max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC, blank=True,
    )
    # زمان‌بندیِ انتشار (اختیاری) — وقتی پر باشد و در آینده باشد، کالا تا آن
    # لحظه حتی اگر status=active باشد در فروشگاه نمایش داده نمی‌شود؛ نگاه
    # کنید به ``apps.catalog.services.product_publish_service``.
    publish_at = models.DateTimeField("زمانِ انتشارِ زمان‌بندی‌شده", null=True, blank=True)

    rating = models.DecimalField(
        "میانگین امتیاز", max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    reviews_count = models.PositiveIntegerField("تعداد نظرات", default=0)
    sold_count = models.PositiveIntegerField("تعداد فروش", default=0)
    views_count = models.PositiveIntegerField("تعداد بازدید", default=0)

    tag = models.CharField("برچسب", max_length=10, choices=Tag.choices, blank=True)
    icon = models.CharField("آیکون/اموجی", max_length=20, blank=True)
    tint = models.CharField("رنگ پس‌زمینه کارت", max_length=20, blank=True)

    # واحدِ شمارش (Product Entry final wave 1). ``choices`` ثابت — مثلِ
    # status/product_type/visibility همین مدل — چون فهرستِ نهایی‌ای است که
    # فقط با تغییرِ کد گسترش پیدا می‌کند، نه یک مدلِ Store-owned جدا
    # (over-engineering برایِ این مرحله). پیش‌فرضِ PIECE هم برایِ کالاهایِ
    # تازه و هم برایِ backfillِ سطرهای قبلی (نگاه کنید به مایگریشنِ افزودنِ
    # این فیلد) یکسان است — بدونِ نیازِ RunPython.
    unit = models.CharField("واحد شمارش", max_length=12, choices=Unit.choices, default=Unit.PIECE)
    # مدل/کدِ فنیِ سازنده — با sku (کدِ داخلیِ فروشنده) اشتباه گرفته نشود؛
    # این کد از سازنده/برند می‌آید، نه از خودِ فروشگاه.
    model_code = models.CharField("مدل یا کد فنی", max_length=80, blank=True, default="")
    # کشورِ سازنده‌یِ خودِ کالا — مستقل از Brand.country (کشورِ برند)، چون
    # ممکن است برندی در یک کشور ثبت شده باشد اما کالایِ مشخصی را در کشورِ
    # دیگری تولید کند.
    country_of_origin = models.CharField("کشور سازنده", max_length=80, blank=True, default="")

    # لجستیک و شناسه‌های اضافی (Phase 1C — مطابق فیلدهای موجود در پروتوتایپ
    # merchant-panel-x25، بخش «مشخصات لجستیک»)
    barcode = models.CharField("بارکد محصول", max_length=64, blank=True, default="")
    weight_grams = models.PositiveIntegerField("وزن (گرم)", null=True, blank=True)
    requires_shipping = models.BooleanField("نیاز به ارسال فیزیکی", default=True)
    # خالی یعنی «از دسته‌ی مالیاتیِ پیش‌فرضِ Store استفاده کن» (نگاه کنید به
    # ADR-44 در SAAS_DOMAIN_DECISIONS.md) — این یک مقدارِ خطا نیست.
    tax_class = models.ForeignKey(
        "orders.TaxClass", verbose_name="دسته‌ی مالیاتی", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="products",
    )

    # سئو (Phase 1C — پیش‌تر هیچ فیلد سئویی روی Product وجود نداشت)
    seo_title = models.CharField("عنوان سئو", max_length=70, blank=True, default="")
    seo_description = models.CharField("توضیحات متا", max_length=160, blank=True, default="")

    # پیش‌نویسِ داخلیِ در حالِ ساخت (Product Entry full-page rebuild) — وقتی
    # مدیرِ فروشگاه صفحه‌ی «افزودنِ کالا» را باز می‌کند، بلافاصله (پیش از پرکردنِ
    # نام/دسته‌بندی) یک ردیفِ واقعیِ Product ساخته یا از سر گرفته می‌شود تا
    # ویژگی‌ها/تنوع‌ها/تصاویر بتوانند همان لحظه به یک pkِ واقعی وصل شوند —
    # نگاه کنید به ``apps.catalog.services.product_draft_service``. این پرچم
    # کاملاً مستقل از ``status`` (که وضعیتِ انتشارِ *واقعیِ* یک کالای تکمیل‌شده
    # را کنترل می‌کند) است: پیش‌نویسِ نیمه‌کاره هرگز در فهرست/آمار/فروشگاه ظاهر
    # نمی‌شود، فارغ از این‌که status چه مقداری دارد. ذخیره‌ی نهاییِ معتبر
    # (``_save_product``) همیشه این پرچم را False می‌کند.
    is_draft_placeholder = models.BooleanField(
        "پیش‌نویسِ داخلیِ در حالِ ساخت", default=False, db_index=True,
    )
    # فقط برایِ اطلاع/حسابرسی (کدام کاربر این پیش‌نویس را شروع کرده) — مالکیتِ
    # واقعی و ایزوله‌سازیِ چندمستأجری از رویِ ``store`` انجام می‌شود، نه این
    # فیلد؛ حذفِ کاربر هرگز نباید پیش‌نویس را حذف کند (SET_NULL).
    draft_created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="سازنده‌ی پیش‌نویس", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    # برچسب‌های آزاد کالا (Product Entry rebuild) — مستقل از ``tag`` (نشانِ
    # بازاریابیِ تک‌انتخابیِ قدیمی مثل «جدید»/«پرفروش») که بدونِ تغییر باقی
    # می‌ماند. برایِ جست‌وجو، فیلتر و مجموعه‌های کالا — نگاه کنید به ``ProductTag``.
    tags = models.ManyToManyField("ProductTag", verbose_name="برچسب‌ها", blank=True, related_name="products")

    class Meta:
        verbose_name = "کالا"
        verbose_name_plural = "کالاها"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_product_slug_per_store"),
            models.UniqueConstraint(fields=["store", "sku"], name="uniq_product_sku_per_store"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        """کالا نمی‌تواند به فروشنده/دسته‌بندی/برندِ متعلق به Store دیگری وصل شود.

        این یک بررسی سطح دیتابیس نیست (SQLite نمی‌تواند CHECK بین‌جدولی
        اجرا کند) — این‌جا و در لایه‌ی سرویس/فرم اعمال می‌شود."""
        from django.core.exceptions import ValidationError

        errors = {}
        if self.vendor_id and self.store_id and self.vendor.store_id != self.store_id:
            errors["vendor"] = "این فروشنده متعلق به فروشگاه دیگری است."
        if self.category_id and self.store_id and self.category.store_id != self.store_id:
            errors["category"] = "این دسته‌بندی متعلق به فروشگاه دیگری است."
        if self.brand_id and self.store_id and self.brand.store_id != self.store_id:
            errors["brand"] = "این برند متعلق به فروشگاه دیگری است."
        if self.tax_class_id and self.store_id and self.tax_class.store_id != self.store_id:
            errors["tax_class"] = "این دسته‌ی مالیاتی متعلق به فروشگاه دیگری است."
        if errors:
            raise ValidationError(errors)

    @property
    def final_price(self):
        """قیمت نهایی = price * (1 - discount_percent/100)، گرد شده."""
        factor = (Decimal(100) - self.discount_percent) / Decimal(100)
        return (self.price * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @property
    def is_variable(self):
        return self.product_type == self.ProductType.VARIABLE

    @property
    def cover_image(self):
        """تصویر کاور کالا برای کارت محصول — از cache مربوط به prefetch_related('images') استفاده می‌کند تا N+1 پیش نیاید."""
        images = list(self.images.all())
        if not images:
            return None
        for img in images:
            if img.is_cover:
                return img
        return images[0]

    @property
    def secondary_image(self):
        """دومین تصویرِ گالریِ کالا (اولین تصویرِ غیرِ کاور) — برای رندررهایِ
        کارتی که تصویرِ دوم را هنگامِ Hover نشان می‌دهند (مثلاً
        ``catalog_second_image``، تصمیمِ مالک Q-13). محصولِ تک‌تصویری
        ``None`` برمی‌گرداند — کارت باید بدونِ Crossfade، فقط تصویرِ ثابت
        نشان دهد؛ همان cache مربوط به ``prefetch_related('images')`` را
        استفاده می‌کند، بدونِ کوئریِ اضافه."""
        images = list(self.images.all())
        cover = self.cover_image
        for img in images:
            if img.pk != getattr(cover, "pk", None):
                return img
        return None


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="images")
    # اگر خالی باشد، تصویر عمومی کالا (برای همه‌ی تنوع‌ها) است. اگر پر باشد، فقط
    # مختص همان تنوع است — هنگام حذف تنوع، تصویر باقی می‌ماند و به تصویر عمومی
    # کالا برمی‌گردد (SET_NULL)، نه اینکه حذف شود.
    variant = models.ForeignKey(
        "ProductVariant", verbose_name="تنوع مرتبط", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="images",
    )
    # اختصاص به یک مقدارِ ویژگیِ خاص (مثلاً «قرمز»)، مستقل از سایر محورها —
    # برای سوییچ‌شدنِ خودکارِ تصویر در فروشگاه با انتخابِ رنگ/جنس/... حتی
    # پیش از این‌که مشتری بقیه‌ی محورها (مثلاً سایز) را هم انتخاب کند. جدا
    # از ``variant`` که به یک ترکیبِ کاملِ تنوع (مثلاً «قرمز/L») وصل می‌شود.
    option_value = models.ForeignKey(
        "ProductOptionValue", verbose_name="مقدارِ ویژگیِ مرتبط", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="images",
    )
    image = models.ImageField("تصویر", upload_to="products/gallery/")
    thumbnail = models.ImageField("تصویر بندانگشتی", upload_to="products/thumbnails/", null=True, blank=True)
    alt = models.CharField("متن جایگزین", max_length=200, blank=True)
    caption = models.CharField("توضیحِ کوتاه (کپشن)", max_length=300, blank=True)
    order = models.PositiveIntegerField("ترتیب", default=0)
    is_cover = models.BooleanField("تصویر اصلی (کاور)", default=False)
    # زیرساختِ آماده‌برایِ‌آینده‌ی نمایشِ ۳۶۰ درجه — فقط یک پرچمِ داده‌ای است؛
    # هنوز هیچ ویوئرِ ۳۶۰ درجه‌ای پیاده‌سازی نشده (نگاه کنید به یادداشتِ
    # توصیه‌های باقی‌مانده در گزارشِ نهایی). علامت‌گذاریِ یک تصویر با این
    # پرچم صرفاً برایِ آماده‌سازیِ داده برایِ آن ویژگیِ آینده است.
    is_360 = models.BooleanField("بخشی از مجموعه‌ی ۳۶۰ درجه (به‌زودی)", default=False)

    class Meta:
        verbose_name = "تصویر کالا"
        verbose_name_plural = "گالری تصاویر کالا"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} — تصویر {self.order}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.variant_id and self.product_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "این تنوع متعلق به کالای دیگری است."})
        if self.option_value_id and self.product_id and self.option_value.option.product_id != self.product_id:
            raise ValidationError({"option_value": "این مقدارِ ویژگی متعلق به کالای دیگری است."})


class ProductVideo(TimeStampedModel):
    """ویدیویِ معرفیِ کالا — فقط از طریقِ لینکِ یوتیوب/آپارات (بدونِ آپلودِ
    مستقیمِ فایلِ ویدیو، که زیرساختِ جداگانه‌ای می‌خواهد). ``embed_url`` در
    ``apps.catalog.services.product_video_service`` از رویِ ``url`` محاسبه
    می‌شود، نه این‌جا — این مدل فقط داده را نگه می‌دارد."""

    class Provider(models.TextChoices):
        YOUTUBE = "youtube", "یوتیوب"
        APARAT = "aparat", "آپارات"
        INSTAGRAM = "instagram", "اینستاگرام"

    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="videos")
    provider = models.CharField("سرویس", max_length=10, choices=Provider.choices)
    url = models.URLField("لینکِ ویدیو", max_length=500)
    title = models.CharField("عنوان (اختیاری)", max_length=200, blank=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "ویدیوی کالا"
        verbose_name_plural = "ویدیوهای کالا"
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"{self.product.name} — ویدیوی {self.get_provider_display()}"

    @property
    def embed_url(self) -> str:
        from apps.catalog.services.product_video_service import embed_url as _compute_embed_url

        return _compute_embed_url(self)

    @property
    def instagram_permalink(self) -> str:
        from apps.catalog.services.product_video_service import instagram_permalink as _permalink

        return _permalink(self)


class VariantMutationError(Exception):
    """تلاش برای تغییر فیلدهای حساس به نرمال‌سازی از مسیری که نرمال‌سازی را دور می‌زند."""


def _normalize_variant_fields(instance: "ProductVariant") -> None:
    """attribute/value/sku یک نمونه‌ی ProductVariant را نرمال و فیلدهای normalized_* را از روی آن‌ها محاسبه می‌کند.

    هم ``ProductVariant.save()`` و هم ``ProductVariantQuerySet.bulk_create()`` از همین
    تابع استفاده می‌کنند تا نرمال‌سازی هرگز در دو جا تکرار/ناهم‌سو نشود.

    ``store`` هم همیشه این‌جا از روی ``product.store`` بازمحاسبه می‌شود —
    عمداً یک فیلد مستقل قابل‌ویرایش نیست (``ProductVariantQuerySet`` تغییر
    مستقیم آن را هم مثل بقیه‌ی فیلدهای حساس مسدود می‌کند)، تا کالای دیگر
    هرگز نتواند تنوعِ Store دیگری را «تصاحب» کند؛ تنها راه تغییر مالکیت
    Store یک تنوع، تغییر مالکیت خود کالا است.
    """
    from apps.core.utils import normalization_key, normalize_digits

    instance.attribute = (instance.attribute or "").strip()
    instance.value = (instance.value or "").strip()
    instance.normalized_attribute = normalization_key(instance.attribute)
    instance.normalized_value = normalization_key(instance.value)
    instance.sku = normalize_digits(instance.sku or "").strip()
    instance.store_id = instance.product.store_id


class ProductVariantQuerySet(models.QuerySet):
    """کوئری‌ست اختصاصی ProductVariant — مسیرهای فله‌ای دور زننده‌ی ``save()`` را کنترل می‌کند.

    ``bulk_create()`` قبل از درج، هر نمونه را نرمال می‌کند (چون Django هرگز
    ``save()``/``clean()`` را برای bulk_create صدا نمی‌زند). ``update()`` و
    ``bulk_update()`` تغییر مستقیم فیلدهای حساس به نرمال‌سازی را رد می‌کنند، چون
    یک SQL UPDATE ساده نمی‌تواند normalized_attribute/normalized_value را هم‌زمان
    و درست بازمحاسبه کند؛ برای این فیلدها باید از ``instance.save()`` یا
    ``apps.catalog.services.variant_service`` استفاده شود.

    ``product``/``product_id`` هم مسدود است: یک تنوع پس از ایجاد نباید به
    کالای دیگری منتقل شود (نه حتی کالای دیگری در همان Store) — این تغییر
    مستقیم عضویت ``store`` تنوع را (که همیشه از ``product.store`` مشتق
    می‌شود — نگاه کنید به ``_normalize_variant_fields``) از ``product``ِ
    واقعی جدا می‌کند، چون یک SQL UPDATE ساده هرگز ``store_id`` را هم‌زمان
    بازمحاسبه نمی‌کند.
    """

    NORMALIZATION_SENSITIVE_FIELDS = frozenset({
        "attribute", "value", "sku", "normalized_attribute", "normalized_value",
        "store", "store_id", "product", "product_id",
    })

    def bulk_create(self, objs, *args, **kwargs):
        objs = list(objs)
        for obj in objs:
            _normalize_variant_fields(obj)
        return super().bulk_create(objs, *args, **kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        blocked = self.NORMALIZATION_SENSITIVE_FIELDS.intersection(fields)
        if blocked:
            raise VariantMutationError(
                "فیلدهای {} را نمی‌توان با bulk_update تغییر داد؛ از instance.save() یا "
                "apps.catalog.services.variant_service استفاده کنید.".format("، ".join(sorted(blocked)))
            )
        return super().bulk_update(objs, fields, *args, **kwargs)

    def update(self, **kwargs):
        blocked = self.NORMALIZATION_SENSITIVE_FIELDS.intersection(kwargs)
        if blocked:
            raise VariantMutationError(
                "فیلدهای {} را نمی‌توان مستقیماً با update() تغییر داد؛ از instance.save() یا "
                "apps.catalog.services.variant_service استفاده کنید.".format("، ".join(sorted(blocked)))
            )
        return super().update(**kwargs)


ProductVariantManager = models.Manager.from_queryset(ProductVariantQuerySet)


class ProductVariant(TimeStampedModel):
    """تنوع جنریک محصول (رنگ، سایز، وزن و...) از طریق attribute/value.

    ``attribute`` نام تنوعی است که فروشنده تعریف می‌کند (مثل «طول» یا «رایحه»)
    و در کد هاردکد نمی‌شود. ``normalized_attribute``/``normalized_value`` فقط
    برای جلوگیری از ثبت مقدار تکراری (با اختلاف فاصله/ارقام فارسی-لاتین)
    محاسبه و نگه‌داری می‌شوند و مستقیماً توسط کاربر ویرایش نمی‌شوند.
    """

    objects = ProductVariantManager()

    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="variants")
    # مالکیت Store این‌جا مستقل نیست — همیشه از product.store کپی می‌شود
    # (نگاه کنید به _normalize_variant_fields). فقط برای این وجود دارد که
    # یکتاییِ SKU بتواند در سطح دیتابیس به‌ازای هر Store اجرا شود؛ Django's
    # UniqueConstraint نمی‌تواند از یک join (product__store) عبور کند.
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="product_variants",
    )
    attribute = models.CharField("نام تنوع", max_length=60)
    value = models.CharField("مقدار تنوع", max_length=60)
    normalized_attribute = models.CharField(max_length=80, editable=False, blank=True, default="")
    normalized_value = models.CharField(max_length=80, editable=False, blank=True, default="")
    value_hex = models.CharField("کد رنگ (Hex)", max_length=9, blank=True)
    sku = models.CharField("کد کالا (SKU)", max_length=64, blank=True, default="")
    barcode = models.CharField("بارکد", max_length=64, blank=True, default="")
    stock = models.PositiveIntegerField("موجودی", default=0)
    extra_price = models.DecimalField("تغییر قیمت (تومان)", max_digits=12, decimal_places=0, default=0)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    # قیمت‌گذاری اختصاصی تنوع (Phase 1D). هر دو فیلد اختیاری‌اند: خالی یعنی
    # این تنوع مقدار مستقلی ندارد و مسیر قیمت‌گذاری فعلی (extra_price نسبت
    # به Product.price) بدون تغییر اعمال می‌شود — نگاه کنید به
    # apps.dashboard.services.variant_engine_service برای قرارداد کامل.
    compare_at_price = models.DecimalField(
        "قیمت مقایسه‌ای (تومان)", max_digits=12, decimal_places=0, null=True, blank=True,
    )
    cost = models.DecimalField("بهای تمام‌شده (تومان)", max_digits=12, decimal_places=0, null=True, blank=True)

    # قیمتِ مستقلِ این تنوع (Product Entry rebuild). خالی یعنی «از مسیرِ
    # قدیمیِ delta استفاده کن» (product.price + extra_price) — نگاه کنید به
    # apps.catalog.services.pricing_service. وقتی پر باشد، این مقدار *کاملِ*
    # قیمتِ فروشِ این تنوع است (نه افزوده به قیمتِ کالا) — برایِ حالت‌هایی که
    # تنوع‌ها قیمت‌هایِ کاملاً متفاوت دارند (مثلاً قیچیِ ایرانی ۱۰۰,۰۰۰ در برابرِ
    # قیچیِ ایتالیایی ۸۰۰,۰۰۰). ``compare_at_price`` در این حالت نقشِ «قیمتِ
    # پیش از تخفیف» را برایِ همین تنوع بازی می‌کند.
    price = models.DecimalField(
        "قیمتِ مستقلِ این تنوع (تومان)", max_digits=12, decimal_places=0, null=True, blank=True,
    )
    wholesale_price = models.DecimalField(
        "قیمتِ عمده (تومان)", max_digits=12, decimal_places=0, null=True, blank=True,
        help_text="زیرساختِ آماده‌برایِ‌آینده‌یِ فروشِ عمده — هنوز در محاسبه‌ی قیمتِ مشتری استفاده نمی‌شود.",
    )
    sales_limit_min = models.PositiveIntegerField(
        "محدودیتِ فروش (حداقل تعداد در هر سفارش)", null=True, blank=True,
        help_text="خالی = بدونِ حداقل.",
    )
    sales_limit = models.PositiveIntegerField(
        "محدودیتِ فروش (حداکثر تعداد در هر سفارش)", null=True, blank=True,
        help_text="خالی = بدونِ محدودیت. اگر پر باشد، مشتری نمی‌تواند در یک سفارش بیش از این تعداد از این تنوع بخرد.",
    )
    # خالی یعنی «از دسته‌ی مالیاتیِ کالا/Store استفاده کن»، دقیقاً همان
    # قراردادِ Product.tax_class.
    tax_class = models.ForeignKey(
        "orders.TaxClass", verbose_name="دسته‌ی مالیاتیِ اختصاصی", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="product_variants",
    )

    # موجودی (Phase 1D)
    track_inventory = models.BooleanField("پیگیری موجودی", default=True)
    low_stock_threshold = models.PositiveIntegerField("آستانه‌ی هشدار کمبود موجودی", null=True, blank=True)

    # لجستیک اختصاصی تنوع (Phase 1D) — در نبود مقدار، از Product ارث‌بری می‌شود.
    weight_grams = models.PositiveIntegerField("وزن (گرم)", null=True, blank=True)
    length_mm = models.PositiveIntegerField("طول (میلی‌متر)", null=True, blank=True)
    width_mm = models.PositiveIntegerField("عرض (میلی‌متر)", null=True, blank=True)
    height_mm = models.PositiveIntegerField("ارتفاع (میلی‌متر)", null=True, blank=True)

    # موتور Attribute/Option چندمحوره (Phase 1D). ``combination_key`` فقط
    # به‌دست ``variant_engine_service.generate_variants`` نوشته می‌شود؛ برای
    # تنوع‌های تک‌محوره‌ی قدیمی (ساخته‌شده با variant_service) همیشه خالی
    # می‌ماند — نگاه کنید به ADR-20.
    combination_key = models.CharField(max_length=64, editable=False, blank=True, default="")
    is_default = models.BooleanField("تنوع پیش‌فرض", default=False)
    is_obsolete = models.BooleanField("منسوخ (دیگر با محورهای فعال کالا مطابقت ندارد)", default=False)

    class Meta:
        verbose_name = "تنوع کالا"
        verbose_name_plural = "تنوع‌های کالا"
        ordering = ["display_order", "attribute", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "normalized_attribute", "normalized_value"],
                condition=models.Q(is_active=True),
                name="uniq_active_variant_value_per_product",
            ),
            models.UniqueConstraint(
                fields=["store", "sku"],
                condition=~models.Q(sku=""),
                name="uniq_variant_sku_when_set",
            ),
            models.UniqueConstraint(
                fields=["product", "combination_key"],
                condition=~models.Q(combination_key=""),
                name="uniq_variant_combination_key_per_product",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_default=True),
                name="uniq_default_variant_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.attribute}: {self.value}"

    @property
    def display_image(self):
        """تصویرِ نمایشیِ این تنوع — همان اولویتِ سه‌مرحله‌ایِ فروشگاه (Part
        8): ۱) تصویرِ دقیقِ همین تنوع، ۲) تصویرِ اختصاص‌یافته به یکی از
        مقادیرِ ویژگیِ تصویرمحورِ این ترکیب، ۳) کاورِ کالا. پیش‌تر این‌جا فقط
        مرحله‌ی ۱/۳ پیاده بود (مرحله‌ی ۲ نادیده گرفته می‌شد) — یعنی جدولِ
        «پیکربندیِ تنوع‌ها»یِ پنلِ مدیریت برایِ کالاهایِ چندمحوره (مثلاً
        رنگ×سایز) تصویرِ اشتباه (کاور) نشان می‌داد حتی وقتی تصویرِ رنگ
        درست map شده بود. اکنون از همان تابعِ مرجعِ فروشگاه
        (``storefront_variant_service.resolve_display_image``) استفاده
        می‌کند تا هرگز دو منطقِ اولویتِ ناهمسان نداشته باشیم.

        عمداً از ``self.images.all()``/``self.option_values.all()`` (نه
        ``.filter()``) استفاده می‌کند تا در صفحاتی که این روابط
        prefetch شده‌اند، کوئری جدید صادر نشود.
        """
        from apps.catalog.services.storefront_variant_service import resolve_display_image

        option_value_ids = {ov.option_value_id for ov in self.option_values.all()}
        return resolve_display_image(self.product, self, option_value_ids)

    @property
    def discount_percent_display(self):
        """درصدِ تخفیفِ مشتق‌شده از price/compare_at_price — فقط برایِ نمایش
        (نه یک فیلدِ ذخیره‌شده)؛ همان قراردادِ ``product_variant_set_price``."""
        if not self.compare_at_price or not self.price or self.compare_at_price <= self.price:
            return 0
        return round((1 - (self.price / self.compare_at_price)) * 100)

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        attribute = (self.attribute or "").strip()
        value = (self.value or "").strip()
        if not attribute:
            errors["attribute"] = "نام تنوع نمی‌تواند خالی باشد."
        if not value:
            errors["value"] = "مقدار تنوع نمی‌تواند خالی باشد."
        if self.tax_class_id and self.product_id and self.tax_class.store_id != self.product.store_id:
            errors["tax_class"] = "این دسته‌ی مالیاتی متعلق به فروشگاه دیگری است."
        if self.sales_limit_min is not None and self.sales_limit is not None and self.sales_limit_min > self.sales_limit:
            errors["sales_limit_min"] = "حداقلِ محدودیتِ فروش نمی‌تواند بیشتر از حداکثر باشد."
        if errors:
            raise ValidationError(errors)
        self.attribute = attribute
        self.value = value

    def save(self, *args, **kwargs):
        _normalize_variant_fields(self)
        super().save(*args, **kwargs)


class StockMovement(TimeStampedModel):
    """دفترِ حسابرسیِ موجودی — هر تغییرِ موجودیِ ``Product``/``ProductVariant``
    (چه در ثبت سفارش، چه لغو/بازگشت، چه اصلاحِ دستیِ مدیر) دقیقاً یک ردیف
    این‌جا ثبت می‌کند و هرگز حذف/به‌روزرسانی نمی‌شود — نگاه کنید به
    ``apps.catalog.services.inventory_service`` و ADR-31 در
    ``SAAS_DOMAIN_DECISIONS.md``.

    ``variant`` وقتی خالی است که این تغییر مستقیماً روی موجودیِ خودِ کالا
    (نه یک تنوعِ خاص) اعمال شده — دقیقاً همان قلمی که این تغییر را نوشته
    (Product یا ProductVariant) با هم سازگار است چون حتی برای کالاهای
    دارای تنوع، ``product`` همیشه پر است (نگاه کنید به
    ``inventory_service.decrement_stock_for_order_item``).
    """

    class Reason(models.TextChoices):
        ORDER_PLACED = "order_placed", "ثبت سفارش (کاهش موجودی)"
        ORDER_CANCELED = "order_canceled", "لغو سفارش (بازگشت موجودی)"
        MANUAL_ADJUSTMENT = "manual_adjustment", "اصلاح دستی موجودی"
        RETURN_RESTOCK = "return_restock", "بازگشتِ مرجوعی به موجودی"
        REFUND_RESTOCK = "refund_restock", "بازگشتِ موجودی هنگام استرداد (بدون مرجوعیِ رسمی)"
        WAREHOUSE_TRANSFER_OUT = "warehouse_transfer_out", "خروج به‌واسطه‌ی انتقال بین انبارها"
        WAREHOUSE_TRANSFER_IN = "warehouse_transfer_in", "ورود به‌واسطه‌ی انتقال بین انبارها"
        IMPORT_ADJUSTMENT = "import_adjustment", "اصلاح موجودی از طریق واردات (Import)"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="stock_movements",
    )
    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="stock_movements",
    )
    variant = models.ForeignKey(
        ProductVariant, verbose_name="تنوع", on_delete=models.CASCADE, null=True, blank=True,
        related_name="stock_movements",
    )
    order = models.ForeignKey(
        "orders.Order", verbose_name="سفارش", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_movements",
    )
    return_item = models.ForeignKey(
        "orders.ReturnItem", verbose_name="قلمِ مرجوعی", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_movements",
    )
    refund_item = models.ForeignKey(
        "orders.RefundItem", verbose_name="قلمِ استرداد", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_movements",
    )
    warehouse = models.ForeignKey(
        "Warehouse", verbose_name="انبار", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="stock_movements",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="stock_movements",
    )
    reason = models.CharField("علت", max_length=30, choices=Reason.choices)
    delta = models.IntegerField("مقدار تغییر (مثبت=افزایش، منفی=کاهش)")
    stock_before = models.IntegerField("موجودی پیش از تغییر")
    stock_after = models.IntegerField("موجودی پس از تغییر")
    note = models.CharField("یادداشت", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "رویداد موجودی"
        verbose_name_plural = "دفتر موجودی"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "product", "-created_at"], name="idx_stockmv_store_product"),
        ]
        constraints = [
            # جلوگیری از بازگشتِ دوباره‌ی موجودیِ یک قلمِ مرجوعی — نگاه کنید
            # به ADR-35 و inventory_service.restock_return_item.
            models.UniqueConstraint(
                fields=["return_item"],
                condition=models.Q(return_item__isnull=False),
                name="uniq_stockmv_per_return_item",
            ),
            models.UniqueConstraint(
                fields=["refund_item"],
                condition=models.Q(refund_item__isnull=False),
                name="uniq_stockmv_per_refund_item",
            ),
        ]

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.product.name} {sign}{self.delta} ({self.get_reason_display()})"


# =============================================================================
# انبار و موجودیِ چندانباره (Admin Panel Completion Program checkpoint 3 —
# ADR-37 تا ADR-39 در SAAS_DOMAIN_DECISIONS.md). ``Product.stock``/
# ``ProductVariant.stock`` همچنان تکِ منبعِ حقیقتِ موجودیِ قابل‌فروش باقی
# می‌مانند (ADR-38) — ``WarehouseInventory`` تفکیکِ موجودی به‌ازای هر انبار
# را نگه می‌دارد و همیشه باید با آن جمع‌جور بماند (بررسی‌شده توسط
# ``verify_inventory_consistency``)، نه یک منبعِ حقیقتِ مستقلِ دوم.
# =============================================================================


class Warehouse(TimeStampedModel):
    """انبار/محلِ نگه‌داریِ کالا — Store-owned. هر Store حداقل یک انبارِ
    پیش‌فرض دارد (نگاه کنید به ``provision_default_warehouses``)."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="warehouses",
    )
    name = models.CharField("نام انبار", max_length=150)
    code = models.SlugField("کد انبار", max_length=40, allow_unicode=True)
    address = models.TextField("آدرس", blank=True, default="")
    province = models.CharField("استان", max_length=80, blank=True, default="")
    city = models.CharField("شهر", max_length=80, blank=True, default="")
    postal_code = models.CharField("کد پستی", max_length=10, blank=True, default="")
    contact_name = models.CharField("نام مسئول", max_length=150, blank=True, default="")
    contact_phone = models.CharField("تلفن مسئول", max_length=20, blank=True, default="")
    is_active = models.BooleanField("فعال", default=True)
    is_default = models.BooleanField("انبار پیش‌فرض", default=False)
    is_pickup_location = models.BooleanField("محلِ تحویلِ حضوری", default=False)
    fulfillment_priority = models.PositiveIntegerField("اولویتِ تأمین", default=0)

    class Meta:
        verbose_name = "انبار"
        verbose_name_plural = "انبارها"
        ordering = ["fulfillment_priority", "name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_warehouse_code_per_store"),
            # نگاه کنید به ADR-37 — دقیقاً یک انبارِ پیش‌فرض به‌ازای هر Store؛
            # حتی اگر آن انبار بعداً غیرفعال شود، باید ابتدا صریحاً
            # جایگزین شود (سرویس این را اجرا می‌کند، نه فقط این قید).
            models.UniqueConstraint(
                fields=["store"], condition=models.Q(is_default=True), name="uniq_default_warehouse_per_store",
            ),
        ]

    def __str__(self):
        marker = " (پیش‌فرض)" if self.is_default else ""
        return f"{self.name}{marker}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.is_active and self.is_default:
            raise ValidationError({"is_active": "انبارِ پیش‌فرض نمی‌تواند غیرفعال باشد."})


class WarehouseInventory(TimeStampedModel):
    """موجودیِ یک کالا/تنوع در یک انبارِ مشخص.

    ``product`` همیشه پر است؛ ``variant`` فقط برای کالاهای دارای تنوع پر
    می‌شود (دقیقاً همان قراردادِ ``StockMovement``). مجموعِ ``on_hand`` این
    مدل به‌ازای همه‌ی انبارهای یک کالا/تنوع باید با
    ``Product.stock``/``ProductVariant.stock`` برابر بماند — نگاه کنید به
    ADR-38.
    """

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="warehouse_inventories",
    )
    warehouse = models.ForeignKey(
        Warehouse, verbose_name="انبار", on_delete=models.CASCADE, related_name="inventory_balances",
    )
    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="warehouse_balances",
    )
    variant = models.ForeignKey(
        ProductVariant, verbose_name="تنوع", on_delete=models.CASCADE, null=True, blank=True,
        related_name="warehouse_balances",
    )
    on_hand = models.IntegerField("موجودیِ فیزیکی", default=0)
    low_stock_threshold = models.PositiveIntegerField("آستانه‌ی هشدار کمبود", null=True, blank=True)
    track_inventory = models.BooleanField("پیگیری موجودی", default=True)

    class Meta:
        verbose_name = "موجودیِ انبار"
        verbose_name_plural = "موجودی‌های انبار"
        ordering = ["warehouse", "product"]
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "product"], condition=models.Q(variant__isnull=True),
                name="uniq_warehouse_product_balance",
            ),
            models.UniqueConstraint(
                fields=["warehouse", "variant"], condition=models.Q(variant__isnull=False),
                name="uniq_warehouse_variant_balance",
            ),
            models.CheckConstraint(check=models.Q(on_hand__gte=0), name="warehouse_inventory_on_hand_non_negative"),
        ]

    def __str__(self):
        target = self.variant if self.variant_id else self.product
        return f"{self.warehouse.name} — {target} ({self.on_hand})"


class InventoryReservation(TimeStampedModel):
    """رزروِ موقتِ موجودی — موجودیِ در دسترس (available) را کم می‌کند بدونِ
    تغییرِ موجودیِ فیزیکی (on_hand) تا زمانی که مصرف (consume) یا آزاد
    (release/expire) شود — نگاه کنید به ADR-39.

    ``consumed_at``/``released_at`` دقیقاً یکی از آن‌ها ممکن است پر شود، و
    فقط یک‌بار — با انتقالِ صریح در ``inventory_service``، نه نوشتنِ مستقیم.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        CONSUMED = "consumed", "مصرف‌شده"
        RELEASED = "released", "آزادشده"
        EXPIRED = "expired", "منقضی‌شده"
        CANCELLED = "cancelled", "لغوشده"

    FINAL_STATUSES = {Status.CONSUMED, Status.RELEASED, Status.EXPIRED, Status.CANCELLED}

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="inventory_reservations",
    )
    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="reservations",
    )
    variant = models.ForeignKey(
        ProductVariant, verbose_name="تنوع", on_delete=models.CASCADE, null=True, blank=True,
        related_name="reservations",
    )
    cart = models.ForeignKey(
        "cart.Cart", verbose_name="سبد خرید", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="inventory_reservations",
    )
    order = models.ForeignKey(
        "orders.Order", verbose_name="سفارش", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="inventory_reservations",
    )
    quantity = models.PositiveIntegerField("تعداد")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    idempotency_key = models.CharField("کلید یکتای درخواست", max_length=64, blank=True, default="")
    source = models.CharField("منبع", max_length=30, blank=True, default="checkout")
    expires_at = models.DateTimeField("زمان انقضا", null=True, blank=True)
    released_at = models.DateTimeField("زمان آزادسازی", null=True, blank=True)
    consumed_at = models.DateTimeField("زمان مصرف", null=True, blank=True)
    metadata = models.JSONField("فراداده", blank=True, default=dict)

    class Meta:
        verbose_name = "رزروِ موجودی"
        verbose_name_plural = "رزروهای موجودی"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "status", "expires_at"], name="idx_reservation_status_expiry"),
            models.Index(fields=["product", "variant", "status"], name="idx_reservation_target_status"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="reservation_quantity_positive"),
            models.UniqueConstraint(
                fields=["idempotency_key"], condition=~models.Q(idempotency_key=""),
                name="uniq_reservation_idempotency_key_when_set",
            ),
        ]

    def __str__(self):
        target = self.variant if self.variant_id else self.product
        return f"رزرو {self.quantity} — {target} ({self.get_status_display()})"


class WarehouseTransfer(TimeStampedModel):
    """انتقالِ موجودی بین دو انبارِ همان Store — گردشِ وضعیتِ صریح.

    ``draft`` هیچ اثری روی موجودی ندارد؛ ``in_transit`` (ارسال) موجودیِ
    مبدأ را کم می‌کند؛ ``received`` (دریافت) موجودیِ مقصد را زیاد می‌کند —
    نگاه کنید به ADR-40."""

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        REQUESTED = "requested", "درخواست‌شده"
        IN_TRANSIT = "in_transit", "در حال ارسال"
        RECEIVED = "received", "دریافت‌شده"
        CANCELLED = "cancelled", "لغوشده"

    ALLOWED_TRANSITIONS = {
        Status.DRAFT: {Status.REQUESTED, Status.CANCELLED},
        Status.REQUESTED: {Status.IN_TRANSIT, Status.CANCELLED},
        Status.IN_TRANSIT: {Status.RECEIVED, Status.CANCELLED},
        Status.RECEIVED: set(),
        Status.CANCELLED: set(),
    }
    FINAL_STATUSES = {Status.RECEIVED, Status.CANCELLED}

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="warehouse_transfers",
    )
    transfer_number = models.CharField("شماره انتقال", max_length=24)
    source_warehouse = models.ForeignKey(
        Warehouse, verbose_name="انبارِ مبدأ", on_delete=models.PROTECT, related_name="transfers_out",
    )
    destination_warehouse = models.ForeignKey(
        Warehouse, verbose_name="انبارِ مقصد", on_delete=models.PROTECT, related_name="transfers_in",
    )
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.DRAFT)
    note = models.TextField("یادداشت", blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="warehouse_transfers",
    )
    shipped_at = models.DateTimeField("زمان ارسال", null=True, blank=True)
    received_at = models.DateTimeField("زمان دریافت", null=True, blank=True)
    cancelled_at = models.DateTimeField("زمان لغو", null=True, blank=True)

    class Meta:
        verbose_name = "انتقالِ انبار"
        verbose_name_plural = "انتقال‌های انبار"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "transfer_number"], name="uniq_transfer_number_per_store"),
            models.CheckConstraint(
                check=~models.Q(source_warehouse=models.F("destination_warehouse")),
                name="transfer_source_ne_destination",
            ),
        ]

    def __str__(self):
        return f"{self.transfer_number} — {self.source_warehouse} → {self.destination_warehouse}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.source_warehouse_id and self.source_warehouse.store_id != self.store_id:
            errors["source_warehouse"] = "این انبار متعلق به فروشگاه دیگری است."
        if self.destination_warehouse_id and self.destination_warehouse.store_id != self.store_id:
            errors["destination_warehouse"] = "این انبار متعلق به فروشگاه دیگری است."
        if self.source_warehouse_id and self.source_warehouse_id == self.destination_warehouse_id:
            errors["destination_warehouse"] = "انبارِ مبدأ و مقصد نمی‌تواند یکسان باشد."
        if errors:
            raise ValidationError(errors)


class WarehouseTransferItem(TimeStampedModel):
    transfer = models.ForeignKey(
        WarehouseTransfer, verbose_name="انتقال", on_delete=models.CASCADE, related_name="items",
    )
    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.PROTECT, related_name="transfer_items",
    )
    variant = models.ForeignKey(
        ProductVariant, verbose_name="تنوع", on_delete=models.PROTECT, null=True, blank=True,
        related_name="transfer_items",
    )
    quantity_requested = models.PositiveIntegerField("تعداد درخواستی")
    quantity_shipped = models.PositiveIntegerField("تعداد ارسالی", null=True, blank=True)
    quantity_received = models.PositiveIntegerField("تعداد دریافتی", null=True, blank=True)

    class Meta:
        verbose_name = "قلمِ انتقال"
        verbose_name_plural = "اقلامِ انتقال"
        constraints = [
            models.CheckConstraint(check=models.Q(quantity_requested__gt=0), name="transfer_item_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.product.name} × {self.quantity_requested}"


# =============================================================================
# موتور Attribute / Option / Variant چندمحوره (Phase 1D) — نگاه کنید به
# ADR-19 (جدایی ویژگی توصیفی از محور تنوع‌ساز)، ADR-20 (هویت پایدار ترکیب) و
# ADR-21 (سیاست تطبیق/منسوخ‌سازی) در SAAS_DOMAIN_DECISIONS.md.
# =============================================================================


class Attribute(TimeStampedModel):
    """تعریف قابل‌استفاده‌ی مجدد یک ویژگی در سطح Store — توصیفی یا واجد شرایط محور تنوع.

    ``is_variant_axis`` فقط *واجد شرایط بودن* را نشان می‌دهد، نه تعهد — یک
    Store می‌تواند «رنگ» را هم به‌صورت توصیفی روی کالاهای ساده و هم به‌عنوان
    محور تنوع روی کالاهای دارای تنوع استفاده کند (نگاه کنید به ADR-19)."""

    class DataType(models.TextChoices):
        TEXT = "text", "متن"
        NUMBER = "number", "عدد"
        BOOLEAN = "boolean", "بله/خیر"
        SELECT = "select", "تک‌انتخابی"
        MULTISELECT = "multiselect", "چندانتخابی"
        COLOR = "color", "رنگ"
        DATE = "date", "تاریخ"

    class DisplayType(models.TextChoices):
        TEXT = "text", "متن ساده"
        DROPDOWN = "dropdown", "کشویی"
        SWATCH = "swatch", "نمونه (رنگ/تصویر)"
        CHECKBOX = "checkbox", "چک‌باکس"
        RADIO = "radio", "دکمه رادیویی"

    #: نوع‌های داده‌ای که به یک فهرست AttributeValue واقعی نیاز دارند.
    CHOICE_DATA_TYPES = frozenset({DataType.SELECT, DataType.MULTISELECT, DataType.COLOR})

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="attributes",
    )
    code = models.SlugField("کد داخلی", max_length=60, allow_unicode=True)
    label = models.CharField("عنوان نمایشی", max_length=120)
    description = models.TextField("توضیحات", blank=True)
    data_type = models.CharField("نوع داده", max_length=12, choices=DataType.choices, default=DataType.TEXT)
    display_type = models.CharField("نوع نمایش", max_length=12, choices=DisplayType.choices, blank=True, default="")
    unit = models.CharField("واحد", max_length=30, blank=True)
    is_required = models.BooleanField("الزامی", default=False)
    is_filterable = models.BooleanField("قابل فیلتر", default=False)
    is_searchable = models.BooleanField("قابل جست‌وجو", default=False)
    is_comparable = models.BooleanField("قابل مقایسه", default=False)
    is_variant_axis = models.BooleanField("واجد شرایط محور تنوع", default=False)
    # وقتی روشن باشد، مقادیرِ این ویژگی (مثلاً رنگ‌ها) در فرمِ مدیریتِ تصاویر
    # به‌عنوانِ گزینه‌ی «اختصاصِ تصویر به مقدار» پیشنهاد می‌شوند تا با انتخابِ
    # آن مقدار در فروشگاه، تصویرِ نمایش‌داده‌شده خودکار عوض شود.
    is_image_driving = models.BooleanField("تصویرمحور (سوییچِ خودکارِ تصویر)", default=False)
    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attributes",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    # ردیابی صرفاً اطلاعاتی منشأ نصب صنف (Phase 1E) — نگاه کنید به ADR-22.
    source_template_attribute = models.ForeignKey(
        "IndustryTemplateAttribute", verbose_name="ویژگی مبدأ در قالب صنف", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="installed_attributes",
    )

    class Meta:
        verbose_name = "ویژگی"
        verbose_name_plural = "ویژگی‌ها"
        ordering = ["display_order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_attribute_code_per_store"),
        ]

    def __str__(self):
        return self.label

    @property
    def is_choice_type(self):
        return self.data_type in self.CHOICE_DATA_TYPES

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.category_id and self.store_id and self.category.store_id != self.store_id:
            errors["category"] = "این دسته‌بندی متعلق به فروشگاه دیگری است."

        if self.data_type in self.CHOICE_DATA_TYPES:
            if self.data_type == self.DataType.COLOR:
                allowed_display = {self.DisplayType.SWATCH, ""}
            else:
                allowed_display = {
                    self.DisplayType.DROPDOWN, self.DisplayType.SWATCH,
                    self.DisplayType.CHECKBOX, self.DisplayType.RADIO, "",
                }
            if self.display_type not in allowed_display:
                errors["display_type"] = "نوع نمایش با نوع داده‌ی انتخاب‌شده سازگار نیست."
        elif self.display_type not in {"", self.DisplayType.TEXT}:
            errors["display_type"] = "این نوع داده فقط می‌تواند نوع نمایش «متن ساده» یا خالی داشته باشد."

        if errors:
            raise ValidationError(errors)


class AttributeValue(TimeStampedModel):
    """یکی از مقادیر مجاز یک ویژگی انتخابی (SELECT/MULTISELECT/COLOR)."""

    attribute = models.ForeignKey(Attribute, verbose_name="ویژگی", on_delete=models.CASCADE, related_name="values")
    label = models.CharField("برچسب", max_length=120)
    value = models.CharField("مقدار داخلی", max_length=120, blank=True, default="")
    normalized_label = models.CharField(max_length=140, editable=False, blank=True, default="")
    color_hex = models.CharField("کد رنگ (Hex)", max_length=9, blank=True)
    swatch_image = models.ImageField(
        "تصویر نمونه (Swatch)", upload_to="attributes/swatches/", null=True, blank=True,
        help_text="برای نمایشِ نمونه‌ی تصویری به‌جای/همراهِ رنگ — مثلاً بافتِ پارچه یا الگوی چوب.",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    # ردیابی صرفاً اطلاعاتی منشأ نصب صنف (Phase 1F) — برای تشخیص سفارشی‌سازی
    # (ADR-28)؛ مقداری بدون این FK (مثلاً نصب‌شده در Phase 1E پیش از افزودن
    # این فیلد، یا ساخته‌شده توسط مدیر فروشگاه) همیشه «سفارشی‌شده» فرض می‌شود.
    source_template_value = models.ForeignKey(
        "IndustryTemplateAttributeValue", verbose_name="مقدار مبدأ در قالب صنف", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="installed_values",
    )

    class Meta:
        verbose_name = "مقدار ویژگی"
        verbose_name_plural = "مقادیر ویژگی"
        ordering = ["display_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["attribute", "normalized_label"], condition=models.Q(is_active=True),
                name="uniq_active_attribute_value_label",
            ),
        ]

    def __str__(self):
        return f"{self.attribute.label}: {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from apps.core.utils import normalization_key

        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": "برچسب مقدار نمی‌تواند خالی باشد."})
        self.label = label
        if not self.value:
            self.value = label
        self.normalized_label = normalization_key(label)


class ProductAttributeValue(TimeStampedModel):
    """انتساب توصیفی یک ویژگی به یک کالای مشخص — برخلاف ProductOption، هرگز تنوع نمی‌سازد."""

    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="attribute_values",
    )
    attribute = models.ForeignKey(
        Attribute, verbose_name="ویژگی", on_delete=models.PROTECT, related_name="product_assignments",
    )
    value = models.ForeignKey(
        AttributeValue, verbose_name="مقدار", on_delete=models.PROTECT, null=True, blank=True,
        related_name="product_assignments",
    )
    text_value = models.CharField("مقدار متنی", max_length=500, blank=True, default="")
    number_value = models.DecimalField("مقدار عددی", max_digits=14, decimal_places=4, null=True, blank=True)
    boolean_value = models.BooleanField("مقدار بولی", null=True, blank=True)

    class Meta:
        verbose_name = "مقدار ویژگی کالا"
        verbose_name_plural = "مقادیر ویژگی کالا"
        ordering = ["attribute__display_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "attribute", "value"], name="uniq_product_attribute_value"),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.attribute.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.attribute_id and self.product_id and self.attribute.store_id != self.product.store_id:
            errors["attribute"] = "این ویژگی متعلق به فروشگاه دیگری است."
        if self.value_id and self.attribute_id and self.value.attribute_id != self.attribute_id:
            errors["value"] = "این مقدار متعلق به ویژگی دیگری است."
        if errors:
            raise ValidationError(errors)


class ProductTag(TimeStampedModel):
    """برچسبِ Store-owned برای جست‌وجو/فیلتر/مجموعه‌ی کالاها — دقیقاً همان الگویِ
    ``apps.customers.models.CustomerTag``: ``code`` فقط در محدوده‌ی همین Store
    یکتاست، و حذفِ فیزیکی وقتی به کالایی متصل است مجاز نیست؛ به‌جایِ آن آرشیو
    (``is_active=False``) می‌شود.

    ``purpose`` (Product Entry final prototype) همان رابطه‌ی M2M را برایِ دو
    کاربردِ جداگانه تفکیک می‌کند: برچسبِ عادیِ جست‌وجو/فیلتر در برابرِ
    «گروهِ دوم» (مجموعه‌ی فروش/merchandising) در فرمِ کالا — که یک مفهومِ
    بازاریابیِ مستقل از درختِ دسته‌بندیِ واقعی است، نه یک سطحِ دومِ
    دسته‌بندی؛ نگاه کنید به گزارشِ گپ‌آنالیزِ محصول برایِ توجیهِ کاملِ این
    تصمیم."""

    class Purpose(models.TextChoices):
        GENERAL = "general", "برچسبِ عادی"
        COLLECTION = "collection", "مجموعه‌ی فروش (گروهِ دوم)"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="product_tags",
    )
    name = models.CharField("نام", max_length=60)
    code = models.SlugField("کد", max_length=60, allow_unicode=True)
    purpose = models.CharField("کاربرد", max_length=12, choices=Purpose.choices, default=Purpose.GENERAL)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "برچسبِ کالا"
        verbose_name_plural = "برچسب‌های کالا"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_producttag_code_per_store"),
        ]

    def __str__(self):
        return self.name


class ProductMetafield(TimeStampedModel):
    """متادیتایِ توسعه‌پذیرِ محصول — مکانیزمِ مشترک برایِ هر نوع اطلاعاتِ
    ساختاریِ اختیاری (سایزگاید، سازنده/منطقه، ویژگی‌های خاص و...).

    طراحی:
    - ``namespace``: دسته‌بندیِ منطقی (مثلاً ``size_guide``, ``artisan``, ``specs``)
    - ``key``: کلیدِ مشخص در آن namespace (مثلاً ``chart_html``, ``maker``, ``region``)
    - ``value_text``: مقدارِ متنی (برای متن ساده و HTML)
    - ``value_json``: مقدارِ ساختاری (برای جدول سایز، لیست‌ها و...)

    یک محصول می‌تواند تعداد دلخواه metafield داشته باشد. تمپلیت‌ها از
    یک template tag مشترک استفاده می‌کنند.

    Store-owned: هر metafield به یک Product وصل است و Product خودش
    Store-owned است — پس ایزولاسیونِ چندمستأجری از طریقِ Product تضمین
    می‌شود (نیازی به فیلدِ store مستقیم نیست)."""

    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="metafields",
    )
    namespace = models.CharField(
        "فضای نام", max_length=40, db_index=True,
        help_text="دسته‌بندیِ منطقی: size_guide, artisan, specs, custom",
    )
    key = models.CharField(
        "کلید", max_length=60,
        help_text="کلیدِ مشخص: chart_html, maker, region, material, dimensions",
    )
    value_text = models.TextField(
        "مقدارِ متنی", blank=True, default="",
        help_text="برای متن ساده، HTML امن (سایزگاید)، یا مقادیرِ کوتاه.",
    )
    value_json = models.JSONField(
        "مقدارِ ساختاری", null=True, blank=True, default=None,
        help_text="برای داده‌ی ساختاری: جدول سایز، لیست ویژگی‌ها و...",
    )

    class Meta:
        verbose_name = "متادیتای کالا"
        verbose_name_plural = "متادیتاهای کالا"
        ordering = ["namespace", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "namespace", "key"],
                name="uniq_product_metafield",
            ),
        ]

    def __str__(self):
        return f"{self.namespace}.{self.key} = {self.value_text[:50] or '(JSON)'}"


# ---------------------------------------------------------------- Namespace constants (convenience)
METAFIELD_NS_SIZE_GUIDE = "size_guide"
METAFIELD_NS_ARTISAN = "artisan"
METAFIELD_NS_SPECS = "specs"
METAFIELD_NS_CUSTOM = "custom"


class MerchantCollection(TimeStampedModel):
    """کالکشنِ دستیِ مرچنت — گروه‌بندیِ merchandising مستقل با صفحه‌ی عمومیِ
    مخصوص به خود (فاز B نقشه‌راه سازنده بصری).

    این مدل معادلِ واقعیِ «Collection»ای است که ممیزیِ فاز قبل
    (``docs/reports/STOREFRONT_TEMPLATE_AND_BUILDER_AUDIT.md`` بخش ۶) آن را
    از ``ProductTag(purpose="collection")`` («گروهِ دوم») متمایز کرد: آن
    مدل فاقدِ تصویر/سئو/ترتیبِ دستی/صفحه‌ی مستقل است و عمداً دست‌نخورده
    باقی می‌ماند — نگاه کنید به ``apps.catalog.services.tag_service`` و
    دستورِ اختیاریِ تبدیلِ داده‌های قدیمی
    ``migrate_legacy_product_tag_collections``.

    ``collection_type`` از روز اول برای ``smart`` رزرو شده اما در این فاز
    فقط ``manual`` توسطِ سرویس‌ها/UI پذیرفته می‌شود — بدونِ موتورِ قوانینِ
    هوشمند (که به فازِ بعد موکول شده)."""

    class CollectionType(models.TextChoices):
        MANUAL = "manual", "دستی"
        SMART = "smart", "هوشمند"  # رزروشده — هنوز هیچ سرویس/UIای این نوع را نمی‌پذیرد

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="merchant_collections",
    )
    name = models.CharField("نام", max_length=150)
    slug = models.SlugField("اسلاگ", max_length=170, allow_unicode=True)
    description = models.TextField("توضیحات", blank=True)
    image = models.ImageField("تصویر", upload_to="collections/images/", null=True, blank=True)
    is_active = models.BooleanField("فعال", default=True)
    collection_type = models.CharField(
        "نوع کالکشن", max_length=10, choices=CollectionType.choices, default=CollectionType.MANUAL,
    )
    seo_title = models.CharField("عنوان سئو", max_length=70, blank=True, default="")
    seo_description = models.CharField("توضیحات متا", max_length=160, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ایجادکننده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="آخرین ویرایشگر", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    # ردیابی صرفاً اطلاعاتیِ منشأِ تبدیلِ اختیاریِ «گروه دوم» (همان الگویِ
    # ``Category.source_template_category``) — فقط توسطِ دستورِ مدیریتیِ
    # ``migrate_legacy_product_tag_collections`` نوشته می‌شود، هرگز توسطِ
    # مسیرِ عادیِ ساختِ کالکشن. تنها برایِ idempotent بودنِ اجرایِ دوباره‌ی
    # همان دستور استفاده می‌شود؛ حذفِ ProductTag مبدأ هرگز این کالکشن یا
    # داده‌اش را حذف نمی‌کند (SET_NULL).
    source_legacy_product_tag = models.ForeignKey(
        "ProductTag", verbose_name="برچسبِ «گروه دوم» مبدأ", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="converted_collections",
    )

    class Meta:
        verbose_name = "کالکشن"
        verbose_name_plural = "کالکشن‌ها"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "slug"], name="uniq_merchantcollection_slug_per_store"),
        ]
        indexes = [
            models.Index(fields=["store", "is_active"], name="idx_collection_store_active"),
            models.Index(fields=["store", "name"], name="idx_collection_store_name"),
        ]

    def __str__(self):
        return self.name


class MerchantCollectionItem(TimeStampedModel):
    """یک کالایِ عضوِ یک کالکشنِ دستی، با ترتیبِ نمایشِ صریح.

    عمداً یک مدلِ ``through`` واقعی است (نه ``ManyToManyField`` ساده)، چون
    ترتیبِ دستی خودش یک فیلدِ داده‌ای است، نه چیزی که بتوان از ترتیبِ درجِ
    ردیف حدس زد — نگاه کنید به یافته‌ی ممیزیِ فاز A درباره‌ی
    ``Product.tags`` (بخش ۶: «بدونِ فیلدِ order روی رابطه»)."""

    collection = models.ForeignKey(
        MerchantCollection, verbose_name="کالکشن", on_delete=models.CASCADE, related_name="items",
    )
    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="collection_items",
    )
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "قلمِ کالکشن"
        verbose_name_plural = "اقلامِ کالکشن"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "product"], name="uniq_collectionitem_product_per_collection",
            ),
        ]
        indexes = [
            models.Index(fields=["collection", "order"], name="idx_mci_collection_order"),
        ]

    def __str__(self):
        return f"{self.collection.name} — {self.product.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.collection_id and self.product_id and self.product.store_id != self.collection.store_id:
            raise ValidationError({"product": "کالا متعلق به فروشگاه دیگری است."})


class ProductOption(TimeStampedModel):
    """محور تنوع‌سازِ یک کالای مشخص (مثلاً «رنگ» یا «سایز») — نگاه کنید به ADR-19."""

    class InputType(models.TextChoices):
        TEXT = "text", "متن"
        COLOR = "color", "رنگ"
        NUMBER = "number", "عدد"

    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="options")
    attribute = models.ForeignKey(
        Attribute, verbose_name="ویژگی مرتبط", on_delete=models.PROTECT, null=True, blank=True,
        related_name="product_options",
    )
    label = models.CharField("عنوان محور", max_length=60)
    normalized_label = models.CharField(max_length=80, editable=False, blank=True, default="")
    input_type = models.CharField(
        "نوعِ ورودیِ مقادیر", max_length=10, choices=InputType.choices, default=InputType.TEXT,
    )
    position = models.PositiveSmallIntegerField("موقعیت", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "محور تنوع کالا"
        verbose_name_plural = "محورهای تنوع کالا"
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "position"], name="uniq_option_position_per_product"),
            models.UniqueConstraint(
                fields=["product", "normalized_label"], condition=models.Q(is_active=True),
                name="uniq_active_option_label_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from apps.core.utils import normalization_key

        errors = {}
        label = (self.label or "").strip()
        if not label:
            errors["label"] = "عنوان محور نمی‌تواند خالی باشد."
        if self.attribute_id and self.product_id and self.attribute.store_id != self.product.store_id:
            errors["attribute"] = "این ویژگی متعلق به فروشگاه دیگری است."
        if self.attribute_id and not self.attribute.is_variant_axis:
            errors["attribute"] = "این ویژگی برای محور تنوع مجاز نیست."
        if errors:
            raise ValidationError(errors)
        self.label = label
        self.normalized_label = normalization_key(label)


class ProductOptionValue(TimeStampedModel):
    """یکی از مقادیر یک محور تنوع مشخص (مثلاً محور «رنگ» -> مقدار «سبز»)."""

    option = models.ForeignKey(ProductOption, verbose_name="محور", on_delete=models.CASCADE, related_name="values")
    attribute_value = models.ForeignKey(
        AttributeValue, verbose_name="مقدار ویژگی مرتبط", on_delete=models.PROTECT, null=True, blank=True,
        related_name="option_values",
    )
    label = models.CharField("برچسب", max_length=60)
    normalized_label = models.CharField(max_length=80, editable=False, blank=True, default="")
    color_hex = models.CharField("کد رنگ (Hex)", max_length=9, blank=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "مقدار محور تنوع"
        verbose_name_plural = "مقادیر محور تنوع"
        ordering = ["display_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["option", "normalized_label"], condition=models.Q(is_active=True),
                name="uniq_active_option_value_label",
            ),
        ]

    def __str__(self):
        return f"{self.option.label}: {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from apps.core.utils import normalization_key

        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": "برچسب مقدار نمی‌تواند خالی باشد."})
        self.label = label
        self.normalized_label = normalization_key(label)


class VariantOptionValue(TimeStampedModel):
    """هویت پایدارِ هر محور برای یک تنوع تولیدشده — نگاه کنید به ADR-20.

    ``option_value`` عمداً ``PROTECT`` است: یک ProductOptionValue که هنوز
    هویت یک تنوع را می‌سازد هرگز نباید hard-delete شود — حذف امن فقط از
    مسیر غیرفعال‌سازی + بازتولید (``variant_engine_service``) ممکن است."""

    variant = models.ForeignKey(
        ProductVariant, verbose_name="تنوع", on_delete=models.CASCADE, related_name="option_values",
    )
    option = models.ForeignKey(ProductOption, verbose_name="محور", on_delete=models.CASCADE, related_name="variant_links")
    option_value = models.ForeignKey(
        ProductOptionValue, verbose_name="مقدار", on_delete=models.PROTECT, related_name="variant_links",
    )

    class Meta:
        verbose_name = "مقدار محورِ تنوع"
        verbose_name_plural = "مقادیر محورهای تنوع"
        constraints = [
            models.UniqueConstraint(fields=["variant", "option"], name="uniq_variant_option_axis"),
            models.UniqueConstraint(fields=["variant", "option_value"], name="uniq_variant_option_value"),
        ]

    def __str__(self):
        return f"{self.variant} — {self.option.label}: {self.option_value.label}"


# =============================================================================
# قالب‌های صنف پلتفرم و طرح ویژگی دسته‌بندی (Phase 1E) — نگاه کنید به
# ADR-22 (استراتژی کپی قالب صنف)، ADR-23 (وراثت طرح ویژگی دسته‌بندی)،
# ADR-24 (چرخه‌ی عمر مقدار ویژگی هنگام تغییر دسته‌بندی) و ADR-25
# (نسخه‌بندی قالب صنف) در SAAS_DOMAIN_DECISIONS.md.
#
# قالب‌های IndustryTemplate* متعلق به پلتفرم‌اند — هیچ‌کدام FK به Store
# ندارند و هرگز از مسیر StoreMembership قابل نوشتن نیستند (فقط Django
# admin/دستور مدیریتی — نگاه کنید به ADR-22). نصب یک قالب صنف روی یک
# Store، رکوردهای Category/Attribute/CategoryAttributeSchema *جدید و
# کاملاً مالکیت Store* می‌سازد (deep copy) — نه رفرنس زنده به قالب.
# =============================================================================


class IndustryTemplate(TimeStampedModel):
    """یک نسخه‌ی غیرقابل‌تغییر از ساختار کاتالوگ پیشنهادی یک صنف — پلتفرم‌محور.

    نسخه‌ی جدید یک صنف همیشه یک ردیف کاملاً جدید است، نه ویرایش این ردیف
    (ADR-25) — بنابراین هیچ رکورد IndustryTemplate پس از ساخته‌شدن هرگز
    توسط کد این فاز تغییر نمی‌کند."""

    class Readiness(models.TextChoices):
        """چرخه‌ی عمر آمادگیِ قالب — نگاه کنید به ADR-26.

        فقط ``PRODUCTION_READY`` به مرچنت‌ها برای نصب جدید پیشنهاد می‌شود؛
        بقیه‌ی حالت‌ها فقط برای اپراتور پلتفرم (پنل ادمین) قابل‌مشاهده‌اند."""

        DRAFT = "draft", "پیش‌نویس"
        VALIDATION_FAILED = "validation_failed", "اعتبارسنجی ناموفق"
        REVIEW_REQUIRED = "review_required", "نیازمند بازبینی"
        PRODUCTION_READY = "production_ready", "آماده‌ی تولید"
        DEPRECATED = "deprecated", "منسوخ"
        ARCHIVED = "archived", "بایگانی‌شده"

    class Sector(models.TextChoices):
        """رسته‌ی اصلیِ صنف — برای فیلترِ تب‌محورِ انتخاب‌گرِ صنف (کاتالوگِ تأییدشده)."""

        RETAIL = "retail", "خرده‌فروشی و پوشاک"
        DIGITAL = "digital", "دیجیتال و الکترونیک"
        FOOD = "food", "خوراک و نوشیدنی"
        HOME = "home", "خانه و آشپزخانه"
        BEAUTY = "beauty", "سلامت و زیبایی"
        SPORT = "sport", "ورزش و سرگرمی"
        CULTURE = "culture", "فرهنگ و آموزش"
        AUTO = "auto", "خودرو و ابزار"
        INDUSTRY = "industry", "صنعتی و ساختمان"
        SERVICES = "services", "خدمات و تخصصی"
        OTHER = "other", "سایر"

    slug = models.SlugField("اسلاگ", max_length=60)
    name = models.CharField("نام صنف", max_length=120)
    description = models.TextField("توضیحات", blank=True)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    sector = models.CharField("رسته", max_length=20, choices=Sector.choices, default=Sector.OTHER)
    version = models.PositiveIntegerField("نسخه", default=1)
    locale = models.CharField("زبان", max_length=10, default="fa")
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)
    readiness = models.CharField(
        "آمادگی", max_length=20, choices=Readiness.choices, default=Readiness.DRAFT,
    )
    content_fingerprint = models.CharField(
        "اثرانگشت محتوا", max_length=64, blank=True, default="",
        help_text="هش SHA-256 قطعی محتوای قالب — نگاه کنید به ADR-27",
    )
    default_section_keys = models.JSONField(
        "بخش‌های پیشنهادی صفحه اصلی", default=list, blank=True,
        help_text=(
            "فهرست ترتیب‌دارِ کلیدهای نوع بخش (سازنده‌ی بصری صفحه فروشگاه) که "
            "چیدمان پیشنهادیِ این صنف را می‌سازند. اعتبارسنجیِ این کلیدها در برابر "
            "Section Registry در لایه‌ی apps.storefront_builder انجام می‌شود، نه اینجا، "
            "تا apps.catalog به آن اپ وابسته نشود."
        ),
    )

    class Meta:
        verbose_name = "قالب صنف"
        verbose_name_plural = "قالب‌های صنف"
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["slug", "version"], name="uniq_industry_template_slug_version"),
        ]

    def __str__(self):
        return f"{self.name} (نسخه {self.version})"

    @property
    def is_offerable_for_new_installation(self):
        return self.is_active and self.readiness == self.Readiness.PRODUCTION_READY


class IndustryTemplateCategory(TimeStampedModel):
    industry_template = models.ForeignKey(
        IndustryTemplate, verbose_name="قالب صنف", on_delete=models.CASCADE, related_name="categories",
    )
    code = models.SlugField("کد پایدار", max_length=60, allow_unicode=True)
    name = models.CharField("نام", max_length=120)
    icon = models.CharField("آیکون", max_length=20, blank=True)
    parent = models.ForeignKey(
        "self", verbose_name="دسته‌ی والد", on_delete=models.CASCADE, null=True, blank=True,
        related_name="children",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "دسته‌بندی قالب صنف"
        verbose_name_plural = "دسته‌بندی‌های قالب صنف"
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["industry_template", "code"], name="uniq_template_category_code_per_template",
            ),
        ]

    def __str__(self):
        return f"{self.industry_template.name} — {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.parent_id and self.industry_template_id and self.parent.industry_template_id != self.industry_template_id:
            raise ValidationError({"parent": "دسته‌ی والد متعلق به قالب صنف دیگری است."})


class IndustryTemplateAttribute(TimeStampedModel):
    industry_template = models.ForeignKey(
        IndustryTemplate, verbose_name="قالب صنف", on_delete=models.CASCADE, related_name="attributes",
    )
    code = models.SlugField("کد پایدار", max_length=60, allow_unicode=True)
    label = models.CharField("عنوان نمایشی", max_length=120)
    data_type = models.CharField(
        "نوع داده", max_length=12, choices=Attribute.DataType.choices, default=Attribute.DataType.TEXT,
    )
    display_type = models.CharField(
        "نوع نمایش", max_length=12, choices=Attribute.DisplayType.choices, blank=True, default="",
    )
    unit = models.CharField("واحد", max_length=30, blank=True)
    is_variant_axis = models.BooleanField("واجد شرایط محور تنوع", default=False)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "ویژگی قالب صنف"
        verbose_name_plural = "ویژگی‌های قالب صنف"
        ordering = ["display_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["industry_template", "code"], name="uniq_template_attribute_code_per_template",
            ),
        ]

    def __str__(self):
        return f"{self.industry_template.name} — {self.label}"


class IndustryTemplateAttributeValue(TimeStampedModel):
    template_attribute = models.ForeignKey(
        IndustryTemplateAttribute, verbose_name="ویژگی قالب", on_delete=models.CASCADE, related_name="values",
    )
    label = models.CharField("برچسب", max_length=120)
    value = models.CharField("مقدار داخلی", max_length=120, blank=True, default="")
    color_hex = models.CharField("کد رنگ (Hex)", max_length=9, blank=True)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "مقدار ویژگی قالب صنف"
        verbose_name_plural = "مقادیر ویژگی قالب صنف"
        ordering = ["display_order", "label"]

    def __str__(self):
        return f"{self.template_attribute.label}: {self.label}"


class IndustryTemplateCategoryAttributeMapping(TimeStampedModel):
    """این ویژگی روی این دسته‌بندیِ قالب صنف باید نمایش داده شود — با تنظیمات پیش‌فرض."""

    template_category = models.ForeignKey(
        IndustryTemplateCategory, verbose_name="دسته‌بندی قالب", on_delete=models.CASCADE,
        related_name="attribute_mappings",
    )
    template_attribute = models.ForeignKey(
        IndustryTemplateAttribute, verbose_name="ویژگی قالب", on_delete=models.CASCADE,
        related_name="category_mappings",
    )
    group = models.CharField("گروه/بخش", max_length=80, blank=True, default="")
    group_order = models.PositiveIntegerField("ترتیب گروه", default=0)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_required = models.BooleanField("الزامی", default=False)
    is_filterable = models.BooleanField("قابل فیلتر", default=False)
    is_comparable = models.BooleanField("قابل مقایسه", default=False)
    is_searchable = models.BooleanField("قابل جست‌وجو", default=False)
    help_text = models.CharField("متن راهنما", max_length=300, blank=True, default="")
    placeholder = models.CharField("متن جای‌گیر", max_length=120, blank=True, default="")

    class Meta:
        verbose_name = "نگاشت ویژگی-دسته‌بندی قالب صنف"
        verbose_name_plural = "نگاشت‌های ویژگی-دسته‌بندی قالب صنف"
        ordering = ["group_order", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["template_category", "template_attribute"], name="uniq_template_category_attribute",
            ),
        ]

    def __str__(self):
        return f"{self.template_category.name} — {self.template_attribute.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if (
            self.template_category_id and self.template_attribute_id
            and self.template_category.industry_template_id != self.template_attribute.industry_template_id
        ):
            raise ValidationError({"template_attribute": "این ویژگی متعلق به قالب صنف دیگری است."})


class IndustryTemplateRecommendedOption(TimeStampedModel):
    """محور تنوع پیشنهادی برای این دسته‌بندیِ قالب صنف (مثلاً «رنگ» برای «تی‌شرت»)."""

    template_category = models.ForeignKey(
        IndustryTemplateCategory, verbose_name="دسته‌بندی قالب", on_delete=models.CASCADE,
        related_name="recommended_options",
    )
    template_attribute = models.ForeignKey(
        IndustryTemplateAttribute, verbose_name="ویژگی قالب", on_delete=models.CASCADE,
        related_name="recommended_for_categories",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "محور تنوع پیشنهادی قالب صنف"
        verbose_name_plural = "محورهای تنوع پیشنهادی قالب صنف"
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["template_category", "template_attribute"], name="uniq_template_recommended_option",
            ),
        ]

    def __str__(self):
        return f"{self.template_category.name} — {self.template_attribute.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.template_attribute_id and not self.template_attribute.is_variant_axis:
            raise ValidationError({
                "template_attribute": "فقط ویژگی‌های واجد شرایط محور تنوع می‌توانند پیشنهاد شوند.",
            })


class StoreIndustryInstallation(TimeStampedModel):
    """رکورد نصب یک قالب صنف روی یک Store — نگاه کنید به ADR-25.

    یک Store در طول عمرش فقط می‌تواند یک بار نصب انجام دهد (سیاست ساده و
    امن انتخاب‌شده در ADR-25)؛ ``UniqueConstraint`` روی ``store`` این را
    در سطح دیتابیس هم تضمین می‌کند، نه فقط در لایه‌ی سرویس."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "نصب‌شده"
        FAILED = "failed", "ناموفق"

    store = models.OneToOneField(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="industry_installation",
    )
    industry_template = models.ForeignKey(
        IndustryTemplate, verbose_name="قالب صنف", on_delete=models.PROTECT, related_name="installations",
    )
    installed_version = models.PositiveIntegerField("نسخه‌ی نصب‌شده")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.COMPLETED)
    categories_created = models.PositiveIntegerField("تعداد دسته‌بندی ساخته‌شده", default=0)
    attributes_created = models.PositiveIntegerField("تعداد ویژگی ساخته‌شده", default=0)

    class Meta:
        verbose_name = "نصب قالب صنف"
        verbose_name_plural = "نصب‌های قالب صنف"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.store.name} ← {self.industry_template.name}"


class CategoryAttributeSchema(TimeStampedModel):
    """طرح ویژگیِ یک دسته‌بندیِ متعلق به Store — نگاه کنید به ADR-23.

    ``is_inherited_by_children`` فقط نگاشت این ردیف را کنترل می‌کند: آیا
    این ردیف باید به زیردسته‌ها هم به ارث برسد یا نه. این دسته همیشه
    نگاشت مستقیم خودش را استفاده می‌کند، صرف‌نظر از مقدار این پرچم روی
    ردیف‌های خودش — این پرچم فقط جهت تأثیر رو به پایین (روی فرزندان) را
    تعیین می‌کند."""

    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی", on_delete=models.CASCADE, related_name="attribute_schema_entries",
    )
    attribute = models.ForeignKey(
        Attribute, verbose_name="ویژگی", on_delete=models.PROTECT, related_name="category_schema_entries",
    )
    group = models.CharField("گروه/بخش", max_length=80, blank=True, default="")
    group_order = models.PositiveIntegerField("ترتیب گروه", default=0)
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_required = models.BooleanField("الزامی", default=False)
    is_filterable_override = models.BooleanField("قابل فیلتر (بازنویسی)", null=True, blank=True)
    is_comparable_override = models.BooleanField("قابل مقایسه (بازنویسی)", null=True, blank=True)
    is_searchable_override = models.BooleanField("قابل جست‌وجو (بازنویسی)", null=True, blank=True)
    help_text = models.CharField("متن راهنما", max_length=300, blank=True, default="")
    placeholder = models.CharField("متن جای‌گیر", max_length=120, blank=True, default="")
    is_visible_on_storefront = models.BooleanField("نمایش در فروشگاه", default=True)
    is_inherited_by_children = models.BooleanField("به ارث رسیدن به زیردسته‌ها", default=True)
    source_template_mapping = models.ForeignKey(
        IndustryTemplateCategoryAttributeMapping, verbose_name="نگاشت مبدأ در قالب صنف", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="installed_mappings",
    )

    class Meta:
        verbose_name = "طرح ویژگی دسته‌بندی"
        verbose_name_plural = "طرح‌های ویژگی دسته‌بندی"
        ordering = ["group_order", "display_order"]
        constraints = [
            models.UniqueConstraint(fields=["category", "attribute"], name="uniq_category_attribute_schema"),
        ]

    def __str__(self):
        return f"{self.category.name} — {self.attribute.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.attribute_id and self.category_id and self.attribute.store_id != self.category.store_id:
            raise ValidationError({"attribute": "این ویژگی متعلق به فروشگاه دیگری است."})

    @property
    def is_filterable(self):
        if self.is_filterable_override is not None:
            return self.is_filterable_override
        return self.attribute.is_filterable

    @property
    def is_comparable(self):
        if self.is_comparable_override is not None:
            return self.is_comparable_override
        return self.attribute.is_comparable

    @property
    def is_searchable(self):
        if self.is_searchable_override is not None:
            return self.is_searchable_override
        return self.attribute.is_searchable


class CategoryRecommendedOption(TimeStampedModel):
    """محور تنوع پیشنهادی برای این دسته‌بندیِ متعلق به Store (نسخه‌ی نصب‌شده/دستی)."""

    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی", on_delete=models.CASCADE, related_name="recommended_options",
    )
    attribute = models.ForeignKey(
        Attribute, verbose_name="ویژگی", on_delete=models.CASCADE, related_name="recommended_for_categories",
    )
    display_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "محور تنوع پیشنهادی دسته‌بندی"
        verbose_name_plural = "محورهای تنوع پیشنهادی دسته‌بندی"
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(fields=["category", "attribute"], name="uniq_category_recommended_option"),
        ]

    def __str__(self):
        return f"{self.category.name} — {self.attribute.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.attribute_id and self.category_id and self.attribute.store_id != self.category.store_id:
            errors["attribute"] = "این ویژگی متعلق به فروشگاه دیگری است."
        if self.attribute_id and not self.attribute.is_variant_axis:
            errors["attribute"] = "فقط ویژگی‌های واجد شرایط محور تنوع می‌توانند پیشنهاد شوند."
        if errors:
            raise ValidationError(errors)


# =============================================================================
# چارچوب کیفیت و به‌روزرسانیِ قالب صنف (Phase 1F) — نگاه کنید به ADR-26 تا ADR-29.
# =============================================================================


class IndustryTemplateValidationResult(TimeStampedModel):
    """آخرین نتیجه‌ی اعتبارسنجیِ کش‌شده‌ی یک قالب صنف — نگاه کنید به ADR-26/27.

    چون ردیف‌های فرزندِ ``IndustryTemplate`` پس از ساخت هرگز تغییر
    نمی‌کنند (ADR-25)، این نتیجه فقط وقتی نامعتبر می‌شود که
    ``content_fingerprint``ِ قالب تغییر کند (که خودش یعنی یک ردیف
    ``IndustryTemplate`` کاملاً جدید ساخته شده) — پس یک ردیف کش به‌ازای
    هر (قالب، fingerprint) کافی است، نه یک تاریخچه‌ی نامحدود."""

    class Status(models.TextChoices):
        VALID = "valid", "معتبر"
        INVALID = "invalid", "نامعتبر"

    industry_template = models.OneToOneField(
        IndustryTemplate, verbose_name="قالب صنف", on_delete=models.CASCADE, related_name="validation_result",
    )
    fingerprint = models.CharField("اثرانگشت زمانِ اعتبارسنجی", max_length=64)
    validator_version = models.CharField("نسخه‌ی اعتبارسنج", max_length=20)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices)
    quality_score = models.PositiveSmallIntegerField("امتیاز کیفیت", null=True, blank=True)
    errors = models.JSONField("خطاها", default=list, blank=True)
    warnings = models.JSONField("هشدارها", default=list, blank=True)
    infos = models.JSONField("اطلاعات", default=list, blank=True)
    metrics = models.JSONField("سنجه‌ها", default=dict, blank=True)
    duration_ms = models.PositiveIntegerField("مدت اجرا (میلی‌ثانیه)", null=True, blank=True)

    class Meta:
        verbose_name = "نتیجه‌ی اعتبارسنجی قالب صنف"
        verbose_name_plural = "نتایج اعتبارسنجی قالب صنف"

    def __str__(self):
        return f"{self.industry_template.name} — {self.get_status_display()}"

    @property
    def is_stale(self):
        return self.fingerprint != self.industry_template.content_fingerprint


class StoreTemplateUpdate(TimeStampedModel):
    """تاریخچه‌ی هر تلاش برای به‌روزرسانیِ نصبِ قالب صنف یک Store — نگاه کنید به ADR-29.

    ``idempotency_key`` امکان رد کردن ارسال تکراری/هم‌زمانِ همان درخواست
    را می‌دهد بدون نیاز به قفل سطح‌بالاتر."""

    class Status(models.TextChoices):
        PENDING = "pending", "در حال انجام"
        COMPLETED = "completed", "تکمیل‌شده"
        FAILED = "failed", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="template_updates",
    )
    installation = models.ForeignKey(
        StoreIndustryInstallation, verbose_name="نصب", on_delete=models.CASCADE, related_name="update_attempts",
    )
    from_template = models.ForeignKey(
        IndustryTemplate, verbose_name="قالب مبدأ", on_delete=models.PROTECT, related_name="updates_from",
    )
    target_template = models.ForeignKey(
        IndustryTemplate, verbose_name="قالب مقصد", on_delete=models.PROTECT, related_name="updates_to",
    )
    actor = models.ForeignKey(
        "auth.User", verbose_name="انجام‌دهنده", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="template_updates",
    )
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    idempotency_key = models.CharField("کلید یکتایی درخواست", max_length=80, unique=True)
    started_at = models.DateTimeField("زمان شروع", auto_now_add=True)
    completed_at = models.DateTimeField("زمان پایان", null=True, blank=True)
    selected_change_ids = models.JSONField("تغییرات انتخاب‌شده", default=list, blank=True)
    applied_changes = models.JSONField("تغییرات اعمال‌شده", default=list, blank=True)
    skipped_changes = models.JSONField("تغییرات نادیده‌گرفته‌شده", default=list, blank=True)
    conflicts = models.JSONField("تعارض‌ها", default=list, blank=True)
    failure_reason = models.TextField("دلیل شکست", blank=True, default="")

    class Meta:
        verbose_name = "به‌روزرسانی نصب قالب صنف"
        verbose_name_plural = "به‌روزرسانی‌های نصب قالب صنف"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.store.name}: {self.from_template.version} → {self.target_template.version} ({self.status})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.installation_id and self.store_id and self.installation.store_id != self.store_id:
            raise ValidationError({"installation": "این نصب متعلق به فروشگاه دیگری است."})
        if (
            self.from_template_id and self.target_template_id
            and self.from_template.slug != self.target_template.slug
        ):
            raise ValidationError({"target_template": "قالب مقصد باید از همان خانواده‌ی صنف باشد."})
        if self.from_template_id and self.target_template_id and self.from_template_id == self.target_template_id:
            raise ValidationError({"target_template": "قالب مقصد نمی‌تواند همان نسخه‌ی فعلی باشد."})


class Specification(TimeStampedModel):
    """مشخصه‌ی فنی توصیفی کالا (برچسب/مقدار) — انتخابی مشتری نیست، فقط اطلاعاتی."""

    product = models.ForeignKey(
        Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="specifications"
    )
    label = models.CharField("عنوان مشخصه", max_length=100)
    value = models.CharField("مقدار", max_length=300, blank=True)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "مشخصه فنی"
        verbose_name_plural = "مشخصات فنی"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} — {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": "عنوان مشخصه نمی‌تواند خالی باشد."})
        self.label = label
        self.value = (self.value or "").strip()

    def save(self, *args, **kwargs):
        self.label = (self.label or "").strip()
        self.value = (self.value or "").strip()
        super().save(*args, **kwargs)


class SpecificationTemplate(TimeStampedModel):
    """قالب مشخصات قابل‌استفاده‌ی مجدد — فهرستی از عنوان‌های پیشنهادی، نه یک اسکیمای پیچیده."""

    name = models.CharField("نام قالب", max_length=100, unique=True)
    category = models.ForeignKey(
        Category, verbose_name="دسته‌بندی مرتبط", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="specification_templates",
    )

    class Meta:
        verbose_name = "قالب مشخصات"
        verbose_name_plural = "قالب‌های مشخصات"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SpecificationTemplateField(TimeStampedModel):
    template = models.ForeignKey(
        SpecificationTemplate, verbose_name="قالب", on_delete=models.CASCADE, related_name="fields"
    )
    label = models.CharField("عنوان مشخصه", max_length=100)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "فیلد قالب مشخصات"
        verbose_name_plural = "فیلدهای قالب مشخصات"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["template", "label"], name="uniq_template_field_label"),
        ]

    def __str__(self):
        return f"{self.template.name} — {self.label}"

    def clean(self):
        from django.core.exceptions import ValidationError

        label = (self.label or "").strip()
        if not label:
            raise ValidationError({"label": "عنوان فیلد نمی‌تواند خالی باشد."})
        self.label = label

    def save(self, *args, **kwargs):
        self.label = (self.label or "").strip()
        super().save(*args, **kwargs)


class Review(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="کالا", on_delete=models.CASCADE, related_name="reviews")
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField("امتیاز", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("متن نظر")
    is_approved = models.BooleanField("تأییدشده", default=False)

    class Meta:
        verbose_name = "نظر"
        verbose_name_plural = "نظرات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} — {self.product.name} ({self.rating}★)"
