"""Uncertain BNPL settlement is NEVER a definitive customer payment failure.

Real service + database boundaries; only the outbound provider calls (verify / settle / inquire) are mocked. Distinguishes:
definitive rejection (authoritative provider status) · timeout / transport · malformed answer · unknown outcome · confirmed settlement
· duplicate callback · recovery workers · duplicate initiation while unresolved."""

import threading
from unittest.mock import patch

from django.db import connection
from django.test import Client, TransactionTestCase
from django.urls import reverse

from apps.notifications.models import NotificationEvent
from apps.orders.gateways.base import (
    GatewayAmountMismatchError, GatewayConnectionError, GatewayResponseError, PaymentInquiryResult, PaymentSettleResult,
)
from apps.orders.models import Order, PaymentAttempt, PaymentGatewayConfig, PaymentReconciliation, PaymentTransactionEvent, Transaction
from apps.orders.services.gateway_payment_service import (
    PaymentSettlementUnresolved, PaymentVerificationFailed, initiate_payment, process_callback_and_verify, resolve_unknown_payment,
)
from apps.orders.tests.test_payment_integration_extra import SNAPPAY_CREDS, IntegrationExtraBase, settle_fail, verify_ok

SNAPP = "apps.orders.gateways.snappay.SnappPayAdapter"
VERIFY, SETTLE, INQUIRE = f"{SNAPP}.verify_payment", f"{SNAPP}.settle_payment", f"{SNAPP}.inquire_payment"
CALLBACK = {"state": "OK"}


def inquiry(status, *, settled=False, terminal=False, ref="REF-INQ"):
    return PaymentInquiryResult(paid=status in ("VERIFY", "SETTLE"), settled=settled, ref_id=ref, status=status, terminal_negative=terminal)


class UncertaintyBase(IntegrationExtraBase):
    def setUp(self):
        super().setUp()
        self.config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        self.order = self.new_order()
        self.attempt = self._attempt(self.order, self.config, track="SP-TOKEN-1")

    def callback(self, *, settle=None, settle_exc=None, inq=None, inq_exc=None, verify=None, data=None):
        with patch(VERIFY, return_value=verify or verify_ok()) as v, \
             patch(SETTLE, return_value=settle, side_effect=settle_exc) as s, \
             patch(INQUIRE, return_value=inq, side_effect=inq_exc) as i:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    result = process_callback_and_verify(attempt_public_id=self.attempt.public_id, callback_data=data if data is not None else CALLBACK, store=self.store)
                    error = None
                except PaymentVerificationFailed as exc:
                    result, error = None, exc
        return result, error, (v, s, i)

    def reload(self):
        self.order.refresh_from_db(); self.attempt.refresh_from_db()

    def make_unknown(self):
        self.callback(settle_exc=GatewayConnectionError("timeout", code="timeout"), inq_exc=GatewayConnectionError("down"))
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)

    def payment_failed_events(self):
        return NotificationEvent.objects.filter(type_key="payment.failed").count()

    def assert_untouched_order(self):
        self.reload()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(Transaction.objects.filter(order=self.order).count(), 0)


