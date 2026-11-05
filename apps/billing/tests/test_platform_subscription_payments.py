"""End-to-end platform subscription purchase through the PLATFORM's own gateway (mocked Zibal/Zarinpal; synthetic ids):
owner checkout → gateway redirect → public callback → server-side verify → exactly-once activation."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service
from apps.billing.tests.platform_payment_support import (
    FakeZibal, open_invoice_for, patch_zarinpal, patch_zibal, ready_platform_zarinpal, ready_platform_zibal,
)
from apps.core.models import AuditLogEntry
from apps.portal.models import OwnerProfile
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service

User = get_user_model()
_HOST = "rastisi.localhost"
S = SubscriptionPaymentAttempt.Status


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_BILLING_PROVIDER="manual")
class PlatformSubscriptionPaymentTests(TestCase):
    PRICE = 490_000

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.store = Store.objects.create(name="فروشگاه پرداخت", slug="pay-store", admin_subdomain="pay-store")
        self.owner = User.objects.create_user(username="09121240011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121240011", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        trial_plan = Plan.objects.create(code="trial-pay", name="Trial", is_publicly_selectable=True)
        trial_version = PlanVersion.objects.create(
            plan=trial_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.NONE, display_price=0, trial_days=14,
        )
        sub = subscription_service.create_subscription(self.store, trial_version, actor=self.owner)
        self.subscription = subscription_service.start_trial(sub, actor=self.owner)
        self.plan = Plan.objects.create(code="pro-pay", name="Pro", is_active=True, is_publicly_selectable=True)
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=self.PRICE,
        )
        self.fake = patch_zibal(self)
        ready_platform_zibal(self)
        self.client.force_login(self.owner)

    # -- helpers ----------------------------------------------------------------------------------------------------
    def checkout(self, **extra):
        return self.client.post(
            f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", extra, HTTP_HOST=_HOST,
        )

    def start(self):
        response = self.checkout()
        attempt = SubscriptionPaymentAttempt.objects.filter(store=self.store).order_by("-pk").first()
        return response, attempt

    def callback(self, attempt, query="success=1&status=2&trackId=777"):
        cache.clear()                                     # the verify throttle is per-token and cache-backed
        return self.client.get(f"/billing/return/{attempt.public_token}/?{query}", HTTP_HOST=_HOST)

    def invoice(self, attempt):
        return SubscriptionInvoice.objects.get(pk=attempt.invoice_id)

    def reload_sub(self):
        return StoreSubscription.objects.get(pk=self.subscription.pk)

    # -- checkout ---------------------------------------------------------------------------------------------------
    def test_owner_checkout_redirects_to_the_platform_gateway_with_platform_merchant_and_a_public_callback(self):
        response, attempt = self.start()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://gateway.zibal.ir/start/777")
        self.assertEqual((attempt.provider, attempt.status, attempt.provider_session_id), ("zibal", S.PENDING, "777"))
        sent = self.fake.calls_to("request")[0]
        self.assertEqual(sent["amount"], self.PRICE * 10)                            # Toman → Rial at the single boundary
        self.assertEqual(sent["orderId"], attempt.public_token)
        self.assertTrue(sent["callbackUrl"].endswith(f"/billing/return/{attempt.public_token}/"))
        self.assertTrue(attempt.return_to.endswith(f"/app/stores/{self.store.public_id}/billing/return/"))
        self.assertTrue(sent["callbackUrl"].startswith("http"))
        self.assertEqual(self.reload_sub().status, StoreSubscription.Status.TRIALING)   # nothing activated by a redirect

    def test_nothing_is_fulfilled_by_the_redirect_alone(self):
        _response, attempt = self.start()
        invoice = self.invoice(attempt)
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAYMENT_PENDING)
        self.assertEqual(invoice.amount_paid, 0)

    def test_gateway_failure_at_start_is_a_safe_failed_attempt_not_a_500(self):
        def boom(*a, **k):
            import requests
            raise requests.ConnectionError("down")

        from unittest.mock import patch
        with patch("apps.billing.providers.zibal.requests.post", boom):
            response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing/", response["Location"])
        attempt = SubscriptionPaymentAttempt.objects.get(store=self.store)
        self.assertEqual(attempt.status, S.FAILED)
        self.assertEqual(attempt.failure_code, "connection_error")
        self.assertEqual(self.invoice(attempt).amount_paid, 0)

    def test_manual_mode_keeps_the_previous_behaviour(self):
        from apps.portal.services import platform_gateway_service as pgs
        pgs.save_gateway("zibal", credentials={}, sandbox=False, enabled=False)
        cache.clear()
        response = self.checkout()
        attempt = SubscriptionPaymentAttempt.objects.get(store=self.store)
        self.assertEqual(attempt.provider, "manual")
        self.assertIn(f"/app/stores/{self.store.public_id}/billing/return/{attempt.public_token}/", response["Location"])

    def test_owner_can_choose_among_ready_gateways_but_not_an_unready_one(self):
        ready_platform_zarinpal(self)
        patch_zarinpal(self)
        response = self.checkout(gateway="zarinpal")
        attempt = SubscriptionPaymentAttempt.objects.filter(store=self.store).order_by("-pk").first()
        self.assertEqual(attempt.provider, "zarinpal")
        from apps.orders.gateways.zarinpal import ZARINPAL_STARTPAY_URL
        self.assertTrue(response["Location"].startswith(ZARINPAL_STARTPAY_URL))
        before = SubscriptionPaymentAttempt.objects.count()
        bad = self.checkout(gateway="saman")
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), before)
        self.assertEqual(bad.status_code, 302)

    # -- callback: success --------------------------------------------------------------------------------------------
    def test_verified_callback_activates_the_subscription_exactly_once(self):
        _r, attempt = self.start()
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=attempt.public_token)
        response = self.callback(attempt)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/billing/return/?payment=ok"))
        attempt.refresh_from_db()
        invoice = self.invoice(attempt)
        self.assertEqual(attempt.status, S.SUCCEEDED)
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(invoice.amount_paid, self.PRICE)
        sub = self.reload_sub()
        self.assertEqual((sub.status, sub.plan_version_id), (StoreSubscription.Status.ACTIVE, self.version.pk))

    def test_repeated_and_concurrent_style_callbacks_apply_the_payment_once(self):
        _r, attempt = self.start()
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=attempt.public_token)
        for _ in range(4):
            self.callback(attempt)
        verify_calls = len(self.fake.calls_to("verify"))
        invoice = self.invoice(attempt)
        self.assertEqual(invoice.amount_paid, self.PRICE)
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(status=S.SUCCEEDED).count(), 1)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_confirmed").count(), 1)
        self.assertEqual(verify_calls, 1, "a final attempt must not hit the gateway again")

    def test_direct_service_calls_are_idempotent_too(self):
        _r, attempt = self.start()
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=attempt.public_token)
        for _ in range(3):
            payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        self.assertEqual(self.invoice(attempt).amount_paid, self.PRICE)

    # -- callback: not proof of payment ------------------------------------------------------------------------------
    def test_a_forged_success_callback_without_a_gateway_verified_payment_changes_nothing(self):
        _r, attempt = self.start()                       # fake.verify says "not paid" (result 202)
        response = self.callback(attempt, "success=1&status=2&trackId=777")
        self.assertTrue(response["Location"].endswith("payment=pending"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, S.PENDING)
        self.assertEqual(self.invoice(attempt).amount_paid, 0)
        self.assertEqual(self.reload_sub().status, StoreSubscription.Status.TRIALING)

    def test_a_cancelled_payment_marks_the_attempt_failed_but_stays_retryable(self):
        _r, attempt = self.start()
        response = self.callback(attempt, "success=0&status=3&trackId=777")
        self.assertTrue(response["Location"].endswith("payment=failed"))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.FAILED, "gateway_declined"))
        invoice = self.invoice(attempt)
        self.assertTrue(invoice.is_payable)
        self.assertEqual(self.reload_sub().status, StoreSubscription.Status.TRIALING)
        self.fake.track_id = 888                          # the owner retries ⇒ a NEW attempt (history preserved)
        self.checkout()
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(invoice=invoice).count(), 2)

    def test_a_late_real_payment_after_a_failed_return_is_still_honoured(self):
        _r, attempt = self.start()
        self.callback(attempt, "success=0&trackId=777")
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.FAILED)
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=attempt.public_token)
        payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        self.assertEqual(self.invoice(attempt).status, SubscriptionInvoice.Status.PAID)

    def test_an_amount_mismatch_is_flagged_for_reconciliation_and_never_fulfilled(self):
        _r, attempt = self.start()
        self.fake.paid(amount_rial=1_000, order_id=attempt.public_token)         # gateway took a different amount
        response = self.callback(attempt)
        self.assertTrue(response["Location"].endswith("payment=action"))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.REQUIRES_ACTION, "amount_mismatch"))
        self.assertEqual(self.invoice(attempt).amount_paid, 0)
        self.assertEqual(self.reload_sub().status, StoreSubscription.Status.TRIALING)

    def test_a_payment_for_a_different_order_id_is_never_attributed_to_this_attempt(self):
        _r, attempt = self.start()
        self.fake.paid(amount_rial=self.PRICE * 10, order_id="someone-elses-order")
        self.callback(attempt)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.REQUIRES_ACTION, "order_mismatch"))
        self.assertEqual(self.invoice(attempt).amount_paid, 0)

    def test_a_second_payment_on_an_already_paid_invoice_is_flagged_not_applied(self):
        _r, first = self.start()
        invoice = self.invoice(first)
        self.fake.track_id = 888
        # second attempt created while the first is still in flight (e.g. two tabs)
        second, _session = payment_flow_service.start_payment(invoice, callback_base_url="https://rastisi.test")
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=first.public_token)
        payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=first.pk))
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=second.public_token)
        payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=second.pk))
        second.refresh_from_db()
        self.assertEqual((second.status, second.failure_code), (S.REQUIRES_ACTION, "duplicate_payment"))
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, self.PRICE)                    # applied once
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(status=S.SUCCEEDED).count(), 1)

    def test_unknown_or_foreign_tokens_404_and_never_call_the_gateway(self):
        for token in ("nope", "sms_nope", "x" * 40):
            self.assertEqual(self.client.get(f"/billing/return/{token}/", HTTP_HOST=_HOST).status_code, 404, token)
        self.assertEqual(self.fake.calls, [])

    def test_a_subscription_token_that_happens_to_start_with_the_sms_prefix_still_resolves(self):
        _r, attempt = self.start()
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(public_token="sms_collision-subscription-token")
        self.fake.paid(amount_rial=self.PRICE * 10, order_id="sms_collision-subscription-token")
        cache.clear()
        response = self.client.get("/billing/return/sms_collision-subscription-token/?success=1", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.SUCCEEDED)

    def test_the_callback_is_rate_limited_per_attempt(self):
        _r, attempt = self.start()
        cache.clear()
        self.client.get(f"/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST)
        self.client.get(f"/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST)
        self.client.get(f"/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST)
        self.assertEqual(len(self.fake.calls_to("verify")), 1)

    def test_open_redirect_via_return_to_is_impossible(self):
        for hostile in ("https://evil.example/x", "//evil.example/x", "/\\evil.example", "javascript:alert(1)", "",
                        "https://user:pw@rastisi.localhost/x", "https://rastisi.localhost.evil.example/x", "/x\r\nSet-Cookie: a=b"):
            self.assertEqual(payment_flow_service.safe_return_to(hostile), "", hostile)
        self.assertEqual(payment_flow_service.safe_return_to("/admin-portal/billing/?a=1"), "/admin-portal/billing/?a=1")
        self.assertEqual(payment_flow_service.safe_return_to("https://rastisi.localhost/app/x/"), "https://rastisi.localhost/app/x/")

    def test_callback_data_is_only_a_hint_and_secrets_are_never_logged(self):
        _r, attempt = self.start()
        with self.assertLogs("billing", level="WARNING") as logs:
            from unittest.mock import patch
            with patch("apps.billing.providers.zibal.requests.post", side_effect=Exception("boom")):
                self.callback(attempt, "success=1&token=SECRET-QUERY-VALUE")
        self.assertNotIn("SECRET-QUERY-VALUE", "\n".join(logs.output))
        self.assertNotIn("PLATFORM-FAKE-MERCHANT", "\n".join(logs.output))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, S.PENDING)

    # -- zarinpal through the adapter bridge --------------------------------------------------------------------------
    def test_zarinpal_flow_verifies_server_side_and_activates_once(self):
        zp = patch_zarinpal(self)
        ready_platform_zarinpal(self, default=True)
        self.checkout()
        attempt = SubscriptionPaymentAttempt.objects.filter(store=self.store).order_by("-pk").first()
        self.assertEqual((attempt.provider, attempt.provider_session_id), ("zarinpal", zp.AUTHORITY))
        sent = zp.calls[0][1]
        self.assertEqual((sent["merchant_id"], sent["amount"]), ("a" * 36, self.PRICE * 10))
        zp.paid()
        response = self.callback(attempt, f"Authority={zp.AUTHORITY}&Status=OK")
        self.assertTrue(response["Location"].endswith("payment=ok"))
        self.assertEqual(self.invoice(attempt).amount_paid, self.PRICE)
        self.assertEqual(self.reload_sub().status, StoreSubscription.Status.ACTIVE)

    def test_zarinpal_nok_status_without_gateway_confirmation_fails_the_attempt(self):
        zp = patch_zarinpal(self)
        ready_platform_zarinpal(self, default=True)
        self.checkout()
        attempt = SubscriptionPaymentAttempt.objects.filter(store=self.store).order_by("-pk").first()
        zp.verify_payload = {"data": {"code": -51, "message": "failed"}, "errors": []}
        self.callback(attempt, f"Authority={zp.AUTHORITY}&Status=NOK")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, S.FAILED)
        self.assertEqual(self.invoice(attempt).amount_paid, 0)

    # -- merchant dashboard path --------------------------------------------------------------------------------------
    def test_dashboard_invoice_payment_uses_the_same_platform_flow(self):
        sub = self.reload_sub()
        from apps.billing.services import invoice_service
        invoice = invoice_service.create_invoice(
            sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(self.version)],
        )
        invoice = invoice_service.open_invoice(invoice)
        self.assertEqual(invoice.store_id, self.store.pk)
        self.assertFalse(SubscriptionPaymentAttempt.objects.filter(invoice=invoice).exists())
        # drive the dashboard view through the service contract it uses
        attempt, session = payment_flow_service.start_payment(
            invoice, callback_base_url="https://rastisi.ir/", return_to=f"/admin-portal/billing/invoices/{invoice.pk}/",
        )
        self.assertEqual(session.redirect_url, "https://gateway.zibal.ir/start/777")
        self.fake.paid(amount_rial=self.PRICE * 10, order_id=attempt.public_token)
        response = self.callback(attempt)
        self.assertTrue(response["Location"].endswith(f"/admin-portal/billing/invoices/{invoice.pk}/?payment=ok"))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice.pk).status, SubscriptionInvoice.Status.PAID)
