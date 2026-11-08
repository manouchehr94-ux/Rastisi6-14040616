"""Financial acceptance for commits 506cf70d (Trial first-purchase classification) and 5a0add96 (portal gateway ordering).

Everything runs over real HTTP with REAL provisioning (``provision_trial_store``), the real expiry evaluator, the real
unified checkout and the in-process fake Zibal (no network, dummy credentials). Money assertions come from the database."""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import PlatformCouponRedemption as Redemption, SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import platform_coupon_service as svc
from apps.billing.tests.test_trial_purchase_flow import EXPECTED, PW, PurchaseBase, make_owner
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent, subscription_service as ss

User = get_user_model()
PORTAL_HOST = "rastisi.localhost"


class Base(PurchaseBase):
    def setUp(self):
        super().setUp()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.finance = User.objects.create_user(username="fa-fin@example.com", password=PW, is_staff=True, is_superuser=True)

    def coupon(self, code="WELCOME20", **kw):
        kw.setdefault("name", code or "auto")
        kw.setdefault("kind", "percent")
        kw.setdefault("percent", 20)
        return svc.create_coupon(actor=self.finance, code=code, **kw)

    def end_trial(self, store=None):
        sub = self.sub(store)
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()

    def portal_buy(self, store, owner, version, interval="monthly"):
        c = Client(HTTP_HOST=PORTAL_HOST)
        c.force_login(owner)
        return c.post(f"/app/stores/{store.public_id}/billing/checkout/{version.pk}/", {"billing_interval": interval})

    def buy_with_code(self, version, code, interval="monthly", client=None, store=None):
        c = client or self.client
        token = c.post(reverse("dashboard:subscription-plan-preview"),
                       {"version_id": version.pk, "billing_interval": interval, "coupon_code": code}).context["preview"]["token"]
        return c.post(reverse("dashboard:subscription-plan-execute"),
                      {"version_id": version.pk, "preview_token": token, "billing_interval": interval, "coupon_code": code})

    def settle_online(self, invoice, client=None):
        attempt = self.pay_online(invoice, client)
        self.fake.paid(amount_rial=int(invoice.amount_due) * 10, order_id=attempt.public_token)
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        return attempt

    def activations(self, store):
        return SubscriptionEvent.objects.filter(subscription__store=store, to_status=StoreSubscription.Status.ACTIVE).count()


class FirstPaidPurchaseAfterEveryTrialStateTests(Base):
    """1. First paid purchase after an enabled-running, expired and disabled Trial, via the real engine."""

    def _assert_first_purchase_with_coupon(self, store, client, expected_status_before):
        self.assertEqual(svc.purpose_for(store, "plan_change"), "initial")
        self.assertEqual(self.sub(store).status, expected_status_before)
        coupon = self.coupon("WELCOME20")
        self.buy_with_code(self.pro, "WELCOME20", client=client)
        inv = self.invoice(store)
        self.assertEqual((inv.subtotal, inv.discount_total, inv.amount_due), (Decimal(EXPECTED["monthly"]), Decimal(200_000), Decimal(800_000)))
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.RESERVED)
        self.assertEqual(coupon.counted_redemptions(), 1)
        self.settle_online(inv, client)
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_paid, inv.amount_due), ("paid", Decimal(800_000), Decimal(0)))
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.REDEEMED)
        self.assertEqual(self.sub(store).status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.activations(store), 1)

    def test_enabled_running_trial(self):
        self._assert_first_purchase_with_coupon(self.store, self.client, StoreSubscription.Status.TRIALING)

    def test_expired_trial_after_the_real_evaluator_ran(self):
        self.end_trial()
        self._assert_first_purchase_with_coupon(self.store, self.client, StoreSubscription.Status.SUSPENDED)

    def test_trial_disabled_by_the_platform_never_started(self):
        from apps.subscriptions.tests.test_trial_engine import configure

        configure(enabled=False)
        owner, store = make_owner("notrial-fa@example.com", "بدون آزمایشی")
        client = self.client_for(store, owner)
        self.assertIsNone(self.sub(store).trial_start_at)
        self._assert_first_purchase_with_coupon(store, client, StoreSubscription.Status.SUSPENDED)

    def test_a_store_with_paid_history_is_no_longer_an_initial_purchase_in_any_trial_state(self):
        self.coupon("WELCOME20")
        self.buy_with_code(self.pro, "WELCOME20")
        self.settle_online(self.invoice())
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "plan_change")
        result = svc.evaluate(self.store, plan_version=self.lite, interval="monthly", purpose=svc.purpose_for(self.store, "plan_change"), code="WELCOME20")
        self.assertFalse(result.ok)

    def test_first_purchase_only_coupon_is_refused_after_a_real_paid_purchase_but_accepted_before(self):
        # allow_plan_change=True so that the ONLY thing that can refuse it later is the first-purchase rule itself
        self.coupon("ONCE", first_purchase_only=True, allow_plan_change=True)
        self.end_trial()
        self.buy_with_code(self.pro, "ONCE")
        self.assertEqual(self.invoice().discount_total, Decimal(200_000))
        self.settle_online(self.invoice())
        result = svc.evaluate(self.store, plan_version=self.lite, interval="monthly", purpose="plan_change", code="ONCE")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "first_purchase_only")


