"""بازپرداختِ پرداختِ اشتراک از مسیرِ Provider abstraction (ADR-81).

نمی‌تواند از مبلغِ قابلِ‌بازپرداخت (پرداخت‌شده منهایِ بازپرداخت‌هایِ موفق/باز)
بیشتر باشد و دوبار انجام نمی‌شود (idempotent روی کلید). Providerِ دستی خودکار
تأیید نمی‌کند — بازپرداخت در حالتِ ``pending`` می‌ماند تا اقدامِ صریحِ مدیر.
هرگز از مدل‌هایِ Refundِ سفارشِ فروشگاه استفاده نمی‌شود."""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import (
    SubscriptionCreditNote,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
    SubscriptionRefund,
)
from apps.billing.providers import registry
from apps.billing.providers.base import BillingProviderError
from apps.core.services.audit_service import record_audit_event

ZERO = Decimal("0")
logger = logging.getLogger("billing")

#: Interim marker for an AMBIGUOUS provider outcome (timeout, transport error, unexpected exception, lost response, or a crash
#: after the intent was committed). It rides on the existing PENDING status because a dedicated UNKNOWN status is a model choices
#: change, i.e. a migration, which is not approved yet (see docs/payments/PHASE2_MIGRATION_PROPOSAL). Behaviourally it is what
#: UNKNOWN will be: the amount stays reserved, the provider is NEVER called again automatically, and only a person with a bank
#: reference can resolve it.
UNKNOWN_OUTCOME = "unknown_outcome"
STALE_INTENT_AFTER = timedelta(minutes=10)
_MIN_REFERENCE_LEN = 6
#: BillingProviderError codes that mean the request definitely never left our side (nothing was sent to a bank).
NOT_SENT_CODES = frozenset({"ineligible_gateway", "not_configured", "provider_unavailable", "unknown_provider"})


class RefundError(Exception):
    """خطای قابل‌نمایش هنگام بازپرداخت."""


def refunded_total(invoice) -> Decimal:
    """جمعِ بازپرداخت‌هایِ موفق + باز (requested/pending) — تا از رزروِ دوباره
    جلوگیری شود."""
    agg = invoice.refunds.filter(
        status__in=(
            SubscriptionRefund.Status.SUCCEEDED,
            SubscriptionRefund.Status.REQUESTED,
            SubscriptionRefund.Status.PENDING,
        ),
    ).aggregate(s=Sum("amount"))
    return agg["s"] or ZERO


def refundable_amount(invoice) -> Decimal:
    return max(invoice.amount_paid - refunded_total(invoice), ZERO)


def _sync_invoice_refund_status(invoice, *, now, refund=None):
    """وضعیتِ بازپرداختِ فاکتور را از بازپرداخت‌هایِ *موفق* بازمحاسبه می‌کند."""
    succeeded = invoice.refunds.filter(status=SubscriptionRefund.Status.SUCCEEDED).aggregate(
        s=Sum("amount"))["s"] or ZERO
    if succeeded <= ZERO:
        return
    if succeeded >= invoice.amount_paid:
        invoice.status = SubscriptionInvoice.Status.REFUNDED
        from apps.billing.services import platform_coupon_service

        platform_coupon_service.reverse_for_refund(invoice, now=now)   # سیاستِ کوپن: فقط بازپرداختِ کامل در پنجره‌ی مجاز
    else:
        invoice.status = SubscriptionInvoice.Status.PARTIALLY_REFUNDED
    invoice.save(update_fields=["status", "updated_at"])


def _validate_existing_subscription_refund(
    existing: SubscriptionRefund, *, invoice: SubscriptionInvoice,
    amount: Decimal, reason: str, payment_attempt=None, credit_note=None,
) -> SubscriptionRefund:
    if existing.store_id != invoice.store_id or existing.invoice_id != invoice.pk:
        raise RefundError("کلید یکتای بازپرداخت با این فاکتور مطابقت ندارد.")
    if (
        existing.amount != amount
        or existing.reason != reason
        or existing.credit_note_id != (credit_note.pk if credit_note is not None else None)
        or (payment_attempt is not None and existing.payment_attempt_id != payment_attempt.pk)
    ):
        raise RefundError("مشخصات درخواست بازپرداخت با کلید قبلی مطابقت ندارد.")
    return existing


