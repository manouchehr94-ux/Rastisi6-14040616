"""کادوپیچیِ پیشرفته: سیاستِ محاسبه، اهلیتِ کالا، پیام، ثبتِ سفارش، تخفیف و استرداد."""

from decimal import Decimal

from apps.cart.models import CartItem, Coupon
from apps.cart.services import gift_wrap_service as gw
from apps.core.models import ShopSettings
from apps.orders.models import Order
from apps.orders.services.order_service import change_order_status
from apps.orders.services.payment_service import simulate_payment
from apps.orders.services.refund_service import execute_order_refund, refundable_amount
from apps.orders.tests.engine_base import EngineBase

Scope = ShopSettings.GiftWrapScope


class GiftWrapBase(EngineBase):
    def setUp(self):
        super().setUp()
        self.shop = ShopSettings.load(store=self.store)
        self.shop.gift_wrap_available = True
        self.shop.gift_wrap_price = Decimal("20000")
        self.shop.save()
        self.p1 = self._product("gw1", "100000")
        self.p2 = self._product("gw2", "200000")

    def _wrapped_cart(self, lines, wrapped=(True, True)):
        cart = self._cart(lines=lines)
        for item, flag in zip(cart.items.order_by("pk"), wrapped):
            item.gift_wrap_selected = flag
            item.gift_wrap_unit_price = gw.resolve_gift_wrap_price(self.store, item.product, shop=self.shop) if flag else 0
            item.save()
        return cart

    def _set_scope(self, scope):
        self.shop.gift_wrap_pricing_scope = scope
        self.shop.save()


