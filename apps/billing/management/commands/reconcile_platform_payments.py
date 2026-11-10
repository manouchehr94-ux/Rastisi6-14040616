"""تطبیقِ پرداخت‌هایِ پلتفرم (اشتراک + بسته‌ی پیامک) که کاربر پس از پرداخت به سایت برنگشته است.

برای هر تلاشِ ``created/pending`` که جلسه‌یِ درگاه دارد و از ``--min-age-minutes`` قدیمی‌تر (و از
``--max-age-hours`` جدیدتر) است، verify سرور-به-سرور انجام می‌دهد. اگر درگاه پرداخت را تأیید کند، همان
مسیرِ کانونیکِ تأیید (قفل، idempotent، یک‌بار) اعمال می‌شود؛ هیچ موفقیتِ جعلی/دستی ساخته نمی‌شود و هیچ
تلاشِ نامشخصی «ناموفق» علامت نمی‌خورد. امنِ اجرای مکرر (cron هر ۱۰ دقیقه). ``--dry-run`` فقط می‌شمارد."""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from apps.core.job_lock import exclusive
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import SubscriptionPaymentAttempt
from apps.billing.providers import registry
from apps.billing.providers.base import BillingProviderError
from apps.billing.services import payment_flow_service, sms_purchase_payment_service
from apps.billing.services.confirmation_service import ConfirmationError
from apps.sms.models import SmsPackagePaymentAttempt


logger = logging.getLogger("billing")


class Command(BaseCommand):
    help = "Verify stale pending platform payments (subscription + SMS packages) server-to-server; idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--min-age-minutes", type=int, default=5)
        parser.add_argument("--max-age-hours", type=int, default=72)
        parser.add_argument("--declined-max-age-hours", type=int, default=24,
                            help="Also re-verify attempts marked failed only by a browser hint (gateway_declined) newer than this.")
        parser.add_argument("--dry-run", action="store_true")

    @exclusive("reconcile_platform_payments")
    def handle(self, *args, **opts):
        now = timezone.now()
        newest = now - timedelta(minutes=opts["min_age_minutes"])
        oldest = now - timedelta(hours=opts["max_age_hours"])
        declined_oldest = now - timedelta(hours=opts["declined_max_age_hours"])
        counts = {"checked": 0, "confirmed": 0, "still_pending": 0, "errors": 0, "unexpected_errors": 0}

        jobs = (
            (SubscriptionPaymentAttempt, payment_flow_service.confirm_from_provider_verification),
            (SmsPackagePaymentAttempt, sms_purchase_payment_service.verify_and_fulfill),
        )
        for model, verify in jobs:
            S = model.Status
            # Pending attempts, plus attempts failed ONLY by an unauthenticated browser hint: the gateway may have settled
            # them afterwards (F-01). Provider-decided failures stay final and are not re-checked.
            queryset = (
                model.objects.filter(
                    Q(status__in=(S.CREATED, S.PENDING), created_at__gte=oldest)
                    | Q(status=S.FAILED, failure_code="gateway_declined", created_at__gte=declined_oldest),
                    created_at__lt=newest,
                )
                .exclude(provider_session_id="").exclude(provider__in=registry.MANUAL_PROVIDER_CODES).order_by("created_at")
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
                except Exception as exc:  # noqa: BLE001 — one bad row must not stop the others (F-04); it is logged and fails the run
                    counts["unexpected_errors"] += 1
                    logger.exception("reconcile_platform_payments: unexpected error on %s#%s", model.__name__, attempt.pk)
                    self.stderr.write(f"{model.__name__}#{attempt.pk}: UNEXPECTED {type(exc).__name__}")
                    continue
                if result.status == S.SUCCEEDED:
                    counts["confirmed"] += 1
                else:
                    counts["still_pending"] += 1
        self.stdout.write(
            "reconcile_platform_payments: checked=%(checked)d confirmed=%(confirmed)d "
            "still_pending=%(still_pending)d errors=%(errors)d unexpected_errors=%(unexpected_errors)d%(dry)s"
            % {**counts, "dry": " (dry-run)" if opts["dry_run"] else ""}
        )
        if counts["unexpected_errors"]:
            # All remaining rows WERE processed; the non-zero exit makes cron/run_job.sh alert instead of hiding the failure.
            raise CommandError(f"{counts['unexpected_errors']} attempt(s) failed unexpectedly; see the billing log.")
