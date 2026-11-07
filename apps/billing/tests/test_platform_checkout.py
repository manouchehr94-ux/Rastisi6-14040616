"""Unified merchant checkout for platform purchases (subscription invoice + SMS package) — acceptance matrix over real HTTP.

Everything is synthetic: in-process fake gateways (no network), dummy credentials, throw-away receipt storage. Each
scenario runs for BOTH products through the same page/URLs. Money-moving behaviour is asserted from the database
(``amount_paid`` / ledger rows / claim state), never from page text alone."""

import threading
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import (
    PlatformManualPaymentClaim as Claim, SubscriptionInvoice, SubscriptionPaymentAttempt,
)
from apps.billing.services import manual_card_service as mcs
from apps.billing.services import payment_flow_service, platform_checkout_service as pcs, sms_purchase_payment_service
from apps.billing.tests.platform_payment_support import (
    STORE_MERCHANT, open_invoice_for, patch_zibal, ready_platform_zarinpal, ready_platform_zibal,
)
from apps.billing.tests.test_platform_card_to_card import enable_platform_card, upload, use_private_tmp
from apps.billing.tests.test_platform_gated_providers import CREDS as GATED_CREDS, REF
from apps.orders.models import PaymentGatewayConfig
from apps.portal.services import platform_gateway_matrix as matrix
from apps.portal.services import platform_gateway_service as pgs
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePaymentAttempt, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
SUB, SMS = "subscription", "sms"
KINDS = (SUB, SMS)
OWNER_HOST = f"pcout.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
OTHER_HOST = f"pcother.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
PLATFORM_HOST = "platformadmins.rastisi.localhost"
SUB_PRICE, SMS_PRICE, SMS_CREDITS = 300_000, 150_000, 500


UP_HOST = f"pcup.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
PORTAL_HOST = "rastisi.localhost"
FREE_HOST = f"pcfree.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[OWNER_HOST, OTHER_HOST, UP_HOST, FREE_HOST, PLATFORM_HOST, PORTAL_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class CheckoutBase(TestCase):
    def setUp(self):
        use_private_tmp(self)
        self.addCleanup(cache.clear)
        cache.clear()
        self.store = Store.objects.create(name="فروشگاه تسویه", slug="pcout", admin_subdomain="pcout", status=Store.Status.ACTIVE)
        self.other = Store.objects.create(name="فروشگاه دیگر", slug="pcother", admin_subdomain="pcother", status=Store.Status.ACTIVE)
        self.owner = self._member(self.store, "pcout-owner")
        self.other_owner = self._member(self.other, "pcother-owner")
        self.finance = User.objects.create_user(username="pcout-fin@example.com", password="pass12345", is_staff=True, is_superuser=True)
        self.sub, self.invoice = open_invoice_for(self.store, code="pcout", price=str(SUB_PRICE))
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        SmsBalance.objects.update_or_create(store=self.other, defaults={"credits": 100})
        self.package = SmsPackage.objects.create(name="بسته تسویه", credit_amount=SMS_CREDITS, price=SMS_PRICE)
        self.purchase = balance_service.request_purchase(store=self.store, package=self.package)
        self.foreign_purchase = balance_service.request_purchase(store=self.other, package=self.package)
        self.fake = patch_zibal(self)
        self.owner_client = Client(HTTP_HOST=OWNER_HOST)
        self.owner_client.login(username="pcout-owner", password="pass12345")
        self.other_client = Client(HTTP_HOST=OTHER_HOST)
        self.other_client.login(username="pcother-owner", password="pass12345")
        self.admin_client = Client(HTTP_HOST=PLATFORM_HOST)
        self.admin_client.force_login(self.finance)

    def _member(self, store, username):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=store, user=user, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        return user

    # ---- per-product helpers
    def target(self, kind):
        return self.invoice if kind == SUB else self.purchase

    def price(self, kind):
        return SUB_PRICE if kind == SUB else SMS_PRICE

    def url(self, kind, action=""):
        name = {"": "platform-checkout", "pay": "platform-checkout-pay", "status": "platform-checkout-status"}[action]
        return reverse(f"dashboard:{name}", args=[kind, self.target(kind).pk])

    def page(self, kind, client=None):
        return (client or self.owner_client).get(self.url(kind))

    def pay(self, kind, method=None, client=None, **extra):
        data = dict(extra)
        if method is not None:
            data["method"] = method
        return (client or self.owner_client).post(self.url(kind, "pay"), data)

    def attempts(self, kind):
        model = SubscriptionPaymentAttempt if kind == SUB else SmsPackagePaymentAttempt
        return model.objects.filter(invoice=self.invoice) if kind == SUB else model.objects.filter(purchase=self.purchase)

    def claims(self, kind):
        return Claim.objects.filter(invoice=self.invoice) if kind == SUB else Claim.objects.filter(sms_purchase=self.purchase)

    def effect_count(self, kind):
        """How many times the purchase effect was applied (0 or 1 by design)."""
        if kind == SUB:
            return int(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid > 0)
        return SmsCreditLedger.objects.filter(purchase=self.purchase).count()

    def paid_now(self, kind):
        if kind == SUB:
            return SubscriptionInvoice.objects.get(pk=self.invoice.pk).status == SubscriptionInvoice.Status.PAID
        return SmsPackagePurchase.objects.get(pk=self.purchase.pk).status == SmsPackagePurchase.Status.COMPLETED

    def credits(self):
        return SmsBalance.objects.get(store=self.store).credits

    def callback(self, attempt, query="success=1&status=2&trackId=777"):
        cache.clear()
        return Client().get(f"/billing/return/{attempt.public_token}/?{query}")

    def mark_paid(self, attempt, kind):
        self.fake.paid(amount_rial=self.price(kind) * 10, order_id=attempt.public_token)

    def start_online(self, kind):
        ready_platform_zibal(self)
        response = self.pay(kind, "zibal")
        return response, self.attempts(kind).get()


