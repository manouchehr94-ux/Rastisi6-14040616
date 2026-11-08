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
    def test_ten_sections_match_toc(self):
        ids = re.findall(
            r'<section data-privacy-section="\d+" id="(p-\d+)">',
            BODY,
        )
        links = re.findall(r'href="#(p-\d+)"', TOC)
        self.assertEqual(ids, [f"p-{i}" for i in range(1, 11)])
        self.assertEqual(links, ids)

    def test_security_claims_are_not_absolute(self):
        self.assertIn("هیچ سامانه اینترنتی", BODY)
        self.assertNotIn("امنیت صددرصد", BODY)
        for claim in ("ISO 27001", "PCI DSS", "SOC 2",
                      "گواهی‌نامه امنیتی"):
            self.assertNotIn(claim, BODY)

    def test_no_invented_contact_details(self):
        plain = re.sub(r"<[^>]+>", " ", BODY)
        self.assertNotRegex(
            plain, r"@[A-Za-z0-9.-]+\.[a-z]{2,}"
        )
        self.assertNotRegex(
            plain, r"\b0?9\d{9}\b|\b0\d{2}[- ]?\d{8}\b"
        )
        self.assertNotIn("سرورهای ایران", plain)

    def test_retention_section_does_not_invent_a_schedule(self):
        section = BODY.split('id="p-7"', 1)[1]
        section = section.split("</section>", 1)[0]
        self.assertIn("الزامات قانونی", section)
        self.assertNotRegex(
            section, r"\d+\s*(روز|ماه|سال)"
        )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PrivacyPageStateTests(TestCase):
    def _get(self, path="/privacy/"):
        return self.client.get(path, HTTP_HOST=HOST)

    def test_unapproved_policy_is_noindex_with_ten_sections(self):
        html = self._get().content.decode()
        self.assertIn('content="noindex, nofollow"', html)
        for i in range(1, 11):
            self.assertIn(f'id="p-{i}"', html)

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

    def test_legacy_design_uses_same_policy_and_noindex(self):
        from django.test import override_settings as ovr

        with ovr(PUBLIC_SITE_FORCE_DESIGN="legacy"):
            html = self._get().content.decode()
        self.assertIn('content="noindex, nofollow"', html)
        self.assertIn('id="p-4"', html)
        self.assertIn('id="p-10"', html)
