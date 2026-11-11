"""SES / SNS authenticity, webhook handling, bounce/complaint/suppression, duplicate delivery, provider failures,
rate limits, recipient/tenant isolation and template-injection safety. No network, no real email."""

import base64
import json
import threading
from datetime import datetime, timedelta, timezone as dt_tz
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.customers.models import Customer
from apps.notifications import webhook_views
from apps.notifications.mail import events_service as es
from apps.notifications.mail import sns
from apps.notifications.mail.base import SendOutcome
from apps.notifications.mail.fake import FakeTransport
from apps.notifications.models import EmailProviderEvent, EmailSuppression, NotificationOutbox
from apps.notifications.services import template_service as ts
from apps.notifications.services.dispatcher import dispatch_event, safe_dispatch
from apps.notifications.services.notification_service import _claim_batch, deliver_pending
from apps.notifications.tests.helpers import give_active_sender
from apps.stores.models import Store
from apps.core.tests.serialized_rollback import SerializedRollbackSafeMixin

User = get_user_model()
S = NotificationOutbox.Status
TOPIC = "arn:aws:sns:eu-west-1:123456789012:rastisi-ses-events"
CERT_URL = "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-abc.pem"


def make_key_and_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.eu-west-1.amazonaws.com")])
    now = datetime.now(dt_tz.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30)).sign(key, hashes.SHA256()))
    return key, cert.public_bytes(serialization.Encoding.PEM)


KEY, CERT_PEM = make_key_and_cert()
OTHER_KEY, _ = make_key_and_cert()


def sign(payload: dict, *, key=KEY, version="2") -> dict:
    payload = {**payload, "SignatureVersion": version, "SigningCertURL": CERT_URL}
    algo = hashes.SHA256() if version == "2" else hashes.SHA1()  # noqa: S303
    sig = key.sign(sns.string_to_sign(payload).encode(), padding.PKCS1v15(), algo)
    payload["Signature"] = base64.b64encode(sig).decode()
    return payload


def notification(message: dict, **extra) -> dict:
    return sign({
        "Type": "Notification", "MessageId": "m-" + str(abs(hash(json.dumps(message, sort_keys=True)))),
        "TopicArn": TOPIC, "Message": json.dumps(message), "Timestamp": "2026-11-04T10:00:00.000Z", **extra,
    })


FETCH = lambda url: CERT_PEM  # noqa: E731


@override_settings(RASTISI_SES_SNS_TOPIC_ARNS=(TOPIC,))
class SnsVerificationTests(TestCase):
    def test_valid_v2_and_v1_signatures_are_accepted(self):
        for version in ("2", "1"):
            sns.verify_sns_message(sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x",
                                         "Timestamp": "t"}, version=version), cert_fetcher=FETCH)

    def test_optional_subject_is_part_of_the_signed_string(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t", "Subject": "s"})
        sns.verify_sns_message(p, cert_fetcher=FETCH)
        p["Subject"] = "tampered"
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=FETCH)

    def test_tampered_message_is_rejected(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})
        p["Message"] = "y"
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=FETCH)

    def test_signature_from_a_different_key_is_rejected(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"}, key=OTHER_KEY)
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=FETCH)

    def test_foreign_topic_is_rejected_even_if_validly_signed(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": "arn:aws:sns:eu-west-1:999:evil", "Message": "x",
                  "Timestamp": "t"})
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=FETCH)

    @override_settings(RASTISI_SES_SNS_TOPIC_ARNS=())
    def test_no_allowlist_configured_rejects_everything(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=FETCH)

    def test_untrusted_certificate_urls_are_rejected_before_any_fetch(self):
        base = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})
        bad_urls = [
            "http://sns.eu-west-1.amazonaws.com/cert.pem",                    # not https
            "https://evil.test/sns.eu-west-1.amazonaws.com/cert.pem",         # wrong host
            "https://sns.eu-west-1.amazonaws.com.evil.test/cert.pem",         # suffix trick
            "https://evilsns.eu-west-1.amazonaws.com/cert.pem",               # prefix trick
            "https://sns.eu-west-1.amazonaws.com:8443/cert.pem",              # non-443 port
            "https://user@evil.test/cert.pem", "", "ftp://sns.eu-west-1.amazonaws.com/c.pem",
        ]
        for url in bad_urls:
            fetched = []
            with self.assertRaises(sns.SnsVerificationError, msg=url):
                sns.verify_sns_message({**base, "SigningCertURL": url}, cert_fetcher=lambda u: fetched.append(u) or CERT_PEM)
            self.assertEqual(fetched, [], f"must not fetch {url!r}")

    def test_unsupported_version_and_garbage_signature_are_rejected(self):
        base = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})
        for patch_ in ({"SignatureVersion": "3"}, {"Signature": "!!not base64!!"}, {"Signature": ""}):
            with self.assertRaises(sns.SnsVerificationError):
                sns.verify_sns_message({**base, **patch_}, cert_fetcher=FETCH)

    def test_certificate_fetch_failure_fails_closed(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})

        def boom(url):
            raise OSError("network down")

        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=boom)

    def test_garbage_certificate_fails_closed(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=lambda u: b"not a cert")

    def test_missing_required_field_is_rejected(self):
        p = sign({"Type": "Notification", "MessageId": "1", "TopicArn": TOPIC, "Message": "x", "Timestamp": "t"})
        del p["Timestamp"]
        with self.assertRaises(sns.SnsVerificationError):
            sns.verify_sns_message(p, cert_fetcher=FETCH)


