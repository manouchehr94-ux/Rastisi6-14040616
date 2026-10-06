"""درخواست‌های صادراتِ منقضی‌شده (``ExportJob.expires_at`` گذشته) را به وضعیتِ
``expired`` تبدیل و فایلِ آن‌ها را از دیسک حذف می‌کند — نگاه کنید به ADR-52.

این کدبیس هیچ صفِ کارِ پس‌زمینه‌ای ندارد (نگاه کنید به ADR-49)، پس این دستور
باید به‌صورتِ دوره‌ای از یک زمان‌بندِ خارجی (cron/systemd timer) اجرا شود؛
خودش هیچ زمان‌بندیِ داخلی ندارد — این محدودیت اینجا صادقانه ثبت می‌شود، نه
پنهان."""

from django.core.management.base import BaseCommand

from apps.core.services.export_service import mark_expired_jobs
from apps.stores.models import Store


class Command(BaseCommand):
    help = "ExportJobهای منقضی‌شده را expired می‌کند و فایلِ آن‌ها را حذف می‌کند."

    def add_arguments(self, parser):
        parser.add_argument("--store", default=None, help="فقط این اسلاگ فروشگاه را پاک‌سازی کن")

    def handle(self, *args, **options):
        if options["store"]:
            store = Store.objects.filter(slug=options["store"]).first()
            if store is None:
                self.stderr.write(self.style.ERROR(f"فروشگاهی با اسلاگِ «{options['store']}» یافت نشد."))
                return
            total = mark_expired_jobs(store=store)
        else:
            total = 0
            for store in Store.objects.all().iterator(chunk_size=100):
                total += mark_expired_jobs(store=store)
        self.stdout.write(self.style.SUCCESS(f"{total} خروجِ اطلاعاتِ منقضی‌شده پاک‌سازی شد."))
