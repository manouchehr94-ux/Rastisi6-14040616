"""Section 16 — the notification outbox: enqueue is always durable (never
sends anything itself), delivery is the only place that actually sends,
and a failed send never loses the notification (it becomes retryable
FAILED, not silently dropped)."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.notifications.models import NotificationOutbox
from apps.notifications.services.notification_service import deliver_pending, enqueue, notify_security_event

User = get_user_model()


class EnqueueTests(TestCase):
    def test_enqueue_creates_a_pending_row_without_sending_anything(self):
        with patch("apps.portal.services.owner_sms_service.send_platform_sms") as mock_send:
            notification = enqueue(channel=NotificationOutbox.Channel.SMS, body="hello", recipient_phone="0912")
        mock_send.assert_not_called()
        self.assertEqual(notification.status, NotificationOutbox.Status.PENDING)


class DeliverPendingTests(TestCase):
    def test_in_app_notification_is_marked_sent_without_any_external_call(self):
        user = User.objects.create_user(username="09121340011", password="a-very-strong-pass-1")
        enqueue(channel=NotificationOutbox.Channel.IN_APP, body="متن", recipient_user=user)
        result = deliver_pending()
        self.assertEqual(result, {"processed": 1, "sent": 1, "failed": 0, "skipped": 0})
        notification = NotificationOutbox.objects.get(recipient_user=user)
        self.assertEqual(notification.status, NotificationOutbox.Status.SENT)
        self.assertIsNotNone(notification.sent_at)

    def test_sms_delivery_success_marks_sent(self):
        from apps.sms.services.backends import SmsSendResult

        enqueue(channel=NotificationOutbox.Channel.SMS, body="کد شما", recipient_phone="09121340099")
        with patch("apps.portal.services.owner_sms_service.send_platform_sms") as mock_send:
            mock_send.return_value = SmsSendResult(success=True, provider_ref_id="x")
            result = deliver_pending()
        self.assertEqual(result["sent"], 1)
        notification = NotificationOutbox.objects.get(recipient_phone="09121340099")
        self.assertEqual(notification.status, NotificationOutbox.Status.SENT)

    def test_sms_delivery_failure_is_retryable_not_lost(self):
        from apps.sms.services.backends import SmsSendResult

        enqueue(channel=NotificationOutbox.Channel.SMS, body="کد شما", recipient_phone="09121340088")
        with patch("apps.portal.services.owner_sms_service.send_platform_sms") as mock_send:
            mock_send.return_value = SmsSendResult(success=False, error_message="گیت‌وی در دسترس نیست")
            result = deliver_pending()
        self.assertEqual(result["failed"], 1)
        notification = NotificationOutbox.objects.get(recipient_phone="09121340088")
        self.assertEqual(notification.status, NotificationOutbox.Status.FAILED)
        self.assertIn("گیت‌وی", notification.last_error)
        self.assertEqual(notification.attempts, 1)

        # Still exists, still retryable on a subsequent run — never deleted.
        self.assertTrue(NotificationOutbox.objects.filter(recipient_phone="09121340088").exists())

    def test_email_delivery_uses_django_send_mail(self):
        enqueue(
            channel=NotificationOutbox.Channel.EMAIL, subject="موضوع", body="متن",
            recipient_email="test@example.com",
        )
        result = deliver_pending()
        self.assertEqual(result["sent"], 1)
        from django.core import mail

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["test@example.com"])

    def test_one_failure_does_not_block_the_rest_of_the_batch(self):
        from apps.sms.services.backends import SmsSendResult

        enqueue(channel=NotificationOutbox.Channel.SMS, body="a", recipient_phone="0001")
        enqueue(channel=NotificationOutbox.Channel.EMAIL, subject="s", body="b", recipient_email="ok@example.com")
        with patch("apps.portal.services.owner_sms_service.send_platform_sms") as mock_send:
            mock_send.return_value = SmsSendResult(success=False, error_message="fail")
            result = deliver_pending()
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["sent"], 1)

    def test_already_sent_notifications_are_not_reprocessed(self):
        enqueue(channel=NotificationOutbox.Channel.IN_APP, body="متن")
        deliver_pending()
        result = deliver_pending()
        self.assertEqual(result["processed"], 0)


class NotifySecurityEventTests(TestCase):
    def test_creates_both_in_app_and_sms_when_both_provided(self):
        user = User.objects.create_user(username="09121340077", password="a-very-strong-pass-1")
        created = notify_security_event(
            subject="هشدارِ امنیتی", body="یک عملیاتِ حساس انجام شد", user=user, phone="09121340077",
        )
        self.assertEqual(len(created), 2)
        channels = {n.channel for n in created}
        self.assertEqual(channels, {NotificationOutbox.Channel.IN_APP, NotificationOutbox.Channel.SMS})
        self.assertTrue(all(n.is_security for n in created))

    def test_only_sms_when_no_user_account_yet(self):
        created = notify_security_event(subject="s", body="b", phone="09121340066")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].channel, NotificationOutbox.Channel.SMS)