class PortalAutomaticCampaignAndGatewayTests(Base):
    """2, 3, 5. Portal first-purchase path: gateway judged on the post-discount amount_due, atomically."""

    def _no_gateway(self):
        return mock.patch("apps.portal.services.platform_gateway_service.checkout_options", return_value=[])

    def test_automatic_100_percent_needs_no_gateway_and_settles_internally_without_any_gateway_call(self):
        self.coupon(None, name="free-first", is_automatic=True, percent=100)
        with self._no_gateway():
            response = self.portal_buy(self.store, self.owner, self.pro)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-portal/handoff/", response["Location"])
        inv = self.invoice()
        self.assertEqual((inv.subtotal, inv.discount_total, inv.amount_due), (Decimal(EXPECTED["monthly"]), Decimal(EXPECTED["monthly"]), Decimal(0)))
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.RESERVED)
        self.assertEqual(self.sub().status, StoreSubscription.Status.TRIALING)          # creating the invoice activates nothing

        pay = reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk])
        with self._no_gateway(), mock.patch("apps.billing.services.payment_flow_service.start_payment") as start, \
                mock.patch("apps.billing.providers.zibal.requests.post", side_effect=AssertionError("NETWORK CALL")) as http:
            self.client.post(pay, {"method": "zibal", "amount": "1"})                    # a forged amount is ignored
            self.client.post(pay, {"method": "zibal"})                                   # repeated request
            start.assert_not_called()
            http.assert_not_called()
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_due), ("paid", Decimal(0)))
        # By design the internal settlement leaves ONE audit attempt: provider "manual", amount 0, a zero-due reference.
        # No gateway provider attempt exists and no network/gateway call was made (asserted above).
        attempts = list(SubscriptionPaymentAttempt.objects.filter(invoice=inv))
        self.assertEqual(len(attempts), 1)
        self.assertEqual((attempts[0].provider, attempts[0].amount), ("manual", Decimal(0)))
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=inv, provider="zibal").exists())
        self.assertEqual(Redemption.objects.filter(invoice=inv, status=Redemption.Status.REDEEMED).count(), 1)
        self.assertEqual(self.sub().status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.activations(self.store), 1)

    def test_positive_amount_without_gateway_is_refused_and_nothing_remains(self):
        self.coupon(None, name="part-first", is_automatic=True, percent=20)
        with self._no_gateway():
            response = self.portal_buy(self.store, self.owner, self.pro)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").exists())
        self.assertFalse(Redemption.objects.exists())
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, to_status=StoreSubscription.Status.ACTIVE).count(), 0)

    def _state(self):
        from apps.billing.models import BillingSequence, PlatformCouponAuditEvent, ScheduledPlanChange
        from apps.core.models import AuditLogEntry

        return (ScheduledPlanChange.objects.count(), AuditLogEntry.objects.count(), PlatformCouponAuditEvent.objects.count(),
                sorted(BillingSequence.objects.values_list("key", "last_value")))

    def test_refusal_rolls_back_scheduled_change_supersession_audit_rows_and_invoice_numbering(self):
        """start_plan_change supersedes an older scheduled change before it creates the invoice. A refusal for lack of a gateway
        must undo that too: the scheduled change survives, no audit row is left behind and no invoice number is burnt."""
        from apps.billing.models import ScheduledPlanChange

        ScheduledPlanChange.objects.create(subscription=self.sub(), store=self.store, target_plan_version=self.lite)
        self.coupon(None, name="part-first", is_automatic=True, percent=20)
        before = self._state()
        self.assertEqual(before[0], 1)
        with self._no_gateway():
            self.portal_buy(self.store, self.owner, self.pro)
        self.assertEqual(self._state(), before)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())

    def test_control_with_a_gateway_does_supersede_the_scheduled_change(self):
        """Proves the test above is not vacuous: the same purchase WITH a gateway really changes this state."""
        from apps.billing.models import ScheduledPlanChange

        ScheduledPlanChange.objects.create(subscription=self.sub(), store=self.store, target_plan_version=self.lite)
        self.coupon(None, name="part-first", is_automatic=True, percent=20)
        before = self._state()
        self.portal_buy(self.store, self.owner, self.pro)
        self.assertNotEqual(self._state(), before)
        self.assertEqual(ScheduledPlanChange.objects.count(), 0)
        self.assertTrue(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").exists())

    def test_no_coupon_positive_amount_without_gateway_is_still_refused(self):
        with self._no_gateway():
            self.portal_buy(self.store, self.owner, self.pro)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").exists())

    def test_with_a_gateway_the_automatic_campaign_charges_the_discounted_amount_once(self):
        self.coupon(None, name="part-first", is_automatic=True, percent=20)
        self.portal_buy(self.store, self.owner, self.pro)
        inv = self.invoice()
        self.assertEqual((inv.discount_total, inv.amount_due), (Decimal(200_000), Decimal(800_000)))
        attempt = self.pay_online(inv)
        self.assertEqual(int(attempt.amount), 800_000)


class ReuseReservationAndCallbackIntegrityTests(Base):
    """4, 6. Existing-invoice reuse, reservation consistency across failed/retried/duplicate payments."""

    def test_double_submit_reuses_one_invoice_and_one_reservation(self):
        self.coupon(None, name="auto20", is_automatic=True, percent=20)
        self.portal_buy(self.store, self.owner, self.pro)
        self.portal_buy(self.store, self.owner, self.pro)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").count(), 1)
        inv = self.invoice()
        self.assertEqual(Redemption.objects.filter(invoice=inv).count(), 1)
        self.assertEqual(inv.amount_due, Decimal(800_000))

    def test_failed_payment_keeps_one_reserved_discount_and_the_retry_pays_it_once(self):
        coupon = self.coupon("WELCOME20")
        self.buy_with_code(self.pro, "WELCOME20")
        inv = self.invoice()
        failed = self.pay_online(inv)
        self.callback(failed, "success=0&status=3&trackId=%d" % self.fake.track_id)
        inv.refresh_from_db()
        self.assertEqual((inv.amount_paid, inv.amount_due), (Decimal(0), Decimal(800_000)))
        self.assertEqual(self.sub().status, StoreSubscription.Status.TRIALING)
        self.assertEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.RESERVED)
        self.assertEqual(coupon.counted_redemptions(), 1)                                 # reserved, never double counted
        attempt = self.settle_online(inv)
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)      # duplicate callback
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(800_000)))
        self.assertEqual(Redemption.objects.filter(invoice=inv, status=Redemption.Status.REDEEMED).count(), 1)
        self.assertEqual(Redemption.objects.filter(invoice=inv).count(), 1)
        self.assertEqual(self.activations(self.store), 1)

    def test_wrong_amount_from_the_gateway_never_activates_and_never_redeems(self):
        self.coupon("WELCOME20")
        self.buy_with_code(self.pro, "WELCOME20")
        inv = self.invoice()
        attempt = self.pay_online(inv)
        self.fake.paid(amount_rial=EXPECTED["monthly"] * 10, order_id=attempt.public_token)       # the UNDISCOUNTED amount
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        inv.refresh_from_db()
        self.assertNotEqual(inv.status, "paid")
        self.assertEqual(self.sub().status, StoreSubscription.Status.TRIALING)
        self.assertNotEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.REDEEMED)

    def test_paid_invoice_is_immutable_to_coupon_changes_and_late_apply(self):
        self.coupon("WELCOME20")
        self.coupon("OTHER50", percent=50)
        self.buy_with_code(self.pro, "WELCOME20")
        inv = self.invoice()
        self.settle_online(inv)
        snapshot = (inv.subtotal, inv.discount_total)
        svc.set_coupon_status(svc.PlatformCoupon.objects.get(code="WELCOME20"), "disabled", actor=self.finance)
        with self.assertRaises(svc.CouponError):
            svc.apply_coupon_to_invoice(inv, code="OTHER50", actor=self.finance)
        inv.refresh_from_db()
        self.assertEqual((inv.subtotal, inv.discount_total), snapshot)
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.REDEEMED)


