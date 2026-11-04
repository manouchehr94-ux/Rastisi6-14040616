"""FEAT-006 (BLOCKER 5) — BNPL cartList carries authoritative, immutable
per-line order-item snapshots that reconcile EXACTLY to the Rial order amount.

Both SnappPay and TorobPay previously built ONE synthetic cart item (name
``سفارش {code}``, count 1, amount = full total, shipping/tax 0), so real
multi-item BNPL orders were not represented. These tests exercise the real
service -> adapter boundary:

* ``build_order_cart_snapshot`` forwards per-line OrderItem snapshots + the
  order-level totals (all TOMAN).
* ``SnappPayAdapter._build_cart_list`` / ``TorobPayAdapter._build_cart_list``
  build REAL cartItems (product id/sku, product_name, quantity, unit amounts)
  and allocate shipping/tax/discount to the documented cartList-level fields.
* The built cartList reconciles EXACTLY to ``int(grand_total) * 10`` Rial for
  multi-item, discounted, and shipping+tax orders.
* A tampered line (so the cart total diverges) raises
  GatewayAmountMismatchError instead of sending a bad cart.

All amounts are integer TOMAN (Order money fields have 0 decimal places), so
the reconciliation is exact with no rounding residual. No real network is
touched — the cart builder and snapshot are pure/local.

Reconciliation identity (RS-11, verified against apps/cart/services/pricing.py)::

    grand_total = items_total + gift_wrap_total + shipping_cost + tax_added
                  - coupon_discount

where ``tax_added = (0 if prices_include_tax else order.tax) + shipping_tax``
and ``sum(line_total) == items_total``. The coupon discount is applied per
cartItem via each line's authoritative ``discount_allocation`` (net amounts),
so the documented cart shape (which has no cart-level discount field) still
reconciles without inventing fields.
"""

from decimal import Decimal

from apps.orders.gateways.base import GatewayAmountMismatchError
from apps.orders.gateways.snappay import TOMAN_TO_RIAL, SnappPayAdapter
from apps.orders.gateways.torobpay import TorobPayAdapter
from apps.orders.models import Order, OrderItem
from apps.orders.services.gateway_payment_service import build_order_cart_snapshot
from apps.orders.tests.engine_base import EngineBase

SYNTHETIC_NAME_PREFIX = "سفارش "


class BnplCartReconciliationBase(EngineBase):
    """Builds real multi-item orders directly with explicit, self-consistent
    money fields so reconciliation is deterministic."""

    order_seq = 0

    def _make_order(
        self,
        *,
        lines,
        shipping_cost=0,
        tax=0,
        shipping_tax=0,
        coupon_discount=0,
        line_discounts=None,
        gift_wrap_total=0,
        gift_wrap_discount=0,
        prices_include_tax=False,
    ):
        """Create an Order + OrderItems where the money fields satisfy RS-11.

        ``lines`` is a list of ``(product, quantity, unit_price)``.
        ``line_discounts`` (optional) maps the line index to the coupon
        discount allocated to that line; the sum must equal the item portion of
        ``coupon_discount`` (coupon_discount - gift_wrap_discount).
        """
        BnplCartReconciliationBase.order_seq += 1
        line_discounts = line_discounts or {}

        items_total = sum(up * q for (_p, q, up) in lines)
        tax_added = (Decimal("0") if prices_include_tax else Decimal(tax)) + Decimal(shipping_tax)
        grand_total = (
            Decimal(items_total)
            + Decimal(gift_wrap_total)
            + Decimal(shipping_cost)
            + tax_added
            - Decimal(coupon_discount)
        )

        order = Order.objects.create(
            code=f"BN-{self.order_seq:04d}",
            store=self.store,
            customer=self.customer,
            vendor=self.vendor,
            shipping_method=self.shipping,
            payment_gateway=self.gateway,
            address={},
            items_total=Decimal(items_total),
            product_discount=Decimal("0"),
            coupon_discount=Decimal(coupon_discount),
            shipping_cost=Decimal(shipping_cost),
            tax=Decimal(tax),
            shipping_tax=Decimal(shipping_tax),
            grand_total=grand_total,
            prices_include_tax=prices_include_tax,
            gift_wrap_total=Decimal(gift_wrap_total),
            gift_wrap_discount=Decimal(gift_wrap_discount),
        )
        for idx, (product, qty, unit_price) in enumerate(lines):
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                sku=product.sku,
                quantity=qty,
                unit_price=Decimal(unit_price),
                line_total=Decimal(unit_price) * qty,
                discount_allocation=Decimal(line_discounts.get(idx, 0)),
                total_tax=Decimal("0"),
            )
        return order

    def _products(self, n=2):
        return [
            self._product(f"bnpl-p{i}", str(100000 * (i + 1)))
            for i in range(n)
        ]

    def _expected_rial(self, order):
        return int(order.grand_total) * TOMAN_TO_RIAL

    def _cart_total_rial(self, cart_list):
        return sum(c["totalAmount"] for c in cart_list)

    def _all_item_names(self, cart_list):
        return [ci["name"] for c in cart_list for ci in c["cartItems"]]

    def _build(self, adapter, order):
        cart_items, cart_totals = build_order_cart_snapshot(order)
        amount_rial = int(order.grand_total) * TOMAN_TO_RIAL
        return adapter._build_cart_list(
            order.code, amount_rial, cart_items=cart_items, cart_totals=cart_totals
        )


