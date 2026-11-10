"""Phase 2 / F-08: a FULL refund of the period in force suspends the subscription; past and future periods and partial refunds do
not; the scheduled evaluator restores a financially suspended subscription when a paid period begins; only a platform superuser can
reinstate by hand, with an audit trail. Nothing is ever deleted. Synthetic providers only; no schema change."""

import io
import itertools
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund
from apps.billing.providers.base import RefundResult
from apps.billing.services import (
    attempt_service, confirmation_service, financial_suspension_service as fss, invoice_service, refund_service,
)
from apps.billing.tests.test_phase2_refunds import FakeProvider, patched
from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
S = StoreSubscription.Status
ET = SubscriptionEvent.EventType
PLATFORM_HOST = "platformadmins.rastisi.localhost"
_ids = itertools.count(1)


def paying_provider():
    return FakeProvider(lambda p: RefundResult(provider_refund_id=f"fs-rf-{next(_ids)}", succeeded=True, raw_summary={}))


def make_version(slug, price="400000", number=1):
    plan = Plan.objects.get_or_create(code=f"pl-{slug}", defaults={"name": "Plan"})[0]
    return PlanVersion.objects.create(
        plan=plan, version_number=number, status=PlanVersion.Status.PUBLISHED, display_price=Decimal(price), currency="IRT")


def pay(invoice):
    inv = invoice_service.open_invoice(invoice)
    attempt = attempt_service.create_attempt(inv)
    confirmation_service.confirm_payment(
        attempt=attempt, amount=inv.amount_due, currency=inv.currency, provider_payment_id=f"fs-pay-{inv.pk}")
    inv.refresh_from_db()
    return inv


def renewal(sub, start, end):
    return invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(sub.plan_version)],
        period_start=start, period_end=end)


class FinBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.store = Store.objects.create(name="ف", slug="p2fs", admin_subdomain="p2fs")
        self.version = make_version("p2fs")
        self.sub = sub_svc.create_subscription(self.store, self.version)

    def day(self, n):
        return self.now + timedelta(days=n)

    def initial_paid(self):
        """A real INITIAL payment on a PENDING subscription (the funded period is recorded at fulfilment)."""
        inv = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(self.version)])
        inv = pay(inv)
        self.sub.refresh_from_db()
        return inv

    def renewal_paid(self, start, end):
        inv = pay(renewal(self.sub, start, end))
        self.sub.refresh_from_db()
        return inv

    def full_refund(self, invoice, *, provider=None):
        invoice.refresh_from_db()
        with patched(provider or paying_provider()):
            return refund_service.request_refund(invoice, amount=invoice.amount_paid, reason="full", idempotency_key=f"fs-{invoice.pk}")

    def events(self, event_type):
        return list(self.sub.events.filter(event_type=event_type).order_by("pk"))

    def refresh(self):
        self.sub.refresh_from_db()
        return self.sub.status


class FundedPeriodRecordingTests(FinBase):
    def test_initial_payment_records_invoice_and_funded_period_on_the_activation_event(self):
        inv = self.initial_paid()
        event = self.sub.events.get(idempotency_key=f"invoice-{inv.pk}")
        self.assertEqual(event.metadata["invoice_id"], inv.pk)
        self.assertIn("funded_start", event.metadata)
        self.assertEqual(fss.funded_period(inv)[0], "period")

    def test_renewal_payment_records_the_funded_period(self):
        self.initial_paid()
        inv = self.renewal_paid(self.day(30), self.day(60))
        kind, start, end = fss.funded_period(inv)
        self.assertEqual(kind, "period")
        self.assertEqual((start, end), (inv.billing_period_start, inv.billing_period_end))

    def test_a_paid_plan_upgrade_differential_funds_no_period(self):
        self.initial_paid()
        higher = make_version("p2fs-hi", "900000")
        inv = invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=higher,
            lines=[invoice_service.plan_line_spec(higher)])
        inv = pay(inv)
        self.assertEqual(fss.funded_period(inv)[0], "none")


