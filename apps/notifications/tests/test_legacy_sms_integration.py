"""S0 (تاریخچه‌ی یکپارچه) و S1 (مدیریتِ یکپارچه‌ی قالبِ پیامک) برایِ رویدادهایِ پیامکِ قدیمی."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.notifications import events as ev
from apps.notifications import legacy_sms
from apps.notifications.models import NotificationOutbox, NotificationTemplate
from apps.notifications.services import legacy_history, template_service as ts
from apps.notifications.services.notification_service import (
    RetryNotAllowed, deliver_pending, deliver_single, retry_notification,
)
from apps.sms.events import DEFAULT_TEMPLATES, EVENT_VARIABLES, SmsEvent
from apps.sms.models import SmsBalance, SmsLog, SmsTemplate
from apps.sms.services.sms_service import retry_failed_log, send_event_sms, send_raw_sms, send_test_sms
from apps.stores.models import Store

User = get_user_model()
LEGACY_EVENTS = [e for e in ev.EVENTS.values() if e.legacy_sms_event]


class AliasMapTests(TestCase):
    def test_every_legacy_event_has_a_complete_bijective_valid_alias_map(self):
        self.assertTrue(LEGACY_EVENTS)
        for event in LEGACY_EVENTS:
            legacy_vars = set(EVENT_VARIABLES[event.legacy_sms_event])
            mapping = legacy_sms.legacy_to_new_map(event.legacy_sms_event)
            self.assertEqual(set(mapping), legacy_vars, event.key)
            self.assertEqual(len(set(mapping.values())), len(mapping), f"not injective: {event.key}")
            self.assertLessEqual(set(mapping.values()), set(event.variables), f"target not in new vocabulary: {event.key}")
            # دوسویه: تبدیلِ رفت‌وبرگشتِ متنِ پیش‌فرض بدونِ تغییر
            default = DEFAULT_TEMPLATES[event.legacy_sms_event]
            self.assertEqual(legacy_sms.body_to_legacy(event.legacy_sms_event, legacy_sms.body_to_new(event.legacy_sms_event, default)), default)

    def test_unsupported_and_unsafe_new_variables_rejected(self):
        with self.assertRaises(legacy_sms.LegacyTemplateError):
            legacy_sms.body_to_legacy("order_placed", "{order_url}")  # در پیامکِ قدیمی معادل ندارد
        with self.assertRaises(legacy_sms.LegacyTemplateError):
            legacy_sms.body_to_legacy("order_placed", "{customer_name.__class__}")


class Base(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        SmsTemplate.ensure_defaults()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 1000})
        user = User.objects.create_user(username="09125550000", password="x12345678")
        self.customer = Customer.objects.create(user=user, full_name="سارا", phone="09125550000", email="s@example.com")


class UnifiedTemplateAdminTests(Base):
    def test_get_template_reads_the_real_sms_template_with_new_vocabulary(self):
        SmsTemplate.objects.filter(event_key="order_placed").update(body="{customer_name}: {order_code} / {amount} / {shop_name}", is_active=False)
        tpl = ts.get_template(self.store, "order.created", "sms")
        self.assertEqual(tpl["body"], "{customer_name}: {order_number} / {order_total} / {store_name}")
        self.assertFalse(tpl["enabled"])
        self.assertEqual(tpl["managed_by"], "legacy_sms")
        self.assertTrue(tpl["customized"])

    def test_non_legacy_event_unchanged(self):
        tpl = ts.get_template(self.store, "return.requested", "sms")
        self.assertNotIn("managed_by", tpl)

    def test_save_writes_smstemplate_in_legacy_vocabulary_and_drops_stale_row(self):
        NotificationTemplate.objects.create(store=self.store, event_key="order.created", channel="sms", body="قدیمیِ بی‌اثر")
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="",
                         body="سفارش {order_number} به {order_total} - {store_name}")
        row = SmsTemplate.objects.get(event_key="order_placed")
        self.assertEqual(row.body, "سفارش {order_code} به {amount} - {shop_name}")
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, event_key="order.created", channel="sms").exists())
        # و پیامکِ واقعی دقیقاً همین متن را می‌فرستد
        log = send_event_sms("order_placed", "09121234567", {"customer_name": "س", "order_code": "A1", "amount": "5"}, store=self.store)
        self.assertEqual(log.message, "سفارش A1 به 5 - " + ShopSettings.load(store=self.store).name)

    def test_save_rejects_unsupported_unsafe_and_leaves_template_untouched(self):
        before = SmsTemplate.objects.get(event_key="order_placed").body
        for bad in ["{order_url}", "{customer_name.__class__}", "{unknown}", "{x"]:
            with self.assertRaises(ts.TemplateError, msg=bad):
                ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body=bad)
        self.assertEqual(SmsTemplate.objects.get(event_key="order_placed").body, before)

    def test_enabled_flag_controls_real_delivery(self):
        ts.save_template(self.store, "order.created", "sms", enabled=False, subject="", body="")
        self.assertFalse(SmsTemplate.objects.get(event_key="order_placed").is_active)
        self.assertIsNone(send_event_sms("order_placed", "09121234567", {"customer_name": "س"}, store=self.store))

    def test_reset_restores_default_text(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="سفارش {order_number}")
        ts.reset_template(self.store, "order.created", "sms")
        self.assertEqual(SmsTemplate.objects.get(event_key="order_placed").body, DEFAULT_TEMPLATES["order_placed"])

    def test_preview_uses_legacy_rules_and_sample_data(self):
        result = ts.preview(self.store, "order.created", "sms", body="{{x}} {order_number}")
        self.assertEqual(result["body"], "{x} DM-12345")
        with self.assertRaises(ts.TemplateError):
            ts.preview(self.store, "order.created", "sms", body="{order_url}")


class LegacyHistoryMirrorTests(Base):
    def send(self, **ctx):
        return send_event_sms("order_placed", "09125550000",
                              {"customer_name": "سارا", "order_code": "X1", "amount": "100", **ctx}, store=self.store)

    def test_one_mirror_row_with_links_and_no_second_delivery(self):
        with patch("apps.sms.services.backends.ConsoleBackend.send") as send:
            send.return_value = type("R", (), {"success": True, "provider_ref_id": "r1", "error_message": "", "provider": "console"})()
            log = self.send()
            self.assertEqual(send.call_count, 1)
            rows = NotificationOutbox.objects.filter(sms_log=log)
            self.assertEqual(rows.count(), 1)
            row = rows.get()
            self.assertEqual((row.event_key, row.channel, row.status, row.store_id), ("order.created", "sms", "sent", self.store.pk))
            self.assertEqual((row.body, row.recipient_phone, row.provider_ref), (log.message, "09125550000", "r1"))
            self.assertEqual(row.customer_id, self.customer.pk)
            self.assertTrue(row.is_legacy_sms_mirror)
            self.assertEqual(row.metadata["legacy_sms_log_id"], log.pk)
            self.assertEqual(row.created_at, log.created_at)
            # کارگرِ outbox هیچ پیامکِ دومی نمی‌فرستد
            self.assertEqual(deliver_pending()["processed"], 0)
            self.assertEqual(deliver_single(row).status, "sent")
            self.assertEqual(send.call_count, 1)
            self.assertEqual(SmsLog.objects.count(), 1)

    def test_repeated_processing_creates_no_duplicates(self):
        log = self.send()
        for _ in range(3):
            legacy_history.record_legacy_sms(log)
        self.assertEqual(NotificationOutbox.objects.filter(dedupe_key=f"legacy_sms:{log.pk}").count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(sms_log=log).count(), 1)

    def test_failed_send_is_mirrored_as_dead_and_not_retried_by_outbox(self):
        with patch("apps.sms.services.backends.ConsoleBackend.send") as send:
            send.return_value = type("R", (), {"success": False, "provider_ref_id": "", "error_message": "قطعی 09125550000", "provider": "console"})()
            log = self.send()
            row = NotificationOutbox.objects.get(sms_log=log)
            self.assertEqual(row.status, "dead")
            self.assertNotIn("09125550000", row.last_error)  # ماسک
            self.assertEqual(deliver_pending()["processed"], 0)
            with self.assertRaises(RetryNotAllowed):
                retry_notification(row)
            row.refresh_from_db()
            self.assertEqual(row.status, "dead")
            # تلاشِ دوباره از مسیرِ قدیمی: همان ردیف همگام می‌شود، ردیفِ دوم ساخته نمی‌شود
            send.return_value = type("R", (), {"success": True, "provider_ref_id": "ok", "error_message": "", "provider": "console"})()
            retry_failed_log(log_id=log.pk, store=self.store)
            row.refresh_from_db()
            self.assertEqual((row.status, row.provider_ref, row.last_error), ("sent", "ok", ""))
            self.assertEqual(NotificationOutbox.objects.filter(sms_log=log).count(), 1)

    def test_insufficient_credit_failure_is_mirrored(self):
        SmsBalance.objects.filter(store=self.store).update(credits=0)
        log = self.send()
        self.assertEqual(log.status, "failed")
        self.assertEqual(NotificationOutbox.objects.get(sms_log=log).status, "dead")

    def test_otp_raw_and_storeless_logs_are_not_mirrored(self):
        send_event_sms("otp", "09125550000", {"otp_code": "123456"}, store=self.store)
        raw = send_raw_sms(phone="09125550000", message="پیام خام", store=self.store)
        self.assertIsNotNone(raw)
        orphan = SmsLog.objects.create(store=None, event_key="order_placed", recipient="0912", message="x", status="sent")
        self.assertIsNone(legacy_history.record_legacy_sms(orphan))
        self.assertEqual(NotificationOutbox.objects.filter(sms_log__isnull=False).count(), 0)

    def test_new_system_sms_is_not_duplicated_by_mirror(self):
        from apps.notifications.services.dispatcher import dispatch_event

        rows = dispatch_event("return.requested", store=self.store, customer=self.customer,
                              context={"customer_name": "س", "order_number": "A", "return_number": "R"}, channels=["sms"])
        self.assertEqual(len(rows), 1)
        deliver_pending()
        self.assertEqual(SmsLog.objects.filter(event_key="notification").count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(channel="sms").count(), 1)

    def test_mirror_failure_never_breaks_sms(self):
        with patch("apps.notifications.services.legacy_history.record_legacy_sms", side_effect=RuntimeError("boom")):
            log = self.send()
        self.assertEqual(log.status, "sent")

    def test_test_send_is_mirrored_flagged_as_test(self):
        log = send_test_sms(event_key="order_placed", phone="09125550000", store=self.store)
        self.assertTrue(NotificationOutbox.objects.get(sms_log=log).is_test)

    def test_backfill_is_idempotent_scoped_and_dry_run_safe(self):
        with patch("apps.notifications.services.legacy_history.safe_record_legacy_sms", return_value=None):
            old1 = self.send()
            old2 = send_event_sms("welcome", "09125550000", {"customer_name": "س"}, store=self.store)
        other = Store.objects.create(name="o", slug="mirror-other", status=Store.Status.ACTIVE)
        old3 = SmsLog.objects.create(store=other, event_key="order_shipped", recipient="09120000000", message="m", status="sent")
        SmsLog.objects.create(store=self.store, event_key="otp", recipient="09120000000", message="", status="sent")
        SmsLog.objects.create(store=self.store, event_key="order_placed", recipient="09120000000", message="p", status="pending")
        self.assertEqual(NotificationOutbox.objects.count(), 0)
        out = StringIO(); call_command("backfill_sms_history", "--dry-run", stdout=out)
        self.assertIn("candidates=3 created=0", out.getvalue())
        self.assertEqual(NotificationOutbox.objects.count(), 0)
        call_command("backfill_sms_history", "--store", self.store.slug, stdout=StringIO())
        self.assertEqual(NotificationOutbox.objects.count(), 2)
        for _ in range(2):
            call_command("backfill_sms_history", stdout=StringIO())
        self.assertEqual(NotificationOutbox.objects.count(), 3)
        self.assertEqual(NotificationOutbox.objects.get(sms_log=old3).store_id, other.pk)
        row = NotificationOutbox.objects.get(sms_log=old1)
        self.assertIsNone(row.customer_id)  # حدس‌زدنِ لینک ممنوع
        self.assertEqual(row.created_at, old1.created_at)
        self.assertEqual(SmsLog.objects.count(), 5)  # SmsLog دست‌نخورده
        self.assertEqual(NotificationOutbox.objects.get(sms_log=old2).event_key, "account.registered")


class AdminUiTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        SmsTemplate.ensure_defaults()

    def post(self, body, enabled="on", **extra):
        data = {"sms_body": body, "email_body": "x", "email_subject": "s", "email_enabled": "on"}
        if enabled:
            data["sms_enabled"] = enabled
        data.update(extra)
        return self.client.post(reverse("dashboard:notification-template-edit", args=["order.created"]), data)

    def test_editor_edits_real_template_and_shows_shared_notice(self):
        r = self.client.get(reverse("dashboard:notification-template-edit", args=["order.created"]))
        self.assertContains(r, "مشترک")
        self.assertContains(r, "{order_number}")
        r = self.post("سفارش {order_number} ثبت شد", )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SmsTemplate.objects.get(event_key="order_placed").body, "سفارش {order_code} ثبت شد")

    def test_invalid_template_shows_error_and_keeps_data(self):
        before = SmsTemplate.objects.get(event_key="order_placed").body
        r = self.post("{customer_name.__class__}")
        self.assertContains(r, "ساختارِ غیرمجاز")
        self.assertEqual(SmsTemplate.objects.get(event_key="order_placed").body, before)

    def test_without_sms_permission_legacy_sms_is_read_only(self):
        before = SmsTemplate.objects.get(event_key="order_placed")
        from apps.dashboard import engagement_views as views
        from apps.stores.authorization import SMS_SETTINGS_MANAGE, membership_has_permission

        def fake(membership, permission):
            return False if permission == SMS_SETTINGS_MANAGE else membership_has_permission(membership, permission)

        with patch.object(views, "membership_has_permission", side_effect=fake):
            self.assertContains(self.client.get(reverse("dashboard:notification-template-edit", args=["order.created"])), "فقط نمایش")
            r = self.post("متنِ دیگر {order_number}", enabled="")
            self.assertContains(r, "دسترسیِ «تنظیماتِ پیامک»")
        after = SmsTemplate.objects.get(event_key="order_placed")
        self.assertEqual((after.body, after.is_active), (before.body, before.is_active))

    def test_warning_when_store_sms_is_disabled(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_enabled = False
        shop.save()
        self.assertContains(self.client.get(reverse("dashboard:notification-templates")), "غیرفعال است")
        self.assertContains(self.client.get(reverse("dashboard:notification-template-edit", args=["order.created"])), "غیرفعال است")

    def test_history_shows_legacy_badge_and_legacy_retry_link(self):
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})
        send_event_sms("order_placed", "09125550000", {"customer_name": "س"}, store=self.store)
        row = NotificationOutbox.objects.get(sms_log__isnull=False)
        r = self.client.get(reverse("dashboard:notification-history"))
        self.assertContains(r, "پیامکِ قدیمی")
        self.assertContains(r, reverse("dashboard:sms-log-list"))
        r = self.client.post(reverse("dashboard:notification-retry", args=[row.pk]))
        row.refresh_from_db()
        self.assertEqual(row.status, "dead")
