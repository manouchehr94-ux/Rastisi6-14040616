"""SUB-001 (independent architecture review, Repair 2) — the Platform Admin
plan-change override (``apps.portal.platform_admin_views.store_change_plan``)
is an explicit, non-merchant-reachable operator action, distinct from the
Merchant Admin billing-aware plan-change flow (covered in
``apps.dashboard.tests.test_subscription_views``). It must:

* remain restricted to authenticated Django superusers (``_is_platform_staff``),
  never to any merchant ``StoreMembership``/``ROLE_PERMISSIONS`` role
  (including ``SUBSCRIPTION_CHANGE``);
* switch the plan immediately through the existing low-level
  ``subscription_service.change_plan_version`` primitive (no invoice, no
  payment, no second billing engine);
* record the acting Platform Admin on the resulting immutable
  ``SubscriptionEvent``;
* reject an unpublished/hidden target version;
* no longer depend on the previously-broken ``preview["preview_token"]``
  round trip (``preview_plan_change`` returns ``"token"``, not
  ``"preview_token"`` — the override route no longer calls preview at all).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
_HOST = "platformadmins.rastisi.localhost"


@override_settings(ALLOWED_HOSTS=[_HOST, "testserver"])
class StoreChangePlanViewTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.superuser = User.objects.create_user(
            username="pa-plan-super@example.com", email="pa-plan-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        self.store = Store.objects.create(
            name="فروشگاه Override پلن", slug="plan-override-store", admin_subdomain="plan-override-store",
        )
        self.from_plan = Plan.objects.create(code="override-from", name="From")
        self.from_version = PlanVersion.objects.create(
            plan=self.from_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        self.to_plan = Plan.objects.create(code="override-to", name="To", is_publicly_selectable=True)
        self.to_version = PlanVersion.objects.create(
            plan=self.to_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        sub = sub_svc.create_subscription(self.store, self.from_version)
        self.subscription = sub_svc.activate_subscription(sub)
        ent.clear_entitlement_cache()
        self.client.force_login(self.superuser)

    def _url(self):
        return f"/stores/{self.store.public_id}/change-plan/"

    # -- (1) a Platform superuser can intentionally perform the override ----

    def test_superuser_can_change_the_plan(self):
        response = self.client.post(
            self._url(), {"plan_version_id": self.to_version.pk, "reason": "درخواستِ پشتیبانی"},
            HTTP_HOST=_HOST,
        )
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.to_version.pk)

    # -- (2) the change uses the existing subscription lifecycle primitive --
    #    (proven indirectly: from_version -> to_version switched, same
    #    invariants as subscription_service.change_plan_version, e.g. no
    #    SubscriptionInvoice/ScheduledPlanChange side effects at all)

    def test_override_creates_no_billing_side_effects(self):
        from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice

        self.client.post(
            self._url(), {"plan_version_id": self.to_version.pk, "reason": "بدونِ صورتحساب"}, HTTP_HOST=_HOST,
        )
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), 0)
        self.assertEqual(ScheduledPlanChange.objects.filter(subscription=self.subscription).count(), 0)

    # -- (3) actor is recorded in the resulting plan-change event -----------

    def test_actor_is_recorded_on_the_plan_changed_event(self):
        self.client.post(
            self._url(), {"plan_version_id": self.to_version.pk, "reason": "تغییرِ اپراتوری"}, HTTP_HOST=_HOST,
        )
        event = self.subscription.events.get(event_type=SubscriptionEvent.EventType.PLAN_CHANGED)
        self.assertEqual(event.actor, self.superuser)
        self.assertEqual(event.reason, "تغییرِ اپراتوری")
        self.assertEqual(event.from_plan_version_id, self.from_version.pk)
        self.assertEqual(event.to_plan_version_id, self.to_version.pk)

    # -- (4) an ordinary merchant OWNER cannot call this as billing bypass --

    def test_merchant_owner_cannot_reach_the_override_view(self):
        owner = User.objects.create_user(
            username="pa-plan-owner@example.com", email="pa-plan-owner@example.com",
            password="a-very-strong-pass-1",
        )
        StoreMembership.objects.create(
            store=self.store, user=owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="pa-plan-owner@example.com", password="a-very-strong-pass-1")
        response = self.client.post(
            self._url(), {"plan_version_id": self.to_version.pk}, HTTP_HOST=_HOST,
        )
        # _is_platform_staff requires is_staff AND is_superuser — an OWNER
        # StoreMembership grants neither, regardless of ROLE_PERMISSIONS
        # (including SUBSCRIPTION_CHANGE, which OWNER does hold).
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.from_version.pk)

    def test_merchant_owner_calling_the_service_function_directly_is_rejected(self):
        """Even bypassing the view/permission decorator entirely, the
        service-level guard inside ``execute_platform_admin_plan_override``
        itself rejects a non-superuser actor — the override is not merely
        view-decorator-deep."""
        owner = User.objects.create_user(
            username="pa-plan-owner2@example.com", email="pa-plan-owner2@example.com",
            password="a-very-strong-pass-1",
        )
        with self.assertRaises(pcs.PlanChangeError):
            pcs.execute_platform_admin_plan_override(self.store, self.to_version, actor=owner)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.from_version.pk)

    # -- (5) unpublished target is rejected ----------------------------------

    def test_unpublished_target_rejected(self):
        draft_plan = Plan.objects.create(code="override-draft", name="Draft")
        draft_version = PlanVersion.objects.create(
            plan=draft_plan, version_number=1, status=PlanVersion.Status.DRAFT,
        )
        response = self.client.post(
            self._url(), {"plan_version_id": draft_version.pk}, HTTP_HOST=_HOST,
        )
        # The view's own PlanVersion.objects.filter(status=PUBLISHED) lookup
        # already excludes a DRAFT version id, so this never even reaches
        # execute_platform_admin_plan_override.
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.from_version.pk)

    def test_service_level_guard_also_rejects_an_unpublished_version(self):
        """Defense in depth: the service function itself re-validates
        publication status, independent of the view's own filter."""
        draft_plan = Plan.objects.create(code="override-draft-2", name="Draft2")
        draft_version = PlanVersion.objects.create(
            plan=draft_plan, version_number=1, status=PlanVersion.Status.DRAFT,
        )
        with self.assertRaises(pcs.PlanChangeError):
            pcs.execute_platform_admin_plan_override(self.store, draft_version, actor=self.superuser)

    # -- (6) the view no longer depends on preview["preview_token"] ---------

    def test_view_does_not_call_preview_plan_change_at_all(self):
        """Regression lock for the fixed defect: the old view called
        ``preview_plan_change`` and then accessed the non-existent
        ``preview["preview_token"]`` key (the real key is ``"token"``). The
        override no longer previews at all — it changes the plan directly —
        so no KeyError-prone round trip exists anymore."""
        from unittest.mock import patch

        with patch(
            "apps.subscriptions.services.plan_change_service.preview_plan_change"
        ) as mocked_preview:
            response = self.client.post(
                self._url(), {"plan_version_id": self.to_version.pk, "reason": "بدونِ پیش‌نمایش"},
                HTTP_HOST=_HOST,
            )
        mocked_preview.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.to_version.pk)

    def test_missing_current_subscription_is_rejected(self):
        empty_store = Store.objects.create(
            name="فروشگاهِ بدونِ اشتراک", slug="plan-override-empty", admin_subdomain="plan-override-empty",
        )
        with self.assertRaises(pcs.PlanChangeError):
            pcs.execute_platform_admin_plan_override(empty_store, self.to_version, actor=self.superuser)
