"""سیستمِ اعلانِ رویدادمحور: قالب، توزیع، رضایت، dedupe، تحویل، retry."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.customers.models import Customer
from apps.notifications import events as ev
from apps.notifications.models import NotificationOutbox, NotificationTemplate
from apps.notifications.services import template_service as ts
from apps.notifications.services.dispatcher import dispatch_event, safe_dispatch
from apps.notifications.services.notification_service import (
    RetryNotAllowed, deliver_pending, retry_notification, sanitize_error,
)
from apps.sms.models import SmsLog
from apps.stores.models import Store, StoreMembership

User = get_user_model()
S = NotificationOutbox.Status


class Base(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09120001111", password="x12345678")
        self.customer = Customer.objects.create(
            user=user, full_name="سارا", phone="09120001111", email="sara@example.com",
            accepts_promotional_sms=True, accepts_promotional_email=True,  # رضایتِ ثبت‌شده (پیش‌فرضِ جدید: بدونِ رضایت)
        )
        self.ctx = {"discount_code": "GIFT-1", "discount_amount": "۳۰٪", "discount_max": "", "discount_expires_at": "۱۴۰۵/۱/۱",
                    "campaign_name": "کمپین", "occasion_name": "مناسبت", "customer_name": "سارا"}


class TemplateServiceTests(Base):
    def test_unknown_variable_rejected(self):
        with self.assertRaises(ts.TemplateError) as cm:
            ts.validate_text("order.created", "سلام {customer_name} {password}")
        self.assertIn("{password}", str(cm.exception))

    def test_attribute_access_and_stray_braces_rejected(self):
        for bad in ["{customer_name.__class__}", "{0}", "{", "abc}", "{ customer_name }"]:
            with self.assertRaises(ts.TemplateError, msg=bad):
                ts.validate_text("order.created", bad)

    def test_render_and_missing(self):
        text, missing = ts.render_text("{a} و {b}", {"a": "x"})
        self.assertEqual((text, missing), ("x و ", ["b"]))
        text, missing = ts.render_text("{a}", {"a": ""})
        self.assertEqual((text, missing), ("", []))

    def test_html_escape_only_for_html(self):
        self.assertEqual(ts.render_text("{a}", {"a": "<b>"}, html=True)[0], "&lt;b&gt;")
        self.assertEqual(ts.render_text("{a}", {"a": "<b>"})[0], "<b>")

    def test_example_template_from_spec(self):
        body = "Dear {customer_name}, your order {order_number} has been successfully created. Order total: {order_total}. Thank you for shopping with us."
        ts.validate_text("order.created", body)
        text, missing = ts.render_text(body, {"customer_name": "Sara", "order_number": "DM-1", "order_total": "100"})
        self.assertEqual(missing, [])
        self.assertIn("order DM-1 has been", text)

    def test_every_event_default_template_is_valid(self):
        for key, event in ev.EVENTS.items():
            ts.validate_text(key, event.default_sms, what=key)
            ts.validate_text(key, event.default_email_subject, what=key)
            ts.validate_text(key, event.default_email_body, what=key)
            text, missing = ts.render_text(event.default_sms, event.sample)
            self.assertEqual(missing, [], key)

    def test_save_and_reset_and_preview(self):
        ts.save_template(self.store, "order.created", "email", enabled=True, subject="سفارش {order_number}", body="سلام {customer_name}")
        tpl = ts.get_template(self.store, "order.created", "email")
        self.assertTrue(tpl["customized"])
        self.assertEqual(ts.preview(self.store, "order.created", "email")["subject"], "سفارش DM-12345")
        with self.assertRaises(ts.TemplateError):
            ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="{nope}")
        with self.assertRaises(ts.TemplateError):
            ts.save_template(self.store, "order.created", "sms", enabled=True, subject="", body="  ")
        ts.reset_template(self.store, "order.created", "email")
        self.assertFalse(ts.get_template(self.store, "order.created", "email")["customized"])

    def test_templates_are_store_scoped(self):
        other = Store.objects.create(name="دیگر", slug="notif-other", status=Store.Status.ACTIVE)
        ts.save_template(self.store, "order.created", "email", enabled=True, subject="الف", body="ب {order_number}")
        self.assertFalse(ts.get_template(other, "order.created", "email")["customized"])


class DispatchTests(Base):
    def _dispatch(self, key="coupon.issued", **kw):
        return dispatch_event(key, store=self.store, customer=self.customer, context=self.ctx, **kw)

    def test_creates_sms_and_email_rows_pending(self):
        rows = self._dispatch()
        self.assertEqual({r.channel for r in rows}, {"sms", "email"})
        self.assertTrue(all(r.status == S.PENDING for r in rows))
        sms = next(r for r in rows if r.channel == "sms")
        self.assertEqual(sms.recipient_phone, "09120001111")
        self.assertIn("GIFT-1", sms.body)
        self.assertEqual(sms.event_key, "coupon.issued")
        self.assertEqual(sms.customer, self.customer)
        self.assertTrue(sms.is_promotional)

    def test_nothing_is_sent_by_dispatch(self):
        with patch("apps.notifications.services.notification_service._deliver_one") as m:
            self._dispatch()
        m.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_disabled_channel_not_created(self):
        ts.save_template(self.store, "coupon.issued", "sms", enabled=False, subject="", body="{discount_code}")
        rows = self._dispatch()
        self.assertEqual({r.channel for r in rows}, {"email"})

    def test_custom_template_used(self):
        ts.save_template(self.store, "coupon.issued", "sms", enabled=True, subject="", body="کد: {discount_code}")
        sms = next(r for r in self._dispatch() if r.channel == "sms")
        self.assertEqual(sms.body, "کد: GIFT-1")

    def test_promotional_requires_consent_per_channel(self):
        self.customer.accepts_promotional_sms = False
        self.customer.save()
        rows = self._dispatch()
        by = {r.channel: r for r in rows}
        self.assertEqual(by["sms"].status, S.SKIPPED)
        self.assertEqual(by["sms"].skip_reason, "no_promotional_consent")
        self.assertEqual(by["email"].status, S.PENDING)
        deliver_pending()
        by["sms"].refresh_from_db()
        self.assertEqual(by["sms"].status, S.SKIPPED)  # never delivered
        self.assertEqual(len(mail.outbox), 1)

    def test_transactional_ignores_promotional_consent(self):
        self.customer.accepts_promotional_sms = False
        self.customer.accepts_promotional_email = False
        self.customer.save()
        ctx = {"order_number": "DM-1", "order_total": "1", "order_status": "x", "order_url": "", "customer_name": "س",
               "return_number": "R1", "reason": ""}
        rows = dispatch_event("return.approved", store=self.store, customer=self.customer, context=ctx)
        self.assertEqual([r.status for r in rows], [S.PENDING, S.PENDING])

    def test_security_events_flagged_and_ignore_consent(self):
        self.customer.accepts_promotional_sms = False
        self.customer.save()
        rows = dispatch_event("account.sensitive_changed", store=self.store, customer=self.customer,
                              context={"customer_name": "س", "changed_field": "ایمیل"})
        self.assertTrue(all(r.is_security and not r.is_promotional for r in rows))
        self.assertTrue(all(r.status == S.PENDING for r in rows))

    def test_legacy_sms_events_only_create_email(self):
        ctx = {"order_number": "DM-1", "order_total": "1", "order_status": "x", "order_url": "", "customer_name": "س"}
        rows = dispatch_event("order.created", store=self.store, customer=self.customer, order=None, context=ctx)
        self.assertEqual({r.channel for r in rows}, {"email"})

    def test_invalid_recipient_skipped(self):
        self.customer.email = "not-an-email"
        self.customer.phone = "123"
        rows = self._dispatch()
        self.assertEqual({r.skip_reason for r in rows}, {"invalid_recipient"})
        self.assertTrue(all(r.status == S.SKIPPED for r in rows))

    def test_blank_email_creates_no_row(self):
        self.customer.email = ""
        rows = self._dispatch()
        self.assertEqual({r.channel for r in rows}, {"sms"})

    def test_unresolved_variable_never_sent(self):
        ctx = dict(self.ctx)
        ctx.pop("discount_code")
        rows = dispatch_event("coupon.issued", store=self.store, customer=self.customer, context=ctx)
        self.assertTrue(all(r.status == S.SKIPPED and r.skip_reason.startswith("unresolved_variables:") for r in rows))

    def test_dedupe_prevents_duplicates(self):
        first = self._dispatch(dedupe_key="issuance:1")
        second = self._dispatch(dedupe_key="issuance:1")
        self.assertEqual(len(first), 2)
        self.assertEqual(second, [])
        self.assertEqual(NotificationOutbox.objects.count(), 2)
        third = self._dispatch(dedupe_key="issuance:2")
        self.assertEqual(len(third), 2)

    def test_staff_event_uses_extra_recipients_and_owner_email(self):
        owner = User.objects.create_user(username="own", password="x12345678", email="owner@example.com")
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        NotificationTemplate.objects.create(
            store=self.store, event_key="staff.order_created", channel="email", is_enabled=True,
            subject="سفارش {order_number}", body="{order_number} {customer_name} {order_total} {gift_wrap_note} {store_name}",
            extra_recipients="ops@example.com\nbad-address",
        )
        rows = dispatch_event("staff.order_created", store=self.store, context={
            "order_number": "DM-1", "customer_name": "س", "order_total": "1", "gift_wrap_note": ""})
        by_recipient = {r.recipient_email: r.status for r in rows}
        self.assertEqual(by_recipient["ops@example.com"], S.PENDING)
        self.assertEqual(by_recipient["owner@example.com"], S.PENDING)
        self.assertEqual(by_recipient["bad-address"], S.SKIPPED)

    def test_staff_events_disabled_by_default(self):
        rows = dispatch_event("staff.order_created", store=self.store, context={
            "order_number": "DM-1", "customer_name": "س", "order_total": "1", "gift_wrap_note": ""})
        self.assertEqual(rows, [])

    def test_safe_dispatch_swallows_errors(self):
        self.assertEqual(safe_dispatch("no.such.event", store=self.store), [])

    def test_test_send_ignores_consent_and_flags_row(self):
        self.customer.accepts_promotional_email = False
        self.customer.save()
        rows = dispatch_event("coupon.issued", store=self.store, customer=None, context=self.ctx,
                              is_test=True, test_recipient="qa@example.com", channels=["email"])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].is_test)
        self.assertEqual(rows[0].status, S.PENDING)


class DeliveryTests(Base):
    def _row(self, channel="email", **kw):
        return NotificationOutbox.objects.create(
            channel=channel, store=self.store, body="متن", subject="موضوع", recipient_email="a@example.com",
            recipient_phone="09120001111", event_key="coupon.issued", **kw,
        )

    def test_email_delivery_is_rtl_html_with_store_name(self):
        self._row()
        deliver_pending()
        msg = mail.outbox[0]
        html = msg.alternatives[0][0]
        self.assertIn('dir="rtl"', html)
        self.assertIn(self.store.name, html)
        self.assertEqual(msg.body, "متن")

    def test_html_in_body_is_escaped(self):
        NotificationOutbox.objects.create(channel="email", store=self.store, subject="s", body="<script>x</script>",
                                          recipient_email="a@example.com")
        deliver_pending()
        self.assertNotIn("<script>", mail.outbox[0].alternatives[0][0])

    def test_sms_provider_recorded(self):
        row = self._row("sms")
        log = SmsLog(status=SmsLog.Status.SENT, provider="kavenegar", provider_ref_id="r-1")
        with patch("apps.sms.services.sms_service.send_raw_sms", return_value=log):
            deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.provider, row.provider_ref), (S.SENT, "kavenegar", "r-1"))
        self.assertIsNotNone(row.sent_at)

    def test_failure_backoff_then_retry_then_dead(self):
        row = self._row("sms", max_attempts=2)
        bad = SmsLog(status=SmsLog.Status.FAILED, error_message="خطا برای 09120001111")
        now = timezone.now()
        with patch("apps.sms.services.sms_service.send_raw_sms", return_value=bad):
            deliver_pending(now=now)
            row.refresh_from_db()
            self.assertEqual(row.status, S.FAILED)
            self.assertEqual(row.attempts, 1)
            self.assertGreater(row.next_attempt_at, now)
            self.assertNotIn("09120001111", row.last_error)  # masked
            # not yet due → untouched
            self.assertEqual(deliver_pending(now=now)["processed"], 0)
            # due → second attempt exhausts the cap
            deliver_pending(now=row.next_attempt_at + timedelta(seconds=1))
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), (S.DEAD, 2))
        # DEAD rows are not picked again
        with patch("apps.sms.services.sms_service.send_raw_sms", return_value=bad) as m:
            deliver_pending(now=now + timedelta(days=2))
        m.assert_not_called()

    def test_manual_retry_allows_one_more_attempt(self):
        row = self._row("sms", max_attempts=1)
        bad = SmsLog(status=SmsLog.Status.FAILED, error_message="x")
        with patch("apps.sms.services.sms_service.send_raw_sms", return_value=bad):
            deliver_pending()
            row.refresh_from_db()
            self.assertEqual(row.status, S.DEAD)
            retry_notification(row)
            row.refresh_from_db()
            self.assertEqual(row.status, S.PENDING)
            self.assertEqual(row.max_attempts, 2)
        ok = SmsLog(status=SmsLog.Status.SENT, provider="p")
        with patch("apps.sms.services.sms_service.send_raw_sms", return_value=ok):
            deliver_pending()
        row.refresh_from_db()
        self.assertEqual(row.status, S.SENT)

    def test_cannot_retry_sent_or_skipped(self):
        for status in (S.SENT, S.SKIPPED, S.PENDING):
            row = self._row(status=status)
            with self.assertRaises(RetryNotAllowed):
                retry_notification(row)

    def test_stale_sending_claim_is_reclaimed_but_fresh_one_is_not(self):
        fresh = self._row(status=S.SENDING, claimed_at=timezone.now())
        stale = self._row(status=S.SENDING, claimed_at=timezone.now() - timedelta(minutes=30))
        deliver_pending()
        fresh.refresh_from_db()
        stale.refresh_from_db()
        self.assertEqual(fresh.status, S.SENDING)
        self.assertEqual(stale.status, S.SENT)

    def test_sanitize_error_masks_pii(self):
        text = sanitize_error("fail 09123456789 to a@b.com " + "x" * 500)
        self.assertNotIn("09123456789", text)
        self.assertNotIn("a@b.com", text)
        self.assertLessEqual(len(text), 300)
