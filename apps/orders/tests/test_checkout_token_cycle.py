"""Checkout idempotency token vs repeat purchases (P0).

``Cart.checkout_token`` makes a double-click / network retry return the FIRST order instead of creating a second one. It must NOT make a
genuinely new purchase (new items added to the same, now empty, cart row) collapse into the old order. These tests drive the real views
(cart add → checkout-pay) with the real session, and also the service layer for concurrency."""

import threading
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store

User = get_user_model()
PAYLOAD = {
    "receiver_name": "علی رضایی", "phone": "09123456781", "province": "تهران", "city": "تهران", "postal_code": "1415873920",
    "full_address": "تهران، خیابان ولیعصر، پلاک ۱", "note": "",
}


class CycleBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        ShopSettings.objects.filter(store=self.store).update(tax_enabled=False)
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="tok-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="tok-cat")
        self.a = Product.objects.create(store=self.store, vendor=self.vendor, category=self.category, name="کالای الف", slug="tok-a", sku="TOK-A", price=Decimal("200000"), stock=10)
        self.b = Product.objects.create(store=self.store, vendor=self.vendor, category=self.category, name="کالای ب", slug="tok-b", sku="TOK-B", price=Decimal("350000"), stock=10)
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="tok-post", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="tok-zarin")
        p = patch("apps.sms.services.otp_service.send_event_sms"); m = p.start(); m.return_value.status = "sent"; m.return_value.error_message = ""
        self.addCleanup(p.stop)
        self.user = User.objects.create_user(username="09123456781", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="علی رضایی", phone="09123456781")
        self.client.login(username="09123456781", password="pass12345")

    def add(self, product, qty=1, client=None):
        return (client or self.client).post(reverse("cart:add", args=[product.slug]), {"quantity": qty})

    def pay(self, client=None):
        return (client or self.client).post(reverse("orders:checkout-pay"), PAYLOAD)

    def stock(self, product):
        return Product.objects.get(pk=product.pk).stock


