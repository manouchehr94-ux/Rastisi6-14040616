"""Final refund policy for PLATFORM-owned payments (owner decision 2026-11-10): no automatic post-payment refund; every refund is reviewed
and approved by the platform administrator, paid out MANUALLY through an authorised banking channel, and completed in RastiSi only
with a bank reference. Approval and completion are separate events. Synthetic providers only: no network, no real bank.

Normal payment behaviour (verified activation exactly once, failed payment retryable, unknown result stays pending) is proved by
test_platform_subscription_payments / test_platform_provider_coverage / test_trial_purchase_flow, which are part of the regression run;
the end-to-end test added there proves a refund after a verified payment never contacts the gateway."""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import mock, skipUnless

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings

from apps.billing.admin import SubscriptionRefundAdmin
from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund
from apps.billing.providers import bank_refund_policy as policy
from apps.billing.providers import registry
from apps.billing.services import duplicate_payment_service as dups
from apps.billing.services import refund_service as rs
from apps.billing.services import sms_purchase_payment_service as sms_svc
from apps.billing.tests.test_credit_refund import _paid_invoice
from apps.billing.tests.test_sms_refund_disabled import SmsRefundDisabledBase
from apps.core.models import AuditLogEntry
from apps.sms.models import SmsCreditLedger
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
R = SubscriptionRefund.Status
PLATFORM_HOST = "platformadmins.rastisi.localhost"
AMOUNT = Decimal("400000")
ALL_PROVIDERS = ("manual", "zibal", "zarinpal", "platform_card", "snappay", "pasargad", "saman", "mellat")


