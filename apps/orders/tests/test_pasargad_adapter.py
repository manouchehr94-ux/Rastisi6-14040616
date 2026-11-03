"""Contract tests for the Pasargad PSP adapter (DOCUMENTATION_BLOCKED skeleton).

No real network is ever involved — the adapter makes NO HTTP calls. Because the
official current Pasargad contract was not verifiable in this environment, the
adapter implements only credential validation + capability/category declaration
and must raise GatewayUnsupportedOperationError for every money-moving method.
These tests assert exactly that honest behavior and that the config's
readiness_status resolves to DOCUMENTATION_BLOCKED (never selectable at real
checkout). They do NOT assert any invented endpoint/signature/error-code.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
    PaymentOperation,
)
from apps.orders.gateways.pasargad import PasargadAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {
    "merchant_code": "100100100",
    "terminal_code": "200200200",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nAAAA\n-----END RSA PRIVATE KEY-----",
}


class PasargadRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("pasargad")
        self.assertIsInstance(adapter, PasargadAdapter)
        self.assertEqual(adapter.code, "pasargad")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        self.assertTrue(adapter.documentation_blocked)

    def test_declares_no_capabilities(self):
        adapter = get_adapter("pasargad")
        self.assertEqual(adapter.capabilities, frozenset())
        for op in PaymentOperation:
            self.assertFalse(adapter.supports(op))


class PasargadCredentialTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials,
            ["merchant_code", "terminal_code", "private_key"],
        )

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        errors = self.adapter.validate_credentials({})
        self.assertEqual(len(errors), 3)

    def test_credential_values_never_in_errors(self):
        errors = self.adapter.validate_credentials({"merchant_code": "100100100"})
        self.assertTrue(errors)
        for message in errors:
            self.assertNotIn("100100100", message)


class PasargadUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = PasargadAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-P1",
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
            self.adapter.inquire_payment(
                track_id="t1", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )
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
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.cancel_payment(track_id="t1", credentials=VALID_CREDS)


class PasargadReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="pasargad", is_active=False,
        )
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )

    def test_not_selectable_at_real_checkout_even_if_active(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="pasargad", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        # Documentation-blocked providers are never selectable at real checkout.
        self.assertFalse(config.is_selectable_at_checkout)
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
