"""Checkpoint 5B commit 8 (ADR-80): plan-change billing without fake proration.
Upgrade requires a paid plan-change invoice before the plan version switches;
downgrade is scheduled for the next period; stale-preview protection retained."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    invoice_service,
    plan_change_billing_service as pcb,
    renewal_service,
)
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs
from apps.subscriptions.services import subscription_service as sub_svc


def _published(code, *, price):
    plan = Plan.objects.create(code=code, name=code, is_publicly_selectable=True)
    return PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT", billing_interval=PlanVersion.BillingInterval.MONTHLY,
    )


class UpgradeBillingTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="up-store", admin_subdomain="up-store")
        self.cheap = _published("up-cheap", price="100000")
        self.pricey = _published("up-pricey", price="300000")
        sub = sub_svc.create_subscription(self.store, self.cheap)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=30))
        ent.clear_entitlement_cache()

    def _token(self):
        return pcs._preview_token(ent.get_current_subscription(self.store), self.pricey)

    def test_upgrade_creates_invoice_and_does_not_switch_until_paid(self):
        kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=self._token())
        self.assertEqual(kind, "invoice")
        self.assertEqual(invoice.kind, SubscriptionInvoice.Kind.PLAN_CHANGE)
        self.assertEqual(invoice.grand_total, Decimal("300000"))
        # Plan version NOT switched yet.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.cheap.pk)

    def test_upgrade_switches_plan_after_payment(self):
        _kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=self._token())
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        ent.clear_entitlement_cache()
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.pricey.pk)

    def test_stale_token_rejected(self):
        with self.assertRaises(pcs.StalePreviewError):
            pcb.start_plan_change(self.sub, self.pricey, preview_token="stale")

    def test_preview_reports_upgrade(self):
        preview = pcb.preview(self.sub, self.pricey)
        self.assertTrue(preview["is_upgrade"])
        self.assertEqual(preview["payable_amount"], Decimal("300000"))


class TrialToPaidUpgradeBillingTests(TestCase):
    """A Store's very first purchase is always an "upgrade" out of a free
    trial plan_version — this must both switch plan_version AND activate the
    still-trialing subscription (portal purchase relies on this; a trialing
    subscription that merely changed plan_version would never satisfy
    handle-claim's ACTIVE-only requirement)."""

    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="trial-up-store", admin_subdomain="trial-up-store")
        self.trial = _published("trial-up-free", price="0")
        self.paid = _published("trial-up-paid", price="200000")
        sub = sub_svc.create_subscription(self.store, self.trial)
        self.sub = sub_svc.start_trial(sub)
        ent.clear_entitlement_cache()

    def _token(self):
        return pcs._preview_token(ent.get_current_subscription(self.store), self.paid)

    def test_upgrade_from_trial_activates_subscription_on_payment(self):
        self.assertEqual(self.sub.status, StoreSubscription.Status.TRIALING)
        _kind, invoice = pcb.start_plan_change(self.sub, self.paid, preview_token=self._token())
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, StoreSubscription.Status.ACTIVE)
        self.assertEqual(self.sub.plan_version_id, self.paid.pk)
        self.assertIsNotNone(self.sub.current_period_end)


class DowngradeBillingTests(TestCase):
    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="dn-store", admin_subdomain="dn-store")
        self.pricey = _published("dn-pricey", price="300000")
        self.cheap = _published("dn-cheap", price="100000")
        sub = sub_svc.create_subscription(self.store, self.pricey)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=1))
        ent.clear_entitlement_cache()

    def _token(self):
        return pcs._preview_token(ent.get_current_subscription(self.store), self.cheap)

    def test_downgrade_is_scheduled_no_immediate_switch(self):
        kind, scheduled = pcb.start_plan_change(self.sub, self.cheap, preview_token=self._token())
        self.assertEqual(kind, "scheduled")
        self.assertIsInstance(scheduled, ScheduledPlanChange)
        # Still on the pricey plan until next period.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.pricey.pk)
        self.assertEqual(pcb.preview(self.sub, self.cheap)["payable_amount"], Decimal("0"))

    def test_scheduled_downgrade_applied_at_renewal(self):
        pcb.start_plan_change(self.sub, self.cheap, preview_token=self._token())
        renewal_service.generate_renewals(lead_days=3)
        ent.clear_entitlement_cache()
        # Renewal applied the downgrade: now on cheap, scheduled record cleared.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.cheap.pk)
        self.assertFalse(ScheduledPlanChange.objects.filter(subscription=self.sub).exists())
        invoice = SubscriptionInvoice.objects.get(subscription=self.sub, kind=SubscriptionInvoice.Kind.RENEWAL)
        self.assertEqual(invoice.grand_total, Decimal("100000"))

    def test_equal_price_target_follows_the_same_scheduled_policy_as_downgrade(self):
        """``is_upgrade`` is a strict ``>`` comparison — an equal-price
        target is therefore not an upgrade and must follow the same
        no-immediate-switch, no-payable-invoice, scheduled-for-next-period
        policy as a genuine downgrade."""
        same_price_plan = _published("dn-same-price", price="300000")
        token = pcs._preview_token(ent.get_current_subscription(self.store), same_price_plan)
        kind, scheduled = pcb.start_plan_change(self.sub, same_price_plan, preview_token=token)
        self.assertEqual(kind, "scheduled")
        self.assertIsInstance(scheduled, ScheduledPlanChange)
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.pricey.pk)
        self.assertFalse(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=same_price_plan,
            ).exists()
        )


