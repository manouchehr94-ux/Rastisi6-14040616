"""Phase 2, Priority 1 + F-05: a confirmed payment is never lost, never grants unearned entitlements, and batch jobs never halt.

Covers F-02 (terminal subscription), F-05 (late VOID / UNCOLLECTIBLE / stale plan-change payments), F-01 (browser failure hint must not
strand a payment) and F-04 (a failing row must not stop financial jobs, and the failure must stay visible).
Real HTTP, real provisioning and the in-process fake gateway; synthetic data only; no real provider is ever contacted."""

import io
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import PlatformCouponRedemption as Redemption, SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import confirmation_service as cs, duplicate_payment_service as dups, invoice_service
from apps.billing.tests.test_platform_coupon_financial_acceptance import Base
from apps.billing.tests.test_trial_purchase_flow import make_owner
from apps.core.models import AuditLogEntry
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent, subscription_service as ss

A = SubscriptionPaymentAttempt.Status


class PayBase(Base):
    def open_pro_invoice(self, store=None, client=None):
        c = client or self.client
        t = c.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly"}).context["preview"]["token"]
        c.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.pro.pk, "preview_token": t, "billing_interval": "monthly"})
        return SubscriptionInvoice.objects.filter(store=store or self.store, kind="plan_change").latest("pk")

    def gateway_confirms(self, attempt, invoice):
        self.fake.paid(amount_rial=int(invoice.amount_due) * 10, order_id=attempt.public_token)

    def sub(self, store=None):
        return StoreSubscription.objects.get(store=store or self.store, is_current=True)

    def plan_code(self, store=None):
        return StoreSubscription.objects.filter(store=store or self.store).latest("pk").plan_version.plan.code


class TerminalSubscriptionPaymentTests(PayBase):
    """F-02: money confirmed by the gateway for a cancelled/expired subscription is recorded and flagged, not lost."""

    def _cancel_during_payment(self):
        inv = self.open_pro_invoice()
        attempt = self.pay_online(inv)
        ss.cancel_immediately(self.sub(), reason="owner closed the store")        # invoice stays payable on purpose (worst case)
        self.gateway_confirms(attempt, inv)
        return inv, attempt

    def test_browser_return_parks_the_payment_instead_of_leaving_it_pending(self):
        inv, attempt = self._cancel_during_payment()
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        attempt.refresh_from_db(); inv.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (A.REQUIRES_ACTION, "fulfilment_blocked"))
        self.assertTrue(attempt.provider_payment_id or attempt.completed_at)
        self.assertEqual(inv.status, SubscriptionInvoice.Status.PAYMENT_PENDING)        # no entitlement-bearing state change
        self.assertEqual(inv.amount_paid, Decimal(0))
        self.assertEqual(self.plan_code(), "trial")                                      # nothing was granted
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 0)

    def test_the_parked_payment_is_audited_once_and_listed_for_finance(self):
        inv, attempt = self._cancel_during_payment()
        for _ in range(3):                                                               # repeated browser returns / re-verification
            self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_parked", object_id=str(attempt.pk)).count(), 1)
        attempt.refresh_from_db()
        self.assertTrue(dups.is_duplicate(attempt))                                     # same finance resolution flow as duplicates
        from apps.portal.platform_admin_views import reconciliation_snapshot
        queued = [a.pk for a in reconciliation_snapshot()["requires_action"][0]]
        self.assertIn(attempt.pk, queued)

    def test_finance_can_refund_or_record_an_allocation_for_the_parked_payment(self):
        inv, attempt = self._cancel_during_payment()
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        finance = self.finance
        done = dups.mark_resolved("subscription", attempt.pk, actor=finance, outcome="credited", reference="BANK-REF-123456", note="allocated")
        self.assertTrue(dups.is_resolved(done))

    def test_reconciler_continues_past_the_unfulfillable_payment_and_records_it(self):
        inv, attempt = self._cancel_during_payment()
        owner_b, store_b = make_owner("p2-b@example.com", "فروشگاه ب")
        client_b = self.client_for(store_b, owner_b)
        inv_b = self.open_pro_invoice(store_b, client_b)
        self.fake.track_id += 1
        attempt_b = self.pay_online(inv_b, client_b)
        old = timezone.now() - timedelta(minutes=30)
        SubscriptionPaymentAttempt.objects.filter(pk__in=[attempt.pk, attempt_b.pk]).update(created_at=old)
        self.fake.paid(amount_rial=int(inv_b.amount_due) * 10, order_id=attempt_b.public_token)   # gateway reports B (and A by shared fake)
        out = io.StringIO()
        call_command("reconcile_platform_payments", "--min-age-minutes", "1", stdout=out)
        attempt.refresh_from_db(); attempt_b.refresh_from_db()
        self.assertEqual(attempt.status, A.REQUIRES_ACTION)
        self.assertEqual(attempt_b.status, A.SUCCEEDED)                                  # the later, normal payment was NOT held back

    def test_a_normal_payment_is_unaffected(self):
        inv = self.open_pro_invoice()
        self.settle_online(inv)
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(1_000_000)))
        self.assertEqual(self.plan_code(), "buy-pro")

    def test_manual_mark_paid_refuses_instead_of_reporting_a_false_success(self):
        inv = self.open_pro_invoice()
        ss.cancel_immediately(self.sub(), reason="closed")
        with self.assertRaises(cs.ConfirmationError):
            cs.mark_invoice_paid_manually(inv, actor=self.finance, note="bank ref")
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.OPEN)                    # rolled back: nothing half-recorded
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=inv, provider="manual").exists())


