"""Panel UX (M4-A): the domain page does not present a development/QA address as «the address customers see». Read-only summary only —
the real domain backend (portal, DOMAIN_MANAGE, Step-Up, audit, anti-takeover) is untouched."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.dashboard.services.domain_settings_service import _is_local_address

PARTIAL = "dashboard/partials/settings_domain.html"


def _render(url, local):
    overview = {"storefront_url": url, "storefront_is_local": local, "platform_domains": [], "custom_domains": [],
                "targets_configured": True, "can_manage": False, "portal_url": ""}
    return render_to_string(PARTIAL, {"domain_overview": overview})


class LocalAddressTests(SimpleTestCase):
    def test_development_hosts_are_local(self):
        for url in ("http://shop.rastisi.localhost:8009/", "http://localhost:8000", "https://127.0.0.1/", "http://[::1]:8000/"):
            self.assertTrue(_is_local_address(url), url)

    def test_public_hosts_and_garbage_are_not_local(self):
        for url in ("https://shop.example.com/", "https://akhlaghi.rastisi.ir", "", None, "not a url", "https://localhost.example.com/"):
            self.assertFalse(_is_local_address(url), url)


class DomainPageLabelTests(SimpleTestCase):
    def test_a_local_address_is_labelled_as_a_test_address(self):
        html = _render("http://shop.rastisi.localhost:8009/", True)
        self.assertIn('data-testid="storefront-local-note"', html)
        self.assertIn("نشانیِ فعلیِ محیط آزمایشی", html)
        self.assertNotIn("آدرسی که مشتریان می‌بینند", html)
        self.assertIn('data-testid="storefront-url"', html)          # still a real link

    def test_a_public_address_keeps_the_customer_label_and_no_warning(self):
        html = _render("https://shop.example.com/", False)
        self.assertNotIn("storefront-local-note", html)
        self.assertIn("آدرسی که مشتریان می‌بینند", html)