class FullRefundOfTheCurrentPeriodTests(FinBase):
    def test_full_refund_of_the_period_in_force_suspends_with_a_financial_marker_and_keeps_all_data(self):
        inv = self.initial_paid()
        self.assertEqual(self.refresh(), S.ACTIVE)
        refund = self.full_refund(inv)
        inv.refresh_from_db()
        self.assertEqual((refund.status, inv.status), (SubscriptionRefund.Status.SUCCEEDED, SubscriptionInvoice.Status.REFUNDED))
        self.assertEqual(self.refresh(), S.SUSPENDED)
        event = sub_svc.financial_suspension_event(self.sub)
        self.assertEqual(event.metadata["kind"], "financial")
        self.assertEqual((event.metadata["invoice_id"], event.metadata["refund_id"]), (inv.pk, refund.pk))
        self.assertEqual(event.idempotency_key, f"refund-{refund.pk}-revoke")
        self.assertTrue(Store.objects.filter(pk=self.store.pk).exists())                 # nothing deleted
        self.assertTrue(SubscriptionInvoice.objects.filter(pk=inv.pk).exists())
        self.assertFalse(ent.get_subscription_access_state(self.store).allows_growth)    # restricted, not erased
        self.assertIn("بازپرداخت", ent.get_subscription_access_state(self.store).warning)

    def test_partial_refund_changes_nothing(self):
        inv = self.initial_paid()
        with patched(paying_provider()):
            refund_service.request_refund(inv, amount=Decimal("100000"), reason="partial", idempotency_key="fs-part")
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.PARTIALLY_REFUNDED)
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertEqual(self.events(ET.SUSPENDED), [])

    def test_a_refund_still_pending_or_unknown_does_not_suspend_until_confirmed(self):
        inv = self.initial_paid()
        provider = FakeProvider(lambda p: (_ for _ in ()).throw(RuntimeError("timeout")))
        self.full_refund(inv, provider=provider)
        self.assertEqual(self.refresh(), S.ACTIVE)
        refund = SubscriptionRefund.objects.get(invoice=inv)
        self.assertEqual(refund.status, SubscriptionRefund.Status.PENDING)
        refund_service.complete_refund_manually(refund, actor=None, reference="BANK-REF-77777")
        self.assertEqual(self.refresh(), S.SUSPENDED)                                     # confirmed -> now it applies

    def test_repeating_the_hook_is_idempotent(self):
        inv = self.initial_paid()
        refund = self.full_refund(inv)
        inv.refresh_from_db()
        again = fss.apply_refund(inv, refund)
        self.assertEqual(again, fss.ALREADY)
        self.assertEqual(len(self.events(ET.SUSPENDED)), 1)

    def test_another_store_is_never_affected(self):
        other_store = Store.objects.create(name="ب", slug="p2fs-o", admin_subdomain="p2fs-o")
        other = sub_svc.create_subscription(other_store, make_version("p2fs-o"))
        other_inv = pay(invoice_service.create_invoice(
            other, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(other.plan_version)]))
        inv = self.initial_paid()
        self.full_refund(inv)
        other.refresh_from_db()
        self.assertEqual((other.status, other_inv.status), (S.ACTIVE, SubscriptionInvoice.Status.PAID))
        self.assertEqual(fss.evaluate_restorations(now=self.day(40))["restored"], 0)


class PastFutureAndOverlappingPeriodTests(FinBase):
    def setUp(self):
        super().setUp()
        sub_svc.activate_subscription(self.sub, period_end=self.day(-30))
        self.sub.refresh_from_db()

    def test_refunding_a_past_period_changes_nothing(self):
        past = self.renewal_paid(self.day(-60), self.day(-30))
        current = self.renewal_paid(self.day(-30), self.day(30))
        refund = self.full_refund(past)
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertEqual(self.events(ET.SUSPENDED), [])
        self.assertEqual(
            AuditLogEntry.objects.get(action_code="billing.refund_entitlement_outcome", request_id=f"refund-{refund.pk}-entitlement")
            .after_summary.count(fss.PAST), 1)
        current.refresh_from_db()
        self.assertEqual(current.status, SubscriptionInvoice.Status.PAID)

    def test_refunding_a_future_period_changes_nothing_now(self):
        self.renewal_paid(self.day(-30), self.day(30))
        future = self.renewal_paid(self.day(30), self.day(60))
        self.full_refund(future)
        self.assertEqual(self.refresh(), S.ACTIVE)

    def test_current_period_refund_with_a_paid_future_period_suspends_now_and_restores_when_the_future_period_begins(self):
        current = self.renewal_paid(self.day(-30), self.day(30))
        future = self.renewal_paid(self.day(30), self.day(60))
        self.full_refund(current)
        self.assertEqual(self.refresh(), S.SUSPENDED)                                      # the present is unfunded
        self.assertEqual(fss.evaluate_restorations(now=self.now)["restored"], 0)           # still no payment covers now
        self.assertEqual(self.refresh(), S.SUSPENDED)
        result = fss.evaluate_restorations(now=self.day(31))                               # the paid future period has begun
        self.assertEqual((result["restored"], result["errors"]), (1, []))
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertEqual(self.sub.current_period_end, future.billing_period_end)
        resumed = self.events(ET.RESUMED)
        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0].metadata["kind"], "financial_restored")
        again = fss.evaluate_restorations(now=self.day(32))                                # idempotent
        self.assertEqual(again["restored"], 0)
        self.assertEqual(len(self.events(ET.RESUMED)), 1)
        future.refresh_from_db()
        self.assertEqual(future.status, SubscriptionInvoice.Status.PAID)                    # the future period stayed paid

    def test_a_second_settled_invoice_covering_the_present_prevents_the_suspension(self):
        first = self.renewal_paid(self.day(-30), self.day(30))
        self.renewal_paid(self.day(-10), self.day(40))
        refund = self.full_refund(first)
        self.assertEqual(self.refresh(), S.ACTIVE)
        self.assertEqual(
            AuditLogEntry.objects.get(action_code="billing.refund_entitlement_outcome", request_id=f"refund-{refund.pk}-entitlement")
            .after_summary.count(fss.COVERED), 1)

    def test_a_dunning_or_other_suspension_is_never_auto_restored(self):
        self.renewal_paid(self.day(-30), self.day(30))
        sub_svc.suspend_subscription(self.sub, reason="پایانِ Dunning")
        self.assertEqual(fss.evaluate_restorations(now=self.now)["scanned"], 0)
        self.assertEqual(self.refresh(), S.SUSPENDED)

    def test_a_later_non_financial_suspension_is_not_treated_as_financial(self):
        current = self.renewal_paid(self.day(-30), self.day(30))
        self.full_refund(current)
        self.sub.refresh_from_db()
        self.assertTrue(sub_svc.is_financially_suspended(self.sub))
        renewed = self.renewal_paid(self.day(30), self.day(60))                           # paying again resumes it
        self.assertEqual(self.refresh(), S.ACTIVE)
        sub_svc.suspend_subscription(self.sub, reason="پایانِ Dunning")
        self.sub.refresh_from_db()
        self.assertFalse(sub_svc.is_financially_suspended(self.sub))
        self.assertEqual(fss.evaluate_restorations(now=self.day(31))["restored"], 0)
        self.assertEqual(renewed.status, SubscriptionInvoice.Status.PAID)