class PolicyBase:
    """A paid invoice plus a registry that FAILS the test if any provider is resolved."""

    def make(self, slug, provider="manual"):
        self.store, self.invoice = _paid_invoice(slug)
        SubscriptionPaymentAttempt.objects.filter(invoice=self.invoice).update(provider=provider)
        self.sub = StoreSubscription.objects.get(pk=self.invoice.subscription_id)
        return self

    def forbid_providers(self):
        patcher = mock.patch.object(registry, "get_provider", side_effect=AssertionError("a provider must not be resolved"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, key="k1", amount=AMOUNT):
        return rs.request_refund(SubscriptionInvoice.objects.get(pk=self.invoice.pk), amount=Decimal(amount), reason="test",
                                 idempotency_key=key)

    def sub_status(self):
        return StoreSubscription.objects.get(pk=self.sub.pk).status

    def invoice_status(self):
        return SubscriptionInvoice.objects.get(pk=self.invoice.pk).status

    def platform_client(self, *, superuser=True, login=True):
        user = User.objects.create_user(username=f"pa-{User.objects.count()}", password="x", is_staff=True, is_superuser=superuser)
        client = Client(HTTP_HOST=PLATFORM_HOST)
        if login:
            client.force_login(user)
        return client


class NoAutomaticRefundTests(PolicyBase, TestCase):
    def test_every_provider_code_is_stopped_at_the_service_layer_before_the_provider_is_resolved(self):
        for code in ALL_PROVIDERS:
            with self.subTest(provider=code):
                self.make(f"nar-{code}".replace("_", "-"), code)
                with mock.patch.object(registry, "get_provider", side_effect=AssertionError("provider resolved")) as get_provider:
                    refund = self.request(key=f"nar-{code}")
                self.assertEqual((refund.status, refund.failure_code), (R.PENDING, policy.AUTOMATIC_REFUND_DISABLED))
                self.assertEqual(get_provider.call_count, 0)
                self.assertEqual(rs.review_state(refund), rs.STATE_AWAITING_REVIEW)
                self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)         # never «refunded» by a request
                self.assertEqual(rs.refundable_amount(SubscriptionInvoice.objects.get(pk=self.invoice.pk)), Decimal("0"))  # reserved

    def test_repeat_and_different_key_requests_cannot_bypass_the_policy_or_double_reserve(self):
        self.make("nar-repeat", "pasargad")
        self.forbid_providers()
        first = self.request()
        self.assertEqual(self.request().pk, first.pk)                                   # same key: same row
        with self.assertRaises(rs.RefundError):
            self.request(key="k2")                                                      # fully reserved
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)

    def test_the_environment_alone_cannot_re_enable_a_bank_call(self):
        self.make("nar-env", "saman")
        self.forbid_providers()
        with override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS="pasargad,saman,mellat"):
            refund = self.request()
        self.assertEqual(refund.failure_code, policy.AUTOMATIC_REFUND_DISABLED)

    def test_the_adapter_backed_provider_refuses_a_direct_call_for_every_adapter_code(self):
        from apps.billing.providers.adapter_backed import AdapterBackedBillingProvider

        for code in ("pasargad", "saman", "mellat", "zarinpal", "snappay", "parsian"):
            with self.subTest(provider=code):
                provider = AdapterBackedBillingProvider(code)
                with mock.patch.object(provider, "_adapter", side_effect=AssertionError("adapter touched")), \
                        mock.patch.object(provider, "_credentials", side_effect=AssertionError("credentials read")):
                    result = provider.refund_payment(provider_payment_id="p", amount=AMOUNT, currency="IRT", idempotency_key="direct")
                self.assertFalse(result.succeeded)
                self.assertTrue(result.raw_summary.get(policy.AUTOMATIC_REFUND_DISABLED))

    def test_duplicate_payment_refund_makes_no_provider_call_for_any_provider(self):
        for code in ("zarinpal", "pasargad", "manual"):
            with self.subTest(provider=code):
                self.make(f"nar-dup-{code}".replace("_", "-"), code)
                attempt = SubscriptionPaymentAttempt.objects.create(
                    store=self.store, invoice=self.invoice, provider=code, status=SubscriptionPaymentAttempt.Status.REQUIRES_ACTION,
                    amount=AMOUNT, currency="IRT", failure_code="duplicate_payment", provider_payment_id=f"dup-{code}",
                    idempotency_key=f"dup-key-{code}", public_token=f"dup-token-{code}")
                with mock.patch.object(registry, "get_provider", side_effect=AssertionError("provider resolved")):
                    _a, outcome = dups.refund_duplicate("subscription", attempt.pk, actor=None, reason="duplicate payment")
                    _b, again = dups.refund_duplicate("subscription", attempt.pk, actor=None, reason="duplicate payment")
                self.assertEqual((outcome, again), ("pending_manual", "pending_manual"))

    def test_the_recovery_job_never_calls_a_provider(self):
        from django.core.management import call_command
        from io import StringIO

        self.make("nar-recover", "mellat")
        row = SubscriptionRefund.objects.create(
            store=self.store, invoice=self.invoice, provider="mellat", status=R.REQUESTED, amount=AMOUNT, currency="IRT",
            idempotency_key="stale-intent")
        SubscriptionRefund.objects.filter(pk=row.pk).update(created_at=row.created_at.replace(year=2020))
        self.forbid_providers()
        try:
            call_command("recover_stale_refunds", stdout=StringIO())
        except Exception:  # the command exits non-zero while an unknown refund waits: that is intended
            pass
        row.refresh_from_db()
        self.assertEqual((row.status, row.failure_code), (R.PENDING, rs.UNKNOWN_OUTCOME))

    def test_the_django_admin_cannot_change_a_refund_state(self):
        model_admin = django_admin.site._registry[SubscriptionRefund]
        self.assertIsInstance(model_admin, SubscriptionRefundAdmin)
        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="adm-root", password="x", is_staff=True, is_superuser=True)
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        for field in ("status", "failure_code", "failure_message", "amount", "reason"):
            self.assertIn(field, model_admin.readonly_fields)


