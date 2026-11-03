"""B3 (BLOCKER 3): انتقالِ دستیِ کارت به کارت تا تأییدِ فروشنده «در انتظار» می‌ماند.

* پس از ``initiate_payment`` تلاشِ کارت به کارت ``PENDING`` است و سفارش پرداخت‌نشده (بدونِ ``verified_at``)؛
* تأییدِ فروشنده سفارش را دقیقاً یک‌بار پرداخت‌شده می‌کند و یک تراکنش می‌سازد؛
* مسیرِ رد سفارش را در ``pending`` و بدونِ جابه‌جاییِ پول نگه می‌دارد؛
* تأییدِ تکراری idempotent است (نه تراکنشِ دوم، نه بازخریدِ دوباره‌ی کوپن)؛
* مبلغِ نادرست رد می‌شود؛
* عدم‌رگرسیونِ COD: پس از ``initiate_payment`` تلاشِ COD ``SUCCEEDED`` و سفارش ``PENDING`` است."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

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


class CardToCardDashboardTests(CardToCardBase):
    """B3 reachability: تأیید/ردِ کارت به کارت از طریقِ view/URL/داشبورد در دسترس است.

    عیناً الگویِ ``CodDashboardTests`` را بازتاب می‌دهد: ماتریسِ مجوز، دیده‌شدنِ فرم،
    تأییدِ PENDING→PAID، ردِ PENDING (بدونِ پول)، idempotency، اسکوپِ Store، و GET رد."""

    def setUp(self):
        super().setUp()
        from apps.dashboard.tests.test_coupon_views import HOST

        self.host = HOST
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.order = self.c2c_order()
        self.initiate(self.order)  # تلاشِ PENDING برای مسیرِ رد
        self.counter = 0

    def client_for(self, role):
        from django.test import Client
        from apps.stores.models import StoreMembership

        client = Client(HTTP_HOST=self.host)
        if role == StoreMembership.Role.OWNER:
            client.force_login(self.owner)
            return client
        self.counter += 1
        user = get_user_model().objects.create_user(
            username=f"0912779{self.counter:04d}", password="pass12345", is_staff=True
        )
        StoreMembership.objects.create(
            store=self.store, user=user, role=role, status="active",
            accepted_at=timezone.now(),
        )
        client.force_login(user)
        return client

    def confirm_post(self, client, order=None, **data):
        from django.urls import reverse

        order = order or self.order
        payload = {"amount": str(int(order.grand_total)), "reference": "R-C2C-9", "token": "t-c2c-1"}
        payload.update(data)
        return client.post(reverse("dashboard:order-card-to-card-payment", args=[order.code]), payload)

    def reject_post(self, client, order=None, **data):
        from django.urls import reverse

        order = order or self.order
        payload = {"reason": "رسید نامعتبر", "token": "t-c2c-2"}
        payload.update(data)
        return client.post(reverse("dashboard:order-card-to-card-reject", args=[order.code]), payload)

    def pay_status(self, order):
        order.refresh_from_db()
        return order.payment_status

    def test_permission_matrix(self):
        from apps.stores.models import StoreMembership

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            Role = StoreMembership.Role
            for role in (Role.ANALYST, Role.CATALOG_MANAGER, Role.CONTENT_EDITOR):
                order = self.c2c_order()
                self.initiate(order)
                self.assertEqual(self.confirm_post(self.client_for(role), order=order).status_code, 403, role)
                self.assertEqual(self.reject_post(self.client_for(role), order=order).status_code, 403, role)
                self.assertEqual(self.pay_status(order), Order.PaymentStatus.PENDING, role)
            for role in (Role.ORDER_MANAGER, Role.ADMINISTRATOR, Role.OWNER):
                order = self.c2c_order()
                self.initiate(order)
                with self.captureOnCommitCallbacks(execute=True):
                    resp = self.confirm_post(self.client_for(role), order=order)
                self.assertEqual(resp.status_code, 302, role)
                self.assertEqual(self.pay_status(order), Order.PaymentStatus.PAID, role)
                self.assertEqual(self.tx_ok(order), 1, role)

    def test_confirm_flow_and_form_visibility(self):
        from django.urls import reverse
        from apps.stores.models import StoreMembership

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            url = reverse("dashboard:order-detail", args=[self.order.code])
            self.assertContains(owner.get(url), "تأیید انتقالِ کارت به کارت")
            analyst = self.client_for(StoreMembership.Role.ANALYST)
            self.assertNotContains(analyst.get(url), "تأیید انتقالِ کارت به کارت")
            with self.captureOnCommitCallbacks(execute=True):
                response = self.confirm_post(owner)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.pay_status(self.order), Order.PaymentStatus.PAID)
            self.assertEqual(self.tx_ok(self.order), 1)
            page = owner.get(url)
            # فرمِ تأیید پنهان شد (سفارش دیگر در‌انتظار نیست). توجه: کارت به کارت از
            # متدِ GATEWAY استفاده می‌کند تا نیازی به مهاجرت نباشد، پس تراکنشِ آن در
            # بلوکِ رسیدهایِ آفلاین (method != 'gateway') نمایش داده نمی‌شود؛ خودِ
            # پرداخت‌شدنِ سفارش در بالا بررسی شده است.
            self.assertNotContains(page, 'name="amount"')
            # تأییدِ تکراری: اطلاع، بدونِ اثر
            before_tx = self.tx_ok(self.order)
            with self.captureOnCommitCallbacks(execute=True):
                self.confirm_post(owner, token="t-c2c-9")
            self.assertEqual(self.tx_ok(self.order), before_tx)

    def test_reject_flow_leaves_order_pending_without_money(self):
        from apps.stores.models import StoreMembership

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            resp = self.reject_post(owner)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(self.pay_status(self.order), Order.PaymentStatus.PENDING)
            self.assertEqual(self.tx_ok(self.order), 0)
            self.assertEqual(
                PaymentAttempt.objects.filter(
                    order=self.order, status=PaymentAttempt.Status.CANCELED
                ).count(),
                1,
            )

    def test_wrong_amount_and_online_orders_rejected_in_view(self):
        from django.urls import reverse
        from apps.stores.models import StoreMembership

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            self.confirm_post(owner, amount="1")
            self.assertEqual(self.pay_status(self.order), Order.PaymentStatus.PENDING)
            online = self.new_order()
            self.confirm_post(owner, order=online)
            online.refresh_from_db()
            self.assertEqual(online.payment_status, Order.PaymentStatus.PENDING)
            self.assertNotContains(
                owner.get(reverse("dashboard:order-detail", args=[online.code])),
                "تأیید انتقالِ کارت به کارت",
            )

    def test_other_store_order_is_404_and_get_not_allowed(self):
        from django.urls import reverse
        from apps.stores.models import Store, StoreMembership

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            owner = self.client_for(StoreMembership.Role.OWNER)
            Order.objects.filter(pk=self.order.pk).update(
                store=Store.objects.create(name="o", slug="c2c-o2", status=Store.Status.ACTIVE)
            )
            self.assertEqual(self.confirm_post(owner).status_code, 404)
            self.assertEqual(self.reject_post(owner).status_code, 404)
            self.assertEqual(
                owner.get(reverse("dashboard:order-card-to-card-payment", args=[self.order.code])).status_code,
                405,
            )


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