class TenantIsolationTests(Base):
    """6. Tenant isolation on the changed portal path and on callbacks."""

    def setUp(self):
        super().setUp()
        self.other_owner, self.other_store = make_owner("other-fa@example.com", "فروشگاه دیگر")

    def test_another_owner_cannot_buy_into_this_store_through_the_portal(self):
        self.coupon(None, name="auto20", is_automatic=True, percent=20)
        response = self.portal_buy(self.store, self.other_owner, self.pro)           # other owner, victim store id
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())
        self.assertFalse(Redemption.objects.exists())

    def test_automatic_campaign_restricted_to_one_store_never_discounts_another(self):
        self.coupon(None, name="only-mine", is_automatic=True, percent=50, stores=[self.store])
        self.portal_buy(self.other_store, self.other_owner, self.pro)
        other_inv = SubscriptionInvoice.objects.get(store=self.other_store, kind="plan_change")
        self.assertEqual((other_inv.discount_total, other_inv.amount_due), (Decimal(0), Decimal(EXPECTED["monthly"])))
        self.assertFalse(Redemption.objects.filter(store=self.other_store).exists())
        self.portal_buy(self.store, self.owner, self.pro)
        mine = SubscriptionInvoice.objects.get(store=self.store, kind="plan_change")
        self.assertEqual(mine.discount_total, Decimal(500_000))
        self.assertEqual(Redemption.objects.get(invoice=mine).store_id, self.store.pk)

    def test_another_stores_client_cannot_settle_or_view_this_discounted_invoice(self):
        self.coupon(None, name="free", is_automatic=True, percent=100)
        self.portal_buy(self.store, self.owner, self.pro)
        inv = self.invoice()
        intruder = self.client_for(self.other_store, self.other_owner)
        pay = reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk])
        self.assertEqual(intruder.get(reverse("dashboard:platform-checkout", args=["subscription", inv.pk])).status_code, 404)
        self.assertEqual(intruder.post(pay, {"method": "zibal"}).status_code, 404)
        inv.refresh_from_db()
        self.assertNotEqual(inv.status, "paid")
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.RESERVED)


