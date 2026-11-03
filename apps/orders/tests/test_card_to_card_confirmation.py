"""B3 (BLOCKER 3): انتقالِ دستیِ کارت به کارت تا تأییدِ فروشنده «در انتظار» می‌ماند.

* پس از ``initiate_payment`` تلاشِ کارت به کارت ``PENDING`` است و سفارش پرداخت‌نشده (بدونِ ``verified_at``)؛
* تأییدِ فروشنده سفارش را دقیقاً یک‌بار پرداخت‌شده می‌کند و یک تراکنش می‌سازد؛
* مسیرِ رد سفارش را در ``pending`` و بدونِ جابه‌جاییِ پول نگه می‌دارد؛
* تأییدِ تکراری idempotent است (نه تراکنشِ دوم، نه بازخریدِ دوباره‌ی کوپن)؛
* مبلغِ نادرست رد می‌شود؛
* عدم‌رگرسیونِ COD: پس از ``initiate_payment`` تلاشِ COD ``SUCCEEDED`` و سفارش ``PENDING`` است."""

from decimal import Decimal

from django.contrib.auth import get_user_model

from apps.core.models import AuditLogEntry
from apps.orders.models import (
    CouponRedemption, Order, PaymentAttempt, PaymentGateway, PaymentGatewayConfig, Transaction,
)
from apps.orders.services import card_to_card_payment_service as c2c
from apps.orders.services.gateway_payment_service import initiate_payment
from apps.orders.tests.test_payment_safety import SafetyBase

R = CouponRedemption.Status


class CardToCardBase(SafetyBase):
    def setUp(self):
        super().setUp()
        self.customer.email = "c2c-buyer@example.com"
        self.customer.save(update_fields=["email"])
        self.c2c_gw = PaymentGateway.objects.create(
            store=self.store, name="کارت به کارت", slug="card_to_card"
        )
        self.config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="card_to_card", is_active=True
        )
        self.config.set_credentials({"card_number": "6037997599995995", "cardholder_name": "علی"})
        self.config.save()
        self.actor = get_user_model().objects.create_user(
            username="09127744444", password="x12345678", email="mgr-c2c@example.com"
        )

    def c2c_order(self, coupon=True, qty=1):
        order = self.new_order(coupon=coupon, qty=qty)
        Order.objects.filter(pk=order.pk).update(payment_gateway=self.c2c_gw)
        order.refresh_from_db()
        return order

    def initiate(self, order):
        with self.captureOnCommitCallbacks(execute=True):
            return initiate_payment(
                order=order, gateway_config=self.config,
                callback_url="https://x/cb", store=self.store,
            )

    def confirm(self, order, **kw):
        args = dict(
            store=self.store, actor=self.actor, amount=order.grand_total,
            reference="RC-C2C", idempotency_key="tok-c2c-1",
        )
        args.update(kw)
        with self.captureOnCommitCallbacks(execute=True):
            return c2c.confirm_transfer(order.pk, **args)

    def tx_ok(self, order):
        return Transaction.objects.filter(order=order, status=Transaction.Status.OK).count()


class PendingAtSelectionTests(CardToCardBase):
    def test_initiate_leaves_attempt_pending_and_order_unpaid(self):
        order = self.c2c_order()
        attempt = self.initiate(order)
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        self.assertIsNone(attempt.verified_at)
        self.assertEqual(attempt.gateway_track_id, f"card2card-{order.code}")
        self.assertNotIn("cod-", attempt.gateway_track_id)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(self.tx_ok(order), 0)
        # کوپن تا تأیید فقط رزرو می‌ماند
        self.assertEqual(self.signature(order)["redemption"], R.RESERVED)

    def test_receipt_submission_never_auto_verifies(self):
        # تلاش در انتظار می‌ماند؛ هیچ گذارِ خودکاری به SUCCEEDED رخ نمی‌دهد.
        order = self.c2c_order()
        self.initiate(order)
        self.assertFalse(
            PaymentAttempt.objects.filter(
                order=order, status=PaymentAttempt.Status.SUCCEEDED
            ).exists()
        )
        self.assertTrue(c2c.can_confirm(order))


