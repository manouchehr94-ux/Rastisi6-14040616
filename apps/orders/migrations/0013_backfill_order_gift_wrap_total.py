from django.db import migrations


def backfill(apps, schema_editor):
    """سفارش‌هایِ پیشین فقط اسنپ‌شاتِ سطحِ قلم داشتند (تعداد × قیمت)؛ مبلغِ
    کادوپیچی را با همان سیاستِ ``per_unit`` به سطحِ سفارش منتقل می‌کند."""
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    totals = {}
    for item in OrderItem.objects.filter(gift_wrap_selected=True).iterator():
        totals[item.order_id] = totals.get(item.order_id, 0) + item.gift_wrap_unit_price * item.quantity
    for order_id, total in totals.items():
        Order.objects.filter(pk=order_id, gift_wrap_total=0).update(gift_wrap_total=total, gift_wrap_scope="per_unit")


class Migration(migrations.Migration):
    dependencies = [("orders", "0012_order_gift_wrap_discount_order_gift_wrap_scope_and_more")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
