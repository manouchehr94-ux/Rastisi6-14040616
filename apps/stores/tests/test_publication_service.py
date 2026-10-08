from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreDomain
from apps.stores.services.platform_code_service import generate_unique_platform_code
from apps.stores.services.publication_service import (
    NON_PUBLIC_STATES,
    PublicationState,
    get_store_publication_state,
    is_publicly_visible,
)
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription


def _make_store(**kwargs):
    kwargs.setdefault("name", "Pub Store")
    kwargs.setdefault("slug", f"pub-store-{Store.objects.count()}")
    kwargs.setdefault("status", Store.Status.ACTIVE)
    kwargs.setdefault("platform_code", generate_unique_platform_code())
    return Store.objects.create(**kwargs)


def _make_subscription(store, *, status, trial_end_at=None):
    plan = Plan.objects.create(code=f"plan-{Store.objects.count()}", name="Test Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
    )
    return StoreSubscription.objects.create(
        store=store, plan_version=version, status=status, is_current=True, trial_end_at=trial_end_at,
    )


class PublicationStateNoSubscriptionTests(TestCase):
    def test_store_with_no_subscription_is_publicly_visible_fail_open(self):
        store = _make_store()
        self.assertTrue(is_publicly_visible(store))
        self.assertEqual(get_store_publication_state(store), PublicationState.ACTIVE_PAID)

    def test_provisioning_status_is_never_public_even_without_subscription(self):
        store = _make_store(status=Store.Status.PROVISIONING)
        self.assertFalse(is_publicly_visible(store))
        self.assertEqual(get_store_publication_state(store), PublicationState.ONBOARDING)

    def test_suspended_store_is_never_public(self):
        store = _make_store(status=Store.Status.SUSPENDED)
        self.assertFalse(is_publicly_visible(store))
        self.assertEqual(get_store_publication_state(store), PublicationState.SUSPENDED)

    def test_closed_store_is_inactive(self):
        store = _make_store(status=Store.Status.CLOSED)
        self.assertEqual(get_store_publication_state(store), PublicationState.INACTIVE)


class OnboardingRequiredGateTests(TestCase):
    """``onboarding_required_at`` = the durable "modern portal Store" signal. Such a Store is private
    until the final Publish whatever the subscription says; Stores without the signal are untouched."""

    def test_modern_store_without_any_subscription_is_private_until_onboarding_completes(self):
        store = _make_store(onboarding_required_at=timezone.now())
        self.assertEqual(get_store_publication_state(store), PublicationState.TRIAL_PRIVATE)
        self.assertFalse(is_publicly_visible(store))

    def test_after_onboarding_completes_the_normal_no_subscription_policy_applies_unchanged(self):
        store = _make_store(onboarding_required_at=timezone.now(), onboarding_completed_at=timezone.now())
        self.assertEqual(get_store_publication_state(store), PublicationState.ACTIVE_PAID)
        self.assertTrue(is_publicly_visible(store))

    def test_modern_store_with_a_subscription_stays_private_then_follows_the_normal_policy(self):
        store = _make_store(onboarding_required_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.TRIALING, trial_end_at=timezone.now())
        self.assertEqual(get_store_publication_state(store), PublicationState.TRIAL_PRIVATE)
        store.onboarding_completed_at = timezone.now()
        self.assertEqual(get_store_publication_state(store), PublicationState.TRIAL_PUBLIC)

    def test_a_restricted_subscription_is_still_reported_as_restricted(self):
        store = _make_store(onboarding_required_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.SUSPENDED)
        self.assertEqual(get_store_publication_state(store), PublicationState.RESTRICTED)

    def test_lifecycle_statuses_still_win_over_the_gate(self):
        for status, expected in (
            (Store.Status.SUSPENDED, PublicationState.SUSPENDED),
            (Store.Status.CLOSED, PublicationState.INACTIVE),
            (Store.Status.PROVISIONING, PublicationState.ONBOARDING),
        ):
            with self.subTest(status=status):
                store = _make_store(status=status, onboarding_required_at=timezone.now())
                self.assertEqual(get_store_publication_state(store), expected)

    def test_a_legacy_store_with_no_signal_is_not_made_private(self):
        """No ``onboarding_required_at`` + no subscription + onboarding never completed = a true legacy /
        ad-hoc Store: it must remain exactly as it was (ADR-65 fail-open)."""
        store = _make_store()
        self.assertIsNone(store.onboarding_required_at)
        self.assertIsNone(store.onboarding_completed_at)
        self.assertEqual(get_store_publication_state(store), PublicationState.ACTIVE_PAID)
        self.assertTrue(is_publicly_visible(store))

    def test_the_field_is_nullable_with_no_default_so_history_is_never_fabricated(self):
        field = Store._meta.get_field("onboarding_required_at")
        self.assertTrue(field.null)
        self.assertFalse(field.has_default())


