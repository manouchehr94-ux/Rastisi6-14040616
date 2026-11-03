"""FEAT-006 (M8) — currency conversion & rounding at provider boundaries.

RastiSi stores all order amounts in TOMAN as integer ``Decimal`` values
(``decimal_places=0``). The Iranian online gateways (Zibal, Zarinpal) expect
the amount in RIAL (Toman x 10). This module proves, with ``Decimal`` / integer
assertions:

* the Toman -> Rial conversion happens EXACTLY ONCE, at the adapter boundary;
* there is NO accidental 10x or 0.1x error (no double conversion, no missing
  conversion);
* no float is used anywhere in the amount path (amounts stay ``Decimal`` /
  ``int``);
* the amount actually submitted to each provider is recorded (on the create
  request payload and on the verify request payload, and the stored
  ``PaymentAttempt.amount`` is the authoritative Toman total).

All provider HTTP is MOCKED; no real endpoint is contacted.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.orders.gateways.zarinpal import (
    TOMAN_TO_RIAL as ZARINPAL_TOMAN_TO_RIAL,
    ZARINPAL_CURRENCY_RIAL,
    ZarinpalAdapter,
)
from apps.orders.gateways.zibal import (
    TOMAN_TO_RIAL as ZIBAL_TOMAN_TO_RIAL,
    ZibalAdapter,
)

VALID_MERCHANT_36 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

# A representative set of Toman amounts, including values whose x10 could expose
# a float rounding bug if floats were ever used.
TOMAN_AMOUNTS = [
    Decimal("1"),
    Decimal("9"),
    Decimal("10"),
    Decimal("99"),
    Decimal("250000"),
    Decimal("1234567"),
    Decimal("9999999"),
]


def _resp(json_body):
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = 200
    return mock


class ZibalCurrencyTests(TestCase):
    def setUp(self):
        self.adapter = ZibalAdapter()
        self.creds = {"merchant": "m-zibal"}

    def test_multiplier_is_exactly_ten(self):
        self.assertEqual(ZIBAL_TOMAN_TO_RIAL, 10)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_create_converts_toman_to_rial_exactly_once(self, mock_post):
        for toman in TOMAN_AMOUNTS:
            mock_post.return_value = _resp({"result": 100, "trackId": "T1"})
            self.adapter.create_payment(
                amount=toman,
                currency="TOMAN",
                callback_url="https://x/cb",
                credentials=self.creds,
                order_code="DM-CUR",
            )
            sent = mock_post.call_args.kwargs["json"]
            expected_rial = int(toman) * 10
            self.assertEqual(sent["amount"], expected_rial, toman)
            # Submitted amount is a plain int (no float) and is exactly x10.
            self.assertIsInstance(sent["amount"], int)
            self.assertNotEqual(sent["amount"], int(toman))  # not un-converted
            self.assertNotEqual(sent["amount"], int(toman) * 100)  # not double x10

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_amount_match_uses_rial_no_double_conversion(self, mock_post):
        toman = Decimal("250000")
        mock_post.return_value = _resp(
            {
                "result": 100,
                "status": 1,
                "amount": int(toman) * 10,  # gateway echoes Rial
                "refNumber": "R1",
                "cardNumber": "x",
            }
        )
        result = self.adapter.verify_payment(
            track_id="T1",
            expected_amount=toman,
            currency="TOMAN",
            credentials=self.creds,
            callback_data={},
        )
        self.assertTrue(result.success)

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_verify_detects_10x_mismatch(self, mock_post):
        from apps.orders.gateways.base import GatewayAmountMismatchError

        toman = Decimal("250000")
        # Gateway echoes TEN TIMES the correct Rial (a double-conversion bug):
        mock_post.return_value = _resp(
            {
                "result": 100,
                "status": 1,
                "amount": int(toman) * 100,
                "refNumber": "R1",
                "cardNumber": "x",
            }
        )
        with self.assertRaises(GatewayAmountMismatchError) as ctx:
            self.adapter.verify_payment(
                track_id="T1",
                expected_amount=toman,
                currency="TOMAN",
                credentials=self.creds,
                callback_data={},
            )
        details = ctx.exception.details
        self.assertEqual(details["expected_rial"], int(toman) * 10)
        self.assertEqual(details["returned_rial"], int(toman) * 100)


class ZarinpalCurrencyTests(TestCase):
    def setUp(self):
        self.adapter = ZarinpalAdapter()
        self.creds = {"merchant_id": VALID_MERCHANT_36}

    def test_multiplier_is_exactly_ten(self):
        self.assertEqual(ZARINPAL_TOMAN_TO_RIAL, 10)

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_create_sends_rial_and_pins_currency_irr(self, mock_post):
        for toman in TOMAN_AMOUNTS:
            mock_post.return_value = _resp(
                {"data": {"code": 100, "authority": "A" + "0" * 35}, "errors": []}
            )
            self.adapter.create_payment(
                amount=toman,
                currency="TOMAN",
                callback_url="https://x/cb",
                credentials=self.creds,
                order_code="DM-CUR-Z",
            )
            sent = mock_post.call_args.kwargs["json"]
            expected_rial = int(toman) * 10
            self.assertEqual(sent["amount"], expected_rial, toman)
            self.assertIsInstance(sent["amount"], int)
            # currency explicitly pinned to IRR so amount is unambiguously Rial.
            self.assertEqual(sent["currency"], ZARINPAL_CURRENCY_RIAL)
            self.assertEqual(sent["currency"], "IRR")

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_sends_rial_amount(self, mock_post):
        toman = Decimal("250000")
        mock_post.return_value = _resp(
            {"data": {"code": 100, "ref_id": 7, "card_pan": "x"}, "errors": []}
        )
        self.adapter.verify_payment(
            track_id="A123",
            expected_amount=toman,
            currency="TOMAN",
            credentials=self.creds,
            callback_data={"Status": "OK"},
        )
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["amount"], int(toman) * 10)
        self.assertIsInstance(sent["amount"], int)

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_verify_detects_0_1x_mismatch(self, mock_post):
        from apps.orders.gateways.base import GatewayAmountMismatchError

        toman = Decimal("250000")
        # Gateway echoes the TOMAN value (conversion forgotten) -> 0.1x of Rial.
        mock_post.return_value = _resp(
            {
                "data": {
                    "code": 100,
                    "ref_id": 1,
                    "card_pan": "x",
                    "amount": int(toman),  # Toman, not Rial -> mismatch
                },
                "errors": [],
            }
        )
        with self.assertRaises(GatewayAmountMismatchError) as ctx:
            self.adapter.verify_payment(
                track_id="A123",
                expected_amount=toman,
                currency="TOMAN",
                credentials=self.creds,
                callback_data={"Status": "OK"},
            )
        details = ctx.exception.details
        self.assertEqual(details["expected_rial"], int(toman) * 10)
        self.assertEqual(details["returned_rial"], int(toman))


class AmountTypeIntegrityTests(TestCase):
    """No float anywhere in the amount path; amounts are Decimal/int."""

    @patch("apps.orders.gateways.zibal.requests.post")
    def test_submitted_amount_is_int_not_float(self, mock_post):
        mock_post.return_value = _resp({"result": 100, "trackId": "T1"})
        ZibalAdapter().create_payment(
            amount=Decimal("250000"),
            currency="TOMAN",
            callback_url="https://x/cb",
            credentials={"merchant": "m"},
            order_code="DM-INT",
        )
        sent = mock_post.call_args.kwargs["json"]
        self.assertIsInstance(sent["amount"], int)
        self.assertNotIsInstance(sent["amount"], float)

    @patch("apps.orders.gateways.zarinpal.requests.post")
    def test_zarinpal_submitted_amount_is_int_not_float(self, mock_post):
        mock_post.return_value = _resp(
            {"data": {"code": 100, "authority": "A" + "0" * 35}, "errors": []}
        )
        ZarinpalAdapter().create_payment(
            amount=Decimal("250000"),
            currency="TOMAN",
            callback_url="https://x/cb",
            credentials={"merchant_id": VALID_MERCHANT_36},
            order_code="DM-INT-Z",
        )
        sent = mock_post.call_args.kwargs["json"]
        self.assertIsInstance(sent["amount"], int)
        self.assertNotIsInstance(sent["amount"], float)


class RecordedSubmittedAmountTests(TestCase):
    """The amount actually submitted to the provider is recorded end to end.

    The orchestrator stores the authoritative Toman total on
    ``PaymentAttempt.amount`` and submits its Rial equivalent. These tests use
    the real orchestrator with a mocked adapter boundary.
    """

    def setUp(self):
        from decimal import Decimal as D

        from apps.catalog.models import Vendor
        from apps.customers.models import Customer
        from apps.orders.encryption import reset_fernet
        from apps.orders.models import Order, PaymentGateway, ShippingMethod
        from apps.stores.models import Store
        from django.contrib.auth import get_user_model

        reset_fernet()
        self.addCleanup(reset_fernet)
        self.store = Store.objects.get(slug="akhlaghi")
        user = get_user_model().objects.create_user(username="cur_user", password="x12345678")
        self.customer = Customer.objects.create(user=user, full_name="c", phone="09120000001")
        self.vendor = Vendor.objects.create(store=self.store, name="v", slug="cur-vendor")
        self.shipping = ShippingMethod.objects.create(
            store=self.store, name="p", slug="cur-post", cost=D("0"), is_active=True
        )
        self.gateway = PaymentGateway.objects.create(
            store=self.store, name="زیبال", slug="zibal", is_active=True
        )
        self.order = Order.objects.create(
            code="DM-CUR-REC",
            store=self.store,
            customer=self.customer,
            vendor=self.vendor,
            address={},
            shipping_method=self.shipping,
            payment_gateway=self.gateway,
            items_total=D("250000"),
            grand_total=D("250000"),
        )

    def test_attempt_amount_is_authoritative_toman_total(self):
        from decimal import Decimal as D
        from unittest.mock import patch as _patch

        from apps.orders.models import PaymentAttempt, PaymentGatewayConfig
        from apps.orders.services.gateway_payment_service import initiate_payment

        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=True, is_sandbox=False
        )
        config.set_credentials({"merchant": "m-rec"})
        config.save()

        with _patch("apps.orders.gateways.zibal.requests.post") as mock_post:
            mock_post.return_value = _resp({"result": 100, "trackId": "TREC"})
            attempt = initiate_payment(
                order=self.order,
                gateway_config=config,
                callback_url="https://x/cb",
                store=self.store,
            )
            # Submitted Rial == order Toman x 10, recorded Toman == order total.
            sent = mock_post.call_args.kwargs["json"]
            self.assertEqual(sent["amount"], int(self.order.grand_total) * 10)
        self.assertEqual(attempt.amount, D("250000"))
        self.assertEqual(attempt.currency, "TOMAN")
        self.assertEqual(attempt.status, PaymentAttempt.Status.REDIRECT_READY)
