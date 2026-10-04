"""G1: تعریف‌هایِ مشترکِ سفارشِ مشتری — رفتارِ تاریخیِ سگمنت (legacy) تغییر نمی‌کند، تعریفِ
valid با موتورِ قواعد هم‌خوان است، و گزارشِ اثر فقط‌خواندنی است."""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.cart.models import Coupon
from apps.customers.models import Customer, CustomerSegment, CustomerSegmentMembership, CustomerSegmentRule
from apps.dashboard.services import segment_service as ss
from apps.dashboard.tests.test_segment_service import SegmentServiceTestCase
from apps.engagement.services import rule_data
from apps.orders.models import Order, OrderItem, Refund
from apps.orders.services import order_definitions as od, refund_service


class Dataset(SegmentServiceTestCase):
    """مشتریانِ نمونه (علاوه بر دو مشتریِ پایه‌ی SegmentServiceTestCase: ۱٬۰۰۰٬۰۰۰ و ۵۰٬۰۰۰ پرداخت‌شده):

    * ``canceled``  — یک سفارشِ پرداخت‌شده‌ی لغوشده (۵۰۰٬۰۰۰)
    * ``unpaid``    — یک سفارشِ در انتظارِ پرداخت (COD) (۳۰۰٬۰۰۰)
    * ``failed``    — پرداختِ ناموفق (۲۰۰٬۰۰۰)
    * ``mixed``     — سفارشِ معتبر ۱۰۰٬۰۰۰ + سفارشِ لغوشده‌ی پرداخت‌شده ۹۰۰٬۰۰۰
    * ``refunded``  — سفارشِ پرداخت‌شده ۸۰۰٬۰۰۰ با استردادِ جزئیِ موفق ۱۰۰٬۰۰۰
    """

    def _customer(self, tag):
        user = self.big_spender_user.__class__.objects.create_user(username=f"0912888{tag}", password="p")
        return Customer.objects.create(user=user, full_name=tag, phone=f"0912888{tag}")

    def _order(self, customer, code, *, status="delivered", pay="paid", total=100000, product=True, coupon=None, days_ago=0):
        o = Order.objects.create(
            code=code, store=self.store, customer=customer, vendor=self.vendor, address={}, shipping_method=self.shipping,
            payment_gateway=self.gateway, grand_total=Decimal(total), payment_status=pay, status=status, coupon=coupon,
        )
        Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timezone.timedelta(days=days_ago))
        if product:
            OrderItem.objects.create(order=o, product=self.product, product_name="p", quantity=1,
                                     unit_price=Decimal(total), line_total=Decimal(total))
        return o

    def setUp(self):
        super().setUp()
        self.coupon = Coupon.objects.create(store=self.store, code="G1C", type="percent", value=10)
        self.canceled = self._customer("0001"); self._order(self.canceled, "G-C", status="canceled", total=500000, days_ago=40)
        self.unpaid = self._customer("0002"); self._order(self.unpaid, "G-U", status="pending", pay="pending", total=300000, days_ago=100)
        self.failed = self._customer("0003"); self._order(self.failed, "G-F", status="pending", pay="failed", total=200000, days_ago=3)
        self.mixed = self._customer("0004")
        self._order(self.mixed, "G-M1", total=100000, days_ago=60)
        self._order(self.mixed, "G-M2", status="canceled", total=900000, days_ago=1, product=False)
        self.refunded = self._customer("0005")
        self.refunded_order = self._order(self.refunded, "G-R", total=800000, coupon=self.coupon, days_ago=10)
        Refund.objects.create(order=self.refunded_order, store=self.store, status=Refund.Status.SUCCEEDED,
                              requested_amount=Decimal(100000), approved_amount=Decimal(100000))

    def ids(self, field, operator, value, definition, value2=""):
        rule = CustomerSegmentRule(field=field, operator=operator, value=value, value2=value2)
        return ss._matching_customer_ids(self.store, rule, definition)

    def pks(self, *customers):
        return {c.pk for c in customers}


