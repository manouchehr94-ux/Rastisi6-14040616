"""Section 18 — SEO/indexing: internal/account pages are noindex, real
public marketing pages carry unique metadata, and the platform's own
robots.txt/sitemap.xml (distinct from the tenant-scoped apps.core.seo
ones) only ever reference genuinely public pages."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PublicPageIndexabilityTests(TestCase):
    def test_home_page_is_indexable(self):
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "noindex")

    def test_features_plans_help_contact_are_indexable_with_unique_descriptions(self):
        seen_descriptions = set()
        for path in ["/features/", "/design/", "/plans/", "/about/", "/help/", "/contact/"]:
            response = self.client.get(path, HTTP_HOST=_HOST)
            self.assertNotContains(response, "noindex")
            content = response.content.decode()
            start = content.index('name="description" content="') + len('name="description" content="')
            description = content[start:content.index('"', start)]
            self.assertNotIn(description, seen_descriptions, f"{path} reuses a description")
            seen_descriptions.add(description)

    def test_register_is_indexable(self):
        response = self.client.get("/register/", HTTP_HOST=_HOST)
        self.assertNotContains(response, "noindex")

    def test_terms_and_privacy_are_indexable(self):
        for path in ["/terms/", "/privacy/"]:
            response = self.client.get(path, HTTP_HOST=_HOST)
            self.assertContains(response, "index, follow")


class AuthAndAccountPageNoindexTests(TestCase):
    def test_login_is_noindex(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, "noindex")

    def test_login_email_redirects_to_the_noindex_unified_login(self):
        response = self.client.get("/login-email/", HTTP_HOST=_HOST, follow=True)
        self.assertContains(response, "noindex")

    def test_register_email_is_noindex(self):
        response = self.client.get("/register-email/", HTTP_HOST=_HOST)
        self.assertContains(response, "noindex")

    def test_password_reset_request_is_noindex(self):
        response = self.client.get("/reset-password/", HTTP_HOST=_HOST)
        self.assertContains(response, "noindex")

    def test_otp_verify_is_noindex(self):
        # Requires an in-flight OTP session to render 200; a bare GET
        # redirects to /login/ instead, so just confirm the template itself
        # declares noindex by checking the source directly.
        with open("apps/portal/templates/portal/public/otp_verify.html") as fh:
            self.assertIn("noindex", fh.read())

    def test_my_stores_app_pages_are_noindex(self):
        owner = User.objects.create_user(username="09121360011", password="a-very-strong-pass-1")
        self.client.force_login(owner)
        response = self.client.get("/app/", HTTP_HOST=_HOST)
        self.assertContains(response, "noindex")


class PlatformRobotsAndSitemapTests(TestCase):
    def test_robots_txt_disallows_the_app_area_and_points_at_the_sitemap(self):
        response = self.client.get("/robots.txt", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        body = response.content.decode()
        self.assertIn("Disallow: /app/", body)
        self.assertIn("Sitemap:", body)
        self.assertIn("sitemap.xml", body)

    def test_sitemap_xml_lists_only_public_pages(self):
        response = self.client.get("/sitemap.xml", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        body = response.content.decode()
        self.assertIn("/features/", body)
        self.assertIn("/design/", body)
        self.assertIn("/about/", body)
        self.assertIn("/supported-industries/", body)
        self.assertIn("/plans/", body)
        self.assertIn("/register/", body)
        self.assertNotIn("/app/", body)
        self.assertNotIn("/login/", body)