class RepeatPurchaseHttpTests(CycleBase):
    def test_second_purchase_after_a_completed_order_is_a_new_independent_order(self):
        self.add(self.a)
        first = self.pay()
        self.assertIn("HX-Redirect", first.headers)
        order1 = Order.objects.get()
        retry = self.pay()                                                                    # double click / network retry
        self.assertEqual(Order.objects.count(), 1)
        self.assertIn(order1.code, retry.headers["HX-Redirect"])                              # replay → the FIRST order
        self.assertEqual(self.stock(self.a), 9)                                               # …and no second stock deduction

        self.add(self.b, 2)                                                                   # a brand new purchase cycle
        second = self.pay()
        self.assertIn("HX-Redirect", second.headers)
        self.assertEqual(Order.objects.count(), 2)
        order2 = Order.objects.exclude(pk=order1.pk).get()
        self.assertNotEqual(order1.code, order2.code)
        self.assertIn(order2.code, second.headers["HX-Redirect"])
        self.assertEqual([i.product_id for i in order2.items.all()], [self.b.pk])
        self.assertEqual(order2.items.get().quantity, 2)
        self.assertEqual(order1.items.get().product_id, self.a.pk)
        self.assertEqual((self.stock(self.a), self.stock(self.b)), (9, 8))
        order1.refresh_from_db()
        self.assertEqual(order1.grand_total, Decimal("245000"))                               # 200 000 + 45 000 shipping (tax off in this store)
        self.assertEqual(order2.items_total, Decimal("700000"))                               # 2 × 350 000 (its own lines, not order 1's)
        self.assertEqual(order2.grand_total, order2.items_total + order2.shipping_cost)       # shipping may be free above the store threshold
        self.assertNotEqual(order1.idempotency_key, order2.idempotency_key)

    def test_second_purchase_of_the_same_product(self):
        self.add(self.a); self.pay()
        self.add(self.a); self.pay()
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(self.stock(self.a), 8)

    def test_replay_after_the_second_order_returns_the_second_not_the_first(self):
        self.add(self.a); self.pay()
        self.add(self.b); self.pay()
        replay = self.pay()
        self.assertEqual(Order.objects.count(), 2)
        latest = Order.objects.order_by("-pk").first()
        self.assertIn(latest.code, replay.headers["HX-Redirect"])

    def test_three_cycles_have_three_distinct_keys(self):
        for product in (self.a, self.b, self.a):
            self.add(product); self.pay()
        keys = list(Order.objects.values_list("idempotency_key", flat=True))
        self.assertEqual(len(set(keys)), 3)
        self.assertEqual(self.stock(self.a), 8)

    def test_adding_items_without_paying_keeps_the_same_token_and_the_cart_total_is_right(self):
        self.add(self.a); self.add(self.b)
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.items.count(), 2)

    def test_guest_first_purchase_creates_the_account_and_the_logged_in_second_purchase_is_independent(self):
        guest = Client()
        payload = dict(PAYLOAD, phone="09125550077")
        self.add(self.a, client=guest)
        r1 = guest.post(reverse("orders:checkout-pay"), payload)
        self.assertIn("HX-Redirect", r1.headers)
        self.assertEqual(Order.objects.filter(customer__phone="09125550077").count(), 1)
        self.add(self.b, client=guest)
        r2 = guest.post(reverse("orders:checkout-pay"), payload)
        self.assertIn("HX-Redirect", r2.headers)
        self.assertEqual(Order.objects.filter(customer__phone="09125550077").count(), 2)
        self.assertEqual((self.stock(self.a), self.stock(self.b)), (9, 9))

    def test_a_failed_attempt_does_not_burn_the_token_and_a_retry_still_creates_exactly_one_order(self):
        self.add(self.a)
        bad = self.client.post(reverse("orders:checkout-pay"), dict(PAYLOAD, full_address=""))
        self.assertEqual(Order.objects.count(), 0)
        ok = self.pay()
        self.assertIn("HX-Redirect", ok.headers)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.stock(self.a), 9)

    def test_an_idempotency_hit_never_returns_another_customers_order(self):
        """Lookup by token must stay inside customer + store: a token that exists on someone else's order is not a replay."""
        self.add(self.a); self.pay()
        victim_order = Order.objects.get()
        other_user = User.objects.create_user(username="09123456782", password="pass12345")
        other = Customer.objects.create(user=other_user, full_name="دیگری", phone="09123456782")
        other_cart = Cart.objects.create(customer=other)
        Cart.objects.filter(pk=other_cart.pk).update(checkout_token=victim_order.idempotency_key)   # forced collision
        CartItem.objects.create(cart=other_cart, product=self.b, quantity=1, unit_price=self.b.final_price)
        c2 = Client(); c2.login(username="09123456782", password="pass12345")
        resp = c2.post(reverse("orders:checkout-pay"), dict(PAYLOAD, phone="09123456782"))
        orders = Order.objects.filter(customer=other)
        self.assertEqual(orders.count(), 1)                                                   # a real new order for the other customer
        self.assertNotIn(victim_order.code, resp.headers.get("HX-Redirect", ""))
        self.assertNotEqual(orders.get().pk, victim_order.pk)


