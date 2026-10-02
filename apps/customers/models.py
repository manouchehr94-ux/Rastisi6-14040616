from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Customer(TimeStampedModel):
    """پروفایل مشتری — گسترش کاربر جنگو."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="customer_profile"
    )
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)
    phone = models.CharField("موبایل", max_length=15, unique=True)
    email = models.EmailField("ایمیل", blank=True)
    city = models.CharField("شهر", max_length=80, blank=True)
    is_vip = models.BooleanField("مشتری ویژه (VIP)", default=False)
    orders_count = models.PositiveIntegerField("تعداد سفارش‌ها", default=0)
    total_spent = models.DecimalField("مجموع خرید (تومان)", max_digits=14, decimal_places=0, default=0)

    # تاریخ تولد — میلادی ذخیره می‌شود (قراردادِ تاریخ‌هایِ پروژه)؛ ورودی/نمایشِ
    # جلالی در لایه‌ی فرم است (``apps.core.jalali_utils``). اختیاری؛ یک مقدارِ
    # خالی هرگز تولدِ ذخیره‌شده را پاک نمی‌کند (نگاه کنید به
    # ``customer_profile_service.update_birth_date``).
    birth_date = models.DateField("تاریخ تولد", null=True, blank=True)
    # کلیدِ قابل‌ایندکسِ «ماه*۱۰۰+روزِ جلالی» برایِ جست‌وجوی سریعِ تولدهایِ یک
    # روز بدونِ پیمایشِ همه‌ی مشتریان — همیشه در ``save`` از ``birth_date`` بازسازی می‌شود.
    birth_month_day = models.PositiveSmallIntegerField(
        "ماه/روزِ تولد (جلالی)", null=True, blank=True, db_index=True, editable=False,
    )

    # ترجیحاتِ ارتباطی — پیام‌هایِ تبلیغاتی (کمپین/تولد/مناسبت) فقط در صورتِ
    # رضایت ارسال می‌شود؛ پیام‌هایِ تراکنشی/امنیتی (سفارش، OTP…) مستقل‌اند.
    accepts_promotional_sms = models.BooleanField("دریافتِ پیامکِ تبلیغاتی", default=True)
    accepts_promotional_email = models.BooleanField("دریافتِ ایمیلِ تبلیغاتی", default=True)

    class Meta:
        verbose_name = "مشتری"
        verbose_name_plural = "مشتریان"
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        from apps.core.jalali_utils import birthday_month_day_key

        self.birth_month_day = birthday_month_day_key(self.birth_date)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "birth_date" in update_fields:
            kwargs["update_fields"] = list(set(update_fields) | {"birth_month_day"})
        super().save(*args, **kwargs)

    @property
    def joined_at(self):
        return self.created_at


class Address(TimeStampedModel):
    customer = models.ForeignKey(Customer, verbose_name="مشتری", on_delete=models.CASCADE, related_name="addresses")
    receiver_name = models.CharField("نام گیرنده", max_length=150)
    phone = models.CharField("موبایل گیرنده", max_length=15)
    province = models.CharField("استان", max_length=80)
    city = models.CharField("شهر", max_length=80)
    postal_code = models.CharField("کد پستی", max_length=10, blank=True)
    full_address = models.TextField("آدرس پستی کامل")
    is_default = models.BooleanField("آدرس پیش‌فرض", default=False)

    class Meta:
        verbose_name = "آدرس"
        verbose_name_plural = "آدرس‌ها"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.receiver_name} — {self.city}"


class CustomerTag(TimeStampedModel):
    """برچسبِ Store-owned برای دسته‌بندیِ مشتریان (مثلاً «مشتریِ عمده»،
    «شکایت‌دار») — نگاه کنید به checkpoint 4 §16.

    ``code`` فقط در محدوده‌ی همین Store یکتاست (دو Store می‌توانند کدِ
    یکسان داشته باشند)؛ حذفِ فیزیکی وقتی برچسب به پروفایلی متصل است مجاز
    نیست (نگاه کنید به ``crm_service.archive_customer_tag``) — به‌جای آن
    آرشیو (``is_active=False``) می‌شود، دقیقاً همان الگویِ
    ``Attribute``/``Warehouse``."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="customer_tags",
    )
    name = models.CharField("نام", max_length=60)
    code = models.SlugField("کد", max_length=60, allow_unicode=True)
    description = models.CharField("توضیحات", max_length=200, blank=True, default="")
    color = models.CharField("رنگ (Hex)", max_length=9, blank=True, default="")
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "برچسبِ مشتری"
        verbose_name_plural = "برچسب‌های مشتری"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["store", "code"], name="uniq_customertag_code_per_store"),
        ]

    def __str__(self):
        return self.name


