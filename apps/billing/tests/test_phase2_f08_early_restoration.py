"""F-08 correction: a financially suspended subscription must NOT resume merely because a FUTURE period has been paid.

Access resumes automatically only when a valid, settled, non-refunded funded period actually covers the current time (the scheduled
evaluator), or through the authorized, audited superuser reinstatement. Synthetic data only; no schema change."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.billing.services import financial_suspension_service as fss, invoice_service
from apps.billing.tests.test_phase2_financial_suspension import FinBase, make_version, pay, renewal
from apps.sms.models import SmsBalance
from apps.stores.models import Store
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
S = StoreSubscription.Status
ET = SubscriptionEvent.EventType


class EarlyRestorationTests(FinBase):
    def setUp(self):
        super().setUp()
        sub_svc.activate_subscription(self.sub, period_end=self.day(-30))
        self.sub.refresh_from_db()
        self.current = self.renewal_paid(self.day(-30), self.day(30))

    def access(self):
        return ent.get_subscription_access_state(self.store)

    def assert_restricted(self):
        self.assertEqual(self.refresh(), S.SUSPENDED)
        self.assertFalse(self.access().allows_growth)

    # -- the scenario list requested in review -------------------------------------------------------------------------------
    def test_refund_of_the_current_funded_period_suspends(self):
        self.full_refund(self.current)
        self.assert_restricted()
        self.assertTrue(sub_svc.is_financially_suspended(self.sub))

    def test_a_future_period_paid_AFTER_the_suspension_does_not_resume_access(self):
        self.full_refund(self.current)
        future = self.renewal_paid(self.day(30), self.day(60))                      # the customer pays the next period in advance
        self.assertEqual(future.status, SubscriptionInvoice.Status.PAID)
        self.assert_restricted()                                                    # before the fix: ACTIVE immediately
        self.assertTrue(sub_svc.is_financially_suspended(self.sub))                 # still recognised as financial
        self.assertEqual(self.sub.current_period_end, future.billing_period_end)    # the paid period is recorded, not lost
        kept = self.events(ET.RENEWED)[-1]
        self.assertEqual((kept.from_status, kept.to_status), (S.SUSPENDED, S.SUSPENDED))
        self.assertTrue(kept.metadata.get("kept_suspended"))

    def test_no_access_before_the_future_period_begins_and_restoration_exactly_when_it_begins(self):
        self.full_refund(self.current)
        future = self.renewal_paid(self.day(30), self.day(60))
        for moment in (self.now, self.day(15), self.day(30) - timedelta(seconds=1)):
            result = fss.evaluate_restorations(now=moment)
            self.assertEqual((result["restored"], result["errors"]), (0, []), moment)
            self.assertEqual(self.refresh(), S.SUSPENDED)
        result = fss.evaluate_restorations(now=self.day(30))                        # the funded period begins
        self.assertEqual((result["restored"], result["errors"]), (1, []))
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertEqual((self.sub.current_period_start, self.sub.current_period_end), (future.billing_period_start, future.billing_period_end))
        self.assertTrue(self.access().allows_growth)
        self.assertEqual(fss.evaluate_restorations(now=self.day(31))["restored"], 0)    # idempotent
        self.assertEqual(len(self.events(ET.RESUMED)), 1)

    def test_the_funded_period_end_is_exclusive(self):
        self.full_refund(self.current)
        self.renewal_paid(self.day(30), self.day(60))
        self.assertEqual(fss.evaluate_restorations(now=self.day(60))["restored"], 0)
        self.assertEqual(self.refresh(), S.SUSPENDED)

    def test_a_future_period_paid_BEFORE_the_refund_is_preserved_but_gives_no_access_until_it_begins(self):
        future = self.renewal_paid(self.day(30), self.day(60))
        self.full_refund(self.current)
        self.assert_restricted()
        self.assertEqual(fss.evaluate_restorations(now=self.day(10))["restored"], 0)
        self.assertEqual(self.refresh(), S.SUSPENDED)
        future.refresh_from_db()
        self.assertEqual((future.status, future.amount_paid), (SubscriptionInvoice.Status.PAID, future.grand_total))   # still paid
        self.assertEqual(fss.evaluate_restorations(now=self.day(30))["restored"], 1)
        self.assertEqual(self.refresh(), S.ACTIVE)

    def test_a_payment_whose_period_covers_the_present_does_resume_access(self):
        self.full_refund(self.current)
        self.assert_restricted()
        self.renewal_paid(self.day(-1), self.day(29))                                # money for the present was received
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertTrue(self.access().allows_growth)

    def test_a_non_financial_suspension_still_resumes_on_a_renewal_as_before(self):
        sub_svc.suspend_subscription(self.sub, reason="پایانِ Dunning")
        self.renewal_paid(self.day(30), self.day(60))
        self.assertEqual(self.refresh(), S.ACTIVE)                                   # unchanged behaviour outside F-08

    def test_the_audited_superuser_reinstatement_is_the_only_early_path(self):
        self.full_refund(self.current)
        self.renewal_paid(self.day(30), self.day(60))
        staff = User.objects.create_user(username="f08-staff", password="x", is_staff=True)
        root = User.objects.create_user(username="f08-root", password="x", is_staff=True, is_superuser=True)
        with self.assertRaises(fss.FinancialSuspensionError):
            fss.reinstate(self.sub, actor=staff, reason="not allowed for staff")
        self.assertEqual(self.refresh(), S.SUSPENDED)
        fss.reinstate(self.sub, actor=root, reason="goodwill approved by finance")
        self.assertEqual(self.refresh(), S.ACTIVE)
        resumed = self.events(ET.RESUMED)[-1]
        self.assertEqual((resumed.actor_id, resumed.metadata["kind"]), (root.pk, "financial_reinstated"))

    # -- independently paid entitlements are preserved --------------------------------------------------------------------
    def test_independently_paid_invoices_stores_and_sms_credits_are_untouched(self):
        future = self.renewal_paid(self.day(30), self.day(60))
        other_store = Store.objects.create(name="ب", slug="f08-other", admin_subdomain="f08-other")
        other = sub_svc.create_subscription(other_store, make_version("f08-other"))
        other_inv = pay(invoice_service.create_invoice(
            other, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(other.plan_version)]))
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 321})
        self.full_refund(self.current)
        self.renewal_paid(self.day(60), self.day(90))                                # and one more, paid later
        other.refresh_from_db()
        self.assertEqual((other.status, other_inv.status), (S.ACTIVE, SubscriptionInvoice.Status.PAID))
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 321)
        self.assertEqual(SubscriptionInvoice.objects.filter(subscription=self.sub, status="paid").count(), 2)
        self.assertEqual(Decimal(SubscriptionInvoice.objects.get(pk=future.pk).amount_paid), future.grand_total)
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())

    def test_a_second_settled_invoice_that_covers_the_present_keeps_access_continuous(self):
        self.renewal_paid(self.day(-10), self.day(40))                               # independently paid, covers now
        self.full_refund(self.current)
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertEqual(self.events(ET.SUSPENDED), [])
