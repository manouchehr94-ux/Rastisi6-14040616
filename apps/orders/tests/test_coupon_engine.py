"""موتورِ پیشرفته‌ی کد تخفیف + دفترِ استفاده + کادوپیچی (سمتِ سرور)."""

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.cart.models import Cart, CartItem, Coupon
from apps.cart.services import coupon_rules
from apps.cart.services.pricing import cart_totals
from apps.catalog.models import Brand, Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.customers.models import Address, Customer
from apps.orders.models import CouponRedemption, Order, PaymentGateway, ShippingMethod
from apps.orders.services.coupon_redemption_service import CouponUnavailableError, mark_redeemed, release_redemption
from apps.orders.services.order_service import change_order_status, create_order_from_cart
from apps.orders.services.payment_service import simulate_payment
from apps.orders.tests.engine_base import EngineBase
from apps.stores.models import Store

User = get_user_model()


class DiscountCalculationTests(EngineBase):
    def test_percent_with_max_discount_cap(self):
        p = self._product("p1", "20000000")
        coupon = self._coupon(value=30, max_discount=Decimal("4000000"))
        totals = self._totals(self._cart(lines=[(p, 1)]), coupon)
        self.assertTrue(totals["coupon_applied"])
        self.assertEqual(totals["coupon_discount"], Decimal("4000000"))  # 30% = 6M, capped
        self.assertEqual(
            totals["grand_total"], Decimal("20000000") - Decimal("4000000") + totals["tax"] + totals["shipping_cost"],
        )

    def test_percent_below_cap_not_capped(self):
        p = self._product("p2", "10000000")
        coupon = self._coupon(value=30, max_discount=Decimal("4000000"))
        totals = self._totals(self._cart(lines=[(p, 1)]), coupon)
        self.assertEqual(totals["coupon_discount"], Decimal("3000000"))

    def test_fixed_discount_never_makes_total_negative(self):
        p = self._product("p3", "50000")
        coupon = self._coupon(type=Coupon.Type.FIXED, value=999999)
        totals = self._totals(self._cart(lines=[(p, 1)]), coupon)
        self.assertEqual(totals["coupon_discount"], Decimal("50000"))
        self.assertEqual(totals["grand_total"], Decimal("0"))

    def test_free_shipping_coupon(self):
        p = self._product("p4", "100000")
        self.shipping.cost = Decimal("30000")
        self.shipping.save()
        cart = self._cart(lines=[(p, 1)])
        coupon = self._coupon(type=Coupon.Type.FREE_SHIP, value=0)
        totals = cart_totals(cart, store=self.store, coupon=coupon, shipping_method=self.shipping, customer=self.customer)
        self.assertTrue(totals["free_shipping"])
        self.assertEqual(totals["shipping_cost"], Decimal("0"))

    def test_expired_and_not_started_codes_rejected(self):
        p = self._product("p5", "100000")
        cart = self._cart(lines=[(p, 1)])
        expired = self._coupon("EXP", expires_at=timezone.now() - dt.timedelta(minutes=1))
        future = self._coupon("FUT", starts_at=timezone.now() + dt.timedelta(days=1))
        self.assertEqual(self._totals(cart, expired)["coupon_error_code"], coupon_rules.EXPIRED)
        self.assertEqual(self._totals(cart, future)["coupon_error_code"], coupon_rules.NOT_STARTED)
        self.assertEqual(self._totals(cart, expired)["coupon_discount"], Decimal("0"))

    def test_min_max_cart_and_item_count(self):
        p = self._product("p6", "100000")
        cart = self._cart(lines=[(p, 2)])  # 200000, 2 items
        self.assertEqual(self._totals(cart, self._coupon("A", min_order=Decimal("300000")))["coupon_error_code"], coupon_rules.MIN_ORDER)
        self.assertEqual(self._totals(cart, self._coupon("B", max_order=Decimal("100000")))["coupon_error_code"], coupon_rules.MAX_ORDER)
        self.assertEqual(self._totals(cart, self._coupon("C", min_items=3))["coupon_error_code"], coupon_rules.MIN_ITEMS)
        self.assertEqual(self._totals(cart, self._coupon("D", max_items=1))["coupon_error_code"], coupon_rules.MAX_ITEMS)
        self.assertTrue(self._totals(cart, self._coupon("E", min_items=2, max_items=2))["coupon_applied"])

    def test_category_brand_product_restrictions_discount_only_eligible_lines(self):
        bag = self._product("bag1", "1000000", self.cat_bag)
        shoe = self._product("shoe1", "1000000", self.cat_shoe, brand=self.nike)
        cart = self._cart(lines=[(bag, 1), (shoe, 1)])
        by_cat = self._coupon("CAT", value=50, restrictions={"category_ids": [self.cat_shoe.pk]})
        self.assertEqual(self._totals(cart, by_cat)["coupon_discount"], Decimal("500000"))
        by_brand = self._coupon("BR", value=10, restrictions={"brand_ids": [self.nike.pk]})
        self.assertEqual(self._totals(cart, by_brand)["coupon_discount"], Decimal("100000"))
        excl = self._coupon("EX", value=10, restrictions={"excluded_brand_ids": [self.nike.pk]})
        self.assertEqual(self._totals(cart, excl)["coupon_discount"], Decimal("100000"))
        none = self._coupon("NO", restrictions={"product_ids": [999999]})
        self.assertEqual(self._totals(cart, none)["coupon_error_code"], coupon_rules.NO_ELIGIBLE_ITEMS)

    def test_child_category_matches_parent_restriction(self):
        child = Category.objects.create(store=self.store, name="کیف دستی", slug="hand-eng", parent=self.cat_bag)
        p = self._product("hb", "1000000", child)
        coupon = self._coupon("PAR", value=10, restrictions={"category_ids": [self.cat_bag.pk]})
        self.assertEqual(self._totals(self._cart(lines=[(p, 1)]), coupon)["coupon_discount"], Decimal("100000"))

    def test_not_stackable_with_product_discount_excludes_discounted_lines(self):
        disc = self._product("d1", "1000000", discount=10)  # final 900000
        full = self._product("f1", "1000000")
        cart = self._cart(lines=[(disc, 1), (full, 1)])
        coupon = self._coupon("NS", value=10, stacks_with_product_discount=False)
        self.assertEqual(self._totals(cart, coupon)["coupon_discount"], Decimal("100000"))  # only full-price line

    def test_payment_and_shipping_restrictions(self):
        p = self._product("pr", "100000")
        cart = self._cart(lines=[(p, 1)])
        other_gw = PaymentGateway.objects.create(store=self.store, name="دیگر", slug="gw2-eng")
        coupon = self._coupon("PG", restrictions={"payment_gateway_ids": [other_gw.pk]})
        self.assertEqual(self._totals(cart, coupon)["coupon_error_code"], coupon_rules.PAYMENT_METHOD)

    def test_restrictions_validation(self):
        self.assertEqual(coupon_rules.validate_restrictions({"product_ids": [3, 1, 3]}), {"product_ids": [1, 3]})
        for bad in [{"evil": 1}, {"product_ids": "1"}, {"product_ids": [-1]}, {"weekdays": [9]}, {"hours": [5, 5]}, "x"]:
            with self.assertRaises(coupon_rules.CouponRestrictionError, msg=str(bad)):
                coupon_rules.validate_restrictions(bad)


