"""Hand refunds whose outcome is uncertain to finance (F-06). Idempotent; safe to run every few minutes (cron).

A refund (or a duplicate-payment refund) left ``requested`` / ``requesting`` long after its intent was committed means the process
died around the provider call. The provider may or may not have moved the money, so this command only MARKS such rows as unknown
outcome (the amount stays reserved). It NEVER calls a provider: a blind retry could pay the customer twice. Finance resolves each
one with a bank reference from the invoice page / reconciliation page.

It exits non-zero while any refund is waiting in the unknown state so the scheduler's alert wrapper keeps flagging it."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.billing.models import SubscriptionRefund
from apps.billing.services import duplicate_payment_service, refund_service


class Command(BaseCommand):
    help = "Mark refunds stuck in the intent state as unknown-outcome for finance review (never calls a provider)."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-minutes", type=int, default=10)

    def handle(self, *args, **opts):
        now = timezone.now()
        older = timedelta(minutes=opts["older_than_minutes"])
        marked = refund_service.recover_stale_intents(now=now, older_than=older)
        marked_dup = duplicate_payment_service.recover_stale_requests(now=now, older_than=older)
        waiting = SubscriptionRefund.objects.filter(
            status=SubscriptionRefund.Status.PENDING, failure_code=refund_service.UNKNOWN_OUTCOME).count()
        self.stdout.write(f"recover_stale_refunds: marked={marked} duplicate_marked={marked_dup} unknown_waiting={waiting}")
        if waiting:
            raise CommandError(f"{waiting} refund(s) have an unknown provider outcome and need finance review.")
