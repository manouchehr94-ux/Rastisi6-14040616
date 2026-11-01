"""Google Search Console layer: off by default, OAuth state bound to ONE store, tokens encrypted and store-scoped, sitemap submission through a fake transport,
revoked access handled, no Indexing API, no claim of indexing. Nothing here touches the network."""

from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.core import signing
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core import automation
from apps.stores.integrations import search_console as gsc
from apps.stores.models import Store, StoreIntegrationConnection

ORIGIN = "https://shop.brand-example.ir"
ON = dict(RASTISI_GSC_OAUTH_ENABLED=True, RASTISI_GOOGLE_OAUTH_CLIENT_ID="cid", RASTISI_GOOGLE_OAUTH_CLIENT_SECRET="csecret")


class Fake:
    """Programmable Google: ``routes`` maps (method, url-part) -> list of (status, body) answers (the last one repeats)."""
    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        for (m, part), answers in self.routes.items():
            if m == method and (url.endswith(part[:-1]) if part.endswith('$') else part in url):
                return answers.pop(0) if len(answers) > 1 else answers[0]
        return 404, {}


SITES = (200, {"siteEntry": [{"siteUrl": ORIGIN + "/", "permissionLevel": "siteOwner"}]})


def happy(extra=None):
    routes = {("GET", "/sites$"): [SITES], ("PUT", "/sitemaps/"): [(204, {})], ("GET", "/sitemaps/"): [(200, {"errors": 0, "warnings": 1, "isPending": True})]}
    routes.update(extra or {})
    return Fake(routes)


class SearchConsoleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.create(name="A", slug="gsc-a", status=Store.Status.ACTIVE)
        self.other = Store.objects.create(name="B", slug="gsc-b", status=Store.Status.ACTIVE)
        p = mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def connect(self, store=None, **creds):
        gsc._save(store or self.store, {"refresh_token": "RT-secret-1", "access_token": "AT-secret-1", **creds}, active=True)

    def sync(self, transport, **kw):
        return gsc.sync_sitemap(kw.pop("store", self.store), kw.pop("origin", ORIGIN), transport=transport, sleep=lambda s: None, **kw)

    # ---- off by default ---------------------------------------------------------------------------------------------------------
    def test_everything_is_off_by_default_and_nothing_is_called(self):
        self.assertEqual(gsc.status(self.store)["state"], "disabled")
        self.assertIn("اتصال خودکار هنوز در دسترس نیست", gsc.status(self.store)["text"])
        with self.assertRaises(gsc.GscError):
            gsc.authorization_url(self.store, "https://x/cb")
        fake = happy()
        self.assertEqual(self.sync(fake).status, automation.DISABLED)
        self.assertEqual(fake.calls, [])

    @override_settings(RASTISI_GSC_OAUTH_ENABLED=True)
    def test_enabled_but_without_an_approved_oauth_client_is_not_configured(self):
        self.assertEqual(gsc.status(self.store)["state"], "not_configured")
        with self.assertRaises(gsc.GscError):
            gsc.authorization_url(self.store, "https://x/cb")

    # ---- OAuth --------------------------------------------------------------------------------------------------------------------
    @override_settings(**ON)
    def test_the_authorization_url_asks_for_the_webmasters_scope_offline_and_binds_the_store(self):
        url = gsc.authorization_url(self.store, "https://panel.example.ir/cb")
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(urlsplit(url).netloc, "accounts.google.com")
        self.assertEqual(query["scope"], [gsc.SCOPE])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(signing.loads(query["state"][0], salt=gsc.STATE_SALT)["store"], str(self.store.public_id))
        self.assertNotIn("csecret", url)

    @override_settings(**ON)
    def test_a_callback_can_only_attach_tokens_to_the_store_that_started_the_flow(self):
        state = parse_qs(urlsplit(gsc.authorization_url(self.store, "https://p/cb")).query)["state"][0]
        fake = Fake({("POST", "oauth2.googleapis.com"): [(200, {"refresh_token": "RT-new", "access_token": "AT-new"})]})
        with self.assertRaises(gsc.GscError):                               # another store's session presents this state
            gsc.complete_authorization(self.other, code="c", state=state, redirect_uri="https://p/cb", transport=fake)
        self.assertEqual(fake.calls, [])
        self.assertFalse(StoreIntegrationConnection.objects.filter(provider_code=gsc.PROVIDER_CODE).exists())
        with self.assertRaises(gsc.GscError):
            gsc.complete_authorization(self.store, code="c", state="tampered", redirect_uri="https://p/cb", transport=fake)
        with mock.patch.object(gsc, "STATE_MAX_AGE", -1), self.assertRaises(gsc.GscError):         # expired
            gsc.complete_authorization(self.store, code="c", state=state, redirect_uri="https://p/cb", transport=fake)
        result = gsc.complete_authorization(self.store, code="c", state=state, redirect_uri="https://p/cb", transport=fake)
        self.assertEqual(result["state"], "connected")
        conn = StoreIntegrationConnection.objects.get(provider_code=gsc.PROVIDER_CODE)
        self.assertEqual(conn.store, self.store)
        self.assertNotIn("RT-new", str(conn.encrypted_credentials))        # encrypted at rest
        self.assertEqual(conn.get_credentials()["refresh_token"], "RT-new")
        self.assertEqual(gsc.status(self.other)["state"], "not_connected")

    # ---- sitemap submission ---------------------------------------------------------------------------------------------------------
    @override_settings(**ON)
    def test_it_submits_this_stores_sitemap_for_the_matching_property_and_reports_what_google_says(self):
        self.connect()
        fake = happy()
        result = self.sync(fake)
        self.assertEqual(result.status, automation.DONE)
        methods = [(c[0], c[1].split("/webmasters/v3")[1].split("%2F")[0][:30]) for c in fake.calls]
        self.assertEqual([m for m, _ in methods], ["GET", "PUT", "GET"])
        put = fake.calls[1]
        self.assertIn(f"sitemaps/{ORIGIN.replace(':', '%3A').replace('/', '%2F')}%2Fsitemap.xml", put[1])
        self.assertEqual(put[2]["Authorization"], "Bearer AT-secret-1")
        self.assertEqual((result.metrics["errors"], result.metrics["warnings"], result.metrics["pending"]), (0, 1, True))
        self.assertIn("indexing is not guaranteed", result.metrics["note"])
        info = automation.last_result(self.store, gsc.OPERATION)
        self.assertNotIn("AT-secret-1", str(info))
        self.assertNotIn("RT-secret-1", str(info))

    def test_property_resolution_only_uses_verified_owner_or_full_user_properties(self):
        sites = [{"siteUrl": ORIGIN + "/", "permissionLevel": "siteUnverifiedUser"}, {"siteUrl": "https://other.example/", "permissionLevel": "siteOwner"},
                 {"siteUrl": "sc-domain:brand-example.ir", "permissionLevel": "siteFullUser"}, {"siteUrl": "sc-domain:evil-brand-example.ir", "permissionLevel": "siteOwner"}]
        self.assertEqual(gsc.resolve_property(sites, ORIGIN), "sc-domain:brand-example.ir")
        self.assertEqual(gsc.resolve_property(sites[:2], ORIGIN), None)
        self.assertEqual(gsc.resolve_property([{"siteUrl": ORIGIN + "/", "permissionLevel": "siteOwner"}] + sites, ORIGIN), ORIGIN + "/")

    @override_settings(**ON)
    def test_a_missing_or_unverified_property_is_explained_and_nothing_is_submitted(self):
        self.connect()
        for sites, code in (([], "no_property"), ([{"siteUrl": ORIGIN + "/", "permissionLevel": "siteUnverifiedUser"}], "not_owner")):
            cache.clear()
            fake = happy({("GET", "/sites$"): [(200, {"siteEntry": sites})]})
            result = self.sync(fake)
            self.assertEqual((result.status, result.detail), (automation.FAILED, code))
            self.assertFalse([c for c in fake.calls if c[0] == "PUT"])
        self.assertEqual(gsc.status(self.store)["text"], gsc.MESSAGES["not_owner"])

    @override_settings(**ON)
    def test_an_expired_access_token_is_refreshed_once_and_the_call_repeated(self):
        self.connect()
        fake = happy({("GET", "/sites$"): [(401, {}), SITES], ("POST", "oauth2.googleapis.com"): [(200, {"access_token": "AT-fresh"})]})
        self.assertEqual(self.sync(fake).status, automation.DONE)
        self.assertEqual(StoreIntegrationConnection.objects.get(store=self.store, provider_code=gsc.PROVIDER_CODE).get_credentials()["access_token"], "AT-fresh")

    @override_settings(**ON)
    def test_a_revoked_grant_turns_into_access_lost_and_stops_calling_google(self):
        self.connect()
        fake = happy({("GET", "/sites$"): [(401, {})], ("POST", "oauth2.googleapis.com"): [(400, {"error": "invalid_grant"})]})
        result = self.sync(fake)
        self.assertEqual((result.status, result.detail), (automation.FAILED, "access_lost"))
        self.assertEqual(gsc.status(self.store)["state"], "access_lost")
        again = happy()
        self.assertEqual(self.sync(again).detail, "not_connected")
        self.assertEqual(again.calls, [])

    @override_settings(**ON)
    def test_google_rate_limits_and_outages_are_retried_but_a_refusal_is_not(self):
        self.connect()
        flaky = happy({("GET", "/sites$"): [(503, {}), (429, {}), SITES]})
        self.assertEqual(self.sync(flaky).status, automation.DONE)
        cache.clear()
        denied = happy({("PUT", "/sitemaps/"): [(403, {})]})
        result = self.sync(denied)
        self.assertEqual((result.status, result.detail), (automation.FAILED, "not_owner"))
        self.assertEqual(len([c for c in denied.calls if c[0] == "PUT"]), 1)

    @override_settings(**ON)
    def test_dry_run_only_reads_and_localhost_or_another_store_never_calls_google(self):
        self.connect()
        fake = happy()
        dry = self.sync(fake, dry_run=True)
        self.assertEqual(dry.status, automation.DRY_RUN)
        self.assertEqual([c[0] for c in fake.calls], ["GET"])
        self.assertFalse(automation.last_result(self.store, gsc.OPERATION))
        local = happy()
        self.assertEqual(self.sync(local, origin="http://shop.rastisi.localhost:8000").reason, "test_host")
        self.assertEqual(local.calls, [])
        other = happy()
        self.assertEqual(self.sync(other, store=self.other).detail, "not_connected")        # store B can never use store A's tokens
        self.assertEqual(other.calls, [])

    def test_the_indexing_api_is_never_used_and_the_connection_has_no_seller_form(self):
        from pathlib import Path

        source = Path(gsc.__file__).read_text(encoding="utf-8")
        self.assertNotIn("indexing.googleapis.com", source)
        self.assertNotIn("urlNotifications", source)
        from apps.stores.integrations.registry import get_provider

        self.assertIsNone(get_provider(gsc.PROVIDER_CODE))                  # tokens can never be typed in through the integrations form

    @override_settings(**ON)
    def test_disconnect_wipes_the_tokens(self):
        self.connect()
        gsc.disconnect(self.store)
        conn = StoreIntegrationConnection.objects.get(store=self.store, provider_code=gsc.PROVIDER_CODE)
        self.assertEqual(conn.get_credentials(), {})
        self.assertFalse(conn.is_active)
        self.assertEqual(gsc.status(self.store)["state"], "not_connected")