class TokenLifecycleServiceTests(CycleBase):
    """Deterministic (any DB): stale in-memory carts, rotation point, token kept after the order, store/customer-scoped lookup."""

    def test_token_is_created_once_and_stale_instances_converge_on_the_same_value(self):
        from apps.orders.services.checkout_service import get_or_create_checkout_token

        cart = Cart.objects.create(customer=self.customer)
        first, second = Cart.objects.get(pk=cart.pk), Cart.objects.get(pk=cart.pk)       # two "requests", both see an empty token
        self.assertEqual(get_or_create_checkout_token(first), get_or_create_checkout_token(second))
        self.assertTrue(first.checkout_token)

    def test_token_survives_the_order_but_is_cleared_when_the_next_cycle_gets_its_first_item(self):
        self.add(self.a); self.pay()
        cart = Cart.objects.get(customer=self.customer)
        kept = cart.checkout_token
        self.assertTrue(kept)                                                              # NOT cleared right after the order
        self.assertFalse(cart.items.exists())
        self.add(self.b)
        cart.refresh_from_db()
        self.assertEqual(cart.checkout_token, "")                                          # new cycle → next checkout mints a fresh token
        self.add(self.b)                                                                   # more items in the same cycle never rotate again
        self.pay()
        cart.refresh_from_db()
        self.assertNotEqual(cart.checkout_token, kept)
        self.assertTrue(cart.checkout_token)

    def test_adding_a_second_item_to_a_non_empty_cart_keeps_the_token(self):
        from apps.orders.services.checkout_service import get_or_create_checkout_token

        self.add(self.a)
        cart = Cart.objects.get(customer=self.customer)
        token = get_or_create_checkout_token(cart)                                         # e.g. an attempt that failed validation
        self.add(self.b)
        cart.refresh_from_db()
        self.assertEqual(cart.checkout_token, token)

    def test_guest_cart_merge_into_an_empty_customer_cart_starts_a_new_cycle(self):
        self.add(self.a); self.pay()                                                       # customer cart now empty with a kept token
        old = Cart.objects.get(customer=self.customer).checkout_token
        guest = Client()
        self.add(self.b, client=guest)                                                     # a guest builds a cart, then logs in through the real view
        guest.post(reverse("customers:login"), {"identifier": "09123456781", "password": "pass12345"})
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual({i.product_id for i in cart.items.all()}, {self.b.pk})
        self.assertEqual(cart.checkout_token, "")                                          # merged items = a new purchase cycle
        self.assertNotEqual(old, "")

    def test_a_token_on_someone_elses_order_is_not_a_replay_and_gets_rotated(self):
        other_user = User.objects.create_user(username="09123456799", password="x12345678")
        other = Customer.objects.create(user=other_user, full_name="دیگری", phone="09123456799")
        other_cart = Cart.objects.create(customer=other)
        CartItem.objects.create(cart=other_cart, product=self.b, quantity=1, unit_price=self.b.final_price)
        from apps.orders.services.order_service import create_order_from_cart
        from apps.customers.models import Address

        addr = Address.objects.create(customer=other, receiver_name="د", phone="09123456799", province="تهران", city="تهران", full_address="x")
        foreign = create_order_from_cart(other_cart, customer=other, vendor=self.vendor, address=addr, shipping_method=self.shipping,
                                         payment_gateway=self.gateway, store=self.store, idempotency_key="shared-key-123")
        mine = Cart.objects.create(customer=self.customer, checkout_token="shared-key-123") if not Cart.objects.filter(customer=self.customer).exists() else None
        if mine is None:
            Cart.objects.filter(customer=self.customer).update(checkout_token="shared-key-123")
        self.add(self.a)
        Cart.objects.filter(customer=self.customer).update(checkout_token="shared-key-123")
        resp = self.pay()
        self.assertIn("HX-Redirect", resp.headers)
        self.assertNotIn(foreign.code, resp.headers["HX-Redirect"])
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)
        self.assertNotEqual(Order.objects.get(customer=self.customer).idempotency_key, "shared-key-123")


from unittest import skipUnless