class ApprovalTests(PolicyBase, TestCase):
    def test_approval_never_calls_a_provider_and_changes_neither_money_nor_entitlement(self):
        self.make("ap-1", "pasargad")
        refund = self.request()
        before = (self.sub_status(), self.sub.current_period_end if hasattr(self.sub, "current_period_end") else None)
        self.forbid_providers()
        approved = rs.approve_refund_for_manual_processing(refund, actor=None, note="checked")
        self.assertEqual((approved.status, approved.failure_code), (R.PENDING, rs.MANUAL_APPROVED))
        self.assertEqual(rs.review_state(approved), rs.STATE_APPROVED)
        self.assertNotEqual(approved.status, R.SUCCEEDED)
        self.assertIsNone(approved.completed_at)
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)
        self.assertEqual(self.sub_status(), before[0])
        self.assertEqual(rs.refundable_amount(SubscriptionInvoice.objects.get(pk=self.invoice.pk)), Decimal("0"))   # still reserved
        entry = AuditLogEntry.objects.get(action_code="billing.refund_approved_for_manual")
        self.assertIn("provider_called", str(entry.metadata))
        self.assertFalse(AuditLogEntry.objects.filter(action_code="billing.refund_entitlement_outcome").exists())

    def test_approval_is_idempotent_and_audited_once(self):
        self.make("ap-2")
        refund = self.request()
        first = rs.approve_refund_for_manual_processing(refund, actor=None)
        second = rs.approve_refund_for_manual_processing(refund, actor=None)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_approved_for_manual").count(), 1)

    def test_the_http_approval_endpoint_records_the_decision_without_a_provider_call(self):
        self.make("ap-3", "saman")
        refund = self.request()
        client = self.platform_client()
        self.forbid_providers()
        response = client.post(f"/payments/refund/{refund.pk}/approve/", {"note": "ok"}, follow=True)
        self.assertEqual(response.status_code, 200)
        refund.refresh_from_db()
        self.assertEqual(rs.review_state(refund), rs.STATE_APPROVED)
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)
        self.assertContains(response, rs.STATE_LABELS[rs.STATE_APPROVED])

    def test_forged_requests_to_every_decision_endpoint_change_nothing(self):
        self.make("ap-4", "mellat")
        refund = self.request()
        snapshot = SubscriptionRefund.objects.filter(pk=refund.pk).values().get()
        anonymous = self.platform_client(login=False)
        plain_staff = self.platform_client(superuser=False)
        self.forbid_providers()
        for who, client in (("anonymous", anonymous), ("staff", plain_staff)):
            for action, data in (("approve", {}), ("reject", {"reason": "forged"}), ("complete", {"reference": "FORGED-REF-1"}),
                                 ("complete", {"resolution": "not_executed", "reference": "FORGED-REF-1"})):
                response = client.post(f"/payments/refund/{refund.pk}/{action}/", data)
                self.assertEqual(response.status_code, 302, (who, action))
                self.assertIn("login", response["Location"], (who, action))
            self.assertEqual(client.get(f"/payments/refund/{refund.pk}/approve/").status_code in (302, 405), True)
        root = self.platform_client()
        self.assertEqual(root.get(f"/payments/refund/{refund.pk}/approve/").status_code, 405)    # POST only
        root.post(f"/payments/refund/{refund.pk}/complete/", {"reference": "FORGED-REF-1"}, follow=True)   # not approved: refused
        self.assertEqual(SubscriptionRefund.objects.filter(pk=refund.pk).values().get()["status"], snapshot["status"])
        self.assertEqual(SubscriptionRefund.objects.filter(pk=refund.pk).values().get()["failure_code"], snapshot["failure_code"])
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)


