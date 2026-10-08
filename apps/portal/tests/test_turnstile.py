from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.portal.models import ContactMessage, OwnerOtpChallenge
from apps.portal.services import owner_auth_service, turnstile_service

User = get_user_model()
_HOST = "rastisi.localhost"

_ENABLED = dict(
    TURNSTILE_ENABLED=True,
    TURNSTILE_SITE_KEY="1x00000000000000000000AA",
    TURNSTILE_SECRET_KEY="1x0000000000000000000000000000000AA",
    TURNSTILE_EXPECTED_HOSTNAMES=(_HOST,),
    TURNSTILE_VERIFY_TIMEOUT_SECONDS=5,
    ALLOWED_HOSTS=[_HOST, "testserver"],
)


class TurnstileServiceTests(TestCase):
    def _response(self, payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    @override_settings(TURNSTILE_ENABLED=False)
    def test_disabled_mode_skips_external_validation(self):
        with patch("apps.portal.services.turnstile_service.requests.post") as post:
            result = turnstile_service.verify_token(
                token="", expected_action="register"
            )
        self.assertTrue(result.success)
        self.assertTrue(result.skipped)
        post.assert_not_called()

    @override_settings(**_ENABLED)
    def test_missing_token_fails_closed(self):
        result = turnstile_service.verify_token(
            token="", expected_action="register"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "missing-token")

    @override_settings(**_ENABLED)
    def test_success_requires_matching_action_and_hostname(self):
        with patch(
            "apps.portal.services.turnstile_service.requests.post",
            return_value=self._response({
                "success": True,
                "hostname": _HOST,
                "action": "register",
                "error-codes": [],
            }),
        ) as post:
            result = turnstile_service.verify_token(
                token="dummy-token",
                remote_ip="1.2.3.4",
                expected_action="register",
            )
        self.assertTrue(result.success)
        self.assertEqual(post.call_args.kwargs["timeout"], 5)
        self.assertEqual(
            post.call_args.kwargs["data"]["secret"],
            _ENABLED["TURNSTILE_SECRET_KEY"],
        )

    @override_settings(**_ENABLED)
    def test_action_mismatch_fails_closed(self):
        with patch(
            "apps.portal.services.turnstile_service.requests.post",
            return_value=self._response({
                "success": True,
                "hostname": _HOST,
                "action": "wrong_action",
            }),
        ):
            result = turnstile_service.verify_token(
                token="dummy-token", expected_action="register"
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "action-mismatch")

    @override_settings(**_ENABLED)
    def test_hostname_mismatch_fails_closed(self):
        with patch(
            "apps.portal.services.turnstile_service.requests.post",
            return_value=self._response({
                "success": True,
                "hostname": "evil.example",
                "action": "register",
            }),
        ):
            result = turnstile_service.verify_token(
                token="dummy-token", expected_action="register"
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "hostname-mismatch")

    @override_settings(**_ENABLED)
    def test_siteverify_network_failure_fails_closed(self):
        with patch(
            "apps.portal.services.turnstile_service.requests.post",
            side_effect=requests.Timeout("timeout"),
        ):
            result = turnstile_service.verify_token(
                token="dummy-token", expected_action="register"
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "siteverify-unavailable")

    @override_settings(**_ENABLED)
    def test_overlong_token_is_rejected_without_network(self):
        with patch("apps.portal.services.turnstile_service.requests.post") as post:
            result = turnstile_service.verify_token(
                token="x" * 2049, expected_action="register"
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "token-too-long")
        post.assert_not_called()


@override_settings(**_ENABLED)
class ProtectedPublicFormsTests(TestCase):
    def _deny(self):
        return patch(
            "apps.portal.services.turnstile_service.verify_request",
            return_value=turnstile_service.TurnstileValidationResult(
                success=False, error_code="verification-failed"
            ),
        )

    def test_register_renders_widget_when_enabled(self):
        response = self.client.get("/register/", HTTP_HOST=_HOST)
        self.assertContains(response, "cf-turnstile")
        self.assertContains(response, 'data-action="register"')
        self.assertContains(response, _ENABLED["TURNSTILE_SITE_KEY"])

    def test_registration_is_blocked_when_turnstile_fails(self):
        with self._deny():
            response = self.client.post(
                "/register/",
                {"full_name": "Bot Owner", "phone": "09121230001", "accept_terms": "1"},
                HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        self.assertFalse(
            OwnerOtpChallenge.objects.filter(phone="09121230001").exists()
        )

    def test_otp_login_request_is_blocked_when_turnstile_fails(self):
        with self._deny():
            response = self.client.post(
                "/login/", {"phone": "09121230002"}, HTTP_HOST=_HOST
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
        self.assertFalse(
            OwnerOtpChallenge.objects.filter(phone="09121230002").exists()
        )

    def test_password_login_is_blocked_when_turnstile_fails(self):
        owner_auth_service.register_owner(
            full_name="Protected Login",
            email="protected-login@example.com",
            password="a-very-strong-pass-1",
        )
        with self._deny():
            response = self.client.post(
                "/login/password/",
                {
                    "identifier": "protected-login@example.com",
                    "password": "a-very-strong-pass-1",
                },
                HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_legacy_email_registration_route_only_redirects_and_never_creates_anything(self):
        # Anonymous email registration was removed: the route is a redirect, so
        # there is nothing left for Turnstile to guard (and nothing is created).
        response = self.client.post(
            "/register-email/",
            {"full_name": "Bot Email", "email": "bot-email@example.com", "password": "a-very-strong-pass-1"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/register/")
        self.assertFalse(User.objects.filter(username="bot-email@example.com").exists())

    def test_password_reset_request_is_blocked_when_turnstile_fails(self):
        owner_auth_service.register_owner(
            full_name="Reset Protected",
            email="reset-protected@example.com",
            password="a-very-strong-pass-1",
        )
        with self._deny():
            response = self.client.post(
                "/reset-password/",
                {"email": "reset-protected@example.com"},
                HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_contact_is_blocked_when_turnstile_fails(self):
        with self._deny():
            response = self.client.post(
                "/contact/",
                {
                    "full_name": "Bot",
                    "email": "bot@example.com",
                    "subject": "spam",
                    "message": "automated spam message",
                },
                HTTP_HOST=_HOST,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, turnstile_service.PUBLIC_ERROR_MESSAGE)