PLATFORM_HOST = "rastisi.localhost"  # a member of RASTISI_PLATFORM_HOSTS: the only public, platform-owned host


@override_settings(RASTISI_SES_SNS_TOPIC_ARNS=(TOPIC,), ALLOWED_HOSTS=[PLATFORM_HOST, "platformadmins.rastisi.localhost",
                                                                       "mystore.rastisi.localhost", "testserver"])
class WebhookTests(TestCase):
    URL = "/notifications/email/ses-events/"

    def setUp(self):
        FakeTransport.reset()
        webhook_views.ses_sns_webhook.cert_fetcher = FETCH
        self.addCleanup(lambda: setattr(webhook_views.ses_sns_webhook, "cert_fetcher", None))
        self.client = Client(HTTP_HOST=PLATFORM_HOST)
        self.store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09128880001", password="x12345678")
        self.customer = Customer.objects.create(user=user, full_name="سارا", phone="09128880001", email="sara@example.com")
        give_active_sender(self.store)
        self.row = NotificationOutbox.objects.create(
            channel="email", store=self.store, customer=self.customer, recipient_email="sara@example.com", subject="s", body="b",
            status=S.SENT, provider="fake", provider_ref="msg-1", event_key="order.created", sent_at=timezone.now(),
        )

    def post(self, payload):
        return self.client.post(self.URL, data=json.dumps(payload), content_type="text/plain; charset=UTF-8")

    def bounce(self, kind="Permanent", rcpt="sara@example.com", mid="msg-1"):
        return {"notificationType": "Bounce", "mail": {"messageId": mid},
                "bounce": {"bounceType": kind, "bounceSubType": "General", "bouncedRecipients": [{"emailAddress": rcpt}]}}

    def test_endpoint_is_served_on_the_platform_host_only(self):
        """SNS must reach a stable platform-owned public host. The Platform Admin host (not public, own urlconf) and tenant
        hosts do not expose it, so a store's own domain can never be used to feed events."""
        signed = notification(self.bounce("Transient"))
        self.assertEqual(self.client.post(self.URL, data=json.dumps(signed), content_type="text/plain").status_code, 200)
        for host in ("platformadmins.rastisi.localhost", "mystore.rastisi.localhost"):
            r = Client(HTTP_HOST=host).post(self.URL, data=json.dumps(signed), content_type="text/plain")
            self.assertIn(r.status_code, (404, 403), host)
            self.assertNotEqual(r.content, b"ok 1", host)

    def test_unsigned_request_is_rejected_403_and_changes_nothing(self):
        r = self.post({"Type": "Notification", "TopicArn": TOPIC, "Message": json.dumps(self.bounce())})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_get_is_not_allowed_and_csrf_does_not_block_signed_posts(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True, HTTP_HOST=PLATFORM_HOST)
        r = csrf_client.post(self.URL, data=json.dumps(notification(self.bounce("Transient"))), content_type="text/plain")
        self.assertEqual(r.status_code, 200)

    def test_oversized_and_invalid_json_are_rejected(self):
        self.assertEqual(self.client.post(self.URL, data="x" * (300 * 1024), content_type="text/plain").status_code, 400)
        self.assertEqual(self.client.post(self.URL, data="{not json", content_type="text/plain").status_code, 400)
        self.assertEqual(self.client.post(self.URL, data="[1,2]", content_type="text/plain").status_code, 400)

    def test_permanent_bounce_marks_row_and_suppresses_recipient_for_that_store_only(self):
        other = Store.objects.create(name="دیگر", slug="sup-other", status=Store.Status.ACTIVE)
        self.assertEqual(self.post(notification(self.bounce("Permanent"))).status_code, 200)
        self.row.refresh_from_db()
        self.assertEqual(self.row.delivery_state, "bounced")
        self.assertTrue(EmailSuppression.objects.filter(store=self.store, email="sara@example.com", reason="bounce").exists())
        self.assertFalse(EmailSuppression.objects.filter(store=other).exists())  # tenant isolation

    def test_transient_bounce_is_recorded_but_does_not_suppress(self):
        self.post(notification(self.bounce("Transient")))
        self.row.refresh_from_db()
        self.assertEqual(self.row.delivery_state, "bounced")
        self.assertFalse(EmailSuppression.objects.exists())

    def test_complaint_suppresses(self):
        msg = {"notificationType": "Complaint", "mail": {"messageId": "msg-1"},
               "complaint": {"complaintFeedbackType": "abuse", "complainedRecipients": [{"emailAddress": "sara@example.com"}]}}
        self.post(notification(msg))
        self.row.refresh_from_db()
        self.assertEqual(self.row.delivery_state, "complained")
        self.assertTrue(EmailSuppression.objects.filter(reason="complaint").exists())

    def test_delivery_event_marks_delivered_and_never_downgrades_a_worse_state(self):
        msg = {"notificationType": "Delivery", "mail": {"messageId": "msg-1"}, "delivery": {"recipients": ["sara@example.com"]}}
        self.post(notification(msg))
        self.row.refresh_from_db()
        self.assertEqual(self.row.delivery_state, "delivered")
        self.post(notification(self.bounce("Transient")))
        self.post(notification(msg, MessageId="another"))
        self.row.refresh_from_db()
        self.assertEqual(self.row.delivery_state, "bounced")

    def test_duplicate_sns_delivery_is_idempotent(self):
        payload = notification(self.bounce("Permanent"))
        self.assertEqual(self.post(payload).content, b"ok 1")
        self.assertEqual(self.post(payload).content, b"ok 0")
        self.assertEqual(EmailProviderEvent.objects.count(), 1)
        self.assertEqual(EmailSuppression.objects.count(), 1)

    def test_event_for_an_unknown_message_id_creates_no_suppression_and_no_attribution(self):
        self.post(notification(self.bounce("Permanent", mid="not-ours")))
        self.assertFalse(EmailSuppression.objects.exists())
        ev = EmailProviderEvent.objects.get()
        self.assertIsNone(ev.store)

    def test_attacker_cannot_forge_attribution_by_putting_a_store_in_the_body(self):
        other = Store.objects.create(name="قربانی", slug="victim", status=Store.Status.ACTIVE)
        msg = self.bounce("Permanent", rcpt="victim@example.com", mid="not-ours")
        msg["mail"]["tags"] = {"store_id": [str(other.pk)]}
        self.post(notification(msg))
        self.assertFalse(EmailSuppression.objects.filter(store=other).exists())

    def test_subscription_confirmation_only_for_an_allowlisted_signed_topic(self):
        calls = []
        webhook_views.confirm_subscription = lambda url: calls.append(url)
        self.addCleanup(lambda: setattr(webhook_views, "confirm_subscription", None))
        good = sign({"Type": "SubscriptionConfirmation", "MessageId": "s1", "TopicArn": TOPIC, "Message": "m",
                     "Timestamp": "t", "Token": "tok", "SubscribeURL": "https://sns.eu-west-1.amazonaws.com/?Action=ConfirmSubscription"})
        self.assertEqual(self.post(good).status_code, 200)
        self.assertEqual(len(calls), 1)
        evil = sign({"Type": "SubscriptionConfirmation", "MessageId": "s2", "TopicArn": "arn:aws:sns:x:1:evil", "Message": "m",
                     "Timestamp": "t", "Token": "tok", "SubscribeURL": "https://evil.test/confirm"})
        self.assertEqual(self.post(evil).status_code, 403)
        self.assertEqual(len(calls), 1)

    def test_webhook_events_never_store_headers_or_bodies(self):
        msg = self.bounce("Permanent")
        msg["bounce"]["bouncedRecipients"][0]["diagnosticCode"] = "smtp; 550 no such user"
        msg["mail"]["headers"] = [{"name": "Authorization", "value": "SECRET"}]
        self.post(notification(msg))
        ev = EmailProviderEvent.objects.get()
        self.assertNotIn("SECRET", json.dumps(ev.detail))
        self.assertTrue(set(ev.detail) <= {"bounceType", "bounceSubType", "diagnosticCode", "complaintFeedbackType", "status", "action"})