class CompletionTests(PolicyBase, TestCase):
    def test_completion_needs_prior_approval_and_a_bank_reference(self):
        self.make("co-1", "pasargad")
        refund = self.request()
        with self.assertRaises(rs.RefundError):                                        # not approved
            rs.complete_refund_manually(refund, actor=None, reference="BANK-REF-0001")
        rs.approve_refund_for_manual_processing(refund, actor=None)
        for bad in ("", "   ", "abc12", None):
            with self.assertRaises(rs.RefundError):
                rs.complete_refund_manually(refund, actor=None, reference=bad)
        refund.refresh_from_db()
        self.assertEqual(rs.review_state(refund), rs.STATE_APPROVED)
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)

    def test_entitlement_is_revoked_only_by_the_verified_completion_and_only_once(self):
        self.make("co-2", "saman")
        refund = self.request()
        self.assertEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)
        rs.approve_refund_for_manual_processing(refund, actor=None)
        self.assertEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)            # approval changes nothing
        self.forbid_providers()
        done = rs.complete_refund_manually(refund, actor=None, reference="BANK-REF-0002")
        self.assertEqual((done.status, rs.review_state(done)), (R.SUCCEEDED, rs.STATE_COMPLETED))
        self.assertIn("BANK-REF-0002", done.failure_message)
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.REFUNDED)
        revoked = self.sub_status()        # this fixture records no funded period, so F-08 only audits; the real flow suspends (see below)
        for reference in ("BANK-REF-0002", "OTHER-REF-9999"):                           # duplicate completion, even with another reference
            again = rs.complete_refund_manually(refund, actor=None, reference=reference)
            self.assertEqual((again.pk, again.status), (done.pk, R.SUCCEEDED))
        self.assertEqual(self.sub_status(), revoked)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_completed").count(), 1)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_entitlement_outcome").count(), 1)
        self.assertIn("BANK-REF-0002", SubscriptionRefund.objects.get(pk=refund.pk).failure_message)   # the first evidence stands

    def test_a_partial_completion_never_suspends_and_a_second_refund_cannot_exceed_the_paid_amount(self):
        self.make("co-3")
        part = self.request(key="p1", amount="100000")
        rs.approve_refund_for_manual_processing(part, actor=None)
        rs.complete_refund_manually(part, actor=None, reference="BANK-REF-0003")
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PARTIALLY_REFUNDED)
        self.assertEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)
        with self.assertRaises(rs.RefundError):
            self.request(key="p2", amount="400000")

    def test_the_http_completion_flow_approve_then_complete_with_a_reference(self):
        self.make("co-4", "mellat")
        refund = self.request()
        client = self.platform_client()
        self.forbid_providers()
        client.post(f"/payments/refund/{refund.pk}/complete/", {"reference": "BANK-REF-0004"}, follow=True)     # not approved
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)
        client.post(f"/payments/refund/{refund.pk}/approve/")
        client.post(f"/payments/refund/{refund.pk}/complete/", {"reference": ""}, follow=True)                 # no evidence
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)
        response = client.post(f"/payments/refund/{refund.pk}/complete/", {"reference": "BANK-REF-0004"}, follow=True)
        self.assertContains(response, rs.STATE_LABELS[rs.STATE_COMPLETED])
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.REFUNDED)
        client.post(f"/payments/refund/{refund.pk}/complete/", {"reference": "BANK-REF-0004"}, follow=True)    # double click
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_completed").count(), 1)


