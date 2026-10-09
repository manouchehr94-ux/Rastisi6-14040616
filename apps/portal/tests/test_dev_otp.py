"""Opt-in LOCAL-QA owner OTP (``RASTISI_DEV_OTP_CODE``) — DEVELOPMENT ONLY.

Proves the secure default is unchanged, that the explicit dev code works end-to-end through the
real views (register / login / password reset), that the raw code is never logged or stored, and
that production can neither start with it nor be tricked into fake console OTP delivery.
"""

import logging
import sys
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings

from apps.portal.models import OwnerOtpChallenge, OwnerProfile, PlatformConfiguration
from apps.portal.tests._owner_signup import age_otp_cooldown, complete_account
from apps.portal.services import owner_otp_service, owner_sms_service
from apps.sms.models import SmsLog
from apps.sms.services.backends import MelipayamakBackend, SmsSendResult, UnavailableBackend
from shop_core import checks
from shop_core.env_config import dev_otp_problems, resolve_allow_console_otp, resolve_dev_otp_code

User = get_user_model()
_HOST = "rastisi.localhost"
_CODE = "123456"
_PHONE = "09121230077"
_NAME = "کاربر آزمایشی"

#: what a developer's plain ``runserver`` looks like: no test flag, no dev code
_SECURE_DEFAULT = dict(RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False, RASTISI_DEV_OTP_CODE="", RASTISI_PRODUCTION_MODE=False)
_DEV = dict(RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False, RASTISI_DEV_OTP_CODE=_CODE, RASTISI_PRODUCTION_MODE=False)


