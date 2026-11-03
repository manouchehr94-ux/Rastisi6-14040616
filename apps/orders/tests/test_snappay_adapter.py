"""Contract tests for the SnappPay BNPL adapter — real REST v2.1 contract.

All HTTP is MOCKED via ``unittest.mock.patch`` on
``apps.orders.gateways.snappay.requests.request`` — NO real network calls are
ever made. Assertions follow the official SnappPay self-cms REST API v2.1
contract verified 2026-11-03 (https://academy.snapppay.ir/self-cms/):

- Auth: POST /api/online/v1/oauth/token (Basic base64(client_id:client_secret))
  -> JWT ``access_token``.
- eligibility: GET /api/online/offer/v1/eligible?amount=<IRR> -> provider payload.
- create: POST /api/online/payment/v1/token -> {successful, response:{paymentToken,
  paymentPageUrl}}.
- verify: POST /api/online/payment/v1/verify -> success/failure (does NOT finalize).
- settle: POST /api/online/payment/v1/settle -> success/failure.
- cancel: POST /api/online/payment/v1/cancel.
- status: GET /api/online/payment/v1/status -> {status in SETTLE|CANCEL|VERIFY|PENDING|REVERT}.
- All amounts are IRR (Rial): Toman -> Rial x10 once; amount mismatch raises
  GatewayAmountMismatchError with evidence.

These tests FAIL if the adapter is reverted to the documentation-blocked
skeleton (capabilities != empty, documentation_blocked False, real endpoints,
eligibility returns a payload instead of raising).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayCredentialError,
    GatewayPaymentError,
    PaymentOperation,
)
from apps.orders.gateways.snappay import (
    SNAPPAY_CANCEL_PATH,
    SNAPPAY_ELIGIBLE_PATH,
    SNAPPAY_PAYMENT_TOKEN_PATH,
    SNAPPAY_SETTLE_PATH,
    SNAPPAY_STATUS_PATH,
    SNAPPAY_TOKEN_PATH,
    SNAPPAY_VERIFY_PATH,
    TOMAN_TO_RIAL,
    SnappPayAdapter,
)
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"client_id": "snapp-client", "client_secret": "s3cr3t"}


def _resp(json_body, status_code=200):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = status_code
    return mock


def _oauth_ok():
    return _resp({"access_token": "JWT-ABC", "expires_in": 3600})


class _Router:
    """Dispatch ``requests.request(method, url, ...)`` to a per-path response.

    ``routes`` maps a path suffix to either a single response or a list of
    responses consumed in order (for re-auth / multi-call scenarios).
    """

    def __init__(self, routes):
        self.routes = {k: (v if isinstance(v, list) else [v]) for k, v in routes.items()}
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for path, responses in self.routes.items():
            if url.endswith(path):
                if len(responses) > 1:
                    return responses.pop(0)
                return responses[0]
        raise AssertionError(f"Unexpected URL in test: {url}")


class SnappPayRegistryTests(TestCase):
    def test_registered_as_online_bnpl(self):
        adapter = get_adapter("snappay")
        self.assertIsInstance(adapter, SnappPayAdapter)
        self.assertEqual(adapter.code, "snappay")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.BNPL)
        # Real contract: NOT documentation-blocked.
        self.assertFalse(adapter.documentation_blocked)

    def test_capabilities_include_settle(self):
        adapter = get_adapter("snappay")
        self.assertEqual(
            adapter.capabilities,
            frozenset(
                {
                    PaymentOperation.CREATE,
                    PaymentOperation.VERIFY,
                    PaymentOperation.SETTLE,
                    PaymentOperation.CANCEL,
                    PaymentOperation.INQUIRE,
                }
            ),
        )
        self.assertTrue(adapter.supports(PaymentOperation.SETTLE))
        # update/revert intentionally not declared.
        self.assertFalse(adapter.supports(PaymentOperation.REFUND))


class SnappPayCredentialTests(TestCase):
    def setUp(self):
        self.adapter = SnappPayAdapter()

    def test_required_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["client_id", "client_secret"])

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertEqual(len(self.adapter.validate_credentials({})), 2)

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({}):
            self.assertNotIn("s3cr3t", message)


class SnappPayAuthTests(TestCase):
    def setUp(self):
        self.adapter = SnappPayAdapter()

    def test_oauth_success_returns_jwt(self):
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok()})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            token = self.adapter._get_token(VALID_CREDS)
        self.assertEqual(token, "JWT-ABC")
        # The token call uses HTTP Basic (base64 client_id:client_secret).
        method, url, kwargs = router.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith(SNAPPAY_TOKEN_PATH))
        self.assertTrue(kwargs["headers"]["Authorization"].startswith("Basic "))

    def test_oauth_rejected_raises_credential_error(self):
        router = _Router({SNAPPAY_TOKEN_PATH: _resp({"error": "unauthorized"}, status_code=401)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            with self.assertRaises(GatewayCredentialError):
                self.adapter._get_token(VALID_CREDS)

    def test_credentials_never_logged_on_oauth(self):
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok()})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            self.adapter._get_token(VALID_CREDS)
        # The raw secret is never a positional/keyword value in any call args.
        for _m, _u, kwargs in router.calls:
            self.assertNotIn("s3cr3t", str(kwargs.get("data")))


class SnappPayEligibilityTests(TestCase):
    def setUp(self):
        self.adapter = SnappPayAdapter()

    def test_eligibility_returns_provider_payload(self):
        payload = {
            "successful": True,
            "response": {"eligible": True, "title": "اقساط اسنپ‌پی"},
        }
        router = _Router(
            {SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_ELIGIBLE_PATH: _resp(payload)}
        )
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.check_bnpl_eligibility(
                amount=Decimal("500000"), currency="TOMAN", credentials=VALID_CREDS,
            )
        # Provider payload returned verbatim; nothing fabricated.
        self.assertEqual(result, payload)
        # Amount was converted Toman -> Rial once (x10) in the query.
        eligible_call = [c for c in router.calls if c[1].endswith(SNAPPAY_ELIGIBLE_PATH)][0]
        self.assertEqual(eligible_call[2]["params"]["amount"], 500000 * TOMAN_TO_RIAL)


class SnappPayCreateTests(TestCase):
    def setUp(self):
        self.adapter = SnappPayAdapter()

    def test_create_parses_page_url_and_token(self):
        create_body = {
            "successful": True,
            "response": {
                "paymentToken": "PT-123",
                "paymentPageUrl": "https://snapppay/pay/PT-123",
            },
        }
        router = _Router(
            {SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_PAYMENT_TOKEN_PATH: _resp(create_body)}
        )
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.create_payment(
                amount=Decimal("500000"), currency="TOMAN", callback_url="https://shop/cb",
                credentials=VALID_CREDS, order_code="DM-SP1",
            )
        self.assertEqual(result.track_id, "PT-123")
        self.assertEqual(result.gateway_url, "https://snapppay/pay/PT-123")
        self.assertEqual(result.extra["paymentPageUrl"], "https://snapppay/pay/PT-123")
        # Request body carried IRR amount (x10) and a 5-10 char transactionId.
        create_call = [c for c in router.calls if c[1].endswith(SNAPPAY_PAYMENT_TOKEN_PATH)][0]
        body = create_call[2]["json"]
        self.assertEqual(body["amount"], 500000 * TOMAN_TO_RIAL)
        self.assertTrue(5 <= len(body["transactionId"]) <= 10)
        self.assertEqual(body["cartList"][0]["totalAmount"], 500000 * TOMAN_TO_RIAL)

    def test_build_redirect_url_returns_page_url(self):
        self.assertEqual(
            self.adapter.build_redirect_url("https://snapppay/pay/PT-123"),
            "https://snapppay/pay/PT-123",
        )

    def test_create_rejected_raises_payment_error(self):
        router = _Router(
            {
                SNAPPAY_TOKEN_PATH: _oauth_ok(),
                SNAPPAY_PAYMENT_TOKEN_PATH: _resp({"successful": False, "errorData": {"message": "x"}}),
            }
        )
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            with self.assertRaises(GatewayPaymentError):
                self.adapter.create_payment(
                    amount=Decimal("500000"), currency="TOMAN", callback_url="https://shop/cb",
                    credentials=VALID_CREDS, order_code="DM-SP1",
                )


class SnappPayVerifyTests(TestCase):
    def setUp(self):
        self.adapter = SnappPayAdapter()

    def test_verify_success(self):
        body = {"successful": True, "response": {"transactionId": "TXN1", "amount": 5000000}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_VERIFY_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.verify_payment(
                track_id="PT-123", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={"state": "OK"},
            )
        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "TXN1")

    def test_verify_failure(self):
        body = {"successful": False, "errorData": {"message": "declined"}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_VERIFY_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.verify_payment(
                track_id="PT-123", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )
        self.assertFalse(result.success)

    def test_verify_amount_mismatch_raises_with_evidence(self):
        # Provider confirms a DIFFERENT amount than the order expects.
        body = {"successful": True, "response": {"transactionId": "TXN1", "amount": 9999999}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_VERIFY_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            with self.assertRaises(GatewayAmountMismatchError) as ctx:
                self.adapter.verify_payment(
                    track_id="PT-123", expected_amount=Decimal("500000"), currency="TOMAN",
                    credentials=VALID_CREDS, callback_data={},
                )
        evidence = ctx.exception.details["evidence"]
        self.assertEqual(evidence["expected_rial"], 5000000)
        self.assertEqual(evidence["returned_rial"], 9999999)

    def test_verify_timeout_falls_back_to_status_verify(self):
        import requests as _requests

        status_body = {"response": {"status": "VERIFY", "transactionId": "TXN1", "amount": 5000000}}

        def side_effect(method, url, **kwargs):
            if url.endswith(SNAPPAY_TOKEN_PATH):
                return _oauth_ok()
            if url.endswith(SNAPPAY_VERIFY_PATH):
                raise _requests.Timeout("read timed out")
            if url.endswith(SNAPPAY_STATUS_PATH):
                return _resp(status_body)
            raise AssertionError(url)

        with patch("apps.orders.gateways.snappay.requests.request", side_effect=side_effect):
            result = self.adapter.verify_payment(
                track_id="PT-123", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )
        self.assertTrue(result.success)


class SnappPaySettleCancelInquireTests(TestCase):
    def setUp(self):
        self.adapter = SnappPayAdapter()

    def test_settle_success(self):
        body = {"successful": True, "response": {"transactionId": "TXN1"}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_SETTLE_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.settle_payment(
                track_id="PT-123", amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        self.assertTrue(result.success)

    def test_settle_failure(self):
        body = {"successful": False, "errorData": {"message": "cannot settle"}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_SETTLE_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.settle_payment(
                track_id="PT-123", amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        self.assertFalse(result.success)

    def test_cancel_success(self):
        body = {"successful": True, "response": {}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_CANCEL_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.cancel_payment(track_id="PT-123", credentials=VALID_CREDS)
        self.assertTrue(result.success)

    def test_inquire_status_mapping(self):
        body = {"response": {"status": "SETTLE", "transactionId": "TXN1", "amount": 5000000}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_STATUS_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.inquire_payment(
                track_id="PT-123", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        self.assertTrue(result.paid)
        self.assertTrue(result.settled)
        self.assertEqual(result.status, "SETTLE")

    def test_inquire_pending_not_paid(self):
        body = {"response": {"status": "PENDING", "transactionId": "TXN1"}}
        router = _Router({SNAPPAY_TOKEN_PATH: _oauth_ok(), SNAPPAY_STATUS_PATH: _resp(body)})
        with patch("apps.orders.gateways.snappay.requests.request", side_effect=router):
            result = self.adapter.inquire_payment(
                track_id="PT-123", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        self.assertFalse(result.paid)
        self.assertFalse(result.settled)


class SnappPayReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_no_credentials_not_configured_and_not_selectable(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=True,
        )
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NOT_CONFIGURED,
        )
        self.assertFalse(config.is_selectable_at_checkout)

    def test_partial_credentials_needs_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=True,
        )
        config.set_credentials({"client_id": "only-id"})
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NEEDS_CREDENTIALS,
        )
        self.assertFalse(config.is_selectable_at_checkout)

    def test_full_creds_sandbox_ready_for_test_and_selectable_in_sandbox(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=True, is_sandbox=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.READY_FOR_TEST,
        )
        # Selectable ONLY because it is in sandbox mode.
        self.assertTrue(config.is_selectable_at_checkout)

    def test_not_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertNotEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
