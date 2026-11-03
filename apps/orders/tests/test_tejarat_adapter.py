"""Contract tests for the Tejarat PSP adapter (DOCUMENTATION_BLOCKED, special).

No real network is involved. "Tejarat" is a storefront display label; the
technical PSP was NOT confirmed from an official source (IranKish is not
assumed). The adapter only validates credentials + declares its category and
must raise GatewayUnsupportedOperationError for every money-moving method.
Tests assert the display label is kept as a label, the honest unsupported
behavior, and DOCUMENTATION_BLOCKED readiness.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
)
from apps.orders.gateways.tejarat import TejaratAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"terminal_id": "99887766"}


class TejaratRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("tejarat")
        self.assertIsInstance(adapter, TejaratAdapter)
        self.assertEqual(adapter.code, "tejarat")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        self.assertTrue(adapter.documentation_blocked)

    def test_display_label_is_just_a_label(self):
        # Display name is the storefront label; it does not assert IranKish or
        # any specific technical PSP identity.
        adapter = get_adapter("tejarat")
        self.assertEqual(adapter.display_name, "بانک تجارت")
        self.assertNotIn("ایران", adapter.display_name)

    def test_declares_no_capabilities(self):
        self.assertEqual(get_adapter("tejarat").capabilities, frozenset())


class TejaratCredentialTests(TestCase):
    def setUp(self):
        self.adapter = TejaratAdapter()

    def test_required_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["terminal_id"])

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertTrue(self.adapter.validate_credentials({}))


class TejaratUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = TejaratAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-T1",
            )

    def test_verify_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.verify_payment(
                track_id="t1", expected_amount=Decimal("1000"), currency="TOMAN",
                credentials=VALID_CREDS, callback_data={},
            )


class TejaratReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="tejarat", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
