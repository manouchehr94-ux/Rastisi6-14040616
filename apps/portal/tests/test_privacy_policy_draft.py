"""The privacy page (PUBLIC-03): a complete DRAFT built from what the platform actually does, never presented as approved.

Safe defaults: unapproved -> visible draft notice, ``noindex``, absent from the sitemap. Only the owner's explicit switch (``privacy.approved``) removes the notice and
allows indexing. Every item that needs a business/legal fact carries a visible ``needs-confirm`` marker; the text must not invent entities, contact data, retention
periods, certifications or hosting locations."""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from apps.portal.models import PublicSiteSetting

HOST = "rastisi.localhost"
PARTIALS = Path(__file__).resolve().parents[1] / "templates/portal/public"
BODY = (PARTIALS / "_privacy_body.html").read_text(encoding="utf-8")
TOC = (PARTIALS / "_privacy_toc.html").read_text(encoding="utf-8")


class PrivacyTextContractTests(SimpleTestCase):
    def test_all_fifteen_required_sections_exist_and_the_toc_links_to_each(self):
        ids = re.findall(r'<section class="r-legal-section" id="(p-[a-z]+)"', BODY)
        self.assertEqual(len(ids), 15)
        self.assertEqual(sorted(re.findall(r'href="#(p-[a-z]+)"', TOC)), sorted(ids))
        self.assertEqual(len(set(ids)), 15)

    def test_unknown_business_and_legal_facts_are_marked_not_invented(self):
        self.assertGreaterEqual(BODY.count("needs-confirm"), 12)
        for section in ("p-hosting", "p-children", "p-deletion", "p-contact"):
            block = BODY[BODY.index(f'id="{section}"'):]
            block = block[:block.index("</section>")]
            self.assertIn("needs-confirm", block, f"{section} depends on a fact only the owner can supply")

    def test_no_invented_identifiers_contacts_certifications_or_locations(self):
        text = re.sub(r"<[^>]+>", " ", BODY)
        self.assertNotRegex(text, r"@[A-Za-z0-9.-]+\.[a-z]{2,}")                      # no email address
        self.assertNotRegex(text, r"\b0?9\d{9}\b|\b0\d{2}[- ]?\d{8}\b")               # no phone number
        for forbidden in ("ISO", "PCI", "SOC", "GDPR", "گواهی‌نامه", "سرورهای ایران", "خارج از ایران", "خارج از کشور ذخیره"):
            self.assertNotIn(forbidden.lower() if forbidden.isascii() else forbidden, text.lower() if forbidden.isascii() else text, forbidden)
        self.assertIn("این متن گواهی یا استانداردی را ادعا نمی‌کند", text)

    def test_every_numeric_retention_fact_is_one_that_exists_in_code(self):
        # 120 s OTP validity, 30 d import files / persistent session, 180 d consent cookie — see docs/legal/PRIVACY_POLICY_DRAFT_20261106.md for the source of each
        from apps.core import consent
        from apps.dashboard.services import import_service
        from apps.portal.services import owner_otp_service
        from django.conf import settings

        self.assertEqual(owner_otp_service.OTP_TTL_SECONDS, 120)
        self.assertEqual(import_service.IMPORT_FILE_RETENTION_DAYS, 30)
        self.assertEqual(settings.AUTH_SESSION_REMEMBER_ME_EXPIRY_SECONDS, 30 * 24 * 3600)
        self.assertEqual(consent.COOKIE_MAX_AGE, 180 * 24 * 3600)
        text = re.sub(r"<[^>]+>", " ", BODY)
        for needle in ("۲ دقیقه", "۳۰ روز", "۱۸۰ روز"):
            self.assertIn(needle, text)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PrivacyPageStateTests(TestCase):
    def _get(self, path="/privacy/"):
        return self.client.get(path, HTTP_HOST=HOST)

    def test_default_is_a_noindex_draft_with_a_visible_notice(self):
        html = self._get().content.decode()
        self.assertIn('content="noindex, nofollow"', html)
        self.assertIn("data-privacy-draft-notice", html)
        self.assertIn("پیش‌نویس", html)
        self.assertGreaterEqual(html.count("needs-confirm"), 12)
        for anchor in ("p-intro", "p-third", "p-cookies", "p-contact"):
            self.assertIn(f'id="{anchor}"', html)

    def test_the_draft_is_not_advertised_in_the_sitemap(self):
        xml = self._get("/sitemap.xml").content.decode()
        self.assertNotIn("/privacy/", xml)
        self.assertIn("/terms/", xml)

    def test_only_the_owners_explicit_approval_switch_publishes_it(self):
        PublicSiteSetting.objects.create(key="privacy.approved", value="1")
        html = self._get().content.decode()
        self.assertIn('content="index, follow"', html)
        self.assertNotIn("data-privacy-draft-notice", html)
        self.assertIn("/privacy/", self._get("/sitemap.xml").content.decode())

    def test_the_switch_exists_in_the_public_site_registry_and_defaults_to_off(self):
        from apps.portal.public_site import registry

        field = registry.get_field("privacy.approved")
        self.assertIsNotNone(field)
        self.assertEqual(field.default, "")

    def test_the_legacy_design_serves_the_same_single_source_text(self):
        from django.test import override_settings as ovr

        with ovr(RASTISI_PUBLIC_SITE_DESIGN="legacy"):
            html = self._get().content.decode()
        self.assertIn("data-privacy-draft-notice", html)
        self.assertIn('id="p-security"', html)