class SuppressionAndRecipientIsolationTests(TestCase):
    def setUp(self):
        FakeTransport.reset()
        self.a = Store.objects.get(slug="akhlaghi")
        self.b = Store.objects.create(name="B", slug="iso-b", status=Store.Status.ACTIVE)
        give_active_sender(self.a, "info@a-example.test")
        FakeTransport.identities["b-example.test"] = {"status": "verified"}
        from apps.notifications.models import EmailSenderIdentity

        EmailSenderIdentity.objects.create(store=self.b, domain_name="b-example.test", local_part="info", provider="fake",
                                           status=EmailSenderIdentity.Status.ACTIVE)
        user = User.objects.create_user(username="09128880002", password="x12345678")
        self.customer = Customer.objects.create(user=user, full_name="سارا", phone="09128880002", email="shared@example.com")

    def queue(self, store, key):
        (row,) = dispatch_event("return.approved", store=store, customer=self.customer, channels=["email"], dedupe_key=key,
                                context={"customer_name": "x", "return_number": "1", "order_number": "1", "order_total": "1",
                                         "order_status": "x", "order_url": "u", "reason": ""})
        return row

    def test_suppressed_recipient_is_skipped_at_send_time_without_burning_an_attempt(self):
        es_row = self.queue(self.a, "s1")
        EmailSuppression.objects.create(store=self.a, email="Shared@Example.com", reason="bounce")
        deliver_pending()
        es_row.refresh_from_db()
        self.assertEqual((es_row.status, es_row.skip_reason, es_row.attempts), (S.SKIPPED, "recipient_suppressed", 0))
        self.assertEqual(FakeTransport.sent, [])

    def test_suppression_in_one_store_does_not_affect_another_store(self):
        EmailSuppression.objects.create(store=self.a, email="shared@example.com", reason="complaint")
        row_b = self.queue(self.b, "s2")
        deliver_pending()
        row_b.refresh_from_db()
        self.assertEqual(row_b.status, S.SENT)
        self.assertEqual(FakeTransport.sent[0]["message"].from_address, "info@b-example.test")

    def test_each_store_sends_only_from_its_own_domain(self):
        ra, rb = self.queue(self.a, "x1"), self.queue(self.b, "x2")
        deliver_pending()
        sent = {m["message"].from_address for m in FakeTransport.sent}
        self.assertEqual(sent, {"info@a-example.test", "info@b-example.test"})
        ra.refresh_from_db(), rb.refresh_from_db()
        self.assertTrue(ra.sender_address.endswith("a-example.test") and rb.sender_address.endswith("b-example.test"))

    def test_one_recipient_row_per_recipient_no_cc_leak(self):
        self.queue(self.a, "x3")
        deliver_pending()
        msg = FakeTransport.sent[0]["message"]
        self.assertEqual(msg.to_address, "shared@example.com")
        self.assertEqual(msg.headers, {})


class TemplateInjectionTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_no_expression_evaluation_is_possible(self):
        for payload in ("{{7*7}}", "{customer_name.__class__}", "{% load x %}", "{customer_name|upper}",
                        "{0}", "{customer_name[0]}", "{ customer_name }"):
            with self.assertRaises(ts.TemplateError, msg=payload):
                ts.validate_text("account.registered", payload)

    def test_dollar_brace_syntax_is_inert_plain_text_not_an_expression(self):
        """``${customer_name}`` has no ``{identifier}`` substitution syntax error (the ``$`` is just a literal
        character) — this proves there is no second, undocumented template language to exploit, not that this
        exact string is accepted as a variable."""
        ts.validate_text("account.registered", "${customer_name}")
        text, missing = ts.render_text("${customer_name}", {"customer_name": "x"})
        self.assertEqual(text, "$x")

    def test_malicious_variable_value_cannot_inject_headers(self):
        user = User.objects.create_user(username="09128880003", password="x12345678")
        cust = Customer.objects.create(user=user, full_name="x", phone="09128880003", email="c@example.com")
        give_active_sender(self.store)
        (row,) = dispatch_event(
            "account.registered", store=self.store, customer=cust, channels=["email"], dedupe_key="inj",
            context={"customer_name": "Eve\r\nBcc: victim@example.com"},
        )
        self.assertNotIn("\n", row.subject)
        self.assertNotIn("\r", row.subject)
        deliver_pending()
        msg = FakeTransport.sent[0]["message"]
        self.assertEqual(msg.to_address, "c@example.com")
        self.assertNotIn("\n", msg.subject)

    def test_saved_html_is_sanitized_and_script_never_reaches_the_outbox(self):
        ts.save_template(self.store, "account.registered", "email", enabled=True, subject="s {store_name}",
                         body="{customer_name}", body_html='<p>{customer_name}</p><script>steal()</script><a href="javascript:x()">y</a>')
        row = ts.get_template(self.store, "account.registered", "email")
        self.assertNotIn("script", row["body_html"])
        self.assertNotIn("javascript", row["body_html"])
        user = User.objects.create_user(username="09128880004", password="x12345678")
        cust = Customer.objects.create(user=user, full_name="x", phone="09128880004", email="c4@example.com")
        (out,) = dispatch_event("account.registered", store=self.store, customer=cust, channels=["email"], dedupe_key="h1",
                                context={"customer_name": "<img src=x onerror=alert(1)>"})
        self.assertNotIn("<img", out.html_body)
        self.assertIn("&lt;img", out.html_body)  # escaped text — not a live, exploitable <img onerror=...> element

    def test_html_over_the_size_limit_is_rejected(self):
        with self.assertRaises(ts.TemplateError):
            ts.save_template(self.store, "account.registered", "email", enabled=True, subject="s", body="{customer_name}",
                             body_html="<p>x</p>" * 5000)

    def test_unknown_variable_in_html_is_rejected(self):
        with self.assertRaises(ts.TemplateError):
            ts.save_template(self.store, "account.registered", "email", enabled=True, subject="s", body="{customer_name}",
                             body_html="<p>{password}</p>")


