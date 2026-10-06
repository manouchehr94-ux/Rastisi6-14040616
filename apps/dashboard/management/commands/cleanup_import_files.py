"""فایلِ منبع و گزارشِ خطایِ ``ImportJob``هایِ قدیمی را از دیسک حذف می‌کند
(بدونِ حذفِ رکوردِ Job/نتیجه‌ی ردیف‌ها) — نگاه کنید به ADR-62.

مانندِ ``cleanup_expired_exports``/``refresh_customer_segments`` (ADR-49)،
این کدبیس هیچ صفِ کارِ پس‌زمینه‌ای ندارد، پس این دستور باید به‌صورتِ دوره‌ای
از یک زمان‌بندِ خارجی (cron/systemd timer) اجرا شود."""

from django.core.management.base import BaseCommand

from apps.dashboard.services.import_service import IMPORT_FILE_RETENTION_DAYS, cleanup_import_files
from apps.stores.models import Store


class Command(BaseCommand):
    help = "فایل‌هایِ منبع/گزارشِ خطایِ ImportJobهایِ قدیمی را حذف می‌کند (رکورد حفظ می‌شود)."

    def add_arguments(self, parser):
        parser.add_argument("--store", default=None, help="فقط این اسلاگ فروشگاه را پاک‌سازی کن")
        parser.add_argument(
            "--retention-days", type=int, default=IMPORT_FILE_RETENTION_DAYS,
            help=f"فایل‌هایِ قدیمی‌تر از این تعداد روز حذف می‌شوند (پیش‌فرض {IMPORT_FILE_RETENTION_DAYS}).",
        )

    def handle(self, *args, **options):
        retention_days = options["retention_days"]
        if options["store"]:
            store = Store.objects.filter(slug=options["store"]).first()
            if store is None:
                self.stderr.write(self.style.ERROR(f"فروشگاهی با اسلاگِ «{options['store']}» یافت نشد."))
                return
            total = cleanup_import_files(store=store, retention_days=retention_days)
        else:
            total = cleanup_import_files(retention_days=retention_days)
        self.stdout.write(self.style.SUCCESS(f"فایل‌هایِ {total} ورودِ اطلاعات پاک‌سازی شد."))
