"""End-to-end custom-domain flow through the seller panel with FAKE DNS and FAKE HTTPS (no real network, ever).

Every network-facing primitive of ``domain_verification_service`` (TXT lookup, A/CNAME lookup, TLS probe) is replaced; ``dns.resolver.resolve``
and ``socket.create_connection`` additionally raise, so a code path that forgot to use the fakes fails the test instead of querying the
internet."""

from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.cache import caches
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import Store, StoreDomain
from apps.stores.services import domain_verification_service as dvs

HOST = f"dom-flow.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
PAGE = "/admin-portal/settings/?section=domain"
V = StoreDomain.VerificationStatus

TARGETS = {"RASTISI_CUSTOM_DOMAIN_A_TARGETS": ("203.0.113.10",), "RASTISI_CUSTOM_DOMAIN_CNAME_TARGET": ""}


class FakeInfra:
    """Switchable fake internet for one test."""

    def __init__(self):
        self.txt_visible = False
        self.routing_connected = False
        self.tls_ready = False
        self.calls = {"txt": 0, "routing": 0, "tls": 0}

    def txt(self, hostname, expected_value):
        self.calls["txt"] += 1
        return self.txt_visible

    def routing(self, hostname):
        self.calls["routing"] += 1
        configured = bool(settings.RASTISI_CUSTOM_DOMAIN_A_TARGETS or settings.RASTISI_CUSTOM_DOMAIN_CNAME_TARGET)
        return dvs.DnsRoutingCheck(configured=configured, connected=configured and self.routing_connected,
                                   expected_a_targets=tuple(settings.RASTISI_CUSTOM_DOMAIN_A_TARGETS), observed_a_targets=(),
                                   expected_cname="", observed_cname="", error="")

    def tls(self, hostname):
        self.calls["tls"] += 1
        return dvs.SslConnectionCheck(reachable=self.tls_ready, certificate_expires_at=None, error="" if self.tls_ready else "fake: not ready")


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"], **TARGETS)
class DomainFlowWithFakeInfraTests(PermissionEnforcementTestCase):
    def setUp(self):
        super().setUp()
        self.other = Store.objects.create(name="Store B", slug="store-b-flow", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(store=self.store, hostname=HOST, is_primary=True, domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                                   verification_status=V.VERIFIED, verified_at=timezone.now())
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.client = Client(HTTP_HOST=HOST)
        self.fake = FakeInfra()
        for target, repl in (
            ("apps.stores.services.domain_verification_service._txt_records_match", self.fake.txt),
            ("apps.stores.services.domain_verification_service.check_dns_routing", self.fake.routing),
            ("apps.stores.services.domain_verification_service.check_ssl_connection", self.fake.tls),
        ):
            patcher = mock.patch(target, side_effect=repl)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target in ("dns.resolver.resolve", "socket.create_connection"):
            patcher = mock.patch(target, side_effect=AssertionError("real network access in a test"))
            patcher.start()
            self.addCleanup(patcher.stop)
        caches["ratelimit"].clear() if "ratelimit" in settings.CACHES else None

    # helpers -----------------------------------------------------------------------------------------------------------------
    def msgs(self, res):
        return [str(m) for m in get_messages(res.wsgi_request)]

    def add_domain(self, hostname="shop.example.com"):
        self._login(self.owner)
        res = self.client.post(reverse("dashboard:settings-domain-add"), {"hostname": hostname})
        self.assertRedirects(res, PAGE, fetch_redirect_response=False)
        return StoreDomain.objects.get(store=self.store, hostname=hostname)

    def refresh(self, domain, **extra):
        return self.client.post(reverse("dashboard:settings-domain-refresh", args=[domain.id]), **extra)

    def phase(self):
        html = self.client.get(PAGE).content.decode()
        marker = 'data-phase="'
        return html.split(marker)[1].split('"')[0] if marker in html else None

    # the whole journey --------------------------------------------------------------------------------------------------------
    def test_full_seller_journey_ends_at_the_owner_level_confirmation_and_never_activates_by_itself(self):
        d = self.add_domain()
        # 1) registering already issued the ownership record: no extra button, nothing was looked up
        self.assertEqual(d.verification_status, V.PENDING)
        self.assertEqual(self.fake.calls, {"txt": 0, "routing": 0, "tls": 0})
        html = self.client.get(PAGE).content.decode()
        self.assertIn('data-testid="domain-txt-record"', html)
        self.assertIn(d.verification_token, html)
        self.assertEqual(self.phase(), "awaiting_ownership")

        # 2) TXT not visible yet → honest warning, still pending, nothing verified
        res = self.refresh(d)
        d.refresh_from_db()
        self.assertEqual(d.verification_status, V.PENDING)
        self.assertTrue(any("هنوز پیدا نشد" in m for m in self.msgs(res)))

        # 3) TXT visible → ownership verified AND the DNS check runs in the same press (routing not connected yet)
        self.fake.txt_visible = True
        res = self.refresh(d)
        d.refresh_from_db()
        self.assertEqual(d.verification_status, V.VERIFIED)
        self.assertEqual(d.routing_status, StoreDomain.RoutingStatus.NOT_CONNECTED)
        self.assertTrue(any("مالکیتِ دامنه تأیید شد" in m for m in self.msgs(res)))
        self.assertEqual(self.phase(), "needs_action")
        self.assertIn('data-testid="domain-routing-records"', self.client.get(PAGE).content.decode())

        # 4) DNS reaches RastiSi but HTTPS is not ready → «checking», explicitly nothing for the seller to do
        self.fake.routing_connected = True
        res = self.refresh(d)
        self.assertTrue(any("فعلاً نیازی به انجام کاری از طرف شما نیست" in m for m in self.msgs(res)))
        html = self.client.get(PAGE).content.decode()
        self.assertEqual(self.phase(), "checking")
        self.assertIn("فعلاً نیازی به انجام کاری از طرف شما نیست.", html)

        # 5) HTTPS ready → waiting for the final confirmation (portal, Step-Up); NOTHING became primary
        self.fake.tls_ready = True
        self.refresh(d)
        d.refresh_from_db()
        self.assertEqual(self.phase(), "awaiting_final")
        self.assertFalse(d.is_primary)
        html = self.client.get(PAGE).content.decode()
        self.assertIn('data-testid="domain-act-activate"', html)
        self.assertNotIn('data-testid="domain-act-refresh"', html)           # the readiness is fresh: the single next action is the confirmation
        self.assertEqual(StoreDomain.objects.filter(store=self.store, is_primary=True).get().hostname, HOST)

        # 6) the page survives a reload with the same truth (state lives in the database, not in the page)
        self.assertEqual(self.phase(), "awaiting_final")

        # 7) audit trail of what happened
        for code in ("store.custom_domain_requested", "store.custom_domain_verified", "store.custom_domain_readiness_checked"):
            self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code=code).exists(), code)

    def test_stale_readiness_asks_for_one_more_check_instead_of_the_final_confirmation(self):
        d = self.add_domain()
        self.fake.txt_visible = self.fake.routing_connected = self.fake.tls_ready = True
        self.refresh(d)
        self.assertEqual(self.phase(), "awaiting_final")
        StoreDomain.objects.filter(pk=d.pk).update(routing_checked_at=timezone.now() - timezone.timedelta(hours=2))
        html = self.client.get(PAGE).content.decode()
        self.assertIn('data-testid="domain-act-refresh"', html)
        self.assertNotIn('data-testid="domain-act-activate"', html)

    def test_refresh_is_idempotent_and_never_reissues_the_token_for_a_verified_domain(self):
        d = self.add_domain()
        self.fake.txt_visible = True
        self.refresh(d)
        d.refresh_from_db()
        token = d.verification_token
        for _ in range(3):
            self.refresh(d)
        d.refresh_from_db()
        self.assertEqual(d.verification_token, token)
        self.assertEqual(d.verification_status, V.VERIFIED)

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=(), RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="")
    def test_without_platform_targets_the_flow_stops_honestly(self):
        d = self.add_domain()
        self.fake.txt_visible = True
        res = self.refresh(d)
        d.refresh_from_db()
        self.assertEqual(d.verification_status, V.VERIFIED)
        self.assertTrue(any("تنظیم نشده" in m for m in self.msgs(res)))
        self.assertEqual(self.phase(), "platform_wait")
        self.assertFalse(d.is_primary)

    # security ---------------------------------------------------------------------------------------------------------------------
    def test_pending_or_unverified_domains_can_never_become_active_through_the_panel(self):
        d = self.add_domain()
        self.fake.routing_connected = self.fake.tls_ready = True            # DNS+HTTPS look perfect, but ownership is NOT proven
        for _ in range(3):
            self.refresh(d)
        d.refresh_from_db()
        self.assertEqual(d.verification_status, V.PENDING)
        self.assertFalse(d.is_primary)
        self.assertEqual(self.fake.calls["routing"], 0)                      # the DNS/HTTPS probes did not even run before ownership
        self.assertEqual(self.fake.calls["tls"], 0)

    def test_refresh_is_post_only_csrf_protected_and_needs_login_and_permission(self):
        d = self.add_domain()
        url = reverse("dashboard:settings-domain-refresh", args=[d.id])
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        for user in (self.analyst, self.content_editor, self.catalog_manager, self.order_manager):
            self._login(user)
            self.assertIn(self.client.post(url).status_code, (302, 403), user.username)
        d.refresh_from_db()
        self.assertEqual(self.fake.calls, {"txt": 0, "routing": 0, "tls": 0})

    def test_another_stores_domain_is_a_404_and_is_never_looked_up(self):
        foreign = StoreDomain.objects.create(store=self.other, hostname="foreign.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                             verification_status=V.PENDING, verification_token="OTHERSECRET", verification_requested_at=timezone.now())
        self._login(self.owner)
        self.assertEqual(self.refresh(foreign).status_code, 404)
        self.assertEqual(self.fake.calls, {"txt": 0, "routing": 0, "tls": 0})
        html = self.client.get(PAGE).content.decode()
        self.assertNotIn("foreign.example.com", html)
        self.assertNotIn("OTHERSECRET", html)

    def test_a_hostname_of_another_store_cannot_be_registered_and_gets_no_token(self):
        StoreDomain.objects.create(store=self.other, hostname="taken.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN)
        self._login(self.owner)
        self.client.post(reverse("dashboard:settings-domain-add"), {"hostname": "taken.example.com"})
        taken = StoreDomain.objects.get(hostname="taken.example.com")
        self.assertEqual(taken.store_id, self.other.id)
        self.assertEqual(taken.verification_token, "")

    def test_ips_internal_and_test_only_names_are_refused_before_anything_is_stored(self):
        self._login(self.owner)
        before = StoreDomain.objects.count()
        for bad in ("127.0.0.1", "10.0.0.5", "[::1]", "localhost", "shop.localhost", "x.rasti-mode-demo.rastisi.localhost", "a.local", "b.test",
                    "c.internal", "d.invalid", "http://shop.example.com", "shop.example.com/path", "shop.example.com:8000", "user@shop.example.com"):
            self.client.post(reverse("dashboard:settings-domain-add"), {"hostname": bad})
        self.assertEqual(StoreDomain.objects.count(), before)
        self.assertEqual(self.fake.calls, {"txt": 0, "routing": 0, "tls": 0})

    def test_checks_are_rate_limited_per_store_and_domain(self):
        d = self.add_domain()
        for _ in range(8):
            self.refresh(d)
        calls_before = dict(self.fake.calls)
        res = self.refresh(d)                                                # the 9th press within the minute
        self.assertTrue(any("صبر کنید" in m for m in self.msgs(res)))
        self.assertEqual(self.fake.calls, calls_before)

    def test_background_recheck_is_silent_json_and_does_not_spam_messages(self):
        d = self.add_domain()
        self.client.get(PAGE)                                                # show (and so consume) the «domain registered» message
        res = self.refresh(d, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "outcome": "txt_missing"})
        self.assertEqual(self.msgs(res), [])

    def test_the_token_is_only_ever_shown_to_the_owning_store(self):
        d = self.add_domain()
        other_client = Client(HTTP_HOST=HOST)
        self.assertNotIn(d.verification_token, other_client.get(PAGE).content.decode())     # anonymous gets a redirect, never the page
