"""Expiry / validity policy: nothing stale, expired or contextually invalid is ever delivered; records are preserved and
failures are actionable. Order/coupon state is only READ — no financial logic is invoked."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import Coupon
from apps.dashboard.tests.test_coupon_views import CouponViewsTestCase
from apps.notifications import events as ev
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import NotificationOutbox
from apps.notifications.services import expiry
from apps.notifications.services.notification_service import (
    RetryNotAllowed, deliver_pending, release_held, retry_notification,
)
from apps.engagement.tests.base import EngagementBase
from apps.notifications.tests.helpers import give_active_sender
from apps.stores.models import Store

User = get_user_model()
S = NotificationOutbox.Status


class PolicyTableTests(TestCase):
    def test_every_event_has_a_policy_with_sane_windows(self):
        for key, event in ev.EVENTS.items():
            p = expiry.policy_for(key)
            self.assertGreater(p.ttl_hours, 0, key)
            self.assertLessEqual(p.hold_hours, p.ttl_hours, key)
            if p.validator:
                self.assertIn(p.validator, expiry.VALIDATORS, key)

    def test_category_defaults(self):
        self.assertEqual(expiry.policy_for("account.sensitive_changed").ttl_hours, 48)  # security: short
        self.assertEqual(expiry.policy_for("order.created").ttl_hours, 168)              # transactional: a week
        self.assertEqual(expiry.policy_for("coupon.issued").ttl_hours, 24)               # promotional: a day
        self.assertEqual(expiry.policy_for("payment.failed").ttl_hours, 72)
        for key, event in ev.EVENTS.items():
            if event.category == ev.PROMOTIONAL:
                self.assertLessEqual(expiry.policy_for(key).ttl_hours, 24, key)

    def test_coupon_bearing_promotions_are_bound_to_coupon_validity(self):
        for key in ev.EVENTS:
            if key.startswith(expiry.COUPON_BOUND_PREFIXES):
                self.assertEqual(expiry.policy_for(key).validator, "coupon_still_usable", key)

    def test_no_event_in_this_engine_carries_a_code_token_or_reset_link(self):
        """OTPs and password-reset links never travel through the queue (they have their own few-minute validity)."""
        bad = ("otp", "token", "code_", "reset", "verify_url", "magic")
        for key, event in ev.EVENTS.items():
            leaked = [v for v in event.variables if any(b in v.lower() for b in bad) and v != "discount_code"]
            self.assertEqual(leaked, [], key)
        self.assertFalse([k for k in ev.EVENTS if "otp" in k or "password" in k])


class Base(EngagementBase):
    """Real store/products/orders from the engagement test base (orders go through the real order service)."""

    def setUp(self):
        super().setUp()  # also gives the store an ACTIVE fake sender
        self.cust = self.customer("سارا", email="sara@example.com")
        self.item = self.product("کالا", 1000)

    def make_order(self, *, status="pending", payment="pending"):
        order = self.order(self.cust, [(self.item, 1)], when=timezone.now(), status=status, payment=payment)
        NotificationOutbox.objects.all().delete()  # drop the notifications order creation itself queued
        return order

    def row(self, event_key, *, age_hours=0, order=None, metadata=None, channel="email", promotional=False, **kw):
        kw.setdefault("recipient_email", "sara@example.com")
        row = NotificationOutbox.objects.create(
            channel=channel, store=self.store, customer=self.cust, order=order, event_key=event_key, subject="s", body="b",
            recipient_phone=self.cust.phone, is_promotional=promotional, metadata=metadata or {}, **kw)
        if age_hours:
            NotificationOutbox.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=age_hours))
            row.refresh_from_db()
        return row


class TtlTests(Base):
    def test_a_message_older_than_its_ttl_is_never_sent_and_is_kept_as_expired(self):
        for key, hours in (("account.sensitive_changed", 49), ("order.created", 169), ("payment.failed", 73), ("coupon.issued", 25)):
            row = self.row(key, age_hours=hours, promotional=key.startswith("coupon"))
            deliver_pending()
            row.refresh_from_db()
            self.assertEqual((row.status, row.last_error), (S.EXPIRED, "ttl_exceeded"), key)
        self.assertEqual(FakeTransport.sent, [])
        self.assertEqual(NotificationOutbox.objects.filter(status=S.EXPIRED).count(), 4)  # nothing deleted

    def test_a_message_just_inside_its_ttl_is_sent(self):
        row = self.row("order.created", age_hours=167)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)

    def test_expired_rows_cannot_be_retried_or_revived(self):
        row = self.row("order.created", age_hours=200)
        deliver_pending()
        row.refresh_from_db()
        with self.assertRaises(RetryNotAllowed):
            retry_notification(row)
        self.assertEqual(release_held(self.store), {"released": 0, "revived": 0, "finalized": 0})
        deliver_pending()
        self.assertEqual(FakeTransport.sent, [])

    def test_manual_retry_of_a_dead_row_past_its_ttl_is_refused_with_a_persian_reason_and_finalized(self):
        row = self.row("payment.failed", age_hours=80, status=S.DEAD, last_error="sender_not_active_expired")
        with self.assertRaises(RetryNotAllowed) as cm:
            retry_notification(row)
        self.assertIn("مهلت", str(cm.exception))
        row.refresh_from_db()
        self.assertEqual(row.status, S.EXPIRED)

    def test_sms_rows_in_the_outbox_are_subject_to_the_same_rules(self):
        row = self.row("order.created", age_hours=200, channel="sms")
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.EXPIRED)


class ContextualValidityTests(Base):
    def order_(self, **kw):
        return self.make_order(status=kw.get("status", "pending"), payment=kw.get("payment_status", "pending"))

    def assert_stale(self, row, reason):
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, f"stale:{reason}"))
        self.assertEqual(FakeTransport.sent, [])

    def test_payment_failed_notice_is_dropped_once_the_order_was_paid(self):
        o = self.order_(payment_status="paid")
        self.assert_stale(self.row("payment.failed", order=o), "payment_resolved")

    def test_payment_failed_notice_still_sent_while_unpaid(self):
        o = self.order_(payment_status="failed")
        row = self.row("payment.failed", order=o)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)

    def test_processing_notice_is_superseded_by_later_status(self):
        for st in ("shipped", "delivered", "canceled"):
            o = self.order_(status=st)
            row = self.row("order.processing", order=o)
            deliver_pending()
            row.refresh_from_db()
            self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, f"stale:order_{st}"), st)

    def test_shipped_notice_dropped_after_cancel_or_delivery_but_not_while_current(self):
        self.assert_stale(self.row("order.shipped", order=self.order_(status="canceled")), "order_canceled")
        ok = self.row("order.shipped", order=self.order_(status="shipped"))
        deliver_pending()
        ok.refresh_from_db()
        self.assertEqual(ok.status, S.SENT)

    def test_order_created_confirmation_dropped_if_order_was_canceled_meanwhile(self):
        self.assert_stale(self.row("order.created", order=self.order_(status="canceled")), "order_canceled")

    def test_cancellation_notice_itself_is_always_valid(self):
        row = self.row("order.canceled", order=self.order_(status="canceled"))
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)

    def coupon(self, **kw):
        base = dict(store=self.store, code=f"C{Coupon.objects.count()}", type=Coupon.Type.PERCENT, value=Decimal("10"), is_active=True)
        base.update(kw)
        return Coupon.objects.create(**base)

    def test_coupon_notice_dropped_when_the_code_expired_was_deactivated_or_used_up(self):
        past = timezone.now() - timedelta(hours=1)
        cases = (("coupon_expired", dict(expires_at=past)), ("coupon_inactive", dict(is_active=False)),
                 ("coupon_used_up", dict(usage_limit=1, used_count=1)))
        for reason, kw in cases:
            c = self.coupon(**kw)
            row = self.row("coupon.issued", metadata={"coupon_id": c.pk}, promotional=True)
            deliver_pending()
            row.refresh_from_db()
            self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, f"stale:{reason}"), reason)

    def test_valid_coupon_notice_is_sent(self):
        c = self.coupon(expires_at=timezone.now() + timedelta(days=3))
        row = self.row("coupon.issued", metadata={"coupon_id": c.pk}, promotional=True)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)

    def test_another_stores_coupon_id_in_metadata_cannot_validate_or_invalidate_this_message(self):
        other = Store.objects.create(name="o", slug="exp-other", status=Store.Status.ACTIVE)
        foreign = Coupon.objects.create(store=other, code="FOREIGN", type=Coupon.Type.PERCENT, value=Decimal("5"), is_active=False)
        row = self.row("coupon.issued", metadata={"coupon_id": foreign.pk}, promotional=True)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)  # foreign coupon is ignored (store-scoped lookup), not trusted

    def test_expiring_reminder_uses_the_issuance_to_find_the_coupon(self):
        from apps.engagement.models import Campaign, CampaignIssuance

        c = self.coupon(expires_at=timezone.now() - timedelta(minutes=5))
        campaign = Campaign.objects.create(store=self.store, name="k", trigger_type="manual", rules={}, coupon_type="percent", coupon_value=5)
        issuance = CampaignIssuance.objects.create(campaign=campaign, customer=self.cust, coupon=c)
        row = self.row("coupon.expiring", metadata={"campaign_id": campaign.pk, "issuance_id": issuance.pk}, promotional=True)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, "stale:coupon_expired"))

    def test_test_sends_are_not_blocked_by_context_checks(self):
        o = self.order_(status="canceled")
        row = self.row("order.processing", order=o, is_test=True)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)

    def test_platform_sender_notices_are_dropped_when_the_state_they_report_no_longer_holds(self):
        from apps.notifications.models import EmailSenderIdentity

        EmailSenderIdentity.objects.filter(store=self.store).update(status="active")
        problem = self.row("platform.email_sender_problem", recipient_email="o@x.test")
        deliver_pending()
        problem.refresh_from_db()
        self.assertEqual((problem.status, problem.skip_reason), (S.SKIPPED, "stale:sender_recovered"))
        EmailSenderIdentity.objects.filter(store=self.store).update(status="error")
        active = self.row("platform.email_sender_active", recipient_email="o@x.test")
        deliver_pending()
        active.refresh_from_db()
        self.assertEqual((active.status, active.skip_reason), (S.SKIPPED, "stale:sender_no_longer_active"))

    def test_validity_checks_never_write_to_orders_or_coupons(self):
        o = self.order_(status="shipped", payment_status="paid")
        c = self.coupon()
        before_o = (o.status, o.payment_status, o.updated_at)
        before_c = (c.is_active, c.used_count, c.updated_at)
        self.row("order.processing", order=o)
        self.row("coupon.issued", metadata={"coupon_id": c.pk}, promotional=True)
        deliver_pending()
        o.refresh_from_db(), c.refresh_from_db()
        self.assertEqual(((o.status, o.payment_status, o.updated_at)), before_o)
        self.assertEqual((c.is_active, c.used_count, c.updated_at), before_c)


class HoldAndRevivalTests(Base):
    def test_transactional_hold_window_then_actionable_failure_then_revival_when_still_valid(self):
        from apps.notifications.models import EmailSenderIdentity

        EmailSenderIdentity.objects.filter(store=self.store).update(status="inactive")
        row = self.row("return.approved", age_hours=0)
        t0 = timezone.now()
        deliver_pending(now=t0)
        later = t0 + timedelta(hours=73)
        NotificationOutbox.objects.filter(pk=row.pk).update(next_attempt_at=later - timedelta(minutes=1))
        deliver_pending(now=later)
        row.refresh_from_db()
        self.assertEqual((row.status, row.last_error), (S.DEAD, "sender_not_active_expired"))   # visible, actionable
        EmailSenderIdentity.objects.filter(store=self.store).update(status="active")
        self.assertEqual(release_held(self.store, now=t0 + timedelta(hours=100))["revived"], 1)  # < 168h: still valid
        row.refresh_from_db()
        self.assertEqual(row.status, S.PENDING)

    def test_revival_finalizes_rows_that_became_invalid_while_held(self):
        from apps.notifications.models import EmailSenderIdentity
        EmailSenderIdentity.objects.filter(store=self.store).update(status="inactive")
        order = self.make_order()
        stale_payment = self.row("payment.failed", order=order)
        past_ttl = self.row("order.created", age_hours=0)
        t0 = timezone.now()
        deliver_pending(now=t0)
        deliver_pending(now=t0 + timedelta(hours=71) + timedelta(minutes=16))   # still held
        NotificationOutbox.objects.filter(pk__in=[stale_payment.pk, past_ttl.pk]).update(
            status=S.DEAD, last_error="sender_not_active_expired")
        __import__("apps.orders.models", fromlist=["Order"]).Order.objects.filter(pk=order.pk).update(payment_status="paid")   # paid while the notice was stuck
        NotificationOutbox.objects.filter(pk=past_ttl.pk).update(created_at=timezone.now() - timedelta(hours=200))
        EmailSenderIdentity.objects.filter(store=self.store).update(status="active")
        result = release_held(self.store)
        self.assertEqual(result, {"released": 0, "revived": 0, "finalized": 2})
        stale_payment.refresh_from_db(), past_ttl.refresh_from_db()
        self.assertEqual((stale_payment.status, stale_payment.skip_reason), (S.SKIPPED, "stale:payment_resolved"))
        self.assertEqual((past_ttl.status, past_ttl.last_error), (S.EXPIRED, "ttl_exceeded"))
        deliver_pending()
        self.assertEqual(FakeTransport.sent, [])

    def test_security_hold_window_is_shorter_than_transactional(self):
        self.assertEqual(expiry.policy_for("account.sensitive_changed").hold_hours, 24)
        self.assertEqual(expiry.policy_for("return.approved").hold_hours, 72)
        self.assertEqual(expiry.policy_for("coupon.issued").hold_hours, 24)

    @override_settings(RASTISI_EMAIL_HOLD_MAX_HOURS=10)
    def test_hold_window_is_configurable_but_never_exceeds_the_ttl(self):
        self.assertEqual(expiry.policy_for("return.approved").hold_hours, 10)
        self.assertLessEqual(expiry.policy_for("payment.failed").hold_hours, expiry.policy_for("payment.failed").ttl_hours)


class UiExposureTests(CouponViewsTestCase):
    def setUp(self):
        super().setUp()
        give_active_sender(self.store)

    def test_history_explains_expired_and_stale_rows_in_persian_and_filters_by_status(self):
        NotificationOutbox.objects.create(channel="email", store=self.store, event_key="order.created", subject="s", body="b",
                                          recipient_email="a@b.co", status="expired", last_error="ttl_exceeded")
        NotificationOutbox.objects.create(channel="email", store=self.store, event_key="payment.failed", subject="s", body="b",
                                          recipient_email="a@b.co", status="skipped", skip_reason="stale:payment_resolved")
        NotificationOutbox.objects.create(channel="email", store=self.store, event_key="order.shipped", subject="s", body="b",
                                          recipient_email="a@b.co", status="dead", last_error="sender_not_active_expired")
        page = self.client.get(reverse("dashboard:notification-history"))
        self.assertContains(page, "مهلتِ اعتبارِ این پیام گذشته است")
        self.assertContains(page, "پرداختِ سفارش در این فاصله تعیین تکلیف شده است")
        self.assertContains(page, "مهلتِ نگه‌داری تمام شد")
        self.assertContains(self.client.get(reverse("dashboard:notification-history") + "?status=expired"), "ttl_exceeded")
        self.assertNotContains(self.client.get(reverse("dashboard:notification-history") + "?status=sent"), "ttl_exceeded")

    def test_retry_post_is_refused_for_expired_rows(self):
        row = NotificationOutbox.objects.create(channel="email", store=self.store, event_key="order.created", subject="s", body="b",
                                                recipient_email="a@b.co", status="expired", last_error="ttl_exceeded")
        self.client.post(reverse("dashboard:notification-retry", args=[row.pk]))
        row.refresh_from_db()
        self.assertEqual(row.status, "expired")  # not re-queued
        page = self.client.get(reverse("dashboard:notification-history") + "?status=expired")
        self.assertNotContains(page, reverse("dashboard:notification-retry", args=[row.pk]))  # and no retry button offered


class SmsRastiQueueAgeTests(CouponViewsTestCase):
    def test_stale_device_queue_items_are_failed_not_delivered_and_fresh_ones_still_are(self):
        from django.test import Client

        from apps.core.models import ShopSettings
        from apps.sms.models import SmsOutboxItem

        shop = ShopSettings.load(store=self.store)
        shop.smsrasti_device_token = "devtoken"
        shop.save()
        old = SmsOutboxItem.objects.create(store=self.store, phone="09120000001", message="قدیمی")
        SmsOutboxItem.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=80))
        fresh = SmsOutboxItem.objects.create(store=self.store, phone="09120000002", message="تازه")
        resp = Client().get(reverse("sms:smsrasti-poll"), {"token": "devtoken"})
        old.refresh_from_db(), fresh.refresh_from_db()
        self.assertEqual(old.status, SmsOutboxItem.Status.FAILED)
        self.assertIn("منقضی", old.error_message)
        self.assertNotIn("قدیمی", resp.content.decode())
        self.assertEqual(fresh.status, SmsOutboxItem.Status.SENDING)
        self.assertIn("تازه", resp.content.decode())

    def test_otp_never_uses_the_device_queue_even_when_the_store_uses_the_phone_gateway(self):
        from unittest.mock import patch

        from apps.core.models import ShopSettings
        from apps.sms.models import SmsOutboxItem
        from apps.sms.services.backends import SmsSendResult
        from apps.sms.models import SmsBalance, SmsTemplate
        from apps.sms.services.sms_service import send_event_sms

        SmsTemplate.ensure_defaults()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        shop = ShopSettings.load(store=self.store)
        shop.sms_backend = ShopSettings.SmsBackend.SMSRASTI
        shop.smsrasti_device_token = "devtoken"
        shop.save()
        with patch("apps.portal.services.owner_sms_service.send_platform_otp", return_value=SmsSendResult(True, "x")) as central:
            send_event_sms("otp", "09120000003", {"otp_code": "123456"}, store=self.store)
        self.assertTrue(central.called)
        self.assertFalse(SmsOutboxItem.objects.exists())


class HealthCheckTests(Base):
    """A broken store sender must not look like a dead delivery cron (false CRITICAL), but must be visible."""

    def checks(self):
        from apps.core.management.commands.check_background_jobs import collect

        return {c["check"]: c for c in collect()}

    def test_held_mail_is_not_reported_as_a_stuck_backlog_but_is_reported_as_held(self):
        from apps.notifications.models import EmailSenderIdentity

        EmailSenderIdentity.objects.filter(store=self.store).update(status="inactive")
        row = self.row("return.approved", age_hours=5)
        NotificationOutbox.objects.filter(pk=row.pk).update(held_since=timezone.now() - timedelta(hours=5), last_error="sender_not_active")
        c = self.checks()
        self.assertEqual(c["notification_backlog"]["level"], "OK")
        self.assertEqual(c["email_held"]["level"], "WARNING")
        self.assertIn("held=1", c["email_held"]["detail"])

    def test_a_genuinely_stuck_unheld_row_is_still_critical(self):
        row = self.row("return.approved", age_hours=5)
        self.assertEqual(self.checks()["notification_backlog"]["level"], "CRITICAL")

    def test_sender_errors_expired_rows_and_missing_revalidation_cron_are_visible(self):
        EmailSenderIdentity = __import__("apps.notifications.models", fromlist=["x"]).EmailSenderIdentity
        EmailSenderIdentity.objects.filter(store=self.store).update(status="error", next_check_at=timezone.now() - timedelta(hours=9))
        self.row("order.created", age_hours=200, status=S.EXPIRED)
        c = self.checks()
        self.assertEqual(c["email_sender_errors"]["level"], "WARNING")
        self.assertEqual(c["email_sender_revalidation"]["level"], "WARNING")
        self.assertEqual(c["notification_expired_24h"]["level"], "WARNING")

    def test_all_clear_when_nothing_is_wrong(self):
        c = self.checks()
        for name in ("email_held", "notification_expired_24h", "email_sender_errors", "email_sender_revalidation"):
            self.assertEqual(c[name]["level"], "OK", name)