class DeliveryReliabilityTests(TestCase):
    def setUp(self):
        FakeTransport.reset()
        self.store = Store.objects.get(slug="akhlaghi")
        give_active_sender(self.store)
        user = User.objects.create_user(username="09128880005", password="x12345678")
        self.customer = Customer.objects.create(user=user, full_name="x", phone="09128880005", email="r@example.com")
        self.ctx = {"customer_name": "x", "return_number": "1", "order_number": "1", "order_total": "1", "order_status": "x",
                    "order_url": "u", "reason": ""}

    def queue(self, key="k"):
        (row,) = dispatch_event("return.approved", store=self.store, customer=self.customer, channels=["email"],
                                dedupe_key=key, context=self.ctx)
        return row

    def test_transient_provider_error_retries_with_exponential_backoff_then_sends_once(self):
        row = self.queue()
        FakeTransport.next_send_failures = [
            SendOutcome(False, error_code="Throttling", error="slow down", retryable=True),
            SendOutcome(False, error_code="Throttling", error="slow down", retryable=True),
        ]
        t = timezone.now()
        deliver_pending(now=t)
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), (S.FAILED, 1))
        d1 = row.next_attempt_at - t
        deliver_pending(now=row.next_attempt_at + timedelta(seconds=1))
        row.refresh_from_db()
        d2 = row.next_attempt_at - (t + d1)
        self.assertGreater(d2, d1)  # backoff grows
        deliver_pending(now=row.next_attempt_at + timedelta(seconds=1))
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts, len(FakeTransport.sent)), (S.SENT, 3, 1))

    def test_permanent_provider_error_goes_dead_immediately(self):
        row = self.queue()
        FakeTransport.next_send_failures = [SendOutcome(False, error_code="MessageRejected", error="rejected", retryable=False)]
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, row.attempts), (S.DEAD, 1))
        deliver_pending(now=timezone.now() + timedelta(days=3))
        self.assertEqual(len(FakeTransport.sent), 0)

    def test_dead_row_is_recoverable_by_operator_retry(self):
        from apps.notifications.services.notification_service import retry_notification

        row = self.queue()
        FakeTransport.next_send_failures = [SendOutcome(False, error_code="MessageRejected", error="x", retryable=False)]
        deliver_pending()
        row.refresh_from_db()
        retry_notification(row)
        deliver_pending()
        row.refresh_from_db()
        self.assertEqual((row.status, len(FakeTransport.sent)), (S.SENT, 1))

    def test_unexpected_exception_in_one_row_does_not_block_the_rest_of_the_queue(self):
        r1, r2 = self.queue("a"), self.queue("b")
        real = FakeTransport.send
        calls = {"n": 0}

        def flaky(self_, message):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("provider socket exploded")
            return real(self_, message)

        with patch.object(FakeTransport, "send", flaky):
            result = deliver_pending()
        self.assertEqual((result["failed"], result["sent"]), (1, 1))

    def test_error_text_never_leaks_recipient_or_secrets(self):
        row = self.queue()
        FakeTransport.next_send_failures = [SendOutcome(False, error="fail for r@example.com key AKIAIOSFODNN7EXAMPLE", retryable=True)]
        deliver_pending()
        row.refresh_from_db()
        self.assertNotIn("r@example.com", row.last_error)

    def test_repeated_business_event_creates_exactly_one_notification(self):
        first = self.queue("same")
        again = dispatch_event("return.approved", store=self.store, customer=self.customer, channels=["email"],
                               dedupe_key="same", context=self.ctx)
        self.assertEqual(again, [])
        self.assertEqual(NotificationOutbox.objects.filter(event_key="return.approved", channel="email").count(), 1)
        deliver_pending()
        deliver_pending()
        first.refresh_from_db()
        self.assertEqual(len(FakeTransport.sent), 1)

    def test_two_workers_cannot_claim_the_same_row(self):
        self.queue()
        now = timezone.now()
        first, second = _claim_batch(10, now), _claim_batch(10, now)
        self.assertEqual((len(first), len(second)), (1, 0))

    @override_settings(RASTISI_EMAIL_STORE_HOURLY_LIMIT=2)
    def test_store_rate_limit_holds_excess_mail_without_losing_it(self):
        rows = [self.queue(f"rl{i}") for i in range(3)]
        t = timezone.now()
        result = deliver_pending(now=t)
        self.assertEqual((result["sent"], result["held"]), (2, 1))
        held = [r for r in rows if (r.refresh_from_db() or r.status) == S.PENDING]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].last_error, "rate_limited")
        deliver_pending(now=t + timedelta(hours=1, minutes=20))
        held[0].refresh_from_db()
        self.assertEqual(held[0].status, S.SENT)

    @override_settings(RASTISI_EMAIL_STORE_HOURLY_LIMIT=1)
    def test_security_mail_is_not_subject_to_the_store_rate_limit(self):
        self.queue("filler")
        deliver_pending()
        (sec,) = dispatch_event("account.sensitive_changed", store=self.store, customer=self.customer, channels=["email"],
                                dedupe_key="sec", context={**self.ctx, "changed_field": "ایمیل"})
        self.assertTrue(sec.is_security)
        deliver_pending()
        sec.refresh_from_db()
        self.assertEqual(sec.status, S.SENT)

    @override_settings(RASTISI_EMAIL_PLATFORM_MINUTE_LIMIT=1)
    def test_platform_wide_rate_limit(self):
        self.queue("p1"), self.queue("p2")
        result = deliver_pending()
        self.assertEqual((result["sent"], result["held"]), (1, 1))

    def test_dispatch_failure_never_raises_into_the_business_transaction(self):
        with patch("apps.notifications.services.dispatcher.dispatch_event", side_effect=RuntimeError("db down")):
            self.assertEqual(safe_dispatch("order.created", store=self.store), [])

    def test_security_mail_cannot_be_disabled_by_store_or_platform(self):
        ts.save_template(self.store, "account.sensitive_changed", "email", enabled=False, subject="s {changed_field}",
                         body="{changed_field}")
        self.assertTrue(ts.get_template(self.store, "account.sensitive_changed", "email")["enabled"])
        ts.save_platform_template("account.sensitive_changed", "email", enabled=False, subject="s", body="{changed_field}")
        self.assertTrue(ts.get_template(self.store, "account.sensitive_changed", "email")["enabled"])
        with self.assertRaises(ts.TemplateError):
            ts.set_channel_enabled(self.store, "account.sensitive_changed", "email", False)
        with self.assertRaises(ts.TemplateError):  # protected variable cannot be removed
            ts.save_template(self.store, "account.sensitive_changed", "email", enabled=True, subject="s", body="سلام")

    def test_promotional_consent_is_still_enforced_for_email(self):
        self.customer.accepts_promotional_email = False
        self.customer.save()
        ctx = {"discount_code": "G", "discount_amount": "x", "discount_max": "", "discount_expires_at": "x",
               "campaign_name": "c", "occasion_name": "o", "customer_name": "x"}
        (row,) = dispatch_event("coupon.issued", store=self.store, customer=self.customer, channels=["email"],
                                dedupe_key="promo", context=ctx)
        self.assertEqual((row.status, row.skip_reason), (S.SKIPPED, "no_promotional_consent"))