class ClassificationTests(UncertaintyBase):
    def test_timeout_is_unknown_not_failed_and_never_payment_failed(self):
        result, error, (_v, settle, _i) = self.callback(settle_exc=GatewayConnectionError("read timed out", code="timeout"), inq_exc=GatewayConnectionError("down"))
        self.assertIsNone(error)
        self.reload()
        self.assertEqual(settle.call_count, 1)
        self.assertEqual((self.attempt.status, self.attempt.failure_code), (PaymentAttempt.Status.UNKNOWN, "settle_uncertain"))
        self.assertEqual(self.attempt.gateway_ref_id, "REF-OK")                            # provider reference preserved
        self.assert_untouched_order()
        self.assertEqual(self.payment_failed_events(), 0)
        record = PaymentReconciliation.objects.get(attempt=self.attempt)
        self.assertEqual((record.kind, record.evidence_level, record.status), ("settlement_uncertain", "suspected", "open"))
        self.assertTrue(NotificationEvent.objects.filter(type_key="payment.suspicious").exists())
        self.assertTrue(PaymentTransactionEvent.objects.filter(attempt=self.attempt).exists())   # durable append-only evidence

    def test_malformed_provider_answer_is_unknown_too(self):
        _r, error, _ = self.callback(settle_exc=GatewayResponseError("not json", code="invalid_response"), inq_exc=GatewayResponseError("bad"))
        self.assertIsNone(error)
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assert_untouched_order()

    def test_unexpected_crash_inside_settle_is_unknown(self):
        self.callback(settle_exc=RuntimeError("boom"), inq_exc=GatewayConnectionError("down"))
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)

    def test_bare_rejection_the_provider_cannot_confirm_is_still_unknown(self):
        self.callback(settle=settle_fail(), inq=inquiry("VERIFY"))
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assertEqual(self.payment_failed_events(), 0)
        self.assert_untouched_order()

    def test_a_pending_provider_status_is_not_a_failure(self):
        self.callback(settle_exc=GatewayConnectionError("t"), inq=inquiry("PENDING"))
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)

    def test_authoritative_revert_is_a_definitive_failure_with_exactly_one_payment_failed(self):
        _r, error, _ = self.callback(settle=settle_fail(), inq=inquiry("REVERT", terminal=True))
        self.assertIsInstance(error, PaymentVerificationFailed)
        self.reload()
        self.assertEqual((self.attempt.status, self.attempt.failure_code), (PaymentAttempt.Status.FAILED, "settle_reverted"))
        self.assert_untouched_order()
        self.assertEqual(self.payment_failed_events(), 1)
        self.assertFalse(PaymentReconciliation.objects.filter(attempt=self.attempt).exists())

    def test_late_success_via_inquiry_after_a_settle_timeout_pays_once(self):
        result, error, (_v, settle, inq) = self.callback(settle_exc=GatewayConnectionError("t", code="timeout"), inq=inquiry("SETTLE", settled=True, ref="REF-LATE"))
        self.assertIsNone(error)
        self.reload()
        self.assertEqual(settle.call_count, 1)                                           # no duplicate settle request
        self.assertEqual((self.attempt.status, self.order.payment_status), (PaymentAttempt.Status.SUCCEEDED, Order.PaymentStatus.PAID))
        self.assertEqual(Transaction.objects.filter(order=self.order, status="ok").count(), 1)
        self.assertEqual(self.payment_failed_events(), 0)

    def test_confirmed_settlement_still_pays_once(self):
        self.callback(settle=PaymentSettleResult(success=True, settle_ref="S1", status_code=100))
        self.reload()
        self.assertEqual((self.attempt.status, self.order.payment_status), (PaymentAttempt.Status.SUCCEEDED, Order.PaymentStatus.PAID))
        self.assertEqual(Transaction.objects.filter(order=self.order, status="ok").count(), 1)


