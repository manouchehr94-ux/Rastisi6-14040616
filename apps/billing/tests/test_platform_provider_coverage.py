"""Platform provider coverage: the evidence matrix is pinned to the adapters, every status is distinct and truthful,
Pasargad (Dorsa) works end-to-end through the shared platform infrastructure with INDEPENDENT credentials, and the
secure configuration test never moves money or leaks a secret. Synthetic credentials; mocked provider APIs."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import payment_flow_service, refund_service, sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import (
    PASARGAD_CREDS, PLATFORM_MERCHANT, STORE_MERCHANT, open_invoice_for, patch_pasargad, patch_zibal,
    ready_platform_pasargad, ready_platform_zibal,
)
from apps.core.models import AuditLogEntry
from apps.orders.gateways.base import GatewayCategory, PaymentOperation
from apps.orders.gateways.redirects import gateway_redirect_response
from apps.orders.gateways.registry import get_adapter, registered_codes
from apps.orders.models import PaymentGatewayConfig
from apps.portal.models import OwnerProfile, PlatformAuditLogEntry, PlatformGatewayConfig
from apps.portal.services import platform_gateway_matrix as matrix
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service

User = get_user_model()
S = SubscriptionPaymentAttempt.Status
_HOST = "rastisi.localhost"
SECRET = PASARGAD_CREDS["password"]


class MatrixIsPinnedToAdaptersTests(SimpleTestCase):
    """The provider matrix is evidence; it must never contradict what the adapters themselves declare."""

    def test_every_registered_gateway_has_a_matrix_row_except_store_only_methods(self):
        self.assertEqual(set(registered_codes()) - set(matrix.MATRIX), set(matrix.STORE_ONLY))
        self.assertEqual(set(matrix.STORE_ONLY), {"cod", "card_to_card"})
        self.assertEqual({c for c, f in matrix.MATRIX.items() if f.kind == matrix.KIND_ONLINE} - set(registered_codes()), set())

    def test_cod_and_store_card_transfer_are_not_platform_methods_at_all(self):
        for code in matrix.STORE_ONLY:
            self.assertNotIn(code, matrix.MATRIX)
            self.assertNotIn(code, matrix.IMPLEMENTED_CODES)
            self.assertNotIn(code, pgs.ELIGIBLE_CODES)
            self.assertFalse(pgs.is_eligible(code))

    def test_approved_online_rows_are_real_verified_adapters_without_gates(self):
        for code, facts in matrix.MATRIX.items():
            if facts.platform == matrix.APPROVED and facts.kind == matrix.KIND_ONLINE:
                adapter = get_adapter(code)
                self.assertTrue(adapter.is_online, code)
                self.assertFalse(adapter.documentation_blocked, code)
                self.assertEqual(facts.gates, (), code)
                self.assertIn(adapter.category, (GatewayCategory.PSP, GatewayCategory.FACILITATOR), code)
                self.assertTrue(adapter.supports(PaymentOperation.CREATE) and adapter.supports(PaymentOperation.VERIFY), code)
                self.assertTrue(facts.evidence and facts.setup_steps, code)

    def test_gated_rows_have_real_adapters_and_the_right_gates(self):
        for code, facts in matrix.MATRIX.items():
            if facts.platform != matrix.GATED:
                continue
            adapter = get_adapter(code)
            self.assertTrue(adapter.supports(PaymentOperation.CREATE) and adapter.supports(PaymentOperation.VERIFY), code)
            self.assertIn(matrix.GATE_LIVE_VERIFICATION, facts.gates, code)                 # mocked tests never make anything "ready"
            if adapter.category == GatewayCategory.BNPL:
                self.assertEqual(facts.default_purchase_types, (), code)                     # no purchase type until explicitly approved
                self.assertIn(matrix.GATE_PROVIDER_APPROVAL, facts.gates, code)             # written approval for SaaS purchases
                self.assertTrue(adapter.supports(PaymentOperation.SETTLE), code)
                self.assertFalse(adapter.supports_dry_run_session, code)                     # never invents a cart for a test
            else:
                self.assertIn(matrix.GATE_CONTRACT_VERIFICATION, facts.gates, code)
                self.assertTrue(adapter.documentation_blocked, code)                         # unverified contract stays blocked for stores
            self.assertTrue(facts.blocker and facts.evidence, code)
        self.assertTrue(get_adapter("mellat").supports(PaymentOperation.SETTLE))             # SETTLE is a DISTINCT capability

    def test_not_implemented_rows_are_really_skeletons(self):
        for code, facts in matrix.MATRIX.items():
            if facts.platform == matrix.NOT_IMPLEMENTED:
                adapter = get_adapter(code)
                self.assertTrue(adapter.documentation_blocked, code)
                self.assertFalse(adapter.supports(PaymentOperation.CREATE), code)
                self.assertTrue(facts.blocker, code)

    def test_the_manual_card_row_is_a_first_class_manual_method_without_any_adapter(self):
        facts = matrix.MATRIX[matrix.PLATFORM_CARD]
        self.assertEqual((facts.kind, facts.platform, facts.gates), (matrix.KIND_MANUAL, matrix.APPROVED, ()))
        self.assertNotIn(matrix.PLATFORM_CARD, registered_codes())                           # never the store's card_to_card adapter
        self.assertTrue(any(f["name"] == "destination_card" for f in facts.manual_fields))

    def test_the_allow_list_is_derived_from_the_matrix(self):
        self.assertEqual(pgs.ELIGIBLE_CODES, matrix.IMPLEMENTED_CODES)
        self.assertEqual(set(pgs.ELIGIBLE_CODES), {"zibal", "zarinpal", "pasargad", "snappay", "torobpay", "saman", "mellat", "platform_card"})


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class StatusTaxonomyTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()

    def state(self, code):
        return pgs.gateway_state(code)

    def test_every_provider_gets_the_status_that_is_actually_true(self):
        expected = {
            "zibal": pgs.MISSING_CREDENTIALS, "zarinpal": pgs.MISSING_CREDENTIALS, "pasargad": pgs.MISSING_CREDENTIALS,
            "snappay": pgs.MISSING_CREDENTIALS, "torobpay": pgs.MISSING_CREDENTIALS, "saman": pgs.MISSING_CREDENTIALS,
            "mellat": pgs.MISSING_CREDENTIALS, "platform_card": pgs.MISSING_CREDENTIALS,
            "parsian": pgs.NOT_IMPLEMENTED, "sadad": pgs.NOT_IMPLEMENTED, "tejarat": pgs.NOT_IMPLEMENTED,
            "cod": pgs.NOT_ELIGIBLE, "card_to_card": pgs.NOT_ELIGIBLE,
        }
        for code, status in expected.items():
            self.assertEqual(self.state(code).status, status, code)
            self.assertFalse(self.state(code).ready, code)

    def test_blocked_providers_do_not_share_one_generic_message(self):
        details = {code: self.state(code).status_detail for code in ("parsian", "sadad", "tejarat")}
        self.assertEqual(len(set(details.values())), len(details), "each blocker must be provider-specific")
        self.assertTrue(all(len(text) > 25 for text in details.values()))
        self.assertIn("PSP", self.state("tejarat").status_detail)                            # Tejarat: underlying PSP unknown

    def test_status_labels_are_distinct_and_cover_every_case(self):
        self.assertEqual(len(set(pgs.STATUS_LABELS.values())), 8)
        self.assertEqual(set(pgs.STATUS_LABELS), {pgs.READY, pgs.DISABLED, pgs.MISSING_CREDENTIALS, pgs.MISSING_CONFIG,
                                                  pgs.PENDING_CONTRACT, pgs.PENDING_VERIFICATION, pgs.NOT_IMPLEMENTED, pgs.NOT_ELIGIBLE})

    def test_ready_disabled_and_missing_credentials_transitions(self):
        pgs.save_gateway("pasargad", credentials=dict(PASARGAD_CREDS), sandbox=False, enabled=False)
        self.assertEqual(self.state("pasargad").status, pgs.DISABLED)                 # complete but switched off
        pgs.save_gateway("pasargad", credentials={}, sandbox=False, enabled=True)
        self.assertEqual(self.state("pasargad").status, pgs.READY)
        self.assertEqual(pgs.ready_codes(), ["pasargad"])
        incomplete = dict(PASARGAD_CREDS, terminalNumber="")
        PlatformGatewayConfig.objects.filter(gateway_code="pasargad").delete()
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.save_gateway("pasargad", credentials=incomplete, sandbox=False, enabled=True)
        self.assertEqual(self.state("pasargad").status, pgs.MISSING_CREDENTIALS)

    @override_settings(DEBUG=False, RASTISI_PLATFORM_PRIMARY_HOST="rastisi.localhost")
    def test_a_local_callback_domain_is_a_configuration_problem_not_a_credential_problem(self):
        pgs.save_gateway("pasargad", credentials=dict(PASARGAD_CREDS), sandbox=False, enabled=False)
        state = self.state("pasargad")
        self.assertEqual(state.status, pgs.MISSING_CONFIG)
        self.assertIn("localhost", state.status_detail)
        self.assertTrue(state.configured)                      # credentials are fine; the callback domain is not
        with self.assertRaises(pgs.PlatformGatewayError):      # …so it can never become the default
            pgs.set_default("pasargad")

    @override_settings(DEBUG=False, RASTISI_PLATFORM_PRIMARY_HOST="rastisi.localhost")
    def test_sandbox_mode_allows_a_local_callback_domain_for_laptop_qa(self):
        pgs.save_gateway("zibal", credentials={}, sandbox=True, enabled=True)
        self.assertEqual(self.state("zibal").status, pgs.READY)        # no money moves in sandbox
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=True)
        self.assertEqual(self.state("zibal").status, pgs.MISSING_CONFIG)   # live mode needs a real domain

    def test_the_default_cannot_be_a_gateway_that_is_not_ready(self):
        for code in ("zibal", "pasargad", "snappay", "saman", "cod", "nope"):
            with self.assertRaises(pgs.PlatformGatewayError, msg=code):
                pgs.set_default(code)
        pgs.set_default("manual")

    def test_blocked_providers_cannot_be_configured_even_by_direct_service_calls(self):
        for code in ("parsian", "sadad", "tejarat", "cod", "card_to_card"):
            with self.assertRaises(pgs.PlatformGatewayError, msg=code):
                pgs.save_gateway(code, credentials={"client_id": "x", "merchant_id": "y" * 36}, sandbox=True, enabled=True)
            with self.assertRaises(pgs.PlatformGatewayError, msg=code):
                pgs.run_connection_test(code, callback_base="https://rastisi.ir/")
        self.assertFalse(PlatformGatewayConfig.objects.exists())


class RedirectRefererTests(SimpleTestCase):
    def test_pasargad_is_reached_through_an_origin_referrer_interstitial(self):
        response = gateway_redirect_response("https://pep.shaparak.ir/dorsa1/URL?x=1&y=<2>", adapter=get_adapter("pasargad"))
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "origin")
        self.assertIn('<meta name="referrer" content="origin">', body)
        self.assertIn("http-equiv=\"refresh\"", body)
        self.assertNotIn("<2>", body)                               # the URL is HTML-escaped
        self.assertNotIn("<script", body)                           # works under a strict CSP

    def test_other_providers_keep_a_plain_302(self):
        for code in ("zibal", "zarinpal", "snappay"):
            response = gateway_redirect_response("https://gateway.example/start/1", adapter=get_adapter(code))
            self.assertEqual((response.status_code, response["Location"]), (302, "https://gateway.example/start/1"), code)
        self.assertEqual(gateway_redirect_response("https://x.example/", adapter=None).status_code, 302)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", RASTISI_BILLING_PROVIDER="manual")
class PasargadPlatformFlowTests(TestCase):
    PRICE = 490_000

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.store = Store.objects.create(name="فروشگاه پاسارگاد", slug="pg-store", admin_subdomain="pg-store")
        self.owner = User.objects.create_user(username="09121250077", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121250077", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        trial = Plan.objects.create(code="trial-pg", name="Trial", is_publicly_selectable=True)
        trial_v = PlanVersion.objects.create(
            plan=trial, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.NONE, display_price=0, trial_days=14,
        )
        sub = subscription_service.create_subscription(self.store, trial_v, actor=self.owner)
        self.subscription = subscription_service.start_trial(sub, actor=self.owner)
        self.plan = Plan.objects.create(code="pro-pg", name="Pro", is_active=True, is_publicly_selectable=True)
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=self.PRICE,
        )
        # The STORE has its own (different) Pasargad terminal — it must never be touched.
        cfg = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="pasargad", is_active=True)
        cfg.set_credentials({"username": "STORE-USER", "password": "STORE-PASS", "terminalNumber": "999999", "serviceCode": "8"})
        cfg.save()
        self.store_snapshot = PaymentGatewayConfig.objects.get(pk=cfg.pk).encrypted_credentials
        self.fake = patch_pasargad(self)
        ready_platform_pasargad(self, default=True)
        self.client.force_login(self.owner)

    def checkout(self, **extra):
        return self.client.post(f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", extra, HTTP_HOST=_HOST)

    def start(self):
        response = self.checkout()
        return response, SubscriptionPaymentAttempt.objects.filter(store=self.store).order_by("-pk").first()

    def callback(self, attempt, query):
        cache.clear()
        return self.client.get(f"/billing/return/{attempt.public_token}/?{query}", HTTP_HOST=_HOST)

    def invoice(self, attempt):
        return SubscriptionInvoice.objects.get(pk=attempt.invoice_id)

    def pay(self, attempt):
        self.fake.paid(amount_rial=self.PRICE * 10)

    # -- request / redirect -------------------------------------------------------------------------------------
    def test_checkout_uses_the_platform_terminal_numeric_invoice_and_the_referer_interstitial(self):
        response, attempt = self.start()
        self.assertEqual(response.status_code, 200)                                  # interstitial, not a bare 302
        body = response.content.decode()
        self.assertIn('<meta name="referrer" content="origin">', body)
        self.assertIn(f"https://pep.shaparak.ir/dorsa1/{self.fake.URL_ID}", body)
        self.assertEqual(response["Referrer-Policy"], "origin")
        purchase = self.fake.calls_to("purchase")[0]
        self.assertEqual(purchase["terminalNumber"], PASARGAD_CREDS["terminalNumber"])          # platform terminal
        self.assertNotEqual(purchase["terminalNumber"], "999999")                               # not the store's
        self.assertEqual(purchase["amount"], self.PRICE * 10)                                   # Toman → Rial once
        self.assertEqual(purchase["invoice"], f"1{attempt.pk:09d}")                             # digits only, unique
        self.assertTrue(purchase["callbackApi"].endswith(f"/billing/return/{attempt.public_token}/"))
        tokens = [c for c in self.fake.calls if c[0] == "getToken"]
        self.assertEqual(tokens[0][1]["username"], PASARGAD_CREDS["username"])
        self.assertEqual((attempt.provider, attempt.provider_session_id), ("pasargad", f"1{attempt.pk:09d}"))
        self.assertEqual(attempt.provider_extra.get("urlId"), self.fake.URL_ID)                 # server-side only
        self.assertEqual(self.subscription.status, StoreSubscription.Status.TRIALING)

    def test_store_terminal_is_never_used_or_modified(self):
        self.start()
        self.pay(None)
        usernames = {payload.get("username") for name, payload, _h in self.fake.calls if name == "getToken"}
        self.assertEqual(usernames, {PASARGAD_CREDS["username"]})
        cfg = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="pasargad")
        self.assertEqual(cfg.encrypted_credentials, self.store_snapshot)

    # -- verification ---------------------------------------------------------------------------------------------
    def test_success_callback_verifies_with_the_server_stored_urlid_and_fulfils_once(self):
        _r, attempt = self.start()
        self.pay(attempt)
        response = self.callback(attempt, f"invoiceId={attempt.provider_session_id}&status=success&referenceNumber=R1&trackId=T1&urlId=EVIL-BROWSER-VALUE")
        self.assertTrue(response["Location"].endswith("payment=ok"))
        verify = self.fake.calls_to("verify-transactions")
        self.assertEqual(len(verify), 1)
        self.assertEqual(verify[0], {"invoice": attempt.provider_session_id, "urlId": self.fake.URL_ID})   # not the browser's
        self.assertEqual(self.fake.calls_to("payment-inquiry")[0], {"invoiceId": attempt.provider_session_id})
        self.assertEqual(self.invoice(attempt).amount_paid, self.PRICE)
        self.assertEqual(StoreSubscription.objects.get(pk=self.subscription.pk).status, StoreSubscription.Status.ACTIVE)

    def test_repeated_callbacks_are_idempotent_and_do_not_reverify(self):
        _r, attempt = self.start()
        self.pay(attempt)
        for _ in range(4):
            self.callback(attempt, "status=success")
        self.assertEqual(len(self.fake.calls_to("verify-transactions")), 1)
        self.assertEqual(self.invoice(attempt).amount_paid, self.PRICE)
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_confirmed").count(), 1)

    def test_a_forged_success_without_a_gateway_confirmed_payment_changes_nothing(self):
        _r, attempt = self.start()                                      # inquiry says "unknown" (status 2)
        response = self.callback(attempt, "status=success&referenceNumber=FORGED")
        self.assertTrue(response["Location"].endswith("payment=pending"))
        self.assertEqual(self.fake.calls_to("verify-transactions"), [])
        self.assertEqual(self.invoice(attempt).amount_paid, 0)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.PENDING)

    def test_cancelled_expired_and_failed_returns_fail_the_attempt_only_after_the_server_agrees(self):
        for status in ("cancel", "expire", "failed"):
            _r, attempt = self.start()
            self.callback(attempt, f"status={status}")
            self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.FAILED, status)
        self.assertTrue(self.invoice(attempt).is_payable)

    def test_unknown_status_return_stays_pending(self):
        _r, attempt = self.start()
        self.callback(attempt, "status=unknown")
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.PENDING)

    def test_amount_mismatch_is_flagged_and_never_finalised_at_the_provider(self):
        _r, attempt = self.start()
        self.fake.paid(amount_rial=1000)
        response = self.callback(attempt, "status=success")
        self.assertTrue(response["Location"].endswith("payment=action"))
        self.assertEqual(self.fake.calls_to("verify-transactions"), [])                         # never finalise a wrong amount
        refreshed = SubscriptionPaymentAttempt.objects.get(pk=attempt.pk)
        self.assertEqual((refreshed.status, refreshed.failure_code), (S.REQUIRES_ACTION, "amount_mismatch"))
        self.assertEqual(self.invoice(attempt).amount_paid, 0)

    def test_provider_verify_rejection_after_a_paid_inquiry_does_not_fulfil(self):
        _r, attempt = self.start()
        self.pay(attempt)
        self.fake.verify_result = {"resultCode": 13071}
        self.callback(attempt, "status=success")
        self.assertEqual(self.invoice(attempt).amount_paid, 0)
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.PENDING)

    def test_already_verified_at_the_provider_is_accepted_idempotently(self):
        _r, attempt = self.start()
        self.pay(attempt)
        self.fake.verify_result = {"resultCode": 13428}
        self.callback(attempt, "status=success")
        self.assertEqual(self.invoice(attempt).amount_paid, self.PRICE)

    def test_gateway_rejecting_the_purchase_is_a_safe_failed_attempt(self):
        self.fake.purchase_result = {"resultCode": 13028, "resultMsg": "bad callback domain"}
        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        attempt = SubscriptionPaymentAttempt.objects.get(store=self.store)
        self.assertEqual((attempt.status, attempt.failure_code), (S.FAILED, "pasargad_13028"))

    # -- reconciliation / SMS / refund ---------------------------------------------------------------------------
    def test_reconcile_confirms_a_paid_pasargad_attempt_that_never_returned(self):
        from io import StringIO
        from datetime import timedelta

        from django.core.management import call_command

        _r, attempt = self.start()
        self.pay(attempt)
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(minutes=8))
        out = StringIO()
        call_command("reconcile_platform_payments", stdout=out)           # default min-age is 5 min (Pasargad deadline 25)
        self.assertIn("confirmed=1", out.getvalue())
        self.assertEqual(self.invoice(attempt).status, SubscriptionInvoice.Status.PAID)

    def test_sms_package_via_pasargad_credits_once_with_ledger(self):
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 5})
        package = SmsPackage.objects.create(name="بسته", credit_amount=200, price=80_000)
        purchase = balance_service.request_purchase(store=self.store, package=package)
        attempt, session = sms_svc.start_payment(purchase, callback_base_url="https://rastisi.ir/")
        self.assertEqual(self.fake.calls_to("purchase")[0]["invoice"], f"2{attempt.pk:09d}")   # distinct namespace from subscriptions
        self.fake.paid(amount_rial=800_000)
        for _ in range(3):
            sms_svc.verify_and_fulfill(SmsPackagePaymentAttempt.objects.get(pk=attempt.pk), callback_data={"status": "success"})
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 205)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=purchase).count(), 1)
        self.assertEqual(len(self.fake.calls_to("verify-transactions")), 1)

    def test_refund_uses_the_documented_reverse_endpoint_within_the_deadline(self):
        _r, attempt = self.start()
        self.pay(attempt)
        self.callback(attempt, "status=success")
        invoice = self.invoice(attempt)
        refund = refund_service.request_refund(invoice, amount=invoice.amount_paid, reason="درخواست مشتری", idempotency_key="rf-1")
        self.assertEqual(refund.status, "succeeded")
        self.assertEqual(self.fake.calls_to("reverse-transactions")[0], {"invoice": attempt.provider_session_id, "urlId": self.fake.URL_ID})
        self.assertEqual(self.invoice(attempt).status, SubscriptionInvoice.Status.REFUNDED)
        again = refund_service.request_refund(invoice, amount=invoice.amount_paid, reason="درخواست مشتری", idempotency_key="rf-1")
        self.assertEqual(again.pk, refund.pk)
        self.assertEqual(len(self.fake.calls_to("reverse-transactions")), 1)                     # idempotent
        self.assertTrue(AuditLogEntry.objects.filter(action_code="billing.refund_requested").exists())

    def test_refund_falls_back_to_manual_when_the_provider_refuses_or_amount_is_partial(self):
        _r, attempt = self.start()
        self.pay(attempt)
        self.callback(attempt, "status=success")
        invoice = self.invoice(attempt)
        partial = refund_service.request_refund(invoice, amount=Decimal("1000"), reason="جزئی", idempotency_key="rf-p")
        self.assertEqual(partial.status, "pending")                                              # reverse is full-amount only
        self.assertEqual(self.fake.calls_to("reverse-transactions"), [])
        self.fake.reverse_result = {"resultCode": 13033 + 1}                                     # provider refuses (deadline passed)
        full = refund_service.request_refund(invoice, amount=invoice.amount_paid - Decimal("1000"), reason="کامل", idempotency_key="rf-f")
        self.assertEqual(full.status, "pending")                                                 # honest manual lifecycle
        manual = refund_service.complete_refund_manually(full, actor=self.owner)
        self.assertEqual(manual.status, "succeeded")


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SecureConfigurationTestTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()

    def test_pasargad_test_checks_auth_then_a_non_paying_request_and_stores_no_payment(self):
        fake = patch_pasargad(self)
        ready_platform_pasargad(self)
        result = pgs.run_connection_test("pasargad", callback_base="https://rastisi.ir/")
        self.assertTrue(result.ok)
        self.assertEqual([c[0] for c in fake.calls], ["getToken", "getToken", "purchase"])        # auth check, then dry-run
        self.assertTrue(fake.calls_to("purchase")[0]["invoice"].startswith("9"))                 # test namespace, not an attempt
        self.assertEqual(fake.calls_to("payment-inquiry"), [])
        self.assertEqual(fake.calls_to("verify-transactions"), [])
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), 0)
        self.assertEqual(SmsPackagePaymentAttempt.objects.count(), 0)
        row = PlatformGatewayConfig.objects.get(gateway_code="pasargad")
        self.assertTrue(row.last_test_ok)
        self.assertTrue(pgs.gateway_state("pasargad").last_test_ok)

    def test_zibal_sandbox_test_creates_only_an_unpaid_request(self):
        fake = patch_zibal(self)
        pgs.save_gateway("zibal", credentials={}, sandbox=True, enabled=True)
        result = pgs.run_connection_test("zibal", callback_base="https://rastisi.ir/")
        self.assertTrue(result.ok)
        self.assertEqual([p for p, _ in fake.calls], ["request"])
        self.assertEqual(fake.calls_to("request")[0]["merchant"], "zibal")                       # documented sandbox merchant
        self.assertEqual(fake.calls_to("verify"), [])

    def test_failures_show_a_code_and_a_safe_sentence_never_a_secret(self):
        fake = patch_pasargad(self)
        ready_platform_pasargad(self)
        fake.token_result = {"resultCode": 1, "resultMsg": f"bad creds {SECRET}"}
        result = pgs.run_connection_test("pasargad", callback_base="https://rastisi.ir/")
        self.assertFalse(result.ok)
        self.assertIn("pasargad_1", result.message)
        self.assertNotIn(SECRET, result.message)
        self.assertNotIn(SECRET, repr(result))
        row = PlatformGatewayConfig.objects.get(gateway_code="pasargad")
        self.assertFalse(row.last_test_ok)
        self.assertNotIn(SECRET, row.last_test_message)
        trail = " ".join(f"{e.after_summary} {e.metadata}" for e in PlatformAuditLogEntry.objects.filter(action_code="platform_gateway.tested"))
        self.assertNotIn(SECRET, trail)
        self.assertNotIn(PASARGAD_CREDS["username"], trail)

    def test_callback_domain_rejection_is_reported_with_its_code(self):
        fake = patch_pasargad(self)
        ready_platform_pasargad(self)
        fake.purchase_result = {"resultCode": 13028}
        result = pgs.run_connection_test("pasargad", callback_base="https://rastisi.ir/")
        self.assertFalse(result.ok)
        self.assertIn("13028", result.message)

    def test_changing_credentials_invalidates_the_previous_test_result(self):
        patch_pasargad(self)
        ready_platform_pasargad(self)
        pgs.run_connection_test("pasargad", callback_base="https://rastisi.ir/")
        pgs.save_gateway("pasargad", credentials={"terminalNumber": "000222"}, sandbox=False, enabled=True)
        state = pgs.gateway_state("pasargad")
        self.assertIsNone(state.last_test_ok)

    def test_an_unconfigured_gateway_cannot_be_tested(self):
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.run_connection_test("pasargad", callback_base="https://rastisi.ir/")


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class MerchantAvailabilityTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()

    def test_only_ready_gateways_are_offered_and_the_default_is_marked(self):
        self.assertEqual(pgs.checkout_options(), [])
        ready_platform_zibal(self)
        ready_platform_pasargad(self)
        pgs.save_gateway("zarinpal", credentials={"merchant_id": "c" * 36}, sandbox=False, enabled=False)
        options = pgs.checkout_options()
        self.assertEqual({o["code"] for o in options}, {"zibal", "pasargad"})
        self.assertEqual([o["code"] for o in options if o["is_default"]], ["zibal"])
        for pending in ("snappay", "torobpay", "saman"):
            with self.assertRaises(pgs.PlatformGatewayError):
                pgs.resolve_checkout_provider(pending)


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", RASTISI_BILLING_PROVIDER="manual")
class RenewalAndHistoryTests(TestCase):
    """Renewal invoices are paid through the same platform gateway; history is visible to the owner and the platform."""

    PRICE = Decimal("500000")

    def setUp(self):
        from datetime import timedelta

        from apps.billing.services import renewal_service

        self.addCleanup(cache.clear)
        cache.clear()
        self.store = Store.objects.create(name="فروشگاه تمدید", slug="rn-pay", admin_subdomain="rn-pay")
        plan = Plan.objects.create(code="pl-rn-pay", name="Plan")
        self.version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=self.PRICE, currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY,
        )
        sub = subscription_service.create_subscription(self.store, self.version)
        self.period_end = timezone.now() + timedelta(days=1)
        self.subscription = subscription_service.activate_subscription(sub, period_end=self.period_end)
        renewal_service.generate_renewals(lead_days=3)
        self.invoice = SubscriptionInvoice.objects.get(subscription=self.subscription, kind=SubscriptionInvoice.Kind.RENEWAL)
        self.fake = patch_pasargad(self)
        ready_platform_pasargad(self, default=True)

    def test_a_renewal_invoice_is_paid_through_the_platform_gateway_and_extends_the_period_exactly_once(self):
        attempt, _session = payment_flow_service.start_payment(self.invoice, callback_base_url="https://rastisi.ir/")
        self.fake.paid(amount_rial=int(self.PRICE) * 10)
        before = StoreSubscription.objects.get(pk=self.subscription.pk).current_period_end
        for _ in range(3):
            cache.clear()
            self.client.get(f"/billing/return/{attempt.public_token}/?status=success", HTTP_HOST=_HOST)
        sub = StoreSubscription.objects.get(pk=self.subscription.pk)
        self.assertGreater(sub.current_period_end, before)
        first_extension = sub.current_period_end
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)
        # a duplicate callback / service call must not extend the period again
        payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        self.assertEqual(StoreSubscription.objects.get(pk=self.subscription.pk).current_period_end, first_extension)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, self.PRICE)

    def test_an_overdue_renewal_can_still_be_paid_and_a_failed_attempt_keeps_it_payable(self):
        SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(status=SubscriptionInvoice.Status.PAST_DUE)
        attempt, _s = payment_flow_service.start_payment(SubscriptionInvoice.objects.get(pk=self.invoice.pk), callback_base_url="https://rastisi.ir/")
        cache.clear()
        self.client.get(f"/billing/return/{attempt.public_token}/?status=cancel", HTTP_HOST=_HOST)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertTrue(invoice.is_payable)
        retry, _s2 = payment_flow_service.start_payment(invoice, callback_base_url="https://rastisi.ir/")
        self.assertNotEqual(retry.pk, attempt.pk)                                                 # history kept: new attempt row
        self.fake.paid(amount_rial=int(self.PRICE) * 10)
        payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=retry.pk), callback_data={"status": "success"})
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)
        statuses = sorted(SubscriptionPaymentAttempt.objects.filter(invoice=self.invoice).values_list("status", flat=True))
        self.assertEqual(statuses, ["failed", "succeeded"])                                         # both preserved

    def test_platform_admin_sees_the_attempt_in_transactions_and_invoice_detail(self):
        attempt, _s = payment_flow_service.start_payment(self.invoice, callback_base_url="https://rastisi.ir/")
        su = User.objects.create_user(username="pa-hist@example.com", password="a-very-strong-pass-1", is_staff=True, is_superuser=True)
        self.client.force_login(su)
        with override_settings(ALLOWED_HOSTS=["platformadmins.rastisi.localhost", "testserver"]):
            tx = self.client.get("/payments/transactions/", HTTP_HOST="platformadmins.rastisi.localhost").content.decode()
            detail = self.client.get(f"/payments/invoice/{self.invoice.pk}/", HTTP_HOST="platformadmins.rastisi.localhost").content.decode()
        self.assertIn(self.invoice.number, tx)
        self.assertIn("pasargad", tx)
        self.assertIn(self.invoice.number, detail)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class OwnerDashboardPlatformBillingTests(TestCase):
    """Merchant (store-admin) view of platform billing: invoice + attempt history, SMS purchase history, and the
    gateway chooser (shown only when several platform gateways are ready)."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.user = User.objects.create_user(username="09121250099", password="pass12345", is_staff=True)
        self.store = Store.objects.get(slug="akhlaghi")
        StoreMembership.objects.create(
            store=self.store, user=self.user, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="09121250099", password="pass12345")
        self.fake = patch_pasargad(self)
        ready_platform_pasargad(self, default=True)

    def _invoice(self):
        from apps.billing.services import invoice_service

        plan = Plan.objects.create(code="pl-dash", name="Dash")
        version = PlanVersion.objects.create(
            plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("100000"), currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY,
        )
        sub = (StoreSubscription.objects.filter(store=self.store, is_current=True).first()
               or subscription_service.create_subscription(self.store, version))
        return invoice_service.open_invoice(invoice_service.create_invoice(
            sub, kind=SubscriptionInvoice.Kind.RENEWAL, lines=[invoice_service.plan_line_spec(version)],
        ))

    def test_gateway_chooser_appears_only_when_several_gateways_are_ready_and_lists_only_ready_ones(self):
        invoice = self._invoice()
        one_ready = self.client.get(f"/admin-portal/billing/invoices/{invoice.pk}/").content.decode()
        self.assertIn(f"/admin-portal/billing/invoices/{invoice.pk}/pay/", one_ready)
        self.assertNotIn("<select", one_ready.split('billing/invoices/%d/pay/' % invoice.pk, 1)[1].split("</form>", 1)[0])   # single gateway ⇒ no chooser
        ready_platform_zibal(self)
        two_ready = self.client.get(f"/admin-portal/billing/invoices/{invoice.pk}/").content.decode()
        self.assertIn('name="gateway"', two_ready)
        self.assertIn('value="zibal"', two_ready)
        self.assertIn('value="pasargad"', two_ready)
        self.assertNotIn('value="snappay"', two_ready)
        self.assertNotIn('value="saman"', two_ready)
        self.assertNotIn(SECRET, two_ready)

    def test_paying_an_invoice_from_the_dashboard_goes_through_the_pasargad_referer_interstitial(self):
        invoice = self._invoice()
        response = self.client.post(f"/admin-portal/billing/invoices/{invoice.pk}/pay/", {"gateway": "pasargad"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('<meta name="referrer" content="origin">', response.content.decode())
        self.assertEqual(self.fake.calls_to("purchase")[0]["terminalNumber"], PASARGAD_CREDS["terminalNumber"])

    def test_an_unready_gateway_cannot_be_forced_through_the_pay_form(self):
        invoice = self._invoice()
        before = SubscriptionPaymentAttempt.objects.count()
        response = self.client.post(f"/admin-portal/billing/invoices/{invoice.pk}/pay/", {"gateway": "snappay"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), before)

    def test_sms_purchase_history_lists_status_and_online_attempt(self):
        package = SmsPackage.objects.create(name="بسته تاریخچه", credit_amount=50, price=10_000)
        purchase = balance_service.request_purchase(store=self.store, package=package)
        sms_svc.start_payment(purchase, callback_base_url="https://rastisi.ir/")
        html = self.client.get("/admin-portal/settings/?section=sms").content.decode()
        self.assertIn("sms-purchase-history", html)
        self.assertIn("بسته تاریخچه", html)
        self.assertNotIn(SECRET, html)


_PA_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_PA_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class PlatformAdminGatewayUiTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.su = User.objects.create_user(username="pa-ui@example.com", password="a-very-strong-pass-1", is_staff=True, is_superuser=True)
        self.client.force_login(self.su)

    def get(self):
        return self.client.get("/payments/gateways/", HTTP_HOST=_PA_HOST).content.decode()

    def post(self, data, follow=False):
        return self.client.post("/payments/gateways/", data, HTTP_HOST=_PA_HOST, follow=follow)

    def test_page_shows_every_status_class_with_its_own_label_and_no_generic_unavailable_text(self):
        html = self.get()
        for status in ("missing_credentials", "not_implemented"):
            self.assertIn(f'data-status="{status}"', html, status)
        for code in ("pasargad", "zibal", "zarinpal", "snappay", "torobpay", "saman", "parsian", "mellat", "sadad", "tejarat", "platform_card"):
            self.assertIn(f'id="gw-{code}"', html, code)
        self.assertNotIn('id="gw-cod"', html)
        self.assertNotIn('id="gw-card_to_card"', html)
        self.assertNotIn("غیرقابل‌استفاده برای پلتفرم", html)                    # the old one-size-fits-all label is gone
        self.assertIn("SaaS", html)                                              # BNPL blocker is specific
        self.assertIn("IP", html)                                                # Pasargad prerequisites are shown
        self.assertIn("راهنمای راه‌اندازی", html)

    def test_pasargad_can_be_configured_enabled_tested_and_made_default_from_the_ui(self):
        fake = patch_pasargad(self)
        self.post({"action": "save", "gateway_code": "pasargad", "is_enabled": "on", "display_order": "1",
                   **{f"cred_{k}": v for k, v in PASARGAD_CREDS.items()}})
        self.assertEqual(pgs.gateway_state("pasargad").status, pgs.READY)
        html = self.get()
        self.assertNotIn(SECRET, html)
        self.assertNotIn(PASARGAD_CREDS["username"], html)
        followed = self.post({"action": "test", "gateway_code": "pasargad"}, follow=True)
        self.assertContains(followed, "تستِ پیکربندی")
        self.assertIn("تست موفق", self.get())
        self.post({"action": "set_default", "gateway_code": "pasargad"})
        self.assertEqual(pgs.default_code(), "pasargad")
        self.assertEqual(SubscriptionPaymentAttempt.objects.count(), 0)
        self.assertEqual(fake.calls_to("verify-transactions"), [])

    def test_default_select_disables_unready_gateways_and_the_server_refuses_forged_defaults(self):
        html = self.get()
        self.assertIn('id="default-gateway"', html)
        for code in ("zibal", "zarinpal", "pasargad"):
            segment = html.split(f'<option value="{code}"', 1)[1].split(">", 1)[0]
            self.assertIn("disabled", segment, code)
        segment = html.split('<option value="snappay"', 1)[1].split(">", 1)[0]
        self.assertIn("disabled", segment)                                       # configured-or-not, a gated BNPL is never selectable
        self.assertNotIn('<option value="platform_card"', html)                  # manual methods are never the online default
        self.assertNotIn('<option value="parsian"', html)
        self.post({"action": "set_default", "gateway_code": "snappay"})
        self.post({"action": "set_default", "gateway_code": "pasargad"})
        self.assertEqual(pgs.default_code(), "manual")
        ready_platform_pasargad(self)
        segment = self.get().split('<option value="pasargad"', 1)[1].split(">", 1)[0]
        self.assertNotIn("disabled", segment)

    def test_test_button_failure_is_reported_without_secrets_and_audited(self):
        fake = patch_pasargad(self)
        ready_platform_pasargad(self)
        fake.token_result = {"resultCode": 401, "resultMsg": f"denied {SECRET}"}
        response = self.post({"action": "test", "gateway_code": "pasargad"}, follow=True)
        body = response.content.decode()
        self.assertNotIn(SECRET, body)
        self.assertIn("تست ناموفق", self.get())
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="platform_gateway.tested").exists())

    def test_testing_a_blocked_or_unconfigured_gateway_is_refused(self):
        patch_pasargad(self)
        for code in ("snappay", "saman", "pasargad"):
            response = self.post({"action": "test", "gateway_code": code}, follow=True)
            self.assertEqual(response.status_code, 200, code)
        self.assertFalse(PlatformGatewayConfig.objects.exists())


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", RASTISI_BILLING_PROVIDER="manual")
class ZibalSandboxModeFlowTests(TestCase):
    """The one provider whose official docs describe a sandbox: Zibal's fixed `zibal` merchant. Mocked here; the real
    sandbox run is part of the Windows QA procedure."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.fake = patch_zibal(self)
        pgs.save_gateway("zibal", credentials={}, sandbox=True, enabled=True)
        pgs.set_default("zibal")
        cache.clear()
        self.store = Store.objects.create(name="فروشگاه سندباکس", slug="sbx-store", admin_subdomain="sbx-store")
        _sub, self.invoice = open_invoice_for(self.store, code="sbx", price="100000")

    def test_sandbox_mode_needs_no_merchant_uses_the_documented_sandbox_merchant_and_fulfils_once(self):
        state = pgs.gateway_state("zibal")
        self.assertEqual((state.status, state.sandbox), (pgs.READY, True))
        attempt, session = payment_flow_service.start_payment(self.invoice, callback_base_url="https://rastisi.ir/")
        sent = self.fake.calls_to("request")[0]
        self.assertEqual(sent["merchant"], "zibal")
        self.assertNotEqual(sent["merchant"], STORE_MERCHANT)
        self.fake.paid(amount_rial=1_000_000, order_id=attempt.public_token)
        for _ in range(2):
            payment_flow_service.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, Decimal("100000"))
        self.assertEqual({p["merchant"] for p in self.fake.calls_to("verify")}, {"zibal"})
