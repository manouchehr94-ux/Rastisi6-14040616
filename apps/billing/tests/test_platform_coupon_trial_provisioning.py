"""First-paid-purchase eligibility for stores provisioned through the REAL Trial engine
(``trial_service.grant_initial_trial``), not through the hand-built subscriptions used by the coupon tests.

Covers: running Trial, expired Trial, and Trial disabled by the platform (never-started, suspended)."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.services import platform_coupon_service as svc
from apps.stores.models import Store
from apps.subscriptions.models import StoreSubscription
from apps.subscriptions.services import subscription_service as ss
from apps.subscriptions.services import trial_service
from apps.subscriptions.tests.test_pricing_dynamic import make_plan


class TrialProvisioningPurposeTests(TestCase):
    def setUp(self):
        _p, self.paid_v = make_plan("trprov-paid", base=300000, order=5)

    def _store(self, slug):
        return Store.objects.create(name=slug, slug=slug, admin_subdomain=slug, status=Store.Status.ACTIVE)

    def test_running_trial_granted_by_engine_is_initial_purchase(self):
        store = self._store("trprov-run")
        sub = trial_service.grant_initial_trial(store)
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertEqual(svc.purpose_for(store, "plan_change"), "initial")

    def test_expired_trial_is_still_initial_purchase(self):
        """Runs the REAL subscription-state evaluator (the scheduled job) instead of assuming what expiry does."""
        store = self._store("trprov-exp")
        sub = trial_service.grant_initial_trial(store)
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        result = ss.evaluate_subscription_states()
        self.assertGreaterEqual(result["scanned"], 1)
        current = StoreSubscription.objects.get(pk=sub.pk)
        # the evaluator really moved it: it is no longer TRIALING, yet it stays the current, non-terminal row (so it can buy)
        self.assertNotEqual(current.status, StoreSubscription.Status.TRIALING)
        self.assertEqual(current.status, StoreSubscription.Status.SUSPENDED)
        self.assertTrue(current.is_current)
        self.assertNotIn(current.status, StoreSubscription.TERMINAL_STATUSES)
        self.assertEqual(svc.purpose_for(store, "plan_change"), "initial")

    def test_trial_disabled_by_platform_store_buying_first_plan_is_initial_purchase(self):
        from unittest import mock

        store = self._store("trprov-off")
        with mock.patch.object(trial_service, "current_policy", return_value=trial_service.TrialPolicy(enabled=False, days=30)):
            sub = trial_service.grant_initial_trial(store)
        self.assertIsNotNone(sub)
        self.assertNotIn(sub.status, StoreSubscription.TERMINAL_STATUSES)           # still current, so the store can buy
        self.assertTrue(sub.is_current)
        # never-started Trial: no TRIAL_STARTED event exists, status is suspended
        self.assertEqual(svc.purpose_for(store, "plan_change", subscription=sub), "initial",
                         f"status={sub.status!r}: a store that never bought anything and is buying its first plan "
                         f"must be an initial purchase")
