"""begin_checkout identity = one checkout CYCLE (not the cart row, not a 24 h window). Real views, real sessions, real order placement."""

import json
import re
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart
from apps.catalog.models import Category, InventoryReservation, Product, Vendor
from apps.core.models import ShopSettings
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection

HOST_A = "cyc-a.brand-example.ir"
HOST_B = "cyc-b.brand-example.ir"
EVENTS_RE = re.compile(r'<script id="rs-track-events" type="application/json">(.*?)</script>', re.S)
PAYLOAD = {"receiver_name": "علی رضایی", "phone": "09125550077", "province": "تهران", "city": "تهران", "postal_code": "1415873920", "full_address": "تهران، ولیعصر ۱", "note": ""}


def begin_checkout_events(response):
    match = EVENTS_RE.search(response.content.decode())
    return [e for e in (json.loads(match.group(1)) if match else []) if e["name"] == "begin_checkout"]


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"], RASTISI_STOREFRONT_TRACKING_ENABLED=True)
class CycleFixture(TestCase):
    def setUp(self):
        cache.clear()
        for target in ("apps.stores.services.publication_service.is_publicly_visible",):
            p = mock.patch(target, return_value=True); p.start(); self.addCleanup(p.stop)
        p = mock.patch("apps.sms.services.otp_service.send_event_sms"); m = p.start(); m.return_value.status = "sent"; m.return_value.error_message = ""; self.addCleanup(p.stop)
        self.store = Store.objects.get(slug="akhlaghi")
        ShopSettings.objects.filter(store=self.store).update(tax_enabled=False)
        StoreDomain.objects.create(store=self.store, hostname=HOST_A, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        conn = StoreIntegrationConnection.objects.create(store=self.store, provider_code="google_analytics", is_active=True)
        conn.set_credentials({"measurement_id": "G-AAAA1111"}); conn.save()
        vendor = Vendor.objects.create(store=self.store, name="v", slug="cyc-v")
        cat = Category.objects.create(store=self.store, name="c", slug="cyc-c")
        self.a = Product.objects.create(store=self.store, vendor=vendor, category=cat, name="الف", slug="cyc-a", sku="CYC-A", price=Decimal("200000"), stock=20)
        self.b = Product.objects.create(store=self.store, vendor=vendor, category=cat, name="ب", slug="cyc-b", sku="CYC-B", price=Decimal("350000"), stock=20)
        ShippingMethod.objects.create(store=self.store, name="پست", slug="cyc-post", cost=Decimal("45000"))
        PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="cyc-zarin")

    def visitor(self):
        return Client(HTTP_HOST=HOST_A)

    def add(self, client, product, qty=1):
        return client.post(reverse("cart:add", args=[product.slug]), {"quantity": qty}, HTTP_HX_REQUEST="true")

    def enter(self, client):
        events = begin_checkout_events(client.get("/checkout/"))
        return events[0]["id"] if events else None

    def pay(self, client):
        response = client.post(reverse("orders:checkout-pay"), PAYLOAD, HTTP_HX_REQUEST="true")
        self.assertIn("HX-Redirect", response.headers, response.content[:300])
        return response



