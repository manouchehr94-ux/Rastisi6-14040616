from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Category, Product, StockMovement, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, Refund, RefundItem, ShippingMethod
from apps.orders.services.refund_service import (
    RefundError,
    execute_order_refund,
    paid_amount,
    plan_order_refund,
    record_refund_result,
    refundable_amount,
    refunded_total,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class RefundServiceTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="09121300001", password="pass12345")
        self.staff = User.objects.create_user(username="09121300099", password="pass12345", is_staff=True)
        self.customer = Customer.objects.create(user=self.user, full_name="سارا محمدی", phone="09121300001")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-rf")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-rf")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="اسپیکر", slug="speaker-rf",
            sku="SKU-RF1", price=Decimal("500000"), stock=20,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rf", cost=Decimal("50000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="zarin-rf")
        self.order = Order.objects.create(
            code="DM-RF1", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            items_total=Decimal("1000000"), shipping_cost=Decimal("50000"),
            grand_total=Decimal("1050000"), payment_status=Order.PaymentStatus.PAID,
        )
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=Decimal("500000"), line_total=Decimal("1000000"),
        )


class RefundableAmountTests(RefundServiceTestCase):
    def test_paid_amount_zero_when_not_paid(self):
        self.order.payment_status = Order.PaymentStatus.PENDING
        self.order.save(update_fields=["payment_status"])
        self.assertEqual(paid_amount(self.order), Decimal("0"))

    def test_refundable_equals_grand_total_before_any_refund(self):
        self.assertEqual(refundable_amount(self.order), Decimal("1050000"))

    def test_refundable_decreases_after_successful_refund(self):
        execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
        )
        self.assertEqual(refunded_total(self.order), Decimal("500000"))
        self.assertEqual(refundable_amount(self.order), Decimal("550000"))


class PlanOrderRefundTests(RefundServiceTestCase):
    def test_full_item_refund_plan(self):
        plan = plan_order_refund(
            self.order, store=self.store, line_requests=[{"order_item_id": self.item.pk, "quantity": 2}],
        )
        self.assertEqual(plan.items_total, Decimal("1000000"))
        self.assertEqual(plan.total_amount, Decimal("1000000"))

    def test_partial_quantity_refund_plan(self):
        plan = plan_order_refund(
            self.order, store=self.store, line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
        )
        self.assertEqual(plan.items_total, Decimal("500000"))

    def test_shipping_refund_included(self):
        plan = plan_order_refund(
            self.order, store=self.store, line_requests=[], shipping_amount=Decimal("50000"),
        )
        self.assertEqual(plan.total_amount, Decimal("50000"))

    def test_over_refund_rejected(self):
        with self.assertRaises(RefundError):
            plan_order_refund(
                self.order, store=self.store, line_requests=[{"order_item_id": self.item.pk, "quantity": 3}],
            )

    def test_excess_shipping_refund_rejected(self):
        with self.assertRaises(RefundError):
            plan_order_refund(
                self.order, store=self.store, line_requests=[], shipping_amount=Decimal("99999999"),
            )

    def test_wrong_store_rejected(self):
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="rf-other", status=Store.Status.ACTIVE)
        with self.assertRaises(RefundError):
            plan_order_refund(
                self.order, store=other_store, line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
            )

    def test_order_item_from_other_order_rejected(self):
        other_order = Order.objects.create(
            code="DM-RF2", store=self.store, customer=self.customer, vendor=self.vendor, address={},
            shipping_method=self.shipping, payment_gateway=self.gateway,
            grand_total=Decimal("100000"), payment_status=Order.PaymentStatus.PAID,
        )
        with self.assertRaises(RefundError):
            plan_order_refund(
                other_order, store=self.store, line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
            )

    def test_total_over_paid_amount_rejected_even_if_per_item_valid(self):
        # zero out payment status so nothing is refundable at all
        self.order.payment_status = Order.PaymentStatus.PENDING
        self.order.save(update_fields=["payment_status"])
        with self.assertRaises(RefundError):
            plan_order_refund(
                self.order, store=self.store, line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
            )


