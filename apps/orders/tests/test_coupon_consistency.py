"""C1: یک منبعِ حقیقت برایِ اعتبارِ کد + ابزارِ تشخیصیِ فقط‌خواندنیِ verify_coupon_consistency."""

import datetime as dt
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.cart.models import Coupon
from apps.cart.services import coupon_rules as cr
from apps.cart.services.coupon_service import customer_coupons
from apps.cart.services.pricing import coupon_is_applicable
from apps.cart.management.commands.verify_coupon_consistency import Command
from apps.orders.models import CouponRedemption, Order
from apps.orders.services.order_service import change_order_status
from apps.orders.services.payment_service import simulate_payment
from apps.orders.tests.engine_base import EngineBase

R = CouponRedemption.Status


class SingleSourceOfTruthTests(EngineBase):
    def setUp(self):
        super().setUp()
        self.p = self._product("c1", "1000000")
        self.now = timezone.now()

    def surfaces(self, coupon, customer=None):
        """نتیجه‌ی همه‌ی سطوح برایِ یک کد: (evaluate, cart_totals, coupon_is_applicable, customer_coupons)."""
        customer = customer or self.customer
        cart = self._cart(customer, lines=[(self.p, 1)])
        totals = self._totals(cart, coupon, customer=customer)
        evaluation = cr.evaluate_coupon(coupon, lines=_lines(cart, coupon), customer=customer, payment_gateway=self.gateway)
        return evaluation, totals

    def test_all_surfaces_agree_for_every_lifecycle_state(self):
        day = dt.timedelta(days=1)
        cases = {
            "active": dict(),
            "inactive": dict(is_active=False),
            "not_started": dict(starts_at=self.now + day),
            "expired": dict(expires_at=self.now - day),
            "capacity_full": dict(usage_limit=1, used_count=1),
        }
        for name, kw in cases.items():
            coupon = self._coupon(f"S-{name}"[:20], customer=self.customer, **kw)
            evaluation, totals = self.surfaces(coupon)
            self.assertEqual(totals["coupon_applied"], evaluation.ok, name)
            self.assertEqual(totals["coupon_error_code"], evaluation.code, name)
            self.assertEqual(coupon_is_applicable(coupon, Decimal("1000000")), evaluation.ok, name)
            state = customer_coupons(self.store, self.customer)
            row = next(r for r in state if r["coupon"].pk == coupon.pk)
            self.assertEqual(row["state"] == "active", evaluation.ok, name)
            expected_state = {"active": "active", "inactive": "inactive", "not_started": "upcoming",
                              "expired": "expired", "capacity_full": "used"}[name]
            self.assertEqual(row["state"], expected_state, name)
            # ثبتِ سفارش هم همان تصمیم را می‌گیرد
            order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
            self.assertEqual(order.coupon_discount > 0, evaluation.ok, name)

    def test_per_customer_exhaustion_is_consistent_everywhere(self):
        coupon = self._coupon("PCX", customer=self.customer, per_customer_limit=1)
        self._order(self._cart(lines=[(self.p, 1)]), coupon)
        evaluation, totals = self.surfaces(coupon)
        self.assertEqual((evaluation.ok, evaluation.code), (False, cr.PER_CUSTOMER_LIMIT))
        self.assertEqual(totals["coupon_error_code"], cr.PER_CUSTOMER_LIMIT)
        row = next(r for r in customer_coupons(self.store, self.customer) if r["coupon"].pk == coupon.pk)
        self.assertEqual(row["state"], "used")  # قبلاً به‌اشتباه «active» نمایش داده می‌شد

    def test_per_customer_window_reopens_the_code_in_account_view(self):
        coupon = self._coupon("PCW", customer=self.customer, per_customer_limit=1, per_customer_period_days=30)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        CouponRedemption.objects.filter(order=order).update(created_at=self.now - dt.timedelta(days=31))
        row = next(r for r in customer_coupons(self.store, self.customer) if r["coupon"].pk == coupon.pk)
        self.assertEqual(row["state"], "active")

    def test_ownership_is_enforced_by_the_same_helper(self):
        coupon = self._coupon("OWN", customer=self.customer)
        stranger = self._customer("u77", "09120000077")
        self.assertEqual(cr.ownership_failure(coupon, stranger), cr.WRONG_CUSTOMER)
        self.assertEqual(cr.ownership_failure(coupon, None), cr.LOGIN_REQUIRED)
        self.assertEqual(cr.ownership_failure(coupon, self.customer), "")
        self.assertEqual(cr.availability_failure(coupon, customer=stranger), cr.WRONG_CUSTOMER)
        # کدِ عمومی برایِ همه قابل‌استفاده است
        self.assertEqual(cr.availability_failure(self._coupon("PUB"), customer=None), "")

    def test_helper_order_matches_documented_precedence(self):
        coupon = self._coupon("PREC", is_active=False, expires_at=self.now - dt.timedelta(days=1), usage_limit=1, used_count=1)
        self.assertEqual(cr.validity_failure(coupon), cr.INACTIVE)
        coupon.is_active = True
        self.assertEqual(cr.validity_failure(coupon), cr.EXPIRED)
        coupon.expires_at = None
        self.assertEqual(cr.availability_failure(coupon), cr.USAGE_LIMIT)
        self.assertEqual(cr.availability_failure(coupon, check_usage=False), "")

    def test_legacy_coupon_is_applicable_signature_and_min_order(self):
        coupon = self._coupon("LEG", min_order=Decimal("500000"))
        self.assertFalse(coupon_is_applicable(coupon, Decimal("100000")))
        self.assertTrue(coupon_is_applicable(coupon, Decimal("500000")))
        self.assertFalse(coupon_is_applicable(None, Decimal("1")))


