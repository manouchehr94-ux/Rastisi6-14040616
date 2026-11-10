"""تأییدِ تراکنشیِ پرداختِ اشتراک (ADR-77).

تنها مسیرِ مجاز برایِ «پرداخت انجام شد» — نه در View. قفلِ تلاش و فاکتور،
بررسیِ مبلغ/ارز/Provider، علامتِ یک‌بارِ موفقیت، اعمالِ یک‌بارِ پرداخت، پرداخت‌
شدنِ فاکتور، فعال‌سازی/تمدیدِ اشتراک، ثبتِ SubscriptionEvent و Audit — همه
idempotent در برابرِ تحویلِ تکراریِ Webhook."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import invoice_service
from apps.billing.services.period_utils import next_period_end
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc

ZERO = Decimal("0")


class ConfirmationError(Exception):
    """خطای قابل‌نمایش هنگام تأییدِ پرداخت (مبلغ/ارز/Provider نامطابق)."""


#: Failure codes of an attempt whose money WAS confirmed by the gateway but could not be applied. The attempt becomes
#: ``REQUIRES_ACTION`` (listed in the finance reconciliation queue, resolvable by refund or by a documented allocation);
#: the invoice and subscription are left untouched and NO entitlement is granted. A confirmed payment is never dropped.
PARKED_FAILURE_CODES = frozenset({"fulfilment_blocked", "late_payment_void", "late_payment_uncollectible", "stale_decision"})

_PARK_MESSAGES = {
    "late_payment_void": "پرداخت پس از باطل‌شدنِ فاکتور رسید؛ هیچ اثری اعمال نشد و برای رسیدگیِ مالی (بازپرداخت/تخصیص) ثبت شد.",
    "late_payment_uncollectible": "پرداخت پس از وصول‌ناشدنی‌شدنِ فاکتور رسید؛ هیچ اثری اعمال نشد و برای رسیدگیِ مالی ثبت شد.",
    "stale_decision": "پرداخت برای تصمیمِ تغییرِ پلنی رسید که دیگر معتبر نیست (اشتراک از زمانِ ساختِ فاکتور تغییر کرده)؛ برای رسیدگیِ مالی ثبت شد.",
    "fulfilment_blocked": "پرداخت تأیید شد امّا اعمالِ آن روی اشتراک ممکن نبود (اشتراک پایان‌یافته یا تغییر کرده)؛ برای رسیدگیِ مالی ثبت شد.",
}


def _park_reason(invoice):
    """Why a confirmed payment must NOT be applied to ``invoice`` (or ``None`` to apply it)."""
    S = SubscriptionInvoice.Status
    if invoice.status == S.VOID:
        return "late_payment_void"
    if invoice.status == S.UNCOLLECTIBLE:
        return "late_payment_uncollectible"
    subscription = StoreSubscription.objects.filter(pk=invoice.subscription_id).first()
    if subscription is None or subscription.status in StoreSubscription.TERMINAL_STATUSES:
        return "fulfilment_blocked"
    if invoice.kind == SubscriptionInvoice.Kind.PLAN_CHANGE:
        from apps.subscriptions.models import SubscriptionEvent

        # The plan changed AFTER this invoice was created (admin override, scheduled change applied at renewal, another
        # purchase): paying it would overwrite that newer decision. Status-only changes (grace, suspension) do not count.
        if SubscriptionEvent.objects.filter(
            subscription_id=invoice.subscription_id, event_type=SubscriptionEvent.EventType.PLAN_CHANGED,
            created_at__gt=invoice.created_at,
        ).exists():
            return "stale_decision"
    return None


def _park_payment(locked_attempt, invoice, code, *, provider_payment_id, actor, now):
    """Record a confirmed-but-unapplicable payment for finance reconciliation. Idempotent (callers return early on a
    parked attempt). Grants nothing, redeems nothing, and does not change the invoice or the subscription."""
    locked_attempt.status = SubscriptionPaymentAttempt.Status.REQUIRES_ACTION
    locked_attempt.failure_code = code
    locked_attempt.failure_message = _PARK_MESSAGES[code]
    if provider_payment_id:
        locked_attempt.provider_payment_id = provider_payment_id
    locked_attempt.completed_at = now
    locked_attempt.save(update_fields=[
        "status", "failure_code", "failure_message", "provider_payment_id", "completed_at", "updated_at",
    ])
    record_audit_event(
        store=invoice.store, actor=actor, action_code="billing.payment_parked",
        object_type="SubscriptionPaymentAttempt", object_id=locked_attempt.pk, object_label=locked_attempt.public_token,
        after={"code": code, "invoice": invoice.number, "invoice_status": invoice.status, "amount": str(locked_attempt.amount)},
    )
    return locked_attempt


@transaction.atomic
def confirm_payment(*, attempt, amount, currency, provider_payment_id="", actor=None, now=None):
    """پرداختِ یک تلاش را تأیید و اعمال می‌کند — idempotent. مبلغ/ارزِ نامطابق
    را رد می‌کند. تلاشِ از قبل موفق را دوباره پردازش نمی‌کند."""
    now = now or timezone.now()
    locked_attempt = SubscriptionPaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=locked_attempt.invoice_id)

    # idempotency: تلاشِ از قبل موفق ⇒ بدونِ اعمالِ دوباره.
    if locked_attempt.status == SubscriptionPaymentAttempt.Status.SUCCEEDED:
        return locked_attempt
    if locked_attempt.status == SubscriptionPaymentAttempt.Status.REQUIRES_ACTION and (
            locked_attempt.failure_code == "duplicate_payment" or locked_attempt.failure_code in PARKED_FAILURE_CODES):
        return locked_attempt                          # پرداختِ تکراری/پارک‌شده از قبل ثبت شده: تکرارِ callback حسابرسیِ دوباره نمی‌سازد
    if invoice.status == SubscriptionInvoice.Status.PAID:
        # فاکتور از قبل پرداخت‌شده (تلاشِ دیگری موفق بود) و این تلاش هم پولی گرفته: پرداختِ
        # دوباره **اعمال نمی‌شود**، و این تلاش «نیازمندِ اقدام» (پرداختِ تکراری — احتمالاً
        # بازپرداخت) علامت می‌خورد تا در فهرستِ تطبیقِ مدیر دیده شود، نه اینکه گم شود.
        locked_attempt.status = SubscriptionPaymentAttempt.Status.REQUIRES_ACTION
        locked_attempt.failure_code = "duplicate_payment"
        locked_attempt.failure_message = "فاکتور پیش‌تر پرداخت شده؛ این پرداختِ تکراری نیازمندِ بازپرداخت/بررسی است."
        if provider_payment_id:
            locked_attempt.provider_payment_id = provider_payment_id
        locked_attempt.completed_at = now
        locked_attempt.save(update_fields=[
            "status", "failure_code", "failure_message", "provider_payment_id", "completed_at", "updated_at",
        ])
        record_audit_event(
            store=invoice.store, actor=actor, action_code="billing.duplicate_payment_flagged",
            object_type="SubscriptionPaymentAttempt", object_id=locked_attempt.pk, object_label=locked_attempt.public_token,
            after={"invoice": invoice.number, "amount": str(locked_attempt.amount)},
        )
        return locked_attempt

    amount = Decimal(amount)
    # بررسی‌هایِ امنیتی: Provider، ارز، مبلغ باید بخوانند.
    if currency != invoice.currency:
        raise ConfirmationError("ارزِ پرداخت با فاکتور نمی‌خواند.")
    if amount != invoice.amount_due:
        raise ConfirmationError("مبلغِ پرداخت با مبلغِ باقی‌مانده‌ی فاکتور نمی‌خواند.")

    reason = _park_reason(invoice)
    if reason:
        return _park_payment(locked_attempt, invoice, reason, provider_payment_id=provider_payment_id, actor=actor, now=now)

    try:
        with transaction.atomic():                     # savepoint: a fulfilment failure must not erase the record of the money
            _apply_confirmed_payment(locked_attempt, invoice, amount, provider_payment_id=provider_payment_id, actor=actor, now=now)
    except sub_svc.SubscriptionError:
        locked_attempt.refresh_from_db()
        invoice.refresh_from_db()
        return _park_payment(locked_attempt, invoice, "fulfilment_blocked", provider_payment_id=provider_payment_id, actor=actor, now=now)
    return locked_attempt


def _apply_confirmed_payment(locked_attempt, invoice, amount, *, provider_payment_id, actor, now):
    """Mark the attempt succeeded, apply the money to the invoice, redeem the coupon once, fulfil the subscription."""
    locked_attempt.status = SubscriptionPaymentAttempt.Status.SUCCEEDED
    locked_attempt.failure_code = ""
    locked_attempt.failure_message = ""
    if provider_payment_id:
        locked_attempt.provider_payment_id = provider_payment_id
    locked_attempt.completed_at = now
    locked_attempt.save(update_fields=["status", "failure_code", "failure_message", "provider_payment_id", "completed_at", "updated_at"])

    invoice.amount_paid = invoice.amount_paid + amount
    invoice.recompute_amount_due()
    if invoice.amount_due <= ZERO:
        invoice.status = SubscriptionInvoice.Status.PAID
        invoice.paid_at = now
        invoice.provider_reference = provider_payment_id or invoice.provider_reference
    invoice.save(update_fields=[
        "amount_paid", "amount_due", "status", "paid_at", "provider_reference", "updated_at",
    ])
    record_audit_event(
        store=invoice.store, actor=actor, action_code="billing.payment_confirmed",
        object_type="SubscriptionInvoice", object_id=invoice.pk, object_label=invoice.number,
        after={"amount": str(amount), "status": invoice.status},
    )

    if invoice.status == SubscriptionInvoice.Status.PAID:
        from apps.billing.services import platform_coupon_service

        platform_coupon_service.redeem_for_paid_invoice(invoice, actor=actor, now=now)   # مصرفِ کوپن دقیقاً یک‌بار
        _activate_or_renew(invoice, actor=actor, now=now)


@transaction.atomic
def mark_invoice_paid_manually(invoice, *, actor=None, now=None, note=""):
    """یک فاکتورِ باز را به‌صورتِ دستی (توسطِ مدیرِ پلتفرم) پرداخت‌شده علامت
    می‌زند — با ثبتِ صریحِ Audit. یک تلاشِ پرداختِ «manual» می‌سازد و از همان
    مسیرِ ``confirm_payment`` عبور می‌کند (پس فعال‌سازی/تمدید هم رخ می‌دهد)."""
    from apps.billing.services import attempt_service

    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if not locked.is_payable:
        raise ConfirmationError("این فاکتور در وضعیتِ قابلِ‌پرداخت نیست.")
    attempt = attempt_service.create_attempt(locked, provider="manual", actor=actor, now=now)
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.manual_mark_paid",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        metadata={"note": note},
    )
    result = confirm_payment(
        attempt=attempt, amount=locked.amount_due, currency=locked.currency,
        provider_payment_id=f"manual-admin-{attempt.public_token}", actor=actor, now=now,
    )
    if result.status != SubscriptionPaymentAttempt.Status.SUCCEEDED:
        # The payment could not be applied (e.g. the subscription is closed or the plan decision is stale). An admin asserting
        # "paid" must not get a false success; raising rolls the manual attempt back so nothing half-recorded remains.
        raise ConfirmationError(result.failure_message or "پرداخت اعمال نشد.")
    return result


@transaction.atomic
def settle_zero_due_invoice(invoice, *, actor=None, now=None):
    """فاکتورِ **واقعاً صفر** (مثلاً قیمتِ صفر یا تخفیفِ کامل) را بدونِ درگاه تسویه و اعمال می‌کند — دقیقاً یک‌بار.

    سخت‌گیریِ سمتِ سرور (هیچ دسترسیِ رایگان به پلنِ پولی): فاکتور باید قابلِ پرداخت باشد، ``grand_total``/``amount_due``/
    ``amount_paid`` همگی صفر باشند و **جمعِ ردیف‌هایِ فاکتور** (که سرور از نسخه‌ی پلن ساخته) هم صفر باشد؛ برایِ ``PLAN_CHANGE``
    تازگیِ تصمیم مثلِ ``start_payment`` بررسی می‌شود. از همان ``confirm_payment`` (ثبتِ تلاش، حسابرسی، فعال‌سازی/تمدید) می‌گذرد."""
    from apps.billing.services import attempt_service

    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status == SubscriptionInvoice.Status.PAID:
        return locked                                                  # idempotent
    if not locked.is_payable:
        raise ConfirmationError("این فاکتور در وضعیتِ قابلِ‌پرداخت نیست.")
    lines_total = sum((line.total for line in locked.lines.all()), ZERO)
    if locked.grand_total != ZERO or locked.amount_due != ZERO or locked.amount_paid != ZERO or lines_total != ZERO:
        raise ConfirmationError("این فاکتور مبلغِ صفر ندارد و باید پرداخت شود.")
    if locked.kind == SubscriptionInvoice.Kind.PLAN_CHANGE:
        from apps.subscriptions.services import plan_change_service as pcs

        current = StoreSubscription.objects.get(pk=locked.subscription_id)
        if not locked.idempotency_key or locked.idempotency_key != pcs._preview_token(current, locked.plan_version):
            raise ConfirmationError("این فاکتورِ تغییرِ پلن دیگر تصمیمِ معتبرِ فعلی نیست.")
    from apps.billing.services import platform_coupon_service

    try:
        platform_coupon_service.ensure_reservation_active(locked, now=now)
    except platform_coupon_service.CouponError as exc:
        raise ConfirmationError(exc.message) from exc
    attempt = attempt_service.create_attempt(locked, provider="manual", actor=actor, now=now)
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.zero_invoice_settled",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        after={"grand_total": "0", "kind": locked.kind},
    )
    result = confirm_payment(
        attempt=attempt, amount=ZERO, currency=locked.currency,
        provider_payment_id=f"zero-due-{attempt.public_token}", actor=actor, now=now,
    )
    if result.status != SubscriptionPaymentAttempt.Status.SUCCEEDED:
        raise ConfirmationError(result.failure_message or "تسویهٔ صفر اعمال نشد.")
    return SubscriptionInvoice.objects.get(pk=locked.pk)


def _remember_interval(subscription, interval):
    """دوره‌ی خریداری‌شده را روی اشتراک ثبت می‌کند تا تمدیدها با همان دوره/قیمتِ نسخه‌ی تغییرناپذیر صادر شوند."""
    subscription.refresh_from_db(fields=["billing_interval"])
    if subscription.billing_interval != interval:
        subscription.billing_interval = interval
        subscription.save(update_fields=["billing_interval", "updated_at"])


def _activate_or_renew(invoice, *, actor, now):
    """پس از پرداختِ کاملِ فاکتور، اشتراک را فعال یا تمدید می‌کند. تغییرِ پلن
    (kind=plan_change) در commit 8 مدیریت می‌شود."""
    subscription = StoreSubscription.objects.select_for_update().get(pk=invoice.subscription_id)
    interval = invoice_service.invoice_billing_interval(invoice)
    period_start = invoice.billing_period_start or now
    period_end = invoice.billing_period_end or next_period_end(period_start, interval)
    idem = f"invoice-{invoice.pk}"

    if invoice.kind == SubscriptionInvoice.Kind.INITIAL:
        # پرداختِ اولین فاکتور: pending/trialing → active (هرگز پیش از تأیید).
        if subscription.status in (StoreSubscription.Status.PENDING, StoreSubscription.Status.TRIALING):
            sub_svc.activate_subscription(subscription, actor=actor, period_end=period_end, idempotency_key=idem)
            _remember_interval(subscription, interval)
    elif invoice.kind == SubscriptionInvoice.Kind.RENEWAL:
        sub_svc.renew_subscription(
            subscription, period_start=period_start, period_end=period_end, actor=actor, idempotency_key=idem,
        )
    elif invoice.kind == SubscriptionInvoice.Kind.PLAN_CHANGE:
        # SUB-001 Repair 4 (همگراییِ دفاعی، تصمیمِ معمار): در عملیاتِ
        # کانونیکِ فعلی، ``ScheduledPlanChange`` و یک فاکتورِ قابلِ‌پرداختِ
        # ``PLAN_CHANGE`` دیگر هرگز هم‌زمان برایِ یک اشتراک زنده نمی‌مانند
        # (``start_plan_change``/``execute_platform_admin_plan_override``
        # هر دو پیش از ساختن/اجرا آن را جانشین می‌کنند). اما داده‌یِ
        # تاریخی/پیش از این ترمیم یا هر ناهماهنگیِ دیگر ممکن است هنوز هر دو
        # را هم‌زمان داشته باشد. اکنون پول واقعاً جابه‌جا شده — تأییدِ
        # Providerی که همین بالا اعمال شد رخداده و برنمی‌گردد (هیچ بازپرداختِ
        # جعلی‌ای اینجا ساخته نمی‌شود) — پس تصمیمِ *پرداخت‌شده* باید پیروز
        # شود: هر ``ScheduledPlanChange``یِ باقی‌مانده همینجا، زیرِ همینِ
        # قفلِ اشتراک، از طریقِ همان کمکِ کانونیکِ
        # ``plan_change_billing_service.supersede_scheduled_plan_change``
        # (با ثبتِ حسابرسی) پاک می‌شود، سپس هدفِ پرداخت‌شده اعمال می‌شود.
        from apps.billing.services import plan_change_billing_service as pcb

        pcb.supersede_scheduled_plan_change(
            subscription, actor=actor,
            reason="ارتقایِ تأییدشده‌یِ پرداخت جایِ تنزلِ زمان‌بندی‌شده‌یِ باقی‌مانده را گرفت",
            replacement_intent=f"paid_plan_change_invoice:{invoice.pk}",
        )
        was_trial_plan = subscription.plan_version.plan.code == "trial"          # the internal Trial plan (read BEFORE the version changes)
        sub_svc.change_plan_version(
            subscription, invoice.plan_version, actor=actor, reason="ارتقا پس از پرداخت",
            idempotency_key=idem,
        )
        # اگر این ارتقا همان اولین پرداختِ واقعیِ Store بود (هنوز trialing/
        # pending، مثلِ تبدیلِ آزمایشی به پولی) — تغییرِ پلن به‌تنهایی وضعیت را
        # عوض نمی‌کند؛ پس اینجا هم فعال می‌شود، دقیقاً مثلِ kind=INITIAL. همین برایِ فروشگاهی که Trialش *تمام شده*
        # (restricted/grace/past_due روی پلنِ Trial) و حالا اولین اشتراکِ پولی‌اش را می‌خرد هم صادق است: پرداختِ تأییدشده آن را
        # دوباره فعال می‌کند (فقط پس از تأییدِ واقعیِ پرداخت — این تابع تنها از confirm_payment/تأییدِ دستیِ مالی فراخوانی می‌شود).
        reactivate = (StoreSubscription.Status.PENDING, StoreSubscription.Status.TRIALING)
        if was_trial_plan:
            reactivate += (StoreSubscription.Status.GRACE_PERIOD, StoreSubscription.Status.SUSPENDED, StoreSubscription.Status.PAST_DUE)
        if subscription.status in reactivate:
            sub_svc.activate_subscription(
                subscription, actor=actor, period_end=period_end, idempotency_key=f"{idem}-activate",
            )
        _remember_interval(subscription, interval)
    ent.clear_entitlement_cache()