class CustomerProfile(TimeStampedModel):
    """دیدِ Store-scopedِ یک ``Customer`` — نگاه کنید به ADR-50 در
    ``SAAS_DOMAIN_DECISIONS.md`` و checkpoint 4 §14.

    ``Customer`` عمداً سراسری است (بدونِ فیلدِ ``store``)؛ این مدل داده‌ای
    که مخصوصِ رابطه‌ی «این Store با این مشتری» است را نگه می‌دارد، بدونِ
    این‌که به هویتِ سراسریِ Customer دست بزند. با ``get_or_create`` در
    اولین نیاز ساخته می‌شود (نگاه کنید به ``crm_service.get_or_create_profile``)
    — نه با یک مهاجرتِ پرهزینه که برای هر جفتِ Store×Customer از پیش
    ردیف بسازد.

    ``order_count``/``total_spent``/``first_order_at``/``last_order_at``
    فیلدهای کش‌شده‌اند که فقط با فراخوانیِ صریحِ
    ``crm_service.refresh_customer_profile_stats`` به‌روز می‌شوند — هرگز با
    signal خودکار (تا staleness آن‌ها همیشه صادقانه و قابل‌پیش‌بینی باشد،
    نه یک وعده‌ی «همیشه زنده» که برآورده نمی‌شود)."""

    class InternalStatus(models.TextChoices):
        NORMAL = "normal", "عادی"
        VIP = "vip", "ویژه (VIP)"
        WATCH = "watch", "تحتِ نظر"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="customer_profiles",
    )
    customer = models.ForeignKey(
        Customer, verbose_name="مشتری", on_delete=models.CASCADE, related_name="store_profiles",
    )
    display_name_override = models.CharField("نامِ نمایشیِ اختصاصی", max_length=150, blank=True, default="")
    internal_status = models.CharField(
        "وضعیتِ داخلی", max_length=10, choices=InternalStatus.choices, default=InternalStatus.NORMAL,
    )
    internal_notes_summary = models.CharField(
        "خلاصه‌ی یادداشتِ داخلی (سنجاق‌شده)", max_length=300, blank=True, default="",
    )
    tags = models.ManyToManyField(CustomerTag, verbose_name="برچسب‌ها", blank=True, related_name="profiles")

    order_count = models.PositiveIntegerField("تعداد سفارش (کش‌شده)", default=0)
    total_spent = models.DecimalField("مجموع خرید — کش‌شده (تومان)", max_digits=14, decimal_places=0, default=0)
    first_order_at = models.DateTimeField("اولین سفارش", null=True, blank=True)
    last_order_at = models.DateTimeField("آخرین سفارش", null=True, blank=True)
    stats_refreshed_at = models.DateTimeField("زمانِ آخرینِ به‌روزرسانیِ آمار", null=True, blank=True)

    class Meta:
        verbose_name = "پروفایلِ مشتریِ فروشگاه"
        verbose_name_plural = "پروفایل‌های مشتریِ فروشگاه"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["store", "customer"], name="uniq_customerprofile_per_store"),
        ]

    def __str__(self):
        return f"{self.customer.full_name} @ {self.store.slug}"

    def display_name(self) -> str:
        return self.display_name_override or self.customer.full_name


class CustomerNote(TimeStampedModel):
    """یادداشتِ داخلیِ کارکنانِ Store روی یک ``CustomerProfile`` — هرگز در
    فروشگاهِ عمومی نمایش داده نمی‌شود (نگاه کنید به checkpoint 4 §17)."""

    profile = models.ForeignKey(
        CustomerProfile, verbose_name="پروفایلِ مشتری", on_delete=models.CASCADE, related_name="notes",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="نویسنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="customer_notes_authored",
    )
    body = models.TextField("متن")
    is_pinned = models.BooleanField("سنجاق‌شده", default=False)

    class Meta:
        verbose_name = "یادداشتِ مشتری"
        verbose_name_plural = "یادداشت‌های مشتری"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return f"یادداشتِ {self.profile} — {self.created_at:%Y-%m-%d}"