class UndeterminableAndFailureTests(FinBase):
    def test_legacy_invoice_without_a_recorded_period_is_never_revoked_automatically(self):
        sub_svc.activate_subscription(self.sub, period_end=self.day(30))                   # activated BEFORE: no funded metadata
        inv = pay(invoice_service.create_invoice(
            self.sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(self.version)]))
        refund = self.full_refund(inv)
        self.assertEqual(refund.status, SubscriptionRefund.Status.SUCCEEDED)
        self.assertEqual(self.refresh(), S.ACTIVE)
        entry = AuditLogEntry.objects.get(action_code="billing.refund_entitlement_outcome", request_id=f"refund-{refund.pk}-entitlement")
        self.assertIn(fss.UNDETERMINED, entry.after_summary)

    def test_a_failure_in_the_hook_never_undoes_the_refund_and_asks_finance_to_review(self):
        inv = self.initial_paid()
        with mock.patch.object(fss, "apply_refund", side_effect=RuntimeError("boom")):
            refund = self.full_refund(inv)
        inv.refresh_from_db()
        self.assertEqual((refund.status, inv.status), (SubscriptionRefund.Status.SUCCEEDED, SubscriptionInvoice.Status.REFUNDED))
        self.assertTrue(AuditLogEntry.objects.filter(action_code="billing.refund_entitlement_review_needed", object_id=str(inv.pk)).exists())
        self.assertEqual(self.refresh(), S.ACTIVE)

    def test_the_evaluate_command_runs_the_restoration_and_reports_it(self):
        sub_svc.activate_subscription(self.sub, period_end=self.day(-30))
        current = self.renewal_paid(self.day(-30), self.day(30))
        self.renewal_paid(self.day(30), self.day(60))
        self.full_refund(current)
        out = io.StringIO()
        call_command("evaluate_subscription_states", "--dry-run", stdout=out)
        self.assertIn("financial_suspension_restored=0", out.getvalue())
        self.assertEqual(self.refresh(), S.SUSPENDED)