class PlanChangeIdempotencyTests(TestCase):
    """SUB-001 architecture review: ``start_plan_change`` must not create a
    second payable ``PLAN_CHANGE`` invoice for the same still-current
    subscription state and same target when called repeatedly with the
    same valid preview decision (e.g. a double form-submit, a retried
    request, or two browser tabs). This is a repair inside the canonical
    billing service itself — not a workaround in any calling view — so both
    Merchant Admin (``apps.dashboard``) and Portal (``apps.portal``) callers
    benefit identically."""

    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="idem-store", admin_subdomain="idem-store")
        self.cheap = _published("idem-cheap", price="100000")
        self.pricey = _published("idem-pricey", price="300000")
        sub = sub_svc.create_subscription(self.store, self.cheap)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=30))
        ent.clear_entitlement_cache()

    def _token(self):
        return pcs._preview_token(ent.get_current_subscription(self.store), self.pricey)

    def test_repeated_upgrade_call_reuses_the_same_payable_invoice(self):
        token = self._token()
        kind1, invoice1 = pcb.start_plan_change(self.sub, self.pricey, preview_token=token)
        kind2, invoice2 = pcb.start_plan_change(self.sub, self.pricey, preview_token=token)

        self.assertEqual(kind1, "invoice")
        self.assertEqual(kind2, "invoice")
        self.assertEqual(invoice1.pk, invoice2.pk)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey,
            ).count(),
            1,
        )
        # Plan still not switched — the reused invoice is unpaid.
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.cheap.pk)

    def test_three_repeated_calls_still_resolve_to_exactly_one_invoice(self):
        token = self._token()
        for _ in range(3):
            pcb.start_plan_change(self.sub, self.pricey, preview_token=token)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey,
            ).count(),
            1,
        )

    def test_a_voided_plan_change_invoice_is_never_silently_reused(self):
        """A financially-closed invoice (VOID/PAID/...) must never be handed
        back as if it were still payable — the merchant needs a genuinely
        new attempt, and the closed document's history must stay intact."""
        token = self._token()
        _kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=token)
        invoice_service.void_invoice(invoice)

        _kind2, invoice2 = pcb.start_plan_change(self.sub, self.pricey, preview_token=token)
        self.assertNotEqual(invoice.pk, invoice2.pk)
        self.assertEqual(invoice2.status, SubscriptionInvoice.Status.OPEN)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=self.pricey,
            ).count(),
            2,
        )

    def test_repeated_downgrade_call_updates_the_single_scheduled_row(self):
        """Downgrade/equal-price idempotency: repeating the same scheduling
        decision must not create a second ``ScheduledPlanChange`` — the
        model's ``OneToOneField(subscription)`` plus
        ``update_or_create`` already guarantee exactly one row per
        subscription; this test locks that contract for SUB-001."""
        # Move to a paid plan first so cheap is a genuine downgrade target.
        up_token = pcs._preview_token(ent.get_current_subscription(self.store), self.pricey)
        _kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=up_token)
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        ent.clear_entitlement_cache()

        down_token = pcs._preview_token(ent.get_current_subscription(self.store), self.cheap)
        pcb.start_plan_change(self.sub, self.cheap, preview_token=down_token)
        pcb.start_plan_change(self.sub, self.cheap, preview_token=down_token)

        self.assertEqual(ScheduledPlanChange.objects.filter(subscription=self.sub).count(), 1)

    def test_stale_token_still_rejected_before_any_lock_side_effect(self):
        """The subscription-locking repair must not weaken stale-preview
        protection: a stale token is still rejected, and no invoice or
        scheduled change is created."""
        with self.assertRaises(pcs.StalePreviewError):
            pcb.start_plan_change(self.sub, self.pricey, preview_token="not-the-real-token")
        self.assertFalse(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE,
            ).exists()
        )
        self.assertFalse(ScheduledPlanChange.objects.filter(subscription=self.sub).exists())
