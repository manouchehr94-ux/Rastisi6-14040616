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


class IntegrationsFiveGroupStructureTests(PermissionEnforcementTestCase):
    """The page for an ordinary seller: one status + one next action, five plain groups (A–E), technical detail folded, no fake «connected»."""

    def page(self, user=None):
        self._login(user or self.owner)
        return self.client.get(reverse("dashboard:settings") + "?section=integrations").content.decode()

    def connect(self, code, store=None, **creds):
        conn = StoreIntegrationConnection.objects.create(store=store or self.store, provider_code=code, is_active=True)
        conn.set_credentials(creds)
        conn.save()

    def test_summary_group_chips_and_the_five_groups_exist_in_order(self):
        html = self.page()
        for marker in ('data-testid="integration-summary"', 'data-testid="integration-next-action"', 'data-testid="int-section-visibility"',
                       'data-testid="int-section-stats"', 'data-testid="int-section-sales"', 'data-testid="int-section-trust"',
                       'data-testid="int-section-future"', 'data-testid="int-chip-visibility"', 'data-testid="int-chip-stats"'):
            self.assertIn(marker, html)
        positions = [html.index(f'data-testid="int-section-{name}"') for name in ("visibility", "stats", "sales", "trust", "future")]
        self.assertEqual(positions, sorted(positions))

    def test_technical_seo_detail_is_folded_and_the_seller_facing_rows_stay_visible(self):
        html = self.page()
        folded = html.split('data-testid="seo-technical"')[1].split("</details>")[0]
        for key in ("robots_sitemap", "structured_data", "ai_search"):
            self.assertIn(f'data-testid="seo-row-{key}"', folded)
        tag = html[html.index('data-testid="seo-technical"') - 40:html.index('data-testid="seo-technical"') + 40]
        self.assertNotIn(" open", tag)                                           # the technical fold is closed by default
        for key in ("published", "public_host"):
            self.assertNotIn(f'data-testid="seo-row-{key}"', folded)           # these are the seller-facing rows, outside the fold
            self.assertIn(f'data-testid="seo-row-{key}"', html)

    def test_a_nothing_to_do_message_or_a_concrete_next_action_is_always_shown(self):
        text = self.page().split('data-testid="integration-next-action"')[1][:260]
        self.assertTrue("فعلاً نیازی به انجام کاری از طرف شما نیست" in text or "قدم بعدی" in text)

    def test_nothing_is_presented_as_connected_without_a_saved_identifier(self):
        html = self.page()
        self.assertIn('data-testid="int-chip-stats"', html)
        self.assertRegex(html, r'data-testid="int-chip-stats">متصل‌نشده<')
        self.assertRegex(html, r'data-testid="int-chip-sales">متصل‌نشده<')
        self.assertRegex(html, r'data-testid="int-chip-trust">متصل‌نشده<')
        self.assertNotIn("متصل و فعال", html)

    def test_saved_identifiers_are_chipped_as_stored_not_connected_and_tracking_stays_off_by_default(self):
        self.connect("torob", merchant_id="123")
        self.connect("enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP")
        self.connect("google_analytics", measurement_id="G-ABC1234DEF")
        html = self.page()
        self.assertRegex(html, r'data-testid="int-chip-sales">فقط شناسه ذخیره شده<')
        self.assertRegex(html, r'data-testid="int-chip-trust">فقط شناسه ذخیره شده<')
        stats = html.split('data-testid="int-chip-stats">')[1].split("<")[0]
        self.assertIn("ذخیره شد", stats)                                         # saved, NOT «active»: loading is off until the platform enables it
        self.assertNotIn('data-effect="live"', html)

    def test_future_services_have_no_forms_and_never_look_connectable(self):
        html = self.page()
        section = html.split('data-testid="int-section-future"')[1]
        self.assertNotIn("<form", section.split("</details>")[0])
        for name in ("Google Search Console", "Bing Webmaster Tools", "Merchant Center"):
            self.assertIn(name, section)

    def test_another_stores_connections_never_appear(self):
        from django.conf import settings
        from django.test import Client, override_settings
        from django.utils import timezone

        from apps.stores.models import Store, StoreDomain

        host = f"int-iso.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        other = Store.objects.create(name="Other store", slug="int-other", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(store=self.store, hostname=host, is_primary=True, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self.store.admin_subdomain = host.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.connect("torob", store=other, merchant_id="OTHERSTORE777")
        with override_settings(ALLOWED_HOSTS=[host, "testserver"]):
            self.client = Client(HTTP_HOST=host)
            html = self.page()
        self.assertNotIn("OTHERSTORE777", html)
        self.assertRegex(html, r'data-testid="int-chip-sales">متصل‌نشده<')

    def test_no_guarantee_or_ranking_promise_anywhere(self):
        html = self.page()
        for phrase in ("تضمین می‌شود", "رتبه ۱", "ثبت قطعی", "حتماً ایندکس"):
            self.assertNotIn(phrase, html)
        self.assertIn("تضمین نمی‌کند", html)
