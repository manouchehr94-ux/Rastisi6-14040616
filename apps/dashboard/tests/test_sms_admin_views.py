import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.sms.events import SmsEvent
from apps.sms.models import SmsBalance, SmsLog, SmsTemplate
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

SMS_HOST_A = f"sms-a.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
SMS_HOST_B = f"sms-b.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


class SmsAdminViewsTestCase(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()
        self.staff = User.objects.create_user(username="09121193001", password="pass12345", is_staff=True)
        store = Store.objects.get(slug="akhlaghi")
        StoreMembership.objects.create(
            store=store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        # این suite رفتار UI قدیمی را می‌سنجد، نه سیاست کمبود اعتبار؛ برای
        # مستقل‌ماندن تست‌ها از Credit Gate جدید، fixture اعتبار کافی دارد.
        SmsBalance.objects.update_or_create(store=store, defaults={"credits": 100})
        self.client.login(username="09121193001", password="pass12345")


class SettingsSmsConnectionViewTests(SmsAdminViewsTestCase):
    """پس از جداسازیِ زیرساختِ پیامک (Platform Owner panel)، این فرم فقط
    فعال‌سازی/خاموشی و انتخابِ «درگاهِ مرکزیِ پلتفرم در برابرِ دستگاهِ
    اسمس‌راستیِ خودم» را می‌پذیرد — نه ارائه‌دهنده/کلید/شماره‌ی فرستنده."""

    def test_valid_post_updates_shop_settings(self):
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_enabled": "on", "sms_backend": ShopSettings.SmsBackend.CONSOLE,
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")
        shop = ShopSettings.load()
        self.assertTrue(shop.sms_enabled)
        self.assertEqual(shop.sms_backend, ShopSettings.SmsBackend.CONSOLE)

    def test_can_opt_into_own_smsrasti_device(self):
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_enabled": "on", "sms_backend": ShopSettings.SmsBackend.SMSRASTI,
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")
        self.assertEqual(ShopSettings.load().sms_backend, ShopSettings.SmsBackend.SMSRASTI)

    def test_unchecked_box_disables_sms(self):
        self.client.post(reverse("dashboard:settings-sms-connection"), {
            "sms_backend": ShopSettings.SmsBackend.CONSOLE,
        })
        self.assertFalse(ShopSettings.load().sms_enabled)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(reverse("dashboard:settings-sms-connection"), {})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

    def test_provider_credential_fields_are_no_longer_shown_to_store_admins(self):
        """زیرساختِ پیامک (ارائه‌دهنده/کلید/شماره‌ی فرستنده) اکنون فقط از
        Platform Admin پیکربندی می‌شود — نباید هیچ فیلدِ ورودیِ آن‌ها در
        صفحه‌ی تنظیماتِ Store دیده شود."""
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertNotContains(response, 'name="melipayamak_username"')
        self.assertNotContains(response, 'name="melipayamak_password"')
        self.assertNotContains(response, 'name="kavenegar_api_key"')
        self.assertNotContains(response, 'name="sms_sender_number"')

    def test_sms_balance_is_shown(self):
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(response, "اعتبار پیامک")

    def test_active_packages_are_listed_for_purchase(self):
        from apps.sms.models import SmsPackage

        SmsPackage.objects.create(name="بسته‌ی تست", credit_amount=100, price=90_000, is_active=True)
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertContains(response, "بسته‌ی تست")

    def test_inactive_package_is_not_listed(self):
        from apps.sms.models import SmsPackage

        SmsPackage.objects.create(name="بسته‌ی غیرفعال", credit_amount=100, price=90_000, is_active=False)
        response = self.client.get(reverse("dashboard:settings") + "?section=sms")
        self.assertNotContains(response, "بسته‌ی غیرفعال")


class SmsPackagePurchaseViewTests(SmsAdminViewsTestCase):
    def setUp(self):
        super().setUp()
        from apps.sms.models import SmsPackage

        self.package = SmsPackage.objects.create(
            name="بسته‌ی استاندارد", credit_amount=500, price=400_000, is_active=True,
        )

    def test_purchase_creates_pending_request_and_does_not_grant_credit_yet(self):
        from apps.sms.models import SmsBalance, SmsPackagePurchase

        store = Store.objects.get(slug="akhlaghi")
        credits_before = SmsBalance.objects.get(store=store).credits

        from apps.billing.tests.platform_payment_support import cache
        from apps.billing.tests.test_platform_card_to_card import enable_platform_card

        enable_platform_card(self)                      # a purchase needs at least one ready platform payment method
        response = self.client.post(
            reverse("dashboard:settings-sms-package-purchase"), {"package_id": self.package.pk},
        )
        purchase = SmsPackagePurchase.objects.get(package=self.package)
        self.assertRedirects(response, f"/admin-portal/billing/checkout/sms/{purchase.pk}/", fetch_redirect_response=False)
        self.assertEqual(purchase.status, SmsPackagePurchase.Status.PENDING)
        self.assertEqual(purchase.credit_amount, 500)
        self.assertEqual(
            SmsBalance.objects.get(store=purchase.store).credits,
            credits_before,
            "درخواست خریدِ pending نباید موجودی فعلی Store را تغییر دهد",
        )

    def test_with_no_ready_payment_method_no_dead_purchase_is_created(self):
        from apps.sms.models import SmsPackagePurchase

        response = self.client.post(
            reverse("dashboard:settings-sms-package-purchase"), {"package_id": self.package.pk},
        )
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")
        self.assertFalse(SmsPackagePurchase.objects.filter(package=self.package).exists())

    def test_inactive_package_cannot_be_purchased(self):
        self.package.is_active = False
        self.package.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("dashboard:settings-sms-package-purchase"), {"package_id": self.package.pk},
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.post(
            reverse("dashboard:settings-sms-package-purchase"), {"package_id": self.package.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)


class SmsTemplateFormViewTests(SmsAdminViewsTestCase):
    def setUp(self):
        super().setUp()
        self.template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)

    def test_get_prefills_current_body(self):
        response = self.client.get(reverse("dashboard:sms-template-edit", args=[self.template.pk]))
        self.assertContains(response, self.template.body)
        self.assertContains(response, "customer_name")

    def test_valid_edit_updates_body(self):
        response = self.client.post(
            reverse("dashboard:sms-template-edit", args=[self.template.pk]),
            {"body": "{customer_name} سلام، متن تازه از {shop_name}"},
        )
        self.assertEqual(response.status_code, 200)
        self.template.refresh_from_db()
        self.assertIn("متن تازه", self.template.body)
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("modal-close", trigger)

    def test_unknown_variable_rejected_with_clear_error(self):
        response = self.client.post(
            reverse("dashboard:sms-template-edit", args=[self.template.pk]),
            {"body": "کد شما {otp_code} است"},
        )
        self.assertContains(response, "متغیر ناشناخته")
        self.template.refresh_from_db()
        self.assertNotIn("otp_code", self.template.body)

    def test_empty_body_rejected(self):
        original_body = self.template.body
        response = self.client.post(reverse("dashboard:sms-template-edit", args=[self.template.pk]), {"body": "  "})
        self.assertContains(response, "این فیلد لازم است")
        self.template.refresh_from_db()
        self.assertEqual(self.template.body, original_body)


class SmsTemplateToggleViewTests(SmsAdminViewsTestCase):
    def test_toggle_flips_is_active(self):
        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        self.assertTrue(template.is_active)
        response = self.client.post(reverse("dashboard:sms-template-toggle", args=[template.pk]))
        self.assertEqual(response.status_code, 204)
        template.refresh_from_db()
        self.assertFalse(template.is_active)

    def test_disabled_template_stops_sending(self):
        from apps.sms.services.sms_service import send_event_sms
        from apps.stores.models import Store

        template = SmsTemplate.objects.get(event_key=SmsEvent.WELCOME)
        self.client.post(reverse("dashboard:sms-template-toggle", args=[template.pk]))
        store = Store.objects.get(slug="akhlaghi")
        result = send_event_sms(SmsEvent.WELCOME, "09121234567", {"customer_name": "test"}, store=store)
        self.assertIsNone(result)


class SmsTestSendViewTests(SmsAdminViewsTestCase):
    def test_valid_phone_sends_and_redirects(self):
        response = self.client.post(reverse("dashboard:sms-test-send"), {
            "phone": "09121234567", "event_key": SmsEvent.WELCOME,
        })
        self.assertRedirects(response, "/admin-portal/settings/?section=sms")
        self.assertTrue(SmsLog.objects.filter(recipient="09121234567").exists())

    def test_invalid_phone_does_not_send(self):
        self.client.post(reverse("dashboard:sms-test-send"), {"phone": "123", "event_key": SmsEvent.WELCOME})
        self.assertFalse(SmsLog.objects.exists())


@override_settings(ALLOWED_HOSTS=[SMS_HOST_A, SMS_HOST_B, "testserver"])
class SmsLogListViewTests(SmsAdminViewsTestCase):
    """چون این تست‌ها یک Store دومی هم می‌سازند، حالتِ سازگاریِ تک-Storeِ
    resolve_compatibility_store دیگر معتبر نیست — همان الگویِ
    test_order_store_isolation.py (میزبانِ صریح + دامنه‌ی تأییدشده) استفاده
    می‌شود تا درخواست‌ها هنوز به Storeِ خودِ کارمند resolve شوند."""

    def setUp(self):
        super().setUp()
        self.store = Store.objects.get(slug="akhlaghi")
        _verified_domain(self.store, SMS_HOST_A)
        self.store.admin_subdomain = SMS_HOST_A.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        SmsLog.objects.create(
            store=self.store, event_key=SmsEvent.WELCOME, recipient="09121111111", message="پیام ۱",
            status=SmsLog.Status.SENT,
        )
        SmsLog.objects.create(
            store=self.store, event_key=SmsEvent.OTP, recipient="09122222222", message="پیام ۲",
            status=SmsLog.Status.FAILED, error_message="خطای اتصال",
        )

    def test_renders_all_logs(self):
        response = self.client.get(reverse("dashboard:sms-log-list"), HTTP_HOST=SMS_HOST_A)
        self.assertContains(response, "09121111111")
        self.assertContains(response, "09122222222")

    def test_filter_by_status(self):
        response = self.client.get(
            reverse("dashboard:sms-log-table"), {"status": SmsLog.Status.FAILED}, HTTP_HOST=SMS_HOST_A,
        )
        self.assertContains(response, "09122222222")
        self.assertNotContains(response, "09121111111")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:sms-log-list"), HTTP_HOST=SMS_HOST_A)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)

    def test_legacy_unattributed_log_is_never_shown(self):
        """ردیفِ store=NULL (پیش از افزودنِ این فیلد) نباید به هیچ داشبوردی نشان داده شود."""
        SmsLog.objects.create(
            store=None, event_key=SmsEvent.WELCOME, recipient="09123334444", message="لاگِ قدیمی بدونِ Store",
            status=SmsLog.Status.SENT,
        )
        response = self.client.get(reverse("dashboard:sms-log-list"), HTTP_HOST=SMS_HOST_A)
        self.assertNotContains(response, "09123334444")

    def test_cross_store_logs_are_never_visible(self):
        other_store = Store.objects.create(name="Store D", slug="store-d-log", status=Store.Status.ACTIVE)
        _verified_domain(other_store, SMS_HOST_B)
        other_store.admin_subdomain = SMS_HOST_B.split(".")[0]
        other_store.save(update_fields=["admin_subdomain"])
        SmsLog.objects.create(
            store=other_store, event_key=SmsEvent.WELCOME, recipient="09125556666",
            message="متعلق به فروشگاه دیگر", status=SmsLog.Status.SENT,
        )
        response = self.client.get(reverse("dashboard:sms-log-list"), HTTP_HOST=SMS_HOST_A)
        self.assertNotContains(response, "09125556666")

    def test_retry_resends_failed_log(self):
        # OTP قدیمی عمداً قابل Retry نیست؛ این تستِ UI باید یک پیام عادیِ
        # ناموفق را Retry کند و قرارداد امنیتی OTP را دور نزند.
        failed_log = SmsLog.objects.create(
            store=self.store,
            event_key=SmsEvent.WELCOME,
            recipient="09123335555",
            message="پیام عادی ناموفق برای Retry",
            status=SmsLog.Status.FAILED,
            error_message="خطای آزمایشی",
        )
        response = self.client.post(reverse("dashboard:sms-log-retry", args=[failed_log.pk]), HTTP_HOST=SMS_HOST_A)
        self.assertEqual(response.status_code, 302)
        failed_log.refresh_from_db()
        self.assertEqual(failed_log.status, SmsLog.Status.SENT)
        self.assertEqual(failed_log.attempt_count, 1)

    def test_retry_rejects_already_sent_log(self):
        sent_log = SmsLog.objects.get(status=SmsLog.Status.SENT)
        response = self.client.post(reverse("dashboard:sms-log-retry", args=[sent_log.pk]), HTTP_HOST=SMS_HOST_A)
        self.assertEqual(response.status_code, 302)
        sent_log.refresh_from_db()
        self.assertEqual(sent_log.attempt_count, 0)

    def test_cannot_retry_another_stores_log(self):
        other_store = Store.objects.create(name="Store E", slug="store-e-log", status=Store.Status.ACTIVE)
        _verified_domain(other_store, SMS_HOST_B)
        other_store.admin_subdomain = SMS_HOST_B.split(".")[0]
        other_store.save(update_fields=["admin_subdomain"])
        other_log = SmsLog.objects.create(
            store=other_store, event_key=SmsEvent.WELCOME, recipient="09127778888",
            message="متعلق به فروشگاه دیگر", status=SmsLog.Status.FAILED,
        )
        response = self.client.post(reverse("dashboard:sms-log-retry", args=[other_log.pk]), HTTP_HOST=SMS_HOST_A)
        self.assertEqual(response.status_code, 302)
        other_log.refresh_from_db()
        self.assertEqual(other_log.status, SmsLog.Status.FAILED)
        self.assertEqual(other_log.attempt_count, 0)


@override_settings(ALLOWED_HOSTS=[SMS_HOST_A, SMS_HOST_B, "testserver"])
class SmsOutboxListViewTests(SmsAdminViewsTestCase):
    def setUp(self):
        super().setUp()
        self.store = Store.objects.get(slug="akhlaghi")
        _verified_domain(self.store, SMS_HOST_A)
        self.store.admin_subdomain = SMS_HOST_A.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])

    def test_renders_own_stores_items_only(self):
        from apps.sms.models import SmsOutboxItem

        SmsOutboxItem.objects.create(store=self.store, phone="09121111111", message="آیتمِ خودم")
        other_store = Store.objects.create(name="Store F", slug="store-f-outbox", status=Store.Status.ACTIVE)
        _verified_domain(other_store, SMS_HOST_B)
        other_store.admin_subdomain = SMS_HOST_B.split(".")[0]
        other_store.save(update_fields=["admin_subdomain"])
        SmsOutboxItem.objects.create(store=other_store, phone="09129998888", message="آیتمِ فروشگاهِ دیگر")

        response = self.client.get(reverse("dashboard:sms-outbox-list"), HTTP_HOST=SMS_HOST_A)
        self.assertContains(response, "09121111111")
        self.assertNotContains(response, "09129998888")

    def test_retry_requeues_failed_item(self):
        from apps.sms.models import SmsOutboxItem

        item = SmsOutboxItem.objects.create(
            store=self.store, phone="09121111111", message="ناموفق",
            status=SmsOutboxItem.Status.FAILED, error_message="خطا",
        )
        response = self.client.post(reverse("dashboard:sms-outbox-retry", args=[item.pk]), HTTP_HOST=SMS_HOST_A)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, SmsOutboxItem.Status.PENDING)
        self.assertEqual(item.error_message, "")

    def test_anonymous_denied(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard:sms-outbox-list"), HTTP_HOST=SMS_HOST_A)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin-portal/login/", response.url)
        self.assertIn("admin_return=", response.url)