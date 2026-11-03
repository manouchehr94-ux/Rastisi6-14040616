"""Contract tests for the Saman / SEP PSP adapter (DOCUMENTATION_BLOCKED skeleton).

No real network is involved. The SEP landing page is a marketing page with no
technical contract, so the adapter only validates credentials + declares its
category and must raise GatewayUnsupportedOperationError for every money-moving
method. Tests assert that honest behavior and DOCUMENTATION_BLOCKED readiness.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
    PaymentOperation,
)
from apps.orders.gateways.saman import SamanAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"terminal_id": "12345678"}


class SamanRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("saman")
        self.assertIsInstance(adapter, SamanAdapter)
        self.assertEqual(adapter.code, "saman")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        self.assertTrue(adapter.documentation_blocked)

    def test_declares_no_capabilities(self):
        adapter = get_adapter("saman")
        self.assertEqual(adapter.capabilities, frozenset())


class SamanCredentialTests(TestCase):
    def setUp(self):
        self.adapter = SamanAdapter()

    def test_required_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["terminal_id"])

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertTrue(self.adapter.validate_credentials({}))

    def test_credential_values_never_in_errors(self):
        errors = self.adapter.validate_credentials({})
        for message in errors:
            self.assertNotIn("12345678", message)


class SamanUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = SamanAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-S1",
            )

    def test_build_redirect_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.build_redirect_url("t1")

    def test_verify_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.verify_payment(
                track_id="t1", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )

    def test_optional_operations_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.refund_payment(
                track_id="t1", amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.settle_payment(
                track_id="t1", amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )


class SamanReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="saman", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