class ConfirmationTests(CardToCardBase):
    def test_merchant_confirmation_pays_order_once(self):
        order = self.c2c_order()
        self.initiate(order)
        tx = self.confirm(order)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.PENDING)  # advance_to_processing=False
        self.assertEqual(self.tx_ok(order), 1)
        self.assertEqual((tx.ref_id, tx.amount, tx.confirmed_by_id), ("RC-C2C", order.grand_total, self.actor.pk))
        self.assertEqual(tx.method, Transaction.Method.GATEWAY)
        self.assertIsNotNone(tx.confirmed_at)
        self.assertEqual(self.signature(order)["redemption"], R.REDEEMED)
        self.assertEqual(
            AuditLogEntry.objects.filter(
                action_code="order.card_to_card_payment_confirmed", object_id=str(order.pk)
            ).count(),
            1,
        )

    def test_confirmation_sends_no_sms(self):
        from apps.sms.models import SmsLog

        order = self.c2c_order()
        self.initiate(order)
        self.confirm(order)
        self.assertEqual(SmsLog.objects.filter(event_key="payment_success").count(), 0)

    def test_duplicate_confirmation_is_idempotent(self):
        order = self.c2c_order()
        self.initiate(order)
        self.confirm(order)
        before_tx = self.tx_ok(order)
        before_used = self.signature(order)["coupon_used"]
        for key in ("tok-c2c-1", "tok-other"):
            with self.assertRaises(c2c.AlreadyConfirmed):
                self.confirm(order, idempotency_key=key)
        self.assertEqual(self.tx_ok(order), before_tx)  # بدونِ تراکنشِ دوم
        self.assertEqual(self.signature(order)["coupon_used"], before_used)  # بدونِ بازخریدِ دوباره
        self.assertEqual(
            AuditLogEntry.objects.filter(action_code="order.card_to_card_payment_confirmed").count(),
            1,
        )

    def test_wrong_amount_is_rejected(self):
        order = self.c2c_order()
        self.initiate(order)
        for bad in (order.grand_total - 1, order.grand_total + 1, "abc", ""):
            with self.assertRaises(c2c.CardToCardConfirmationError):
                self.confirm(order, amount=bad)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(self.tx_ok(order), 0)

    def test_canceled_and_non_card_to_card_orders_rejected(self):
        from apps.orders.services.order_service import change_order_status

        canceled = self.c2c_order()
        self.initiate(canceled)
        change_order_status(canceled, Order.Status.CANCELED, store=self.store)
        with self.assertRaises(c2c.CardToCardConfirmationError):
            self.confirm(canceled)
        online = self.new_order()  # درگاهِ آنلاین/غیرِ کارت به کارت
        with self.assertRaises(c2c.CardToCardConfirmationError):
            self.confirm(online)
        self.assertEqual(self.tx_ok(canceled), 0)


class RejectionTests(CardToCardBase):
    def test_rejection_leaves_order_pending_without_money(self):
        order = self.c2c_order()
        attempt = self.initiate(order)
        c2c.reject_transfer(order.pk, store=self.store, actor=self.actor, reason="رسید نامعتبر")
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(self.tx_ok(order), 0)
        self.assertEqual(attempt.status, PaymentAttempt.Status.CANCELED)
        self.assertEqual(attempt.failure_code, "card_to_card_rejected")
        self.assertEqual(
            AuditLogEntry.objects.filter(
                action_code="order.card_to_card_payment_rejected", object_id=str(order.pk)
            ).count(),
            1,
        )

    def test_cannot_reject_a_paid_order(self):
        order = self.c2c_order()
        self.initiate(order)
        self.confirm(order)
        with self.assertRaises(c2c.CardToCardConfirmationError):
            c2c.reject_transfer(order.pk, store=self.store, actor=self.actor)


class CodRegressionTests(SafetyBase):
    """عدم‌رگرسیونِ COD: SUCCEEDED-at-selection همچنان برقرار است."""

    def setUp(self):
        super().setUp()
        self.cod_config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="cod", is_active=True
        )

    def test_cod_attempt_is_succeeded_and_order_pending_at_selection(self):
        order = self.new_order()
        with self.captureOnCommitCallbacks(execute=True):
            attempt = initiate_payment(
                order=order, gateway_config=self.cod_config,
                callback_url="https://x/cb", store=self.store,
            )
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertIsNotNone(attempt.verified_at)
        self.assertEqual(attempt.gateway_track_id, f"cod-{order.code}")
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(
            Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 0
        )
