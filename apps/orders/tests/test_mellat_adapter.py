"""Contract tests for the Mellat / Behpardakht PSP adapter (DOCUMENTATION_BLOCKED).

No real network is involved. The behpardakht host was unreachable, so the
adapter only validates credentials + declares its category and must raise
GatewayUnsupportedOperationError for every money-moving method (including the
SETTLE/finalization step, which is never emulated). Tests assert that honest
behavior and DOCUMENTATION_BLOCKED readiness.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
)
from apps.orders.gateways.mellat import MellatAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"terminal_id": "123456", "username": "user", "password": "pass"}


class MellatRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("mellat")
        self.assertIsInstance(adapter, MellatAdapter)
        self.assertEqual(adapter.code, "mellat")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        self.assertTrue(adapter.documentation_blocked)

    def test_declares_no_capabilities(self):
        self.assertEqual(get_adapter("mellat").capabilities, frozenset())


class MellatCredentialTests(TestCase):
    def setUp(self):
        self.adapter = MellatAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials,
            ["terminal_id", "username", "password"],
        )

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertEqual(len(self.adapter.validate_credentials({})), 3)

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({"username": "user"}):
            self.assertNotIn("pass", message)


class MellatUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = MellatAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-M1",
            )

    def test_verify_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.verify_payment(
                track_id="t1", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )

    def test_settle_is_not_emulated(self):
        # SETTLE (finalization) must NOT be conflated with verify nor emulated.
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.settle_payment(
                track_id="t1", amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS,
            )


class MellatReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="mellat", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