class LegacyBehaviourIsFrozenTests(Dataset):
    """طلایی: رفتارِ تاریخیِ سگمنت (همه‌ی سفارش‌ها در تعداد/تاریخ/کالا/کد؛ مجموعِ خرید = paid، حتی لغوشده)."""

    def test_order_count_counts_every_order_including_canceled_unpaid_failed(self):
        got = self.ids("order_count", "greater_than_or_equal", "1", od.LEGACY)
        self.assertEqual(got, self.pks(self.big_spender, self.small_spender, self.canceled, self.unpaid, self.failed, self.mixed, self.refunded))
        self.assertEqual(self.ids("order_count", "equals", "2", od.LEGACY), self.pks(self.mixed))

    def test_total_spent_is_paid_orders_even_if_canceled_and_gross_of_refunds(self):
        self.assertEqual(self.ids("total_spent", "greater_than", "700000", od.LEGACY),
                         self.pks(self.big_spender, self.mixed, self.refunded))  # mixed = 100k + 900k(canceled, paid)
        self.assertEqual(self.ids("total_spent", "equals", "800000", od.LEGACY), self.pks(self.refunded))

    def test_dates_products_and_coupons_use_all_orders(self):
        self.assertIn(self.canceled.pk, self.ids("has_purchased_product", "contains", str(self.product.pk), od.LEGACY))
        self.assertEqual(self.ids("has_used_coupon", "contains", str(self.coupon.pk), od.LEGACY), self.pks(self.refunded))
        self.assertIn(self.mixed.pk, self.ids("last_order_at", "after", str((timezone.now() - timezone.timedelta(days=5)).date()), od.LEGACY))

    def test_default_definition_is_legacy_and_unknown_setting_falls_back(self):
        self.assertEqual(ss.current_definition().key, "legacy")
        with override_settings(SEGMENT_ORDER_DEFINITION="nonsense"):
            self.assertEqual(ss.current_definition().key, "legacy")
        with override_settings(SEGMENT_ORDER_DEFINITION="valid"):
            self.assertEqual(ss.current_definition().key, "valid")

    def test_refresh_membership_unchanged_by_default(self):
        seg = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=seg, field="order_count", operator="greater_than", value="0")
        count = ss.refresh_segment_membership(seg)
        self.assertEqual(count, 7)
        self.assertEqual(CustomerSegmentMembership.objects.filter(segment=seg).count(), 7)


class ValidDefinitionTests(Dataset):
    def test_valid_excludes_canceled_unpaid_and_failed_everywhere(self):
        everyone_valid = self.pks(self.big_spender, self.small_spender, self.mixed, self.refunded)
        self.assertEqual(self.ids("order_count", "greater_than_or_equal", "1", od.VALID), everyone_valid)
        self.assertEqual(self.ids("order_count", "equals", "1", od.VALID), everyone_valid)  # mixed: canceled ignored
        self.assertEqual(self.ids("total_spent", "greater_than", "700000", od.VALID), self.pks(self.big_spender, self.refunded))
        self.assertEqual(self.ids("has_purchased_product", "contains", str(self.product.pk), od.VALID), self.pks(self.big_spender, self.mixed, self.refunded))
        self.assertNotIn(self.canceled.pk, self.ids("has_purchased_category", "contains", str(self.category.pk), od.VALID))

    def test_valid_zero_count_for_customers_with_only_invalid_orders(self):
        self.assertEqual(self.ids("order_count", "equals", "0", od.VALID), self.pks(self.canceled, self.unpaid, self.failed))

    def test_valid_dates_and_inactivity(self):
        # mixed: آخرین سفارشِ معتبر ۶۰ روز پیش (سفارشِ لغوشده‌ی ۱ روز پیش نادیده)
        self.assertIn(self.mixed.pk, self.ids("no_purchase_for_days", "greater_than_or_equal", "30", od.VALID))
        self.assertNotIn(self.mixed.pk, self.ids("no_purchase_for_days", "greater_than_or_equal", "30", od.LEGACY))
        # مشتریِ فقط‌-لغوشده «هرگز نخریده» است، نه «مدتی نخریده»
        self.assertNotIn(self.canceled.pk, self.ids("no_purchase_for_days", "greater_than_or_equal", "30", od.VALID))

    def test_valid_matches_campaign_rules_engine_for_every_customer(self):
        """همان مشتریان/تعداد/مجموع که موتورِ قواعد (rule_data.load_facts) می‌بیند."""
        facts = rule_data.load_facts(self.store, [c.pk for c in Customer.objects.all()], ("paid",))
        for field, getter in (("order_count", lambda f: f.lifetime_orders),):
            for customer_id, f in facts.items():
                ids = self.ids(field, "equals", str(getter(f)), od.VALID)
                if getter(f) > 0:
                    self.assertIn(customer_id, ids, (field, customer_id))
        spent_ids = self.ids("total_spent", "equals", "800000", od.VALID)
        self.assertEqual(spent_ids, {cid for cid, f in facts.items() if f.lifetime_spent == 800000})

    def test_segment_evaluation_uses_override_setting_and_explicit_argument(self):
        seg = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=seg, field="order_count", operator="greater_than", value="0")
        self.assertEqual(len(ss.evaluate_segment(seg)), 7)
        with override_settings(SEGMENT_ORDER_DEFINITION="valid"):
            self.assertEqual(len(ss.evaluate_segment(seg)), 4)
        self.assertEqual(len(ss.evaluate_segment(seg, od.VALID)), 4)

    def test_store_isolation(self):
        from apps.stores.models import Store

        other = Store.objects.create(name="o", slug="seg-other", status=Store.Status.ACTIVE)
        rule = CustomerSegmentRule(field="order_count", operator="greater_than", value="0")
        self.assertEqual(ss._matching_customer_ids(other, rule, od.VALID), set())
        # کالا/کوپنِ یک Store هرگز مشتریانِ Storeِ دیگر را برنمی‌گرداند
        foreign = CustomerSegmentRule(field="has_purchased_product", operator="contains", value=str(self.product.pk))
        self.assertEqual(ss._matching_customer_ids(other, foreign, od.LEGACY), set())


