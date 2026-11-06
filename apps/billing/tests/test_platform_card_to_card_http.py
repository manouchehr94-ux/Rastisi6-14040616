"""Platform card-to-card over HTTP: owner dashboard pages (claim form, cancel, own receipt), Platform Admin review queue / detail /
approve / reject / private receipt, and the cross-host / permission / tenant boundaries. Synthetic data only."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.billing.models import PlatformManualPaymentClaim as Claim, SubscriptionInvoice
from apps.billing.services import manual_card_service as mcs
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.billing.tests.test_platform_card_to_card import PNG, enable_platform_card, upload, use_private_tmp
from apps.core.models import AuditLogEntry
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
S = Claim.Status


def D(name, *args):
    return reverse(f"dashboard:{name}", args=list(args))

PLATFORM_HOST = "platformadmins.rastisi.localhost"
OWNER_HOST = f"c2chttp.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"
OTHER_HOST = f"c2cother.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


@override_settings(ALLOWED_HOSTS=[PLATFORM_HOST, OWNER_HOST, OTHER_HOST, "testserver"])
class CardHttpBase(TestCase):
    def setUp(self):
        use_private_tmp(self)
        self.store = Store.objects.create(name="فروشگاه اچ‌تی‌تی‌پی", slug="c2c-http", admin_subdomain="c2chttp", status=Store.Status.ACTIVE)
        self.other = Store.objects.create(name="فروشگاه دیگر", slug="c2c-other-http", admin_subdomain="c2cother", status=Store.Status.ACTIVE)
        self.owner = self._member(self.store, "c2c-http-owner")
        self.other_owner = self._member(self.other, "c2c-http-other")
        self.finance = User.objects.create_user(username="fin-http@example.com", password="pass12345", is_staff=True, is_superuser=True)
        self.sub, self.invoice = open_invoice_for(self.store, code="c2chttp", price="300000")
        enable_platform_card(self)
        self.owner_client = Client(HTTP_HOST=OWNER_HOST)
        self.owner_client.login(username="c2c-http-owner", password="pass12345")
        self.admin_client = Client(HTTP_HOST=PLATFORM_HOST)
        self.admin_client.force_login(self.finance)

    def _member(self, store, username):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=store, user=user, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        return user

    def claim_form(self, **extra):
        data = {"reference": "HTTP-TRK-556677", "transferred_at": timezone.localtime(timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "payer_card_last4": "4321", "receipt": upload()}
        data.update(extra)
        return self.owner_client.post(D("billing-card-claim", self.invoice.pk), data)

    def the_claim(self):
        return Claim.objects.get(invoice=self.invoice)


class OwnerFlowTests(CardHttpBase):
    def test_the_claim_page_shows_destination_details_and_the_server_side_amount(self):
        response = self.owner_client.get(D("billing-card-claim", self.invoice.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "6037 9970 0000 0019")
        self.assertContains(response, "۳۰۰٬۰۰۰")
        self.assertNotContains(response, 'name="amount"')                       # the amount is never posted by the client

    def test_posting_a_claim_stores_it_pending_and_activates_nothing(self):
        response = self.claim_form()
        self.assertEqual(response.status_code, 302)
        claim = self.the_claim()
        self.assertEqual((claim.status, claim.submitted_by_id, claim.payer_card_last4), (S.PENDING_REVIEW, self.owner.pk, "4321"))
        self.assertTrue(claim.receipt)
        self.assertNotEqual(StoreSubscription.objects.get(pk=self.sub.pk).status, StoreSubscription.Status.ACTIVE)
        page = self.owner_client.get(D("billing-card-claim", self.invoice.pk))
        self.assertContains(page, "در انتظار")

    def test_invalid_submissions_show_an_error_and_create_nothing(self):
        for bad in ({"reference": "12"}, {"transferred_at": "not-a-date"}, {"receipt": upload(b"<script>x</script>", "a.png", "image/png")}):
            response = self.claim_form(**bad)
            self.assertEqual(response.status_code, 200, bad)
        self.assertEqual(Claim.objects.count(), 0)

    def test_the_owner_can_cancel_and_view_only_their_own_claim_and_receipt(self):
        self.claim_form()
        claim = self.the_claim()
        receipt = self.owner_client.get(D("billing-card-claim-receipt", claim.pk))
        self.assertEqual((receipt.status_code, receipt["Content-Type"], receipt["Cache-Control"], receipt["X-Content-Type-Options"]),
                         (200, "image/png", "private, no-store", "nosniff"))
        self.assertEqual(b"".join(receipt.streaming_content), PNG)
        stranger = Client(HTTP_HOST=OTHER_HOST)
        stranger.login(username="c2c-http-other", password="pass12345")
        self.assertEqual(stranger.get(D("billing-card-claim-receipt", claim.pk)).status_code, 404)
        self.assertEqual(stranger.post(D("billing-card-claim-cancel", claim.pk)).status_code, 404)
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.PENDING_REVIEW)
        self.assertEqual(Client(HTTP_HOST=OWNER_HOST).get(D("billing-card-claim-receipt", claim.pk)).status_code, 302)   # anonymous → login
        self.assertEqual(self.owner_client.get(D("billing-card-claim-cancel", claim.pk)).status_code, 405)                # POST only
        self.owner_client.post(D("billing-card-claim-cancel", claim.pk))
        self.assertEqual(Claim.objects.get(pk=claim.pk).status, S.CANCELLED)

    def test_the_page_is_unavailable_when_the_method_is_disabled_and_other_stores_invoices_are_404(self):
        enable_platform_card(self, enabled=False)
        response = self.owner_client.get(D("billing-card-claim", self.invoice.pk))
        self.assertEqual(response.status_code, 302)
        enable_platform_card(self)
        _s, foreign = open_invoice_for(self.other, code="c2cforeign", price="100000")
        self.assertEqual(self.owner_client.get(D("billing-card-claim", foreign.pk)).status_code, 404)

    def test_the_checkout_offers_card_to_card_only_when_ready_and_choosing_it_opens_the_claim_page(self):
        checkout = D("platform-checkout", "subscription", self.invoice.pk)
        self.assertContains(self.owner_client.get(D("billing-invoice-detail", self.invoice.pk)), checkout)
        self.assertContains(self.owner_client.get(checkout), 'value="platform_card"')
        pay = self.owner_client.post(D("platform-checkout-pay", "subscription", self.invoice.pk), {"method": "platform_card"})
        self.assertRedirects(pay, D("billing-card-claim", self.invoice.pk), fetch_redirect_response=False)
        self.assertEqual(Claim.objects.count(), 0)                                           # choosing the method creates no claim
        enable_platform_card(self, enabled=False)
        self.assertNotContains(self.owner_client.get(checkout), 'value="platform_card"')
        pay = self.owner_client.post(D("platform-checkout-pay", "subscription", self.invoice.pk), {"method": "platform_card"})
        self.assertRedirects(pay, checkout, fetch_redirect_response=False)
        legacy = self.owner_client.post(D("billing-pay", self.invoice.pk), {"gateway": "platform_card"})       # legacy URL, same rules
        self.assertRedirects(legacy, checkout, fetch_redirect_response=False)

    def test_the_sms_purchase_claim_page_works_for_the_owners_own_purchase_only(self):
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 0})
        package = SmsPackage.objects.create(name="بسته", credit_amount=100, price=50_000)
        purchase = balance_service.request_purchase(store=self.store, package=package)
        foreign = balance_service.request_purchase(store=self.other, package=package)
        page = self.owner_client.get(D("sms-purchase-card-claim", purchase.pk))
        self.assertContains(page, "6037 9970 0000 0019")
        self.assertEqual(self.owner_client.get(D("sms-purchase-card-claim", foreign.pk)).status_code, 404)
        response = self.owner_client.post(D("sms-purchase-card-claim", purchase.pk), {
            "reference": "SMS-HTTP-998877", "transferred_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H:%M")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SmsCreditLedger.objects.count(), 0)                                  # claim ≠ credit


class PlatformAdminReviewTests(CardHttpBase):
    def setUp(self):
        super().setUp()
        self.claim_form()
        self.claim = self.the_claim()

    def action(self, action, **data):
        return self.admin_client.post(f"/payments/card-claims/{self.claim.pk}/{action}/", data)

    def test_the_queue_and_detail_show_the_claim_with_the_review_form_for_finance(self):
        queue = self.admin_client.get("/payments/card-claims/")
        self.assertContains(queue, "HTTP-TRK-556677")
        detail = self.admin_client.get(f"/payments/card-claims/{self.claim.pk}/")
        self.assertContains(detail, "HTTP-TRK-556677")
        self.assertContains(detail, "bank_reference")
        self.assertContains(detail, f"/payments/card-claims/{self.claim.pk}/receipt/")

    def test_finance_approves_with_a_bank_reference_and_the_exact_amount_and_it_applies_once(self):
        self.action("approve", bank_reference="BANK-HTTP-0001", confirmed_amount="300000")
        self.action("approve", bank_reference="BANK-HTTP-0001", confirmed_amount="300000")
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.APPROVED)
        invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
        self.assertEqual((invoice.status, invoice.amount_paid), (SubscriptionInvoice.Status.PAID, Decimal("300000")))
        self.assertEqual(AuditLogEntry.objects.filter(action_code="billing.payment_confirmed").count(), 1)

    def test_wrong_amount_or_missing_reference_is_refused_and_changes_nothing(self):
        for data in ({"bank_reference": "BANK-HTTP-0002", "confirmed_amount": "299999"}, {"bank_reference": "", "confirmed_amount": "300000"},
                     {"bank_reference": "BANK-HTTP-0002", "confirmed_amount": "300001"}):
            self.action("approve", **data)
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.PENDING_REVIEW)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, 0)

    def test_rejection_requires_a_reason_and_leaves_the_invoice_payable(self):
        self.action("reject", reason="")
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.PENDING_REVIEW)
        self.action("reject", reason="رسید با صورتحساب نمی‌خواند")
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.REJECTED)
        self.assertTrue(SubscriptionInvoice.objects.get(pk=self.invoice.pk).is_payable)
        self.assertEqual(self.action("bogus").status_code, 302)
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.REJECTED)

    def test_only_platform_superusers_reach_the_queue_detail_actions_and_receipts(self):
        paths = [("get", "/payments/card-claims/"), ("get", f"/payments/card-claims/{self.claim.pk}/"),
                 ("get", f"/payments/card-claims/{self.claim.pk}/receipt/"),
                 ("post", f"/payments/card-claims/{self.claim.pk}/approve/")]
        staff = User.objects.create_user(username="plain-staff@example.com", password="pass12345", is_staff=True)
        for who in ("anonymous", "store_owner", "staff"):
            client = Client(HTTP_HOST=PLATFORM_HOST)
            if who == "store_owner":
                client.force_login(self.owner)
            elif who == "staff":
                client.force_login(staff)
            for method, path in paths:
                response = getattr(client, method)(path, {"bank_reference": "BANK-X-9999", "confirmed_amount": "300000"})
                self.assertIn(response.status_code, (302, 403, 404), (who, path))
                if response.status_code == 302:
                    self.assertIn("login", response["Location"], (who, path))
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.PENDING_REVIEW)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).amount_paid, 0)

    def test_a_staff_user_without_the_finance_permission_can_view_but_not_review(self):
        # platform staff in the admin (non-superuser) cannot pass _is_platform_staff; an active superuser without a membership can.
        response = self.action("approve", bank_reference="BANK-HTTP-0003", confirmed_amount="300000")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Claim.objects.get(pk=self.claim.pk).status, S.APPROVED)

    def test_the_admin_receipt_is_served_privately_and_the_owners_host_cannot_serve_the_admin_route(self):
        response = self.admin_client.get(f"/payments/card-claims/{self.claim.pk}/receipt/")
        self.assertEqual((response.status_code, response["Cache-Control"], response["X-Content-Type-Options"]), (200, "private, no-store", "nosniff"))
        self.assertEqual(b"".join(response.streaming_content), PNG)
        self.assertEqual(self.owner_client.get(f"/payments/card-claims/{self.claim.pk}/receipt/").status_code, 404)    # not on the store host

    def test_the_queue_filters_by_status_and_flags_duplicates_for_reviewers(self):
        mcs.reject_claim(self.claim, reviewer=self.finance, reason="تست فیلتر")
        self.assertNotContains(self.admin_client.get("/payments/card-claims/"), "HTTP-TRK-556677")
        self.assertContains(self.admin_client.get("/payments/card-claims/?status=rejected"), "HTTP-TRK-556677")


class ReconciliationPageTests(CardHttpBase):
    def test_manual_claims_are_surfaced_in_their_own_section_not_as_stale_gateway_attempts(self):
        from apps.billing.models import SubscriptionPaymentAttempt

        self.claim_form()
        claim = self.the_claim()
        SubscriptionPaymentAttempt.objects.filter(pk=claim.subscription_attempt_id).update(created_at=timezone.now() - timedelta(hours=3))
        Claim.objects.filter(pk=claim.pk).update(created_at=timezone.now() - timedelta(hours=30))
        page = self.admin_client.get("/payments/reconciliation/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "ادعاهایِ کارت‌به‌کارتِ در انتظار: 1")
        self.assertContains(page, "بیش از ۲۴ ساعت")
        self.assertEqual(page.context["totals"]["stale_pending"], 0)              # the manual attempt is not a "check with gateway" item

    def test_a_verified_but_unsettled_attempt_is_listed_with_a_recovery_action(self):
        from apps.billing.models import SubscriptionPaymentAttempt

        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=self.invoice, provider="mellat", status="pending", amount=self.invoice.amount_due,
            currency="IRT", public_token="recon-token-1", idempotency_key="recon-1", provider_session_id="1000000009",
            provider_extra={"verified": True, "verified_ref": "SALE-1"},
        )
        page = self.admin_client.get("/payments/reconciliation/")
        self.assertEqual(page.context["totals"]["verified_unsettled"], 1)
        self.assertContains(page, "استعلام و تسویه")
        self.assertContains(page, attempt.invoice.number)
