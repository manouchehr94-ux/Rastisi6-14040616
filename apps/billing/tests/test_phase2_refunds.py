"""Phase 2 / F-06: refunds that survive uncertain provider outcomes.

Synthetic providers only (no network, no real bank). The contract under test:
* the refund INTENT is committed before the provider is contacted, and the provider is contacted at most once per refund row;
* a timeout / transport error / unexpected exception / lost response is UNKNOWN, never a blind retry and never a lost record;
* a crash between the provider call and the outcome is recovered by a job that never calls the provider;
* finance resolves an unknown outcome only with a documented bank reference;
* no provider call happens inside a transaction or while a row lock is held.
The PostgreSQL class uses real threads and is skipped on SQLite (which ignores row locks)."""

import io
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund
from apps.billing.providers.base import BillingProviderError, ProviderConnectionError, RefundResult
from apps.billing.services import duplicate_payment_service as dups
from apps.billing.services import refund_service
from apps.billing.tests.test_credit_refund import _paid_invoice
from apps.core.models import AuditLogEntry

User = get_user_model()
R = SubscriptionRefund.Status
PLATFORM_HOST = "platformadmins.rastisi.localhost"


class FakeProvider:
    """Records every call. ``behaviour`` returns a RefundResult or raises."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []
        self.in_transaction_flags = []

    def refund_payment(self, *, provider_payment_id, amount, currency, idempotency_key):
        self.calls.append({"payment": provider_payment_id, "amount": amount, "key": idempotency_key})
        self.in_transaction_flags.append(connection.in_atomic_block)
        return self.behaviour(self)


def ok(p):
    return RefundResult(provider_refund_id=f"bank-rf-{len(p.calls)}-{threading.get_ident()}", succeeded=True, raw_summary={})


def manual(p):
    return RefundResult(provider_refund_id=f"manual-{len(p.calls)}", succeeded=False, raw_summary={"manual": True})


def lost_response(_p):
    return RefundResult(provider_refund_id="", succeeded=False, raw_summary={"manual": True, "unknown": True, "reason": "x"})


def timeout(_p):
    raise ProviderConnectionError("timeout", code="timeout")


def boom(_p):
    raise RuntimeError("unexpected")


def not_configured(_p):
    raise BillingProviderError("not configured", code="not_configured")


def patched(provider):
    return mock.patch("apps.billing.services.refund_service.registry.get_provider", return_value=provider)


class RefundBase(TestCase):
    def setUp(self):
        self.store, self.invoice = _paid_invoice("p2rf")

    def refund(self, provider, amount="100000", key="k1", **kw):
        with patched(provider):
            return refund_service.request_refund(self.invoice, amount=Decimal(amount), reason="test", idempotency_key=key, **kw)


class RefundOutcomeTests(RefundBase):
    def test_confirmed_provider_success_completes_and_refunds_the_invoice(self):
        provider = FakeProvider(ok)
        refund = self.refund(provider, amount="400000")
        self.invoice.refresh_from_db()
        self.assertEqual((refund.status, refund.provider_refund_id.startswith("bank-rf-")), (R.SUCCEEDED, True))
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.REFUNDED)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0]["key"], "k1")                       # the stable key is the row key

    def test_repeat_with_the_same_key_never_contacts_the_provider_again(self):
        provider = FakeProvider(ok)
        first = self.refund(provider)
        second = self.refund(provider)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(len(provider.calls), 1)

    def test_provider_without_automatic_refund_leaves_a_manual_pending_row_that_is_not_unknown(self):
        refund = self.refund(FakeProvider(manual))
        self.assertEqual((refund.status, refund.failure_code), (R.PENDING, ""))

    def test_timeout_after_the_request_is_unknown_keeps_the_amount_reserved_and_is_never_retried(self):
        provider = FakeProvider(timeout)
        refund = self.refund(provider, amount="400000")
        self.assertEqual((refund.status, refund.failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)   # not refunded: the outcome is not confirmed
        self.assertEqual(refund_service.refundable_amount(self.invoice), Decimal("0"))   # but the money stays reserved
        again = self.refund(provider, amount="400000")                            # a retry with the same key
        self.assertEqual(again.pk, refund.pk)
        with self.assertRaises(refund_service.RefundError):                       # and a new key cannot double-pay
            self.refund(provider, amount="100000", key="k2")
        self.assertEqual(len(provider.calls), 1)

    def test_unexpected_exception_and_lost_response_are_both_unknown(self):
        for name, behaviour in (("exception", boom), ("lost", lost_response)):
            with self.subTest(name):
                store, invoice = _paid_invoice(f"p2rf-{name}")
                provider = FakeProvider(behaviour)
                with patched(provider):
                    refund = refund_service.request_refund(invoice, amount=Decimal("100000"), idempotency_key=f"u-{name}")
                self.assertEqual((refund.status, refund.failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
                self.assertEqual(len(provider.calls), 1)

    def test_definite_not_sent_failure_releases_the_reservation(self):
        refund = self.refund(FakeProvider(not_configured), amount="400000")
        self.assertEqual((refund.status, refund.failure_code), (R.FAILED, "not_configured"))
        self.assertEqual(refund_service.refundable_amount(self.invoice), Decimal("400000"))

    def test_the_intent_is_committed_before_the_provider_is_contacted(self):
        seen = {}

        def look(p):
            seen["status"] = list(SubscriptionRefund.objects.values_list("status", flat=True))
            return ok(p)

        self.refund(FakeProvider(look))
        self.assertEqual(seen["status"], [R.REQUESTED])

    def test_the_provider_is_never_called_inside_a_transaction_block_created_by_the_service(self):
        # TestCase wraps everything in one outer atomic block, so assert the service did not ADD another one around the call.
        baseline = connection.in_atomic_block
        provider = FakeProvider(ok)
        depth = {}

        def probe(p):
            depth["savepoints"] = len(connection.savepoint_ids)
            return ok(p)

        provider.behaviour = probe
        base_depth = len(connection.savepoint_ids)
        self.refund(provider)
        self.assertTrue(baseline)
        self.assertEqual(depth["savepoints"], base_depth)

    def test_audit_trail_records_the_intent_and_the_unknown_outcome(self):
        self.refund(FakeProvider(timeout))
        codes = set(AuditLogEntry.objects.values_list("action_code", flat=True))
        self.assertIn("billing.refund_intent_recorded", codes)
        self.assertIn("billing.refund_outcome_unknown", codes)


class RefundRecoveryTests(RefundBase):
    def test_db_failure_after_provider_success_leaves_a_recoverable_intent_and_no_second_call(self):
        provider = FakeProvider(ok)
        with patched(provider), mock.patch.object(refund_service, "_record_outcome", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                refund_service.request_refund(self.invoice, amount=Decimal("100000"), idempotency_key="crash")
        row = SubscriptionRefund.objects.get(idempotency_key="crash")
        self.assertEqual(row.status, R.REQUESTED)                                 # the record survived the failure
        with patched(provider):
            again = refund_service.request_refund(self.invoice, amount=Decimal("100000"), idempotency_key="crash")
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(len(provider.calls), 1)                                  # the retry did NOT pay twice
        SubscriptionRefund.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=1))
        with patched(provider):
            self.assertEqual(refund_service.recover_stale_intents(), 1)
            self.assertEqual(refund_service.recover_stale_intents(), 0)           # idempotent
        row.refresh_from_db()
        self.assertEqual((row.status, row.failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
        self.assertEqual(len(provider.calls), 1)                                  # recovery never calls the provider

    def test_recovery_ignores_fresh_intents(self):
        row = SubscriptionRefund.objects.create(
            store=self.store, invoice=self.invoice, provider="manual", status=R.REQUESTED, amount=Decimal("1"), currency="IRT",
            requested_at=timezone.now(), idempotency_key="fresh")
        self.assertEqual(refund_service.recover_stale_intents(), 0)
        row.refresh_from_db()
        self.assertEqual(row.status, R.REQUESTED)

    def test_command_marks_stale_intents_never_calls_a_provider_and_fails_loudly_while_unknowns_wait(self):
        row = SubscriptionRefund.objects.create(
            store=self.store, invoice=self.invoice, provider="manual", status=R.REQUESTED, amount=Decimal("100000"),
            currency="IRT", requested_at=timezone.now(), idempotency_key="stale")
        SubscriptionRefund.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=2))
        provider = FakeProvider(ok)
        out = io.StringIO()
        with patched(provider):
            with self.assertRaises(CommandError):
                call_command("recover_stale_refunds", stdout=out)
        self.assertIn("marked=1", out.getvalue())
        self.assertEqual(provider.calls, [])
        row.refresh_from_db()
        self.assertEqual(row.failure_code, refund_service.UNKNOWN_OUTCOME)


class UnknownRefundResolutionTests(RefundBase):
    def unknown(self, amount="400000"):
        return self.refund(FakeProvider(timeout), amount=amount)

    def test_completing_an_unknown_refund_requires_a_bank_reference(self):
        refund = self.unknown()
        for bad in ("", "  ", "abc"):
            with self.assertRaises(refund_service.RefundError):
                refund_service.complete_refund_manually(refund, actor=None, reference=bad)
        refund.refresh_from_db()
        self.assertEqual(refund.status, R.PENDING)
        done = refund_service.complete_refund_manually(refund, actor=None, reference="BANK-REF-12345")
        self.assertEqual(done.status, R.SUCCEEDED)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.REFUNDED)
        self.assertEqual(refund_service.complete_refund_manually(done, actor=None, reference="BANK-REF-12345").pk, done.pk)  # idempotent

    def test_a_manual_pending_refund_still_completes_without_a_reference(self):
        refund = self.refund(FakeProvider(manual), amount="400000")
        self.assertEqual(refund_service.complete_refund_manually(refund, actor=None).status, R.SUCCEEDED)

    def test_finance_can_prove_non_execution_which_releases_the_amount_for_a_corrected_refund(self):
        refund = self.unknown()
        with self.assertRaises(refund_service.RefundError):
            refund_service.fail_refund_manually(refund, actor=None, reference="x")
        failed = refund_service.fail_refund_manually(refund, actor=None, reference="BANK-NOTHING-SENT", note="no debit")
        self.assertEqual((failed.status, failed.failure_code), (R.FAILED, "manual_declined"))
        self.assertEqual(refund_service.refundable_amount(self.invoice), Decimal("400000"))
        self.assertEqual(refund_service.fail_refund_manually(failed, actor=None, reference="BANK-NOTHING-SENT").pk, failed.pk)
        self.assertEqual(self.refund(FakeProvider(ok), amount="400000", key="k-new").status, R.SUCCEEDED)

    def test_a_finished_refund_cannot_be_failed_or_completed_again_differently(self):
        refund = self.refund(FakeProvider(ok))
        with self.assertRaises(refund_service.RefundError):
            refund_service.fail_refund_manually(refund, actor=None, reference="BANK-REF-12345")


class PlatformAdminRefundViewTests(RefundBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(username="p2-fin", password="x", is_staff=True, is_superuser=True)
        self.client = Client(HTTP_HOST=PLATFORM_HOST)
        self.client.force_login(self.staff)

    def post_refund(self, provider, **data):
        with patched(provider):
            return self.client.post(f"/payments/invoice/{self.invoice.pk}/refund/", {"amount": "100000", "reason": "dup", **data})

    def test_the_form_carries_a_per_render_idempotency_key(self):
        response = self.client.get(f"/payments/invoice/{self.invoice.pk}/")
        self.assertContains(response, 'name="idempotency_key"')

    def test_a_double_submit_of_the_same_form_makes_one_refund_and_one_provider_call(self):
        provider = FakeProvider(ok)
        self.post_refund(provider, idempotency_key="form-token-1")
        self.post_refund(provider, idempotency_key="form-token-1")
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(len(provider.calls), 1)

    def test_without_a_form_token_a_repeat_after_an_unknown_outcome_is_refused_not_re_sent(self):
        provider = FakeProvider(timeout)
        self.post_refund(provider)
        self.post_refund(provider)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)

    def test_without_a_form_token_a_repeat_after_a_success_is_bounded_by_the_refundable_amount(self):
        provider = FakeProvider(ok)
        for _ in range(6):
            self.post_refund(provider)
        self.assertEqual(sum(r.amount for r in SubscriptionRefund.objects.filter(invoice=self.invoice)), self.invoice.amount_paid)

    def test_unknown_outcome_is_shown_as_a_warning_not_as_success(self):
        provider = FakeProvider(timeout)
        with patched(provider):
            response = self.client.post(f"/payments/invoice/{self.invoice.pk}/refund/",
                                        {"amount": "100000", "reason": "dup", "idempotency_key": "w1"}, follow=True)
        self.assertContains(response, "نامشخص")

    def test_complete_requires_a_reference_for_unknown_and_not_executed_path_releases(self):
        refund = self.refund(FakeProvider(timeout))
        self.client.post(f"/payments/refund/{refund.pk}/complete/", {"reference": ""})
        refund.refresh_from_db()
        self.assertEqual(refund.status, R.PENDING)
        self.client.post(f"/payments/refund/{refund.pk}/complete/", {"resolution": "not_executed", "reference": "PROOF-123456"})
        refund.refresh_from_db()
        self.assertEqual(refund.status, R.FAILED)

    def test_a_non_superuser_cannot_resolve_refunds(self):
        refund = self.refund(FakeProvider(timeout))
        plain = User.objects.create_user(username="p2-plain", password="x", is_staff=True)
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(plain)
        client.post(f"/payments/refund/{refund.pk}/complete/", {"reference": "BANK-REF-12345"})
        refund.refresh_from_db()
        self.assertEqual(refund.status, R.PENDING)


@override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS="saman")        # the ENABLED path; disabled behaviour: test_bank_refund_disabled.py
class AdapterUnknownOutcomeTests(TestCase):
    """The real adapter-backed provider must report a transport failure during a reverse as UNKNOWN, a plain gateway refusal as
    a manual follow-up, and a pre-send failure (credentials) as a definite not-executed."""

    def build(self, cancel):
        from apps.billing.providers.adapter_backed import AdapterBackedBillingProvider
        from apps.orders.gateways.base import GatewayCategory, PaymentOperation

        provider = AdapterBackedBillingProvider("saman")
        adapter = mock.Mock()
        adapter.supports.side_effect = lambda op: op == PaymentOperation.CANCEL
        adapter.category = GatewayCategory.PSP
        adapter.cancel_payment.side_effect = cancel
        attempt = mock.Mock(amount=Decimal("1000"), provider_extra={"verified_ref": "REF-1"}, provider_session_id="s1")
        patches = [
            mock.patch.object(provider, "_adapter", return_value=adapter),
            mock.patch.object(provider, "_attempt_for_payment", return_value=attempt),
            mock.patch.object(provider, "_credentials", return_value=(adapter, {}, True)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return provider

    def reverse(self, cancel):
        return self.build(cancel).refund_payment(
            provider_payment_id="p1", amount=Decimal("1000"), currency="IRT", idempotency_key="k")

    def test_connection_failure_is_unknown(self):
        from apps.orders.gateways.base import GatewayConnectionError

        def cancel(**_kw):
            raise GatewayConnectionError("timeout", code="timeout")

        result = self.reverse(cancel)
        self.assertFalse(result.succeeded)
        self.assertTrue(result.raw_summary.get("unknown"))

    def test_unreadable_response_is_unknown(self):
        from apps.orders.gateways.base import GatewayResponseError

        def cancel(**_kw):
            raise GatewayResponseError("bad", code="bad_json")

        self.assertTrue(self.reverse(cancel).raw_summary.get("unknown"))

    def test_explicit_gateway_refusal_is_a_manual_followup_not_unknown(self):
        from apps.orders.gateways.base import GatewayPaymentError

        def cancel(**_kw):
            raise GatewayPaymentError("refused", code="refused")

        result = self.reverse(cancel)
        self.assertTrue(result.raw_summary.get("manual"))
        self.assertFalse(result.raw_summary.get("unknown"))

    def test_confirmed_reverse_is_success(self):
        result = self.reverse(lambda **_kw: mock.Mock(success=True, status_code="0"))
        self.assertTrue(result.succeeded)


class DuplicateRefundTests(TestCase):
    """``duplicate_payment_service.refund_duplicate`` (surplus of a duplicate attempt) gets the same intent -> call -> outcome shape."""

    def setUp(self):
        self.store, self.invoice = _paid_invoice("p2dup")
        self.attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=self.invoice, provider="manual", status=SubscriptionPaymentAttempt.Status.REQUIRES_ACTION,
            amount=Decimal("400000"), currency="IRT", failure_code="duplicate_payment", provider_payment_id="dup-pay",
            idempotency_key="dup-attempt-key")

    def call(self, provider, **kw):
        with mock.patch.object(dups.registry, "get_provider", return_value=provider):
            return dups.refund_duplicate("subscription", self.attempt.pk, actor=None, reason="duplicate", **kw)

    def test_success_records_refunded_once(self):
        provider = FakeProvider(ok)
        self.assertEqual(self.call(provider)[1], "refunded")
        self.assertEqual(self.call(provider)[1], "refunded")
        self.assertEqual(len(provider.calls), 1)

    def test_timeout_is_unknown_and_is_never_re_sent(self):
        provider = FakeProvider(timeout)
        self.assertEqual(self.call(provider)[1], "unknown")
        self.assertEqual(self.call(provider)[1], "unknown")
        self.assertEqual(len(provider.calls), 1)
        self.attempt.refresh_from_db()
        self.assertFalse(dups.is_resolved(self.attempt))                          # still on the finance work list

    def test_finance_resolves_an_unknown_outcome_with_a_reference(self):
        self.call(FakeProvider(timeout))
        with self.assertRaises(dups.DuplicatePaymentError):
            dups.mark_resolved("subscription", self.attempt.pk, actor=None, outcome="refunded_external", reference="x")
        dups.mark_resolved("subscription", self.attempt.pk, actor=None, outcome="refunded_external", reference="BANK-REF-99999")
        self.attempt.refresh_from_db()
        self.assertTrue(dups.is_resolved(self.attempt))

    def test_a_definitely_unsent_request_releases_the_intent_so_it_can_be_retried(self):
        with self.assertRaises(dups.DuplicatePaymentError):
            self.call(FakeProvider(not_configured))
        self.attempt.refresh_from_db()
        self.assertEqual(dups.resolution_of(self.attempt), {})
        provider = FakeProvider(ok)
        self.assertEqual(self.call(provider)[1], "refunded")

    def test_stale_requesting_intent_becomes_unknown_without_calling_the_provider(self):
        provider = FakeProvider(ok)
        with mock.patch.object(dups, "_store_resolution", wraps=dups._store_resolution):
            with mock.patch.object(dups.registry, "get_provider", return_value=provider):
                # simulate a crash right after the intent: write the intent only
                dups._store_resolution(self.attempt, outcome=dups.REQUESTING, reason="r", by=None, key="k",
                                       at=(timezone.now() - timedelta(hours=1)).isoformat(timespec="seconds"))
                self.assertEqual(dups.recover_stale_requests(), 1)
                self.assertEqual(dups.recover_stale_requests(), 0)
        self.attempt.refresh_from_db()
        self.assertEqual(dups.resolution_of(self.attempt)["outcome"], "unknown")
        self.assertEqual(provider.calls, [])
        # and an explicit refund request now refuses to re-send
        self.assertEqual(self.call(provider)[1], "unknown")
        self.assertEqual(provider.calls, [])


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrency")
class PostgresConcurrentRefundTests(TransactionTestCase):
    def setUp(self):
        self.store, self.invoice = _paid_invoice("p2pg")

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

    def test_8_simultaneous_submissions_with_one_key_make_one_row_and_one_provider_call(self):
        provider = FakeProvider(ok)

        def go(_i):
            return refund_service.request_refund(
                SubscriptionInvoice.objects.get(pk=self.invoice.pk), amount=Decimal("100000"), idempotency_key="same").pk

        with patched(provider):
            pks = self.run_parallel(8, go)
        self.assertEqual(len(set(pks)), 1, pks)
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(len(provider.calls), 1)

    def test_6_simultaneous_different_keys_can_never_refund_more_than_was_paid(self):
        provider = FakeProvider(ok)

        def go(i):
            return refund_service.request_refund(
                SubscriptionInvoice.objects.get(pk=self.invoice.pk), amount=Decimal("100000"), idempotency_key=f"k{i}").status

        with patched(provider):
            out = Counter(self.run_parallel(6, go))
        rows = SubscriptionRefund.objects.filter(invoice=self.invoice)
        self.assertEqual(rows.count(), 4, out)                                    # 400000 / 100000
        self.assertEqual(out.get("RefundError"), 2, out)
        self.assertEqual(sum(r.amount for r in rows), Decimal("400000"))
        self.assertEqual(len(provider.calls), 4)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.REFUNDED)

    def test_no_lock_is_held_and_the_intent_is_visible_to_other_connections_during_the_provider_call(self):
        observed = {}

        def during_call(p):
            def look():
                close_old_connections()
                try:
                    with transaction.atomic():
                        SubscriptionInvoice.objects.select_for_update(nowait=True).get(pk=self.invoice.pk)   # would raise if locked
                        observed["lock_free"] = True
                    observed["status"] = SubscriptionRefund.objects.get(idempotency_key="vis").status
                except Exception as exc:  # noqa: BLE001
                    observed["error"] = type(exc).__name__
                finally:
                    connection.close()

            t = threading.Thread(target=look)
            t.start()
            t.join(timeout=20)
            return ok(p)

        provider = FakeProvider(during_call)
        with patched(provider):
            refund_service.request_refund(self.invoice, amount=Decimal("100000"), idempotency_key="vis")
        self.assertEqual(observed, {"lock_free": True, "status": R.REQUESTED})
        self.assertEqual(provider.in_transaction_flags, [False])                   # not inside any transaction

    def test_provider_timeout_with_concurrent_retries_stays_one_unknown_refund(self):
        provider = FakeProvider(timeout)

        def go(_i):
            return refund_service.request_refund(
                SubscriptionInvoice.objects.get(pk=self.invoice.pk), amount=Decimal("400000"), idempotency_key="t1").status

        with patched(provider):
            self.run_parallel(5, go)
        row = SubscriptionRefund.objects.get(idempotency_key="t1")
        self.assertEqual((row.status, row.failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
        self.assertEqual(len(provider.calls), 1)

    def test_6_simultaneous_duplicate_refund_requests_call_the_provider_once(self):
        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=self.invoice, provider="manual", status=SubscriptionPaymentAttempt.Status.REQUIRES_ACTION,
            amount=Decimal("400000"), currency="IRT", failure_code="duplicate_payment", provider_payment_id="dup-pay",
            idempotency_key="dup-conc")
        provider = FakeProvider(ok)

        def go(_i):
            return dups.refund_duplicate("subscription", attempt.pk, actor=None, reason="duplicate")[1]

        with mock.patch.object(dups.registry, "get_provider", return_value=provider):
            out = Counter(self.run_parallel(6, go))
        self.assertEqual(len(provider.calls), 1, out)
        self.assertEqual(provider.in_transaction_flags, [False])
