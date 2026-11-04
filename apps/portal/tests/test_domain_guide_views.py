"""Portal custom-domain page: six-step guide, real Host/Type/Value records with Copy, honest «targets not configured», actionable hints,
fresh-only activation, permission/isolation. DNS/TLS are mocked — nothing real is queried."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.portal.tests.test_custom_domain_views import _HOST, CustomDomainViewsTestCase, _FakeTXTRecord, _resolve_target
from apps.stores.models import Store, StoreDomain, StoreMembership
from apps.portal.models import OwnerProfile

User = get_user_model()
TARGETS = {"RASTISI_CUSTOM_DOMAIN_A_TARGETS": ("203.0.113.10",), "RASTISI_CUSTOM_DOMAIN_CNAME_TARGET": "edge.rastisi.test"}


class GuideViewTests(CustomDomainViewsTestCase):
    def page(self):
        return self.client.get(self._list_url(), HTTP_HOST=_HOST)

    def add(self, hostname="shop.example.com"):
        self.client.post(self._list_url(), {"action": "add", "hostname": hostname}, HTTP_HOST=_HOST)
        return StoreDomain.objects.get(store=self.store, hostname=hostname)

    def verify(self, domain):
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/begin-verify/", HTTP_HOST=_HOST)
        domain.refresh_from_db()
        with patch(_resolve_target()) as r:
            r.return_value = [_FakeTXTRecord(f"rastisi-verify={domain.verification_token}")]
            self.client.post(f"/app/stores/{self.store.public_id}/domains/{domain.pk}/check/", HTTP_HOST=_HOST)
        domain.refresh_from_db()
        return domain

    def test_guide_and_six_steps_are_shown(self):
        self.add()
        page = self.page()
        self.assertContains(page, "راهنمای شش‌مرحله‌ای")
        self.assertContains(page, 'data-testid="domain-card"')
        self.assertEqual(page.content.decode().count('class="dm-step '), 6)
        self.assertContains(page, "shop.example.com")

    @override_settings(**TARGETS)
    def test_txt_record_has_host_type_value_and_copy_buttons(self):
        d = self.add()
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{d.pk}/begin-verify/", HTTP_HOST=_HOST)
        d.refresh_from_db()
        html = self.page().content.decode()
        self.assertIn('data-testid="txt-record"', html)
        self.assertIn("_rastisi-verify.shop", html)
        self.assertIn(f"rastisi-verify={d.verification_token}", html)
        self.assertGreaterEqual(html.count("data-copy-target"), 2)
        self.assertIn("بررسی مجدد رکورد TXT", html)

    @override_settings(**TARGETS)
    def test_verified_subdomain_shows_cname_as_recommended_with_copy(self):
        d = self.verify(self.add())
        html = self.page().content.decode()
        self.assertIn('data-testid="routing-records"', html)
        self.assertIn("edge.rastisi.test", html)
        self.assertIn("203.0.113.10", html)
        self.assertRegex(html, r'class="dm-reco"[^>]*>\s*<td><code>CNAME</code>')
        self.assertNotIn('data-testid="targets-missing"', html)

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=(), RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="")
    def test_unconfigured_targets_are_stated_honestly_and_no_value_is_invented(self):
        self.verify(self.add())
        page = self.page()
        self.assertContains(page, 'data-testid="targets-missing"')
        self.assertContains(page, "مقصد اتصال هنوز آماده نیست")
        self.assertNotContains(page, 'class="dm-reco"')

    @override_settings(**TARGETS)
    def test_activation_button_only_with_fresh_readiness(self):
        d = self.verify(self.add())
        self.assertNotContains(self.page(), 'data-testid="activate"')
        now = timezone.now()
        StoreDomain.objects.filter(pk=d.pk).update(routing_status="connected", routing_checked_at=now, tls_status="ready", tls_checked_at=now)
        self.assertContains(self.page(), 'data-testid="activate"')
        old = now - timedelta(hours=2)
        StoreDomain.objects.filter(pk=d.pk).update(routing_checked_at=old, tls_checked_at=old)
        page = self.page()
        self.assertNotContains(page, 'data-testid="activate"')
        self.assertContains(page, "قدیمی")

    @override_settings(**TARGETS)
    def test_active_domain_shows_the_live_link(self):
        d = self.verify(self.add())
        StoreDomain.objects.filter(pk=d.pk).update(is_primary=True)
        page = self.page()
        self.assertContains(page, 'data-testid="live-link"')
        self.assertContains(page, "https://shop.example.com/")

    @override_settings(**TARGETS)
    def test_activation_still_goes_through_step_up_and_rechecks_freshness(self):
        d = self.verify(self.add())
        now = timezone.now()
        StoreDomain.objects.filter(pk=d.pk).update(routing_status="connected", routing_checked_at=now, tls_status="ready", tls_checked_at=now)
        resp = self.client.post(f"/app/stores/{self.store.public_id}/domains/{d.pk}/activate/", HTTP_HOST=_HOST)
        d.refresh_from_db()
        self.assertFalse(d.is_primary)                                           # not active until the Step-Up code is confirmed
        self.assertEqual(resp.status_code, 302)
        stale = now - timedelta(hours=2)
        StoreDomain.objects.filter(pk=d.pk).update(routing_checked_at=stale, tls_checked_at=stale)
        self.client.post(f"/app/stores/{self.store.public_id}/domains/{d.pk}/activate/step-up/", {"code": self.code}, HTTP_HOST=_HOST)
        d.refresh_from_db()
        self.assertFalse(d.is_primary)                                           # stale readiness is refused by the service

    def test_a_domain_of_another_store_cannot_be_added_or_seen(self):
        other = Store.objects.create(name="دیگر", slug="guide-other", status=Store.Status.ACTIVE)
        StoreDomain.objects.create(store=other, hostname="taken.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status="verified", verified_at=timezone.now())
        self.client.post(self._list_url(), {"action": "add", "hostname": "taken.example.com"}, HTTP_HOST=_HOST)
        self.assertFalse(StoreDomain.objects.filter(store=self.store, hostname="taken.example.com").exists())
        self.assertNotContains(self.page(), 'data-testid="domain-card"')        # no card for a domain this store does not own

    def test_non_owner_member_sees_status_but_no_actions(self):
        staff = User.objects.create_user(username="09121290055", password="x-Pass#1234")
        OwnerProfile.objects.create(user=staff, phone="09121290055", full_name="عضو")
        StoreMembership.objects.create(store=self.store, user=staff, role=StoreMembership.Role.ADMINISTRATOR,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.add()
        self.client.force_login(staff)
        res = self.client.get(self._list_url(), HTTP_HOST=_HOST)
        if res.status_code == 200:
            self.assertNotContains(res, 'name="hostname"')
            self.assertNotContains(res, "begin-verify")
        post = self.client.post(self._list_url(), {"action": "add", "hostname": "x.example.com"}, HTTP_HOST=_HOST)
        self.assertFalse(StoreDomain.objects.filter(hostname="x.example.com").exists())