class ConcurrentSchedulingTests(SerializedRollbackSafeMixin, TransactionTestCase):
    serialized_rollback = True  # restore migration-seeded rows (e.g. the akhlaghi Store) for any later test class

    """Real threads scheduling the same business event: exactly one outbox row (DB unique constraint)."""

    def test_concurrent_identical_dispatches_create_a_single_row(self):
        store = Store.objects.get(slug="akhlaghi")
        user = User.objects.create_user(username="09128880006", password="x12345678")
        cust = Customer.objects.create(user=user, full_name="x", phone="09128880006", email="t@example.com")
        ctx = {"customer_name": "x", "return_number": "1", "order_number": "1", "order_total": "1", "order_status": "x",
               "order_url": "u", "reason": ""}
        errors = []
        barrier = threading.Barrier(6)

        def work():
            from django.db import connection

            try:
                barrier.wait(timeout=5)
                for _ in range(3):
                    try:
                        dispatch_event("return.approved", store=store, customer=cust, channels=["email"],
                                       dedupe_key="race", context=ctx)
                        break
                    except Exception as exc:  # noqa: BLE001 — SQLite writer lock contention: retry like a real worker would
                        if "locked" not in str(exc).lower():
                            raise
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=work) for _ in range(6)]
        [t.start() for t in threads]
        [t.join(15) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(NotificationOutbox.objects.filter(event_key="return.approved", channel="email").count(), 1)
