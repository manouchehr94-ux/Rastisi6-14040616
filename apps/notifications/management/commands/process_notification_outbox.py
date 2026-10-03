from django.core.management.base import BaseCommand, CommandError

from apps.core.job_lock import single_instance
from apps.notifications.services.notification_service import deliver_pending


class Command(BaseCommand):
    help = "اعلان‌هایِ در-انتظارِ صف را واقعاً ارسال می‌کند (پیامک/ایمیل؛ درون‌برنامه‌ای نیازی به ارسال ندارد)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        with single_instance("process_notification_outbox") as acquired:
            if not acquired:
                self.stdout.write("skipped: another process_notification_outbox is still running")
                return
            result = deliver_pending(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(
            f"{result['processed']} اعلان پردازش شد — {result['sent']} ارسال‌شده، {result['failed']} ناموفق، "
            f"{result.get('skipped', 0)} ردشده (رضایت)."
        ))
        if result["failed"] and not result["sent"]:  # کلِ دسته شکست خورده (مثلاً ارائه‌دهنده از کار افتاده) ⇒ هشدارِ پایش
            raise CommandError(f"all {result['failed']} deliveries in this batch failed")