class UnresolvedAttemptBlocksRiskTests(UncertaintyBase):
    def test_a_duplicate_callback_never_reverifies_or_resettles(self):
        self.make_unknown()
        _r, error, (verify, settle, inq) = self.callback(inq=inquiry("VERIFY"))
        self.assertIsNone(error)
        self.assertEqual((verify.call_count, settle.call_count), (0, 0))                 # NO duplicate verify / settle
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assertEqual(PaymentReconciliation.objects.filter(attempt=self.attempt).count(), 1)   # still ONE record

    def test_a_late_callback_that_proves_revert_fails_it_once(self):
        self.make_unknown()
        _r, error, _ = self.callback(inq=inquiry("CANCEL", terminal=True))
        self.assertIsInstance(error, PaymentVerificationFailed)
        self.callback(inq=inquiry("CANCEL", terminal=True))                              # replay
        self.assertEqual(self.payment_failed_events(), 1)

    def test_no_new_chargeable_operation_while_unresolved_for_any_provider(self):
        self.make_unknown()
        with self.assertRaises(PaymentSettlementUnresolved):
            initiate_payment(order=self.order, gateway_config=self.config, callback_url="https://x/cb", store=self.store)
        zibal = self._ready_config("zibal", {"merchant": "zibal"}, sandbox=True)
        with patch("apps.orders.gateways.zibal.ZibalAdapter.create_payment") as create:
            with self.assertRaises(PaymentSettlementUnresolved):
                initiate_payment(order=self.order, gateway_config=zibal, callback_url="https://x/cb", store=self.store)
        self.assertFalse(create.called)                                                   # no second provider operation
        self.assertEqual(PaymentAttempt.objects.filter(order=self.order).count(), 1)

    def test_the_payment_page_answers_409_not_a_new_gateway_redirect(self):
        self.make_unknown()
        from django.contrib.auth import get_user_model
        client = Client()
        client.force_login(self.order.customer.user)
        with patch("apps.orders.views.resolve_store_for_service", return_value=self.store):
            response = client.get(reverse("orders:payment-initiate", args=[self.order.code]))
        self.assertEqual(response.status_code, 409)

    def test_other_orders_of_the_same_customer_are_not_blocked(self):
        self.make_unknown()
        other_order = self.new_order()
        zibal = self._ready_config("zibal", {"merchant": "zibal"}, sandbox=True)
        from apps.orders.gateways.base import PaymentCreationResult
        with patch("apps.orders.gateways.zibal.ZibalAdapter.create_payment", return_value=PaymentCreationResult(track_id="Z1", gateway_url=None)):
            attempt = initiate_payment(order=other_order, gateway_config=zibal, callback_url="https://x/cb", store=self.store)
        self.assertEqual(attempt.status, PaymentAttempt.Status.REDIRECT_READY)


