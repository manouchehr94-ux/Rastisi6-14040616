"""Panel UX (domain page): a plain-language status banner, a «what do I do where» box and a per-domain step checklist. Presentation only —
the domain backend (portal, DOMAIN_MANAGE, Step-Up, audit, anti-takeover) is untouched and this page still has no form."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.dashboard.services.domain_settings_service import _status_summary

PARTIAL = "dashboard/partials/settings_domain.html"
PLATFORM = [{"hostname": "shop.rastisi.ir", "kind": "زیردامنهٔ راستی‌سی", "is_primary": True}]


def _row(hostname, *, primary, next_step="", steps=()):
    return {"hostname": hostname, "is_primary": primary, "verification": "تأیید شده", "routing": "متصل", "tls": "آماده", "overall": "active" if primary else "pending",
            "tone": "ok" if primary else "warn", "next_step": next_step, "next_hint": "", "steps": list(steps)}


class StatusSummaryTests(SimpleTestCase):
    def test_a_test_environment_is_named_as_such_and_points_to_the_real_address(self):
        summary = _status_summary(storefront_url="http://x.localhost:8000/", is_local=True, platform_domains=PLATFORM, custom_rows=[])
        self.assertEqual(summary["key"], "test_environment")
        self.assertIn("shop.rastisi.ir", summary["text"])
        self.assertEqual(summary["tone"], "warn")

    def test_an_active_custom_domain_is_announced(self):
        summary = _status_summary(storefront_url="https://shop.example.com/", is_local=False, platform_domains=PLATFORM,
                                  custom_rows=[_row("shop.example.com", primary=True)])
        self.assertEqual((summary["key"], summary["tone"]), ("custom_active", "ok"))
        self.assertIn("shop.example.com", summary["title"])

    def test_a_domain_in_progress_says_the_shop_stays_reachable_and_names_the_next_step(self):
        summary = _status_summary(storefront_url="https://shop.rastisi.ir/", is_local=False, platform_domains=PLATFORM,
                                  custom_rows=[_row("shop.example.com", primary=False, next_step="تأیید مالکیت با رکورد TXT")])
        self.assertEqual(summary["key"], "custom_in_progress")
        self.assertIn("تأیید مالکیت", summary["text"])
        self.assertIn("آدرس راستی‌سی", summary["text"])

    def test_without_a_custom_domain_it_is_optional_and_never_a_problem(self):
        summary = _status_summary(storefront_url="https://shop.rastisi.ir/", is_local=False, platform_domains=PLATFORM, custom_rows=[])
        self.assertEqual((summary["key"], summary["tone"]), ("platform_only", "info"))
        self.assertIn("اختیاری", summary["text"])

    def test_no_address_at_all_is_flagged(self):
        summary = _status_summary(storefront_url="", is_local=False, platform_domains=[], custom_rows=[])
        self.assertEqual(summary["key"], "no_public_address")


class DomainPageRenderTests(SimpleTestCase):
    def _html(self, **extra):
        overview = {"summary": _status_summary(storefront_url="https://shop.rastisi.ir/", is_local=False, platform_domains=PLATFORM, custom_rows=[]),
                    "storefront_url": "https://shop.rastisi.ir/", "storefront_is_local": False, "platform_domains": PLATFORM, "custom_domains": [],
                    "targets_configured": True, "can_manage": True, "portal_url": "https://rastisi.ir/portal/domains/"}
        overview.update(extra)
        return render_to_string(PARTIAL, {"domain_overview": overview})

    def test_banner_who_does_what_and_guide_are_present_and_the_page_has_no_form(self):
        html = self._html()
        for marker in ('data-testid="domain-status-summary"', 'data-summary="platform_only"', 'data-testid="domain-who-does-what"',
                       'data-testid="domain-six-steps"', 'data-testid="portal-domains-link"'):
            self.assertIn(marker, html)
        self.assertNotIn("<form", html)

    def test_the_six_step_guide_is_open_for_a_shop_without_a_domain_and_folded_once_one_exists(self):
        self.assertRegex(self._html(), r'data-testid="domain-six-steps"\s+open')
        steps = [{"title": "تأیید مالکیت با رکورد TXT", "state": "current", "state_label": "مرحلهٔ فعلی"}]
        with_domain = self._html(custom_domains=[_row("shop.example.com", primary=False, next_step="تأیید مالکیت", steps=steps)])
        self.assertNotRegex(with_domain, r'data-testid="domain-six-steps"\s+open')
        self.assertIn('data-testid="domain-steps"', with_domain)
        self.assertIn("domain-step--current", with_domain)
        self.assertIn("مرحلهٔ فعلی", with_domain)
