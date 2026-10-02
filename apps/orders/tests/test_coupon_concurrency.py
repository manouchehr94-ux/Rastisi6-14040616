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
