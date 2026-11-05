"""مدل‌هایِ دامنه‌ی اشتراکِ SaaS (Checkpoint 5A) — پلن، نسخه‌ی پلن، تعریفِ
حق‌دسترسی (Entitlement)، و حق‌دسترسیِ پلن.

نگاه کنید به ADR-63 (نسخه‌ی پلنِ تغییرناپذیر)، ADR-64 (سرویسِ مرکزیِ
Entitlement)، ADR-66 (ماشینِ حالتِ اشتراک)، ADR-71 (SubscriptionEvent در
برابرِ Audit Log) در ``SAAS_DOMAIN_DECISIONS.md``.

این‌ها همه *platform-owned* هستند — نه Store-owned. فقط مدیرِ پلتفرم
(superuser، از طریقِ Django Admin) آن‌ها را مدیریت می‌کند؛ هیچ مسیرِ
Merchant Admin به این جدول‌ها نمی‌نویسد."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel


class Plan(TimeStampedModel):
    """یک پلنِ تجاریِ platform-owned (مثلاً starter/professional/business).

    ``code`` سراسری یکتاست و پس از اولین استفاده نباید تغییر کند (کنترلِ
    تغییر در لایه‌ی سرویس/Admin؛ نگاه کنید به ADR-63). نامِ پلن هرگز در
    منطقِ مجوز/entitlement هاردکد نمی‌شود — همه‌چیز از طریقِ کلیدِ
    Entitlement عبور می‌کند (ADR-64)."""

    code = models.SlugField("کد", max_length=50, unique=True, allow_unicode=False)
    name = models.CharField("نامِ داخلی", max_length=100)
    public_title = models.CharField("عنوانِ عمومی", max_length=100, blank=True, default="")
    description = models.TextField("توضیحات", blank=True, default="")
    is_active = models.BooleanField("فعال", default=True)
    is_publicly_selectable = models.BooleanField("قابلِ انتخابِ عمومی", default=True)
    is_recommended = models.BooleanField("پیشنهادی", default=False)
    display_order = models.PositiveIntegerField("ترتیبِ نمایش", default=0)
    # --- متنِ بازاریابیِ صفحه‌ی تعرفه (غیرِ قراردادی؛ به قیمت/Entitlementِ اشتراک‌ها ربطی ندارد و زنده ویرایش می‌شود) ---
    tagline = models.CharField("شعارِ کوتاه", max_length=160, blank=True, default="")
    badge_text = models.CharField("متنِ نشانِ پیشنهادی", max_length=40, blank=True, default="")
    cta_label = models.CharField("متنِ دکمه", max_length=40, blank=True, default="")

    class Meta:
        verbose_name = "پلن"
        verbose_name_plural = "پلن‌ها"
        ordering = ["display_order", "code"]
        indexes = [
            models.Index(fields=["is_active", "is_publicly_selectable"], name="idx_plan_active_public"),
        ]

    def __str__(self):
        return self.public_title or self.name


class EntitlementDefinition(TimeStampedModel):
    """تعریفِ یک قابلیت/محدودیتِ قابلِ سنجش — کلیدِ ماشین‌خوانِ پایدار
    (مثلاً ``catalog.products``). نگاه کنید به ADR-64.

    ``entitlement_type`` تعیین می‌کند کدام ستونِ ``PlanEntitlement`` معنادار
    است: ``boolean`` → ``is_enabled``؛ ``integer_limit`` → ``integer_limit``
    (یا ``is_unlimited``)؛ ``decimal_limit`` → ``decimal_limit`` (یا
    ``is_unlimited``)؛ ``text_value`` → ``text_value``. هیچ زبانِ عبارتِ
    آزادی وجود ندارد — فقط این چهار نوعِ بسته."""

    class EntitlementType(models.TextChoices):
        BOOLEAN = "boolean", "بولی (روشن/خاموش)"
        INTEGER_LIMIT = "integer_limit", "محدودیتِ عددِ صحیح"
        DECIMAL_LIMIT = "decimal_limit", "محدودیتِ عددِ اعشاری"
        TEXT_VALUE = "text_value", "مقدارِ متنی"

    key = models.SlugField("کلید", max_length=60, unique=True, allow_unicode=False)
    name = models.CharField("نام", max_length=120)
    description = models.CharField("توضیحات", max_length=300, blank=True, default="")
    entitlement_type = models.CharField(
        "نوع", max_length=15, choices=EntitlementType.choices, default=EntitlementType.BOOLEAN,
    )
    # رفتارِ پیش‌فرض وقتی یک نسخه‌ی پلن این Entitlement را صراحتاً تعریف
    # نکرده باشد — برایِ boolean یعنی «آیا در نبودِ تعریف، فعال است؟».
    default_enabled = models.BooleanField("پیش‌فرض: فعال", default=False)
    is_active = models.BooleanField("فعال", default=True)

    class Meta:
        verbose_name = "تعریفِ حق‌دسترسی"
        verbose_name_plural = "تعریف‌هایِ حق‌دسترسی"
        ordering = ["key"]

    def __str__(self):
        return f"{self.name} ({self.key})"


class PlanVersion(TimeStampedModel):
    """نسخه‌ی تغییرناپذیرِ یک پلن — نگاه کنید به ADR-63.

    فقط نسخه‌ی ``published`` می‌تواند اشتراکِ تازه بگیرد. پس از انتشار، شرایطِ
    تاریخیِ نسخه (Entitlementها/قیمت/تریال) نباید تغییر کند؛ تغییرِ شرایط
    یعنی ساختِ یک نسخه‌ی تازه، نه ویرایشِ نسخه‌ی منتشرشده. اشتراک‌هایِ موجود
    تا زمانِ مهاجرتِ صریح رویِ نسخه‌ی خودشان می‌مانند.

    قیمت در Checkpoint 5A فقط اطلاعاتی است — دریافتِ واقعیِ پول به 5B موکول
    شده (ADR-72)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"
        RETIRED = "retired", "بازنشسته"
        ARCHIVED = "archived", "آرشیوشده"

    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "ماهانه"
        QUARTERLY = "quarterly", "سه‌ماهه"
        SEMIANNUAL = "semiannual", "شش‌ماهه"
        YEARLY = "yearly", "سالانه"
        NONE = "none", "بدونِ دوره (رایگان/legacy)"

    #: تعدادِ ماهِ هر دوره (برایِ محاسبه‌ی پایانِ دوره و قیمتِ ماهانه‌ی معادل).
    INTERVAL_MONTHS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "yearly": 12}
    #: ترتیبِ نمایشِ دوره‌ها در صفحه‌ی تعرفه.
    PAID_INTERVALS = ("monthly", "quarterly", "semiannual", "yearly")

    plan = models.ForeignKey(Plan, verbose_name="پلن", on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField("شماره‌ی نسخه")
    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    currency = models.CharField("ارز", max_length=8, default="IRT")
    billing_interval = models.CharField(
        "دوره‌ی صورتحساب (گزینه‌ی اصلی)", max_length=10, choices=BillingInterval.choices, default=BillingInterval.MONTHLY,
    )
    display_price = models.DecimalField("قیمتِ نمایشی (اطلاعاتی)", max_digits=14, decimal_places=0, default=0)
    trial_days = models.PositiveIntegerField("روزهایِ تریال", default=0)
    trial_once_per_store = models.BooleanField(
        "تریال فقط یک‌بار برایِ هر فروشگاه", default=True,
        help_text="اگر روشن باشد فروشگاهی که قبلاً تریالِ این پلن را گرفته دوباره واجدِ تریال نیست.",
    )
    grace_period_days = models.PositiveIntegerField("روزهایِ مهلتِ ارفاقی (grace)", default=7)
    public_description_snapshot = models.TextField("توضیحاتِ عمومی (اسنپ‌شات)", blank=True, default="")

    effective_from = models.DateTimeField("معتبر از", null=True, blank=True)
    published_at = models.DateTimeField("زمانِ انتشار", null=True, blank=True)
    retired_at = models.DateTimeField("زمانِ بازنشستگی", null=True, blank=True)

    entitlements = models.ManyToManyField(
        EntitlementDefinition, through="PlanEntitlement", related_name="plan_versions",
    )

    class Meta:
        verbose_name = "نسخه‌ی پلن"
        verbose_name_plural = "نسخه‌هایِ پلن"
        ordering = ["plan", "-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "version_number"], name="uniq_planversion_number_per_plan"),
        ]
        indexes = [
            models.Index(fields=["plan", "status"], name="idx_planversion_plan_status"),
        ]

    def __str__(self):
        return f"{self.plan.code} v{self.version_number} ({self.get_status_display()})"

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    # ---- گزینه‌هایِ قیمتِ دوره‌ای -------------------------------------------------------------
    # ``display_price``/``billing_interval`` همچنان «گزینه‌ی اصلی» و تنها منبعِ نسخه‌هایِ قدیمی‌اند؛
    # ``prices`` فقط دوره‌هایِ *اضافیِ* همین نسخه را نگه می‌دارد. همه‌ی مصرف‌کننده‌هایِ مالی از
    # ``price_for`` می‌خوانند تا یک منبعِ حقیقت باشد.
    def price_options(self) -> dict:
        """``{interval: {"price": Decimal, "compare_at": Decimal|None, "label": str}}`` — اصلی + اضافی."""
        options = {}
        if self.billing_interval != self.BillingInterval.NONE:
            options[self.billing_interval] = {"price": Decimal(self.display_price), "compare_at": None, "label": ""}
        for row in self.prices.all():
            if row.billing_interval == self.billing_interval:
                # ردیفِ گزینه‌ی اصلی فقط متادیتا (قیمتِ قبل از تخفیف/برچسب) می‌دهد؛ قیمت همیشه از خودِ نسخه است.
                options[row.billing_interval].update(
                    compare_at=Decimal(row.compare_at_price) if row.compare_at_price else None, label=row.label,
                )
                continue
            options[row.billing_interval] = {
                "price": Decimal(row.price), "compare_at": Decimal(row.compare_at_price) if row.compare_at_price else None,
                "label": row.label,
            }
        return options

    def price_for(self, interval=None) -> Decimal:
        """قیمتِ دوره‌ی ``interval`` (پیش‌فرض: گزینه‌ی اصلی). دوره‌ی تعریف‌نشده ⇒ ``KeyError`` (هرگز حدس نمی‌زند)."""
        interval = interval or self.billing_interval
        if interval == self.billing_interval:
            return Decimal(self.display_price)
        return self.price_options()[interval]["price"]

    def offers_interval(self, interval) -> bool:
        return interval == self.billing_interval or interval in self.price_options()

    def monthly_equivalent(self, interval=None) -> Decimal:
        """قیمتِ ماهانه‌ی معادل — فقط برایِ مقایسه‌ی ارتقا/تنزل و نمایشِ صرفه‌جویی."""
        interval = interval or self.billing_interval
        months = self.INTERVAL_MONTHS.get(interval)
        if not months:
            return Decimal(0)
        return Decimal(self.price_for(interval)) / Decimal(months)


class PlanVersionPrice(TimeStampedModel):
    """قیمتِ *اضافیِ* یک دوره (سه‌ماهه/شش‌ماهه/سالانه/…) برایِ یک نسخه‌ی پلن. مثلِ Entitlementها با
    انتشارِ نسخه تغییرناپذیر می‌شود (اعمال در ``plan_service``)؛ تغییرِ قیمت = نسخه‌ی تازه."""

    plan_version = models.ForeignKey(PlanVersion, verbose_name="نسخه‌ی پلن", on_delete=models.CASCADE, related_name="prices")
    billing_interval = models.CharField("دوره", max_length=10, choices=PlanVersion.BillingInterval.choices)
    price = models.DecimalField("قیمت", max_digits=14, decimal_places=0)
    compare_at_price = models.DecimalField("قیمتِ قبل از تخفیف (نمایشی)", max_digits=14, decimal_places=0, null=True, blank=True)
    label = models.CharField("برچسبِ دوره (مثلاً «۲ ماه رایگان»)", max_length=60, blank=True, default="")

    class Meta:
        verbose_name = "قیمتِ دوره‌ایِ نسخه‌ی پلن"
        verbose_name_plural = "قیمت‌هایِ دوره‌ایِ نسخه‌هایِ پلن"
        ordering = ["plan_version", "billing_interval"]
        constraints = [
            models.UniqueConstraint(fields=["plan_version", "billing_interval"], name="uniq_planversionprice_interval"),
            models.CheckConstraint(check=models.Q(price__gte=0), name="planversionprice_non_negative"),
        ]

    def __str__(self):
        return f"{self.plan_version} · {self.billing_interval} · {self.price}"

    def clean(self):
        if self.billing_interval == PlanVersion.BillingInterval.NONE:
            raise ValidationError({"billing_interval": "دوره‌ی «بدونِ دوره» قیمتِ اضافی ندارد."})
        if self.plan_version_id and self.billing_interval == self.plan_version.billing_interval \
                and Decimal(self.price) != Decimal(self.plan_version.display_price):
            raise ValidationError({"price": "قیمتِ گزینه‌ی اصلی باید با قیمتِ خودِ نسخه برابر باشد."})
        if self.compare_at_price is not None and self.compare_at_price < self.price:
            raise ValidationError({"compare_at_price": "قیمتِ قبل از تخفیف نمی‌تواند کمتر از قیمتِ فعلی باشد."})


class PlanEntitlement(TimeStampedModel):
    """مقدارِ یک Entitlement برایِ یک نسخه‌ی پلنِ مشخص.

    نوعِ مقدار باید با ``entitlement.entitlement_type`` بخواند (در ``clean``
    اعتبارسنجی می‌شود). «نامحدود» صراحتاً با ``is_unlimited=True`` نشان داده
    می‌شود، نه با یک عددِ بزرگِ دلخواه (ADR-64، §6)."""

    plan_version = models.ForeignKey(
        PlanVersion, verbose_name="نسخه‌ی پلن", on_delete=models.CASCADE, related_name="plan_entitlements",
    )
    entitlement = models.ForeignKey(
        EntitlementDefinition, verbose_name="حق‌دسترسی", on_delete=models.PROTECT, related_name="plan_entitlements",
    )
    is_enabled = models.BooleanField("فعال", default=True)
    is_unlimited = models.BooleanField("نامحدود", default=False)
    integer_limit = models.IntegerField("محدودیتِ عددی", null=True, blank=True)
    decimal_limit = models.DecimalField("محدودیتِ اعشاری", max_digits=14, decimal_places=2, null=True, blank=True)
    text_value = models.CharField("مقدارِ متنی", max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "حق‌دسترسیِ پلن"
        verbose_name_plural = "حق‌دسترسی‌هایِ پلن"
        ordering = ["plan_version", "entitlement__key"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan_version", "entitlement"], name="uniq_planentitlement_per_version",
            ),
            models.CheckConstraint(
                check=models.Q(integer_limit__isnull=True) | models.Q(integer_limit__gte=0),
                name="planentitlement_integer_limit_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.plan_version} · {self.entitlement.key}"

    def clean(self):
        """نوعِ مقدار باید با نوعِ Entitlement بخواند — لایه‌ی دومِ دفاعی کنارِ
        CheckConstraint (که نمی‌تواند به جدولِ دیگر join کند)."""
        if self.entitlement_id is None:
            return
        etype = self.entitlement.entitlement_type
        errors = {}
        if etype == EntitlementDefinition.EntitlementType.INTEGER_LIMIT:
            if not self.is_unlimited and self.integer_limit is None:
                errors["integer_limit"] = "برایِ محدودیتِ عددی، یا مقدار بدهید یا «نامحدود» را علامت بزنید."
            if self.integer_limit is not None and self.integer_limit < 0:
                errors["integer_limit"] = "محدودیتِ عددی نمی‌تواند منفی باشد."
        elif etype == EntitlementDefinition.EntitlementType.DECIMAL_LIMIT:
            if not self.is_unlimited and self.decimal_limit is None:
                errors["decimal_limit"] = "برایِ محدودیتِ اعشاری، یا مقدار بدهید یا «نامحدود» را علامت بزنید."
            if self.decimal_limit is not None and self.decimal_limit < 0:
                errors["decimal_limit"] = "محدودیتِ اعشاری نمی‌تواند منفی باشد."
        elif etype == EntitlementDefinition.EntitlementType.BOOLEAN:
            if self.is_unlimited:
                errors["is_unlimited"] = "«نامحدود» برایِ Entitlementِ بولی معنا ندارد."
        if errors:
            raise ValidationError(errors)

    def resolved_limit(self):
        """محدودیتِ عددیِ مؤثر را برمی‌گرداند: ``None`` یعنی «نامحدود»، وگرنه
        عددِ صحیح. فقط برایِ نوعِ ``integer_limit`` معنا دارد."""
        if self.is_unlimited:
            return None
        return self.integer_limit


class StoreSubscription(TimeStampedModel):
    """اشتراکِ یک Store به یک نسخه‌ی پلن — نگاه کنید به ADR-66 (ماشینِ حالت).

    حداکثر یک اشتراکِ *غیرِ نهایی* (non-terminal) به‌ازای هر Store مجاز است
    (قیدِ شرطیِ دیتابیس). اشتراک‌هایِ نهایی‌شده (cancelled/expired) به‌عنوانِ
    تاریخچه می‌مانند و حذف نمی‌شوند. فیلدهایِ خاصِ درگاهِ پرداخت این‌جا
    نمی‌آیند — فقط یک ``external_reference`` عمومی (ADR-72)."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        TRIALING = "trialing", "دوره‌ی آزمایشی"
        ACTIVE = "active", "فعال"
        GRACE_PERIOD = "grace_period", "مهلتِ ارفاقی"
        PAST_DUE = "past_due", "معوق"
        SUSPENDED = "suspended", "معلق"
        CANCELLED = "cancelled", "لغوشده"
        EXPIRED = "expired", "منقضی‌شده"

    #: حالت‌هایِ نهایی — اشتراک پس از رسیدن به این‌ها دیگر تغییرِ حالت نمی‌دهد
    #: (به‌جز طبقِ سیاستِ صریحِ تمدید که یک اشتراکِ *تازه* می‌سازد، نه احیایِ
    #: همین رکورد).
    TERMINAL_STATUSES = {Status.CANCELLED, Status.EXPIRED}
    #: حالت‌هایی که به‌عنوانِ «اشتراکِ جاریِ فعالِ Store» شمرده می‌شوند (برایِ
    #: قیدِ یکتاییِ یک‌اشتراکِ‌جاری‌به‌ازای‌هر‌Store).
    NON_TERMINAL_STATUSES = {
        Status.PENDING, Status.TRIALING, Status.ACTIVE,
        Status.GRACE_PERIOD, Status.PAST_DUE, Status.SUSPENDED,
    }

    class Source(models.TextChoices):
        LEGACY = "legacy", "مهاجرتِ legacy"
        DEFAULT = "default", "پیش‌فرضِ فروشگاهِ تازه"
        ADMIN = "admin", "مدیرِ پلتفرم"
        SELF_SERVICE = "self_service", "انتخابِ تاجر"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="subscriptions",
    )
    plan_version = models.ForeignKey(
        PlanVersion, verbose_name="نسخه‌ی پلن", on_delete=models.PROTECT, related_name="subscriptions",
    )
    status = models.CharField("وضعیت", max_length=14, choices=Status.choices, default=Status.PENDING, db_index=True)
    # ``is_current`` صراحتاً نگه داشته می‌شود تا قیدِ «یک اشتراکِ جاری به‌ازای
    # هر Store» به‌صورتِ یک UniqueConstraintِ شرطیِ ساده قابلِ اجرا باشد
    # (SQLite/Postgres نمی‌توانند از یک مجموعه‌ی status در شرطِ قید عبور
    # کنند). سرویسِ ماشینِ حالت این را همگام با ``status`` نگه می‌دارد.
    is_current = models.BooleanField("اشتراکِ جاری", default=True)

    start_at = models.DateTimeField("زمانِ شروع", null=True, blank=True)
    trial_start_at = models.DateTimeField("شروعِ تریال", null=True, blank=True)
    trial_end_at = models.DateTimeField("پایانِ تریال", null=True, blank=True)
    current_period_start = models.DateTimeField("شروعِ دوره‌ی جاری", null=True, blank=True)
    current_period_end = models.DateTimeField("پایانِ دوره‌ی جاری", null=True, blank=True)
    grace_period_end = models.DateTimeField("پایانِ مهلتِ ارفاقی", null=True, blank=True)
    cancel_at_period_end = models.BooleanField("لغو در پایانِ دوره", default=False)
    cancelled_at = models.DateTimeField("زمانِ لغو", null=True, blank=True)
    suspended_at = models.DateTimeField("زمانِ تعلیق", null=True, blank=True)
    expired_at = models.DateTimeField("زمانِ انقضا", null=True, blank=True)

    # دوره‌ایِ که تاجر خریده؛ خالی = گزینه‌ی اصلیِ نسخه (همه‌ی اشتراک‌هایِ قبلی). قیمت همیشه از نسخه‌ی
    # تغییرناپذیر می‌آید، پس تغییرِ قیمتِ بعدی هرگز بی‌صدا رویِ مشترکِ موجود اعمال نمی‌شود.
    billing_interval = models.CharField("دوره‌ی خریداری‌شده", max_length=10, blank=True, default="")

    source = models.CharField("منبع", max_length=15, choices=Source.choices, default=Source.ADMIN)
    external_reference = models.CharField("ارجاعِ خارجی (رزرو برایِ 5B)", max_length=120, blank=True, default="")

    class Meta:
        verbose_name = "اشتراکِ فروشگاه"
        verbose_name_plural = "اشتراک‌هایِ فروشگاه"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["store"], condition=models.Q(is_current=True),
                name="uniq_current_subscription_per_store",
            ),
        ]
        indexes = [
            models.Index(fields=["store", "status"], name="idx_subscription_store_status"),
            models.Index(fields=["status", "current_period_end"], name="idx_subscription_status_period"),
            models.Index(fields=["status", "trial_end_at"], name="idx_subscription_status_trial"),
            models.Index(fields=["status", "grace_period_end"], name="idx_subscription_status_grace"),
        ]

    def __str__(self):
        return f"{self.store.slug} → {self.plan_version} ({self.get_status_display()})"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    @property
    def effective_billing_interval(self) -> str:
        """دوره‌ی مؤثر: انتخابِ تاجر اگر نسخه همچنان آن را عرضه کند، وگرنه گزینه‌ی اصلیِ نسخه."""
        chosen = self.billing_interval
        if chosen and self.plan_version.offers_interval(chosen):
            return chosen
        return self.plan_version.billing_interval


class SubscriptionEvent(TimeStampedModel):
    """تاریخچه‌ی تغییرناپذیرِ رخدادهایِ اشتراک — نگاه کنید به ADR-71.

    این یک مدلِ تاریخچه‌ی دامنه‌ای است و در کنارِ Audit Logِ عمومی وجود دارد
    (نه جایگزینِ آن). هرگز رمز/متادادهٔ حساس ذخیره نمی‌کند."""

    class EventType(models.TextChoices):
        CREATED = "created", "ایجاد"
        TRIAL_STARTED = "trial_started", "شروعِ تریال"
        ACTIVATED = "activated", "فعال‌سازی"
        RENEWED = "renewed", "تمدید"
        PLAN_CHANGED = "plan_changed", "تغییرِ پلن"
        GRACE_STARTED = "grace_started", "شروعِ مهلتِ ارفاقی"
        PAST_DUE = "past_due", "معوق‌شدن"
        SUSPENDED = "suspended", "تعلیق"
        RESUMED = "resumed", "ازسرگیری"
        CANCEL_SCHEDULED = "cancel_scheduled", "زمان‌بندیِ لغو"
        CANCELLED = "cancelled", "لغو"
        EXPIRED = "expired", "انقضا"
        TRIAL_EXTENDED = "trial_extended", "تمدیدِ دستیِ تریال"
        TRIAL_END_SET = "trial_end_set", "تنظیمِ دستیِ پایانِ تریال"
        TRIAL_ENDED_MANUALLY = "trial_ended_manually", "پایانِ دستیِ تریال"

    subscription = models.ForeignKey(
        StoreSubscription, verbose_name="اشتراک", on_delete=models.CASCADE, related_name="events",
    )
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="subscription_events",
    )
    event_type = models.CharField("نوعِ رخداد", max_length=20, choices=EventType.choices)
    from_status = models.CharField("از وضعیت", max_length=14, blank=True, default="")
    to_status = models.CharField("به وضعیت", max_length=14, blank=True, default="")
    from_plan_version = models.ForeignKey(
        PlanVersion, verbose_name="از نسخه‌ی پلن", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    to_plan_version = models.ForeignKey(
        PlanVersion, verbose_name="به نسخه‌ی پلن", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="subscription_events",
    )
    reason = models.CharField("علت", max_length=200, blank=True, default="")
    metadata = models.JSONField("فراداده", blank=True, default=dict)
    idempotency_key = models.CharField("کلیدِ یکتا", max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "رخدادِ اشتراک"
        verbose_name_plural = "رخدادهایِ اشتراک"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "idempotency_key"], condition=~models.Q(idempotency_key=""),
                name="uniq_subscriptionevent_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["store", "-created_at"], name="idx_subevent_store_created"),
            models.Index(fields=["subscription", "-created_at"], name="idx_subevent_sub_created"),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} — {self.store.slug}"


class UsageRecord(TimeStampedModel):
    """شمارنده‌ی مصرفِ دوره‌ای برایِ متریک‌هایی که با دوره‌ی صورتحساب صفر
    می‌شوند (مثلِ ردیف‌هایِ واردات، تعدادِ صادرات) — نگاه کنید به ADR-68.

    متریک‌هایِ شمارشیِ ساده (کالا/تنوع/کارمند/انبار/سگمنت) شمارنده‌ی ذخیره‌شده
    ندارند؛ آن‌ها زنده از ``QuerySet.count()`` خوانده می‌شوند (ADR-68). این
    مدل فقط برایِ متریک‌هایِ *دوره‌ای* است."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="usage_records",
    )
    subscription = models.ForeignKey(
        StoreSubscription, verbose_name="اشتراک", on_delete=models.CASCADE, related_name="usage_records",
        null=True, blank=True,
    )
    metric_key = models.CharField("کلیدِ متریک", max_length=60, db_index=True)
    period_start = models.DateTimeField("شروعِ دوره")
    period_end = models.DateTimeField("پایانِ دوره")
    used_quantity = models.PositiveIntegerField("مقدارِ مصرف‌شده", default=0)

    class Meta:
        verbose_name = "رکوردِ مصرف"
        verbose_name_plural = "رکوردهایِ مصرف"
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["store", "metric_key", "period_start"], name="uniq_usagerecord_store_metric_period",
            ),
        ]
        indexes = [
            models.Index(fields=["store", "metric_key", "-period_start"], name="idx_usage_store_metric"),
        ]

    def __str__(self):
        return f"{self.store.slug} · {self.metric_key} · {self.period_start:%Y-%m}"



