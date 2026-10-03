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


class AuditTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.shop = ShopSettings.load(store=self.store)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_non_real_backends_are_flagged_and_exit_nonzero(self):
        self.shop.sms_enabled, self.shop.sms_backend = True, ShopSettings.SmsBackend.CONSOLE
        self.shop.save()
        code, out = run("--store", self.store.slug)
        self.assertEqual(code, 1)
        self.assertIn("NOT REAL", out)
        self.assertIn("accepted by provider", out)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="smtp.example.com",
        EMAIL_HOST_USER="user", EMAIL_HOST_PASSWORD="S3CRET-PASSWORD", DEFAULT_FROM_EMAIL="no-reply@example.com",
        RASTISI_OWNER_SMS_BACKEND="kavenegar",
    )
    def test_configured_stack_passes_and_never_prints_secrets(self):
        self.shop.sms_enabled, self.shop.sms_backend = True, ShopSettings.SmsBackend.KAVENEGAR
        self.shop.kavenegar_api_key, self.shop.sms_sender_number = "KEY-SECRET-123", "1000"
        self.shop.save()
        from apps.sms.models import SmsBalance

        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 50})
        code, out = run("--store", self.store.slug)
        self.assertEqual(code, 0, out)
        for secret in ("S3CRET-PASSWORD", "KEY-SECRET-123", "user"):
            self.assertNotIn(secret, out.replace("EMAIL_HOST_USER", ""))
        self.assertIn("credits=50", out)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="")
    def test_missing_smtp_settings_and_provider_credentials_are_reported(self):
        self.shop.sms_enabled, self.shop.sms_backend = True, ShopSettings.SmsBackend.MELIPAYAMAK
        self.shop.melipayamak_username = self.shop.melipayamak_password = ""
        self.shop.save()
        code, out = run("--store", self.store.slug)
        self.assertEqual(code, 1)
        self.assertIn("EMAIL_HOST: MISSING", out)
        self.assertIn("credentials MISSING", out)


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
