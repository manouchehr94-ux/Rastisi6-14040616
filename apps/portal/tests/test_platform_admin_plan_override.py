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

    # -- (7) SUB-001 Repair 3, Blocker 1: is_staff is now required, not just
    #    is_superuser -----------------------------------------------------

    def test_authenticated_superuser_without_is_staff_is_rejected(self):
        """The canonical Platform Admin predicate
        (``apps.portal.platform_admin_views._is_platform_staff``) requires
        ``is_authenticated AND is_staff AND is_superuser``. Repair 2's guard
        only checked ``is_authenticated AND is_superuser`` — weaker than the
        canonical boundary. An authenticated, superuser-but-not-staff actor
        must be rejected with zero mutation."""
        non_staff_superuser = User.objects.create_user(
            username="pa-plan-super-nostaff@example.com", email="pa-plan-super-nostaff@example.com",
            password="a-very-strong-pass-1", is_staff=False, is_superuser=True,
        )
        with self.assertRaises(pcs.PlanChangeError):
            pcs.execute_platform_admin_plan_override(self.store, self.to_version, actor=non_staff_superuser)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.from_version.pk)

    # -- (8) SUB-001 Repair 3, Blocker 3: override vs. an open PLAN_CHANGE
    #    invoice — reject before void, succeed after void ------------------

    def test_override_rejected_while_a_payable_plan_change_invoice_exists(self):
        """A merchant-initiated, unresolved ``PLAN_CHANGE`` invoice must not
        be silently invalidated/bypassed by an unrelated operator override:
        the override is rejected outright, the invoice is untouched, and the
        subscription does not move."""
        from apps.billing.models import SubscriptionInvoice
        from apps.billing.services import plan_change_billing_service as pcb

        # Give the subscription a price so `to_version` is a genuine upgrade
        # target, so `start_plan_change` creates a payable invoice.
        self.to_version.display_price = "150000"
        self.to_version.currency = "IRT"
        self.to_version.billing_interval = PlanVersion.BillingInterval.MONTHLY
        self.to_version.save(update_fields=["display_price", "currency", "billing_interval"])
        self.from_version.display_price = "50000"
        self.from_version.currency = "IRT"
        self.from_version.billing_interval = PlanVersion.BillingInterval.MONTHLY
        self.from_version.save(update_fields=["display_price", "currency", "billing_interval"])

        from apps.subscriptions.services import plan_change_service as pcs_module

        token = pcs_module._preview_token(self.subscription, self.to_version)
        _kind, invoice = pcb.start_plan_change(self.subscription, self.to_version, preview_token=token)
        self.assertTrue(invoice.is_payable)

        other_plan = Plan.objects.create(code="override-other", name="Other")
        other_version = PlanVersion.objects.create(
            plan=other_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        with self.assertRaises(pcs.PlanChangeError):
            pcs.execute_platform_admin_plan_override(self.store, other_version, actor=self.superuser, reason="QA")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, self.from_version.pk)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_payable)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(subscription=self.subscription).count(), 1,
        )

    def test_override_succeeds_after_the_open_invoice_is_explicitly_voided(self):
        """Once the merchant's open ``PLAN_CHANGE`` invoice is resolved via
        the canonical billing lifecycle (``invoice_service.void_invoice``),
        the same override that was previously rejected must succeed."""
        from apps.billing.services import invoice_service, plan_change_billing_service as pcb
        from apps.subscriptions.services import plan_change_service as pcs_module

        self.to_version.display_price = "150000"
        self.to_version.currency = "IRT"
        self.to_version.billing_interval = PlanVersion.BillingInterval.MONTHLY
        self.to_version.save(update_fields=["display_price", "currency", "billing_interval"])
        self.from_version.display_price = "50000"
        self.from_version.currency = "IRT"
        self.from_version.billing_interval = PlanVersion.BillingInterval.MONTHLY
        self.from_version.save(update_fields=["display_price", "currency", "billing_interval"])

        token = pcs_module._preview_token(self.subscription, self.to_version)
        _kind, invoice = pcb.start_plan_change(self.subscription, self.to_version, preview_token=token)

        other_plan = Plan.objects.create(code="override-other-2", name="Other2")
        other_version = PlanVersion.objects.create(
            plan=other_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        with self.assertRaises(pcs.PlanChangeError):
            pcs.execute_platform_admin_plan_override(self.store, other_version, actor=self.superuser, reason="QA")

        invoice_service.void_invoice(invoice)
        pcs.execute_platform_admin_plan_override(self.store, other_version, actor=self.superuser, reason="QA")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, other_version.pk)

    # -- (9) SUB-001 Repair 4, architect decision: override supersedes a
    #    ScheduledPlanChange (non-financial) rather than being blocked by it
    #    -----------------------------------------------------------------

    def test_override_supersedes_a_scheduled_plan_change_and_audits_the_supersession(self):
        """Unlike a payable PLAN_CHANGE invoice (a financial artifact that
        must be explicitly resolved), a ScheduledPlanChange represents no
        money moved yet — an explicit Platform Admin immediate override may
        supersede it directly, in the same transaction/lock, with an
        audited supersession, so it does not survive behind the operator
        override and silently revert it at the next renewal."""
        from apps.billing.models import ScheduledPlanChange
        from apps.billing.services import plan_change_billing_service as pcb
        from apps.core.models import AuditLogEntry

        self.to_version.display_price = "150000"
        self.to_version.currency = "IRT"
        self.to_version.billing_interval = PlanVersion.BillingInterval.MONTHLY
        self.to_version.save(update_fields=["display_price", "currency", "billing_interval"])
        self.from_version.display_price = "300000"
        self.from_version.currency = "IRT"
        self.from_version.billing_interval = PlanVersion.BillingInterval.MONTHLY
        self.from_version.save(update_fields=["display_price", "currency", "billing_interval"])

        # `to_version` (150000) is cheaper than `from_version` (300000), so
        # this start_plan_change call is a genuine downgrade -> schedules,
        # doesn't invoice.
        token = pcs._preview_token(self.subscription, self.to_version)
        kind, _scheduled = pcb.start_plan_change(self.subscription, self.to_version, preview_token=token)
        self.assertEqual(kind, "scheduled")
        self.assertTrue(ScheduledPlanChange.objects.filter(subscription=self.subscription).exists())

        other_plan = Plan.objects.create(code="override-other-3", name="Other3")
        other_version = PlanVersion.objects.create(
            plan=other_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        pcs.execute_platform_admin_plan_override(self.store, other_version, actor=self.superuser, reason="QA")

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.plan_version_id, other_version.pk)
        self.assertFalse(ScheduledPlanChange.objects.filter(subscription=self.subscription).exists())
        self.assertTrue(
            AuditLogEntry.objects.filter(
                store=self.store, action_code="billing.plan_change_schedule_superseded",
            ).exists()
        )
