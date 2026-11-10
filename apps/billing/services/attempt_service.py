"""ساختِ ``SubscriptionPaymentAttempt`` — هر Retry یک ردیفِ تازه (ADR-75/77).

این سرویس فقط تلاش را *می‌سازد*؛ تأییدِ پرداخت (علامت‌زدنِ succeeded و اعمالِ
پرداخت رویِ فاکتور) در ``confirmation_service`` انجام می‌شود، تراکنشی و
idempotent (ADR-77)."""

import secrets

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers import registry
from apps.core.services.audit_service import record_audit_event


class PaymentAttemptError(Exception):
    """خطای قابل‌نمایش هنگام ساختِ تلاشِ پرداخت."""


def _new_token() -> str:
    return secrets.token_urlsafe(24)[:40]


@transaction.atomic
def get_or_create_attempt(invoice, *, provider=None, idempotency_key="", actor=None, now=None):
    """``(attempt, created)``. idempotent روی ``idempotency_key`` و *متعلق به همان فاکتور*: کلیدِ یک تلاشِ موجود فقط برایِ همان
    فاکتور/فروشگاه/درگاه/ارز دوباره‌استفاده می‌شود؛ هر ناهمخوانی خطاست (F-13) و هیچ تلاشی عوض یا باز نمی‌شود. مبلغ/ارز از خودِ
    فاکتور می‌آید (نه از مرورگر)."""
    now = now or timezone.now()
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if not locked.is_payable:
        raise PaymentAttemptError("این فاکتور در وضعیتِ قابلِپرداخت نیست.")

    provider_code = provider or registry.active_provider_code()
    if idempotency_key:
        existing = SubscriptionPaymentAttempt.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if (
                existing.invoice_id != locked.pk or existing.store_id != locked.store_id
                or existing.provider != provider_code or existing.currency != locked.currency
            ):
                raise PaymentAttemptError("کلید یکتای پرداخت با این فاکتور مطابقت ندارد.")
            return existing, False
    else:
        idempotency_key = f"attempt-{locked.pk}-{secrets.token_hex(8)}"

    attempt_number = SubscriptionPaymentAttempt.objects.filter(invoice=locked).count() + 1

    attempt = SubscriptionPaymentAttempt.objects.create(
        store=locked.store, invoice=locked, provider=provider_code,
        status=SubscriptionPaymentAttempt.Status.CREATED,
        amount=locked.amount_due, currency=locked.currency,
        public_token=_new_token(), idempotency_key=idempotency_key,
        attempt_number=attempt_number, started_at=now,
    )
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.payment_attempt_created",
        object_type="SubscriptionPaymentAttempt", object_id=attempt.pk, object_label=attempt.public_token,
        after={"invoice": locked.number, "amount": str(attempt.amount), "provider": provider_code},
    )
    return attempt, True


def create_attempt(invoice, *, provider=None, idempotency_key="", actor=None, now=None):
    """Compatibility wrapper: the attempt only (see ``get_or_create_attempt``)."""
    return get_or_create_attempt(invoice, provider=provider, idempotency_key=idempotency_key, actor=actor, now=now)[0]
