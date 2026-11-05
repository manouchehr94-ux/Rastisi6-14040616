"""Saman (SEP) and Mellat (Behpardakht) through the platform billing bridge — mocked transports only, gates opened explicitly.

Proves platform behaviour around the contracts AS ENCODED in the adapters (those contracts are unverified against the providers'
current official documents): form-POST redirect, unique sale reference, forged / replayed / mismatched callbacks, verify (+settle)
before activation, ambiguity ⇒ pending, reconcile recovery, SMS credit exactly once. Never proves live readiness."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service as flow
from apps.billing.services import sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.billing.tests.test_platform_gated_providers import GatedBase, MELLAT_CREDS, SAMAN_CREDS
from apps.orders.tests.test_mellat_adapter import FakeMellat
from apps.orders.tests.test_saman_adapter import FakeSep
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage
from apps.sms.services import balance_service
from apps.stores.models import Store
from apps.subscriptions.models import StoreSubscription

S = SubscriptionPaymentAttempt.Status
HOST = "platformadmins.rastisi.localhost"


class EchoSep(FakeSep):
    """The bank's VerifyTransaction answer names the RefNum it was asked about (as the real service does)."""

    def __call__(self, url, json=None, timeout=None, **kw):
        response = super().__call__(url, json=json, timeout=timeout, **kw)
        body = response._body
        if isinstance(body, dict) and isinstance(body.get("TransactionDetail"), dict) and json and json.get("RefNum"):
            body["TransactionDetail"]["RefNum"] = json["RefNum"]
        return response


def sep_callback(attempt, *, ref="SEP-REF-0001", state="OK"):
    return {"State": state, "RefNum": ref, "ResNum": attempt.provider_session_id, "RRN": "123", "TraceNo": "9", "SecurePan": "603799******0019"}


def mellat_callback(attempt, *, ref="SALE-REF-0001", code="0"):
    return {"ResCode": code, "RefId": "REF-ID-1", "SaleOrderId": attempt.provider_session_id, "SaleReferenceId": ref,
            "CardHolderPan": "603799******0019"}


class PspBase(GatedBase):
    PRICE = "250000"

    def setUp(self):
        super().setUp()
        self.fake_sep = EchoSep()
        self.fake_mellat = FakeMellat()
        from apps.orders.gateways.mellat import MELLAT_SERVICE_URL

        def router(url, *args, **kwargs):             # both adapters use the same ``requests.post`` object: route by URL
            return (self.fake_mellat if url == MELLAT_SERVICE_URL else self.fake_sep)(url, *args, **kwargs)

        patcher = patch("apps.orders.gateways.saman.requests.post", router)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store.objects.create(name="فروشگاه پی‌اس‌پی", slug="psp-store", admin_subdomain="psp-store")
        self.sub, self.invoice = open_invoice_for(self.store, code="psp", price=self.PRICE)

    def prepare(self, code):
        self.configure(code)
        self.open_gates(code)
        # the fake bank echoes the amount the adapter was asked to charge (rial = toman × 10)
        rial = int(Decimal(self.PRICE)) * 10
        self.fake_sep.verify["TransactionDetail"]["OrginalAmount"] = rial
        self.fake_sep.verify["TransactionDetail"]["AffectiveAmount"] = rial

    def start(self, code, invoice=None):
        return flow.start_payment(invoice or self.invoice, provider=code, callback_base_url="https://rastisi.ir")

    def inv(self):
        return SubscriptionInvoice.objects.get(pk=self.invoice.pk)

    def activated(self):
        return StoreSubscription.objects.get(pk=self.sub.pk).status == StoreSubscription.Status.ACTIVE