import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks")
@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class PortalPurchaseContentionTests(TransactionTestCase):
    """Real threads through the real portal view. Two stores race for ONE allocation of a 100% automatic campaign while NO
    gateway is configured. Exactly one gets the free invoice; the other is judged on the full price, so with no gateway it is
    refused and leaves nothing behind. The capacity is never over-allocated."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        from apps.billing.tests.test_trial_purchase_flow import formula_plan

        _p, self.pro = formula_plan("race-pro", 1_000_000, order=2)
        self.finance = User.objects.create_user(username="race-fin@example.com", password=PW, is_staff=True, is_superuser=True)
        self.buyers = [make_owner(f"race-buy-{i}@example.com", f"رقابت {i}") for i in range(2)]
        self.campaign = svc.create_coupon(actor=self.finance, code=None, name="one-free", is_automatic=True, kind="percent", percent=100,
                                          max_redemptions=1)

    def test_last_free_allocation_goes_to_exactly_one_store_through_the_portal_view(self):
        barrier = threading.Barrier(2)

        def worker(pair):
            owner, store = pair
            close_old_connections()
            try:
                c = Client(HTTP_HOST=PORTAL_HOST)
                c.force_login(owner)
                barrier.wait(timeout=15)
                with mock.patch("apps.portal.services.platform_gateway_service.checkout_options", return_value=[]):
                    return c.post(f"/app/stores/{store.public_id}/billing/checkout/{self.pro.pk}/", {"billing_interval": "monthly"}).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(worker, self.buyers))
        self.assertEqual(codes, [302, 302])
        invoices = list(SubscriptionInvoice.objects.filter(kind="plan_change"))
        self.assertEqual(len(invoices), 1, "the loser (full price, no gateway) must leave no invoice")
        self.assertEqual((invoices[0].discount_total, invoices[0].amount_due), (Decimal(EXPECTED["monthly"]), Decimal(0)))
        self.assertEqual(Redemption.objects.count(), 1)
        self.assertEqual(self.campaign.counted_redemptions(), 1)


class ZeroValueConversionEndsInitialEligibilityTests(Base):
    """Finding: a fully discounted first Trial-to-paid conversion settles with amount_paid == 0, so positive-money history never
    saw it and the next upgrade was classified ``initial`` again. A settled conversion must end ``initial`` eligibility, while
    ``first_purchase_only`` keeps its positive-payment meaning."""

    def _free_first_conversion(self, store=None, owner=None, version=None):
        store, owner, version = store or self.store, owner or self.owner, version or self.lite
        client = self.client if store is self.store else self.client_for(store, owner)
        self.portal_buy(store, owner, version)
        inv = SubscriptionInvoice.objects.filter(store=store, kind="plan_change").latest("pk")
        client.post(reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk]), {"method": "zibal"})
        inv.refresh_from_db()
        return inv, client

    def _assert_settled_free(self, inv, store):
        self.assertEqual((inv.status, inv.amount_paid, inv.amount_due), ("paid", Decimal(0), Decimal(0)))
        self.assertEqual(inv.coupon_redemption.status, Redemption.Status.REDEEMED)
        self.assertEqual(self.sub(store).status, StoreSubscription.Status.ACTIVE)
        self.assertNotEqual(self.sub(store).plan_version.plan.code, "trial")

    def test_second_upgrade_after_enabled_trial_free_conversion_is_plan_change_and_not_discounted_again(self):
        campaign = self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        inv, _ = self._free_first_conversion()
        self._assert_settled_free(inv, self.store)
        # the historical TRIAL_STARTED event is still there: that is exactly what used to resurrect `initial`
        self.assertTrue(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="trial_started").exists())
        self.assertFalse(svc.has_paid_subscription_history(self.store))                 # positive-money semantics untouched
        self.assertTrue(svc.has_completed_initial_conversion(self.store))
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "plan_change")

        self.portal_buy(self.store, self.owner, self.pro)
        upgrade = SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").latest("pk")
        self.assertNotEqual(upgrade.pk, inv.pk)
        self.assertEqual((upgrade.discount_total, upgrade.amount_due), (Decimal(0), Decimal(EXPECTED["monthly"])))
        self.assertFalse(Redemption.objects.filter(invoice=upgrade).exists())
        self.assertEqual(campaign.counted_redemptions(), 1)

    def test_free_conversion_after_a_naturally_expired_trial_ends_initial_eligibility(self):
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        self.end_trial()
        self.assertEqual(self.sub().status, StoreSubscription.Status.SUSPENDED)
        inv, _ = self._free_first_conversion()
        self._assert_settled_free(inv, self.store)
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "plan_change")
        self.portal_buy(self.store, self.owner, self.pro)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change").latest("pk").discount_total, Decimal(0))

    def test_free_conversion_when_the_platform_disabled_the_trial_ends_initial_eligibility(self):
        from apps.subscriptions.tests.test_trial_engine import configure

        configure(enabled=False)
        owner, store = make_owner("notrial-conv@example.com", "بدون آزمایشی")
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        self.assertIsNone(self.sub(store).trial_start_at)
        inv, _ = self._free_first_conversion(store, owner)
        self._assert_settled_free(inv, store)
        self.assertEqual(svc.purpose_for(store, "plan_change"), "plan_change")
        self.portal_buy(store, owner, self.pro)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=store, kind="plan_change").latest("pk").discount_total, Decimal(0))

    def test_an_initial_only_campaign_cannot_be_chained_across_repeated_zero_value_upgrades(self):
        campaign = self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        self._free_first_conversion()
        for version in (self.pro, self.lite, self.pro):                                  # keeps trying to upgrade/switch
            self.portal_buy(self.store, self.owner, version)
        free_redeemed = Redemption.objects.filter(store=self.store, status=Redemption.Status.REDEEMED)
        self.assertEqual(free_redeemed.count(), 1)
        self.assertEqual(campaign.counted_redemptions(), 1)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store, kind="plan_change", discount_total__gt=0).exclude(
            pk__in=free_redeemed.values("invoice_id")).exists())

    def test_the_converting_invoice_never_disqualifies_itself_when_its_reservation_is_renewed_after_settlement(self):
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        inv, _ = self._free_first_conversion()
        self.assertEqual(svc.purpose_for(self.store, "plan_change", exclude_invoice=inv), "initial")   # evaluating ITSELF
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "plan_change")                  # anyone else after it
        self.assertEqual(svc.ensure_reservation_active(inv).status, Redemption.Status.REDEEMED)       # settled: untouched

    def test_first_purchase_only_keeps_its_positive_payment_meaning(self):
        """Not changed by this correction: a free conversion moved no money, so first_purchase_only is still accepted afterwards,
        and it is refused only once real money has been paid."""
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        self.coupon("FIRSTONLY", first_purchase_only=True, allow_plan_change=True)
        self._free_first_conversion()
        result = svc.evaluate(self.store, plan_version=self.pro, interval="monthly", purpose="plan_change", code="FIRSTONLY")
        self.assertTrue(result.ok)
        self.buy_with_code(self.pro, "FIRSTONLY")
        paid = self.invoice()
        self.settle_online(paid)
        again = svc.evaluate(self.store, plan_version=self.lite, interval="monthly", purpose="plan_change", code="FIRSTONLY")
        self.assertFalse(again.ok)
        self.assertEqual(again.code, "first_purchase_only")

    def test_a_refund_does_not_reopen_initial_eligibility(self):
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        inv, _ = self._free_first_conversion()
        SubscriptionInvoice.objects.filter(pk=inv.pk).update(status=SubscriptionInvoice.Status.REFUNDED)
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "plan_change")

    def test_a_trial_plan_invoice_alone_is_not_a_conversion(self):
        """Only a settled invoice on a REAL plan ends initial eligibility; nothing on the internal Trial plan does."""
        self.assertFalse(svc.has_completed_initial_conversion(self.store))
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "initial")
        self.portal_buy(self.store, self.owner, self.pro)                                 # an OPEN (unsettled) invoice
        self.assertFalse(svc.has_completed_initial_conversion(self.store))
        self.assertEqual(svc.purpose_for(self.store, "plan_change"), "initial")

    def test_cross_tenant_zero_value_conversion_is_denied_and_creates_no_invoice_or_reservation(self):
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        intruder_owner, intruder_store = make_owner("intruder-conv@example.com", "مهاجم")
        before = (SubscriptionInvoice.objects.count(), Redemption.objects.count())
        denied = self.portal_buy(self.store, intruder_owner, self.lite)                 # intruder owner, victim store
        self.assertIn(denied.status_code, (403, 404))
        self.assertEqual((SubscriptionInvoice.objects.count(), Redemption.objects.count()), before)
        self.assertEqual(self.sub().status, StoreSubscription.Status.TRIALING)
        self.assertEqual(self.sub(intruder_store).status, StoreSubscription.Status.TRIALING)

    def test_zero_value_settlement_creates_only_the_internal_zero_value_record_and_never_calls_a_gateway(self):
        self.coupon(None, name="free-auto", is_automatic=True, percent=100)
        self.portal_buy(self.store, self.owner, self.lite)
        inv = self.invoice()
        pay = reverse("dashboard:platform-checkout-pay", args=["subscription", inv.pk])
        with mock.patch("apps.billing.services.payment_flow_service.start_payment") as start, \
                mock.patch("apps.billing.providers.zibal.requests.post", side_effect=AssertionError("NETWORK CALL")) as http:
            self.client.post(pay, {"method": "zibal"})
            self.client.post(pay, {"method": "zibal"})                                   # repeated settlement request
            start.assert_not_called()
            http.assert_not_called()
        attempts = list(SubscriptionPaymentAttempt.objects.filter(invoice=inv))
        self.assertEqual(len(attempts), 1)
        self.assertEqual((attempts[0].provider, attempts[0].amount, attempts[0].status), ("manual", Decimal(0), "succeeded"))
        self.assertTrue(attempts[0].provider_payment_id.startswith("zero-due-"))
        self.assertFalse(SubscriptionPaymentAttempt.objects.exclude(provider="manual").filter(invoice=inv).exists())
        self.assertEqual(self.activations(self.store), 1)
        self.assertEqual(Redemption.objects.filter(invoice=inv, status=Redemption.Status.REDEEMED).count(), 1)
