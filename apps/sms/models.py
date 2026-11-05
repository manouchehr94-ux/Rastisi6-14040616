from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel

from .events import DEFAULT_TEMPLATES, SmsEvent


class SmsTemplate(TimeStampedModel):
    """قالب پیامک هر رویداد — یک رکورد به‌ازای هر کد رویداد، مستقلاً قابل فعال/غیرفعال‌سازی."""

    event_key = models.CharField(
        "رویداد", max_length=30, choices=SmsEvent.choices, unique=True
    )
    title = models.CharField("عنوان", max_length=150)
    body = models.TextField("متن قالب")
    is_active = models.BooleanField("فعال", default=True)
    melipayamak_body_id = models.CharField(
        "BodyId ملی‌پیامک", max_length=30, blank=True, default="",
        help_text="شناسه الگوی تاییدشده در وب‌سرویس خدماتی ملی‌پیامک.",
    )
    melipayamak_variables_order = models.CharField(
        "ترتیب متغیرهای ملی‌پیامک", max_length=255, blank=True, default="otp_code",
        help_text="نام متغیرها به ترتیب Pattern؛ مثال: otp_code,expire_minutes",
    )
    kavenegar_template = models.CharField(
        "Template کاوه‌نگار", max_length=100, blank=True, default="",
        help_text="نام قالب VerifyLookup برای پیام‌های OTP.",
    )

    class Meta:
        verbose_name = "قالب پیامک"
        verbose_name_plural = "قالب‌های پیامک"
        ordering = ["event_key"]

    def __str__(self):
        return self.title

    @classmethod
    def ensure_defaults(cls) -> None:
        """برای هر رویداد تعریف‌شده که هنوز قالبی ندارد، یک قالب پیش‌فرض می‌سازد (بوت‌استرپ، مثل ShopSettings.load)."""
        existing = set(cls.objects.values_list("event_key", flat=True))
        missing = [event for event in SmsEvent.values if event not in existing]
        cls.objects.bulk_create([
            cls(event_key=event, title=SmsEvent(event).label, body=DEFAULT_TEMPLATES[event])
            for event in missing
        ])


class SmsBillingPolicy(TimeStampedModel):
    """سیاست سراسری قیمت‌گذاری و اعتبار پیامک در سطح پلتفرم.

    فقط رکورد pk=1 توسط پنل مالک پلتفرم استفاده می‌شود. هر ``chars_per_credit``
    کاراکتر یک واحد اعتبار محسوب می‌شود؛ قیمت هر واحد و سقف بدهی OTP نیز
    همین‌جا قابل ویرایش‌اند.
    """

    chars_per_credit = models.PositiveIntegerField("کاراکتر در هر اعتبار", default=70)
    price_per_credit_toman = models.PositiveIntegerField("قیمت هر اعتبار (تومان)", default=205)
    otp_overdraft_limit = models.PositiveIntegerField("سقف بدهی OTP", default=10)

    class Meta:
        verbose_name = "سیاست هزینه پیامک"
        verbose_name_plural = "سیاست هزینه پیامک"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"هر {self.chars_per_credit} کاراکتر = {self.price_per_credit_toman} تومان"


