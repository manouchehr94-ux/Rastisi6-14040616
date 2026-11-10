"""Phase 2 / Priority 2: webhook reliability (F-15 concurrent ingestion, F-16 durable failure + recovery, F-17 terminal state).

The signed ``manual`` webhook is the only push channel. Synthetic secret, synthetic provider, no network.
The PostgreSQL class runs REAL concurrent requests (threads); it is skipped on SQLite, which ignores row locks."""

import hashlib
import hmac
import io
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.management.commands.reprocess_billing_webhooks import due_events
from apps.billing.models import BillingWebhookEvent, SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service, webhook_service
from apps.billing.tests.test_platform_coupon_financial_acceptance import Base
from apps.billing.tests.test_trial_purchase_flow import formula_plan, make_owner
from apps.subscriptions.models import StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent, plan_change_service as pcs
from apps.billing.services import plan_change_billing_service as pcb

SECRET = "phase2-test-secret-not-real"
P = BillingWebhookEvent.ProcessingStatus


def signed(body: dict):
    raw = json.dumps(body).encode()
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, {"HTTP_X_BILLING_SIGNATURE": sig, "HTTP_X_BILLING_TIMESTAMP": ts}


def post(body: dict, client=None):
    raw, headers = signed(body)
    return (client or Client(raise_request_exception=False)).post("/billing/webhook/manual/", data=raw, content_type="application/json", **headers)


@override_settings(RASTISI_BILLING_WEBHOOK_SECRET=SECRET)
class WebhookBase(Base):
    def manual_attempt(self):
        t = self.client.post(reverse("dashboard:subscription-plan-preview"), {"version_id": self.pro.pk, "billing_interval": "monthly"}).context["preview"]["token"]
        self.client.post(reverse("dashboard:subscription-plan-execute"), {"version_id": self.pro.pk, "preview_token": t, "billing_interval": "monthly"})
        inv = self.invoice()
        attempt, _ = payment_flow_service.start_payment(inv, provider="manual", callback_base_url="http://testserver")
        return inv, attempt

    def success_body(self, inv, attempt, event_id):
        return {"event_id": event_id, "event_type": "payment.succeeded", "session_id": attempt.provider_session_id,
                "provider_payment_id": f"pp-{event_id}", "amount": str(inv.amount_due), "currency": inv.currency}


class IngestionTests(WebhookBase):
    def test_sequential_duplicate_delivery_is_idempotent(self):
        body = {"event_id": "evt-dup", "event_type": "payment.ignored"}
        self.assertEqual((post(body).status_code, post(body).status_code), (200, 200))
        self.assertEqual(BillingWebhookEvent.objects.filter(external_event_id="evt-dup").count(), 1)

    def test_losing_a_duplicate_insert_race_returns_the_existing_event_and_not_an_error(self):
        """F-15: the pre-insert lookup misses (another request inserted meanwhile), the INSERT violates the unique constraint."""
        body = {"event_id": "evt-race", "event_type": "payment.ignored"}
        post(body)
        real_manager = BillingWebhookEvent.objects

        class Blind:
            def select_for_update(self): return self
            def filter(self, **kw): return self
            def first(self): return None                      # the lookup "does not see" the row
            def __getattr__(self, name): return getattr(real_manager, name)

        with mock.patch.object(BillingWebhookEvent, "objects", Blind()):
            response = post(body)
        self.assertEqual(response.status_code, 200)            # used to be an unhandled TransactionManagementError (HTTP 500)
        self.assertEqual(BillingWebhookEvent.objects.filter(external_event_id="evt-race").count(), 1)

    def test_invalid_signature_still_rejected_without_storing_anything(self):
        raw = json.dumps({"event_id": "evt-bad", "event_type": "payment.succeeded"}).encode()
        r = Client().post("/billing/webhook/manual/", data=raw, content_type="application/json",
                          HTTP_X_BILLING_SIGNATURE="00" * 32, HTTP_X_BILLING_TIMESTAMP=str(int(time.time())))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(BillingWebhookEvent.objects.filter(external_event_id="evt-bad").exists())