class SamanBridgeTests(PspBase):
    def test_checkout_uses_a_post_form_redirect_with_the_token_and_a_short_alphanumeric_order_code(self):
        self.prepare("saman")
        attempt, session = self.start("saman")
        self.assertEqual(session.extra["post_fields"], {"Token": "TOKEN-SYNTH"})
        self.assertEqual(attempt.status, S.PENDING)
        self.assertRegex(attempt.provider_session_id, r"^B\d{9}$")                      # ResNum = our order code
        self.assertNotIn("post_fields", attempt.provider_extra)                          # the one-time token is never persisted
        self.assertFalse(self.activated())
        sent = self.fake_sep.calls[0][1]
        self.assertEqual((sent["Amount"], sent["ResNum"]), (int(self.PRICE) * 10, attempt.provider_session_id))

    def test_the_redirect_response_is_an_auto_submitting_post_form_not_a_get_url(self):
        self.prepare("saman")
        _attempt, session = self.start("saman")
        response = flow.gateway_redirect("saman", session.redirect_url, session.extra.get("post_fields"))
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('method="post"', body.lower())
        self.assertIn('name="Token"', body)
        self.assertIn("TOKEN-SYNTH", body)
        self.assertNotIn("TOKEN-SYNTH", response.get("Location", ""))
        self.assertEqual(response["Cache-Control"].split(",")[0].strip(), "no-store") if "Cache-Control" in response else None

    def test_a_verified_callback_activates_exactly_once_and_stores_the_unique_ref_as_the_payment_id(self):
        self.prepare("saman")
        attempt, _ = self.start("saman")
        done = flow.confirm_from_provider_verification(attempt, callback_data=sep_callback(attempt))
        self.assertEqual((done.status, done.provider_payment_id), (S.SUCCEEDED, "SEP-REF-0001"))
        self.assertTrue(self.activated())
        calls = [u for u, _ in self.fake_sep.calls]
        for _ in range(3):
            flow.confirm_from_provider_verification(done, callback_data=sep_callback(attempt))
        self.assertEqual(self.inv().amount_paid, Decimal(self.PRICE))
        self.assertEqual(len(self.fake_sep.calls), len(calls))                                # no further provider calls after success

    def test_a_forged_success_callback_is_ignored_when_the_bank_does_not_confirm(self):
        self.prepare("saman")
        attempt, _ = self.start("saman")
        self.fake_sep.verify = {"Success": False, "ResultCode": -2}
        out = flow.confirm_from_provider_verification(attempt, callback_data=sep_callback(attempt))
        self.assertEqual(out.status, S.PENDING)
        self.assertEqual(self.inv().amount_paid, 0)
        self.assertFalse(self.activated())

    def test_a_forged_order_number_cannot_redirect_the_check_and_a_wrong_amount_never_activates(self):
        self.prepare("saman")
        attempt, _ = self.start("saman")
        # server-stored ResNum always wins over the browser's; the bank's own answer is still what decides.
        self.fake_sep.verify = {"Success": False, "ResultCode": -2}
        forged = {**sep_callback(attempt), "ResNum": "B999999999"}
        out = flow.confirm_from_provider_verification(attempt, callback_data=forged)
        self.assertEqual((out.status, self.inv().amount_paid), (S.PENDING, 0))
        # a bank answer that names a DIFFERENT order is refused (defence in depth if the real contract returns ResNum)
        self.fake_sep.verify = {"Success": True, "ResultCode": 0, "TransactionDetail": {
            "RefNum": "SEP-REF-0001", "ResNum": "B999999999", "OrginalAmount": int(self.PRICE) * 10, "AffectiveAmount": int(self.PRICE) * 10}}
        with self.assertRaises(Exception):
            flow.confirm_from_provider_verification(attempt, callback_data=sep_callback(attempt))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, self.inv().amount_paid), (S.REQUIRES_ACTION, 0))
        # …and so is a wrong amount
        attempt.status = S.PENDING
        attempt.save(update_fields=["status"])
        self.fake_sep.verify = {"Success": True, "ResultCode": 0, "TransactionDetail": {
            "RefNum": "SEP-REF-0001", "OrginalAmount": int(self.PRICE) * 10 - 10, "AffectiveAmount": int(self.PRICE) * 10 - 10}}
        with self.assertRaises(Exception):
            flow.confirm_from_provider_verification(attempt, callback_data=sep_callback(attempt))
        self.assertEqual(self.inv().amount_paid, 0)
        self.assertFalse(self.activated())

    def test_the_provider_reference_can_fulfil_only_one_attempt(self):
        self.prepare("saman")
        first, _ = self.start("saman")
        flow.confirm_from_provider_verification(first, callback_data=sep_callback(first, ref="SEP-REF-REUSED"))
        other_store = Store.objects.create(name="دیگر", slug="psp-other", admin_subdomain="psp-other")
        _sub2, invoice2 = open_invoice_for(other_store, code="psp2", price=self.PRICE)
        second, _ = self.start("saman", invoice2)
        with self.assertRaises(Exception):
            flow.confirm_from_provider_verification(second, callback_data=sep_callback(second, ref="SEP-REF-REUSED"))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice2.pk).amount_paid, 0)       # a replayed receipt pays nothing twice

    def test_a_bank_declined_callback_fails_the_attempt_only_when_the_server_agrees(self):
        self.prepare("saman")
        attempt, _ = self.start("saman")
        out = flow.confirm_from_provider_verification(attempt, callback_data={"State": "CanceledByUser", "ResNum": attempt.provider_session_id})
        self.assertEqual(out.status, S.FAILED)
        self.assertFalse(self.activated())

    def test_refunds_try_the_reverse_within_the_window_and_otherwise_stay_manual(self):
        from apps.billing.providers.registry import get_provider

        self.prepare("saman")
        attempt, _ = self.start("saman")
        flow.confirm_from_provider_verification(attempt, callback_data=sep_callback(attempt))
        result = get_provider("saman").refund_payment(provider_payment_id="SEP-REF-0001", amount=Decimal(self.PRICE), currency="IRT", idempotency_key="r1")
        self.assertTrue(result.succeeded or result.raw_summary.get("manual"))
        partial = get_provider("saman").refund_payment(provider_payment_id="SEP-REF-0001", amount=Decimal("1"), currency="IRT", idempotency_key="r2")
        self.assertFalse(partial.succeeded)                                                    # partial ⇒ always manual
        self.assertTrue(partial.raw_summary.get("manual"))


