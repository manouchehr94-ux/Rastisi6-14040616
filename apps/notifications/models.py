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


# =====================================================================================================================================================
# موتور مرکزیِ اعلانِ مدیران (Inbox) — رویداد ← گیرندگان ← صندوق ← تحویل در کانال. جدا از ``NotificationOutbox`` (ارتباط با مشتری: پیامک/ایمیل).
# =====================================================================================================================================================
import uuid  # noqa: E402


class Severity(models.IntegerChoices):
    INFO = 1, "اطلاعاتی"
    NORMAL = 2, "معمولی"
    IMPORTANT = 3, "مهم"
    CRITICAL = 4, "بحرانی"


class NotificationEvent(models.Model):
    """خودِ رویداد — یک‌بار ثبت می‌شود و از وضعیتِ خواندن/ارسالِ هر گیرنده جداست (``InboxItem``/``NotificationDelivery``).

    ``scope_key`` = ``"platform"`` یا ``"store:<id>"``؛ ``dedupe_key`` در همان محدوده یکتاست (هر رویدادِ واقعی فقط یک‌بار). لینک فقط
    «نامِ URL + پارامتر» است (هرگز نشانیِ خام) تا open-redirect ممکن نباشد؛ هیچ داده‌ی حساس/Secret در متن‌ها نمی‌آید."""

    class Scope(models.TextChoices):
        STORE = "store", "فروشگاه"
        PLATFORM = "platform", "پلتفرم"

    public_id = models.UUIDField("شناسه‌ی عمومی", default=uuid.uuid4, unique=True, editable=False)
    type_key = models.CharField("نوع رویداد", max_length=60, db_index=True)
    category = models.CharField("دسته", max_length=20, db_index=True)
    severity = models.PositiveSmallIntegerField("سطح اهمیت", choices=Severity.choices, default=Severity.NORMAL)
    scope = models.CharField("محدوده", max_length=10, choices=Scope.choices, default=Scope.STORE)
    scope_key = models.CharField("کلیدِ محدوده", max_length=30, db_index=True)
    store = models.ForeignKey("stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, null=True, blank=True, related_name="notification_events")
    title = models.CharField("عنوان", max_length=160)
    summary = models.CharField("متن کوتاه", max_length=300, blank=True, default="")
    details = models.TextField("جزئیات", blank=True, default="")
    entity_type = models.CharField("نوع موجودیت", max_length=40, blank=True, default="")
    entity_id = models.CharField("شناسه‌ی موجودیت", max_length=40, blank=True, default="")
    link_name = models.CharField("نامِ مسیر (URL name)", max_length=80, blank=True, default="")
    link_kwargs = models.JSONField("پارامترهای مسیر", blank=True, default=dict)
    link_permission = models.CharField("مجوزِ صفحه‌ی مقصد", max_length=60, blank=True, default="")
    required_permission = models.CharField("مجوزِ دریافت", max_length=60, blank=True, default="")
    occurred_at = models.DateTimeField("زمانِ وقوع")
    created_at = models.DateTimeField("زمانِ ثبت", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین رخداد", auto_now=True)
    dedupe_key = models.CharField("کلیدِ جلوگیری از تکرار", max_length=200, blank=True, default="")
    group_key = models.CharField("کلیدِ گروه‌بندی", max_length=200, blank=True, default="")
    occurrence_count = models.PositiveIntegerField("تعدادِ رخداد", default=1)
    expires_at = models.DateTimeField("انقضا", null=True, blank=True)
    metadata = models.JSONField("فراداده‌ی عیب‌یابی", blank=True, default=dict)

    class Meta:
        verbose_name = "رویدادِ اعلان"
        verbose_name_plural = "رویدادهای اعلان"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["scope_key", "-id"], name="idx_nev_scope_id"),
            models.Index(fields=["scope_key", "group_key"], name="idx_nev_scope_group"),
            models.Index(fields=["expires_at"], name="idx_nev_expires"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["scope_key", "dedupe_key"], condition=~models.Q(dedupe_key=""), name="uniq_nev_scope_dedupe"),
        ]

    def __str__(self):
        return f"{self.type_key}@{self.scope_key}"