class PublicationStateWithSubscriptionTests(TestCase):
    def test_trialing_subscription_without_onboarding_is_trial_private(self):
        store = _make_store()
        _make_subscription(store, status=StoreSubscription.Status.TRIALING, trial_end_at=timezone.now())
        self.assertEqual(get_store_publication_state(store), PublicationState.TRIAL_PRIVATE)
        self.assertFalse(is_publicly_visible(store))

    def test_trialing_subscription_with_onboarding_complete_is_trial_public(self):
        store = _make_store(onboarding_completed_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.TRIALING, trial_end_at=timezone.now())
        self.assertEqual(get_store_publication_state(store), PublicationState.TRIAL_PUBLIC)
        self.assertTrue(is_publicly_visible(store))

    def test_active_paid_subscription_with_onboarding_complete_is_active_paid(self):
        store = _make_store(onboarding_completed_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.ACTIVE)
        self.assertEqual(get_store_publication_state(store), PublicationState.ACTIVE_PAID)
        self.assertTrue(is_publicly_visible(store))

    def test_suspended_subscription_is_restricted(self):
        store = _make_store(onboarding_completed_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.SUSPENDED)
        self.assertEqual(get_store_publication_state(store), PublicationState.RESTRICTED)
        self.assertFalse(is_publicly_visible(store))

    def test_expired_subscription_is_restricted(self):
        store = _make_store(onboarding_completed_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.EXPIRED)
        self.assertEqual(get_store_publication_state(store), PublicationState.RESTRICTED)
        self.assertFalse(is_publicly_visible(store))

    def test_restricted_overrides_incomplete_onboarding(self):
        store = _make_store()  # onboarding NOT complete
        _make_subscription(store, status=StoreSubscription.Status.SUSPENDED)
        self.assertEqual(get_store_publication_state(store), PublicationState.RESTRICTED)


class NonPublicStatesConsistencyTests(TestCase):
    def test_every_non_public_state_is_actually_flagged_not_visible(self):
        for state in NON_PUBLIC_STATES:
            self.assertIn(state, PublicationState.values)


@override_settings(ALLOWED_HOSTS=["pub-test.example.com", "testserver"])
class ResolveStoreForStorefrontRestrictionTests(TestCase):
    def test_trial_private_store_403s_with_explanation(self):
        store = _make_store(slug="restricted-storefront")
        _make_subscription(store, status=StoreSubscription.Status.TRIALING, trial_end_at=timezone.now())
        StoreDomain.objects.create(
            store=store, hostname="pub-test.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        response = self.client.get("/", HTTP_HOST="pub-test.example.com")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "در دسترسِ عمومی نیست", status_code=403)

    def test_publicly_visible_store_renders_normally(self):
        store = _make_store(slug="public-storefront", onboarding_completed_at=timezone.now())
        _make_subscription(store, status=StoreSubscription.Status.ACTIVE)
        StoreDomain.objects.create(
            store=store, hostname="pub-test.example.com", is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        response = self.client.get("/", HTTP_HOST="pub-test.example.com")
        self.assertEqual(response.status_code, 200)
