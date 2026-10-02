"""job دوره‌ایِ کمپین‌ها/مناسبت‌ها/اعلان‌ها — با cron اجرا شود (مثلاً هر ساعت یا
هر روز صبح): کمپین‌هایِ زمان‌بندی‌شده و مناسبتی را اجرا، یادآوریِ انقضا را صف و
(اختیاری) اعلان‌هایِ صف را ارسال می‌کند. اجرایِ مکرر امن (idempotent) است."""

from django.core.management.base import BaseCommand

from apps.engagement.services.campaign_service import run_due_campaigns
from apps.notifications.services.notification_service import deliver_pending


class Command(BaseCommand):
    help = "کمپین‌هایِ زمان‌بندی‌شده و مناسبتی را اجرا می‌کند و اعلان‌هایِ صف را ارسال می‌کند."

    def add_arguments(self, parser):
        parser.add_argument("--no-deliver", action="store_true", help="فقط صف کن؛ ارسالِ اعلان‌ها را به process_notification_outbox بسپار.")
        parser.add_argument("--limit", type=int, default=500, help="سقفِ اعلان‌هایِ ارسالی در این اجرا.")

    def handle(self, *args, **options):
        summary = run_due_campaigns()
        self.stdout.write(self.style.SUCCESS(
            f"کمپین‌هایِ اجراشده: {summary['campaigns']} — کدهایِ صادرشده: {summary['issued']} — "
            f"خطا: {summary['errors']} — منقضی: {summary['expired']} — یادآوری: {summary.get('reminders', 0)}"
        ))
        if not options["no_deliver"]:
            result = deliver_pending(limit=options["limit"])
            self.stdout.write(self.style.SUCCESS(
                f"اعلان‌ها — پردازش: {result['processed']}، ارسال‌شده: {result['sent']}، ناموفق: {result['failed']}"
            ))
