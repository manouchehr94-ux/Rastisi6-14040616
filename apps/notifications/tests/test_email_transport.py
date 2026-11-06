"""Email workflow through the REAL Django SMTP transport against a local in-process SMTP sink (127.0.0.1, random port).

This proves our code speaks SMTP correctly (headers, multipart, recipients, failure → retry/backoff → single re-send); it does NOT
prove a real provider/account/domain (SPF/DKIM/DMARC, reputation, inbox placement) — that needs operator verification."""

import socket
import socketserver
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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SmtpHandler(socketserver.StreamRequestHandler):
    """Just enough SMTP for Django's backend: EHLO/HELO, MAIL, RCPT, DATA, RSET, NOOP, QUIT. (``smtpd``/``asyncore`` were removed in Python 3.12, which is why this
    sink is a plain ``socketserver`` one — same interface as before: ``received`` holds ``(mailfrom, [recipients], raw message bytes)``.)"""

    def reply(self, text):
        self.wfile.write(text.encode() + b"\r\n")
        self.wfile.flush()

    def handle(self):
        mailfrom, rcpts = "", []
        self.reply("220 localhost test SMTP sink")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            cmd = line.decode("utf-8", "replace").strip()
            upper = cmd.upper()
            if upper.startswith(("EHLO", "HELO")):
                self.reply("250 localhost")
            elif upper.startswith("MAIL FROM:"):
                mailfrom, rcpts = cmd[10:].strip().split(" ")[0].strip("<>"), []
                self.reply("250 OK")
            elif upper.startswith("RCPT TO:"):
                rcpts.append(cmd[8:].strip().split(" ")[0].strip("<>"))
                self.reply("250 OK")
            elif upper == "DATA":
                self.reply("354 End data with <CR><LF>.<CR><LF>")
                chunks = []
                while True:
                    row = self.rfile.readline()
                    if not row or row in (b".\r\n", b".\n"):
                        break
                    chunks.append(row[1:] if row.startswith(b"..") else row)       # dot-unstuffing
                data = b"".join(chunks).replace(b"\r\n", b"\n")
                self.server.received.append((mailfrom, list(rcpts), data))
                self.reply("250 OK queued")
            elif upper == "RSET":
                mailfrom, rcpts = "", []
                self.reply("250 OK")
            elif upper == "NOOP":
                self.reply("250 OK")
            elif upper == "QUIT":
                self.reply("221 Bye")
                return
            else:
                self.reply("502 Command not implemented")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SmtpSink:
    def __init__(self, port):
        self.received = []
        self.server = _Server(("127.0.0.1", port), _SmtpHandler)
        self.server.received = self.received
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


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
        """Platform-originated email (no Store): the Django SMTP path. Store->customer email goes through the
        per-store verified sender (see test_store_sender_policy) and never through this shared SMTP sender."""
        from apps.notifications.services.notification_service import enqueue

        row = enqueue(channel="email", subject="تغییر امنیتی", body="متن تست", recipient_email="sara@example.com")
        self.assertEqual(row.status, "pending")
        return row

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
        self.assertEqual(msg["From"], "shop@example.test")

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
