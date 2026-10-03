"""M1: امنیتِ پرداخت — سفارشِ لغوشده پرداخت نمی‌شود، callbackِ دیرهنگام/تکراری همیشه راستی‌آزمایی می‌شود،
پولِ تأییدشده‌ای که اعمال نشد در ``PaymentReconciliation`` می‌ماند (نه بازگشایی/پرداخت‌شده/رزروِ کد)،
و callback هرگز 500 کنترل‌نشده نمی‌دهد."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import Client
from django.urls import reverse

from apps.cart.models import Coupon
from apps.catalog.models import Product
from apps.notifications.models import NotificationOutbox
from apps.orders.gateways.base import PaymentVerificationResult
from apps.orders.models import (
    CouponRedemption, Order, PaymentAttempt, PaymentGatewayConfig, PaymentReconciliation, Transaction,
)
from apps.orders.services.gateway_payment_service import (
    OrderNotPayableError, PaymentVerificationFailed, initiate_payment, process_callback_and_verify,
)
from apps.orders.services.order_service import change_order_status
from apps.orders.tests.test_lifecycle import LifecycleBase
from apps.stores.models import StoreMembership

K = PaymentReconciliation.Kind
R = CouponRedemption.Status


def ok_response(order, ref="REF-LATE"):
    response = MagicMock()
    response.json.return_value = {"result": 100, "amount": int(order.grand_total) * 10, "status": 1, "refNumber": ref, "cardNumber": "6037-99XX-XXXX-5678"}
    return response


def failed_response():
    response = MagicMock()
    response.json.return_value = {"result": 202, "status": -1, "message": "cancel"}
    return response


class SafetyBase(LifecycleBase):
    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        owner = get_user_model().objects.create_user(username="09127711111", password="x12345678", email="owner@example.com")
        self.owner = owner
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )

    def attempt(self, order, status=PaymentAttempt.Status.REDIRECT_READY):
        config, _ = PaymentGatewayConfig.objects.get_or_create(store=self.store, gateway_code="zibal", defaults={"is_active": True})
        config.set_credentials({"merchant": "m"})
        config.save()
        return PaymentAttempt.objects.create(
            store=self.store, order=order, gateway_config=config, amount=order.grand_total, currency="TOMAN",
            status=status, gateway_track_id=f"trk-{order.pk}-{PaymentAttempt.objects.count()}",
        )

    def callback(self, attempt, response):
        with patch("apps.orders.gateways.zibal.requests.post", return_value=response) as post:
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    return process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data={}, store=self.store), post
                except PaymentVerificationFailed as exc:
                    return exc, post

    def snapshot(self, order):
        return {**self.signature(order), "reconciliations": PaymentReconciliation.objects.filter(order=order).count()}


class CanceledOrderGuardTests(SafetyBase):
    def test_initiate_payment_refuses_canceled_orders_and_creates_no_attempt(self):
        order = self.new_order()
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal", is_active=True)
        config.set_credentials({"merchant": "m"})
        config.save()
        stale = Order.objects.get(pk=order.pk)  # شیِ کهنه: هنوز pending در حافظه
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        with self.assertRaises(OrderNotPayableError):
            initiate_payment(order=stale, gateway_config=config, callback_url="https://x/cb", store=self.store)
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 0)

    def test_views_do_not_start_payment_for_canceled_order(self):
        order = self.new_order()
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        client = Client()
        client.force_login(self.customer.user)
        for name in ("orders:payment-initiate", "orders:payment-start"):
            response = client.get(reverse(name, args=[order.code]))
            self.assertIn(response.status_code, (200, 302), name)
            if response.status_code == 302:
                self.assertNotIn("zibal", response["Location"])
        self.assertContains(client.get(reverse("orders:payment-initiate", args=[order.code])), "لغو شده")
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 0)
        with self.settings(PAYMENTS_SIMULATION_ENABLED=True):
            client.get(reverse("orders:payment-callback", args=[order.code, "success"]))
        order.refresh_from_db()
        self.assertEqual((order.status, order.payment_status), (Order.Status.CANCELED, Order.PaymentStatus.PENDING))

    def test_change_order_status_uses_database_state_not_stale_object(self):
        order = self.new_order()
        stale = Order.objects.get(pk=order.pk)
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        with self.assertRaises(ValueError):  # نهایی — کهنه بودنِ شیِ stale نباید گذارِ دوباره اجازه دهد
            change_order_status(stale, Order.Status.PROCESSING, store=self.store)
        self.assertEqual(Product.objects.get(pk=self.p.pk).stock, 100)  # فقط یک‌بار restock


class LateGatewayPaymentTests(SafetyBase):
    def canceled_order_with_attempt(self):
        order = self.new_order()
        attempt = self.attempt(order)
        stock_before_cancel = Product.objects.get(pk=self.p.pk).stock
        change_order_status(order, Order.Status.CANCELED, store=self.store)
        return order, attempt, stock_before_cancel

    def test_late_success_on_canceled_order_is_recorded_not_applied(self):
        order, attempt, stock_before = self.canceled_order_with_attempt()
        before = self.snapshot(order)
        result, _ = self.callback(attempt, ok_response(order))
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual((record.kind, record.status, record.amount, record.gateway_ref_id), (K.ORDER_CANCELED, "open", order.grand_total, "REF-LATE"))
        self.assertEqual((record.order_status_at_detection, record.payment_status_at_detection), ("canceled", "pending"))
        self.assertEqual(record.evidence["ref_id"], "REF-LATE")
        self.assertNotIn("merchant", str(record.evidence))
        order.refresh_from_db()
        after = self.snapshot(order)
        # سفارش بازگشایی/پرداخت‌شده نشد، کد دوباره رزرو نشد، تراکنشِ OK ساخته نشد، موجودی دوباره کم نشد
        for key in ("payment_status", "status", "redemption", "coupon_used", "tx_ok", "tx_total", "history", "stock"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual((after["status"], after["payment_status"], after["redemption"], after["tx_ok"]), ("canceled", "pending", R.RELEASED, 0))
        self.assertEqual(after["reconciliations"], 1)
        mails = NotificationOutbox.objects.filter(event_key="staff.late_payment")
        self.assertEqual((mails.count(), mails.first().channel), (1, "email"))

    def test_duplicate_late_callbacks_are_idempotent_and_do_not_reverify(self):
        order, attempt, _ = self.canceled_order_with_attempt()
        self.callback(attempt, ok_response(order))
        _, post = self.callback(attempt, ok_response(order))
        post.assert_not_called()  # SUCCEEDED ⇒ idempotent
        self.assertEqual(PaymentReconciliation.objects.filter(order=order).count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment").count(), 1)

    def test_expired_and_canceled_and_failed_attempts_are_still_verified(self):
        for status in (PaymentAttempt.Status.EXPIRED, PaymentAttempt.Status.CANCELED, PaymentAttempt.Status.FAILED):
            order = self.new_order(coupon=False)
            attempt = self.attempt(order, status=status)
            result, post = self.callback(attempt, ok_response(order))
            self.assertEqual(post.call_count, 1, status)
            self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED, status)
            order.refresh_from_db()
            # سفارش هنوز قابل‌پرداخت بود ⇒ پولِ تأییدشده عادی اعمال می‌شود (گم نمی‌شود)
            self.assertEqual((order.payment_status, order.status), (Order.PaymentStatus.PAID, Order.Status.PROCESSING), status)
            self.assertEqual(PaymentReconciliation.objects.filter(order=order).count(), 0)

    def test_failed_verification_of_final_attempt_changes_nothing(self):
        order = self.new_order()
        for status in (PaymentAttempt.Status.EXPIRED, PaymentAttempt.Status.CANCELED, PaymentAttempt.Status.FAILED):
            attempt = self.attempt(order, status=status)
            attempt.failure_message = "قبلی"
            attempt.save(update_fields=["failure_message"])
            before = self.snapshot(order)
            result, post = self.callback(attempt, failed_response())
            self.assertIsInstance(result, PaymentVerificationFailed)
            self.assertEqual(post.call_count, 1)
            attempt.refresh_from_db()
            self.assertEqual((attempt.status, attempt.failure_message), (status, "قبلی"))
            self.assertEqual(self.snapshot(order), before)

    def test_attempt_without_track_id_is_not_sent_to_gateway(self):
        order = self.new_order()
        attempt = self.attempt(order, status=PaymentAttempt.Status.FAILED)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(gateway_track_id="")
        result, post = self.callback(attempt, ok_response(order))
        self.assertIsInstance(result, PaymentVerificationFailed)
        post.assert_not_called()

    def test_processing_error_preserves_evidence_without_partial_effects(self):
        order = self.new_order()
        attempt = self.attempt(order)
        before = self.snapshot(order)
        with patch("apps.orders.services.lifecycle.apply_payment_success", side_effect=RuntimeError("boom 09121234567")):
            result, _ = self.callback(attempt, ok_response(order))  # استثنا نمی‌دهد
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual(record.kind, K.PROCESSING_ERROR)
        self.assertIn("RuntimeError", record.error_message)
        after = self.snapshot(order)
        for key in ("payment_status", "status", "redemption", "tx_ok", "history"):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(NotificationOutbox.objects.filter(event_key="staff.late_payment").count(), 1)

    def test_gateway_callback_view_never_returns_500(self):
        order = self.new_order()
        attempt = self.attempt(order)
        client = Client()
        with patch("apps.orders.views.process_callback_and_verify", side_effect=RuntimeError("unexpected"), create=True), \
                patch("apps.orders.services.gateway_payment_service.process_callback_and_verify", side_effect=RuntimeError("unexpected")):
            response = client.get(reverse("orders:gateway-callback", args=[attempt.public_id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(order.code, response["Location"])

    def test_gateway_callback_view_late_payment_redirects_with_notice(self):
        order, attempt, _ = self.canceled_order_with_attempt()
        client = Client()
        client.force_login(self.customer.user)
        with patch("apps.orders.gateways.zibal.requests.post", return_value=ok_response(order)):
            response = client.get(reverse("orders:gateway-callback", args=[attempt.public_id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PaymentReconciliation.objects.filter(attempt=attempt).exists())
        self.assertContains(response, "پرداخت شما دریافت شد")

    def test_second_confirmed_attempt_for_paid_order_is_reconciled(self):
        order = self.new_order()
        first = self.attempt(order)
        self.callback(first, ok_response(order, "REF-1"))
        second = self.attempt(order)
        result, _ = self.callback(second, ok_response(order, "REF-2"))
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(PaymentReconciliation.objects.get(attempt=second).kind, K.ALREADY_PAID)
        self.assertEqual(Transaction.objects.filter(order=order, status="ok").count(), 1)
        self.assertEqual(self.signature(order)["coupon_used"], 1)

    def test_retry_after_failed_attempt_still_works(self):
        order = self.new_order()
        first = self.attempt(order)
        result, _ = self.callback(first, failed_response())
        self.assertIsInstance(result, PaymentVerificationFailed)
        second = self.attempt(order)
        result, _ = self.callback(second, ok_response(order))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)


class ReconciliationAdminTests(SafetyBase):
    """پنلِ مدیریتِ تطبیق: دسترسی، ایزولاسیونِ Store، رسیدگیِ idempotent."""

    def setUp(self):
        super().setUp()
        from django.test import override_settings  # noqa: F401
        from apps.dashboard.tests.test_coupon_views import HOST

        self.host = HOST
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.order = self.new_order()
        self.attempt_obj = self.attempt(self.order)
        change_order_status(self.order, Order.Status.CANCELED, store=self.store)
        self.callback(self.attempt_obj, ok_response(self.order))
        self.record = PaymentReconciliation.objects.get()

    def login(self, role, suffix):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        if role == StoreMembership.Role.OWNER:
            client = Client(HTTP_HOST=self.host)
            client.force_login(self.owner)
            return client
        user = get_user_model().objects.create_user(username=f"09127700{suffix}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=role, status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        client = Client(HTTP_HOST=self.host)
        client.login(username=user.username, password="pass12345")
        return client

    def test_permissions_and_listing(self):
        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.login(StoreMembership.Role.OWNER, "01")
            response = owner.get(reverse("dashboard:payment-reconciliations"))
            self.assertContains(response, self.order.code)
            self.assertContains(response, "REF-LATE")
            analyst = self.login(StoreMembership.Role.ANALYST, "02")
            self.assertEqual(analyst.get(reverse("dashboard:payment-reconciliations")).status_code, 200)
            self.assertEqual(analyst.post(reverse("dashboard:payment-reconciliation-resolve", args=[self.record.pk]), {"resolution": "no_action"}).status_code, 403)
            catalog = self.login(StoreMembership.Role.CATALOG_MANAGER, "03")
            self.assertEqual(catalog.get(reverse("dashboard:payment-reconciliations")).status_code, 403)
            self.record.refresh_from_db()
            self.assertEqual(self.record.status, "open")

    def test_resolve_is_idempotent_audited_and_scoped(self):
        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            manager = self.login(StoreMembership.Role.ORDER_MANAGER, "04")
            url = reverse("dashboard:payment-reconciliation-resolve", args=[self.record.pk])
            self.assertEqual(manager.post(url, {"resolution": "bogus"}).status_code, 302)
            self.record.refresh_from_db()
            self.assertEqual(self.record.status, "open")
            manager.post(url, {"resolution": "refunded_outside", "note": "برگشت به کارت"})
            manager.post(url, {"resolution": "no_action"})  # دومین بار تغییری نمی‌دهد
            self.record.refresh_from_db()
            self.assertEqual((self.record.status, self.record.resolution, self.record.resolution_note), ("resolved", "refunded_outside", "برگشت به کارت"))
            self.assertIsNotNone(self.record.resolved_by)
            from apps.core.models import AuditLogEntry

            self.assertEqual(AuditLogEntry.objects.filter(action_code="payment_reconciliation.resolved").count(), 1)
            # رسیدگی اثری بر سفارش/پرداخت ندارد
            self.order.refresh_from_db()
            self.assertEqual((self.order.status, self.order.payment_status), ("canceled", "pending"))
            # Store دیگر ⇒ 404
            from apps.stores.models import Store

            other = Store.objects.create(name="o", slug="recon-other", status=Store.Status.ACTIVE)
            self.record.store = other
            self.record.save(update_fields=["store"])
            self.assertEqual(manager.post(url, {"resolution": "no_action"}).status_code, 404)
