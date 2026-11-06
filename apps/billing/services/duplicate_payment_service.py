"""Duplicate / late-settlement overpayments on PLATFORM purchases (subscription invoice or SMS package).

When a merchant retries an unresolved online payment and BOTH attempts later settle, fulfilment already happens exactly once
(``confirmation_service.confirm_payment`` / ``sms_purchase_payment_service.confirm_payment``): the first verified attempt
fulfils; the second is marked ``REQUIRES_ACTION`` (``duplicate_payment`` / ``purchase_<status>``) and applies NOTHING. This
module adds the missing *resolution* of that surplus money, using only supported mechanisms:

* ``refund_duplicate`` – asks the SAME provider of the duplicate attempt to refund/reverse exactly that attempt's amount
  (``provider.refund_payment``; providers without an automatic refund honestly answer «manual processing»);
* ``mark_resolved``    – finance records an out-of-band outcome (refunded in the bank panel / credited / not an overpayment)
  with a mandatory reference.

Both are idempotent, audited, finance-only at the view layer, never touch the fulfilled invoice/purchase, never change the
attempt's status (it stays REQUIRES_ACTION as the immutable fact) and store the resolution in ``provider_extra`` (no schema
change). Resolved attempts leave the reconciliation «needs action» list."""

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.providers import registry
from apps.billing.providers.base import BillingProviderError
from apps.core.services.audit_service import record_audit_event
from apps.sms.models import SmsPackagePaymentAttempt

RESOLUTION_KEY = "duplicate_resolution"
OUTCOMES = ("refunded", "pending_manual", "refunded_external", "credited", "not_an_overpayment")
FINAL_OUTCOMES = ("refunded", "refunded_external", "credited", "not_an_overpayment")


class DuplicatePaymentError(Exception):
    """Shown to the finance admin; never leaks provider internals."""


def attempt_model(kind: str):
    return SmsPackagePaymentAttempt if kind == "sms" else SubscriptionPaymentAttempt


def is_duplicate(attempt) -> bool:
    """A REQUIRES_ACTION attempt whose purchase was already fulfilled by another payment (not an amount mismatch)."""
    return attempt.status == type(attempt).Status.REQUIRES_ACTION and (
        attempt.failure_code == "duplicate_payment" or attempt.failure_code == "purchase_completed"
    )


def resolution_of(attempt) -> dict:
    return dict((attempt.provider_extra or {}).get(RESOLUTION_KEY) or {})


def is_resolved(attempt) -> bool:
    return resolution_of(attempt).get("outcome") in FINAL_OUTCOMES


def _store_resolution(attempt, **data):
    extra = dict(attempt.provider_extra or {})
    extra[RESOLUTION_KEY] = data
    attempt.provider_extra = extra
    attempt.save(update_fields=["provider_extra", "updated_at"])


def _target_label(kind, attempt):
    return f"SMS-{attempt.purchase_id}" if kind == "sms" else attempt.invoice.number


def _audit(kind, attempt, action, actor, **after):
    record_audit_event(
        store=attempt.store, actor=actor, action_code=f"billing.duplicate_payment_{action}",
        object_type=type(attempt).__name__, object_id=attempt.pk, object_label=attempt.public_token,
        after={"target": _target_label(kind, attempt), "amount": str(attempt.amount), "provider": attempt.provider, **after},
    )


def _locked_duplicate(kind, attempt_id):
    model = attempt_model(kind)
    attempt = model.objects.select_for_update().select_related("store").get(pk=attempt_id)
    if not is_duplicate(attempt):
        raise DuplicatePaymentError("این تلاش یک پرداختِ تکراریِ شناسایی‌شده نیست.")
    return attempt


@transaction.atomic
def refund_duplicate(kind, attempt_id, *, actor, reason, idempotency_key=""):
    """Request the provider to refund exactly the duplicate attempt's money. Returns ``(attempt, outcome)``."""
    reason = (reason or "").strip()
    if len(reason) < 4:
        raise DuplicatePaymentError("دلیلِ بازپرداخت الزامی است.")
    attempt = _locked_duplicate(kind, attempt_id)
    done = resolution_of(attempt)
    if done.get("outcome") in OUTCOMES:
        return attempt, done["outcome"]                                    # idempotent: a refund was already requested/recorded
    key = idempotency_key or f"dup-refund-{kind}-{attempt.pk}"
    try:
        result = registry.get_provider(attempt.provider).refund_payment(
            provider_payment_id=attempt.provider_payment_id or attempt.provider_session_id,
            amount=attempt.amount, currency=attempt.currency, idempotency_key=key,
        )
    except BillingProviderError as exc:
        raise DuplicatePaymentError("درخواستِ بازپرداخت به درگاه انجام نشد؛ هیچ تغییری اعمال نشد.") from exc
    outcome = "refunded" if result.succeeded else "pending_manual"
    _store_resolution(
        attempt, outcome=outcome, reason=reason[:300], by=getattr(actor, "pk", None), at=timezone.now().isoformat(timespec="seconds"),
        provider_refund_id=str(result.provider_refund_id or "")[:120],
    )
    _audit(kind, attempt, "refund_requested", actor, outcome=outcome, reason=reason[:300])
    return attempt, outcome


@transaction.atomic
def mark_resolved(kind, attempt_id, *, actor, outcome, reference, note=""):
    """Finance records how the surplus was settled outside the system. ``reference`` (≥ 6 chars) is mandatory."""
    if outcome not in FINAL_OUTCOMES:
        raise DuplicatePaymentError("نتیجه‌ی نامعتبر.")
    reference = (reference or "").strip()
    if len(reference) < 6:
        raise DuplicatePaymentError("ارجاعِ مستند (حداقل ۶ نویسه) الزامی است.")
    attempt = _locked_duplicate(kind, attempt_id)
    done = resolution_of(attempt)
    if done.get("outcome") in FINAL_OUTCOMES:
        return attempt                                                      # idempotent: the first resolution stands
    _store_resolution(
        attempt, outcome=outcome, reference=reference[:120], note=(note or "")[:300], by=getattr(actor, "pk", None),
        at=timezone.now().isoformat(timespec="seconds"), previous=done.get("outcome", ""),
    )
    _audit(kind, attempt, "resolved", actor, outcome=outcome, reference=reference[:120])
    return attempt
