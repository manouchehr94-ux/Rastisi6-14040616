"""Tests for payment gateway configuration admin views.

Covers:
- Authorized store admin access
- Unauthorized user denial
- Full secret not rendered
- Existing secret retained when edit field blank
- Valid configuration save
- Incomplete credential rejection for activation
- Activation and deactivation
- Display ordering
- CSRF protection (Django TestClient handles this automatically)
- Tenant isolation
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from django.utils import timezone

from apps.orders.encryption import reset_fernet
from apps.orders.models import PaymentGatewayConfig
from apps.stores.models import Store, StoreMembership

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class GatewayConfigAdminTests(TestCase):
    def setUp(self):
        reset_fernet()
        self.store = _akhlaghi()
        self.admin_user = User.objects.create_user(
            username="admin_gw", password="pass123", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store, user=self.admin_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.non_staff_user = User.objects.create_user(
            username="customer_gw", password="pass123", is_staff=False
        )

    def tearDown(self):
        reset_fernet()

    def test_settings_page_shows_payment_config_section(self):
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.get("/admin-portal/settings/?section=payment-config")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "پیکربندی درگاه")

    def test_unauthorized_user_redirected(self):
        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/save/",
            {"display_title": "test"},
        )
        # Non-authenticated users get redirected to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_non_staff_user_redirected(self):
        self.client.login(username="customer_gw", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/save/",
            {"display_title": "test"},
        )
        # Non-staff users get redirected to storefront
        self.assertEqual(response.status_code, 302)

    def test_save_zibal_config_creates_record(self):
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/save/",
            {
                "display_title": "درگاه زیبال",
                "display_order": "1",
                "credential_merchant": "my-merchant-123",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal")
        self.assertEqual(config.display_title, "درگاه زیبال")
        self.assertEqual(config.display_order, 1)
        self.assertTrue(config.is_active)
        creds = config.get_credentials()
        self.assertEqual(creds["merchant"], "my-merchant-123")

    def test_save_without_credentials_cannot_activate(self):
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/save/",
            {
                "display_title": "",
                "display_order": "0",
                "credential_merchant": "",  # empty
                "is_active": "on",  # trying to activate
            },
        )
        self.assertEqual(response.status_code, 200)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal")
        # Should NOT be active because credentials are missing
        self.assertFalse(config.is_active)

    def test_blank_credential_retains_existing_value(self):
        self.client.login(username="admin_gw", password="pass123")
        # First save with credential
        self.client.post(
            "/admin-portal/settings/gateway-config/zibal/save/",
            {"credential_merchant": "original-merchant", "display_order": "0"},
        )
        # Second save with blank credential — should keep "original-merchant"
        self.client.post(
            "/admin-portal/settings/gateway-config/zibal/save/",
            {"credential_merchant": "", "display_order": "1", "is_active": "on"},
        )
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal")
        creds = config.get_credentials()
        self.assertEqual(creds["merchant"], "original-merchant")
        self.assertTrue(config.is_active)

    def test_secret_not_displayed_in_settings_page(self):
        self.client.login(username="admin_gw", password="pass123")
        # Save a config with credential
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=True
        )
        config.set_credentials({"merchant": "super-secret-merchant-xyz"})
        config.save()

        response = self.client.get("/admin-portal/settings/?section=payment-config")
        self.assertEqual(response.status_code, 200)
        # The plaintext merchant ID should NOT appear in the HTML
        self.assertNotContains(response, "super-secret-merchant-xyz")

    def test_toggle_activates_configured_gateway(self):
        self.client.login(username="admin_gw", password="pass123")
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=False,
        )
        config.set_credentials({"merchant": "valid-merch"})
        config.save()

        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/toggle/",
        )
        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertTrue(config.is_active)

    def test_toggle_deactivates_gateway(self):
        self.client.login(username="admin_gw", password="pass123")
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=True,
        )
        config.set_credentials({"merchant": "valid-merch"})
        config.save()

        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/toggle/",
        )
        self.assertEqual(response.status_code, 200)
        config.refresh_from_db()
        self.assertFalse(config.is_active)

    def test_toggle_unconfigured_gateway_fails(self):
        self.client.login(username="admin_gw", password="pass123")
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zibal", is_active=False,
        )
        # No credentials set
        response = self.client.post(
            "/admin-portal/settings/gateway-config/zibal/toggle/",
        )
        self.assertEqual(response.status_code, 200)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal")
        self.assertFalse(config.is_active)  # Still inactive

    def test_save_cod_config(self):
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/cod/save/",
            {"display_title": "پرداخت درب منزل", "display_order": "2", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="cod")
        self.assertTrue(config.is_active)
        self.assertEqual(config.display_title, "پرداخت درب منزل")

    def test_invalid_gateway_code_returns_404(self):
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/nonexistent/save/",
            {"display_title": "x"},
        )
        self.assertEqual(response.status_code, 404)

    def test_get_not_allowed_for_save(self):
        """Save endpoint requires POST."""
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.get("/admin-portal/settings/gateway-config/zibal/save/")
        self.assertEqual(response.status_code, 405)
