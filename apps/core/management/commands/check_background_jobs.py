"""Read-only health check of the cron-driven background jobs (ADR-49), derived from the data the jobs
themselves maintain — no heartbeat table, no scheduler. Monitoring-friendly (Nagios-style exit code):

  0 = OK, 1 = WARNING, 2 = CRITICAL.   ``--json`` for machine output.

Detects "the cron job is not running / is failing" as symptoms: notification backlog age, claims
stuck in SENDING, dead deliveries, failed campaign runs, expired-but-unreleased inventory
reservations, unpaid online orders overdue for expiry, and open payment reconciliations."""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import F
from django.utils import timezone

OK, WARN, CRIT = "OK", "WARNING", "CRITICAL"
_RANK = {OK: 0, WARN: 1, CRIT: 2}


def collect(now=None) -> list[dict]:
    from apps.catalog.models import InventoryReservation
    from apps.core.models import ShopSettings
    from apps.engagement.models import CampaignRun
    from apps.notifications.models import NotificationOutbox as N
    from apps.orders.models import Order, PaymentReconciliation

    now = now or timezone.now()
    checks = []

    def add(name, level, detail):
        checks.append({"check": name, "level": level, "detail": detail})

    # ۱) صفِ اعلان — process_notification_outbox / run_engagement_jobs (هر ۵ دقیقه)
    deliverable = N.objects.filter(
        status__in=(N.Status.PENDING, N.Status.FAILED), sms_log__isnull=True, attempts__lt=F("max_attempts"),
    ).exclude(metadata__has_key="legacy_sms_log_id").filter(held_since__isnull=True)
    # rows HELD for an inactive e-mail sender / rate limit are waiting on a *business* condition, not on the cron job: they
    # are reported separately below, so one broken store sender can never look like "the delivery cron is dead".
    oldest = deliverable.order_by("created_at").values_list("created_at", flat=True).first()
    age = (now - oldest) if oldest else timedelta(0)
    level = CRIT if age > timedelta(hours=2) else WARN if age > timedelta(minutes=30) else OK
    add("notification_backlog", level, f"deliverable={deliverable.count()} oldest_age_min={int(age.total_seconds() // 60)}")
    stuck = N.objects.filter(status=N.Status.SENDING, claimed_at__lt=now - timedelta(minutes=30)).count()
    add("notification_stuck_sending", WARN if stuck else OK, f"stuck={stuck}")
    dead = N.objects.filter(status=N.Status.DEAD, updated_at__gte=now - timedelta(hours=24)).count()
    add("notification_dead_24h", WARN if dead else OK, f"dead={dead}")
    held = N.objects.filter(status=N.Status.PENDING, held_since__isnull=False)
    held_oldest = held.order_by("held_since").values_list("held_since", flat=True).first()
    held_age_h = int(((now - held_oldest).total_seconds() // 3600)) if held_oldest else 0
    add("email_held", WARN if held.exists() else OK, f"held={held.count()} oldest_age_h={held_age_h} (sender inactive / rate limit)")
    expired = N.objects.filter(status=N.Status.EXPIRED, is_promotional=False, updated_at__gte=now - timedelta(hours=24)).count()
    add("notification_expired_24h", WARN if expired else OK, f"expired_transactional={expired}")
    from apps.notifications.models import EmailSenderIdentity as E

    broken = E.objects.filter(status=E.Status.ERROR, platform_disabled=False).count()
    add("email_sender_errors", WARN if broken else OK, f"identities_in_error={broken}")
    overdue_checks = E.objects.filter(platform_disabled=False, next_check_at__lt=now - timedelta(hours=3)).exclude(
        status=E.Status.INACTIVE).count()
    add("email_sender_revalidation", WARN if overdue_checks else OK,
        f"identities_overdue_for_recheck={overdue_checks} (is `refresh_email_identities` scheduled?)")

    # ۲) کمپین‌ها — run_engagement_jobs
    bad_runs = CampaignRun.objects.filter(started_at__gte=now - timedelta(hours=24), errors__gt=0).count()
    add("campaign_run_errors_24h", WARN if bad_runs else OK, f"runs_with_errors={bad_runs}")

    # ۳) رزروِ موجودی — expire_inventory_reservations
    overdue_res = InventoryReservation.objects.filter(
        status=InventoryReservation.Status.ACTIVE, expires_at__lt=now - timedelta(minutes=15),
    ).count()
    add("inventory_reservations_overdue", WARN if overdue_res else OK, f"overdue={overdue_res}")

    # ۴) انقضای سفارش — expire_unpaid_orders (فقط فروشگاه‌هایِ دارایِ TTL)
    enabled = ShopSettings.objects.filter(unpaid_online_order_ttl_minutes__gt=0).select_related("store")
    if not enabled:
        add("order_expiry", OK, "disabled for all stores (ttl=0)")
    for shop in enabled:
        limit = timedelta(minutes=shop.unpaid_online_order_ttl_minutes + shop.unpaid_online_order_grace_minutes + 30)
        overdue = Order.objects.filter(
            store=shop.store, status=Order.Status.PENDING, payment_status=Order.PaymentStatus.PENDING,
            created_at__lt=now - limit,
        ).count()  # شاملِ COD و رد‌شده‌ها ⇒ فقط راهنما (WARN نه CRIT)
        add(f"order_expiry:{shop.store.slug}", WARN if overdue else OK, f"pending_older_than_ttl+grace={overdue}")

    # ۵) تطبیق پرداخت — نیازمندِ اقدامِ انسانی
    open_rec = PaymentReconciliation.objects.filter(status=PaymentReconciliation.Status.OPEN)
    old_rec = open_rec.filter(created_at__lt=now - timedelta(hours=24)).count()
    add("payment_reconciliation_open", CRIT if old_rec else WARN if open_rec.exists() else OK,
        f"open={open_rec.count()} older_than_24h={old_rec}")
    checks.extend(collect_billing(now))
    return checks


def collect_billing(now) -> list[dict]:
    """Platform billing jobs (F-03). Like the rest of this module the checks are SYMPTOMS in the data the jobs maintain, so «the
    cron entry is missing / not running / failing» is visible without a heartbeat table. Read-only."""
    from django.db.models import Q

    from apps.billing.models import (
        BillingWebhookEvent, PlatformManualPaymentClaim, SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund,
    )
    from apps.billing.providers.registry import MANUAL_PROVIDER_CODES
    from apps.billing.services import financial_suspension_service as fss
    from apps.billing.services import refund_service
    from apps.sms.models import SmsPackagePaymentAttempt
    from apps.subscriptions.models import StoreSubscription
    from apps.subscriptions.services import subscription_service as sub_svc

    checks = []

    def add(name, level, detail):
        checks.append({"check": name, "level": level, "detail": detail})

    def graded(name, count, oldest, warn_after, crit_after, hint):
        age = (now - oldest) if oldest else timedelta(0)
        level = OK if not count else CRIT if age > crit_after else WARN if age > warn_after else OK
        add(name, level, f"count={count} oldest_age_min={int(age.total_seconds() // 60)} ({hint})")

    # online attempts waiting for the bank's answer -> reconcile_platform_payments (every 10 min)
    stale_total, stale_oldest = 0, None
    for model in (SubscriptionPaymentAttempt, SmsPackagePaymentAttempt):
        S = model.Status
        qs = model.objects.filter(status__in=(S.CREATED, S.PENDING), created_at__lt=now - timedelta(minutes=30)).exclude(
            provider_session_id="").exclude(provider__in=list(MANUAL_PROVIDER_CODES))
        stale_total += qs.count()
        first = qs.order_by("created_at").values_list("created_at", flat=True).first()
        if first and (stale_oldest is None or first < stale_oldest):
            stale_oldest = first
    graded("billing_stale_attempts", stale_total, stale_oldest, timedelta(minutes=30), timedelta(hours=3),
           "is `reconcile_platform_payments` scheduled?")

    # money received but not applied: parked for finance (requires_action)
    parked, parked_oldest = 0, None
    for model in (SubscriptionPaymentAttempt, SmsPackagePaymentAttempt):
        qs = model.objects.filter(status=model.Status.REQUIRES_ACTION)
        parked += qs.count()
        first = qs.order_by("updated_at").values_list("updated_at", flat=True).first()
        if first and (parked_oldest is None or first < parked_oldest):
            parked_oldest = first
    graded("billing_requires_action", parked, parked_oldest, timedelta(hours=24), timedelta(hours=72),
           "confirmed payments awaiting finance: refund / allocate")

    stuck_inv = SubscriptionInvoice.objects.filter(
        status=SubscriptionInvoice.Status.PAYMENT_PENDING, updated_at__lt=now - timedelta(hours=24))
    graded("billing_payment_pending_invoices", stuck_inv.count(), stuck_inv.order_by("updated_at").values_list("updated_at", flat=True).first(),
           timedelta(hours=24), timedelta(hours=72), "invoice payment_pending > 24h")

    # webhooks -> reprocess_billing_webhooks (every 5 min)
    P = BillingWebhookEvent.ProcessingStatus
    wh = BillingWebhookEvent.objects.filter(signature_valid=True).filter(
        Q(processing_status=P.RECEIVED, created_at__lt=now - timedelta(minutes=15)) | Q(processing_status=P.FAILED, retry_count__lt=5))
    graded("billing_webhooks_stuck", wh.count(), wh.order_by("created_at").values_list("created_at", flat=True).first(),
           timedelta(minutes=15), timedelta(hours=2), "is `reprocess_billing_webhooks` scheduled?")
    dead = BillingWebhookEvent.objects.filter(signature_valid=True, processing_status=P.FAILED, retry_count__gte=5).count()
    add("billing_webhooks_exhausted", CRIT if dead else OK, f"failed_after_max_retries={dead} (needs a person)")

    # subscription state machine -> evaluate_subscription_states (hourly)
    S = StoreSubscription.Status
    lag = timedelta(hours=2)
    overdue = StoreSubscription.objects.filter(is_current=True).filter(
        Q(status=S.TRIALING, trial_end_at__lt=now - lag) | Q(status=S.GRACE_PERIOD, grace_period_end__lt=now - lag)
        | Q(status__in=(S.ACTIVE, S.PAST_DUE), current_period_end__lt=now - lag))
    due_dates = []
    for trial_end, grace_end, period_end in overdue.values_list("trial_end_at", "grace_period_end", "current_period_end"):
        due_dates.append(min(d for d in (trial_end, grace_end, period_end) if d))
    oldest_due = min(due_dates, default=None)
    graded("subscription_transitions_overdue", overdue.count(), oldest_due, lag, timedelta(hours=24),
           "is `evaluate_subscription_states` scheduled?")

    # financial suspension that should already have been lifted (a paid period began) -> same evaluator
    unrestored = sum(
        1 for sub in StoreSubscription.objects.filter(is_current=True, status=S.SUSPENDED)
        if sub_svc.financial_suspension_event(sub) is not None and fss.covering_invoice(sub, now)[0] is not None)
    add("billing_financial_suspension_unrestored", CRIT if unrestored else OK,
        f"suspended_but_funded={unrestored} (evaluate_subscription_states restores these)")

    # refunds with an uncertain outcome -> recover_stale_refunds + finance
    R = SubscriptionRefund.Status
    requested = SubscriptionRefund.objects.filter(status=R.REQUESTED, created_at__lt=now - timedelta(minutes=30)).count()
    add("billing_refund_intent_stale", WARN if requested else OK, f"requested_older_than_30min={requested} (is `recover_stale_refunds` scheduled?)")
    unknown = SubscriptionRefund.objects.filter(status=R.PENDING, failure_code=refund_service.UNKNOWN_OUTCOME)
    graded("billing_refund_unknown_outcome", unknown.count(), unknown.order_by("updated_at").values_list("updated_at", flat=True).first(),
           timedelta(hours=1), timedelta(hours=24), "provider outcome unknown: reconcile with the bank, do not retry")

    # manual card claims past their review window
    claims = PlatformManualPaymentClaim.objects.filter(
        status=PlatformManualPaymentClaim.Status.PENDING_REVIEW, created_at__lt=now - timedelta(days=3)).count()
    add("billing_card_claims_waiting", WARN if claims else OK, f"pending_review_older_than_3d={claims}")
    return checks


class Command(BaseCommand):
    help = "Read-only health check of cron-driven background jobs (exit 0 OK / 1 WARNING / 2 CRITICAL)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        checks = collect()
        worst = max((_RANK[c["level"]] for c in checks), default=0)
        if worst >= 2:                                    # CRITICAL ⇒ اعلانِ فوریِ مدیرانِ پلتفرم (یک‌بار در ساعت)
            from apps.notifications.services import admin_events

            admin_events.platform_jobs_unhealthy([c["check"] for c in checks if c["level"] == CRIT])
        if opts["json"]:
            self.stdout.write(json.dumps({"status": [OK, WARN, CRIT][worst], "checks": checks}, ensure_ascii=False))
        else:
            for c in checks:
                self.stdout.write(f"{c['level']:8} {c['check']:34} {c['detail']}")
            self.stdout.write(f"overall: {[OK, WARN, CRIT][worst]}")
        if worst:
            raise SystemExit(worst)
