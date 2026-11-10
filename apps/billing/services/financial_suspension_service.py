"""F-08: what a FULL refund does to the subscription it funded, and how that is undone.

Rules (approved by finance):
* A full refund of the period that is IN FORCE now suspends the subscription (a "financial suspension"), unless another settled,
  non-refunded invoice of the same subscription also funds the present. Nothing is deleted: stores, products, orders and customers
  stay untouched (SUSPENDED only restricts growth, see ``entitlement_service._STATE_POLICY``).
* A full refund of a PAST period changes nothing. A full refund of a FUTURE (already paid) period changes nothing now; that period
  stays paid and the scheduled evaluator restores the subscription automatically when it begins.
* A partial refund changes nothing (this module is only called when the invoice became ``REFUNDED``).
* When the funded period of the refunded invoice cannot be determined (legacy data without the metadata recorded at fulfilment),
  nothing is revoked automatically: an audit entry asks finance to review. Never guess in the direction of taking service away.
* Only a platform superuser can reinstate a financially suspended subscription by hand (reason mandatory, fully audited).
  No Permission row/migration is needed: the named permission is checked with ``has_perm`` (superusers hold every permission).

The funded period is recorded at fulfilment in the metadata of the ``invoice-<pk>`` subscription event
(``confirmation_service.funded_period_metadata``); a financial suspension is the ``suspended`` event with
``metadata["kind"] == "financial"`` (``subscription_service.financial_suspension_event``). No schema change."""

import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc

logger = logging.getLogger("billing")

REINSTATE_PERMISSION = "billing.reinstate_financial_suspension"
S = StoreSubscription.Status
SETTLED_STATUSES = (SubscriptionInvoice.Status.PAID, SubscriptionInvoice.Status.PARTIALLY_REFUNDED)

# outcomes of apply_refund
SUSPENDED = "suspended"
COVERED = "covered_by_other_payment"
FUTURE = "future_period_preserved"
PAST = "past_period_no_change"
NOT_A_PERIOD = "funds_no_period"
UNDETERMINED = "review_required"
ALREADY = "already_suspended"
INACTIVE = "subscription_not_current"


class FinancialSuspensionError(Exception):
    """Shown to the platform admin."""


# ---------------------------------------------------------------------------------------------- funded periods

