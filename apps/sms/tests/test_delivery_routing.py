"""SMS delivery routing — ONE method per store (phone = SmsRasti Android gateway | platform = central provider).

Everything goes through the existing path (``send_event_sms``/``send_raw_sms`` → ``_dispatch`` → ``get_backend``); these tests pin:
automatic routing for transactional and campaign events, no silent method change, credit rules, device ack/poll behaviour,
history sync, retries, duplicate protection. HTTP to the real provider is mocked (nothing is sent to anyone)."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.customers.models import Customer
from apps.customers.services import consent_service
from apps.notifications.models import NotificationOutbox
from apps.notifications.services.dispatcher import dispatch_event
from apps.notifications.services.notification_service import deliver_pending
from apps.notifications.tests.test_verify_delivery_channels import set_platform
from apps.sms.events import DEFAULT_TEMPLATES, SmsEvent
from apps.sms.gateway_views import MAX_CLAIMS
from apps.sms.models import SmsBalance, SmsLog, SmsOutboxItem, SmsTemplate
from apps.sms.services.delivery_status_service import get_sms_delivery_status
from apps.sms.services.sms_service import retry_smsrasti_outbox_item, send_event_sms, send_raw_sms
from apps.stores.models import Store

User = get_user_model()
TOKEN = "device-token-routing-1"
OK = {"return": {"status": 200}, "entries": [{"messageid": 4242}]}
FAIL = {"return": {"status": 418, "message": "provider rejected"}}
CTX = {"discount_code": "GIFT-1", "discount_amount": "۳۰٪", "discount_max": "", "discount_expires_at": "۱۴۰۵/۱/۱",
       "campaign_name": "کمپین", "occasion_name": "مناسبت", "customer_name": "سارا"}
RETURN_CTX = {"order_number": "DM-1", "order_total": "1", "order_status": "x", "order_url": "", "customer_name": "س",
              "return_number": "R1", "reason": ""}


def http(payload=OK):
    response = MagicMock()
    response.json.return_value = payload
    return patch("requests.post", return_value=response)


class RoutingBase(TestCase):
    def setUp(self):
        SmsTemplate.ensure_defaults()
        self.store = Store.objects.get(slug="akhlaghi")
        self.shop = ShopSettings.load(store=self.store)
        self.shop.sms_enabled = True
        self.shop.smsrasti_device_token = TOKEN
        self.shop.save()
        set_platform("kavenegar", kavenegar_api_key="k-routing", kavenegar_sender="1000")
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        user = User.objects.create_user(username="09125550100", password="x12345678")
        self.customer = Customer.objects.create(
            user=user, full_name="سارا", phone="09125550100", email="s@example.com",
            accepts_promotional_sms=True, accepts_promotional_email=True,
        )

    def use(self, method):
        self.shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI if method == "phone" else ShopSettings.SmsBackend.CONSOLE
        self.shop.save()

    def credits(self):
        return SmsBalance.objects.get(store=self.store).credits

    def send_order(self):
        return send_event_sms(SmsEvent.ORDER_PLACED, self.customer.phone, {
            "customer_name": "سارا", "order_code": "DM-1", "amount": "1000",
        }, store=self.store)


class AutomaticRoutingTests(RoutingBase):
    def test_platform_method_uses_central_provider_and_consumes_credit(self):
        self.use("platform")
        with http() as post:
            log = self.send_order()
        self.assertEqual(post.call_count, 1)
        self.assertIn("k-routing", post.call_args.args[0])  # central credentials, none stored per store
        self.assertEqual((log.status, log.provider, log.provider_ref_id), ("sent", "kavenegar", "4242"))
        self.assertEqual(self.credits(), 100 - log.billable_units)
        self.assertEqual(SmsOutboxItem.objects.count(), 0)

    def test_phone_method_queues_for_the_device_without_touching_the_provider_or_credit(self):
        self.use("phone")
        with http() as post:
            log = self.send_order()
        post.assert_not_called()
        item = SmsOutboxItem.objects.get()
        self.assertEqual((item.status, item.phone, log.provider, log.provider_ref_id, log.cost_toman), ("pending", self.customer.phone, "smsrasti", str(item.pk), 0))
        self.assertEqual(self.credits(), 100)

    def test_phone_method_works_with_zero_platform_credit_platform_method_does_not(self):
        SmsBalance.objects.filter(store=self.store).update(credits=0)
        self.use("phone")
        with http() as post:
            self.assertEqual(self.send_order().status, "sent")
        post.assert_not_called()
        self.use("platform")
        with http() as post:
            log = self.send_order()
        post.assert_not_called()
        self.assertEqual((log.status, log.error_message), ("failed", "اعتبار پیامک کافی نیست"))
        self.assertEqual(SmsOutboxItem.objects.count(), 1)  # NO silent fallback to the phone

    def test_no_silent_fallback_to_platform_when_the_phone_is_not_configured(self):
        self.use("phone")
        self.shop.smsrasti_device_token = None
        self.shop.save()
        with http() as post:
            log = self.send_order()
        post.assert_not_called()
        self.assertEqual(log.status, "failed")
        self.assertEqual(self.credits(), 100)

    def test_provider_failure_refunds_credit_and_does_not_fall_back_to_the_phone(self):
        self.use("platform")
        with http(FAIL) as post:
            log = self.send_order()
        self.assertEqual((log.status, post.call_count), ("failed", 1))
        self.assertEqual(self.credits(), 100)
        self.assertEqual(SmsOutboxItem.objects.count(), 0)

    @override_settings(RASTISI_OWNER_SMS_ALLOW_CONSOLE_OTP=False)
    def test_unconfigured_platform_gateway_fails_loudly_instead_of_fake_success(self):
        set_platform("console")
        self.use("platform")
        log = self.send_order()
        self.assertEqual(log.status, "failed")
        self.assertIn("پیکربندی نشده", log.error_message)
        self.assertEqual(self.credits(), 100)  # refunded: nothing was charged for a message that never left

    def test_otp_always_uses_the_central_provider_even_for_phone_stores(self):
        self.use("phone")
        with patch("apps.sms.services.sms_service.get_backend") as never, patch(
            "apps.portal.services.owner_sms_service.send_platform_otp",
        ) as otp:
            otp.return_value = MagicMock(success=True, provider_ref_id="o1", provider="kavenegar", error_message="")
            log = send_event_sms(SmsEvent.OTP, self.customer.phone, {"otp_code": "123456"}, store=self.store)
        never.assert_not_called()
        otp.assert_called_once()
        self.assertEqual((log.status, SmsOutboxItem.objects.count()), ("sent", 0))
        self.assertEqual(log.message, "")  # OTP body is never stored

    def test_changing_the_method_affects_only_subsequent_messages_and_never_resends(self):
        self.use("phone")
        with http() as post:
            self.send_order()
        first = SmsOutboxItem.objects.get()
        self.use("platform")
        with http() as post:
            self.send_order()
        self.assertEqual(post.call_count, 1)  # only the NEW message went to the provider
        first.refresh_from_db()
        self.assertEqual((first.status, SmsOutboxItem.objects.count()), ("pending", 1))  # old one untouched, not re-sent
        self.use("phone")
        with http() as post:
            self.send_order()
        post.assert_not_called()
        self.assertEqual(SmsOutboxItem.objects.count(), 2)
        self.assertEqual(SmsLog.objects.filter(store=self.store).count(), 3)

    def test_disabled_sms_sends_nothing_with_either_method(self):
        self.shop.sms_enabled = False
        self.shop.save()
        for method in ("phone", "platform"):
            self.use(method)
            with http() as post:
                self.assertIsNone(self.send_order())
            post.assert_not_called()
        self.assertEqual((SmsOutboxItem.objects.count(), SmsLog.objects.count()), (0, 0))


class NotificationOutboxRoutingTests(RoutingBase):
    """Campaign (promotional) and transactional new-system events: same routing, one send, no duplicates."""

    def queue(self, key, ctx):
        rows = dispatch_event(key, store=self.store, customer=self.customer, context=ctx, channels=["sms"], dedupe_key=f"{key}-1")
        self.assertEqual([r.status for r in rows], ["pending"])
        return rows[0]

    def test_campaign_and_transactional_events_follow_platform_method(self):
        self.use("platform")
        self.queue("coupon.issued", CTX)
        self.queue("return.approved", RETURN_CTX)
        with http() as post:
            result = deliver_pending()
            deliver_pending()  # second worker run must not resend
        self.assertEqual((result["sent"], post.call_count), (2, 2))
        self.assertEqual(SmsOutboxItem.objects.count(), 0)
        self.assertEqual(NotificationOutbox.objects.filter(status="sent", channel="sms").count(), 2)

    def test_campaign_and_transactional_events_follow_phone_method(self):
        self.use("phone")
        self.queue("coupon.issued", CTX)
        self.queue("return.approved", RETURN_CTX)
        with http() as post:
            deliver_pending()
            deliver_pending()
        post.assert_not_called()
        self.assertEqual(SmsOutboxItem.objects.count(), 2)  # exactly one device message per event
        self.assertEqual(self.credits(), 100)

    def test_legacy_synchronous_events_have_no_outbox_sms_so_they_are_never_sent_twice(self):
        self.use("platform")
        rows = dispatch_event("order.created", store=self.store, customer=self.customer, channels=["sms"], dedupe_key="o1", context={
            "order_number": "DM-1", "order_total": "1", "customer_name": "س", "order_status": "x", "order_url": ""})
        self.assertEqual(rows, [])  # SMS for order.created comes ONLY from send_event_sms

    def test_outbox_failure_is_retried_by_the_existing_worker_with_platform_credit_error(self):
        self.use("platform")
        SmsBalance.objects.filter(store=self.store).update(credits=0)
        row = self.queue("coupon.issued", CTX)
        with http() as post:
            deliver_pending()
        post.assert_not_called()
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), ("failed", 1))
        self.assertIn("اعتبار", row.last_error)
        SmsBalance.objects.filter(store=self.store).update(credits=50)
        NotificationOutbox.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now() - timedelta(minutes=1))
        with http() as post:
            deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, post.call_count), ("sent", 1))


class DeviceProtocolTests(RoutingBase):
    def setUp(self):
        super().setUp()
        self.use("phone")
        self.client_kw = {"HTTP_HOST": "testserver"}

    def poll(self, token=TOKEN):
        return self.client.get(reverse("sms:smsrasti-poll"), {"token": token})

    def ack(self, item, status="sent", token=TOKEN, **extra):
        return self.client.post(reverse("sms:smsrasti-ack"), {"token": token, "id": item.pk, "status": status, **extra})

    def queued(self, n=1):
        items = []
        for i in range(n):
            send_raw_sms(phone=f"0912555{i:04d}", message=f"پیام {i}", store=self.store)
            items.append(SmsOutboxItem.objects.order_by("-pk").first())
        return items

    def test_endpoints_exist(self):
        self.assertEqual(self.poll().status_code, 200)

    def test_pairing_requires_the_exact_token_and_poll_marks_the_device_online(self):
        self.assertEqual(self.poll("wrong").status_code, 401)
        self.assertIsNone(ShopSettings.objects.get(pk=self.shop.pk).smsrasti_last_seen_at)
        self.assertEqual(self.poll().json(), {"status": "empty"})
        status = get_sms_delivery_status(self.store)
        self.assertTrue(status["device"]["online"])
        self.assertEqual(status["health"], "ok")

    def test_offline_device_keeps_messages_queued_in_order_and_drains_them_when_back(self):
        first, second = self.queued(2)
        status = get_sms_delivery_status(self.store)
        self.assertEqual(status["queue"]["pending"], 2)
        self.assertEqual(status["health"], "error")  # never connected
        ShopSettings.objects.filter(pk=self.shop.pk).update(smsrasti_last_seen_at=timezone.now() - timedelta(minutes=30))
        status = get_sms_delivery_status(self.store)
        self.assertEqual(status["health"], "warning")
        self.assertTrue(any("آفلاین" in w and "2" in w.replace("۲", "2") for w in status["warnings"]))
        self.assertEqual(self.poll().json()["id"], first.pk)  # oldest first, nothing lost
        self.ack(first)
        self.assertEqual(self.poll().json()["id"], second.pk)

    def test_duplicate_polling_never_hands_the_same_message_to_two_pollers(self):
        (item,) = self.queued(1)
        self.assertEqual(self.poll().json()["id"], item.pk)
        self.assertEqual(self.poll().json(), {"status": "empty"})  # still SENDING within the reclaim window
        item.refresh_from_db()
        self.assertEqual((item.status, item.attempt_count), ("sending", 1))

    def test_ack_sent_is_final_and_a_late_duplicate_or_conflicting_ack_cannot_change_it(self):
        (item,) = self.queued(1)
        self.poll()
        self.ack(item, rec_id="R-1")
        self.assertEqual(self.ack(item, status="failed", error="late").json().get("duplicate"), True)
        item.refresh_from_db()
        self.assertEqual((item.status, item.provider_ref_id, item.error_message), ("sent", "R-1", ""))
        self.assertEqual(SmsLog.objects.get(provider="smsrasti").status, "sent")

    def test_failed_ack_is_reported_in_history_and_status_then_safe_manual_retry_requeues_it(self):
        (item,) = self.queued(1)
        self.poll()
        self.ack(item, status="failed", error="no signal")
        item.refresh_from_db()
        self.assertEqual((item.status, item.error_message), ("failed", "no signal"))
        log = SmsLog.objects.get(provider="smsrasti")
        self.assertEqual((log.status, log.error_message), ("failed", "no signal"))
        self.assertEqual(get_sms_delivery_status(self.store)["queue"]["failed"], 1)
        retry_smsrasti_outbox_item(item_id=item.pk, store=self.store)
        item.refresh_from_db()
        self.assertEqual((item.status, item.attempt_count), ("pending", 0))
        self.assertEqual(self.poll().json()["id"], item.pk)
        self.ack(item)
        log.refresh_from_db()
        self.assertEqual(log.status, "sent")  # history follows the real outcome after the retry

    def test_unacknowledged_message_is_reclaimed_a_bounded_number_of_times_then_failed(self):
        (item,) = self.queued(1)
        claimed = 0
        for _ in range(MAX_CLAIMS + 2):
            SmsOutboxItem.objects.filter(pk=item.pk, status="sending").update(claimed_at=timezone.now() - timedelta(minutes=10))
            if self.poll().json().get("status") == "ok":
                claimed += 1
        item.refresh_from_db()
        self.assertEqual(claimed, MAX_CLAIMS)
        self.assertEqual(item.status, "failed")
        self.assertIn(str(MAX_CLAIMS), item.error_message)
        self.assertEqual(SmsLog.objects.get(provider="smsrasti").status, "failed")

    def test_a_device_can_only_see_and_ack_its_own_stores_messages(self):
        other = Store.objects.create(name="دیگر", slug="other-sms", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(other)
        other_shop = ShopSettings.load(store=other)
        other_shop.smsrasti_device_token = "other-device-token"
        other_shop.save()
        (mine,) = self.queued(1)
        self.assertEqual(self.poll("other-device-token").json(), {"status": "empty"})
        self.assertEqual(self.ack(mine, token="other-device-token").status_code, 404)

    def test_regenerating_the_token_invalidates_the_old_device_immediately(self):
        from apps.sms.services.sms_service import regenerate_smsrasti_device_token

        self.queued(1)
        new = regenerate_smsrasti_device_token(store=self.store)
        self.assertEqual(self.poll().status_code, 401)
        self.assertEqual(self.poll(new).json()["status"], "ok")


class StatusAndBrandingTests(RoutingBase):
    def test_platform_status_reports_credit_and_actionable_errors(self):
        self.use("platform")
        status = get_sms_delivery_status(self.store)
        self.assertEqual((status["method"], status["credits"], status["health"]), ("platform", 100, "ok"))
        SmsBalance.objects.filter(store=self.store).update(credits=0)
        status = get_sms_delivery_status(self.store)
        self.assertEqual(status["health"], "error")
        self.assertTrue(any("اعتبار" in e for e in status["errors"]))
        self.shop.sms_enabled = False
        self.shop.save()
        self.assertTrue(any("خاموش" in e for e in get_sms_delivery_status(self.store)["errors"]))

    def test_dashboard_page_shows_the_status_block(self):
        from apps.dashboard.tests.test_coupon_views import HOST

        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        from apps.stores.models import StoreMembership

        owner = User.objects.create_user(username="09125550199", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client.login(username="09125550199", password="pass12345")
        self.use("phone")
        with self.settings(ALLOWED_HOSTS=[HOST, "testserver"]):
            page = self.client.get(reverse("dashboard:settings") + "?section=sms", HTTP_HOST=HOST)
        self.assertContains(page, "وضعیتِ ارسالِ پیامک")
        self.assertContains(page, "گوشیِ شما")
        self.assertContains(page, "جفت‌شده، هنوز متصل نشده")

    def test_no_store_customer_default_message_carries_platform_branding(self):
        platform_only = {SmsEvent.PLATFORM_OWNER_OTP, SmsEvent.PLATFORM_TEST}
        for key, body in DEFAULT_TEMPLATES.items():
            if key in platform_only:
                continue
            for brand in ("راستی", "RastiSi", "rastisi"):
                self.assertNotIn(brand, body, f"{key} must speak for the store, not the platform")
        from apps.notifications import events as ev

        for key, definition in ev.EVENTS.items():
            for text in (definition.default_sms, definition.default_email_subject, definition.default_email_body):
                for brand in ("راستی", "RastiSi", "rastisi"):
                    self.assertNotIn(brand, text, key)
