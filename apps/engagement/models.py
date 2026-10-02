"""کمپین‌های هوشمندِ تخفیف و مناسبت‌ها (تولد، سالگرد، نقاطِ عطف…).

یک مدلِ واحد (``Campaign``) هر دو را پوشش می‌دهد: کمپینِ دستی/زمان‌بندی‌شده/
رویدادی و کمپینِ مناسبتی؛ تفاوت فقط در ``trigger_type`` است. قواعدِ
شمول در یک درختِ JSON (AND/OR/تودرتو) ذخیره و سمتِ سرور اعتبارسنجی می‌شود
(``apps.engagement.services.rules``) — هرگز SQL/کدِ دلخواه نیست."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Campaign(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "فعال"
        PAUSED = "paused", "متوقف"
        EXPIRED = "expired", "منقضی‌شده"
        COMPLETED = "completed", "تکمیل‌شده"

    class Trigger(models.TextChoices):
        MANUAL = "manual", "اجرای دستی"
        SCHEDULED = "scheduled", "زمان‌بندی‌شده (job دوره‌ای)"
        EVENT = "event", "رویداد (پس از پرداختِ موفق)"
        OCCASION = "occasion", "مناسبت"

    class Scope(models.TextChoices):
        AGGREGATE = "aggregate", "ترکیبِ سفارش‌ها (هر شرط می‌تواند با سفارشِ متفاوتی برقرار شود)"
        SAME_ORDER = "same_order", "همه‌ی شرط‌ها باید با یک سفارشِ واحد برقرار شوند"

    class PeriodMode(models.TextChoices):
        NONE = "none", "بدونِ بازه (کلِ تاریخچه)"
        JALALI_MONTHS = "jalali_months", "ماه‌های شمسی"
        DATES = "dates", "بازه‌ی تاریخ"

    class AmountBasis(models.TextChoices):
        NET = "net_total", "مبلغِ خالص (پس از کسرِ استرداد)"
        GRAND = "grand_total", "مبلغِ نهایی فاکتور"
        ITEMS = "items_total", "جمعِ کالاها"

    class Occasion(models.TextChoices):
        BIRTHDAY = "birthday", "تولد"
        REGISTRATION_ANNIVERSARY = "registration_anniversary", "سالگردِ ثبت‌نام"
        FIRST_PURCHASE_ANNIVERSARY = "first_purchase_anniversary", "سالگردِ اولین خرید"
        ORDER_MILESTONE = "order_milestone", "نقطه‌ی عطفِ تعدادِ سفارش"
        SPENDING_MILESTONE = "spending_milestone", "نقطه‌ی عطفِ مجموعِ خرید"
        REACTIVATION = "reactivation", "بازگشتِ مشتریِ غیرفعال"
        HOLIDAY = "holiday", "تعطیلی/مناسبتِ عمومی (ماه/روزِ شمسی)"
        CUSTOM_DATE = "custom_date", "مناسبتِ اختصاصیِ فروشگاه (تاریخِ مشخص)"

    class Reward(models.TextChoices):
        COUPON = "coupon", "کدِ تخفیف"
        NONE = "none", "فقط اطلاع‌رسانی (بدونِ پاداش)"

    store = models.ForeignKey("stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField("نام", max_length=150)
    description = models.TextField("توضیحات", blank=True, default="")
    status = models.CharField("وضعیت", max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    trigger_type = models.CharField("نوعِ اجرا", max_length=12, choices=Trigger.choices, default=Trigger.MANUAL)

    # --- قواعدِ شمول ---
    rules = models.JSONField("درختِ قواعد", default=dict, blank=True)
    rule_scope = models.CharField("دامنه‌ی ارزیابیِ قواعدِ سفارش", max_length=12, choices=Scope.choices, default=Scope.AGGREGATE)
    period_mode = models.CharField("بازه‌ی خرید", max_length=14, choices=PeriodMode.choices, default=PeriodMode.NONE)
    period_jalali_year = models.PositiveSmallIntegerField("سالِ شمسی", null=True, blank=True)
    period_start_month = models.PositiveSmallIntegerField("ماهِ شروع (شمسی)", null=True, blank=True)
    period_end_month = models.PositiveSmallIntegerField("ماهِ پایان (شمسی)", null=True, blank=True)
    period_start_date = models.DateField("تاریخِ شروع (میلادی)", null=True, blank=True)
    period_end_date = models.DateField("تاریخِ پایان (میلادی)", null=True, blank=True)
    valid_payment_statuses = models.JSONField("وضعیت‌های پرداختِ معتبر", default=list, blank=True)
    amount_basis = models.CharField("مبنای مبلغ فاکتور", max_length=12, choices=AmountBasis.choices, default=AmountBasis.NET)

    # --- پاداش ---
    reward_type = models.CharField("نوع پاداش", max_length=8, choices=Reward.choices, default=Reward.COUPON)
    coupon_type = models.CharField("نوع تخفیف", max_length=10, default="percent")
    coupon_value = models.DecimalField("مقدار تخفیف", max_digits=12, decimal_places=0, default=0)
    coupon_max_discount = models.DecimalField("سقفِ مبلغ تخفیف (تومان)", max_digits=12, decimal_places=0, null=True, blank=True)
    coupon_min_order = models.DecimalField("حداقل مبلغ سفارش", max_digits=12, decimal_places=0, default=0)
    coupon_applies_to_gift_wrap = models.BooleanField("تخفیف روی کادوپیچی هم اعمال شود", default=False)
    code_prefix = models.CharField("پیشوندِ کد", max_length=12, blank=True, default="")
    personalized = models.BooleanField("کدِ اختصاصیِ هر مشتری", default=True)
    code_starts_at = models.DateTimeField("فعال‌سازیِ کد", null=True, blank=True)
    code_expires_at = models.DateTimeField("انقضایِ کد (تاریخِ ثابت)", null=True, blank=True)
    code_valid_days = models.PositiveIntegerField("اعتبارِ کد پس از صدور (روز)", null=True, blank=True)
    total_redemption_limit = models.PositiveIntegerField("سقفِ کلِ استفاده از هر کد", null=True, blank=True)
    per_customer_limit = models.PositiveIntegerField("سقفِ استفاده برایِ هر مشتری", null=True, blank=True, default=1)
    per_customer_period_days = models.PositiveIntegerField("پنجره‌ی سقفِ هر مشتری (روز)", null=True, blank=True)
    validity_from_delivery = models.BooleanField(
        "اعتبارِ کد از لحظه‌ی تحویلِ اعلان حساب شود (نه صدور)", default=False,
    )
    max_issuances = models.PositiveIntegerField("سقفِ تعدادِ کدهایِ صادرشده (ظرفیتِ کمپین)", null=True, blank=True)
    shared_coupon = models.ForeignKey(
        "cart.Coupon", verbose_name="کدِ مشترک (کمپینِ غیراختصاصی)", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    # --- اطلاع‌رسانی ---
    channels = models.JSONField("کانال‌ها", default=list, blank=True)
    custom_sms_body = models.TextField("متنِ پیامکِ اختصاصیِ کمپین", blank=True, default="")
    custom_email_subject = models.CharField("موضوعِ ایمیلِ اختصاصیِ کمپین", max_length=200, blank=True, default="")
    custom_email_body = models.TextField("متنِ ایمیلِ اختصاصیِ کمپین", blank=True, default="")
    reminder_days_before_expiry = models.PositiveSmallIntegerField("یادآوریِ انقضا (روز مانده)", null=True, blank=True)

    # --- مناسبت ---
    occasion_kind = models.CharField("نوعِ مناسبت", max_length=30, choices=Occasion.choices, blank=True, default="")
    occasion_name = models.CharField("نامِ مناسبت (در پیام)", max_length=100, blank=True, default="")
    occasion_offset_days = models.SmallIntegerField(
        "فاصله‌ی روز از مناسبت (منفی = پیش از، ۰ = همان روز، مثبت = پس از)", default=0,
    )
    occasion_params = models.JSONField("پارامترهایِ مناسبت", default=dict, blank=True)

    # --- چرخه‌ی عمر ---
    active_from = models.DateTimeField("شروعِ فعالیتِ کمپین", null=True, blank=True)
    active_until = models.DateTimeField("پایانِ فعالیتِ کمپین", null=True, blank=True)
    activated_at = models.DateTimeField("زمانِ فعال‌سازی", null=True, blank=True)
    last_run_at = models.DateTimeField("آخرین اجرا", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="سازنده", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "کمپین"
        verbose_name_plural = "کمپین‌ها"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["store", "status", "trigger_type"], name="idx_campaign_store_status")]

    def __str__(self):
        return self.name


class CampaignIssuance(TimeStampedModel):
    """صدورِ یک پاداش برایِ یک مشتری در یک چرخه. یکتایی
    (``campaign``, ``customer``, ``cycle_key``) ضامنِ idempotency است: اجرای
    دوباره‌ی job هرگز پاداش/پیامِ تکراری نمی‌سازد."""

    campaign = models.ForeignKey(Campaign, verbose_name="کمپین", on_delete=models.CASCADE, related_name="issuances")
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.CASCADE, related_name="campaign_issuances",
    )
    cycle_key = models.CharField("کلیدِ چرخه", max_length=60, default="once")
    coupon = models.ForeignKey(
        "cart.Coupon", verbose_name="کد تخفیف", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="issuances",
    )
    notified_at = models.DateTimeField("زمانِ صفِ اعلان", null=True, blank=True)

    class Meta:
        verbose_name = "صدورِ پاداش"
        verbose_name_plural = "صدورهایِ پاداش"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "customer", "cycle_key"], name="uniq_campaign_issuance_cycle"),
        ]
        indexes = [models.Index(fields=["customer", "campaign"], name="idx_issuance_customer")]

    def __str__(self):
        return f"{self.campaign_id}/{self.customer_id}/{self.cycle_key}"


class CampaignRun(TimeStampedModel):
    class Trigger(models.TextChoices):
        MANUAL = "manual", "دستی"
        SCHEDULED = "scheduled", "زمان‌بندی"
        EVENT = "event", "رویداد"
        OCCASION = "occasion", "مناسبت"
        PREVIEW = "preview", "پیش‌نمایش"

    campaign = models.ForeignKey(Campaign, verbose_name="کمپین", on_delete=models.CASCADE, related_name="runs")
    trigger = models.CharField("محرک", max_length=10, choices=Trigger.choices)
    dry_run = models.BooleanField("خشک (بدونِ صدور)", default=False)
    started_at = models.DateTimeField("شروع")
    finished_at = models.DateTimeField("پایان", null=True, blank=True)
    evaluated = models.PositiveIntegerField("بررسی‌شده", default=0)
    eligible = models.PositiveIntegerField("مشمول", default=0)
    issued = models.PositiveIntegerField("صادرشده", default=0)
    skipped_existing = models.PositiveIntegerField("قبلاً صادرشده", default=0)
    errors = models.PositiveIntegerField("خطا", default=0)
    error_text = models.TextField("متنِ خطا", blank=True, default="")

    class Meta:
        verbose_name = "اجرای کمپین"
        verbose_name_plural = "اجراهایِ کمپین"
        ordering = ["-started_at"]