class RecoveryTests(UncertaintyBase):
    def test_recovery_settled_pays_once_and_closes_the_suspected_record(self):
        self.make_unknown()
        with patch(INQUIRE, return_value=inquiry("SETTLE", settled=True, ref="REF-R")), patch(SETTLE) as settle:
            first = resolve_unknown_payment(self.attempt.pk)
            second = resolve_unknown_payment(self.attempt.pk)                           # idempotent
        self.assertEqual((first.status, second.status), (PaymentAttempt.Status.SUCCEEDED, PaymentAttempt.Status.SUCCEEDED))
        self.assertFalse(settle.called)                                                  # recovery never settles again
        self.reload()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(Transaction.objects.filter(order=self.order, status="ok").count(), 1)
        record = PaymentReconciliation.objects.get(attempt=self.attempt)
        self.assertEqual((record.status, record.resolution), ("resolved", "auto_verified"))

    def test_recovery_terminal_negative_fails_once_and_resolves_the_record(self):
        self.make_unknown()
        with patch(INQUIRE, return_value=inquiry("REVERT", terminal=True)):
            with self.captureOnCommitCallbacks(execute=True):
                resolve_unknown_payment(self.attempt.pk)
            with self.captureOnCommitCallbacks(execute=True):
                resolve_unknown_payment(self.attempt.pk)
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.FAILED)
        self.assert_untouched_order()
        self.assertEqual(self.payment_failed_events(), 1)
        record = PaymentReconciliation.objects.get(attempt=self.attempt)
        self.assertEqual((record.status, record.resolution), ("resolved", "not_paid"))

    def test_an_inconclusive_inquiry_changes_nothing(self):
        self.make_unknown()
        for kwargs in ({"inq": inquiry("VERIFY")}, {"inq_exc": GatewayConnectionError("down")}, {"inq": inquiry("PENDING")}):
            with patch(INQUIRE, return_value=kwargs.get("inq"), side_effect=kwargs.get("inq_exc")):
                resolved = resolve_unknown_payment(self.attempt.pk)
            self.assertEqual(resolved.status, PaymentAttempt.Status.UNKNOWN)
        self.assertEqual(PaymentReconciliation.objects.get(attempt=self.attempt).status, "open")

    def test_an_amount_mismatch_found_on_inquiry_keeps_the_money_evidence_and_never_pays_the_order(self):
        self.make_unknown()
        exc = GatewayAmountMismatchError("mismatch", code="amount_mismatch", details={"evidence": {"expected_rial": 1, "returned_rial": 2}})
        with patch(INQUIRE, side_effect=exc):
            resolve_unknown_payment(self.attempt.pk)
        self.assert_untouched_order()                                                    # the order is never paid on a mismatching amount
        record = PaymentReconciliation.objects.get(attempt=self.attempt)                 # the SAME record is upgraded, not duplicated
        self.assertEqual((record.kind, record.evidence_level), ("amount_mismatch", "confirmed"))
        self.assertEqual(PaymentAttempt.objects.get(pk=self.attempt.pk).status, PaymentAttempt.Status.SUCCEEDED)   # provider money moved: evidence kept

    def test_recovery_is_tenant_scoped(self):
        self.make_unknown()
        from apps.stores.models import Store
        other = Store.objects.create(name="Other", slug="unk-other", status=Store.Status.ACTIVE)
        with patch(INQUIRE, return_value=inquiry("SETTLE", settled=True)) as inq:
            self.assertIsNone(resolve_unknown_payment(self.attempt.pk, store=other))
        self.assertFalse(inq.called)
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)

    def test_management_command_resolves_in_bulk_and_respects_min_age(self):
        from django.core.management import call_command
        from io import StringIO
        self.make_unknown()
        out = StringIO()
        with patch(INQUIRE, return_value=inquiry("SETTLE", settled=True)):
            call_command("reconcile_unknown_payments", "--min-age-minutes", "60", stdout=out)   # too fresh: skipped
            self.assertIn("'checked': 0", out.getvalue())
            call_command("reconcile_unknown_payments", "--min-age-minutes", "0", stdout=out)
        self.assertIn("'paid': 1", out.getvalue())
        self.reload()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)

    def test_a_canceled_order_gets_a_reconciliation_not_a_reopened_order(self):
        self.make_unknown()
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.CANCELED)
        with patch(INQUIRE, return_value=inquiry("SETTLE", settled=True)):
            resolve_unknown_payment(self.attempt.pk)
        self.reload()
        self.assertEqual(self.order.status, Order.Status.CANCELED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(Transaction.objects.filter(order=self.order).count(), 0)
        self.assertTrue(PaymentReconciliation.objects.filter(attempt=self.attempt).exists())


class ConcurrentRecoveryTests(TransactionTestCase):
    """Competing recovery workers on a real database: the order is paid once (row locks => PostgreSQL)."""

    serialized_rollback = True

    def test_two_workers_resolve_the_same_unknown_attempt_once(self):
        if connection.vendor != "postgresql":
            self.skipTest("real row locks need PostgreSQL (run with DATABASE_URL=postgres://…)")
        base = UncertaintyBase()
        base.setUp()
        base.make_unknown()
        results, barrier = [], threading.Barrier(2)

        def worker():
            from django.db import connections
            try:
                barrier.wait(timeout=10)
                with patch(INQUIRE, return_value=inquiry("SETTLE", settled=True, ref="REF-C")):
                    results.append(resolve_unknown_payment(base.attempt.pk).status)
            except Exception as exc:  # noqa: BLE001
                results.append(type(exc).__name__)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        [t.start() for t in threads]; [t.join(60) for t in threads]
        self.assertEqual(results, [PaymentAttempt.Status.SUCCEEDED] * 2, results)
        self.assertEqual(Transaction.objects.filter(order=base.order, status="ok").count(), 1)
        self.assertEqual(Order.objects.get(pk=base.order.pk).payment_status, Order.PaymentStatus.PAID)


class VerifyFailureConfirmationTests(UncertaintyBase):
    """A repeated verify can answer "unsuccessful" for a payment the provider already verified (crash/retry). Two-step providers are
    asked for their status before anything is called a failure."""

    def fail_verify(self):
        from apps.orders.gateways.base import PaymentVerificationResult
        return PaymentVerificationResult(success=False, status_code=0, message="verify unsuccessful")

    def test_verify_unsuccessful_but_provider_says_verified_continues_to_settle_and_pays_once(self):
        _r, error, (_v, settle, _i) = self.callback(verify=self.fail_verify(), inq=inquiry("VERIFY", ref="REF-V"),
                                                    settle=PaymentSettleResult(success=True, settle_ref="S", status_code=100))
        self.assertIsNone(error)
        self.reload()
        self.assertEqual((settle.call_count, self.order.payment_status), (1, Order.PaymentStatus.PAID))
        self.assertEqual(Transaction.objects.filter(order=self.order, status="ok").count(), 1)

    def test_verify_unsuccessful_but_provider_says_already_settled_pays_without_settling_again(self):
        _r, error, (_v, settle, _i) = self.callback(verify=self.fail_verify(), inq=inquiry("SETTLE", settled=True, ref="REF-S"))
        self.assertIsNone(error)
        self.reload()
        self.assertEqual((settle.call_count, self.order.payment_status), (0, Order.PaymentStatus.PAID))

    def test_verify_unsuccessful_and_provider_says_not_paid_is_a_definitive_failure(self):
        _r, error, _ = self.callback(verify=self.fail_verify(), inq=inquiry("PENDING"), data={"state": "FAILED"})
        self.assertIsInstance(error, PaymentVerificationFailed)
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(self.payment_failed_events(), 1)
        self.assert_untouched_order()

    def test_a_callback_that_claims_success_is_never_announced_as_a_customer_failure(self):
        _r, error, _ = self.callback(verify=self.fail_verify(), inq=inquiry("PENDING"))        # callback body says state=OK
        self.assertIsInstance(error, PaymentVerificationFailed)
        self.assertEqual(self.payment_failed_events(), 0)

    def test_verify_unsuccessful_with_an_unreadable_status_fails_the_attempt_without_a_failure_alert(self):
        _r, error, _ = self.callback(verify=self.fail_verify(), inq_exc=GatewayConnectionError("down"))
        self.assertIsInstance(error, PaymentVerificationFailed)
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(self.payment_failed_events(), 0)                                # cannot tell "never paid" from "paid, unreadable"

    def test_a_callback_that_claims_success_is_never_a_definitive_failure_for_any_provider_shape(self):
        for data in ({"state": "OK"}, {"Status": "OK"}, {"success": "1"}, {"status": "2"}, {"state": "SUCCESS"}):
            self.assertTrue(PaymentGatewayConfig(gateway_code="snappay") and __import__("apps.orders.services.gateway_payment_service", fromlist=["x"])._callback_claims_success(data))
        for data in ({"state": "FAILED"}, {"Status": "NOK"}, {"success": "0"}, {}):
            self.assertFalse(__import__("apps.orders.services.gateway_payment_service", fromlist=["x"])._callback_claims_success(data))


class CustomerFacingOutcomeTests(UncertaintyBase):
    def test_the_callback_view_tells_the_customer_not_to_pay_again_and_never_500s(self):
        from django.contrib.messages import get_messages
        client = Client()
        client.force_login(self.order.customer.user)                                     # the result page is the customer's own
        with patch(VERIFY, return_value=verify_ok()), patch(SETTLE, side_effect=GatewayConnectionError("t")), patch(INQUIRE, side_effect=GatewayConnectionError("d")):
            response = client.post(reverse("orders:gateway-callback", args=[self.attempt.public_id]), CALLBACK, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("دوباره پرداخت نکنید" in str(m) for m in get_messages(response.wsgi_request)))
        self.reload()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assert_untouched_order()