class CustomerOwnedCouponTests(EngineBase):
    def test_owned_coupon_only_for_owner(self):
        p = self._product("o1", "100000")
        other = self._customer("u2", "09120000002")
        coupon = self._coupon("MINE", customer=self.customer)
        cart = self._cart(lines=[(p, 1)])
        self.assertTrue(self._totals(cart, coupon)["coupon_applied"])
        self.assertEqual(self._totals(cart, coupon, customer=other)["coupon_error_code"], coupon_rules.WRONG_CUSTOMER)
        guest = cart_totals(cart, store=self.store, coupon=coupon, customer=None)
        self.assertEqual(guest["coupon_error_code"], coupon_rules.LOGIN_REQUIRED)

    def test_owned_coupon_cannot_be_forced_through_order_creation(self):
        p = self._product("o2", "100000")
        other = self._customer("u3", "09120000003")
        Address.objects.create(customer=other, receiver_name="ب", phone="09120000003", province="فارس", city="شیراز",
                               postal_code="1111111111", full_address="x")
        coupon = self._coupon("MINE2", customer=self.customer)
        order = self._order(self._cart(customer=other, lines=[(p, 1)]), coupon, customer=other)
        self.assertEqual(order.coupon_discount, Decimal("0"))
        self.assertIsNone(order.coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)


