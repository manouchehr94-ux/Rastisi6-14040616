"""Section 10 — step-up OTP enforcement, wired concretely into the one
sensitive action Section 9 already built: subscription purchase. Uses the
real (default-enabled) PlatformConfiguration.step_up_actions policy, unlike
test_billing_views.py which explicitly disables it to isolate checkout
mechanics. Since the technical-consolidation pass (ADR-105/ADR-106), the
purchase itself goes through apps.billing (plan_change_billing_service +
payment_flow_service) instead of a portal-only billing layer."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice
from apps.portal.models import OwnerProfile
from apps.portal.tests._owner_signup import age_otp_cooldown
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service

User = get_user_model()
_HOST = "rastisi.localhost"


def _fixed_code():
    import apps.portal.services.owner_otp_service as svc

    original = svc._generate_code
    svc._generate_code = lambda: "778899"
    return original, "778899"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class StepUpBillingTests(TestCase):
    def setUp(self):
        cache.clear()  # OTP rate-limit counters are cache-backed and leak across tests otherwise
        self.store = Store.objects.create(
            name="فروشگاه تأیید گام‌دوم", slug="step-up-store", admin_subdomain="step-up-store",
        )
        self.owner = User.objects.create_user(username="09121250011", password="a-very-strong-pass-1")
        OwnerProfile.objects.create(user=self.owner, phone="09121250011", full_name="مالک")
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        trial_plan = Plan.objects.create(code="trial-stepup", name="Trial", is_publicly_selectable=True)
        trial_version = PlanVersion.objects.create(
            plan=trial_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.NONE, display_price=0, trial_days=14,
        )
        sub = subscription_service.create_subscription(self.store, trial_version, actor=self.owner)
        subscription_service.start_trial(sub, actor=self.owner)

        self.plan = Plan.objects.create(code="pro-stepup", name="Pro", is_active=True, is_publicly_selectable=True)
        self.version = PlanVersion.objects.create(
            plan=self.plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            billing_interval=PlanVersion.BillingInterval.MONTHLY, display_price=490_000,
        )
        self.client.force_login(self.owner)

        import apps.portal.services.owner_otp_service as svc
        original, self.code = _fixed_code()
        self.addCleanup(setattr, svc, "_generate_code", original)

    def _checkout(self):
        return self.client.post(
            f"/app/stores/{self.store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=_HOST,
        )

    def test_checkout_is_gated_behind_step_up_by_default(self):
        response = self._checkout()
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/billing/step-up/")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)

    def test_owner_without_a_phone_cannot_purchase_at_all(self):
        self.owner.owner_profile.delete()
        response = self._checkout()
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/billing/")
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)

    def test_wrong_code_does_not_create_an_invoice(self):
        self._checkout()
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/billing/step-up/", {"code": "000000"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)

    def test_correct_code_completes_the_purchase_and_reaches_return_page(self):
        self._checkout()
        response = self.client.post(
            f"/app/stores/{self.store.public_id}/billing/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/app/stores/{self.store.public_id}/billing/return/", response["Location"])
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 1)

    def test_step_up_stays_verified_for_a_second_purchase_on_the_same_store(self):
        self._checkout()
        self.client.post(
            f"/app/stores/{self.store.public_id}/billing/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        # A second checkout on the same Store, still within the verified
        # window, must not require another OTP round-trip.
        response = self._checkout()
        self.assertIn(f"/app/stores/{self.store.public_id}/billing/return/", response["Location"])

    def test_step_up_verification_does_not_carry_over_to_a_different_store(self):
        self._checkout()
        self.client.post(
            f"/app/stores/{self.store.public_id}/billing/step-up/", {"code": self.code}, HTTP_HOST=_HOST,
        )
        # a verified step-up code does not release the send cooldown early; a new code for another store is only
        # requested once the 120 s window since the first request has passed
        age_otp_cooldown(self.owner.username)
        other_store = Store.objects.create(
            name="فروشگاه دیگرِ گام‌دوم", slug="step-up-other-store", admin_subdomain="step-up-other-store",
        )
        StoreMembership.objects.create(
            store=other_store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        response = self.client.post(
            f"/app/stores/{other_store.public_id}/billing/checkout/{self.version.pk}/", HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, f"/app/stores/{other_store.public_id}/billing/step-up/")

    def test_step_up_page_requires_a_pending_challenge_for_this_store(self):
        response = self.client.get(
            f"/app/stores/{self.store.public_id}/billing/step-up/", HTTP_HOST=_HOST,
        )
        self.assertRedirects(response, f"/app/stores/{self.store.public_id}/billing/")
