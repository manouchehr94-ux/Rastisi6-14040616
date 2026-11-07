"""کوپنِ پلتفرم (SaaS) برایِ اشتراک‌های راستیسی.

کاملاً جدا از دامنه‌ی تخفیف/کوپنِ فروشگاهِ مرچنت (``apps.cart``): این کوپن‌ها را
**راستیسی** برایِ خریدِ اشتراکِ مرچنت‌ها تعریف می‌کند. مبالغ مثلِ بقیه‌ی دامنه‌ی
صورتحساب ``Decimal`` با صفر رقمِ اعشار و واحدِ تومان (IRT) هستند.

سیاستِ صریح:
- هر فاکتور حداکثر یک کوپن دارد (ترکیبِ کوپن‌ها پشتیبانی نمی‌شود: ``STACKING_ALLOWED = False``).
- تخفیف فقط به «همین فاکتور/دوره‌ی صورتحساب» اعمال می‌شود؛ تخفیفِ تکرارشونده (recurring) پشتیبانی **نمی‌شود**
  و تمدیدِ بعدی با قیمتِ کامل صادر می‌شود، مگر کوپنِ دیگری واجد شرایط باشد.
- وضعیتِ «منقضی/زمان‌بندی‌شده/تمام‌شده» از زمان و شمارش *محاسبه* می‌شود؛ فقط active/disabled/archived ذخیره می‌شود.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

ZERO = Decimal("0")
STACKING_ALLOWED = False


def normalize_code(value) -> str:
    """کدِ کوپن را case-insensitive و بدونِ فاصله یکسان می‌کند (ارقامِ فارسی/عربی → لاتین، حروفِ بزرگ)."""
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return "".join(str(value or "").translate(table).split()).upper()


def _money(**kwargs):
    return models.DecimalField(max_digits=14, decimal_places=0, default=ZERO, **kwargs)


class PlatformCoupon(TimeStampedModel):
    class Kind(models.TextChoices):
        PERCENT = "percent", "درصدی"
        FIXED = "fixed", "مبلغِ ثابت (تومان)"

    class Status(models.TextChoices):
        ACTIVE = "active", "فعال"
        DISABLED = "disabled", "غیرفعال"
        ARCHIVED = "archived", "بایگانی‌شده"

    # وضعیت‌هایِ محاسبه‌شده (derived)
    STATE_ACTIVE, STATE_INACTIVE, STATE_SCHEDULED, STATE_EXPIRED, STATE_EXHAUSTED = (
        "active", "inactive", "scheduled", "expired", "exhausted",
    )

    name = models.CharField("نامِ داخلی", max_length=120)
    description = models.CharField("توضیح", max_length=300, blank=True, default="")
    #: کدِ نرمال‌شده (حروفِ بزرگ)؛ ``null`` برایِ تخفیفِ خودکارِ بدونِ کد. یکتای سراسری.
    code = models.CharField("کد", max_length=40, null=True, blank=True, unique=True)
    is_automatic = models.BooleanField(
        "خودکار (بدونِ کد)", default=False, help_text="بدونِ نیاز به کد، در صورتِ واجد شرایط بودن خودکار اعمال می‌شود.",
    )

    kind = models.CharField("نوع", max_length=8, choices=Kind.choices, default=Kind.PERCENT)
    percent = models.PositiveSmallIntegerField("درصد", null=True, blank=True)
    fixed_amount = models.DecimalField("مبلغِ ثابت", max_digits=14, decimal_places=0, null=True, blank=True)
    max_discount_amount = models.DecimalField("سقفِ تخفیف (درصدی)", max_digits=14, decimal_places=0, null=True, blank=True)
    min_amount = models.DecimalField("حداقلِ مبلغِ واجد شرایط", max_digits=14, decimal_places=0, null=True, blank=True)

    plans = models.ManyToManyField("subscriptions.Plan", blank=True, related_name="platform_coupons", verbose_name="پلن‌هایِ مجاز")
    #: فهرستِ دوره‌هایِ مجاز (مقدارهایِ ``PlanVersion.BillingInterval``)؛ خالی = همه.
    intervals = models.JSONField("دوره‌هایِ مجاز", blank=True, default=list)
    stores = models.ManyToManyField(
        "stores.Store", blank=True, related_name="platform_coupons_assigned", verbose_name="فروشگاه‌هایِ مجاز",
        help_text="خالی = عمومی؛ در غیرِ این صورت فقط همین فروشگاه‌ها.",
    )

    starts_at = models.DateTimeField("شروع", null=True, blank=True)
    ends_at = models.DateTimeField("پایان", null=True, blank=True)

    max_redemptions = models.PositiveIntegerField("سقفِ کلِ استفاده", null=True, blank=True)
    max_per_store = models.PositiveIntegerField("سقفِ استفاده برایِ هر فروشگاه", null=True, blank=True)

    allow_initial = models.BooleanField("خریدِ اولیه", default=True)
    allow_renewal = models.BooleanField("تمدید", default=False)
    allow_plan_change = models.BooleanField("ارتقا/تغییرِ پلن", default=False)
    first_purchase_only = models.BooleanField(
        "فقط اولین خریدِ پولی", default=False,
        help_text="فقط فروشگاهی که هرگز اشتراکِ پولی را با موفقیت پرداخت نکرده است.",
    )

    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="سازنده",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="آخرین ویرایش",
    )

    class Meta:
        verbose_name = "کوپنِ پلتفرم"
        verbose_name_plural = "کوپن‌هایِ پلتفرم"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(kind="percent", percent__gte=1, percent__lte=100)
                    | models.Q(kind="fixed", fixed_amount__gt=0)
                ),
                name="platformcoupon_kind_value_valid",
            ),
            models.CheckConstraint(
                check=models.Q(code__isnull=False) | models.Q(is_automatic=True),
                name="platformcoupon_code_or_automatic",
            ),
        ]

    def __str__(self):
        return self.code or self.name

    def clean(self):
        super().clean()
        if self.kind == self.Kind.PERCENT and not (self.percent and 1 <= self.percent <= 100):
            raise ValidationError({"percent": "درصد باید بین ۱ تا ۱۰۰ باشد."})
        if self.kind == self.Kind.FIXED and (self.fixed_amount is None or self.fixed_amount <= 0):
            raise ValidationError({"fixed_amount": "مبلغِ ثابت باید بزرگ‌تر از صفر باشد."})
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "پایان باید پس از شروع باشد."})
        if not self.code and not self.is_automatic:
            raise ValidationError({"code": "کوپنِ غیرخودکار باید کد داشته باشد."})
        valid = {value for value, _ in _interval_choices()}
        bad = [i for i in (self.intervals or []) if i not in valid]
        if bad:
            raise ValidationError({"intervals": "دوره‌ی نامعتبر."})

    def save(self, *args, **kwargs):
        self.code = normalize_code(self.code) or None
        if self.kind == self.Kind.FIXED:
            self.percent = None
        else:
            self.fixed_amount = None
        super().save(*args, **kwargs)

    def counted_redemptions(self, *, now=None, store=None) -> int:
        """تعدادِ مصرف‌ها: redeemed + reserved *منقضی‌نشده* (رزروِ منقضی سهمیه را اشغال نمی‌کند)."""
        return counting_queryset(self.redemptions.all(), now=now, store=store).count()

    def derived_state(self, *, now=None) -> str:
        now = now or timezone.now()
        if self.status != self.Status.ACTIVE:
            return self.STATE_INACTIVE
        if self.starts_at and now < self.starts_at:
            return self.STATE_SCHEDULED
        if self.ends_at and now >= self.ends_at:
            return self.STATE_EXPIRED
        if self.max_redemptions is not None and self.counted_redemptions(now=now) >= self.max_redemptions:
            return self.STATE_EXHAUSTED
        return self.STATE_ACTIVE


def _interval_choices():
    from apps.subscriptions.models import PlanVersion

    return [c for c in PlanVersion.BillingInterval.choices if c[0] != "none"]


def counting_queryset(qs, *, now=None, store=None):
    now = now or timezone.now()
    S = PlatformCouponRedemption.Status
    qs = qs.filter(
        models.Q(status=S.REDEEMED) | models.Q(status=S.RESERVED, expires_at__gt=now)
    )
    if store is not None:
        qs = qs.filter(store=store)
    return qs


class PlatformCouponRedemption(TimeStampedModel):
    """رزرو/مصرفِ یک کوپن برایِ یک فاکتور (حداکثر یکی به‌ازایِ هر فاکتور).

    چرخه: reserved → redeemed (پرداختِ فاکتور، دقیقاً یک‌بار) | released (ابطال/انقضا/برداشتن) ؛
    redeemed → reversed (بازپرداختِ کامل در پنجره‌ی مجاز؛ سهمیه آزاد می‌شود)."""

    class Status(models.TextChoices):
        RESERVED = "reserved", "رزروشده"
        REDEEMED = "redeemed", "مصرف‌شده"
        RELEASED = "released", "آزادشده"
        REVERSED = "reversed", "برگشت‌خورده"

    coupon = models.ForeignKey(PlatformCoupon, on_delete=models.PROTECT, related_name="redemptions", verbose_name="کوپن")
    store = models.ForeignKey("stores.Store", on_delete=models.PROTECT, related_name="platform_coupon_redemptions", verbose_name="فروشگاه")
    invoice = models.OneToOneField(
        "billing.SubscriptionInvoice", on_delete=models.PROTECT, related_name="coupon_redemption", verbose_name="فاکتور",
    )
    status = models.CharField("وضعیت", max_length=10, choices=Status.choices, default=Status.RESERVED, db_index=True)

    code_snapshot = models.CharField("کد (اسنپ‌شات)", max_length=40, blank=True, default="")
    original_amount = _money(verbose_name="مبلغِ اصلی")
    discount_amount = _money(verbose_name="تخفیف")
    final_amount = _money(verbose_name="مبلغِ نهایی")
    terms_snapshot = models.JSONField("اسنپ‌شاتِ شرایط", blank=True, default=dict)

    reserved_at = models.DateTimeField("زمانِ رزرو", null=True, blank=True)
    expires_at = models.DateTimeField("انقضایِ رزرو", null=True, blank=True)
    redeemed_at = models.DateTimeField("زمانِ مصرف", null=True, blank=True)
    released_at = models.DateTimeField("زمانِ آزادسازی", null=True, blank=True)
    reversed_at = models.DateTimeField("زمانِ برگشت", null=True, blank=True)
    end_reason = models.CharField("علتِ پایان", max_length=60, blank=True, default="")

    class Meta:
        verbose_name = "مصرفِ کوپنِ پلتفرم"
        verbose_name_plural = "مصرف‌هایِ کوپنِ پلتفرم"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["coupon", "status"], name="idx_pcr_coupon_status"),
            models.Index(fields=["coupon", "store", "status"], name="idx_pcr_coupon_store_status"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(original_amount__gte=0, discount_amount__gte=0, final_amount__gte=0),
                name="pcr_amounts_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.code_snapshot or self.coupon_id} → {self.invoice_id} ({self.status})"


class PlatformCouponAuditEvent(models.Model):
    """دفترِ حسابرسیِ append-only برایِ تعریف/ویرایش/فعال‌سازی و مصرفِ کوپن. هرگز راز/اعتبارنامه ذخیره نمی‌شود."""

    coupon = models.ForeignKey(PlatformCoupon, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField("رخداد", max_length=40, db_index=True)
    store = models.ForeignKey("stores.Store", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    invoice = models.ForeignKey("billing.SubscriptionInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    detail = models.JSONField("جزئیات", blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "رخدادِ حسابرسیِ کوپن"
        verbose_name_plural = "رخدادهایِ حسابرسیِ کوپن"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.coupon_id}:{self.action}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("رخدادِ حسابرسی تغییرناپذیر است.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("رخدادِ حسابرسی حذف‌شدنی نیست.")
