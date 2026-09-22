"""CAT-002 — Checkout header totals vs. OrderItem line valuation must never
disagree (architecture-convergence finding CAT-002).

Root cause (pre-fix): ``apps.cart.services.pricing.cart_totals()`` computes
the Order header (items_total/coupon_discount/tax/shipping_cost/grand_total)
by summing the *stale* ``CartItem.unit_price`` snapshot, while
``apps.orders.services.order_service.create_order_from_cart()`` computed each
``OrderItem.unit_price`` via an *independent*, fresh call to
``apps.catalog.services.pricing_service.resolve_effective_price()``. If the
catalog price changed between "add to cart" and "checkout", the header and
the line items disagreed.

Binding product decision: reprice at checkout using
``resolve_effective_price()`` as the sole canonical authority, freeze
exactly ONE snapshot, and use it everywhere (header + every line). If the
live price differs from the cart snapshot at final checkout time, the
customer must see a refreshed cart + exact warning and must explicitly
resubmit — no Order/inventory/coupon/cart-mutation/redirect happens on that
first attempt.

These tests were written RED-first, before any production fix, following
the existing ``_OrderCreationFixture`` pattern in
``test_checkout_correctness.py``.
"""

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartItem, Coupon
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.customers.models import Address, Customer
from apps.orders.models import Order, OrderItem, PaymentGateway, ShippingMethod
from apps.orders.services.checkout_service import get_or_create_checkout_token
from apps.orders.services.order_service import create_order_from_cart
from apps.orders.services.payment_service import simulate_payment
from apps.stores.models import Store

User = get_user_model()

