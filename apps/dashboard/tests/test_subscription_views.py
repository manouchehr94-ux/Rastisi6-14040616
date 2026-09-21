"""Checkpoint 5A commit 7: Merchant Admin subscription/usage/plans/preview/
history views, permission gating (SUBSCRIPTION_VIEW / SUBSCRIPTION_CHANGE /
USAGE_VIEW), and that plan selection is restricted to publicly-selectable
published versions (a merchant cannot POST an arbitrary version id).

SUB-001 (architecture convergence, Wave 1B): ``subscription_plan_execute``
no longer calls ``plan_change_service.execute_plan_change`` (which switched
``plan_version`` immediately after only a preview-token check, with no
payment). It now routes through the same canonical billing authority the
Portal purchase flow already uses,
``apps.billing.services.plan_change_billing_service.start_plan_change``:
an upgrade creates a payable ``PLAN_CHANGE`` invoice and leaves the plan
unchanged until the invoice is actually paid (``confirmation_service``); a
downgrade/equal-price change is scheduled for the next period with no
immediate switch. See ``PlanChangeExecuteBillingConvergenceTests`` below —
this class supersedes the old immediate-switch behavior."""

from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice
from apps.billing.services import attempt_service, confirmation_service
from apps.stores.authorization import (
    ROLE_PERMISSIONS,
    SUBSCRIPTION_CHANGE,
    SUBSCRIPTION_VIEW,
    USAGE_VIEW,
)
from apps.stores.models import Store, StoreMembership
from apps.subscriptions import entitlements as ekeys
from apps.subscriptions.models import (
    EntitlementDefinition,
    Plan,
    PlanEntitlement,
    PlanVersion,
)
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs

User = get_user_model()

HOST = f"sub-test.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"


