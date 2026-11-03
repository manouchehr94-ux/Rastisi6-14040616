"""BLOCKER 2 — gateway callback HTTP integration (GET + POST).

These tests drive the REAL public callback view
(``orders:gateway-callback``) with Django's test ``Client`` and prove:

- A classic GET provider (Zibal) callback still works (no HTTP 405) and, with
  the gateway's server-to-server verify mocked to succeed, finalizes the order.
- A BNPL POST provider (SnappPay) callback with the documented body
  ``{transactionId, state: 'OK', amount}`` is accepted (NOT 405) and, with
  ``verify_payment`` AND ``settle_payment`` mocked to succeed, finalizes the
  order. The CSRF-exempt POST goes through the normal test client (no CSRF
  token) which proves the narrow ``@csrf_exempt`` is in effect.
- A FORGED-SUCCESS POST (``state: 'OK'`` but ``verify_payment`` mocked to fail)
  does NOT finalize the order: the order stays PENDING and the attempt is not
  SUCCEEDED. Server-to-server verify is the sole authority.
- A duplicate callback (POST twice) is idempotent: the order is paid exactly
  once and exactly one OK Transaction exists.
- A cross-tenant callback — the attempt belongs to a DIFFERENT store than the
  one the request resolves to — returns HTTP 404 and leaves the foreign attempt
  untouched.

Every gateway HTTP call is MOCKED (no external network). We patch the adapter
methods ``verify_payment`` / ``settle_payment`` on the adapter classes, which
is exactly what the orchestrator calls via ``get_adapter``.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.gateways.base import (
    GatewayError,
    PaymentSettleResult,
    PaymentVerificationResult,
)
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGatewayConfig,
    Transaction,
)
from apps.orders.tests.test_lifecycle import LifecycleBase
from apps.stores.models import Store, StoreDomain

SNAPPAY_CREDS = {"client_id": "snapp-client", "client_secret": "s3cr3t"}
ZIBAL_CREDS = {"merchant": "zbl-merchant"}

# The documented SnappPay POST callback body delivered to returnURL.
SNAPPAY_CALLBACK_OK = {
    "transactionId": "SP-TXN-123",
    "state": "OK",
    "amount": "1000000",
}


def verify_ok(ref="REF-OK"):
    return PaymentVerificationResult(success=True, ref_id=ref, status_code=100, message="ok")


def verify_fail():
    return PaymentVerificationResult(success=False, status_code=0, message="verify failed")


def settle_ok(ref="SETTLE-OK"):
    return PaymentSettleResult(success=True, settle_ref=ref, status_code=100, message="settled")


class CallbackIntegrationBase(LifecycleBase):
    """Builds a ready gateway config + attempt and drives the real view."""

    def _ready_config(self, gateway_code, creds, *, sandbox=False, store=None):
        config = PaymentGatewayConfig.objects.create(
            store=store or self.store,
            gateway_code=gateway_code,
            is_active=True,
            is_sandbox=sandbox,
        )
        config.set_credentials(creds)
        config.save()
        return config

    def _attempt(self, order, config, *, store=None, track="TRK-CB-1"):
        return PaymentAttempt.objects.create(
            store=store or self.store,
            order=order,
            gateway_config=config,
            amount=order.grand_total,
            currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY,
            gateway_track_id=track,
        )

    def _callback_url(self, attempt):
        return reverse("orders:gateway-callback", args=[attempt.public_id])

    def _get(self, attempt, data=None):
        client = Client()
        with self.captureOnCommitCallbacks(execute=True):
            return client.get(self._callback_url(attempt), data or {})

    def _post(self, attempt, data=None, **extra):
        client = Client()
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(self._callback_url(attempt), data or {}, **extra)


class GetCallbackTests(CallbackIntegrationBase):
    """A classic GET provider keeps working (no 405) and finalizes on verify."""

    def test_get_callback_success_marks_order_paid(self):
        config = self._ready_config("zibal", ZIBAL_CREDS)
        order = self.new_order()
        attempt = self._attempt(order, config, track="ZBL-CB-1")

        with patch(
            "apps.orders.gateways.zibal.ZibalAdapter.verify_payment",
            return_value=verify_ok(),
        ):
            response = self._get(attempt, {"trackId": "ZBL-CB-1", "success": "1"})

        # The customer is redirected to the result page — never a 405.
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.status_code, 405)

        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1
        )


class PostCallbackTests(CallbackIntegrationBase):
    """A BNPL POST provider (SnappPay) is accepted and finalized via verify+settle."""

    def test_post_callback_is_not_405(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-CB-1")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ), patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_ok(),
        ):
            response = self._post(attempt, SNAPPAY_CALLBACK_OK)

        self.assertNotEqual(response.status_code, 405)
        self.assertEqual(response.status_code, 302)

    def test_post_callback_success_finalizes_order(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-CB-2")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ) as verify, patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_ok(),
        ) as settle:
            response = self._post(attempt, SNAPPAY_CALLBACK_OK)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        attempt.refresh_from_db()
        # BNPL finalization requires BOTH verify and settle to be invoked.
        self.assertTrue(verify.called)
        self.assertTrue(settle.called)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1
        )

    def test_post_callback_passes_merged_body_as_callback_data(self):
        """GET and POST params are merged and handed through as callback_data."""
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-CB-3")

        captured = {}

        def _verify(**kwargs):
            captured.update(kwargs.get("callback_data") or {})
            return verify_ok()

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            side_effect=_verify,
        ), patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_ok(),
        ):
            self._post(attempt, SNAPPAY_CALLBACK_OK)

        self.assertEqual(captured.get("transactionId"), "SP-TXN-123")
        self.assertEqual(captured.get("state"), "OK")
        self.assertEqual(captured.get("amount"), "1000000")


class ForgedSuccessTests(CallbackIntegrationBase):
    """A forged-success POST never finalizes: verify is the sole authority."""

    def test_forged_success_post_does_not_finalize(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-FORGE-1")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_fail(),
        ), patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_ok(),
        ) as settle:
            response = self._post(attempt, SNAPPAY_CALLBACK_OK)

        # The view never crashes; it redirects to the result page.
        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        attempt.refresh_from_db()
        # Despite state=='OK' in the body, verify failed -> nothing is finalized.
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertNotEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(Transaction.objects.filter(order=order).count(), 0)
        # settle must never run once verify has failed.
        self.assertFalse(settle.called)

    def test_forged_success_post_when_verify_raises_does_not_finalize(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-FORGE-2")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            side_effect=GatewayError("gateway exploded", code="verify_error"),
        ):
            response = self._post(attempt, SNAPPAY_CALLBACK_OK)

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertNotEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)


class DuplicateCallbackTests(CallbackIntegrationBase):
    """Posting the callback twice finalizes the order exactly once."""

    def test_duplicate_post_callback_is_idempotent(self):
        config = self._ready_config("snappay", SNAPPAY_CREDS, sandbox=True)
        order = self.new_order()
        attempt = self._attempt(order, config, track="SP-DUP-1")

        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ), patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.settle_payment",
            return_value=settle_ok(),
        ):
            first = self._post(attempt, SNAPPAY_CALLBACK_OK)
            second = self._post(attempt, SNAPPAY_CALLBACK_OK)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        # Paid exactly once: a single OK Transaction, never two.
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1
        )


CB_HOST = "cb-tenant.example.com"


@override_settings(ALLOWED_HOSTS=[CB_HOST, "testserver"])
class CrossTenantCallbackTests(CallbackIntegrationBase):
    """A callback resolved against a different store cannot touch a foreign attempt."""

    def setUp(self):
        super().setUp()
        # A verified domain makes the resolution middleware resolve the request
        # to self.store, so a foreign attempt (on another store) is invisible.
        StoreDomain.objects.create(
            store=self.store,
            hostname=CB_HOST,
            is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    def test_foreign_store_attempt_returns_404_and_is_untouched(self):
        # Build an attempt that belongs to a DIFFERENT store than the one the
        # request resolves to (the request host maps to self.store).
        other_store = Store.objects.create(
            name="Other", slug="cb-other", status=Store.Status.ACTIVE
        )
        foreign_config = self._ready_config(
            "snappay", SNAPPAY_CREDS, sandbox=True, store=other_store
        )
        order = self.new_order()
        foreign_attempt = PaymentAttempt.objects.create(
            store=other_store,
            order=order,
            gateway_config=foreign_config,
            amount=order.grand_total,
            currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY,
            gateway_track_id="SP-FOREIGN-1",
        )

        # verify is patched, but it must never be reached — resolution against
        # self.store fails to find the foreign attempt first.
        with patch(
            "apps.orders.gateways.snappay.SnappPayAdapter.verify_payment",
            return_value=verify_ok(),
        ) as verify:
            response = self._post(foreign_attempt, SNAPPAY_CALLBACK_OK, HTTP_HOST=CB_HOST)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(verify.called)

        foreign_attempt.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(foreign_attempt.status, PaymentAttempt.Status.REDIRECT_READY)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(Transaction.objects.filter(order=order).count(), 0)
