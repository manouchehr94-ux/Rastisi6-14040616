"""Customer account / order / payment isolation between stores for ONE shared global Customer (P0).

``Customer`` is global by design (one person, many stores). Everything commercial must still be scoped to the CURRENT store:
the order list and counters, order details, payment pages and actions, and card-to-card submission. A cross-store order code is a 404
(never 403/redirect, so its existence is not revealed) and nothing is mutated."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer, CustomerProfile
from apps.orders.models import CardTransferSubmission, Order, PaymentGateway, PaymentGatewayConfig, ShippingMethod
from apps.stores.models import Store, StoreDomain

User = get_user_model()
HOST_A, HOST_B = "acct-a.example.com", "acct-b.example.com"


def _domain(store, host):
    StoreDomain.objects.create(store=store, hostname=host, is_primary=True,
                               verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"], PAYMENTS_SIMULATION_ENABLED=True)
class SharedCustomerTwoStoreTests(TestCase):
    def setUp(self):
        self.a = Store.objects.get(slug="akhlaghi")
        self.b = Store.objects.create(name="Store B", slug="acct-store-b", status=Store.Status.ACTIVE)
        _domain(self.a, HOST_A); _domain(self.b, HOST_B)
        ShopSettings.provision_for(self.b); FooterSettings.provision_for(self.b)
        self.user = User.objects.create_user(username="09127770099", password="OldPass#2026")
        self.customer = Customer.objects.create(user=self.user, full_name="مشتری مشترک", phone="09127770099")
        self.address = Address.objects.create(customer=self.customer, receiver_name="م", phone="09127770099", province="تهران", city="تهران", full_address="x")
        self.data = {}
        for tag, store in (("a", self.a), ("b", self.b)):
            vendor = Vendor.objects.create(store=store, name=f"V{tag}", slug=f"acct-v-{tag}")
            category = Category.objects.create(store=store, name=f"C{tag}", slug=f"acct-c-{tag}")
            product = Product.objects.create(store=store, vendor=vendor, category=category, name=f"کالای {tag}", slug=f"acct-p-{tag}",
                                             sku=f"ACCT-{tag}", price=Decimal("100000"), stock=50)
            ship = ShippingMethod.objects.create(store=store, name="پست", slug=f"acct-ship-{tag}", cost=Decimal("0"))
            zibal = PaymentGateway.objects.create(store=store, name="زیبال", slug=f"zibal", is_active=True)
            c2c = PaymentGateway.objects.create(store=store, name="کارت", slug="card_to_card", is_active=True)
            cfg = PaymentGatewayConfig.objects.create(store=store, gateway_code="card_to_card", is_active=True)
            cfg.set_credentials({"destination_card": "6037997000000019", "holder_name": "علی"}); cfg.save()
            paid = Order.objects.create(code=f"AC-{tag.upper()}-PAID", store=store, customer=self.customer, vendor=vendor, address={"receiver_name": "م"},
                                        shipping_method=ship, payment_gateway=zibal, items_total=Decimal("100000"),
                                        grand_total=Decimal("100000") if tag == "a" else Decimal("700000"),
                                        payment_status=Order.PaymentStatus.PAID, status=Order.Status.PROCESSING)
            pending = Order.objects.create(code=f"AC-{tag.upper()}-PEND", store=store, customer=self.customer, vendor=vendor, address={"receiver_name": "م"},
                                           shipping_method=ship, payment_gateway=c2c, items_total=Decimal("100000"), grand_total=Decimal("100000"))
            self.data[tag] = {"store": store, "paid": paid, "pending": pending, "product": product, "host": HOST_A if tag == "a" else HOST_B}
        self.client.force_login(self.user)

    def get(self, host, path):
        return self.client.get(path, HTTP_HOST=host)

    def post(self, host, path, data=None):
        return self.client.post(path, data or {}, HTTP_HOST=host)

    # ---- list + stats
    def test_account_page_lists_only_the_current_stores_orders_and_stats(self):
        page = self.get(HOST_A, reverse("customers:account"))
        self.assertEqual(page.status_code, 200)
        codes = {o.code for o in page.context["orders"]}
        self.assertEqual(codes, {"AC-A-PAID", "AC-A-PEND"})
        self.assertNotContains(page, "AC-B-PAID")
        summary = page.context["store_summary"]
        self.assertEqual((summary["orders_count"], summary["total_spent"]), (2, Decimal("100000")))     # B's 700 000 is NOT added
        other = self.get(HOST_B, reverse("customers:account"))
        self.assertEqual({o.code for o in other.context["orders"]}, {"AC-B-PAID", "AC-B-PEND"})
        self.assertEqual(other.context["store_summary"]["total_spent"], Decimal("700000"))

    def test_global_customer_counters_are_never_used(self):
        Customer.objects.filter(pk=self.customer.pk).update(orders_count=99, total_spent=Decimal("999999999"))
        page = self.get(HOST_A, reverse("customers:account"))
        self.assertNotContains(page, "۹۹۹٬۹۹۹")
        self.assertNotContains(page, "999,999,999")
        self.assertEqual(page.context["store_summary"]["orders_count"], 2)

    def test_level_is_per_store_and_internal_status_other_than_vip_is_never_shown(self):
        CustomerProfile.objects.create(store=self.b, customer=self.customer, internal_status=CustomerProfile.InternalStatus.VIP)
        CustomerProfile.objects.create(store=self.a, customer=self.customer, internal_status=CustomerProfile.InternalStatus.WATCH)
        self.assertFalse(self.get(HOST_A, reverse("customers:account")).context["store_summary"]["is_vip"])
        self.assertTrue(self.get(HOST_B, reverse("customers:account")).context["store_summary"]["is_vip"])
        self.assertNotContains(self.get(HOST_A, reverse("customers:account")), "تحتِ نظر")

    def test_profile_update_response_has_store_scoped_stats(self):
        res = self.post(HOST_A, reverse("customers:account-profile-update"), {"full_name": "مشتری مشترک", "email": "", "city": ""})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["store_summary"]["total_spent"], Decimal("100000"))

    # ---- direct URL access
    def test_other_stores_order_detail_is_404_but_own_is_200(self):
        self.assertEqual(self.get(HOST_A, reverse("customers:account-order-detail", args=["AC-B-PAID"])).status_code, 404)
        self.assertEqual(self.get(HOST_B, reverse("customers:account-order-detail", args=["AC-A-PAID"])).status_code, 404)
        self.assertEqual(self.get(HOST_A, reverse("customers:account-order-detail", args=["AC-A-PAID"])).status_code, 200)
        self.assertEqual(self.get(HOST_B, reverse("customers:account-order-detail", args=["AC-B-PAID"])).status_code, 200)

    def test_every_order_page_and_payment_action_of_the_other_store_is_404_and_mutates_nothing(self):
        target = self.data["b"]["pending"]
        for name, kwargs in (("orders:payment-result", {}), ("orders:payment-start", {}), ("orders:payment-initiate", {}),
                             ("orders:card-transfer", {}), ("orders:payment-callback", {"status": "success"})):
            url = reverse(name, kwargs={"code": target.code, **kwargs})
            self.assertEqual(self.get(HOST_A, url).status_code, 404, name)
        res = self.post(HOST_A, reverse("orders:card-transfer", args=[target.code]), {"source_last4": "1234", "tracking_number": "TRK-CROSS-1"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(CardTransferSubmission.objects.count(), 0)
        target.refresh_from_db()
        self.assertEqual((target.payment_status, target.status), (Order.PaymentStatus.PENDING, Order.Status.PENDING))
        # the owner store still works
        self.assertEqual(self.get(HOST_B, reverse("orders:card-transfer", args=[target.code])).status_code, 200)

    def test_simulated_payment_callback_cannot_pay_another_stores_order(self):
        target = self.data["b"]["pending"]
        self.assertEqual(self.get(HOST_A, reverse("orders:payment-callback", args=[target.code, "success"])).status_code, 404)
        target.refresh_from_db()
        self.assertEqual(target.payment_status, Order.PaymentStatus.PENDING)

    def test_another_customer_still_cannot_open_an_order_of_the_same_store(self):
        other = User.objects.create_user(username="09127770098", password="x")
        Customer.objects.create(user=other, full_name="دیگری", phone="09127770098")
        self.client.force_login(other)
        self.assertEqual(self.get(HOST_A, reverse("customers:account-order-detail", args=["AC-A-PAID"])).status_code, 404)

    # ---- side effects
    def test_cart_badge_counts_only_the_current_stores_items(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.data["a"]["product"], quantity=2, unit_price=Decimal("100000"))
        CartItem.objects.create(cart=cart, product=self.data["b"]["product"], quantity=5, unit_price=Decimal("100000"))
        self.assertEqual(self.get(HOST_A, reverse("customers:account")).context["cart_count"], 2)
        self.assertEqual(self.get(HOST_B, reverse("customers:account")).context["cart_count"], 5)
