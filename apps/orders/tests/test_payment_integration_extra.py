"""FEAT-007 — cross-blocker end-to-end integration tests.

These complement the per-blocker modules (test_payment_redirect_integration,
test_callback_integration, test_card_to_card_confirmation, test_idempotency_tenant,
test_bnpl_cart_reconciliation) with the two scenarios the reviewer called out
that were not yet directly proven end-to-end:

1. PAYMENT RETRY. A first payment attempt that FAILS (gateway create rejected)
   must be retryable: a second initiation for the SAME operation initiates
   correctly (a fresh live attempt), and the new idempotency rules do not let
   the dead attempt's key block the retry. We prove it at two levels:
     * the orchestration service ``initiate_payment`` directly, with a reused
       deterministic idempotency key (the exact key the real view builds), and
     * the REAL Django ``orders:payment-initiate`` view end-to-end (mocked
       gateway) so the full view -> service -> persistence -> redirect path is
       exercised, including the deterministic-key retry path.

2. FAILED BNPL SETTLEMENT. For a capability-gated BNPL provider (SnappPay /
   TorobPay) whose ``verify_payment`` succeeds but whose ``settle_payment``
   FAILS (or raises), the order must NOT be finalized: it stays PENDING, the
   attempt is not SUCCEEDED, and NO OK Transaction is written. Money is only
   considered captured once settle succeeds. We drive the REAL public callback
   view so the whole HTTP -> orchestrator -> capability-gated settle path runs.

Duplicate callback and cross-tenant callback rejection are already proven in
test_callback_integration.py (DuplicateCallbackTests, CrossTenantCallbackTests);
this module does not duplicate them.

Every gateway HTTP call is MOCKED — no external network. We patch the adapter
methods (create_payment / verify_payment / settle_payment) that the orchestrator
reaches through ``get_adapter``.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import Client
from django.urls import reverse

from apps.orders.gateways.base import (
    GatewayError,
    PaymentCreationResult,
    PaymentSettleResult,
    PaymentVerificationResult,
)
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGatewayConfig,
    Transaction,
)
from apps.orders.services.gateway_payment_service import (
    PaymentInitiationError,
    PaymentVerificationFailed,
    initiate_payment,
    process_callback_and_verify,
)
from apps.orders.tests.test_lifecycle import LifecycleBase

SNAPPAY_CREDS = {"client_id": "snapp-client", "client_secret": "s3cr3t"}
TOROBPAY_CREDS = {
    "client_id": "torob-client",
    "client_secret": "t0p-s3cr3t",
    "client_username": "merchant",
    "client_password": "p@ss",
}
ZIBAL_CREDS = {"merchant": "zbl-merchant"}

SNAPPAY_CALLBACK_OK = {
    "transactionId": "SP-TXN-EXTRA",
    "state": "OK",
    "amount": "1000000",
}


def verify_ok(ref="REF-OK"):
    return PaymentVerificationResult(success=True, ref_id=ref, status_code=100, message="ok")


def settle_ok(ref="SETTLE-OK"):
    return PaymentSettleResult(success=True, settle_ref=ref, status_code=100, message="settled")


def settle_fail():
    return PaymentSettleResult(success=False, settle_ref="", status_code=0, message="settle rejected")


class IntegrationExtraBase(LifecycleBase):
    """Shared helpers to build ready gateway configs and attempts."""

    def _ready_config(self, gateway_code, creds, *, sandbox=False):
        config = PaymentGatewayConfig.objects.create(
            store=self.store,
            gateway_code=gateway_code,
            is_active=True,
            is_sandbox=sandbox,
        )
        config.set_credentials(creds)
        config.save()
        return config

    def _attempt(self, order, config, *, track, status=PaymentAttempt.Status.REDIRECT_READY):
        return PaymentAttempt.objects.create(
            store=self.store,
            order=order,
            gateway_config=config,
            amount=order.grand_total,
            currency="TOMAN",
            status=status,
            gateway_track_id=track,
        )

    def _callback_url(self, attempt):
        return reverse("orders:gateway-callback", args=[attempt.public_id])

    def _post_callback(self, attempt, data):
        client = Client()
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(self._callback_url(attempt), data)


# ---------------------------------------------------------------------------
# 1. Payment retry after a failed attempt
# ---------------------------------------------------------------------------


class PaymentRetryServiceTests(IntegrationExtraBase):
    """A FAILED attempt can be retried through the orchestration service."""

    def _deterministic_key(self, order, config):
        """Mirror the key the real view builds from the operation identity."""
        import hashlib

        seed = f"{self.store.pk}:{order.code}:{config.pk}:{order.grand_total}"
        return f"pay-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:48]}"

    def test_retry_after_failed_create_initiates_a_fresh_live_attempt(self):
        config = self._ready_config("zibal", ZIBAL_CREDS)
        order = self.new_order()
        key = self._deterministic_key(order, config)

        # First initiation: the gateway create is rejected -> attempt FAILED.
        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            side_effect=GatewayError("gateway down", code="gw_down"),
        ):
            with self.assertRaises(PaymentInitiationError):
                initiate_payment(
                    order=order, gateway_config=config,
                    callback_url="https://x/cb", store=self.store,
                    idempotency_key=key,
                )
        first = PaymentAttempt.objects.get(order=order)
        self.assertEqual(first.status, PaymentAttempt.Status.FAILED)

        # Retry the SAME operation with the SAME deterministic key. The dead
        # attempt's key must not block the retry.
        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            return_value=PaymentCreationResult(
                track_id="ZBL-RETRY-OK", gateway_url=None, extra=None
            ),
        ):
            retried = initiate_payment(
                order=order, gateway_config=config,
                callback_url="https://x/cb", store=self.store,
                idempotency_key=key,
            )

        self.assertNotEqual(retried.pk, first.pk)
        self.assertEqual(retried.status, PaymentAttempt.Status.REDIRECT_READY)
        self.assertEqual(retried.gateway_track_id, "ZBL-RETRY-OK")
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 2)
        # The retry minted a distinct (deterministic) key, never the dead one.
        self.assertNotEqual(retried.idempotency_key, first.idempotency_key)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_retry_then_callback_finalizes_order_exactly_once(self):
        config = self._ready_config("zibal", ZIBAL_CREDS)
        order = self.new_order()
        key = self._deterministic_key(order, config)

        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            side_effect=GatewayError("gateway down", code="gw_down"),
        ):
            with self.assertRaises(PaymentInitiationError):
                initiate_payment(
                    order=order, gateway_config=config,
                    callback_url="https://x/cb", store=self.store,
                    idempotency_key=key,
                )

        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            return_value=PaymentCreationResult(
                track_id="ZBL-RETRY-FIN", gateway_url=None, extra=None
            ),
        ):
            retried = initiate_payment(
                order=order, gateway_config=config,
                callback_url="https://x/cb", store=self.store,
                idempotency_key=key,
            )

        # The retried attempt's callback verifies and finalizes the order once.
        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.verify_payment",
            return_value=verify_ok(),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                process_callback_and_verify(
                    attempt_public_id=retried.public_id,
                    callback_data={"trackId": "ZBL-RETRY-FIN", "success": "1"},
                    store=self.store,
                )

        order.refresh_from_db()
        retried.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(retried.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1
        )


class PaymentRetryViewTests(IntegrationExtraBase):
    """End-to-end retry through the real payment-initiate view."""

    def _post_initiate(self, order):
        client = Client()
        client.force_login(self.customer.user)
        return client.post(reverse("orders:payment-initiate", args=[order.code]))

    def test_view_retry_after_failed_create_redirects_and_makes_new_attempt(self):
        # A selectable online config the view will auto-pick.
        self._ready_config("zibal", ZIBAL_CREDS)
        order = self.new_order()

        # First POST: gateway create fails -> the view renders the error page
        # (HTTP 200) and the attempt is FAILED.
        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            side_effect=GatewayError("gateway down", code="gw_down"),
        ):
            first_response = self._post_initiate(order)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(
            PaymentAttempt.objects.filter(
                order=order, status=PaymentAttempt.Status.FAILED
            ).count(),
            1,
        )

        # Second POST (customer hits "retry"): the view builds the SAME
        # deterministic key, the service skips the dead attempt and initiates a
        # fresh one, and the customer is redirected to the gateway (HTTP 302).
        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.create_payment",
            return_value=PaymentCreationResult(
                track_id="ZBL-VIEW-RETRY", gateway_url=None, extra=None
            ),
        ):
            second_response = self._post_initiate(order)

        self.assertEqual(second_response.status_code, 302)
        self.assertIn("ZBL-VIEW-RETRY", second_response["Location"])
        live = PaymentAttempt.objects.filter(
            order=order, status=PaymentAttempt.Status.REDIRECT_READY
        )
        self.assertEqual(live.count(), 1)
        self.assertEqual(live.first().gateway_track_id, "ZBL-VIEW-RETRY")
        # Two attempts total: the dead FAILED one and the live retry.
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 2)


# ---------------------------------------------------------------------------
# 2. Failed BNPL settlement must not finalize the order
# ---------------------------------------------------------------------------


class FailedSettlementTests(IntegrationExtraBase):
    """verify succeeds but settle fails -> order stays PENDING, no OK Transaction."""

    def setUp(self):
        super().setUp()
        # Hermetic: the provider status inquiry that follows an unproven settle must never reach a real network.
        from apps.orders.gateways.base import PaymentInquiryResult

        for target in ("apps.orders.gateways.snappay.SnappPayAdapter.inquire_payment", "apps.orders.gateways.torobpay.TorobPayAdapter.inquire_payment"):
            patcher = patch(target, return_value=PaymentInquiryResult(paid=True, settled=False, status="VERIFY"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def _assert_not_finalized(self, order, attempt):
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertNotEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 0
        )
        self.assertEqual(Transaction.objects.filter(order=order).count(), 0)

    def test_snappay_settle_failure_does_not_finalize_via_callback_view(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-SETTLE-FAIL-1")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ) as verify, patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_fail(),
        ) as settle:
            response = self._post_callback(attempt, SNAPPAY_CALLBACK_OK)

        # The view never crashes; it redirects to the result page.
        self.assertEqual(response.status_code, 302)
        # verify ran and reported success; settle ran and reported failure.
        self.assertTrue(verify.called)
        self.assertTrue(settle.called)
        # Despite a successful verify, a failed settle blocks finalization.
        self._assert_not_finalized(order, attempt)

    def test_snappay_settle_raising_does_not_finalize_via_callback_view(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-SETTLE-FAIL-2")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ), patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            side_effect=GatewayError("settle exploded", code="settle_error"),
        ) as settle:
            response = self._post_callback(attempt, SNAPPAY_CALLBACK_OK)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(settle.called)
        self._assert_not_finalized(order, attempt)

    def test_torobpay_settle_rejection_is_uncertain_not_a_definitive_failure(self):
        """A bare ``success=False`` settle answer is NOT proof the money did not move: when the provider's own status cannot
        confirm a terminal negative, the verified attempt is UNKNOWN (needs reconciliation) — never FAILED, never an order paid,
        and no ``payment.failed``."""
        from apps.notifications.models import NotificationEvent
        from apps.orders.gateways.base import PaymentInquiryResult

        config = self._ready_config("torobpay", TOROBPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="TP-SETTLE-FAIL-1")

        with patch(
            "apps.orders.gateways.torobpay.TorobPayAdapter.verify_payment",
            return_value=verify_ok(),
        ), patch(
            "apps.orders.gateways.torobpay.TorobPayAdapter.settle_payment",
            return_value=settle_fail(),
        ) as settle, patch(
            "apps.orders.gateways.torobpay.TorobPayAdapter.inquire_payment",
            return_value=PaymentInquiryResult(paid=True, settled=False, status="VERIFY"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                result = process_callback_and_verify(
                    attempt_public_id=attempt.public_id,
                    callback_data={"transactionId": "TP-SETTLE-FAIL-1", "state": "OK"},
                    store=self.store,
                )

        self.assertTrue(settle.called)
        self._assert_not_finalized(order, attempt)
        attempt.refresh_from_db()
        self.assertEqual(result.pk, attempt.pk)
        self.assertEqual(attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assertEqual(attempt.failure_code, "settle_uncertain")
        self.assertFalse(NotificationEvent.objects.filter(type_key="payment.failed").exists())
        self.assertTrue(NotificationEvent.objects.filter(type_key="payment.suspicious").exists())

    def test_successful_settle_finalizes_as_a_control(self):
        """Control: with settle succeeding the SAME flow DOES finalize, proving
        the non-finalization above is caused by the settle failure alone."""
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-SETTLE-OK-1")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ), patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_ok(),
        ):
            response = self._post_callback(attempt, SNAPPAY_CALLBACK_OK)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1
        )
