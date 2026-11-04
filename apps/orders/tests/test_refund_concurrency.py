import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import skipUnless
from django.db import connection
from django.contrib.auth import get_user_model
from django.db import connections, close_old_connections
from django.test import TransactionTestCase
from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, Refund, ShippingMethod
from apps.orders.services.refund_service import execute_order_refund, RefundError
from apps.notifications.models import NotificationEvent
from apps.stores.models import Store
User = get_user_model()
@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL")
class RefundConcurrencyTests(TransactionTestCase):
    # TransactionTestCase commits fixtures so other threads/connections can see them.
    databases = {"default"}

    def setUp(self):
        self.store = Store.objects.create(
            name="P0 Refund concurrency", slug="p0-refund-concurrency",
            status=Store.Status.ACTIVE,
        )
        self.customer_user = User.objects.create_user(
            username="p0ref_customer", password="unused-P0-1",
        )
        self.actor = User.objects.create_user(
            username="p0ref_operator", password="unused-P0-2", is_staff=True,
        )
        self.customer = Customer.objects.create(
            user=self.customer_user, full_name="Refund probe", phone="09120009991",
        )
        self.vendor = Vendor.objects.create(
            store=self.store, name="P0 Vendor", slug="p0-vendor",
        )
        category = Category.objects.create(
            store=self.store, name="P0 Category", slug="p0-category",
        )
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=category,
            name="P0 Product", slug="p0-product", sku="P0-CONC-1",
            price=Decimal("500000"), stock=20,
        )
        shipping = ShippingMethod.objects.create(
            store=self.store, name="P0 Shipping", slug="p0-shipping", cost=Decimal("0"),
        )
        gateway = PaymentGateway.objects.create(
            store=self.store, name="P0 Gateway", slug="p0-gateway",
        )
        self.order = Order.objects.create(
            code="P0-RF-CONC", store=self.store, customer=self.customer,
            vendor=self.vendor, address={}, shipping_method=shipping,
            payment_gateway=gateway, items_total=Decimal("1000000"),
            grand_total=Decimal("1000000"), payment_status=Order.PaymentStatus.PAID,
        )
        self.item = OrderItem.objects.create(
            order=self.order, product=self.product, product_name=self.product.name,
            quantity=2, unit_price=Decimal("500000"), line_total=Decimal("1000000"),
        )

    def _concurrent_refunds(self, *, quantity: int, keys: tuple[str, str]):
        # Fresh DB connection in each thread; no connection may be shared.
        barrier = threading.Barrier(2)

        def worker(key):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                try:
                    result = execute_order_refund(
                        self.order, store=self.store, actor=self.actor,
                        line_requests=[{"order_item_id": self.item.pk, "quantity": quantity}],
                        idempotency_key=key,
                    )
                    return ("ok", result.pk)
                except RefundError as exc:
                    return ("refund_error", str(exc))
                except Exception as exc:
                    return ("unexpected", f"{type(exc).__name__}: {exc}")
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="p0-refund") as pool:
            futures = [pool.submit(worker, key) for key in keys]
            return [f.result(timeout=45) for f in futures]

    def test_two_competing_full_refunds_do_not_overrefund(self):
        outcomes = self._concurrent_refunds(
            quantity=2, keys=("p0-different-key-a", "p0-different-key-b"),
        )
        self.assertEqual([o[0] for o in outcomes].count("ok"), 1, outcomes)
        self.assertEqual([o[0] for o in outcomes].count("refund_error"), 1, outcomes)
        from django.db.models import Sum
        qs = Refund.objects.filter(order=self.order)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.aggregate(s=Sum("approved_amount"))["s"], Decimal("1000000"))
        self.assertEqual(qs.first().items.get().quantity, 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(NotificationEvent.objects.filter(
            store=self.store, type_key="refund.completed",
        ).count(), 1)

    def test_concurrent_same_key_returns_one_refund(self):
        outcomes = self._concurrent_refunds(
            quantity=1, keys=("p0-same-key", "p0-same-key"),
        )
        self.assertEqual([o[0] for o in outcomes], ["ok", "ok"], outcomes)
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        self.assertEqual(Refund.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Refund.objects.get(order=self.order).approved_amount, Decimal("500000"))
        self.assertEqual(NotificationEvent.objects.filter(
            store=self.store, type_key="refund.completed",
        ).count(), 1)
