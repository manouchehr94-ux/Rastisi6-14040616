"""Contract tests for the Parsian / PEC PSP adapter (DOCUMENTATION_BLOCKED skeleton).

No real network is involved. The official PEC contract (historically SOAP/WSDL)
was not reachable, so the adapter only validates credentials + declares its
category and must raise GatewayUnsupportedOperationError for every money-moving
method. Tests assert that honest behavior and DOCUMENTATION_BLOCKED readiness.
"""

from decimal import Decimal

from django.test import TestCase

from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import (
    GatewayCategory,
    GatewayUnsupportedOperationError,
)
from apps.orders.gateways.parsian import ParsianAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CREDS = {"login_account": "abcd1234efgh5678"}


class ParsianRegistryTests(TestCase):
    def test_registered_as_online_psp(self):
        adapter = get_adapter("parsian")
        self.assertIsInstance(adapter, ParsianAdapter)
        self.assertEqual(adapter.code, "parsian")
        self.assertTrue(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.PSP)
        self.assertTrue(adapter.documentation_blocked)

    def test_declares_no_capabilities(self):
        self.assertEqual(get_adapter("parsian").capabilities, frozenset())


class ParsianCredentialTests(TestCase):
    def setUp(self):
        self.adapter = ParsianAdapter()

    def test_required_credentials(self):
        self.assertEqual(self.adapter.required_credentials, ["login_account"])

    def test_valid_credentials(self):
        self.assertEqual(self.adapter.validate_credentials(VALID_CREDS), [])

    def test_missing_credentials(self):
        self.assertTrue(self.adapter.validate_credentials({}))

    def test_credential_values_never_in_errors(self):
        for message in self.adapter.validate_credentials({}):
            self.assertNotIn("abcd1234efgh5678", message)


class ParsianUnsupportedOperationTests(TestCase):
    def setUp(self):
        self.adapter = ParsianAdapter()

    def test_create_payment_unsupported(self):
        with self.assertRaises(GatewayUnsupportedOperationError):
            self.adapter.create_payment(
                amount=Decimal("1000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=VALID_CREDS, order_code="DM-PA1",
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


class ParsianReadinessTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_readiness_is_documentation_blocked(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="parsian", is_active=True,
        )
        config.set_credentials(VALID_CREDS)
        config.save()
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.DOCUMENTATION_BLOCKED,
        )
        self.assertFalse(config.is_selectable_at_checkout)
