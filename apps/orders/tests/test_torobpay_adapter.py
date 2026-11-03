"""Contract tests for the TorobPay BNPL adapter (DOCUMENTATION_BLOCKED skeleton).

No real network is involved. TorobPay is a BNPL provider (category BNPL), not an
ordinary PSP. Only a non-authoritative WordPress plugin was available as
evidence, so the adapter only validates credentials + declares its category and
must raise GatewayUnsupportedOperationError for every money-moving method,
INCLUDING BNPL eligibility (no installment offers are fabricated). Tests assert
that honest behavior and DOCUMENTATION_BLOCKED readiness.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
    PaymentOperation,
)
from apps.orders.gateways.torobpay import TorobPayAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"client_id": "torob-client", "client_secret": "t0p-s3cr3t"}


class TorobPayRegistryTests(TestCase):
    def test_registered_as_online_bnpl(self):
        adapter = get_adapter("torobpay")
        self.assertIsInstance(adapter, TorobPayAdapter)
        self.assertEqual(adapter.code, "torobpay")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.BNPL)
        self.assertTrue(adapter.documentation_blocked)

    def test_declares_no_capabilities(self):
        adapter = get_adapter("torobpay")
        self.assertEqual(adapter.capabilities, frozenset())
        self.assertFalse(adapter.supports(PaymentOperation.SETTLE))


class TorobPayCredentialTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials, ["client_id", "client_secret"]
        )

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertEqual(len(self.adapter.validate_credentials({})), 2)

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({}):
            self.assertNotIn("t0p-s3cr3t", message)


class TorobPayUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = TorobPayAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-TP1",
            )

    def test_verify_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.verify_payment(
                track_id="t1", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )

    def test_settle_and_cancel_distinct_and_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.settle_payment(
                track_id="t1", amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.cancel_payment(track_id="t1", credentials=VALID_CREDS)

    def test_bnpl_eligibility_never_fabricated(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.check_bnpl_eligibility(
                amount=Decimal("5000000"), currency="TOMAN", credentials=VALID_CREDS,
            )


class TorobPayReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="torobpay", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
