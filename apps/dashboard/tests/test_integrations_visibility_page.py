"""«یکپارچه‌سازی‌ها» page: honest status vocabulary + search-visibility readiness (no fake «connected», no guarantees)."""

from django.urls import reverse

from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import StoreIntegrationConnection


class IntegrationsVisibilityPageTests(PermissionEnforcementTestCase):
    def page(self):
        self._login(self.owner)
        return self.client.get(reverse("dashboard:settings") + "?section=integrations").content.decode()

    def connect(self, code, **creds):
        conn = StoreIntegrationConnection.objects.create(store=self.store, provider_code=code, is_active=True)
        conn.set_credentials(creds)
        conn.save()

    def test_readiness_card_and_groups_are_present(self):
        html = self.page()
        for marker in ('data-testid="seo-readiness"', 'data-testid="seo-row-published"', 'data-testid="seo-row-public_host"',
                       'data-testid="seo-row-robots_sitemap"', 'data-testid="seo-row-ai_search"', 'data-testid="seo-row-search_console"',
                       'data-testid="integration-accordions-stored"', 'data-testid="visibility-not-available"'):
            self.assertIn(marker, html)

    def test_stored_only_providers_never_say_connected_and_active(self):
        self.connect("torob", merchant_id="123")
        self.connect("enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP")
        html = self.page()
        self.assertNotIn("متصل و فعال", html)
        self.assertIn('data-effect="stored"', html)
        self.assertIn("فقط ذخیره شده", html)

    def test_analytics_on_a_test_address_says_it_waits_for_publish_not_that_it_is_live(self):
        self.connect("google_analytics", measurement_id="G-ABC1234DEF")
        html = self.page()
        self.assertIn('data-effect="waiting"', html)
        self.assertNotIn('data-effect="live"', html)

    def test_unavailable_services_are_listed_apart_and_without_connect_forms(self):
        html = self.page()
        section = html[html.index('data-testid="visibility-not-available"'):]
        for name in ("Google Search Console", "Bing Webmaster Tools", "Merchant Center"):
            self.assertIn(name, section)
        self.assertNotIn("<form", section.split("</ul>")[0])

    def test_no_guarantee_wording_on_the_page(self):
        html = self.page()
        for phrase in ("تضمین می‌شود", "رتبه ۱ خودکار", "ثبت قطعی"):
            self.assertNotIn(phrase, html)
        self.assertIn("تضمین نمی‌کند", html)

    def test_a_field_flagged_secret_never_renders_its_stored_value(self):
        """No provider has a secret field today (every identifier is public by nature: GA/GTM/pixel ids and the eNamad badge ids appear in
        public HTML anyway). The guard is for the day one is added: a ``is_secret`` field must never echo its value back."""
        from unittest import mock
        from apps.stores.integrations import registry

        provider = registry.PROVIDERS["torob"]
        secret = registry.IntegrationField(key="merchant_id", label="شناسه", is_secret=True)
        patched = {**registry.PROVIDERS, "torob": registry.IntegrationProvider(
            code=provider.code, display_name=provider.display_name, category=provider.category, description=provider.description,
            setup_guide=provider.setup_guide, fields=(secret,), validate=provider.validate)}
        self.connect("torob", merchant_id="TOPSECRETVALUE99")
        with mock.patch.dict(registry.PROVIDERS, patched, clear=True):
            self.assertNotIn("TOPSECRETVALUE99", self.page())
