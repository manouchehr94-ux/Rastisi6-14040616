"""بازپرداختِ پرداختِ اشتراک از مسیرِ Provider abstraction (ADR-81).

نمی‌تواند از مبلغِ قابلِ‌بازپرداخت (پرداخت‌شده منهایِ بازپرداخت‌هایِ موفق/باز)
بیشتر باشد و دوبار انجام نمی‌شود (idempotent روی کلید). Providerِ دستی خودکار
تأیید نمی‌کند — بازپرداخت در حالتِ ``pending`` می‌ماند تا اقدامِ صریحِ مدیر.
هرگز از مدل‌هایِ Refundِ سفارشِ فروشگاه استفاده نمی‌شود."""

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
from apps.core.services.audit_service import record_audit_event

ZERO = Decimal("0")


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


def _sync_invoice_refund_status(invoice, *, now):
    """وضعیتِ بازپرداختِ فاکتور را از بازپرداخت‌هایِ *موفق* بازمحاسبه می‌کند."""
    succeeded = invoice.refunds.filter(status=SubscriptionRefund.Status.SUCCEEDED).aggregate(
        s=Sum("amount"))["s"] or ZERO
    if succeeded <= ZERO:
        return
    if succeeded >= invoice.amount_paid:
        invoice.status = SubscriptionInvoice.Status.REFUNDED
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


@transaction.atomic
def request_refund(invoice, *, amount, reason="", requested_by=None, payment_attempt=None,
                   credit_note=None, idempotency_key="", now=None):
    """یک بازپرداخت درخواست می‌کند و از Provider می‌خواهد آن را پردازش کند.
    idempotent روی ``idempotency_key``. از مبلغِ قابلِ‌بازپرداخت تجاوز نمی‌کند."""
    now = now or timezone.now()
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
            )
    else:
        import secrets
        idempotency_key = f"refund-{locked.pk}-{secrets.token_hex(8)}"

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
        )

    provider = registry.get_provider(provider_code)
    provider_payment_id = payment_attempt.provider_payment_id if payment_attempt else ""
    result = provider.refund_payment(
        provider_payment_id=provider_payment_id, amount=amount, currency=locked.currency,
        idempotency_key=idempotency_key,
    )
    refund.provider_refund_id = result.provider_refund_id
    if result.succeeded:
        refund.status = SubscriptionRefund.Status.SUCCEEDED
        refund.completed_at = now
    else:
        # Providerِ دستی: منتظرِ تکمیلِ دستی می‌ماند.
        refund.status = SubscriptionRefund.Status.PENDING
    refund.save(update_fields=["provider_refund_id", "status", "completed_at", "updated_at"])

    if refund.status == SubscriptionRefund.Status.SUCCEEDED:
        _sync_invoice_refund_status(locked, now=now)

    record_audit_event(
        store=locked.store, actor=requested_by, action_code="billing.refund_requested",
        object_type="SubscriptionRefund", object_id=refund.pk, object_label=str(refund.amount),
        after={"invoice": locked.number, "amount": str(amount), "status": refund.status},
    )
    return refund


@transaction.atomic
def complete_refund_manually(refund, *, actor=None, now=None):
    """یک بازپرداختِ در انتظار را (پس از پردازشِ دستیِ واقعی) موفق علامت می‌زند
    و وضعیتِ فاکتور را همگام می‌کند. فقط از حالتِ requested/pending."""
    now = now or timezone.now()
    locked = SubscriptionRefund.objects.select_for_update().get(pk=refund.pk)
    if locked.status == SubscriptionRefund.Status.SUCCEEDED:
        return locked
    if locked.status not in SubscriptionRefund.OPEN_STATUSES:
        raise RefundError("این بازپرداخت در وضعیتِ قابلِ‌تکمیل نیست.")
    locked.status = SubscriptionRefund.Status.SUCCEEDED
    locked.completed_at = now
    locked.save(update_fields=["status", "completed_at", "updated_at"])
    invoice = SubscriptionInvoice.objects.select_for_update().get(pk=locked.invoice_id)
    _sync_invoice_refund_status(invoice, now=now)
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.refund_completed",
        object_type="SubscriptionRefund", object_id=locked.pk, object_label=str(locked.amount),
    )
    return locked
