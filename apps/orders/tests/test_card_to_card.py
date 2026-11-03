"""Contract tests for the Manual Card-to-Card offline adapter.

No external network is involved (the adapter is offline). These tests assert:
- registration as an OFFLINE adapter with is_online == False and no capabilities
- credential validation (card number + cardholder required; IBAN optional/validated)
- verify_payment returns success=False BY DESIGN (never auto-verifies)
- card number / IBAN round-trip through the encrypted credentials mechanism and
  never leak into logs, str(), or the encrypted blob in plaintext
"""

import logging
from decimal import Decimal

from django.test import TestCase

from apps.orders.encryption import reset_fernet
from apps.orders.gateways import get_adapter
from apps.orders.gateways.base import GatewayCategory, PaymentOperation
from apps.orders.gateways.card_to_card import CardToCardAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store

VALID_CARD = "6037997599995995"
VALID_IBAN = "IR820540102680020817909002"


class CardToCardRegistryTests(TestCase):
    def test_registered_as_offline_adapter(self):
        adapter = get_adapter("card_to_card")
        self.assertIsInstance(adapter, CardToCardAdapter)
        self.assertEqual(adapter.code, "card_to_card")
        self.assertFalse(adapter.is_online)
        self.assertEqual(adapter.category, GatewayCategory.OFFLINE)
        self.assertFalse(adapter.documentation_blocked)

    def test_no_online_capabilities(self):
        adapter = get_adapter("card_to_card")
        self.assertEqual(adapter.capabilities, frozenset())
        self.assertFalse(adapter.supports(PaymentOperation.CREATE))
        self.assertFalse(adapter.supports(PaymentOperation.VERIFY))


class CardToCardCredentialTests(TestCase):
    def setUp(self):
        self.adapter = CardToCardAdapter()

    def test_required_credentials(self):
        self.assertEqual(
            self.adapter.required_credentials, ["card_number", "cardholder_name"]
        )

    def test_valid_config(self):
        errors = self.adapter.validate_credentials(
            {"card_number": VALID_CARD, "cardholder_name": "علی اکبری", "iban": VALID_IBAN}
        )
        self.assertEqual(errors, [])

    def test_valid_config_with_dashes(self):
        errors = self.adapter.validate_credentials(
            {"card_number": "6037-9975-9999-5995", "cardholder_name": "علی"}
        )
        self.assertEqual(errors, [])

    def test_missing_card_number(self):
        errors = self.adapter.validate_credentials({"cardholder_name": "علی"})
        self.assertTrue(errors)

    def test_missing_cardholder(self):
        errors = self.adapter.validate_credentials({"card_number": VALID_CARD})
        self.assertTrue(errors)

    def test_invalid_card_length(self):
        errors = self.adapter.validate_credentials(
            {"card_number": "12345", "cardholder_name": "علی"}
        )
        self.assertTrue(errors)

    def test_invalid_iban(self):
        errors = self.adapter.validate_credentials(
            {"card_number": VALID_CARD, "cardholder_name": "علی", "iban": "IR123"}
        )
        self.assertTrue(errors)

    def test_error_messages_do_not_leak_card_number(self):
        # Even with an invalid card, the number itself must not appear in errors.
        errors = self.adapter.validate_credentials(
            {"card_number": "1111222233334444", "cardholder_name": ""}
        )
        joined = " ".join(errors)
        self.assertNotIn("1111222233334444", joined)


class CardToCardFlowTests(TestCase):
    def setUp(self):
        self.adapter = CardToCardAdapter()

    def test_create_payment_no_redirect(self):
        result = self.adapter.create_payment(
            amount=Decimal("100000"), currency="TOMAN", callback_url="https://x/cb",
            credentials={"card_number": VALID_CARD, "cardholder_name": "علی"},
            order_code="DM-C1",
        )
        self.assertIsNone(result.gateway_url)
        self.assertIn("card2card", result.track_id)

    def test_build_redirect_url_empty(self):
        self.assertEqual(self.adapter.build_redirect_url("x"), "")

    def test_verify_never_auto_confirms(self):
        # By design: a customer-submitted receipt NEVER marks the order paid.
        result = self.adapter.verify_payment(
            track_id="card2card-DM-C1", expected_amount=Decimal("100000"),
            currency="TOMAN",
            credentials={"card_number": VALID_CARD, "cardholder_name": "علی"},
            callback_data={"receipt": "uploaded"},
        )
        self.assertFalse(result.success)


class CardToCardEncryptedConfigTests(TestCase):
    """Sensitive card/IBAN config round-trips via the encrypted credentials
    mechanism and is never stored or logged in plaintext."""

    def setUp(self):
        reset_fernet()
        self.store = Store.objects.get(slug="akhlaghi")

    def tearDown(self):
        reset_fernet()

    def test_card_and_iban_round_trip_encrypted(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="card_to_card", is_active=False,
        )
        config.set_credentials(
            {
                "card_number": VALID_CARD,
                "cardholder_name": "علی اکبری",
                "bank_name": "ملت",
                "iban": VALID_IBAN,
            }
        )
        config.save()
        config.refresh_from_db()

        # The encrypted blob must NOT contain the plaintext card/IBAN.
        self.assertNotIn(VALID_CARD, config.encrypted_credentials)
        self.assertNotIn(VALID_IBAN, config.encrypted_credentials)
        self.assertTrue(config.encrypted_credentials)

        # Decryption returns the original values.
        creds = config.get_credentials()
        self.assertEqual(creds["card_number"], VALID_CARD)
        self.assertEqual(creds["iban"], VALID_IBAN)
        self.assertEqual(creds["cardholder_name"], "علی اکبری")

    def test_readiness_needs_credentials_until_configured(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="card_to_card", is_active=False,
        )
        # No credentials yet -> not fully configured.
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.NOT_CONFIGURED,
        )

        config.set_credentials({"card_number": VALID_CARD, "cardholder_name": "علی"})
        config.save()
        # Offline + configured + non-sandbox -> CONNECTED.
        self.assertEqual(
            config.readiness_status,
            PaymentGatewayConfig.ReadinessStatus.CONNECTED,
        )

    def test_logs_do_not_leak_card_number(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="card_to_card", is_active=False,
        )
        config.set_credentials({"card_number": VALID_CARD, "cardholder_name": "علی"})
        config.save()

        adapter = CardToCardAdapter()
        with self.assertLogs("payment", level="INFO") as cm:
            adapter.create_payment(
                amount=Decimal("100000"), currency="TOMAN", callback_url="https://x/cb",
                credentials=config.get_credentials(), order_code="DM-C2",
            )
        logged = "\n".join(cm.output)
        self.assertNotIn(VALID_CARD, logged)