class RecoveryTests(WebhookBase):
    def test_unexpected_error_is_recorded_durably_and_answered_retryably(self):
        inv, attempt = self.manual_attempt()
        body = self.success_body(inv, attempt, "evt-crash")
        with mock.patch("apps.billing.services.payment_flow_service.confirm_payment", side_effect=RuntimeError("transient db blip")):
            response = post(body)
        self.assertEqual(response.status_code, 503)           # a provider that redelivers will do so
        ev = BillingWebhookEvent.objects.get(external_event_id="evt-crash")
        self.assertEqual((ev.processing_status, ev.retry_count), (P.FAILED, 1))
        self.assertEqual(ev.error_summary, "unexpected:RuntimeError")      # class name only: nothing sensitive stored
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.PAYMENT_PENDING)

    def test_redelivery_after_a_transient_failure_activates_exactly_once(self):
        inv, attempt = self.manual_attempt()
        body = self.success_body(inv, attempt, "evt-redeliver")
        with mock.patch("apps.billing.services.payment_flow_service.confirm_payment", side_effect=RuntimeError("blip")):
            post(body)
        self.assertEqual(post(body).status_code, 200)
        self.assertEqual(post(body).status_code, 200)
        ev = BillingWebhookEvent.objects.get(external_event_id="evt-redeliver")
        inv.refresh_from_db()
        self.assertEqual((ev.processing_status, inv.status, inv.amount_paid), (P.PROCESSED, "paid", Decimal(1_000_000)))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 1)

    def test_reprocess_job_recovers_a_stuck_received_event(self):
        inv, attempt = self.manual_attempt()
        raw, headers = signed(self.success_body(inv, attempt, "evt-stuck"))
        event = webhook_service.ingest_webhook(provider_code="manual", headers={"x-billing-signature": headers["HTTP_X_BILLING_SIGNATURE"],
                                                                                   "x-billing-timestamp": headers["HTTP_X_BILLING_TIMESTAMP"]}, body=raw)
        self.assertEqual(event.processing_status, P.RECEIVED)                 # the worker died right here
        BillingWebhookEvent.objects.filter(pk=event.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        call_command("reprocess_billing_webhooks", stdout=io.StringIO())
        event.refresh_from_db(); inv.refresh_from_db()
        self.assertEqual((event.processing_status, inv.status), (P.PROCESSED, "paid"))

    def test_reprocess_job_is_idempotent_and_bounded(self):
        inv, attempt = self.manual_attempt()
        raw, h = signed(self.success_body(inv, attempt, "evt-idem"))
        ev = webhook_service.ingest_webhook(provider_code="manual", headers={"x-billing-signature": h["HTTP_X_BILLING_SIGNATURE"], "x-billing-timestamp": h["HTTP_X_BILLING_TIMESTAMP"]}, body=raw)
        BillingWebhookEvent.objects.filter(pk=ev.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        for _ in range(3):
            call_command("reprocess_billing_webhooks", stdout=io.StringIO())
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal(1_000_000))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription__store=self.store, event_type="activated").count(), 1)
        # bounded: an event that keeps failing stops being retried after max_retries
        bad = BillingWebhookEvent.objects.create(provider="manual", external_event_id="evt-exhausted", event_type="payment.succeeded",
                                                 signature_valid=True, processing_status=P.FAILED, retry_count=5,
                                                 sanitized_payload={}, received_at=timezone.now())
        BillingWebhookEvent.objects.filter(pk=bad.pk).update(updated_at=timezone.now() - timedelta(days=1))
        self.assertNotIn(bad.pk, [e.pk for e in due_events(timezone.now())])

    def test_backoff_delays_a_recently_failed_event(self):
        ev = BillingWebhookEvent.objects.create(provider="manual", external_event_id="evt-backoff", event_type="payment.succeeded",
                                                signature_valid=True, processing_status=P.FAILED, retry_count=3,
                                                sanitized_payload={}, received_at=timezone.now())
        self.assertNotIn(ev.pk, [e.pk for e in due_events(timezone.now())])       # 2**3 = 8 minutes not yet elapsed
        BillingWebhookEvent.objects.filter(pk=ev.pk).update(updated_at=timezone.now() - timedelta(minutes=9))
        self.assertIn(ev.pk, [e.pk for e in due_events(timezone.now())])

    def test_one_failing_event_does_not_stop_the_job_and_fails_the_run(self):
        events = []
        for i in range(2):
            ev = BillingWebhookEvent.objects.create(provider="manual", external_event_id=f"evt-job-{i}", event_type="payment.ignored",
                                                    signature_valid=True, processing_status=P.RECEIVED, sanitized_payload={}, received_at=timezone.now())
            BillingWebhookEvent.objects.filter(pk=ev.pk).update(created_at=timezone.now() - timedelta(minutes=10))
            events.append(ev)
        real = payment_flow_service.process_webhook_event

        def flaky(event, **kw):
            if event.pk == events[0].pk:
                raise RuntimeError("poison event")
            return real(event, **kw)

        out = io.StringIO()
        with mock.patch.object(payment_flow_service, "process_webhook_event", flaky):
            with self.assertRaises(CommandError):
                call_command("reprocess_billing_webhooks", stdout=out)
        self.assertIn("unexpected_errors=1", out.getvalue())
        events[1].refresh_from_db(); events[0].refresh_from_db()
        self.assertEqual(events[1].processing_status, P.IGNORED)                 # the healthy event WAS processed
        self.assertEqual((events[0].processing_status, events[0].error_summary), (P.FAILED, "unexpected:RuntimeError"))

    def test_staff_reconciliation_lists_failed_and_long_stuck_received_events(self):
        from apps.portal.platform_admin_views import reconciliation_snapshot
        stuck = BillingWebhookEvent.objects.create(provider="manual", external_event_id="evt-vis-stuck", signature_valid=True,
                                                   processing_status=P.RECEIVED, sanitized_payload={}, received_at=timezone.now())
        fresh = BillingWebhookEvent.objects.create(provider="manual", external_event_id="evt-vis-fresh", signature_valid=True,
                                                   processing_status=P.RECEIVED, sanitized_payload={}, received_at=timezone.now())
        failed = BillingWebhookEvent.objects.create(provider="manual", external_event_id="evt-vis-failed", signature_valid=True,
                                                    processing_status=P.FAILED, sanitized_payload={}, received_at=timezone.now())
        BillingWebhookEvent.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        listed = {e.pk for e in reconciliation_snapshot()["failed_webhooks"]}
        self.assertIn(stuck.pk, listed)
        self.assertIn(failed.pk, listed)
        self.assertNotIn(fresh.pk, listed)                                        # a just-received event is not an alarm


