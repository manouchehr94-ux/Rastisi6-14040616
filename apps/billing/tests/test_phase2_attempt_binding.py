"""Phase 2 / F-13 + F-14: a payment-attempt idempotency key is bound to one invoice/store/provider/currency, and repeating a
start-payment request with the same key never opens a second provider session or reopens a final attempt.
Synthetic provider only. The PostgreSQL class runs real threads and is skipped on SQLite."""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import mock, skipUnless

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers.base import PaymentSessionResult
from apps.billing.services import attempt_service, invoice_service, payment_flow_service
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc

A = SubscriptionPaymentAttempt.Status


def open_invoice(slug, price="400000"):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED, display_price=Decimal(price), currency="IRT")
    sub = sub_svc.activate_subscription(sub_svc.create_subscription(store, version))
    invoice = invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(version)])
    return store, invoice_service.open_invoice(invoice)


class FakeSessions:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def create_payment_session(self, *, attempt, invoice, return_url):
        with self.lock:
            self.calls += 1
            n = self.calls
        return PaymentSessionResult(session_id=f"sess-{n}", redirect_url=f"https://bank.test/{n}")


def with_provider(fake):
    return mock.patch("apps.billing.services.payment_flow_service.registry.get_provider", return_value=fake)


class AttemptKeyBindingTests(TestCase):
    def setUp(self):
        self.store, self.invoice = open_invoice("p2ab-a")
        self.other_store, self.other_invoice = open_invoice("p2ab-b")

    def test_same_key_same_invoice_returns_the_same_attempt(self):
        first, created1 = attempt_service.get_or_create_attempt(self.invoice, provider="manual", idempotency_key="k")
        second, created2 = attempt_service.get_or_create_attempt(self.invoice, provider="manual", idempotency_key="k")
        self.assertEqual((first.pk, created1, created2), (second.pk, True, False))

    def test_a_key_cannot_be_reused_for_another_invoice_or_store(self):
        first = attempt_service.create_attempt(self.invoice, provider="manual", idempotency_key="shared")
        with self.assertRaises(attempt_service.PaymentAttemptError):
            attempt_service.create_attempt(self.other_invoice, provider="manual", idempotency_key="shared")
        first.refresh_from_db()
        self.assertEqual((first.invoice_id, first.store_id), (self.invoice.pk, self.store.pk))
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(idempotency_key="shared").count(), 1)
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=self.other_invoice).exists())

    def test_a_key_cannot_be_reused_with_another_provider(self):
        attempt_service.create_attempt(self.invoice, provider="manual", idempotency_key="prov")
        with self.assertRaises(attempt_service.PaymentAttemptError):
            attempt_service.create_attempt(self.invoice, provider="zibal", idempotency_key="prov")

    def test_the_flow_surfaces_a_mismatch_as_a_displayable_error_and_changes_nothing(self):
        fake = FakeSessions()
        with with_provider(fake):
            payment_flow_service.start_payment(self.invoice, provider="manual", idempotency_key="x", callback_base_url="http://t")
            with self.assertRaises(payment_flow_service.PaymentFlowError):
                payment_flow_service.start_payment(self.other_invoice, provider="manual", idempotency_key="x", callback_base_url="http://t")
        self.assertEqual(fake.calls, 1)
        self.other_invoice.refresh_from_db()
        self.assertEqual(self.other_invoice.status, SubscriptionInvoice.Status.OPEN)


class StartPaymentRepeatTests(TestCase):
    def setUp(self):
        self.store, self.invoice = open_invoice("p2sp")

    def test_a_repeat_with_the_same_key_opens_no_second_provider_session(self):
        fake = FakeSessions()
        with with_provider(fake):
            attempt, session = payment_flow_service.start_payment(self.invoice, provider="manual", idempotency_key="rep", callback_base_url="http://t")
            again, session2 = payment_flow_service.start_payment(self.invoice, provider="manual", idempotency_key="rep", callback_base_url="http://t")
        self.assertIsNotNone(session)
        self.assertIsNone(session2)
        self.assertEqual((attempt.pk, fake.calls), (again.pk, 1))
        again.refresh_from_db()
        self.assertEqual(again.provider_session_id, "sess-1")                    # not overwritten by a second session

    def test_a_final_attempt_is_never_reopened_by_a_repeat(self):
        fake = FakeSessions()
        with with_provider(fake):
            attempt, _ = payment_flow_service.start_payment(self.invoice, provider="manual", idempotency_key="fin", callback_base_url="http://t")
            SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(status=A.FAILED, failure_code="provider_terminal_failure")
            again, session = payment_flow_service.start_payment(self.invoice, provider="manual", idempotency_key="fin", callback_base_url="http://t")
        again.refresh_from_db()
        self.assertEqual((again.status, session, fake.calls), (A.FAILED, None, 1))

    def test_without_a_key_each_deliberate_retry_still_gets_a_fresh_attempt_and_session(self):
        fake = FakeSessions()
        with with_provider(fake):
            a1, s1 = payment_flow_service.start_payment(self.invoice, provider="manual", callback_base_url="http://t")
            a2, s2 = payment_flow_service.start_payment(self.invoice, provider="manual", callback_base_url="http://t")
        self.assertNotEqual(a1.pk, a2.pk)
        self.assertIsNotNone(s1)
        self.assertIsNotNone(s2)
        self.assertEqual(fake.calls, 2)


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrency")
class PostgresConcurrentStartTests(TransactionTestCase):
    def test_5_simultaneous_starts_with_one_key_make_one_attempt_and_one_provider_session(self):
        _store, invoice = open_invoice("p2pgs")
        fake = FakeSessions()
        barrier = threading.Barrier(5)

        def worker(_i):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                with with_provider(fake):
                    attempt, session = payment_flow_service.start_payment(
                        SubscriptionInvoice.objects.get(pk=invoice.pk), provider="manual", idempotency_key="conc", callback_base_url="http://t")
                return ("session" if session is not None else "repeat", attempt.pk)
            except Exception as exc:  # noqa: BLE001
                return (type(exc).__name__, None)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=5) as pool:
            out = list(pool.map(worker, range(5)))
        self.assertEqual(Counter(kind for kind, _ in out), {"session": 1, "repeat": 4}, out)    # before the fix: 5 sessions
        self.assertEqual(len({pk for _, pk in out}), 1)
        self.assertEqual(fake.calls, 1)
        rows = SubscriptionPaymentAttempt.objects.filter(invoice=invoice)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().provider_session_id, "sess-1")
