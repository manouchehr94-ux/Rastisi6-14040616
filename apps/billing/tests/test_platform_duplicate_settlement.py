"""Late settlements / duplicate charges: a merchant retries an unresolved online payment and BOTH attempts later settle.
Fulfilment stays exactly once for both products; the surplus money is detected, recorded, visible in reconciliation and can be
refunded / resolved by finance through audited, idempotent actions — without ever touching the fulfilled purchase."""

import threading
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import duplicate_payment_service as dups
from apps.billing.services import payment_flow_service, refund_service, sms_purchase_payment_service
from apps.billing.tests.platform_payment_support import ready_platform_zibal
from apps.billing.tests.test_platform_checkout import (
    KINDS, OWNER_HOST, PLATFORM_HOST, SMS, SMS_CREDITS, SMS_PRICE, SUB, SUB_PRICE, CheckoutBase,
)
from apps.core.models import AuditLogEntry
from apps.portal.platform_admin_views import reconciliation_snapshot
from apps.sms.models import SmsCreditLedger, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store
from apps.subscriptions.models import StoreSubscription

User = get_user_model()


class _Resp:
    def __init__(self, payload):
        self._p, self.status_code = payload, 200

    def json(self):
        return self._p


class MultiTrackZibal:
    """In-process Zibal where every ``request`` gets its own trackId and EVERY track the bank was told about verifies as paid
    (the worst case: both attempts of one purchase really settled)."""

    def __init__(self):
        self.n = 8000
        self.tracks = {}

    def __call__(self, url, json=None, timeout=None, **kw):
        path = url.rsplit("/", 1)[-1]
        if path == "request":
            self.n += 1
            self.tracks[self.n] = {"orderId": json["orderId"], "amount": json["amount"]}
            return _Resp({"result": 100, "trackId": self.n, "message": "success"})
        if path == "verify":
            t = self.tracks[int(json["trackId"])]
            return _Resp({"result": 100, "amount": t["amount"], "status": 1, "refNumber": str(500000 + int(json["trackId"])), "orderId": t["orderId"]})
        raise AssertionError(url)


class DuplicateBase(CheckoutBase):
    def setUp(self):
        super().setUp()
        self.bank = MultiTrackZibal()
        patcher = mock.patch("apps.billing.providers.zibal.requests.post", self.bank)
        patcher.start()
        self.addCleanup(patcher.stop)
        ready_platform_zibal(self)

    def two_attempts(self, kind):
        self.pay(kind, "zibal")
        self.pay(kind, "zibal", ack="1")                     # merchant retries the unresolved online payment
        first, second = list(self.attempts(kind).order_by("pk"))
        self.assertEqual(self.attempts(kind).count(), 2)
        return first, second

    def verify(self, kind, attempt):
        cache.clear()
        return self.callback(attempt)

    def staff_post(self, kind, attempt, action, **data):
        return self.admin_client.post(f"/payments/duplicates/{kind}/{attempt.pk}/{action}/", data)