class LateAndStalePaymentTests(PayBase):
    """F-05: confirmed money on a VOID / UNCOLLECTIBLE invoice or a stale plan-change decision is recorded and never entitles."""

    def _pending(self):
        inv = self.open_pro_invoice()
        return inv, self.pay_online(inv)

    def _confirm(self, inv, attempt):
        return cs.confirm_payment(attempt=attempt, amount=inv.amount_due, currency=inv.currency, provider_payment_id="gw-late-1")

    def _assert_parked(self, inv, attempt, code):
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (A.REQUIRES_ACTION, code))
        self.assertEqual(attempt.provider_payment_id, "gw-late-1")                       # the gateway's reference is kept for finance
        self.assertEqual(self.plan_code(), "trial")
        self.assertEqual(self.sub().status, StoreSubscription.Status.TRIALING)
        self.assertEqual(Redemption.objects.filter(invoice=inv, status=Redemption.Status.REDEEMED).count(), 0)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_parked", object_id=str(attempt.pk)).count(), 1)

    def test_void_invoice_late_payment_is_recorded_not_entitled(self):
        inv, attempt = self._pending()
        invoice_service.void_invoice(inv, reason="merchant cancelled")
        self._confirm(inv, attempt)
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.VOID)                    # the invoice is NOT silently turned into paid
        self.assertEqual(inv.amount_paid, Decimal(0))
        self._assert_parked(inv, attempt, "late_payment_void")

    def test_uncollectible_invoice_late_payment_is_recorded_not_entitled(self):
        inv, attempt = self._pending()
        SubscriptionInvoice.objects.filter(pk=inv.pk).update(status=SubscriptionInvoice.Status.UNCOLLECTIBLE)
        self._confirm(inv, attempt)
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.UNCOLLECTIBLE)
        self._assert_parked(inv, attempt, "late_payment_uncollectible")

    def test_repeated_confirmation_of_a_parked_payment_is_idempotent(self):
        inv, attempt = self._pending()
        invoice_service.void_invoice(inv, reason="x")
        for _ in range(3):
            self._confirm(inv, attempt)
        self._assert_parked(inv, attempt, "late_payment_void")

    def test_stale_plan_change_decision_is_parked(self):
        inv, attempt = self._pending()
        sub = self.sub()
        ss.change_plan_version(sub, self.lite, reason="admin override after the invoice was created")
        self._confirm(inv, attempt)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (A.REQUIRES_ACTION, "stale_decision"))
        self.assertEqual(self.plan_code(), "buy-lite")                                   # the admin's newer decision is NOT overwritten
        inv.refresh_from_db()
        self.assertNotEqual(inv.status, SubscriptionInvoice.Status.PAID)

    def test_a_status_only_change_does_not_make_the_decision_stale(self):
        """Trial expiry (status change, no plan change) while the customer is paying must still be honoured."""
        inv, attempt = self._pending()
        StoreSubscription.objects.filter(pk=self.sub().pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()
        self.assertEqual(self.sub().status, StoreSubscription.Status.SUSPENDED)
        self._confirm(inv, attempt)
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(self.plan_code(), "buy-pro")
        self.assertEqual(self.sub().status, StoreSubscription.Status.ACTIVE)

    def test_a_valid_open_invoice_is_still_applied_exactly_once(self):
        inv, attempt = self._pending()
        self._confirm(inv, attempt)
        self._confirm(inv, attempt)
        inv.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(1_000_000)))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 1)


