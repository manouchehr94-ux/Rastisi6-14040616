"""SMS credit-package purchase through the platform's own gateway (mocked; synthetic ids): verified payment → credits
added exactly once with a ledger trail; cancel / refund / duplicate / mismatch / isolation behaviour."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.services import sms_purchase_payment_service as svc
from apps.billing.tests.platform_payment_support import (
    PLATFORM_MERCHANT, STORE_MERCHANT, patch_zibal, ready_platform_zibal,
)
from apps.core.models import AuditLogEntry
from apps.orders.models import PaymentGatewayConfig
from apps.sms.models import (
    SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase,
)
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()
S = SmsPackagePaymentAttempt.Status
P = SmsPackagePurchase.Status
PAY_URL = "/admin-portal/settings/?section=sms"


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SmsPaymentBase(TestCase):
    PRICE = 150_000
    CREDITS = 500

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.staff = User.objects.create_user(username="09121193777", password="pass12345", is_staff=True)
        self.store = Store.objects.get(slug="akhlaghi")
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        self.package = SmsPackage.objects.create(name="بسته ۵۰۰", credit_amount=self.CREDITS, price=self.PRICE)
        self.fake = patch_zibal(self)
        self.client.login(username="09121193777", password="pass12345")

    def credits(self):
        return SmsBalance.objects.get(store=self.store).credits

    def buy(self, **extra):
        return self.client.post(reverse("dashboard:settings-sms-package-purchase"), {"package_id": self.package.pk, **extra})

    def purchase_and_attempt(self):
        ready_platform_zibal(self)
        response = self.buy()
        purchase = SmsPackagePurchase.objects.get(package=self.package)
        attempt = SmsPackagePaymentAttempt.objects.get(purchase=purchase)
        return response, purchase, attempt

    def callback(self, attempt, query="success=1&status=2&trackId=777"):
        cache.clear()
        return self.client.get(f"/billing/return/{attempt.public_token}/?{query}")

    def paid(self, attempt, rial=None):
        self.fake.paid(amount_rial=rial if rial is not None else self.PRICE * 10, order_id=attempt.public_token)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SmsCheckoutTests(SmsPaymentBase):
    def test_purchase_redirects_to_the_platform_gateway_and_adds_no_credit_yet(self):
        response, purchase, attempt = self.purchase_and_attempt()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://gateway.zibal.ir/start/777")
        self.assertEqual((purchase.status, attempt.status, attempt.provider), (P.PENDING, S.PENDING, "zibal"))
        self.assertEqual((attempt.amount, attempt.currency, attempt.store_id), (self.PRICE, "IRT", self.store.pk))
        self.assertTrue(attempt.public_token.startswith("sms_"))
        sent = self.fake.calls_to("request")[0]
        self.assertEqual((sent["merchant"], sent["amount"]), (PLATFORM_MERCHANT, self.PRICE * 10))
        self.assertIn("پیامک", sent["description"])
        self.assertEqual(self.credits(), 100)
        self.assertFalse(SmsCreditLedger.objects.exists())

    def test_without_a_ready_platform_gateway_the_old_manual_flow_is_unchanged(self):
        response = self.buy()
        self.assertRedirects(response, PAY_URL, fetch_redirect_response=False)
        purchase = SmsPackagePurchase.objects.get(package=self.package)
        self.assertEqual(purchase.status, P.PENDING)
        self.assertFalse(SmsPackagePaymentAttempt.objects.exists())
        self.assertEqual(self.credits(), 100)

    def test_the_price_is_the_server_side_snapshot_not_a_browser_field(self):
        ready_platform_zibal(self)
        self.buy(price="1", amount="1", credit_amount="999999")
        attempt = SmsPackagePaymentAttempt.objects.get()
        self.assertEqual(attempt.amount, self.PRICE)
        self.assertEqual(SmsPackagePurchase.objects.get().credit_amount, self.CREDITS)

    def test_buying_the_same_package_again_reuses_the_pending_purchase(self):
        ready_platform_zibal(self)
        self.buy()
        self.fake.track_id = 888
        self.buy()
        self.assertEqual(SmsPackagePurchase.objects.count(), 1)
        self.assertEqual(SmsPackagePaymentAttempt.objects.count(), 2)

    def test_an_existing_pending_purchase_created_before_the_gateway_can_be_paid_online(self):
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        ready_platform_zibal(self)
        response = self.client.post(reverse("dashboard:settings-sms-purchase-pay", args=[purchase.pk]))
        self.assertEqual(response["Location"], "https://gateway.zibal.ir/start/777")
        self.assertEqual(SmsPackagePaymentAttempt.objects.get().purchase_id, purchase.pk)

    def test_gateway_down_gives_a_failed_attempt_and_a_message_not_a_crash(self):
        ready_platform_zibal(self)
        import requests
        from unittest.mock import patch

        with patch("apps.billing.providers.zibal.requests.post", side_effect=requests.Timeout()):
            response = self.buy()
        self.assertRedirects(response, PAY_URL, fetch_redirect_response=False)
        attempt = SmsPackagePaymentAttempt.objects.get()
        self.assertEqual((attempt.status, attempt.failure_code), (S.FAILED, "timeout"))
        self.assertEqual(self.credits(), 100)
        self.assertEqual(SmsPackagePurchase.objects.get().status, P.PENDING)       # can retry later

    def test_another_stores_purchase_cannot_be_paid_by_this_store(self):
        other = Store.objects.create(name="دیگر", slug="sms-other", admin_subdomain="sms-other")
        foreign = balance_service.request_purchase(store=other, package=self.package)
        ready_platform_zibal(self)
        response = self.client.post(reverse("dashboard:settings-sms-purchase-pay", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SmsPackagePaymentAttempt.objects.exists())


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SmsFulfilmentTests(SmsPaymentBase):
    def test_verified_payment_adds_credits_once_with_a_full_ledger_trail(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        self.paid(attempt)
        response = self.callback(attempt)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"http://testserver{PAY_URL}&payment=ok")
        purchase.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual((purchase.status, attempt.status), (P.COMPLETED, S.SUCCEEDED))
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        entry = SmsCreditLedger.objects.get()
        self.assertEqual(
            (entry.kind, entry.delta, entry.balance_before, entry.balance_after, entry.purchase_id, entry.payment_attempt_id),
            (SmsCreditLedger.Kind.PURCHASE, self.CREDITS, 100, 100 + self.CREDITS, purchase.pk, attempt.pk),
        )
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.sms_payment_confirmed").count(), 1)

    def test_duplicate_callbacks_and_service_calls_never_add_credit_twice(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        self.paid(attempt)
        for _ in range(5):
            self.callback(attempt)
        for _ in range(3):
            svc.verify_and_fulfill(SmsPackagePaymentAttempt.objects.get(pk=attempt.pk))
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        self.assertEqual(SmsCreditLedger.objects.count(), 1)
        self.assertEqual(len(self.fake.calls_to("verify")), 1)

    def test_a_forged_success_redirect_without_a_gateway_verified_payment_adds_nothing(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        response = self.callback(attempt, "success=1&status=2&trackId=777")      # fake gateway: not paid
        self.assertTrue(response["Location"].endswith("payment=pending"))
        self.assertEqual(self.credits(), 100)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, P.PENDING)

    def test_a_declined_payment_is_marked_failed_and_can_be_retried(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        response = self.callback(attempt, "success=0&status=3&trackId=777")
        self.assertTrue(response["Location"].endswith("payment=failed"))
        self.assertEqual(SmsPackagePaymentAttempt.objects.get(pk=attempt.pk).status, S.FAILED)
        self.assertEqual(self.credits(), 100)
        self.fake.track_id = 999
        self.buy()
        self.assertEqual(SmsPackagePaymentAttempt.objects.filter(purchase=purchase).count(), 2)

    def test_amount_mismatch_adds_no_credit_and_is_flagged(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        self.paid(attempt, rial=10)
        response = self.callback(attempt)
        self.assertTrue(response["Location"].endswith("payment=action"))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.REQUIRES_ACTION, "amount_mismatch"))
        self.assertEqual(self.credits(), 100)
        self.assertFalse(SmsCreditLedger.objects.exists())

    def test_another_orders_payment_is_not_attributed_to_this_purchase(self):
        _r, _purchase, attempt = self.purchase_and_attempt()
        self.fake.paid(amount_rial=self.PRICE * 10, order_id="sms_other-attempt")
        self.callback(attempt)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.REQUIRES_ACTION, "order_mismatch"))
        self.assertEqual(self.credits(), 100)

    def test_payment_arriving_after_the_purchase_was_cancelled_creates_no_credit_but_is_reconcilable(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        balance_service.cancel_purchase(purchase=purchase)
        self.paid(attempt)
        self.callback(attempt)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.REQUIRES_ACTION, "purchase_canceled"))
        self.assertEqual(self.credits(), 100)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, P.CANCELED)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.sms_payment_needs_reconciliation").count(), 1)

    def test_manual_completion_followed_by_an_online_payment_never_double_credits(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        balance_service.complete_purchase(purchase=purchase, actor=self.staff)
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        self.paid(attempt)
        self.callback(attempt)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.REQUIRES_ACTION, "purchase_completed"))
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        self.assertEqual(SmsCreditLedger.objects.count(), 1)

    def test_manual_completion_is_still_available_and_now_leaves_a_ledger_row(self):
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        balance_service.complete_purchase(purchase=purchase, actor=self.staff)
        entry = SmsCreditLedger.objects.get()
        self.assertEqual((entry.delta, entry.payment_attempt_id, entry.actor_id), (self.CREDITS, None, self.staff.pk))
        with self.assertRaises(balance_service.PurchaseNotPendingError):
            balance_service.complete_purchase(purchase=purchase)
        self.assertEqual(self.credits(), 100 + self.CREDITS)

    def test_the_database_itself_refuses_a_second_credit_row_for_the_same_purchase(self):
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        balance_service.complete_purchase(purchase=purchase)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SmsCreditLedger.objects.create(
                store=self.store, purchase=purchase, kind=SmsCreditLedger.Kind.PURCHASE,
                delta=1, balance_before=0, balance_after=1,
            )

    def test_credits_added_do_not_lose_a_concurrent_deduction(self):
        """Regression: complete_purchase used a stale read-then-write; it must add to the LOCKED current balance."""
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        balance_service.deduct_credit(store=self.store)                         # 100 → 99 before completion
        balance_service.complete_purchase(purchase=purchase)
        self.assertEqual(self.credits(), 99 + self.CREDITS)
        entry = SmsCreditLedger.objects.get()
        self.assertEqual((entry.balance_before, entry.balance_after), (99, 99 + self.CREDITS))


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SmsRefundAndCancelTests(SmsPaymentBase):
    def completed(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        self.paid(attempt)
        self.callback(attempt)
        return SmsPackagePurchase.objects.get(pk=purchase.pk), SmsPackagePaymentAttempt.objects.get(pk=attempt.pk)

    def test_refund_reverses_exactly_the_purchased_credits_once_and_records_the_ledger(self):
        purchase, attempt = self.completed()
        refunded, result = svc.refund_purchase(purchase, actor=self.staff, reason="درخواست مشتری")
        self.assertEqual(refunded.status, P.REFUNDED)
        self.assertEqual(self.credits(), 100)
        kinds = list(SmsCreditLedger.objects.order_by("id").values_list("kind", "delta", "balance_after"))
        self.assertEqual(kinds, [("purchase", self.CREDITS, 100 + self.CREDITS), ("purchase_reversal", -self.CREDITS, 100)])
        self.assertFalse(result.succeeded)                                         # Zibal has no automatic refund API
        self.assertIn("manual", result.provider_refund_id)
        entry = AuditLogEntry.objects.get(action_code="billing.sms_refund_requested")
        self.assertIn("pending_manual", entry.after_summary)
        self.assertNotIn(PLATFORM_MERCHANT, entry.after_summary + str(entry.metadata))
        with self.assertRaises(svc.SmsRefundError):
            svc.refund_purchase(SmsPackagePurchase.objects.get(pk=purchase.pk), actor=self.staff, reason="تکرار")
        self.assertEqual(self.credits(), 100)
        self.assertEqual(SmsCreditLedger.objects.count(), 2)

    def test_refund_is_blocked_when_credits_were_already_consumed(self):
        purchase, _attempt = self.completed()
        SmsBalance.objects.filter(store=self.store).update(credits=self.CREDITS - 1)       # consumed some
        with self.assertRaises(svc.SmsRefundError):
            svc.refund_purchase(purchase, actor=self.staff, reason="تست")
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, P.COMPLETED)
        self.assertEqual(SmsCreditLedger.objects.count(), 1)
        self.assertEqual(self.credits(), self.CREDITS - 1)                          # nothing changed

    def test_refund_requires_a_reason_and_a_real_online_payment(self):
        purchase, _attempt = self.completed()
        with self.assertRaises(svc.SmsRefundError):
            svc.refund_purchase(purchase, actor=self.staff, reason="  ")
        manual = balance_service.request_purchase(store=self.store, package=self.package)
        balance_service.complete_purchase(purchase=manual)
        with self.assertRaises(svc.SmsRefundError):
            svc.refund_purchase(manual, actor=self.staff, reason="x")

    def test_only_pending_purchases_can_be_cancelled(self):
        purchase, _attempt = self.completed()
        with self.assertRaises(balance_service.PurchaseNotPendingError):
            balance_service.cancel_purchase(purchase=purchase)
        pending = balance_service.request_purchase(store=self.store, package=self.package)
        balance_service.cancel_purchase(purchase=pending)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=pending.pk).status, P.CANCELED)

    def test_refund_after_a_later_online_duplicate_does_not_touch_the_flagged_attempt(self):
        purchase, attempt = self.completed()
        svc.refund_purchase(purchase, actor=self.staff, reason="r")
        self.assertEqual(SmsPackagePaymentAttempt.objects.get(pk=attempt.pk).status, S.SUCCEEDED)   # history preserved


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class StoreSideIsolationTests(SmsPaymentBase):
    def test_the_stores_own_gateway_config_is_never_used_or_modified_by_sms_purchases(self):
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal", is_active=True)
        config.set_credentials({"merchant": STORE_MERCHANT})
        config.save()
        snapshot = PaymentGatewayConfig.objects.get(pk=config.pk).encrypted_credentials
        _r, purchase, attempt = self.purchase_and_attempt()
        self.paid(attempt)
        self.callback(attempt)
        merchants = {payload.get("merchant") for _path, payload in self.fake.calls}
        self.assertEqual(merchants, {PLATFORM_MERCHANT})
        self.assertEqual(PaymentGatewayConfig.objects.get(pk=config.pk).encrypted_credentials, snapshot)
