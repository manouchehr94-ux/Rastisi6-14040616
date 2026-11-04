"""Email-engine models (sender identity, platform default templates, template revisions, provider events,
suppressions). Kept in their own module — imported by ``models.py`` — so the notifications app's models file stays
small and parallel work on it (e.g. the Inbox engine) merges without textual conflicts."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class PlatformNotificationTemplate(TimeStampedModel):
    """پیش‌فرضِ پلتفرم برایِ هر رویداد/کانال: «پیش‌فرضِ پلتفرم ← بازنویسیِ فروشگاه ← اعلانِ رندرشده».

    نبودنِ ردیف یعنی پیش‌فرضِ داخلِ کد (``events.EVENTS``). ``locked_for_stores``: فروشگاه‌ها نمی‌توانند
    متن را بازنویسی کنند (مثلاً اعلان‌هایِ پلتفرم به مدیرِ فروشگاه)."""

    event_key = models.CharField("رویداد", max_length=60)
    channel = models.CharField("کانال", max_length=10, choices=[("sms", "پیامک"), ("email", "ایمیل")])
    is_enabled = models.BooleanField("فعالِ پیش‌فرض", default=True)
    subject = models.CharField("موضوعِ ایمیل", max_length=200, blank=True, default="")
    body = models.TextField("متن")
    body_html = models.TextField("متنِ HTML (ایمیل)", blank=True, default="")
    locked_for_stores = models.BooleanField("قفل برایِ فروشگاه‌ها", default=False)
    version = models.PositiveIntegerField("نسخه", default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="آخرین ویرایشگر", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "قالبِ پیش‌فرضِ پلتفرم"
        verbose_name_plural = "قالب‌هایِ پیش‌فرضِ پلتفرم"
        ordering = ["event_key", "channel"]
        constraints = [
            models.UniqueConstraint(fields=["event_key", "channel"], name="uniq_platform_notification_template"),
        ]
        permissions = [
            ("view_notification_catalog", "مشاهده‌ی فهرستِ رویدادهایِ اعلان"),
            ("manage_platform_templates", "ویرایشِ قالب‌هایِ پیش‌فرضِ اعلان"),
            ("view_notification_delivery", "مشاهده‌ی شکست‌ها و مصرفِ ارسال"),
            ("manage_email_senders", "مدیریتِ هویتِ فرستنده‌ی ایمیلِ فروشگاه‌ها"),
            ("send_notification_tests", "ارسالِ آزمایشیِ اعلان"),
        ]

    def __str__(self):
        return f"platform:{self.event_key}/{self.channel}"


class NotificationTemplateRevision(TimeStampedModel):
    """تاریخچه‌ی نسخه‌ها و ردپایِ ممیزیِ تغییرِ قالب‌ها (پلتفرم و فروشگاه)."""

    class Scope(models.TextChoices):
        PLATFORM = "platform", "پلتفرم"
        STORE = "store", "فروشگاه"

    scope = models.CharField(max_length=10, choices=Scope.choices)
    store = models.ForeignKey(
        "stores.Store", on_delete=models.CASCADE, null=True, blank=True, related_name="notification_template_revisions",
    )
    event_key = models.CharField(max_length=60)
    channel = models.CharField(max_length=10)
    version = models.PositiveIntegerField()
    action = models.CharField(max_length=12, default="save")  # save | reset
    is_enabled = models.BooleanField(default=True)
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    body_html = models.TextField(blank=True, default="")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["scope", "store", "event_key", "channel"], name="idx_notif_rev_lookup")]


class EmailSenderIdentity(TimeStampedModel):
    """هویتِ فرستنده‌ی ایمیلِ یک فروشگاه — همیشه روی دامنه‌ی اختصاصیِ خودِ فروشگاه (``info@<دامنه>``).

    ``status`` فقط پس از تأییدِ واقعیِ ارائه‌دهنده ``ACTIVE`` می‌شود؛ هیچ دامنه‌ی مشترک/جایگزینی وجود ندارد."""

    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        INACTIVE = "inactive", "غیرفعال"
        PENDING = "pending", "در انتظارِ تأیید"
        ERROR = "error", "خطا"

    store = models.OneToOneField("stores.Store", on_delete=models.CASCADE, related_name="email_sender_identity")
    domain = models.ForeignKey(
        "stores.StoreDomain", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    domain_name = models.CharField("دامنه", max_length=253, blank=True, default="")
    local_part = models.CharField("بخشِ محلی", max_length=40, default="info")
    provider = models.CharField(max_length=20, blank=True, default="")
    provider_ref = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INACTIVE, db_index=True)
    reason_code = models.CharField(max_length=40, blank=True, default="")
    reason_detail = models.CharField(max_length=300, blank=True, default="")
    dns_records = models.JSONField(default=list, blank=True)
    dns_auto_requested = models.BooleanField("درخواستِ ثبتِ خودکارِ DNS ارسال شد (تأییدشده نیست)", default=False)
    dns_automation_state = models.CharField(
        "وضعیتِ ثبتِ خودکارِ DNS", max_length=14, blank=True, default="",
        help_text="requested | not_attempted | failed — «requested» یعنی ناحیه‌ی مجاز درخواست را پذیرفت، نه اینکه تأیید شده باشد.")
    dns_automation_code = models.CharField("کدِ نتیجه‌ی ثبتِ خودکارِ DNS", max_length=30, blank=True, default="")
    dns_automation_detail = models.CharField("جزئیاتِ فنی (بدونِ اطلاعاتِ محرمانه)", max_length=200, blank=True, default="")
    platform_disabled = models.BooleanField("غیرفعال‌سازی توسطِ پلتفرم", default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    consecutive_failures = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "هویتِ فرستنده‌ی ایمیل"
        verbose_name_plural = "هویت‌هایِ فرستنده‌ی ایمیل"

    @property
    def from_address(self) -> str:
        return f"{self.local_part}@{self.domain_name}" if self.domain_name else ""

    def __str__(self):
        return f"{self.store_id}:{self.from_address}:{self.status}"


class EmailProviderEvent(TimeStampedModel):
    """رویدادِ تحویل/برگشت/شکایتِ دریافتی از ارائه‌دهنده (idempotent بر اساسِ ``event_id``)."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=200)
    event_type = models.CharField(max_length=12)  # delivery | bounce | complaint
    message_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    recipient = models.CharField(max_length=254, blank=True, default="")
    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    outbox = models.ForeignKey("notifications.NotificationOutbox", on_delete=models.SET_NULL, null=True, blank=True, related_name="provider_events")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "event_id"], name="uniq_email_provider_event")]
        ordering = ["-created_at"]


class EmailSuppression(TimeStampedModel):
    """نشانی‌ای که به‌دلیلِ برگشتِ دائمی یا شکایت دیگر ایمیل نمی‌گیرد (به‌ازای هر فروشگاه)."""

    store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, related_name="email_suppressions")
    email = models.EmailField()
    reason = models.CharField(max_length=12)  # bounce | complaint | manual

    class Meta:
        constraints = [models.UniqueConstraint(fields=["store", "email"], name="uniq_email_suppression")]
