"""Legacy ``/payments/zibal/`` (PR #43 and earlier): now ONLY a permission-safe redirect to the canonical
``/payments/gateways/`` console. The canonical behaviours the old page used to cover — DB-editable encrypted merchant,
masked echo, blank-preserves, sandbox toggle — are asserted here against the unified console so nothing is lost."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import PlatformConfiguration, PlatformGatewayConfig
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import get_platform_configuration

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"
GATEWAYS = "/payments/gateways/"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class LegacyZibalRedirectTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.superuser = User.objects.create_user(
            username="pa-zibal-super@example.com", email="pa-zibal-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary = User.objects.create_user(
            username="pa-zibal-ordinary@example.com", email="pa-zibal-ordinary@example.com", password="a-very-strong-pass-1",
        )

    def _save_via_console(self, **extra):
        data = {"action": "save", "gateway_code": "zibal", "is_enabled": "on", **extra}
        return self.client.post(GATEWAYS, data, HTTP_HOST=_HOST)

    # ---- the old URL
    def test_ordinary_user_is_sent_to_login_not_to_the_gateway_console(self):
        self.client.force_login(self.ordinary)
        response = self.client.get("/payments/zibal/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("payments/gateways", response["Location"])

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get("/payments/zibal/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("payments/gateways", response["Location"])

    def test_staff_get_redirects_to_the_zibal_card_of_the_unified_console(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/payments/zibal/", HTTP_HOST=_HOST)
        self.assertEqual((response.status_code, response["Location"]), (302, GATEWAYS + "#gw-zibal"))

    def test_staff_post_redirects_and_writes_nothing(self):
        self.client.force_login(self.superuser)
        response = self.client.post("/payments/zibal/", {
            "default_payment_provider": "zibal", "zibal_merchant": "legacy-should-be-ignored", "zibal_sandbox_mode": "on",
        }, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PlatformGatewayConfig.objects.exists())
        config = get_platform_configuration()
        self.assertEqual((config.encrypted_zibal_credentials, config.default_payment_provider), ("", "manual"))

    def test_the_old_page_is_not_in_the_sidebar_and_the_console_is(self):
        self.client.force_login(self.superuser)
        html = self.client.get(GATEWAYS, HTTP_HOST=_HOST).content.decode()
        self.assertNotIn("/payments/zibal/", html)
        self.assertIn(GATEWAYS, html)

    # ---- canonical behaviours preserved on the unified console
    def test_superuser_can_save_enable_and_use_sandbox(self):
        self.client.force_login(self.superuser)
        response = self._save_via_console(cred_merchant="platform-merchant-999", sandbox_mode="on")
        self.assertEqual(response.status_code, 302)
        creds, sandbox, source = pgs.credentials_and_mode("zibal")
        self.assertEqual((creds["merchant"], sandbox, source), ("platform-merchant-999", True, "row"))

    def test_merchant_credential_encrypted_at_rest_and_single_copy(self):
        self.client.force_login(self.superuser)
        self._save_via_console(cred_merchant="super-secret-merchant-abc")
        row = PlatformGatewayConfig.objects.get(gateway_code="zibal")
        self.assertNotIn("super-secret-merchant-abc", row.encrypted_credentials)
        self.assertEqual(get_platform_configuration().encrypted_zibal_credentials, "")        # no second credential store

    def test_merchant_never_echoed_back_in_plaintext(self):
        self.client.force_login(self.superuser)
        self._save_via_console(cred_merchant="super-secret-merchant-abc")
        response = self.client.get(GATEWAYS, HTTP_HOST=_HOST)
        self.assertNotContains(response, "super-secret-merchant-abc")

    def test_blank_merchant_preserves_existing_value(self):
        self.client.force_login(self.superuser)
        self._save_via_console(cred_merchant="original-merchant-id")
        self._save_via_console(cred_merchant="")
        self.assertEqual(pgs.credentials_and_mode("zibal")[0]["merchant"], "original-merchant-id")

    def test_disabling_on_the_console_never_resets_a_different_default(self):
        self.client.force_login(self.superuser)
        self._save_via_console(cred_merchant="m-1")
        self.assertEqual(pgs.default_code(), "zibal")
        self.client.post(GATEWAYS, {"action": "save", "gateway_code": "zibal", "cred_merchant": ""}, HTTP_HOST=_HOST)    # untick enabled
        cache.clear()
        self.assertNotEqual(pgs.default_code(), "zibal")


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class LegacyZibalDataMigrationTests(TestCase):
    """Migration 0019 on realistic legacy data (written through the model methods the old page used)."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _run(self):
        import importlib

        from django.apps import apps as django_apps

        module = importlib.import_module("apps.portal.migrations.0019_zibal_legacy_to_gateway_config")
        module.consolidate(django_apps, None)
        cache.clear()

    def test_legacy_enabled_zibal_becomes_a_ready_row_with_the_same_merchant_and_nothing_is_deleted(self):
        config = get_platform_configuration()
        config.default_payment_provider = "zibal"
        config.zibal_sandbox_mode = True
        config.set_zibal_credentials(merchant="LEGACY-MERCHANT-1")
        config.save()
        before_cipher = PlatformConfiguration.objects.get(pk=1).encrypted_zibal_credentials
        self._run()
        row = PlatformGatewayConfig.objects.get(gateway_code="zibal")
        self.assertEqual((row.is_enabled, row.sandbox_mode, row.get_credentials()["merchant"]), (True, True, "LEGACY-MERCHANT-1"))
        self.assertEqual(PlatformConfiguration.objects.get(pk=1).encrypted_zibal_credentials, before_cipher)     # untouched rollback copy
        self.assertEqual(pgs.gateway_state("zibal").source, "row")
        self.assertTrue(pgs.gateway_state("zibal").ready)

    def test_idempotent_and_existing_row_always_wins(self):
        config = get_platform_configuration()
        config.default_payment_provider = "zibal"
        config.set_zibal_credentials(merchant="LEGACY-OLD")
        config.save()
        pgs.save_gateway("zibal", credentials={"merchant": "ROW-NEW"}, sandbox=False, enabled=True)
        self._run()
        self._run()
        self.assertEqual(PlatformGatewayConfig.objects.filter(gateway_code="zibal").count(), 1)
        self.assertEqual(pgs.credentials_and_mode("zibal")[0]["merchant"], "ROW-NEW")

    def test_no_legacy_data_creates_nothing(self):
        self._run()
        self.assertFalse(PlatformGatewayConfig.objects.exists())

    def test_manual_default_with_credentials_is_kept_but_not_enabled(self):
        config = get_platform_configuration()
        config.set_zibal_credentials(merchant="LEGACY-MERCHANT-2")
        config.save()
        self._run()
        row = PlatformGatewayConfig.objects.get(gateway_code="zibal")
        self.assertEqual((row.is_enabled, row.get_credentials()["merchant"]), (False, "LEGACY-MERCHANT-2"))