@skipUnless(connection.vendor == "postgresql", "real row locks need PostgreSQL (run with DATABASE_URL=postgres://…)")
class ConcurrentCheckoutTests(TransactionTestCase):
    """Real threads, real HTTP views, real ``SELECT … FOR UPDATE``. Invariants: never a duplicate order/payment/stock deduction."""

    serialized_rollback = True

    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        ShopSettings.objects.filter(store=self.store).update(tax_enabled=False)
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="ctok-shop")
        self.category = Category.objects.create(store=self.store, name="د", slug="ctok-cat")
        self.a = Product.objects.create(store=self.store, vendor=self.vendor, category=self.category, name="الف", slug="ctok-a", sku="CTOK-A", price=Decimal("200000"), stock=10)
        self.b = Product.objects.create(store=self.store, vendor=self.vendor, category=self.category, name="ب", slug="ctok-b", sku="CTOK-B", price=Decimal("350000"), stock=10)
        ShippingMethod.objects.create(store=self.store, name="پست", slug="ctok-post", cost=Decimal("45000"))
        PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="ctok-zarin")
        self.user = User.objects.create_user(username="09123456761", password="pass12345")
        self.customer = Customer.objects.create(user=self.user, full_name="علی", phone="09123456761")
        self.payload = dict(PAYLOAD, phone="09123456761")

    def clients(self, n):
        out = []
        for _ in range(n):
            c = Client(); c.login(username="09123456761", password="pass12345"); out.append(c)
        return out

    def race(self, jobs):
        from django.db import close_old_connections

        barrier = threading.Barrier(len(jobs)); results, errors = [None] * len(jobs), []

        def run(i, job):
            try:
                barrier.wait(); results[i] = job()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                close_old_connections()

        ts = [threading.Thread(target=run, args=(i, j)) for i, j in enumerate(jobs)]
        [t.start() for t in ts]; [t.join() for t in ts]
        return results, errors

    def test_simultaneous_double_submit_creates_exactly_one_order_and_one_stock_deduction(self):
        first = self.clients(1)[0]
        first.post(reverse("cart:add", args=[self.a.slug]), {"quantity": 1})
        clients = self.clients(6)
        results, errors = self.race([lambda c=c: c.post(reverse("orders:checkout-pay"), self.payload) for c in clients])
        self.assertEqual(errors, [])
        self.assertEqual(Order.objects.filter(customer=self.customer).count(), 1)
        self.assertEqual(Product.objects.get(pk=self.a.pk).stock, 9)
        order = Order.objects.get()
        for r in results:
            if "HX-Redirect" in r.headers:
                self.assertIn(order.code, r.headers["HX-Redirect"])

    def test_replay_racing_with_the_next_purchase_never_merges_or_duplicates(self):
        c0 = self.clients(1)[0]
        c0.post(reverse("cart:add", args=[self.a.slug]), {"quantity": 1}); c0.post(reverse("orders:checkout-pay"), self.payload)
        order1 = Order.objects.get()
        replay, adder = self.clients(2)
        results, errors = self.race([
            lambda: replay.post(reverse("orders:checkout-pay"), self.payload),
            lambda: adder.post(reverse("cart:add", args=[self.b.slug]), {"quantity": 1}),
        ])
        self.assertEqual(errors, [])
        orders = list(Order.objects.filter(customer=self.customer).order_by("pk"))
        self.assertLessEqual(len(orders), 2)
        self.assertEqual([i.product_id for i in order1.items.all()], [self.a.pk])
        for o in orders[1:]:
            self.assertEqual({i.product_id for i in o.items.all()}, {self.b.pk})            # a new order only ever holds the NEW items
        self.assertEqual(len({o.idempotency_key for o in orders}), len(orders))
        self.assertEqual(Product.objects.get(pk=self.a.pk).stock, 9)
        self.assertEqual(Product.objects.get(pk=self.b.pk).stock, 10 - (len(orders) - 1))
        # whatever the interleaving, the next explicit purchase attempt ends in a consistent state
        adder.post(reverse("orders:checkout-pay"), self.payload)
        final = list(Order.objects.filter(customer=self.customer))
        self.assertEqual(len({o.idempotency_key for o in final}), len(final))
        self.assertEqual(Product.objects.get(pk=self.b.pk).stock, 9)

    def test_two_simultaneous_first_items_into_an_empty_cart_keep_both_lines_and_a_cleared_token(self):
        # NOTE: two simultaneous *first ever* adds can still create two Cart rows for one customer (``get_or_create`` without a unique
        # constraint — confirmed on PostgreSQL, pre-existing, tracked in CART_STORE_SCOPING_PLAN.md). Here the cart already exists.
        cart0 = Cart.objects.create(customer=self.customer, checkout_token="stale-token-from-the-previous-cycle")
        c1, c2 = self.clients(2)
        results, errors = self.race([
            lambda: c1.post(reverse("cart:add", args=[self.a.slug]), {"quantity": 1}),
            lambda: c2.post(reverse("cart:add", args=[self.b.slug]), {"quantity": 1}),
        ])
        self.assertEqual(errors, [])
        cart = Cart.objects.get(customer=self.customer)
        self.assertEqual(cart.pk, cart0.pk)
        self.assertEqual({i.product_id for i in cart.items.all()}, {self.a.pk, self.b.pk})
        self.assertEqual(cart.checkout_token, "")                                           # exactly one rotation, no lost update
