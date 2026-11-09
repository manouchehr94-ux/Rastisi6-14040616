"""``first_purchase_only`` after a zero-value Trial-to-paid conversion.

Policy: a successfully settled conversion from Trial to ANY non-Trial plan consumes first-purchase eligibility, even when the
payable amount was zero. Positive-payment history still counts. The invoice being evaluated never disqualifies itself, a refund
does not restore eligibility, and renewal/upgrade coupons that are not first-purchase-only are unaffected.

Real HTTP, real provisioning, real settlement path, in-process fake gateway, synthetic data only."""

from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.billing.models import PlatformCouponRedemption as Redemption, SubscriptionInvoice
from apps.billing.services import platform_coupon_service as svc
from apps.billing.tests.test_platform_coupon_financial_acceptance import Base
from apps.billing.tests.test_trial_purchase_flow import make_owner
from apps.subscriptions.models import StoreSubscription

FIRST = "FIRSTONLY"


class FirstPurchaseBase(Base):
    def setUp(self):
        super().setUp()
        # allow_plan_change=True so that ONLY the first-purchase rule can refuse it after the conversion
        self.first = self.coupon(FIRST, first_purchase_only=True, allow_plan_change=True)

    def free_conversion(self, store=None, owner=None, version=None):
        """Real first purchase from the Trial with a 100% automatic campaign, settled through the internal zero-value path."""
        store, owner, version = store or self.store, owner or self.owner, version or self.lite
        if not hasattr(self, "_auto"):
            self._auto = self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        client = self.client if store is self.store else self.client_for(store, owner)
        self.portal_buy(store, owner, version)
        inv = SubscriptionInvoice.objects.filter(store=store, kind="plan_change").latest("pk")
        client.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"})
        inv.refresh_from_db()
        return inv

    def evaluate_first(self, store=None, *, purpose="plan_change", version=None, **kw):
        return svc.evaluate(store or self.store, plan_version=version or self.pro, interval="monthly", purpose=purpose, code=FIRST, **kw)


class ZeroValueConversionConsumesFirstPurchaseTests(FirstPurchaseBase):
    def test_precondition_the_conversion_really_moved_no_money(self):
        inv = self.free_conversion()
        self.assertEqual((inv.status, inv.amount_paid, inv.amount_due, inv.discount_total), ("paid", Decimal(0), Decimal(0), inv.subtotal))
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.REDEEMED)
        self.assertEqual(self.sub().status, StoreSubscription.Status.ACTIVE)
        self.assertFalse(svc.has_paid_subscription_history(self.store))                 # no positive payment...
        self.assertTrue(svc.has_completed_initial_conversion(self.store))               # ...but the conversion is complete

    def test_first_purchase_only_is_rejected_after_a_zero_value_conversion_even_when_plan_changes_are_allowed(self):
        self.assertTrue(self.evaluate_first().ok)                                        # eligible before the conversion
        self.free_conversion()
        result = self.evaluate_first()
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "first_purchase_only")

    def test_rejected_through_the_real_checkout_apply_endpoint_and_nothing_is_written(self):
        self.free_conversion()
        self.portal_buy(self.store, self.owner, self.pro)                                # a normal, undiscounted upgrade invoice
        upgrade = SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").latest("pk")
        self.assertEqual(upgrade.discount_total, Decimal(0))
        response = self.client.post(reverse("dashboard:platform-checkout-coupon-apply", args=["subscription", upgrade.pk]),
                                    {"coupon_code": FIRST}, follow=True)
        self.assertIn(svc.MESSAGES["first_purchase_only"], [str(m) for m in response.context["messages"]])
        upgrade.refresh_from_db()
        self.assertEqual((upgrade.discount_total, upgrade.coupon_snapshot), (Decimal(0), {}))
        self.assertFalse(Redemption.objects.filter(invoice=upgrade).exists())
        with self.assertRaises(svc.CouponError) as ctx:
            svc.apply_coupon_to_invoice(upgrade, code=FIRST, actor=self.finance)
        self.assertEqual(ctx.exception.code, "first_purchase_only")

    def test_the_rule_holds_after_a_naturally_expired_trial(self):
        self.end_trial()
        self.assertEqual(self.sub().status, StoreSubscription.Status.SUSPENDED)
        self.free_conversion()
        self.assertEqual(self.evaluate_first().code, "first_purchase_only")

    def test_the_rule_holds_when_the_platform_disabled_the_trial(self):
        from apps.subscriptions.tests.test_trial_engine import configure

        configure(enabled=False)
        owner, store = make_owner("fp-notrial@example.com", "بدون آزمایشی")
        self.assertIsNone(self.sub(store).trial_start_at)
        self.assertTrue(self.evaluate_first(store).ok)
        self.free_conversion(store, owner)
        self.assertEqual(self.evaluate_first(store).code, "first_purchase_only")