class MellatBridgeTests(PspBase):
    def settle_ops(self):
        return [op for op in self.fake_mellat.ops() if op in ("bpVerifyRequest", "bpSettleRequest")]

    def test_checkout_posts_a_form_with_the_ref_id_and_uses_a_numeric_order_id(self):
        self.prepare("mellat")
        attempt, session = self.start("mellat")
        self.assertEqual(session.extra["post_fields"], {"RefId": "REF-ID-1"})
        self.assertRegex(attempt.provider_session_id, r"^1\d{9}$")                              # numeric: 1 + pk (subscription)
        pay = [p for op, p in self.fake_mellat.calls if op == "bpPayRequest"][0]
        self.assertEqual((pay["orderId"], pay["amount"]), (attempt.provider_session_id, str(int(self.PRICE) * 10)))
        self.assertFalse(self.activated())

    def test_activation_needs_verify_and_then_settle_in_that_order(self):
        self.prepare("mellat")
        attempt, _ = self.start("mellat")
        done = flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt))
        self.assertEqual((done.status, done.provider_payment_id), (S.SUCCEEDED, "SALE-REF-0001"))
        self.assertEqual(self.settle_ops(), ["bpVerifyRequest", "bpSettleRequest"])
        self.assertTrue(self.activated())

    def test_a_settle_failure_keeps_it_pending_and_unfulfilled_then_inquiry_and_settle_recover(self):
        self.prepare("mellat")
        attempt, _ = self.start("mellat")
        self.fake_mellat.answers["bpSettleRequest"] = "17"                                      # not settled
        out = flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt))
        self.assertEqual(out.status, S.PENDING)
        self.assertEqual(self.inv().amount_paid, 0)
        self.assertFalse(self.activated())
        self.fake_mellat.calls.clear()
        self.fake_mellat.answers["bpSettleRequest"] = "0"
        done = flow.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        self.assertEqual(done.status, S.SUCCEEDED)
        self.assertEqual(self.fake_mellat.ops(), ["bpInquiryRequest", "bpSettleRequest"])        # never verifies a second time
        self.assertEqual(self.inv().amount_paid, Decimal(self.PRICE))

    def test_already_settled_answers_are_idempotent_not_errors(self):
        self.prepare("mellat")
        attempt, _ = self.start("mellat")
        self.fake_mellat.answers.update({"bpVerifyRequest": "43", "bpSettleRequest": "45"})      # already verified / already settled
        self.assertEqual(flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt)).status, S.SUCCEEDED)

    def test_reversed_transactions_are_never_treated_as_settled(self):
        self.prepare("mellat")
        attempt, _ = self.start("mellat")
        self.fake_mellat.answers["bpSettleRequest"] = "17"
        flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt))
        self.fake_mellat.answers["bpInquiryRequest"] = "48"                                      # reversed by the bank
        with self.assertRaises(Exception):
            flow.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.FAILED, "provider_terminal_failure"))
        self.assertEqual(self.inv().amount_paid, 0)
        self.assertFalse(self.activated())

    def test_forged_callbacks_change_nothing(self):
        self.prepare("mellat")
        attempt, _ = self.start("mellat")
        self.fake_mellat.answers["bpVerifyRequest"] = "41"
        out = flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt))
        self.assertEqual((out.status, self.inv().amount_paid), (S.PENDING, 0))
        no_ref = {**mellat_callback(attempt), "SaleReferenceId": ""}
        self.assertEqual(flow.confirm_from_provider_verification(attempt, callback_data=no_ref).status, S.PENDING)
        wrong_order = {**mellat_callback(attempt), "SaleOrderId": "1999999999"}
        self.assertEqual(flow.confirm_from_provider_verification(attempt, callback_data=wrong_order).status, S.PENDING)
        self.assertFalse(self.activated())
        failed = flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt, code="17"))
        self.assertEqual(failed.status, S.FAILED)                                                # ResCode≠0 and nothing verified

    def test_the_sale_reference_can_fulfil_only_one_attempt(self):
        self.prepare("mellat")
        first, _ = self.start("mellat")
        flow.confirm_from_provider_verification(first, callback_data=mellat_callback(first, ref="SALE-REUSED"))
        other_store = Store.objects.create(name="دیگرِ ملت", slug="psp-mellat-2", admin_subdomain="psp-mellat-2")
        _s, invoice2 = open_invoice_for(other_store, code="psp3", price=self.PRICE)
        second, _ = self.start("mellat", invoice2)
        with self.assertRaises(Exception):
            flow.confirm_from_provider_verification(second, callback_data=mellat_callback(second, ref="SALE-REUSED"))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice2.pk).amount_paid, 0)

    def test_reconcile_recovers_a_verified_but_unsettled_payment_once(self):
        from datetime import timedelta
        from django.utils import timezone

        self.prepare("mellat")
        attempt, _ = self.start("mellat")
        self.fake_mellat.answers["bpSettleRequest"] = "17"
        flow.confirm_from_provider_verification(attempt, callback_data=mellat_callback(attempt))
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=2))
        self.fake_mellat.answers["bpSettleRequest"] = "0"
        for _ in range(2):
            call_command("reconcile_platform_payments", stdout=StringIO())
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.SUCCEEDED)
        self.assertEqual(self.inv().amount_paid, Decimal(self.PRICE))