# =====================================================================================================================
# محتوایِ صفحه‌ی تعرفه — ردیف‌هایِ مقایسه، پرسش‌هایِ متداول، خدماتِ اختیاری
# =====================================================================================================================

class PricingFeature(TimeStampedModel):
    """یک ردیفِ ماتریسِ مقایسه. منبعِ ساختاری (دسته، اتصال به Entitlement، «وضعیتِ پیاده‌سازی») کد است
    (``apps.subscriptions.feature_catalog``) و با ``sync_feature_catalog`` همگام می‌شود؛ مدیرِ پلتفرم فقط متنِ
    نمایشی، ترتیب و پنهان‌کردنِ ردیف را ویرایش می‌کند. قابلیتی که پیاده نشده هرگز عمومی نمی‌شود."""

    class Category(models.TextChoices):
        STORE_OPERATIONS = "store_operations", "عملیاتِ فروشگاه"
        INFRASTRUCTURE = "infrastructure", "زیرساختِ فنی"
        SEO_CONTENT = "seo_content", "سئو و محتوا"
        PAYMENTS = "payments", "پرداخت"
        DESIGN = "design", "طراحی و شخصی‌سازیِ ویترین"
        MARKETING = "marketing", "بازاریابی و رشدِ فروش"
        SERVICES = "services", "خدماتِ حرفه‌ایِ اختیاری"

    class Availability(models.TextChoices):
        IMPLEMENTED = "implemented", "پیاده‌سازی‌شده"
        PARTIAL = "partial", "پیاده‌سازیِ جزئی"
        EXTERNAL = "external", "نیازمندِ سرویسِ بیرونی"
        PLANNED = "planned", "پیاده نشده (عمومی نمی‌شود)"

    key = models.SlugField("کلید", max_length=70, unique=True)
    category = models.CharField("دسته", max_length=20, choices=Category.choices, db_index=True)
    title = models.CharField("عنوانِ نمایشی", max_length=140)
    description = models.TextField("توضیحِ قابلِ‌بازشدن", blank=True, default="")
    unit_label = models.CharField("واحدِ سقف", max_length=30, blank=True, default="")
    entitlement = models.ForeignKey(
        EntitlementDefinition, verbose_name="حق‌دسترسیِ مرتبط", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pricing_features",
    )
    availability = models.CharField("وضعیتِ پیاده‌سازی", max_length=12, choices=Availability.choices, default=Availability.IMPLEMENTED)
    note = models.CharField("یادداشتِ شفاف‌سازی", max_length=200, blank=True, default="")
    display_order = models.PositiveIntegerField("ترتیب", default=0)
    is_visible = models.BooleanField("نمایش در صفحه‌ی عمومی", default=True)

    class Meta:
        verbose_name = "ردیفِ ماتریسِ تعرفه"
        verbose_name_plural = "ردیف‌هایِ ماتریسِ تعرفه"
        ordering = ["category", "display_order", "key"]

    def __str__(self):
        return self.title

    @property
    def is_publishable(self) -> bool:
        """فقط قابلیت‌هایِ واقعاً موجود (کاملِ، جزئی، یا نیازمندِ سرویسِ بیرونی با برچسبِ صادقانه) عمومی می‌شوند."""
        return self.availability != self.Availability.PLANNED


