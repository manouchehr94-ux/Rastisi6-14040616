"""Contract tests for the Mellat / Behpardakht adapter — implemented, but its contract is UNVERIFIED (documentation_blocked stays True).

No real network: ``requests.post`` is replaced by an in-process SOAP fake mirroring the SECONDHAND contract the adapter encodes
(bpPayRequest / bpVerifyRequest / bpSettleRequest / bpInquiryRequest / bpReversalRequest; ``"code,RefId"`` answers). These tests prove
fail-closed behaviour — notably that SETTLE is distinct, ``48`` (reversed) is never "settled", and a callback is never proof — NOT that
the adapter matches the bank's current API. Passing them never makes the gateway "ready"."""

import re
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayConnectionError,
    GatewayCredentialError,
    GatewayPaymentError,
    GatewayResponseError,
    GatewayVerificationError,
    PaymentOperation,
)
from apps.orders.gateways.mellat import MELLAT_PAY_URL, MELLAT_SERVICE_URL, MellatAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"terminal_id": "123456", "username": "user", "password": "pass"}


class _Resp:
    def __init__(self, text):
        self.content = text.encode("utf-8")


def soap(value):
    return _Resp(
        '<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        f'<ns1:r xmlns:ns1="http://interfaces.core.sw.bps.com/"><return>{value}</return></ns1:r></soap:Body></soap:Envelope>'
    )


class FakeMellat:
    def __init__(self):
        self.calls = []
        self.answers = {"bpPayRequest": "0,REF-ID-1", "bpVerifyRequest": "0", "bpSettleRequest": "0", "bpInquiryRequest": "0", "bpReversalRequest": "0"}

    def __call__(self, url, data=None, headers=None, timeout=None, **kw):
        assert url == MELLAT_SERVICE_URL
        text = data.decode("utf-8")
        op = re.search(r"<int:(\w+)>", text).group(1)
        params = dict(re.findall(r"<(\w+)>([^<]*)</\1>", text))
        self.calls.append((op, params))
        answer = self.answers[op]
        return answer if isinstance(answer, _Resp) else soap(answer)

    def ops(self):
        return [op for op, _ in self.calls]


class MellatRegistryTests(TestCase):
    def test_registered_as_online_psp_with_blocked_documentation(self):
        adapter = get_adapter("mellat")
        self.assertIsInstance(adapter, MellatAdapter)
        self.assertEqual((adapter.code, adapter.is_online, adapter.category), ("mellat", True, GatewayCategory.PSP))
        self.assertTrue(adapter.documentation_blocked)

    def test_settle_is_a_distinct_capability(self):
        caps = get_adapter("mellat").capabilities
        self.assertEqual(caps, frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY, PaymentOperation.SETTLE,
                                          PaymentOperation.INQUIRE, PaymentOperation.CANCEL}))


class MellatCredentialTests(TestCase):
    def setUp(self):
        self.adapter = MellatAdapter()

    def test_required_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["terminal_id", "username", "password"])
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])
        self.assertEqual(len(self.adapter.validate_credentials({})), 3)
        self.assertTrue(self.adapter.validate_credentials({**VALID_CREDS, "terminal_id": "abc"}))

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({"username": "user"}):
            self.assertNotIn("pass", message)


