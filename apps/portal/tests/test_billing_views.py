"""Section 8/9 — the portal-facing subscription purchase flow, now a
consumer of the pre-existing apps.billing domain (technical-consolidation
pass — see ADR-105/ADR-106 in SAAS_DOMAIN_DECISIONS.md): plan list →
checkout → real signed-webhook confirmation → return. Exercised through the
real HTTP client (not the service layer directly) so the urlconf/reverse
wiring between apps.portal and apps.billing is actually verified, and so a
real (signed) webhook delivery — the only way apps.billing's "manual"
provider ever confirms a payment — is proven to activate the subscription
end-to-end, exactly like apps.billing's own WebhookToActivationTests."""

import hashlib
import hmac
import json
import time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers.manual import SIGNATURE_HEADER, TIMESTAMP_HEADER
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service

User = get_user_model()
_HOST = "rastisi.localhost"
WEBHOOK_SECRET = "test-billing-webhook-secret"


def _signed_webhook_headers(*, secret, body: bytes):
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {
        "HTTP_" + SIGNATURE_HEADER.upper().replace("-", "_"): sig,
        "HTTP_" + TIMESTAMP_HEADER.upper().replace("-", "_"): ts,
    }


@override_settings(
    ALLOWED_HOSTS=[_HOST, "testserver"], RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir",
    RASTISI_BILLING_WEBHOOK_SECRET=WEBHOOK_SECRET, RASTISI_BILLING_PROVIDER="manual",
)
class BillingViewsTestCase(TestCase):
    """Section 10's step-up OTP is exercised on its own in
    test_step_up_billing.py; these tests are about checkout/apps.billing
    mechanics, so step-up is explicitly turned off here to isolate that.

    Every real Store is provisioned with a trialing subscription the moment
    it's created (Section 3.1) — so, matching that real precondition, this
    fixture always creates one too, rather than a bare Store with no
    subscription at all.
    """

    def setUp(self):
        self.addCleanup(cache.clear)
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.store = Store.objects.create(
            name="فروشگاه صورتحساب", slug="billing-view-store", admin_subdomain="billing-view-store",
        )
        self.owner = User.objects.create_user(username="09121230011", password="a-very-strong-pass-1")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.trial_plan = Plan.objects.create(code="trial-view", name="Trial", is_publicly_selectable=True)
        self.trial_version = PlanVersion.objects.create(
            plan=self.trial_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.NONE, display_price=0, trial_days=14,
        )
        sub = subscription_service.create_subscription(self.store, self.trial_version, actor=self.owner)
        self.subscription = subscription_service.start_trial(sub, actor=self.owner)

        self.plan = Plan.objects.create(code="pro-view", name="Pro", is_active=True, is_publicly_selectable=True)
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        from apps.billing.tests.platform_payment_support import ready_platform_zibal

        ready_platform_zibal(self)                      # the portal refuses to issue an invoice when NO platform method is ready
        self.client.force_login(self.owner)

    def _checkout(self):
        return self.client.post(
            f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=_HOST,
        )

    def _attempt(self):
        """Portal «buy» issues the invoice; the signed-webhook ``manual`` provider is test infrastructure for the webhook path
        (merchants can never pick it at the checkout), so its attempt is started through the service."""
        from apps.billing.services import payment_flow_service

        self._checkout()
        invoice = SubscriptionInvoice.objects.filter(store=self.store).order_by("-pk").first()
        attempt, _session = payment_flow_service.start_payment(invoice, actor=self.owner, provider="manual")
        return attempt

    def _confirm_via_webhook(self, attempt, *, event_id, event_type="payment.succeeded"):
        body = json.dumps({
            "event_id": event_id, "event_type": event_type,
            "session_id": f"manual-sess-{attempt.public_token}", "provider_payment_id": f"pay-{event_id}",
            "amount": str(attempt.amount), "currency": attempt.currency,
        }).encode()
        headers = _signed_webhook_headers(secret=WEBHOOK_SECRET, body=body)
        return Client().post(
            reverse("billing:webhook", args=["manual"]), data=body, content_type="application/json", **headers,
        )


class BillingPlansViewTests(BillingViewsTestCase):
    def test_lists_published_paid_plan(self):
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pro")

    def test_hides_draft_versions(self):
        PlanVersion.objects.create(
            plan=self.plan, version_number=2, status=PlanVersion.Status.DRAFT, display_price=1,
        )
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        versions = response.context["plan_versions"]
        self.assertEqual([v.pk for v in versions], [self.version.pk])

    def test_hides_free_plans(self):
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        versions = response.context["plan_versions"]
        self.assertNotIn(self.trial_plan.code, [v.plan.code for v in versions])

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 302)

    def test_other_owner_cannot_see_someone_elses_billing_page(self):
        other = User.objects.create_user(username="09121230022", password="a-very-strong-pass-1")
        self.client.force_login(other)
        response = self.client.get(f"/app/stores/{self.store.public_id}/billing/", HTTP_HOST=_HOST)
        self.assertEqual(response.status_code, 404)


class BillingCheckoutViewTests(BillingViewsTestCase):
    def test_creates_invoice_and_hands_off_to_the_unified_checkout_without_any_payment_attempt(self):
        response = self._checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-portal/handoff/", response["Location"])
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 1)
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(store=self.store).count(), 0)

    def test_get_is_not_allowed(self):
        response = self.client.get(
            f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 405)

    def test_draft_version_cannot_be_checked_out(self):
        draft = PlanVersion.objects.create(plan=self.plan, version_number=2, status=PlanVersion.Status.DRAFT)
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/billing/checkout/{draft.pk}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)


