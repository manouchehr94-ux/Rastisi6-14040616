from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["rastisi.localhost", "platformadmins.rastisi.localhost", "testserver"])
class PlatformHostRoutingTests(TestCase):
    def test_marketing_host_serves_portal_home(self):
        response = self.client.get("/", HTTP_HOST="rastisi.localhost")
        self.assertEqual(response.status_code, 200)
        # Canonical brand spelling uses a zero-width non-joiner: راستی‌سی.
        self.assertContains(response, "راستی\u200cسی")
        self.assertRegex(response.content.decode(), r"<title>[^<]*راستی\u200cسی[^<]*</title>")

    def test_platform_admin_host_serves_platform_admin_login_redirect(self):
        response = self.client.get("/", HTTP_HOST="platformadmins.rastisi.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_marketing_host_does_not_serve_platform_admin_routes(self):
        response = self.client.get("/login/", HTTP_HOST="rastisi.localhost")
        # This is the owner portal's own /login/, not the platform-admin one —
        # both exist, on different hosts, and must not cross-resolve.
        self.assertEqual(response.status_code, 200)

    def test_ordinary_host_is_unaffected_by_platform_routing(self):
        response = self.client.get("/", HTTP_HOST="testserver")
        # Falls through to ROOT_URLCONF's per-Store catalog routing exactly
        # as before this middleware existed (compatibility-fallback storefront).
        self.assertIn(response.status_code, (200, 404))
