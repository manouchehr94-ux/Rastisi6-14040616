"""Contract tests for the Zarinpal REST v4 adapter.

All HTTP is MOCKED via ``unittest.mock.patch`` on ``apps.orders.gateways
.zarinpal.requests.post`` — NO real network calls are ever made. Assertions are
based on the documented Zarinpal REST v4 contract (confirmed 2026-11-03 from
https://www.zarinpal.com/docs/paymentGateway/connectToGateway , .../moreFeatures
/currency and .../errorList):

- Request: merchant_id (36-char), amount (Integer, Rial), currency ("IRR"),
  callback_url, description, metadata.order_id.
- On success: data.code == 100 and data.authority; redirect to StartPay/{auth}.
- Verify request: merchant_id, amount (Rial), authority.
- Verify response: data.code (100 success / 101 already-verified), ref_id,
  card_pan; code -50 = amount mismatch.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayPaymentError,
    GatewayResponseError,
    PaymentOperation,
)
from apps.orders.gateways.zarinpal import (
    TOMAN_TO_RIAL,
    ZARINPAL_REQUEST_URL,
    ZARINPAL_STARTPAY_URL,
    ZARINPAL_VERIFY_URL,
    ZarinpalAdapter,
)

# A valid 36-character merchant_id (UUID form) per the documentation.
VALID_MERCHANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _resp(json_body):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = 200
    return mock


class ZarinpalRegistryTests(TestCase):
    def test_registered_as_online_facilitator(self):
        adapter = get_adapter("zarinpal")
        self.assertIsInstance(adapter, ZarinpalAdapter)
        self.assertEqual(adapter.code, "zarinpal")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.FACILITATOR)
        self.assertFalse(adapter.documentation_blocked)

    def test_capabilities_create_and_verify_only(self):
        adapter = get_adapter("zarinpal")
        self.assertEqual(
            adapter.capabilities,
            frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY}),
        )
        # Optional financial operations are NOT declared and must raise.
        self.assertFalse(adapter.supports(PaymentOperation.REFUND))
        self.assertFalse(adapter.supports(PaymentOperation.INQUIRE))


class ZarinpalCredentialTests(TestCase):
    def setUp(self):
        self.adapter = ZarinpalAdapter()

    def test_required_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["merchant_id"])

    def test_valid_merchant_id(self):
        self.assertEqual(self.adapter.validate_credentials({"merchant_id": VALID_MERCHANT}), [])

    def test_missing_merchant_id(self):
        errors = self.adapter.validate_credentials({})
        self.assertTrue(errors)

    def test_wrong_length_merchant_id(self):
        errors = self.adapter.validate_credentials({"merchant_id": "too-short"})
        self.assertTrue(errors)


class ZarinpalCreatePaymentTests(TestCase):
    def setUp(self):
        self.adapter = ZarinpalAdapter()
        self.creds = {"merchant_id": VALID_MERCHANT}

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_create_success_and_request_serialization(self, mock_post):
        mock_post.return_value = _resp(
            {"data": {"code": 100, "authority": "A0000000000000000000000000000012345"}, "errors": []}
        )

        result = self.adapter.create_payment(
            amount=Decimal("250000"),  # Toman
            currency="TOMAN",
            callback_url="https://shop.example/cb",
            credentials=self.creds,
            order_code="DM-Z1",
            description="سفارش آزمایشی",
        )

        # Correct endpoint and timeout.
        self.assertEqual(mock_post.call_args.args[0], ZARINPAL_REQUEST_URL)
        self.assertEqual(mock_post.call_args.kwargs["timeout"], (10, 30))

        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["merchant_id"], VALID_MERCHANT)
        # Toman -> Rial conversion happens exactly once at the boundary.
        self.assertEqual(sent["amount"], 250000 * TOMAN_TO_RIAL)
        # currency pinned to IRR so amount is unambiguously Rial.
        self.assertEqual(sent["currency"], "IRR")
        self.assertEqual(sent["callback_url"], "https://shop.example/cb")
        self.assertEqual(sent["metadata"]["order_id"], "DM-Z1")

        self.assertEqual(result.track_id, "A0000000000000000000000000000012345")
        self.assertEqual(
            result.gateway_url, f"{ZARINPAL_STARTPAY_URL}A0000000000000000000000000000012345"
        )

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_create_rejected_raises_payment_error(self, mock_post):
        # -11: terminal not active (a documented error code).
        mock_post.return_value = _resp({"data": {"code": -11, "message": "not active"}, "errors": []})
        with self.assertRaises(GatewayPaymentError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN",
                callback_url="https://x/cb", credentials=self.creds, order_code="DM-Z2",
            )

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_create_missing_authority_raises_response_error(self, mock_post):
        mock_post.return_value = _resp({"data": {"code": 100}, "errors": []})
        with self.assertRaises(GatewayResponseError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN",
                callback_url="https://x/cb", credentials=self.creds, order_code="DM-Z3",
            )

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_create_malformed_json_raises_response_error(self, mock_post):
        mock = MagicMock()
        mock.json.side_effect = ValueError("no json")
        mock.status_code = 502
        mock_post.return_value = mock
        with self.assertRaises(GatewayResponseError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN",
                callback_url="https://x/cb", credentials=self.creds, order_code="DM-Z4",
            )

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_create_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = requests.Timeout("timeout")
        with self.assertRaises(GatewayConnectionError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN",
                callback_url="https://x/cb", credentials=self.creds, order_code="DM-Z5",
            )

    def test_create_without_credentials_raises(self):
        with self.assertRaises(GatewayCredentialError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN",
                callback_url="https://x/cb", credentials={}, order_code="DM-Z6",
            )


class ZarinpalRedirectTests(TestCase):
    def test_build_redirect_url(self):
        adapter = ZarinpalAdapter()
        self.assertEqual(
            adapter.build_redirect_url("A123"), f"{ZARINPAL_STARTPAY_URL}A123"
        )


class ZarinpalVerifyPaymentTests(TestCase):
    def setUp(self):
        self.adapter = ZarinpalAdapter()
        self.creds = {"merchant_id": VALID_MERCHANT}

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_success_code_100(self, mock_post):
        mock_post.return_value = _resp(
            {"data": {"code": 100, "ref_id": 123456789, "card_pan": "502229******5995"}, "errors": []}
        )
        result = self.adapter.verify_payment(
            track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
            credentials=self.creds, callback_data={"Status": "OK"},
        )
        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "123456789")
        self.assertEqual(result.card_number, "502229******5995")
        self.assertEqual(result.status_code, 100)

        # Verify request uses the correct endpoint and sends the Rial amount.
        self.assertEqual(mock_post.call_args.args[0], ZARINPAL_VERIFY_URL)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["merchant_id"], VALID_MERCHANT)
        self.assertEqual(sent["authority"], "A123")
        self.assertEqual(sent["amount"], 250000 * TOMAN_TO_RIAL)
        self.assertEqual(mock_post.call_args.kwargs["timeout"], (10, 30))

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_already_verified_code_101_is_success(self, mock_post):
        # Per the docs: a second verify of the SAME transaction returns 101,
        # which is a SUCCESSFUL (already verified) state — idempotent.
        mock_post.return_value = _resp(
            {"data": {"code": 101, "ref_id": 123456789, "card_pan": "502229******5995"}, "errors": []}
        )
        result = self.adapter.verify_payment(
            track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
            credentials=self.creds, callback_data={"Status": "OK"},
        )
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 101)
        self.assertEqual(result.ref_id, "123456789")

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_failure_other_code(self, mock_post):
        # -51: unsuccessful payment (documented).
        mock_post.return_value = _resp({"data": {"code": -51, "message": "failed"}, "errors": []})
        result = self.adapter.verify_payment(
            track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
            credentials=self.creds, callback_data={"Status": "NOK"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.ref_id, "")
        self.assertEqual(result.status_code, -51)

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_amount_mismatch_raises(self, mock_post):
        # Gateway confirmed (code 100) but echoes a DIFFERENT amount -> money
        # may have moved -> GatewayAmountMismatchError with evidence.
        mock_post.return_value = _resp(
            {"data": {"code": 100, "ref_id": 1, "card_pan": "x", "amount": 9999990}, "errors": []}
        )
        with self.assertRaises(GatewayAmountMismatchError) as ctx:
            self.adapter.verify_payment(
                track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
                credentials=self.creds, callback_data={"Status": "OK"},
            )
        details = ctx.exception.details
        self.assertEqual(details["expected_rial"], 250000 * TOMAN_TO_RIAL)
        self.assertEqual(details["returned_rial"], 9999990)
        self.assertIn("evidence", details)

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_amount_match_echoed_amount_ok(self, mock_post):
        mock_post.return_value = _resp(
            {"data": {"code": 100, "ref_id": 7, "card_pan": "x", "amount": 2500000}, "errors": []}
        )
        result = self.adapter.verify_payment(
            track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
            credentials=self.creds, callback_data={"Status": "OK"},
        )
        self.assertTrue(result.success)

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = requests.Timeout("verify timeout")
        with self.assertRaises(GatewayConnectionError):
            self.adapter.verify_payment(
                track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
                credentials=self.creds, callback_data={},
            )

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_malformed_json_raises_response_error(self, mock_post):
        mock = MagicMock()
        mock.json.side_effect = ValueError("no json")
        mock.status_code = 500
        mock_post.return_value = mock
        with self.assertRaises(GatewayResponseError):
            self.adapter.verify_payment(
                track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
                credentials=self.creds, callback_data={},
            )

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_missing_data_raises_response_error(self, mock_post):
        mock_post.return_value = _resp({"errors": {"code": -54}})
        with self.assertRaises(GatewayResponseError):
            self.adapter.verify_payment(
                track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
                credentials=self.creds, callback_data={},
            )

    def test_verify_without_credentials_raises(self):
        with self.assertRaises(GatewayCredentialError):
            self.adapter.verify_payment(
                track_id="A123", expected_amount=Decimal("250000"), currency="TOMAN",
                credentials={}, callback_data={},
            )


class ZarinpalCredentialLeakTests(TestCase):
    """The merchant_id must never leak into error messages / exceptions."""

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_merchant_id_not_in_payment_error(self, mock_post):
        adapter = ZarinpalAdapter()
        mock_post.return_value = _resp({"data": {"code": -11, "message": "x"}, "errors": []})
        try:
            adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials={"merchant_id": VALID_MERCHANT}, order_code="DM-Z9",
            )
        except GatewayPaymentError as exc:
            self.assertNotIn(VALID_MERCHANT, str(exc))
            self.assertNotIn(VALID_MERCHANT, repr(exc.details))