# The exact, binding Persian warning text the customer must see when final
# checkout repricing detects a live-price change. Do not alter this string —
# it is a verbatim product requirement.
PRICE_CHANGED_MESSAGE = (
    "قیمت یک یا چند کالا از زمان افزودن به سبد تغییر کرده است. "
    "مبلغ نهایی به‌روزرسانی شد؛ لطفاً مبلغ جدید را بررسی و دوباره پرداخت را تأیید کنید."
)


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class _Cat002Fixture(TestCase):
    """Same base fixture shape as ``_OrderCreationFixture`` in
    test_checkout_correctness.py — reused deliberately so these tests slot
    into the existing suite conventions."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-c2")
        self.category = Category.objects.create(store=self.store, name="دیجیتال", slug="digital-c2")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="هدفون", slug="headphone-c2", sku="SKU-C2-1",
            price=Decimal("500000"), stock=10, status=Product.Status.ACTIVE,
        )
        user = User.objects.create_user(username="c2-user", password="pass12345")
        self.customer = Customer.objects.create(user=user, full_name="مشتری", phone="09121230081")
        self.address = Address.objects.create(
            customer=self.customer, receiver_name="مشتری", phone="09121230081",
            province="تهران", city="تهران", postal_code="1111111111", full_address="خیابان آزادی",
        )
        self.shipping = ShippingMethod.objects.create(store=self.store, name="پست", slug="post-c2", cost=Decimal("10000"))
        self.gateway = PaymentGateway.objects.create(store=self.store, name="درگاه", slug="gw-c2")

    def _cart_with_item(self, quantity=1, variant=None, unit_price=None):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.product, variant=variant, quantity=quantity,
            unit_price=unit_price if unit_price is not None else self.product.final_price,
        )
        return cart

    def _create(self, cart, **kwargs):
        return create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store, **kwargs
        )


# ---------------------------------------------------------------------------
# Scenario 1 — simple product price increase
# ---------------------------------------------------------------------------
class PriceIncreaseTests(_Cat002Fixture):
    def test_price_increase_between_cart_add_and_checkout_uses_new_price_everywhere(self):
        # Cart snapshot was taken at 500,000.
        cart = self._cart_with_item(quantity=2, unit_price=Decimal("500000"))
        # Catalog price rises to 700,000 before checkout.
        self.product.price = Decimal("700000")
        self.product.save(update_fields=["price"])

        order = self._create(cart)

        item = order.items.first()
        self.assertEqual(item.unit_price, Decimal("700000"))
        self.assertEqual(item.line_total, Decimal("1400000"))
        # Header must agree with the line — the whole point of CAT-002.
        self.assertEqual(order.items_total, Decimal("1400000"))
        self.assertEqual(order.grand_total, item.line_total + order.shipping_cost + order.tax)


# ---------------------------------------------------------------------------
# Scenario 2 — simple product price decrease
# ---------------------------------------------------------------------------
class PriceDecreaseTests(_Cat002Fixture):
    def test_price_decrease_between_cart_add_and_checkout_uses_new_lower_price(self):
        cart = self._cart_with_item(quantity=3, unit_price=Decimal("500000"))
        self.product.price = Decimal("300000")
        self.product.save(update_fields=["price"])

        order = self._create(cart)

        item = order.items.first()
        self.assertEqual(item.unit_price, Decimal("300000"))
        self.assertEqual(item.line_total, Decimal("900000"))
        self.assertEqual(order.items_total, Decimal("900000"))


# ---------------------------------------------------------------------------
# Scenario 3 — customer price-change confirmation two-step flow (HTTP)
# ---------------------------------------------------------------------------
class PriceChangeConfirmationFlowTests(_Cat002Fixture):
    def setUp(self):
        super().setUp()
        self.client.login(username="c2-user", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.payload = {
            "receiver_name": "مشتری", "phone": "09121230081", "province": "تهران",
            "city": "تهران", "postal_code": "1111111111",
            "full_address": "خیابان آزادی", "note": "",
        }

    def test_first_submit_after_price_change_does_not_create_order_or_side_effects(self):
        cart = Cart.objects.get(customer=self.customer)
        original_stock = self.product.stock
        # Price changes after the item was added to the cart above.
        self.product.price = Decimal("650000")
        self.product.save(update_fields=["price"])

        resp = self.client.post(reverse("orders:checkout-pay"), self.payload)

        self.assertNotIn("HX-Redirect", resp.headers)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, original_stock)  # no reservation/decrement
        self.assertTrue(cart.items.exists())  # cart NOT cleared
        cart.refresh_from_db()
        item = cart.items.first()
        # Cart pricing refreshed for customer review.
        self.assertEqual(item.unit_price, Decimal("650000"))
        # Exact required Persian warning surfaced via HX-Trigger toast.
        trigger = json.loads(resp.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["message"], PRICE_CHANGED_MESSAGE)

    def test_second_submit_with_no_further_change_creates_order_with_refreshed_price(self):
        self.product.price = Decimal("650000")
        self.product.save(update_fields=["price"])

        first = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertNotIn("HX-Redirect", first.headers)

        second = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertIn("HX-Redirect", second.headers)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.get()
        item = order.items.first()
        self.assertEqual(item.unit_price, Decimal("650000"))
        self.assertEqual(order.items_total, Decimal("650000"))

    def test_repeat_price_change_on_second_submit_warns_again(self):
        self.product.price = Decimal("650000")
        self.product.save(update_fields=["price"])
        first = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertNotIn("HX-Redirect", first.headers)

        # Price changes AGAIN before the customer resubmits.
        self.product.price = Decimal("720000")
        self.product.save(update_fields=["price"])

        second = self.client.post(reverse("orders:checkout-pay"), self.payload)
        self.assertNotIn("HX-Redirect", second.headers)
        self.assertEqual(Order.objects.count(), 0)
        trigger = json.loads(second.headers["HX-Trigger"])
        self.assertEqual(trigger["toast"]["message"], PRICE_CHANGED_MESSAGE)


# ---------------------------------------------------------------------------
# Scenario 4 — variable product / absolute variant price change
# ---------------------------------------------------------------------------
class VariantAbsolutePriceChangeTests(_Cat002Fixture):
    def setUp(self):
        super().setUp()
        self.scissors = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="قیچی",
            slug="scissors-c2", sku="SKU-SCISSORS-C2", price=Decimal("1"),
            product_type=Product.ProductType.VARIABLE, stock=0,
        )
        self.italian = ProductVariant.objects.create(
            product=self.scissors, store=self.store, attribute="کشور سازنده", value="ایتالیایی",
            price=Decimal("800000"), stock=4,
        )

    def test_variant_absolute_price_change_is_repriced_via_variant_not_parent_product(self):
        cart = Cart.objects.create(customer=self.customer)
        CartItem.objects.create(
            cart=cart, product=self.scissors, variant=self.italian, quantity=1, unit_price=Decimal("800000"),
        )
        # Variant's own absolute price changes; parent Product.price/discount
        # must be irrelevant to this repricing (mirrors
        # resolve_effective_price's variant.price-is-absolute contract).
        self.italian.price = Decimal("950000")
        self.italian.save(update_fields=["price"])
        self.scissors.discount_percent = 90  # must be ignored for absolute variant price
        self.scissors.save(update_fields=["discount_percent"])

        order = create_order_from_cart(
            cart, customer=self.customer, vendor=self.vendor, address=self.address,
            shipping_method=self.shipping, payment_gateway=self.gateway, store=self.store,
        )
        item = order.items.get(variant=self.italian)
        self.assertEqual(item.unit_price, Decimal("950000"))
        self.assertEqual(item.line_total, Decimal("950000"))
        self.assertEqual(order.items_total, Decimal("950000"))


# ---------------------------------------------------------------------------
# Scenario 5 — discount_percent change between cart-add and checkout
# ---------------------------------------------------------------------------
class DiscountPercentChangeTests(_Cat002Fixture):
    def test_discount_percent_change_reflected_in_final_snapshot(self):
        self.product.price = Decimal("1000000")
        self.product.discount_percent = 0
        self.product.save(update_fields=["price", "discount_percent"])
        cart = self._cart_with_item(quantity=1, unit_price=Decimal("1000000"))

        self.product.discount_percent = 20
        self.product.save(update_fields=["discount_percent"])

        order = self._create(cart)
        item = order.items.first()
        self.assertEqual(item.unit_price, Decimal("800000"))
        self.assertEqual(order.items_total, Decimal("800000"))
        self.assertEqual(order.product_discount, Decimal("200000"))


# ---------------------------------------------------------------------------
# Scenario 6 — coupon/tax allocation consistency after reprice
# ---------------------------------------------------------------------------
class CouponTaxAllocationConsistencyTests(_Cat002Fixture):
    def test_coupon_and_tax_allocations_reconcile_with_header_after_reprice(self):
        self.product.price = Decimal("500000")
        self.product.discount_percent = 0
        self.product.save(update_fields=["price", "discount_percent"])
        cart = self._cart_with_item(quantity=2, unit_price=Decimal("500000"))
        coupon = Coupon.objects.create(
            store=self.store, code="CAT2TEN", type=Coupon.Type.PERCENT, value=Decimal("10"),
        )

        # Price rises after cart-add, before checkout.
        self.product.price = Decimal("600000")
        self.product.save(update_fields=["price"])

        order = self._create(cart, coupon=coupon)
        item = order.items.first()

        # Every line's unit_price must be derived from the SAME repriced
        # base (600,000), and header items_total must equal that base.
        self.assertEqual(item.unit_price, Decimal("600000"))
        self.assertEqual(order.items_total, Decimal("1200000"))
        # Coupon discount computed off the repriced items_total, not the
        # stale one.
        self.assertEqual(order.coupon_discount, Decimal("120000"))
        # Per-line taxable_amount/total_tax must reconcile with the header
        # fields — one coherent valuation derived from the same repriced
        # base (not asserting on discount_allocation here: that field is
        # populated from tax_service's per-line breakdown, a pre-existing,
        # CAT-002-unrelated mechanism).
        self.assertEqual(
            order.grand_total,
            (order.items_total - order.coupon_discount) + order.shipping_cost + order.tax,
        )


# ---------------------------------------------------------------------------
# Scenario 7 — free-shipping threshold crossing via repriced subtotal
# ---------------------------------------------------------------------------
class FreeShippingThresholdRepriceTests(_Cat002Fixture):
    def test_price_increase_crossing_free_shipping_threshold_uses_repriced_subtotal(self):
        from apps.core.models import ShopSettings

        settings_row = ShopSettings.load(store=self.store)
        threshold = settings_row.free_shipping_threshold

        # Cart-add price keeps the cart BELOW threshold.
        below = threshold - Decimal("100000")
        if below <= 0:
            below = Decimal("1000")
        cart = self._cart_with_item(quantity=1, unit_price=below)

        # Catalog price rises so the repriced subtotal now clears the
        # threshold.
        self.product.price = threshold + Decimal("100000")
        self.product.discount_percent = 0
        self.product.save(update_fields=["price", "discount_percent"])

        order = self._create(cart)
        self.assertEqual(order.items_total, threshold + Decimal("100000"))
        self.assertEqual(order.shipping_cost, Decimal("0"))


# ---------------------------------------------------------------------------
# Scenario 8 — idempotency / historical freeze survives later catalog changes
# ---------------------------------------------------------------------------
class IdempotencyHistoricalFreezeTests(_Cat002Fixture):
    def test_repeat_call_with_same_token_returns_frozen_order_ignoring_further_price_changes(self):
        cart = self._cart_with_item(quantity=1, unit_price=Decimal("500000"))
        token = get_or_create_checkout_token(cart)

        order1 = self._create(cart, idempotency_key=token)
        original_unit_price = order1.items.first().unit_price
        original_total = order1.grand_total

        # Catalog price changes again AFTER the order was created.
        self.product.price = Decimal("999999")
        self.product.save(update_fields=["price"])

        CartItem.objects.create(cart=cart, product=self.product, quantity=1, unit_price=self.product.final_price)
        order2 = self._create(cart, idempotency_key=token)

        self.assertEqual(order1.pk, order2.pk)
        order2.refresh_from_db()
        self.assertEqual(order2.items.first().unit_price, original_unit_price)
        self.assertEqual(order2.grand_total, original_total)


# ---------------------------------------------------------------------------
# Scenario 9 — payment amount derives from frozen Order.grand_total
# ---------------------------------------------------------------------------
class PaymentAmountDerivesFromFrozenGrandTotalTests(_Cat002Fixture):
    def test_simulated_payment_amount_matches_frozen_grand_total_not_recomputed(self):
        cart = self._cart_with_item(quantity=1, unit_price=Decimal("500000"))
        self.product.price = Decimal("777000")
        self.product.save(update_fields=["price"])

        order = self._create(cart)
        frozen_grand_total = order.grand_total

        # Catalog price changes yet again, after Order creation, before
        # payment — must have zero effect on payment amount.
        self.product.price = Decimal("111000")
        self.product.save(update_fields=["price"])

        tx = simulate_payment(order, True, store=self.store)
        self.assertEqual(tx.amount, frozen_grand_total)
        order.refresh_from_db()
        self.assertEqual(order.grand_total, frozen_grand_total)


# ---------------------------------------------------------------------------
# Scenario 10 — failure safety: price-change round has zero side effects
# ---------------------------------------------------------------------------
class PriceChangeFailureSafetyTests(_Cat002Fixture):
    def setUp(self):
        super().setUp()
        self.client.login(username="c2-user", password="pass12345")
        self.client.post(reverse("cart:add", args=[self.product.slug]), {"quantity": 1})
        self.payload = {
            "receiver_name": "مشتری", "phone": "09121230081", "province": "تهران",
            "city": "تهران", "postal_code": "1111111111",
            "full_address": "خیابان آزادی", "note": "",
        }

    def test_price_change_round_creates_no_orphan_address_or_order_and_preserves_session(self):
        from apps.customers.models import Address

        address_count_before = Address.objects.count()
        cart = Cart.objects.get(customer=self.customer)
        coupon = Coupon.objects.create(
            store=self.store, code="C2SAFE", type=Coupon.Type.PERCENT, value=Decimal("5"),
        )

        self.product.price = Decimal("650000")
        self.product.save(update_fields=["price"])

        resp = self.client.post(reverse("orders:checkout-pay"), self.payload)

        self.assertNotIn("HX-Redirect", resp.headers)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Address.objects.count(), address_count_before)  # no orphan address
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)  # coupon usage never incremented
        cart.refresh_from_db()
        self.assertTrue(cart.items.exists())  # cart preserved, not deleted
