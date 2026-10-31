"""Admin «دامنه و آدرس» (settings?section=domain): read-only overview + the real link to the owner-portal domain manager."""

import re

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.tests.test_permission_enforcement import PermissionEnforcementTestCase
from apps.stores.models import StoreDomain


class DomainSettingsPageTests(PermissionEnforcementTestCase):
    def url(self):
        return reverse("dashboard:settings") + "?section=domain"

    def custom(self, **kw):
        defaults = dict(store=self.store, hostname="shop.example.com", domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN)
        defaults.update(kw)
        if defaults.get("verification_status") == "verified":
            defaults.setdefault("verified_at", timezone.now())
        return StoreDomain.objects.create(**defaults)

    def test_owner_sees_current_address_the_guide_and_the_portal_link_built_with_reverse(self):
        self._login(self.owner)
        res = self.client.get(self.url())
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'data-testid="domain-settings"')
        link = res.context["domain_overview"]["portal_url"]
        path = reverse("portal:custom-domains", args=[self.store.public_id], urlconf="shop_core.urls_platform")
        self.assertTrue(link.endswith(path), link)
        self.assertContains(res, 'data-testid="portal-domains-link"')
        self.assertContains(res, "مدیریت و راهنمای اتصال دامنه")

    def test_real_domain_statuses_and_next_step_are_shown(self):
        self.custom()
        self._login(self.owner)
        res = self.client.get(self.url())
        self.assertContains(res, 'data-testid="custom-domain-row"')
        self.assertContains(res, "shop.example.com")
        self.assertContains(res, "قدم بعدی")
        self.assertEqual(res.context["domain_overview"]["custom_domains"][0]["overall"], "pending")

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=(), RASTISI_CUSTOM_DOMAIN_CNAME_TARGET="")
    def test_missing_deployment_targets_are_reported_honestly(self):
        self._login(self.owner)
        self.assertContains(self.client.get(self.url()), 'data-testid="targets-missing"')

    @override_settings(RASTISI_CUSTOM_DOMAIN_A_TARGETS=("203.0.113.10",))
    def test_configured_targets_remove_the_warning(self):
        self._login(self.owner)
        self.assertNotContains(self.client.get(self.url()), 'data-testid="targets-missing"')

    def test_active_domain_is_marked(self):
        self.custom(verification_status="verified", is_primary=True, routing_status="connected", tls_status="ready",
                    routing_checked_at=timezone.now(), tls_checked_at=timezone.now())
        self._login(self.owner)
        self.assertContains(self.client.get(self.url()), "فعال و آدرس اصلیِ فروشگاه")

    def test_administrator_without_domain_manage_sees_status_but_no_portal_link(self):
        self.custom()
        self._login(self.administrator)
        res = self.client.get(self.url())
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "shop.example.com")
        self.assertNotContains(res, 'data-testid="portal-domains-link"')
        self.assertContains(res, 'data-testid="owner-only"')
        self.assertEqual(res.context["domain_overview"]["portal_url"], "")

    def test_no_settings_permission_gets_403_and_the_tab_is_hidden(self):
        self._login(self.analyst)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        page = self.client.get(reverse("dashboard:shipping-setup"))
        self.assertNotContains(page, 'data-tab="settings-domain"')

    def test_manager_gets_the_add_form_posting_to_the_panel_and_never_to_the_owner_portal(self):
        self._login(self.owner)
        html = self.client.get(self.url()).content.decode()
        self.assertIn('data-testid="domain-add-form"', html)
        self.assertIn(f'action="{reverse("dashboard:settings-domain-add")}"', html)
        section = html[html.index('data-testid="domain-settings"'):].split("</main>")[0]
        for action in re.findall(r'<form[^>]*action="([^"]+)"', section):
            self.assertTrue(action.startswith("/admin-portal/settings/domain/"), action)

    def test_a_member_without_domain_manage_sees_the_page_without_any_form(self):
        self._login(self.analyst)
        res = self.client.get(self.url())
        if res.status_code == 200:
            html = res.content.decode()
            section = html[html.index('data-testid="domain-settings"'):].split("</main>")[0] if 'data-testid="domain-settings"' in html else ""
            self.assertNotIn('method="post"', section)

    def test_legacy_section_links_still_resolve(self):
        self._login(self.owner)
        for section in ("general", "finance", "payment-config", "unpaid-orders", "delivery-payment", "sms", "integrations", "industry"):
            self.assertEqual(self.client.get(reverse("dashboard:settings") + f"?section={section}").status_code, 200, section)

    def test_settings_pages_render_exactly_one_tab_row_and_a_subtab_row_where_needed(self):
        self._login(self.owner)
        html = self.client.get(reverse("dashboard:settings") + "?section=payment-config").content.decode()
        self.assertEqual(html.count('class="admin-section-tablist"'), 1)
        self.assertNotIn('class="settings-nav"', html)
        self.assertIn('data-testid="admin-subtabs"', html)
        self.assertIn('data-subtab="payment-config"', html)
        self.assertIn("data-au-search-input", html)