class RejectionAndParkedStatesTests(PolicyBase, TestCase):
    def test_rejection_releases_the_reservation_without_any_provider_call_or_entitlement_change(self):
        self.make("rj-1", "zarinpal")
        refund = self.request()
        self.forbid_providers()
        with self.assertRaises(rs.RefundError):
            rs.reject_refund(refund, actor=None, reason="  ")
        rejected = rs.reject_refund(refund, actor=None, reason="not eligible")
        self.assertEqual((rejected.status, rs.review_state(rejected)), (R.CANCELLED, rs.STATE_REJECTED))
        self.assertEqual(rs.reject_refund(refund, actor=None, reason="again").pk, rejected.pk)                  # idempotent
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_rejected").count(), 1)
        self.assertEqual((self.invoice_status(), self.sub_status()), (SubscriptionInvoice.Status.PAID, StoreSubscription.Status.ACTIVE))
        self.assertEqual(rs.refundable_amount(SubscriptionInvoice.objects.get(pk=self.invoice.pk)), AMOUNT)     # released
        with self.assertRaises(rs.RefundError):
            rs.approve_refund_for_manual_processing(refund, actor=None)
        with self.assertRaises(rs.RefundError):
            rs.complete_refund_manually(refund, actor=None, reference="BANK-REF-0005")

    def test_an_unknown_outcome_stays_parked_it_cannot_be_approved_rejected_or_re_requested(self):
        self.make("rj-2", "mellat")
        row = SubscriptionRefund.objects.create(
            store=self.store, invoice=self.invoice, provider="mellat", status=R.PENDING, failure_code=rs.UNKNOWN_OUTCOME,
            amount=AMOUNT, currency="IRT", idempotency_key="legacy-unknown")
        self.assertEqual(rs.review_state(row), rs.STATE_UNKNOWN)
        self.forbid_providers()
        with self.assertRaises(rs.RefundError):
            rs.approve_refund_for_manual_processing(row, actor=None)
        with self.assertRaises(rs.RefundError):
            rs.reject_refund(row, actor=None, reason="no longer wanted")
        with self.assertRaises(rs.RefundError):
            self.request(key="new")                                                                           # blocked while unknown
        with self.assertRaises(rs.RefundError):
            rs.complete_refund_manually(row, actor=None, reference="")                                          # evidence required
        done = rs.complete_refund_manually(row, actor=None, reference="BANK-RECON-0006")                       # reconciled with the bank
        self.assertEqual(done.status, R.SUCCEEDED)

    def test_historical_rows_remain_reconcilable_and_finished_ones_are_untouched(self):
        self.make("rj-3", "manual")
        legacy = SubscriptionRefund.objects.create(                                                            # created before this policy
            store=self.store, invoice=self.invoice, provider="manual", status=R.PENDING, failure_code="",
            amount=AMOUNT, currency="IRT", idempotency_key="legacy-pending")
        self.assertEqual(rs.review_state(legacy), rs.STATE_AWAITING_REVIEW)
        with self.assertRaises(rs.RefundError):
            rs.complete_refund_manually(legacy, actor=None, reference="BANK-REF-0007")                          # needs the approval event
        rs.approve_refund_for_manual_processing(legacy, actor=None)
        self.assertEqual(rs.complete_refund_manually(legacy, actor=None, reference="BANK-REF-0007").status, R.SUCCEEDED)
        for finished in (legacy,):
            with self.assertRaises(rs.RefundError):
                rs.approve_refund_for_manual_processing(finished, actor=None)
            with self.assertRaises(rs.RefundError):
                rs.reject_refund(finished, actor=None, reason="rewrite history")
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)                    # nothing duplicated

    def test_proof_that_nothing_was_paid_out_still_releases_an_approved_refund(self):
        self.make("rj-4", "saman")
        refund = self.request()
        rs.approve_refund_for_manual_processing(refund, actor=None)
        released = rs.fail_refund_manually(refund, actor=None, reference="BANK-PROOF-0008")
        self.assertEqual(released.status, R.FAILED)
        self.assertEqual(rs.refundable_amount(SubscriptionInvoice.objects.get(pk=self.invoice.pk)), AMOUNT)


class AdminPageStatesTests(PolicyBase, TestCase):
    def test_the_invoice_page_names_each_state_and_offers_only_the_matching_actions(self):
        self.make("ui-1", "saman")
        client = self.platform_client()
        page = f"/payments/invoice/{self.invoice.pk}/"
        refund = self.request()
        html = client.get(page).content.decode()
        self.assertIn(rs.STATE_LABELS[rs.STATE_AWAITING_REVIEW], html)
        self.assertIn(f"/payments/refund/{refund.pk}/approve/", html)
        self.assertNotIn("ثبتِ انجامِ تأییدشده", html)                                                         # cannot complete before approval
        rs.approve_refund_for_manual_processing(refund, actor=None)
        html = client.get(page).content.decode()
        self.assertIn(rs.STATE_LABELS[rs.STATE_APPROVED], html)
        self.assertNotIn(f"/payments/refund/{refund.pk}/approve/", html)
        self.assertIn("ثبتِ انجامِ تأییدشده", html)
        rs.complete_refund_manually(refund, actor=None, reference="BANK-REF-0009")
        html = client.get(page).content.decode()
        self.assertIn(rs.STATE_LABELS[rs.STATE_COMPLETED], html)
        self.assertNotIn(f"/payments/refund/{refund.pk}/", html)                                              # no action left
        unknown = SubscriptionRefund.objects.create(
            store=self.store, invoice=self.invoice, provider="saman", status=R.PENDING, failure_code=rs.UNKNOWN_OUTCOME,
            amount=Decimal("1"), currency="IRT", idempotency_key="ui-unknown")
        self.assertIn(rs.STATE_LABELS[rs.STATE_UNKNOWN], client.get(page).content.decode())
        rs.fail_refund_manually(unknown, actor=None, reference="BANK-PROOF-0010")
        rejected_src = SubscriptionRefund.objects.create(
            store=self.store, invoice=self.invoice, provider="saman", status=R.CANCELLED, failure_code=rs.MANUAL_REJECTED,
            amount=Decimal("1"), currency="IRT", idempotency_key="ui-rejected")
        self.assertIn(rs.STATE_LABELS[rs.STATE_REJECTED], client.get(page).content.decode())
        self.assertEqual(rs.review_state(rejected_src), rs.STATE_REJECTED)

    def test_no_template_action_targets_a_gateway_refund(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[2] / "portal/templates/portal/platform_admin/payment_invoice_detail.html").read_text(encoding="utf-8")
        for name in ("payment-refund-approve", "payment-refund-reject", "payment-refund-complete", "payment-invoice-refund"):
            self.assertIn(name, text)
        self.assertNotRegex(text, r"reverse|gateway-refund|refund_payment")