class SmsLog(TimeStampedModel):
    """تاریخچه‌ی هر تلاش برای ارسال پیامک — برای پیگیری و رفع اشکال.

    ``store`` عمداً ``null=True`` است: ردیف‌های پیش از افزودنِ این فیلد
    Store‌شان قابلِ بازسازی نیست (هیچ‌جا ذخیره نشده بود) — به‌جایِ حدس‌زدن یا
    نسبت‌دادنِ نادرست، آن ردیف‌های قدیمی «بی‌صاحب» می‌مانند و
    ``sms_admin_service.filtered_logs`` با فیلترِ الزامیِ Store به‌طورِ
    خودکار از دیدِ همه‌ی داشبوردها کنار گذاشته می‌شوند (ایزوله‌سازیِ
    چندمستأجری — پیش از این فیلد، لاگِ هر Store برایِ همه‌ی Store‌های دیگر
    هم قابلِ دیدن بود، شاملِ متنِ کاملِ پیامکِ OTP)."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        related_name="sms_logs", null=True, blank=True,
    )
    event_key = models.CharField("رویداد", max_length=30, choices=SmsEvent.choices)
    recipient = models.CharField("گیرنده", max_length=15)
    message = models.TextField("متن نهایی")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField("پیام خطا", blank=True)
    provider_ref_id = models.CharField("شناسه‌ی ارجاع سرویس", max_length=100, blank=True)
    provider = models.CharField("شرکت پیامکی", max_length=20, blank=True, default="")
    character_count = models.PositiveIntegerField("تعداد کاراکتر", default=0)
    billable_units = models.PositiveIntegerField("تعداد اعتبار مصرفی", default=0)
    unit_price_toman = models.PositiveIntegerField("قیمت هر اعتبار (تومان)", default=0)
    cost_toman = models.PositiveBigIntegerField("هزینه نهایی (تومان)", default=0)
    balance_before = models.IntegerField("اعتبار قبل", null=True, blank=True)
    balance_after = models.IntegerField("اعتبار بعد", null=True, blank=True)
    attempt_count = models.PositiveIntegerField("تعداد تلاش", default=0)
    sent_at = models.DateTimeField("زمان ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "گزارش پیامک"
        verbose_name_plural = "گزارش پیامک‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_event_key_display()} → {self.recipient} ({self.get_status_display()})"


class SmsOutboxItem(TimeStampedModel):
    """صفِ پیامک‌های در انتظارِ ارسال توسط گیت‌وی اندرویدِ SmsRasti یک Store.

    برخلافِ ``SmsLog`` (که فقط تاریخچه‌ی یک تلاشِ همزمان است)، این مدل
    چرخه‌ی عمرِ واقعیِ ارسال را دنبال می‌کند: ``pending`` → ``sending``
    (poll شده توسطِ دستگاه، هنوز تأییدنشده) → ``sent``/``failed`` (فقط با
    ack صریحِ دستگاه). هرگز صرفِ poll‌شدن را «ارسال‌شده» علامت نمی‌زند —
    برخلافِ نسخه‌ی باگ‌دارِ مرجع (``reference_imports/.../gateway_api.py``)
    که این کار را می‌کرد؛ اینجا از الگویِ بهترِ نسخه‌ی جایگزین‌شده‌ی همان
    مرجع (``sms_gateway.py``) پیروی شده: claim فقط ``sending`` می‌کند."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        SENDING = "sending", "در حالِ ارسال"
        SENT = "sent", "ارسال‌شده"
        FAILED = "failed", "ناموفق"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_outbox_items",
    )
    phone = models.CharField("گیرنده", max_length=15)
    message = models.TextField("متن پیامک")
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_ref_id = models.CharField("شناسه‌ی ارجاعِ گیت‌وی", max_length=100, blank=True)
    error_message = models.TextField("پیامِ خطا", blank=True)
    attempt_count = models.PositiveIntegerField("تعدادِ claim", default=0)
    claimed_at = models.DateTimeField("زمانِ claim", null=True, blank=True)
    sent_at = models.DateTimeField("زمانِ ارسال", null=True, blank=True)

    class Meta:
        verbose_name = "پیامِ صفِ SmsRasti"
        verbose_name_plural = "پیام‌هایِ صفِ SmsRasti"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.phone} ({self.get_status_display()})"


class SmsBalance(TimeStampedModel):
    """اعتبارِ باقی‌مانده‌ی پیامکِ هر Store — منبعِ واحدِ حقیقتِ «چند پیامک
    دیگر می‌تواند بفرستد». هر ارسالِ موفق یک واحد کم می‌کند (نگاه کنید به
    ``apps.sms.services.balance_service``)؛ اعتبار فقط با تکمیلِ یک
    ``SmsPackagePurchase`` افزوده می‌شود.

    ارسال‌های عادی بدون اعتبار کافی مسدود می‌شوند. OTP استثنای ایمنی است و
    می‌تواند تا سقف قابل‌تنظیم ``SmsBillingPolicy.otp_overdraft_limit`` وارد
    اعتبار منفی شود تا مشتری فروشگاه در زمان کمبود اعتبار قفل نشود."""

    store = models.OneToOneField(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_balance",
    )
    credits = models.IntegerField("اعتبارِ باقی‌مانده", default=0)

    class Meta:
        verbose_name = "اعتبارِ پیامکِ فروشگاه"
        verbose_name_plural = "اعتبارهایِ پیامکِ فروشگاه"

    def __str__(self):
        return f"{self.store.name} — {self.credits} اعتبار"


