"""Resolve payment attempts whose provider settlement outcome is UNKNOWN, using the provider's AUTHORITATIVE status inquiry.

Safe to run from cron, repeatedly and concurrently (each attempt is applied under the order+attempt locks with a status re-check).
It never calls settle again, never fabricates a result, never touches an order unless the provider proves it settled, and never
fails an attempt unless the provider proves it will not complete. Attempts the provider cannot decide stay UNKNOWN and keep their
open reconciliation record for the administrative reconciliation page."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import PaymentAttempt
from apps.orders.services.gateway_payment_service import resolve_unknown_payment


class Command(BaseCommand):
    help = "Resolve UNKNOWN (verified, settlement-unproven) payment attempts via the provider status inquiry."

    def add_arguments(self, parser):
        parser.add_argument("--min-age-minutes", type=int, default=2, help="skip attempts updated more recently than this (let the in-flight request finish)")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--store", type=int, default=0, help="restrict to one store id")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=max(0, options["min_age_minutes"]))
        qs = PaymentAttempt.objects.filter(status=PaymentAttempt.Status.UNKNOWN, updated_at__lte=cutoff).order_by("updated_at", "pk")
        if options["store"]:
            qs = qs.filter(store_id=options["store"])
        counts = {"checked": 0, "paid": 0, "failed": 0, "still_unknown": 0}
        for pk in list(qs.values_list("pk", flat=True)[: max(1, options["limit"])]):
            counts["checked"] += 1
            attempt = resolve_unknown_payment(pk)
            status = getattr(attempt, "status", "")
            if status == PaymentAttempt.Status.SUCCEEDED:
                counts["paid"] += 1
            elif status in (PaymentAttempt.Status.FAILED, PaymentAttempt.Status.CANCELED):
                counts["failed"] += 1
            else:
                counts["still_unknown"] += 1
        self.stdout.write(f"reconcile_unknown_payments: {counts}")
