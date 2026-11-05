"""منقضی‌کردنِ ادعاهایِ کارت‌به‌کارتِ پلتفرم که پس از مهلت رسیدگی نشده‌اند.

هیچ اثرِ مالی ندارد (فاکتور/خریدِ پیامک همچنان قابلِ پرداخت می‌ماند) و شماره‌ی پیگیری آزاد می‌شود. امنِ اجرای مکرر (cron ساعتی).
``--dry-run`` فقط می‌شمارد."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import PlatformManualPaymentClaim
from apps.billing.services import manual_card_service


class Command(BaseCommand):
    help = "Expire stale platform card-to-card claims (no financial effect); idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if opts["dry_run"]:
            due = PlatformManualPaymentClaim.objects.filter(
                status=PlatformManualPaymentClaim.Status.PENDING_REVIEW, expires_at__lte=timezone.now(),
            ).count()
            self.stdout.write(f"due={due} expired=0 (dry-run)")
            return
        self.stdout.write(f"expired={manual_card_service.expire_stale_claims()}")