class SmsPackage(TimeStampedModel):
    """بسته‌ی خریدِ اعتبارِ پیامک — تعریف‌شده و مدیریت‌شده توسطِ مالکِ پلتفرم
    (Django Admin، فقط superuser)، نه Store. فروشگاه‌ها فقط بسته‌هایِ
    ``is_active=True`` را در تنظیماتِ پیامکِ خودشان می‌بینند و می‌خرند."""

    name = models.CharField("نام بسته", max_length=100)
    credit_amount = models.PositiveIntegerField("تعدادِ اعتبار")
    price = models.DecimalField("قیمت (تومان)", max_digits=12, decimal_places=0)
    is_active = models.BooleanField("فعال", default=True)
    display_order = models.PositiveIntegerField("ترتیبِ نمایش", default=0)

    class Meta:
        verbose_name = "بسته‌ی پیامک"
        verbose_name_plural = "بسته‌های پیامک"
        ordering = ["display_order", "credit_amount"]

    def __str__(self):
        return f"{self.name} ({self.credit_amount} اعتبار)"


class SmsPackagePurchase(TimeStampedModel):
    """رکوردِ درخواستِ خریدِ یک بسته توسطِ یک Store.

    ``PENDING`` یعنی درخواست ثبت شده اما هنوز اعتباری افزوده نشده. اعتبار فقط از
    ``balance_service.complete_purchase`` افزوده می‌شود: یا پس از **پرداختِ آنلاینِ تأییدشده**
    توسطِ درگاهِ پلتفرم (``apps.billing.services.sms_purchase_payment_service``)، یا با
    تکمیلِ دستیِ مدیرِ پلتفرم. هر دو از یک قفل و یک دفترِ تغییرناپذیر (``SmsCreditLedger``)
    عبور می‌کنند؛ بازگشتِ مرورگر هرگز مدرکِ پرداخت نیست."""

    class Status(models.TextChoices):
        PENDING = "pending", "در انتظارِ تکمیل"
        COMPLETED = "completed", "تکمیل‌شده"
        CANCELED = "canceled", "لغوشده"
        REFUNDED = "refunded", "بازپرداخت‌شده"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_package_purchases",
    )
    package = models.ForeignKey(
        SmsPackage, verbose_name="بسته", on_delete=models.PROTECT, related_name="purchases",
    )
    credit_amount = models.PositiveIntegerField("تعدادِ اعتبار (اسنپ‌شات)")
    price = models.DecimalField("قیمت (اسنپ‌شات، تومان)", max_digits=12, decimal_places=0)
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.PENDING)
    completed_at = models.DateTimeField("زمانِ تکمیل", null=True, blank=True)
    refunded_at = models.DateTimeField("زمانِ بازپرداخت", null=True, blank=True)

    class Meta:
        verbose_name = "خریدِ بسته‌ی پیامک"
        verbose_name_plural = "خریدهایِ بسته‌ی پیامک"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.store.name} ← {self.package.name} ({self.get_status_display()})"


