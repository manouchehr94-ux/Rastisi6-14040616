"""موتورِ کوپنِ پلتفرم (SaaS) برایِ فاکتورهایِ اشتراک.

جدا از دامنه‌ی تخفیفِ فروشگاه (``apps.cart``) است و آن را تغییر نمی‌دهد.

اصول:
- **سرور مرجع است**: هیچ مبلغ/تخفیفی از مرورگر پذیرفته نمی‌شود؛ ورودیِ این سرویس‌ها فقط کد، فروشگاه و فاکتور است.
- تخفیف روی ردیفِ «پلن»ِ فاکتور (``discount``) و ``coupon_snapshot`` ثبت می‌شود؛ ویرایشِ بعدیِ کوپن فاکتور را عوض نمی‌کند.
- چرخه‌ی مصرف: ``reserved`` (با انقضا؛ ``PLATFORM_COUPON_RESERVATION_MINUTES``، پیش‌فرض ۳۰) → ``redeemed`` (پرداختِ فاکتور،
  دقیقاً یک‌بار، idempotent) | ``released`` (ابطال/انقضا/برداشتن). تلاشِ ناموفقِ پرداخت سهمیه را نمی‌سوزاند؛ رزروِ
  منقضی در شمارش نمی‌آید. **ظرفیت** زیرِ ``select_for_update`` رویِ ردیفِ کوپن بررسی می‌شود (PostgreSQL-safe).
- سیاستِ بازپرداخت: بازپرداختِ *کامل* تا ``PLATFORM_COUPON_REVERSAL_WINDOW_HOURS`` (پیش‌فرض ۲۴) پس از پرداخت، مصرف را
  ``reversed`` و سهمیه را آزاد می‌کند؛ بازپرداختِ جزئی، یا کامل پس از آن پنجره، و Credit Note مصرف را *مصرف‌شده* نگه می‌دارد.
- ترکیبِ کوپن‌ها (stacking) ممنوع است؛ تخفیفِ تکرارشونده پشتیبانی نمی‌شود (تخفیف فقط به همین فاکتور/دوره).
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    PlatformCoupon,
    PlatformCouponAuditEvent,
    PlatformCouponRedemption,
    PlatformManualPaymentClaim,
    SubscriptionInvoice,
    SubscriptionInvoiceLine,
    SubscriptionPaymentAttempt,
)
from apps.billing.platform_coupon_models import STACKING_ALLOWED, counting_queryset, normalize_code  # noqa: F401
from apps.core.services.audit_service import record_audit_event

ZERO = Decimal("0")
Redemption = PlatformCouponRedemption
Kind = SubscriptionInvoice.Kind

PURPOSE_BY_KIND = {Kind.INITIAL: "initial", Kind.RENEWAL: "renewal", Kind.PLAN_CHANGE: "plan_change"}
PURPOSES = tuple(PURPOSE_BY_KIND.values())

MESSAGES = {
    "invalid_code": "کد تخفیف نامعتبر است.",
    "not_authorized": "کد تخفیف نامعتبر است.",          # عمداً هم‌متن با invalid_code: واگذاریِ خصوصی افشا نمی‌شود
    "inactive": "این کد تخفیف غیرفعال است.",
    "not_started": "زمانِ استفاده از این کد تخفیف هنوز شروع نشده است.",
    "expired": "این کد تخفیف منقضی شده است.",
    "limit_reached": "سقفِ استفاده از این کد تخفیف تکمیل شده است.",
    "store_limit_reached": "شما پیش‌تر از حداکثرِ دفعاتِ مجازِ این کد تخفیف استفاده کرده‌اید.",
    "ineligible_plan": "این کد تخفیف برایِ این پلن قابلِ استفاده نیست.",
    "ineligible_interval": "این کد تخفیف برایِ این دوره‌ی پرداخت قابلِ استفاده نیست.",
    "ineligible_purpose": "این کد تخفیف برایِ این نوعِ خرید قابلِ استفاده نیست.",
    "first_purchase_only": "این کد تخفیف فقط برایِ اولین خریدِ اشتراکِ پولی معتبر است.",
    "min_amount": "مبلغِ خرید به حداقلِ لازم برایِ این کد تخفیف نمی‌رسد.",
    "incompatible": "این تخفیف با تخفیفِ دیگرِ اعمال‌شده روی این فاکتور قابلِ ترکیب نیست.",
    "no_discount": "این کد تخفیف برایِ این خرید مبلغی کم نمی‌کند.",
    "invoice_locked": "این فاکتور دیگر قابلِ تغییر نیست.",
    "payment_in_progress": "برایِ این فاکتور پرداختِ در جریان وجود دارد؛ تا مشخص شدنِ نتیجه تخفیف قابلِ تغییر نیست.",
    "unsupported_invoice": "تخفیف روی این نوعِ فاکتور پشتیبانی نمی‌شود.",
    "reservation_lost": "رزروِ کوپن منقضی شده و ظرفیتِ آن دیگر در دسترس نیست؛ کوپن را بردارید یا دوباره اعمال کنید.",
    "not_zero_value": "این فاکتور با تخفیفِ کامل صفر نشده است و باید پرداخت شود.",
    "forbidden": "اجازه‌ی این عملیات را ندارید.",
    "rate_limited": "تعدادِ تلاش برایِ کدِ تخفیف بیش از حدِ مجاز است؛ یک دقیقه صبر کنید و دوباره تلاش کنید.",
}


class CouponError(Exception):
    """خطای قابلِ‌نمایش (پیامِ فارسی) برایِ کوپنِ پلتفرم."""

    def __init__(self, code, message=None):
        self.code = code
        self.message = message or MESSAGES.get(code, "خطا در اعمالِ کوپن.")
        super().__init__(self.message)


@dataclass(frozen=True)
class Evaluation:
    ok: bool
    code: str = ""
    message: str = ""
    coupon: object = None
    original_amount: Decimal = ZERO
    discount_amount: Decimal = ZERO
    final_amount: Decimal = ZERO
    automatic: bool = False

    @property
    def is_full_discount(self) -> bool:
        return self.ok and self.final_amount == ZERO and self.original_amount > ZERO


def _fail(code, original=ZERO):
    return Evaluation(ok=False, code=code, message=MESSAGES[code], original_amount=original, final_amount=original)


# ----------------------------------------------------------------------------------------------- settings / math
def check_attempt_rate(user, store):
    """سقفِ تلاشِ کد (اعمال/پیشنمایش) برایِ هر کاربر+فروشگاه در دقیقه؛ جلوگیری از حدسِ کدها. پیامهایِ خطایِ متمایز
    (غیرفعال/منقضی/تکمیل) خواستهی مالک است، پس مهارِ نرخ جایگزینِ پیامِ یکسان است. backend در دسترس نباشد ⇒ بسته (fail-closed)."""
    from apps.core.services.rate_limit import RateLimitExceeded, RateLimitUnavailable, enforce_rate_limit

    limit = int(getattr(settings, "PLATFORM_COUPON_ATTEMPTS_PER_MINUTE", 10))
    try:
        enforce_rate_limit("platform.coupon.attempt", f"{getattr(store, 'pk', '')}:{getattr(user, 'pk', '')}",
                           max_attempts=limit, window_seconds=60)
    except (RateLimitExceeded, RateLimitUnavailable) as exc:
        raise CouponError("rate_limited") from exc


def reservation_lifetime() -> timedelta:
    return timedelta(minutes=int(getattr(settings, "PLATFORM_COUPON_RESERVATION_MINUTES", 30)))


def reversal_window() -> timedelta:
    return timedelta(hours=int(getattr(settings, "PLATFORM_COUPON_REVERSAL_WINDOW_HOURS", 24)))


def calculate_discount(coupon, amount) -> Decimal:
    """تخفیفِ این کوپن برایِ ``amount`` (تومانِ صحیح). درصدی: رو به پایین (هرگز بیش از حق)، با سقف؛
    ثابت: حداکثر تا مبلغ. همیشه ``0 <= discount <= amount`` (فاکتورِ منفی ممکن نیست)."""
    amount = max(Decimal(amount), ZERO)
    if coupon.kind == PlatformCoupon.Kind.PERCENT:
        raw = (amount * Decimal(coupon.percent or 0) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_DOWN)
        if coupon.max_discount_amount is not None:
            raw = min(raw, Decimal(coupon.max_discount_amount))
    else:
        raw = Decimal(coupon.fixed_amount or 0)
    return min(max(raw, ZERO), amount)


# ----------------------------------------------------------------------------------------------- eligibility
def has_paid_subscription_history(store, *, exclude_invoice=None) -> bool:
    """منبعِ حقیقتِ «اولین خرید»: فاکتورِ اشتراکِ *پرداخت‌شده* با مبلغِ پرداخت‌شده > ۰ (حتی اگر بعداً بازپرداخت شده).
    پرداختِ ناموفق/رزرو/فاکتورِ صفر (تخفیفِ کامل) حساب نمی‌شود."""
    qs = SubscriptionInvoice.objects.filter(
        store=store, amount_paid__gt=0,
        status__in=(
            SubscriptionInvoice.Status.PAID, SubscriptionInvoice.Status.REFUNDED,
            SubscriptionInvoice.Status.PARTIALLY_REFUNDED,
        ),
    )
    if exclude_invoice is not None:
        qs = qs.exclude(pk=exclude_invoice.pk)
    return qs.exists()


def _evaluate_coupon(coupon, store, plan_version, interval, purpose, amount, *, now, exclude_invoice=None, automatic=False):
    amount = Decimal(amount)
    if coupon.stores.exists() and not coupon.stores.filter(pk=store.pk).exists():
        return _fail("not_authorized", amount)
    if coupon.status != PlatformCoupon.Status.ACTIVE:
        return _fail("inactive", amount)
    if coupon.starts_at and now < coupon.starts_at:
        return _fail("not_started", amount)
    if coupon.ends_at and now >= coupon.ends_at:
        return _fail("expired", amount)
    own = Redemption.objects.filter(invoice=exclude_invoice).values_list("pk", flat=True) if exclude_invoice is not None else []
    base = counting_queryset(coupon.redemptions.all(), now=now).exclude(pk__in=list(own))
    if coupon.max_redemptions is not None and base.count() >= coupon.max_redemptions:
        return _fail("limit_reached", amount)
    if coupon.max_per_store is not None and base.filter(store=store).count() >= coupon.max_per_store:
        return _fail("store_limit_reached", amount)
    allowed = {"initial": coupon.allow_initial, "renewal": coupon.allow_renewal, "plan_change": coupon.allow_plan_change}
    if not allowed.get(purpose, False):
        return _fail("ineligible_purpose", amount)
    plan_ids = list(coupon.plans.values_list("pk", flat=True))
    if plan_ids and plan_version.plan_id not in plan_ids:
        return _fail("ineligible_plan", amount)
    if coupon.intervals and interval not in coupon.intervals:
        return _fail("ineligible_interval", amount)
    if not plan_version.offers_interval(interval):
        return _fail("ineligible_interval", amount)
    if coupon.first_purchase_only and has_paid_subscription_history(store, exclude_invoice=exclude_invoice):
        return _fail("first_purchase_only", amount)
    if coupon.min_amount is not None and amount < coupon.min_amount:
        return _fail("min_amount", amount)
    discount = calculate_discount(coupon, amount)
    if discount <= ZERO:
        return _fail("no_discount", amount)
    return Evaluation(
        ok=True, coupon=coupon, original_amount=amount, discount_amount=discount,
        final_amount=amount - discount, automatic=automatic,
    )


def evaluate(store, *, plan_version, interval, purpose, code="", now=None, exclude_invoice=None) -> Evaluation:
    """بررسی و محاسبه‌ی کد (یا بهترین تخفیفِ خودکار اگر ``code`` خالی باشد) برایِ پیش‌نمایش؛ بدونِ هیچ نوشتن.
    قیمت همیشه از ``plan_version.price_for(interval)`` می‌آید، نه از مرورگر."""
    now = now or timezone.now()
    interval = interval or plan_version.billing_interval
    if purpose not in PURPOSES:
        return _fail("ineligible_purpose")
    if not plan_version.offers_interval(interval):
        return _fail("ineligible_interval")
    amount = Decimal(plan_version.price_for(interval))
    normalized = normalize_code(code)
    if not normalized:
        return best_automatic(store, plan_version=plan_version, interval=interval, purpose=purpose, amount=amount,
                              now=now, exclude_invoice=exclude_invoice)
    coupon = PlatformCoupon.objects.filter(code=normalized).first()
    if coupon is None:
        return _fail("invalid_code", amount)
    return _evaluate_coupon(coupon, store, plan_version, interval, purpose, amount, now=now, exclude_invoice=exclude_invoice)


def best_automatic(store, *, plan_version, interval, purpose, amount=None, now=None, exclude_invoice=None) -> Evaluation:
    """بیشترین تخفیفِ خودکارِ واجد شرایط (تساوی: کوپنِ با شناسه‌ی کمتر). نبودنِ کوپن ⇒ ``invalid_code`` (بی‌صدا)."""
    now = now or timezone.now()
    amount = Decimal(plan_version.price_for(interval)) if amount is None else Decimal(amount)
    best = None
    candidates = PlatformCoupon.objects.filter(is_automatic=True, status=PlatformCoupon.Status.ACTIVE).order_by("pk")
    for coupon in candidates:
        result = _evaluate_coupon(coupon, store, plan_version, interval, purpose, amount, now=now,
                                  exclude_invoice=exclude_invoice, automatic=True)
        if result.ok and (best is None or result.discount_amount > best.discount_amount):
            best = result
    return best or _fail("invalid_code", amount)


# ----------------------------------------------------------------------------------------------- audit
def _coupon_event(coupon, action, *, actor=None, store=None, invoice=None, detail=None):
    return PlatformCouponAuditEvent.objects.create(
        coupon=coupon, actor=actor if getattr(actor, "pk", None) else None, action=action,
        store=store, invoice=invoice, detail=detail or {},
    )


def _terms_snapshot(coupon) -> dict:
    return {
        "coupon_id": coupon.pk, "name": coupon.name, "kind": coupon.kind, "percent": coupon.percent,
        "fixed_amount": str(coupon.fixed_amount) if coupon.fixed_amount is not None else None,
        "max_discount_amount": str(coupon.max_discount_amount) if coupon.max_discount_amount is not None else None,
        "min_amount": str(coupon.min_amount) if coupon.min_amount is not None else None,
        "automatic": coupon.is_automatic,
    }


# ----------------------------------------------------------------------------------------------- invoice helpers
def _plan_line(invoice):
    """تنها ردیفِ «پلن» (فاکتورِ دارایِ ردیفِ تعدیل/تناسبی/مالیات پشتیبانی نمی‌شود: عملیاتِ ناامن اختراع نمی‌شود)."""
    lines = list(invoice.lines.all())
    if len(lines) != 1 or lines[0].line_type != SubscriptionInvoiceLine.LineType.PLAN:
        raise CouponError("unsupported_invoice")
    return lines[0]


def _has_inflight_payment(invoice) -> bool:
    A = SubscriptionPaymentAttempt.Status
    if invoice.payment_attempts.filter(status__in=(A.CREATED, A.PENDING, A.REQUIRES_ACTION, A.SUCCEEDED)).exists():
        return True
    return invoice.manual_claims.filter(status=PlatformManualPaymentClaim.Status.PENDING_REVIEW).exists()


def _lock_mutable_invoice(invoice):
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    S = SubscriptionInvoice.Status
    if locked.status not in (S.DRAFT, S.OPEN, S.PAST_DUE) or locked.amount_paid > ZERO:
        raise CouponError("invoice_locked")
    if locked.kind not in PURPOSE_BY_KIND:
        raise CouponError("unsupported_invoice")
    if _has_inflight_payment(locked):
        raise CouponError("payment_in_progress")
    return locked


def _write_discount(invoice, line, discount, snapshot):
    from apps.billing.services import invoice_service

    line.discount = discount
    line.total = line.subtotal - discount + line.tax
    meta = dict(line.metadata or {})
    if snapshot:
        meta["coupon"] = {"code": snapshot.get("code"), "coupon_id": snapshot.get("coupon_id")}
    else:
        meta.pop("coupon", None)
    line.metadata = meta
    line.save(update_fields=["discount", "total", "metadata", "updated_at"])
    invoice.coupon_snapshot = snapshot
    invoice_service.recompute_totals(invoice)
    invoice.save(update_fields=[
        "subtotal", "discount_total", "tax_total", "grand_total", "amount_due", "coupon_snapshot", "updated_at",
    ])


def _invoice_context(invoice):
    from apps.billing.services import invoice_service

    return invoice_service.invoice_billing_interval(invoice), purpose_for(invoice.store, invoice.kind, subscription=invoice.subscription, exclude_invoice=invoice)


def purpose_for(store, kind, *, subscription=None, exclude_invoice=None) -> str:
    """هدفِ خرید برایِ اهلیتِ کوپن. اولین خریدِ پولیِ پس از تریال در این سیستم یک فاکتورِ ``plan_change`` است (ارتقا از
    پلنِ آزمایشیِ رایگان؛ ``portal.views._start_purchase``)، ولی برایِ کوپن «خریدِ اولیه» است؛ وگرنه کوپنِ پیشفرض
    (``allow_initial``) هرگز روی اولین خریدِ پس از تریال کار نمیکرد. شرط: اشتراک pending/trialing است (یا تریال داشته)
    و فروشگاه هنوز پرداختِ واقعی نداشته. ارتقایِ معمولِ مشتریِ پولی همچنان ``plan_change`` میماند."""
    if kind != Kind.PLAN_CHANGE:
        return PURPOSE_BY_KIND[kind]
    from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
    from apps.subscriptions.services import entitlement_service

    from apps.subscriptions.services import trial_service

    sub = subscription or entitlement_service.get_current_subscription(store)
    if sub is None or has_paid_subscription_history(store, exclude_invoice=exclude_invoice):
        return PURPOSE_BY_KIND[kind]
    # The internal Trial plan itself is the authoritative marker: a Trial the platform disabled is provisioned on that plan
    # but never started (status suspended, no TRIAL_STARTED event), and its first paid purchase is still an initial purchase.
    on_trial_plan = trial_service.is_trial_plan(getattr(getattr(sub, "plan_version", None), "plan", None))
    was_trial = on_trial_plan or sub.status in (StoreSubscription.Status.PENDING, StoreSubscription.Status.TRIALING) or SubscriptionEvent.objects.filter(
        subscription=sub, event_type=SubscriptionEvent.EventType.TRIAL_STARTED).exists()
    return "initial" if was_trial else PURPOSE_BY_KIND[kind]


# ----------------------------------------------------------------------------------------------- apply / remove
@transaction.atomic
def apply_coupon_to_invoice(invoice, *, code="", actor=None, now=None, automatic=False):
    """کوپن را روی فاکتورِ پرداخت‌نشده (draft/open/past_due، بدونِ پرداختِ در جریان) اعمال و ظرفیت را *رزرو* می‌کند.

    idempotent: همان کوپن دوباره ⇒ همان رزرو (فقط انقضا تمدید می‌شود)، تخفیفِ تکراری نمی‌افتد. کدِ صریح جایگزینِ
    تخفیفِ خودکار می‌شود؛ جایگزینیِ کوپنِ دستیِ دیگر ⇒ ``incompatible`` (ابتدا باید برداشته شود)."""
    now = now or timezone.now()
    locked = _lock_mutable_invoice(invoice)
    interval, purpose = _invoice_context(locked)
    line = _plan_line(locked)
    existing = Redemption.objects.select_for_update().filter(invoice=locked).first()
    active_existing = existing is not None and existing.status in (Redemption.Status.RESERVED, Redemption.Status.REDEEMED)

    if automatic:
        evaluation = best_automatic(locked.store, plan_version=locked.plan_version, interval=interval, purpose=purpose,
                                    amount=line.subtotal, now=now, exclude_invoice=locked)
        if not evaluation.ok:
            raise CouponError(evaluation.code)
    else:
        normalized = normalize_code(code)
        coupon = PlatformCoupon.objects.filter(code=normalized).first() if normalized else None
        if coupon is None:
            raise CouponError("invalid_code")
        evaluation = None

    # قفلِ ردیفِ کوپن پیش از شمارشِ ظرفیت: دو مرچنتِ رقیب برایِ آخرین سهمیه سریال می‌شوند.
    target = evaluation.coupon if evaluation else coupon
    target = PlatformCoupon.objects.select_for_update().get(pk=target.pk)
    if active_existing:
        if existing.coupon_id == target.pk:
            if existing.status == Redemption.Status.RESERVED:
                existing.expires_at = now + reservation_lifetime()
                existing.save(update_fields=["expires_at", "updated_at"])
            return existing
        if existing.coupon.is_automatic and not automatic:
            _release(existing, "replaced", actor=actor, now=now)
            _write_discount(locked, line, ZERO, {})
            existing = Redemption.objects.get(pk=existing.pk)
        else:
            raise CouponError("incompatible")
    evaluation = _evaluate_coupon(
        target, locked.store, locked.plan_version, interval, purpose, line.subtotal,
        now=now, exclude_invoice=locked, automatic=automatic,
    )
    if not evaluation.ok:
        raise CouponError(evaluation.code)

    snapshot = {
        **_terms_snapshot(target), "code": target.code or "", "original_amount": str(evaluation.original_amount),
        "discount_amount": str(evaluation.discount_amount), "final_amount": str(evaluation.final_amount),
        "billing_interval": interval, "purpose": purpose, "currency": locked.currency,
        "applied_at": now.isoformat(), "applies_to": "this_invoice_only",
    }
    fields = dict(
        coupon=target, store=locked.store, status=Redemption.Status.RESERVED, code_snapshot=target.code or "",
        original_amount=evaluation.original_amount, discount_amount=evaluation.discount_amount,
        final_amount=evaluation.final_amount, terms_snapshot=snapshot, reserved_at=now,
        expires_at=now + reservation_lifetime(), redeemed_at=None, released_at=None, reversed_at=None, end_reason="",
    )
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        existing.save()
        redemption = existing
    else:
        redemption = Redemption.objects.create(invoice=locked, **fields)
    _write_discount(locked, line, evaluation.discount_amount, snapshot)
    _coupon_event(target, "reserved", actor=actor, store=locked.store, invoice=locked, detail={
        "invoice": locked.number, "discount": str(evaluation.discount_amount), "automatic": automatic,
    })
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.platform_coupon_applied",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        after={"coupon": target.code or target.name, "discount": str(evaluation.discount_amount),
               "grand_total": str(locked.grand_total)},
    )
    return redemption


def apply_automatic_to_invoice(invoice, *, actor=None, now=None):
    """تخفیفِ خودکار را (در صورتِ وجود) روی فاکتور اعمال می‌کند؛ هرگز استثنا نمی‌دهد و اگر کوپنی نباشد ``None``."""
    if not PlatformCoupon.objects.filter(is_automatic=True, status=PlatformCoupon.Status.ACTIVE).exists():
        return None
    try:
        return apply_coupon_to_invoice(invoice, actor=actor, now=now, automatic=True)
    except CouponError:
        return None


@transaction.atomic
def remove_coupon_from_invoice(invoice, *, actor=None, now=None):
    """کوپن را پیش از پرداخت از فاکتور برمی‌دارد، مبلغ به قیمتِ کامل برمی‌گردد و رزرو آزاد می‌شود. idempotent."""
    now = now or timezone.now()
    locked = _lock_mutable_invoice(invoice)
    redemption = Redemption.objects.select_for_update().filter(invoice=locked).first()
    if redemption is None or not locked.coupon_snapshot:
        return None
    if redemption.status in (Redemption.Status.REDEEMED, Redemption.Status.REVERSED):
        raise CouponError("invoice_locked")
    line = _plan_line(locked)
    _write_discount(locked, line, ZERO, {})
    if redemption.status == Redemption.Status.RESERVED:
        _release(redemption, "removed", actor=actor, now=now)
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.platform_coupon_removed",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        after={"grand_total": str(locked.grand_total)},
    )
    return Redemption.objects.get(pk=redemption.pk)


# ----------------------------------------------------------------------------------------------- lifecycle
def _release(redemption, reason, *, actor=None, now=None):
    now = now or timezone.now()
    redemption.status = Redemption.Status.RELEASED
    redemption.released_at = now
    redemption.end_reason = reason
    redemption.save(update_fields=["status", "released_at", "end_reason", "updated_at"])
    _coupon_event(redemption.coupon, "released", actor=actor, store=redemption.store, invoice=redemption.invoice,
                  detail={"reason": reason})


@transaction.atomic
def ensure_reservation_active(invoice, *, now=None):
    """پیش از هر تلاشِ پرداخت: رزروِ فعال تمدید می‌شود (Retry تخفیفِ تکراری نمی‌سازد)؛ رزروِ منقضی/آزادشده فقط در صورتِ
    باقی‌ماندنِ ظرفیت و اعتبارِ کوپن (زیرِ قفل) دوباره رزرو می‌شود، وگرنه ``CouponError(reservation_lost)``.
    فاکتورِ بدونِ کوپن یا با مصرفِ نهایی ⇒ بدونِ اثر."""
    now = now or timezone.now()
    redemption = Redemption.objects.select_for_update().filter(invoice_id=invoice.pk).first()
    if redemption is None or redemption.status in (Redemption.Status.REDEEMED, Redemption.Status.REVERSED):
        return redemption
    if redemption.status == Redemption.Status.RESERVED and redemption.expires_at and redemption.expires_at > now:
        redemption.expires_at = now + reservation_lifetime()
        redemption.save(update_fields=["expires_at", "updated_at"])
        return redemption
    coupon = PlatformCoupon.objects.select_for_update().get(pk=redemption.coupon_id)
    snap = redemption.terms_snapshot or {}
    inv = SubscriptionInvoice.objects.get(pk=invoice.pk)
    interval, purpose = _invoice_context(inv)
    result = _evaluate_coupon(coupon, inv.store, inv.plan_version, interval, purpose, redemption.original_amount,
                              now=now, exclude_invoice=inv, automatic=bool(snap.get("automatic")))
    if not result.ok or result.discount_amount != redemption.discount_amount:
        raise CouponError("reservation_lost")
    redemption.status = Redemption.Status.RESERVED
    redemption.reserved_at = now
    redemption.expires_at = now + reservation_lifetime()
    redemption.released_at = None
    redemption.end_reason = ""
    redemption.save()
    _coupon_event(coupon, "reservation_renewed", store=inv.store, invoice=inv, detail={"invoice": inv.number})
    return redemption


def redeem_for_paid_invoice(invoice, *, actor=None, now=None):
    """فاکتور پرداخت شد ⇒ مصرفِ کوپن *دقیقاً یک‌بار* قطعی می‌شود. idempotent برایِ callbackِ تکراری. اگر رزرو
    در این فاصله منقضی/آزاد شده باشد، چون پول با تخفیفِ ثبت‌شده دریافت شده، همان تخفیف محترم است و مصرف ثبت می‌شود."""
    now = now or timezone.now()
    redemption = Redemption.objects.select_for_update().filter(invoice_id=invoice.pk).first()
    if redemption is None or redemption.status in (Redemption.Status.REDEEMED, Redemption.Status.REVERSED):
        return redemption
    was = redemption.status
    over = _over_capacity(redemption, now)
    redemption.status = Redemption.Status.REDEEMED
    redemption.redeemed_at = now
    redemption.released_at = None
    redemption.end_reason = ""
    redemption.save(update_fields=["status", "redeemed_at", "released_at", "end_reason", "updated_at"])
    _coupon_event(redemption.coupon, "redeemed", actor=actor, store=redemption.store, invoice=redemption.invoice, detail={
        "invoice": invoice.number, "discount": str(redemption.discount_amount), "from": was,
    })
    if over:
        # سیاستِ صریح: پول با تخفیفِ ثبتشده دریافت شده، پس تخفیف محترم است (رد نمیشود)؛ ولی تجاوز از سقف ثبت و ردگیری میشود.
        _coupon_event(redemption.coupon, "over_redeemed", store=redemption.store, invoice=redemption.invoice, detail={
            "invoice": invoice.number, "from": was, "scope": over,
            "max_redemptions": redemption.coupon.max_redemptions, "max_per_store": redemption.coupon.max_per_store,
        })
        record_audit_event(
            store=redemption.store, actor=actor, action_code="billing.platform_coupon_over_redeemed",
            object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
            after={"coupon": redemption.code_snapshot, "scope": over, "from": was},
        )
    return redemption


def _over_capacity(redemption, now) -> str:
    """پیش از مصرفِ قطعی: آیا با احتسابِ مصرف/رزروهایِ *دیگر* سقفِ کوپن پر شده است؟ ('' | 'total' | 'store')."""
    coupon = PlatformCoupon.objects.get(pk=redemption.coupon_id)
    others = counting_queryset(coupon.redemptions.exclude(pk=redemption.pk), now=now)
    if coupon.max_redemptions is not None and others.count() >= coupon.max_redemptions:
        return "total"
    if coupon.max_per_store is not None and others.filter(store_id=redemption.store_id).count() >= coupon.max_per_store:
        return "store"
    return ""


@transaction.atomic
def hold_reservation_for_claim(invoice, *, until, now=None):
    """ادعایِ کارتبهکارت در انتظارِ بررسی: رزروِ کوپن (با بازرزروِ ایمن در صورتِ انقضا) تا ``until`` نگه داشته میشود تا
    سهمیه در فاصلهی بررسی فروخته نشود. رزروِ ازدسترفته ⇒ ``CouponError(reservation_lost)``. بدونِ کوپن ⇒ بدونِ اثر."""
    now = now or timezone.now()
    redemption = ensure_reservation_active(invoice, now=now)
    if redemption is not None and redemption.status == Redemption.Status.RESERVED and redemption.expires_at < until:
        redemption.expires_at = until
        redemption.save(update_fields=["expires_at", "updated_at"])
    return redemption


@transaction.atomic
def restore_reservation_lifetime(invoice, *, now=None):
    """ادعا بسته شد (ردّ/لغو/انقضا): رزروِ نگهداشتهشده به عمرِ عادی برمیگردد تا سهمیه بیش از لازم قفل نماند."""
    now = now or timezone.now()
    redemption = Redemption.objects.select_for_update().filter(invoice_id=invoice.pk, status=Redemption.Status.RESERVED).first()
    if redemption is not None and redemption.expires_at and redemption.expires_at > now + reservation_lifetime():
        redemption.expires_at = now + reservation_lifetime()
        redemption.save(update_fields=["expires_at", "updated_at"])
    return redemption


@transaction.atomic
def release_for_invoice(invoice, reason, *, actor=None, now=None):
    """رزروِ باز را آزاد می‌کند (ابطالِ فاکتور). مصرفِ قطعی را دست نمی‌زند."""
    redemption = Redemption.objects.select_for_update().filter(invoice_id=invoice.pk, status=Redemption.Status.RESERVED).first()
    if redemption is not None:
        _release(redemption, reason, actor=actor, now=now)
    return redemption


def release_expired_reservations(*, now=None) -> int:
    """رزروهایِ منقضی را آزاد می‌کند (جاروب). شمارش به این جاروب وابسته نیست (رزروِ منقضی خودبه‌خود حساب نمی‌شود)."""
    now = now or timezone.now()
    count = 0
    for pk in list(Redemption.objects.filter(status=Redemption.Status.RESERVED, expires_at__lte=now).values_list("pk", flat=True)):
        with transaction.atomic():
            row = Redemption.objects.select_for_update().filter(pk=pk, status=Redemption.Status.RESERVED, expires_at__lte=now).first()
            if row is not None:
                _release(row, "expired", now=now)
                count += 1
    return count


def reverse_for_refund(invoice, *, now=None):
    """هنگامِ بازپرداختِ *کامل*: درونِ پنجره‌ی مجاز مصرف ``reversed`` و سهمیه آزاد می‌شود؛ وگرنه مصرف‌شده می‌ماند."""
    now = now or timezone.now()
    redemption = Redemption.objects.select_for_update().filter(invoice_id=invoice.pk, status=Redemption.Status.REDEEMED).first()
    if redemption is None:
        return None
    within = bool(invoice.paid_at) and now - invoice.paid_at <= reversal_window()
    if not within:
        _coupon_event(redemption.coupon, "refund_kept_consumed", store=redemption.store, invoice=redemption.invoice,
                      detail={"reason": "outside_reversal_window"})
        return None
    redemption.status = Redemption.Status.REVERSED
    redemption.reversed_at = now
    redemption.end_reason = "full_refund"
    redemption.save(update_fields=["status", "reversed_at", "end_reason", "updated_at"])
    _coupon_event(redemption.coupon, "reversed", store=redemption.store, invoice=redemption.invoice,
                  detail={"reason": "full_refund"})
    return redemption


# ----------------------------------------------------------------------------------------------- zero-value settlement
def _can_settle(actor, store) -> bool:
    if actor is None or not getattr(actor, "is_authenticated", False) or not actor.is_active:
        return False
    if actor.is_staff and actor.is_superuser:
        return True
    from apps.stores.authorization import BILLING_PAYMENT_MANAGE, user_has_permission

    return user_has_permission(actor, store, BILLING_PAYMENT_MANAGE)


@transaction.atomic
def settle_zero_value_invoice(invoice, *, actor, now=None):
    """تسویه‌ی فاکتورِ **کاملاً تخفیف‌خورده** (قابل‌پرداخت = ۰) بدونِ هیچ تماسی با درگاه.

    فقط ادمینِ پلتفرم یا کاربری با مجوزِ مدیریتِ پرداخت در همان فروشگاه. از مسیرِ کانونیکِ
    ``confirmation_service.settle_zero_due_invoice`` می‌گذرد (تلاشِ ``manual`` با مبلغِ ۰، حسابرسی، فعال‌سازی/تمدیدِ
    یک‌باره)؛ هرگز callbackِ درگاه جعل نمی‌شود. idempotent."""
    from apps.billing.services import confirmation_service

    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if not _can_settle(actor, locked.store):
        raise CouponError("forbidden")
    if locked.status == SubscriptionInvoice.Status.PAID:
        return locked
    redemption = Redemption.objects.filter(invoice=locked).first()
    if (redemption is None or not locked.coupon_snapshot or locked.grand_total != ZERO or locked.amount_due != ZERO
            or locked.discount_total != locked.subtotal or locked.subtotal <= ZERO):
        raise CouponError("not_zero_value")
    ensure_reservation_active(locked, now=now)
    try:
        settled = confirmation_service.settle_zero_due_invoice(locked, actor=actor, now=now)
    except confirmation_service.ConfirmationError as exc:
        raise CouponError("not_zero_value", str(exc)) from exc
    _coupon_event(redemption.coupon, "zero_value_settled", actor=actor, store=locked.store, invoice=locked,
                  detail={"invoice": locked.number})
    return settled


# ----------------------------------------------------------------------------------------------- admin (platform staff)
EDITABLE_FIELDS = (
    "name", "description", "code", "is_automatic", "kind", "percent", "fixed_amount", "max_discount_amount",
    "min_amount", "intervals", "starts_at", "ends_at", "max_redemptions", "max_per_store", "allow_initial",
    "allow_renewal", "allow_plan_change", "first_purchase_only",
)


def _require_platform_staff(actor):
    if not (actor is not None and getattr(actor, "is_authenticated", False) and actor.is_active
            and actor.is_staff and actor.is_superuser):
        raise CouponError("forbidden")


def _jsonable(value):
    return str(value) if isinstance(value, (Decimal,)) or hasattr(value, "isoformat") else value


@transaction.atomic
def create_coupon(*, actor, plans=(), stores=(), **fields) -> PlatformCoupon:
    """فقط ادمینِ پلتفرم. اعتبارسنجیِ مدل (``full_clean``) اجرا می‌شود."""
    _require_platform_staff(actor)
    unknown = set(fields) - set(EDITABLE_FIELDS)
    if unknown:
        raise CouponError("forbidden", f"فیلدِ نامعتبر: {', '.join(sorted(unknown))}")
    coupon = PlatformCoupon(created_by=actor, updated_by=actor, **fields)
    coupon.code = normalize_code(coupon.code) or None
    coupon.full_clean(exclude=["created_by", "updated_by"])
    coupon.save()
    coupon.plans.set(list(plans))
    coupon.stores.set(list(stores))
    _coupon_event(coupon, "created", actor=actor, detail={
        "code": coupon.code or "", "kind": coupon.kind, "plans": [p.pk for p in plans], "stores": [s.pk for s in stores],
    })
    return coupon


@transaction.atomic
def update_coupon(coupon, *, actor, plans=None, stores=None, **changes) -> PlatformCoupon:
    """ویرایشِ تعریف (فقط ادمینِ پلتفرم). فاکتورهایِ صادرشده/رزروها تغییر نمی‌کنند (اسنپ‌شات)."""
    _require_platform_staff(actor)
    coupon = PlatformCoupon.objects.select_for_update().get(pk=coupon.pk)
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise CouponError("forbidden", f"فیلدِ نامعتبر: {', '.join(sorted(unknown))}")
    diff = {}
    for key, value in changes.items():
        old = getattr(coupon, key)
        if key == "code":
            value = normalize_code(value) or None
        if old != value:
            diff[key] = {"from": _jsonable(old), "to": _jsonable(value)}
            setattr(coupon, key, value)
    coupon.updated_by = actor
    coupon.full_clean(exclude=["created_by", "updated_by"])
    coupon.save()
    if plans is not None:
        old_ids = sorted(coupon.plans.values_list("pk", flat=True))
        coupon.plans.set(list(plans))
        diff["plans"] = {"from": old_ids, "to": sorted(p.pk for p in plans)}
    if stores is not None:
        old_ids = sorted(coupon.stores.values_list("pk", flat=True))
        coupon.stores.set(list(stores))
        diff["stores"] = {"from": old_ids, "to": sorted(s.pk for s in stores)}
    if diff:
        _coupon_event(coupon, "updated", actor=actor, detail={"changes": diff})
    return coupon


@transaction.atomic
def set_coupon_status(coupon, status, *, actor) -> PlatformCoupon:
    _require_platform_staff(actor)
    if status not in PlatformCoupon.Status.values:
        raise CouponError("forbidden", "وضعیتِ نامعتبر.")
    coupon = PlatformCoupon.objects.select_for_update().get(pk=coupon.pk)
    if coupon.status != status:
        old, coupon.status, coupon.updated_by = coupon.status, status, actor
        coupon.save(update_fields=["status", "updated_by", "updated_at"])
        _coupon_event(coupon, {"active": "enabled", "disabled": "disabled", "archived": "archived"}[status],
                      actor=actor, detail={"from": old, "to": status})
    return coupon


def redemptions_for(coupon):
    """فاکتورهایی که از این کوپن استفاده کرده‌اند (برایِ گزارشِ ادمین)."""
    return coupon.redemptions.select_related("invoice", "store").order_by("-created_at")