def request_refund(invoice, *, amount, reason="", requested_by=None, payment_attempt=None,
                   credit_note=None, idempotency_key="", now=None):
    """Request a refund, in three separate steps so an uncertain external outcome can never duplicate money or lose the record:

    1. INTENT: validate and commit a ``REQUESTED`` refund row (reserves the amount). Idempotent on ``idempotency_key``; a repeat
       returns the existing row WITHOUT contacting the provider.
    2. CALL: contact the provider with NO transaction and NO row lock held, once, using the stable key stored on the row.
    3. OUTCOME: record the result in a short conditional transaction (only if the row is still ``REQUESTED``).

    Do not call this from inside an outer ``transaction.atomic()``: the intent would not be committed before the provider call."""
    now = now or timezone.now()
    refund, created = _record_intent(
        invoice, amount=amount, reason=reason, requested_by=requested_by, payment_attempt=payment_attempt,
        credit_note=credit_note, idempotency_key=idempotency_key, now=now,
    )
    if not created:
        return refund
    return _execute_with_provider(refund.pk, now=now)


@transaction.atomic
def _record_intent(invoice, *, amount, reason, requested_by, payment_attempt, credit_note, idempotency_key, now):
    """Step 1. Returns ``(refund, created)``."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    amount = Decimal(amount)

    if payment_attempt is not None and not SubscriptionPaymentAttempt.objects.filter(
        pk=payment_attempt.pk, invoice_id=locked.pk, store_id=locked.store_id,
        status=SubscriptionPaymentAttempt.Status.SUCCEEDED,
    ).exists():
        raise RefundError("تلاش پرداخت انتخاب‌شده متعلق به این فاکتور یا موفق نیست.")
    if credit_note is not None and not SubscriptionCreditNote.objects.filter(
        pk=credit_note.pk, invoice_id=locked.pk, store_id=locked.store_id,
        status=SubscriptionCreditNote.Status.ISSUED,
    ).exists():
        raise RefundError("سند اعتبار انتخاب‌شده متعلق به این فاکتور یا معتبر نیست.")

    if idempotency_key:
        existing = SubscriptionRefund.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return _validate_existing_subscription_refund(
                existing, invoice=locked, amount=amount, reason=reason,
                payment_attempt=payment_attempt, credit_note=credit_note,
            ), False
    else:
        import secrets
        idempotency_key = f"refund-{locked.pk}-{secrets.token_hex(8)}"

    if SubscriptionRefund.objects.filter(
        invoice=locked, status=SubscriptionRefund.Status.PENDING, failure_code=UNKNOWN_OUTCOME,
    ).exists():
        # An earlier refund may already have been paid out. A new request could pay the customer twice, so finance must first
        # resolve the unknown one (confirm it with a bank reference, or prove it did not happen).
        raise RefundError("یک بازپرداخت با نتیجهٔ نامشخص برای این فاکتور وجود دارد؛ ابتدا آن را تعیین تکلیف کنید.")
    if amount <= ZERO:
        raise RefundError("مبلغِ بازپرداخت باید بزرگ‌تر از صفر باشد.")
    if amount > refundable_amount(locked):
        raise RefundError("مبلغِ بازپرداخت از مبلغِ قابلِ‌بازپرداخت بیشتر است.")

    if payment_attempt is None:
        payment_attempt = SubscriptionPaymentAttempt.objects.filter(
            invoice=locked, status=SubscriptionPaymentAttempt.Status.SUCCEEDED,
        ).order_by("-completed_at").first()

    provider_code = payment_attempt.provider if payment_attempt else registry.active_provider_code()
    try:
        with transaction.atomic():
            refund = SubscriptionRefund.objects.create(
                store=locked.store, invoice=locked, payment_attempt=payment_attempt, credit_note=credit_note,
                provider=provider_code, status=SubscriptionRefund.Status.REQUESTED, amount=amount,
                currency=locked.currency, reason=reason, requested_by=requested_by, requested_at=now,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        existing = SubscriptionRefund.objects.filter(idempotency_key=idempotency_key).first()
        if existing is None:
            raise
        return _validate_existing_subscription_refund(
            existing, invoice=locked, amount=amount, reason=reason,
            payment_attempt=payment_attempt, credit_note=credit_note,
        ), False
    record_audit_event(
        store=locked.store, actor=requested_by, action_code="billing.refund_intent_recorded",
        object_type="SubscriptionRefund", object_id=refund.pk, object_label=str(refund.amount),
        after={"invoice": locked.number, "amount": str(amount), "provider": provider_code},
    )
    return refund, True


def _execute_with_provider(refund_pk, *, now=None):
    """Steps 2 and 3. At most one provider call per refund row, ever (the caller only gets here for a newly created row)."""
    now = now or timezone.now()
    refund = SubscriptionRefund.objects.select_related("payment_attempt").get(pk=refund_pk)
    try:
        provider = registry.get_provider(refund.provider)
    except BillingProviderError as exc:
        # Nothing was sent anywhere: a definite, safe failure that releases the reservation.
        return _record_outcome(refund_pk, "declined", failure_code=(exc.code or "provider_unavailable")[:64], now=now)
    provider_payment_id = refund.payment_attempt.provider_payment_id if refund.payment_attempt_id else ""
    try:
        result = provider.refund_payment(
            provider_payment_id=provider_payment_id, amount=refund.amount, currency=refund.currency,
            idempotency_key=refund.idempotency_key,
        )
    except BillingProviderError as exc:
        if (exc.code or "") in NOT_SENT_CODES:
            return _record_outcome(refund_pk, "declined", failure_code=exc.code[:64], now=now)
        logger.warning("refund %s: provider error %s is ambiguous", refund_pk, exc.code)
        return _record_outcome(refund_pk, "unknown", failure_code=UNKNOWN_OUTCOME, detail=(exc.code or type(exc).__name__)[:80], now=now)
    except Exception as exc:  # noqa: BLE001 — after contacting a bank ANY failure is ambiguous: it may have been executed
        logger.exception("refund %s: provider call failed with an ambiguous outcome", refund_pk)
        return _record_outcome(refund_pk, "unknown", failure_code=UNKNOWN_OUTCOME, detail=type(exc).__name__, now=now)
    summary = result.raw_summary or {}
    if result.succeeded:
        return _record_outcome(refund_pk, "succeeded", provider_refund_id=result.provider_refund_id, now=now)
    if summary.get("unknown"):
        return _record_outcome(refund_pk, "unknown", failure_code=UNKNOWN_OUTCOME, provider_refund_id=result.provider_refund_id,
                               detail=str(summary.get("reason", ""))[:200], now=now)
    return _record_outcome(refund_pk, "manual", provider_refund_id=result.provider_refund_id, now=now)


@transaction.atomic
def _record_outcome(refund_pk, outcome, *, provider_refund_id="", failure_code="", detail="", now):
    """Step 3: conditional on the row still being REQUESTED, so a recovery job or a second path can never be overwritten."""
    refund = SubscriptionRefund.objects.select_for_update().get(pk=refund_pk)
    if refund.status != SubscriptionRefund.Status.REQUESTED:
        return refund
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=refund.invoice_id)
    if provider_refund_id:
        refund.provider_refund_id = provider_refund_id
    if outcome == "succeeded":
        refund.status = SubscriptionRefund.Status.SUCCEEDED
        refund.completed_at = now
    elif outcome == "declined":
        refund.status = SubscriptionRefund.Status.FAILED
        refund.failure_code = failure_code
        refund.failure_message = "درخواست بازپرداخت به درگاه ارسال نشد."
        refund.completed_at = now
    elif outcome == "unknown":
        refund.status = SubscriptionRefund.Status.PENDING
        refund.failure_code = failure_code
        refund.failure_message = ("نتیجهٔ بازپرداخت نزد درگاه نامشخص است؛ دوباره درخواست نکنید. با ارجاعِ بانکی بررسی و تعیین تکلیف شود.")[:300]
    else:                                              # "manual": the provider has no automatic refund; finance completes it
        refund.status = SubscriptionRefund.Status.PENDING
    refund.save(update_fields=["provider_refund_id", "status", "failure_code", "failure_message", "completed_at", "updated_at"])
    if refund.status == SubscriptionRefund.Status.SUCCEEDED:
        _sync_invoice_refund_status(invoice, now=now, refund=refund)
    record_audit_event(
        store=invoice.store, actor=refund.requested_by, action_code=(
            "billing.refund_outcome_unknown" if outcome == "unknown" else "billing.refund_requested"),
        object_type="SubscriptionRefund", object_id=refund.pk, object_label=str(refund.amount),
        after={"invoice": invoice.number, "amount": str(refund.amount), "status": refund.status, "outcome": outcome},
        metadata={"detail": detail} if detail else None,
    )
    return refund


def recover_stale_intents(*, now=None, older_than=STALE_INTENT_AFTER) -> int:
    """A refund still ``REQUESTED`` long after its intent was committed means the process died between the intent and the
    outcome. The provider may or may not have been called, so the outcome is AMBIGUOUS: mark it unknown and hand it to finance.
    This NEVER calls the provider. Idempotent. Returns the number of refunds marked."""
    now = now or timezone.now()
    marked = 0
    stale = SubscriptionRefund.objects.filter(
        status=SubscriptionRefund.Status.REQUESTED, provider_refund_id="", created_at__lt=now - older_than,
    )
    for pk in list(stale.values_list("pk", flat=True)):
        with transaction.atomic():
            refund = SubscriptionRefund.objects.select_for_update().select_related("store", "invoice").get(pk=pk)
            if refund.status != SubscriptionRefund.Status.REQUESTED or refund.provider_refund_id:
                continue
            refund.status = SubscriptionRefund.Status.PENDING
            refund.failure_code = UNKNOWN_OUTCOME
            refund.failure_message = "فرایند پیش از ثبتِ نتیجه متوقف شد؛ نتیجه نامشخص است. دوباره درخواست نکنید."
            refund.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])
            record_audit_event(
                store=refund.store, action_code="billing.refund_outcome_unknown", object_type="SubscriptionRefund", object_id=refund.pk,
                object_label=str(refund.amount), after={"invoice": refund.invoice.number, "reason": "stale_intent"},
            )
            marked += 1
    return marked


def _require_reference(refund, reference):
    reference = (reference or "").strip()
    if refund.failure_code == UNKNOWN_OUTCOME and len(reference) < _MIN_REFERENCE_LEN:
        raise RefundError("برای بازپرداختِ با نتیجهٔ نامشخص، ارجاعِ مستندِ بانکی (حداقل ۶ نویسه) الزامی است.")
    return reference


@transaction.atomic
def complete_refund_manually(refund, *, actor=None, now=None, reference=""):
    """Mark an open refund as really paid out (after the manual bank transfer / confirmed provider outcome) and sync the invoice.
    For an ambiguous-outcome refund a documented bank reference is mandatory."""
    now = now or timezone.now()
    locked = SubscriptionRefund.objects.select_for_update().get(pk=refund.pk)
    if locked.status == SubscriptionRefund.Status.SUCCEEDED:
        return locked
    if locked.status not in SubscriptionRefund.OPEN_STATUSES:
        raise RefundError("این بازپرداخت در وضعیتِ قابلِ‌تکمیل نیست.")
    reference = _require_reference(locked, reference)
    locked.status = SubscriptionRefund.Status.SUCCEEDED
    locked.completed_at = now
    if reference:
        locked.failure_message = f"تکمیلِ دستی با ارجاع: {reference}"[:300]
    locked.save(update_fields=["status", "completed_at", "failure_message", "updated_at"])
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=locked.invoice_id)
    _sync_invoice_refund_status(invoice, now=now, refund=locked)
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.refund_completed",
        object_type="SubscriptionRefund", object_id=locked.pk, object_label=str(locked.amount),
        metadata={"reference": reference} if reference else None,
    )
    return locked


@transaction.atomic
def fail_refund_manually(refund, *, actor, reference, note="", now=None):
    """Finance determined, with evidence, that an open refund did NOT happen at the provider. Releases the reserved amount so a
    corrected refund can be requested. Evidence (a reference of at least 6 characters) is mandatory and audited."""
    now = now or timezone.now()
    reference = (reference or "").strip()
    if len(reference) < _MIN_REFERENCE_LEN:
        raise RefundError("ارجاعِ مستند (حداقل ۶ نویسه) الزامی است.")
    locked = SubscriptionRefund.objects.select_for_update().get(pk=refund.pk)
    if locked.status == SubscriptionRefund.Status.FAILED:
        return locked
    if locked.status not in SubscriptionRefund.OPEN_STATUSES:
        raise RefundError("این بازپرداخت در وضعیتِ قابلِ‌رسیدگی نیست.")
    locked.status = SubscriptionRefund.Status.FAILED
    locked.failure_code = "manual_declined"
    locked.failure_message = f"تأییدِ مالی: بازپرداخت انجام نشد. ارجاع: {reference}"[:300]
    locked.completed_at = now
    locked.save(update_fields=["status", "failure_code", "failure_message", "completed_at", "updated_at"])
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.refund_failed_manually",
        object_type="SubscriptionRefund", object_id=locked.pk, object_label=str(locked.amount),
        metadata={"reference": reference, "note": (note or "")[:200]},
    )
    return locked