class SharedBaseDefinitionTests(Dataset):
    def test_rule_engine_valid_orders_come_from_shared_definition(self):
        a = set(rule_data.valid_orders_qs(self.store, ("paid",)).values_list("pk", flat=True))
        b = set(od.valid_orders(self.store, ("paid",)).values_list("pk", flat=True))
        self.assertEqual(a, b)
        self.assertNotIn(Order.objects.get(code="G-C").pk, a)  # لغوشده
        self.assertNotIn(Order.objects.get(code="G-U").pk, a)  # پرداخت‌نشده

    def test_custom_valid_statuses_are_respected(self):
        pks = set(od.valid_orders(self.store, ("paid", "pending")).values_list("code", flat=True))
        self.assertIn("G-U", pks)
        self.assertNotIn("G-F", pks)
        self.assertNotIn("G-C", pks)

    def test_active_refund_definition_is_single_and_consistent(self):
        order = self.refunded_order
        Refund.objects.create(order=order, store=self.store, status=Refund.Status.FAILED, requested_amount=Decimal(50000))
        Refund.objects.create(order=order, store=self.store, status=Refund.Status.CANCELLED, requested_amount=Decimal(40000))
        Refund.objects.create(order=order, store=self.store, status=Refund.Status.PENDING, requested_amount=Decimal(30000))
        self.assertEqual(Refund.INACTIVE_STATUSES, ("failed", "cancelled"))
        service_total = refund_service.refunded_total(order)
        self.assertEqual(service_total, Decimal(130000))  # 100k succeeded + 30k pending
        facts_orders, _ = rule_data.load_orders(self.store, [self.refunded.pk], ("paid",))
        self.assertEqual(facts_orders[self.refunded.pk][0].refunded, service_total)
        self.assertEqual(od.net_amount(Decimal(800000), service_total), Decimal(670000))


class AnalyzeCommandTests(Dataset):
    def test_report_is_read_only_and_quantifies_impact(self):
        seg = self._dynamic_segment()
        CustomerSegmentRule.objects.create(segment=seg, field="order_count", operator="greater_than", value="0")
        ss.refresh_segment_membership(seg)
        before = (list(CustomerSegmentMembership.objects.order_by("pk").values_list("pk", "customer_id")), Order.objects.count())
        out = StringIO()
        call_command("analyze_segment_definitions", "--store", self.store.slug, stdout=out)
        text = out.getvalue()
        self.assertIn("active definition: legacy", text)
        self.assertIn("stored=7 legacy_now=7 valid=4 stale_cache_vs_legacy=0 would_add=0 would_remove=3", text)
        self.assertIn("TOTAL would_add=0 would_remove=3 (nothing was changed)", text)
        self.assertEqual(before, (list(CustomerSegmentMembership.objects.order_by("pk").values_list("pk", "customer_id")), Order.objects.count()))
        seg.refresh_from_db()
        self.assertEqual(CustomerSegmentMembership.objects.filter(segment=seg).count(), 7)


class OperatorColumnLengthTests(SegmentServiceTestCase):
    """رگرسیون: هر عملگرِ مجاز باید در ستون جا شود (PostgreSQL طولِ varchar را اعمال می‌کند؛ SQLite نه)."""

    def test_every_allowed_operator_and_field_fits_the_columns(self):
        max_op = CustomerSegmentRule._meta.get_field("operator").max_length
        max_field = CustomerSegmentRule._meta.get_field("field").max_length
        for field, meta in ss.ALLOWED_FIELDS.items():
            self.assertLessEqual(len(field), max_field, field)
            for operator in meta["operators"]:
                self.assertLessEqual(len(operator), max_op, operator)
        self.assertGreaterEqual(max_op, len("greater_than_or_equal"))

    def test_every_allowed_rule_can_be_persisted_and_evaluated(self):
        seg = self._dynamic_segment()
        for field, meta in ss.ALLOWED_FIELDS.items():
            for operator in meta["operators"]:
                value = "2025-01-01" if meta["value_type"] == "date" else "1"
                value2 = "2030-01-01" if operator == "between" else ""
                rule = CustomerSegmentRule.objects.create(segment=seg, field=field, operator=operator, value=value, value2=value2)
                rule.refresh_from_db()
                self.assertEqual(rule.operator, operator)
                ss.validate_rule(rule.field, rule.operator)
        # و عملگرِ ≥ واقعاً کار می‌کند
        CustomerSegmentRule.objects.filter(segment=seg).delete()
        CustomerSegmentRule.objects.create(segment=seg, field="order_count", operator="greater_than_or_equal", value="1")
        self.assertEqual(ss.refresh_segment_membership(seg), 2)  # دو مشتریِ پایه‌ی SegmentServiceTestCase
