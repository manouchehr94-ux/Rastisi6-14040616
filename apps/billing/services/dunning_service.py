"""سیاستِ قطعیِ Dunning برایِ فاکتورهایِ معوق (ADR-79).

زمان‌بندی از ``settings.RASTISI_BILLING_DUNNING_SCHEDULE`` (روزهایِ پس از سررسید،
مثلاً «0,3,7,14»). چون Providerِ پیش‌فرض (manual) شارژِ خودکار ندارد، Dunning
به‌جایِ تلاشِ خودکار، وضعیتِ فاکتور/اشتراک را طبقِ زمان‌بندی بالا می‌برد و یک
«رکوردِ نیازمندِ Retry» (``SubscriptionDunningState``) نگه می‌دارد؛ لینکِ پرداختِ
دستی از رویِ همان فاکتور در Merchant UI در دسترس است.

مراحل: نخستین مرحله فاکتور را معوق و اشتراک را به مهلتِ ارفاقی (هشدار) می‌برد؛
مرحله‌ی پایانی اشتراک را معلق و فاکتور را وصول‌ناشدنی می‌کند. idempotent،
batch-safe، بدونِ تلاشِ تکراری (با ``next_retry_at`` کنترل می‌شود)، و هرگز
فاکتورِ پرداخت‌شده/باطل را Retry نمی‌کند."""

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.models import SubscriptionDunningState, SubscriptionInvoice
from apps.core.services.audit_service import record_audit_event
from apps.subscriptions.models import StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc
from apps.subscriptions.services.subscription_service import IllegalTransitionError

logger = logging.getLogger("billing")
ZERO = Decimal("0")
_ESCALATABLE = (
    StoreSubscription.Status.ACTIVE,
    StoreSubscription.Status.GRACE_PERIOD,
    StoreSubscription.Status.PAST_DUE,
)


def parse_schedule():
    raw = getattr(settings, "RASTISI_BILLING_DUNNING_SCHEDULE", "0,3,7,14")
    days = []
    for part in str(raw).split(","):
        part = part.strip()
        if part:
            try:
                days.append(int(part))
            except ValueError:
                continue
    return days or [0]


def _unpaid_past_due_invoices(now, store=None):
    qs = SubscriptionInvoice.objects.filter(
        status__in=(
            SubscriptionInvoice.Status.OPEN,
            SubscriptionInvoice.Status.PAYMENT_PENDING,
            SubscriptionInvoice.Status.PAST_DUE,
        ),
        amount_due__gt=ZERO, due_at__isnull=False, due_at__lte=now,
    ).select_related("subscription", "store")
    if store is not None:
        qs = qs.filter(store=store)
    return qs


@transaction.atomic
def _process_invoice(invoice, *, schedule, now):
    """یک مرحله‌ی Dunning را روی یک فاکتورِ معوق اعمال می‌کند اگر سررسید رسیده
    باشد. رشته‌ی نتیجه را برمی‌گرداند: advanced/suspended/waiting/resolved."""
    locked = SubscriptionInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status in (
        SubscriptionInvoice.Status.PAID, SubscriptionInvoice.Status.VOID,
        SubscriptionInvoice.Status.UNCOLLECTIBLE, SubscriptionInvoice.Status.REFUNDED,
        SubscriptionInvoice.Status.PARTIALLY_REFUNDED,
    ) or locked.amount_due <= ZERO:
        # پرداخت/باطل شده — Dunning را حل‌شده علامت بزن.
        SubscriptionDunningState.objects.filter(invoice=locked).update(
            status=SubscriptionDunningState.Status.RESOLVED,
        )
        return "resolved"

    state, _ = SubscriptionDunningState.objects.select_for_update().get_or_create(
        invoice=locked, defaults={"store": locked.store},
    )
    if state.status != SubscriptionDunningState.Status.ACTIVE:
        return "waiting"

    n = len(schedule)
    stage = state.stage
    # زمانِ سررسیدِ این مرحله.
    due_at = locked.due_at + timezone.timedelta(days=schedule[min(stage, n - 1)])
    if state.next_retry_at is not None:
        due_at = state.next_retry_at
    if now < due_at:
        return "waiting"

    subscription = StoreSubscription.objects.select_for_update().get(pk=locked.subscription_id)

    # مرحله‌ی نخست: فاکتور معوق، اشتراک به مهلتِ ارفاقی.
    if stage == 0:
        if locked.status in (SubscriptionInvoice.Status.OPEN, SubscriptionInvoice.Status.PAYMENT_PENDING):
            locked.status = SubscriptionInvoice.Status.PAST_DUE
            locked.save(update_fields=["status", "updated_at"])
        if subscription.status == StoreSubscription.Status.ACTIVE:
            try:
                sub_svc.enter_grace_period(subscription)
            except IllegalTransitionError:
                pass

    state.attempt_count += 1
    state.last_attempt_at = now

    if stage >= n - 1:
        # مرحله‌ی پایانی: تعلیقِ اشتراک + وصول‌ناشدنیِ فاکتور.
        if subscription.status in _ESCALATABLE:
            try:
                sub_svc.suspend_subscription(subscription, reason="پایانِ Dunning")
            except IllegalTransitionError:
                pass
        locked.status = SubscriptionInvoice.Status.UNCOLLECTIBLE
        locked.save(update_fields=["status", "updated_at"])
        state.status = SubscriptionDunningState.Status.EXHAUSTED
        state.next_retry_at = None
        outcome = "suspended"
    else:
        state.stage = stage + 1
        state.next_retry_at = locked.due_at + timezone.timedelta(days=schedule[stage + 1])
        outcome = "advanced"

    state.save()
    ent.clear_entitlement_cache()
    record_audit_event(
        store=locked.store, action_code="billing.dunning_advanced",
        object_type="SubscriptionInvoice", object_id=locked.pk, object_label=locked.number,
        metadata={"stage": stage, "outcome": outcome, "attempt_count": state.attempt_count},
    )
    return outcome


def process_dunning(*, now=None, store=None, dry_run=False) -> dict:
    """همه‌ی فاکتورهایِ معوق را طبقِ زمان‌بندی پیش می‌برد. ``dry_run`` فقط
    می‌شمارد."""
    now = now or timezone.now()
    schedule = parse_schedule()
    result = {"scanned": 0, "advanced": 0, "suspended": 0, "waiting": 0, "resolved": 0, "errors": []}
    for invoice in _unpaid_past_due_invoices(now, store=store).iterator(chunk_size=200):
        result["scanned"] += 1
        if dry_run:
            continue
        try:
            outcome = _process_invoice(invoice, schedule=schedule, now=now)   # its own transaction
        except Exception as exc:  # noqa: BLE001 — isolate the failing invoice (F-04); reported, never hidden
            logger.exception("process_dunning: invoice %s failed", invoice.pk)
            result["errors"].append({"invoice": invoice.pk, "error": type(exc).__name__})
            continue
        result[outcome] = result.get(outcome, 0) + 1
    return result
