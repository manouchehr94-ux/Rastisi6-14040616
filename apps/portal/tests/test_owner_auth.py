from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.customers.models import Customer
from apps.portal.models import OwnerProfile
from apps.portal.services import owner_auth_service

User = get_user_model()

_HOST = "rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OwnerRegistrationTests(TestCase):
    def test_the_internal_service_creates_user_and_owner_profile_no_customer(self):
        # register_owner() is an internal service (fixtures/commands); the public
        # /register-email/ route no longer exists (see the hardening module).
        user = owner_auth_service.register_owner(
            full_name="Sara Ahmadi", email="Sara@Example.com", password="a-very-strong-pass-1",
        )
        self.assertEqual(user.username, "sara@example.com")
        self.assertTrue(OwnerProfile.objects.filter(user=user).exists())
        self.assertFalse(Customer.objects.filter(user=user).exists())
        self.assertFalse(user.is_staff)

    def test_register_rejects_duplicate_email_case_insensitively(self):
        owner_auth_service.register_owner(full_name="A", email="dup@example.com", password="a-very-strong-pass-1")
        with self.assertRaises(owner_auth_service.OwnerAuthError):
            owner_auth_service.register_owner(full_name="B", email="DUP@Example.com", password="another-strong-pass-2")

    def test_register_enforces_password_validation(self):
        with self.assertRaises(owner_auth_service.OwnerAuthError):
            owner_auth_service.register_owner(full_name="A", email="weak@example.com", password="123")

    def test_owner_registration_never_creates_a_customer_profile(self):
        owner_auth_service.register_owner(full_name="A", email="owneronly@example.com", password="a-very-strong-pass-1")
        user = User.objects.get(username="owneronly@example.com")
        self.assertFalse(hasattr(user, "customer_profile"))


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class OwnerLoginLogoutTests(TestCase):
    """HTTP-level tests for the canonical unified login's password form
    (POSTs to /login/password/ — /login-email/ is now a bare redirect to
    /login/, see LoginEmailRedirectTests below)."""

    def setUp(self):
        self.user = owner_auth_service.register_owner(
            full_name="Login Test", email="login@example.com", password="a-very-strong-pass-1",
        )

    def test_login_with_correct_credentials_succeeds(self):
        response = self.client.post(
            "/login/password/", {"identifier": "login@example.com", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_is_case_insensitive_on_email(self):
        response = self.client.post(
            "/login/password/", {"identifier": "LOGIN@Example.com", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(response.status_code, 302)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            "/login/password/", {"identifier": "login@example.com", "password": "wrong-password"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, owner_auth_service.GENERIC_LOGIN_ERROR)

    def test_login_error_message_is_generic_and_never_mentions_email_specifically(self):
        response = self.client.post(
            "/login/password/", {"identifier": "nobody-registered@example.com", "password": "whatever-guess"},
            HTTP_HOST=_HOST,
        )
        self.assertContains(response, owner_auth_service.GENERIC_LOGIN_ERROR)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        response = self.client.get("/logout/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 405)

    def test_logout_via_post_clears_session(self):
        self.client.force_login(self.user)
        response = self.client.post("/logout/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_redirect_never_follows_external_next(self):
        response = self.client.post(
            "/login/password/",
            {
                "identifier": "login@example.com", "password": "a-very-strong-pass-1",
                "next": "https://evil.example.com/",
            },
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response["Location"])


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class LoginEmailRedirectTests(TestCase):
    """/login-email/ is kept only so old bookmarked links don't 404 — it
    always redirects to the unified /login/ page, preserving query params."""

    def test_get_redirects_to_unified_login(self):
        response = self.client.get("/login-email/", HTTP_HOST=_HOST)
        self.assertRedirects(response, "/login/")

    def test_next_param_is_preserved_across_the_redirect(self):
        response = self.client.get("/login-email/?next=/app/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?next=", response["Location"])

    def test_post_to_login_email_also_redirects_rather_than_authenticating(self):
        owner_auth_service.register_owner(
            full_name="Post Redirect", email="postredirect@example.com", password="a-very-strong-pass-1",
        )
        response = self.client.post(
            "/login-email/", {"email": "postredirect@example.com", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class AuthenticateOwnerByIdentifierTests(TestCase):
    """Canonical email-or-phone + password authentication service —
    unifies what used to be two separate login views (Section 8/9's
    consolidation slice)."""

    def setUp(self):
        self.email_owner = owner_auth_service.register_owner(
            full_name="Email Owner", email="unified@example.com", password="a-very-strong-pass-1",
        )
        self.phone_owner, _created = owner_auth_service.get_or_create_owner_by_phone(
            phone="09121234567", full_name="Phone Owner",
        )
        self.phone_owner.set_password("phone-owner-pass-1")
        self.phone_owner.save(update_fields=["password"])

    def test_authenticates_by_email(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="unified@example.com", password="a-very-strong-pass-1",
        )
        self.assertEqual(user, self.email_owner)

    def test_email_lookup_is_case_insensitive(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="UNIFIED@Example.com", password="a-very-strong-pass-1",
        )
        self.assertEqual(user, self.email_owner)

    def test_authenticates_by_phone_local_format(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="09121234567", password="phone-owner-pass-1",
        )
        self.assertEqual(user, self.phone_owner)

    def test_authenticates_by_phone_international_format(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="+989121234567", password="phone-owner-pass-1",
        )
        self.assertEqual(user, self.phone_owner)

    def test_wrong_password_returns_none(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="unified@example.com", password="totally-wrong",
        )
        self.assertIsNone(user)

    def test_nonexistent_email_returns_none(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="nobody@example.com", password="anything-at-all",
        )
        self.assertIsNone(user)

    def test_nonexistent_phone_returns_none(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="09129999999", password="anything-at-all",
        )
        self.assertIsNone(user)

    def test_malformed_phone_returns_none_not_exception(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="not-a-phone-or-email", password="anything-at-all",
        )
        self.assertIsNone(user)

    def test_inactive_user_cannot_authenticate(self):
        self.email_owner.is_active = False
        self.email_owner.save(update_fields=["is_active"])
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="unified@example.com", password="a-very-strong-pass-1",
        )
        self.assertIsNone(user)

    def test_phone_owner_with_unusable_password_cannot_use_password_login(self):
        """Owners created via phone+OTP registration (the primary flow) get
        set_unusable_password() — logging in with any password must fail
        safely, never crash, never leak that the account exists."""
        otp_owner, _created = owner_auth_service.get_or_create_owner_by_phone(
            phone="09120001111", full_name="OTP Only Owner",
        )
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="09120001111", password="anything-guessed",
        )
        self.assertIsNone(user)

    def test_a_pure_customer_account_sharing_the_phone_is_never_returned_as_owner(self):
        """apps.customers also uses User.username = phone; a phone that only
        has a Customer (no OwnerProfile) must never authenticate as an
        owner via this service."""
        customer_user = User.objects.create_user(username="09127654321", password="customer-pass-1")
        Customer.objects.create(user=customer_user, full_name="Pure Customer", phone="09127654321")
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="09127654321", password="customer-pass-1",
        )
        self.assertIsNone(user)

    def test_empty_identifier_returns_none(self):
        user = owner_auth_service.authenticate_owner_by_identifier(None, identifier="", password="whatever")
        self.assertIsNone(user)

    def test_empty_password_returns_none(self):
        user = owner_auth_service.authenticate_owner_by_identifier(
            None, identifier="unified@example.com", password="",
        )
        self.assertIsNone(user)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()  # the per-email reset throttle lives in the cache
        self.user = owner_auth_service.register_owner(
            full_name="Reset Test", email="reset@example.com", password="a-very-strong-pass-1",
        )

    def test_request_for_unknown_email_does_not_error_or_reveal_existence(self):
        response = self.client.post("/reset-password/", {"email": "nobody@example.com"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_for_known_email_sends_mail(self):
        response = self.client.post("/reset-password/", {"email": "reset@example.com"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset@example.com", mail.outbox[0].to)

    def test_full_reset_flow_changes_password(self):
        owner_auth_service.request_password_reset(email="reset@example.com", base_url="https://rastisi.ir")
        body = mail.outbox[0].body
        # extract "/reset-password/<uidb64>/<token>/" from the rendered email body
        path = body.split("https://rastisi.ir", 1)[1].split()[0].strip()
        response = self.client.get(path, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            path, {"password": "brand-new-strong-pass-9", "password_confirm": "brand-new-strong-pass-9"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-strong-pass-9"))

    def test_weak_new_password_returns_form_error_instead_of_500(self):
        owner_auth_service.request_password_reset(
            email="reset@example.com", base_url="https://rastisi.ir"
        )
        path = mail.outbox[0].body.split("https://rastisi.ir", 1)[1].split()[0].strip()

        response = self.client.post(
            path,
            {"password": "123", "password_confirm": "123"},
            HTTP_HOST=_HOST,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "p-error")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a-very-strong-pass-1"))

    def test_reused_reset_token_is_rejected(self):
        owner_auth_service.request_password_reset(email="reset@example.com", base_url="https://rastisi.ir")
        path = mail.outbox[0].body.split("https://rastisi.ir", 1)[1].split()[0].strip()
        self.client.post(
            path, {"password": "brand-new-strong-pass-9", "password_confirm": "brand-new-strong-pass-9"},
            HTTP_HOST=_HOST,
        )
        # Token is bound to the password hash (Django's default_token_generator);
        # once the password changed, the same link must no longer work.
        response = self.client.get(path, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 400)
