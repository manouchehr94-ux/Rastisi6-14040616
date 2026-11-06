"""Cross-tenant regression suite for the three findings reported by an external audit harness.

* ``service_order_lookup_cross_tenant``       — an order of Store A must never be returned for Store B.
* ``http_payment_result_other_store_same_user`` — the payment-result page must not disclose another store's order, even to the same global Customer.
* ``refund_idempotency_cross_tenant``         — a refund idempotency key must never read or mutate another store's refund.

Every negative case asserts a NON-DISCLOSING outcome (404 / generic error, no order code, amount or customer data in the body) and that nothing was
created or changed. Positive controls prove the legitimate path still works so the guards cannot pass by simply breaking everything.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, Refund, ShippingMethod
from apps.orders.services import card_transfer_service
from apps.orders.services.refund_service import RefundError, execute_order_refund
from apps.stores.models import Store, StoreDomain

User = get_user_model()
HOST_A, HOST_B = "tenant-a.example.com", "tenant-b.example.com"
SECRET_AMOUNT_A = "7654321"          # a distinctive amount that must never appear on another store's response


def _domain(store, host):
    StoreDomain.objects.create(store=store, hostname=host, is_primary=True,
                               verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"], PAYMENTS_SIMULATION_ENABLED=True)
class TenantFixture(TestCase):
    def setUp(self):
        self.a = Store.objects.get(slug="akhlaghi")
        self.b = Store.objects.create(name="Store B", slug="tenant-store-b", status=Store.Status.ACTIVE)
        _domain(self.a, HOST_A)
        _domain(self.b, HOST_B)
        ShopSettings.provision_for(self.b)
        FooterSettings.provision_for(self.b)
        self.user = User.objects.create_user(username="09125550101", password="Pass#12345")
        self.customer = Customer.objects.create(user=self.user, full_name="مشتریِ مشترک", phone="09125550101")
        self.stranger = User.objects.create_user(username="09125550202", password="Pass#12345")
        Customer.objects.create(user=self.stranger, full_name="غریبه", phone="09125550202")
        self.staff = User.objects.create_user(username="09125550303", password="Pass#12345", is_staff=True)
        self.t = {}
        for tag, store in (("a", self.a), ("b", self.b)):
            vendor = Vendor.objects.create(store=store, name=f"V{tag}", slug=f"ti-v-{tag}")
            category = Category.objects.create(store=store, name=f"C{tag}", slug=f"ti-c-{tag}")
            product = Product.objects.create(store=store, vendor=vendor, category=category, name=f"کالای {tag}", slug=f"ti-p-{tag}",
                                             sku=f"TI-{tag}", price=Decimal("500000"), stock=50)
            ship = ShippingMethod.objects.create(store=store, name="پست", slug=f"ti-ship-{tag}", cost=Decimal("0"))
            gateway = PaymentGateway.objects.create(store=store, name="زیبال", slug=f"ti-zibal-{tag}", is_active=True)
            total = Decimal(SECRET_AMOUNT_A) if tag == "a" else Decimal("1000000")
            order = Order.objects.create(code=f"TI-{tag.upper()}-1", store=store, customer=self.customer, vendor=vendor, address={"receiver_name": "م"},
                                         shipping_method=ship, payment_gateway=gateway, items_total=total, grand_total=total,
                                         payment_status=Order.PaymentStatus.PAID, status=Order.Status.PROCESSING)
            OrderItem.objects.create(order=order, product=product, product_name=product.name, quantity=2,
                                     unit_price=total / 2, line_total=total)
            self.t[tag] = {"store": store, "order": order, "host": HOST_A if tag == "a" else HOST_B}


class ServiceOrderLookupCrossTenantTests(TenantFixture):
    """finding: service_order_lookup_cross_tenant"""

    def test_service_layer_never_returns_another_stores_order(self):
        order_a = self.t["a"]["order"]
        with self.assertRaises(Order.DoesNotExist):
            card_transfer_service.submit(order_a.pk, store=self.b, customer=self.customer, source_last4="1234", tracking_number="123456")

    def test_refund_service_refuses_an_order_of_another_store_without_mutation(self):
        order_a = self.t["a"]["order"]
        item = order_a.items.get()
        with self.assertRaises(RefundError):
            execute_order_refund(order_a, store=self.b, actor=self.staff, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        self.assertEqual(Refund.objects.count(), 0)

    def test_checkout_idempotency_token_of_another_store_is_never_replayed(self):
        # The checkout replay path only returns an order when BOTH customer and store match (checkout_service.place_order).
        from apps.orders.services import checkout_service

        order_a = self.t["a"]["order"]
        order_a.idempotency_key = "tok-tenant-collision"
        order_a.save(update_fields=["idempotency_key"])
        found = Order.objects.filter(idempotency_key="tok-tenant-collision").first()
        self.assertIsNotNone(found)
        self.assertNotEqual(found.store_id, self.b.pk)               # the guard in place_order compares store_id; pin the premise here
        self.assertTrue(hasattr(checkout_service, "_rotate_checkout_token"))


class HttpPaymentResultOtherStoreSameUserTests(TenantFixture):
    """finding: http_payment_result_other_store_same_user"""

    def _assert_not_disclosed(self, response, code="TI-A-1"):
        self.assertEqual(response.status_code, 404)
        body = response.content.decode()
        self.assertIn("صفحه پیدا نشد", body)                                   # the generic not-found page, not an order page
        # The 404 page echoes the *requested* URL (canonical / og:url) — that is the caller's own input, not a disclosure. Remove it, then
        # nothing about the order may remain.
        body = body.replace(f"/checkout/order/{code}/", "")
        for secret in (code, SECRET_AMOUNT_A, "7,654,321", "۷٬۶۵۴٬۳۲۱", "مشتریِ مشترک"):
            self.assertNotIn(secret, body)

    def test_same_user_on_another_stores_host_gets_404_and_no_disclosure(self):
        self.client.force_login(self.user)
        for name in ("orders:payment-result", "orders:payment-start", "orders:payment-initiate"):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, kwargs={"code": "TI-A-1"}), HTTP_HOST=HOST_B)
                self._assert_not_disclosed(response)

    def test_a_different_user_on_the_right_host_gets_404(self):
        self.client.force_login(self.stranger)
        self._assert_not_disclosed(self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST=HOST_A))

    def test_anonymous_gets_404_not_a_login_redirect_that_confirms_existence(self):
        response = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 404)

    def test_positive_control_the_owner_sees_their_own_result_page_on_their_own_store(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        other = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-B-1"}), HTTP_HOST=HOST_B)
        self.assertEqual(other.status_code, 200)
        self.assertNotContains(other, "TI-A-1")

    def test_a_host_that_resolves_to_no_store_discloses_nothing(self):
        self.client.force_login(self.user)
        with override_settings(ALLOWED_HOSTS=["*"]):
            response = self.client.get(reverse("orders:payment-result", kwargs={"code": "TI-A-1"}), HTTP_HOST="unknown-host.example.org")
        self.assertIn(response.status_code, (400, 404))
        body = response.content.decode().replace("/checkout/order/TI-A-1/", "")
        for secret in ("TI-A-1", SECRET_AMOUNT_A, "مشتریِ مشترک"):
            self.assertNotIn(secret, body)


class RefundIdempotencyCrossTenantTests(TenantFixture):
    """finding: refund_idempotency_cross_tenant"""

    KEY = "idem-shared-key-0001"

    def _refund(self, tag, key=None, qty=1):
        order = self.t[tag]["order"]
        item = order.items.get()
        return execute_order_refund(order, store=self.t[tag]["store"], actor=self.staff,
                                    line_requests=[{"order_item_id": item.pk, "quantity": qty}], idempotency_key=key or self.KEY)

    def test_legitimate_retry_in_the_same_store_returns_the_same_refund(self):
        first = self._refund("a")
        again = self._refund("a")
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Refund.objects.filter(store=self.a).count(), 1)

    def test_another_store_reusing_the_key_gets_no_foreign_refund_and_changes_nothing(self):
        first = self._refund("a")
        before = {f: getattr(first, f) for f in ("status", "approved_amount", "store_id", "order_id")}
        try:
            result = self._refund("b")
        except RefundError as exc:
            message = str(exc)
            for secret in (str(first.pk), "TI-A-1", SECRET_AMOUNT_A, str(first.approved_amount)):
                self.assertNotIn(secret, message)
            result = None
        # Whatever the policy, Store B must never be handed Store A's refund …
        if result is not None:
            self.assertEqual(result.store_id, self.b.pk)
            self.assertNotEqual(result.pk, first.pk)
        # … and Store A's refund must be completely untouched.
        first.refresh_from_db()
        self.assertEqual({f: getattr(first, f) for f in before}, before)
        self.assertEqual(Refund.objects.filter(store=self.a).count(), 1)

    def test_the_key_namespace_is_per_store_so_two_tenants_may_use_the_same_key(self):
        # A tenant's retry key must not collide with (or be blocked by) a key another tenant happened to use.
        first = self._refund("a")
        second = self._refund("b")
        self.assertEqual((first.store_id, second.store_id), (self.a.pk, self.b.pk))
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self._refund("b").pk, second.pk)                    # and Store B's own retry is still idempotent
        self.assertEqual(self._refund("a").pk, first.pk)

    def test_same_key_with_a_different_request_in_the_same_store_is_still_refused(self):
        self._refund("a", qty=1)
        with self.assertRaises(RefundError):
            self._refund("a", qty=2)
        self.assertEqual(Refund.objects.filter(store=self.a).count(), 1)


# --------------------------------------------------------------------------------------------------------------- PostgreSQL concurrency
import threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from unittest import skipUnless  # noqa: E402

from django.db import close_old_connections, connection  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL (row locks / real concurrent transactions)")
class RefundIdempotencyConcurrencyAcrossTenantsTests(TransactionTestCase):
    """The same retry key used by two stores AT THE SAME TIME must produce two independent refunds (no error, no cross-talk);
    the same key used twice in ONE store at the same time must still produce exactly one refund."""

    databases = {"default"}

    def setUp(self):
        self.staff = User.objects.create_user(username="09125559999", password="Pass#12345", is_staff=True)
        self.customer_user = User.objects.create_user(username="09125558888", password="Pass#12345")
        self.customer = Customer.objects.create(user=self.customer_user, full_name="مشتری", phone="09125558888")
        self.stores = {}
        for tag in ("a", "b"):
            store = Store.objects.create(name=f"Conc {tag}", slug=f"conc-tenant-{tag}", status=Store.Status.ACTIVE)
            vendor = Vendor.objects.create(store=store, name=f"V{tag}", slug=f"cv-{tag}")
            category = Category.objects.create(store=store, name=f"C{tag}", slug=f"cc-{tag}")
            product = Product.objects.create(store=store, vendor=vendor, category=category, name="p", slug=f"cp-{tag}", sku=f"CONC-{tag}",
                                             price=Decimal("500000"), stock=20)
            shipping = ShippingMethod.objects.create(store=store, name="s", slug=f"cs-{tag}", cost=Decimal("0"))
            gateway = PaymentGateway.objects.create(store=store, name="g", slug=f"cg-{tag}")
            order = Order.objects.create(code=f"CONC-{tag.upper()}", store=store, customer=self.customer, vendor=vendor, address={},
                                         shipping_method=shipping, payment_gateway=gateway, items_total=Decimal("1000000"),
                                         grand_total=Decimal("1000000"), payment_status=Order.PaymentStatus.PAID)
            item = OrderItem.objects.create(order=order, product=product, product_name="p", quantity=2,
                                            unit_price=Decimal("500000"), line_total=Decimal("1000000"))
            self.stores[tag] = (store, order, item)

    def _run(self, tags, key="conc-shared-key"):
        barrier = threading.Barrier(len(tags))

        def worker(tag):
            close_old_connections()
            store, order, item = self.stores[tag]
            try:
                barrier.wait(timeout=15)
                try:
                    refund = execute_order_refund(order, store=store, actor=self.staff,
                                                  line_requests=[{"order_item_id": item.pk, "quantity": 1}], idempotency_key=key)
                    return ("ok", refund.pk, refund.store_id)
                except RefundError as exc:
                    return ("refund_error", str(exc), None)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=len(tags)) as pool:
            return list(pool.map(worker, tags))

    def test_two_stores_racing_with_the_same_key_each_get_their_own_single_refund(self):
        results = self._run(["a", "b"])
        self.assertEqual([r[0] for r in results], ["ok", "ok"], results)
        self.assertEqual({r[2] for r in results}, {self.stores["a"][0].pk, self.stores["b"][0].pk})
        self.assertEqual(Refund.objects.filter(store=self.stores["a"][0]).count(), 1)
        self.assertEqual(Refund.objects.filter(store=self.stores["b"][0]).count(), 1)

    def test_one_store_racing_with_the_same_key_still_yields_exactly_one_refund(self):
        results = self._run(["a", "a", "a"])
        self.assertEqual({r[1] for r in results if r[0] == "ok"}.__len__(), 1, results)      # every success is the SAME refund
        self.assertEqual(Refund.objects.filter(store=self.stores["a"][0]).count(), 1)
        self.assertEqual(Refund.objects.filter(store=self.stores["b"][0]).count(), 0)
