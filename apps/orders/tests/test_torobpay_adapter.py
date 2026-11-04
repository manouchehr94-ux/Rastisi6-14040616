"""Contract tests for the TorobPay BNPL adapter — real REST contract.

All HTTP is MOCKED via ``unittest.mock.patch`` on
``apps.orders.gateways.torobpay.requests.request`` — NO real network calls are
ever made, and NO WordPress/PHP dependency is involved. Assertions follow the
provider-published WooCommerce plugin HTTP contract verified 2026-11-03
(plugins.svn.wordpress.org/torobpay-for-woocommerce/trunk/class-torobpay-api.php),
implemented natively in Django:

- Auth: POST api/online/v1/oauth/token (password grant, scope online-merchant,
  Basic base64(client_id:client_secret)) -> {access_token, expires_in}. On HTTP
  401 the token is dropped and a single re-auth is attempted.
- eligibility: GET api/online/offer/v1/eligible?amount=<IRR> -> provider payload.
- create/verify/settle/cancel/status: api/online/payment/v1/{token,verify,settle,
  cancel,status} with {paymentToken}.
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
from apps.orders.gateways.torobpay import (
    TOMAN_TO_RIAL,
    TOROBPAY_CANCEL_PATH,
    TOROBPAY_ELIGIBLE_PATH,
    TOROBPAY_PAYMENT_TOKEN_PATH,
    TOROBPAY_SETTLE_PATH,
    TOROBPAY_STATUS_PATH,
    TOROBPAY_TOKEN_PATH,
    TOROBPAY_VERIFY_PATH,
    TorobPayAdapter,
)
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {
    "client_id": "torob-client",
    "client_secret": "t0p-s3cr3t",
    "client_username": "merchant",
    "client_password": "p@ss",
}


def _resp(json_body, status_code=200):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = status_code
    return mock


def _oauth_ok():
    return _resp({"access_token": "ACCESS-1", "expires_in": 3300})


class _Router:
    """Dispatch ``requests.request(method, url, ...)`` to per-path responses.

    ``routes`` maps a path suffix to a single response or a list consumed in
    order (for 401 re-auth / multi-call flows).
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


class TorobPayRegistryTests(TestCase):
    def test_registered_as_online_bnpl(self):
        adapter = get_adapter("torobpay")
        self.assertIsInstance(adapter, TorobPayAdapter)
        self.assertEqual(adapter.code, "torobpay")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.BNPL)
        self.assertFalse(adapter.documentation_blocked)

    def test_capabilities_include_settle(self):
        adapter = get_adapter("torobpay")
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
        self.assertFalse(adapter.supports(PaymentOperation.REFUND))


class TorobPayCredentialTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials,
            ["client_id", "client_secret", "client_username", "client_password"],
        )

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertEqual(len(self.adapter.validate_credentials({})), 4)

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({}):
            self.assertNotIn("t0p-s3cr3t", message)
            self.assertNotIn("p@ss", message)


class TorobPayAuthTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_oauth_success_password_grant(self):
        router = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok()})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            token = self.adapter._get_token(VALID_CREDS)
        self.assertEqual(token, "ACCESS-1")
        method, url, kwargs = router.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(kwargs["headers"]["Authorization"].startswith("Basic "))
        self.assertEqual(kwargs["data"]["grant_type"], "password")
        self.assertEqual(kwargs["data"]["scope"], "online-merchant")

    def test_401_drops_token_and_reauths_once(self):
        # First verify returns 401 -> adapter re-auths -> retried verify ok.
        router = _Router(
            {
                TOROBPAY_TOKEN_PATH: [_oauth_ok(), _oauth_ok()],
                TOROBPAY_VERIFY_PATH: [
                    _resp({"error": "unauthorized"}, status_code=401),
                    _resp({"successful": True, "response": {"transactionId": "T1", "amount": 5000000}}),
                ],
            }
        )
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.verify_payment(
                track_id="PT-1", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )
        self.assertTrue(result.success)
        # Two token fetches (initial + re-auth) and two verify calls happened.
        token_calls = [c for c in router.calls if c[1].endswith(TOROBPAY_TOKEN_PATH)]
        verify_calls = [c for c in router.calls if c[1].endswith(TOROBPAY_VERIFY_PATH)]
        self.assertEqual(len(token_calls), 2)
        self.assertEqual(len(verify_calls), 2)

    def test_oauth_rejected_raises_credential_error(self):
        router = _Router({TOROBPAY_TOKEN_PATH: _resp({"error": "bad"}, status_code=400)})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            with self.assertRaises(GatewayCredentialError):
                self.adapter._get_token(VALID_CREDS)


class TorobPayEligibilityTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_eligibility_returns_provider_payload(self):
        payload = {"successful": True, "response": {"eligible": True}}
        router = _Router(
            {TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_ELIGIBLE_PATH: _resp(payload)}
        )
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.check_bnpl_eligibility(
                amount=Decimal("500000"), currency="TOMAN", credentials=VALID_CREDS,
            )
        self.assertEqual(result, payload)
        eligible_call = [c for c in router.calls if c[1].endswith(TOROBPAY_ELIGIBLE_PATH)][0]
        self.assertEqual(eligible_call[2]["params"]["amount"], 500000 * TOMAN_TO_RIAL)


class TorobPayCreateTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_create_parses_page_url_and_token(self):
        body = {
            "successful": True,
            "response": {"paymentToken": "PT-9", "paymentPageUrl": "https://cpg.torobpay.com/p/PT-9"},
        }
        router = _Router(
            {TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_PAYMENT_TOKEN_PATH: _resp(body)}
        )
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.create_payment(
                amount=Decimal("500000"), currency="TOMAN", callback_url="https://shop/cb",
                credentials=VALID_CREDS, order_code="DM-TP1",
            )
        self.assertEqual(result.track_id, "PT-9")
        self.assertEqual(result.gateway_url, "https://cpg.torobpay.com/p/PT-9")
        create_call = [c for c in router.calls if c[1].endswith(TOROBPAY_PAYMENT_TOKEN_PATH)][0]
        payload = create_call[2]["json"]
        self.assertEqual(payload["amount"], 500000 * TOMAN_TO_RIAL)
        self.assertEqual(payload["paymentMethodTypeDto"], "INSTALLMENT")
        self.assertTrue(5 <= len(payload["transactionId"]) <= 10)
        self.assertEqual(payload["cartList"][0]["totalAmount"], 500000 * TOMAN_TO_RIAL)

    def test_create_rejected_raises_payment_error(self):
        router = _Router(
            {
                TOROBPAY_TOKEN_PATH: _oauth_ok(),
                TOROBPAY_PAYMENT_TOKEN_PATH: _resp({"successful": False, "errorData": {"m": "x"}}),
            }
        )
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            with self.assertRaises(GatewayPaymentError):
                self.adapter.create_payment(
                    amount=Decimal("500000"), currency="TOMAN", callback_url="https://shop/cb",
                    credentials=VALID_CREDS, order_code="DM-TP1",
                )


class TorobPayVerifySettleCancelTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_verify_success(self):
        body = {"successful": True, "response": {"transactionId": "T1", "amount": 5000000}}
        router = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_VERIFY_PATH: _resp(body)})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.verify_payment(
                track_id="PT-1", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )
        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "T1")

    def test_verify_failure(self):
        body = {"successful": False, "errorData": {"m": "declined"}}
        router = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_VERIFY_PATH: _resp(body)})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.verify_payment(
                track_id="PT-1", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )
        self.assertFalse(result.success)

    def test_verify_amount_mismatch_raises_with_evidence(self):
        body = {"successful": True, "response": {"transactionId": "T1", "amount": 1234567}}
        router = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_VERIFY_PATH: _resp(body)})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            with self.assertRaises(GatewayAmountMismatchError) as ctx:
                self.adapter.verify_payment(
                    track_id="PT-1", expected_amount=Decimal("500000"), currency="TOMAN",
                    credentials=VALID_CREDS, callback_data={},
                )
        evidence = ctx.exception.details["evidence"]
        self.assertEqual(evidence["expected_rial"], 5000000)
        self.assertEqual(evidence["returned_rial"], 1234567)

    def test_settle_success_and_failure(self):
        ok = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_SETTLE_PATH: _resp({"successful": True, "response": {}})})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=ok):
            r1 = self.adapter.settle_payment(
                track_id="PT-1", amount=Decimal("500000"), currency="TOMAN", credentials=VALID_CREDS,
            )
        self.assertTrue(r1.success)

        bad = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_SETTLE_PATH: _resp({"successful": False})})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=bad):
            r2 = self.adapter.settle_payment(
                track_id="PT-1", amount=Decimal("500000"), currency="TOMAN", credentials=VALID_CREDS,
            )
        self.assertFalse(r2.success)

    def test_cancel_success(self):
        router = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_CANCEL_PATH: _resp({"successful": True})})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.cancel_payment(track_id="PT-1", credentials=VALID_CREDS)
        self.assertTrue(result.success)

    def test_inquire_status_mapping(self):
        body = {"response": {"status": "VERIFY", "transactionId": "T1", "amount": 5000000}}
        router = _Router({TOROBPAY_TOKEN_PATH: _oauth_ok(), TOROBPAY_STATUS_PATH: _resp(body)})
        with patch("apps.orders.gateways.torobpay.requests.request", side_effect=router):
            result = self.adapter.inquire_payment(
                track_id="PT-1", expected_amount=Decimal("500000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        self.assertTrue(result.paid)
        self.assertFalse(result.settled)
        self.assertEqual(result.status, "VERIFY")


class TorobPayReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_no_credentials_not_configured_and_not_selectable(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="torobpay", is_active=True,
        )
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NOT_CONFIGURED,
        )
        self.assertFalse(config.is_selectable_at_checkout)

    def test_partial_credentials_needs_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="torobpay", is_active=True,
        )
        config.set_credentials({"client_id": "id", "client_secret": "sec"})
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NEEDS_CREDENTIALS,
        )
        self.assertFalse(config.is_selectable_at_checkout)

    def test_full_creds_sandbox_ready_for_test_and_selectable_in_sandbox(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="torobpay", is_active=True, is_sandbox=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.READY_FOR_TEST,
        )
        self.assertTrue(config.is_selectable_at_checkout)

    def test_full_creds_non_sandbox_inactive_not_selectable(self):
        # is_active default False -> never selectable even when CONNECTED.
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="torobpay", is_active=False, is_sandbox=False,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
