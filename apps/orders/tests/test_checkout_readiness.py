"""RS-12 — checkout must not promise a payment it cannot take: no gateway / no shipping method ⇒ a clear notice, a disabled
button, and (server side) NO side effects (no guest account, no SMS, no order). RS-11 — the rendered summary reconciles."""

import json
import re
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.customers.models import Customer
from apps.orders.models import Order, PaymentGateway, ShippingMethod
from apps.stores.models import Store


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=self.store, name="V", slug="v-rdy")
        category = Category.objects.create(store=self.store, name="C", slug="c-rdy")
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کتانی", slug="k-rdy", sku="RDY1",
            price=Decimal("6450000"), discount_percent=18, stock=20,
        )
        self.payload = {
            "receiver_name": "علی", "phone": "09123456780", "province": "تهران", "city": "تهران",
            "postal_code": "1415873920", "full_address": "تهران، ولیعصر", "note": "",
        }
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 6})

    def page(self):
        return self.client.get(reverse("orders:checkout-step1"))


class NoGatewayTests(_Base):
    def setUp(self):
        super().setUp()
        ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rdy", cost=45000)

    def test_page_explains_and_disables_the_button_and_makes_no_security_promise(self):
        r = self.page()
        self.assertContains(r, "پرداخت آنلاین هنوز برای این فروشگاه فعال نشده است")
        self.assertContains(r, "ثبت سفارش در دسترس نیست")
        self.assertContains(r, "disabled")
        self.assertNotContains(r, "ادامه و پرداخت")
        self.assertNotContains(r, "نماد اعتماد")
        self.assertNotContains(r, "WELCOME10")
        self.assertNotContains(r, "پرداخت امن")
        self.assertFalse(r.context["readiness"]["can_place_order"])

    def test_pay_post_has_no_side_effects_and_returns_the_reason(self):
        customers, orders = Customer.objects.count(), Order.objects.count()
        r = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertNotIn("HX-Redirect", r.headers)
        self.assertEqual((Customer.objects.count(), Order.objects.count()), (customers, orders))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("پرداخت آنلاین", json.loads(r.headers["HX-Trigger"])["toast"]["message"])


class NoShippingTests(_Base):
    def setUp(self):
        super().setUp()
        PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="z-rdy")

    def test_missing_shipping_blocks_with_its_own_message(self):
        r = self.page()
        self.assertContains(r, "روش ارسالی برای این فروشگاه تعریف نشده است")
        self.assertNotContains(r, "ادامه و پرداخت")
        self.assertNotContains(r, "هزینه ارسال")  # no fake "0" shipping row without a method
        count = Customer.objects.count()
        self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertEqual(Customer.objects.count(), count)


class ReadyCheckoutTests(_Base):
    def setUp(self):
        super().setUp()
        ShippingMethod.objects.create(store=self.store, name="پست", slug="post-rdy2", cost=45000)
        PaymentGateway.objects.create(store=self.store, name="زرین‌پال", slug="z-rdy2")

    def test_ready_checkout_keeps_the_pay_button_and_reconciles(self):
        r = self.page()
        self.assertTrue(r.context["readiness"]["can_place_order"])
        self.assertContains(r, "ادامه و پرداخت")
        b = r.context["totals"]["breakdown"]
        self.assertTrue(b["reconciles"], b)
        self.assertContains(r, "جمع کالاها (قیمت اصلی)")
        self.assertContains(r, "جمع پس از تخفیف کالا")
        # rows printed in the page add up to the printed payable amount
        self.assertEqual(b["checked_total"], r.context["totals"]["grand_total"])

    def test_empty_cart_is_not_reported_as_a_missing_gateway(self):
        self.client.cookies.clear()
        r = self.client.get(reverse("orders:checkout-step1"))
        self.assertContains(r, "سبد خرید شما خالی است")
        self.assertNotContains(r, "هنوز برای این فروشگاه فعال نشده")