class GiftWrapPricingScopeTests(GiftWrapBase):
    def test_per_unit(self):
        self._set_scope(Scope.PER_UNIT)
        totals = self._totals(self._wrapped_cart([(self.p1, 2), (self.p2, 3)]), None)
        self.assertEqual(totals["gift_wrap_total"], Decimal("100000"))  # (2+3)*20000

    def test_per_line(self):
        self._set_scope(Scope.PER_LINE)
        totals = self._totals(self._wrapped_cart([(self.p1, 2), (self.p2, 3)]), None)
        self.assertEqual(totals["gift_wrap_total"], Decimal("40000"))

    def test_per_order_charges_once_at_highest_price(self):
        self._set_scope(Scope.PER_ORDER)
        self.p2.gift_wrap_price = Decimal("50000")
        self.p2.save()
        totals = self._totals(self._wrapped_cart([(self.p1, 2), (self.p2, 3)]), None)
        self.assertEqual(totals["gift_wrap_total"], Decimal("50000"))
        self.assertEqual(sum(totals["gift_wrap_allocations"].values()), Decimal("50000"))

    def test_quantity_change_recalculates_per_unit(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        self.assertEqual(self._totals(cart, None)["gift_wrap_total"], Decimal("20000"))
        CartItem.objects.filter(cart=cart).update(quantity=4)
        self.assertEqual(self._totals(cart, None)["gift_wrap_total"], Decimal("80000"))

    def test_unselected_lines_not_charged_even_with_stale_price(self):
        cart = self._wrapped_cart([(self.p1, 2), (self.p2, 1)], wrapped=(True, False))
        CartItem.objects.filter(cart=cart, product=self.p2).update(gift_wrap_unit_price=99999)
        self.assertEqual(self._totals(cart, None)["gift_wrap_total"], Decimal("40000"))

    def test_free_wrap_has_zero_charge(self):
        self.shop.gift_wrap_price = Decimal("0")
        self.shop.save()
        cart = self._wrapped_cart([(self.p1, 2)], wrapped=(True,))
        self.assertEqual(self._totals(cart, None)["gift_wrap_total"], Decimal("0"))


class GiftWrapEligibilityTests(GiftWrapBase):
    def test_global_switch_off_blocks_selection_and_charge(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        self.shop.gift_wrap_available = False
        self.shop.save()
        self.assertEqual(self._totals(cart, None)["gift_wrap_total"], Decimal("0"))
        self.assertEqual(gw.resolve_gift_wrap_selection(self.store, requested=True, product=self.p1), (False, Decimal("0")))

    def test_product_disabled_is_ineligible(self):
        self.p1.gift_wrap_enabled = False
        self.p1.save()
        self.assertFalse(gw.is_product_gift_wrap_eligible(self.p1))
        self.assertEqual(gw.resolve_gift_wrap_selection(self.store, requested=True, product=self.p1), (False, Decimal("0")))
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        self.assertEqual(self._totals(cart, None)["gift_wrap_total"], Decimal("0"))  # disabled after selection → dropped

    def test_product_price_override(self):
        self.p2.gift_wrap_price = Decimal("0")  # free for this product
        self.p2.save()
        self.assertEqual(gw.resolve_gift_wrap_price(self.store, self.p2), Decimal("0"))
        self.assertEqual(gw.resolve_gift_wrap_price(self.store, self.p1), Decimal("20000"))
        self.assertEqual(gw.resolve_gift_wrap_selection(self.store, requested=True, product=self.p1), (True, Decimal("20000")))

    def test_not_requested(self):
        self.assertEqual(gw.resolve_gift_wrap_selection(self.store, requested=False, product=self.p1), (False, Decimal("0")))

    def test_message_cleaning(self):
        self.assertEqual(gw.clean_gift_message("  سلام \x00 دوست\n\n من  ", store=self.store), "سلام دوست من")
        self.assertEqual(len(gw.clean_gift_message("x" * 500, store=self.store)), 200)
        self.shop.gift_wrap_message_enabled = False
        self.shop.save()
        self.assertEqual(gw.clean_gift_message("hi", store=self.store), "")


class GiftWrapOrderTests(GiftWrapBase):
    def test_order_persists_gift_wrap_separately_with_message(self):
        cart = self._wrapped_cart([(self.p1, 2), (self.p2, 1)], wrapped=(True, False))
        CartItem.objects.filter(cart=cart, product=self.p1).update(gift_message="تولدت مبارک")
        order = self._order(cart)
        self.assertEqual(order.gift_wrap_total, Decimal("40000"))
        self.assertEqual(order.gift_wrap_scope, "per_unit")
        self.assertEqual(order.items_total, Decimal("400000"))  # gift wrap NOT in items_total
        i1 = order.items.get(product=self.p1)
        i2 = order.items.get(product=self.p2)
        self.assertTrue(i1.gift_wrap_selected)
        self.assertEqual(i1.gift_message, "تولدت مبارک")
        self.assertFalse(i2.gift_wrap_selected)
        self.assertEqual(order.grand_total, order.items_total + order.tax + order.shipping_cost + order.gift_wrap_total)

    def test_price_change_after_order_does_not_alter_snapshot(self):
        order = self._order(self._wrapped_cart([(self.p1, 1)], wrapped=(True,)))
        self.shop.gift_wrap_price = Decimal("99999")
        self.shop.save()
        item = order.items.first()
        item.refresh_from_db()
        self.assertEqual(item.gift_wrap_unit_price, Decimal("20000"))

    def test_disabled_selection_dropped_at_order_time(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        self.p1.gift_wrap_enabled = False
        self.p1.save()
        order = self._order(cart)
        self.assertEqual(order.gift_wrap_total, Decimal("0"))
        self.assertFalse(order.items.first().gift_wrap_selected)
        self.assertEqual(order.items.first().gift_message, "")


class GiftWrapDiscountTests(GiftWrapBase):
    def test_coupon_does_not_discount_gift_wrap_by_default(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        totals = self._totals(cart, self._coupon("GW0", value=50))
        self.assertEqual(totals["coupon_discount"], Decimal("50000"))
        self.assertEqual(totals["gift_wrap_discount"], Decimal("0"))
        self.assertEqual(totals["gift_wrap_total"], Decimal("20000"))
        self.assertEqual(totals["grand_total"], Decimal("100000") - 50000 + totals["tax"] + 20000)

    def test_coupon_can_discount_gift_wrap_when_configured_no_double_count(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        totals = self._totals(cart, self._coupon("GW1", value=50, applies_to_gift_wrap=True))
        self.assertEqual(totals["coupon_discount"], Decimal("60000"))  # 50% of (100000+20000)
        self.assertEqual(totals["gift_wrap_discount"], Decimal("10000"))
        self.assertEqual(totals["coupon_item_discount"], Decimal("50000"))
        self.assertEqual(totals["grand_total"], Decimal("100000") - 50000 + totals["tax"] + 20000 - 10000)

    def test_max_discount_cap_applies_across_items_and_wrap(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        totals = self._totals(cart, self._coupon("GW2", value=100, applies_to_gift_wrap=True, max_discount=Decimal("30000")))
        self.assertEqual(totals["coupon_discount"], Decimal("30000"))
        self.assertEqual(totals["gift_wrap_discount"] + totals["coupon_item_discount"], Decimal("30000"))

    def test_order_with_coupon_and_wrap_persists_split(self):
        cart = self._wrapped_cart([(self.p1, 1)], wrapped=(True,))
        order = self._order(cart, self._coupon("GW3", value=50, applies_to_gift_wrap=True))
        self.assertEqual(order.coupon_discount, Decimal("60000"))
        self.assertEqual(order.gift_wrap_discount, Decimal("10000"))
        self.assertEqual(
            order.grand_total,
            order.items_total - (order.coupon_discount - order.gift_wrap_discount) + order.tax
            + order.shipping_cost + order.gift_wrap_total - order.gift_wrap_discount,
        )


class GiftWrapRefundTests(GiftWrapBase):
    def test_partial_and_full_refunds_include_net_gift_wrap(self):
        coupon = self._coupon("GWR", value=50, applies_to_gift_wrap=True)
        cart = self._wrapped_cart([(self.p1, 2)], wrapped=(True,))  # items 200000, wrap 40000
        order = self._order(cart, coupon)
        simulate_payment(order, True, store=self.store)
        item = order.items.first()
        r1 = execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        r2 = execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        order.refresh_from_db()
        total_gw = r1.items.first().gift_wrap_amount + r2.items.first().gift_wrap_amount
        self.assertEqual(total_gw, order.gift_wrap_total - order.gift_wrap_discount)
        self.assertEqual(refundable_amount(order), Decimal("0"))

    def test_cancellation_keeps_wrap_in_refundable_total(self):
        order = self._order(self._wrapped_cart([(self.p1, 1)], wrapped=(True,)))
        simulate_payment(order, True, store=self.store)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        self.assertEqual(refundable_amount(order), order.grand_total)
        self.assertIn(order.gift_wrap_total, [Decimal("20000")])


class GiftWrapRefundScopeTests(GiftWrapBase):
    def _refund_all_one_by_one(self, order):
        total_gw = Decimal("0")
        for item in order.items.all():
            for _ in range(item.quantity):
                refund = execute_order_refund(
                    order, store=self.store, actor=None,
                    line_requests=[{"order_item_id": item.pk, "quantity": 1}],
                )
                total_gw += refund.items.get().gift_wrap_amount
        return total_gw

    def test_per_line_and_per_order_refunds_never_exceed_or_lose_gift_wrap(self):
        coupon_kw = dict(value=10, applies_to_gift_wrap=True)
        for scope, expected_gross in ((Scope.PER_LINE, Decimal("40000")), (Scope.PER_ORDER, Decimal("20000"))):
            self._set_scope(scope)
            order = self._order(self._wrapped_cart([(self.p1, 2), (self.p2, 3)]), self._coupon(f"S-{scope}", **coupon_kw))
            self.assertEqual(order.gift_wrap_total, expected_gross)
            simulate_payment(order, True, store=self.store)
            order.refresh_from_db()
            refunded_gw = self._refund_all_one_by_one(order)
            self.assertEqual(refunded_gw, order.gift_wrap_total - order.gift_wrap_discount, scope)
            order.refresh_from_db()
            self.assertEqual(refundable_amount(order), order.shipping_cost + order.shipping_tax, scope)