class SmsPackagePaymentAttempt(TimeStampedModel):
    """یک تلاشِ پرداختِ آنلاینِ **پلتفرم** برای یک ``SmsPackagePurchase`` — زمینهٔ مالیِ صریح و جدا از
    پرداختِ سفارشِ فروشگاه (``orders.PaymentAttempt``) و از فاکتورِ اشتراک. مبلغ/ارز از اسنپ‌شاتِ سمتِ
    سرورِ خرید می‌آید، نه مرورگر. هر Retry یک ردیفِ تازه است؛ تلاش‌ها تاریخی‌اند و
    «موفق»شدنِ آن‌ها فقط از مسیرِ ``sms_purchase_payment_service`` ممکن است."""

    class Status(models.TextChoices):
        CREATED = "created", "ایجادشده"
        PENDING = "pending", "در انتظار"
        REQUIRES_ACTION = "requires_action", "نیازمندِ اقدام"
        SUCCEEDED = "succeeded", "موفق"
        FAILED = "failed", "ناموفق"
        CANCELLED = "cancelled", "لغوشده"
        EXPIRED = "expired", "منقضی‌شده"

    FINAL_STATUSES = frozenset({Status.SUCCEEDED, Status.FAILED, Status.CANCELLED, Status.EXPIRED})

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="sms_purchase_payment_attempts",
    )
    purchase = models.ForeignKey(
        SmsPackagePurchase, verbose_name="خرید", on_delete=models.PROTECT, related_name="payment_attempts",
    )
    provider = models.CharField("Provider", max_length=40)
    status = models.CharField("وضعیت", max_length=16, choices=Status.choices, default=Status.CREATED, db_index=True)
    amount = models.DecimalField("مبلغ (تومان)", max_digits=14, decimal_places=0)
    currency = models.CharField("ارز", max_length=8, default="IRT")
    public_token = models.CharField("توکنِ عمومی", max_length=44, unique=True, editable=False)
    provider_payment_id = models.CharField("شناسه‌ی پرداختِ Provider", max_length=120, blank=True, default="")
    provider_session_id = models.CharField("شناسه‌ی جلسه‌ی Provider", max_length=120, blank=True, default="")
    idempotency_key = models.CharField("کلیدِ یکتا", max_length=100, unique=True)
    attempt_number = models.PositiveIntegerField("شماره‌ی تلاش", default=1)
    failure_code = models.CharField("کدِ خطا", max_length=64, blank=True, default="")
    failure_message = models.CharField("پیامِ خطا", max_length=300, blank=True, default="")
    started_at = models.DateTimeField("زمانِ شروع", null=True, blank=True)
    completed_at = models.DateTimeField("زمانِ پایان", null=True, blank=True)
    return_to = models.CharField("مقصد بازگشت", max_length=500, blank=True, default="")
    #: داده‌ی غیرحساسِ جلسه‌ی Provider که برای verify لازم است (مثلاً ``urlId`` پاسارگاد) — فقط سمتِ سرور، هرگز از مرورگر.
    provider_extra = models.JSONField("داده‌ی جلسه‌ی Provider", blank=True, default=dict)

    class Meta:
        verbose_name = "تلاشِ پرداختِ بسته‌ی پیامک"
        verbose_name_plural = "تلاش‌هایِ پرداختِ بسته‌ی پیامک"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_payment_id"], condition=~models.Q(provider_payment_id=""),
                name="uniq_smspay_provider_payment_id",
            ),
            models.CheckConstraint(check=models.Q(amount__gte=0), name="smspay_amount_non_negative"),
        ]
        indexes = [
            models.Index(fields=["purchase", "status"], name="idx_smspay_purchase_status"),
            models.Index(fields=["store", "status"], name="idx_smspay_store_status"),
        ]

    def __str__(self):
        return f"SmsPay<{self.public_token}> {self.get_status_display()}"

    @property
    def is_final(self) -> bool:
        return self.status in self.FINAL_STATUSES