class TerminalStateTests(WebhookBase):
    def test_a_stale_writer_cannot_move_a_processed_event_back_to_failed(self):
        inv, attempt = self.manual_attempt()
        raw, h = signed(self.success_body(inv, attempt, "evt-term"))
        event = webhook_service.ingest_webhook(provider_code="manual", headers={"x-billing-signature": h["HTTP_X_BILLING_SIGNATURE"], "x-billing-timestamp": h["HTTP_X_BILLING_TIMESTAMP"]}, body=raw)
        stale = BillingWebhookEvent.objects.get(pk=event.pk)
        payment_flow_service.process_webhook_event(event)
        webhook_service.mark_failed(stale, error="late failure from a stale worker")
        final = BillingWebhookEvent.objects.get(pk=event.pk)
        self.assertEqual((final.processing_status, final.retry_count), (P.PROCESSED, 0))
        self.assertEqual(final.error_summary, "")

    def test_a_stale_snapshot_does_not_reprocess_or_double_apply(self):
        inv, attempt = self.manual_attempt()
        raw, h = signed(self.success_body(inv, attempt, "evt-snap"))
        event = webhook_service.ingest_webhook(provider_code="manual", headers={"x-billing-signature": h["HTTP_X_BILLING_SIGNATURE"], "x-billing-timestamp": h["HTTP_X_BILLING_TIMESTAMP"]}, body=raw)
        stale = BillingWebhookEvent.objects.get(pk=event.pk)
        payment_flow_service.process_webhook_event(event)
        with mock.patch.object(payment_flow_service, "confirm_payment") as confirm:
            result = payment_flow_service.process_webhook_event(stale)
            confirm.assert_not_called()                                           # the fresh status was consulted, not the snapshot
        self.assertEqual(result.processing_status, P.PROCESSED)

    def test_processed_and_ignored_helpers_are_idempotent(self):
        ev = BillingWebhookEvent.objects.create(provider="manual", external_event_id="evt-help", signature_valid=True, sanitized_payload={}, received_at=timezone.now())
        webhook_service.mark_processed(ev); webhook_service.mark_processed(ev)
        self.assertEqual(BillingWebhookEvent.objects.get(pk=ev.pk).processing_status, P.PROCESSED)


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrency")
@override_settings(ALLOWED_HOSTS=["*"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", RASTISI_BILLING_WEBHOOK_SECRET=SECRET)
class PostgresConcurrentWebhookTests(TransactionTestCase):
    def setUp(self):
        from apps.billing.tests.platform_payment_support import patch_zibal, ready_platform_zibal
        ready_platform_zibal(self)
        self.fake = patch_zibal(self)
        _p, self.pro = formula_plan("p2wh-pro", 1_000_000, order=2)
        self.owner, self.store = make_owner("p2wh@example.com", "هم‌زمانی وب‌هوک")

    def _run(self, body, workers):
        barrier = threading.Barrier(workers)

        def worker(_):
            close_old_connections()
            try:
                raw, h = signed(body)
                barrier.wait(timeout=20)
                return Client(raise_request_exception=False).post("/billing/webhook/manual/", data=raw, content_type="application/json", **h).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(worker, range(workers)))

    def test_12_simultaneous_identical_deliveries_all_succeed_with_one_stored_event(self):
        codes = self._run({"event_id": "evt-conc", "event_type": "payment.ignored"}, 12)
        self.assertEqual(dict(Counter(codes)), {200: 12})                       # before the fix: 9 x HTTP 500
        self.assertEqual(BillingWebhookEvent.objects.filter(external_event_id="evt-conc").count(), 1)

    def test_8_simultaneous_deliveries_of_one_success_event_activate_exactly_once(self):
        sub = ent.get_current_subscription(self.store)
        _k, inv = pcb.start_plan_change(sub, self.pro, preview_token=pcs._preview_token(sub, self.pro), actor=self.owner, billing_interval="monthly")
        attempt, _ = payment_flow_service.start_payment(inv, provider="manual", callback_base_url="http://testserver")
        body = {"event_id": "evt-pay", "event_type": "payment.succeeded", "session_id": attempt.provider_session_id,
                "provider_payment_id": "pp-pg", "amount": str(inv.amount_due), "currency": inv.currency}
        codes = self._run(body, 8)
        self.assertEqual(dict(Counter(codes)), {200: 8})
        events = BillingWebhookEvent.objects.filter(external_event_id="evt-pay")
        inv.refresh_from_db()
        sub = ent.get_current_subscription(self.store)
        self.assertEqual([e.processing_status for e in events], [P.PROCESSED])
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(1_000_000)))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription=sub, event_type="activated").count(), 1)
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(invoice=inv, status="succeeded").count(), 1)

    def test_concurrent_reprocessing_of_one_stuck_event_applies_the_payment_once(self):
        sub = ent.get_current_subscription(self.store)
        _k, inv = pcb.start_plan_change(sub, self.pro, preview_token=pcs._preview_token(sub, self.pro), actor=self.owner, billing_interval="monthly")
        attempt, _ = payment_flow_service.start_payment(inv, provider="manual", callback_base_url="http://testserver")
        body = {"event_id": "evt-recon", "event_type": "payment.succeeded", "session_id": attempt.provider_session_id,
                "provider_payment_id": "pp-recon", "amount": str(inv.amount_due), "currency": inv.currency}
        raw, h = signed(body)
        event = webhook_service.ingest_webhook(provider_code="manual", headers={"x-billing-signature": h["HTTP_X_BILLING_SIGNATURE"], "x-billing-timestamp": h["HTTP_X_BILLING_TIMESTAMP"]}, body=raw)
        barrier = threading.Barrier(6)

        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                payment_flow_service.process_webhook_event(BillingWebhookEvent.objects.get(pk=event.pk))
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return type(exc).__name__
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=6) as pool:
            out = list(pool.map(worker, range(6)))
        inv.refresh_from_db()
        self.assertEqual(dict(Counter(out)), {"ok": 6})
        self.assertEqual((inv.status, inv.amount_paid), ("paid", Decimal(1_000_000)))
        self.assertEqual(SubscriptionEvent.objects.filter(subscription=ent.get_current_subscription(self.store), event_type="activated").count(), 1)
        self.assertEqual(BillingWebhookEvent.objects.get(pk=event.pk).processing_status, P.PROCESSED)