class BillingWebhookConfirmationViewTests(BillingViewsTestCase):
    def test_return_page_shows_pending_before_confirmation(self):
        attempt = self._attempt()
        response = self.client.get(
            f"/app/stores/{self.store.public_id}/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "در انتظارِ تأیید")

    def test_browser_return_alone_never_activates(self):
        attempt = self._attempt()
        for _ in range(3):
            self.client.get(
                f"/app/stores/{self.store.public_id}/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST,
            )
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.TRIALING)

    def test_non_succeeded_webhook_event_never_activates(self):
        attempt = self._attempt()
        self._confirm_via_webhook(attempt, event_id="evt-fail-1", event_type="payment.failed")
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.TRIALING)
        invoice = attempt.invoice
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAYMENT_PENDING)

    def test_signed_webhook_activates_subscription_and_return_page_shows_success(self):
        attempt = self._attempt()
        webhook_response = self._confirm_via_webhook(attempt, event_id="evt-pay-1")
        self.assertEqual(webhook_response.status_code, 200)

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.subscription.plan_version_id, self.version.pk)

        response = self.client.get(
            f"/app/stores/{self.store.public_id}/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "با موفقیت")

    def test_duplicate_webhook_does_not_double_activate(self):
        attempt = self._attempt()
        self._confirm_via_webhook(attempt, event_id="evt-dup-1")
        self._confirm_via_webhook(attempt, event_id="evt-dup-1")
        invoice = attempt.invoice
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, invoice.grand_total)

    def test_other_owners_attempt_is_not_reachable(self):
        attempt = self._attempt()
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="billing-other-store", admin_subdomain="billing-other-store",
        )
        other_owner = User.objects.create_user(username="09121230044", password="a-very-strong-pass-1")
        StoreMembership.objects.create(
            store=other_store, user=other_owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.force_login(other_owner)
        response = self.client.get(
            f"/app/stores/{other_store.public_id}/billing/return/{attempt.public_token}/", HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 404)


class BillingCheckoutNoGatewayCouponTests(BillingViewsTestCase):
    """The portal first-purchase path must judge gateway availability on the POST-discount invoice amount, inside the
    same atomic block as the invoice and its automatic campaign. A fully discounted invoice needs no gateway; a partially
    discounted one does, and then NOTHING (invoice, redemption reservation) may remain."""

    def _staff(self):
        return User.objects.create_user(username="npgw-fin@example.com", password="pass12345", is_staff=True, is_superuser=True)

    def _no_gateway(self):
        from unittest import mock

        return mock.patch("apps.portal.services.platform_gateway_service.checkout_options", return_value=[])

    def test_automatic_100_percent_campaign_needs_no_gateway(self):
        from apps.billing.models import PlatformCouponRedemption
        from apps.billing.services import platform_coupon_service as svc

        svc.create_coupon(actor=self._staff(), name="free-first", code=None, is_automatic=True, kind="percent", percent=100)
        with self._no_gateway():
            response = self._checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-portal/handoff/", response["Location"])
        invoice = SubscriptionInvoice.objects.get(store=self.store)
        self.assertEqual(invoice.amount_due, 0)
        self.assertTrue(PlatformCouponRedemption.objects.filter(invoice=invoice).exists())

    def test_partial_automatic_campaign_without_gateway_rolls_back_invoice_and_reservation(self):
        from apps.billing.models import PlatformCouponRedemption
        from apps.billing.services import platform_coupon_service as svc

        svc.create_coupon(actor=self._staff(), name="part-first", code=None, is_automatic=True, kind="percent", percent=20)
        with self._no_gateway():
            response = self._checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn("billing", response["Location"])
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())
        self.assertFalse(PlatformCouponRedemption.objects.exists())

    def test_no_coupon_positive_amount_without_gateway_is_still_refused(self):
        with self._no_gateway():
            self._checkout()
        self.assertFalse(SubscriptionInvoice.objects.filter(store=self.store).exists())

    def test_repeat_submit_reuses_the_invoice_and_never_duplicates_the_redemption(self):
        from apps.billing.models import PlatformCouponRedemption
        from apps.billing.services import platform_coupon_service as svc

        svc.create_coupon(actor=self._staff(), name="reuse-auto", code=None, is_automatic=True, kind="percent", percent=20)
        first = self._checkout()
        second = self._checkout()                                   # double click / browser retry
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 1)
        invoice = SubscriptionInvoice.objects.get(store=self.store)
        self.assertEqual(PlatformCouponRedemption.objects.filter(invoice=invoice).count(), 1)
        self.assertEqual(invoice.discount_total, invoice.subtotal * 20 // 100)
        self.assertEqual(invoice.amount_due, invoice.subtotal - invoice.discount_total)

    def test_refused_reuse_without_gateway_leaves_the_existing_discounted_invoice_untouched(self):
        from apps.billing.models import PlatformCouponRedemption
        from apps.billing.services import platform_coupon_service as svc

        svc.create_coupon(actor=self._staff(), name="reuse-keep", code=None, is_automatic=True, kind="percent", percent=20)
        self._checkout()
        before = SubscriptionInvoice.objects.get(store=self.store)
        snapshot = (before.discount_total, before.amount_due, before.status)
        with self._no_gateway():
            self._checkout()                                        # gateways vanished between the two submits
        after = SubscriptionInvoice.objects.get(store=self.store)
        self.assertEqual((after.discount_total, after.amount_due, after.status), snapshot)
        self.assertEqual(PlatformCouponRedemption.objects.filter(invoice=after).count(), 1)
        self.assertEqual(PlatformCouponRedemption.objects.get(invoice=after).status, "reserved")
