"""چرخه‌ی Dunning را رویِ فاکتورهایِ معوق اجرا می‌کند (ADR-79).

idempotent و batch-safe؛ فاکتورِ پرداخت‌شده/باطل را Retry نمی‌کند. باید از یک
زمان‌بندِ خارجی (cron) اجرا شود (بدونِ صفِ کار — ADR-49)."""

from django.core.management.base import BaseCommand, CommandError

from apps.billing.services.dunning_service import process_dunning
from apps.stores.models import Store


class Command(BaseCommand):
    help = "چرخه‌ی Dunning را رویِ فاکتورهایِ معوق پیش می‌برد."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش، بدونِ تغییر.")
        parser.add_argument("--store", default=None, help="فقط این اسلاگِ فروشگاه.")

    def handle(self, *args, **options):
        store = None
        if options["store"]:
            store = Store.objects.filter(slug=options["store"]).first()
            if store is None:
                self.stderr.write(self.style.ERROR(f"فروشگاهی با اسلاگِ «{options['store']}» یافت نشد."))
                return
        result = process_dunning(store=store, dry_run=options["dry_run"])
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}بررسی‌شده={result['scanned']}, پیش‌رفته={result.get('advanced', 0)}, "
            f"معلق={result.get('suspended', 0)}, منتظر={result.get('waiting', 0)}, "
            f"حل‌شده={result.get('resolved', 0)}."
        ))

        if result.get("errors"):
            # The remaining rows WERE processed. A non-zero exit makes cron/run_job.sh alert, so a failing row is never silent.
            raise CommandError(f"{len(result['errors'])} item(s) failed (dunning): " + ", ".join(
                f"{list(e.values())[0]}:{e['error']}" for e in result["errors"][:10]))
