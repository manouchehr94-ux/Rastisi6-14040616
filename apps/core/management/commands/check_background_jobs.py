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
    ).exclude(metadata__has_key="legacy_sms_log_id")
    oldest = deliverable.order_by("created_at").values_list("created_at", flat=True).first()
    age = (now - oldest) if oldest else timedelta(0)
    level = CRIT if age > timedelta(hours=2) else WARN if age > timedelta(minutes=30) else OK
    add("notification_backlog", level, f"deliverable={deliverable.count()} oldest_age_min={int(age.total_seconds() // 60)}")
    stuck = N.objects.filter(status=N.Status.SENDING, claimed_at__lt=now - timedelta(minutes=30)).count()
    add("notification_stuck_sending", WARN if stuck else OK, f"stuck={stuck}")
    dead = N.objects.filter(status=N.Status.DEAD, updated_at__gte=now - timedelta(hours=24)).count()
    add("notification_dead_24h", WARN if dead else OK, f"dead={dead}")

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
    return checks


class Command(BaseCommand):
    help = "Read-only health check of cron-driven background jobs (exit 0 OK / 1 WARNING / 2 CRITICAL)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        checks = collect()
        worst = max((_RANK[c["level"]] for c in checks), default=0)
        if opts["json"]:
            self.stdout.write(json.dumps({"status": [OK, WARN, CRIT][worst], "checks": checks}, ensure_ascii=False))
        else:
            for c in checks:
                self.stdout.write(f"{c['level']:8} {c['check']:34} {c['detail']}")
            self.stdout.write(f"overall: {[OK, WARN, CRIT][worst]}")
        if worst:
            raise SystemExit(worst)
