"""M3: تأییدِ دستیِ دریافتِ وجهِ پرداخت در محل — امن، یک‌باره، بدونِ پیامک، بدونِ تغییرِ وضعیتِ سفارش،
ظرفیتِ کد تا تأیید رزرو، و اصلاح فقط با استرداد."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.cart.management.commands.verify_coupon_consistency import Command as ConsistencyCommand
from apps.core.models import AuditLogEntry
from apps.notifications.models import NotificationOutbox
from apps.orders.models import CouponRedemption, Order, OrderStatusHistory, PaymentGateway, Refund, Transaction
from apps.orders.services import cod_payment_service as cod
from apps.orders.services.order_definitions import valid_orders
from apps.orders.services.order_service import change_order_status
from apps.orders.services.refund_service import execute_order_refund
from apps.orders.tests.test_payment_safety import SafetyBase
from apps.sms.models import SmsLog
from apps.stores.models import StoreMembership

R = CouponRedemption.Status
M = Transaction.Method


class CodBase(SafetyBase):
    def setUp(self):
        super().setUp()
        self.customer.email = "cod-buyer@example.com"
        self.customer.save(update_fields=["email"])
        self.cod_gw = PaymentGateway.objects.create(store=self.store, name="پرداخت در محل", slug="cod")
        self.actor = get_user_model().objects.create_user(username="09127733333", password="x12345678", email="mgr@example.com")

    def cod_order(self, status=None, coupon=True, qty=1):
        order = self.new_order(coupon=coupon, qty=qty)
        Order.objects.filter(pk=order.pk).update(payment_gateway=self.cod_gw)
        order.refresh_from_db()
        if status:
            for step in ("processing", "shipped", "delivered"):
                change_order_status(order, step, store=self.store)
                if step == status:
                    break
        return order

    def confirm(self, order, **kw):
        args = dict(store=self.store, actor=self.actor, amount=order.grand_total, method=M.COD_CASH, reference="RC-1", idempotency_key="tok-1")
        args.update(kw)
        with self.captureOnCommitCallbacks(execute=True):
            return cod.confirm_collection(order.pk, **args)

    def state(self, order):
        order.refresh_from_db()
        return {
            "status": order.status, "payment_status": order.payment_status,
            "tx": Transaction.objects.filter(order=order, status="ok").count(),
            "history": OrderStatusHistory.objects.filter(order=order).count(),
            "receipts": NotificationOutbox.objects.filter(order=order, event_key="payment.succeeded").count(),
            "sms": SmsLog.objects.filter(event_key="payment_success").count(),
            "redemption": getattr(CouponRedemption.objects.filter(order=order).first(), "status", None),
        }


class ConfirmationEffectsTests(CodBase):
    def test_confirmation_preserves_order_status_for_every_stage(self):
        for stage in (None, "processing", "shipped", "delivered"):
            order = self.cod_order(status=stage)
            before = self.state(order)
            tx = self.confirm(order)
            after = self.state(order)
            self.assertEqual(after["status"], before["status"], stage)  # pending/processing/shipped/delivered حفظ می‌شود
            self.assertEqual(after["payment_status"], Order.PaymentStatus.PAID, stage)
            self.assertEqual(after["history"], before["history"], stage)  # گذارِ وضعیت‌ی ثبت نشد
            self.assertEqual((tx.method, tx.confirmed_by_id, tx.ref_id, tx.amount, tx.status), (M.COD_CASH, self.actor.pk, "RC-1", order.grand_total, "ok"), stage)
            self.assertIsNotNone(tx.confirmed_at)
            self.assertEqual((after["tx"], after["receipts"], after["sms"]), (1, 1, 0), stage)  # یک رسیدِ ایمیلی، بدونِ پیامک
            self.assertEqual(after["redemption"], R.REDEEMED, stage)

    def test_receipt_is_email_only(self):
        order = self.cod_order()
        self.confirm(order)
        channels = list(NotificationOutbox.objects.filter(order=order, event_key="payment.succeeded").values_list("channel", flat=True))
        self.assertEqual(channels, ["email"])

    def test_coupon_stays_reserved_until_confirmation_then_redeemed(self):
        order = self.cod_order(status="delivered")
        self.assertEqual(self.state(order)["redemption"], R.RESERVED)  # حتی بعد از تحویل
        self.assertEqual(self.signature(order)["coupon_used"], 1)
        self.confirm(order)
        self.assertEqual(self.state(order)["redemption"], R.REDEEMED)
        self.assertEqual(self.signature(order)["coupon_used"], 1)

    def test_audit_event_and_no_backfill_of_other_orders(self):
        other = self.cod_order(status="delivered")  # سفارشِ قدیمیِ تحویل‌شده بدونِ تأیید
        order = self.cod_order()
        self.confirm(order)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="order.cod_payment_confirmed", object_id=str(order.pk)).count(), 1)
        other.refresh_from_db()
        self.assertEqual(other.payment_status, Order.PaymentStatus.PENDING)

    def test_payment_counts_for_paid_statistics_only_after_confirmation(self):
        order = self.cod_order(status="delivered")
        self.assertNotIn(order.pk, set(valid_orders(self.store).values_list("pk", flat=True)))
        self.confirm(order)
        self.assertIn(order.pk, set(valid_orders(self.store).values_list("pk", flat=True)))

    def test_consistency_clean_and_cod_without_coupon(self):
        self.confirm(self.cod_order())
        plain = self.cod_order(coupon=False)
        self.confirm(plain, idempotency_key="tok-2")
        self.assertEqual(self.state(plain)["redemption"], None)
        self.assertEqual(ConsistencyCommand.collect(self.store), [])


class DuplicateAndValidationTests(CodBase):
    def test_second_confirmation_is_rejected_without_new_effects(self):
        order = self.cod_order(status="delivered")
        self.confirm(order)
        before = self.state(order)
        for key in ("tok-1", "tok-other"):
            with self.assertRaises(cod.AlreadyConfirmed):
                self.confirm(order, idempotency_key=key)
        self.assertEqual(self.state(order), before)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="order.cod_payment_confirmed").count(), 1)

    def test_invalid_requests_change_nothing(self):
        order = self.cod_order()
        before = self.state(order)
        bad = [
            dict(amount=order.grand_total - 1), dict(amount=order.grand_total + 1), dict(amount="abc"), dict(amount=""),
            dict(method="cash"), dict(method=M.GATEWAY), dict(reference="x" * 61),
        ]
        for kw in bad:
            with self.assertRaises(cod.CodConfirmationError, msg=str(kw)):
                self.confirm(order, **kw)
        self.assertEqual(self.state(order), before)

    def test_canceled_non_cod_and_other_store_orders_are_rejected(self):
        canceled = self.cod_order()
        change_order_status(canceled, Order.Status.CANCELED, store=self.store)
        with self.assertRaises(cod.CodConfirmationError):
            self.confirm(canceled)
        online = self.new_order()  # درگاهِ آنلاین/غیر COD
        with self.assertRaises(cod.CodConfirmationError):
            self.confirm(online)
        from apps.stores.models import Store

        other = Store.objects.create(name="o", slug="cod-other", status=Store.Status.ACTIVE)
        with self.assertRaises(Order.DoesNotExist):
            cod.confirm_collection(self.cod_order().pk, store=other, actor=self.actor, amount=1, method=M.COD_CASH)
        self.assertEqual(self.state(canceled)["tx"], 0)

    def test_amount_formats_with_separators_are_accepted(self):
        order = self.cod_order()
        self.confirm(order, amount=f"{int(order.grand_total):,}")
        self.assertEqual(self.state(order)["payment_status"], Order.PaymentStatus.PAID)

    def test_delivery_and_status_changes_never_pay_cod(self):
        order = self.cod_order(status="delivered")
        self.assertEqual(self.state(order)["payment_status"], Order.PaymentStatus.PENDING)
        self.assertEqual(self.state(order)["tx"], 0)
        self.assertTrue(cod.can_confirm(order))
        self.confirm(order)
        order.refresh_from_db()
        self.assertFalse(cod.can_confirm(order))


class RefundCorrectionTests(CodBase):
    def test_correction_uses_refund_workflow_and_keeps_audit_trail(self):
        order = self.cod_order(status="delivered", qty=2)
        tx = self.confirm(order)
        order.refresh_from_db()
        item = order.items.first()
        first = execute_order_refund(order, store=self.store, actor=self.actor, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        second = execute_order_refund(order, store=self.store, actor=self.actor, line_requests=[{"order_item_id": item.pk, "quantity": 1}])
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.assertEqual(self.state(order)["redemption"], R.REFUNDED)
        self.assertEqual(first.approved_amount + second.approved_amount, order.grand_total - order.shipping_cost - order.shipping_tax)
        tx.refresh_from_db()
        self.assertEqual((tx.status, tx.method, tx.confirmed_by_id), ("ok", M.COD_CASH, self.actor.pk))  # اثرِ مالیِ اصلی حذف/بازنویسی نمی‌شود
        self.assertEqual(Refund.objects.filter(order=order).count(), 2)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="order.cod_payment_confirmed").count(), 1)


class CodDashboardTests(CodBase):
    def setUp(self):
        super().setUp()
        from apps.dashboard.tests.test_coupon_views import HOST

        self.host = HOST
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.order = self.cod_order(status="delivered")
        self.counter = 0

    def client_for(self, role):
        client = Client(HTTP_HOST=self.host)
        if role == StoreMembership.Role.OWNER:
            client.force_login(self.owner)
            return client
        self.counter += 1
        user = get_user_model().objects.create_user(username=f"0912774{self.counter:04d}", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=role, status="active", accepted_at=timezone.now())
        client.force_login(user)
        return client

    def post(self, client, order=None, **data):
        order = order or self.order
        payload = {"amount": str(int(order.grand_total)), "method": M.COD_CASH, "reference": "R-9", "token": "t-1"}
        payload.update(data)
        return client.post(reverse("dashboard:order-cod-payment", args=[order.code]), payload)

    def test_permission_matrix(self):
        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            Role = StoreMembership.Role
            for role in (Role.ANALYST, Role.CATALOG_MANAGER, Role.CONTENT_EDITOR):
                self.assertEqual(self.post(self.client_for(role)).status_code, 403, role)
            self.assertEqual(self.state(self.order)["payment_status"], "pending")
            for role in (Role.ORDER_MANAGER, Role.ADMINISTRATOR, Role.OWNER):
                order = self.cod_order(status="delivered")
                self.assertEqual(self.post(self.client_for(role), order=order).status_code, 302, role)
                self.assertEqual(self.state(order)["payment_status"], "paid", role)

    def test_form_visibility_and_confirmation_flow(self):
        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            url = reverse("dashboard:order-detail", args=[self.order.code])
            self.assertContains(owner.get(url), "تأیید دریافتِ وجه")
            analyst = self.client_for(StoreMembership.Role.ANALYST)
            self.assertNotContains(analyst.get(url), "تأیید دریافتِ وجه")
            response = self.post(owner, follow=False) if False else self.post(owner)
            self.assertEqual(response.status_code, 302)
            page = owner.get(url)
            self.assertNotContains(page, 'name="amount"')  # فرمِ تأیید پنهان شد
            self.assertContains(page, "تأییدشده توسط")
            self.assertContains(page, "R-9")
            # تأییدِ تکراری: اطلاع، بدونِ اثر
            before = self.state(self.order)
            self.post(owner, token="t-2")
            self.assertEqual(self.state(self.order), before)

    def test_wrong_amount_and_online_orders_rejected_in_view(self):
        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            self.post(owner, amount="1")
            self.assertEqual(self.state(self.order)["payment_status"], "pending")
            online = self.new_order()
            self.post(owner, order=online)
            online.refresh_from_db()
            self.assertEqual(online.payment_status, "pending")
            self.assertNotContains(owner.get(reverse("dashboard:order-detail", args=[online.code])), "تأیید دریافتِ وجه")

    def test_other_store_order_is_404_and_get_not_allowed(self):
        from apps.stores.models import Store

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            Order.objects.filter(pk=self.order.pk).update(store=Store.objects.create(name="o", slug="cod-o2", status=Store.Status.ACTIVE))
            self.assertEqual(self.post(owner).status_code, 404)
            self.assertEqual(owner.get(reverse("dashboard:order-cod-payment", args=[self.order.code])).status_code, 405)
