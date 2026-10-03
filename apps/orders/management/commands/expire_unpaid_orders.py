"""سفارش‌هایِ آنلاینِ پرداخت‌نشده‌ی منقضی را لغو می‌کند (موجودی و ظرفیتِ کد برمی‌گردد).

قابل اجرا دوره‌ای (cron، مثلاً هر ۵–۱۰ دقیقه — ADR-49). فقط فروشگاه‌هایی که
``unpaid_online_order_ttl_minutes > 0`` دارند؛ پیش‌فرض همه ۰ (غیرفعال). idempotent."""

from django.core.management.base import BaseCommand, CommandError

from apps.orders.services.order_expiry_service import expire_unpaid_orders


class Command(BaseCommand):
    help = "Cancel expired unpaid ONLINE orders (per-store TTL; disabled by default; COD never expires)."

    def add_arguments(self, parser):
        parser.add_argument("--store", help="slug of a single store")
        parser.add_argument("--dry-run", action="store_true", help="report only; change nothing")
        parser.add_argument("--batch-size", type=int, default=200)

    def handle(self, *args, **opts):
        store = None
        if opts["store"]:
            from apps.stores.models import Store

            try:
                store = Store.objects.get(slug=opts["store"])
            except Store.DoesNotExist as exc:
                raise CommandError(f"unknown store {opts['store']}") from exc
        from apps.core.job_lock import single_instance

        with single_instance("expire_unpaid_orders") as acquired:
            if not acquired:
                self.stdout.write("skipped: another expire_unpaid_orders is still running")
                return
            stats = expire_unpaid_orders(store=store, dry_run=opts["dry_run"], batch_size=opts["batch_size"])
        skipped = " ".join(f"{k}={v}" for k, v in sorted(stats["skipped"].items()))
        verb = "would_expire" if opts["dry_run"] else "expired"
        self.stdout.write(
            f"candidates={stats['candidates']} {verb}={stats['expired']} errors={stats['errors']} skipped: {skipped or '-'}"
        )
        if stats["errors"]:  # بقیه‌ی سفارش‌ها پردازش شدند؛ فقط خروج برایِ پایش غیرصفر است
            raise CommandError(f"{stats['errors']} order(s) failed to expire; see logs")
