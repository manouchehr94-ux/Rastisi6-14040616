"""فاکتورِ تمدید برایِ اشتراک‌هایِ نزدیک به پایانِ دوره تولید می‌کند (ADR-78).

idempotent و batch-safe؛ باید از یک زمان‌بندِ خارجی (cron) اجرا شود چون این
کدبیس صفِ کارِ پس‌زمینه‌ای ندارد (ADR-49)."""

from django.core.management.base import BaseCommand, CommandError

from apps.billing.services.renewal_service import generate_renewals
from apps.stores.models import Store


class Command(BaseCommand):
    help = "فاکتورِ تمدید برایِ اشتراک‌هایِ نزدیک به پایانِ دوره می‌سازد (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="فقط گزارش، بدونِ ساخت.")
        parser.add_argument("--store", default=None, help="فقط این اسلاگِ فروشگاه.")
        parser.add_argument("--lead-days", type=int, default=None, help="چند روز پیش از پایانِ دوره.")

    def handle(self, *args, **options):
        store = None
        if options["store"]:
            store = Store.objects.filter(slug=options["store"]).first()
            if store is None:
                self.stderr.write(self.style.ERROR(f"فروشگاهی با اسلاگِ «{options['store']}» یافت نشد."))
                return
        result = generate_renewals(store=store, lead_days=options["lead_days"], dry_run=options["dry_run"])
        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}بررسی‌شده={result['scanned']}, "
            f"ساخته‌شده={result['created']}, موجود={result['skipped_existing']}."
        ))

        if result.get("errors"):
            # The remaining rows WERE processed. A non-zero exit makes cron/run_job.sh alert, so a failing row is never silent.
            raise CommandError(f"{len(result['errors'])} item(s) failed (renewals): " + ", ".join(
                f"{list(e.values())[0]}:{e['error']}" for e in result["errors"][:10]))