class PlanFaq(TimeStampedModel):
    """پرسشِ متداولِ صفحه‌ی تعرفه؛ ``plan`` خالی = سراسری."""

    plan = models.ForeignKey(Plan, verbose_name="پلنِ مرتبط", on_delete=models.CASCADE, null=True, blank=True, related_name="faqs")
    question = models.CharField("پرسش", max_length=240)
    answer = models.TextField("پاسخ")
    display_order = models.PositiveIntegerField("ترتیب", default=0)
    is_published = models.BooleanField("منتشرشده", default=True)

    class Meta:
        verbose_name = "پرسشِ متداولِ تعرفه"
        verbose_name_plural = "پرسش‌هایِ متداولِ تعرفه"
        ordering = ["display_order", "id"]

    def __str__(self):
        return self.question


class OptionalService(TimeStampedModel):
    """خدمتِ حرفه‌ایِ اختیاری (فقط اگر مدیر تعریف و فعال کند). قیمت و دسترسیِ هر پلن دستیِ مدیر است — هیچ
    خدمتی به‌صورتِ پیش‌فرض ساخته نمی‌شود و هیچ تعهدِ قراردادی از اینجا استنباط نمی‌شود."""

    code = models.SlugField("کد", max_length=50, unique=True)
    title = models.CharField("عنوان", max_length=140)
    description = models.TextField("توضیح", blank=True, default="")
    price = models.DecimalField("قیمت (تومان)", max_digits=14, decimal_places=0, null=True, blank=True)
    price_note = models.CharField("توضیحِ قیمت (مثلاً «استعلام»)", max_length=80, blank=True, default="")
    display_order = models.PositiveIntegerField("ترتیب", default=0)
    is_active = models.BooleanField("فعال", default=False)

    class Meta:
        verbose_name = "خدمتِ اختیاری"
        verbose_name_plural = "خدماتِ اختیاری"
        ordering = ["display_order", "code"]

    def __str__(self):
        return self.title


class PlanOptionalService(TimeStampedModel):
    class Mode(models.TextChoices):
        INCLUDED = "included", "همراهِ پلن"
        PAID = "paid", "با هزینه‌ی جدا"
        UNAVAILABLE = "unavailable", "در دسترس نیست"

    plan = models.ForeignKey(Plan, verbose_name="پلن", on_delete=models.CASCADE, related_name="optional_services")
    service = models.ForeignKey(OptionalService, verbose_name="خدمت", on_delete=models.CASCADE, related_name="plan_modes")
    mode = models.CharField("وضعیت", max_length=12, choices=Mode.choices, default=Mode.UNAVAILABLE)

    class Meta:
        verbose_name = "خدمتِ اختیاریِ پلن"
        verbose_name_plural = "خدماتِ اختیاریِ پلن‌ها"
        constraints = [models.UniqueConstraint(fields=["plan", "service"], name="uniq_planoptionalservice")]