class ReinstatementTests(FinBase):
    def setUp(self):
        super().setUp()
        self.inv = self.initial_paid()
        self.full_refund(self.inv)
        self.sub.refresh_from_db()
        self.root = User.objects.create_user(username="p2fs-root", password="x", is_staff=True, is_superuser=True)

    def test_only_a_platform_superuser_can_reinstate_and_a_reason_is_mandatory(self):
        staff = User.objects.create_user(username="p2fs-staff", password="x", is_staff=True)
        owner = User.objects.create_user(username="p2fs-owner", password="x")
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER)
        for user in (staff, owner, None):
            with self.assertRaises(fss.FinancialSuspensionError):
                fss.reinstate(self.sub, actor=user, reason="reason is fine")
        with self.assertRaises(fss.FinancialSuspensionError):
            fss.reinstate(self.sub, actor=self.root, reason="  ")
        self.assertEqual(self.refresh(), S.SUSPENDED)

    def test_reinstatement_records_actor_reason_time_and_subscription_and_is_idempotent(self):
        fss.reinstate(self.sub, actor=self.root, reason="finance approved goodwill")
        self.assertEqual(self.refresh(), S.ACTIVE)
        event = self.events(ET.RESUMED)[-1]
        self.assertEqual((event.actor_id, event.reason), (self.root.pk, "finance approved goodwill"))
        self.assertEqual(event.metadata["kind"], "financial_reinstated")
        self.assertIn("at", event.metadata)
        audit = AuditLogEntry.objects.get(action_code="billing.financial_suspension_reinstated")
        self.assertEqual((audit.actor_id, audit.object_id), (self.root.pk, str(self.sub.pk)))
        fss.reinstate(self.sub, actor=self.root, reason="finance approved goodwill")      # a double click is harmless
        self.assertEqual(len(self.events(ET.RESUMED)), 1)

    def test_a_non_financial_suspension_cannot_be_lifted_through_this_path(self):
        fss.reinstate(self.sub, actor=self.root, reason="restore first")
        sub_svc.suspend_subscription(self.sub, reason="پایانِ Dunning")
        self.sub.refresh_from_db()
        with self.assertRaises(fss.FinancialSuspensionError):
            fss.reinstate(self.sub, actor=self.root, reason="should not work")

    def root_client(self):
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(self.root)
        return client

    def test_platform_view_reinstates_for_a_superuser_and_refuses_a_plain_staff_user(self):
        url = f"/stores/{self.store.public_id}/reinstate-financial-suspension/"
        staff = User.objects.create_user(username="p2fs-staff2", password="x", is_staff=True)
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(staff)
        client.post(url, {"reason": "attempt by staff"})
        self.assertEqual(self.refresh(), S.SUSPENDED)
        self.root_client().post(url, {"reason": "approved by the owner of the platform"})
        self.assertEqual(self.refresh(), S.ACTIVE)

    def test_the_generic_resume_and_extend_actions_refuse_a_financial_suspension(self):
        client = self.root_client()
        client.post(f"/subscriptions/{self.sub.pk}/resume/")
        self.assertEqual(self.refresh(), S.SUSPENDED)
        client.post(f"/stores/{self.store.public_id}/extend-subscription/", {"days": "30"})
        self.assertEqual(self.refresh(), S.SUSPENDED)

    def test_the_store_page_shows_the_financial_suspension_and_its_control(self):
        response = self.root_client().get(f"/stores/{self.store.public_id}/?tab=subscription")
        self.assertContains(response, "dlg-reinstate-fin")
        self.assertContains(response, "تعلیقِ مالی")


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrency")
class PostgresConcurrentFinancialSuspensionTests(TransactionTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.store = Store.objects.create(name="ف", slug="p2fspg", admin_subdomain="p2fspg")
        self.version = make_version("p2fspg")
        self.sub = sub_svc.create_subscription(self.store, self.version)
        sub_svc.activate_subscription(self.sub, period_end=self.now - timedelta(days=30))
        self.sub.refresh_from_db()
        self.current = pay(renewal(self.sub, self.now - timedelta(days=30), self.now + timedelta(days=30)))
        self.future = pay(renewal(self.sub, self.now + timedelta(days=30), self.now + timedelta(days=60)))

    def parallel(self, n, fn):
        barrier = threading.Barrier(n)

        def worker(i):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                return fn(i)
            except Exception as exc:  # noqa: BLE001
                return type(exc).__name__
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=n) as pool:
            return list(pool.map(worker, range(n)))

    def test_6_concurrent_revocations_suspend_once_and_6_concurrent_restorations_restore_once(self):
        with patched(paying_provider()):
            refund = refund_service.request_refund(
                SubscriptionInvoice.objects.get(pk=self.current.pk), amount=self.current.amount_paid, idempotency_key="pg-fs")
        sub = StoreSubscription.objects.get(pk=self.sub.pk)
        self.assertEqual(sub.status, S.SUSPENDED)
        inv = SubscriptionInvoice.objects.get(pk=self.current.pk)
        out = Counter(self.parallel(6, lambda _i: fss.apply_refund(SubscriptionInvoice.objects.get(pk=inv.pk), refund)))
        self.assertEqual(set(out), {fss.ALREADY}, out)
        self.assertEqual(sub.events.filter(event_type=ET.SUSPENDED).count(), 1)
        later = self.now + timedelta(days=31)
        results = self.parallel(6, lambda _i: fss.evaluate_restorations(now=later)["restored"])
        self.assertEqual(sum(r for r in results if isinstance(r, int)), 1, results)
        sub.refresh_from_db()
        self.assertEqual(sub.status, S.ACTIVE)
        self.assertEqual(sub.events.filter(event_type=ET.RESUMED).count(), 1)
