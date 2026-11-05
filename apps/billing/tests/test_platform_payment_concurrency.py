"""Real-concurrency checks for exactly-once fulfilment (PostgreSQL only: SQLite serialises writers, so a thread race
proves nothing there). Run with a throwaway PostgreSQL via DATABASE_URL; skipped otherwise."""

import threading
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import confirmation_service, payment_flow_service, sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store


def run_in_threads(callables):
    results, barrier = [None] * len(callables), threading.Barrier(len(callables))

    def worker(i, fn):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            results[i] = ("ok", fn())
        except Exception as exc:  # noqa: BLE001 — recorded, asserted by the caller
            results[i] = ("err", exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, fn)) for i, fn in enumerate(callables)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL for real row-lock concurrency")
class PlatformPaymentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه هم‌زمانی", slug="conc-store", admin_subdomain="conc-store")
        self.package = SmsPackage.objects.create(name="بسته", credit_amount=300, price=90_000)
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 10})

    def sms_attempt(self):
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        attempt = SmsPackagePaymentAttempt.objects.create(
            store=self.store, purchase=purchase, provider="zibal", status="pending", amount=purchase.price, currency="IRT",
            public_token=sms_svc._new_token(), idempotency_key=f"conc-{purchase.pk}", provider_session_id="t1",
        )
        return purchase, attempt

    def test_many_simultaneous_confirmations_of_one_sms_attempt_add_credit_once(self):
        purchase, attempt = self.sms_attempt()
        call = lambda: sms_svc.confirm_payment(attempt=attempt, amount=attempt.amount, currency="IRT", provider_payment_id="p1")
        results = run_in_threads([call] * 8)
        self.assertTrue(all(kind == "ok" for kind, _ in results), results)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10 + 300)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=purchase).count(), 1)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, SmsPackagePurchase.Status.COMPLETED)

    def test_online_confirmation_racing_manual_completion_credits_once(self):
        purchase, attempt = self.sms_attempt()
        online = lambda: sms_svc.confirm_payment(attempt=attempt, amount=attempt.amount, currency="IRT", provider_payment_id="p2")
        manual = lambda: balance_service.complete_purchase(purchase=purchase)
        run_in_threads([online, manual, online, manual])
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10 + 300)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=purchase).count(), 1)

    def test_credit_purchase_racing_message_deductions_loses_no_update(self):
        purchase, attempt = self.sms_attempt()
        deduct = lambda: balance_service.deduct_credit(store=self.store)
        add = lambda: sms_svc.confirm_payment(attempt=attempt, amount=attempt.amount, currency="IRT", provider_payment_id="p3")
        run_in_threads([add, deduct, deduct, deduct])
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10 + 300 - 3)

    def test_two_attempts_paying_one_invoice_apply_the_money_once_and_flag_the_other(self):
        _sub, invoice = open_invoice_for(self.store, code="conc-inv", price="200000")
        a1 = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=invoice, provider="zibal", status="pending", amount=invoice.amount_due, currency="IRT",
            public_token="conc-tok-1", idempotency_key="conc-k1", provider_session_id="s1",
        )
        a2 = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=invoice, provider="zibal", status="pending", amount=invoice.amount_due, currency="IRT",
            public_token="conc-tok-2", idempotency_key="conc-k2", provider_session_id="s2",
        )
        confirm = lambda a, pid: (lambda: confirmation_service.confirm_payment(
            attempt=a, amount=invoice.amount_due, currency="IRT", provider_payment_id=pid))
        results = run_in_threads([confirm(a1, "pay-1"), confirm(a2, "pay-2"), confirm(a1, "pay-1"), confirm(a2, "pay-2")])
        self.assertTrue(all(kind == "ok" for kind, _ in results), results)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(invoice.amount_paid, invoice.grand_total)
        statuses = sorted(SubscriptionPaymentAttempt.objects.values_list("status", flat=True))
        self.assertEqual(statuses, ["requires_action", "succeeded"])

    def test_concurrent_callbacks_through_the_service_layer_are_idempotent(self):
        _sub, invoice = open_invoice_for(self.store, code="conc-cb", price="120000")
        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=invoice, provider="manual", status="pending", amount=invoice.amount_due, currency="IRT",
            public_token="conc-tok-3", idempotency_key="conc-k3", provider_session_id="s3",
        )
        call = lambda: payment_flow_service.confirm_from_provider_verification(attempt)
        run_in_threads([call] * 4)                      # manual provider has no automatic capture ⇒ no-op, never fabricates
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, 0)
