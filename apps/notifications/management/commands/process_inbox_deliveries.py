from django.core.management.base import BaseCommand

from apps.core.job_lock import single_instance
from apps.notifications.services.channel_delivery import deliver_pending


class Command(BaseCommand):
    help = "تحویلِ کانال‌هایِ بیرونیِ اعلانِ مدیران (Web Push/ایمیل/موبایل) — با پرچم‌هایِ خاموش هیچ‌چیز ارسال نمی‌شود؛ ردیف‌هایِ مربوط «ارسال‌نشده» می‌شوند."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options):
        with single_instance("process_inbox_deliveries") as acquired:
            if not acquired:
                self.stdout.write("skipped: another process_inbox_deliveries is still running")
                return
            result = deliver_pending(limit=options["limit"])
        self.stdout.write(f"{result['processed']} processed — {result['delivered']} delivered, {result['failed']} failed, {result['skipped']} skipped")