class RolePermissionMappingTests(TestCase):
    def test_owner_can_change_but_administrator_cannot(self):
        self.assertIn(SUBSCRIPTION_CHANGE, ROLE_PERMISSIONS[StoreMembership.Role.OWNER])
        self.assertNotIn(SUBSCRIPTION_CHANGE, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])

    def test_administrator_can_view_subscription_and_usage(self):
        self.assertIn(SUBSCRIPTION_VIEW, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])
        self.assertIn(USAGE_VIEW, ROLE_PERMISSIONS[StoreMembership.Role.ADMINISTRATOR])

    def test_content_editor_sees_none_of_the_three(self):
        perms = ROLE_PERMISSIONS[StoreMembership.Role.CONTENT_EDITOR]
        self.assertNotIn(SUBSCRIPTION_VIEW, perms)
        self.assertNotIn(SUBSCRIPTION_CHANGE, perms)
        self.assertNotIn(USAGE_VIEW, perms)

    def test_analyst_sees_usage_only(self):
        perms = ROLE_PERMISSIONS[StoreMembership.Role.ANALYST]
        self.assertIn(USAGE_VIEW, perms)
        self.assertNotIn(SUBSCRIPTION_CHANGE, perms)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class SubscriptionViewTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.client = Client(HTTP_HOST=HOST)
        self.store = Store.objects.get(slug="akhlaghi")  # legacy sub → unlimited, display_price=0
        self.store.admin_subdomain = "sub-test"
        self.store.save(update_fields=["admin_subdomain"])

        # A publicly-selectable, priced plan — an "upgrade" relative to the
        # legacy (display_price=0) subscription akhlaghi starts on, so
        # SUB-001's billing-aware upgrade path is actually exercised.
        self.target_plan = Plan.objects.create(code="growth-sv", name="Growth", is_publicly_selectable=True)
        self.target_version = PlanVersion.objects.create(
            plan=self.target_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("350000"), currency="IRT",
            billing_interval=PlanVersion.BillingInterval.MONTHLY,
        )
        PlanEntitlement.objects.create(
            plan_version=self.target_version,
            entitlement=EntitlementDefinition.objects.get(key=ekeys.CATALOG_PRODUCTS),
            is_enabled=True, integer_limit=50,
        )

        self.owner = self._member("sv-owner", StoreMembership.Role.OWNER)
        self.client.login(username="sv-owner", password="pass12345")

    def _member(self, username, role):
        user = User.objects.create_user(username=username, password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=user, role=role,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        return user

    def _login(self, username, role):
        self._member(username, role)
        self.client.logout()
        self.client.login(username=username, password="pass12345")

    def test_owner_can_view_overview(self):
        resp = self.client.get(reverse("dashboard:subscription-overview"))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_view_usage(self):
        resp = self.client.get(reverse("dashboard:usage-overview"))
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_view_plans_and_history(self):
        self.assertEqual(self.client.get(reverse("dashboard:subscription-plans")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:subscription-history")).status_code, 200)

    def test_content_editor_forbidden_from_overview(self):
        self._login("sv-editor", StoreMembership.Role.CONTENT_EDITOR)
        resp = self.client.get(reverse("dashboard:subscription-overview"))
        self.assertEqual(resp.status_code, 403)

    def test_administrator_can_view_but_not_change(self):
        self._login("sv-admin", StoreMembership.Role.ADMINISTRATOR)
        self.assertEqual(self.client.get(reverse("dashboard:subscription-overview")).status_code, 200)
        # Plans page requires SUBSCRIPTION_CHANGE → forbidden for administrator.
        self.assertEqual(self.client.get(reverse("dashboard:subscription-plans")).status_code, 403)

    def test_execute_rejects_non_selectable_version(self):
        hidden_plan = Plan.objects.create(code="hidden-sv", name="Hidden", is_publicly_selectable=False)
        hidden_version = PlanVersion.objects.create(
            plan=hidden_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        resp = self.client.post(
            reverse("dashboard:subscription-plan-execute"),
            {"version_id": hidden_version.pk, "preview_token": "whatever"},
        )
        self.assertEqual(resp.status_code, 404)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PlanChangeExecuteBillingConvergenceTests(TestCase):
    """SUB-001 — ``subscription_plan_execute`` must route through the
    canonical billing-aware authority (``plan_change_billing_service.
    start_plan_change``), exactly like the Portal purchase flow, instead of
    directly switching ``plan_version`` after only a preview-token check.

    This class supersedes the old
    ``SubscriptionViewTests.test_preview_then_execute_changes_plan``, whose
    assertion (``current.plan_version_id == self.target_version.pk``
    *immediately* after ``execute``) encoded the SUB-001 defect itself and
    would fail the moment the fix lands — proving this is the exact
    pre-fix-vs-post-fix boundary."""

    def setUp(self):
        ent.clear_entitlement_cache()
        self.client = Client(HTTP_HOST=HOST)
        self.store = Store.objects.get(slug="akhlaghi")  # legacy sub → display_price=0
        self.store.admin_subdomain = "sub-test"
        self.store.save(update_fields=["admin_subdomain"])

        self.pricey_plan = Plan.objects.create(code="pricey-sv", name="Pricey", is_publicly_selectable=True)
        self.pricey_version = PlanVersion.objects.create(
            plan=self.pricey_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("350000"), currency="IRT",
            billing_interval=PlanVersion.BillingInterval.MONTHLY,
        )
        self.cheap_plan = Plan.objects.create(code="cheap-sv", name="Cheap", is_publicly_selectable=True)
        self.cheap_version = PlanVersion.objects.create(
            plan=self.cheap_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
            display_price=Decimal("0"), currency="IRT",
            billing_interval=PlanVersion.BillingInterval.MONTHLY,
        )

        self.owner = User.objects.create_user(username="sv-owner-bill", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.login(username="sv-owner-bill", password="pass12345")

    def _token_for(self, target_version):
        current = ent.get_current_subscription(self.store)
        return pcs._preview_token(current, target_version)

    def _execute(self, target_version, token=None):
        """``token=None`` means "auto-generate a valid preview token for
        this call" (the common case for positive-path tests). Any other
        value — including the empty string ``""`` — is sent to the view
        EXACTLY as given, unmodified. This distinction matters: ``"" or x``
        would silently replace an intentionally-empty token with a valid
        one (since ``""`` is falsy in Python), which would make
        ``test_empty_preview_token_creates_no_mutation`` actually exercise
        a legitimate upgrade instead of the empty-token rejection path it
        claims to test. Using an explicit ``is None`` check avoids that."""
        if token is None:
            token = self._token_for(target_version)
        return self.client.post(
            reverse("dashboard:subscription-plan-execute"),
            {"version_id": target_version.pk, "preview_token": token},
        )

    # -- helper self-test: proves the exact wire value _execute sends -------
    # (independent review Blocker 1 repair). This spies only on the test
    # client's own ``post`` method (via ``wraps=``, so the real call still
    # happens) — it never mocks any production billing/subscription
    # service, so it cannot hide or fake the behavior under test.

    def test_helper_token_none_generates_a_valid_token(self):
        with patch.object(self.client, "post", wraps=self.client.post) as spy:
            self._execute(self.pricey_version, token=None)
        sent = spy.call_args.args[1]["preview_token"]
        self.assertEqual(sent, self._token_for(self.pricey_version))
        self.assertNotEqual(sent, "")

    def test_helper_empty_string_token_is_sent_exactly_empty(self):
        with patch.object(self.client, "post", wraps=self.client.post) as spy:
            self._execute(self.pricey_version, token="")
        sent = spy.call_args.args[1]["preview_token"]
        self.assertEqual(sent, "")

    def test_helper_stale_token_is_sent_exactly_as_given(self):
        with patch.object(self.client, "post", wraps=self.client.post) as spy:
            self._execute(self.pricey_version, token="stale")
        sent = spy.call_args.args[1]["preview_token"]
        self.assertEqual(sent, "stale")

    # -- (1) upgrade: invoice created, plan NOT switched --------------------

    def test_upgrade_execute_creates_invoice_and_does_not_switch_plan(self):
        before = ent.get_current_subscription(self.store).plan_version_id
        resp = self._execute(self.pricey_version)

        invoice = SubscriptionInvoice.objects.get(
            store=self.store, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey_version,
        )
        self.assertRedirects(resp, reverse("dashboard:billing-invoice-detail", args=[invoice.pk]))
        self.assertTrue(invoice.is_payable)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store, kind=SubscriptionInvoice.Kind.PLAN_CHANGE).count(), 1)

        ent.clear_entitlement_cache()
        current = ent.get_current_subscription(self.store)
        self.assertEqual(current.plan_version_id, before)
        self.assertNotEqual(current.plan_version_id, self.pricey_version.pk)
        # No PLAN_CHANGED event before payment.
        self.assertFalse(current.events.filter(event_type="plan_changed").exists())

    # -- (2) upgrade switches plan only after canonical payment confirmation

    def test_upgrade_switches_plan_only_after_payment_confirmation(self):
        self._execute(self.pricey_version)
        invoice = SubscriptionInvoice.objects.get(
            store=self.store, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey_version,
        )
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency=invoice.currency)

        ent.clear_entitlement_cache()
        current = ent.get_current_subscription(self.store)
        self.assertEqual(current.plan_version_id, self.pricey_version.pk)
        self.assertEqual(current.events.filter(event_type="plan_changed").count(), 1)

    # -- (3) repeated identical upgrade execute does not duplicate invoices -

    def test_repeated_upgrade_execute_does_not_create_duplicate_invoice(self):
        first = self._execute(self.pricey_version)
        second = self._execute(self.pricey_version)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first["Location"], second["Location"])
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                store=self.store, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey_version,
            ).count(),
            1,
        )

    # -- (4) downgrade/equal: scheduled, no immediate switch ----------------

    def test_downgrade_execute_schedules_change_without_immediate_switch(self):
        # First move the Store onto a paid plan so the next change is a
        # genuine downgrade rather than "equal to legacy's free price".
        self._execute(self.pricey_version)
        invoice = SubscriptionInvoice.objects.get(
            store=self.store, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey_version,
        )
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency=invoice.currency)
        ent.clear_entitlement_cache()

        resp = self._execute(self.cheap_version)
        self.assertRedirects(resp, reverse("dashboard:subscription-overview"))

        current = ent.get_current_subscription(self.store)
        self.assertEqual(current.plan_version_id, self.pricey_version.pk)  # unchanged, still on pricey
        self.assertTrue(ScheduledPlanChange.objects.filter(subscription=current, target_plan_version=self.cheap_version).exists())

    # -- (5) stale / empty preview token: no mutation at all ----------------

    def test_stale_preview_token_creates_no_mutation(self):
        before_plan = ent.get_current_subscription(self.store).plan_version_id
        before_invoices = SubscriptionInvoice.objects.filter(store=self.store).count()
        before_scheduled = ScheduledPlanChange.objects.count()

        resp = self._execute(self.pricey_version, token="definitely-stale")
        self.assertRedirects(resp, reverse("dashboard:subscription-plans"))

        ent.clear_entitlement_cache()
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, before_plan)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), before_invoices)
        self.assertEqual(ScheduledPlanChange.objects.count(), before_scheduled)

    def test_empty_preview_token_creates_no_mutation(self):
        before_plan = ent.get_current_subscription(self.store).plan_version_id
        before_invoices = SubscriptionInvoice.objects.filter(store=self.store).count()

        resp = self._execute(self.pricey_version, token="")
        self.assertRedirects(resp, reverse("dashboard:subscription-plans"))

        ent.clear_entitlement_cache()
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, before_plan)
        self.assertEqual(SubscriptionInvoice.objects.filter(store=self.store).count(), before_invoices)

    # -- (6) non-selectable/unpublished target still rejected (unchanged) ---

    def test_hidden_version_still_rejected_after_convergence(self):
        hidden_plan = Plan.objects.create(code="hidden-sv-2", name="Hidden", is_publicly_selectable=False)
        hidden_version = PlanVersion.objects.create(
            plan=hidden_plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        )
        resp = self._execute(hidden_version, token="whatever")
        self.assertEqual(resp.status_code, 404)

    # -- (7) authorized OWNER path works; SUBSCRIPTION_CHANGE still enforced

    def test_administrator_still_forbidden_from_execute(self):
        admin = User.objects.create_user(username="sv-admin-bill", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=admin, role=StoreMembership.Role.ADMINISTRATOR,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client.logout()
        self.client.login(username="sv-admin-bill", password="pass12345")
        resp = self._execute(self.pricey_version)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(
            SubscriptionInvoice.objects.filter(store=self.store, kind=SubscriptionInvoice.Kind.PLAN_CHANGE).exists()
        )
