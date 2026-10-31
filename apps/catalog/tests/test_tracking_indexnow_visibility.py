"""Search-visibility add-ons: analytics snippets only on real public pages of the owning store, the IndexNow key file / payload /
submission (fake transport — nothing ever leaves the test process), and the honest readiness facts of the integrations page."""

from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.core import indexnow
from apps.core.models import ShopSettings
from apps.dashboard.services import search_visibility_service as svc
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection
from apps.stores.services import tracking_service

HOST_A = "trk-a.example.com"
HOST_B = "trk-b.example.com"


def connect(store, code, **creds):
    conn = StoreIntegrationConnection.objects.create(store=store, provider_code=code, is_active=True)
    conn.set_credentials(creds)
    conn.save()
    return conn


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class TrackingAndIndexNowTests(TestCase):
    def setUp(self):
        self.a = Store.objects.get(slug="akhlaghi")
        self.b = Store.objects.create(name="Store B", slug="trk-store-b", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(self.b)
        for store, host in ((self.a, HOST_A), (self.b, HOST_B)):
            StoreDomain.objects.create(store=store, hostname=host, is_primary=True,
                                       verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())

    def home(self, host=HOST_A):
        return self.client.get("/", HTTP_HOST=host).content.decode()

    # ── analytics injection ─────────────────────────────────────────────────────────────────────────────
    def test_nothing_is_injected_without_a_connection(self):
        html = self.home()
        for marker in ("googletagmanager.com", "fbevents.js"):
            self.assertNotIn(marker, html)

    def test_active_connections_inject_only_their_own_validated_ids_on_a_public_page(self):
        connect(self.a, "google_analytics", measurement_id="G-ABC1234DEF")
        connect(self.a, "google_tag_manager", container_id="GTM-ABC1234")
        connect(self.a, "ad_pixel", pixel_id="1234567890123456")
        html = self.home()
        self.assertIn("G-ABC1234DEF", html)
        self.assertIn("GTM-ABC1234", html)
        self.assertIn("1234567890123456", html)
        self.assertIn("ns.html?id=GTM-ABC1234", html)

    def test_another_stores_ids_never_appear(self):
        connect(self.b, "google_analytics", measurement_id="G-BBBB1234")
        self.assertNotIn("G-BBBB1234", self.home(HOST_A))
        self.assertIn("G-BBBB1234", self.home(HOST_B))

    def test_inactive_connection_injects_nothing(self):
        conn = connect(self.a, "google_analytics", measurement_id="G-ABC1234DEF")
        conn.is_active = False
        conn.save()
        self.assertNotIn("G-ABC1234DEF", self.home())

    def test_malformed_stored_ids_render_nothing_instead_of_markup(self):
        for code, key, bad in (("google_analytics", "measurement_id", "G-1');alert(1);//"),
                               ("google_tag_manager", "container_id", "GTM-</script>"),
                               ("ad_pixel", "pixel_id", "12345678901'+alert(1)")):
            connect(self.a, code, **{key: bad})
        html = self.home()
        self.assertNotIn("alert(1)", html)
        self.assertNotIn("googletagmanager.com/gtag", html)
        self.assertEqual(tracking_service.active_tracking_ids(self.a), {})

    def test_a_store_that_is_not_published_loads_no_tracking(self):
        connect(self.a, "google_analytics", measurement_id="G-ABC1234DEF")
        self.a.status = Store.Status.PROVISIONING
        self.a.save(update_fields=["status"])
        self.assertNotIn("G-ABC1234DEF", self.home())

    @override_settings(ALLOWED_HOSTS=["*"], STORES_DEVELOPMENT_HOST_ALLOWLIST=["shop.localhost"])
    def test_a_local_test_host_never_loads_tracking(self):
        connect(self.a, "google_analytics", measurement_id="G-ABC1234DEF")
        html = self.client.get("/", HTTP_HOST="shop.localhost").content.decode()
        self.assertNotIn("G-ABC1234DEF", html)

    # ── IndexNow ────────────────────────────────────────────────────────────────────────────────────────
    def test_key_is_stable_per_store_and_differs_between_stores(self):
        self.assertEqual(indexnow.key_for_store(self.a), indexnow.key_for_store(self.a))
        self.assertNotEqual(indexnow.key_for_store(self.a), indexnow.key_for_store(self.b))
        self.assertRegex(indexnow.key_for_store(self.a), r"^[0-9a-f]{32}$")

    def test_key_file_is_served_only_for_its_own_store_on_its_own_host(self):
        key_a = indexnow.key_for_store(self.a)
        ok = self.client.get(f"/{key_a}.txt", HTTP_HOST=HOST_A)
        self.assertEqual((ok.status_code, ok.content.decode()), (200, key_a))
        self.assertEqual(self.client.get(f"/{key_a}.txt", HTTP_HOST=HOST_B).status_code, 404)   # another store's host
        self.assertEqual(self.client.get(f"/{'0' * 32}.txt", HTTP_HOST=HOST_A).status_code, 404)  # a guessed key

    def test_key_file_is_not_served_while_the_store_is_not_public(self):
        key_a = indexnow.key_for_store(self.a)
        self.a.status = Store.Status.PROVISIONING
        self.a.save(update_fields=["status"])
        self.assertEqual(self.client.get(f"/{key_a}.txt", HTTP_HOST=HOST_A).status_code, 404)

    def test_payload_keeps_only_urls_of_the_stores_own_host(self):
        origin = f"https://{HOST_A}"
        payload = indexnow.build_payload(self.a, origin, [
            f"{origin}/", f"{origin}/p/1/", f"{origin}/p/1/",            # duplicate
            f"https://{HOST_B}/x/", "javascript:alert(1)", "ftp://a/b", f"https://evil.{HOST_A}/"])
        self.assertEqual(payload["urlList"], [f"{origin}/", f"{origin}/p/1/"])
        self.assertEqual(payload["host"], HOST_A)
        self.assertEqual(payload["keyLocation"], f"{origin}/{indexnow.key_for_store(self.a)}.txt")

    @override_settings(RASTISI_INDEXNOW_ENABLED=False)
    def test_nothing_is_sent_while_the_platform_switch_is_off(self):
        transport = mock.Mock(return_value=200)
        res = indexnow.submit(self.a, f"https://{HOST_A}", [f"https://{HOST_A}/"], indexable=True, transport=transport)
        self.assertEqual(res.status, "disabled")
        transport.assert_not_called()

    @override_settings(RASTISI_INDEXNOW_ENABLED=True)
    def test_nothing_is_sent_for_a_store_that_is_not_indexable(self):
        transport = mock.Mock(return_value=200)
        res = indexnow.submit(self.a, f"https://{HOST_A}", [f"https://{HOST_A}/"], indexable=False, transport=transport)
        self.assertEqual(res.status, "not_public")
        transport.assert_not_called()

    @override_settings(RASTISI_INDEXNOW_ENABLED=True)
    def test_accepted_submission_and_bounded_retry_with_backoff(self):
        origin = f"https://{HOST_A}"
        ok = mock.Mock(return_value=202)
        self.assertTrue(indexnow.submit(self.a, origin, [f"{origin}/"], indexable=True, transport=ok).sent)
        sleeps = []
        flaky = mock.Mock(side_effect=[429, 503, 200])
        res = indexnow.submit(self.a, origin, [f"{origin}/"], indexable=True, transport=flaky, sleep=sleeps.append)
        self.assertTrue(res.sent)
        self.assertEqual(sleeps, [1, 2])
        always_down = mock.Mock(return_value=500)
        res = indexnow.submit(self.a, origin, [f"{origin}/"], indexable=True, transport=always_down, sleep=lambda s: None)
        self.assertEqual((res.sent, res.status), (False, "failed"))
        self.assertEqual(always_down.call_count, 3)

    @override_settings(RASTISI_INDEXNOW_ENABLED=True)
    def test_final_errors_are_not_retried_and_transport_exceptions_never_escape(self):
        origin = f"https://{HOST_A}"
        forbidden = mock.Mock(return_value=403)
        res = indexnow.submit(self.a, origin, [f"{origin}/"], indexable=True, transport=forbidden, sleep=lambda s: None)
        self.assertEqual((res.status, forbidden.call_count), ("failed", 1))
        boom = mock.Mock(side_effect=OSError("network down"))
        res = indexnow.submit(self.a, origin, [f"{origin}/"], indexable=True, transport=boom, sleep=lambda s: None)
        self.assertEqual(res.status, "failed")

    def test_command_defaults_to_a_dry_run_that_sends_nothing(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch("apps.core.indexnow._post") as post:
            call_command("indexnow_submit", store="akhlaghi", stdout=out)
        post.assert_not_called()
        self.assertIn("dry-run", out.getvalue())

    # ── honest page facts ───────────────────────────────────────────────────────────────────────────────
    def test_readiness_never_calls_a_stored_only_provider_active(self):
        self.assertEqual(svc.provider_effect("torob", connected=True, store_live=True)["state"], "stored")
        self.assertEqual(svc.provider_effect("enamad", connected=True, store_live=True)["state"], "stored")
        self.assertEqual(svc.provider_effect("google_analytics", connected=True, store_live=False)["state"], "waiting")
        self.assertEqual(svc.provider_effect("google_analytics", connected=True, store_live=True)["state"], "live")
        self.assertEqual(svc.provider_effect("google_analytics", connected=False, store_live=True)["state"], "off")


class WordingTests(SimpleTestCase):
    def test_no_guarantee_wording_in_the_visibility_texts(self):
        banned = ("تضمین می‌شود", "حتماً", "رتبه ۱", "رتبه‌ی ۱", "قطعاً")
        texts = [n["note"] for n in svc.NOT_AVAILABLE]
        for text in texts:
            for word in banned:
                self.assertNotIn(word, text)

    def test_not_available_services_are_not_connectable_providers(self):
        from apps.stores.integrations.registry import PROVIDERS
        self.assertFalse({n["key"] for n in svc.NOT_AVAILABLE} & set(PROVIDERS))
