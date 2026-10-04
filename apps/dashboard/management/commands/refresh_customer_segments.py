"""عضویتِ محقق‌شده‌یِ همه‌یِ سگمنت‌هایِ ``dynamic`` را تازه‌سازی می‌کند —
Store-safe و batch-safe (نگاه کنید به ADR-53).

مانندِ ``cleanup_expired_exports``، این کدبیس هیچ صفِ کارِ پس‌زمینه‌ای ندارد
(ADR-49)، پس این دستور باید به‌صورتِ دوره‌ای از یک زمان‌بندِ خارجی
(cron/systemd timer) اجرا شود — این محدودیت اینجا صادقانه ثبت می‌شود."""

from django.core.management.base import BaseCommand, CommandError

from apps.core.job_lock import single_instance

from apps.customers.models import CustomerSegment
from apps.dashboard.services.segment_service import SegmentError, refresh_segment_membership
from apps.stores.models import Store


class Command(BaseCommand):
    help = "عضویتِ همه‌ی سگمنت‌هایِ dynamic (فعال) را تازه‌سازی می‌کند."

    def add_arguments(self, parser):
        parser.add_argument("--store", default=None, help="فقط این اسلاگ فروشگاه را تازه‌سازی کن")

    def handle(self, *args, **options):
        segments = CustomerSegment.objects.filter(
            segment_type=CustomerSegment.SegmentType.DYNAMIC, is_active=True,
        ).select_related("store")
        if options["store"]:
            store = Store.objects.filter(slug=options["store"]).first()
            if store is None:
                self.stderr.write(self.style.ERROR(f"فروشگاهی با اسلاگِ «{options['store']}» یافت نشد."))
                return
            segments = segments.filter(store=store)

        with single_instance("refresh_customer_segments") as acquired:
            if not acquired:
                self.stdout.write("skipped: another refresh_customer_segments is still running")
                return
            refreshed, failed = 0, 0
            for segment in segments.iterator(chunk_size=100):
                try:
                    refresh_segment_membership(segment)
                    refreshed += 1
                except Exception as exc:  # noqa: BLE001 — یک سگمنت خراب بقیه را متوقف نمی‌کند
                    failed += 1
                    self.stderr.write(self.style.WARNING(f"سگمنتِ «{segment.name}» ({segment.store.slug}): {exc}"))

            self.stdout.write(self.style.SUCCESS(f"{refreshed} سگمنت تازه‌سازی شد، {failed} مورد ناموفق."))
        if failed:
            raise CommandError(f"{failed} segment(s) failed to refresh")
