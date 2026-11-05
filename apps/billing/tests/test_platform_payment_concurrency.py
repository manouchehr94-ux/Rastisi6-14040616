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


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL for real row-lock concurrency")
class ManualCardClaimConcurrencyTests(TransactionTestCase):
    """The card-to-card review workflow under real concurrent reviewers / submitters (each class run on a throwaway PostgreSQL)."""

    def setUp(self):
        import tempfile

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from apps.billing.tests.test_platform_card_to_card import enable_platform_card, use_private_tmp
        from apps.stores.models import StoreMembership

        self.addCleanup(__import__("django").core.cache.cache.clear)
        use_private_tmp(self)
        User = get_user_model()
        self.store = Store.objects.create(name="فروشگاه هم‌زمانیِ کارت", slug="conc-card", admin_subdomain="conc-card")
        self.owner = User.objects.create_user(username="conc-card-owner", password="x", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.reviewers = [User.objects.create_user(username=f"conc-fin-{i}@example.com", password="x", is_staff=True, is_superuser=True) for i in range(4)]
        self.sub, self.invoice = open_invoice_for(self.store, code="conccard", price="300000")
        enable_platform_card(self)

    def claim(self, invoice=None, store=None, ref="CONC-CARD-0001"):
        from django.utils import timezone

        from apps.billing.services import manual_card_service as mcs

        return mcs.submit_claim(user=self.owner, store=store or self.store, reference=ref, transferred_at=timezone.now(), invoice=invoice or self.invoice)

    def test_simultaneous_approvals_by_several_finance_admins_apply_the_payment_once(self):
        from apps.billing.models import PlatformManualPaymentClaim as Claim
        from apps.billing.services import manual_card_service as mcs
        from apps.core.models import AuditLogEntry

        claim = self.claim()
        calls = [
            (lambda r=r, n=n: mcs.approve_claim(Claim.objects.get(pk=claim.pk), reviewer=r, bank_confirmation_reference="BANK-CONC-0001", confirmed_amount="300000"))
            for n, r in enumerate(self.reviewers)
        ]
        results = run_in_threads(calls)
        self.assertTrue(all(kind == "ok" for kind, _ in results), results)
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, Claim.Status.APPROVED)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, 300000))
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_confirmed").count(), 1)
        self.assertEqual(Claim.objects.get(pk=claim.pk).events.filter(action="approved").count(), 1)

    def test_approve_racing_reject_and_cancel_has_exactly_one_winner_and_never_activates_after_a_loss(self):
        from apps.billing.models import PlatformManualPaymentClaim as Claim
        from apps.billing.services import manual_card_service as mcs

        claim = self.claim()
        fresh = lambda: Claim.objects.get(pk=claim.pk)
        results = run_in_threads([
            lambda: mcs.approve_claim(fresh(), reviewer=self.reviewers[0], bank_confirmation_reference="BANK-CONC-0002", confirmed_amount="300000"),
            lambda: mcs.reject_claim(fresh(), reviewer=self.reviewers[1], reason="رسید نامعتبر"),
            lambda: mcs.cancel_claim(fresh(), user=self.owner),
            lambda: mcs.approve_claim(fresh(), reviewer=self.reviewers[2], bank_confirmation_reference="BANK-CONC-0002", confirmed_amount="300000"),
        ])
        final = Claim.objects.get(pk=claim.pk)
        self.assertIn(final.status, (Claim.Status.APPROVED, Claim.Status.REJECTED, Claim.Status.CANCELLED))
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        if final.status == Claim.Status.APPROVED:
            self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, 300000))
        else:
            self.assertEqual(int(invoice.amount_paid), 0)
            self.assertTrue(invoice.is_payable)
        terminal = final.events.exclude(action="submitted").values_list("action", flat=True)
        self.assertEqual(len(set(terminal)), 1, list(terminal))                                  # one terminal decision recorded

    def test_the_same_reference_submitted_by_two_stores_at_once_creates_one_claim(self):
        from django.db import IntegrityError  # noqa: F401

        from apps.billing.models import PlatformManualPaymentClaim as Claim
        from apps.billing.services import manual_card_service as mcs

        stores = []
        for n in range(4):
            store = Store.objects.create(name=f"رقیب {n}", slug=f"conc-rival-{n}", admin_subdomain=f"conc-rival-{n}")
            _sub, invoice = open_invoice_for(store, code=f"concrival{n}", price="100000")
            stores.append((store, invoice))
        from django.utils import timezone

        results = run_in_threads([
            (lambda s=s, i=i: mcs.submit_claim(user=self.owner, store=s, reference="RACE-REF-998877", transferred_at=timezone.now(), invoice=i))
            for s, i in stores
        ])
        winners = [r for kind, r in results if kind == "ok"]
        losers = [r for kind, r in results if kind == "err"]
        self.assertEqual(len(winners), 1, results)
        self.assertTrue(all(isinstance(e, (mcs.DuplicateReferenceError, mcs.ClaimError)) for e in losers), losers)
        self.assertEqual(Claim.objects.filter(reference_key="racerefs"[:0] + winners[0].reference_key).count(), 1)

    def test_one_bank_statement_line_cannot_approve_two_claims_at_once(self):
        from django.utils import timezone

        from apps.billing.models import PlatformManualPaymentClaim as Claim
        from apps.billing.services import manual_card_service as mcs

        pairs = []
        for n in range(3):
            store = Store.objects.create(name=f"بانک {n}", slug=f"conc-bank-{n}", admin_subdomain=f"conc-bank-{n}")
            _sub, invoice = open_invoice_for(store, code=f"concbank{n}", price="120000")
            pairs.append((invoice, mcs.submit_claim(user=self.owner, store=store, reference=f"BANK-RACE-TRK-{n}0099", transferred_at=timezone.now(), invoice=invoice)))
        results = run_in_threads([
            (lambda c=c, r=r: mcs.approve_claim(Claim.objects.get(pk=c.pk), reviewer=r, bank_confirmation_reference="ONE-STATEMENT-LINE", confirmed_amount="120000"))
            for (_i, c), r in zip(pairs, self.reviewers)
        ])
        approved = [c for _i, c in pairs if Claim.objects.get(pk=c.pk).status == Claim.Status.APPROVED]
        self.assertEqual(len(approved), 1, results)
        paid = [i for i, _c in pairs if int(SubscriptionInvoice.objects.get(pk=i.pk).amount_paid) > 0]
        self.assertEqual(len(paid), 1)

    def test_sms_claim_approval_race_credits_once(self):
        from django.utils import timezone

        from apps.billing.models import PlatformManualPaymentClaim as Claim
        from apps.billing.services import manual_card_service as mcs

        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})
        package = SmsPackage.objects.create(name="بسته", credit_amount=200, price=70_000)
        purchase = balance_service.request_purchase(store=self.store, package=package)
        claim = mcs.submit_claim(user=self.owner, store=self.store, reference="SMS-RACE-445566", transferred_at=timezone.now(), sms_purchase=purchase)
        results = run_in_threads([
            (lambda r=r: mcs.approve_claim(Claim.objects.get(pk=claim.pk), reviewer=r, bank_confirmation_reference="BANK-SMS-RACE", confirmed_amount="70000"))
            for r in self.reviewers
        ])
        self.assertTrue(all(kind == "ok" for kind, _ in results), results)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 200)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=purchase).count(), 1)