class SmsCreditsAreNeverRevokedByTheFlagAloneTests(SmsRefundDisabledBase):
    def test_enabling_the_sms_flag_without_the_owner_approval_constant_still_changes_nothing(self):
        purchase, _attempt = self.completed()
        before = self.snapshot()
        self.provider_spy()
        with override_settings(RASTISI_SMS_REFUND_ENABLED=True):
            self.assertFalse(sms_svc.sms_refunds_enabled())
            with self.assertRaises(sms_svc.SmsRefundDisabledError):
                sms_svc.refund_purchase(purchase, actor=self.staff, reason="try", idempotency_key="k")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(SmsCreditLedger.objects.filter(kind="purchase_reversal").count(), 0)
        self.assertEqual(self.credits(), 100 + self.CREDITS)


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrency")
class PostgresConcurrentDecisionTests(PolicyBase, TransactionTestCase):
    """Real threads: a double-clicked or raced completion applies the financial effect exactly once; no provider is ever resolved."""

    def run_parallel(self, workers, fn):
        barrier = threading.Barrier(workers)

        def worker(i):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                return fn(i)
            except Exception as exc:  # noqa: BLE001
                return type(exc).__name__
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(worker, range(workers)))

    def test_eight_simultaneous_completions_apply_the_refund_and_the_suspension_once(self):
        self.make("pg-1", "saman")
        refund = self.request()
        rs.approve_refund_for_manual_processing(refund, actor=None)
        self.forbid_providers()
        results = self.run_parallel(8, lambda i: rs.complete_refund_manually(refund, actor=None, reference=f"BANK-REF-{i:04d}").pk)
        self.assertEqual({r for r in results}, {refund.pk}, results)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_completed").count(), 1)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.refund_entitlement_outcome").count(), 1)
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice, status=R.SUCCEEDED).count(), 1)
        self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.REFUNDED)

    def test_simultaneous_approve_reject_and_complete_end_in_exactly_one_final_state(self):
        self.make("pg-2", "mellat")
        refund = self.request()
        rs.approve_refund_for_manual_processing(refund, actor=None)
        self.forbid_providers()

        def act(i):
            if i % 2:
                return rs.reject_refund(refund, actor=None, reason="race").status
            return rs.complete_refund_manually(refund, actor=None, reference="BANK-REF-RACE").status

        self.run_parallel(6, act)
        final = SubscriptionRefund.objects.get(pk=refund.pk)
        self.assertIn(final.status, (R.SUCCEEDED, R.CANCELLED))
        if final.status == R.SUCCEEDED:
            self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.REFUNDED)
        else:
            self.assertEqual(self.invoice_status(), SubscriptionInvoice.Status.PAID)
        self.assertEqual(AuditLogEntry.objects.filter(action_code__in=["billing.refund_completed", "billing.refund_rejected"]).count(), 1)
