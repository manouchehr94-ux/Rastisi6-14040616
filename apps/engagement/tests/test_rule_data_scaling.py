"""H8: بارگذاریِ تنبلِ ردیف‌هایِ سفارش در موتورِ قواعد — همان نتیجه، بدونِ N+1.

* قاعده‌ایِ که به ردیف‌ها نگاه نمی‌کند (مبلغ/تعداد/شهر…) هیچ queryِ ``OrderItem`` نمی‌زند.
* قاعده‌ی ردیفی ردیف‌هایِ کلِ دسته را با تعدادِ ثابتی query می‌خواند (مستقل از تعدادِ سفارش‌ها).
* اسنپ‌شاتِ مسیرِ دسته‌ای (prefetch) با مسیرِ تکی (checkout) دقیقاً برابر است (با اسنپ‌شات و بدونِ آن)."""

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.engagement.services import campaign_service as cs
from apps.engagement.services import rule_data
from apps.engagement.tests.test_campaign_scenario import M, MandatoryBase
from apps.orders.models import OrderItem
from apps.orders.services.item_snapshot_service import effective_item_snapshot


def item_queries(ctx):
    return sum(1 for q in ctx.captured_queries if "orders_orderitem" in q["sql"].lower())


class LazyLinesTests(MandatoryBase):
    def setUp(self):
        super().setUp()
        self.customers = []
        for i in range(6):
            c = self.customer(f"مشتری {i}")
            self.order(c, [(self.olive_bag, 1 + i % 2), (self.nike_shoe, 1)], when=self.mehr(5 + i), city="شیراز")
            self.customers.append(c)

    def eligible_ids(self, tree):
        campaign = self.campaign(rules=tree)
        return set(cs.compute_eligible(campaign))

    def test_order_level_rules_never_load_order_items(self):
        tree = {"type": "group", "op": "and", "children": [
            {"type": "order_total", "op": "gte", "value": 1}, {"type": "shipping_city", "values": ["شیراز"]},
            {"type": "order_count", "op": "gte", "value": 1},
        ]}
        with CaptureQueriesContext(connection) as ctx:
            ids = self.eligible_ids(tree)
        self.assertEqual(ids, {c.pk for c in self.customers})
        self.assertEqual(item_queries(ctx), 0)

    def test_line_rules_load_items_with_constant_queries_regardless_of_order_count(self):
        tree = {"type": "group", "op": "and", "children": [{"type": "line_match", "brand_ids": [self.nike.pk]}]}
        with CaptureQueriesContext(connection) as small:
            self.eligible_ids(tree)
        for c in self.customers:  # دو برابر سفارش
            self.order(c, [(self.nike_shoe, 1), (self.olive_bag, 1)], when=self.aban(3 + c.pk % 5), city="شیراز")
        with CaptureQueriesContext(connection) as large:
            ids = self.eligible_ids(tree)
        self.assertEqual(ids, {c.pk for c in self.customers})
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))

    def test_item_count_rule_uses_lazy_lines(self):
        tree = {"type": "group", "op": "and", "children": [{"type": "item_count", "op": "gte", "value": 3}]}
        self.assertEqual(self.eligible_ids(tree), {self.customers[1].pk, self.customers[3].pk, self.customers[5].pk})

    def test_chunk_snapshot_equals_single_item_snapshot_with_and_without_stored_snapshot(self):
        orders = list(self.customers[0].orders.all()) + list(self.customers[1].orders.all())
        for variant_row in OrderItem.objects.filter(order__in=orders)[:1]:  # یک ردیفِ «قدیمی» بدونِ اسنپ‌شات
            OrderItem.objects.filter(pk=variant_row.pk).update(attributes_snapshot={})
        valid_by, _ = rule_data.load_orders(self.store, [c.pk for c in self.customers[:2]], ["paid"])
        views = [v for vs in valid_by.values() for v in vs]
        self.assertTrue(views)
        for view in views:
            expected = {i.pk: effective_item_snapshot(OrderItem.objects.select_related("product", "variant").get(pk=i.pk))
                        for i in OrderItem.objects.filter(order_id=view.pk)}
            got = {}
            for line, item in zip(view.get_lines(), OrderItem.objects.filter(order_id=view.pk).order_by("pk")):
                got[item.pk] = line.snapshot
            self.assertEqual(got, expected)
