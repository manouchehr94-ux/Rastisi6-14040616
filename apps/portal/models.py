import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ShopSettings, TimeStampedModel

#: Reuses apps.core.models.ShopSettings.SmsBackend's choices/labels instead
#: of redefining them — see PlatformConfiguration.sms_backend.
_SmsBackendChoices = ShopSettings.SmsBackend


class OwnerProfile(TimeStampedModel):
    """Portal-only profile data for a Store-owner ``User``.

    Deliberately separate from ``apps.customers.models.Customer`` (ADR-93):
    an owner registering through the portal never gets a ``Customer`` row as
    a side effect, and a storefront customer never gets an ``OwnerProfile``.
    Both are optional one-to-one extensions of the same plain ``auth.User``
    table — a person can hold either, both, or neither.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="owner_profile",
    )
    full_name = models.CharField("نام و نام خانوادگی", max_length=150)
    phone = models.CharField(
        "موبایل", max_length=15, unique=True, null=True, blank=True,
        help_text="فرمتِ متعارف ۰۹xxxxxxxxx — شناسه‌ی اصلیِ ورودِ OTP (Section 3).",
    )

    class Meta:
        verbose_name = "پروفایل مالک"
        verbose_name_plural = "پروفایل‌های مالک"

    def __str__(self):
        return self.full_name or self.phone or self.user.email


class OwnerTermsAcceptance(TimeStampedModel):
    """سابقه‌ی ماندگار و نسخه‌دارِ پذیرشِ «قوانین و مقررات» توسطِ یک مالکِ *تازه*.

    یک Boolean کافی نیست (متنِ قانونی تغییر می‌کند)، پس هر ردیف «چه کسی، کدام نسخه،
    چه زمانی، از کدام مسیر» را نگه می‌دارد. ``(user, terms_version)`` یکتاست تا تکرار/
    هم‌زمانی بی‌اثر (idempotent) باشد. فقط هنگامِ ساخته‌شدنِ واقعیِ ``OwnerProfile`` نوشته
    می‌شود؛ هرگز برایِ مالکانِ قدیمی «ساختگی» ثبت نمی‌شود و هیچ OTP/IP/User-Agentی
    اینجا نیست."""

    class Source(models.TextChoices):
        REGISTRATION = "registration", "ثبت‌نام (/register/)"
        SIGNUP_COMPLETE = "signup_complete", "تکمیل ثبت‌نام پس از ورودِ OTP"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE,
        related_name="terms_acceptances",
    )
    terms_version = models.CharField("نسخه‌ی قوانین", max_length=40)
    accepted_at = models.DateTimeField("زمانِ پذیرش", default=timezone.now)
    source = models.CharField("مسیرِ پذیرش", max_length=20, choices=Source.choices)

    class Meta:
        verbose_name = "پذیرشِ قوانین توسطِ مالک"
        verbose_name_plural = "پذیرش‌هایِ قوانین توسطِ مالکان"
        constraints = [
            models.UniqueConstraint(fields=["user", "terms_version"], name="uniq_owner_terms_acceptance_user_version"),
        ]
        indexes = [models.Index(fields=["terms_version"], name="idx_owner_terms_version")]

    def __str__(self):
        return f"{self.user_id} → {self.terms_version}"


class OwnerOtpChallenge(TimeStampedModel):
    """کدِ یکبارمصرفِ ورود/ثبت‌نامِ مالک با موبایل (Section 3).

    ``code_hash`` — نه متنِ خامِ کد — ذخیره می‌شود (با همان هَشرِ رمزِ عبورِ
    جنگو، ``django.contrib.auth.hashers``)؛ حتی دسترسیِ خواندنی به دیتابیس
    کدِ OTP فعال را فاش نمی‌کند."""

    class Purpose(models.TextChoices):
        REGISTER = "register", "ثبت‌نام"
        LOGIN = "login", "ورود"
        STEP_UP = "step_up", "تأییدِ عملیاتِ حساس (Section 10)"
        #: بازیابی/تعیینِ رمز عبور با موبایل. هرگز ورود نیست و هیچ‌چیز نمی‌سازد؛ فقط
        #: یک مجوزِ کوتاه‌عمرِ سمتِ سرور برایِ تعیینِ رمزِ جدید صادر می‌کند.
        PASSWORD_RESET = "reset", "بازیابی رمز عبور"

    phone = models.CharField("موبایل", max_length=15, db_index=True)
    purpose = models.CharField("هدف", max_length=10, choices=Purpose.choices)
    code_hash = models.CharField("هَشِ کد", max_length=200)
    attempt_count = models.PositiveSmallIntegerField("تعداد تلاشِ تأیید", default=0)
    expires_at = models.DateTimeField("زمان انقضا")
    consumed_at = models.DateTimeField("زمان مصرف", null=True, blank=True)

    class Meta:
        verbose_name = "کدِ یکبارمصرفِ مالک"
        verbose_name_plural = "کدهای یکبارمصرفِ مالک"
        indexes = [
            models.Index(fields=["phone", "purpose", "created_at"], name="idx_owner_otp_phone_purpose"),
        ]

    def __str__(self):
        return f"OTP:{self.phone}:{self.purpose}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired


def _generate_handoff_token() -> str:
    return secrets.token_urlsafe(32)


class AdminHandoffTicket(TimeStampedModel):
    """Single-use, short-lived ticket bridging owner-portal auth to a Store's
    distinct Merchant Admin host (ADR-98).

    ``SESSION_COOKIE_DOMAIN`` is unset in this project (host-only cookies by
    design), so a logged-in owner on the portal host has no session on
    ``{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}``. This ticket is
    issued only for a (user, store) pair with an active ``StoreMembership``,
    is valid for a short window, and is consumed exactly once (atomically) by
    the admin-host handoff view, which then calls Django's own ``login()``
    for that host. It grants no authorization by itself — every subsequent
    admin-portal request still goes through the existing ``staff_required``/
    membership checks unchanged.
    """

    token = models.CharField("توکن", max_length=64, unique=True, default=_generate_handoff_token, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="کاربر", on_delete=models.CASCADE, related_name="admin_handoff_tickets",
    )
    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE, related_name="admin_handoff_tickets",
    )
    destination_path = models.CharField("مسیر مقصد", max_length=200, default="/admin-portal/")
    expires_at = models.DateTimeField("زمان انقضا")
    consumed_at = models.DateTimeField("زمان مصرف", null=True, blank=True)
    # خالی یعنی یک handoff معمولیِ مالک بین فروشگاه‌های خودش است (بدونِ
    # تغییر در رفتارِ موجود). مقداردهی‌شده یعنی این بلیت را یک مدیرِ پلتفرم
    # برایِ «ورودِ پشتیبانی» صادر کرده — نگاه کنید به
    # ``apps.portal.services.handoff_service.issue_support_ticket``؛
    # ``consume_admin_handoff`` از رویِ همین فیلد نشانه‌ی «حالتِ پشتیبانی
    # فعال است» را در سشن می‌گذارد.
    issued_by_platform_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="صادرشده توسطِ مدیرِ پلتفرم (پشتیبانی)",
        on_delete=models.SET_NULL, null=True, blank=True, related_name="issued_support_handoff_tickets",
    )

    class Meta:
        verbose_name = "بلیت ورود به پنل مدیریت"
        verbose_name_plural = "بلیت‌های ورود به پنل مدیریت"
        indexes = [
            models.Index(fields=["token", "consumed_at"], name="idx_handoff_token_consumed"),
        ]

    def __str__(self):
        return f"handoff:{self.user_id}->{self.store_id}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired


#: Sensitive owner actions that MAY require fresh step-up OTP verification
#: (spec §3.20). This is the whitelist enforced on
#: ``PlatformConfiguration.step_up_actions`` — an arbitrary key can never be
#: added via the edit form, only these. Not every key is wired to an actual
#: enforcement point yet; ``step_up_service`` (a later slice) is the single
#: place that reads this list at the moment a sensitive action needs it.
STEP_UP_ACTION_CHOICES = (
    ("subscription_purchase_confirm", "تأیید خرید اشتراک"),
    ("permanent_handle_claim", "ثبت نهاییِ نام دائمی فروشگاه"),
    ("custom_domain_activate", "فعال‌سازی دامنه‌ی اختصاصی"),
    ("store_delete", "حذف فروشگاه"),
    ("store_ownership_transfer", "انتقال مالکیت فروشگاه"),
    ("owner_email_change", "تغییر ایمیل مالک"),
    ("owner_phone_change", "تغییر شماره موبایل مالک"),
    ("owner_security_change", "تغییر امنیتی حساب مالک"),
    ("staff_high_privilege_add", "افزودن عضو تیم با دسترسی بالا"),
    ("staff_owner_remove", "حذف یک مالک دیگر"),
    ("payment_method_change", "تغییر روش پرداخت"),
    ("platform_superuser_change", "تغییرات حساس مدیر پلتفرم"),
)
STEP_UP_ACTION_KEYS = frozenset(key for key, _label in STEP_UP_ACTION_CHOICES)

#: Defaults chosen conservatively: every irreversible/high-impact action
#: starts protected; low-risk ones start off so the platform owner opts in.
DEFAULT_STEP_UP_ACTIONS = {
    "subscription_purchase_confirm": True,
    "permanent_handle_claim": True,
    "custom_domain_activate": True,
    "store_delete": True,
    "store_ownership_transfer": True,
    "owner_email_change": True,
    "owner_phone_change": True,
    "owner_security_change": True,
    "staff_high_privilege_add": True,
    "staff_owner_remove": True,
    "payment_method_change": False,
    "platform_superuser_change": True,
}


class PlatformConfiguration(TimeStampedModel):
    """Singleton, platform-wide editable configuration (spec §Section 2).

    Exactly one row ever exists (``pk=1``, enforced by ``save()``). Read via
    ``apps.portal.services.platform_config_service.get_platform_
    configuration()`` — cached, never queried per-template-render directly.
    Edited only through Platform Admin, by a superuser, with every change
    audited (``PlatformAuditLogEntry``).
    """

    default_trial_days = models.PositiveIntegerField("روزهای پیش‌فرض دوره‌ی آزمایشی", default=30)
    deletion_retention_days = models.PositiveIntegerField(
        "روزهای نگهداریِ داده پس از درخواست حذف", default=365,
        help_text="بین ۱۸۰ تا ۳۶۵ روز (۶ تا ۱۲ ماه).",
    )
    primary_brand_color = models.CharField("رنگ اصلی برند", max_length=7, default="#10a37a")
    secondary_brand_color = models.CharField("رنگ ثانویه برند", max_length=7, default="#e0a72e")
    temporary_logo_text = models.CharField(
        "نشان موقت برند (متنی)", max_length=20, default="راستیسی",
        help_text="تا زمانی‌که لوگوی نهایی آپلود نشده، همین‌جا نمایش داده می‌شود.",
    )
    logo = models.ImageField("لوگوی نهایی", upload_to="platform/", null=True, blank=True)
    support_contact_phone = models.CharField("تلفن پشتیبانی", max_length=20, blank=True, default="")
    support_contact_email = models.EmailField("ایمیل پشتیبانی", blank=True, default="")
    step_up_actions = models.JSONField(
        "سیاست تأیید مجدد (Step-up OTP)", default=dict,
        help_text="نگاشتِ کلیدِ عملیات به روشن/خاموش — فقط کلیدهای STEP_UP_ACTION_CHOICES مجازند.",
    )
    default_payment_provider = models.CharField(
        "درگاه پرداخت پیش‌فرض", max_length=40, default="manual",
        choices=[("manual", "دستی (بدونِ درگاهِ واقعی)"), ("zibal", "زیبال")],
        help_text="Providerِ فعالِ پرداختِ اشتراکِ خودِ پلتفرم — جدا از درگاهِ پرداختِ سفارشِ هر Store.",
    )
    enabled_payment_providers = models.JSONField(
        "درگاه‌های پرداخت فعال", default=list,
        help_text="فهرستِ کدهای درگاه فعال — نمایش‌دادنی در تسویه‌حساب اشتراک.",
    )
    enamad_verification_meta_tag = models.TextField(
        "متاتگ احراز فنی اینماد",
        blank=True,
        default="",
        help_text=(
            "متاتگی که سامانه اینماد برای احراز دسترسی فنی دامنه rastisi.ir "
            "می‌دهد. فقط یک <meta name=... content=...> امن پذیرفته می‌شود."
        ),
    )
    # --- نمادِ نهاییِ اینماد (پس از صدور) — کاملاً مستقل از متاتگِ احرازِ فنیِ
    # بالا. فقط دو شناسه‌ی ساختاریافته که خودِ اینماد صادر می‌کند؛ هرگز
    # HTML/اسکریپتِ دلخواه. RastiSi از رویِ همین دو مقدار، لینک/تصویرِ
    # امن را با URLِ ثابتِ trustseal.enamad.ir می‌سازد (نگاه کنید به
    # ``apps.stores.services.enamad_verification_service``).
    enamad_id = models.CharField("شناسه‌ی نمادِ نهاییِ پلتفرم", max_length=12, blank=True, default="")
    enamad_auth_code = models.CharField("کدِ تأییدِ نمادِ نهاییِ پلتفرم", max_length=64, blank=True, default="")
    enamad_badge_enabled = models.BooleanField(
        "نمایشِ نمادِ نهایی فعال است", default=False,
        help_text="حتی اگر شناسه/کد ثبت شده باشد، تا این کلید روشن نشود نماد نمایش داده نمی‌شود.",
    )

    # --- درگاهِ پیامکِ مرکزیِ پلتفرم ---
    # زیرساختِ ارسالِ پیامک (ارائه‌دهنده/کلیدِ API/شماره‌ی فرستنده) یک تصمیمِ
    # سطحِ پلتفرم است، نه Store — همان انتخابِ backend اینجا برایِ OTP هویتِ
    # مشتری/مالک و پیامک‌های رویدادِ همه‌ی Storeها استفاده می‌شود (نگاه کنید
    # به ``apps.portal.services.owner_sms_service.get_platform_sms_backend``
    # و ``apps.sms.services.sms_service.get_backend``). استثنایِ عمدی: گیت‌وی
    # اندرویدِ SmsRasti، که برخلافِ بقیه دستگاهِ فیزیکیِ خودِ همان Store است،
    # نه زیرساختِ پلتفرم — همچنان در تنظیماتِ خودِ Store پیکربندی می‌شود.
    sms_backend = models.CharField(
        "درگاهِ پیامکِ مرکزی", max_length=20, blank=True,
        choices=[
            (code, label) for code, label in _SmsBackendChoices.choices
            if code != _SmsBackendChoices.SMSRASTI
        ],
        default=_SmsBackendChoices.CONSOLE,
    )
    sms_sender_number = models.CharField("شماره‌ی فرستنده‌ی مرکزی", max_length=20, blank=True, default="")
    # اعتبارنامه‌های ارائه‌دهنده (نام‌کاربری/رمز/کلیدِ API) به‌صورتِ یک JSON
    # رمزنگاری‌شده در یک فیلد ذخیره می‌شوند — همان الگویِ
    # ``apps.orders.models.PaymentGatewayConfig.encrypted_credentials``
    # (تکرار نشده، بازاستفاده‌شده) با همان ابزارِ رمزنگاریِ Fernet
    # (``apps.orders.encryption``).
    encrypted_sms_credentials = models.TextField(
        "اعتبارنامه‌ی پیامکِ رمزنگاری‌شده", blank=True, default="",
        help_text="مقدارِ رمزنگاری‌شده — هرگز مستقیم خوانده نمی‌شود",
    )

    # --- عملیاتِ پلتفرم (Section 20) ---
    maintenance_mode_enabled = models.BooleanField(
        "حالتِ تعمیرات", default=False,
        help_text="روشن یعنی پرتالِ مالک/فروشگاه‌سازیِ تازه موقتاً در دسترسِ عمومی نیست.",
    )
    new_store_registration_enabled = models.BooleanField(
        "ثبت‌نامِ فروشگاهِ تازه فعال است", default=True,
    )

    def get_sms_credentials(self) -> dict:
        """رمزگشایی و بازگرداندنِ اعتبارنامه‌های پیامک به‌صورتِ dict."""
        import json

        from apps.orders.encryption import decrypt_credential

        if not self.encrypted_sms_credentials:
            return {}
        plaintext = decrypt_credential(self.encrypted_sms_credentials)
        if not plaintext:
            return {}
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            return {}

    # --- زیبال — درگاهِ پرداختِ اشتراکِ خودِ پلتفرم (Phase 3) ---
    # این اعتبارنامه فقط برایِ پرداختِ اشتراکِ RastiSi از مشتریانِ راستیسی
    # است (``apps.billing``) — کاملاً جدا از اعتبارنامه‌یِ زیبالِ هر Store
    # برایِ پرداختِ سفارش‌هایِ مشتریانِ آن Store (``apps.orders.PaymentGatewayConfig``).
    # این دو دامنه هرگز نباید با هم مخلوط شوند.
    zibal_sandbox_mode = models.BooleanField(
        "حالتِ آزمایشیِ زیبال (Sandbox)", default=False,
        help_text="در حالتِ آزمایشی، merchant واقعی نادیده گرفته و مقدارِ Sandbox زیبال استفاده می‌شود.",
    )
    encrypted_zibal_credentials = models.TextField(
        "اعتبارنامه‌ی زیبالِ پلتفرمِ رمزنگاری‌شده", blank=True, default="",
        help_text="مقدارِ رمزنگاری‌شده — هرگز مستقیم خوانده نمی‌شود",
    )

    def get_zibal_credentials(self) -> dict:
        """رمزگشایی و بازگرداندنِ اعتبارنامه‌ی زیبالِ پلتفرم به‌صورتِ dict."""
        import json

        from apps.orders.encryption import decrypt_credential

        if not self.encrypted_zibal_credentials:
            return {}
        plaintext = decrypt_credential(self.encrypted_zibal_credentials)
        if not plaintext:
            return {}
        try:
            return json.loads(plaintext)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_zibal_credentials(self, *, remove_keys=(), **updates) -> None:
        """اعتبارنامه‌ی زیبالِ پلتفرم را ادغام و رمزنگاری می‌کند — Secretِ خالی
        یعنی «بدون تغییر» (همان الگویِ ``set_sms_credentials``)."""
        import json

        from apps.orders.encryption import encrypt_credential

        merged = dict(self.get_zibal_credentials())
        for key in remove_keys:
            merged.pop(key, None)
        merged.update({k: v for k, v in updates.items() if v is not None and v != ""})
        clean = {k: v for k, v in merged.items() if v is not None and v != ""}
        self.encrypted_zibal_credentials = (
            encrypt_credential(json.dumps(clean, ensure_ascii=False))
            if clean else ""
        )

    def set_sms_credentials(self, *, remove_keys=(), **updates) -> None:
        """اعتبارنامه/پیکربندی SMS را ادغام و رمزنگاری می‌کند.

        Secretهای خالی «بدون تغییر» هستند؛ ``remove_keys`` فقط برای Routeهای
        غیرمحرمانه مثل BodyId/Template است که باید قابل پاک‌کردن باشند.
        """
        import json

        from apps.orders.encryption import encrypt_credential

        merged = dict(self.get_sms_credentials())
        for key in remove_keys:
            merged.pop(key, None)
        merged.update({k: v for k, v in updates.items() if v is not None and v != ""})
        clean = {k: v for k, v in merged.items() if v is not None and v != ""}
        self.encrypted_sms_credentials = (
            encrypt_credential(json.dumps(clean, ensure_ascii=False))
            if clean else ""
        )

    class Meta:
        verbose_name = "تنظیمات پلتفرم"
        verbose_name_plural = "تنظیمات پلتفرم"

    def __str__(self):
        return "تنظیمات پلتفرم راستیسی"

    def save(self, *args, **kwargs):
        self.pk = 1
        if not self.step_up_actions:
            self.step_up_actions = dict(DEFAULT_STEP_UP_ACTIONS)
        if not self.enabled_payment_providers:
            self.enabled_payment_providers = [self.default_payment_provider]
        super().save(*args, **kwargs)


class PlatformAuditLogEntry(models.Model):
    """Platform-level audit trail — same shape/intent as
    ``apps.core.models.AuditLogEntry`` (ADR-36), but for events that are not
    owned by exactly one Store (editing global platform configuration, Plan
    definitions, a superuser's own access to Platform Admin, ...). Store-
    scoped superuser actions (trial adjustment on a specific Store, a
    deletion/transfer decision) still use the existing Store-owned
    ``AuditLogEntry`` — this model is additive, not a replacement.
    """

    class ResultStatus(models.TextChoices):
        SUCCESS = "success", "موفق"
        FAILURE = "failure", "ناموفق"

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="انجام‌دهنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="platform_audit_log_entries",
    )
    action_code = models.CharField("کد عملیات", max_length=60, db_index=True)
    object_type = models.CharField("نوع شیء", max_length=60, blank=True, default="")
    object_id = models.CharField("شناسه‌ی شیء", max_length=40, blank=True, default="")
    object_label = models.CharField("برچسبِ شیء", max_length=200, blank=True, default="")
    before_summary = models.TextField("خلاصه‌ی پیش از تغییر", blank=True, default="")
    after_summary = models.TextField("خلاصه‌ی پس از تغییر", blank=True, default="")
    metadata = models.JSONField("متادیتا", default=dict, blank=True)
    result = models.CharField(
        "نتیجه", max_length=10, choices=ResultStatus.choices, default=ResultStatus.SUCCESS,
    )

    class Meta:
        verbose_name = "رخداد حسابرسی پلتفرم"
        verbose_name_plural = "رخدادهای حسابرسی پلتفرم"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action_code", "created_at"], name="idx_pf_audit_action_created"),
        ]

    def __str__(self):
        return f"{self.action_code} @ {self.created_at:%Y-%m-%d %H:%M}"


class PlatformInternalNote(TimeStampedModel):
    """یادداشتِ داخلیِ پشتیبانی/عملیاتِ مدیرِ پلتفرم — دقیقاً یکی از
    ``store``/``about_user`` (نه هر دو، نه هیچ‌کدام). هرگز به مالک/مشتری
    نمایش داده نمی‌شود؛ فقط در پنلِ مدیرِ پلتفرم قابل‌دیدن است."""

    store = models.ForeignKey(
        "stores.Store", verbose_name="فروشگاه", on_delete=models.CASCADE,
        null=True, blank=True, related_name="platform_internal_notes",
    )
    about_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="درباره‌ی کاربر", on_delete=models.CASCADE,
        null=True, blank=True, related_name="platform_internal_notes_about",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="نویسنده", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="authored_platform_internal_notes",
    )
    body = models.TextField("متنِ یادداشت")

    class Meta:
        verbose_name = "یادداشتِ داخلیِ پلتفرم"
        verbose_name_plural = "یادداشت‌هایِ داخلیِ پلتفرم"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(store__isnull=False) & models.Q(about_user__isnull=True))
                    | (models.Q(store__isnull=True) & models.Q(about_user__isnull=False))
                ),
                name="platforminternalnote_exactly_one_subject",
            ),
        ]

    def __str__(self):
        subject = self.store.name if self.store_id else str(self.about_user)
        return f"یادداشت درباره‌ی {subject}"


class ContactMessage(TimeStampedModel):
    """پیامِ ثبت‌شده از فرم «تماس با ما»ی سایت عمومی راستیسی.

    فقط ذخیره می‌کند — بدون صف/ارسال پیامک/ایمیل خودکار. بازبینیِ این پیام‌ها
    بخشی از پنل مدیریت پلتفرم (Section M) است."""

    full_name = models.CharField("نام", max_length=150)
    email = models.EmailField("ایمیل")
    subject = models.CharField("موضوع", max_length=200, blank=True, default="")
    message = models.TextField("پیام")
    is_reviewed = models.BooleanField("بررسی‌شده", default=False)

    class Meta:
        verbose_name = "پیام تماس"
        verbose_name_plural = "پیام‌های تماس"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


class PublicSitePhoto(models.Model):
    """Optional platform-owned photo overrides for the public marketing website.

    Customer storefront media is deliberately stored elsewhere. Removing an
    override makes the public website use its versioned static WebP fallback.
    """

    SLOT_CHOICES = (
        ("stilllife", "تصویر اصلی محصولات دکور و Hero"),
        ("ceramics", "نمای فروشگاه و محصولات سرامیکی"),
        ("ivory", "محصول سرامیکی روشن"),
        ("olive", "محصول سرامیکی زیتونی"),
        ("clay", "محصول سفالی"),
        ("fashion", "گالری پوشاک"),
        ("beauty", "گالری محصولات زیبایی"),
        ("skincare", "محصولات مراقبت پوست"),
        ("bag", "عکس کیف و اکسسوری"),
    )

    slot = models.CharField("جایگاه تصویر", max_length=24, primary_key=True, choices=SLOT_CHOICES)
    image = models.ImageField("تصویر", upload_to="portal/public-photos/")
    alt_text = models.CharField(
        "متن جایگزین تصویر", max_length=180, blank=True, default="",
        help_text="برای دسترس‌پذیری و موتورهای جست‌وجو، تصویر را کوتاه و دقیق توصیف کنید.",
    )
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ویرایشگر",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="public_site_photo_updates",
    )

    class Meta:
        verbose_name = "تصویر سایت عمومی"
        verbose_name_plural = "تصاویر سایت عمومی"

    def __str__(self):
        return self.get_slot_display()
