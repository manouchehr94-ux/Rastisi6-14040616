"""Email workflow through the REAL Django SMTP transport against a local in-process SMTP sink (127.0.0.1, random port).

This proves our code speaks SMTP correctly (headers, multipart, recipients, failure → retry/backoff → single re-send); it does NOT
prove a real provider/account/domain (SPF/DKIM/DMARC, reputation, inbox placement) — that needs operator verification."""

import asyncore
import smtpd
import socket
import threading
import warnings
from datetime import timedelta
from email import message_from_bytes

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.notifications.models import NotificationOutbox
from apps.notifications.services.dispatcher import dispatch_event
from apps.notifications.services.notification_service import deliver_pending
from apps.stores.models import Store

User = get_user_model()
warnings.filterwarnings("ignore", category=DeprecationWarning)


class Sink(smtpd.SMTPServer):
    received: list

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        self.received.append((mailfrom, rcpttos, data))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SmtpSink:
    def __init__(self, port):
        self.received = []
        Sink.received = self.received
        self.server = Sink(("127.0.0.1", port), None, decode_data=False)
        self.map = {}
        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def loop(self):
        while self.running:
            asyncore.loop(timeout=0.1, count=1)

    def stop(self):
        self.running = False
        self.thread.join(2)
        self.server.close()
        asyncore.close_all()


class EmailTransportTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09125550777", password="x12345678")
        self.customer = Customer.objects.create(
            user=user, full_name="سارا", phone="09125550777", email="sara@example.com",
            accepts_promotional_sms=True, accepts_promotional_email=True,
        )
        self.port = free_port()
        self.ctx = {"order_number": "DM-1", "order_total": "1", "order_status": "x", "order_url": "", "customer_name": "سارا",
                    "return_number": "R1", "reason": ""}
        self.settings_override = override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="127.0.0.1", EMAIL_PORT=self.port,
            EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="", EMAIL_USE_TLS=False, DEFAULT_FROM_EMAIL="shop@example.test",
            EMAIL_TIMEOUT=3,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def queue(self):
        rows = dispatch_event("return.approved", store=self.store, customer=self.customer, context=self.ctx, channels=["email"], dedupe_key="smtp-1")
        self.assertEqual([r.status for r in rows], ["pending"])
        return rows[0]

    def test_message_is_delivered_over_smtp_with_correct_envelope_and_multipart_once(self):
        sink = SmtpSink(self.port)
        self.addCleanup(sink.stop)
        row = self.queue()
        result = deliver_pending()
        deliver_pending()  # a second worker run never re-sends a SENT row
        row.refresh_from_db()
        self.assertEqual((result["sent"], row.status, row.provider), (1, "sent", "email"))
        self.assertEqual(len(sink.received), 1)
        mailfrom, rcpt, data = sink.received[0]
        self.assertEqual((mailfrom, rcpt), ("shop@example.test", ["sara@example.com"]))
        msg = message_from_bytes(data)
        self.assertEqual(msg["To"], "sara@example.com")
        self.assertTrue(msg.is_multipart())
        self.assertEqual({p.get_content_type() for p in msg.walk() if not p.is_multipart()}, {"text/plain", "text/html"})
        self.assertNotIn("راستی", str(msg["Subject"]))  # store message — no platform branding added

    def test_unreachable_server_fails_with_backoff_then_recovers_with_exactly_one_send(self):
        row = self.queue()  # nothing is listening on the port
        result = deliver_pending()
        row.refresh_from_db()
        self.assertEqual((result["failed"], row.status, row.attempts), (1, "failed", 1))
        self.assertIsNotNone(row.next_attempt_at)
        self.assertGreater(row.next_attempt_at, timezone.now())
        self.assertNotIn("S3CRET", row.last_error)
        self.assertEqual(deliver_pending()["processed"], 0)  # not due yet: no hammering
        sink = SmtpSink(self.port)  # provider comes back
        self.addCleanup(sink.stop)
        NotificationOutbox.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, len(sink.received)), ("sent", 1))

    def test_invalid_recipient_is_skipped_at_dispatch_and_never_reaches_smtp(self):
        self.customer.email = "not-an-email"
        self.customer.save()
        rows = dispatch_event("return.approved", store=self.store, customer=self.customer, context=self.ctx, channels=["email"], dedupe_key="smtp-bad")
        self.assertEqual([(r.status, r.skip_reason) for r in rows], [("skipped", "invalid_recipient")])

    def test_withdrawn_promotional_consent_blocks_the_smtp_send(self):
        from apps.customers.services import consent_service

        sink = SmtpSink(self.port)
        self.addCleanup(sink.stop)
        ctx = {"discount_code": "G", "discount_amount": "x", "discount_max": "", "discount_expires_at": "x",
               "campaign_name": "c", "occasion_name": "o", "customer_name": "سارا"}
        (row,) = dispatch_event("coupon.issued", store=self.store, customer=self.customer, context=ctx, channels=["email"], dedupe_key="smtp-promo")
        consent_service.set_promotional_consent(self.customer, source="account", email=False)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.skip_reason, len(sink.received)), ("skipped", "consent_withdrawn", 0))
