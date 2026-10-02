"""L1: چرخه‌ی عمرِ سفارش — اثرهای جانبیِ هر گذار دقیقاً یک‌بار و در همه‌ی مسیرها یکسان.

این تست‌ها ابتدا روی کدِ پیش از facade نوشته و سبز شدند (characterization) و بعد از
استخراجِ ``lifecycle.apply_payment_success`` بدونِ تغییر سبز ماندند."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.cart.models import Coupon
from apps.catalog.models import Product
from apps.engagement.models import Campaign
from apps.notifications.models import NotificationOutbox
from apps.orders.encryption import reset_fernet
from apps.orders.models import (
    CouponRedemption, Order, OrderStatusHistory, PaymentAttempt, PaymentGatewayConfig, Refund, Transaction,
)
from apps.orders.services.gateway_payment_service import (
    PaymentVerificationFailed, initiate_payment, process_callback_and_verify,
)
from apps.orders.services.order_service import change_order_status
from apps.orders.services.payment_service import simulate_payment
from apps.orders.services.refund_service import execute_order_refund
from apps.orders.tests.engine_base import EngineBase
from apps.sms.models import SmsBalance, SmsLog, SmsTemplate

R = CouponRedemption.Status


class LifecycleBase(EngineBase):
    def setUp(self):
        super().setUp()
        reset_fernet()
        SmsTemplate.ensure_defaults()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 1000})
        self.p = self._product("lc", "1000000", discount=0)
        self.coupon = self._coupon("LC10", value=10, usage_limit=5)

    def tearDown(self):
        reset_fernet()

    def new_order(self, coupon=True, qty=1):
        return self._order(self._cart(lines=[(self.p, qty)]), self.coupon if coupon else None)

    def signature(self, order):
        order.refresh_from_db()
        redemption = CouponRedemption.objects.filter(order=order).first()
        return {
            "payment_status": order.payment_status,
            "status": order.status,
            "redemption": redemption.status if redemption else None,
            "coupon_used": Coupon.objects.get(pk=self.coupon.pk).used_count,
            "tx_ok": Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(),
            "tx_total": Transaction.objects.filter(order=order).count(),
            "history": list(OrderStatusHistory.objects.filter(order=order).order_by("pk").values_list("from_status", "to_status")),
            "events": sorted(NotificationOutbox.objects.filter(order=order).values_list("event_key", "channel")),
            "sms": sorted(SmsLog.objects.filter(store=self.store).values_list("event_key", flat=True)),
            "stock": Product.objects.get(pk=self.p.pk).stock,
        }

    def gateway_pay(self, order, *, ok=True):
        config, _ = PaymentGatewayConfig.objects.get_or_create(store=self.store, gateway_code="zibal", defaults={"is_active": True})
        config.set_credentials({"merchant": "m"})
        config.save()
        attempt = PaymentAttempt.objects.create(
            store=self.store, order=order, gateway_config=config, amount=order.grand_total, currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY, gateway_track_id=f"t-{order.pk}-{PaymentAttempt.objects.count()}",
        )
        response = MagicMock()
        response.json.return_value = (
            {"result": 100, "amount": int(order.grand_total) * 10, "status": 1, "refNumber": "REF-1", "cardNumber": "6037-99XX-XXXX-5678"}
            if ok else {"result": 202, "status": -1, "message": "cancel"}
        )
        with patch("apps.orders.gateways.zibal.requests.post", return_value=response):
            with self.captureOnCommitCallbacks(execute=True):
                return attempt, process_callback_and_verify(
                    attempt_public_id=attempt.public_id, callback_data={"trackId": attempt.gateway_track_id, "success": "1" if ok else "0"},
                    store=self.store,
                )


class PaymentSuccessParityTests(LifecycleBase):
    def test_simulated_and_gateway_success_have_identical_effects(self):
        a = self.new_order()
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(a, True, store=self.store)
        sig_simulated = self.signature(a)
        SmsLog.objects.all().delete()
        Coupon.objects.filter(pk=self.coupon.pk).update(used_count=0)
        b = self.new_order()
        self.gateway_pay(b)
        sig_gateway = self.signature(b)
        for key in ("payment_status", "status", "redemption", "tx_ok", "tx_total", "history", "sms"):
            self.assertEqual(sig_simulated[key], sig_gateway[key], key)
        self.assertEqual(sig_simulated["events"], sig_gateway["events"])
        self.assertEqual(sig_simulated["payment_status"], Order.PaymentStatus.PAID)
        self.assertEqual(sig_simulated["status"], Order.Status.PROCESSING)
        self.assertEqual(sig_simulated["redemption"], R.REDEEMED)
        self.assertEqual(sig_simulated["tx_ok"], 1)
        self.assertEqual(sig_simulated["history"], [("", "pending"), ("pending", "processing")])
        self.assertIn("payment_success", sig_simulated["sms"])
        self.assertIn("payment.succeeded", [e for e, _ in sig_simulated["events"]])

    def test_success_effects_run_exactly_once_even_if_repeated(self):
        order = self.new_order()
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(order, True, store=self.store)
        with self.assertRaises(ValueError):
            simulate_payment(order, True, store=self.store)  # قبلاً پرداخت شده
        sig = self.signature(order)
        self.assertEqual((sig["tx_ok"], sig["coupon_used"], sig["sms"].count("payment_success")), (1, 1, 1))
        self.assertEqual([e for e, _ in sig["events"]].count("payment.succeeded"), 1)

    def test_duplicate_gateway_callback_is_idempotent(self):
        order = self.new_order()
        attempt, _ = self.gateway_pay(order)
        before = self.signature(order)
        again = process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store)
        self.assertTrue(again.is_final)
        self.assertEqual(self.signature(order), before)

    def test_second_attempt_after_paid_is_canceled_not_double_paid(self):
        order = self.new_order()
        self.gateway_pay(order)
        before = self.signature(order)
        attempt2, result = self.gateway_pay(order)
        self.assertEqual(result.status, PaymentAttempt.Status.CANCELED)
        self.assertEqual(self.signature(order), before)

    def test_success_without_coupon_has_no_redemption_side_effects(self):
        order = self.new_order(coupon=False)
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(order, True, store=self.store)
        sig = self.signature(order)
        self.assertIsNone(sig["redemption"])
        self.assertEqual(sig["coupon_used"], 0)
        self.assertEqual(sig["payment_status"], Order.PaymentStatus.PAID)

    def test_engagement_event_campaign_hook_runs_after_commit_for_both_paths(self):
        calls = []
        with patch("apps.engagement.services.campaign_service.run_event_campaigns", side_effect=lambda store, customer: calls.append(customer.pk)):
            a = self.new_order()
            with self.captureOnCommitCallbacks(execute=True):
                simulate_payment(a, True, store=self.store)
            b = self.new_order()
            self.gateway_pay(b)
        self.assertEqual(calls, [self.customer.pk, self.customer.pk])

    def test_payment_success_on_canceled_order_rolls_back_atomically(self):
        """رفتارِ فعلی (حفظ‌شده): سفارشِ لغوشده پرداخت نمی‌شود و هیچ اثر جانبی‌ای باقی نمی‌ماند."""
        order = self.new_order()
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        before = self.signature(order)
        with self.assertRaises(ValueError):
            simulate_payment(order, True, store=self.store)
        self.assertEqual(self.signature(order), before)


class PaymentFailureAndRetryTests(LifecycleBase):
    def test_failed_simulated_payment_effects_and_retry_success(self):
        order = self.new_order()
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(order, False, store=self.store)
        sig = self.signature(order)
        self.assertEqual((sig["payment_status"], sig["status"], sig["redemption"], sig["coupon_used"]),
                         (Order.PaymentStatus.FAILED, Order.Status.PENDING, R.RELEASED, 0))
        self.assertEqual(sig["tx_ok"], 0)
        self.assertEqual(sig["sms"], ["payment_failed"])  # order_placed در on_commit ثبتِ سفارش (خارج از capture)
        self.assertIn("payment.failed", [e for e, _ in sig["events"]])
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(order, True, store=self.store)  # تلاشِ دوباره
        sig = self.signature(order)
        self.assertEqual((sig["payment_status"], sig["status"], sig["redemption"], sig["coupon_used"], sig["tx_ok"]),
                         (Order.PaymentStatus.PAID, Order.Status.PROCESSING, R.REDEEMED, 1, 1))

    def test_gateway_failure_keeps_order_payable_and_capacity_reserved(self):
        order = self.new_order()
        with self.assertRaises(PaymentVerificationFailed):
            self.gateway_pay(order, ok=False)
        sig = self.signature(order)
        self.assertEqual((sig["payment_status"], sig["status"], sig["redemption"], sig["coupon_used"], sig["tx_total"]),
                         (Order.PaymentStatus.PENDING, Order.Status.PENDING, R.RESERVED, 1, 0))
        # تلاشِ بعدی با موفقیت تمام می‌شود
        self.gateway_pay(order)
        sig = self.signature(order)
        self.assertEqual((sig["payment_status"], sig["redemption"], sig["tx_ok"]), (Order.PaymentStatus.PAID, R.REDEEMED, 1))


class CodNeverAutoPaidTests(LifecycleBase):
    def test_cod_selection_and_delivery_do_not_mark_paid(self):
        order = self.new_order()
        cod, _ = PaymentGatewayConfig.objects.get_or_create(store=self.store, gateway_code="cod", defaults={"is_active": True})
        attempt = initiate_payment(order=order, gateway_config=cod, callback_url="https://x/cb", store=self.store)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        with self.captureOnCommitCallbacks(execute=True):
            for status in (Order.Status.PROCESSING, Order.Status.SHIPPED, Order.Status.DELIVERED):
                change_order_status(order, status, store=self.store)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)  # تأییدِ دریافت: گردشِ کارِ جداگانه
        self.assertEqual(Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 0)
        self.assertEqual(CouponRedemption.objects.get(order=order).status, R.RESERVED)
        self.assertTrue(attempt.pk)

    def test_cod_verification_never_pays(self):
        order = self.new_order()
        cod, _ = PaymentGatewayConfig.objects.get_or_create(store=self.store, gateway_code="cod", defaults={"is_active": True})
        attempt = PaymentAttempt.objects.create(
            store=self.store, order=order, gateway_config=cod, amount=order.grand_total, currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY, gateway_track_id="cod-x",
        )
        with self.assertRaises(PaymentVerificationFailed):
            process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)


class CancellationAndRefundRegressionTests(LifecycleBase):
    def test_cancel_unpaid_order_restocks_releases_coupon_notifies_once(self):
        order = self.new_order(qty=2)
        stock_after_order = Product.objects.get(pk=self.p.pk).stock
        with self.captureOnCommitCallbacks(execute=True):
            change_order_status(order, Order.Status.CANCELED, store=self.store)
        sig = self.signature(order)
        self.assertEqual(sig["stock"], stock_after_order + 2)
        self.assertEqual((sig["status"], sig["redemption"], sig["coupon_used"]), (Order.Status.CANCELED, R.RELEASED, 0))
        self.assertEqual(sig["history"][-1], ("pending", "canceled"))
        self.assertEqual([e for e, _ in sig["events"]].count("order.canceled"), 1)
        self.assertEqual(sig["sms"].count("order_canceled"), 1)
        with self.assertRaises(ValueError):
            change_order_status(order, Order.Status.PROCESSING, store=self.store)  # نهایی

    def test_cancel_paid_order_releases_coupon_and_restocks_without_touching_payment_status(self):
        order = self.new_order()
        with self.captureOnCommitCallbacks(execute=True):
            simulate_payment(order, True, store=self.store)
            change_order_status(order, Order.Status.CANCELED, store=self.store)
        sig = self.signature(order)
        self.assertEqual((sig["payment_status"], sig["redemption"], sig["coupon_used"]), (Order.PaymentStatus.PAID, R.RELEASED, 0))

    def test_full_and_partial_refunds_keep_ledger_gift_wrap_and_status_consistent(self):
        order = self.new_order(qty=2)
        simulate_payment(order, True, store=self.store)
        item = order.items.first()
        first = execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}], restock=True)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)  # جزئی
        self.assertEqual(CouponRedemption.objects.get(order=order).status, R.REDEEMED)
        second = execute_order_refund(order, store=self.store, actor=None, line_requests=[{"order_item_id": item.pk, "quantity": 1}], restock=True)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(CouponRedemption.objects.get(order=order).status, R.REFUNDED)
        self.assertEqual(Coupon.objects.get(pk=self.coupon.pk).used_count, 1)  # ظرفیتِ خریدِ تکمیل‌شده برنمی‌گردد
        self.assertEqual(first.approved_amount + second.approved_amount, order.grand_total - order.shipping_cost - order.shipping_tax)
        self.assertEqual(Refund.objects.filter(order=order).count(), 2)
        self.assertEqual(NotificationOutbox.objects.filter(order=order, event_key="refund.completed").count(), 2)
        from apps.cart.management.commands.verify_coupon_consistency import Command
        self.assertEqual(Command.collect(self.store), [])


class FacadeContractTests(LifecycleBase):
    def test_conditional_transition_returns_none_and_runs_no_side_effects(self):
        from apps.orders.services.lifecycle import apply_payment_success

        order = self.new_order()
        before = self.signature(order)
        # شرطِ from_statuses برقرار نیست (سفارش pending است، فقط از failed مجاز) ⇒ هیچ اثری
        self.assertIsNone(apply_payment_success(order, store=self.store, ref_id="x", note="n", from_statuses=(Order.PaymentStatus.FAILED,)))
        self.assertEqual(self.signature(order), before)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)

    def test_already_paid_is_a_noop_for_default_guard(self):
        from apps.orders.services.lifecycle import apply_payment_success

        order = self.new_order()
        simulate_payment(order, True, store=self.store)
        before = self.signature(order)
        self.assertIsNone(apply_payment_success(order, store=self.store, ref_id="y", note="n"))
        self.assertEqual(self.signature(order), before)

    def test_explicit_gateway_is_recorded_on_the_transaction(self):
        from apps.orders.models import PaymentGateway

        other = PaymentGateway.objects.create(store=self.store, name="دیگر", slug="gw-other-lc")
        order = self.new_order()
        tx = simulate_payment(order, True, gateway=other, store=self.store)
        self.assertEqual(tx.gateway_id, other.pk)
        self.assertEqual(tx.amount, order.grand_total)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)  # شیِ درحافظه هم به‌روز است
