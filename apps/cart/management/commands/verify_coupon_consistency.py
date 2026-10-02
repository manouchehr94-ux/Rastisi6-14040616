"""ابزارِ تشخیصیِ فقط‌خواندنیِ سازگاریِ کدهایِ تخفیف (C1).

هیچ ردیفی را تغییر نمی‌دهد. تطابقِ این‌ها را می‌سنجد:

* ``used_count`` کد با تعدادِ ردیف‌هایِ شمرده‌شده‌ی دفترِ ``CouponRedemption``؛
* سقفِ کل/سقفِ هر مشتری؛
* هم‌خوانیِ وضعیتِ ledger با وضعیتِ سفارش (لغو/پرداخت)؛
* سفارش‌هایِ دارایِ کد بدونِ ردیفِ ledger؛
* هم‌خوانیِ Store/مشتریِ ledger با سفارش و مالکِ کد؛
* پیکربندیِ نامعتبرِ خودِ کد (محدودیت‌ها، بازه‌ها، درصد…).

``--fail-on-issues`` برایِ CI/پایش؛ ``--store`` برایِ یک فروشگاه."""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, F

from apps.cart.models import Coupon
from apps.cart.services.coupon_rules import CouponRestrictionError, validate_restrictions
from apps.orders.models import CouponRedemption, Order

R = CouponRedemption.Status


def config_problems(coupon: Coupon) -> list[str]:
    """مشکلاتِ پیکربندیِ یک کد (همان قواعدِ ``coupon_service._validate_semantics``)."""
    out = []
    if coupon.type == Coupon.Type.PERCENT and not (0 < coupon.value <= 100):
        out.append("percent_out_of_range")
    if coupon.type == Coupon.Type.FIXED and coupon.value <= 0:
        out.append("non_positive_value")
    if coupon.max_discount is not None and coupon.max_discount <= 0:
        out.append("non_positive_max_discount")
    if coupon.starts_at and coupon.expires_at and coupon.expires_at <= coupon.starts_at:
        out.append("expires_before_start")
    if coupon.per_customer_period_days and not coupon.per_customer_limit:
        out.append("period_without_limit")
    if coupon.max_order is not None and coupon.max_order < coupon.min_order:
        out.append("max_order_below_min")
    if coupon.min_items and coupon.max_items and coupon.max_items < coupon.min_items:
        out.append("max_items_below_min")
    if coupon.usage_limit is not None and coupon.used_count > coupon.usage_limit:
        out.append("used_count_over_limit")
    if coupon.used_count < 0:
        out.append("negative_used_count")
    try:
        validate_restrictions(coupon.restrictions)
    except CouponRestrictionError:
        out.append("invalid_restrictions")
    return out


class Command(BaseCommand):
    help = "Read-only diagnostics: coupon counters, redemption ledger, orders and configuration consistency."

    def add_arguments(self, parser):
        parser.add_argument("--store", help="slug of a single store")
        parser.add_argument("--limit", type=int, default=50, help="max issue lines printed per category")
        parser.add_argument("--fail-on-issues", action="store_true")

    def handle(self, *args, **opts):
        store = None
        if opts["store"]:
            from apps.stores.models import Store

            try:
                store = Store.objects.get(slug=opts["store"])
            except Store.DoesNotExist as exc:
                raise CommandError(f"unknown store {opts['store']}") from exc
        issues = self.collect(store)
        counts = Counter(kind for kind, _ in issues)
        printed = Counter()
        for kind, detail in issues:
            printed[kind] += 1
            if printed[kind] <= opts["limit"]:
                self.stdout.write(f"{kind}: {detail}")
        coupons = Coupon.objects.filter(store=store) if store else Coupon.objects.all()
        self.stdout.write(
            f"coupons={coupons.count()} issues={sum(counts.values())} "
            + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        )
        if opts["fail_on_issues"] and issues:
            raise CommandError("coupon consistency issues found")

    @staticmethod
    def collect(store=None) -> list[tuple[str, str]]:
        issues: list[tuple[str, str]] = []
        coupons = Coupon.objects.all()
        redemptions = CouponRedemption.objects.select_related("order", "coupon")
        orders = Order.objects.filter(coupon__isnull=False)
        if store is not None:
            coupons = coupons.filter(store=store)
            redemptions = redemptions.filter(coupon__store=store)
            orders = orders.filter(store=store)

        counted = {
            row["coupon_id"]: row["n"] for row in redemptions.filter(status__in=CouponRedemption.COUNTED_STATUSES)
            .values("coupon_id").annotate(n=Count("id"))
        }
        for coupon in coupons.iterator():
            for problem in config_problems(coupon):
                issues.append((problem, f"coupon {coupon.pk} {coupon.code}"))
            expected = counted.get(coupon.pk, 0)
            if coupon.used_count != expected:
                issues.append(("used_count_drift", f"coupon {coupon.pk} {coupon.code} used_count={coupon.used_count} ledger={expected}"))

        for r in redemptions.iterator():
            order = r.order
            tag = f"redemption {r.pk} order {order.code} coupon {r.coupon.code}"
            if order.store_id != r.coupon.store_id:
                issues.append(("cross_store_redemption", tag))
            if r.customer_id != order.customer_id:
                issues.append(("redemption_customer_mismatch", tag))
            if r.coupon.customer_id is not None and r.coupon.customer_id != r.customer_id:
                issues.append(("personal_coupon_used_by_other", tag))
            counted_status = r.status in CouponRedemption.COUNTED_STATUSES
            if counted_status and order.status == Order.Status.CANCELED and r.status != R.REFUNDED:
                issues.append(("counted_on_canceled_order", f"{tag} status={r.status}"))
            if counted_status and r.status != R.REFUNDED and order.payment_status == Order.PaymentStatus.FAILED \
                    and order.status != Order.Status.CANCELED:
                issues.append(("counted_on_failed_payment", f"{tag} status={r.status}"))
            if r.status == R.RELEASED and order.payment_status == Order.PaymentStatus.PAID \
                    and order.status != Order.Status.CANCELED:
                issues.append(("released_on_paid_order", tag))
            if r.status == R.REDEEMED and order.payment_status != Order.PaymentStatus.PAID:
                issues.append(("redeemed_on_unpaid_order", f"{tag} payment={order.payment_status}"))

        for order in orders.filter(coupon_discount__gt=0).filter(coupon_redemption__isnull=True).iterator():
            issues.append(("order_without_redemption", f"order {order.code} coupon {order.coupon_id}"))

        over = (
            redemptions.filter(status__in=CouponRedemption.COUNTED_STATUSES, coupon__per_customer_limit__isnull=False)
            .values("coupon_id", "customer_id", "coupon__per_customer_limit", "coupon__per_customer_period_days")
            .annotate(n=Count("id")).filter(coupon__per_customer_period_days__isnull=True, n__gt=F("coupon__per_customer_limit"))
        )
        for row in over:
            issues.append(("per_customer_limit_exceeded",
                           f"coupon {row['coupon_id']} customer {row['customer_id']} uses={row['n']} limit={row['coupon__per_customer_limit']}"))
        return issues
