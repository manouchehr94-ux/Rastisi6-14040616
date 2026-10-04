"""تحلیلِ فقط‌خواندنیِ اثرِ تغییرِ تعریفِ سفارشِ سگمنت‌ها (G1) — قبل از هر تغییر.

برایِ هر سگمنتِ dynamic فعال، عضویتِ **ذخیره‌شده**، ارزیابیِ ``legacy`` (رفتارِ فعلی) و
ارزیابیِ ``valid`` (تعریفِ مشترکِ «سفارشِ معتبر») را مقایسه می‌کند و تعدادِ مشتریانی را
که اضافه/حذف می‌شوند گزارش می‌دهد. چیزی نمی‌نویسد/تازه‌سازی نمی‌کند."""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from apps.customers.models import CustomerSegment
from apps.dashboard.services import segment_service
from apps.orders import models as order_models
from apps.orders.services import order_definitions
from apps.stores.models import Store


class Command(BaseCommand):
    help = "Read-only impact report: segment membership under legacy vs shared 'valid order' definitions."

    def add_arguments(self, parser):
        parser.add_argument("--store", help="slug of a single store")
        parser.add_argument("--sample", type=int, default=5, help="customer ids to print per diff")

    def handle(self, *args, **opts):
        stores = Store.objects.all()
        if opts["store"]:
            stores = stores.filter(slug=opts["store"])
            if not stores:
                raise CommandError(f"unknown store {opts['store']}")
        self.stdout.write(f"active definition: {segment_service.current_definition().key}")
        total_added = total_removed = 0
        for store in stores:
            orders = order_models.Order.objects.filter(store=store)
            canceled = orders.filter(status=order_models.Order.Status.CANCELED).count()
            unpaid = orders.exclude(payment_status__in=order_definitions.DEFAULT_VALID_PAYMENT_STATUSES).count()
            by_pay = dict(orders.values_list("payment_status").annotate(n=Count("pk")))
            self.stdout.write(f"[{store.slug}] orders={orders.count()} canceled={canceled} not_valid_payment={unpaid} payment={by_pay}")
            segments = CustomerSegment.objects.filter(
                store=store, segment_type=CustomerSegment.SegmentType.DYNAMIC, is_active=True,
            ).prefetch_related("rules")
            for seg in segments:
                stored = set(seg.memberships.values_list("customer_id", flat=True))
                legacy = segment_service.evaluate_segment(seg, order_definitions.LEGACY)
                valid = segment_service.evaluate_segment(seg, order_definitions.VALID)
                added, removed = sorted(valid - legacy), sorted(legacy - valid)
                total_added += len(added)
                total_removed += len(removed)
                self.stdout.write(
                    f"  segment {seg.pk} '{seg.name}': stored={len(stored)} legacy_now={len(legacy)} valid={len(valid)} "
                    f"stale_cache_vs_legacy={len(stored ^ legacy)} would_add={len(added)} would_remove={len(removed)}"
                )
                n = opts["sample"]
                if added and n:
                    self.stdout.write(f"    add sample: {added[:n]}")
                if removed and n:
                    self.stdout.write(f"    remove sample: {removed[:n]}")
        self.stdout.write(f"TOTAL would_add={total_added} would_remove={total_removed} (nothing was changed)")
