"""H7: سیاستِ واحدِ مبلغ — نمایش = ساختِ سفارش = درگاه؛ هر تغییرِ مبلغِ مرتبط پس از نمایشِ خلاصه‌ی تسویه‌حساب،
سفارش را نمی‌سازد و مشتری باید مبلغِ جدید را ببیند و دوباره تأیید کند. قیمتِ سبد (اسنپ‌شات) هرگز کورکورانه
مبنا نیست و مبلغِ ارسالیِ کلاینت فقط برایِ مقایسه است."""

import json
import re
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import Order, PaymentAttempt, PaymentGateway, PaymentGatewayConfig, ShippingMethod
from apps.orders.services import refund_service
from apps.orders.services.gateway_payment_service import initiate_payment
from apps.orders.services.order_service import PriceChangedError, create_order_from_cart
from apps.stores.models import Store

User = get_user_model()
EXPECTED_RE = re.compile(r'"expected_total":\s*"(\d+)"')


class PriceConfirmationBase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        shop = ShopSettings.load(store=self.store)
        shop.tax_percent = Decimal("0")
        shop.free_shipping_threshold = Decimal("999999999")
        shop.gift_wrap_available, shop.gift_wrap_price = True, Decimal("20000")
        shop.save()
        self.vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-h7")
        cat = Category.objects.create(store=self.store, name="د", slug="cat-h7")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=cat, name="کالا", slug="p-h7", sku="H71",
            price=Decimal("200000"), stock=10, gift_wrap_enabled=True,
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-h7", cost=Decimal("45000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-h7")
        user = User.objects.create_user(username="09127770001", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09127770001")
        self.client.login(username="09127770001", password="pass12345")
        self.payload = {
            "receiver_name": "علی", "phone": "09127770001", "province": "تهران", "city": "تهران",
            "postal_code": "1415873920", "full_address": "خیابان", "note": "",
        }

    def add_to_cart(self, product=None, variant=None, qty=1):
        data = {"quantity": qty}
        if variant is not None:
            data["variant_id"] = variant.pk
        return self.client.post(reverse("cart:add", args=[(product or self.product).slug]), data)

    def displayed_total(self):
        html = self.client.get(reverse("orders:checkout-step1")).content.decode()
        match = EXPECTED_RE.search(html)
        self.assertIsNotNone(match, "checkout page must post the displayed total")
        return int(match.group(1))

    def pay(self, expected=None, **extra):
        data = dict(self.payload, **extra)
        if expected is not None:
            data["expected_total"] = str(expected)
        return self.client.post(reverse("orders:checkout-pay"), data)

    def orders(self):
        return Order.objects.filter(customer=self.customer)


class DisplayedEqualsChargedTests(PriceConfirmationBase):
    def test_checkout_page_posts_the_displayed_grand_total_and_order_matches_it(self):
        self.add_to_cart()
        shown = self.displayed_total()
        self.assertEqual(shown, 245000)
        response = self.pay(shown)
        self.assertIn("HX-Redirect", response.headers)
        order = self.orders().get()
        self.assertEqual(order.grand_total, Decimal(shown))

    def test_gateway_attempt_amount_equals_persisted_order_total(self):
        self.add_to_cart()
        self.pay(self.displayed_total())
        order = self.orders().get()
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal", is_active=True)
        config.set_credentials({"merchant": "m"})
        config.save()
        with patch("apps.orders.gateways.zibal.requests.post") as post:
            post.return_value.json.return_value = {"result": 100, "trackId": 123456}
            post.return_value.status_code = 200
            attempt = initiate_payment(order=order, gateway_config=config, callback_url="https://x/cb", store=self.store)
        self.assertEqual(attempt.amount, order.grand_total)
        self.assertEqual(post.call_args.kwargs["json"]["amount"], int(order.grand_total) * 10)  # ریال

    def test_missing_expected_total_is_a_direct_call_and_never_blocks_but_client_price_is_never_used(self):
        self.add_to_cart()
        self.pay()  # بدونِ مبلغِ دیده‌شده (فراخوانیِ مستقیم)
        self.assertEqual(self.orders().get().grand_total, Decimal("245000"))


class PriceChangeRequiresReconfirmationTests(PriceConfirmationBase):
    def assert_blocked_then_reconfirmed(self, new_total):
        response = self.pay(self._shown)
        self.assertNotIn("HX-Redirect", response.headers)
        self.assertEqual(self.orders().count(), 0)
        toast = json.loads(response["HX-Trigger"])["toast"]["message"]
        self.assertIn("مبلغِ جدید", toast)
        refreshed = self.displayed_total()
        self.assertEqual(refreshed, new_total)
        self.assertEqual(CartItem.objects.filter(cart__customer=self.customer).count(), 1)  # سبد دست‌نخورده
        response = self.pay(refreshed)
        self.assertIn("HX-Redirect", response.headers)
        self.assertEqual(self.orders().get().grand_total, Decimal(new_total))

    def start(self):
        self.add_to_cart()
        self._shown = self.displayed_total()

    def test_price_increase(self):
        self.start()
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("250000"))
        self.assert_blocked_then_reconfirmed(295000)

    def test_price_decrease_also_requires_reconfirmation(self):
        self.start()
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("150000"))
        self.assert_blocked_then_reconfirmed(195000)

    def test_product_discount_change(self):
        self.start()
        Product.objects.filter(pk=self.product.pk).update(discount_percent=Decimal("10"))
        self.assert_blocked_then_reconfirmed(225000)

    def test_shipping_cost_change(self):
        self.start()
        ShippingMethod.objects.filter(pk=self.shipping.pk).update(cost=Decimal("60000"))
        self.assert_blocked_then_reconfirmed(260000)

    def test_gift_wrap_price_change(self):
        self.add_to_cart()
        item = CartItem.objects.get(cart__customer=self.customer)
        from apps.cart.services.cart_service import set_item_gift_wrap

        set_item_gift_wrap(item, selected=True)
        self._shown = self.displayed_total()
        self.assertEqual(self._shown, 265000)
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_price = Decimal("30000")
        shop.save()
        self.assert_blocked_then_reconfirmed(275000)

    def test_gift_wrap_turned_off_removes_the_charge_with_reconfirmation(self):
        self.add_to_cart()
        from apps.cart.services.cart_service import set_item_gift_wrap

        set_item_gift_wrap(CartItem.objects.get(cart__customer=self.customer), selected=True)
        self._shown = self.displayed_total()
        shop = ShopSettings.load(store=self.store)
        shop.gift_wrap_available = False
        shop.save()
        self.assert_blocked_then_reconfirmed(245000)

    def test_variant_price_change(self):
        variant = ProductVariant.objects.create(
            product=self.product, store=self.store, attribute="رنگ", value="قرمز", stock=5, extra_price=Decimal("10000"),
        )
        self.add_to_cart(variant=variant)
        self._shown = self.displayed_total()
        self.assertEqual(self._shown, 255000)
        ProductVariant.objects.filter(pk=variant.pk).update(extra_price=Decimal("30000"))
        self.assert_blocked_then_reconfirmed(275000)

    def test_coupon_expiring_after_display_raises_the_total_with_reconfirmation(self):
        Coupon.objects.create(store=self.store, code="OFF10", type="percent", value=10, usage_limit=10)
        self.add_to_cart()
        self.client.post(reverse("orders:checkout-coupon-apply"), {"code": "OFF10"})
        self._shown = self.displayed_total()
        self.assertEqual(self._shown, 225000)  # ۱۰٪ تخفیفِ ۲۰۰٬۰۰۰ + ارسال ۴۵٬۰۰۰
        Coupon.objects.filter(code="OFF10").update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assert_blocked_then_reconfirmed(245000)

    def test_tampered_client_totals_never_decide_the_charge(self):
        self.add_to_cart()
        for tampered in (1, 10**9):
            response = self.pay(tampered)
            self.assertNotIn("HX-Redirect", response.headers)
        self.assertEqual(self.orders().count(), 0)
        self.pay(245000)
        self.assertEqual(self.orders().get().grand_total, Decimal("245000"))

    def test_stock_drop_still_blocks_with_its_own_message(self):
        self.add_to_cart(qty=3)
        shown = self.displayed_total()
        Product.objects.filter(pk=self.product.pk).update(stock=1)
        response = self.pay(shown)
        self.assertNotIn("HX-Redirect", response.headers)
        self.assertEqual(self.orders().count(), 0)