class MellatContractTests(TestCase):
    ORDER = "1000000012"
    GOOD = {"ResCode": "0", "RefId": "REF-ID-1", "SaleOrderId": ORDER, "SaleReferenceId": "SALE-REF-9", "CardHolderPan": "603799******0019"}

    def setUp(self):
        self.adapter = MellatAdapter()
        self.fake = FakeMellat()
        patcher = patch("apps.orders.gateways.mellat.requests.post", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def verify(self, callback=None):
        return self.adapter.verify_payment(
            track_id=self.ORDER, expected_amount=Decimal("1000"), currency="TOMAN", credentials=VALID_CREDS,
            callback_data=self.GOOD if callback is None else callback,
        )

    def test_pay_request_uses_rial_numeric_order_and_returns_form_post_refid(self):
        result = self.adapter.create_payment(
            amount=Decimal("1000"), currency="TOMAN", callback_url="https://rastisi.ir/billing/return/T/",
            credentials=VALID_CREDS, order_code=self.ORDER,
        )
        op, params = self.fake.calls[0]
        self.assertEqual(op, "bpPayRequest")
        self.assertEqual((params["amount"], params["orderId"], params["terminalId"], params["userName"]), ("10000", self.ORDER, "123456", "user"))
        self.assertRegex(params["localDate"], r"^\d{8}$")
        self.assertRegex(params["localTime"], r"^\d{6}$")
        self.assertEqual(params["callBackUrl"], "https://rastisi.ir/billing/return/T/")
        self.assertEqual((result.track_id, result.gateway_url, result.extra["post_fields"]), (self.ORDER, MELLAT_PAY_URL, {"RefId": "REF-ID-1"}))

    def test_pay_request_rejects_non_numeric_order_ids_rejections_and_bad_answers(self):
        with self.assertRaises(GatewayPaymentError) as ctx:
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials=VALID_CREDS, order_code="ABC")
        self.assertEqual(ctx.exception.code, "order_id_not_numeric")
        self.fake.answers["bpPayRequest"] = "421"
        with self.assertRaises(GatewayPaymentError) as ctx:
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials=VALID_CREDS, order_code=self.ORDER)
        self.assertEqual(ctx.exception.code, "mellat_421")
        with self.assertRaises(GatewayCredentialError):
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials={}, order_code=self.ORDER)

    def test_verify_uses_our_order_id_and_the_banks_sale_reference(self):
        result = self.verify()
        self.assertTrue(result.success)
        self.assertEqual(result.ref_id, "SALE-REF-9")
        op, params = self.fake.calls[-1]
        self.assertEqual((op, params["orderId"], params["saleOrderId"], params["saleReferenceId"]), ("bpVerifyRequest", self.ORDER, self.ORDER, "SALE-REF-9"))

    def test_a_failed_or_foreign_callback_never_verifies(self):
        self.assertFalse(self.verify({**self.GOOD, "ResCode": "17"}).success)               # user cancelled
        self.assertFalse(self.verify({"ResCode": "0", "SaleOrderId": self.ORDER}).success)   # no sale reference
        self.assertEqual(self.fake.calls, [])
        with self.assertRaises(GatewayVerificationError) as ctx:
            self.verify({**self.GOOD, "SaleOrderId": "999"})
        self.assertEqual(ctx.exception.code, "saleorder_mismatch")
        self.assertEqual(self.fake.calls, [])

    def test_verify_rejection_is_not_success_and_already_verified_is_accepted(self):
        self.fake.answers["bpVerifyRequest"] = "41"
        with self.assertRaises(GatewayVerificationError):
            self.verify()
        self.fake.answers["bpVerifyRequest"] = "43"
        self.assertTrue(self.verify().success)

    def test_settle_is_a_separate_step_that_only_ok_or_already_settled_satisfy(self):
        creds = {**VALID_CREDS, "_saleReferenceId": "SALE-REF-9"}
        ok = self.adapter.settle_payment(track_id=self.ORDER, amount=Decimal("1000"), currency="TOMAN", credentials=creds)
        self.assertTrue(ok.success)
        self.assertEqual(self.fake.ops(), ["bpSettleRequest"])
        self.fake.answers["bpSettleRequest"] = "45"
        self.assertTrue(self.adapter.settle_payment(track_id=self.ORDER, amount=Decimal("1000"), currency="TOMAN", credentials=creds).success)
        for refused in ("48", "46", "47", "421"):                                          # 48 = REVERSED: must never count as settled
            self.fake.answers["bpSettleRequest"] = refused
            self.assertFalse(self.adapter.settle_payment(track_id=self.ORDER, amount=Decimal("1000"), currency="TOMAN", credentials=creds).success, refused)
        self.assertFalse(self.adapter.settle_payment(track_id=self.ORDER, amount=Decimal("1000"), currency="TOMAN", credentials=VALID_CREDS).success)

    def test_inquiry_never_claims_settled_and_flags_terminal_negative_results(self):
        creds = {**VALID_CREDS, "_saleReferenceId": "SALE-REF-9"}
        inq = self.adapter.inquire_payment(track_id=self.ORDER, expected_amount=Decimal("1000"), currency="TOMAN", credentials=creds)
        self.assertEqual((inq.paid, inq.settled, inq.terminal_negative), (True, False, False))
        self.fake.answers["bpInquiryRequest"] = "48"
        inq = self.adapter.inquire_payment(track_id=self.ORDER, expected_amount=Decimal("1000"), currency="TOMAN", credentials=creds)
        self.assertEqual((inq.paid, inq.terminal_negative), (False, True))

    def test_reversal(self):
        creds = {**VALID_CREDS, "_saleReferenceId": "SALE-REF-9"}
        self.assertTrue(self.adapter.cancel_payment(track_id=self.ORDER, credentials=creds).success)
        self.assertEqual(self.fake.ops(), ["bpReversalRequest"])
        self.assertFalse(self.adapter.cancel_payment(track_id=self.ORDER, credentials=VALID_CREDS).success)

    def test_hostile_xml_and_oversized_responses_are_refused(self):
        self.fake.answers["bpPayRequest"] = _Resp('<!DOCTYPE x [<!ENTITY e "boom">]><a>&e;</a>')
        with self.assertRaises(GatewayResponseError) as ctx:
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials=VALID_CREDS, order_code=self.ORDER)
        self.assertEqual(ctx.exception.code, "unsafe_xml")
        self.fake.answers["bpPayRequest"] = _Resp("<a>" + "x" * 70000 + "</a>")
        with self.assertRaises(GatewayResponseError) as ctx:
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials=VALID_CREDS, order_code=self.ORDER)
        self.assertEqual(ctx.exception.code, "response_too_large")
        self.fake.answers["bpPayRequest"] = _Resp("<not-xml")
        with self.assertRaises(GatewayResponseError):
            self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials=VALID_CREDS, order_code=self.ORDER)

    def test_xml_special_characters_in_credentials_are_escaped(self):
        self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/?a=1&b=2",
                                    credentials={**VALID_CREDS, "password": "p<a>&ss"}, order_code=self.ORDER)
        self.assertEqual(self.fake.calls[0][1]["userPassword"], "p&lt;a&gt;&amp;ss")

    def test_network_failure_is_typed_and_never_leaks_credentials(self):
        import requests

        with patch("apps.orders.gateways.mellat.requests.post", side_effect=requests.ConnectionError("pass boom")):
            with self.assertRaises(GatewayConnectionError) as ctx:
                self.adapter.create_payment(amount=Decimal("1"), currency="TOMAN", callback_url="https://x/", credentials=VALID_CREDS, order_code=self.ORDER)
        self.assertNotIn("pass", str(ctx.exception))


class MellatReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_store_checkout_readiness_stays_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="mellat", is_active=True)
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(config.readiness_status, PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED)
        self.assertFalse(config.is_selectable_at_checkout)
