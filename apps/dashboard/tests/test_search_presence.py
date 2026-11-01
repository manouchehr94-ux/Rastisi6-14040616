"""Integrations page, section A and the identifier services: every state comes from real backend facts, nothing is faked, nothing leaves the process.

Covers: localhost / unpublished / public stores, pending and verified domains, the per-capability SEO states and counters, the single next action,
the manual Search Console guide, the Torob link, saving GA4/GTM/Meta identifiers without switching tracking on, eNamad flow honesty and meta safety,
tenant isolation, and «no real request to any external service»."""

import socket
from unittest import mock
from urllib.parse import urlsplit

from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.services import search_presence_service as sps, search_visibility_service as svs
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.integrations import registry
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection
from apps.stores.services import enamad_verification_service as enamad, tracking_service

PUBLIC_URL = "https://shop.brand-example.ir/"
LOCAL_URL = "http://shop.rastisi.localhost:8000/"


def _presence(store, *, published, url, domain=None):
    request = RequestFactory().get("/")
    with mock.patch.object(sps, "is_publicly_visible", return_value=published), \
            mock.patch.object(sps, "resolve_storefront_url_for_store", return_value=url):
        return sps.presence(store, request, domain)


def _caps(presence):
    return {c["key"]: c["state"] for c in presence["capabilities"]}


