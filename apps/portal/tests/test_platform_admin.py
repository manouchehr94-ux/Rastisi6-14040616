from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import PlatformAuditLogEntry

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminAccessTests(TestCase):
    def setUp(self):
        self.staff_superuser = User.objects.create_user(
            username="platformstaff@example.com", email="platformstaff@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.ordinary_owner = User.objects.create_user(
            username="ordinary@example.com", email="ordinary@example.com", password="a-very-strong-pass-1",
        )
        self.staff_but_not_superuser = User.objects.create_user(
            username="halfstaff@example.com", email="halfstaff@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=False,
        )

    def test_anonymous_is_redirected_to_platform_admin_login(self):
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_ordinary_owner_cannot_reach_platform_admin(self):
        self.client.force_login(self.ordinary_owner)
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_staff_without_superuser_cannot_reach_platform_admin(self):
        self.client.force_login(self.staff_but_not_superuser)
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_staff_superuser_can_reach_platform_admin(self):
        self.client.force_login(self.staff_superuser)
        response = self.client.get("/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)

    def test_platform_admin_login_view_works_on_get(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminLoginRememberMeTests(TestCase):
    def setUp(self):
        cache.clear()  # rate-limit counters are cache-backed, not reset by transaction rollback
        self.staff_superuser = User.objects.create_user(
            username="rememberadmin@example.com", email="rememberadmin@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )

    def test_correct_credentials_log_in(self):
        response = self.client.post(
            "/login/", {"email": "rememberadmin@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_remember_me_unchecked_expires_at_browser_close(self):
        self.client.post(
            "/login/", {"email": "rememberadmin@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_checked_uses_persistent_expiry(self):
        self.client.post(
            "/login/",
            {"email": "rememberadmin@example.com", "password": "a-very-strong-pass-1", "remember_me": "on"},
            HTTP_HOST=_HOST,
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)

    def test_remember_me_checkbox_present_on_the_page(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertContains(response, "مرا به خاطر بسپار")

    def test_non_superuser_staff_never_gets_logged_in_even_with_correct_password(self):
        User.objects.create_user(
            username="halfadmin2@example.com", email="halfadmin2@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=False,
        )
        response = self.client.post(
            "/login/", {"email": "halfadmin2@example.com", "password": "a-very-strong-pass-1"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminEmailLoginWithDifferentUsernameTests(TestCase):
    """AUTH_USER_MODEL's USERNAME_FIELD is "username", not "email" — the
    login form only collects email, so authenticate() must be called with
    the real username after an email lookup. Every other login test in this
    file happens to use ``username == email``, which would hide this bug —
    these tests deliberately use a username that does NOT match the email."""

    def setUp(self):
        cache.clear()  # rate-limit counters are cache-backed, not reset by transaction rollback
        self.staff_superuser = User.objects.create_user(
            username="realplatformowner", email="owner@rastisi-platform.example",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )

    def test_login_with_email_succeeds_when_username_differs_from_email(self):
        response = self.client.post(
            "/login/",
            {"email": "owner@rastisi-platform.example", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.staff_superuser.pk)

    def test_login_with_email_is_case_insensitive(self):
        response = self.client.post(
            "/login/",
            {"email": "OWNER@Rastisi-Platform.example", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_with_wrong_password_fails_with_generic_error(self):
        response = self.client.post(
            "/login/",
            {"email": "owner@rastisi-platform.example", "password": "totally-wrong-password"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "شناسه، رمز عبور، یا دسترسی نامعتبر است")

    def test_login_with_unknown_email_fails_with_the_same_generic_error(self):
        response = self.client.post(
            "/login/",
            {"email": "no-such-user@example.com", "password": "whatever-password"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "شناسه، رمز عبور، یا دسترسی نامعتبر است")

    def test_remember_me_still_works_with_email_login(self):
        self.client.post(
            "/login/",
            {
                "email": "owner@rastisi-platform.example", "password": "a-very-strong-pass-1",
                "remember_me": "on",
            },
            HTTP_HOST=_HOST,
        )
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_rate_limit_still_enforced_after_repeated_failed_email_logins(self):
        for _ in range(10):
            self.client.post(
                "/login/",
                {"email": "owner@rastisi-platform.example", "password": "wrong-password"},
                HTTP_HOST=_HOST,
            )
        response = self.client.post(
            "/login/",
            {"email": "owner@rastisi-platform.example", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "تعداد تلاش ورود بیش از حد مجاز است")

    def test_platform_staff_validation_still_enforced_for_email_login(self):
        User.objects.create_user(
            username="notplatformstaff", email="notstaff@rastisi-platform.example",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=False,
        )
        response = self.client.post(
            "/login/",
            {"email": "notstaff@rastisi-platform.example", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_email_login_is_audited(self):
        self.client.post(
            "/login/",
            {"email": "owner@rastisi-platform.example", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        entry = PlatformAuditLogEntry.objects.get(action_code="platform_admin.login_succeeded")
        self.assertEqual(entry.actor, self.staff_superuser)
        self.assertEqual(entry.result, PlatformAuditLogEntry.ResultStatus.SUCCESS)

    def test_failed_email_login_is_audited(self):
        self.client.post(
            "/login/",
            {"email": "owner@rastisi-platform.example", "password": "wrong-password"},
            HTTP_HOST=_HOST,
        )
        entry = PlatformAuditLogEntry.objects.get(action_code="platform_admin.login_failed")
        self.assertEqual(entry.result, PlatformAuditLogEntry.ResultStatus.FAILURE)
        self.assertEqual(entry.object_label, "owner@rastisi-platform.example")

    def test_failed_login_for_unknown_email_is_audited_without_a_user(self):
        self.client.post(
            "/login/", {"email": "no-such-user@example.com", "password": "whatever"}, HTTP_HOST=_HOST,
        )
        entry = PlatformAuditLogEntry.objects.get(action_code="platform_admin.login_failed")
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.object_label, "no-such-user@example.com")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminThreeIdentifierTests(TestCase):
    """Username/mobile/email are accepted without broadening admin access."""

    def setUp(self):
        from apps.portal.models import OwnerProfile

        cache.clear()
        self.admin = User.objects.create_user(
            username="platformroot", email="platformroot@example.com",
            password="StrongPass123!", is_staff=True, is_superuser=True,
        )
        OwnerProfile.objects.create(
            user=self.admin, full_name="Platform Root", phone="09129870001",
        )

    def _post(self, identifier):
        return self.client.post(
            "/login/",
            {"identifier": identifier, "password": "StrongPass123!"},
            HTTP_HOST=_HOST,
        )

    def test_form_renders_three_identifier_field(self):
        response = self.client.get("/login/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="identifier"')
        self.assertContains(response, "شماره موبایل، نام کاربری یا ایمیل")

    def test_username_login(self):
        self.assertEqual(self._post("PLATFORMROOT").status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)

    def test_mobile_login(self):
        self.assertEqual(self._post("09129870001").status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)

    def test_email_login(self):
        self.assertEqual(self._post("PLATFORMROOT@example.com").status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)

    def test_non_superuser_cannot_login_with_valid_username(self):
        User.objects.create_user(
            username="not_superuser", password="StrongPass123!", is_staff=True,
        )
        response = self._post("not_superuser")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
