"""H4: ممیزیِ آمادگیِ کانال‌هایِ ارسال — بدونِ شبکه/افشایِ راز؛ ارسالِ آزمایشی فقط با تأییدِ صریح."""

from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.core.models import ShopSettings
from apps.stores.models import Store


def run(*args):
    out = StringIO()
    code = 0
    try:
        call_command("verify_delivery_channels", *args, stdout=out)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue()


def set_platform(provider="console", **credentials):
    from django.core.cache import cache

    from apps.portal.models import PlatformConfiguration
    from apps.portal.services.platform_config_service import get_platform_configuration

    config = get_platform_configuration()
    config.sms_backend = provider
    if credentials:
        config.set_sms_credentials(**credentials)
    config.save()
    cache.clear()
    return PlatformConfiguration.objects.get(pk=config.pk)


class AuditTests(TestCase):
    """verify_delivery_channels must report what the runtime really does: a store uses ONLY the phone (SmsRasti) or the
    platform gateway — never per-store provider credentials."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.shop = ShopSettings.load(store=self.store)
        self.shop.sms_enabled = True
        self.shop.save()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend", RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False)
    def test_platform_console_gateway_and_console_email_are_flagged_not_real(self):
        set_platform("console")
        code, out = run("--store", self.store.slug)
        self.assertEqual(code, 1)
        self.assertIn("NOT REAL", out)
        self.assertIn("method=platform", out)
        self.assertIn("accepted by provider", out)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="mailuser", EMAIL_HOST_PASSWORD="S3CRET-PASSWORD", DEFAULT_FROM_EMAIL="no-reply@example.com",
    )
    def test_platform_method_with_central_provider_passes_and_prints_no_secrets(self):
        set_platform("kavenegar", kavenegar_api_key="KEY-SECRET-123", kavenegar_sender="1000")
        from apps.sms.models import SmsBalance

        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 50})
        code, out = run("--store", self.store.slug)
        self.assertEqual(code, 0, out)
        self.assertIn("provider=kavenegar REAL", out)
        self.assertIn("credits=50", out)
        for secret in ("S3CRET-PASSWORD", "KEY-SECRET-123", "mailuser"):
            self.assertNotIn(secret, out)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="")
    def test_missing_smtp_and_incomplete_central_provider_are_reported_no_per_store_credentials_needed(self):
        set_platform("melipayamak")  # no credentials anywhere
        self.shop.melipayamak_username = self.shop.melipayamak_password = ""  # obsolete per-store fields: must be irrelevant
        self.shop.save()
        code, out = run("--store", self.store.slug)
        self.assertEqual(code, 1)
        self.assertIn("EMAIL_HOST: MISSING", out)
        self.assertIn("PLATFORM PROBLEM", out)
        self.assertNotIn("credentials MISSING", out)

    def test_store_legacy_provider_values_all_mean_platform(self):
        for legacy in (ShopSettings.SmsBackend.CONSOLE, ShopSettings.SmsBackend.MELIPAYAMAK, ShopSettings.SmsBackend.KAVENEGAR):
            self.shop.sms_backend = legacy
            self.shop.save()
            self.assertEqual(ShopSettings.load(store=self.store).sms_delivery_method, "platform")
            _, out = run("--store", self.store.slug)
            self.assertIn("method=platform", out)

    @override_settings(RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=True)
    def test_phone_method_reports_device_state_instead_of_provider_credentials(self):
        from datetime import timedelta

        from django.utils import timezone

        self.shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        self.shop.smsrasti_device_token = "tok-verify-1"
        self.shop.save()
        _, out = run("--store", self.store.slug)
        self.assertIn("method=phone", out)
        self.assertIn("device_paired=True device_online=False last_seen=never", out)
        ShopSettings.objects.filter(pk=self.shop.pk).update(smsrasti_last_seen_at=timezone.now() - timedelta(minutes=1))
        _, out = run("--store", self.store.slug)
        self.assertIn("device_online=True", out)
        self.assertNotIn("credits=", out)  # no platform credit is consumed by the phone method


class TestSendGuardTests(TestCase):
    def test_test_sends_require_explicit_confirmation(self):
        with self.assertRaises(CommandError):
            call_command("verify_delivery_channels", "--send-test-email", "qa@example.com", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_confirmed_test_email_uses_the_configured_transport_once(self):
        run("--send-test-email", "qa@example.com", "--confirm-test-recipient")
        self.assertEqual([m.to for m in mail.outbox], [["qa@example.com"]])

    def test_sms_test_requires_store(self):
        with self.assertRaises(CommandError):
            call_command("verify_delivery_channels", "--send-test-sms", "09120000000", "--confirm-test-recipient", stdout=StringIO())
