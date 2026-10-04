"""job دوره‌ایِ کمپین‌ها/مناسبت‌ها/اعلان‌ها — با cron اجرا شود (مثلاً هر ساعت یا
هر روز صبح): کمپین‌هایِ زمان‌بندی‌شده و مناسبتی را اجرا، یادآوریِ انقضا را صف و
(اختیاری) اعلان‌هایِ صف را ارسال می‌کند. اجرایِ مکرر امن (idempotent) است."""

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.engagement.services.campaign_service import run_due_campaigns
from apps.notifications.services.notification_service import deliver_pending

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "کمپین‌هایِ زمان‌بندی‌شده و مناسبتی را اجرا می‌کند و اعلان‌هایِ صف را ارسال می‌کند."

    def add_arguments(self, parser):
        parser.add_argument("--no-deliver", action="store_true", help="فقط صف کن؛ ارسالِ اعلان‌ها را به process_notification_outbox بسپار.")
        parser.add_argument("--limit", type=int, default=500, help="سقفِ اعلان‌هایِ ارسالی در این اجرا.")

    def handle(self, *args, **options):
        from apps.core.job_lock import single_instance

        with single_instance("run_engagement_jobs") as acquired:
            if not acquired:
                self.stdout.write("skipped: another run_engagement_jobs is still running")
                return
            failed = self._run(options)
        if failed:  # همه‌ی کارها تمام شد؛ فقط وضعیتِ خروج برایِ پایش غیرصفر می‌شود
            raise CommandError(failed)

    def _run(self, options) -> str:
        problems = []
        try:
            summary = run_due_campaigns()
        except Exception as exc:  # noqa: BLE001 — شکستِ کمپین‌ها نباید ارسالِ صف را متوقف کند
            logger.exception("run_due_campaigns failed")
            summary = None
            problems.append(f"run_due_campaigns: {type(exc).__name__}")
        if summary is not None:
            self.stdout.write(self.style.SUCCESS(
                f"کمپین‌هایِ اجراشده: {summary['campaigns']} — کدهایِ صادرشده: {summary['issued']} — "
                f"خطا: {summary['errors']} — منقضی: {summary['expired']} — یادآوری: {summary.get('reminders', 0)}"
            ))
            if summary["errors"]:
                problems.append(f"{summary['errors']} campaign/issuance error(s)")
        if not options["no_deliver"]:
            result = deliver_pending(limit=options["limit"])
            self.stdout.write(self.style.SUCCESS(
                f"اعلان‌ها — پردازش: {result['processed']}، ارسال‌شده: {result['sent']}، "
                f"ناموفق: {result['failed']}، ردشده: {result.get('skipped', 0)}"
            ))
            if result["failed"] and not result["sent"]:
                problems.append(f"all {result['failed']} notification deliveries failed")
        return "; ".join(problems)