class PositivePaymentHistoryStillRespectedTests(FirstPurchaseBase):
    def test_a_real_paid_purchase_still_consumes_first_purchase_eligibility(self):
        self.coupon("PART20", percent=20)
        self.buy_with_code(self.lite, "PART20")
        inv = self.invoice()
        self.assertGreater(inv.amount_due, 0)
        self.assertTrue(self.evaluate_first().ok)                                        # an unpaid invoice consumes nothing
        self.settle_online(inv)
        self.assertTrue(svc.has_paid_subscription_history(self.store))
        self.assertEqual(self.evaluate_first().code, "first_purchase_only")

    def test_failed_and_abandoned_payments_do_not_consume_eligibility(self):
        self.coupon("PART20", percent=20)
        self.buy_with_code(self.lite, "PART20")
        inv = self.invoice()
        failed = self.pay_online(inv)
        self.callback(failed, "success=0&status=3&trackId=%d" % self.fake.track_id)
        self.pay_online(inv)                                                              # started, never completed
        self.assertFalse(svc.has_completed_initial_conversion(self.store))
        self.assertTrue(self.evaluate_first(purpose="initial").ok)


class InvoiceNeverDisqualifiesItselfTests(FirstPurchaseBase):
    def setUp(self):
        super().setUp()
        self.first100 = self.coupon("FIRST100", percent=100, first_purchase_only=True)

    def _convert_with_first100(self, *, expire_reservation=False):
        self.buy_with_code(self.lite, "FIRST100")
        inv = self.invoice()
        self.assertEqual((inv.amount_due, inv.coupon_redemption.status), (Decimal(0), Redemption.Status.RESERVED))
        if expire_reservation:
            Redemption.objects.filter(invoice=inv).update(expires_at=timezone.now() - timedelta(minutes=5))
        self.client.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"})
        inv.refresh_from_db()
        return inv

    def test_the_first_purchase_only_coupon_itself_converts_and_is_redeemed(self):
        inv = self._convert_with_first100()
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(0)))
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.REDEEMED)

    def test_a_lapsed_reservation_is_renewed_at_settlement_because_the_invoice_excludes_itself(self):
        inv = self._convert_with_first100(expire_reservation=True)
        self.assertEqual(inv.status, "paid")
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.REDEEMED)
        self.assertEqual(self.activations(self.store), 1)

    def test_re_evaluating_the_original_invoice_passes_but_any_other_invoice_is_refused(self):
        inv = self._convert_with_first100()
        own = svc.evaluate(self.store, plan_version=self.lite, interval="monthly", purpose="initial", code="FIRST100", exclude_invoice=inv)
        self.assertTrue(own.ok, own.code)
        other = svc.evaluate(self.store, plan_version=self.lite, interval="monthly", purpose="initial", code="FIRST100")
        self.assertEqual(other.code, "first_purchase_only")
        self.assertEqual(svc.ensure_reservation_active(inv).status, Redemption.Status.REDEEMED)       # settled: untouched
        self.assertEqual(svc.purpose_for(self.store, "plan_change", exclude_invoice=inv), "initial")


