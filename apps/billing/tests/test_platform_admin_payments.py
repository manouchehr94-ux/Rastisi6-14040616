"""Platform Admin → Payment Gateways / Transactions / Reconciliation / SMS purchases: access control, secret hygiene,
audited mutations, and the reconcile management command. Synthetic ids; mocked gateways."""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service, sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import (
    PLATFORM_MERCHANT, ZARINPAL_PLATFORM, open_invoice_for, patch_zibal, ready_platform_zibal,
)
from apps.portal.models import PlatformAuditLogEntry, PlatformGatewayConfig
from apps.portal.services import platform_gateway_service as pgs
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"
SECRET_FIELD_VALUE = "TYPED-SECRET-MERCHANT-VALUE-XYZ"


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", ALLOWED_HOSTS=[_HOST, "testserver"])
class PlatformAdminPaymentsBase(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.superuser = User.objects.create_user(
            username="pa-pay-super@example.com", email="pa-pay-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.owner = User.objects.create_user(username="pa-pay-owner@example.com", password="a-very-strong-pass-1")
        self.client.force_login(self.superuser)

    def get(self, path):
        return self.client.get(path, HTTP_HOST=_HOST)

    def post(self, path, data=None):
        return self.client.post(path, data or {}, HTTP_HOST=_HOST)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class AccessControlTests(PlatformAdminPaymentsBase):
    PATHS = ["/payments/gateways/", "/payments/transactions/", "/payments/reconciliation/", "/payments/sms-purchases/"]

    def test_anonymous_and_non_superusers_cannot_reach_any_platform_payment_page(self):
        for who in ("anonymous", "owner", "staff_only"):
            self.client.logout()
            if who == "owner":
                self.client.force_login(self.owner)
            elif who == "staff_only":
                staff = User.objects.create_user(username="pa-staff@example.com", password="a-very-strong-pass-1", is_staff=True)
                self.client.force_login(staff)
            for path in self.PATHS:
                response = self.get(path)
                self.assertIn(response.status_code, (302, 403, 404), f"{who} {path}")
                if response.status_code == 302:
                    self.assertIn("login", response["Location"])

    def test_mutations_are_post_only_and_blocked_for_non_superusers(self):
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=True)
        self.client.logout()
        self.client.force_login(self.owner)
        response = self.post("/payments/gateways/", {"action": "save", "gateway_code": "zibal", "cred_merchant": "HACK"})
        self.assertIn(response.status_code, (302, 403, 404))
        creds, _s, _src = pgs.credentials_and_mode("zibal")
        self.assertEqual(creds["merchant"], PLATFORM_MERCHANT)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class GatewayPageTests(PlatformAdminPaymentsBase):
    def test_page_lists_eligible_and_blocked_gateways_with_actionable_state(self):
        html = self.get("/payments/gateways/").content.decode()
        self.assertIn("gw-zibal", html)
        self.assertIn("gw-zarinpal", html)
        self.assertIn('data-status="missing_credentials"', html)     # implemented, not yet configured
        self.assertIn('data-status="not_implemented"', html)         # PSP skeletons: no functional adapter
        self.assertNotIn('id="gw-cod"', html)                        # COD is not a platform billing method

    def test_saving_a_gateway_enables_it_audits_it_and_never_echoes_the_secret(self):
        response = self.post("/payments/gateways/", {
            "action": "save", "gateway_code": "zibal", "cred_merchant": SECRET_FIELD_VALUE, "is_enabled": "on", "display_order": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(pgs.gateway_state("zibal").ready)
        for path in ("/payments/gateways/", "/payments/transactions/", "/payments/reconciliation/", "/payments/sms-purchases/"):
            page = self.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertNotIn(SECRET_FIELD_VALUE, page.content.decode(), path)
        followed = self.client.get("/payments/gateways/", HTTP_HOST=_HOST, follow=True)
        self.assertNotIn(SECRET_FIELD_VALUE, followed.content.decode())
        trail = " ".join(f"{e.action_code} {e.before_summary} {e.after_summary} {e.metadata}" for e in PlatformAuditLogEntry.objects.all())
        self.assertNotIn(SECRET_FIELD_VALUE, trail)
        self.assertIn("platform_gateway.saved", trail)
        self.assertNotIn(SECRET_FIELD_VALUE, PlatformGatewayConfig.objects.get(gateway_code="zibal").encrypted_credentials)

    def test_enabling_with_incomplete_credentials_is_refused_with_an_actionable_message(self):
        response = self.client.post("/payments/gateways/", {
            "action": "save", "gateway_code": "zarinpal", "cred_merchant_id": "short", "is_enabled": "on",
        }, HTTP_HOST=_HOST, follow=True)
        self.assertContains(response, "۳۶ کاراکتر")
        self.assertFalse(pgs.gateway_state("zarinpal").ready)

    def test_a_blocked_gateway_cannot_be_configured_through_a_forged_post(self):
        for code in ("saman", "snappay", "cod", "../x"):
            self.post("/payments/gateways/", {"action": "save", "gateway_code": code, "is_enabled": "on", "cred_merchant": "x"})
        self.assertFalse(PlatformGatewayConfig.objects.exists())

    def test_default_can_only_be_set_to_a_ready_gateway(self):
        self.post("/payments/gateways/", {"action": "set_default", "gateway_code": "zibal"})
        self.assertEqual(pgs.default_code(), "manual")
        ready_platform_zibal(self, default=False)
        self.post("/payments/gateways/", {"action": "set_default", "gateway_code": "zibal"})
        self.assertEqual(pgs.default_code(), "zibal")

    def test_legacy_zibal_route_redirects_to_the_unified_console_without_writing(self):
        response = self.post("/payments/zibal/", {
            "default_payment_provider": "zibal", "zibal_merchant": SECRET_FIELD_VALUE, "zibal_sandbox_mode": "",
        })
        self.assertEqual((response.status_code, response["Location"]), (302, "/payments/gateways/#gw-zibal"))
        self.assertFalse(pgs.gateway_state("zibal").ready)
        self.assertNotIn(SECRET_FIELD_VALUE, self.get("/payments/gateways/").content.decode())


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class TransactionsAndReconciliationTests(PlatformAdminPaymentsBase):
    def setUp(self):
        super().setUp()
        self.fake = patch_zibal(self)
        ready_platform_zibal(self)
        self.store = Store.objects.create(name="فروشگاه تراکنش", slug="tx-store", admin_subdomain="tx-store")
        _sub, self.invoice = open_invoice_for(self.store, code="tx")
        self.attempt, _session = payment_flow_service.start_payment(self.invoice, callback_base_url="https://rastisi.ir/")
        self.package = SmsPackage.objects.create(name="بسته", credit_amount=100, price=50_000)
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})
        self.purchase = balance_service.request_purchase(store=self.store, package=self.package)
        self.sms_attempt, _s = sms_svc.start_payment(self.purchase, callback_base_url="https://rastisi.ir/")

    def test_transactions_page_lists_both_contexts_with_filters(self):
        html = self.get("/payments/transactions/").content.decode()
        self.assertIn(self.invoice.number, html)
        self.assertIn(f"SMS-{self.purchase.pk}", html)
        only_sms = self.get("/payments/transactions/?kind=sms").content.decode()
        self.assertIn(f"SMS-{self.purchase.pk}", only_sms)
        self.assertNotIn(self.invoice.number, only_sms)
        failed = self.get("/payments/transactions/?status=failed").content.decode()
        self.assertNotIn(self.invoice.number, failed)

    def test_verify_now_is_server_side_only_and_applies_a_real_payment_once(self):
        self.fake.paid(amount_rial=self.invoice.amount_due * 10, order_id=self.attempt.public_token)
        self.post(f"/payments/verify/subscription/{self.attempt.pk}/")
        self.post(f"/payments/verify/subscription/{self.attempt.pk}/")
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, self.invoice.amount_due)

    def test_verify_now_cannot_fabricate_a_payment(self):
        self.post(f"/payments/verify/sms/{self.sms_attempt.pk}/")           # fake gateway says "not paid"
        self.assertEqual(SmsPackagePurchase.objects.get(pk=self.purchase.pk).status, SmsPackagePurchase.Status.PENDING)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 0)

    def test_reconciliation_lists_stale_and_flagged_attempts(self):
        SubscriptionPaymentAttempt.objects.filter(pk=self.attempt.pk).update(created_at=timezone.now() - timedelta(hours=1))
        SmsPackagePaymentAttempt.objects.filter(pk=self.sms_attempt.pk).update(
            status=SmsPackagePaymentAttempt.Status.REQUIRES_ACTION, failure_code="purchase_canceled",
        )
        html = self.get("/payments/reconciliation/").content.decode()
        self.assertIn(self.invoice.number, html)
        self.assertIn("purchase_canceled", html)
        self.assertIn("بررسی با درگاه", html)

    def test_sms_purchase_admin_actions_are_audited_and_use_the_ledgered_services(self):
        self.post(f"/payments/sms-purchases/{self.purchase.pk}/complete/")
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=self.purchase).count(), 1)
        self.post(f"/payments/sms-purchases/{self.purchase.pk}/complete/")           # idempotent: no second credit
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="platform_sms_purchase.complete").exists())
        self.post(f"/payments/sms-purchases/{self.purchase.pk}/bogus/")
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class ReconcileCommandTests(PlatformAdminPaymentsBase):
    def setUp(self):
        super().setUp()
        self.fake = patch_zibal(self)
        ready_platform_zibal(self)
        self.store = Store.objects.create(name="فروشگاه تطبیق", slug="rc-store", admin_subdomain="rc-store")
        _sub, invoice = open_invoice_for(self.store, code="rc")
        self.invoice = invoice
        self.attempt, _ = payment_flow_service.start_payment(invoice, callback_base_url="https://rastisi.ir/")
        self.package = SmsPackage.objects.create(name="بسته", credit_amount=10, price=20_000)
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})
        self.purchase = balance_service.request_purchase(store=self.store, package=self.package)
        self.fake.track_id = 888
        self.sms_attempt, _ = sms_svc.start_payment(self.purchase, callback_base_url="https://rastisi.ir/")

    def age(self, minutes):
        old = timezone.now() - timedelta(minutes=minutes)
        SubscriptionPaymentAttempt.objects.update(created_at=old)
        SmsPackagePaymentAttempt.objects.update(created_at=old)

    def run_cmd(self, *args):
        out = StringIO()
        call_command("reconcile_platform_payments", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_fresh_attempts_are_left_alone(self):
        self.assertIn("checked=0", self.run_cmd())
        self.assertEqual(self.fake.calls_to("verify"), [])

    def test_stale_paid_attempts_are_confirmed_exactly_once_across_repeated_runs(self):
        self.age(30)
        # one answer function serves both verifies; each attempt gets its own order id / amount
        def answer(url, json=None, timeout=None, **kw):
            path = url.rsplit("/", 1)[-1]
            self.fake.calls.append((path, dict(json or {})))
            from apps.billing.tests.platform_payment_support import _Resp
            if path == "verify":
                if str(json.get("trackId")) == "777":
                    return _Resp({"result": 100, "amount": self.invoice.amount_due * 10, "status": 1, "orderId": self.attempt.public_token})
                return _Resp({"result": 100, "amount": 200_000, "status": 1, "orderId": self.sms_attempt.public_token})
            return _Resp({"result": 100, "trackId": 1})
        from unittest.mock import patch
        with patch("apps.billing.providers.zibal.requests.post", answer):
            first = self.run_cmd()
            second = self.run_cmd()
        self.assertIn("confirmed=2", first)
        self.assertIn("checked=0", second)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, self.invoice.amount_due)
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10)
        self.assertEqual(SmsCreditLedger.objects.count(), 1)

    def test_unpaid_stale_attempts_stay_pending_and_are_never_failed_by_the_job(self):
        self.age(30)
        out = self.run_cmd()
        self.assertIn("still_pending=2", out)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=self.attempt.pk).status, SubscriptionPaymentAttempt.Status.PENDING)
        self.assertEqual(SmsPackagePaymentAttempt.objects.get(pk=self.sms_attempt.pk).status, SmsPackagePaymentAttempt.Status.PENDING)

    def test_dry_run_changes_nothing_and_calls_no_gateway(self):
        self.age(30)
        before = len(self.fake.calls)
        self.assertIn("(dry-run)", self.run_cmd("--dry-run"))
        self.assertEqual(len(self.fake.calls), before)

    def test_very_old_attempts_outside_the_window_are_ignored(self):
        self.age(60 * 24 * 10)
        self.assertIn("checked=0", self.run_cmd())
