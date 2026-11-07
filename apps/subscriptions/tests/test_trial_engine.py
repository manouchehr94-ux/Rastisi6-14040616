"""Initial Trial engine (2026-11-07): default length from the platform setting, one Trial per store, the internal non-purchasable Trial plan, real
limits and post-expiry policy. Everything synthetic; PostgreSQL for the concurrency class."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.portal.models import PlatformAuditLogEntry
from apps.portal.services import provisioning_service
from apps.portal.services.platform_config_service import update_platform_configuration
from apps.stores.models import Store
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import enforcement, entitlement_service as ent, pricing_page_service, subscription_service as ss, trial_service
from apps.subscriptions.tests.test_pricing_dynamic import make_plan

User = get_user_model()


def new_store(name="فروشگاه آزمایشی", username=None):
    owner = User.objects.create_user(username=username or f"own-{User.objects.count()}@example.com", password="pass-12345-x")
    return provisioning_service.provision_trial_store(owner=owner, name=name), owner


def configure(*, days=None, enabled=None):
    staff, _ = User.objects.get_or_create(username="trial-cfg@example.com", defaults={"is_staff": True, "is_superuser": True})
    fields = {}
    if days is not None:
        fields["default_trial_days"] = days
    if enabled is not None:
        fields["trial_enabled"] = enabled
    return update_platform_configuration(actor=staff, **fields)


class InitialTrialGrantTests(TestCase):
    def test_a_new_store_gets_the_default_30_day_trial_on_the_internal_trial_plan(self):
        store, _owner = new_store()
        sub = ent.get_current_subscription(store)
        self.assertEqual(sub.plan_version.plan.code, trial_service.TRIAL_PLAN_CODE)
        self.assertEqual(sub.status, StoreSubscription.Status.TRIALING)
        self.assertEqual((sub.trial_end_at - sub.trial_start_at).days, 30)
        self.assertEqual(sub.source, StoreSubscription.Source.DEFAULT)
        self.assertTrue(SubscriptionEvent.objects.filter(subscription=sub, event_type="trial_started").exists())

    def test_changing_the_default_affects_only_stores_created_afterwards(self):
        old_store, _ = new_store("قدیمی")
        old_end = ent.get_current_subscription(old_store).trial_end_at
        configure(days=14)
        fresh_store, _ = new_store("تازه")
        fresh = ent.get_current_subscription(fresh_store)
        self.assertEqual((fresh.trial_end_at - fresh.trial_start_at).days, 14)
        self.assertEqual(ent.get_current_subscription(old_store).trial_end_at, old_end)           # a running trial is never rewritten
        configure(days=60)
        self.assertEqual(ent.get_current_subscription(old_store).trial_end_at, old_end)
        self.assertEqual((ent.get_current_subscription(fresh_store).trial_end_at - fresh.trial_start_at).days, 14)

    def test_the_duration_is_read_live_not_from_the_cached_configuration(self):
        from apps.portal.services.platform_config_service import get_platform_configuration

        get_platform_configuration()                                   # warm the 5-minute cache
        configure(days=7)
        store, _ = new_store()
        self.assertEqual((ent.get_current_subscription(store).trial_end_at - timezone.now()).days, 6)   # 7 days minus the elapsed instant

    def test_disabled_trial_creates_no_trial_and_the_store_must_buy(self):
        configure(enabled=False)
        store, _ = new_store()
        sub = ent.get_current_subscription(store)
        self.assertIsNotNone(sub)
        self.assertIsNone(sub.trial_start_at)
        self.assertEqual(sub.status, StoreSubscription.Status.SUSPENDED)         # restricted but NON-terminal: the store can still buy
        self.assertTrue(sub.is_current)
        self.assertFalse(trial_service.store_has_used_trial(store))
        self.assertEqual(ent.get_subscription_access_state(store).state, ent.AccessState.RESTRICTED)
        info = trial_service.trial_info(store)
        self.assertEqual((info["state"], info.get("never_started")), ("ended", True))
        self.assertTrue(Store.objects.filter(pk=store.pk).exists())     # nothing deleted

    def test_a_chosen_paid_plan_never_grants_a_second_or_different_trial(self):
        _plan, paid = make_plan("paid-with-trial", base=300000, trial=14, order=3)       # an old per-plan trial_days must not matter any more
        owner = User.objects.create_user(username="chooser@example.com", password="pass-12345-x")
        store = provisioning_service.provision_trial_store(owner=owner, name="انتخاب", plan_version=paid)
        sub = ent.get_current_subscription(store)
        self.assertEqual(sub.plan_version.plan.code, "trial")             # still the independent initial trial …
        self.assertEqual((sub.trial_end_at - sub.trial_start_at).days, 30)    # … of the platform length, not the paid plan's 14
        self.assertEqual(StoreSubscription.objects.filter(store=store).count(), 1)

    def test_one_trial_per_store_even_after_it_ends_or_is_cancelled(self):
        store, _ = new_store()
        sub = ent.get_current_subscription(store)
        self.assertEqual(trial_service.grant_initial_trial(store).pk, sub.pk)                  # idempotent while it exists
        ss.cancel_immediately(sub, reason="test")
        self.assertIsNone(ent.get_current_subscription(store))
        self.assertTrue(trial_service.store_has_used_trial(store))
        self.assertFalse(trial_service.is_eligible(store))
        self.assertIsNone(trial_service.grant_initial_trial(store))                            # no second trial
        self.assertIsNone(ss.provision_default_subscription(store))
        self.assertEqual(StoreSubscription.objects.filter(store=store, trial_start_at__isnull=False).count(), 1)

    def test_a_converted_store_cannot_get_another_trial(self):
        _p, paid = make_plan("conv-paid", base=100000, order=2)
        store, _ = new_store()
        sub = ent.get_current_subscription(store)
        ss.change_plan_version(sub, paid)
        ss.activate_subscription(sub, period_end=timezone.now() + timedelta(days=30))
        ss.cancel_immediately(sub, reason="x")
        self.assertIsNone(trial_service.grant_initial_trial(store))

    def test_the_audit_trail_records_grant_and_the_platform_side_change(self):
        configure(days=21)
        entry = PlatformAuditLogEntry.objects.filter(action_code="platform_configuration.updated").latest("pk")
        self.assertIn("21", entry.after_summary)
        store, _ = new_store()
        from apps.core.models import AuditLogEntry

        self.assertTrue(AuditLogEntry.objects.filter(store=store, action_code="trial.granted").exists())

    def test_days_validation(self):
        for bad in (0, -1, 366, "x", None, "3.5"):
            with self.subTest(bad=bad):
                with self.assertRaises(trial_service.TrialPolicyError):
                    trial_service.validate_days(bad)
        self.assertEqual(trial_service.validate_days("30"), 30)
        self.assertEqual(trial_service.validate_days(365), 365)


class InternalTrialPlanTests(TestCase):
    def setUp(self):
        trial_service.ensure_trial_plan()
        self.paid_plan, self.paid = make_plan("pub-paid", base=490000, order=2, extra={"quarterly": 1400000, "semiannual": 2700000, "yearly": 5000000})

    def test_the_trial_plan_is_internal_published_and_idempotent(self):
        plan = Plan.objects.get(code="trial")
        self.assertFalse(plan.is_publicly_selectable)
        self.assertTrue(plan.versions.filter(status="published").exists())
        before = plan.versions.count()
        trial_service.ensure_trial_plan()
        self.assertEqual(plan.versions.count(), before)

    def test_ensure_hides_a_previously_public_trial_plan_without_touching_versions(self):
        plan = Plan.objects.get(code="trial")
        Plan.objects.filter(pk=plan.pk).update(is_publicly_selectable=True)
        versions = list(plan.versions.values_list("pk", "version_number", "trial_days"))
        trial_service.ensure_trial_plan()
        plan.refresh_from_db()
        self.assertFalse(plan.is_publicly_selectable)
        self.assertEqual(list(plan.versions.values_list("pk", "version_number", "trial_days")), versions)

    def test_the_trial_plan_is_in_no_public_or_purchasable_list(self):
        self.assertNotIn("trial", [p.code for p, _v in pricing_page_service.offered_plans()])
        page = pricing_page_service.build_pricing_page()
        self.assertNotIn("trial", [c["plan"].code for c in page["cards"]])
        from apps.portal.public_site.plans import public_plan_rows

        self.assertNotIn("trial", [r["plan"].code for r in public_plan_rows()])
        self.assertIsNone(pricing_page_service.resolve_selection("trial"))
        trial_version = trial_service.trial_plan_version()
        self.assertFalse(pricing_page_service.is_purchasable_version(trial_version))
        self.assertTrue(pricing_page_service.is_purchasable_version(self.paid))

    def test_pricing_cards_show_the_platform_trial_length_and_hide_it_when_disabled(self):
        configure(days=45)
        self.assertTrue(all(c["trial_days"] == 45 for c in pricing_page_service.build_pricing_page()["cards"]))
        configure(enabled=False)
        self.assertTrue(all(c["trial_days"] == 0 for c in pricing_page_service.build_pricing_page()["cards"]))

    def test_older_or_unpublished_or_archived_versions_are_not_purchasable(self):
        v2 = PlanVersion.objects.create(plan=self.paid_plan, version_number=2, status="published", billing_interval="monthly", display_price=500000)
        self.assertFalse(pricing_page_service.is_purchasable_version(PlanVersion.objects.get(pk=self.paid.pk)))
        self.assertTrue(pricing_page_service.is_purchasable_version(v2))
        Plan.objects.filter(pk=self.paid_plan.pk).update(is_active=False)
        self.assertFalse(pricing_page_service.is_purchasable_version(PlanVersion.objects.get(pk=v2.pk)))


class TrialLimitsAreEnforcedTests(TestCase):
    """The Trial limits are ordinary entitlements of the published Trial version, enforced in the service layer (not only the UI)."""

    def setUp(self):
        self.store, self.owner = new_store()

    def test_the_default_limits_are_the_trial_versions(self):
        self.assertEqual(ent.get_entitlement_limit(self.store, ekeys.CATALOG_PRODUCTS), 20)
        self.assertEqual(ent.get_entitlement_limit(self.store, ekeys.CATALOG_VARIANTS), 60)
        self.assertEqual(ent.get_entitlement_limit(self.store, ekeys.STAFF_MEMBERS), 1)
        self.assertEqual(ent.get_entitlement_limit(self.store, ekeys.INVENTORY_WAREHOUSES), 1)

    def test_creating_products_is_blocked_at_the_trial_cap(self):
        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="v", slug="v")
        category = Category.objects.create(store=self.store, name="c", slug="c")
        for i in range(20):
            Product.objects.create(store=self.store, vendor=vendor, category=category, name=f"p{i}", slug=f"p{i}", sku=f"S{i}", price=1000, stock=1)
        with self.assertRaises(enforcement.UsageLimitExceeded):
            enforcement.enforce_can_create_product(self.store)

    def test_staff_and_warehouse_caps(self):
        with self.assertRaises(enforcement.UsageLimitExceeded):
            enforcement.enforce_can_add_staff(self.store, count=2)             # owner counts as 1 of 1 or the increment itself exceeds
        with self.assertRaises(enforcement.UsageLimitExceeded):
            enforcement.enforce_can_create_warehouse(self.store)                # the default warehouse already uses the single slot

    def test_a_disabled_boolean_feature_is_refused(self):
        with self.assertRaises(enforcement.FeatureNotAvailable):
            enforcement.enforce_feature(self.store, ekeys.CATALOG_IMPORT)

    def test_after_the_trial_ends_growth_is_closed_but_data_stays(self):
        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="v", slug="v")
        category = Category.objects.create(store=self.store, name="c", slug="c")
        Product.objects.create(store=self.store, vendor=vendor, category=category, name="p", slug="p", sku="S", price=1000, stock=1)
        sub = ent.get_current_subscription(self.store)
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()
        state = ent.get_subscription_access_state(self.store)
        self.assertEqual(state.state, ent.AccessState.RESTRICTED)
        self.assertTrue(ent.get_current_subscription(self.store).is_current)         # still buyable
        self.assertIn("دوره‌ی آزمایشی", state.message)
        with self.assertRaises(ent.SubscriptionRestricted):
            enforcement.enforce_can_create_product(self.store)
        self.assertEqual(Product.objects.filter(store=self.store).count(), 1)
        self.assertEqual(trial_service.trial_info(self.store)["state"], "ended")

    def test_a_grace_period_after_the_trial_keeps_growth_open_with_a_warning(self):
        sub = ent.get_current_subscription(self.store)
        PlanVersion.objects.filter(pk=sub.plan_version_id).update(grace_period_days=3)
        StoreSubscription.objects.filter(pk=sub.pk).update(trial_end_at=timezone.now() - timedelta(minutes=1))
        ss.evaluate_subscription_states()
        sub.refresh_from_db()
        self.assertEqual(sub.status, StoreSubscription.Status.GRACE_PERIOD)
        self.assertEqual(ent.get_subscription_access_state(self.store).state, ent.AccessState.GRACE)


class TrialInfoTests(TestCase):
    def test_states(self):
        store, _ = new_store()
        info = trial_service.trial_info(store)
        self.assertEqual(info["state"], "trialing")
        self.assertIn(info["days_left"], (29, 30))
        self.assertEqual(trial_service.trial_info(Store.objects.create(name="خالی", slug="empty", admin_subdomain="empty"))["state"], "none")

    def test_other_stores_trial_never_leaks(self):
        a, _ = new_store("الف")
        b = Store.objects.create(name="ب", slug="bbb", admin_subdomain="bbb")
        self.assertEqual(trial_service.trial_info(b)["state"], "none")
        self.assertEqual(trial_service.trial_info(a)["state"], "trialing")


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks")
class InitialTrialConcurrencyTests(TransactionTestCase):
    """N simultaneous provisioning attempts for the SAME store grant exactly one Trial (one subscription, one trial_started event)."""

    def test_eight_concurrent_grants_create_one_trial(self):
        owner = User.objects.create_user(username="conc-trial@example.com", password="pass-12345-x")
        store = Store.objects.create(name="هم‌زمان", slug="conc-trial", admin_subdomain="conc-trial")
        barrier = threading.Barrier(8)

        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return trial_service.grant_initial_trial(store, actor=owner).pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(worker, range(8)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(StoreSubscription.objects.filter(store=store).count(), 1)
        self.assertEqual(SubscriptionEvent.objects.filter(store=store, event_type="trial_started").count(), 1)