class ExecuteOrderRefundTests(RefundServiceTestCase):
    def test_manual_refund_succeeds_immediately(self):
        refund = execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
        )
        self.assertEqual(refund.status, Refund.Status.SUCCEEDED)
        self.assertEqual(refund.approved_amount, Decimal("500000"))
        self.assertIsNotNone(refund.completed_at)
        self.assertEqual(RefundItem.objects.filter(refund=refund).count(), 1)

    def test_gateway_method_rejected_honestly(self):
        with self.assertRaises(RefundError):
            execute_order_refund(
                self.order, store=self.store, actor=self.staff,
                line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
                refund_method=Refund.Method.GATEWAY,
            )

    def test_duplicate_idempotency_key_returns_same_refund(self):
        first = execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], idempotency_key="ret-key-1",
        )
        second = execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], idempotency_key="ret-key-1",
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Refund.objects.filter(order=self.order).count(), 1)


    def test_retry_key_rejects_other_store_and_order(self):
        execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], idempotency_key="p0-shared",
        )
        other_store = Store.objects.create(name="فروشگاه دیگر", slug="p0-other-store", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشنده", slug="p0-other-vendor")
        other_shipping = ShippingMethod.objects.create(store=other_store, name="ارسال", slug="p0-other-shipping", cost=Decimal("0"))
        other_gateway = PaymentGateway.objects.create(store=other_store, name="پرداخت", slug="p0-other-gateway")
        other_order = Order.objects.create(
            code="P0-OTHER", store=other_store, customer=self.customer, vendor=other_vendor,
            address={}, shipping_method=other_shipping, payment_gateway=other_gateway,
            items_total=Decimal("100000"), grand_total=Decimal("100000"),
            payment_status=Order.PaymentStatus.PAID,
        )
        other_item = OrderItem.objects.create(
            order=other_order, product_name="کالا", quantity=1,
            unit_price=Decimal("100000"), line_total=Decimal("100000"),
        )
        with self.assertRaises(RefundError):
            execute_order_refund(
                other_order, store=other_store, actor=self.staff,
                line_requests=[{"order_item_id": other_item.pk, "quantity": 1}],
                idempotency_key="p0-shared",
            )
        self.assertFalse(Refund.objects.filter(store=other_store).exists())

    def test_retry_key_rejects_changed_request_fields(self):
        original = {"order": self.order, "store": self.store, "actor": self.staff,
                    "line_requests": [{"order_item_id": self.item.pk, "quantity": 1}],
                    "idempotency_key": "p0-params"}
        execute_order_refund(**original)
        for change in (
            {"line_requests": [{"order_item_id": self.item.pk, "quantity": 2}]},
            {"shipping_amount": Decimal("50000")},
            {"reason": "changed"},
            {"merchant_note": "changed"},
            {"restock": True},
        ):
            with self.subTest(change=change):
                with self.assertRaises(RefundError):
                    execute_order_refund(**{**original, **change})
        self.assertEqual(Refund.objects.filter(order=self.order).count(), 1)

    def test_full_refund_marks_order_refunded(self):
        execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 2}], shipping_amount=Decimal("50000"),
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_second_refund_on_already_fully_refunded_item_rejected(self):
        execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 2}],
        )
        with self.assertRaises(RefundError):
            execute_order_refund(
                self.order, store=self.store, actor=self.staff,
                line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
            )

    def test_restock_true_creates_stock_movement(self):
        self.product.stock = 5
        self.product.save(update_fields=["stock"])
        execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], restock=True,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertTrue(StockMovement.objects.filter(reason=StockMovement.Reason.REFUND_RESTOCK).exists())

    def test_restock_false_does_not_change_stock(self):
        self.product.stock = 5
        self.product.save(update_fields=["stock"])
        execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}], restock=False,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)


class RecordRefundResultTests(RefundServiceTestCase):
    def test_cannot_modify_final_refund(self):
        refund = execute_order_refund(
            self.order, store=self.store, actor=self.staff,
            line_requests=[{"order_item_id": self.item.pk, "quantity": 1}],
        )
        with self.assertRaises(RefundError):
            record_refund_result(refund, status=Refund.Status.FAILED)
