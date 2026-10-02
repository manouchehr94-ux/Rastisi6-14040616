"""رقابتِ هم‌زمانِ استفاده از کد — فقط روی PostgreSQL معنا دارد (SQLite نوشتنِ هم‌زمان را
قفلِ کل می‌کند و ``SELECT … FOR UPDATE`` را نادیده می‌گیرد).

اجرا: ``DATABASE_URL=postgres://… python manage.py test apps.orders.tests.test_coupon_concurrency``"""

import threading
from decimal import Decimal
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import CouponRedemption, Order, PaymentGateway, ShippingMethod
from apps.orders.services.order_service import create_order_from_cart
from apps.stores.models import Store

User = get_user_model()


@skipUnless(connection.vendor == "postgresql", "نیازمندِ PostgreSQL")
class ConcurrentRedemptionTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.store = Store.objects.create(name="هم‌زمانی", slug="concurrency-store", status=Store.Status.ACTIVE)
        shop = ShopSettings.provision_for(self.store)
        shop.tax_percent = Decimal("0")
        shop.free_shipping_threshold = Decimal("999999999")
        shop.save()
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="v-cc")
        cat = Category.objects.create(store=self.store, name="c", slug="c-cc")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=cat, name="p", slug="p-cc", sku="CC1",
            price=Decimal("1000000"), stock=1000,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-cc", cost=Decimal("0"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="g", slug="g-cc")

    def _customer(self, n):
        user = User.objects.create_user(username=f"cc{n}", password="x12345678")
        customer = Customer.objects.create(user=user, full_name=f"c{n}", phone=f"0913000{n:04d}")
        address = Address.objects.create(
            customer=customer, receiver_name="x", phone=customer.phone, province="فارس", city="شیراز",
            postal_code="1111111111", full_address="x",
        )
        return customer, address

    def _race(self, jobs):
        barrier = threading.Barrier(len(jobs))
        results, errors = [], []

        def worker(job):
            try:
                barrier.wait()
                results.append(job())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(j,)) for j in jobs]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return results, errors

    def _order_job(self, customer, address, coupon):
        def job():
            cart = Cart.objects.create(customer=customer)
            CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
            return create_order_from_cart(
                cart, customer=customer, vendor=self.vendor, address=address, shipping_method=self.shipping,
                payment_gateway=self.gateway, coupon=coupon, store=self.store,
            )
        return job

    def test_total_limit_one_is_never_exceeded_under_concurrency(self):
        coupon = Coupon.objects.create(store=self.store, code="RACE", type="percent", value=10, usage_limit=1)
        jobs = [self._order_job(*self._customer(i), coupon) for i in range(8)]
        results, errors = self._race(jobs)
        self.assertEqual(errors, [])
        discounted = [o for o in results if o.coupon_discount > 0]
        self.assertEqual(len(discounted), 1)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(CouponRedemption.objects.filter(coupon=coupon).count(), 1)

    def test_per_customer_limit_holds_for_parallel_orders_of_one_customer(self):
        coupon = Coupon.objects.create(store=self.store, code="PERC", type="percent", value=10, per_customer_limit=1)
        customer, address = self._customer(99)
        results, errors = self._race([self._order_job(customer, address, coupon) for _ in range(6)])
        self.assertEqual(errors, [])
        self.assertEqual(len([o for o in results if o.coupon_discount > 0]), 1)
        self.assertEqual(CouponRedemption.objects.filter(coupon=coupon, customer=customer).count(), 1)

    def test_limit_n_allows_exactly_n(self):
        coupon = Coupon.objects.create(store=self.store, code="LIM3", type="percent", value=10, usage_limit=3)
        jobs = [self._order_job(*self._customer(200 + i), coupon) for i in range(8)]
        results, errors = self._race(jobs)
        self.assertEqual(errors, [])
        self.assertEqual(len([o for o in results if o.coupon_discount > 0]), 3)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 3)

    def test_ledger_and_counters_stay_consistent_after_races(self):
        """بعد از رقابت‌هایِ همزمان، ابزارِ تشخیصی هیچ ناهماهنگی‌ای نمی‌بیند."""
        from apps.cart.management.commands.verify_coupon_consistency import Command

        coupon = Coupon.objects.create(store=self.store, code="CONS", type="percent", value=10, usage_limit=2, per_customer_limit=1)
        jobs = [self._order_job(*self._customer(300 + i), coupon) for i in range(6)]
        customer, address = self._customer(399)
        jobs += [self._order_job(customer, address, coupon) for _ in range(3)]
        _, errors = self._race(jobs)
        self.assertEqual(errors, [])
        self.assertEqual(Command.collect(self.store), [])

    def test_parallel_payment_success_applies_effects_exactly_once(self):
        from apps.orders.models import Transaction
        from apps.orders.services.payment_service import simulate_payment

        coupon = Coupon.objects.create(store=self.store, code="PAYRACE", type="percent", value=10, usage_limit=5)
        customer, address = self._customer(500)
        order = self._order_job(customer, address, coupon)()
        results, errors = self._race([lambda: simulate_payment(Order.objects.get(pk=order.pk), True, store=self.store) for _ in range(4)])
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 3)
        self.assertTrue(all(isinstance(e, ValueError) for e in errors))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(Transaction.objects.filter(order=order, status="ok").count(), 1)
        self.assertEqual(CouponRedemption.objects.get(order=order).status, CouponRedemption.Status.REDEEMED)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(order.status_history.filter(to_status="processing").count(), 1)


@skipUnless(connection.vendor == "postgresql", "نیازمندِ PostgreSQL")
class ConcurrentCampaignExecutionTests(TransactionTestCase):
    """دو job هم‌زمانِ یک کمپین (هم‌پوشانیِ cron) هرگز پاداش/اعلانِ تکراری نمی‌سازند."""

    serialized_rollback = True

    def test_overlapping_runs_issue_each_customer_once(self):
        from apps.engagement.models import Campaign, CampaignIssuance
        from apps.engagement.services import campaign_service as cs
        from apps.notifications.models import NotificationOutbox

        store = Store.objects.create(name="هم‌زمانیِ کمپین", slug="campaign-race", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(store)
        for i in range(6):
            user = User.objects.create_user(username=f"cr{i}", password="x12345678")
            Customer.objects.create(user=user, full_name=f"c{i}", phone=f"0914000{i:04d}", email=f"c{i}@example.com")
            from apps.customers.models import CustomerProfile

            CustomerProfile.objects.create(store=store, customer=Customer.objects.get(user=user))
        campaign = cs.save_campaign(Campaign(
            store=store, name="race", rules={}, coupon_type="percent", coupon_value=Decimal("10"), code_valid_days=5, code_prefix="RC",
        ))
        cs.activate(campaign)

        barrier = threading.Barrier(3)
        errors = []

        def run():
            try:
                barrier.wait()
                cs.execute_campaign(Campaign.objects.get(pk=campaign.pk))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=run) for _ in range(3)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(CampaignIssuance.objects.count(), 6)
        self.assertEqual(Coupon.objects.filter(store=store, code__startswith="RC-").count(), 6)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="coupon.issued", channel="email").count(), 6)
