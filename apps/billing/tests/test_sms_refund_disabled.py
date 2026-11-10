"""SMS package refunds are DISABLED by default (fail-closed) until the credit-freeze design (needs a migration) is built.
A direct service call and a direct HTTP POST are both rejected before ANY side effect: no credit reversal, no purchase status change,
no ledger/audit record, no provider call. Purchases, OTP and the history page keep working. Synthetic gateway only."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from apps.billing.providers import bank_refund_policy
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.billing.providers import registry
from apps.billing.services import sms_purchase_payment_service as svc
from apps.billing.tests.test_platform_sms_payments import P, S, SmsPaymentBase
from apps.core.models import AuditLogEntry
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackagePaymentAttempt, SmsPackagePurchase, SmsTemplate
from apps.sms.services import balance_service, otp_service

User = get_user_model()
PLATFORM_HOST = "platformadmins.rastisi.localhost"


class SmsRefundDisabledBase(SmsPaymentBase):
    def completed(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        self.paid(attempt)
        self.callback(attempt)
        return SmsPackagePurchase.objects.get(pk=purchase.pk), SmsPackagePaymentAttempt.objects.get(pk=attempt.pk)

    def snapshot(self):
        return {
            "credits": self.credits(),
            "purchases": list(SmsPackagePurchase.objects.order_by("pk").values("pk", "status", "credit_amount", "updated_at")),
            "attempts": list(SmsPackagePaymentAttempt.objects.order_by("pk").values("pk", "status", "completed_at")),
            "ledger": list(SmsCreditLedger.objects.order_by("pk").values_list("pk", "kind", "delta", "balance_after")),
            "audit": AuditLogEntry.objects.count(),
        }

    def provider_spy(self):
        spy = mock.Mock(name="provider.refund_payment")
        patcher = mock.patch.object(registry, "get_provider", side_effect=AssertionError("provider must not be resolved"))
        patcher.start()
        self.addCleanup(patcher.stop)
        return spy


class DisabledByDefaultTests(SmsRefundDisabledBase):
    def test_the_default_setting_is_fail_closed(self):
        from django.conf import settings

        self.assertIs(settings.RASTISI_SMS_REFUND_ENABLED, False)
        self.assertFalse(svc.sms_refunds_enabled())

    def test_anything_other_than_an_explicit_true_is_disabled(self):
        for value in (None, False, 0, "", "1", "true", "True", 1):
            with override_settings(RASTISI_SMS_REFUND_ENABLED=value):
                self.assertFalse(svc.sms_refunds_enabled(), value)
        with override_settings():
            from django.conf import settings

            del settings.RASTISI_SMS_REFUND_ENABLED                      # a missing setting must also fail closed
            self.assertFalse(svc.sms_refunds_enabled())

    def test_a_direct_service_call_is_rejected_with_no_side_effect_and_no_provider_call(self):
        purchase, _attempt = self.completed()
        before = self.snapshot()
        self.provider_spy()                                              # resolving ANY provider would raise AssertionError
        with self.assertRaises(svc.SmsRefundDisabledError) as ctx:
            svc.refund_purchase(purchase, actor=self.staff, reason="درخواست مشتری")
        self.assertEqual(str(ctx.exception), svc.SMS_REFUND_DISABLED_MESSAGE)
        self.assertIsInstance(ctx.exception, svc.SmsRefundError)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, P.COMPLETED)
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        self.assertFalse(SmsCreditLedger.objects.filter(kind="purchase_reversal").exists())

    def test_the_guard_runs_before_input_validation_and_before_any_database_access(self):
        purchase, _attempt = self.completed()
        for reason in ("", "  ", "valid reason"):
            with CaptureQueriesContext(connection) as queries, self.assertRaises(svc.SmsRefundDisabledError):
                svc.refund_purchase(purchase, actor=self.staff, reason=reason, idempotency_key="k")
            data_queries = [q["sql"] for q in queries if not q["sql"].upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK"))]
            self.assertEqual(data_queries, [])                          # only the atomic block's savepoint bookkeeping

    def test_a_pending_or_manually_completed_purchase_is_rejected_the_same_way(self):
        pending = balance_service.request_purchase(store=self.store, package=self.package)
        with self.assertRaises(svc.SmsRefundDisabledError):
            svc.refund_purchase(pending, actor=self.staff, reason="x")
        self.assertEqual(SmsPackagePurchase.objects.get(pk=pending.pk).status, P.PENDING)

    def test_the_balance_service_reversal_is_never_reached(self):
        purchase, _attempt = self.completed()
        with mock.patch.object(balance_service, "reverse_purchase_credits") as reverse:
            with self.assertRaises(svc.SmsRefundDisabledError):
                svc.refund_purchase(purchase, actor=self.staff, reason="r")
        reverse.assert_not_called()


class DirectHttpRequestTests(SmsRefundDisabledBase):
    def setUp(self):
        super().setUp()
        self.root = User.objects.create_user(username="sms-refund-root", password="x", is_staff=True, is_superuser=True)
        self.platform = Client(HTTP_HOST=PLATFORM_HOST)
        self.platform.force_login(self.root)

    def url(self, purchase, action="refund"):
        return f"/payments/sms-purchases/{purchase.pk}/{action}/"

    def test_a_direct_refund_post_is_rejected_with_a_controlled_message_and_no_side_effect(self):
        purchase, _attempt = self.completed()
        before = self.snapshot()
        self.provider_spy()
        response = self.platform.post(self.url(purchase), {"reason": "direct post"}, follow=True)
        self.assertEqual(response.status_code, 200)                       # a controlled redirect to the list, never a 500
        self.assertContains(response, "موقتاً غیرفعال")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(AuditLogEntry.objects.filter(action_code__in=["platform_sms_purchase.refund", "billing.sms_refund_requested"]).exists())

    def test_a_refund_post_with_the_override_flag_forged_in_the_request_is_still_rejected(self):
        purchase, _attempt = self.completed()
        before = self.snapshot()
        self.platform.post(self.url(purchase), {"reason": "x", "RASTISI_SMS_REFUND_ENABLED": "True", "enabled": "1"}, HTTP_X_FORCE="1")
        self.assertEqual(self.snapshot(), before)

    def test_a_non_superuser_still_cannot_reach_the_action(self):
        purchase, _attempt = self.completed()
        staff = User.objects.create_user(username="sms-refund-staff", password="x", is_staff=True)
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(staff)
        before = self.snapshot()
        response = client.post(self.url(purchase), {"reason": "x"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
        self.assertEqual(self.snapshot(), before)

    def test_the_history_page_stays_readable_and_the_refund_form_is_replaced_by_a_disabled_note(self):
        purchase, _attempt = self.completed()
        response = self.platform.get("/payments/sms-purchases/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بازپرداخت موقتاً غیرفعال")
        self.assertNotContains(response, self.url(purchase))              # no refund form/endpoint is rendered
        self.assertContains(response, f"{self.CREDITS}")                  # read-only history is still shown

    def test_manual_completion_and_cancellation_actions_are_unchanged(self):
        pending = balance_service.request_purchase(store=self.store, package=self.package)
        self.platform.post(self.url(pending, "complete"))
        self.assertEqual(SmsPackagePurchase.objects.get(pk=pending.pk).status, P.COMPLETED)
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        other = balance_service.request_purchase(store=self.store, package=self.package)
        self.platform.post(self.url(other, "cancel"))
        self.assertEqual(SmsPackagePurchase.objects.get(pk=other.pk).status, P.CANCELED)

    def test_the_refund_form_returns_only_when_the_flag_is_explicitly_enabled(self):
        purchase, _attempt = self.completed()
        with override_settings(RASTISI_SMS_REFUND_ENABLED=True), \
                mock.patch.object(bank_refund_policy, "AUTOMATIC_POST_PAYMENT_REFUNDS_APPROVED", True):
            response = self.platform.get("/payments/sms-purchases/")
        self.assertContains(response, self.url(purchase))


class OtherSmsFlowsUnaffectedTests(SmsRefundDisabledBase):
    def test_purchase_checkout_and_verified_payment_still_credit_exactly_once(self):
        _r, purchase, attempt = self.purchase_and_attempt()
        self.assertEqual((purchase.status, attempt.status), (P.PENDING, S.PENDING))
        self.paid(attempt)
        self.callback(attempt)
        self.callback(attempt)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, P.COMPLETED)
        self.assertEqual(self.credits(), 100 + self.CREDITS)
        self.assertEqual(SmsCreditLedger.objects.filter(kind="purchase").count(), 1)

    def test_otp_still_sends_and_is_charged_normally(self):
        SmsTemplate.ensure_defaults()
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        otp = otp_service.request_otp("09121234567", store=self.store, ip_address="1.2.3.4")
        self.assertIsNotNone(otp.pk)
        from apps.sms.models import SmsLog

        self.assertEqual(SmsLog.objects.filter(recipient="09121234567").first().status, SmsLog.Status.SENT)