class MethodVisibilityTests(CheckoutBase):
    def test_no_method_ready_shows_an_honest_page_with_no_way_to_pay_and_creates_nothing(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.page(kind).content.decode()
                self.assertIn('data-testid="no-method"', html)
                self.assertNotIn('name="method"', html)
                self.assertEqual(self.pay(kind, "zibal").status_code, 302)
                self.assertEqual(self.pay(kind).status_code, 302)
                self.assertEqual((self.attempts(kind).count(), self.claims(kind).count()), (0, 0))

    def test_only_online_ready_lists_just_that_gateway(self):
        ready_platform_zibal(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.page(kind).content.decode()
                self.assertEqual(html.count('name="method"'), 1)
                self.assertIn('value="zibal"', html)
                self.assertNotIn('value="platform_card"', html)

    def test_only_card_to_card_ready_lists_just_the_card_and_choosing_it_goes_to_the_claim_form(self):
        enable_platform_card(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.page(kind).content.decode()
                self.assertEqual(html.count('name="method"'), 1)
                self.assertIn('value="platform_card"', html)
                response = self.pay(kind, "platform_card")
                claim_url = reverse("dashboard:billing-card-claim" if kind == SUB else "dashboard:sms-purchase-card-claim", args=[self.target(kind).pk])
                self.assertRedirects(response, claim_url, fetch_redirect_response=False)
                self.assertEqual(self.claims(kind).count(), 0)                    # choosing creates no claim

    def test_both_ready_lists_both_methods_with_the_online_default_preselected(self):
        ready_platform_zibal(self)
        enable_platform_card(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.page(kind).content.decode()
                self.assertEqual(html.count('name="method"'), 2)
                self.assertRegex(html, r'value="zibal"\s+checked')
                self.assertIn('value="platform_card"', html)

    def test_disabled_incomplete_gated_and_unimplemented_methods_never_appear_and_cannot_be_posted(self):
        ready_platform_zibal(self)
        ready_platform_zarinpal(self)
        pgs.save_gateway("zarinpal", credentials={"merchant_id": ""}, sandbox=False, enabled=False)                  # disabled
        pgs.save_gateway("mellat", credentials=dict(GATED_CREDS["mellat"]), sandbox=False, enabled=True,
                         purchase_types=["subscription", "sms_package"])                                              # creds, NO gates
        pgs.save_gateway("saman", credentials={}, sandbox=False, enabled=False)                                       # incomplete
        cache.clear()
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.page(kind).content.decode()
                for code in ("zarinpal", "mellat", "saman", "parsian", "sadad", "tejarat", "snappay", "torobpay", "platform_card"):
                    self.assertNotIn(f'value="{code}"', html, code)
                for code in ("zarinpal", "mellat", "saman", "parsian", "snappay", "platform_card", "manual", "<script>"):
                    self.pay(kind, code)
                self.assertEqual((self.attempts(kind).count(), self.claims(kind).count()), (0, 0))
                self.assertEqual(self.fake.calls_to("request"), [])

    def test_mellat_appears_for_both_products_only_after_credentials_and_both_contract_gates(self):
        pgs.save_gateway("mellat", credentials=dict(GATED_CREDS["mellat"]), sandbox=False, enabled=True,
                         purchase_types=["subscription", "sms_package"])
        cache.clear()
        for kind in KINDS:
            self.assertNotIn('value="mellat"', self.page(kind).content.decode())
        pgs.record_attestation("mellat", matrix.GATE_CONTRACT_VERIFICATION, reference=REF, actor=self.finance)
        cache.clear()
        for kind in KINDS:
            self.assertNotIn('value="mellat"', self.page(kind).content.decode())                                 # one gate is not enough
        pgs.record_attestation("mellat", matrix.GATE_LIVE_VERIFICATION, reference=REF, actor=self.finance)
        cache.clear()
        for kind in KINDS:
            self.assertIn('value="mellat"', self.page(kind).content.decode())
        pgs.record_attestation("mellat", matrix.GATE_LIVE_VERIFICATION, reference="", actor=self.finance, revoke=True)
        cache.clear()
        for kind in KINDS:
            self.assertNotIn('value="mellat"', self.page(kind).content.decode())                                 # revoking withdraws it again

    def test_mellat_and_card_together_are_both_offered_when_both_are_truly_ready(self):
        pgs.save_gateway("mellat", credentials=dict(GATED_CREDS["mellat"]), sandbox=False, enabled=True,
                         purchase_types=["subscription", "sms_package"])
        for gate in matrix.facts_for("mellat").gates:
            pgs.record_attestation("mellat", gate, reference=REF, actor=self.finance)
        enable_platform_card(self)
        for kind in KINDS:
            html = self.page(kind).content.decode()
            self.assertIn('value="mellat"', html)
            self.assertIn('value="platform_card"', html)

    def test_a_purchase_type_not_allowed_for_a_method_hides_it_only_for_that_product(self):
        enable_platform_card(self, types=("subscription",))
        self.assertIn('value="platform_card"', self.page(SUB).content.decode())
        self.assertNotIn('value="platform_card"', self.page(SMS).content.decode())
        self.assertNotIn("<form method=\"post\" action=\"" + self.url(SMS, "pay"), self.page(SMS).content.decode())

    def test_the_stores_own_gateways_never_leak_into_platform_checkout(self):
        cfg = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal", is_active=True)
        cfg.set_credentials({"merchant": STORE_MERCHANT})
        cfg.save()
        for kind in KINDS:
            html = self.page(kind).content.decode()
            self.assertIn('data-testid="no-method"', html)
            self.assertNotIn(STORE_MERCHANT, html)


class PageContentTests(CheckoutBase):
    def test_the_portal_handoff_path_equals_the_dashboard_route(self):
        for kind in (SUB, SMS):
            self.assertEqual(pcs.checkout_path(kind, 17), reverse("dashboard:platform-checkout", args=[kind, 17]))

    def test_summary_shows_the_server_amount_the_product_and_never_the_platform_admin_shell(self):
        ready_platform_zibal(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                response = self.page(kind)
                html = response.content.decode()
                self.assertEqual(response.status_code, 200)
                self.assertIn("data-testid=\"payable-amount\"", html)
                self.assertIn("۳۰۰٬۰۰۰" if kind == SUB else "۱۵۰٬۰۰۰", html)
                self.assertIn("بسته" if kind == SMS else "اشتراک", html)
                self.assertNotIn("pa-shell", html)                      # the Platform Owner Admin shell is not used
                self.assertNotIn("/payments/gateways/", html)
                self.assertNotIn('name="amount"', html)

    def test_credentials_never_appear_in_the_checkout_html(self):
        ready_platform_zibal(self, merchant="SECRET-MERCHANT-NEVER-SHOWN")
        enable_platform_card(self)
        for kind in KINDS:
            self.assertNotIn("SECRET-MERCHANT-NEVER-SHOWN", self.page(kind).content.decode())

    def test_the_browser_cannot_change_the_amount_or_the_target(self):
        ready_platform_zibal(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.owner_client.post(self.url(kind, "pay"), {"method": "zibal", "amount": "1", "price": "1", "invoice": "999", "store": self.other.pk})
                attempt = self.attempts(kind).get()
                self.assertEqual(int(attempt.amount), self.price(kind))
                self.assertEqual(attempt.store_id, self.store.pk)
                sent = self.fake.calls_to("request")[-1]
                self.assertEqual(sent["amount"], self.price(kind) * 10)           # toman → rial happens server-side only
                self.fake.calls.clear()


class CrossTenantTests(CheckoutBase):
    def test_another_stores_owner_gets_404_for_page_pay_and_status(self):
        ready_platform_zibal(self)
        enable_platform_card(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(self.page(kind, self.other_client).status_code, 404)
                self.assertEqual(self.pay(kind, "zibal", client=self.other_client).status_code, 404)
                self.assertEqual(self.pay(kind, "platform_card", client=self.other_client).status_code, 404)
                self.assertEqual(self.other_client.post(self.url(kind, "status")).status_code, 404)
                self.assertEqual((self.attempts(kind).count(), self.claims(kind).count()), (0, 0))

    def test_anonymous_visitors_are_sent_to_login_and_unknown_kinds_are_404(self):
        for kind in KINDS:
            response = Client(HTTP_HOST=OWNER_HOST).get(self.url(kind))
            self.assertEqual(response.status_code, 302)
            self.assertNotIn(self.url(kind), response["Location"].split("?")[0])
        self.assertEqual(self.owner_client.get(f"/admin-portal/billing/checkout/bogus/{self.invoice.pk}/").status_code, 404)

    def test_a_member_without_the_billing_or_sms_permission_is_denied(self):
        ready_platform_zibal(self)
        viewer = User.objects.create_user(username="pcout-viewer", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=viewer, role=StoreMembership.Role.ANALYST,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        client = Client(HTTP_HOST=OWNER_HOST)
        client.login(username="pcout-viewer", password="pass12345")
        for kind in KINDS:
            self.assertEqual(client.get(self.url(kind)).status_code, 403)
            self.assertEqual(client.post(self.url(kind, "pay"), {"method": "zibal"}).status_code, 403)
        self.assertEqual((self.attempts(SUB).count(), self.attempts(SMS).count()), (0, 0))


class OnlineFlowTests(CheckoutBase):
    def test_pay_redirects_to_the_gateway_and_returns_to_the_checkout_page_and_applies_nothing_yet(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                ready_platform_zibal(self)
                self.fake.calls.clear()
                response = self.pay(kind, "zibal")
                self.assertEqual((response.status_code, response["Location"]), (302, "https://gateway.zibal.ir/start/777"))
                attempt = self.attempts(kind).latest("pk")
                self.assertEqual((attempt.provider, int(attempt.amount), attempt.currency), ("zibal", self.price(kind), "IRT"))
                self.assertTrue(attempt.return_to.endswith(self.url(kind)))
                self.assertEqual(self.effect_count(kind), 0)
                self.assertFalse(self.paid_now(kind))
                self.assertContains(self.page(kind), 'data-state="verifying"')

    def test_return_from_the_bank_page_is_not_proof_and_only_the_server_verify_applies_it_exactly_once(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.fake.verify_payload = {"result": 202, "message": "not paid"}
                _r, attempt = self.start_online(kind) if kind == SUB else (None, self._sms_attempt())
                response = self.callback(attempt)                              # browser says success, gateway verify says "not paid"
                self.assertTrue(response["Location"].endswith("payment=pending"))
                self.assertEqual(self.effect_count(kind), 0)
                self.assertContains(self.page(kind), 'data-state="verifying"')
                self.mark_paid(attempt, kind)
                for _ in range(3):                                             # replayed callbacks
                    self.callback(attempt)
                self.assertTrue(self.paid_now(kind))
                self.assertEqual(self.effect_count(kind), 1)
                final = self.page(kind).content.decode()
                self.assertIn('data-state="paid"', final)
                self.assertIn("مبلغِ پرداخت‌شده", final)                      # shows what was paid, never «۰ تومان»
                self.assertIn("۳۰۰٬۰۰۰" if kind == SUB else "۱۵۰٬۰۰۰", final)
        self.assertEqual(self.credits(), 100 + SMS_CREDITS)

    def _sms_attempt(self):
        ready_platform_zibal(self)
        self.pay(SMS, "zibal")
        return self.attempts(SMS).get()

    def test_subscription_is_activated_and_extended_exactly_once_after_verified_payment(self):
        _r, attempt = self.start_online(SUB)
        self.mark_paid(attempt, SUB)
        self.callback(attempt)
        self.callback(attempt)
        sub = StoreSubscription.objects.get(pk=self.sub.pk)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, SUB_PRICE))
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(len(self.fake.calls_to("verify")), 1, "a final attempt never hits the gateway again")

    def test_paying_again_while_an_attempt_is_unverified_needs_an_explicit_acknowledgement(self):
        ready_platform_zibal(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.pay(kind, "zibal")
                self.assertEqual(self.attempts(kind).count(), 1)
                html = self.page(kind).content.decode()
                self.assertIn('data-state="verifying"', html)
                self.assertIn('data-testid="check-status"', html)
                self.assertIn('name="ack"', html)
                self.fake.track_id += 1
                self.pay(kind, "zibal")                                       # no acknowledgement ⇒ refused
                self.assertEqual(self.attempts(kind).count(), 1)
                self.pay(kind, "zibal", ack="1")                              # merchant says the first one was not completed
                self.assertEqual(self.attempts(kind).count(), 2)
                self.assertEqual(self.effect_count(kind), 0)

    def test_declined_payment_shows_failure_and_can_be_retried_as_a_new_attempt(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                ready_platform_zibal(self)
                self.pay(kind, "zibal")
                attempt = self.attempts(kind).latest("pk")
                response = self.callback(attempt, "success=0&status=3&trackId=777")
                self.assertTrue(response["Location"].endswith("payment=failed"))
                html = self.page(kind).content.decode()
                self.assertIn('data-state="failed"', html)
                self.assertIn('name="method"', html)                           # retry possible
                self.assertEqual(self.effect_count(kind), 0)
                self.fake.track_id += 1
                self.pay(kind, "zibal")
                self.assertEqual(self.attempts(kind).count(), 2)

    def test_a_wrong_amount_from_the_gateway_is_flagged_never_fulfilled_and_blocks_a_blind_retry(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                ready_platform_zibal(self)
                self.pay(kind, "zibal")
                attempt = self.attempts(kind).latest("pk")
                self.fake.paid(amount_rial=1000, order_id=attempt.public_token)
                self.callback(attempt)
                self.assertEqual(self.effect_count(kind), 0)
                self.assertFalse(self.paid_now(kind))
                html = self.page(kind).content.decode()
                self.assertIn('data-state="needs_action"', html)
                self.assertNotIn('name="method"', html)                         # no second payment on top of an unreconciled one

    def test_a_pending_attempt_older_than_the_window_allows_retry_and_a_late_payment_is_still_honoured(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                ready_platform_zibal(self)
                self.pay(kind, "zibal")
                attempt = self.attempts(kind).latest("pk")
                type(attempt).objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=2))
                html = self.page(kind).content.decode()
                self.assertIn('data-state="failed"', html)
                self.assertIn('name="method"', html)
                self.mark_paid(attempt, kind)
                self.owner_client.post(self.url(kind, "status"))
                self.assertTrue(self.paid_now(kind))
                self.assertEqual(self.effect_count(kind), 1)

    def test_the_status_button_runs_the_server_verify_and_a_forged_query_string_does_nothing(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                ready_platform_zibal(self)
                self.pay(kind, "zibal")
                attempt = self.attempts(kind).latest("pk")
                self.owner_client.get(self.url(kind) + "?payment=ok&status=paid&success=1")
                self.assertFalse(self.paid_now(kind))
                self.assertContains(self.page(kind), 'data-state="verifying"')
                cache.clear()
                self.owner_client.post(self.url(kind, "status"))
                self.assertFalse(self.paid_now(kind))                           # gateway says not paid
                self.mark_paid(attempt, kind)
                cache.clear()
                self.owner_client.post(self.url(kind, "status"))
                self.assertTrue(self.paid_now(kind))

    def test_a_paid_purchase_cannot_be_paid_again_and_a_closed_one_offers_nothing(self):
        ready_platform_zibal(self)
        enable_platform_card(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.pay(kind, "zibal")
                attempt = self.attempts(kind).latest("pk")
                self.mark_paid(attempt, kind)
                self.callback(attempt)
                before = (self.attempts(kind).count(), self.claims(kind).count())
                self.assertContains(self.page(kind), 'data-state="paid"')
                self.assertNotContains(self.page(kind), 'name="method"')
                self.pay(kind, "zibal")
                self.pay(kind, "platform_card")
                self.assertEqual((self.attempts(kind).count(), self.claims(kind).count()), before)

    def test_a_voided_invoice_and_a_cancelled_purchase_are_closed(self):
        ready_platform_zibal(self)
        SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(status=SubscriptionInvoice.Status.VOID)
        SmsPackagePurchase.objects.filter(pk=self.purchase.pk).update(status=SmsPackagePurchase.Status.CANCELED)
        for kind in KINDS:
            self.assertContains(self.page(kind), 'data-state="closed"')
            self.pay(kind, "zibal")
            self.assertEqual(self.attempts(kind).count(), 0)

    def test_a_gateway_outage_gives_a_message_and_a_failed_attempt_not_a_crash(self):
        import requests

        ready_platform_zibal(self)
        with mock.patch("apps.billing.providers.zibal.requests.post", side_effect=requests.Timeout()):
            for kind in KINDS:
                response = self.pay(kind, "zibal")
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].endswith(self.url(kind)))
                self.assertEqual(self.attempts(kind).get().status, "failed")
                self.assertEqual(self.effect_count(kind), 0)
                html = self.page(kind).content.decode()
                self.assertIn('data-state="failed"', html)
                self.assertIn('name="method"', html)                            # safe retry

    def test_failed_fulfilment_leaves_the_purchase_open_and_the_next_verification_recovers_it_once(self):
        _r, sub_attempt = self.start_online(SUB)
        self.mark_paid(sub_attempt, SUB)
        with mock.patch("apps.billing.services.confirmation_service._activate_or_renew", side_effect=RuntimeError("boom")):
            self.callback(sub_attempt)                                          # the bank return must never be a 500
        self.assertEqual(self.effect_count(SUB), 0)
        self.assertFalse(self.paid_now(SUB))
        self.callback(sub_attempt)                                              # recovery: same authoritative verify, now succeeds
        self.assertTrue(self.paid_now(SUB))
        self.assertEqual(self.effect_count(SUB), 1)
        self.callback(sub_attempt)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, SUB_PRICE)

        sms_attempt = self._sms_attempt()
        self.mark_paid(sms_attempt, SMS)
        with mock.patch.object(balance_service, "complete_purchase", side_effect=RuntimeError("boom")):
            self.callback(sms_attempt)
        self.assertEqual(self.credits(), 100)
        self.assertFalse(self.paid_now(SMS))
        self.callback(sms_attempt)
        self.callback(sms_attempt)
        self.assertEqual(self.credits(), 100 + SMS_CREDITS)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=self.purchase).count(), 1)


class ManualCardToCardTests(CheckoutBase):
    def setUp(self):
        super().setUp()
        enable_platform_card(self)

    def claim_url(self, kind):
        return reverse("dashboard:billing-card-claim" if kind == SUB else "dashboard:sms-purchase-card-claim", args=[self.target(kind).pk])

    def submit(self, kind, reference="PCO-TRK-445566", **extra):
        data = {"reference": reference, "transferred_at": timezone.localtime(timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "payer_card_last4": "4321", "receipt": upload()}
        data.update(extra)
        return self.owner_client.post(self.claim_url(kind), data)

    def review(self, claim, action, **data):
        return self.admin_client.post(f"/payments/card-claims/{claim.pk}/{action}/", data)

    def test_the_claim_page_shows_only_the_platform_account_the_exact_amount_and_the_way_back(self):
        PaymentGatewayConfig.objects.create(store=self.store, gateway_code="card_to_card", is_active=True)
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.owner_client.get(self.claim_url(kind)).content.decode()
                self.assertIn("6037 9970 0000 0019", html)
                self.assertIn("۳۰۰٬۰۰۰" if kind == SUB else "۱۵۰٬۰۰۰", html)
                self.assertNotIn('name="amount"', html)
                self.assertIn(self.url(kind), html)                              # back link returns to the unified checkout

    def test_a_submitted_claim_is_pending_with_a_clear_status_page_and_applies_nothing(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                response = self.submit(kind, reference=f"PCO-TRK-{kind}-1")
                self.assertRedirects(response, self.url(kind), fetch_redirect_response=False)
                claim = self.claims(kind).get()
                self.assertEqual(claim.status, Claim.Status.PENDING_REVIEW)
                html = self.page(kind).content.decode()
                self.assertIn('data-state="pending_review"', html)
                self.assertIn(f"PCO-TRK-{kind}-1", html)
                self.assertNotIn('name="method"', html)                          # cannot pay twice while pending
                self.assertEqual(self.effect_count(kind), 0)
                self.assertFalse(self.paid_now(kind))
                before = self.claims(kind).count()
                self.pay(kind, "platform_card")
                self.submit(kind, reference=f"PCO-TRK-{kind}-2")
                self.assertEqual(self.claims(kind).count(), before)              # one active claim per target

    def test_finance_approval_fulfils_exactly_once_and_a_duplicate_approval_is_idempotent(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.submit(kind, reference=f"PCO-APP-{kind}")
                claim = self.claims(kind).get()
                amount = str(self.price(kind))
                self.review(claim, "approve", bank_reference=f"BANK-{kind}-0001", confirmed_amount=amount)
                self.review(claim, "approve", bank_reference=f"BANK-{kind}-0001", confirmed_amount=amount)
                self.assertTrue(self.paid_now(kind))
                self.assertEqual(self.effect_count(kind), 1)
                final = self.page(kind).content.decode()
                self.assertIn('data-state="paid"', final)
                self.assertIn("مبلغِ پرداخت‌شده", final)                      # shows what was paid, never «۰ تومان»
                self.assertIn("۳۰۰٬۰۰۰" if kind == SUB else "۱۵۰٬۰۰۰", final)
        self.assertEqual(self.credits(), 100 + SMS_CREDITS)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=self.purchase).count(), 1)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, SUB_PRICE)

    def test_rejection_shows_the_reason_and_the_merchant_can_try_again(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.submit(kind, reference=f"PCO-REJ-{kind}")
                claim = self.claims(kind).get()
                self.review(claim, "reject", reason="رسید با صورتحساب نمی‌خواند")
                html = self.page(kind).content.decode()
                self.assertIn('data-state="failed"', html)
                self.assertIn("رسید با صورتحساب نمی‌خواند", html)
                self.assertIn('name="method"', html)
                self.assertEqual(self.effect_count(kind), 0)
                self.submit(kind, reference=f"PCO-REJ-{kind}-B")
                self.assertEqual(self.claims(kind).filter(status=Claim.Status.PENDING_REVIEW).count(), 1)

    def test_the_merchant_can_cancel_a_pending_claim_and_is_returned_to_the_checkout_page(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.submit(kind, reference=f"PCO-CAN-{kind}")
                claim = self.claims(kind).get()
                response = self.owner_client.post(reverse("dashboard:billing-card-claim-cancel", args=[claim.pk]))
                self.assertRedirects(response, self.url(kind), fetch_redirect_response=False)
                claim.refresh_from_db()
                self.assertEqual(claim.status, Claim.Status.CANCELLED)

    def test_self_approval_is_blocked_the_receipt_alone_never_fulfils_and_non_finance_cannot_review(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.submit(kind, reference=f"PCO-SELF-{kind}")
                claim = self.claims(kind).get()
                response = self.owner_client.post(f"/payments/card-claims/{claim.pk}/approve/",
                                                  {"bank_reference": "BANK-SELF", "confirmed_amount": str(self.price(kind))}, HTTP_HOST=PLATFORM_HOST)
                self.assertNotEqual(response.status_code, 200)
                with self.assertRaises(mcs.ClaimError):
                    mcs.approve_claim(claim, reviewer=self.owner, bank_confirmation_reference="BANK-SELF", confirmed_amount=self.price(kind))
                self.assertEqual(self.effect_count(kind), 0)

    def test_a_wrong_confirmed_amount_never_fulfils(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.submit(kind, reference=f"PCO-AMT-{kind}")
                claim = self.claims(kind).get()
                self.review(claim, "approve", bank_reference=f"BANK-AMT-{kind}", confirmed_amount="1000")
                self.assertEqual(self.effect_count(kind), 0)
                self.assertEqual(Claim.objects.get(pk=claim.pk).status, Claim.Status.PENDING_REVIEW)

    def test_an_expired_claim_frees_the_merchant_to_retry_without_any_effect(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.submit(kind, reference=f"PCO-EXP-{kind}")
                claim = self.claims(kind).get()
                Claim.objects.filter(pk=claim.pk).update(expires_at=timezone.now() - timedelta(days=1))
                mcs.expire_stale_claims()
                html = self.page(kind).content.decode()
                self.assertIn('data-state="failed"', html)
                self.assertEqual(self.effect_count(kind), 0)


class PlanChangeThroughCheckoutTests(CheckoutBase):
    """Existing active subscription → upgrade (with a billing interval) → unified checkout → verified payment → plan switched."""

    def setUp(self):
        super().setUp()
        from apps.subscriptions.services import subscription_service as ss
        from apps.subscriptions.tests.test_pricing_dynamic import make_plan

        _p1, self.v1 = make_plan("pcup-low", base=100000, order=1, limits={"catalog.products": 5})
        _p2, self.v2 = make_plan("pcup-high", base=300000, order=2, extra={"yearly": 3000000}, limits={"catalog.products": 50})
        self.store2 = Store.objects.create(name="ارتقا", slug="pcup", admin_subdomain="pcup", status=Store.Status.ACTIVE)
        self.owner2 = self._member(self.store2, "pcup-owner")
        self.sub2 = ss.activate_subscription(ss.create_subscription(self.store2, self.v1), period_end=timezone.now() + timedelta(days=20))
        self.client2 = Client(HTTP_HOST=UP_HOST)
        self.client2.login(username="pcup-owner", password="pass12345")

    def preview_token(self, interval="yearly"):
        response = self.client2.post("/admin-portal/subscription/plans/preview/", {"version_id": self.v2.pk, "billing_interval": interval})
        return response.context["preview"]["token"]

    def execute(self, interval="yearly"):
        return self.client2.post("/admin-portal/subscription/plans/change/", {
            "version_id": self.v2.pk, "preview_token": self.preview_token(interval), "billing_interval": interval})

    def test_no_ready_method_creates_no_dead_invoice_and_says_why(self):
        response = self.execute()
        self.assertRedirects(response, reverse("dashboard:subscription-plans") + "?interval=yearly", fetch_redirect_response=False)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2).count(), 0)

    def test_upgrade_lands_on_the_unified_checkout_pays_online_and_preserves_the_interval(self):
        from apps.subscriptions.services import entitlement_service as ent

        ready_platform_zibal(self)
        enable_platform_card(self)
        response = self.execute()
        invoice = SubscriptionInvoice.objects.get(store=self.store2, kind="plan_change")
        checkout = reverse("dashboard:platform-checkout", args=["subscription", invoice.pk])
        self.assertRedirects(response, checkout, fetch_redirect_response=False)
        self.assertEqual(int(invoice.grand_total), 3_000_000)                       # the YEARLY price, server-computed
        page = self.client2.get(checkout).content.decode()
        self.assertEqual(page.count('name="method"'), 2)
        self.assertIn("۳٬۰۰۰٬۰۰۰", page)
        self.client2.post(reverse("dashboard:platform-checkout-pay", args=["subscription", invoice.pk]), {"method": "zibal"})
        attempt = SubscriptionPaymentAttempt.objects.get(invoice=invoice)
        self.assertEqual(int(attempt.amount), 3_000_000)
        self.assertEqual(ent.get_current_subscription(self.store2).plan_version_id, self.v1.pk)          # unpaid ⇒ unchanged
        self.fake.paid(amount_rial=30_000_000, order_id=attempt.public_token)
        self.callback(attempt)
        self.callback(attempt)
        sub = ent.get_current_subscription(self.store2)
        self.assertEqual(sub.plan_version_id, self.v2.pk)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=invoice.pk).status, SubscriptionInvoice.Status.PAID)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2, kind="plan_change").count(), 1)

    def test_a_downgrade_needs_no_payment_even_with_no_method_ready(self):
        from apps.subscriptions.services import subscription_service as ss

        ss.change_plan_version(self.sub2, self.v2)                                    # start on the higher plan
        response = self.client2.post("/admin-portal/subscription/plans/preview/", {"version_id": self.v1.pk})
        token = response.context["preview"]["token"]
        response = self.client2.post("/admin-portal/subscription/plans/change/", {"version_id": self.v1.pk, "preview_token": token})
        self.assertRedirects(response, reverse("dashboard:subscription-overview"), fetch_redirect_response=False)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store2, kind="plan_change").count(), 0)


class CheckoutNavigationTests(CheckoutBase):
    """Checkout screens are focused: no settings tab bar, sub-tabs or «settings-only» search; the navigation map is still right."""

    def test_checkout_pages_drop_the_settings_chrome_but_keep_the_shell_and_the_hidden_bell_error(self):
        ready_platform_zibal(self)
        for kind in KINDS:
            with self.subTest(kind=kind):
                html = self.page(kind).content.decode()
                for needle in ("admin-section-tabs", "admin-subtabs", "settingsSearch", "فقط صفحه‌های تنظیمات"):
                    self.assertNotIn(needle, html, needle)
                self.assertIn("adminV2SearchTrigger", html)                           # the global search stays
                self.assertRegex(html, r'data-nt-error role="alert" hidden')             # bell error is hidden until a real failure

    def test_the_navigation_map_puts_each_checkout_in_the_right_section_and_tab(self):
        from apps.dashboard import navigation

        self.assertEqual(navigation.resolve_active("sms-checkout", None, "settings"), ("settings", "messaging"))
        self.assertEqual(navigation.resolve_active("sms-checkout-pay", None, "settings"), ("settings", "messaging"))
        self.assertEqual(navigation.resolve_active("platform-checkout", None, "billing"), ("settings", "account"))

    def test_both_routes_resolve_to_the_same_view_and_the_generic_reverse_gives_the_same_path(self):
        self.assertEqual(self.url(SMS), f"/admin-portal/billing/checkout/sms/{self.purchase.pk}/")
        self.assertEqual(self.url(SUB), f"/admin-portal/billing/checkout/subscription/{self.invoice.pk}/")
        from django.urls import resolve

        self.assertEqual(resolve(self.url(SMS)).url_name, "sms-checkout")
        self.assertEqual(resolve(self.url(SUB)).url_name, "platform-checkout")


class ZibalLegacyAuthorityTests(TestCase):
    """The canonical row is authoritative: legacy columns can never override it, and the retirement audit is honest."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()

    def _legacy(self, merchant="LEGACY-MERCHANT", sandbox=True, default="zibal"):
        from apps.portal.services.platform_config_service import get_platform_configuration

        config = get_platform_configuration()
        config.default_payment_provider = default
        config.zibal_sandbox_mode = sandbox
        config.set_zibal_credentials(merchant=merchant)
        config.save()
        cache.clear()

    @override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
    def test_an_existing_canonical_row_always_wins_over_legacy_credentials_mode_and_enabled(self):
        from apps.portal.models import PlatformGatewayConfig

        self._legacy()
        pgs.save_gateway("zibal", credentials={"merchant": "CANON-MERCHANT"}, sandbox=False, enabled=False)
        self._legacy(merchant="LEGACY-NEWER", sandbox=True, default="zibal")              # legacy changed AFTER the row existed
        creds, sandbox, source = pgs.credentials_and_mode("zibal")
        self.assertEqual((creds["merchant"], sandbox, source), ("CANON-MERCHANT", False, "row"))
        state = pgs.gateway_state("zibal")
        self.assertFalse(state.enabled)                       # the row says disabled; legacy default==zibal must not enable it
        self.assertNotIn("zibal", pgs.ready_codes())
        self.assertEqual(PlatformGatewayConfig.objects.filter(gateway_code="zibal").count(), 1)

    @override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
    def test_the_provider_request_uses_the_canonical_merchant_never_the_legacy_one(self):
        from apps.billing.tests.platform_payment_support import patch_zibal

        self._legacy(merchant="LEGACY-MERCHANT", sandbox=False)
        pgs.save_gateway("zibal", credentials={"merchant": "CANON-MERCHANT"}, sandbox=False, enabled=True)
        fake = patch_zibal(self)
        from apps.billing.providers import registry
        from apps.billing.tests.platform_payment_support import open_invoice_for

        store = Store.objects.create(name="کانون", slug="pccanon", admin_subdomain="pccanon")
        _sub, invoice = open_invoice_for(store, code="pccanon")
        payment_flow_service.start_payment(invoice, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
        self.assertEqual(fake.calls_to("request")[0]["merchant"], "CANON-MERCHANT")
        self.assertNotIn("LEGACY-MERCHANT", str(fake.calls))
        self.assertTrue(registry.get_provider("zibal"))

    def test_the_legacy_route_never_writes_and_no_service_path_writes_the_legacy_columns(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        self._legacy(merchant="LEGACY-MERCHANT")
        before = get_platform_configuration().encrypted_zibal_credentials
        pgs.save_gateway("zibal", credentials={"merchant": "ROW-NEW"}, sandbox=False, enabled=True)
        pgs.save_gateway("zibal", credentials={"merchant": ""}, sandbox=True, enabled=False)
        self.assertEqual(get_platform_configuration().encrypted_zibal_credentials, before)         # frozen rollback copy

    def test_the_retirement_audit_reports_legacy_as_blocking_until_the_row_is_the_effective_source(self):
        from io import StringIO

        from django.core.management import CommandError, call_command

        out = StringIO()
        call_command("audit_platform_zibal_legacy", stdout=out)
        self.assertIn("effective_source: none", out.getvalue())
        self._legacy()
        with self.assertRaises(CommandError):
            call_command("audit_platform_zibal_legacy", "--strict", stdout=StringIO(), stderr=StringIO())
        pgs.save_gateway("zibal", credentials={"merchant": ""}, sandbox=False, enabled=True)    # first canonical save keeps the legacy merchant
        out = StringIO()
        call_command("audit_platform_zibal_legacy", "--strict", stdout=out)
        self.assertIn("effective_source: row", out.getvalue())
        self.assertNotIn("LEGACY-MERCHANT", out.getvalue())


class FreeAndZeroDueTests(CheckoutBase):
    """Free / zero-payable purchases never need a gateway, and a PAID plan can never be obtained this way."""

    def setUp(self):
        super().setUp()
        self.free_store = Store.objects.create(name="رایگان", slug="pcfree", admin_subdomain="pcfree", status=Store.Status.ACTIVE)
        self.free_owner = self._member(self.free_store, "pcfree-owner")
        self.free_sub, self.free_invoice = open_invoice_for(self.free_store, code="pcfree", price="0")
        self.free_client = Client(HTTP_HOST=f"pcfree.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}")
        self.free_client.login(username="pcfree-owner", password="pass12345")

    def free_url(self, action=""):
        name = "platform-checkout-pay" if action == "pay" else "platform-checkout"
        return reverse(f"dashboard:{name}", args=["subscription", self.free_invoice.pk])

    def test_a_zero_invoice_shows_the_free_state_without_any_method_or_gateway(self):
        html = self.free_client.get(self.free_url()).content.decode()
        self.assertIn('data-testid="settle-free"', html)
        self.assertNotIn('name="method"', html)
        self.assertNotIn('data-testid="no-method"', html)

    def test_settling_a_zero_invoice_activates_exactly_once_with_no_gateway_and_ignores_browser_fields(self):
        self.assertFalse(pgs.checkout_options("subscription", store=self.free_store))          # no method is ready anywhere
        for _ in range(3):
            self.free_client.post(self.free_url("pay"), {"method": "platform_card", "amount": "999999", "price": "5"})
        invoice = SubscriptionInvoice.objects.get(pk=self.free_invoice.pk)
        self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, 0))
        self.assertEqual(StoreSubscription.objects.get(pk=self.free_sub.pk).status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(invoice=invoice).count(), 1)
        from apps.core.models import AuditLogEntry

        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.zero_invoice_settled").count(), 1)
        self.assertContains(self.free_client.get(self.free_url()), 'data-state="paid"')

    def test_a_paid_invoice_can_never_be_settled_as_free(self):
        from apps.billing.services import confirmation_service as cs

        with self.assertRaises(cs.ConfirmationError):
            cs.settle_zero_due_invoice(self.invoice)
        for method in ("free", "zero", "", "manual"):
            self.pay(SUB, method, amount="0")
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, int(invoice.amount_paid), self.attempts(SUB).count()), (SubscriptionInvoice.Status.OPEN, 0, 0))
        self.assertEqual(StoreSubscription.objects.get(pk=self.sub.pk).status, self.sub.status)       # not activated

    def test_a_tampered_zero_total_with_paid_lines_is_refused_by_the_line_sum_guard(self):
        from apps.billing.services import confirmation_service as cs

        SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(grand_total=0, amount_due=0, subtotal=0)
        with self.assertRaises(cs.ConfirmationError):
            cs.settle_zero_due_invoice(SubscriptionInvoice.objects.get(pk=self.invoice.pk))
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.OPEN)

    def test_cross_tenant_cannot_settle_anothers_zero_invoice(self):
        response = self.owner_client.post(reverse("dashboard:platform-checkout-pay", args=["subscription", self.free_invoice.pk]), {"method": "x"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.free_invoice.pk).status, SubscriptionInvoice.Status.OPEN)

    def test_a_zero_price_sms_package_is_granted_once_and_a_priced_one_never(self):
        free_pkg = SmsPackage.objects.create(name="رایگان", credit_amount=50, price=0)
        purchase = balance_service.request_purchase(store=self.store, package=free_pkg)
        url = reverse("dashboard:platform-checkout", args=["sms", purchase.pk])
        pay = reverse("dashboard:platform-checkout-pay", args=["sms", purchase.pk])
        self.assertContains(self.owner_client.get(url), 'data-testid="settle-free"')
        for _ in range(3):
            self.owner_client.post(pay, {"method": "zibal", "amount": "0"})
        self.assertEqual(self.credits(), 150)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=purchase).count(), 1)
        self.assertEqual(SmsPackagePurchase.objects.get(pk=purchase.pk).status, SmsPackagePurchase.Status.COMPLETED)
        # a priced package: even with the snapshot tampered to look free in the browser, the server price decides
        for _ in range(2):
            self.pay(SMS, "free", amount="0")
        self.assertEqual(self.credits(), 150)
        from apps.billing.services.payment_flow_service import PaymentFlowError

        with self.assertRaises(PaymentFlowError):
            sms_purchase_payment_service.settle_free_purchase(self.purchase)

    def test_buying_a_zero_price_package_works_with_no_ready_method_but_a_priced_one_is_still_refused(self):
        free_pkg = SmsPackage.objects.create(name="رایگان۲", credit_amount=10, price=0)
        response = self.owner_client.post(reverse("dashboard:settings-sms-package-purchase"), {"package_id": free_pkg.pk})
        purchase = SmsPackagePurchase.objects.get(package=free_pkg)
        self.assertRedirects(response, reverse("dashboard:platform-checkout", args=["sms", purchase.pk]), fetch_redirect_response=False)
        self.owner_client.post(reverse("dashboard:settings-sms-package-purchase"), {"package_id": self.package.pk})
        self.assertFalse(SmsPackagePurchase.objects.filter(store=self.store, package=self.package, pk__gt=self.purchase.pk).exists())


class FreeTargetsAreNeverBlockedTests(CheckoutBase):
    """A downgrade / free target is scheduled without any gateway, from both the portal and the dashboard."""

    def setUp(self):
        super().setUp()
        from apps.portal.services.platform_config_service import update_platform_configuration
        from apps.subscriptions.services import subscription_service as ss
        from apps.subscriptions.tests.test_pricing_dynamic import make_plan

        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        _p, self.paid = make_plan("pcfree-paid", base=300000, order=1)
        _p, self.cheap = make_plan("pcfree-cheap", base=100000, order=2)
        _p, self.zero = make_plan("pcfree-zero", base=0, order=3)
        self.st = Store.objects.create(name="تنزل", slug="pcdown", admin_subdomain="pcdown", status=Store.Status.ACTIVE)
        self.st_owner = self._member(self.st, "pcdown-owner")
        self.sub3 = ss.activate_subscription(ss.create_subscription(self.st, self.paid), period_end=timezone.now() + timedelta(days=20))
        self.pc = Client()
        self.pc.force_login(self.st_owner)

    def portal_buy(self, version):
        return self.pc.post(f"/app/stores/{self.st.public_id}/billing/checkout/{version.pk}/", HTTP_HOST=PORTAL_HOST)

    def test_portal_downgrade_and_free_target_with_no_method_ready_are_scheduled_not_blocked(self):
        from apps.billing.models import ScheduledPlanChange

        self.assertFalse(pgs.checkout_options("subscription", store=self.st))
        response = self.portal_buy(self.cheap)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ScheduledPlanChange.objects.filter(subscription__store=self.st).exists())
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.st).exists())
        self.portal_buy(self.zero)
        self.assertEqual(ScheduledPlanChange.objects.get(subscription__store=self.st).target_plan_version_id, self.zero.pk)

    def test_portal_paid_upgrade_with_no_method_is_still_refused_and_creates_no_invoice(self):
        from apps.subscriptions.tests.test_pricing_dynamic import make_plan

        _p, top = make_plan("pcfree-top", base=900000, order=4)
        self.portal_buy(top)
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.st).exists())
        from apps.subscriptions.services import entitlement_service as ent

        self.assertEqual(ent.get_current_subscription(self.st).plan_version_id, self.paid.pk)      # paid plan never granted free


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentCallbackTests(TransactionTestCase):
    """Two simultaneous bank returns (and a status click) for one attempt apply the effect exactly once — PostgreSQL row locks."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.store = Store.objects.create(name="هم‌زمانی", slug="pcconc", admin_subdomain="pcconc", status=Store.Status.ACTIVE)
        self.sub, self.invoice = open_invoice_for(self.store, code="pcconc", price=str(SUB_PRICE))
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 100})
        self.package = SmsPackage.objects.create(name="هم‌زمان", credit_amount=SMS_CREDITS, price=SMS_PRICE)
        self.purchase = balance_service.request_purchase(store=self.store, package=self.package)
        self.fake = patch_zibal(self)

    @override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
    def _run(self, make_attempt, verify, threads=4):
        ready_platform_zibal(self)
        attempt = make_attempt()
        errors = []

        def worker():
            try:
                verify(type(attempt).objects.get(pk=attempt.pk))
            except Exception as exc:  # noqa: BLE001 — a lost race may raise a handled domain error; never corruption
                errors.append(exc)
            finally:
                connection.close()

        pool = [threading.Thread(target=worker) for _ in range(threads)]
        [t.start() for t in pool]
        [t.join() for t in pool]
        return attempt

    @override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
    def test_subscription_concurrent_verification_applies_once(self):
        def make():
            attempt, _session = payment_flow_service.start_payment(
                self.invoice, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
            self.fake.paid(amount_rial=SUB_PRICE * 10, order_id=attempt.public_token)
            return attempt

        attempt = self._run(make, lambda a: payment_flow_service.confirm_from_provider_verification(a))
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, int(invoice.amount_paid)), (SubscriptionInvoice.Status.PAID, SUB_PRICE))
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk, status="succeeded").count(), 1)

    @override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
    def test_sms_concurrent_verification_credits_once(self):
        def make():
            attempt, _session = sms_purchase_payment_service.start_payment(
                self.purchase, provider="zibal", callback_base_url="https://rastisi.ir/", return_to="")
            self.fake.paid(amount_rial=SMS_PRICE * 10, order_id=attempt.public_token)
            return attempt

        self._run(make, lambda a: sms_purchase_payment_service.verify_and_fulfill(a))
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 100 + SMS_CREDITS)
        self.assertEqual(SmsCreditLedger.objects.filter(purchase=self.purchase).count(), 1)
