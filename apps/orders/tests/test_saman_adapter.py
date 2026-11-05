"""Contract tests for the Saman / SEP adapter — implemented, but its contract is UNVERIFIED (documentation_blocked stays True).

No real network: ``requests.post`` is replaced by an in-process fake that mirrors the SECONDHAND contract the adapter encodes
(JSON token request, form-POST redirect fields, callback fields, VerifyTransaction/ReverseTransaction). These tests prove the
adapter's fail-closed behaviour and its internal consistency — NOT that it matches Saman's current API. A passing test here never
makes the provider "ready": store checkout stays DOCUMENTATION_BLOCKED and platform billing holds it behind explicit gates."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayAmountMismatchError,
    GatewayCategory,
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayPaymentError,
    GatewayResponseError,
    GatewayVerificationError,
    PaymentOperation,
)
from apps.orders.gateways.saman import SEP_PAY_URL, SEP_REVERSE_URL, SEP_TOKEN_URL, SEP_VERIFY_URL, SamanAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"terminal_id": "12345678"}


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSep:
    def __init__(self):
        self.calls = []
        self.token = {"status": 1, "token": "TOKEN-SYNTH"}
        self.verify = {"Success": True, "ResultCode": 0, "TransactionDetail": {"RefNum": "REF-1", "OrginalAmount": 10000, "AffectiveAmount": 10000, "MaskedPan": "603799******0019"}}
        self.reverse = {"Success": True, "ResultCode": 0}

    def __call__(self, url, json=None, timeout=None, **kw):
        self.calls.append((url, dict(json or {})))
        return _Resp({SEP_TOKEN_URL: self.token, SEP_VERIFY_URL: self.verify, SEP_REVERSE_URL: self.reverse}[url])


class SamanRegistryTests(TestCase):
    def test_registered_as_online_psp_with_blocked_documentation(self):
        adapter = get_adapter("saman")
        self.assertIsInstance(adapter, SamanAdapter)
        self.assertEqual((adapter.code, adapter.is_online, adapter.category), ("saman", True, GatewayCategory.PSP))
        self.assertTrue(adapter.documentation_blocked)            # contract unverified ⇒ never selectable for stores

    def test_declares_exactly_the_operations_it_implements(self):
        caps = get_adapter("saman").capabilities
        self.assertEqual(caps, frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY, PaymentOperation.CANCEL}))
        self.assertNotIn(PaymentOperation.SETTLE, caps)           # no separate settle in this contract
        self.assertNotIn(PaymentOperation.INQUIRE, caps)          # no documented inquiry ⇒ a missed callback cannot be reconciled


class SamanCredentialTests(TestCase):
    def setUp(self):
        self.adapter = SamanAdapter()

    def test_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["terminal_id"])
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])
        self.assertTrue(self.adapter.validate_credentials({}))
        for message in self.adapter.validate_credentials({}):
            self.assertNotIn("12345678", message)


class SamanContractTests(TestCase):
    def setUp(self):
        self.adapter = SamanAdapter()
        self.fake = FakeSep()
        patcher = patch("apps.orders.gateways.saman.requests.post", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def create(self, **creds):
        return self.adapter.create_payment(
            amount=Decimal("1000"), currency="TOMAN", callback_url="https://rastisi.ir/billing/return/T/",
            credentials={**VALID_CREDS, **creds}, order_code="B000000012",
        )

    def verify(self, callback, amount="1000", **creds):
        return self.adapter.verify_payment(
            track_id="B000000012", expected_amount=Decimal(amount), currency="TOMAN",
            credentials={**VALID_CREDS, **creds}, callback_data=callback,
        )

    GOOD = {"State": "OK", "RefNum": "REF-1", "ResNum": "B000000012"}

    def test_token_request_converts_toman_to_rial_once_and_returns_form_post_fields(self):
        result = self.create(transaction_key="TXKEY")
        url, payload = self.fake.calls[0]
        self.assertEqual(url, SEP_TOKEN_URL)
        self.assertEqual((payload["action"], payload["Amount"], payload["ResNum"], payload["TerminalId"]), ("token", 10000, "B000000012", "12345678"))
        self.assertEqual(payload["TxnRandomSessionKey"], "TXKEY")
        self.assertEqual((result.track_id, result.gateway_url, result.extra["post_fields"]), ("B000000012", SEP_PAY_URL, {"Token": "TOKEN-SYNTH"}))
        self.assertEqual(self.adapter.build_redirect_url("x"), SEP_PAY_URL)

    def test_token_rejection_and_malformed_answers_are_typed_errors(self):
        self.fake.token = {"status": -1, "errorCode": 5, "errorDesc": "bad"}
        with self.assertRaises(GatewayPaymentError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "saman_5")
        self.fake.token = {"status": 1}
        with self.assertRaises(GatewayResponseError):
            self.create()
        with self.assertRaises(GatewayCredentialError):
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials={}, order_code="B1")

    def test_verified_payment_needs_provider_success_exact_amount_and_matching_refnum(self):
        result = self.verify(self.GOOD)
        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "REF-1")
        url, payload = self.fake.calls[-1]
        self.assertEqual((url, payload), (SEP_VERIFY_URL, {"RefNum": "REF-1", "TerminalNumber": 12345678}))

    def test_a_callback_that_is_not_ok_never_reaches_the_provider(self):
        result = self.verify({**self.GOOD, "State": "CanceledByUser"})
        self.assertFalse(result.success)
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.verify({"State": "OK", "ResNum": "B000000012"}).success)         # no RefNum ⇒ not verifiable

    def test_a_callback_for_another_order_is_rejected(self):
        with self.assertRaises(GatewayVerificationError) as ctx:
            self.verify({**self.GOOD, "ResNum": "B000000099"})
        self.assertEqual(ctx.exception.code, "resnum_mismatch")
        self.assertEqual(self.fake.calls, [])

    def test_provider_failure_is_not_success(self):
        self.fake.verify = {"Success": False, "ResultCode": -2}
        with self.assertRaises(GatewayVerificationError):
            self.verify(self.GOOD)

    def test_amount_mismatch_and_refnum_mismatch_raise_with_evidence(self):
        with self.assertRaises(GatewayAmountMismatchError) as ctx:
            self.verify(self.GOOD, amount="2000")
        self.assertEqual(ctx.exception.details["evidence"]["returned_rial"], 10000)
        self.fake.verify["TransactionDetail"]["RefNum"] = "OTHER"
        with self.assertRaises(GatewayAmountMismatchError):
            self.verify(self.GOOD)
        self.fake.verify = {"Success": True, "ResultCode": 0, "TransactionDetail": {}}
        with self.assertRaises(GatewayResponseError):
            self.verify(self.GOOD)

    def test_already_verified_result_code_two_is_accepted(self):
        self.fake.verify["ResultCode"] = 2
        self.assertTrue(self.verify(self.GOOD).success)

    def test_reverse_needs_the_refnum_and_reports_the_provider_answer(self):
        self.assertFalse(self.adapter.cancel_payment(track_id="x", credentials=VALID_CREDS).success)
        self.assertEqual(self.fake.calls, [])
        ok = self.adapter.cancel_payment(track_id="x", credentials={**VALID_CREDS, "_refNum": "REF-1"})
        self.assertTrue(ok.success)
        self.assertEqual(self.fake.calls[-1][0], SEP_REVERSE_URL)
        self.fake.reverse = {"Success": False, "ResultCode": -5}
        self.assertFalse(self.adapter.cancel_payment(track_id="x", credentials={**VALID_CREDS, "_refNum": "REF-1"}).success)

    def test_network_failures_are_typed_and_never_leak_credentials(self):
        import requests

        with patch("apps.orders.gateways.saman.requests.post", side_effect=requests.ConnectionError("12345678 boom")):
            with self.assertRaises(GatewayConnectionError) as ctx:
                self.create()
        self.assertNotIn("12345678", str(ctx.exception))


class SamanReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_store_checkout_readiness_stays_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="saman", is_active=True)
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(config.readiness_status, PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED)
        self.assertFalse(config.is_selectable_at_checkout)
