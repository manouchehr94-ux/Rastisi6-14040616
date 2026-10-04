"""Section: auth unification — the single canonical /login/ page (password
default, OTP secondary) and its remember-me behavior across both paths,
including the merchant-admin handoff continuing to work through the
NEW password path (the OTP path's handoff was already covered by
test_central_admin_login.py before this pass)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.portal.services.handoff_service import build_admin_return_token
from apps.portal.services import owner_auth_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class UnifiedLoginPageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_get_renders_both_password_and_otp_forms(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="identifier"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'name="phone"')
        self.assertContains(response, "رمز یک‌بارمصرف")
        self.assertContains(response, "ارسالِ دوباره‌ی کد", count=0)  # not on this page

    def test_remember_me_checkbox_present_on_both_forms(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, "مرا به خاطر بسپار", count=2)

    def test_password_field_has_correct_autocomplete_attributes(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')

    def test_forgot_password_link_present(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, "فراموشی رمز عبور")

    def test_password_form_posts_to_dedicated_endpoint(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, '/login/password/')


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RememberMeAcrossPasswordLoginTests(TestCase):
    def setUp(self):
        self.owner = owner_auth_service.register_owner(
            full_name="Remember Owner", email="remember@example.com", password="a-very-strong-pass-1",
        )

    def test_unchecked_expires_at_browser_close(self):
        self.client.post(
            "/login/password/", {"identifier": "remember@example.com", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_checked_uses_persistent_expiry(self):
        self.client.post(
            "/login/password/",
            {"identifier": "remember@example.com", "password": "a-very-strong-pass-1", "remember_me": "on"},
            HTTP_HOST=_HOST,
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class RememberMeAcrossOtpLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner, _created = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121230099", full_name="OTP Remember Owner",
        )
        import apps.portal.services.owner_otp_service as svc

        self._original = svc._generate_code
        svc._generate_code = lambda: "554433"
        self.addCleanup(setattr, svc, "_generate_code", self._original)

    def test_remember_me_choice_survives_the_request_to_verify_transition(self):
        self.client.post("/login/", {"phone": "09121230099", "remember_me": "on"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09121230099", "code": "554433"}, HTTP_HOST=_HOST)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)

    def test_unchecked_remember_me_expires_at_browser_close(self):
        self.client.post("/login/", {"phone": "09121230099"}, HTTP_HOST=_HOST)
        self.client.post("/verify/", {"phone": "09121230099", "code": "554433"}, HTTP_HOST=_HOST)
        self.assertTrue(self.client.session.get_expire_at_browser_close())


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PasswordLoginAdminHandoffTests(TestCase):
    """The merchant-admin handoff (admin_return) must work through the NEW
    password login path too, not just the pre-existing OTP path."""

    def setUp(self):
        self.owner = owner_auth_service.register_owner(
            full_name="Handoff Owner", email="handoff@example.com", password="a-very-strong-pass-1",
        )
        self.store = Store.objects.create(
            name="فروشگاه هندشیک", slug="handoff-password-store", admin_subdomain="handoff-password-store",
            status=Store.Status.ACTIVE,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def test_password_login_with_admin_return_redirects_to_handoff_ticket(self):
        token = build_admin_return_token(
            admin_subdomain=self.store.admin_subdomain, destination_path="/admin-portal/",
        )
        response = self.client.post(
            "/login/password/",
            {"identifier": "handoff@example.com", "password": "a-very-strong-pass-1", "admin_return": token},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{self.store.admin_subdomain}.", response["Location"])
        self.assertIn("/admin-portal/handoff/", response["Location"])

    def test_password_login_with_safe_next_redirects_there(self):
        response = self.client.post(
            "/login/password/",
            {"identifier": "handoff@example.com", "password": "a-very-strong-pass-1", "next": "/app/stores/"},
            HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, "/app/stores/", fetch_redirect_response=False)

    def test_password_login_never_follows_unsafe_next(self):
        response = self.client.post(
            "/login/password/",
            {
                "identifier": "handoff@example.com", "password": "a-very-strong-pass-1",
                "next": "https://evil.example.com/",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response["Location"])