class CustomerSegment(TimeStampedModel):
    """گروهِ Store-scopedِ مشتریان — دستی (``static``) یا مبتنی‌بر قاعده
    (``dynamic``) — نگاه کنید به checkpoint 4 §18-19 و ADR-53.

    برایِ نوعِ ``dynamic``، عضویتِ زنده همیشه از طریقِ کوئریِ Store-scoped
    محاسبه می‌شود (نگاه کنید به ``segment_service.evaluate_segment``)؛
    ``CustomerSegmentMembership`` فقط با فراخوانیِ صریحِ «تازه‌سازی»
    (``refresh_segment_membership``) از رویِ همان محاسبه پر می‌شود — هرگز
    خودکار/زمان‌بندی‌شده (نگاه کنید به ADR-53 برایِ محدودیتِ صادقانه‌ی این
    تصمیم)."""

    class SegmentType(models.TextChoices):
        STATIC = "static", "دستی (Static)"
        DYNAMIC = "dynamic", "مبتنی‌بر قاعده (Dynamic)"

    class MatchMode(models.TextChoices):
        ALL = "all", "همه‌ی قاعده‌ها (AND)"
        ANY = "any", "هرکدام از قاعده‌ها (OR)"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="customer_segments",
    )
    name = models.CharField("نام", max_length=100)
    description = models.CharField("توضیحات", max_length=300, blank=True, default="")
    segment_type = models.CharField("نوع", max_length=10, choices=SegmentType.choices, default=SegmentType.STATIC)
    match_mode = models.CharField("حالتِ تطبیق", max_length=5, choices=MatchMode.choices, default=MatchMode.ALL)
    is_active = models.BooleanField("فعال", default=True)

    last_evaluated_at = models.DateTimeField("زمانِ آخرینِ ارزیابی", null=True, blank=True)
    last_evaluation_duration_ms = models.PositiveIntegerField("مدتِ آخرینِ ارزیابی (میلی‌ثانیه)", null=True, blank=True)
    last_evaluation_error = models.TextField("خطایِ آخرینِ ارزیابی", blank=True, default="")

    class Meta:
        verbose_name = "سگمنتِ مشتری"
        verbose_name_plural = "سگمنت‌های مشتری"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


#: نگاه کنید به ``apps.dashboard.services.segment_service`` برایِ منطقِ
#: واقعیِ ارزیابی — این ماژول (models.py) فقط شکلِ داده را تعریف می‌کند، نه
#: قواعدِ مجاز/عملگرها، تا موتورِ قاعده در یک جا (allowlist سرویس) بماند.
class CustomerSegmentRule(TimeStampedModel):
    segment = models.ForeignKey(CustomerSegment, verbose_name="سگمنت", on_delete=models.CASCADE, related_name="rules")
    field = models.CharField("فیلد", max_length=40)
    operator = models.CharField("عملگر", max_length=40)
    value = models.CharField("مقدار", max_length=200, blank=True, default="")
    value2 = models.CharField("مقدارِ دوم (برایِ between)", max_length=200, blank=True, default="")
    position = models.PositiveIntegerField("ترتیب", default=0)

    class Meta:
        verbose_name = "قاعده‌یِ سگمنت"
        verbose_name_plural = "قاعده‌هایِ سگمنت"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.field} {self.operator} {self.value}"


class CustomerSegmentMembership(TimeStampedModel):
    """عضویتِ محقق‌شده (materialized) — برایِ سگمنتِ ``static`` این تنها منبعِ
    حقیقت است؛ برایِ ``dynamic`` یک کشِ صریحاً تازه‌سازی‌شونده است، نه محاسبه‌ی
    زنده (نگاه کنید به مستندسازیِ ``CustomerSegment``)."""

    segment = models.ForeignKey(
        CustomerSegment, verbose_name="سگمنت", on_delete=models.CASCADE, related_name="memberships",
    )
    customer = models.ForeignKey(
        Customer, verbose_name="مشتری", on_delete=models.CASCADE, related_name="segment_memberships",
    )

    class Meta:
        verbose_name = "عضویتِ سگمنت"
        verbose_name_plural = "عضویت‌هایِ سگمنت"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["segment", "customer"], name="uniq_segment_membership"),
        ]

    def __str__(self):
        return f"{self.customer.full_name} ∈ {self.segment.name}"


class Wishlist(TimeStampedModel):
    customer = models.ForeignKey(
        Customer, verbose_name="مشتری", on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(
        "catalog.Product", verbose_name="کالا", on_delete=models.CASCADE, related_name="wishlisted_by"
    )

    class Meta:
        verbose_name = "علاقه‌مندی"
        verbose_name_plural = "علاقه‌مندی‌ها"
        unique_together = ("customer", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} ♥ {self.product}"
