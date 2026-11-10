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
from apps.billing.providers import bank_refund_policy, registry
from apps.billing.providers.base import BillingProviderError
from apps.billing.services.refund_service import NOT_SENT_CODES
from apps.core.services.audit_service import record_audit_event
from apps.sms.models import SmsPackagePaymentAttempt

RESOLUTION_KEY = "duplicate_resolution"
PARKED_CODES = frozenset({"fulfilment_blocked", "late_payment_void", "late_payment_uncollectible", "stale_decision"})
REQUESTING = "requesting"          # intent committed, provider call in flight (or the process died): NEVER re-sent automatically
UNKNOWN = "unknown"                # ambiguous provider outcome: finance resolves it with a bank reference
OUTCOMES = ("refunded", "pending_manual", "refunded_external", "credited", "not_an_overpayment", REQUESTING, UNKNOWN)
#: Outcomes that mean "a provider refund was already requested": the refund action is hidden and never re-sent.
IN_FLIGHT_OUTCOMES = ("pending_manual", REQUESTING, UNKNOWN)
FINAL_OUTCOMES = ("refunded", "refunded_external", "credited", "not_an_overpayment")


class DuplicatePaymentError(Exception):
    """Shown to the finance admin; never leaks provider internals."""


def attempt_model(kind: str):
    return SmsPackagePaymentAttempt if kind == "sms" else SubscriptionPaymentAttempt


def is_duplicate(attempt) -> bool:
    """A REQUIRES_ACTION attempt whose purchase was already fulfilled by another payment (not an amount mismatch)."""
    return attempt.status == type(attempt).Status.REQUIRES_ACTION and (
        attempt.failure_code in ("duplicate_payment", "purchase_completed")
        or attempt.failure_code in PARKED_CODES                        # confirmed money parked by confirm_payment (F-02/F-05)
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


def refund_duplicate(kind, attempt_id, *, actor, reason, idempotency_key=""):
    """Request the provider to refund exactly the duplicate attempt's money. Returns ``(attempt, outcome)``.

    Three steps so an uncertain provider outcome can never duplicate money or be lost (F-06):
    1. INTENT: commit ``outcome="requesting"`` (idempotent; any existing resolution means "already requested" and the provider
       is NOT called again);
    2. CALL: contact the provider once with no transaction and no row lock;
    3. OUTCOME: record ``refunded`` / ``pending_manual`` / ``unknown`` conditionally on the intent still being ``requesting``.
    ``unknown`` and a stale ``requesting`` are never retried automatically: finance resolves them with a bank reference through
    ``mark_resolved``. Do not call from inside an outer ``transaction.atomic()``."""
    reason = (reason or "").strip()
    if len(reason) < 4:
        raise DuplicatePaymentError("دلیلِ بازپرداخت الزامی است.")
    key = idempotency_key or f"dup-refund-{kind}-{attempt_id}"
    with transaction.atomic():
        attempt = _locked_duplicate(kind, attempt_id)
        done = resolution_of(attempt)
        if done.get("outcome") in OUTCOMES:
            return attempt, done["outcome"]                                # idempotent: already requested/recorded
        _store_resolution(
            attempt, outcome=REQUESTING, reason=reason[:300], by=getattr(actor, "pk", None), key=key,
            at=timezone.now().isoformat(timespec="seconds"),
        )
        _audit(kind, attempt, "refund_intent_recorded", actor, reason=reason[:300])
        provider_code = attempt.provider
        payment_id = attempt.provider_payment_id or attempt.provider_session_id
        amount, currency = attempt.amount, attempt.currency

    outcome, refund_id, detail = "unknown", "", ""
    if not bank_refund_policy.automatic_refund_allowed(provider_code):
        # Service-layer fail-closed stop: no provider call. Finance refunds in the bank panel and records it with mark_resolved.
        outcome, detail = "pending_manual", bank_refund_policy.AUTOMATIC_REFUND_DISABLED
        refund_id = f"{provider_code}-manual-refund-{key}"[:120]
    else:
        try:
            result = registry.get_provider(provider_code).refund_payment(
                provider_payment_id=payment_id, amount=amount, currency=currency, idempotency_key=key,
            )
        except BillingProviderError as exc:
            if (getattr(exc, "code", "") or "") in NOT_SENT_CODES:
                outcome, detail = "not_sent", exc.code                     # nothing reached the bank: definite, safe
            else:
                outcome, detail = "unknown", getattr(exc, "code", "") or type(exc).__name__
        except Exception as exc:  # noqa: BLE001 — after contacting a bank any failure is ambiguous
            detail = type(exc).__name__
        else:
            refund_id = str(result.provider_refund_id or "")[:120]
            summary = result.raw_summary or {}
            outcome = "refunded" if result.succeeded else ("unknown" if summary.get("unknown") else "pending_manual")

    not_sent = outcome == "not_sent"
    with transaction.atomic():
        attempt = _locked_duplicate(kind, attempt_id)
        current = resolution_of(attempt)
        if current.get("outcome") != REQUESTING:                           # finance resolved it meanwhile: do not overwrite
            return attempt, current.get("outcome", "")
        if not_sent:
            extra = dict(attempt.provider_extra or {})
            extra.pop(RESOLUTION_KEY, None)                                # release: the refund can be requested again
            attempt.provider_extra = extra
            attempt.save(update_fields=["provider_extra", "updated_at"])
            _audit(kind, attempt, "refund_not_sent", actor, detail=detail)
        else:
            _store_resolution(
                attempt, outcome=outcome, reason=current.get("reason", ""), by=current.get("by"), key=key,
                at=timezone.now().isoformat(timespec="seconds"), provider_refund_id=refund_id, detail=detail[:120],
            )
            _audit(kind, attempt, "refund_requested", actor, outcome=outcome, reason=current.get("reason", ""))
    if not_sent:                                                           # raised OUTSIDE the transaction so the release commits
        raise DuplicatePaymentError("درخواستِ بازپرداخت به درگاه انجام نشد؛ هیچ تغییری اعمال نشد.")
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


def recover_stale_requests(*, now=None, older_than=None) -> int:
    """A duplicate-payment refund still ``requesting`` long after its intent means the process died around the provider call, so
    the outcome is ambiguous: mark it ``unknown`` for finance. NEVER calls the provider; idempotent. Returns how many were marked."""
    from datetime import datetime, timedelta

    now = now or timezone.now()
    older_than = older_than or timedelta(minutes=10)
    marked = 0
    for kind in ("subscription", "sms"):
        model = attempt_model(kind)
        for pk in list(model.objects.filter(status=model.Status.REQUIRES_ACTION).values_list("pk", flat=True)):
            with transaction.atomic():
                attempt = model.objects.select_for_update().select_related("store").get(pk=pk)
                current = resolution_of(attempt)
                if current.get("outcome") != REQUESTING:
                    continue
                try:
                    started = datetime.fromisoformat(current.get("at", ""))
                except ValueError:
                    started = None
                if started is not None and timezone.is_naive(started):
                    started = timezone.make_aware(started)
                if started is not None and started > now - older_than:
                    continue
                _store_resolution(attempt, **{**current, "outcome": UNKNOWN, "detail": "stale_intent"})
                _audit(kind, attempt, "refund_outcome_unknown", None, reason="stale_intent")
                marked += 1
    return marked
