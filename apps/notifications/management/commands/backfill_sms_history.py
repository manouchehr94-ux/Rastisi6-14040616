"""آینه‌سازیِ تاریخچه‌ی پیامکِ قدیمیِ موجود (``SmsLog``) در تاریخچه‌ی اعلان‌ها.

idempotent؛ ``SmsLog`` را تغییر نمی‌دهد و چیزی ارسال نمی‌کند. ``--dry-run`` فقط می‌شمارد."""

from django.core.management.base import BaseCommand

from apps.notifications.services import legacy_history


class Command(BaseCommand):
    help = "Mirror historical legacy SmsLog rows into the notification history (idempotent, no sending)."

    def add_arguments(self, parser):
        parser.add_argument("--store", help="slug of a single store")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        store = None
        if opts["store"]:
            from apps.stores.models import Store

            store = Store.objects.get(slug=opts["store"])
        stats = legacy_history.backfill(
            store=store, batch_size=opts["batch_size"], dry_run=opts["dry_run"], limit=opts["limit"],
        )
        self.stdout.write(f"candidates={stats['candidates']} created={stats['created']}"
                          + (" (dry-run)" if opts["dry_run"] else ""))