class DevOtpSettingParsingTests(SimpleTestCase):
    NAME = "RASTISI_DEV_OTP_CODE"

    def test_empty_or_unset_is_disabled(self):
        for environ in ({}, {self.NAME: ""}, {self.NAME: "   "}):
            self.assertEqual(resolve_dev_otp_code(True, environ=environ), "")
            self.assertEqual(resolve_dev_otp_code(False, environ=environ), "")  # off is always fine

    def test_exactly_six_ascii_digits_is_accepted_in_debug(self):
        self.assertEqual(resolve_dev_otp_code(True, environ={self.NAME: "123456"}), "123456")
        self.assertEqual(resolve_dev_otp_code(True, environ={self.NAME: " 000000 "}), "000000")

    def test_malformed_values_fail_startup(self):
        for bad in ("12345", "1234567", "abcdef", "12345a", "12 456", "١٢٣٤٥٦", "۱۲۳۴۵۶", "+12345", "1.2345", "12\n456", "١23456"):
            with self.subTest(bad=bad), self.assertRaises(ImproperlyConfigured) as ctx:
                resolve_dev_otp_code(True, environ={self.NAME: bad})
            self.assertIn(self.NAME, str(ctx.exception))

    def test_any_value_with_debug_false_fails_startup_without_echoing_it(self):
        for value in ("123456", "000000", "bad"):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured) as ctx:
                resolve_dev_otp_code(False, environ={self.NAME: value})
            self.assertNotIn(value, str(ctx.exception))
            self.assertIn("DEVELOPMENT-ONLY", str(ctx.exception))

    def test_console_otp_flag_cannot_be_enabled_in_production(self):
        name = "RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP"
        with self.assertRaises(ImproperlyConfigured):
            resolve_allow_console_otp(False, running_tests=False, environ={name: "true"})
        self.assertFalse(resolve_allow_console_otp(False, running_tests=False, environ={}))
        self.assertTrue(resolve_allow_console_otp(True, running_tests=False, environ={name: "true"}))
        self.assertTrue(resolve_allow_console_otp(False, running_tests=True, environ={}))  # `manage.py test` compat
        self.assertFalse(resolve_allow_console_otp(True, running_tests=False, environ={}))  # plain runserver: OFF

    def test_system_check_rejects_the_dev_code_in_production_mode(self):
        with override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_DEV_OTP_CODE=_CODE):
            self.assertEqual([e.id for e in checks.check_dev_otp(None)], ["rastisi.E006"])
        with override_settings(RASTISI_PRODUCTION_MODE=False, RASTISI_DEV_OTP_CODE=_CODE):
            self.assertEqual(checks.check_dev_otp(None), [])
        with override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_DEV_OTP_CODE=""):
            self.assertEqual(checks.check_dev_otp(None), [])

    def test_console_flag_in_production_is_a_problem_unless_running_tests(self):
        self.assertTrue(dev_otp_problems(dev_otp_code="", allow_console_otp=True, production=True))
        self.assertFalse(dev_otp_problems(dev_otp_code="", allow_console_otp=True, production=True, running_tests=True))
        self.assertFalse(dev_otp_problems(dev_otp_code="", allow_console_otp=True, production=False))

    def test_default_test_configuration_has_no_dev_code(self):
        from django.conf import settings
        self.assertEqual(settings.RASTISI_DEV_OTP_CODE, "")


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **_SECURE_DEFAULT)
class SecureDefaultTests(TestCase):
    """A plain ``runserver`` (no env var): console OTP must NOT be treated as delivered."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_console_otp_is_not_reported_as_delivered(self):
        result = owner_sms_service.send_platform_otp(to=_PHONE, code="654321")
        self.assertFalse(result.success)
        self.assertFalse(owner_sms_service.otp_delivery_available())
        self.assertEqual(owner_sms_service.dev_otp_code(), "")
        self.assertEqual(owner_sms_service.dev_otp_code_for_console_provider(), "")

    def test_registration_does_not_proceed_and_leaves_no_challenge(self):
        user_count = User.objects.count()
        response = self.client.post("/register/", {"full_name": _NAME, "phone": _PHONE, "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("portal_otp_phone", self.client.session)
        self.assertFalse(OwnerOtpChallenge.objects.filter(phone=_PHONE, consumed_at__isnull=True).exclude(
            expires_at=owner_otp_service.PENDING_EXPIRES_AT).exists())
        self.assertEqual(User.objects.count(), user_count)

    def test_the_random_generator_is_used(self):
        with patch("apps.portal.services.owner_otp_service.secrets.randbelow", return_value=42):
            self.assertEqual(owner_otp_service._generate_code(), "000042")

    def test_non_otp_console_sms_is_still_unavailable(self):
        backend = owner_sms_service.get_platform_sms_backend()
        self.assertIsInstance(backend, UnavailableBackend)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], **_DEV)
class ExplicitDevCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_delivery_is_simulated_only_for_owner_otp_and_only_with_the_code(self):
        self.assertTrue(owner_sms_service.otp_delivery_available())
        result = owner_sms_service.send_platform_otp(to=_PHONE, code=_CODE)
        self.assertTrue(result.success)
        self.assertEqual(owner_sms_service.dev_otp_code_for_console_provider(), _CODE)
        # the generic platform SMS path is NOT made successful by the dev code
        self.assertIsInstance(owner_sms_service.get_platform_sms_backend(), UnavailableBackend)
        self.assertFalse(owner_sms_service.send_platform_sms(to=_PHONE, text="hello").success)

    def test_challenge_uses_the_configured_code_and_is_stored_hashed(self):
        owner_otp_service.request_otp(phone=_PHONE, purpose="login", client_ip="1.1.1.1")
        row = OwnerOtpChallenge.objects.get(phone=_PHONE)
        self.assertNotEqual(row.code_hash, _CODE)
        self.assertNotIn(_CODE, row.code_hash)
        self.assertTrue(row.code_hash.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))
        self.assertIs(owner_otp_service.check_otp(phone=_PHONE, purpose="login", code="000000"), owner_otp_service.OtpCheckResult.INVALID)
        self.assertIs(owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=_CODE), owner_otp_service.OtpCheckResult.OK)
        self.assertIs(owner_otp_service.check_otp(phone=_PHONE, purpose="login", code=_CODE), owner_otp_service.OtpCheckResult.EXPIRED)  # single use

    def test_the_raw_code_is_in_no_log_record_and_no_sms_log_row(self):
        with self.assertLogs(level=logging.DEBUG) as captured:
            logging.getLogger("probe").debug("probe")  # assertLogs needs at least one record
            owner_otp_service.request_otp(phone=_PHONE, purpose="register", client_ip="1.1.1.2")
            owner_otp_service.check_otp(phone=_PHONE, purpose="register", code=_CODE)
            owner_otp_service.check_otp(phone=_PHONE, purpose="register", code="999999")
        self.assertFalse([line for line in captured.output if _CODE in line], captured.output)
        self.assertTrue(SmsLog.objects.filter(recipient=_PHONE).exists())
        for row in SmsLog.objects.all():
            self.assertNotIn(_CODE, f"{row.message} {row.error_message}")

    def test_register_login_and_reset_work_through_the_real_views(self):
        client = self.client
        # 1. register with name + mobile, verify with the configured code
        response = client.post("/register/", {"full_name": _NAME, "phone": _PHONE, "accept_terms": "1"}, HTTP_HOST=_HOST)
        self.assertEqual(response["Location"], "/verify/")
        verified = client.post("/verify/", {"code": _CODE}, HTTP_HOST=_HOST)
        self.assertEqual(verified["Location"], "/signup/complete/")
        done = complete_account(client, phone=_PHONE)
        self.assertIn("/onboarding/", done["Location"])
        self.assertTrue(OwnerProfile.objects.filter(phone=_PHONE).exists())
        client.post("/logout/", HTTP_HOST=_HOST)
        # 2. login with OTP using the same code
        self.assertEqual(client.post("/login/", {"phone": _PHONE}, HTTP_HOST=_HOST)["Location"], "/verify/")
        self.assertEqual(client.post("/verify/", {"code": _CODE}, HTTP_HOST=_HOST)["Location"], "/app/")
        client.post("/logout/", HTTP_HOST=_HOST)
        # 3. resend works in the same mode (once the server-side resend cooldown has elapsed)
        client.post("/login/", {"phone": _PHONE}, HTTP_HOST=_HOST)
        age_otp_cooldown(_PHONE)
        client.post("/verify/resend/", HTTP_HOST=_HOST)
        self.assertContains(client.get("/verify/", HTTP_HOST=_HOST), "کد جدید ارسال شد")
        client.post("/logout/", HTTP_HOST=_HOST)
        cache.clear()
        # 4. password reset by mobile, same code, then phone + password login
        self.assertEqual(client.post("/reset-password/", {"phone": _PHONE}, HTTP_HOST=_HOST)["Location"], "/verify/")
        self.assertEqual(client.post("/verify/", {"code": _CODE}, HTTP_HOST=_HOST)["Location"], "/reset-password/new/")
        new = "my-real-local-password-8"
        self.assertEqual(
            client.post("/reset-password/new/", {"password": new, "password_confirm": new}, HTTP_HOST=_HOST)["Location"],
            "/login/",
        )
        cache.clear()
        login = client.post("/login/password/", {"identifier": _PHONE, "password": new}, HTTP_HOST=_HOST)
        self.assertEqual(login["Location"], "/app/")

    def test_a_real_provider_is_never_replaced_by_the_dev_mechanism(self):
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.sms_backend = "melipayamak"
        config.save()
        cache.clear()
        self.assertEqual(owner_sms_service.dev_otp_code_for_console_provider(), "")
        with patch("apps.portal.services.owner_otp_service.secrets.randbelow", return_value=7):
            self.assertEqual(owner_otp_service._generate_code(), "000007")  # random, NOT the dev code
        with patch.object(
            MelipayamakBackend, "send_pattern", return_value=SmsSendResult(success=True, provider_ref_id="real"),
        ) as pattern:
            result = owner_sms_service.send_platform_otp(to=_PHONE, code="000007")
        pattern.assert_called_once()  # the real provider path ran…
        self.assertEqual(pattern.call_args.kwargs["variables"]["otp_code"], "000007")  # …with the random code
        self.assertEqual(result.provider_ref_id, "real")
        self.assertEqual(result.provider, "melipayamak")

    def test_provider_failure_with_a_real_provider_is_not_masked_by_the_dev_code(self):
        config, _ = PlatformConfiguration.objects.get_or_create(pk=1)
        config.sms_backend = "kavenegar"
        config.save()
        cache.clear()
        result = owner_sms_service.send_platform_otp(to=_PHONE, code=_CODE)  # no credentials configured
        self.assertFalse(result.success)


class ProductionNeverHonoursTheDevCodeTests(TestCase):
    @override_settings(RASTISI_PRODUCTION_MODE=True, RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False, RASTISI_DEV_OTP_CODE=_CODE)
    def test_runtime_backstop_ignores_the_setting_and_delivery_stays_unavailable(self):
        cache.clear()
        with self.assertLogs("apps.portal.services.owner_sms_service", level="ERROR"):
            self.assertEqual(owner_sms_service.dev_otp_code(), "")
        self.assertFalse(owner_sms_service.otp_delivery_available())
        self.assertFalse(owner_sms_service.send_platform_otp(to=_PHONE, code=_CODE).success)
        self.assertNotEqual(owner_otp_service._generate_code(), "")
        with patch("apps.portal.services.owner_otp_service.secrets.randbelow", return_value=5):
            self.assertEqual(owner_otp_service._generate_code(), "000005")