def _parse(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def funded_period(invoice):
    """``("period", start, end)`` (``end`` may be ``None`` = open-ended), ``("none", None, None)`` for an invoice that funds no
    period of its own (an upgrade differential), or ``("unknown", None, None)``."""
    keys = [f"invoice-{invoice.pk}", f"invoice-{invoice.pk}-activate"]
    events = SubscriptionEvent.objects.filter(subscription_id=invoice.subscription_id, idempotency_key__in=keys)
    explicit_none = False
    for event in events:
        meta = event.metadata or {}
        if meta.get("invoice_id") != invoice.pk:
            continue
        if "funded_start" in meta:
            return "period", _parse(meta.get("funded_start")), _parse(meta.get("funded_end"))
        if meta.get("funded") is False:
            explicit_none = True
    if explicit_none:
        return "none", None, None
    if invoice.kind == SubscriptionInvoice.Kind.RENEWAL and invoice.billing_period_start:
        return "period", invoice.billing_period_start, invoice.billing_period_end
    return "unknown", None, None


def _position(invoice, now):
    """Where the invoice's funded period lies relative to ``now``: current / future / past / none / unknown."""
    kind, start, end = funded_period(invoice)
    if kind != "period":
        return kind
    if start is not None and start > now:
        return "future"
    if end is not None and end <= now:
        return "past"
    return "current"


def covering_invoice(subscription, now, *, exclude_pk=None):
    """``(invoice_or_None, uncertain)``: a settled, non-fully-refunded invoice of this subscription whose funded period covers
    ``now``. ``uncertain`` is true when some other settled invoice has an undeterminable period, so coverage cannot be ruled out."""
    uncertain = False
    candidates = SubscriptionInvoice.objects.filter(
        subscription_id=subscription.pk, status__in=SETTLED_STATUSES).order_by("-pk")
    for other in candidates:
        if other.pk == exclude_pk:
            continue
        position = _position(other, now)
        if position == "current":
            return other, False
        if position == "unknown":
            uncertain = True
    return None, uncertain


# ---------------------------------------------------------------------------------------------- refund -> subscription

def _audit(subscription, invoice, refund, outcome, *, actor=None, extra=None):
    record_audit_event(
        store=subscription.store if subscription is not None else invoice.store, actor=actor,
        action_code="billing.refund_entitlement_outcome", object_type="SubscriptionInvoice", object_id=invoice.pk,
        object_label=invoice.number, request_id=f"refund-{refund.pk}-entitlement" if refund is not None else "",
        after={"outcome": outcome, "refund": getattr(refund, "pk", None), **(extra or {})},
    )


@transaction.atomic
def apply_refund(invoice, refund, *, now=None):
    """Called once an invoice has become fully ``REFUNDED``. Returns the outcome code. Idempotent."""
    now = now or timezone.now()
    subscription = StoreSubscription.objects.select_for_update().select_related("store").filter(pk=invoice.subscription_id).first()
    if subscription is None or not subscription.is_current or subscription.status in StoreSubscription.TERMINAL_STATUSES:
        _audit(subscription, invoice, refund, INACTIVE)
        return INACTIVE
    position = _position(invoice, now)
    if position == "future":
        _audit(subscription, invoice, refund, FUTURE)
        return FUTURE
    if position == "past":
        _audit(subscription, invoice, refund, PAST)
        return PAST
    if position == "none":
        _audit(subscription, invoice, refund, NOT_A_PERIOD, extra={"note": "finance review: upgrade differential refunded"})
        return NOT_A_PERIOD
    if position == "unknown":
        _audit(subscription, invoice, refund, UNDETERMINED, extra={"note": "funded period was not recorded; review manually"})
        return UNDETERMINED

    other, uncertain = covering_invoice(subscription, now, exclude_pk=invoice.pk)
    if other is not None:
        _audit(subscription, invoice, refund, COVERED, extra={"covering_invoice": other.number})
        return COVERED
    if uncertain:
        _audit(subscription, invoice, refund, UNDETERMINED, extra={"note": "another settled invoice has an unknown period"})
        return UNDETERMINED
    if subscription.status == S.SUSPENDED:
        _audit(subscription, invoice, refund, ALREADY)
        return ALREADY
    sub_svc.suspend_subscription(
        subscription, actor=refund.requested_by if refund is not None else None,
        reason="بازپرداختِ کاملِ دورهٔ جاری"[:200], idempotency_key=f"refund-{refund.pk}-revoke" if refund is not None else "",
        metadata={"kind": sub_svc.FINANCIAL_SUSPENSION_KIND, "reason": "refund_revocation", "invoice_id": invoice.pk,
                  "refund_id": getattr(refund, "pk", None)},
    )
    ent.clear_entitlement_cache()
    _audit(subscription, invoice, refund, SUSPENDED)
    return SUSPENDED


# ---------------------------------------------------------------------------------------------- automatic restoration

def evaluate_restorations(*, now=None, dry_run=False) -> dict:
    """Scheduled (called by ``evaluate_subscription_states``): restore every FINANCIALLY suspended subscription whose present is
    now funded by a settled, non-refunded invoice (typically the future period that has just begun). Idempotent; one failing
    subscription never stops the others and is reported in ``errors``. A suspension for any other reason is never touched."""
    now = now or timezone.now()
    results = {"scanned": 0, "restored": 0, "errors": []}
    for sub in StoreSubscription.objects.filter(is_current=True, status=S.SUSPENDED).select_related("store").iterator(chunk_size=200):
        if sub_svc.financial_suspension_event(sub) is None:
            continue
        results["scanned"] += 1
        covering, _uncertain = covering_invoice(sub, now)
        if covering is None:
            continue
        if dry_run:
            results["restored"] += 1
            continue
        try:
            with transaction.atomic():
                if _restore(sub, covering, now=now):
                    results["restored"] += 1
        except Exception as exc:  # noqa: BLE001 — isolate (F-04) and report; the command exits non-zero
            logger.exception("financial suspension restore failed for subscription %s", sub.pk)
            results["errors"].append({"subscription": sub.pk, "error": type(exc).__name__})
    return results


def _restore(sub, covering, *, now) -> bool:
    locked = StoreSubscription.objects.select_for_update().select_related("store").get(pk=sub.pk)
    event = sub_svc.financial_suspension_event(locked)
    if event is None:                                              # restored or changed by someone else meanwhile
        return False
    kind, start, end = funded_period(covering)
    sub_svc.resume_subscription(
        locked, actor=None, reason="آغازِ دورهٔ پرداخت‌شده"[:200], idempotency_key=f"fin-restore-{event.pk}",
        metadata={"kind": "financial_restored", "invoice_id": covering.pk, "suspension_event": event.pk},
    )
    locked.refresh_from_db()
    if kind == "period" and (locked.current_period_end is None or (end is not None and locked.current_period_end < end)):
        locked.current_period_start, locked.current_period_end = start, end
        locked.save(update_fields=["current_period_start", "current_period_end", "updated_at"])
    ent.clear_entitlement_cache()
    record_audit_event(
        store=locked.store, action_code="billing.financial_suspension_restored", object_type="StoreSubscription",
        object_id=locked.pk, object_label=covering.number, request_id=f"fin-restore-{event.pk}",
        after={"invoice": covering.number},
    )
    return True


# ---------------------------------------------------------------------------------------------- manual reinstatement

def can_reinstate(user) -> bool:
    return bool(user is not None and user.is_authenticated and user.is_active and user.is_staff and user.is_superuser
                and user.has_perm(REINSTATE_PERMISSION))


@transaction.atomic
def reinstate(subscription, *, actor, reason, now=None):
    """Platform-superuser-only: lift a FINANCIAL suspension by hand. The reason is mandatory; actor, reason, time and
    subscription are recorded (``SubscriptionEvent`` + store audit log). Idempotent: repeating it after success is a no-op."""
    now = now or timezone.now()
    if not can_reinstate(actor):
        raise FinancialSuspensionError("فقط مدیرِ ارشدِ پلتفرم می‌تواند تعلیقِ مالی را رفع کند.")
    reason = (reason or "").strip()
    if len(reason) < 6:
        raise FinancialSuspensionError("ثبتِ دلیل (حداقل ۶ نویسه) الزامی است.")
    locked = StoreSubscription.objects.select_for_update().select_related("store").get(pk=subscription.pk)
    event = sub_svc.financial_suspension_event(locked)
    if event is None:
        last = locked.events.filter(event_type=SubscriptionEvent.EventType.RESUMED).order_by("-pk").first()
        if locked.status != S.SUSPENDED and last is not None and (last.metadata or {}).get("kind") == "financial_reinstated":
            return locked                                           # a repeat of a completed reinstatement
        raise FinancialSuspensionError("این اشتراک در تعلیقِ مالی نیست.")
    sub_svc.resume_subscription(
        locked, actor=actor, reason=reason[:200], idempotency_key=f"fin-reinstate-{event.pk}",
        metadata={"kind": "financial_reinstated", "suspension_event": event.pk, "actor_id": actor.pk,
                  "reason": reason[:300], "at": now.isoformat(timespec="seconds")},
    )
    locked.refresh_from_db()
    ent.clear_entitlement_cache()
    record_audit_event(
        store=locked.store, actor=actor, action_code="billing.financial_suspension_reinstated", object_type="StoreSubscription",
        object_id=locked.pk, object_label=locked.store.name, request_id=f"fin-reinstate-{event.pk}",
        after={"status": locked.status, "current_period_end": str(locked.current_period_end)},
        metadata={"reason": reason[:300], "suspension_event": event.pk},
    )
    return locked
