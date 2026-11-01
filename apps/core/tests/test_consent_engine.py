"""Visitor consent engine (server half + contract of consent.js): no tag before a choice, validated ids only, GTM/GA4 never double-loaded, tracking stays platform-gated."""

import json
import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.core import consent
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection

JS = (Path(__file__).resolve().parents[1] / "static" / "core" / "consent.js").read_text(encoding="utf-8")
CSS = (Path(__file__).resolve().parents[1] / "static" / "core" / "consent.css").read_text(encoding="utf-8")
HOST_A, HOST_B = "cons-a.example.com", "cons-b.example.com"
TAG_MARKERS = ("googletagmanager.com", "fbevents.js", "gtag(", "fbq(", "ns.html", "connect.facebook.net")


def connect(store, code, **creds):
    conn = StoreIntegrationConnection.objects.create(store=store, provider_code=code, is_active=True)
    conn.set_credentials(creds)
    conn.save()


class ConfigTests(SimpleTestCase):
    def test_no_trackers_means_no_config_at_all(self):
        self.assertIsNone(consent.build_config({}))
        self.assertIsNone(consent.build_config({"ga4": "", "unknown": "x"}))

    def test_only_known_trackers_and_one_opt_in_policy(self):
        cfg = consent.build_config({"ga4": "G-ABC1234DEF", "meta_pixel": "1234567890123456", "evil": "<script>"})
        self.assertEqual(cfg["policy"], "opt_in")
        self.assertEqual(set(cfg["ids"]), {"ga4", "meta_pixel"})
        self.assertEqual([i["tracker"] for i in cfg["load"]], ["ga4", "meta_pixel"])

    def test_gtm_wins_over_direct_ga4_so_nothing_is_counted_twice(self):
        cfg = consent.build_config({"ga4": "G-ABC1234DEF", "gtm": "GTM-ABC1234"})
        self.assertEqual([i["tracker"] for i in cfg["load"]], ["gtm"])
        self.assertTrue(cfg["ga4_via_gtm"])

    def test_nothing_but_the_necessary_category_is_on_by_default(self):
        cfg = consent.build_config({"ga4": "G-ABC1234DEF"})
        self.assertEqual([c["key"] for c in cfg["categories"] if c["required"]], ["necessary"])
        self.assertEqual(set(cfg["signals"]["default_denied"]), {"ad_storage", "analytics_storage", "ad_user_data", "ad_personalization", "functionality_storage", "personalization_storage"})
        self.assertEqual(cfg["signals"]["default_granted"], ["security_storage"])


