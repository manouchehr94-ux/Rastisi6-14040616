"""صندوقِ پایدارِ اعلان‌ها (Section 16) — درون‌برنامه‌ای/پیامک/ایمیل، همه از
یک صفِ واحد. هر اعلان یک ردیفِ ``PENDING`` است تا واقعاً تحویل داده شود
(``deliver_pending``) — پس یک خطای گذرا در ارسالِ پیامک هرگز خودِ اعلان را
گم نمی‌کند، فقط آن را ``FAILED`` می‌کند و بعداً قابلِ ری‌تلاش است.

اعلان‌هایِ امنیتی (``is_security=True``) هیچ مکانیزمِ opt-out‌ی ندارند —
``notify_security_event`` تنها مسیرِ ساختِ آن‌هاست و همیشه صف می‌کند."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class NotificationOutbox(TimeStampedModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "درون‌برنامه‌ای"
        SMS = "sms", "پیامک"
        EMAIL = "email", "ایمیل"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظارِ ارسال"
        SENDING = "sending", "در حالِ ارسال"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق (قابلِ تلاشِ دوباره)"
        DEAD = "dead", "ناموفقِ نهایی"
        SKIPPED = "skipped", "ارسال‌نشده (رضایت/گیرنده/متغیر)"

    channel = models.CharField("کانال", max_length=10, choices=Channel.choices)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="گیرنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notifications",
    )
    recipient_phone = models.CharField("موبایلِ گیرنده", max_length=15, blank=True, default="")
    recipient_email = models.EmailField("ایمیلِ گیرنده", blank=True, default="")
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        null=True, blank=True, related_name="notifications",
    )
    subject = models.CharField("موضوع", max_length=200, blank=True, default="")
    body = models.TextField("متن")
    is_security = models.BooleanField("اعلانِ امنیتی (غیرِقابلِ‌غیرفعال‌سازی)", default=False)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField("تعدادِ تلاش", default=0)
    last_error = models.TextField("آخرین خطا", blank=True, default="")
    sent_at = models.DateTimeField("زمانِ ارسال", null=True, blank=True)
    read_at = models.DateTimeField("زمانِ خوانده‌شدن", null=True, blank=True)
    metadata = models.JSONField("فراداده", default=dict, blank=True)

    # --- سیستمِ اعلانِ رویدادمحور (outbox) ---
    event_key = models.CharField("رویداد", max_length=60, blank=True, default="", db_index=True)
    customer = models.ForeignKey(
        "customers.Customer", verbose_name="مشتری", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notifications",
    )
    order = models.ForeignKey(
        "orders.Order", verbose_name="سفارش", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notifications",
    )
    is_promotional = models.BooleanField("تبلیغاتی", default=False)
    dedupe_key = models.CharField("کلیدِ جلوگیری از تکرار", max_length=220, blank=True, default="")
    provider = models.CharField("ارائه‌دهنده", max_length=30, blank=True, default="")
    provider_ref = models.CharField("شناسه‌ی ارجاعِ ارائه‌دهنده", max_length=100, blank=True, default="")
    max_attempts = models.PositiveSmallIntegerField("سقفِ تلاش", default=5)
    next_attempt_at = models.DateTimeField("زمانِ تلاشِ بعدی", null=True, blank=True)
    claimed_at = models.DateTimeField("زمانِ برداشتِ کارگر", null=True, blank=True)
    skip_reason = models.CharField("دلیلِ ارسال‌نشدن", max_length=120, blank=True, default="")
    is_test = models.BooleanField("ارسالِ آزمایشی", default=False)
    sms_log = models.OneToOneField(
        "sms.SmsLog", verbose_name="گزارشِ پیامکِ قدیمی", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="notification_mirror",
        help_text="ردیف‌هایِ آینه‌ایِ پیامکِ قدیمی (apps.sms): فقط تاریخچه‌اند و هرگز توسطِ کارگرِ ارسال برداشته نمی‌شوند.",
    )

    class Meta:
        verbose_name = "اعلان"
        verbose_name_plural = "اعلان‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_user", "channel", "-created_at"], name="idx_notif_user_channel"),
            models.Index(fields=["status", "channel"], name="idx_notif_status_channel"),
            models.Index(fields=["store", "event_key", "-created_at"], name="idx_notif_store_event"),
            models.Index(fields=["status", "next_attempt_at"], name="idx_notif_status_next"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"], condition=~models.Q(dedupe_key=""), name="uniq_notification_dedupe_key",
            ),
        ]

    @property
    def is_legacy_sms_mirror(self) -> bool:
        """آینه‌ی تاریخچه‌ی پیامکِ قدیمی (نه یک اعلانِ قابلِ ارسال)."""
        return bool(self.sms_log_id or (self.metadata or {}).get("legacy_sms_log_id"))

    def __str__(self):
        return f"{self.get_channel_display()} → {self.recipient_user or self.recipient_phone or self.recipient_email}"


class NotificationTemplate(TimeStampedModel):
    """قالبِ قابل‌ویرایشِ هر رویداد/کانال برایِ هر Store. نبودنِ ردیف یعنی
    «قالب و فعال/غیرفعالِ پیش‌فرضِ رویداد» (``apps.notifications.events``)."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="notification_templates",
    )
    event_key = models.CharField("رویداد", max_length=60)
    channel = models.CharField("کانال", max_length=10, choices=[("sms", "پیامک"), ("email", "ایمیل")])
    is_enabled = models.BooleanField("فعال", default=True)
    subject = models.CharField("موضوعِ ایمیل", max_length=200, blank=True, default="")
    body = models.TextField("متن")
    extra_recipients = models.TextField(
        "گیرندگانِ اضافی (کارکنان)", blank=True, default="",
        help_text="برایِ رویدادهایِ کارکنان: هر خط یک ایمیل/شماره موبایل.",
    )

    class Meta:
        verbose_name = "قالبِ اعلان"
        verbose_name_plural = "قالب‌هایِ اعلان"
        ordering = ["event_key", "channel"]
        constraints = [
            models.UniqueConstraint(fields=["store", "event_key", "channel"], name="uniq_notification_template"),
        ]

    def __str__(self):
        return f"{self.event_key}/{self.channel} @ {self.store_id}"