class BrowserHintMustNotStrandPaymentsTests(PayBase):
    """F-01: a `success=0` hint (anyone holding the callback URL can send it) must never permanently strand a payment."""

    def _declined_then_settled(self):
        inv = self.open_pro_invoice()
        attempt = self.pay_online(inv)
        self.callback(attempt, "success=0&status=3&trackId=%d" % self.fake.track_id)      # hint while the gateway is still unpaid
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (A.FAILED, "gateway_declined"))
        self.gateway_confirms(attempt, inv)                                               # the bank settles afterwards
        return inv, attempt

    def test_public_return_recovers_the_payment(self):
        inv, attempt = self._declined_then_settled()
        self.callback(attempt, "success=1&status=2&trackId=%d" % self.fake.track_id)
        attempt.refresh_from_db(); inv.refresh_from_db()
        self.assertEqual(attempt.status, A.SUCCEEDED)
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(1_000_000)))
        self.assertEqual(attempt.failure_code, "")                                        # stale failure text is cleared
        self.assertEqual(self.plan_code(), "buy-pro")

    def test_reconciler_recovers_the_payment(self):
        inv, attempt = self._declined_then_settled()
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        call_command("reconcile_platform_payments", "--min-age-minutes", "1", stdout=io.StringIO())
        attempt.refresh_from_db(); inv.refresh_from_db()
        self.assertEqual((attempt.status, inv.status), (A.SUCCEEDED, "paid"))

    def test_checkout_status_button_recovers_the_payment(self):
        inv, attempt = self._declined_then_settled()
        from django.core.cache import cache
        cache.clear()                                      # the 8 s per-attempt verify throttle (set by the hint callback) is time-based
        self.client.post(reverse("dashboard:platform-checkout-status", args=["subscription", inv.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, A.SUCCEEDED)

    def test_the_hint_alone_never_grants_anything(self):
        inv = self.open_pro_invoice()
        attempt = self.pay_online(inv)
        for query in ("success=1&status=2&trackId=1", "success=1", "status=100", "paid=1"):
            self.callback(attempt, query)                                                 # the gateway has NOT confirmed
        attempt.refresh_from_db(); inv.refresh_from_db()
        self.assertNotEqual(attempt.status, A.SUCCEEDED)
        self.assertEqual((inv.amount_paid, self.plan_code()), (Decimal(0), "trial"))

    def test_a_provider_decided_failure_stays_final_and_is_not_rechecked(self):
        from apps.billing.services import payment_flow_service as pfs
        inv = self.open_pro_invoice()
        attempt = self.pay_online(inv)
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(status=A.FAILED, failure_code="provider_terminal_failure")
        attempt.refresh_from_db()
        self.assertFalse(pfs.needs_verification(attempt))

    def test_a_cache_fault_on_the_return_page_does_not_produce_a_500(self):
        inv = self.open_pro_invoice()
        attempt = self.pay_online(inv)
        with mock.patch("apps.billing.views.cache.add", side_effect=RuntimeError("redis down")):
            response = self.client.get(f"/billing/return/{attempt.public_token}/?success=1")
        self.assertIn(response.status_code, (200, 302))

    def test_duplicate_payment_after_a_hint_failure_never_double_credits(self):
        inv, attempt_a = self._declined_then_settled()
        attempt_b = self.pay_online(inv)                                                  # merchant retries
        self.fake.paid(amount_rial=int(inv.amount_due) * 10, order_id=attempt_b.public_token)
        self.callback(attempt_b, "success=1&status=2&trackId=%d" % self.fake.track_id)
        self.fake.paid(amount_rial=int(inv.amount_due) * 10, order_id=attempt_a.public_token)
        self.callback(attempt_a, "success=1&status=2&trackId=%d" % self.fake.track_id)
        inv.refresh_from_db(); attempt_a.refresh_from_db()
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(1_000_000)))
        self.assertEqual((attempt_a.status, attempt_a.failure_code), (A.REQUIRES_ACTION, "duplicate_payment"))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 1)