class PspSmsTests(PspBase):
    CREDITS, SMS_PRICE = 250, 60_000

    def test_sms_credit_lands_exactly_once_for_both_providers_with_one_ledger_row(self):
        for code, cb in (("saman", sep_callback), ("mellat", mellat_callback)):
            with self.subTest(code):
                store = Store.objects.create(name=f"پیامک {code}", slug=f"sms-{code}", admin_subdomain=f"sms-{code}")
                SmsBalance.objects.update_or_create(store=store, defaults={"credits": 5})
                package = SmsPackage.objects.create(name=f"بسته {code}", credit_amount=self.CREDITS, price=self.SMS_PRICE)
                self.configure(code)
                self.open_gates(code)
                self.fake_sep.verify["TransactionDetail"]["OrginalAmount"] = self.SMS_PRICE * 10
                purchase = balance_service.request_purchase(store=store, package=package)
                attempt, _s = sms_svc.start_payment(purchase, callback_base_url="https://rastisi.ir", provider=code)
                self.assertRegex(attempt.provider_session_id, r"^S?2?\d+$" if code == "mellat" else r"^S\d{9}$")
                for _ in range(3):
                    sms_svc.verify_and_fulfill(attempt, callback_data=cb(attempt, ref=f"SMS-REF-{code}"))
                self.assertEqual(SmsBalance.objects.get(store=store).credits, 5 + self.CREDITS)
                self.assertEqual(SmsCreditLedger.objects.filter(store=store).count(), 1)
