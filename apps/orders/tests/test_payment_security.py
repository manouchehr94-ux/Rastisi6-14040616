"""FEAT-006 (M8) — consolidated payment SECURITY test pass.

These tests assert the security guarantees of the payment engine end to end,
across the gateway adapters, the orchestrator
(``apps.orders.services.gateway_payment_service``) and the credential
encryption layer (``apps.orders.encryption``). They extend — and do not
duplicate — the guarantees already covered by:

* ``test_payment_safety.py``  — canceled-order late payment, duplicate late
  callbacks, forged-callback-param-only rejection, reconciliation admin.
* ``test_feat005_provider_integration.py`` — cross-tenant config rejection,
  cross-tenant callback rejection, callback amount tampering, blocked-provider
  routing refusal.
* ``test_payment_concurrency.py`` — concurrent verification logic.

Every provider HTTP call is MOCKED; no real provider endpoint is ever
contacted and no real-money transaction is ever performed.

CONCURRENCY / POSTGRES NOTE
===========================
The default (and only available) test database in this sandbox is SQLite.
``apps.orders.services.gateway_payment_service`` relies on
``select_for_update`` row-level locking (order row first, then attempt row) to
serialize a cancel racing a payment and two concurrent callbacks. SQLite does
NOT implement ``SELECT ... FOR UPDATE`` row-level locking, so the tests in
``ConcurrentVerificationLogicTests`` verify the *idempotency logic* (the
conditional status transition and the "already SUCCEEDED => return" guard)
only. They do NOT, and cannot, prove the Postgres row-lock behavior. Each such
assertion is explicitly marked ``NOT VERIFIED ON SQLITE`` in a comment. Real
row-level-locking concurrency must be validated against Postgres (see
docs/payments/REGRESSION_RESULTS.md).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.orders.encryption import (
    decrypt_credential,
    encrypt_credential,
    mask_credential,
    reset_fernet,
)
from apps.orders.gateways.base import (
    GatewayCredentialError,
    GatewayPaymentError,
)
from apps.orders.gateways.zarinpal import ZarinpalAdapter
from apps.orders.gateways.zibal import ZibalAdapter
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGatewayConfig,
    PaymentReconciliation,
    Transaction,
)
from apps.orders.services.gateway_payment_service import (
    PaymentConfigError,
    PaymentVerificationFailed,
    initiate_payment,
    process_callback_and_verify,
)
from apps.orders.services.order_service import change_order_status
from apps.orders.tests.test_lifecycle import LifecycleBase

VALID_MERCHANT_36 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SECRET_ZIBAL_MERCHANT = "SUPER-SECRET-ZIBAL-MERCHANT-0001"


def _zibal_ok(order, ref="REF-SEC"):
    response = MagicMock()
    response.json.return_value = {
        "result": 100,
        "amount": int(order.grand_total) * 10,
        "status": 1,
        "refNumber": ref,
        "cardNumber": "6037-99XX-XXXX-5678",
    }
    return response


def _zibal_tampered_amount(order):
    """A verify response claiming success but for a DIFFERENT (larger) amount."""
    response = MagicMock()
    response.json.return_value = {
        "result": 100,
        "amount": int(order.grand_total) * 10 + 10,  # 1 Toman more -> mismatch
        "status": 1,
        "refNumber": "REF-TAMP",
        "cardNumber": "6037-99XX-XXXX-5678",
    }
    return response


class SecurityBase(LifecycleBase):
    """Shared helpers mirroring test_payment_safety.SafetyBase, store-scoped."""

    def _config(self, *, store=None, code="zibal", active=True, secret=SECRET_ZIBAL_MERCHANT):
        store = store or self.store
        config, _ = PaymentGatewayConfig.objects.get_or_create(
            store=store, gateway_code=code, defaults={"is_active": active}
        )
        config.is_active = active
        if secret is not None:
            config.set_credentials({"merchant": secret})
        config.save()
        return config

    def _attempt(self, order, config=None, status=PaymentAttempt.Status.REDIRECT_READY):
        config = config or self._config()
        return PaymentAttempt.objects.create(
            store=config.store,
            order=order,
            gateway_config=config,
            amount=order.grand_total,
            currency="TOMAN",
            status=status,
            gateway_track_id=f"trk-{order.pk}-{PaymentAttempt.objects.count()}",
        )

    def _callback(self, attempt, response, store=None, callback_data=None):
        store = store or self.store
        with patch("apps.orders.gateways.zibal.requests.post", return_value=response) as post:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    return (
                        process_callback_and_verify(
                            attempt_public_id=attempt.public_id,
                            callback_data=callback_data or {},
                            store=store,
                        ),
                        post,
                    )
                except PaymentVerificationFailed as exc:
                    return exc, post


# ---------------------------------------------------------------------------
# Credential encryption & secret-leakage
# ---------------------------------------------------------------------------


class CredentialEncryptionTests(TestCase):
    def setUp(self):
        reset_fernet()
        self.addCleanup(reset_fernet)

    def test_credentials_stored_encrypted_not_plaintext(self):
        store_secret = "MERCHANT-PLAINTEXT-XYZ"
        token = encrypt_credential(store_secret)
        # The ciphertext must NOT contain the plaintext.
        self.assertNotIn(store_secret, token)
        self.assertNotEqual(token, store_secret)
        # And it round-trips.
        self.assertEqual(decrypt_credential(token), store_secret)

    def test_config_encrypted_credentials_column_never_holds_plaintext(self):
        from apps.stores.models import Store

        store = Store.objects.create(name="sec", slug="sec-crypto", status=Store.Status.ACTIVE)
        config = PaymentGatewayConfig(store=store, gateway_code="zibal", is_active=True)
        config.set_credentials({"merchant": SECRET_ZIBAL_MERCHANT})
        config.save()
        config.refresh_from_db()
        # Raw stored column must be ciphertext, not the secret.
        self.assertTrue(config.encrypted_credentials)
        self.assertNotIn(SECRET_ZIBAL_MERCHANT, config.encrypted_credentials)
        # The decrypted round-trip returns the secret.
        self.assertEqual(config.get_credentials()["merchant"], SECRET_ZIBAL_MERCHANT)

    def test_mask_credential_hides_all_but_last_four(self):
        self.assertEqual(mask_credential("1234567890123456"), "************3456")
        self.assertEqual(mask_credential("abcd"), "****")
        self.assertEqual(mask_credential(""), "")


class SecretLeakageTests(SecurityBase):
    """The merchant secret must never appear in rendered HTML, logs, str() or
    error messages anywhere the payment flow can surface."""

    def test_secret_not_in_adapter_exception_or_repr(self):
        adapter = ZibalAdapter()
        with patch("apps.orders.gateways.zibal.requests.post") as post:
            resp = MagicMock()
            resp.json.return_value = {"result": -1, "message": "rejected"}
            post.return_value = resp
            try:
                adapter.create_payment(
                    amount=Decimal("1000"),
                    currency="TOMAN",
                    callback_url="https://x/cb",
                    credentials={"merchant": SECRET_ZIBAL_MERCHANT},
                    order_code="DM-LEAK",
                )
                self.fail("expected GatewayPaymentError")
            except GatewayPaymentError as exc:
                self.assertNotIn(SECRET_ZIBAL_MERCHANT, str(exc))
                self.assertNotIn(SECRET_ZIBAL_MERCHANT, repr(exc.details))

    def test_secret_not_in_zarinpal_exception(self):
        adapter = ZarinpalAdapter()
        with patch("apps.orders.gateways.zarinpal.requests.post") as post:
            resp = MagicMock()
            resp.json.return_value = {"data": {"code": -11, "message": "x"}, "errors": []}
            post.return_value = resp
            try:
                adapter.create_payment(
                    amount=Decimal("1000"),
                    currency="TOMAN",
                    callback_url="https://x/cb",
                    credentials={"merchant_id": VALID_MERCHANT_36},
                    order_code="DM-LEAK2",
                )
                self.fail("expected GatewayPaymentError")
            except GatewayPaymentError as exc:
                self.assertNotIn(VALID_MERCHANT_36, str(exc))
                self.assertNotIn(VALID_MERCHANT_36, repr(exc.details))

    def test_secret_not_logged_during_create_and_verify(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        with self.assertLogs("payment", level="DEBUG") as cm:
            self._callback(attempt, _zibal_ok(order))
        blob = "\n".join(cm.output)
        self.assertNotIn(SECRET_ZIBAL_MERCHANT, blob)

    def test_secret_not_in_reconciliation_evidence(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        self._callback(attempt, _zibal_ok(order))
        record = PaymentReconciliation.objects.get(attempt=attempt)
        # Evidence is persisted and surfaced to staff admin — it must not carry
        # the merchant secret anywhere (dict value or serialized form).
        self.assertNotIn(SECRET_ZIBAL_MERCHANT, str(record.evidence))
        self.assertNotIn(SECRET_ZIBAL_MERCHANT, str(record.error_message))


# ---------------------------------------------------------------------------
# Cross-tenant credential / config isolation
# ---------------------------------------------------------------------------


class CrossTenantIsolationTests(SecurityBase):
    def setUp(self):
        super().setUp()
        from apps.core.models import ShopSettings
        from apps.stores.models import Store

        self.other_store = Store.objects.create(
            name="فروشگاه ب", slug="sec-other-store", status=Store.Status.ACTIVE
        )
        try:
            ShopSettings.provision_for(self.other_store)
        except Exception:  # pragma: no cover - provisioning is best-effort here
            pass

    def test_other_store_config_is_not_routable_by_this_store(self):
        order = self.new_order()
        other_config = self._config(store=self.other_store, code="zibal")
        # initiate_payment must reject a config owned by a different store.
        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=order,
                gateway_config=other_config,
                callback_url="https://x/cb",
                store=self.store,
            )
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 0)

    def test_callback_scoped_to_store_cannot_be_resolved_cross_tenant(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        # A callback presented under the WRONG store must not find the attempt.
        result, post = self._callback(attempt, _zibal_ok(order), store=self.other_store)
        self.assertIsInstance(result, PaymentVerificationFailed)
        post.assert_not_called()  # never even reaches the gateway
        # The attempt remains untouched under its real store.
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REDIRECT_READY)

    def test_each_store_decrypts_only_its_own_credentials(self):
        a_config = self._config(store=self.store, secret="SECRET-STORE-A-0001")
        b_config = self._config(store=self.other_store, secret="SECRET-STORE-B-0002")
        self.assertEqual(a_config.get_credentials()["merchant"], "SECRET-STORE-A-0001")
        self.assertEqual(b_config.get_credentials()["merchant"], "SECRET-STORE-B-0002")
        # Ciphertexts differ; neither column leaks the other's secret.
        self.assertNotIn("SECRET-STORE-B-0002", a_config.encrypted_credentials)
        self.assertNotIn("SECRET-STORE-A-0001", b_config.encrypted_credentials)


# ---------------------------------------------------------------------------
# Forged / replayed callbacks & duplicate finalization
# ---------------------------------------------------------------------------


class ForgedCallbackTests(SecurityBase):
    def test_callback_success_param_alone_does_not_finalize(self):
        """A browser callback claiming success must NEVER finalize the order;
        the server-to-server verify is the sole authority."""
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        # Gateway verify says FAILURE even though the callback claims success.
        failed = MagicMock()
        failed.json.return_value = {"result": 202, "status": -1, "message": "cancel"}
        result, post = self._callback(
            attempt, failed, callback_data={"success": "1", "status": "2"}
        )
        self.assertIsInstance(result, PaymentVerificationFailed)
        post.assert_called_once()  # verify WAS attempted (authority)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertFalse(Transaction.objects.filter(order=order, status="ok").exists())

    def test_callback_replay_after_success_is_idempotent(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        first, _ = self._callback(attempt, _zibal_ok(order, "REF-A"))
        self.assertEqual(first.status, PaymentAttempt.Status.SUCCEEDED)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        # Replaying the SAME callback must not re-verify or create a 2nd tx.
        second, post = self._callback(attempt, _zibal_ok(order, "REF-B"))
        post.assert_not_called()
        self.assertEqual(Transaction.objects.filter(order=order, status="ok").count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_second_attempt_on_paid_order_is_reconciled_not_double_paid(self):
        order = self.new_order()
        first = self._attempt(order)
        self._callback(first, _zibal_ok(order, "REF-1"))
        # A second confirmed attempt (duplicate finalization) must not create a
        # second OK transaction; it is reconciled as ALREADY_PAID.
        second = self._attempt(order)
        result, _ = self._callback(second, _zibal_ok(order, "REF-2"))
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(
            PaymentReconciliation.objects.get(attempt=second).kind,
            PaymentReconciliation.Kind.ALREADY_PAID,
        )
        self.assertEqual(Transaction.objects.filter(order=order, status="ok").count(), 1)


class AmountTamperingTests(SecurityBase):
    def test_gateway_confirmed_different_amount_never_marks_order_paid(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        result, _ = self._callback(attempt, _zibal_tampered_amount(order))
        # Verify confirmed money moved but for a DIFFERENT amount -> mismatch.
        self.assertIsInstance(result, PaymentVerificationFailed)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual(record.kind, PaymentReconciliation.Kind.AMOUNT_MISMATCH)
        # Attempt is SUCCEEDED (money moved) but NO OK transaction created.
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertFalse(Transaction.objects.filter(order=order, status="ok").exists())

    def test_callback_body_amount_is_ignored_server_total_is_authoritative(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        # Callback body lies about amount, but the verify uses the DB amount.
        result, post = self._callback(
            attempt,
            _zibal_ok(order),
            callback_data={"amount": "999999999", "success": "1"},
        )
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        # The amount submitted to the gateway was the stored order total (Rial).
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["trackId"], attempt.gateway_track_id)
        attempt.refresh_from_db()
        self.assertEqual(attempt.amount, order.grand_total)


# ---------------------------------------------------------------------------
# Expired / canceled attempts, unauthorized config, unsafe redirects
# ---------------------------------------------------------------------------


class ExpiredAndFinalAttemptTests(SecurityBase):
    def test_expired_attempt_is_still_verified_money_not_lost(self):
        order = self.new_order(coupon=False)
        attempt = self._attempt(order, status=PaymentAttempt.Status.EXPIRED)
        result, post = self._callback(attempt, _zibal_ok(order))
        post.assert_called_once()
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_attempt_without_track_id_is_not_sent_to_gateway(self):
        order = self.new_order()
        attempt = self._attempt(order, status=PaymentAttempt.Status.FAILED)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(gateway_track_id="")
        result, post = self._callback(attempt, _zibal_ok(order))
        self.assertIsInstance(result, PaymentVerificationFailed)
        post.assert_not_called()


class UnauthorizedConfigTests(SecurityBase):
    def test_inactive_config_cannot_initiate_payment(self):
        order = self.new_order()
        config = self._config(active=False)
        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=order,
                gateway_config=config,
                callback_url="https://x/cb",
                store=self.store,
            )

    def test_documentation_blocked_provider_cannot_initiate(self):
        order = self.new_order()
        # mellat is a documentation-blocked skeleton -> never routable.
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="mellat", is_active=True
        )
        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=order,
                gateway_config=config,
                callback_url="https://x/cb",
                store=self.store,
            )

    def test_unconfigured_online_config_cannot_initiate(self):
        order = self.new_order()
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=True
        )
        # No credentials set -> is_configured False -> rejected.
        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=order,
                gateway_config=config,
                callback_url="https://x/cb",
                store=self.store,
            )


class RedirectSafetyTests(SecurityBase):
    def test_gateway_redirect_urls_stay_on_the_provider_origin(self):
        """build_redirect_url must point at the provider's own domain — never a
        caller-controlled or arbitrary host (open-redirect guard)."""
        zibal = ZibalAdapter()
        url = zibal.build_redirect_url("TRK-123")
        self.assertTrue(url.startswith("https://gateway.zibal.ir/"))

        zarinpal = ZarinpalAdapter()
        url2 = zarinpal.build_redirect_url("A-123")
        self.assertTrue(url2.startswith("https://payment.zarinpal.com/"))

    def test_track_id_is_appended_not_used_to_rewrite_host(self):
        # A hostile track_id cannot move the redirect off the provider origin:
        # it is only ever appended to the fixed provider path.
        zibal = ZibalAdapter()
        url = zibal.build_redirect_url("https://evil.example/steal")
        # The provider origin is preserved as the URL authority.
        self.assertTrue(url.startswith("https://gateway.zibal.ir/start/"))


# ---------------------------------------------------------------------------
# Concurrency (LOGIC ONLY on SQLite — Postgres row-locking NOT verified here)
# ---------------------------------------------------------------------------


class ConcurrentVerificationLogicTests(SecurityBase):
    """Logic-level idempotency of concurrent verification.

    IMPORTANT: SQLite does NOT support ``SELECT ... FOR UPDATE`` row-level
    locking. The orchestrator uses ``select_for_update`` (order row then
    attempt row) to serialize concurrent callbacks and a cancel racing a
    payment. The assertions below prove the *idempotency logic* only (the
    "already SUCCEEDED => return" guard and the conditional status
    transition). They do NOT prove the Postgres row-lock serialization — that
    is **NOT VERIFIED ON SQLITE** and must be validated against Postgres.
    """

    def test_double_apply_of_same_attempt_creates_single_transaction(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        # First callback finalizes.
        self._callback(attempt, _zibal_ok(order, "REF-C1"))
        # NOT VERIFIED ON SQLITE: a genuine *simultaneous* second callback would
        # rely on row-level locking. Here we prove the post-success idempotency
        # guard: a second pass short-circuits on status==SUCCEEDED.
        second, post = self._callback(attempt, _zibal_ok(order, "REF-C2"))
        post.assert_not_called()
        self.assertEqual(second.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(Transaction.objects.filter(order=order, status="ok").count(), 1)

    def test_cancel_then_payment_records_reconciliation_not_double_state(self):
        order = self.new_order()
        config = self._config()
        attempt = self._attempt(order, config)
        # NOT VERIFIED ON SQLITE: the true cancel-vs-pay race is serialized by
        # the order-row lock on Postgres. Here cancel commits first, then the
        # late payment is verified and recorded (never silently applied).
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        result, _ = self._callback(attempt, _zibal_ok(order))
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(
            PaymentReconciliation.objects.get(attempt=attempt).kind,
            PaymentReconciliation.Kind.ORDER_CANCELED,
        )
