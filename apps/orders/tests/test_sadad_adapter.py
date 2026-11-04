"""Contract tests for the Sadad (Bank Melli) PSP adapter (DOCUMENTATION_BLOCKED).

No real network is involved. The sadadpsp.ir host was unreachable, so the
adapter only validates credentials + declares its category and must raise
GatewayUnsupportedOperationError for every money-moving method. No signing or
encryption scheme is guessed. Tests assert that honest behavior and
DOCUMENTATION_BLOCKED readiness.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
)
from apps.orders.gateways.sadad import SadadAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"merchant_id": "m-1", "terminal_id": "t-1", "key": "c2lnbmluZy1rZXk="}


class SadadRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("sadad")
        self.assertIsInstance(adapter, SadadAdapter)
        self.assertEqual(adapter.code, "sadad")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        self.assertTrue(adapter.documentation_blocked)

    def test_declares_no_capabilities(self):
        self.assertEqual(get_adapter("sadad").capabilities, frozenset())


class SadadCredentialTests(TestCase):
    def setUp(self):
        self.adapter = SadadAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials,
            ["merchant_id", "terminal_id", "key"],
        )

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertEqual(len(self.adapter.validate_credentials({})), 3)

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({}):
            self.assertNotIn("c2lnbmluZy1rZXk=", message)


class SadadUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = SadadAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-SD1",
            )

    def test_verify_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.verify_payment(
                track_id="t1", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )

    def test_build_redirect_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.build_redirect_url("t1")


class SadadReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="sadad", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
