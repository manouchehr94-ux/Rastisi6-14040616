from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.portal.models import OwnerOtpChallenge
from apps.portal.services import owner_otp_service
from apps.portal.services.owner_sms_service import send_platform_otp
from apps.sms.services.backends import KavenegarBackend, MelipayamakBackend, SmsSendResult


class ProviderNativeOtpTests(TestCase):
    @patch("requests.post")
    def test_melipayamak_pattern_payload_uses_body_id_and_order(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"RetStatus": 1, "Value": "MP-1"}
        post.return_value = response
        backend = MelipayamakBackend(username="user", password="pass", sender="")
        result = backend.send_pattern(
            to="09121234567",
            body_id="12345",
            variables={"otp_code": "654321", "expire_minutes": "2"},
            variables_order="otp_code,expire_minutes",
        )
        self.assertTrue(result.success)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["bodyId"], 12345)
        self.assertEqual(payload["text"], "654321;2")
        self.assertNotIn("from", payload)

    @patch("requests.post")
    def test_kavenegar_verify_lookup_does_not_require_sender(self, post):
        response = Mock()
        response.json.return_value = {
            "return": {"status": 200, "message": "ok"},
            "entries": [{"messageid": 42}],
        }
        post.return_value = response
        backend = KavenegarBackend(api_key="api-key", sender="")
        result = backend.send_verify_lookup(
            to="09121234567", token="654321", template="RastisiOtp",
        )
        self.assertTrue(result.success)
        payload = post.call_args.kwargs["data"]
        self.assertEqual(payload["token"], "654321")
        self.assertEqual(payload["template"], "RastisiOtp")
        self.assertNotIn("sender", payload)


class PlatformOtpRoutingTests(TestCase):
    def setUp(self):
        cache.clear()
        from apps.portal.services.platform_config_service import get_platform_configuration
        self.config = get_platform_configuration()

    @patch(
        "apps.portal.services.owner_sms_service.MelipayamakBackend.send_pattern",
        return_value=SmsSendResult(success=True, provider_ref_id="meli-1"),
    )
    def test_melipayamak_is_primary_pattern_route(self, send_pattern):
        self.config.sms_backend = "melipayamak"
        self.config.set_sms_credentials(
            melipayamak_username="u",
            melipayamak_password="p",
            melipayamak_otp_body_id="9988",
            melipayamak_otp_variables_order="otp_code",
            otp_fallback_enabled="0",
        )
        self.config.save()
        cache.clear()
        result = send_platform_otp(
            to="09121234567", code="123456", purpose="register",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.provider_ref_id, "meli-1")
        self.assertEqual(send_pattern.call_args.kwargs["body_id"], "9988")

    @patch(
        "apps.portal.services.owner_sms_service.KavenegarBackend.send_verify_lookup",
        return_value=SmsSendResult(success=True, provider_ref_id="kav-1"),
    )
    @patch(
        "apps.portal.services.owner_sms_service.MelipayamakBackend.send_pattern",
        return_value=SmsSendResult(success=False, error_message="meli down"),
    )
    def test_kavenegar_is_used_only_after_melipayamak_failure(self, meli, kaveh):
        self.config.sms_backend = "melipayamak"
        self.config.set_sms_credentials(
            melipayamak_username="u",
            melipayamak_password="p",
            melipayamak_otp_body_id="9988",
            otp_fallback_enabled="1",
            kavenegar_api_key="key",
            kavenegar_otp_template="RastisiOtp",
        )
        self.config.save()
        cache.clear()
        result = send_platform_otp(
            to="09121234567", code="123456", purpose="register",
        )
        self.assertTrue(result.success)
        meli.assert_called_once()
        kaveh.assert_called_once()

    @override_settings(
        RASTISI_OWNER_SMS_BACKEND="console",
        RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False,
    )
    def test_console_route_fails_closed(self):
        self.config.sms_backend = "console"
        self.config.save()
        cache.clear()
        result = send_platform_otp(
            to="09121234567", code="123456", purpose="register",
        )
        self.assertFalse(result.success)


class OwnerOtpDeliveryInvariantTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch(
        "apps.portal.services.owner_otp_service.send_platform_otp",
        return_value=SmsSendResult(success=False, error_message="provider down"),
    )
    def test_failed_delivery_leaves_no_verifiable_challenge(self, _send):
        with self.assertRaises(owner_otp_service.OtpDeliveryError):
            owner_otp_service.request_otp(
                phone="09121234567",
                purpose="register",
                client_ip="1.2.3.4",
            )
        # The accepted request keeps only the never-verifiable pending marker (it holds the 120 s resend cooldown).
        rows = OwnerOtpChallenge.objects.filter(phone="09121234567")
        self.assertFalse(
            rows.exclude(expires_at=owner_otp_service.PENDING_EXPIRES_AT).exists()
        )
        self.assertFalse(
            owner_otp_service.verify_otp(phone="09121234567", purpose="register", code="000000")
        )

    @patch(
        "apps.portal.services.owner_otp_service.send_platform_otp",
        return_value=SmsSendResult(success=True, provider_ref_id="provider-1"),
    )
    def test_successful_delivery_keeps_hashed_challenge(self, _send):
        owner_otp_service.request_otp(
            phone="09121234568",
            purpose="register",
            client_ip="1.2.3.4",
        )
        challenge = OwnerOtpChallenge.objects.get(phone="09121234568")
        self.assertTrue(challenge.is_usable)


@override_settings(ALLOWED_HOSTS=["platformadmins.rastisi.localhost", "testserver"])
class PlatformSmsSettingsOtpRouteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="sms-admin@example.com",
            email="sms-admin@example.com",
            password="strong-password-1",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)

    def test_platform_admin_saves_pattern_and_fallback_route(self):
        response = self.client.post(
            "/sms/settings/",
            {
                "sms_backend": "melipayamak",
                "sms_sender_number": "10001",
                "sms_melipayamak_username": "platform-user",
                "sms_melipayamak_password": "platform-pass",
                "sms_melipayamak_otp_body_id": "778899",
                "sms_melipayamak_otp_variables_order": "otp_code,expire_minutes",
                "sms_otp_fallback_enabled": "on",
                "sms_kavenegar_api_key": "kaveh-secret",
                "sms_kavenegar_otp_template": "RastisiOtp",
            },
            HTTP_HOST="platformadmins.rastisi.localhost",
        )
        self.assertEqual(response.status_code, 302)
        from apps.portal.services.platform_config_service import get_platform_configuration
        cache.clear()
        config = get_platform_configuration()
        creds = config.get_sms_credentials()
        self.assertEqual(creds["melipayamak_otp_body_id"], "778899")
        self.assertEqual(
            creds["melipayamak_otp_variables_order"],
            "otp_code,expire_minutes",
        )
        self.assertEqual(creds["otp_fallback_enabled"], "1")
        self.assertEqual(creds["kavenegar_otp_template"], "RastisiOtp")
        self.assertNotIn("platform-pass", config.encrypted_sms_credentials)
        self.assertNotIn("kaveh-secret", config.encrypted_sms_credentials)
