"""Tests for the gateway payment service — initiation, callback, verification.

Covers:
- Payment initiation for online gateways (Zibal)
- Payment initiation for COD
- Already-paid order rejection
- Gateway config validation
- Idempotency key deduplication
- Callback processing and verification
- Duplicate callback idempotency
- Order not marked paid twice
- Failed verification handling
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.encryption import reset_fernet
from apps.orders.gateways.base import (
    GatewayConnectionError,
    GatewayPaymentError,
    GatewayVerificationError,
    PaymentCreationResult,
    PaymentVerificationResult,
)
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGateway,
    PaymentGatewayConfig,
    ShippingMethod,
    Transaction,
)
from apps.orders.services.gateway_payment_service import (
    PaymentAlreadyPaidError,
    PaymentConfigError,
    PaymentInitiationError,
    PaymentVerificationFailed,
    initiate_payment,
    process_callback_and_verify,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class GatewayPaymentServiceTestBase(TestCase):
    def setUp(self):
        reset_fernet()
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="gw_pay_user", password="test123")
        self.customer = Customer.objects.create(user=self.user, full_name="مشتری", phone="09121111111")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="gw-vendor")
        self.shipping = ShippingMethod.objects.create(
            store=self.store, name="پست", slug="gw-post", cost=Decimal("30000")
        )
        self.legacy_gateway = PaymentGateway.objects.create(
            store=self.store, name="زیبال", slug="zibal"
        )
        self.order = Order.objects.create(
            code="DM-GW001", store=self.store, customer=self.customer,
            vendor=self.vendor, address={}, shipping_method=self.shipping,
            payment_gateway=self.legacy_gateway,
            items_total=Decimal("200000"), grand_total=Decimal("250000"),
        )
        # Create Zibal config
        self.zibal_config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=True,
        )
        self.zibal_config.set_credentials({"merchant": "test-merch"})
        self.zibal_config.save()

        # Create COD config
        self.cod_config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="cod", is_active=True,
        )

    def tearDown(self):
        reset_fernet()


class InitiatePaymentTests(GatewayPaymentServiceTestBase):
    @patch("apps.orders.gateways.zibal.requests.post")
    def test_initiate_zibal_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 777888}
        mock_post.return_value = mock_response

        attempt = initiate_payment(
            order=self.order,
            gateway_config=self.zibal_config,
            callback_url="https://shop.com/callback/PLACEHOLDER",
            store=self.store,
        )

        self.assertEqual(attempt.status, PaymentAttempt.Status.REDIRECT_READY)
        self.assertEqual(attempt.gateway_track_id, "777888")
        self.assertEqual(attempt.amount, Decimal("250000"))
        self.assertEqual(attempt.currency, "TOMAN")
        self.assertEqual(attempt.store, self.store)

    def test_initiate_cod_success(self):
        attempt = initiate_payment(
            order=self.order,
            gateway_config=self.cod_config,
            callback_url="https://shop.com/callback/x",
            store=self.store,
        )

        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertIn("cod", attempt.gateway_track_id)
        self.assertIsNotNone(attempt.verified_at)

    def test_already_paid_order_raises(self):
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save()

        with self.assertRaises(PaymentAlreadyPaidError):
            initiate_payment(
                order=self.order,
                gateway_config=self.zibal_config,
                callback_url="https://shop.com/cb",
                store=self.store,
            )

    def test_inactive_config_raises(self):
        self.zibal_config.is_active = False
        self.zibal_config.save()

        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=self.order,
                gateway_config=self.zibal_config,
                callback_url="https://shop.com/cb",
                store=self.store,
            )

    def test_wrong_store_config_raises(self):
        store2 = Store.objects.create(name="Other", slug="other-gw", status="active")
        other_config = PaymentGatewayConfig.objects.create(
            store=store2, gateway_code="zibal", is_active=True
        )
        other_config.set_credentials({"merchant": "x"})
        other_config.save()

        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=self.order,
                gateway_config=other_config,
                callback_url="https://shop.com/cb",
                store=self.store,
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_idempotency_key_returns_existing(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 111}
        mock_post.return_value = mock_response

        a1 = initiate_payment(
            order=self.order,
            gateway_config=self.zibal_config,
            callback_url="https://shop.com/cb",
            store=self.store,
            idempotency_key="idem-test-1",
        )
        a2 = initiate_payment(
            order=self.order,
            gateway_config=self.zibal_config,
            callback_url="https://shop.com/cb",
            store=self.store,
            idempotency_key="idem-test-1",
        )
        self.assertEqual(a1.pk, a2.pk)
        # Only one API call should have been made
        self.assertEqual(mock_post.call_count, 1)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_gateway_error_marks_attempt_failed(self, mock_post):
        import requests as req
        mock_post.side_effect = req.Timeout("timeout")

        with self.assertRaises(PaymentInitiationError):
            initiate_payment(
                order=self.order,
                gateway_config=self.zibal_config,
                callback_url="https://shop.com/cb",
                store=self.store,
            )

        attempt = PaymentAttempt.objects.filter(order=self.order).first()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertTrue(attempt.failure_code)


class ProcessCallbackTests(GatewayPaymentServiceTestBase):
    def _create_redirect_ready_attempt(self):
        """Helper: create an attempt in REDIRECT_READY state."""
        attempt = PaymentAttempt.objects.create(
            store=self.store,
            order=self.order,
            gateway_config=self.zibal_config,
            amount=self.order.grand_total,
            currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY,
            gateway_track_id="track-999",
        )
        return attempt

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_successful_callback_marks_paid(self, mock_post):
        attempt = self._create_redirect_ready_attempt()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 100,
            "amount": 2500000,  # 250000 Toman in Rial
            "status": 1,
            "refNumber": "REF-OK-123",
            "cardNumber": "6037-99XX-XXXX-5678",
        }
        mock_post.return_value = mock_response

        result = process_callback_and_verify(
            attempt_public_id=attempt.public_id,
            callback_data={"trackId": "track-999", "success": "1"},
            store=self.store,
        )

        result.refresh_from_db()
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(result.gateway_ref_id, "REF-OK-123")

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.status, Order.Status.PROCESSING)

        # Transaction created for backwards compatibility
        self.assertTrue(Transaction.objects.filter(order=self.order, status="ok").exists())

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_failed_verification_does_not_mark_paid(self, mock_post):
        attempt = self._create_redirect_ready_attempt()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 202,
            "status": -1,
            "message": "Canceled by user",
        }
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentVerificationFailed):
            process_callback_and_verify(
                attempt_public_id=attempt.public_id,
                callback_data={"trackId": "track-999", "success": "0"},
                store=self.store,
            )

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_duplicate_callback_is_idempotent(self, mock_post):
        attempt = self._create_redirect_ready_attempt()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": 100, "amount": 2500000, "status": 1,
            "refNumber": "REF-DUP", "cardNumber": "",
        }
        mock_post.return_value = mock_response

        # First callback
        process_callback_and_verify(
            attempt_public_id=attempt.public_id,
            callback_data={},
            store=self.store,
        )

        # Second callback — should be idempotent (attempt already final)
        result2 = process_callback_and_verify(
            attempt_public_id=attempt.public_id,
            callback_data={},
            store=self.store,
        )

        self.assertEqual(result2.status, PaymentAttempt.Status.SUCCEEDED)
        # Only one transaction should exist
        self.assertEqual(Transaction.objects.filter(order=self.order).count(), 1)
        # verify_payment should only be called once
        self.assertEqual(mock_post.call_count, 1)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_already_paid_by_another_attempt_cancels_this(self, mock_post):
        """سفارش قبلاً پرداخت شده: تلاشِ دوم **همچنان با درگاه راستی‌آزمایی می‌شود** (ممکن است پول کسر شده
        باشد)؛ اگر درگاه ناموفق گفت ⇒ تلاش لغو می‌شود، اگر موفق گفت ⇒ تطبیقِ «پرداخت تکراری» (نه از دست رفتن)."""
        self.order.payment_status = Order.PaymentStatus.PAID
        self.order.save()
        attempt = self._create_redirect_ready_attempt()
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 202, "status": -1, "message": "Canceled by user"}
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentVerificationFailed):
            process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.CANCELED)
        self.assertEqual(mock_post.call_count, 1)

    def test_nonexistent_attempt_raises(self):
        with self.assertRaises(PaymentVerificationFailed):
            process_callback_and_verify(
                attempt_public_id="nonexistent-id-xyz",
                callback_data={},
                store=self.store,
            )

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verification_network_error_marks_failed(self, mock_post):
        import requests as req
        attempt = self._create_redirect_ready_attempt()
        mock_post.side_effect = req.Timeout("verify timeout")

        with self.assertRaises(PaymentVerificationFailed):
            process_callback_and_verify(
                attempt_public_id=attempt.public_id,
                callback_data={},
                store=self.store,
            )

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(attempt.failure_code, "verify_timeout")


class PlatformCredentialIsolationTests(GatewayPaymentServiceTestBase):
    """Phase 4 (master-prompt §6.2): the platform's own Zibal credentials
    (apps.portal.PlatformConfiguration, used for RastiSi's own subscription
    billing — Phase 3) must never be usable as a fallback for a merchant
    Store's order checkout, and vice versa. These are two structurally
    separate credential domains with no shared code path; this test locks
    that in with a concrete, observable assertion (the HTTP payload sent to
    Zibal) rather than relying only on code inspection."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        from apps.portal.services.platform_config_service import get_platform_configuration

        self.addCleanup(cache.clear)
        cache.clear()
        platform_config = get_platform_configuration()
        platform_config.default_payment_provider = "zibal"
        platform_config.set_zibal_credentials(merchant="platform-only-merchant-should-never-be-used")
        platform_config.save()
        cache.clear()
        # This Store's own merchant differs from the platform's — if they
        # ever got mixed up, this test would catch it via the sent payload.
        self.zibal_config.set_credentials({"merchant": "store-own-merchant-abc"})
        self.zibal_config.save()

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_checkout_uses_only_the_stores_own_merchant_credential(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": 100, "trackId": 999}
        mock_post.return_value = mock_response

        initiate_payment(
            order=self.order, gateway_config=self.zibal_config, callback_url="https://x/callback",
            store=self.store,
        )
        sent_merchant = mock_post.call_args.kwargs["json"]["merchant"]
        self.assertEqual(sent_merchant, "store-own-merchant-abc")
        self.assertNotEqual(sent_merchant, "platform-only-merchant-should-never-be-used")