class RedemptionLifecycleTests(EngineBase):
    def setUp(self):
        super().setUp()
        self.p = self._product("rl", "1000000")

    def test_reserve_then_redeem_on_payment(self):
        coupon = self._coupon("LIFE", value=10, usage_limit=5)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(order.coupon_discount, Decimal("100000"))
        self.assertEqual(order.coupon_redemption.status, CouponRedemption.Status.RESERVED)
        simulate_payment(order, True, store=self.store)
        order.coupon_redemption.refresh_from_db()
        self.assertEqual(order.coupon_redemption.status, CouponRedemption.Status.REDEEMED)

    def test_failed_payment_releases_capacity(self):
        coupon = self._coupon("FAIL", usage_limit=1)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        simulate_payment(order, False, store=self.store)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        redemption = CouponRedemption.objects.get(order=order)
        self.assertEqual(redemption.status, CouponRedemption.Status.RELEASED)
        self.assertEqual(redemption.release_reason, "payment_failed")
        # a later successful retry re-takes the capacity
        simulate_payment(order, True, store=self.store)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        order.coupon_redemption.refresh_from_db()
        self.assertEqual(order.coupon_redemption.status, CouponRedemption.Status.REDEEMED)

    def test_cancellation_releases_capacity_once(self):
        coupon = self._coupon("CANC", usage_limit=1)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        release_redemption(order, reason="again")  # idempotent
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        # capacity is usable again
        order2 = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        self.assertEqual(order2.coupon_discount, Decimal("100000"))

    def test_total_limit_blocks_second_order(self):
        coupon = self._coupon("ONE", usage_limit=1)
        self._order(self._cart(lines=[(self.p, 1)]), coupon)
        order2 = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        self.assertEqual(order2.coupon_discount, Decimal("0"))  # limit reached → not applied
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_atomic_capacity_check_rejects_when_limit_consumed_concurrently(self):
        """مسابقه‌ی واقعی: totals قبلاً «قابل‌استفاده» بود، اما پیش از رزرو یک سفارشِ دیگر ظرفیت را گرفت."""
        from apps.orders.services.coupon_redemption_service import reserve_redemption

        coupon = self._coupon("RACE", usage_limit=1)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)  # consumes the only slot
        stale = Coupon.objects.get(pk=coupon.pk)
        stale.used_count = 0  # stale in-memory view
        other = self._order(self._cart(lines=[(self.p, 1)]))  # no coupon
        with self.assertRaises(CouponUnavailableError):
            reserve_redemption(coupon=stale, order=other, customer=self.customer, discount_amount=1)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_per_customer_limit(self):
        coupon = self._coupon("PC", per_customer_limit=1)
        self._order(self._cart(lines=[(self.p, 1)]), coupon)
        cart2 = self._cart(lines=[(self.p, 1)])
        self.assertEqual(self._totals(cart2, coupon)["coupon_error_code"], coupon_rules.PER_CUSTOMER_LIMIT)
        other = self._customer("u9", "09120000009")
        self.assertTrue(self._totals(cart2, coupon, customer=other)["coupon_applied"])

    def test_mark_redeemed_without_redemption_is_noop(self):
        order = self._order(self._cart(lines=[(self.p, 1)]))
        self.assertIsNone(mark_redeemed(order))

    def test_full_refund_marks_refunded_and_keeps_capacity_consumed(self):
        from apps.orders.services.refund_service import execute_order_refund

        coupon = self._coupon("RF", value=10, usage_limit=1)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        simulate_payment(order, True, store=self.store)
        item = order.items.first()
        refund = execute_order_refund(
            order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}],
        )
        order.refresh_from_db()
        # refund is net of the coupon share: exactly what the customer paid (no shipping here)
        self.assertEqual(refund.approved_amount, order.grand_total - order.shipping_cost - order.shipping_tax)
        self.assertEqual(CouponRedemption.objects.get(order=order).status, CouponRedemption.Status.REFUNDED)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)  # capacity NOT returned after a completed purchase

    def test_partial_refunds_are_prorated_net_of_coupon_and_sum_to_paid(self):
        from apps.orders.services.refund_service import execute_order_refund, refundable_amount

        coupon = self._coupon("PR", value=10)
        order = self._order(self._cart(lines=[(self.p, 3)]), coupon)  # 3,000,000 − 300,000
        simulate_payment(order, True, store=self.store)
        item = order.items.first()
        r1 = execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        r2 = execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 2}])
        self.assertEqual(r1.items.first().amount, Decimal("900000"))
        self.assertEqual(r2.items.first().amount, Decimal("1800000"))
        order.refresh_from_db()
        self.assertEqual(refundable_amount(order), Decimal("0"))
