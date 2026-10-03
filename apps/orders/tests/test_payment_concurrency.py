"""رقابتِ واقعیِ callbackِ پرداخت با لغو/callbackِ دیگر — فقط PostgreSQL (قفل‌هایِ ردیف).

ناوردا: برایِ هر پرداختِ تأییدشده یا «سفارش پرداخت‌شده + تراکنشِ OK» داریم یا «رکوردِ تطبیق»؛ هرگز هیچ‌کدام
(پولِ گم‌شده) و هرگز هر دو (پرداختِ دوباره‌شمرده). لغو دقیقاً یک‌بار موجودی/کد را برمی‌گرداند."""

import threading
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import (
    CouponRedemption, Order, PaymentAttempt, PaymentGateway, PaymentGatewayConfig, PaymentReconciliation,
    ShippingMethod, Transaction,
)
from apps.orders.services.gateway_payment_service import PaymentVerificationFailed, process_callback_and_verify
from apps.orders.services.order_service import change_order_status, create_order_from_cart
from apps.stores.models import Store

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "نیازمندِ PostgreSQL")
class PaymentRaceTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.store = Store.objects.create(name="رقابتِ پرداخت", slug="payment-race", status=Store.Status.ACTIVE)
        shop = ShopSettings.provision_for(self.store)
        shop.tax_percent = Decimal("0")
        shop.free_shipping_threshold = Decimal("999999999")
        shop.save()
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-pr")
        cat = Category.objects.create(store=self.store, name="c", slug="c-pr")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=cat, name="p", slug="p-pr", sku="PR1",
            price=Decimal("1000000"), stock=1000,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-pr", cost=Decimal("0"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="g", slug="g-pr")
        self.config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal", is_active=True)
        self.config.set_credentials({"merchant": "m"})
        self.config.save()
        self.coupon = Coupon.objects.create(store=self.store, code="PRC", type="percent", value=10, usage_limit=50)
        user = User.objects.create_user(username="pr-cust", password="x12345678")
        self.customer = Customer.objects.create(user=user, full_name="c", phone="09135550001", email="pr@example.com")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="x", phone=self.customer.phone, province="فارس", city="شیراز",
            postal_code="1111111111", full_address="x",
        )
        self.counter = 0

    def order(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        return create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address, shipping_method=self.shipping,
            payment_gateway=self.gateway, coupon=self.coupon, store=self.store,
        )

    def attempt(self, order):
        self.counter += 1
        return PaymentAttempt.objects.create(
            store=self.store, order=order, gateway_config=self.config, amount=order.grand_total, currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY, gateway_track_id=f"pr-{order.pk}-{self.counter}",
        )

    def response(self, order):
        r = MagicMock()
        r.json.return_value = {"result": 100, "amount": int(order.grand_total) * 10, "status": 1, "refNumber": f"REF-{order.pk}", "cardNumber": ""}
        return r

    def race(self, jobs):
        barrier = threading.Barrier(len(jobs))
        errors = []

        def worker(job):
            try:
                barrier.wait()
                job()
            except PaymentVerificationFailed:
                pass
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(j,)) for j in jobs]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return errors

    def assert_money_accounted(self, order, attempts):
        order.refresh_from_db()
        paid = order.payment_status == Order.PaymentStatus.PAID
        ok_tx = Transaction.objects.filter(order=order, status="ok").count()
        reconciled = PaymentReconciliation.objects.filter(order=order).count()
        succeeded = PaymentAttempt.objects.filter(order=order, status=PaymentAttempt.Status.SUCCEEDED).count()
        self.assertEqual(ok_tx, 1 if paid else 0)
        # هر تلاشِ موفق: یا همان که سفارش را پرداخت کرد یا دقیقاً یک رکوردِ تطبیق
        self.assertEqual(succeeded, (1 if paid else 0) + reconciled)
        self.assertEqual(succeeded, len(attempts))
        return paid, reconciled

    def test_callback_vs_cancellation_never_loses_or_double_counts_money(self):
        outcomes = set()
        for _ in range(8):
            order = self.order()
            attempt = self.attempt(order)
            stock_after_order = Product.objects.get(pk=self.product.pk).stock
            used_after_order = Coupon.objects.get(pk=self.coupon.pk).used_count
            with patch("apps.orders.gateways.zibal.requests.post", return_value=self.response(order)):
                errors = self.race([
                    lambda: process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store),
                    lambda: change_order_status(Order.objects.get(pk=order.pk), Order.Status.CANCELED, store=self.store),
                ])
            self.assertEqual(errors, [])
            paid, reconciled = self.assert_money_accounted(order, [attempt])
            order.refresh_from_db()
            self.assertEqual(order.status, Order.Status.CANCELED)  # لغو همیشه موفق است (از PENDING یا PROCESSING)
            self.assertEqual(Product.objects.get(pk=self.product.pk).stock, stock_after_order + 1)  # دقیقاً یک‌بار restock
            self.assertEqual(Coupon.objects.get(pk=self.coupon.pk).used_count, used_after_order - 1)
            self.assertEqual(CouponRedemption.objects.get(order=order).status, CouponRedemption.Status.RELEASED)
            outcomes.add("paid_then_canceled" if paid else "reconciled")
            self.assertEqual(paid + reconciled, 1)
        self.assertTrue(outcomes)  # هر دو ترتیب مجاز است؛ ناورداها بالا بررسی شد

    def test_parallel_duplicate_callbacks_apply_payment_once(self):
        order = self.order()
        attempt = self.attempt(order)
        with patch("apps.orders.gateways.zibal.requests.post", return_value=self.response(order)):
            errors = self.race([
                lambda: process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store)
                for _ in range(5)
            ])
        self.assertEqual(errors, [])
        paid, reconciled = self.assert_money_accounted(order, [attempt])
        self.assertEqual((paid, reconciled), (True, 0))
        self.assertEqual(order.status_history.filter(to_status="processing").count(), 1)
        self.assertEqual(CouponRedemption.objects.get(order=order).status, CouponRedemption.Status.REDEEMED)

    def test_two_attempts_both_confirmed_pay_once_and_reconcile_the_other(self):
        order = self.order()
        a1, a2 = self.attempt(order), self.attempt(order)
        with patch("apps.orders.gateways.zibal.requests.post", return_value=self.response(order)):
            errors = self.race([
                lambda: process_callback_and_verify(attempt_public_id=a1.public_id, callback_data={}, store=self.store),
                lambda: process_callback_and_verify(attempt_public_id=a2.public_id, callback_data={}, store=self.store),
            ])
        self.assertEqual(errors, [])
        paid, reconciled = self.assert_money_accounted(order, [a1, a2])
        self.assertEqual((paid, reconciled), (True, 1))
        self.assertEqual(PaymentReconciliation.objects.get().kind, PaymentReconciliation.Kind.ALREADY_PAID)
        self.assertEqual(Coupon.objects.get(pk=self.coupon.pk).used_count, 1)

    # ---- انقضایِ سفارش (M2) در برابرِ callback و job موازی ----
    def _enable_expiry(self):
        shop = ShopSettings.load(store=self.store)
        shop.unpaid_online_order_ttl_minutes, shop.unpaid_online_order_grace_minutes = 60, 30
        shop.save()
        PaymentGateway.objects.filter(store=self.store, slug="zibal").first() or PaymentGateway.objects.create(store=self.store, name="z", slug="zibal")

    def _old_order_with_old_attempt(self):
        from datetime import timedelta

        from django.utils import timezone

        order = self.order()
        gw = PaymentGateway.objects.get(store=self.store, slug="zibal")
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=3), payment_gateway=gw)
        attempt = self.attempt(order)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(hours=2))
        return Order.objects.get(pk=order.pk), attempt

    def test_expiry_job_vs_callback_never_loses_money(self):
        from apps.orders.services.order_expiry_service import expire_unpaid_orders

        self._enable_expiry()
        outcomes = set()
        for _ in range(8):
            order, attempt = self._old_order_with_old_attempt()
            stock_after_order = Product.objects.get(pk=self.product.pk).stock
            with patch("apps.orders.gateways.zibal.requests.post", return_value=self.response(order)):
                errors = self.race([
                    lambda: process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store),
                    lambda: expire_unpaid_orders(store=self.store),
                ])
            self.assertEqual(errors, [])
            paid, reconciled = self.assert_money_accounted(order, [attempt])
            order.refresh_from_db()
            if paid:  # callback برنده: job باید رد می‌کرد، سفارش لغو نمی‌شود
                self.assertEqual(order.status, Order.Status.PROCESSING)
                self.assertEqual(Product.objects.get(pk=self.product.pk).stock, stock_after_order)
                self.assertEqual(CouponRedemption.objects.get(order=order).status, CouponRedemption.Status.REDEEMED)
            else:  # job برنده: لغو + تطبیق، موجودی دقیقاً یک‌بار برگشته
                self.assertEqual((order.status, reconciled), (Order.Status.CANCELED, 1))
                self.assertEqual(Product.objects.get(pk=self.product.pk).stock, stock_after_order + 1)
                self.assertEqual(CouponRedemption.objects.get(order=order).status, CouponRedemption.Status.RELEASED)
            outcomes.add(paid)
        self.assertTrue(outcomes)

    def test_parallel_expiry_jobs_cancel_once(self):
        from apps.notifications.models import NotificationOutbox
        from apps.orders.services.order_expiry_service import expire_unpaid_orders

        self._enable_expiry()
        order, attempt = self._old_order_with_old_attempt()
        stock_after_order = Product.objects.get(pk=self.product.pk).stock
        used_after_order = Coupon.objects.get(pk=self.coupon.pk).used_count
        errors = self.race([lambda: expire_unpaid_orders(store=self.store) for _ in range(4)])
        self.assertEqual(errors, [])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELED)
        self.assertEqual(Product.objects.get(pk=self.product.pk).stock, stock_after_order + 1)
        self.assertEqual(Coupon.objects.get(pk=self.coupon.pk).used_count, used_after_order - 1)
        self.assertEqual(order.status_history.filter(to_status="canceled").count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(order=order, event_key="order.canceled").count(), 1)