class InboxItem(models.Model):
    """سهمِ هر گیرنده از یک رویداد: خوانده/خوانده‌نشده، بایگانی، Snooze، سنجاق — بین نشست‌ها و دستگاه‌ها ثابت (در دیتابیس)."""

    public_id = models.UUIDField("شناسه‌ی عمومی", default=uuid.uuid4, unique=True, editable=False)
    event = models.ForeignKey(NotificationEvent, verbose_name="رویداد", on_delete=models.CASCADE, related_name="inbox_items")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="گیرنده", on_delete=models.CASCADE, related_name="inbox_items")
    scope_key = models.CharField("کلیدِ محدوده", max_length=30)
    popup = models.BooleanField("نمایشِ فوریِ درون‌برنامه‌ای (Toast)", default=False)
    created_at = models.DateTimeField("زمانِ ایجاد", auto_now_add=True)
    read_at = models.DateTimeField("زمانِ خوانده‌شدن", null=True, blank=True)
    archived_at = models.DateTimeField("زمانِ بایگانی", null=True, blank=True)
    snoozed_until = models.DateTimeField("یادآوری مجدد", null=True, blank=True)
    pinned = models.BooleanField("سنجاق‌شده", default=False)

    class Meta:
        verbose_name = "اعلانِ صندوق"
        verbose_name_plural = "صندوقِ اعلان‌ها"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["user", "scope_key", "read_at", "-id"], name="idx_inbox_user_scope"),
            models.Index(fields=["user", "scope_key", "archived_at"], name="idx_inbox_user_arch"),
        ]
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="uniq_inbox_event_user")]


class NotificationPreference(models.Model):
    """تنظیماتِ شخصیِ اعلان — جدا برای هر (کاربر × محدوده): مدیر پلتفرم و مدیر هر فروشگاه مستقل‌اند. کانال‌های ایمیل/موبایل فقط «آماده‌اند» و فعال نیستند."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    scope_key = models.CharField("کلیدِ محدوده", max_length=30)
    toast_enabled = models.BooleanField("نمایشِ اعلانِ فوری در پنل", default=True)
    browser_enabled = models.BooleanField("اعلانِ سیستمِ مرورگر", default=False)
    min_toast_severity = models.PositiveSmallIntegerField("حداقل اهمیتِ اعلانِ فوری", choices=Severity.choices, default=Severity.IMPORTANT)
    min_browser_severity = models.PositiveSmallIntegerField("حداقل اهمیتِ اعلانِ مرورگر", choices=Severity.choices, default=Severity.IMPORTANT)
    mute_low = models.BooleanField("بی‌صداکردنِ اعلان‌های کم‌اهمیت", default=True)
    disabled_categories = models.JSONField("دسته‌های خاموش", blank=True, default=list)
    email_enabled = models.BooleanField("ایمیل (آینده؛ غیرفعال)", default=False)
    mobile_enabled = models.BooleanField("اعلانِ موبایل (آینده؛ غیرفعال)", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تنظیماتِ اعلان"
        verbose_name_plural = "تنظیماتِ اعلان‌ها"
        constraints = [models.UniqueConstraint(fields=["user", "scope_key"], name="uniq_notif_pref_user_scope")]


class WebPushSubscription(models.Model):
    """دستگاه/مرورگرِ ثبت‌شده برای Web Push. نشانی و کلیدها **رمزنگاری‌شده** (Fernet) ذخیره می‌شوند؛ فقط هشِ نشانی برای یکتایی/جست‌وجو."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="webpush_subscriptions")
    scope_key = models.CharField("کلیدِ محدوده", max_length=30)
    endpoint_hash = models.CharField("هشِ نشانی", max_length=64, unique=True)
    secret_blob = models.TextField("نشانی و کلیدها (رمزنگاری‌شده)")
    device_label = models.CharField("نامِ دستگاه", max_length=80, blank=True, default="")
    user_agent = models.CharField("مرورگر", max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField("لغو", null=True, blank=True)
    failure_count = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "اشتراکِ Web Push"
        verbose_name_plural = "اشتراک‌های Web Push"
        indexes = [models.Index(fields=["user", "scope_key", "revoked_at"], name="idx_wps_user_scope")]


class NotificationDelivery(models.Model):
    """تحویلِ یک اعلانِ صندوق در یک کانالِ بیرونی (Web Push / ایمیل / موبایل) — Outbox پایدار با retry/backoff/dead-letter. Toast و صندوق ردیفِ تحویل ندارند (از خودِ ``InboxItem`` خوانده می‌شوند)."""

    class Channel(models.TextChoices):
        WEB_PUSH = "web_push", "اعلان مرورگر (Web Push)"
        EMAIL = "email", "ایمیل"
        MOBILE_PUSH = "mobile_push", "اعلان موبایل"

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SENDING = "sending", "در حال ارسال"
        DELIVERED = "delivered", "تحویل‌شده"
        FAILED = "failed", "ناموفق (قابل تلاش مجدد)"
        DEAD = "dead", "ناموفق نهایی"
        SKIPPED = "skipped", "ارسال‌نشده"

    inbox_item = models.ForeignKey(InboxItem, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=12, choices=Channel.choices)
    target_key = models.CharField("هدف", max_length=40, blank=True, default="")
    subscription = models.ForeignKey(WebPushSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name="deliveries")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True, default="")
    skip_reason = models.CharField(max_length=60, blank=True, default="")
    provider_ref = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "تحویلِ اعلان"
        verbose_name_plural = "تحویلِ اعلان‌ها"
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="idx_ndel_status_next")]
        constraints = [models.UniqueConstraint(fields=["inbox_item", "channel", "target_key"], name="uniq_ndel_item_channel_target")]
