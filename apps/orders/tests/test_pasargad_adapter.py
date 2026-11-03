"""Contract tests for the Pasargad (Dorsa IPG) PSP adapter.

All HTTP is MOCKED via ``unittest.mock.patch`` on
``apps.orders.gateways.pasargad.requests.post`` — NO real network calls are
ever made. Assertions follow the official Dorsa REST contract verified
2026-11-03 from the ``pep-ipg/Dorsa-IPG-pasargad`` docs (api-reference.md,
usage-guides.md, error-codes.md):

- Auth: POST /token/getToken {username, password} -> {resultCode:0, token};
  Bearer token, 10-minute expiry; HTTP 401 -> re-authenticate once.
- create: POST /api/payment/purchase -> {resultCode:0, data:{urlId, url}}.
- inquiry: POST /api/payment/payment-inquiry {invoiceId}
  -> data{status, amount, referenceNumber, cardNumber, ...}.
- verify: POST /api/payment/verify-transactions {invoice, urlId}.
- reverse: POST /api/payment/reverse-transactions {invoice, urlId}.
- Status codes (error-codes.md): 0 success, 13029 confirmed, 13034 verify
  received = paid; 13033 reversed, 13025 unsuccessful, 2 unknown = not paid;
  13071 amount mismatch.

These tests FAIL if the adapter is reverted to the documentation-blocked
skeleton (capabilities != empty, documentation_blocked False, real endpoints).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayPaymentError,
    PaymentOperation,
)
from apps.orders.gateways.pasargad import (
    PASARGAD_INQUIRY_URL,
    PASARGAD_PURCHASE_URL,
    PASARGAD_REVERSE_URL,
    PASARGAD_TOKEN_URL,
    PASARGAD_VERIFY_URL,
    TOMAN_TO_RIAL,
    PasargadAdapter,
    current_jalali_date_string,
    gregorian_to_jalali,
)
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {
    "username": "merchant-user",
    "password": "s3cr3t-pass",
    "terminalNumber": "123456",
    "serviceCode": "8",
}


def _resp(json_body, status_code=200):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = status_code
    return mock


def _token_ok():
    return _resp({"resultCode": 0, "resultMsg": "موفق", "token": "TKN-ABC"})


class PasargadRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("pasargad")
        self.assertIsInstance(adapter, PasargadAdapter)
        self.assertEqual(adapter.code, "pasargad")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        # Real contract: NOT documentation-blocked.
        self.assertFalse(adapter.documentation_blocked)

    def test_capabilities_create_verify_inquire_cancel(self):
        adapter = get_adapter("pasargad")
        self.assertEqual(
            adapter.capabilities,
            frozenset(
                {
                    PaymentOperation.CREATE,
                    PaymentOperation.VERIFY,
                    PaymentOperation.INQUIRE,
                    PaymentOperation.CANCEL,
                }
            ),
        )
        # REFUND/SETTLE are intentionally NOT declared.
        self.assertFalse(adapter.supports(PaymentOperation.REFUND))
        self.assertFalse(adapter.supports(PaymentOperation.SETTLE))


class PasargadCredentialTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials,
            ["username", "password", "terminalNumber", "serviceCode"],
        )
        # The stale RSA private_key requirement is gone.
        self.assertNotIn("private_key", self.adapter.required_credentials)

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        errors = self.adapter.validate_credentials({})
        self.assertEqual(len(errors), 4)

    def test_non_numeric_service_code(self):
        errors = self.adapter.validate_credentials(
            {**VALID_CREDS, "serviceCode": "abc"}
        )
        self.assertTrue(errors)

    def test_credential_values_never_in_errors(self):
        errors = self.adapter.validate_credentials({"username": "merchant-user"})
        self.assertTrue(errors)
        for message in errors:
            self.assertNotIn("merchant-user", message)
            self.assertNotIn("s3cr3t-pass", message)


class PasargadJalaliTests(TestCase):
    def test_known_gregorian_to_jalali(self):
        # 2024-01-25 (Gregorian) == 1402-11-05 (Jalali).
        self.assertEqual(gregorian_to_jalali(2024, 1, 25), (1402, 11, 5))
        # 2021-03-21 == Nowruz 1400-01-01.
        self.assertEqual(gregorian_to_jalali(2021, 3, 21), (1400, 1, 1))

    def test_current_jalali_date_string_format(self):
        import datetime

        s = current_jalali_date_string(datetime.date(2024, 1, 25))
        self.assertEqual(s, "1402-11-05")
        self.assertRegex(s, r"^\d{4}-\d{2}-\d{2}$")


class PasargadTokenTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_token_success(self, mock_post):
        mock_post.return_value = _token_ok()
        token = self.adapter._get_token(VALID_CREDS)
        self.assertEqual(token, "TKN-ABC")
        self.assertEqual(mock_post.call_args.args[0], PASARGAD_TOKEN_URL)
        self.assertEqual(mock_post.call_args.kwargs["timeout"], (10, 30))
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["username"], "merchant-user")
        self.assertEqual(sent["password"], "s3cr3t-pass")

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_401_triggers_reauth_once(self, mock_post):
        # token -> 401 on purchase -> token again -> success.
        purchase_ok = _resp(
            {"resultCode": 0, "data": {"urlId": "U1", "url": "https://pep.shaparak.ir/dorsa1/U1"}}
        )
        mock_post.side_effect = [
            _token_ok(),                       # first getToken
            _resp({}, status_code=401),        # purchase -> 401
            _token_ok(),                       # re-auth
            purchase_ok,                       # purchase retry succeeds
        ]
        result = self.adapter.create_payment(
            amount=Decimal("1000"), currency="TOMAN",
            callback_url="https://shop.example/cb", credentials=VALID_CREDS,
            order_code="DM-P1",
        )
        self.assertEqual(result.extra["urlId"], "U1")
        # token, purchase(401), re-token, purchase(ok) = 4 calls.
        self.assertEqual(mock_post.call_count, 4)


class PasargadCreateTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_create_success_parses_url_and_track_id(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp(
                {
                    "resultCode": 0,
                    "data": {"urlId": "URL-77", "url": "https://pep.shaparak.ir/dorsa1/URL-77"},
                }
            ),
        ]
        result = self.adapter.create_payment(
            amount=Decimal("250000"), currency="TOMAN",
            callback_url="https://shop.example/cb", credentials=VALID_CREDS,
            order_code="DM-P2",
        )
        self.assertEqual(result.track_id, "DM-P2")
        self.assertEqual(result.gateway_url, "https://pep.shaparak.ir/dorsa1/URL-77")
        self.assertEqual(result.extra["urlId"], "URL-77")
        self.assertEqual(result.extra["invoice"], "DM-P2")

        # Purchase hit the documented endpoint with the Bearer header.
        purchase_call = mock_post.call_args_list[1]
        self.assertEqual(purchase_call.args[0], PASARGAD_PURCHASE_URL)
        self.assertEqual(
            purchase_call.kwargs["headers"]["Authorization"], "Bearer TKN-ABC"
        )
        sent = purchase_call.kwargs["json"]
        # Toman -> Rial conversion happens exactly once.
        self.assertEqual(sent["amount"], 250000 * TOMAN_TO_RIAL)
        self.assertEqual(sent["invoice"], "DM-P2")
        self.assertEqual(sent["serviceType"], "PURCHASE")
        self.assertEqual(sent["serviceCode"], 8)
        self.assertEqual(sent["terminalNumber"], "123456")
        self.assertEqual(sent["callbackApi"], "https://shop.example/cb")
        self.assertRegex(sent["invoiceDate"], r"^\d{4}-\d{2}-\d{2}$")

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_create_nonzero_result_code_raises(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp({"resultCode": 13003, "resultMsg": "شماره فاکتور تکراری است"}),
        ]
        with self.assertRaises(GatewayPaymentError) as ctx:
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN",
                callback_url="https://shop.example/cb", credentials=VALID_CREDS,
                order_code="DM-P3",
            )
        self.assertEqual(ctx.exception.details["resultCode"], 13003)


class PasargadVerifyTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_verify_happy_path(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp(
                {
                    "resultCode": 0,
                    "data": {
                        "status": 0,
                        "amount": 1000 * TOMAN_TO_RIAL,
                        "referenceNumber": "REF-900",
                        "cardNumber": "6037********1234",
                        "trackId": "TRK-1",
                    },
                }
            ),
            _resp(
                {
                    "resultCode": 0,
                    "data": {
                        "referenceNumber": "REF-900",
                        "maskedCardNumber": "6037********1234",
                    },
                }
            ),
        ]
        result = self.adapter.verify_payment(
            track_id="DM-P4", expected_amount=Decimal("1000"), currency="TOMAN",
            credentials=VALID_CREDS, callback_data={"urlId": "URL-4"},
        )
        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "REF-900")
        self.assertEqual(result.card_number, "6037********1234")
        self.assertEqual(result.status_code, 0)

        # inquiry then verify-transactions on documented endpoints.
        self.assertEqual(mock_post.call_args_list[1].args[0], PASARGAD_INQUIRY_URL)
        self.assertEqual(mock_post.call_args_list[1].kwargs["json"], {"invoiceId": "DM-P4"})
        self.assertEqual(mock_post.call_args_list[2].args[0], PASARGAD_VERIFY_URL)
        self.assertEqual(
            mock_post.call_args_list[2].kwargs["json"],
            {"invoice": "DM-P4", "urlId": "URL-4"},
        )

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_verify_confirmed_status_13029_is_paid(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp(
                {
                    "resultCode": 0,
                    "data": {
                        "status": 13029,
                        "amount": 1000 * TOMAN_TO_RIAL,
                        "referenceNumber": "REF-1",
                    },
                }
            ),
            _resp({"resultCode": 0, "data": {}}),
        ]
        result = self.adapter.verify_payment(
            track_id="DM-P5", expected_amount=Decimal("1000"), currency="TOMAN",
            credentials=VALID_CREDS, callback_data={"urlId": "U5"},
        )
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 13029)

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_verify_amount_mismatch_raises_with_evidence(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp(
                {
                    "resultCode": 0,
                    "data": {
                        "status": 0,
                        "amount": 5000 * TOMAN_TO_RIAL,  # wrong amount
                        "referenceNumber": "REF-X",
                        "cardNumber": "6037********9999",
                    },
                }
            ),
        ]
        with self.assertRaises(GatewayAmountMismatchError) as ctx:
            self.adapter.verify_payment(
                track_id="DM-P6", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={"urlId": "U6"},
            )
        details = ctx.exception.details
        self.assertEqual(details["expected_rial"], 1000 * TOMAN_TO_RIAL)
        self.assertEqual(details["returned_rial"], 5000 * TOMAN_TO_RIAL)
        self.assertEqual(details["evidence"]["ref_id"], "REF-X")
        # No verify-transactions call after a mismatch (token + inquiry only).
        self.assertEqual(mock_post.call_count, 2)

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_verify_reversed_status_is_not_success(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp({"resultCode": 0, "data": {"status": 13033, "referenceNumber": "R"}}),
        ]
        result = self.adapter.verify_payment(
            track_id="DM-P7", expected_amount=Decimal("1000"), currency="TOMAN",
            credentials=VALID_CREDS, callback_data={"urlId": "U7"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 13033)
        # No finalize call for a not-paid status.
        self.assertEqual(mock_post.call_count, 2)

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_verify_unsuccessful_status_is_not_success(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp({"resultCode": 0, "data": {"status": 13025}}),
        ]
        result = self.adapter.verify_payment(
            track_id="DM-P8", expected_amount=Decimal("1000"), currency="TOMAN",
            credentials=VALID_CREDS, callback_data={"urlId": "U8"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 13025)


class PasargadInquireCancelTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_inquire_hits_inquiry_endpoint(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp({"resultCode": 0, "data": {"status": 0, "referenceNumber": "REF-INQ"}}),
        ]
        result = self.adapter.inquire_payment(
            track_id="DM-P9", expected_amount=Decimal("1000"), currency="TOMAN",
            credentials=VALID_CREDS,
        )
        self.assertTrue(result.paid)
        self.assertEqual(result.ref_id, "REF-INQ")
        self.assertEqual(mock_post.call_args_list[1].args[0], PASARGAD_INQUIRY_URL)
        self.assertEqual(
            mock_post.call_args_list[1].kwargs["json"], {"invoiceId": "DM-P9"}
        )

    @patch("apps.orders.gateways.pasargad.requests.post")
    def test_cancel_hits_reverse_endpoint(self, mock_post):
        mock_post.side_effect = [
            _token_ok(),
            _resp({"resultCode": 0}),
        ]
        creds = {**VALID_CREDS, "_urlId": "U10"}
        result = self.adapter.cancel_payment(track_id="DM-P10", credentials=creds)
        self.assertTrue(result.success)
        self.assertEqual(mock_post.call_args_list[1].args[0], PASARGAD_REVERSE_URL)
        self.assertEqual(
            mock_post.call_args_list[1].kwargs["json"],
            {"invoice": "DM-P10", "urlId": "U10"},
        )


class PasargadReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_no_credentials_is_not_configured_and_not_selectable(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="pasargad", is_active=True,
        )
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NOT_CONFIGURED,
        )
        self.assertFalse(config.is_selectable_at_checkout)

    def test_partial_credentials_needs_credentials(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="pasargad", is_active=True,
        )
        config.set_credentials({"username": "u", "password": "p"})
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NEEDS_CREDENTIALS,
        )
        self.assertFalse(config.is_selectable_at_checkout)

    def test_full_credentials_active_non_sandbox_is_connected_and_selectable(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="pasargad", is_active=True, is_sandbox=False,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )
        self.assertTrue(config.is_selectable_at_checkout)

    def test_full_credentials_inactive_not_selectable(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="pasargad", is_active=False, is_sandbox=False,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertFalse(config.is_selectable_at_checkout)
