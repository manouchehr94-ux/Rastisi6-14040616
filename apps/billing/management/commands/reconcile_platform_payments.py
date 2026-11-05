"""تطبیقِ پرداخت‌هایِ پلتفرم (اشتراک + بسته‌ی پیامک) که کاربر پس از پرداخت به سایت برنگشته است.

برای هر تلاشِ ``created/pending`` که جلسه‌یِ درگاه دارد و از ``--min-age-minutes`` قدیمی‌تر (و از
``--max-age-hours`` جدیدتر) است، verify سرور-به-سرور انجام می‌دهد. اگر درگاه پرداخت را تأیید کند، همان
مسیرِ کانونیکِ تأیید (قفل، idempotent، یک‌بار) اعمال می‌شود؛ هیچ موفقیتِ جعلی/دستی ساخته نمی‌شود و هیچ
تلاشِ نامشخصی «ناموفق» علامت نمی‌خورد. امنِ اجرای مکرر (cron هر ۱۰ دقیقه). ``--dry-run`` فقط می‌شمارد."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.providers.base import BillingProviderError
from apps.billing.services import payment_flow_service, sms_purchase_payment_service
from apps.billing.services.confirmation_service import ConfirmationError
from apps.sms.models import SmsPackagePaymentAttempt


class Command(BaseCommand):
    help = "Verify stale pending platform payments (subscription + SMS packages) server-to-server; idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--min-age-minutes", type=int, default=10)
        parser.add_argument("--max-age-hours", type=int, default=72)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        now = timezone.now()
        newest = now - timedelta(minutes=opts["min_age_minutes"])
        oldest = now - timedelta(hours=opts["max_age_hours"])
        counts = {"checked": 0, "confirmed": 0, "still_pending": 0, "errors": 0}

        jobs = (
            (SubscriptionPaymentAttempt, payment_flow_service.confirm_from_provider_verification),
            (SmsPackagePaymentAttempt, sms_purchase_payment_service.verify_and_fulfill),
        )
        for model, verify in jobs:
            S = model.Status
            queryset = (
                model.objects.filter(status__in=(S.CREATED, S.PENDING), created_at__lt=newest, created_at__gte=oldest)
                .exclude(provider_session_id="").order_by("created_at")
            )
            for attempt in queryset.iterator():
                counts["checked"] += 1
                if opts["dry_run"]:
                    continue
                try:
                    result = verify(attempt)
                except (BillingProviderError, ConfirmationError, sms_purchase_payment_service.SmsPaymentConfirmationError) as exc:
                    counts["errors"] += 1
                    self.stderr.write(f"{model.__name__}#{attempt.pk}: {getattr(exc, 'code', '') or type(exc).__name__}")
                    continue
                if result.status == S.SUCCEEDED:
                    counts["confirmed"] += 1
                else:
                    counts["still_pending"] += 1
        self.stdout.write(
            "reconcile_platform_payments: checked=%(checked)d confirmed=%(confirmed)d "
            "still_pending=%(still_pending)d errors=%(errors)d%(dry)s" % {**counts, "dry": " (dry-run)" if opts["dry_run"] else ""}
        )