class BothAttemptsSettleTests(DuplicateBase):
    def assert_single_effect(self, kind):
        if kind == SUB:
            invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
            self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, SUB_PRICE))
            self.assertEqual(StoreSubscription.objects.get(pk=self.sub.pk).status, StoreSubscription.Status.ACTIVE)
        else:
            self.assertEqual(self.credits(), 100 + SMS_CREDITS)
            self.assertEqual(SmsCreditLedger.objects.filter(purchase=self.purchase).count(), 1)

    def test_the_later_attempt_settling_after_the_first_never_fulfils_twice_and_is_recorded_as_a_duplicate(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                first, second = self.two_attempts(kind)
                self.verify(kind, first)
                self.assert_single_effect(kind)
                self.verify(kind, second)                      # the late settlement of the retried attempt
                self.assert_single_effect(kind)
                second.refresh_from_db()
                self.assertEqual(second.status, type(second).Status.REQUIRES_ACTION)
                self.assertIn(second.failure_code, ("duplicate_payment", "purchase_completed"))
                self.assertTrue(dups.is_duplicate(second))
                self.assertEqual(int(second.amount), self.price(kind))                  # the surplus amount is on record
                self.assertTrue(second.provider_payment_id or second.provider_session_id)
                first.refresh_from_db()
                self.assertEqual(first.status, type(first).Status.SUCCEEDED)
                html = self.page(kind).content.decode()
                self.assertIn('data-state="paid"', html)

    def test_the_retry_attempt_settling_first_wins_and_the_original_late_payment_is_the_duplicate(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                first, second = self.two_attempts(kind)
                self.verify(kind, second)
                self.verify(kind, first)
                self.assert_single_effect(kind)
                first.refresh_from_db()
                second.refresh_from_db()
                self.assertEqual((second.status, first.status), (type(second).Status.SUCCEEDED, type(first).Status.REQUIRES_ACTION))

    def test_replaying_either_callback_changes_nothing_further(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                first, second = self.two_attempts(kind)
                for _ in range(3):
                    self.verify(kind, first)
                    self.verify(kind, second)
                self.assert_single_effect(kind)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.duplicate_payment_flagged").count(), 1)   # subscription only (SMS uses its own code path)

    def test_the_duplicate_is_audited_and_listed_in_reconciliation_with_the_money_amount(self):
        for kind in KINDS:
            first, second = self.two_attempts(kind)
            self.verify(kind, first)
            self.verify(kind, second)
        snapshot = reconciliation_snapshot()
        sub_rows, sms_rows = snapshot["requires_action"]
        self.assertEqual([(r.is_duplicate, int(r.amount)) for r in sub_rows], [(True, SUB_PRICE)])
        self.assertEqual([(r.is_duplicate, int(r.amount)) for r in sms_rows], [(True, SMS_PRICE)])
        page = self.admin_client.get("/payments/reconciliation/").content.decode()
        self.assertIn("پرداختِ تکراری", page)
        self.assertIn("/payments/duplicates/", page)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.duplicate_payment_flagged").count(), 1)

    def test_a_manual_card_approval_after_an_online_payment_never_double_fulfils_either(self):
        from apps.billing.tests.test_platform_card_to_card import enable_platform_card

        enable_platform_card(self)
        first, _ = self.two_attempts(SUB)
        self.verify(SUB, first)
        self.assert_single_effect(SUB)
        self.assertEqual(int(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid), SUB_PRICE)


class DuplicateResolutionTests(DuplicateBase):
    def settled_pair(self, kind):
        first, second = self.two_attempts(kind)
        self.verify(kind, first)
        self.verify(kind, second)
        second.refresh_from_db()
        return second

    def test_finance_can_request_a_refund_of_exactly_the_duplicate_and_it_is_idempotent_and_leaves_the_purchase_untouched(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                dup = self.settled_pair(kind)
                before_paid = SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid
                self.staff_post(kind, dup, "refund", reason="پرداختِ تکراریِ مرچنت")
                self.staff_post(kind, dup, "refund", reason="پرداختِ تکراریِ مرچنت")
                dup.refresh_from_db()
                resolution = dups.resolution_of(dup)
                self.assertIn(resolution["outcome"], ("refunded", "pending_manual"))
                self.assertEqual(dup.status, type(dup).Status.REQUIRES_ACTION)           # the fact is immutable
                self.assert_untouched(kind, before_paid)
                self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.duplicate_payment_refund_requested", object_type=type(dup).__name__, object_id=str(dup.pk)).count(), 1)

    def assert_untouched(self, kind, before_paid):
        if kind == SUB:
            invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
            self.assertEqual((invoice.status, invoice.amount_paid), (SubscriptionInvoice.Status.PAID, before_paid))
            self.assertEqual(refund_service.refundable_amount(invoice), invoice.amount_paid)   # the duplicate does not inflate it
        else:
            self.assertEqual(self.credits(), 100 + SMS_CREDITS)
            self.assertEqual(SmsPackagePurchase.objects.get(pk=self.purchase.pk).status, SmsPackagePurchase.Status.COMPLETED)

    def test_recording_an_external_settlement_needs_a_reference_removes_it_from_the_open_list_and_keeps_history(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                dup = self.settled_pair(kind)
                self.staff_post(kind, dup, "resolve", outcome="refunded_external", reference="")
                self.assertFalse(dups.is_resolved(type(dup).objects.get(pk=dup.pk)))              # reference is mandatory
                self.staff_post(kind, dup, "resolve", outcome="bogus", reference="BANK-REF-1234")
                self.assertFalse(dups.is_resolved(type(dup).objects.get(pk=dup.pk)))
                self.staff_post(kind, dup, "resolve", outcome="refunded_external", reference="BANK-REF-778899")
                self.staff_post(kind, dup, "resolve", outcome="credited", reference="OTHER-REF-000000")      # first resolution stands
                dup = type(dup).objects.get(pk=dup.pk)
                self.assertEqual(dups.resolution_of(dup)["outcome"], "refunded_external")
                self.assertEqual(dups.resolution_of(dup)["reference"], "BANK-REF-778899")
        snapshot = reconciliation_snapshot()
        self.assertEqual((snapshot["requires_action"][0], snapshot["requires_action"][1]), ([], []))
        self.assertEqual((len(snapshot["duplicates_resolved"][0]), len(snapshot["duplicates_resolved"][1])), (1, 1))

    def test_only_finance_can_act_and_only_on_real_duplicates(self):
        dup = self.settled_pair(SUB)
        plain_staff = User.objects.create_user(username="pcdup-staff@example.com", password="pass12345", is_staff=True)
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(plain_staff)
        url = f"/payments/duplicates/{SUB}/{dup.pk}/refund/"
        self.assertIn(client.post(url, {"reason": "test reason"}).status_code, (302, 403))          # not platform finance: login redirect / forbidden
        self.assertEqual(self.owner_client.post(url, {"reason": "x"}, HTTP_HOST=OWNER_HOST).status_code, 404)       # merchants never reach it
        self.assertFalse(dups.resolution_of(type(dup).objects.get(pk=dup.pk)))
        # a non-duplicate REQUIRES_ACTION (amount mismatch) cannot be "refunded" through this path
        ready_platform_zibal(self)
        self.pay(SMS, "zibal")
        att = self.attempts(SMS).get()
        SmsPackagePaymentAttempt.objects.filter(pk=att.pk).update(status="requires_action", failure_code="amount_mismatch")
        with self.assertRaises(dups.DuplicatePaymentError):
            dups.refund_duplicate(SMS, att.pk, actor=self.finance, reason="should be refused")

    def test_the_merchant_page_tells_the_truth_after_a_duplicate(self):
        self.settled_pair(SUB)
        html = self.page(SUB).content.decode()
        self.assertIn('data-state="paid"', html)
        self.assertIn("پرداختِ تکراری", html)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SimultaneousSettlementTests(TransactionTestCase):
    """Both attempts verify at the same instant (PostgreSQL row locks): exactly one fulfils, the other is the recorded duplicate."""

    def setUp(self):
        from apps.billing.tests.platform_payment_support import open_invoice_for
        from apps.sms.models import SmsBalance, SmsPackage

        self.addCleanup(cache.clear)
        cache.clear()
        self.bank = MultiTrackZibal()
        patcher = mock.patch("apps.billing.providers.zibal.requests.post", self.bank)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store.objects.create(name="هم‌زمان۲", slug="pcsim", admin_subdomain="pcsim", status=Store.Status.ACTIVE)
        self.sub, self.invoice = open_invoice_for(self.store, code="pcsim", price=str(SUB_PRICE))
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        self.package = SmsPackage.objects.create(name="هم‌زمان۲", credit_amount=SMS_CREDITS, price=SMS_PRICE)
        self.purchase = balance_service.request_purchase(store=self.store, package=self.package)
        ready_platform_zibal(self)

    def _race(self, attempts, verify):
        def worker(att):
            try:
                verify(type(att).objects.get(pk=att.pk))
            except Exception:  # noqa: BLE001 — a domain error on the losing side is fine; corruption is not
                pass
            finally:
                connection.close()

        pool = [threading.Thread(target=worker, args=(a,)) for a in attempts]
        [t.start() for t in pool]
        [t.join() for t in pool]

    def test_subscription_two_attempts_verified_simultaneously(self):
        a1, _ = payment_flow_service.start_payment(self.invoice, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
        a2, _ = payment_flow_service.start_payment(self.invoice, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
        self._race([a1, a2], payment_flow_service.confirm_from_provider_verification)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, SUB_PRICE))
        statuses = sorted(SubscriptionPaymentAttempt.objects.filter(invoice=invoice).values_list("status", flat=True))
        self.assertEqual(statuses, ["requires_action", "succeeded"])
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(status="requires_action").failure_code, "duplicate_payment")

    def test_sms_two_attempts_verified_simultaneously(self):
        a1, _ = sms_purchase_payment_service.start_payment(self.purchase, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
        a2, _ = sms_purchase_payment_service.start_payment(self.purchase, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
        self._race([a1, a2], sms_purchase_payment_service.verify_and_fulfill)
        from apps.sms.models import SmsBalance

        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100 + SMS_CREDITS)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=self.purchase).count(), 1)
        statuses = sorted(SmsPackagePaymentAttempt.objects.filter(purchase=self.purchase).values_list("status", flat=True))
        self.assertEqual(statuses, ["requires_action", "succeeded"])
