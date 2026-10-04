from django.db import migrations


def backfill(apps, schema_editor):
    """سفارش‌هایِ پیشینِ دارایِ کد تخفیف دفترِ استفاده نداشتند. برایِ هرکدام یک ردیف می‌سازد تا
    لغو/استردادِ آن‌ها پس از استقرار هم ظرفیتِ کد را درست آزاد/ثبت کند. ``used_count``
    دست‌نخورده می‌ماند (پیش‌تر همین سفارش‌ها را شمرده بود). idempotent."""
    Order = apps.get_model("orders", "Order")
    Redemption = apps.get_model("orders", "CouponRedemption")
    existing = set(Redemption.objects.values_list("order_id", flat=True))
    batch = []
    for order in Order.objects.filter(coupon__isnull=False).only(
        "pk", "coupon_id", "customer_id", "status", "payment_status", "coupon_discount",
    ).iterator():
        if order.pk in existing:
            continue
        if order.status == "canceled":
            status, reason = "released", "legacy_canceled"
        elif order.payment_status == "paid":
            status, reason = "redeemed", ""
        elif order.payment_status == "refunded":
            status, reason = "refunded", ""
        else:
            status, reason = "reserved", ""
        batch.append(Redemption(
            coupon_id=order.coupon_id, order_id=order.pk, customer_id=order.customer_id, status=status,
            discount_amount=order.coupon_discount, release_reason=reason,
        ))
        if len(batch) >= 500:
            Redemption.objects.bulk_create(batch)
            batch = []
    if batch:
        Redemption.objects.bulk_create(batch)


class Migration(migrations.Migration):
    dependencies = [("orders", "0015_order_campaign_indexes")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
