"""INTEGRATION of PR #40 (platform gateway checkout) with the pricing branch (billing periods).
Neither branch alone has this test: it proves that gateway choice and the purchased period travel together through
checkout → platform gateway → verified callback → activation → renewal, and through the OTP step-up continuation."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.services import renewal_service
from apps.billing.tests.platform_payment_support import patch_zibal, ready_platform_zibal
from apps.portal.models import OwnerProfile
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import plan_service as ps
from apps.subscriptions.services import subscription_service

User = get_user_model()
HOST = "rastisi.localhost"


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir", ALLOWED_HOSTS=[HOST, "testserver"], RASTISI_BILLING_PROVIDER="manual")
class GatewayAndPeriodTogetherTests(TestCase):
    MONTHLY, YEARLY = 100_000, 1_000_000

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": False})
        self.store = Store.objects.create(name="فروشگاه ترکیبی", slug="combo-store", admin_subdomain="combo-store")
        self.owner = User.objects.create_user(username="09121250011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121250011", full_name="مالک")
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        trial = Plan.objects.create(code="combo-trial", name="Trial")
        tv = PlanVersion.objects.create(plan=trial, version_number=1, status="published", billing_interval="none", display_price=0, trial_days=14)
        self.subscription = subscription_service.start_trial(subscription_service.create_subscription(self.store, tv, actor=self.owner), actor=self.owner)
        plan = Plan.objects.create(code="combo-pro", name="Pro")
        v = ps.create_plan_version(plan, display_price=self.MONTHLY, billing_interval="monthly")
        ps.set_version_price(v, "yearly", price=self.YEARLY)
        self.version = ps.publish_plan_version(v)
        self.fake = patch_zibal(self)
        ready_platform_zibal(self)
        self.client.force_login(self.owner)

    def checkout(self, **data):
        return self.client.post(f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", data, HTTP_HOST=HOST)

    def test_yearly_period_paid_through_the_platform_gateway_activates_for_a_year_and_renews_yearly(self):
        response = self.checkout(gateway="zibal", billing_interval="yearly")
        self.assertEqual(response.status_code, 302)
        attempt = SubscriptionPaymentAttempt.objects.get(store=self.store)
        invoice = attempt.invoice
        self.assertEqual((attempt.provider, invoice.grand_total), ("zibal", Decimal(self.YEARLY)))
        self.assertEqual(invoice.lines.get().plan_version_snapshot["billing_interval"], "yearly")
        sent = self.fake.calls_to("request")[0]
        self.assertEqual(sent["amount"], self.YEARLY * 10)                             # the YEARLY price (rial), not the monthly one
        self.assertEqual(StoreSubscription.objects.get(pk=self.subscription.pk).status, "trialing")
        self.fake.paid(amount_rial=self.YEARLY * 10, order_id=attempt.public_token)
        cache.clear()
        self.client.get(f"/billing/return/{attempt.public_token}/?success=1&status=2&trackId=777", HTTP_HOST=HOST)
        sub = StoreSubscription.objects.get(pk=self.subscription.pk)
        self.assertEqual((sub.status, sub.plan_version_id, sub.billing_interval), ("active", self.version.pk, "yearly"))
        self.assertGreaterEqual((sub.current_period_end - sub.current_period_start).days, 364)
        StoreSubscription.objects.filter(pk=sub.pk).update(current_period_end=timezone.now() + timedelta(days=1))
        renewal_service.generate_renewals(lead_days=3)
        renewal = SubscriptionInvoice.objects.get(subscription=sub, kind="renewal")
        self.assertEqual(renewal.grand_total, Decimal(self.YEARLY))

    def test_amount_mismatch_between_period_price_and_gateway_never_activates(self):
        self.checkout(gateway="zibal", billing_interval="yearly")
        attempt = SubscriptionPaymentAttempt.objects.get(store=self.store)
        self.fake.paid(amount_rial=self.MONTHLY * 10, order_id=attempt.public_token)       # paid the monthly price for a yearly invoice
        cache.clear()
        self.client.get(f"/billing/return/{attempt.public_token}/?success=1&status=2&trackId=777", HTTP_HOST=HOST)
        self.assertNotEqual(StoreSubscription.objects.get(pk=self.subscription.pk).status, "active")

    def test_step_up_continuation_keeps_both_the_gateway_and_the_period(self):
        update_platform_configuration(actor=None, step_up_actions={"subscription_purchase_confirm": True})
        response = self.checkout(gateway="zibal", billing_interval="yearly")
        self.assertTrue(response["Location"].endswith("/billing/step-up/"))
        session = self.client.session
        self.assertEqual(session["portal_pending_purchase_gateway"], "zibal")
        self.assertEqual(session["portal_pending_purchase_interval"], "yearly")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)       # nothing is created before the OTP
