"""Subscription grace/suspension notifications from the REAL state machine (``enter_grace_period`` / ``suspend_subscription`` / ``evaluate_subscription_states``).
One notification per real transition; none for repeated runs or rolled-back transitions; tenant- and permission-scoped. Billing/entitlement rules are not touched."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.dashboard.tests.test_permission_enforcement import _user_with_role
from apps.notifications import registry as R
from apps.notifications.models import InboxItem, NotificationEvent
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import subscription_service as svc

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="فروشگاه اشتراک", slug="sg-store", admin_subdomain="sg-store")
        self.other = Store.objects.create(name="دیگر", slug="sg-other", admin_subdomain="sg-other")
        self.owner = _user_with_role(self.store, "sg-owner", StoreMembership.Role.OWNER)
        self.admin = _user_with_role(self.store, "sg-admin", StoreMembership.Role.ADMINISTRATOR)
        self.analyst = _user_with_role(self.store, "sg-analyst", StoreMembership.Role.ANALYST)
        self.order_mgr = _user_with_role(self.store, "sg-om", StoreMembership.Role.ORDER_MANAGER)
        self.other_owner = _user_with_role(self.other, "sg-other-owner", StoreMembership.Role.OWNER)
        self.staff = User.objects.create_user(username="sg-platform", password="x", is_staff=True, is_superuser=True)
        plan = Plan.objects.create(code="pro", name="Pro")
        self.version = PlanVersion.objects.create(plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED, trial_days=14, grace_period_days=7)

    def active(self, period_end=None):
        sub = svc.create_subscription(self.store, self.version, actor=self.staff)
        sub = svc.start_trial(sub, actor=self.staff)
        return svc.activate_subscription(sub, actor=self.staff, period_end=period_end)

    def ev(self, key):
        return NotificationEvent.objects.filter(type_key=key)

    def users(self, key):
        return set(InboxItem.objects.filter(event__type_key=key).values_list("user__username", flat=True))


class GracePeriodTests(_Base):
    def test_entering_grace_notifies_subscription_viewers_of_this_store_only(self):
        sub = svc.enter_grace_period(self.active(), actor=self.staff)
        ev = self.ev("subscription.grace_period").get()
        self.assertEqual((ev.severity, ev.entity_id, ev.store_id), (R.IMPORTANT, str(sub.pk), self.store.pk))
        self.assertEqual(self.users("subscription.grace_period"), {"sg-owner", "sg-admin"})         # SUBSCRIPTION_VIEW holders (ROLE_PERMISSIONS); analyst/order manager have none
        self.assertNotIn("sg-other-owner", self.users("subscription.grace_period"))                # tenant isolation
        self.assertNotIn("sg-platform", self.users("subscription.grace_period"))                   # store events never reach the platform inbox
        self.assertFalse(self.ev("subscription.past_due").exists())                                 # a different state: no mislabeled event
        self.assertEqual(sub.status, StoreSubscription.Status.GRACE_PERIOD)

    def test_repeated_runs_while_already_in_grace_create_no_second_notification(self):
        sub = svc.enter_grace_period(self.active(), actor=self.staff)
        for _ in range(3):
            svc.enter_grace_period(sub, actor=self.staff)
        self.assertEqual(self.ev("subscription.grace_period").count(), 1)

    def test_a_rolled_back_transition_publishes_nothing(self):
        sub = self.active()
        try:
            with transaction.atomic():
                svc.enter_grace_period(sub, actor=self.staff)
                raise RuntimeError("caller fails after the transition")
        except RuntimeError:
            pass
        self.assertFalse(self.ev("subscription.grace_period").exists())
        sub.refresh_from_db()
        self.assertEqual(sub.status, StoreSubscription.Status.ACTIVE)

    def test_a_second_grace_episode_after_resuming_is_a_new_event(self):
        sub = svc.enter_grace_period(self.active(), actor=self.staff)
        sub = svc.resume_subscription(sub, actor=self.staff)
        svc.enter_grace_period(sub, actor=self.staff)
        self.assertEqual(self.ev("subscription.grace_period").count(), 2)


class TimedEvaluationTests(_Base):
    def test_period_end_then_grace_expiry_flow_through_the_real_evaluator(self):
        now = timezone.now()
        self.active(period_end=now - timedelta(hours=1))
        svc.evaluate_subscription_states(now=now, actor=self.staff)                                  # active + period over → grace
        self.assertEqual(self.ev("subscription.grace_period").count(), 1)
        svc.evaluate_subscription_states(now=now + timedelta(minutes=5), actor=self.staff)           # still in grace → nothing new
        self.assertEqual(self.ev("subscription.grace_period").count(), 1)
        self.assertFalse(self.ev("subscription.suspended").exists())
        after_grace = now + timedelta(days=8)                                                         # grace (7 days) expired
        svc.evaluate_subscription_states(now=after_grace, actor=self.staff)
        suspended = self.ev("subscription.suspended").get()
        self.assertEqual(suspended.severity, R.CRITICAL)
        svc.evaluate_subscription_states(now=after_grace + timedelta(hours=3), actor=self.staff)     # repeated run
        self.assertEqual(self.ev("subscription.suspended").count(), 1)
        self.assertEqual(self.ev("subscription.grace_period").count(), 1)

    def test_dry_run_notifies_nothing(self):
        now = timezone.now()
        self.active(period_end=now - timedelta(hours=1))
        svc.evaluate_subscription_states(now=now, dry_run=True, actor=self.staff)
        self.assertFalse(NotificationEvent.objects.exists())


class PreservedBehaviourTests(_Base):
    def test_suspension_still_notifies_once_and_a_repeat_does_not(self):
        sub = svc.suspend_subscription(self.active(), actor=self.staff, reason="x")
        svc.suspend_subscription(sub, actor=self.staff, reason="x")
        self.assertEqual(self.ev("subscription.suspended").count(), 1)
        self.assertEqual(self.users("subscription.suspended"), {"sg-owner", "sg-admin"})

    def test_past_due_event_remains_registered_but_is_declared_dormant(self):
        t = R.EVENT_TYPES["subscription.past_due"]
        self.assertEqual(t.lifecycle, "dormant")
        sub = svc.mark_past_due(self.active(), actor=self.staff)                                      # the contract still works if a caller appears
        self.assertEqual(self.ev("subscription.past_due").count(), 1)
        self.assertEqual(sub.status, StoreSubscription.Status.PAST_DUE)

    def test_billing_and_entitlement_state_are_unchanged_by_notifications(self):
        sub = svc.enter_grace_period(self.active(), actor=self.staff)
        self.assertEqual(sub.plan_version_id, self.version.pk)
        self.assertTrue(sub.is_current)
        self.assertIsNotNone(sub.grace_period_end)


from django.test import override_settings                                    # noqa: E402

from apps.billing.services import dunning_service                           # noqa: E402
from apps.billing.tests.test_dunning_cancellation import _sub_with_open_invoice   # noqa: E402
from apps.dashboard.tests.test_permission_enforcement import _user_with_role      # noqa: E402
from apps.notifications.models import InboxItem, NotificationEvent          # noqa: E402
from apps.stores.models import StoreMembership                              # noqa: E402


@override_settings(RASTISI_BILLING_DUNNING_SCHEDULE="0,3,7,14")
class DunningRuntimeReachabilityTests(TestCase):
    """RUNTIME evidence (not an AST reference): the real dunning runner reaches the notification for each REAL transition exactly once, across repeated runs."""

    def test_the_dunning_runner_notifies_one_grace_and_one_suspension_across_repeated_runs(self):
        store, sub, version, invoice = _sub_with_open_invoice("dn-ntf", due_days_ago=20)
        owner = _user_with_role(store, "dn-owner", StoreMembership.Role.OWNER)
        for _ in range(8):                                               # more runs than stages; extra runs must be inert
            dunning_service.process_dunning()
        sub.refresh_from_db()
        self.assertEqual(sub.status, "suspended")
        grace = NotificationEvent.objects.filter(type_key="subscription.grace_period", store=store)
        susp = NotificationEvent.objects.filter(type_key="subscription.suspended", store=store)
        self.assertEqual((grace.count(), susp.count()), (1, 1))
        self.assertTrue(grace.get().dedupe_key.startswith(f"sub:{sub.pk}:grace:"))
        self.assertEqual(InboxItem.objects.filter(user=owner, event__type_key="subscription.grace_period").count(), 1)

    def test_the_transition_functions_stay_atomic(self):
        """Regression: inserting a helper between a decorator and its function once removed ``@transaction.atomic`` from ``enter_grace_period``."""
        import ast
        import inspect

        from apps.subscriptions.services import subscription_service as svc

        tree = ast.parse(inspect.getsource(svc))
        decorated = {n.name: [ast.unparse(d) for d in n.decorator_list] for n in tree.body if isinstance(n, ast.FunctionDef)}
        for name in ("enter_grace_period", "mark_past_due", "suspend_subscription", "activate_subscription"):
            self.assertIn("transaction.atomic", decorated[name], name)
        self.assertEqual(decorated["_status_of"], [])                       # the helper is not itself the atomic unit