class SmsCreditLedger(TimeStampedModel):
    """دفترِ **تغییرناپذیرِ** اعتبارِ پیامکِ ناشی از خرید/بازپرداختِ بسته. هر تغییرِ اعتبار با مقدارِ
    قبل/تغییر/بعد و پیوند به خرید و تلاشِ پرداخت ثبت می‌شود. قیدِ یکتا ``(purchase, kind)`` تضمینِ
    **سطحِ پایگاه‌داده** است که اعتبارِ یک خرید دقیقاً یک‌بار افزوده و دقیقاً یک‌بار برگردانده شود،
    حتی با callbackِ تکراری یا درخواست‌های هم‌زمان. (اصلاح‌هایِ دستی در ``SmsCreditAdjustment`` می‌مانند.)"""

    class Kind(models.TextChoices):
        PURCHASE = "purchase", "افزودنِ اعتبار (خرید)"
        PURCHASE_REVERSAL = "purchase_reversal", "بازگشتِ اعتبار (بازپرداخت)"

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.PROTECT, related_name="sms_credit_ledger",
    )
    purchase = models.ForeignKey(
        SmsPackagePurchase, verbose_name="خرید", on_delete=models.PROTECT, related_name="ledger_entries",
    )
    payment_attempt = models.ForeignKey(
        SmsPackagePaymentAttempt, verbose_name="تلاشِ پرداخت", on_delete=models.PROTECT,
        null=True, blank=True, related_name="ledger_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sms_credit_ledger_entries",
    )
    kind = models.CharField("نوع", max_length=20, choices=Kind.choices)
    delta = models.IntegerField("مقدارِ تغییر")
    balance_before = models.IntegerField("اعتبارِ پیش از تغییر")
    balance_after = models.IntegerField("اعتبارِ پس از تغییر")
    note = models.CharField("یادداشت", max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "ردیفِ دفترِ اعتبارِ پیامک"
        verbose_name_plural = "دفترِ اعتبارِ پیامک"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["purchase", "kind"], name="uniq_smsledger_purchase_kind"),
        ]

    def __str__(self):
        return f"{self.store_id}: {self.get_kind_display()} {self.delta:+d}"


class SmsCreditAdjustment(TimeStampedModel):
    """دفترِ تغییراتِ دستیِ اعتبارِ پیامکِ یک Store — هر ردیف یک اصلاحِ
    غیرِخودکار (نه ناشی از خرید/مصرفِ عادی) توسطِ یک مدیرِ پلتفرم است، با
    مقدارِ قبل/تغییر/بعد. تغییرناپذیر است (فقط created_at معنا دارد) — یک
    اصلاحِ اشتباه با یک ردیفِ جبرانیِ تازه درست می‌شود، نه ویرایشِ این رکورد."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="sms_credit_adjustments",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sms_credit_adjustments",
    )
    delta = models.IntegerField("مقدارِ تغییر")
    balance_before = models.IntegerField("اعتبارِ پیش از تغییر")
    balance_after = models.IntegerField("اعتبارِ پس از تغییر")
    reason = models.CharField("دلیل", max_length=200)
    note = models.CharField("یادداشتِ داخلی", max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "اصلاحِ اعتبارِ پیامک"
        verbose_name_plural = "اصلاح‌هایِ اعتبارِ پیامک"
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.store.name}: {sign}{self.delta} ({self.reason})"


class OtpCode(TimeStampedModel):
    """کد یکبار مصرف پیامکی — برای ورود و تأیید شماره موبایل در خرید مهمان.

    ``code_hash`` — نه متنِ خامِ کد — ذخیره می‌شود (با همان هَشرِ رمزِ عبورِ
    جنگو، ``django.contrib.auth.hashers``)، دقیقاً مثلِ ``apps.portal.
    models.OwnerOtpChallenge``؛ حتی دسترسیِ خواندنی به دیتابیس کدِ فعال را
    فاش نمی‌کند (یکپارچه‌سازیِ احرازِ هویت — پیش از این نسخه، ``code``
    متنِ خام بود)."""

    phone = models.CharField("موبایل", max_length=15, db_index=True)
    code_hash = models.CharField("هَشِ کد", max_length=200)
    expires_at = models.DateTimeField("زمان انقضا")
    attempt_count = models.PositiveIntegerField("تعداد تلاش تأیید", default=0)
    is_used = models.BooleanField("مصرف‌شده", default=False)

    class Meta:
        verbose_name = "کد یکبار مصرف"
        verbose_name_plural = "کدهای یکبار مصرف"
        ordering = ["-created_at"]

    def __str__(self):
        status = "مصرف‌شده" if self.is_used else "فعال"
        return f"{self.phone} — {status}"
