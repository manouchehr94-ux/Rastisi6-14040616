"""H1: مغایرتِ مبلغ و نتیجه‌ی نامشخصِ تأییدِ درگاه — هیچ مغایرتِ تأییدشده یا مشکوکی بی‌صدا گم نمی‌شود و
هیچ مغایرتِ مبلغی سفارش را خودکار «پرداخت‌شده» نمی‌کند. «تأییدشده» فقط وقتی که خودِ درگاه گفته باشد؛
«مشکوک» هرگز ادعایی دربارهٔ موفقیتِ پرداخت نیست."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.test import Client, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ShopSettings
from apps.notifications.models import NotificationOutbox
from apps.orders.gateways.base import (
    GatewayAmountMismatchError, GatewayConnectionError, GatewayResponseError,
)
from apps.orders.gateways.zibal import ZibalAdapter
from apps.orders.models import Order, PaymentAttempt, PaymentReconciliation, Transaction
from apps.orders.services.gateway_payment_service import (
    PaymentAmountMismatch, PaymentVerificationFailed, process_callback_and_verify,
)
from apps.orders.services.order_expiry_service import expire_unpaid_orders
from apps.orders.services.order_service import change_order_status
from apps.orders.tests.test_payment_safety import SafetyBase, failed_response, ok_response
from apps.stores.models import StoreMembership

K = PaymentReconciliation.Kind
L = PaymentReconciliation.EvidenceLevel
CLAIM = {"success": "1", "status": "2"}  # پارامترهایِ بازگشتِ زیبال با ادعای پرداخت


def response_with(order, **overrides):
    response = MagicMock()
    data = {"result": 100, "amount": int(order.grand_total) * 10, "status": 1, "refNumber": "REF-X", "cardNumber": "6037-99XX-XXXX-5678"}
    data.update(overrides)
    data = {k: v for k, v in data.items() if v is not None}
    response.json.return_value = data
    return response


class ZibalAdapterContractTests(SimpleTestCase):
    """قراردادِ پاسخِ verify (مستندات: result 100 = تأییدِ تازه، 201 = قبلاً تأییدشده؛ amount به ریال) با HTTP ماک‌شده."""

    def verify(self, data=None, exc=None, expected=Decimal("5000")):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = data
        patcher = patch("apps.orders.gateways.zibal.requests.post", side_effect=exc) if exc else patch(
            "apps.orders.gateways.zibal.requests.post", return_value=response
        )
        with patcher:
            return ZibalAdapter().verify_payment(
                track_id="t1", expected_amount=expected, currency="TOMAN", credentials={"merchant": "m"}, callback_data={},
            )

    def test_correct_amount_in_rial_is_success_for_fresh_and_already_verified(self):
        for code in (100, 201):
            result = self.verify({"result": code, "amount": 50000, "status": 1, "refNumber": 99})
            self.assertTrue(result.success, code)
            self.assertEqual(result.ref_id, "99")

    def test_toman_sent_as_rial_is_a_confirmed_mismatch_with_evidence(self):
        for code in (100, 201):
            with self.assertRaises(GatewayAmountMismatchError) as ctx:
                self.verify({"result": code, "amount": 5000, "refNumber": 7, "cardNumber": "6037-XX"})  # تومان به‌جایِ ریال
            ev = ctx.exception.details["evidence"]
            self.assertEqual((ev["expected_rial"], ev["returned_rial"], ev["ref_id"], ev["result_code"]), (50000, 5000, "7", code))

    def test_amount_as_numeric_string_is_accepted(self):
        self.assertTrue(self.verify({"result": 100, "amount": "50000", "refNumber": 1}).success)

    def test_success_without_or_with_unreadable_amount_is_ambiguous_not_success(self):
        for bad in (None, "", "abc", [1]):
            data = {"result": 100, "refNumber": 5}
            if bad is not None:
                data["amount"] = bad
            with self.assertRaises(GatewayResponseError) as ctx:
                self.verify(data)
            self.assertEqual(ctx.exception.code, "amount_unavailable")
            self.assertNotIn("returned_rial", ctx.exception.details["evidence"])

    def test_rejected_result_is_plain_failure_without_amount_check(self):
        result = self.verify({"result": 202, "status": -1, "message": "x"})
        self.assertFalse(result.success)

    def test_transport_problems_raise_connection_errors(self):
        for exc in (requests.ConnectionError(), requests.Timeout()):
            with self.assertRaises(GatewayConnectionError):
                self.verify(exc=exc)
        with self.assertRaises(GatewayResponseError):
            self.verify({"no": "result"})


class AmountMismatchFlowTests(SafetyBase):
    def run_callback(self, attempt, response, data=None):
        with patch("apps.orders.gateways.zibal.requests.post", return_value=response) as post:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    return process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data=data or {}, store=self.store), post
                except PaymentVerificationFailed as exc:
                    return exc, post

    def test_correct_amount_pays_the_order_without_a_record(self):
        order = self.new_order()
        attempt = self.attempt(order)
        result, _ = self.run_callback(attempt, ok_response(order))
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(PaymentReconciliation.objects.count(), 0)

    def test_confirmed_mismatch_keeps_evidence_and_never_pays_the_order(self):
        for factor, label in ((Decimal("0.1"), "toman_as_rial"), (Decimal("0.5"), "underpaid"), (Decimal("2"), "overpaid")):
            with self.subTest(label):
                order = self.new_order()
                attempt = self.attempt(order)
                before = self.snapshot(order)
                reported_rial = int(order.grand_total * 10 * factor)
                result, post = self.run_callback(attempt, response_with(order, amount=reported_rial, refNumber=f"REF-{label}"))
                self.assertIsInstance(result, PaymentAmountMismatch)
                self.assertEqual(post.call_count, 1)
                attempt.refresh_from_db()
                self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)  # پولِ درگاه واقعاً جابه‌جا شده
                self.assertEqual(attempt.gateway_ref_id, f"REF-{label}")
                record = PaymentReconciliation.objects.get(attempt=attempt)
                self.assertEqual((record.kind, record.evidence_level, record.status, record.store_id), (K.AMOUNT_MISMATCH, L.CONFIRMED, "open", self.store.pk))
                self.assertEqual(record.amount, order.grand_total)
                self.assertEqual(record.reported_amount, Decimal(reported_rial) / 10)
                self.assertEqual(record.evidence["returned_rial"], reported_rial)
                self.assertEqual(record.evidence["expected_rial"], int(order.grand_total) * 10)
                self.assertNotIn("merchant", str(record.evidence))
                after = self.snapshot(order)
                # سفارش پرداخت‌شده نشد، تراکنشِ OK/وضعیت/کد/موجودی دست‌نخورده
                for key in ("payment_status", "status", "redemption", "coupon_used", "tx_ok", "tx_total", "history", "stock"):
                    self.assertEqual(after[key], before[key], key)
                self.assertEqual(after["payment_status"], "pending")
                self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment", order=order).count(), 1)

    def test_duplicate_mismatch_callbacks_create_one_record_one_notification(self):
        order = self.new_order()
        attempt = self.attempt(order)
        bad = response_with(order, amount=1)
        self.run_callback(attempt, bad)
        _, post = self.run_callback(attempt, bad)
        post.assert_not_called()  # SUCCEEDED ⇒ idempotent
        self.assertEqual(PaymentReconciliation.objects.filter(order=order).count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment").count(), 1)

    def test_mismatch_on_canceled_order_does_not_reopen_or_touch_stock_and_coupon(self):
        order = self.new_order()
        attempt = self.attempt(order)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        before = self.snapshot(order)
        self.run_callback(attempt, response_with(order, amount=1))
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual((record.kind, record.order_status_at_detection), (K.AMOUNT_MISMATCH, "canceled"))
        after = self.snapshot(order)
        for key in ("payment_status", "status", "redemption", "coupon_used", "tx_ok", "history", "stock"):
            self.assertEqual(after[key], before[key], key)

    def test_second_attempt_mismatch_after_order_already_paid_adds_no_transaction(self):
        order = self.new_order()
        first, second = self.attempt(order), self.attempt(order)
        self.run_callback(first, ok_response(order))
        self.run_callback(second, response_with(order, amount=7, refNumber="REF-2"))
        self.assertEqual(Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1)
        self.assertEqual(PaymentReconciliation.objects.get(attempt=second).kind, K.AMOUNT_MISMATCH)
        self.assertFalse(PaymentReconciliation.objects.filter(attempt=first).exists())

    def test_two_successful_attempts_second_is_recorded_as_duplicate(self):
        order = self.new_order()
        first, second = self.attempt(order), self.attempt(order)
        self.run_callback(first, ok_response(order))
        self.run_callback(second, ok_response(order, ref="REF-DUP"))
        self.assertEqual(Transaction.objects.filter(order=order, status="ok").count(), 1)
        self.assertEqual(PaymentReconciliation.objects.get(attempt=second).kind, K.ALREADY_PAID)

    def test_open_reconciliation_blocks_automatic_expiry(self):
        shop = ShopSettings.provision_for(self.store)
        shop.unpaid_online_order_ttl_minutes = 60
        shop.unpaid_online_order_grace_minutes = 0
        shop.save()
        order = self.new_order()
        attempt = self.attempt(order)
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=5))
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(hours=5))
        self.run_callback(attempt, response_with(order, amount=1))
        PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentAttempt.Status.FAILED)  # حتی اگر تلاش باز نباشد
        stats = expire_unpaid_orders(store=self.store)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(stats["expired"], 0)


class AmbiguousVerificationTests(SafetyBase):
    def run_callback(self, attempt, *, response=None, exc=None, data=None):
        kwargs = {"side_effect": exc} if exc else {"return_value": response}
        with patch("apps.orders.gateways.zibal.requests.post", **kwargs):
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    return process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data=data or {}, store=self.store)
                except PaymentVerificationFailed as err:
                    return err

    def test_hidden_amount_with_claimed_success_is_suspected_and_not_asserted_as_paid(self):
        order = self.new_order()
        attempt = self.attempt(order)
        before = self.snapshot(order)
        result = self.run_callback(attempt, response=response_with(order, amount=None), data=CLAIM)
        self.assertIsInstance(result, PaymentVerificationFailed)
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual((record.kind, record.evidence_level, record.status), (K.VERIFY_AMBIGUOUS, L.SUSPECTED, "open"))
        self.assertIsNone(record.reported_amount)
        self.assertTrue(record.evidence["callback_claims_success"])
        attempt.refresh_from_db()
        self.assertNotEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)  # هرگز ادعایی دربارهٔ موفقیت
        after = self.snapshot(order)
        for key in ("payment_status", "status", "tx_ok", "redemption", "stock"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment").count(), 1)

    def test_transport_failure_with_claim_is_suspected_but_without_claim_is_plain_failure(self):
        order = self.new_order()
        claimed = self.attempt(order)
        self.run_callback(claimed, exc=requests.Timeout(), data=CLAIM)
        record = PaymentReconciliation.objects.get(attempt=claimed)
        self.assertEqual((record.kind, record.evidence_level, record.evidence["error_code"]), (K.VERIFY_AMBIGUOUS, L.SUSPECTED, "verify_timeout"))
        silent = self.attempt(order)
        self.run_callback(silent, exc=requests.ConnectionError(), data={"success": "0", "status": "3"})
        self.assertFalse(PaymentReconciliation.objects.filter(attempt=silent).exists())

    def test_gateway_rejection_is_never_suspected(self):
        order = self.new_order()
        attempt = self.attempt(order)
        self.run_callback(attempt, response=failed_response(), data=CLAIM)
        self.assertEqual(PaymentReconciliation.objects.count(), 0)

    def test_duplicate_ambiguous_callbacks_keep_one_record_and_one_notification(self):
        order = self.new_order()
        attempt = self.attempt(order)
        for _ in range(3):
            self.run_callback(attempt, exc=requests.Timeout(), data=CLAIM)
        self.assertEqual(PaymentReconciliation.objects.filter(order=order).count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment").count(), 1)

    def test_later_clean_verification_applies_payment_and_auto_closes_suspected_record(self):
        order = self.new_order()
        attempt = self.attempt(order)
        self.run_callback(attempt, exc=requests.Timeout(), data=CLAIM)
        result = self.run_callback(attempt, response=ok_response(order), data=CLAIM)
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        order.refresh_from_db()
        self.assertEqual((order.payment_status, Transaction.objects.filter(order=order, status="ok").count()), ("paid", 1))
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual((record.status, record.resolution, record.resolved_by), ("resolved", "auto_verified", None))

    def test_later_confirmation_on_canceled_order_upgrades_the_same_record(self):
        order = self.new_order()
        attempt = self.attempt(order)
        self.run_callback(attempt, exc=requests.Timeout(), data=CLAIM)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        self.run_callback(attempt, response=ok_response(order), data=CLAIM)
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual((record.kind, record.evidence_level, record.status), (K.ORDER_CANCELED, L.CONFIRMED, "open"))
        self.assertEqual(PaymentReconciliation.objects.filter(order=order).count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment").count(), 2)  # مشکوک + ارتقا
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), ("canceled", "pending"))


class ReconciliationInterfaceTests(SafetyBase):
    def setUp(self):
        super().setUp()
        from apps.dashboard.tests.test_coupon_views import HOST

        self.host = HOST
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        order = self.new_order()
        attempt = self.attempt(order)
        with patch("apps.orders.gateways.zibal.requests.post", return_value=response_with(order, amount=1, refNumber="REF-MM")):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(PaymentVerificationFailed):
                    process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store)
        self.order, self.record = order, PaymentReconciliation.objects.get()

    def login(self, role, suffix, store=None):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username=f"09127790{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=store or self.store, user=user, role=role, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=self.host if store is None else self.other_host)
        client.login(username=user.username, password="pass12345")
        return client

    def test_listing_shows_level_and_reported_amount_and_resolution_options(self):
        from apps.stores.models import Store

        from django.conf import settings as dj

        self.other_host = f"other-h1.{dj.RASTISI_ADMIN_DOMAIN_SUFFIX}"
        other = Store.objects.create(name="دیگر", slug="other-h1", status=Store.Status.ACTIVE, admin_subdomain="other-h1")
        with self.settings(ALLOWED_HOSTS=[self.host, self.other_host, "testserver"]):
            manager = self.login(StoreMembership.Role.ORDER_MANAGER, "01")
            page = manager.get(reverse("dashboard:payment-reconciliations"))
            self.assertContains(page, "تأییدشده توسط درگاه")
            self.assertContains(page, "مغایرت")
            self.assertContains(page, self.order.code)
            self.assertContains(page, "پس از بررسیِ پنلِ درگاه")
            # فروشگاهِ دیگر: نه رکورد را می‌بیند و نه می‌تواند آن را رسیدگی کند
            outsider = self.login(StoreMembership.Role.OWNER, "02", store=other)
            self.assertNotContains(outsider.get(reverse("dashboard:payment-reconciliations")), self.order.code)
            resp = outsider.post(reverse("dashboard:payment-reconciliation-resolve", args=[self.record.pk]), {"resolution": "no_action"})
            self.assertEqual(resp.status_code, 404)
            manager.post(
                reverse("dashboard:payment-reconciliation-resolve", args=[self.record.pk]),
                {"resolution": "refunded_outside", "note": "تفاوت برگشت داده شد"},
            )
        self.record.refresh_from_db()
        self.assertEqual((self.record.status, self.record.resolution), ("resolved", "refunded_outside"))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")  # رسیدگی هرگز سفارش را پرداخت‌شده نمی‌کند

    def test_customer_sees_mismatch_message_on_callback(self):
        order = self.new_order()
        attempt = self.attempt(order)
        client = Client()
        client.force_login(self.customer.user)
        if True:
            with patch("apps.orders.gateways.zibal.requests.post", return_value=response_with(order, amount=1)):
                response = client.get(reverse("orders:gateway-callback", args=[attempt.public_id]), follow=True)
        self.assertContains(response, "مطابقت")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, "pending")