class RefundDoesNotRestoreEligibilityTests(FirstPurchaseBase):
    def test_refunded_and_partially_refunded_zero_value_conversions_stay_consumed(self):
        inv = self.free_conversion()
        for status in (SubscriptionInvoice.Status.REFUNDED, SubscriptionInvoice.Status.PARTIALLY_REFUNDED):
            with self.subTest(status=status):
                SubscriptionInvoice.objects.filter(pk=inv.pk).update(status=status)
                self.assertEqual(self.evaluate_first().code, "first_purchase_only")
                self.assertEqual(svc.purpose_for(self.store, "plan_change"), "plan_change")

    def test_a_refunded_positive_payment_stays_consumed_too(self):
        self.coupon("PART20", percent=20)
        self.buy_with_code(self.lite, "PART20")
        inv = self.invoice()
        self.settle_online(inv)
        SubscriptionInvoice.objects.filter(pk=inv.pk).update(status=SubscriptionInvoice.Status.REFUNDED)
        self.assertEqual(self.evaluate_first().code, "first_purchase_only")


class OtherCouponCategoriesUnaffectedTests(FirstPurchaseBase):
    def test_a_plain_upgrade_coupon_still_applies_after_a_zero_value_conversion(self):
        self.coupon("UPG20", allow_plan_change=True, allow_initial=False)
        self.free_conversion()
        result = svc.evaluate(self.store, plan_version=self.pro, interval="monthly", purpose=svc.purpose_for(self.store, "plan_change"), code="UPG20")
        self.assertTrue(result.ok, result.code)
        self.assertEqual(result.discount_amount, Decimal(200_000))

    def test_a_renewal_coupon_still_applies_to_a_renewal_after_a_zero_value_conversion(self):
        self.coupon("REN10", percent=10, allow_renewal=True, allow_initial=False)
        self.free_conversion()
        result = svc.evaluate(self.store, plan_version=self.lite, interval="monthly", purpose="renewal", code="REN10")
        self.assertTrue(result.ok, result.code)

    def test_a_plain_initial_coupon_keeps_its_purpose_rule_and_is_not_made_first_purchase_only(self):
        self.coupon("INIT10", percent=10)
        self.free_conversion()
        result = svc.evaluate(self.store, plan_version=self.pro, interval="monthly", purpose="plan_change", code="INIT10")
        self.assertEqual(result.code, "ineligible_purpose")                               # unchanged: refused by purpose, not by first-purchase


class IdempotencyAndIsolationTests(FirstPurchaseBase):
    def test_repeated_settlement_requests_change_nothing_and_the_rule_still_holds(self):
        inv = self.free_conversion()
        pay = reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk])
        for _ in range(3):
            self.client.post(pay, {"method": "zibal"})
        self.assertEqual(Redemption.objects.filter(invoice=inv).count(), 1)
        self.assertEqual(Redemption.objects.filter(invoice=inv, status=Redemption.Status.REDEEMED).count(), 1)
        self.assertEqual(self._auto.counted_redemptions(), 1)
        self.assertEqual(self.activations(self.store), 1)
        self.assertEqual(self.evaluate_first().code, "first_purchase_only")

    def test_another_stores_eligibility_is_not_consumed(self):
        other_owner, other_store = make_owner("fp-other@example.com", "فروشگاه دیگر")
        self.free_conversion()
        self.assertEqual(self.evaluate_first().code, "first_purchase_only")
        self.assertTrue(self.evaluate_first(other_store, purpose="initial").ok)
        self.assertFalse(svc.has_completed_initial_conversion(other_store))

    def test_a_conversion_in_one_store_does_not_leak_into_a_second_free_conversion_elsewhere(self):
        other_owner, other_store = make_owner("fp-other2@example.com", "فروشگاه سوم")
        self.free_conversion()
        inv2 = self.free_conversion(other_store, other_owner)
        self.assertEqual((inv2.status, inv2.coupon_redemption.status), ("paid", Redemption.Status.REDEEMED))
        self.assertEqual(inv2.store_id, other_store.pk)
        self.assertEqual(Redemption.objects.filter(store=self.store, status=Redemption.Status.REDEEMED).count(), 1)
        self.assertEqual(Redemption.objects.filter(store=other_store, status=Redemption.Status.REDEEMED).count(), 1)