class ScriptContractTests(SimpleTestCase):
    """consent.js is browser code; its behaviour is exercised in Chromium (see the QA report) — these pin the invariants that must never regress."""

    def test_google_signals_are_denied_before_any_tag_is_defined(self):
        self.assertLess(JS.index("gtag('consent', 'default'"), JS.index("var LOAD ="))
        self.assertNotIn("ad_storage: 'granted'", JS)
        self.assertIn("wait_for_update", JS)

    def test_tags_are_loaded_only_from_applyChoice_after_a_matching_grant(self):
        for call in ("LOAD[item.tracker](", "script('https://www.googletagmanager.com", "script('https://connect.facebook.net"):
            self.assertIn(call, JS)
        body = JS[JS.index("function applyChoice"):JS.index("// ---- UI")]
        self.assertIn("LOAD[item.tracker](ids[item.tracker])", body)
        self.assertEqual(JS.count("LOAD[item.tracker]("), 1)                       # the ONLY call site
        self.assertIn("var ok = item.needs", body)

    def test_the_choice_is_a_first_party_versioned_cookie_and_reject_has_equal_weight(self):
        self.assertIn("SameSite=Lax", JS)
        self.assertIn("'; Secure'", JS)
        self.assertIn("c.v === cfg.version", JS)
        self.assertIn("rs-consent__btn", JS)
        self.assertRegex(JS, r"accept = el\('button', 'rs-consent__btn'")
        self.assertRegex(JS, r"reject = el\('button', 'rs-consent__btn'")           # same class: not a dark pattern
        self.assertNotIn("input.checked = true", JS.replace("input.checked = cat.required ? true : false", ""))

    def test_ids_are_revalidated_in_the_browser_and_tags_are_built_with_dom_apis(self):
        for pattern in ("G-[A-Z0-9]{6,10}", "GTM-[A-Z0-9]{4,8}", r"\d{10,20}"):
            self.assertIn(pattern, JS)
        self.assertNotIn("innerHTML", JS)
        self.assertNotIn("document.write", JS)
        self.assertNotIn("eval(", JS)

    def test_the_global_privacy_control_keeps_marketing_off_and_withdrawal_reloads(self):
        self.assertIn("navigator.globalPrivacyControl", JS)
        self.assertIn("location.reload()", JS)

    def test_the_banner_is_accessible_and_rtl(self):
        for token in ("role', 'dialog'", "aria-labelledby", "aria-expanded", "banner.focus("):
            self.assertIn(token, JS)
        self.assertIn("direction:rtl", CSS)
        self.assertIn(":focus-visible", CSS)
        self.assertRegex(CSS, r"min-height:44px")


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"], RASTISI_STOREFRONT_TRACKING_ENABLED=True)
class PageTests(TestCase):
    def setUp(self):
        self.a = Store.objects.get(slug="akhlaghi")
        self.b = Store.objects.create(name="Store B", slug="cons-store-b", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(self.b)
        for store, host in ((self.a, HOST_A), (self.b, HOST_B)):
            StoreDomain.objects.create(store=store, hostname=host, is_primary=True,
                                       verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())

    def home(self, host=HOST_A):
        return self.client.get("/", HTTP_HOST=host).content.decode()

    def config(self, html):
        match = re.search(r'<script id="rs-consent-config" type="application/json">(.*?)</script>', html, re.S)
        return json.loads(match.group(1)) if match else None

    def test_a_public_store_with_ids_prints_the_config_and_the_script_but_not_one_tag(self):
        connect(self.a, "google_analytics", measurement_id="G-ABC1234DEF")
        connect(self.a, "google_tag_manager", container_id="GTM-ABC1234")
        connect(self.a, "ad_pixel", pixel_id="1234567890123456")
        html = self.home()
        cfg = self.config(html)
        self.assertEqual(cfg["ids"], {"ga4": "G-ABC1234DEF", "gtm": "GTM-ABC1234", "meta_pixel": "1234567890123456"})
        self.assertIn("core/consent.js", html)
        for marker in TAG_MARKERS:
            self.assertNotIn(marker, html, marker)

    def test_off_by_default_localhost_unpublished_and_no_ids_render_nothing_at_all(self):
        connect(self.a, "google_analytics", measurement_id="G-ABC1234DEF")
        with override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=False):
            html = self.home()
            self.assertIsNone(self.config(html))
            self.assertNotIn("consent.js", html)
        self.assertIsNone(self.config(self.home(HOST_B)))                         # store B has no ids: no banner, no script
        self.assertNotIn("consent.js", self.home(HOST_B))
        self.a.status = Store.Status.PROVISIONING
        self.a.save(update_fields=["status"])
        self.assertNotIn("G-ABC1234DEF", self.home())

    def test_another_stores_ids_and_malformed_ids_never_reach_the_config(self):
        connect(self.b, "google_analytics", measurement_id="G-BBBB1234")
        connect(self.a, "ad_pixel", pixel_id="12345678901'+alert(1)")
        html = self.home()
        self.assertNotIn("G-BBBB1234", html)
        self.assertNotIn("alert(1)", html)
        self.assertIsNone(self.config(html))

    def test_the_platform_default_stays_off(self):
        source = (Path(__file__).resolve().parents[3] / "shop_core" / "settings.py").read_text(encoding="utf-8")
        self.assertIn('RASTISI_STOREFRONT_TRACKING_ENABLED = env_bool("RASTISI_STOREFRONT_TRACKING_ENABLED", default=False)', source)