def _lines(cart, coupon):
    from apps.cart.services.pricing import build_coupon_lines

    return build_coupon_lines(list(cart.items.select_related("product", "variant")), coupon)


class VerifyCouponConsistencyCommandTests(EngineBase):
    def setUp(self):
        super().setUp()
        self.p = self._product("vc", "1000000")

    def run_cmd(self, *args):
        out = StringIO()
        call_command("verify_coupon_consistency", *args, stdout=out)
        return out.getvalue()

    def kinds(self, store=None):
        return {kind for kind, _ in Command.collect(store)}

    def test_clean_after_real_flows(self):
        coupon = self._coupon("FLOW", usage_limit=10, per_customer_limit=3)
        paid = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        simulate_payment(paid, True, store=self.store)
        failed = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        simulate_payment(failed, False, store=self.store)
        canceled = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        change_order_status(canceled, Order.Status.CANCELED, store=self.store)
        self._order(self._cart(lines=[(self.p, 1)]), coupon)  # reserved
        self.assertEqual(Command.collect(), [])
        out = self.run_cmd()
        self.assertIn("issues=0", out)
        self.run_cmd("--fail-on-issues", "--store", self.store.slug)

    def test_detects_each_kind_of_drift_and_is_read_only(self):
        coupon = self._coupon("DRIFT", usage_limit=2, per_customer_limit=1)
        order = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        Coupon.objects.filter(pk=coupon.pk).update(used_count=5)  # drift + over limit
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELED)  # counted on canceled
        bad_cfg = self._coupon("BADCFG", value=150)  # percent > 100
        orphan_order = self._order(self._cart(lines=[(self.p, 1)]), self._coupon("ORPH"))
        CouponRedemption.objects.filter(order=orphan_order).delete()  # order without redemption
        redeemed = self._order(self._cart(lines=[(self.p, 1)]), self._coupon("REDM"))
        CouponRedemption.objects.filter(order=redeemed).update(status=R.REDEEMED)  # redeemed on unpaid order
        other = self._customer("u88", "09120000088")
        mism = self._order(self._cart(lines=[(self.p, 1)]), self._coupon("MISM", customer=self.customer))
        CouponRedemption.objects.filter(order=mism).update(customer=other)
        snapshot = list(Coupon.objects.order_by("pk").values_list("pk", "used_count", "is_active"))
        reds = list(CouponRedemption.objects.order_by("pk").values_list("pk", "status"))
        found = self.kinds()
        for expected in ("used_count_drift", "used_count_over_limit", "counted_on_canceled_order", "percent_out_of_range",
                         "order_without_redemption", "redeemed_on_unpaid_order", "redemption_customer_mismatch",
                         "personal_coupon_used_by_other"):
            self.assertIn(expected, found)
        with self.assertRaises(CommandError):
            self.run_cmd("--fail-on-issues")
        out = self.run_cmd()
        self.assertIn("used_count_drift=", out)
        # فقط‌خواندنی
        self.assertEqual(snapshot, list(Coupon.objects.order_by("pk").values_list("pk", "used_count", "is_active")))
        self.assertEqual(reds, list(CouponRedemption.objects.order_by("pk").values_list("pk", "status")))
        self.assertTrue(bad_cfg.pk)

    def test_released_on_paid_and_counted_on_failed_payment_and_limit_exceeded(self):
        coupon = self._coupon("MORE", per_customer_limit=1)
        o1 = self._order(self._cart(lines=[(self.p, 1)]), coupon)
        simulate_payment(o1, True, store=self.store)
        CouponRedemption.objects.filter(order=o1).update(status=R.RELEASED)
        o2 = self._order(self._cart(lines=[(self.p, 1)]), self._coupon("MORE2"))
        Order.objects.filter(pk=o2.pk).update(payment_status=Order.PaymentStatus.FAILED)
        coupon2 = self._coupon("LIM2", per_customer_limit=1)
        for _ in range(2):
            order = self._order(self._cart(lines=[(self.p, 1)]), coupon2)
        CouponRedemption.objects.filter(coupon=coupon2).update(status=R.RESERVED)
        found = self.kinds()
        self.assertTrue({"released_on_paid_order", "counted_on_failed_payment"} <= found)

    def test_store_scoping(self):
        from apps.stores.models import Store

        other = Store.objects.create(name="o", slug="cc-other", status=Store.Status.ACTIVE)
        Coupon.objects.create(store=other, code="OTHERBAD", type="percent", value=500)
        self.assertIn("percent_out_of_range", self.kinds())
        self.assertNotIn("percent_out_of_range", self.kinds(self.store))
        with self.assertRaises(CommandError):
            self.run_cmd("--store", "nope")