class CheckoutCycleIdentityTests(CycleFixture):
    # ---- the defect (reproduced) ----------------------------------------------------------------------------------------------------
    def test_a_guest_who_orders_and_starts_a_new_purchase_gets_a_new_checkout_identity(self):
        guest = self.visitor()
        self.add(guest, self.a)
        first = self.enter(guest)
        self.pay(guest)
        self.add(guest, self.b)
        second = self.enter(guest)
        self.assertTrue(first and second)
        self.assertNotEqual(first, second, "a genuinely new purchase must not reuse the previous checkout identity")

    # ---- stability within a cycle ---------------------------------------------------------------------------------------------------
    def test_refresh_and_a_second_tab_keep_the_same_identity_within_a_cycle(self):
        guest = self.visitor()                                # a second tab shares the cookie jar = the same Client
        self.add(guest, self.a)
        ids = {self.enter(guest) for _ in range(3)}
        self.assertEqual(len(ids), 1)
        self.add(guest, self.b)                              # more items in the same open checkout: same cycle
        self.assertEqual({self.enter(guest)}, ids)

    def test_a_failed_payment_attempt_or_checkout_edits_do_not_change_the_identity(self):
        guest = self.visitor()
        self.add(guest, self.a)
        first = self.enter(guest)
        bad = guest.post(reverse("orders:checkout-pay"), dict(PAYLOAD, postal_code="x"), HTTP_HX_REQUEST="true")
        self.assertNotIn("HX-Redirect", bad.headers)
        self.assertEqual(self.enter(guest), first)

    def test_every_new_cycle_has_its_own_identity_for_guest_and_logged_in_visitors(self):
        guest = self.visitor()
        seen = []
        for product in (self.a, self.b, self.a):
            self.add(guest, product)
            seen.append(self.enter(guest))
            self.pay(guest)
        self.assertEqual(len(set(seen)), 3)

    def test_an_order_placed_from_another_browser_does_not_change_the_open_checkouts_identity(self):
        one, other = self.visitor(), self.visitor()
        self.add(one, self.a)
        before = self.enter(one)
        self.add(other, self.b)
        self.pay(other)                                      # another cart, another cycle (and, after login, possibly the same account)
        self.assertEqual(self.enter(one), before)

    def test_the_tracking_code_path_adds_no_writes_to_the_get(self):
        """begin_checkout identity is derived from existing rows: the checkout GET writes nothing to the cart, order or reservation tables."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        guest = self.visitor()
        self.add(guest, self.a)
        with CaptureQueriesContext(connection) as ctx:
            guest.get("/checkout/")
        writes = [q["sql"][:120] for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                  and any(t in q["sql"] for t in ("cart_cart", "cart_cartitem", "orders_", "catalog_inventoryreservation"))]
        self.assertEqual(writes, [])
        cart = Cart.objects.get()
        self.assertEqual(cart.checkout_token, "")                      # the idempotency token is untouched by tracking

    def test_the_identity_is_tenant_scoped_and_carries_no_personal_data(self):
        guest = self.visitor()
        self.add(guest, self.a)
        identity = self.enter(guest)
        self.assertIn(f"-{self.store.pk}-", identity)
        for secret in (PAYLOAD["phone"], "token", Cart.objects.get().session_key):
            self.assertNotIn(secret, identity or "x")

    @override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=False)
    def test_nothing_is_built_when_tracking_is_off(self):
        guest = self.visitor()
        self.add(guest, self.a)
        self.assertIsNone(self.enter(guest))


class LegacyIdentityDefectTests(CycleFixture):
    """Reproduces the defects of the first implementation (identity = ``bc-<store>-<cart>-<number of the CUSTOMER's orders in the store>``) next to the corrected behaviour.
"""

    @staticmethod
    def legacy_identity(store, cart, customer):
        count = Order.objects.filter(store=store, customer=customer).count() if customer is not None else 0
        return f"bc-{store.pk}-{cart.pk}-{count}"

    def _place_order_from_cart(self, cart, customer):
        from apps.customers.models import Address
        from apps.orders.services.order_service import create_order_from_cart

        address = Address.objects.create(customer=customer, receiver_name="t", phone=customer.phone, province="تهران", city="تهران", full_address="x")
        return create_order_from_cart(cart, customer=customer, vendor=self.a.vendor, address=address, shipping_method=ShippingMethod.objects.get(store=self.store),
                                      payment_gateway=PaymentGateway.objects.get(store=self.store), store=self.store, idempotency_key=f"legacy-{cart.pk}-{Order.objects.count()}")

    def test_defect_1_an_unauthenticated_cart_reused_after_an_order_collided_and_now_does_not(self):
        from apps.cart.models import CartItem
        from apps.core import tracking_events
        from apps.customers.models import Customer
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="09125550088", password="x12345678")
        customer = Customer.objects.create(user=user, full_name="t", phone="09125550088")
        cart = Cart.objects.create(session_key="g" * 32)                              # a guest (session) cart: customer is None
        CartItem.objects.create(cart=cart, product=self.a, quantity=1, unit_price=self.a.price)
        legacy_before = self.legacy_identity(self.store, cart, None)
        new_before = tracking_events.build_begin_checkout(self.store, cart)["id"]
        self._place_order_from_cart(cart, customer)                                    # the cycle ends; the cart row is re-used
        cart.items.all().delete()
        CartItem.objects.create(cart=cart, product=self.b, quantity=1, unit_price=self.b.price)
        self.assertEqual(self.legacy_identity(self.store, cart, None), legacy_before)  # OLD: identical identity for an independent purchase  ← the defect
        self.assertNotEqual(tracking_events.build_begin_checkout(self.store, cart)["id"], new_before)  # NEW: different

    def test_defect_2_an_unrelated_order_of_the_same_customer_changed_the_identity_of_an_open_checkout(self):
        from apps.customers.models import Customer
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="09125550099", password="x12345678")
        customer = Customer.objects.create(user=user, full_name="t", phone="09125550099")
        client = self.visitor(); client.force_login(user)
        self.add(client, self.a)
        before = self.enter(client)
        cart = Cart.objects.get(customer=customer)
        legacy_before = self.legacy_identity(self.store, cart, customer)
        Order.objects.create(store=self.store, customer=customer, code="UNREL-1", vendor=self.a.vendor,       # e.g. an order made by an admin for this customer
                             payment_gateway=PaymentGateway.objects.get(store=self.store), shipping_method=ShippingMethod.objects.get(store=self.store))
        self.assertNotEqual(self.legacy_identity(self.store, cart, customer), legacy_before)                  # OLD: identity moved mid-checkout → duplicate event  ← the defect
        self.assertEqual(self.enter(client), before)                                                          # NEW: unchanged

    def test_authenticated_customer_cycles_are_independent_and_stable(self):
        from apps.customers.models import Customer
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="09125550066", password="x12345678")
        Customer.objects.create(user=user, full_name="t", phone="09125550066")
        client = self.visitor(); client.force_login(user)
        self.add(client, self.a)
        first = self.enter(client)
        self.assertEqual(self.enter(client), first)
        self.pay(client)
        self.add(client, self.b)
        second = self.enter(client)
        self.assertNotEqual(first, second)
        self.assertEqual(self.enter(client), second)

    def test_a_cycle_in_another_store_cannot_move_this_stores_identity(self):
        from apps.core import tracking_events
        from apps.cart.models import CartItem

        other = Store.objects.create(name="Other", slug="cyc-other", status=Store.Status.ACTIVE)
        cart = Cart.objects.create(session_key="h" * 32)
        CartItem.objects.create(cart=cart, product=self.a, quantity=1, unit_price=self.a.price)
        before = tracking_events.build_begin_checkout(self.store, cart)["id"]
        self.assertEqual(tracking_events.checkout_cycle(other, cart), 0)
        self.assertEqual(tracking_events.build_begin_checkout(self.store, cart)["id"], before)