class BatchJobIsolationTests(PayBase):
    """F-04: one failing row must not stop the others, and the failure must stay visible (logged, counted, non-zero exit)."""

    def test_state_evaluator_isolates_a_failing_subscription_and_reports_it(self):
        owner_b, store_b = make_owner("p2-iso-b@example.com", "فروشگاه ب")
        for st in (self.store, store_b):
            StoreSubscription.objects.filter(store=st).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        real = ss._apply_due_action
        calls = []

        def flaky(sub, action, *, actor=None):
            calls.append(sub.store_id)
            if sub.store_id == self.store.pk:
                raise RuntimeError("poison row")
            return real(sub, action, actor=actor)

        with mock.patch.object(ss, "_apply_due_action", flaky):
            result = ss.evaluate_subscription_states()
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.sub(store_b).status, StoreSubscription.Status.SUSPENDED)   # the other store WAS processed
        self.assertEqual(self.sub().status, StoreSubscription.Status.TRIALING)           # the failing one was rolled back, unchanged
        with mock.patch.object(ss, "_apply_due_action", flaky):
            with self.assertRaises(CommandError):
                call_command("evaluate_subscription_states", stdout=io.StringIO())

    def test_renewals_isolate_a_failing_subscription(self):
        from apps.billing.services import renewal_service as rs
        owners = [make_owner(f"p2-ren-{i}@example.com", f"تمدید {i}") for i in range(2)]
        subs = []
        for owner, store in owners:
            c = self.client_for(store, owner)
            inv = self.open_pro_invoice(store, c)
            cs.confirm_payment(attempt=__import__("apps.billing.services.attempt_service", fromlist=["x"]).create_attempt(inv, provider="manual"),
                               amount=inv.amount_due, currency=inv.currency, provider_payment_id=f"r{store.pk}")
            sub = StoreSubscription.objects.get(store=store, is_current=True)
            StoreSubscription.objects.filter(pk=sub.pk).update(current_period_end=timezone.now() + timedelta(days=1))
            subs.append(sub)
        real = rs._generate_one

        def flaky(subscription, *, now):
            if subscription.pk == subs[0].pk:
                raise RuntimeError("poison row")
            return real(subscription, now=now)

        with mock.patch.object(rs, "_generate_one", flaky):
            result = rs.generate_renewals()
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["created"], 1)                                            # the healthy subscription still got its invoice
        with mock.patch.object(rs, "_generate_one", flaky):
            with self.assertRaises(CommandError):
                call_command("generate_subscription_renewals", stdout=io.StringIO())

    def test_dunning_isolates_a_failing_invoice(self):
        from apps.billing.services import dunning_service as ds
        owner_b, store_b = make_owner("p2-dun-b@example.com", "دانینگ")
        invs = [self.open_pro_invoice(), self.open_pro_invoice(store_b, self.client_for(store_b, owner_b))]
        SubscriptionInvoice.objects.filter(pk__in=[i.pk for i in invs]).update(due_at=timezone.now() - timedelta(days=1))
        real = ds._process_invoice

        def flaky(invoice, *, schedule, now):
            if invoice.pk == invs[0].pk:
                raise RuntimeError("poison row")
            return real(invoice, schedule=schedule, now=now)

        with mock.patch.object(ds, "_process_invoice", flaky):
            result = ds.process_dunning()
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["scanned"], 2)
        self.assertGreaterEqual(result["advanced"] + result["waiting"] + result["suspended"], 1)   # the healthy invoice was handled

    def test_reconciler_survives_an_unexpected_exception_and_fails_the_run(self):
        inv_a = self.open_pro_invoice()
        attempt_a = self.pay_online(inv_a)
        owner_b, store_b = make_owner("p2-rec-b@example.com", "ب")
        client_b = self.client_for(store_b, owner_b)
        inv_b = self.open_pro_invoice(store_b, client_b)
        self.fake.track_id += 1
        attempt_b = self.pay_online(inv_b, client_b)
        SubscriptionPaymentAttempt.objects.filter(pk__in=[attempt_a.pk, attempt_b.pk]).update(created_at=timezone.now() - timedelta(minutes=30))
        self.fake.paid(amount_rial=int(inv_b.amount_due) * 10, order_id=attempt_b.public_token)
        from apps.billing.services import payment_flow_service as pfs
        real = pfs.confirm_from_provider_verification

        def flaky(attempt, **kw):
            if attempt.pk == attempt_a.pk:
                raise RuntimeError("unexpected")
            return real(attempt, **kw)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(pfs, "confirm_from_provider_verification", flaky):
            with self.assertRaises(CommandError):
                call_command("reconcile_platform_payments", "--min-age-minutes", "1", stdout=out, stderr=err)
        self.assertIn("unexpected_errors=1", out.getvalue())
        attempt_b.refresh_from_db()
        self.assertEqual(attempt_b.status, A.SUCCEEDED)                                  # the other row WAS processed
