"""Round 3, issue 1: operation-level reuse must not depend on the verbatim key string.

Sequence: attempt A (key K) FAILS; retry with K creates B under a disambiguated
key K2 (REDIRECT_READY); a third call with K must return B, not create C and not
call create_payment again.
"""

from unittest.mock import patch

from apps.orders.models import Order, PaymentAttempt
from apps.orders.services.gateway_payment_service import (
    PaymentAlreadyPaidError,
    PaymentInitiationError,
    initiate_payment,
)
from apps.orders.gateways.base import GatewayError
from apps.orders.tests.test_idempotency_tenant import SERVICE, IdempotencyTenantBase, mock_online_adapter

S = PaymentAttempt.Status


class FailedRetryReuseTests(IdempotencyTenantBase):
    def _init(self, key, order=None, config=None, store=None):
        return initiate_payment(
            order=order or self.order_a, gateway_config=config or self.config_a,
            callback_url="https://a.example/cb", store=store or self.store_a,
            idempotency_key=key,
        )

    def test_third_call_with_original_key_returns_retry_attempt(self):
        key = "pay-ROUND3-K"
        adapter = mock_online_adapter()
        good = adapter.create_payment.side_effect
        adapter.create_payment.side_effect = GatewayError("boom")
        with patch(SERVICE, return_value=adapter):
            with self.assertRaises(PaymentInitiationError):
                self._init(key)
            a = PaymentAttempt.objects.get(order=self.order_a)
            self.assertEqual(a.status, S.FAILED)
            self.assertEqual(a.idempotency_key, key)

            adapter.create_payment.side_effect = good
            b = self._init(key)
            self.assertNotEqual(a.pk, b.pk)
            self.assertEqual(b.status, S.REDIRECT_READY)
            self.assertNotEqual(b.idempotency_key, key)  # K2
            calls = adapter.create_payment.call_count

            c = self._init(key)
            d = self._init("pay-some-other-string")
        self.assertEqual(c.pk, b.pk)
        self.assertEqual(d.pk, b.pk)
        self.assertEqual(adapter.create_payment.call_count, calls)
        self.assertEqual(PaymentAttempt.objects.filter(order=self.order_a).count(), 2)
        self.assertEqual(
            PaymentAttempt.objects.filter(order=self.order_a, status=S.REDIRECT_READY).count(), 1
        )

    def test_terminal_failure_still_allows_retry(self):
        for terminal in (S.FAILED, S.CANCELED, S.EXPIRED):
            PaymentAttempt.objects.filter(order=self.order_a).delete()
            PaymentAttempt.objects.create(
                store=self.store_a, order=self.order_a, gateway_config=self.config_a,
                amount=self.order_a.grand_total, currency="TOMAN", status=terminal,
                idempotency_key="pay-T",
            )
            adapter = mock_online_adapter()
            with patch(SERVICE, return_value=adapter):
                new = self._init("pay-T")
            self.assertEqual(new.status, S.REDIRECT_READY, terminal)
            self.assertEqual(adapter.create_payment.call_count, 1, terminal)

    def test_foreign_tenant_attempt_never_returned_for_same_key(self):
        with patch(SERVICE, return_value=mock_online_adapter()):
            a = self._init("pay-SHARED")
            b = self._init("pay-SHARED", order=self.order_b, config=self.config_b, store=self.store_b)
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(b.store_id, self.store_b.pk)

    def test_succeeded_attempt_is_returned_not_recharged_and_paid_order_rejected(self):
        done = PaymentAttempt.objects.create(
            store=self.store_a, order=self.order_a, gateway_config=self.config_a,
            amount=self.order_a.grand_total, currency="TOMAN", status=S.SUCCEEDED,
            idempotency_key="pay-DONE", gateway_track_id="trk-done",
        )
        adapter = mock_online_adapter()
        with patch(SERVICE, return_value=adapter):
            self.assertEqual(self._init("pay-other").pk, done.pk)
            self.assertEqual(adapter.create_payment.call_count, 0)
            Order.objects.filter(pk=self.order_a.pk).update(payment_status=Order.PaymentStatus.PAID)
            with self.assertRaises(PaymentAlreadyPaidError):
                self._init("pay-other")
        self.assertEqual(adapter.create_payment.call_count, 0)
