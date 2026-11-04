"""Tenant-specific SMS templates for legacy events: stores edit/disable their OWN SMS text; the global platform template,
provider Pattern ids, billing, OTP and platform-managed (campaign/occasion) texts are untouched."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.models import ShopSettings
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.notifications import events as ev
from apps.notifications.models import NotificationTemplate
from apps.notifications.services import template_service as ts
from apps.sms.events import DEFAULT_TEMPLATES, SmsEvent
from apps.sms.models import SmsBalance, SmsLog, SmsOutboxItem, SmsTemplate
from apps.sms.services.backends import MelipayamakBackend, SmsBackend, SmsSendResult
from apps.sms.services.sms_service import send_event_sms
from apps.stores.models import Store, StoreMembership

User = get_user_model()
CTX = {"customer_name": "س", "order_code": "A1", "amount": "5"}


class RecordingBackend(SmsBackend):
    provider_code = "recording"

    def __init__(self):
        self.sent = []

    def send(self, *, to, text):
        self.sent.append((to, text))
        return SmsSendResult(success=True, provider_ref_id="r1", provider="recording")


class RecordingMeli(MelipayamakBackend):
    def __init__(self):
        super().__init__(username="u", password="p", sender="s")
        self.plain, self.pattern = [], []

    def send(self, *, to, text):
        self.plain.append((to, text))
        return SmsSendResult(success=True, provider_ref_id="plain")

    def send_pattern(self, *, to, body_id, variables, variables_order="otp_code"):
        self.pattern.append((to, body_id, dict(variables)))
        return SmsSendResult(success=True, provider_ref_id="pattern")


class Base(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        SmsTemplate.ensure_defaults()
        self.other = Store.objects.create(name="دیگر", slug="sms-other", status=Store.Status.ACTIVE)
        for st in (self.store, self.other):
            SmsBalance.objects.update_or_create(store=st, defaults={"credits": 1000})
            ShopSettings.objects.filter(store=st).exists() or ShopSettings.provision_for(st)
        self.backend = RecordingBackend()
        patcher = patch("apps.sms.services.sms_service.get_backend", return_value=self.backend)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, store=None, key="order_placed"):
        return send_event_sms(key, "09121234567", dict(CTX), store=store or self.store)


class TenantIsolationTests(Base):
    def test_override_applies_only_to_the_store_that_made_it(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        mine, theirs = self.send(self.store), self.send(self.other)
        self.assertEqual(mine.message, "اختصاصی A1")
        self.assertNotIn("اختصاصی", theirs.message)
        self.assertIn("A1", theirs.message)  # platform default text for the other store

    def test_disabling_one_store_does_not_disable_another(self):
        ts.save_template(self.store, "order.created", "sms", enabled=False, subject="", body="")
        self.assertIsNone(self.send(self.store))
        self.assertIsNotNone(self.send(self.other))
        self.assertEqual(len(self.backend.sent), 1)

    def test_other_store_cannot_read_or_change_my_override_through_the_service(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="سرّی {order_number}")
        self.assertEqual(ts.get_template(self.other, "order.created", "sms")["source"], "platform")
        self.assertNotIn("سرّی", ts.get_template(self.other, "order.created", "sms")["body"])
        self.assertEqual(ts.list_revisions(scope="store", store=self.other), [])

    def test_dashboard_edit_only_ever_writes_the_current_stores_row(self):
        self.client.post(reverse("dashboard:notification-template-edit", args=["order.created"]), {
            "sms_enabled": "on", "sms_body": "فقط من {order_number}", "email_enabled": "on", "email_subject": "s {order_number}",
            "email_body": "b {order_number}"})
        rows = NotificationTemplate.objects.filter(event_key="order.created", channel="sms")
        self.assertEqual([r.store_id for r in rows], [self.store.pk])


class PlatformBoundaryTests(Base):
    def test_global_template_is_never_modified_by_any_store_action(self):
        before = SmsTemplate.objects.get(event_key="order_placed")
        snap = (before.body, before.is_active, before.melipayamak_body_id, before.melipayamak_variables_order, before.kavenegar_template)
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="x {order_number}")
        ts.set_channel_enabled(self.store, "order.created", "sms", False)
        ts.reset_template(self.store, "order.created", "sms")
        after = SmsTemplate.objects.get(event_key="order_placed")
        self.assertEqual((after.body, after.is_active, after.melipayamak_body_id, after.melipayamak_variables_order, after.kavenegar_template), snap)

    def test_platform_kill_switch_beats_a_store_override(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        SmsTemplate.objects.filter(event_key="order_placed").update(is_active=False)
        self.assertIsNone(self.send(self.store))
        tpl = ts.get_template(self.store, "order.created", "sms")
        self.assertFalse(tpl["enabled"])
        self.assertFalse(tpl["platform_active"])

    def test_platform_default_is_what_a_store_without_override_sends(self):
        SmsTemplate.objects.filter(event_key="order_placed").update(body="پلتفرم {order_code}")
        self.assertEqual(self.send(self.store).message, "پلتفرم A1")
        self.assertEqual(self.send(self.other).message, "پلتفرم A1")

    def test_platform_managed_campaign_sms_cannot_be_overridden_by_a_store(self):
        for key in ("campaign.announce", "occasion.birthday"):
            with self.assertRaises(ts.PlatformManagedError):
                ts.save_template(self.store, key, "sms", enabled=True, subject="", body="هک {customer_name}")
            with self.assertRaises(ts.PlatformManagedError):
                ts.set_channel_enabled(self.store, key, "sms", False)
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, channel="sms").exists())

    def test_otp_has_no_override_path_at_all(self):
        self.assertNotIn(SmsEvent.OTP, {e.legacy_sms_event for e in ev.EVENTS.values()})
        from apps.sms.services.sms_service import _store_override

        NotificationTemplate.objects.create(store=self.store, event_key="order.created", channel="sms", body="x")
        self.assertIsNone(_store_override(self.store, SmsEvent.OTP))
        self.assertIsNone(_store_override(self.store, SmsEvent.PLATFORM_OWNER_OTP))


class ProviderAndBillingCompatibilityTests(Base):
    def test_customized_text_is_sent_as_plain_text_while_default_text_still_uses_the_provider_pattern(self):
        meli = RecordingMeli()
        SmsTemplate.objects.filter(event_key="order_placed").update(melipayamak_body_id="12345", melipayamak_variables_order="order_code")
        with patch("apps.sms.services.sms_service.get_backend", return_value=meli):
            self.send(self.other)  # no override -> Pattern, exactly as before this change
            ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
            self.send(self.store)  # override -> plain text (Pattern text would not match the custom wording)
        self.assertEqual([p[1] for p in meli.pattern], ["12345"])
        self.assertEqual(meli.plain, [("09121234567", "اختصاصی A1")])

    def test_credit_billing_and_log_flow_is_unchanged_for_overrides(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        before = SmsBalance.objects.get(store=self.store).credits
        log = self.send(self.store)
        self.assertEqual((log.status, log.event_key, log.store_id), (SmsLog.Status.SENT, "order_placed", self.store.pk))
        self.assertLess(SmsBalance.objects.get(store=self.store).credits, before)
        self.assertEqual(SmsBalance.objects.get(store=self.other).credits, 1000)

    def test_no_credit_still_blocks_an_override_send_like_any_sms(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        SmsBalance.objects.filter(store=self.store).update(credits=0)
        log = self.send(self.store)
        self.assertEqual(log.status, SmsLog.Status.FAILED)
        self.assertEqual(self.backend.sent, [])

    def test_store_level_sms_switch_off_still_wins_over_everything(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        shop = ShopSettings.load(store=self.store)
        shop.sms_enabled = False
        shop.save()
        self.assertIsNone(self.send(self.store))

    def test_a_broken_override_row_falls_back_to_the_platform_text_instead_of_blocking_the_sms(self):
        NotificationTemplate.objects.create(store=self.store, event_key="order.created", channel="sms",
                                            body="{__class__} {nope}", is_enabled=True)
        log = self.send(self.store)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, SmsLog.Status.SENT)
        self.assertNotIn("__class__", log.message)

    def test_smsrasti_device_queue_receives_the_override_text(self):
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "tok"
        shop.save()
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        with patch("apps.sms.services.sms_service.get_backend", side_effect=lambda store: __import__(
                "apps.sms.services.backends", fromlist=["x"]).SmsRastiBackend(store=store, device_token="tok")):
            self.send(self.store)
        self.assertEqual(SmsOutboxItem.objects.get(store=self.store).message, "اختصاصی A1")

    def test_history_mirror_is_still_recorded_once(self):
        from apps.notifications.models import NotificationOutbox

        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="اختصاصی {order_number}")
        self.send(self.store)
        self.assertEqual(NotificationOutbox.objects.filter(store=self.store, channel="sms", event_key="order.created").count(), 1)


class ValidationAndSecurityTests(Base):
    def test_unsafe_or_unsupported_text_is_rejected_and_nothing_is_stored(self):
        for bad in ("{order_url}", "{customer_name.__class__}", "{unknown}", "{x", "a" * 1001, "ab\x00c"):
            with self.assertRaises(ts.TemplateError, msg=bad[:20]):
                ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body=bad)
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, channel="sms").exists())

    def test_empty_text_cannot_be_saved_as_an_enabled_override(self):
        with self.assertRaises(ts.TemplateError):
            ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="  ")

    def test_security_event_sms_remains_always_enabled(self):
        ts.save_template(self.store, "account.sensitive_changed", "sms", enabled=False, subject="", body="{changed_field}")
        self.assertTrue(ts.get_template(self.store, "account.sensitive_changed", "sms")["enabled"])

    def test_revision_history_records_sms_overrides_with_actor(self):
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="یک {order_number}", actor=self.owner)
        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="دو {order_number}", actor=self.owner)
        ts.reset_template(self.store, "order.created", "sms", actor=self.owner)
        revs = ts.list_revisions(scope="store", store=self.store, event_key="order.created", channel="sms")
        self.assertEqual([(r.action, r.actor) for r in revs], [("reset", self.owner), ("save", self.owner), ("save", self.owner)])

    def test_role_without_sms_permission_cannot_edit_or_toggle_legacy_sms(self):
        self._login_as(StoreMembership.Role.CONTENT_EDITOR, "601")
        from apps.dashboard import engagement_views as views
        from apps.stores.authorization import SMS_SETTINGS_MANAGE, membership_has_permission

        def fake(membership, permission):
            return False if permission == SMS_SETTINGS_MANAGE else membership_has_permission(membership, permission)

        with patch.object(views, "membership_has_permission", side_effect=fake), \
                patch("apps.dashboard.notification_admin_views.membership_has_permission", side_effect=fake):
            self.client.post(reverse("dashboard:notification-template-edit", args=["order.created"]), {
                "sms_enabled": "on", "sms_body": "هک {order_number}", "email_enabled": "on", "email_subject": "s {order_number}",
                "email_body": "b {order_number}"})
            self.client.post(reverse("dashboard:notification-channels"), {
                "seen__order.created__sms": "1"})  # forged: unchecked == switch off
        self.assertFalse(NotificationTemplate.objects.filter(store=self.store, channel="sms").exists())
        self.assertIsNotNone(self.send(self.store))

    def test_channels_page_unlocks_legacy_sms_switches_with_the_sms_permission(self):
        page = self.client.get(reverse("dashboard:notification-channels"))
        self.assertContains(page, 'name="seen__order.created__sms"')
        self.client.post(reverse("dashboard:notification-channels"), {"seen__order.created__sms": "1"})  # unchecked = off
        self.assertFalse(ts.get_template(self.store, "order.created", "sms")["store_enabled"])
        self.assertIsNone(self.send(self.store))
        self.assertIsNotNone(self.send(self.other))
        self.client.post(reverse("dashboard:notification-channels"), {"seen__order.created__sms": "1", "order.created__sms": "on"})
        self.assertIsNotNone(self.send(self.store))

    def test_test_send_uses_the_override_text(self):
        from apps.notifications.models import NotificationOutbox

        ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="آزمایشی {order_number}")
        from django.core.cache import cache

        cache.clear()
        self.client.post(reverse("dashboard:notification-template-test", args=["order.created"]),
                         {"channel": "sms", "recipient": "09120001111"})
        row = NotificationOutbox.objects.get(is_test=True)
        self.assertEqual(row.body, "آزمایشی DM-12345")