class PresenceStateTests(PermissionEnforcementTestCase):
    def test_localhost_store_is_a_test_environment_with_the_exact_message(self):
        p = _presence(self.store, published=True, url=LOCAL_URL, domain={"storefront_is_local": True, "custom_domains": []})
        self.assertEqual(p["address"]["state"], sps.ADDRESS_TEST_ENV)
        self.assertEqual(p["test_env_message"], "این فروشگاه در محیط آزمایشی است. پس از فعال‌شدن آدرس عمومی واقعی، امکانات معرفی فروشگاه به موتورهای جست‌وجو قابل استفاده خواهند بود.")
        self.assertFalse(p["indexable"])
        caps = _caps(p)
        for key in ("robots", "sitemap", "canonical", "jsonld", "indexability"):
            self.assertEqual(caps[key], sps.WAITING_ADDRESS, key)          # built, waiting — not «active», not «0 jobs»
        self.assertGreater(p["counters"]["waiting"], 0)
        self.assertEqual(p["next_action"]["key"], "domain")
        self.assertIn("settings", p["next_action"]["href"])
        self.assertEqual(p["search_console"]["sitemap_url"], "")           # no sitemap address is offered before there is a public one

    def test_unpublished_store_waits_for_publish_not_for_an_address(self):
        p = _presence(self.store, published=False, url=PUBLIC_URL, domain={"storefront_is_local": False, "custom_domains": []})
        self.assertFalse(p["indexable"])
        self.assertEqual(_caps(p)["sitemap"], sps.WAITING_PUBLISH)
        self.assertEqual(p["next_action"]["key"], "publish")
        self.assertFalse(p["summary_items"][0]["ok"])

    def test_public_published_store_has_everything_active_and_no_next_action_needed(self):
        with mock.patch.object(sps, "storefront_listing_products") as products:
            products.return_value.count.return_value = 3
            p = _presence(self.store, published=True, url=PUBLIC_URL, domain={"storefront_is_local": False, "custom_domains": []})
        self.assertTrue(p["indexable"])
        caps = _caps(p)
        for key in ("robots", "sitemap", "canonical", "jsonld", "indexability"):
            self.assertEqual(caps[key], sps.ACTIVE, key)
        self.assertEqual(p["address"]["state"], sps.ADDRESS_PUBLIC_READY)
        self.assertIsNone(p["next_action"])
        self.assertEqual(p["search_console"]["sitemap_url"], "https://shop.brand-example.ir/sitemap.xml")
        self.assertEqual(p["counters"]["waiting"], 0)

    def test_published_without_products_asks_for_a_product_only_after_the_address_is_fine(self):
        with mock.patch.object(sps, "storefront_listing_products") as products:
            products.return_value.count.return_value = 0
            p = _presence(self.store, published=True, url=PUBLIC_URL, domain={"storefront_is_local": False, "custom_domains": []})
        self.assertEqual(p["next_action"]["key"], "products")

    def test_pending_verified_and_failing_domains_are_told_apart(self):
        pending = {"storefront_is_local": False, "custom_domains": [{"phase": "awaiting_ownership", "is_primary": False}]}
        active = {"storefront_is_local": False, "custom_domains": [{"phase": "active", "is_primary": True}]}
        broken = {"storefront_is_local": False, "custom_domains": [{"phase": "error", "is_primary": False}]}
        self.assertEqual(_presence(self.store, published=True, url="", domain=pending)["address"]["state"], sps.ADDRESS_DOMAIN_PENDING)
        self.assertEqual(_presence(self.store, published=True, url=PUBLIC_URL, domain=active)["address"]["state"], sps.ADDRESS_DOMAIN_ACTIVE)
        self.assertEqual(_presence(self.store, published=True, url="", domain=broken)["address"]["state"], sps.ADDRESS_ERROR)
        # a pending domain does NOT make search tools look ready while the shop is still on a test address
        self.assertFalse(_presence(self.store, published=True, url=LOCAL_URL, domain=pending)["indexable"])

    def test_a_failure_to_resolve_the_address_is_an_error_not_a_silent_ok(self):
        request = RequestFactory().get("/")
        with mock.patch.object(sps, "is_publicly_visible", return_value=True), \
                mock.patch.object(sps, "resolve_storefront_url_for_store", side_effect=RuntimeError("boom")):
            p = sps.presence(self.store, request, {"storefront_is_local": False, "custom_domains": []})
        self.assertEqual(p["address"]["state"], sps.ADDRESS_ERROR)
        self.assertEqual(_caps(p)["robots"], sps.ERROR)
        self.assertEqual(p["next_action"]["key"], "domain")

    def test_indexnow_has_its_own_honest_state(self):
        public = {"storefront_is_local": False, "custom_domains": []}
        self.assertEqual(_caps(_presence(self.store, published=True, url=PUBLIC_URL, domain=public))["indexnow"], sps.PLATFORM_DISABLED)
        with override_settings(RASTISI_INDEXNOW_ENABLED=True):
            self.assertEqual(_caps(_presence(self.store, published=True, url=LOCAL_URL, domain=public))["indexnow"], sps.WAITING_ADDRESS)
            self.assertEqual(_caps(_presence(self.store, published=True, url=PUBLIC_URL, domain=public))["indexnow"], sps.UNAVAILABLE)   # no verified custom domain
            StoreDomain.objects.create(store=self.store, hostname="shop.brand-example.ir", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                       verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
            self.assertEqual(_caps(_presence(self.store, published=True, url=PUBLIC_URL, domain=public))["indexnow"], sps.READY)

    def test_every_state_has_a_plain_label_from_the_agreed_vocabulary(self):
        self.assertEqual(set(sps.STATE_LABELS), {sps.READY, sps.ACTIVE, sps.WAITING_ADDRESS, sps.WAITING_PUBLISH, sps.PLATFORM_DISABLED, sps.ERROR, sps.UNAVAILABLE})
        for label in ("آماده", "فعال", "منتظر آدرس عمومی", "غیرفعال توسط پلتفرم", "خطا", "در دسترس نیست"):
            self.assertIn(label, sps.STATE_LABELS.values())

    def test_search_and_training_crawlers_are_listed_apart_and_nothing_is_promised(self):
        p = _presence(self.store, published=True, url=PUBLIC_URL, domain={"storefront_is_local": False, "custom_domains": []})
        self.assertFalse(set(p["crawlers"]["search"]) & set(p["crawlers"]["training"]))
        self.assertIn("GPTBot", p["crawlers"]["training"])
        self.assertTrue(p["search_console"]["links"])
        self.assertFalse(p["search_console"]["auto_connect_available"])


class IntegrationsPageTests(PermissionEnforcementTestCase):
    def page(self):
        self._login(self.owner)
        return self.client.get(reverse("dashboard:settings") + "?section=integrations").content.decode()

    def post(self, name, code, **data):
        self._login(self.owner)
        return self.client.post(reverse(f"dashboard:settings-integration-{name}", args=[code]), data, follow=True)

    def test_the_rendered_page_shows_the_agreed_pieces_on_a_test_address(self):
        html = self.page()
        for marker in ("presence-summary", "presence-address", "presence-automatic", "presence-search-console", "presence-bing-ai", "presence-cap-robots",
                       "presence-cap-sitemap", "presence-cap-canonical", "presence-cap-jsonld", "presence-cap-indexability", "presence-cap-indexnow"):
            self.assertIn(f'data-testid="{marker}"', html, marker)
        self.assertIn("اتصال خودکار هنوز در دسترس نیست", html)
        self.assertNotIn("۰ کار خودکار", html)
        self.assertNotIn("0 کار خودکار", html)
        self.assertNotIn('data-testid="presence-sitemap"', html)              # no sitemap to copy before a public address exists
        # one Search Console place only
        self.assertEqual(html.count('data-testid="presence-search-console"'), 1)
        self.assertNotIn("Google Search Console</strong>", html)

    def test_exactly_one_primary_action_in_the_summary(self):
        html = self.page()
        box = html.split('data-testid="presence-summary"')[1].split("</section>")[0]
        self.assertEqual(box.count("au-btn--primary"), 1)

    def test_search_console_guide_with_a_copyable_sitemap_once_the_address_is_public(self):
        with mock.patch.object(sps, "is_publicly_visible", return_value=True), \
                mock.patch.object(sps, "resolve_storefront_url_for_store", return_value=PUBLIC_URL):
            html = self.page()
        self.assertIn('data-testid="presence-sitemap-url"', html)
        self.assertIn("https://shop.brand-example.ir/sitemap.xml", html)
        self.assertIn('data-copy="https://shop.brand-example.ir/sitemap.xml"', html)
        self.assertIn("الزامی نیست", html)
        self.assertIn(sps.SEARCH_CONSOLE_URL, html)

    # ---- links --------------------------------------------------------------------------------------------------------------
    def test_the_torob_link_is_the_seller_signup_page_and_no_guide_link_is_broken_by_shape(self):
        self.assertEqual(registry.get_provider("torob").setup_guide, "https://torob.com/sell/")
        html = self.page()
        self.assertIn('href="https://torob.com/sell/"', html)
        self.assertNotIn("torob.com/seller", html)
        allowed = {"enamad.ir", "torob.com", "analytics.google.com", "tagmanager.google.com", "business.facebook.com"}
        for provider in registry.all_providers():
            parts = urlsplit(provider.setup_guide)
            self.assertEqual(parts.scheme, "https", provider.code)
            self.assertIn(parts.netloc.removeprefix("www."), allowed, provider.code)
        for url in sps.GUIDE_LINKS.values():
            self.assertTrue(url.startswith("https://") and urlsplit(url).netloc.endswith("google.com"), url)

    def test_enamad_homepage_link_is_unchanged(self):
        self.assertIn(registry.get_provider("enamad").setup_guide.rstrip("/"), ("https://enamad.ir",))

    # ---- GA4 / GTM / Meta -----------------------------------------------------------------------------------------------------
    def test_saving_an_identifier_says_saved_not_connected_and_tracking_stays_off(self):
        for code, field, value in (("google_analytics", "measurement_id", "G-ABC1234DEF"), ("google_tag_manager", "container_id", "GTM-ABC1234"),
                                   ("ad_pixel", "pixel_id", "1234567890123456")):
            response = self.post("connect", code, **{field: value})
            text = " ".join(str(m) for m in response.context["messages"])
            self.assertIn("ذخیره شد", text)
            self.assertNotIn("متصل شد", text)
            self.assertNotIn("فعال شد", text)
        self.assertEqual(tracking_service.active_tracking_ids(self.store), {})          # the platform switch is OFF: saving never turns tracking on
        html = self.page()
        self.assertNotIn("ذخیره و اتصال", html)
        self.assertGreaterEqual(html.count('data-testid="int-save"'), 5)
        self.assertNotIn('data-effect="live"', html)
        self.assertIn("ردیابی روی فروشگاه روشن نیست", html)
        self.assertIn("ذخیره‌کردن شناسه، ردیابی را روشن نمی‌کند", html)

    def test_saved_valid_and_live_are_different_facts(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        html = self.page()
        panel = html.split('data-testid="integration-google_analytics"')[1].split('data-testid="integration-google_tag_manager"')[0]
        self.assertIn('data-testid="int-fact-saved" data-on="1"', panel)
        self.assertIn('data-testid="int-fact-validation" data-state="valid"', panel)
        self.assertIn('data-testid="int-fact-enabled" data-on="1"', panel)
        self.assertNotIn('data-effect="live"', panel)
        self.assertNotIn("هنوز بررسی انجام نشده", html)
        with override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=True), \
                mock.patch.object(svs, "store_live", return_value=True):
            live = self.page()
        self.assertIn('data-effect="live"', live)
        self.assertIn("ردیابی فعال است", live)

    def test_backend_still_rejects_malformed_identifiers(self):
        for code, field, bad in (("google_analytics", "measurement_id", "UA-1234"), ("google_tag_manager", "container_id", "GTM-<script>"),
                                 ("ad_pixel", "pixel_id", "12ab")):
            self.post("connect", code, **{field: bad})
            self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store, provider_code=code).exists(), code)

    def test_both_ga4_and_gtm_active_shows_the_duplicate_guidance_only_then(self):
        self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
        self.assertNotIn('data-testid="duplicate-tracking-warning"', self.page())
        self.post("connect", "google_tag_manager", container_id="GTM-ABC1234")
        self.assertIn('data-testid="duplicate-tracking-warning"', self.page())

    # ---- eNamad ----------------------------------------------------------------------------------------------------------------
    def test_enamad_shows_two_stages_and_never_says_verified(self):
        html = self.page()
        self.assertIn("مرحلهٔ ۱ — احراز دسترسی فنی", html)
        self.assertIn("مرحلهٔ ۲ — نمادِ صادرشده", html)
        self.assertIn("هرگز به معنی «اینماد تأییدشده» نیست", html)
        self.post("connect", "enamad", enamad_id="221617", enamad_auth_code="94MqMPJEnuahlSHjb9kP")
        html = self.page()
        self.assertNotIn("اینماد تأییدشده</", html)
        self.assertIn("دامنهٔ اختصاصیِ تأییدشده", html)                      # saved, but there is no verified custom domain → says where it can appear

    def test_enamad_flow_states_follow_stored_data_and_the_verified_domain(self):
        flow = enamad.enamad_flow(self.store, {}, connected=False)
        self.assertEqual([s["state"] for s in flow["stages"]], ["empty", "empty"])
        creds = {"verification_meta_tag": '<meta name="enamad" content="abc123">', "enamad_id": "221617", "enamad_auth_code": "94MqMPJEnuahlSHjb9kP"}
        flow = enamad.enamad_flow(self.store, creds, connected=True)
        self.assertEqual([s["state"] for s in flow["stages"]], ["waiting_domain", "waiting_domain"])
        StoreDomain.objects.create(store=self.store, hostname="shop.brand-example.ir", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self.assertEqual([s["state"] for s in enamad.enamad_flow(self.store, creds, connected=True)["stages"]], ["ready", "ready"])
        bad = enamad.enamad_flow(self.store, {"verification_meta_tag": '<script>alert(1)</script>', "enamad_id": "x", "enamad_auth_code": "y"}, connected=True)
        self.assertEqual([s["state"] for s in bad["stages"]], ["invalid", "invalid"])

    def test_enamad_rejects_arbitrary_html_and_javascript_on_save(self):
        for payload in ('<script>alert(1)</script>', '<meta name="a" content="b"><script>x</script>', '<img src=x onerror=alert(1)>',
                        '<meta http-equiv="refresh" content="0;url=https://evil.example">'):
            self.post("connect", "enamad", verification_meta_tag=payload)
            self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store, provider_code="enamad").exists(), payload)

    # ---- tenant isolation + no external traffic -----------------------------------------------------------------------------------
    def test_another_stores_identifiers_never_reach_this_stores_page_or_state(self):
        other = Store.objects.create(name="Other", slug="pres-other", status=Store.Status.ACTIVE)
        conn = StoreIntegrationConnection.objects.create(store=other, provider_code="google_analytics", is_active=True)
        conn.set_credentials({"measurement_id": "G-OTHER1234"})
        conn.save()
        html = self.page()
        self.assertNotIn("G-OTHER1234", html)
        self.assertFalse(StoreIntegrationConnection.objects.filter(store=self.store).exists())
        self.post("connect", "google_analytics", measurement_id="G-MINE12345")
        self.assertEqual(StoreIntegrationConnection.objects.get(store=other, provider_code="google_analytics").get_credentials()["measurement_id"], "G-OTHER1234")

    def test_nothing_in_the_page_or_the_services_opens_a_network_connection(self):
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("external connection attempted")), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("external request attempted")):
            self.page()
            self.post("connect", "google_analytics", measurement_id="G-ABC1234DEF")
            self.post("test", "google_analytics")
            self.post("connect", "torob", merchant_id="123")
            self.post("toggle", "torob")
            _presence(self.store, published=True, url=PUBLIC_URL, domain={"storefront_is_local": False, "custom_domains": []})

    def test_the_page_makes_no_guarantee_about_indexing_or_ai_answers(self):
        html = self.page()
        for phrase in ("تضمین می‌شود", "رتبه ۱", "حتماً ایندکس", "حتماً در ChatGPT"):
            self.assertNotIn(phrase, html)
        self.assertIn("تضمین نمی‌کند", html)
