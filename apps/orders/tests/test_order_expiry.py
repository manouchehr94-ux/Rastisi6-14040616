"""M2: انقضایِ سفارش‌هایِ آنلاینِ پرداخت‌نشده — پیش‌فرض غیرفعال، فقط آنلاین، هرگز COD، از مسیرِ لغوِ موجود،
ایمیلِ یک‌باره بدونِ پیامک، idempotent، و ایمن در برابرِ callbackِ در راه/موفق."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from apps.cart.management.commands.verify_coupon_consistency import Command as ConsistencyCommand
from apps.catalog.models import Product
from apps.core.models import AuditLogEntry, ShopSettings
from apps.notifications.models import NotificationOutbox
from apps.orders.models import (
    CouponRedemption, Order, PaymentAttempt, PaymentGateway, PaymentGatewayConfig, PaymentReconciliation,
)
from apps.orders.services.gateway_payment_service import OrderNotPayableError, initiate_payment
from apps.orders.services.order_expiry_service import expire_unpaid_orders
from apps.orders.tests.test_payment_safety import SafetyBase, ok_response
from apps.sms.models import SmsLog

R = CouponRedemption.Status
HOUR = timedelta(hours=1)


class ExpiryBase(SafetyBase):
    def setUp(self):
        super().setUp()
        self.customer.email = "buyer@example.com"
        self.customer.save(update_fields=["email"])
        self.online = PaymentGatewayConfig.objects.get_or_create(store=self.store, gateway_code="zibal", defaults={"is_active": True})[0]
        self.online.set_credentials({"merchant": "m"})
        self.online.save()
        self.cod_config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="cod", is_active=True)
        self.zibal_gw = PaymentGateway.objects.create(store=self.store, name="زیبال", slug="zibal")
        self.cod_gw = PaymentGateway.objects.create(store=self.store, name="در محل", slug="cod")

    def enable(self, ttl=60, grace=30, sms=False):
        shop = ShopSettings.load(store=self.store)
        shop.unpaid_online_order_ttl_minutes, shop.unpaid_online_order_grace_minutes, shop.unpaid_expiry_notify_sms = ttl, grace, sms
        shop.save()

    def old_order(self, gateway=None, age=HOUR * 3, coupon=True):
        order = self.new_order(coupon=coupon)
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - age, payment_gateway=gateway or self.zibal_gw,
        )
        order.refresh_from_db()
        return order

    def run_job(self, **kw):
        with self.captureOnCommitCallbacks(execute=True):
            return expire_unpaid_orders(**kw)

    def status(self, order):
        order.refresh_from_db()
        return order.status


class DisabledByDefaultTests(ExpiryBase):
    def test_default_ttl_is_zero_and_job_is_noop(self):
        self.assertEqual(ShopSettings.load(store=self.store).unpaid_online_order_ttl_minutes, 0)
        order = self.old_order(age=timedelta(days=30))
        stats = self.run_job()
        self.assertEqual((stats["candidates"], stats["expired"]), (0, 0))
        self.assertEqual(self.status(order), Order.Status.PENDING)


class ExpiryEffectsTests(ExpiryBase):
    def test_expiry_cancels_through_lifecycle_and_releases_everything_once(self):
        self.enable()
        order = self.old_order()
        attempt = self.attempt(order)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - HOUR)
        stock_reserved = Product.objects.get(pk=self.p.pk).stock
        stats = self.run_job()
        self.assertEqual((stats["candidates"], stats["expired"]), (1, 1))
        sig = self.signature(order)
        self.assertEqual((sig["status"], sig["payment_status"]), ("canceled", "pending"))
        self.assertEqual((sig["redemption"], sig["coupon_used"]), (R.RELEASED, 0))
        self.assertEqual(sig["stock"], stock_reserved + 1)
        self.assertEqual(sig["history"][-1], ("pending", "canceled"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.EXPIRED)
        # دقیقاً یک ایمیلِ لغو، بدونِ پیامک
        mails = NotificationOutbox.objects.filter(order=order, event_key="order.canceled")
        self.assertEqual([m.channel for m in mails], ["email"])
        self.assertEqual(SmsLog.objects.filter(event_key="order_canceled").count(), 0)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="order.payment_expired").count(), 1)
        # idempotent
        again = self.run_job()
        self.assertEqual((again["candidates"], again["expired"]), (0, 0))
        self.assertEqual(self.signature(order)["stock"], stock_reserved + 1)
        self.assertEqual(NotificationOutbox.objects.filter(order=order, event_key="order.canceled").count(), 1)
        self.assertEqual(ConsistencyCommand.collect(self.store), [])

    def test_sms_only_when_explicitly_enabled(self):
        self.enable(sms=True)
        order = self.old_order()
        self.run_job()
        self.assertEqual(self.status(order), Order.Status.CANCELED)
        self.assertEqual(SmsLog.objects.filter(event_key="order_canceled").count(), 1)

    def test_coupon_capacity_is_reusable_after_expiry(self):
        self.enable()
        order = self.old_order()
        self.run_job()
        self.assertEqual(self.status(order), Order.Status.CANCELED)
        fresh = self.new_order()
        self.assertEqual(fresh.coupon_discount > 0, True)
        self.assertEqual(self.signature(fresh)["coupon_used"], 1)

    def test_expired_order_cannot_be_paid_and_late_payment_is_reconciled(self):
        self.enable()
        order = self.old_order()
        attempt = self.attempt(order)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - HOUR)
        self.run_job()
        with self.assertRaises(OrderNotPayableError):
            initiate_payment(order=order, gateway_config=self.online, callback_url="https://x/cb", store=self.store)
        before = self.snapshot(order)
        result, _ = self.callback(attempt, ok_response(order))
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        record = PaymentReconciliation.objects.get(attempt=attempt)
        self.assertEqual(record.kind, PaymentReconciliation.Kind.ORDER_CANCELED)
        after = self.snapshot(order)
        for key in ("status", "payment_status", "redemption", "coupon_used", "stock", "tx_ok"):
            self.assertEqual(after[key], before[key], key)


class EligibilityTests(ExpiryBase):
    def setUp(self):
        super().setUp()
        self.enable()

    def assert_untouched(self, order, reason=None):
        stats = self.run_job()
        self.assertEqual(self.status(order), Order.Status.PENDING)
        if reason:
            self.assertEqual(stats["skipped"].get(reason), 1, stats)

    def test_recent_order_not_expired(self):
        self.assert_untouched(self.old_order(age=timedelta(minutes=10)))

    def test_cod_never_expires_even_when_ancient(self):
        order = self.old_order(gateway=self.cod_gw, age=timedelta(days=60))
        self.assert_untouched(order, "not_online")
        # حتی با یک تلاشِ COD (آفلاین)
        cod_attempt = PaymentAttempt.objects.create(
            store=self.store, order=order, gateway_config=self.cod_config, amount=order.grand_total,
            status=PaymentAttempt.Status.SUCCEEDED, gateway_track_id=f"cod-{order.code}",
        )
        self.assert_untouched(order, "not_online")
        self.assertTrue(cod_attempt.pk)

    def test_unknown_gateway_without_online_evidence_is_never_expired(self):
        other = PaymentGateway.objects.create(store=self.store, name="؟", slug="mystery")
        self.assert_untouched(self.old_order(gateway=other), "not_online")

    def test_unknown_gateway_with_online_attempt_is_eligible(self):
        other = PaymentGateway.objects.create(store=self.store, name="؟", slug="legacy-name")
        order = self.old_order(gateway=other)
        attempt = self.attempt(order, status=PaymentAttempt.Status.FAILED)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - HOUR)
        self.run_job()
        self.assertEqual(self.status(order), Order.Status.CANCELED)

    def test_paid_or_progressed_orders_are_not_touched(self):
        paid = self.old_order()
        Order.objects.filter(pk=paid.pk).update(payment_status=Order.PaymentStatus.PAID)
        processing = self.old_order()
        Order.objects.filter(pk=processing.pk).update(status=Order.Status.PROCESSING)
        self.run_job()
        self.assertEqual(self.status(paid), Order.Status.PENDING)
        self.assertEqual(self.status(processing), Order.Status.PROCESSING)

    def test_in_flight_and_confirmed_payments_are_skipped(self):
        in_flight = self.old_order()
        self.attempt(in_flight, status=PaymentAttempt.Status.PENDING)  # updated_at = اکنون
        self.assert_untouched(in_flight, "payment_in_flight")
        confirmed = self.old_order()
        self.attempt(confirmed, status=PaymentAttempt.Status.SUCCEEDED)
        stats = self.run_job()
        self.assertEqual(self.status(confirmed), Order.Status.PENDING)
        self.assertEqual(stats["skipped"].get("confirmed_payment"), 1)

    def test_grace_boundary(self):
        order = self.old_order()
        attempt = self.attempt(order, status=PaymentAttempt.Status.REDIRECT_READY)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(minutes=29))
        self.assert_untouched(order, "payment_in_flight")
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(minutes=31))
        self.run_job()
        self.assertEqual(self.status(order), Order.Status.CANCELED)

    def test_dry_run_changes_nothing_and_store_scoping(self):
        from apps.stores.models import Store

        order = self.old_order()
        stats = self.run_job(dry_run=True)
        self.assertEqual((stats["expired"], self.status(order)), (1, Order.Status.PENDING))
        other = Store.objects.create(name="o", slug="expiry-other", status=Store.Status.ACTIVE)
        self.run_job(store=other)
        self.assertEqual(self.status(order), Order.Status.PENDING)
        self.assertEqual(NotificationOutbox.objects.filter(order=order, event_key="order.canceled").count(), 0)

    def test_management_command(self):
        order = self.old_order()
        out = StringIO()
        call_command("expire_unpaid_orders", "--dry-run", stdout=out)
        self.assertIn("would_expire=1", out.getvalue())
        out = StringIO()
        call_command("expire_unpaid_orders", stdout=out)
        self.assertIn("expired=1", out.getvalue())
        self.assertEqual(self.status(order), Order.Status.CANCELED)


class ExpirySettingsViewTests(ExpiryBase):
    def setUp(self):
        super().setUp()
        from apps.dashboard.tests.test_coupon_views import HOST
        from django.test import Client

        self.host = HOST
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.client = Client(HTTP_HOST=HOST)
        self.client.force_login(self.owner)

    def test_form_saves_validates_and_audits(self):
        from django.urls import reverse

        with self.settings(ALLOWED_HOSTS=[self.host, "testserver"]):
            url = reverse("dashboard:settings-order-expiry")
            self.client.post(url, {"unpaid_online_order_ttl_minutes": "5", "unpaid_online_order_grace_minutes": "30"})
            self.assertEqual(ShopSettings.load(store=self.store).unpaid_online_order_ttl_minutes, 0)  # <۱۵ رد شد
            self.client.post(url, {"unpaid_online_order_ttl_minutes": "60", "unpaid_online_order_grace_minutes": "30"})
            shop = ShopSettings.load(store=self.store)
            self.assertEqual((shop.unpaid_online_order_ttl_minutes, shop.unpaid_online_order_grace_minutes, shop.unpaid_expiry_notify_sms), (60, 30, False))
            self.assertEqual(AuditLogEntry.objects.filter(action_code="settings.order_expiry_updated").count(), 1)
            page = self.client.get(reverse("dashboard:settings") + "?section=finance")
            self.assertContains(page, "انقضای سفارش‌های پرداخت‌نشده")
            from apps.stores.models import StoreMembership

            analyst = self.login_other(StoreMembership.Role.ANALYST)
            self.assertEqual(analyst.post(url, {"unpaid_online_order_ttl_minutes": "0", "unpaid_online_order_grace_minutes": "30"}).status_code, 403)

    def login_other(self, role):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from apps.stores.models import StoreMembership

        user = get_user_model().objects.create_user(username="09127722222", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=user, role=role, status="active", accepted_at=timezone.now())
        client = Client(HTTP_HOST=self.host)
        client.force_login(user)
        return client


class JobReliabilityTests(ExpiryBase):
    def test_one_failing_order_does_not_stop_the_batch_and_is_counted(self):
        from unittest.mock import patch

        from apps.orders.services import order_expiry_service as svc

        self.enable()
        bad, good = self.old_order(), self.old_order()
        real = svc._expire_one

        def flaky(order_id, *a, **k):
            if order_id == bad.pk:
                raise RuntimeError("boom")
            return real(order_id, *a, **k)

        with patch.object(svc, "_expire_one", side_effect=flaky):
            stats = self.run_job()
        self.assertEqual((stats["expired"], stats["errors"]), (1, 1))
        self.assertEqual((self.status(good), self.status(bad)), (Order.Status.CANCELED, Order.Status.PENDING))
        self.assertEqual(self.run_job()["expired"], 1)  # بازاجرا امن است و سفارشِ خراب را دوباره امتحان می‌کند

    def test_health_check_flags_overdue_order_when_expiry_enabled(self):
        import json

        self.enable(ttl=60, grace=30)
        self.old_order(age=timedelta(hours=5))
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("check_background_jobs", "--json", stdout=out)
        self.assertEqual(ctx.exception.code, 1)
        detail = next(c for c in json.loads(out.getvalue())["checks"] if c["check"].startswith("order_expiry:"))
        self.assertEqual(detail["level"], "WARNING")
