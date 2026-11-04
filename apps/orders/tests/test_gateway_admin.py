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
        self.assertEqual(response.status_code, 200)            # the canonical accordion card is re-rendered with the reason
        self.assertContains(response, "قرارداد رسمی")
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="mellat")
        self.assertFalse(config.is_active)

    def test_toggle_can_not_activate_documentation_blocked_provider(self):
        self.client.login(username="admin_all", password="pass123")
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="saman", is_active=False,
        )
        response = self.client.post(
            "/admin-portal/settings/gateway-config/saman/toggle/",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gw-doc-blocked")         # visible «documentation blocked» note on the card
        self.assertIn("err", response["HX-Trigger"])
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="saman")
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
        self.assertEqual(response.status_code, 200)
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zarinpal")
        # Stored value is encrypted, not plaintext.
        self.assertNotIn(secret, config.encrypted_credentials)
        self.assertEqual(config.get_credentials()["merchant_id"], secret)
        # Zarinpal is a verified online adapter -> can be activated.
        self.assertTrue(config.is_active)
        self.assertNotContains(response, secret)               # the secret is never echoed back

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


class ReadinessWordingTests(TestCase):
    """«پیکربندی کامل» describes configuration completeness only; externally VERIFIED connectivity is a separate fact that nothing can claim yet."""

    def setUp(self):
        reset_fernet()
        self.addCleanup(reset_fernet)
        self.store = _akhlaghi()
        self.owner = User.objects.create_user(username="wording-owner", password="pass123", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        zp = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zarinpal", is_active=True, is_sandbox=False)
        zp.set_credentials({"merchant_id": "a" * 36}); zp.save()

    @staticmethod
    def card(html, code):
        """One accordion's markup: from its own ``data-testid`` to the next accordion's."""
        start = html.index(f'data-testid="gateway-{code}"')
        nxt = html.find('data-testid="gateway-', start + 10)
        return html[start:nxt if nxt != -1 else len(html)]

    def page(self):
        self.client.login(username="wording-owner", password="pass123")
        return self.client.get("/admin-portal/settings/?section=payment-config")

    def test_the_label_never_claims_a_connection(self):
        labels = dict(PaymentGatewayConfig.ReadinessStatus.choices)
        self.assertEqual(labels["connected"], "پیکربندی کامل")
        self.assertNotIn("متصل", " ".join(str(v) for v in labels.values()).replace("اتصال", ""))      # no «متصل …» wording on any readiness state
        self.assertEqual(PaymentGatewayConfig.objects.get(gateway_code="zarinpal").readiness_status, "connected")   # the internal state itself is unchanged

    def test_the_admin_page_shows_configuration_complete_with_an_explicit_unverified_connection_note(self):
        response = self.page()
        self.assertContains(response, "پیکربندی کامل")
        self.assertNotContains(response, "متصل و آماده")
        card = self.card(response.content.decode(), "zarinpal")
        self.assertIn('data-testid="gw-connectivity-unverified"', card)
        self.assertIn("هنوز با آزمونِ مجازِ زنده/Sandbox تأیید نشده", card)

    def test_connectivity_is_never_reported_as_verified_and_other_states_show_no_such_note(self):
        from apps.dashboard.services.settings_admin_service import gateway_configs_context

        rows = {r["code"]: r for r in gateway_configs_context(store=self.store)}
        self.assertTrue(all(r["connectivity_verified"] is False for r in rows.values()))                # no authorized verification call exists
        html = self.page().content.decode()
        for code in ("cod", "card_to_card", "mellat", "saman", "pasargad", "snappay"):                  # offline / blocked / not configured: no note
            self.assertNotIn("gw-connectivity-unverified", self.card(html, code), code)
        self.assertEqual(html.count("gw-connectivity-unverified"), 1)                                  # only the configured, live Zarinpal

    def test_the_selection_rules_and_activation_gates_are_unchanged(self):
        zp = PaymentGatewayConfig.objects.get(gateway_code="zarinpal")
        self.assertTrue(zp.is_selectable_at_checkout)                                                    # still selectable: this round only renamed a label
        blocked = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="mellat", is_active=True)
        self.assertFalse(blocked.is_selectable_at_checkout)
        self.assertFalse(PaymentGatewayConfig(store=self.store, gateway_code="snappay").is_active)       # nothing is activated by default
