"""Checkpoint 5A commit 9: management commands (evaluate_subscription_states,
verify_subscription_consistency, provision_legacy_subscriptions), default-plan
provisioning for new stores, and subscription/entitlement tenant isolation."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
    StoreSubscription,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import subscription_service as svc


def _version(code, *, trial_days=0, grace_days=0, products=None, publicly=True):
    plan = Plan.objects.create(code=code, name=code, is_publicly_selectable=publicly)
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        trial_days=trial_days, grace_period_days=grace_days,
    )
    if products is not None:
        PlanEntitlement.objects.create(
            plan_version=version,
            entitlement=EntitlementDefinition.objects.get(key=ekeys.CATALOG_PRODUCTS),
            is_enabled=True, integer_limit=products,
        )
    return version


class ProvisionLegacyCommandTests(TestCase):
    def test_idempotent_and_covers_new_store(self):
        ent.clear_entitlement_cache()
        store = Store.objects.create(name="ف", slug="legacy-cmd", admin_subdomain="legacy-cmd")
        self.assertIsNone(ent.get_current_subscription(store))
        call_command("provision_legacy_subscriptions", stdout=StringIO())
        sub = ent.get_current_subscription(store)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.source, StoreSubscription.Source.LEGACY)
        # Legacy = unlimited products.
        self.assertIsNone(ent.get_entitlement_limit(store, ekeys.CATALOG_PRODUCTS))
        # Running again creates nothing new.
        count_before = StoreSubscription.objects.count()
        call_command("provision_legacy_subscriptions", stdout=StringIO())
        self.assertEqual(StoreSubscription.objects.count(), count_before)


class EvaluateStatesCommandTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="eval-store", admin_subdomain="eval-store")

    def test_trial_expiry_moves_to_grace(self):
        version = _version("eval-trial", trial_days=7, grace_days=3)
        sub = svc.create_subscription(self.store, version)
        svc.start_trial(sub)
        results = svc.evaluate_subscription_states(now=timezone.now() + timedelta(days=8))
        self.assertEqual(results["grace"], 1)
        self.assertEqual(ent.get_current_subscription(self.store).status, StoreSubscription.Status.GRACE_PERIOD)

    def test_grace_expiry_suspends(self):
        version = _version("eval-grace", grace_days=3)
        sub = svc.create_subscription(self.store, version)
        svc.activate_subscription(sub)
        svc.enter_grace_period(sub)  # grace_end = now + 3d
        results = svc.evaluate_subscription_states(now=timezone.now() + timedelta(days=4))
        self.assertEqual(results["suspended"], 1)
        self.assertEqual(ent.get_current_subscription(self.store).status, StoreSubscription.Status.SUSPENDED)

    def test_scheduled_cancel_fires_at_period_end(self):
        version = _version("eval-cancel")
        sub = svc.create_subscription(self.store, version)
        past = timezone.now() - timedelta(days=1)
        svc.activate_subscription(sub, period_end=past)
        svc.cancel_at_period_end(sub)
        results = svc.evaluate_subscription_states(now=timezone.now())
        self.assertEqual(results["cancelled"], 1)
        current = svc.StoreSubscription.objects.get(pk=sub.pk)
        self.assertEqual(current.status, StoreSubscription.Status.CANCELLED)
        self.assertFalse(current.is_current)

    def test_dry_run_changes_nothing(self):
        version = _version("eval-dry", trial_days=1, grace_days=1)
        sub = svc.create_subscription(self.store, version)
        svc.start_trial(sub)
        results = svc.evaluate_subscription_states(now=timezone.now() + timedelta(days=5), dry_run=True)
        self.assertEqual(results["grace"], 1)
        # Nothing was actually transitioned.
        self.assertEqual(ent.get_current_subscription(self.store).status, StoreSubscription.Status.TRIALING)


class VerifyConsistencyCommandTests(TestCase):
    def test_clean_state_passes(self):
        # akhlaghi has a valid legacy subscription from migration.
        out = StringIO()
        call_command("verify_subscription_consistency", stdout=out)
        self.assertIn("ناسازگاری", out.getvalue())

    def test_terminal_current_subscription_is_flagged(self):
        store = Store.objects.create(name="ف", slug="verify-store", admin_subdomain="verify-store")
        version = _version("verify-plan")
        sub = svc.create_subscription(store, version)
        # Force an inconsistent row: terminal status but still is_current.
        StoreSubscription.objects.filter(pk=sub.pk).update(
            status=StoreSubscription.Status.EXPIRED, is_current=True,
        )
        issues = svc.check_subscription_consistency()
        self.assertTrue(any(i["severity"] == "error" for i in issues))
        with self.assertRaises(CommandError):
            call_command("verify_subscription_consistency", stdout=StringIO(), stderr=StringIO())


@override_settings(RASTISI_DEFAULT_PLAN_CODE="starter-default")
class DefaultPlanProvisioningTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.version = _version("starter-default", trial_days=14, grace_days=3, products=10)

    def test_new_store_gets_default_trial(self):
        store = Store.objects.create(name="ف", slug="def-store", admin_subdomain="def-store")
        sub = svc.provision_default_subscription(store)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.source, StoreSubscription.Source.DEFAULT)
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)

    def test_idempotent(self):
        store = Store.objects.create(name="ف", slug="def-store-2", admin_subdomain="def-store-2")
        first = svc.provision_default_subscription(store)
        second = svc.provision_default_subscription(store)
        self.assertEqual(first.pk, second.pk)

    @override_settings(RASTISI_DEFAULT_PLAN_START_TRIAL=False)
    def test_can_start_active_instead_of_trial(self):
        store = Store.objects.create(name="ف", slug="def-store-3", admin_subdomain="def-store-3")
        sub = svc.provision_default_subscription(store)
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)


@override_settings(RASTISI_DEFAULT_PLAN_CODE="")
class NoDefaultPlanTests(TestCase):
    @override_settings(RASTISI_DEFAULT_PLAN_CODE="none")
    def test_explicit_opt_out_creates_no_subscription_legacy_fail_open(self):
        store = Store.objects.create(name="ف", slug="optout-store", admin_subdomain="optout-store")
        self.assertIsNone(svc.provision_default_subscription(store))

    def test_no_default_configured_now_means_the_platform_initial_trial(self):
        """Before the Trial engine an unset default plan left a new store with NO subscription (= unlimited, fail-open). Now an unset
        ``RASTISI_DEFAULT_PLAN_CODE`` means «the internal Trial plan» (see ``trial_service``)."""
        store = Store.objects.create(name="ف", slug="nodef-store", admin_subdomain="nodef-store")
        sub = svc.provision_default_subscription(store)
        self.assertEqual((sub.plan_version.plan.code, sub.status), ("trial", "trialing"))


class TenantIsolationTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store_a = Store.objects.create(name="A", slug="iso-a", admin_subdomain="iso-a")
        self.store_b = Store.objects.create(name="B", slug="iso-b", admin_subdomain="iso-b")
        self.small = _version("iso-small", products=5)
        self.big = _version("iso-big", products=500)
        for store, version in ((self.store_a, self.small), (self.store_b, self.big)):
            sub = svc.create_subscription(store, version)
            svc.activate_subscription(sub)
        ent.clear_entitlement_cache()

    def test_each_store_sees_only_its_own_subscription(self):
        self.assertEqual(ent.get_effective_plan_version(self.store_a).pk, self.small.pk)
        self.assertEqual(ent.get_effective_plan_version(self.store_b).pk, self.big.pk)
        self.assertEqual(ent.get_entitlement_limit(self.store_a, ekeys.CATALOG_PRODUCTS), 5)
        self.assertEqual(ent.get_entitlement_limit(self.store_b, ekeys.CATALOG_PRODUCTS), 500)

    def test_changing_one_store_plan_does_not_touch_the_other(self):
        svc.change_plan_version(ent.get_current_subscription(self.store_a), self.big)
        ent.clear_entitlement_cache()
        # Store B's subscription is untouched.
        self.assertEqual(ent.get_effective_plan_version(self.store_b).pk, self.big.pk)
        self.assertEqual(
            StoreSubscription.objects.filter(store=self.store_b, is_current=True).count(), 1,
        )