class _AdapterReconciliationMixin:
    """Shared assertions parametrized by ``self.adapter``."""

    adapter = None

    def test_multi_item_order_reconciles_exactly(self):
        p1, p2 = self._products(2)
        order = self._make_order(lines=[(p1, 2, 100000), (p2, 3, 200000)])
        cart_list = self._build(self.adapter, order)

        self.assertEqual(self._cart_total_rial(cart_list), self._expected_rial(order))
        # Real per-line data is present — not the single synthetic line.
        names = self._all_item_names(cart_list)
        self.assertIn(p1.name, names)
        self.assertIn(p2.name, names)
        self.assertNotIn(f"{SYNTHETIC_NAME_PREFIX}{order.code}", names)
        # Real identifiers + counts preserved.
        items = cart_list[0]["cartItems"]
        by_name = {ci["name"]: ci for ci in items}
        self.assertEqual(by_name[p1.name]["id"], str(p1.pk))
        self.assertEqual(by_name[p1.name]["count"], 2)
        self.assertEqual(by_name[p2.name]["count"], 3)
        self.assertEqual(by_name[p1.name]["amount"], 2 * 100000 * TOMAN_TO_RIAL)

    def test_discounted_order_reconciles_exactly(self):
        p1, p2 = self._products(2)
        # items_total = 2*100000 + 1*300000 = 500000; coupon 50000 split 20000/30000.
        order = self._make_order(
            lines=[(p1, 2, 100000), (p2, 1, 300000)],
            coupon_discount=50000,
            line_discounts={0: 20000, 1: 30000},
        )
        cart_list = self._build(self.adapter, order)

        self.assertEqual(self._cart_total_rial(cart_list), self._expected_rial(order))
        items = {ci["name"]: ci for ci in cart_list[0]["cartItems"]}
        # Line amounts are NET of the per-line coupon allocation.
        self.assertEqual(items[p1.name]["amount"], (2 * 100000 - 20000) * TOMAN_TO_RIAL)
        self.assertEqual(items[p2.name]["amount"], (1 * 300000 - 30000) * TOMAN_TO_RIAL)

    def test_shipping_and_tax_order_reconciles_exactly(self):
        p1, p2 = self._products(2)
        order = self._make_order(
            lines=[(p1, 1, 250000), (p2, 2, 125000)],
            shipping_cost=40000,
            tax=45000,
            shipping_tax=3600,
        )
        cart_list = self._build(self.adapter, order)

        self.assertEqual(self._cart_total_rial(cart_list), self._expected_rial(order))
        cart = cart_list[0]
        # Shipping and tax land on the documented cart-level fields.
        self.assertEqual(cart["shippingAmount"], 40000 * TOMAN_TO_RIAL)
        # tax_added = line tax (exclusive) + shipping tax = 45000 + 3600.
        self.assertEqual(cart["taxAmount"], (45000 + 3600) * TOMAN_TO_RIAL)

    def test_shipping_tax_and_discount_combined_reconciles_exactly(self):
        p1, p2 = self._products(2)
        order = self._make_order(
            lines=[(p1, 2, 150000), (p2, 2, 100000)],
            shipping_cost=30000,
            tax=40000,
            shipping_tax=2400,
            coupon_discount=25000,
            line_discounts={0: 15000, 1: 10000},
        )
        cart_list = self._build(self.adapter, order)
        self.assertEqual(self._cart_total_rial(cart_list), self._expected_rial(order))

    def test_tampered_line_raises_amount_mismatch(self):
        p1, p2 = self._products(2)
        order = self._make_order(lines=[(p1, 2, 100000), (p2, 1, 150000)])
        cart_items, cart_totals = build_order_cart_snapshot(order)
        amount_rial = int(order.grand_total) * TOMAN_TO_RIAL
        # Tamper a line so the built cart total diverges from grand_total*10.
        cart_items[0]["line_amount"] += 99999
        with self.assertRaises(GatewayAmountMismatchError):
            self.adapter._build_cart_list(
                order.code, amount_rial, cart_items=cart_items, cart_totals=cart_totals
            )

    def test_tampered_totals_raises_amount_mismatch(self):
        p1, p2 = self._products(2)
        order = self._make_order(
            lines=[(p1, 1, 200000), (p2, 1, 100000)],
            shipping_cost=20000,
        )
        cart_items, cart_totals = build_order_cart_snapshot(order)
        amount_rial = int(order.grand_total) * TOMAN_TO_RIAL
        # Inflate shipping so the cart total no longer matches the order amount.
        cart_totals["shipping"] += 5000
        with self.assertRaises(GatewayAmountMismatchError):
            self.adapter._build_cart_list(
                order.code, amount_rial, cart_items=cart_items, cart_totals=cart_totals
            )

    def test_fallback_without_items_keeps_single_synthetic_cart(self):
        # No cart_items -> historical single synthetic cart (nothing else breaks).
        cart_list = self.adapter._build_cart_list("DM-FALLBACK", 5_000_000)
        self.assertEqual(len(cart_list), 1)
        self.assertEqual(len(cart_list[0]["cartItems"]), 1)
        self.assertEqual(
            cart_list[0]["cartItems"][0]["name"], f"{SYNTHETIC_NAME_PREFIX}DM-FALLBACK"
        )
        self.assertEqual(cart_list[0]["totalAmount"], 5_000_000)

    def test_gift_wrap_rides_as_real_cart_item(self):
        p1, p2 = self._products(2)
        # gift_wrap_discount is a subset of coupon_discount (RS-11), so the
        # coupon discount here (5000) is entirely the gift-wrap discount.
        order = self._make_order(
            lines=[(p1, 1, 100000), (p2, 1, 100000)],
            gift_wrap_total=15000,
            gift_wrap_discount=5000,
            coupon_discount=5000,
        )
        cart_list = self._build(self.adapter, order)
        self.assertEqual(self._cart_total_rial(cart_list), self._expected_rial(order))
        names = self._all_item_names(cart_list)
        self.assertIn("کادوپیچی", names)

    def test_create_payment_forwards_real_cart_items(self):
        """Full create_payment path: forwarded cart_items produce a cartList
        with real product data and the amounts still convert Toman->Rial once."""
        from unittest.mock import MagicMock, patch

        p1, p2 = self._products(2)
        order = self._make_order(lines=[(p1, 2, 100000), (p2, 1, 300000)])
        cart_items, cart_totals = build_order_cart_snapshot(order)

        module = type(self.adapter).__module__
        oauth = MagicMock()
        oauth.json.return_value = {"access_token": "JWT", "expires_in": 3600}
        oauth.status_code = 200
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "successful": True,
            "response": {"paymentToken": "PT-1", "paymentPageUrl": "https://pay/x"},
        }
        token_resp.status_code = 200

        captured = {}

        def _router(method, url, **kwargs):
            if url.endswith("/oauth/token"):
                return oauth
            captured["json"] = kwargs.get("json_body") or kwargs.get("json")
            return token_resp

        with patch(f"{module}.requests.request", side_effect=_router):
            result = self.adapter.create_payment(
                amount=order.grand_total,
                currency="TOMAN",
                callback_url="https://cb",
                credentials={
                    "client_id": "c",
                    "client_secret": "s",
                    "client_username": "u",
                    "client_password": "p",
                },
                order_code=order.code,
                cart_items=cart_items,
                cart_totals=cart_totals,
            )

        self.assertEqual(result.track_id, "PT-1")
        payload = captured["json"]
        self.assertEqual(payload["amount"], int(order.grand_total) * TOMAN_TO_RIAL)
        cart_list = payload["cartList"]
        total_rial = sum(c["totalAmount"] for c in cart_list)
        self.assertEqual(total_rial, int(order.grand_total) * TOMAN_TO_RIAL)
        names = [ci["name"] for c in cart_list for ci in c["cartItems"]]
        self.assertIn(p1.name, names)
        self.assertIn(p2.name, names)
        self.assertNotIn(f"{SYNTHETIC_NAME_PREFIX}{order.code}", names)


class SnappPayCartReconciliationTests(_AdapterReconciliationMixin, BnplCartReconciliationBase):
    def setUp(self):
        super().setUp()
        self.adapter = SnappPayAdapter()


class TorobPayCartReconciliationTests(_AdapterReconciliationMixin, BnplCartReconciliationBase):
    def setUp(self):
        super().setUp()
        self.adapter = TorobPayAdapter()
