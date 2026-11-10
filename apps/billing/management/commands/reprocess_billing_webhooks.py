"""Re-process stuck or failed billing webhook events (F-16). Idempotent, bounded and safe to run often (cron, every ~5 minutes).

A webhook can be left ``received`` (the worker died, or the provider was answered before processing finished) or ``failed`` (an
unexpected error was recorded). Reprocessing goes through ``payment_flow_service.process_webhook_event`` ->
``confirmation_service.confirm_payment`` which is locked and idempotent, so a repeat can never apply a payment twice.

Bounds: at most ``--max-retries`` attempts per event (``retry_count``), exponential backoff between attempts (2^n minutes), and a
per-run ``--limit``. One failing event never stops the others, and the run exits non-zero if any event failed unexpectedly."""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import BillingWebhookEvent
from apps.billing.services import payment_flow_service, webhook_service

logger = logging.getLogger("billing")
P = BillingWebhookEvent.ProcessingStatus


def due_events(now, *, min_age_minutes=2, max_retries=5, limit=100):
    """Events that should be (re)processed now, oldest first. Pure query; used by the command and by tests."""
    candidates = BillingWebhookEvent.objects.filter(
        Q(processing_status=P.RECEIVED, created_at__lt=now - timedelta(minutes=min_age_minutes))
        | Q(processing_status=P.FAILED, retry_count__lt=max_retries),
        signature_valid=True,
    ).order_by("created_at")
    due = []
    for event in candidates.iterator():
        backoff = timedelta(minutes=2 ** min(event.retry_count, 8)) if event.processing_status == P.FAILED else timedelta(0)
        if event.updated_at <= now - backoff:
            due.append(event)
        if len(due) >= limit:
            break
    return due


class Command(BaseCommand):
    help = "Re-process received/failed billing webhook events (idempotent, bounded retries, exponential backoff)."

    def add_arguments(self, parser):
        parser.add_argument("--min-age-minutes", type=int, default=2)
        parser.add_argument("--max-retries", type=int, default=5)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        now = timezone.now()
        counts = {"due": 0, "processed": 0, "still_failed": 0, "unexpected_errors": 0}
        for event in due_events(now, min_age_minutes=opts["min_age_minutes"], max_retries=opts["max_retries"], limit=opts["limit"]):
            counts["due"] += 1
            if opts["dry_run"]:
                continue
            try:
                result = payment_flow_service.process_webhook_event(event)
            except Exception as exc:  # noqa: BLE001 — isolate the failing event (F-04) and record it durably
                counts["unexpected_errors"] += 1
                logger.exception("reprocess_billing_webhooks: event %s failed unexpectedly", event.pk)
                webhook_service.record_unexpected_failure(event, exc)
                continue
            if result.processing_status in (P.PROCESSED, P.IGNORED):
                counts["processed"] += 1
            else:
                counts["still_failed"] += 1
        self.stdout.write("reprocess_billing_webhooks: due=%(due)d processed=%(processed)d still_failed=%(still_failed)d "
                          "unexpected_errors=%(unexpected_errors)d%(dry)s" % {**counts, "dry": " (dry-run)" if opts["dry_run"] else ""})
        if counts["unexpected_errors"]:
            raise CommandError(f"{counts['unexpected_errors']} webhook event(s) failed unexpectedly; see the billing log.")
