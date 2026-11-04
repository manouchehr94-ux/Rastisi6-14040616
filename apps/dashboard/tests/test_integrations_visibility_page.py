"""«یکپارچه‌سازی‌ها» page: honest status vocabulary + search-visibility readiness (no fake «connected», no guarantees)."""

from django.urls import reverse

from apps.dashboard.tests.integration_pages import all_views_html, view_html

from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import StoreIntegrationConnection


class IntegrationsVisibilityPageTests(PermissionEnforcementTestCase):
    def page(self):
        self._login(self.owner)
        return all_views_html(self.client)

    def connect(self, code, **creds):
        conn = StoreIntegrationConnection.objects.create(store=self.store, provider_code=code, is_active=True)
        conn.set_credentials(creds)
        conn.save()

    def test_readiness_card_and_groups_are_present(self):
        html = self.page()
        for marker in ('data-testid="presence-summary"', 'data-testid="presence-item-published"', 'data-testid="presence-item-address"',
                       'data-testid="presence-item-infra"', 'data-testid="presence-item-next"', 'data-testid="presence-address"',
                       'data-testid="presence-automatic"', 'data-testid="presence-search-console"', 'data-testid="presence-bing-ai"',
                       'data-testid="integration-accordions-stored"', 'data-testid="visibility-not-available"'):
            self.assertIn(marker, html)

    def test_stored_only_providers_never_say_connected_and_active(self):
        self.connect("torob", merchant_id="123")
        self.connect("enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP")
        html = self.page()
        self.assertNotIn("متصل و فعال", html)
        self.assertIn('data-effect="stored"', html)
        self.assertIn("فقط شناسه ذخیره شده", html)

    def test_analytics_on_a_test_address_says_it_waits_for_publish_not_that_it_is_live(self):
        self.connect("google_analytics", measurement_id="G-ABC1234DEF")
        from django.test import override_settings

        html = self.page()
        self.assertIn('data-effect="privacy"', html)                       # the platform has not enabled tracking: saved, not running
        self.assertNotIn('data-effect="live"', html)
        with override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=True):
            html = self.page()
        self.assertIn('data-effect="waiting"', html)                       # tracking allowed, but the store is not live on a public address
        self.assertNotIn('data-effect="live"', html)

    def test_unavailable_services_are_listed_apart_and_without_connect_forms(self):
        html = self.page()
        section = html[html.index('data-testid="visibility-not-available"'):]
        for name in ("Bing Webmaster Tools", "Merchant Center"):
            self.assertIn(name, section)
        self.assertNotIn("Search Console", section)                         # one place only (section A), never two contradictory ones
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
        return all_views_html(self.client)

    def connect(self, code, store=None, **creds):
        conn = StoreIntegrationConnection.objects.create(store=store or self.store, provider_code=code, is_active=True)
        conn.set_credentials(creds)
        conn.save()

    def test_no_template_comment_leaks_into_the_page(self):
        html = self.page()
        self.assertNotIn("{#", html)
        self.assertNotIn("#}", html)
        self.assertNotIn("{%", html)

    def view(self, name):
        self._login(self.owner)
        return view_html(self.client, name)

    def test_summary_and_the_six_horizontal_categories_exist_in_order(self):
        overview = self.view("overview")
        for marker in ('data-testid="integration-summary"', 'data-testid="integration-next-action"', 'data-testid="overview-attention"', 'data-testid="admin-subtabs"'):
            self.assertIn(marker, overview)
        keys = ("integrations-overview", "integrations-seo", "integrations-analytics", "integrations-torob", "integrations-enamad", "integrations-future")
        positions = [overview.index(f'data-subtab="{key}"') for key in keys]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('data-subtab="integrations-overview"', overview.split('data-subtab="integrations-seo"')[0])
        self.assertRegex(overview, r'class="admin-subtab active" data-subtab="integrations-overview"')
        self.assertRegex(self.view("analytics"), r'class="admin-subtab active" data-subtab="integrations-analytics"')
        for name, marker in (("seo", "seo-group-status"), ("analytics", "analytics-group"), ("torob", "torob-group"), ("enamad", "enamad-group"), ("future", "int-section-future")):
            self.assertIn(f'data-testid="{marker}"', self.view(name))

    def test_each_category_renders_only_its_own_content_and_an_unknown_view_falls_back_to_overview(self):
        self.assertNotIn('data-testid="analytics-group"', self.view("torob"))
        self.assertNotIn('data-testid="torob-readiness"', self.view("analytics"))
        self.assertIn('data-testid="integration-summary"', self.view("no-such-tab"))

    def test_seo_groups_follow_the_mandatory_order(self):
        html = self.view("seo")
        order = [html.index(f'data-testid="seo-group-{n}"') for n in ("status", "customer", "automatic", "external")]
        self.assertEqual(order, sorted(order))
        self.assertLess(html.index('data-testid="presence-next"') if 'data-testid="presence-item-next"' not in html else html.index('data-testid="presence-item-next"'), html.index('data-testid="seo-group-customer"'))

    def test_one_main_card_is_open_and_the_technical_detail_is_closed_by_default(self):
        html = self.view("seo")
        def tag(testid):
            i = html.index(f'data-testid="{testid}"')
            return html[html.rindex("<details", 0, i):html.index(">", i)]
        self.assertIn(" open", tag("presence-address"))
        for closed in ("presence-automatic", "presence-search-console", "presence-bing-ai"):
            self.assertNotIn(" open", tag(closed), closed)

    def test_a_nothing_to_do_message_or_a_concrete_next_action_is_always_shown(self):
        text = self.page().split('data-testid="integration-next-action"')[1][:260]
        self.assertTrue("فعلاً نیازی به انجام کاری از طرف شما نیست" in text or "قدم بعدی" in text)

    def test_nothing_is_presented_as_connected_without_a_saved_identifier(self):
        html = self.page()
        self.assertNotIn("متصل و فعال", html)
        overview = self.view("overview")
        self.assertEqual(overview.count('data-status="needs_customer"'), 10)          # 5 cards, status on the card and on its chip
        self.assertNotIn('data-live="1"', overview)
        for code in ("google_analytics", "google_tag_manager", "ad_pixel", "torob", "enamad"):
            card = overview.split(f'data-testid="integration-{code}"')[1].split("</article>")[0]
            self.assertIn('data-testid="int-axis-saved" data-on="0"', card)
            self.assertIn('data-testid="int-axis-live" data-on="0"', card)

    def test_saved_identifiers_are_shown_as_stored_not_connected_and_tracking_stays_off_by_default(self):
        self.connect("torob", merchant_id="123")
        self.connect("enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP")
        self.connect("google_analytics", measurement_id="G-ABC1234DEF")
        torob = self.view("torob")
        card = torob.split('data-testid="integration-torob"')[1].split("</article>")[0]
        self.assertIn('data-testid="int-axis-saved" data-on="1"', card)
        self.assertIn('data-testid="int-axis-enabled" data-on="1"', card)
        self.assertIn('data-testid="int-axis-live" data-on="0"', card)              # nothing is ever sent to Torob
        analytics = self.view("analytics")
        ga4 = analytics.split('data-testid="integration-google_analytics"')[1].split("</article>")[0]
        self.assertIn('data-testid="int-axis-saved" data-on="1"', ga4)
        self.assertIn('data-testid="int-axis-live" data-on="0"', ga4)               # platform tracking is off by default → saved ≠ live
        self.assertIn("منتظر فعال‌سازی ردیابی توسط مدیر پلتفرم", ga4)
        self.assertNotIn('data-effect="live"', self.page())

    def test_future_services_have_no_forms_and_never_look_connectable(self):
        section = self.view("future").split('data-testid="int-section-future"')[1].split("</section>")[0]
        self.assertNotIn("<form", section)
        for name in ("Bing Webmaster Tools", "Merchant Center"):
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
            torob = view_html(self.client, "torob", HTTP_HOST=host)
        self.assertNotIn("OTHERSTORE777", html)
        card = torob.split('data-testid="integration-torob"')[1].split("</article>")[0]
        self.assertIn('data-testid="int-axis-saved" data-on="0"', card)

    def test_no_guarantee_or_ranking_promise_anywhere(self):
        html = self.page()
        for phrase in ("تضمین می‌شود", "رتبه ۱", "ثبت قطعی", "حتماً ایندکس"):
            self.assertNotIn(phrase, html)
        self.assertIn("تضمین نمی‌کند", html)