class ServiceLevelPolicyTests(PriceConfirmationBase):
    """سیاست در لایه‌ی سرویس (برای کوپن/موجودی/همزمانی؛ مستقل از UI)."""

    def make_cart(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        address = Address.objects.create(
            customer=self.customer, receiver_name="x", phone=self.customer.phone, province="تهران", city="تهران",
            postal_code="1415873920", full_address="x",
        )
        return cart, address

    def create(self, cart, address, **kw):
        return create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=address, shipping_method=self.shipping,
            payment_gateway=self.gateway, store=self.store, **kw,
        )

    def test_stale_cart_snapshot_is_repriced_to_the_authoritative_price_not_trusted(self):
        cart, address = self.make_cart()
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("300000"))  # بدونِ expected ⇒ قیمتِ معتبر
        order = self.create(cart, address)
        self.assertEqual(order.items_total, Decimal("300000"))
        self.assertEqual(order.items.get().unit_price, Decimal("300000"))

    def test_expected_total_mismatch_raises_and_rolls_back_everything(self):
        cart, address = self.make_cart()
        stock = Product.objects.get(pk=self.product.pk).stock
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("300000"))
        with self.assertRaises(PriceChangedError) as ctx:
            self.create(cart, address, expected_total=Decimal("245000"))
        self.assertEqual((ctx.exception.expected, ctx.exception.actual), (Decimal("245000"), Decimal("345000")))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Product.objects.get(pk=self.product.pk).stock, stock)

    def test_coupon_becoming_invalid_changes_total_and_is_detected(self):
        coupon = Coupon.objects.create(store=self.store, code="H7C", type="percent", value=10, usage_limit=10)
        cart, address = self.make_cart()
        shown = self.create_preview_total(cart, coupon)
        Coupon.objects.filter(pk=coupon.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaises((PriceChangedError, ValueError)):
            self.create(cart, address, coupon=Coupon.objects.get(pk=coupon.pk), expected_total=shown)
        self.assertEqual(Order.objects.count(), 0)

    def create_preview_total(self, cart, coupon):
        from apps.cart.services.pricing import cart_totals

        return cart_totals(cart, store=self.store, coupon=coupon, shipping_method=self.shipping, customer=self.customer)["grand_total"]

    def test_duplicate_submission_with_same_token_returns_same_order_and_amount(self):
        cart, address = self.make_cart()
        first = self.create(cart, address, idempotency_key="tok-h7", expected_total=Decimal("245000"))
        again = self.create(cart, address, idempotency_key="tok-h7", expected_total=Decimal("245000"))
        self.assertEqual((first.pk, again.grand_total), (again.pk, Decimal("245000")))
        self.assertEqual(Order.objects.count(), 1)

    def test_refunds_use_order_snapshots_not_current_prices(self):
        cart, address = self.make_cart()
        order = self.create(cart, address)
        Order.objects.filter(pk=order.pk).update(payment_status=Order.PaymentStatus.PAID)
        order.refresh_from_db()
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("999999"))
        item = order.items.get()
        plan = refund_service.plan_order_refund(
            order, store=self.store, line_requests=[{"order_item_id": item.pk, "quantity": 1}],
        )
        self.assertEqual(plan.total_amount, Decimal("200000"))
        full = refund_service.plan_order_refund(
            order, store=self.store, line_requests=[{"order_item_id": item.pk, "quantity": 1}], shipping_amount=Decimal("45000"),
        )
        self.assertEqual(full.total_amount, order.grand_total)

    def test_historical_orders_keep_their_snapshots_when_prices_change(self):
        cart, address = self.make_cart()
        order = self.create(cart, address)
        Product.objects.filter(pk=self.product.pk).update(price=Decimal("1"))
        order.refresh_from_db()
        self.assertEqual((order.items_total, order.grand_total), (Decimal("200000"), Decimal("245000")))
        self.assertEqual(order.items.get().unit_price, Decimal("200000"))
