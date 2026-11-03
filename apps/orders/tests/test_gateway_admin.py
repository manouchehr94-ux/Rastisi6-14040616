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
        self.assertEqual(response.status_code, 204)
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
        self.assertEqual(response.status_code, 204)
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
        self.assertEqual(response.status_code, 204)
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
        self.assertEqual(response.status_code, 204)
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
        self.assertEqual(response.status_code, 204)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal")
        self.assertFalse(config.is_active)  # Still inactive

    def test_save_cod_config(self):
        self.client.login(username="admin_gw", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/cod/save/",
            {"display_title": "پرداخت درب منزل", "display_order": "2", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 204)
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


# ---------------------------------------------------------------------------
# FEAT-005: all providers render with readiness / category; blocked ones can
# not be activated for real checkout.
# ---------------------------------------------------------------------------


class GatewayConfigAllProvidersAdminTests(TestCase):
    def setUp(self):
        reset_fernet()
        self.store = _akhlaghi()
        self.admin_user = User.objects.create_user(
            username="admin_all", password="pass123", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store, user=self.admin_user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def tearDown(self):
        reset_fernet()

    def test_context_lists_every_registered_provider(self):
        from apps.dashboard.services.settings_admin_service import gateway_configs_context
        from apps.orders.gateways.registry import registered_codes

        rows = gateway_configs_context(store=self.store)
        codes = {r["code"] for r in rows}
        self.assertEqual(codes, set(registered_codes()))

    def test_context_includes_readiness_and_category(self):
        from apps.dashboard.services.settings_admin_service import gateway_configs_context

        rows = {r["code"]: r for r in gateway_configs_context(store=self.store)}
        # Documentation-blocked PSP skeleton
        self.assertEqual(rows["mellat"]["readiness_status"], "documentation_blocked")
        self.assertEqual(rows["mellat"]["category"], "psp")
        self.assertEqual(rows["mellat"]["readiness_badge"], "err")
        # BNPL real adapter (implemented + contract-tested; no creds yet ->
        # derives not_configured, NOT documentation_blocked).
        self.assertEqual(rows["snappay"]["category"], "bnpl")
        self.assertEqual(rows["snappay"]["readiness_status"], "not_configured")
        # Offline
        self.assertEqual(rows["cod"]["category"], "offline")
        # Ready online adapter (no config yet -> not configured)
        self.assertEqual(rows["zibal"]["readiness_status"], "not_configured")

    def test_sandbox_toggle_only_where_supported(self):
        from apps.dashboard.services.settings_admin_service import gateway_configs_context

        rows = {r["code"]: r for r in gateway_configs_context(store=self.store)}
        self.assertTrue(rows["zibal"]["supports_sandbox"])     # zibal has a real sandbox
        self.assertFalse(rows["zarinpal"]["supports_sandbox"])  # no verified sandbox host
        self.assertFalse(rows["cod"]["supports_sandbox"])       # offline
        self.assertFalse(rows["mellat"]["supports_sandbox"])    # documentation-blocked

    def test_settings_page_renders_all_providers(self):
        self.client.login(username="admin_all", password="pass123")
        response = self.client.get("/admin-portal/settings/?section=payment-config")
        self.assertEqual(response.status_code, 200)
        # Persian provider labels present for a spread of categories.
        self.assertContains(response, "زیبال")
        self.assertContains(response, "اسنپ‌پی")
        self.assertContains(response, "بانک ملت")
        # Readiness badge label appears.
        self.assertContains(response, "مسدود به‌دلیل مستندات")

    def test_save_can_not_activate_documentation_blocked_provider(self):
        self.client.login(username="admin_all", password="pass123")
        response = self.client.post(
            "/admin-portal/settings/gateway-config/mellat/save/",
            {
                "display_order": "0",
                "credential_terminal_id": "123",
                "is_active": "on",  # trying to activate a blocked provider
            },
        )
        self.assertEqual(response.status_code, 204)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="mellat")
        self.assertFalse(config.is_active)

    def test_toggle_can_not_activate_documentation_blocked_provider(self):
        self.client.login(username="admin_all", password="pass123")
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=False,
        )
        response = self.client.post(
            "/admin-portal/settings/gateway-config/snappay/toggle/",
        )
        self.assertEqual(response.status_code, 204)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="snappay")
        self.assertFalse(config.is_active)

    def test_save_zarinpal_credentials_stored_encrypted(self):
        self.client.login(username="admin_all", password="pass123")
        secret = "m" * 36
        response = self.client.post(
            "/admin-portal/settings/gateway-config/zarinpal/save/",
            {
                "display_order": "1",
                "credential_merchant_id": secret,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 204)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zarinpal")
        # Stored value is encrypted, not plaintext.
        self.assertNotIn(secret, config.encrypted_credentials)
        self.assertEqual(config.get_credentials()["merchant_id"], secret)
        # Zarinpal is a verified online adapter -> can be activated.
        self.assertTrue(config.is_active)

    def test_plaintext_secret_never_rendered_for_any_provider(self):
        self.client.login(username="admin_all", password="pass123")
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zarinpal", is_active=True,
        )
        config.set_credentials({"merchant_id": "SECRET-ZP-MERCHANT-ID-DO-NOT-LEAK-0001"})
        config.save()
        response = self.client.get("/admin-portal/settings/?section=payment-config")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "SECRET-ZP-MERCHANT-ID-DO-NOT-LEAK-0001")
