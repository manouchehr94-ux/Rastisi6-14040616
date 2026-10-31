"""In-panel custom-domain actions (``views_domain``): the seller starts/continues connecting a domain without leaving the admin panel.

No real DNS / TLS is ever touched — every network-facing function of the domain service is mocked."""

from types import SimpleNamespace
from unittest import mock

from django.contrib.messages import get_messages
from django.conf import settings
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLogEntry
from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import Store, StoreDomain

DVS = "apps.dashboard.views_domain.dvs"
PAGE = "/admin-portal/settings/?section=domain"


HOST = f"dom-a.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class DomainPanelActionTests(PermissionEnforcementTestCase):
    """Two active stores exist, so the Store is resolved from the request host exactly as in production."""

    def setUp(self):
        super().setUp()
        self.other = Store.objects.create(name="Store B", slug="store-b-domain", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(store=self.store, hostname=HOST, is_primary=True,
                                   domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.client = Client(HTTP_HOST=HOST)
        # seed data may already carry domains for this store: assertions are relative to what existed before each test
        self.baseline_all = StoreDomain.objects.filter(store=self.store).count()
        self.baseline_custom = StoreDomain.objects.filter(store=self.store, domain_type="custom_domain").count()

    def add(self, hostname="shop.example.com", **kw):
        return StoreDomain.objects.create(store=kw.pop("store", self.store), hostname=hostname,
                                          domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN, **kw)

    def msgs(self, res):
        return [str(m) for m in get_messages(res.wsgi_request)]

    # ── add ─────────────────────────────────────────────────────────────────────────────────────────────
    def test_owner_adds_a_domain_for_this_store_only_and_is_sent_back_to_the_panel_page(self):
        self._login(self.owner)
        res = self.client.post(reverse("dashboard:settings-domain-add"), {"hostname": "Shop.Example.com"})
        self.assertRedirects(res, PAGE, fetch_redirect_response=False)
        d = StoreDomain.objects.get(hostname="shop.example.com")
        self.assertEqual(d.store_id, self.store.id)
        self.assertEqual(d.domain_type, StoreDomain.DomainType.CUSTOM_DOMAIN)
        self.assertFalse(d.is_primary)  # adding never changes the live address
        # the ownership record is issued right away (one button fewer) — it is only a generated token: nothing is queried or activated
        self.assertEqual(d.verification_status, StoreDomain.VerificationStatus.PENDING)
        self.assertTrue(d.verification_token)
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="store.custom_domain_requested").exists())

    def test_a_hostname_owned_by_another_store_cannot_be_taken_over(self):
        self.add("taken.example.com", store=self.other)
        self._login(self.owner)
        res = self.client.post(reverse("dashboard:settings-domain-add"), {"hostname": "taken.example.com"})
        self.assertRedirects(res, PAGE, fetch_redirect_response=False)
        self.assertEqual(StoreDomain.objects.filter(hostname="taken.example.com").count(), 1)
        self.assertEqual(StoreDomain.objects.get(hostname="taken.example.com").store_id, self.other.id)
        self.assertTrue(any("قبلاً" in m for m in self.msgs(res)))

    def test_invalid_and_platform_owned_hostnames_are_refused_with_a_message(self):
        self._login(self.owner)
        for bad in ("", "not a domain", "http://x", "localhost", "127.0.0.1", "foo.rastisi.ir"):
            res = self.client.post(reverse("dashboard:settings-domain-add"), {"hostname": bad})
            self.assertEqual(res.status_code, 302, bad)
        self.assertEqual(StoreDomain.objects.filter(store=self.store, domain_type="custom_domain").count(), self.baseline_custom)

    # ── permissions / methods / csrf ────────────────────────────────────────────────────────────────────
    def test_members_without_domain_manage_cannot_run_any_action(self):
        d = self.add()
        urls = [reverse("dashboard:settings-domain-add")] + [
            reverse(f"dashboard:settings-domain-{n}", args=[d.id]) for n in ("begin", "check", "readiness")]
        for user in (self.analyst, self.content_editor, self.catalog_manager, self.order_manager):
            self._login(user)
            for u in urls:
                with mock.patch(DVS) as dvs:
                    res = self.client.post(u, {"hostname": "x.example.com"})
                self.assertIn(res.status_code, (302, 403), (user.username, u))
                self.assertFalse(dvs.request_custom_domain.called or dvs.begin_dns_verification.called
                                 or dvs.check_dns_verification.called or dvs.refresh_custom_domain_readiness.called)
        self.assertEqual(StoreDomain.objects.filter(store=self.store).count(), self.baseline_all + 1)

    def test_anonymous_cannot_post(self):
        d = self.add()
        self.client.logout()
        res = self.client.post(reverse("dashboard:settings-domain-begin", args=[d.id]))
        self.assertEqual(res.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.verification_status, StoreDomain.VerificationStatus.UNVERIFIED)

    def test_actions_are_post_only(self):
        d = self.add()
        self._login(self.owner)
        for u in (reverse("dashboard:settings-domain-add"), *[reverse(f"dashboard:settings-domain-{n}", args=[d.id])
                                                              for n in ("begin", "check", "readiness")]):
            self.assertEqual(self.client.get(u).status_code, 405, u)

    def test_csrf_is_enforced_when_the_client_enforces_it(self):
        d = self.add()
        c = Client(enforce_csrf_checks=True, HTTP_HOST=HOST)
        c.force_login(self.owner)
        res = c.post(reverse("dashboard:settings-domain-begin", args=[d.id]))
        self.assertEqual(res.status_code, 403)
        d.refresh_from_db()
        self.assertEqual(d.verification_status, StoreDomain.VerificationStatus.UNVERIFIED)

    # ── tenant scoping ──────────────────────────────────────────────────────────────────────────────────
    def test_another_stores_domain_is_a_404_for_every_action_and_stays_untouched(self):
        foreign = self.add("foreign.example.com", store=self.other)
        self._login(self.owner)
        for n in ("begin", "check", "readiness"):
            with mock.patch(DVS) as dvs:
                res = self.client.post(reverse(f"dashboard:settings-domain-{n}", args=[foreign.id]))
            self.assertEqual(res.status_code, 404, n)
            self.assertFalse(dvs.begin_dns_verification.called or dvs.check_dns_verification.called
                             or dvs.refresh_custom_domain_readiness.called)
        foreign.refresh_from_db()
        self.assertEqual(foreign.verification_status, StoreDomain.VerificationStatus.UNVERIFIED)

    def test_non_custom_and_retired_domains_are_not_actionable(self):
        plat = StoreDomain.objects.create(store=self.store, hostname="shop-x.rastisi.ir",
                                          domain_type=StoreDomain.DomainType.PLATFORM_SUBDOMAIN)
        retired = self.add("old.example.com", retired_at=timezone.now())
        self._login(self.owner)
        for d in (plat, retired):
            self.assertEqual(self.client.post(reverse("dashboard:settings-domain-begin", args=[d.id])).status_code, 404)

    # ── actions use the one service (mocked: no DNS) ───────────────────────────────────────────────────
    def test_begin_calls_the_domain_service_with_the_acting_user_and_this_stores_domain(self):
        d = self.add()
        self._login(self.owner)
        with mock.patch(DVS) as dvs:
            dvs.DomainVerificationError = Exception
            res = self.client.post(reverse("dashboard:settings-domain-begin", args=[d.id]))
        self.assertRedirects(res, PAGE, fetch_redirect_response=False)
        dvs.begin_dns_verification.assert_called_once()
        kw = dvs.begin_dns_verification.call_args.kwargs
        self.assertEqual(kw["domain"].pk, d.pk)
        self.assertEqual(kw["actor"], self.owner)

    def test_begin_really_moves_the_domain_to_pending_with_a_token(self):
        d = self.add()
        self._login(self.owner)
        self.client.post(reverse("dashboard:settings-domain-begin", args=[d.id]))
        d.refresh_from_db()
        self.assertEqual(d.verification_status, StoreDomain.VerificationStatus.PENDING)
        self.assertTrue(d.verification_token)

    def test_check_reports_not_found_as_a_warning_and_found_as_success_without_real_dns(self):
        d = self.add()
        self._login(self.owner)
        with mock.patch(DVS) as dvs:
            dvs.DomainVerificationError = Exception
            dvs.check_dns_verification.return_value = False
            res = self.client.post(reverse("dashboard:settings-domain-check", args=[d.id]))
        self.assertTrue(any("هنوز پیدا نشد" in m for m in self.msgs(res)))
        with mock.patch(DVS) as dvs:
            dvs.DomainVerificationError = Exception
            dvs.check_dns_verification.return_value = True
            res = self.client.post(reverse("dashboard:settings-domain-check", args=[d.id]))
        self.assertTrue(any("تأیید شد" in m for m in self.msgs(res)))

    def test_readiness_messages_cover_unconfigured_not_connected_connecting_and_ready(self):
        d = self.add()
        self._login(self.owner)
        cases = [
            (SimpleNamespace(routing=SimpleNamespace(configured=False, connected=False), tls=None), "تنظیم نشده"),
            (SimpleNamespace(routing=SimpleNamespace(configured=True, connected=False), tls=None), "هنوز به راستی‌سی نرسیده"),
            (SimpleNamespace(routing=SimpleNamespace(configured=True, connected=True), tls=SimpleNamespace(reachable=False)), "آماده‌سازیِ HTTPS"),
            (SimpleNamespace(routing=SimpleNamespace(configured=True, connected=True), tls=SimpleNamespace(reachable=True)), "فقط فعال‌سازیِ نهایی"),
        ]
        for result, expect in cases:
            with mock.patch(DVS) as dvs:
                dvs.DomainVerificationError = Exception
                dvs.refresh_custom_domain_readiness.return_value = result
                res = self.client.post(reverse("dashboard:settings-domain-readiness", args=[d.id]))
            self.assertTrue(any(expect in m for m in self.msgs(res)), (expect, self.msgs(res)))

    def test_service_errors_become_messages_not_500s(self):
        d = self.add()  # unverified → readiness refuses
        self._login(self.owner)
        res = self.client.post(reverse("dashboard:settings-domain-readiness", args=[d.id]))
        self.assertRedirects(res, PAGE, fetch_redirect_response=False)
        self.assertTrue(any("TXT" in m for m in self.msgs(res)))

    # ── page reflects the real state ────────────────────────────────────────────────────────────────────
    def test_page_shows_the_right_primary_action_per_state(self):
        S = StoreDomain.VerificationStatus
        self._login(self.owner)
        d = self.add()
        html = self.client.get(PAGE).content.decode()
        self.assertIn('data-testid="domain-act-begin"', html)                      # (a legacy row that never got its record)
        self.assertIn('data-phase="awaiting_ownership"', html)
        d.verification_status = S.PENDING
        d.verification_requested_at = timezone.now()
        d.verification_token = "tok123"
        d.save()
        html = self.client.get(PAGE).content.decode()
        self.assertIn('data-testid="domain-act-refresh"', html)                    # ONE «check status» button, not separate TXT / DNS buttons
        self.assertNotIn('data-testid="domain-act-begin"', html)
        self.assertIn('data-testid="domain-txt-record"', html)
        d.verification_status = S.VERIFIED
        d.verified_at = timezone.now()
        d.save()
        with override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=("203.0.113.10",)):
            html = self.client.get(PAGE).content.decode()
        self.assertIn('data-phase="needs_action"', html)
        self.assertIn('data-testid="domain-act-refresh"', html)
        self.assertIn('data-testid="domain-routing-records"', html)

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=(), RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="")
    def test_when_the_platform_has_no_connection_targets_the_seller_is_told_honestly_there_is_nothing_to_do(self):
        self.add(verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self._login(self.owner)
        html = self.client.get(PAGE).content.decode()
        self.assertIn('data-phase="platform_wait"', html)
        self.assertIn("فعلاً نیازی به انجام کاری از طرف شما نیست.", html)
        self.assertNotIn('data-testid="domain-act-refresh"', html)                 # no dead button
        self.assertNotIn('data-testid="domain-act-activate"', html)

    def test_page_never_renders_another_stores_domain_or_any_token_secret(self):
        self.add("foreign.example.com", store=self.other, verification_token="OTHERSECRETTOKEN")
        self._login(self.owner)
        html = self.client.get(PAGE).content.decode()
        self.assertNotIn("foreign.example.com", html)
        self.assertNotIn("OTHERSECRETTOKEN", html)

    def test_status_line_shows_labels_never_python_reprs(self):
        d = self.add(verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        self._login(self.owner)
        html = self.client.get(PAGE).content.decode()
        line = next(l for l in html.splitlines() if "اتصال DNS:" in l and d.get_routing_status_display() in l)
        for junk in ("{", "}", "None", "configured", "rows"):
            self.assertNotIn(junk, line)
