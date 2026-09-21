"""Checkpoint 5B commit 8 (ADR-80): plan-change billing without fake proration.
Upgrade requires a paid plan-change invoice before the plan version switches;
downgrade is scheduled for the next period; stale-preview protection retained."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import ScheduledPlanChange, SubscriptionInvoice
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    invoice_service,
    payment_flow_service,
    plan_change_billing_service as pcb,
    renewal_service,
)
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion, StoreSubscription, SubscriptionEvent
from apps.subscriptions.services import entitlement_service as ent
from apps.subscriptions.services import plan_change_service as pcs
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()


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


class ScheduledDowngradeVsPaidUpgradeRaceTests(TestCase):
    """SUB-001 Repair 3, item 7 (mandatory inspection, NOT a fix): does an
    outstanding ``ScheduledPlanChange`` (a downgrade scheduled for next
    period) interact safely with a *new*, separately-paid upgrade that
    happens before that scheduled downgrade is applied at renewal?

    This test DOCUMENTS the current, pre-existing behavior (unchanged by
    this repair — ``start_plan_change``'s upgrade branch never inspects or
    clears any existing ``ScheduledPlanChange`` row, and
    ``renewal_service._generate_one`` unconditionally applies whatever
    ``ScheduledPlanChange`` still exists for the subscription at renewal
    time, regardless of what the subscription's plan_version has become in
    the meantime).

    Result proven below: a merchant who schedules a downgrade, then changes
    their mind and pays for a fresh upgrade before the next renewal, has
    their PAID upgrade silently overwritten back down to the originally
    scheduled (and no-longer-desired) downgrade target at the next renewal
    — with no invoice/refund reconciliation of any kind for the paid
    upgrade they just received. Neither ``start_plan_change`` nor
    ``confirmation_service.confirm_payment`` clears the stale
    ``ScheduledPlanChange`` when an intervening upgrade is paid.

    This is flagged here as a genuine product-policy gap requiring an
    architect decision (e.g.: should starting/paying a new upgrade cancel
    any pending ``ScheduledPlanChange``? should renewal refuse to apply a
    ``ScheduledPlanChange`` whose ``target_plan_version`` no longer reflects
    the merchant's latest paid decision? should the scheduled downgrade be
    fingerprinted the same way ``PLAN_CHANGE`` invoices now are?) — NOT
    invented or implemented as part of this repair, per explicit
    instruction to STOP and report rather than guess at new financial
    policy in this area."""

    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="sched-race-store", admin_subdomain="sched-race-store")
        self.pricey = _published("sched-race-pricey", price="300000")
        self.cheap = _published("sched-race-cheap", price="100000")
        self.enterprise = _published("sched-race-enterprise", price="900000")
        sub = sub_svc.create_subscription(self.store, self.pricey)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=1))
        ent.clear_entitlement_cache()

    def test_paid_upgrade_after_scheduling_a_downgrade_is_silently_reverted_at_renewal(self):
        # 1) Merchant schedules a downgrade (pricey -> cheap) for next period.
        down_token = pcs._preview_token(ent.get_current_subscription(self.store), self.cheap)
        kind, _scheduled = pcb.start_plan_change(self.sub, self.cheap, preview_token=down_token)
        self.assertEqual(kind, "scheduled")
        self.assertTrue(ScheduledPlanChange.objects.filter(subscription=self.sub).exists())

        # 2) Merchant changes their mind and pays for a fresh upgrade
        #    (pricey -> enterprise) BEFORE the scheduled downgrade applies.
        up_token = pcs._preview_token(ent.get_current_subscription(self.store), self.enterprise)
        _kind2, invoice = pcb.start_plan_change(self.sub, self.enterprise, preview_token=up_token)
        attempt = attempt_service.create_attempt(invoice)
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT")
        ent.clear_entitlement_cache()
        self.assertEqual(ent.get_current_subscription(self.store).plan_version_id, self.enterprise.pk)

        # The stale ScheduledPlanChange (still targeting `cheap`) was NOT
        # cleared by the intervening paid upgrade — current behavior.
        self.assertTrue(ScheduledPlanChange.objects.filter(subscription=self.sub).exists())

        # 3) Renewal runs and unconditionally applies the stale scheduled
        #    downgrade, silently reverting the merchant's just-paid
        #    enterprise upgrade back down to `cheap` — with no
        #    invoice/refund reconciliation of the enterprise payment.
        renewal_service.generate_renewals(lead_days=3)
        ent.clear_entitlement_cache()
        self.sub.refresh_from_db()
        self.assertEqual(
            self.sub.plan_version_id, self.cheap.pk,
            "Documents current (unfixed) behavior: renewal blindly applies a "
            "stale ScheduledPlanChange, silently reverting a paid-for "
            "upgrade that happened after the downgrade was scheduled. This "
            "is a genuine product-policy gap flagged to the architect, not "
            "resolved by this repair.",
        )
        self.assertFalse(ScheduledPlanChange.objects.filter(subscription=self.sub).exists())


class PlanChangePaymentStartDefenseTests(TestCase):
    """SUB-001 Repair 3, Blocker 4 (payment-start defense-in-depth):
    ``payment_flow_service.start_payment`` must refuse to start a payment
    on a ``PLAN_CHANGE`` invoice that is no longer the subscription's valid,
    current unresolved decision — while leaving ``INITIAL``/``RENEWAL``
    behavior completely unchanged."""

    def setUp(self):
        ent.clear_entitlement_cache()
        self.store = Store.objects.create(name="ف", slug="pay-start-store", admin_subdomain="pay-start-store")
        self.cheap = _published("pay-start-cheap", price="100000")
        self.pricey = _published("pay-start-pricey", price="300000")
        sub = sub_svc.create_subscription(self.store, self.cheap)
        self.sub = sub_svc.activate_subscription(sub, period_end=timezone.now() + timedelta(days=30))
        ent.clear_entitlement_cache()

    def test_start_payment_succeeds_for_a_still_valid_plan_change_invoice(self):
        token = pcs._preview_token(ent.get_current_subscription(self.store), self.pricey)
        _kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=token)
        attempt, _session = payment_flow_service.start_payment(invoice, return_url="https://example.test/return")
        self.assertIsNotNone(attempt.pk)

    def test_start_payment_rejects_a_plan_change_invoice_whose_source_state_moved_on(self):
        """If the subscription's source state changes (e.g. via a Platform
        Admin override) after the invoice was created but before payment
        starts, the invoice's fingerprinted decision is stale — payment
        must not start on it, even though the invoice itself is still
        formally ``is_payable``."""
        from apps.subscriptions.services import plan_change_service as pcs_module

        token = pcs._preview_token(ent.get_current_subscription(self.store), self.pricey)
        _kind, invoice = pcb.start_plan_change(self.sub, self.pricey, preview_token=token)

        # Void it first isn't needed here — we're proving the *source-state*
        # check, so instead move the subscription via a route that does NOT
        # touch this invoice at all (there is currently no payable-invoice
        # guard on the override once no OTHER payable invoice exists, so
        # void it to let the override through, matching Blocker 3 semantics).
        invoice_service.void_invoice(invoice)
        superuser = get_user_model().objects.create_user(
            username="pay-start-super@example.com", email="pay-start-super@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )
        pcs_module.execute_platform_admin_plan_override(self.store, self.pricey, actor=superuser, reason="QA")
        ent.clear_entitlement_cache()

        with self.assertRaises(payment_flow_service.PaymentFlowError):
            payment_flow_service.start_payment(invoice, return_url="https://example.test/return")

    def test_initial_invoice_payment_start_is_unaffected(self):
        """INITIAL invoices are never fingerprint-checked — only
        ``kind == PLAN_CHANGE`` triggers the new defense-in-depth check."""
        from apps.billing.services import invoice_service as inv_svc

        paid_trial_version = _published("pay-start-initial", price="50000")
        store2 = Store.objects.create(name="ف۲", slug="pay-start-store-2", admin_subdomain="pay-start-store-2")
        sub2 = sub_svc.create_subscription(store2, paid_trial_version)
        invoice = inv_svc.create_invoice(
            sub2, kind=SubscriptionInvoice.Kind.INITIAL, plan_version=paid_trial_version, currency="IRT",
            lines=[inv_svc.plan_line_spec(paid_trial_version, description="آغازِ اشتراک")],
        )
        invoice = inv_svc.open_invoice(invoice)
        self.assertTrue(invoice.is_payable)

        attempt, _session = payment_flow_service.start_payment(invoice, return_url="https://example.test/return")
        self.assertIsNotNone(attempt.pk)

    def test_renewal_invoice_payment_start_is_unaffected(self):
        """RENEWAL invoices are likewise never fingerprint-checked."""
        renewal_service.generate_renewals(lead_days=45)
        invoice = SubscriptionInvoice.objects.get(subscription=self.sub, kind=SubscriptionInvoice.Kind.RENEWAL)
        self.assertTrue(invoice.is_payable)
        attempt, _session = payment_flow_service.start_payment(invoice, return_url="https://example.test/return")
        self.assertIsNotNone(attempt.pk)


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

    def test_open_invoice_blocks_platform_override_until_voided_then_fresh_decision_gets_a_fresh_invoice(self):
        """SUB-001 independent architecture review, Repair 3 (financial
        invariant — supersedes the old Repair 2 version of this test, which
        asserted that a stale A->C invoice and a fresh B->C invoice could
        coexist as *both payable*. That is no longer considered safe: at
        most ONE unresolved/payable ``PLAN_CHANGE`` invoice may exist per
        ``StoreSubscription`` at any time, full stop — regardless of which
        source state produced it.

        New required semantics proven here:
        1. A->C upgrade decision creates one payable invoice.
        2. A same-subscription Platform Admin override (A->B) is REJECTED
           while that invoice is still payable/unresolved — the invoice is
           untouched, the subscription stays on A, no PLAN_CHANGED event is
           recorded for this attempt.
        3. Only after the A->C invoice is explicitly voided via the
           canonical billing lifecycle (``invoice_service.void_invoice``)
           does the SAME override (A->B) succeed.
        4. A fresh decision from the new source state (B->C) may then
           create its own fresh invoice — the voided A->C invoice is never
           silently reused or repurposed.
        """
        from apps.subscriptions.services import plan_change_service as pcs_module

        plan_c = self.pricey  # shared target: C

        token_a_to_c = pcs._preview_token(ent.get_current_subscription(self.store), plan_c)
        _kind, invoice_a_to_c = pcb.start_plan_change(self.sub, plan_c, preview_token=token_a_to_c)
        self.assertEqual(invoice_a_to_c.plan_version_id, plan_c.pk)
        self.assertTrue(invoice_a_to_c.is_payable)

        plan_b = _published("idem-plan-b", price="150000")
        superuser = User.objects.create_user(
            username="idem-superuser@example.com", email="idem-superuser@example.com",
            password="a-very-strong-pass-1", is_staff=True, is_superuser=True,
        )

        # (2) Override is rejected while the A->C invoice is still payable —
        # no mutation at all: subscription stays on A, invoice untouched.
        with self.assertRaises(pcs.PlanChangeError):
            pcs_module.execute_platform_admin_plan_override(self.store, plan_b, actor=superuser, reason="QA")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_version_id, self.cheap.pk)
        invoice_a_to_c.refresh_from_db()
        self.assertTrue(invoice_a_to_c.is_payable)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE,
            ).count(),
            1,
        )

        # (3) Void the open decision through the canonical billing lifecycle,
        # then the SAME override succeeds.
        invoice_service.void_invoice(invoice_a_to_c)
        pcs_module.execute_platform_admin_plan_override(self.store, plan_b, actor=superuser, reason="QA")
        ent.clear_entitlement_cache()
        current_after_move = ent.get_current_subscription(self.store)
        self.assertEqual(current_after_move.plan_version_id, plan_b.pk)

        # (4) A fresh, independently-generated B->C decision creates its own
        # fresh invoice — the voided A->C invoice is never reused.
        token_b_to_c = pcs._preview_token(current_after_move, plan_c)
        self.assertNotEqual(token_b_to_c, token_a_to_c)
        kind_b_to_c, invoice_b_to_c = pcb.start_plan_change(self.sub, plan_c, preview_token=token_b_to_c)

        self.assertEqual(kind_b_to_c, "invoice")
        self.assertNotEqual(invoice_b_to_c.pk, invoice_a_to_c.pk)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=plan_c,
            ).count(),
            2,
        )
        # The old A->C invoice remains VOID (closed history, never touched
        # again); it is not payable and was never silently repurposed.
        invoice_a_to_c.refresh_from_db()
        self.assertEqual(invoice_a_to_c.status, SubscriptionInvoice.Status.VOID)
        self.assertTrue(invoice_b_to_c.is_payable)

    def test_competing_different_target_upgrade_is_rejected_while_one_is_still_payable(self):
        """SUB-001 Repair 3 required test: source A, targets C and D. A->C
        succeeds and creates exactly one payable invoice. A->D, requested
        while A->C is still payable, MUST be rejected outright
        (``PlanChangeBillingError``) — no second invoice, no D invoice, the
        subscription stays on A, and no PLAN_CHANGED event is recorded."""
        plan_c = self.pricey
        plan_d = _published("idem-plan-d", price="500000")

        token_a_to_c = pcs._preview_token(ent.get_current_subscription(self.store), plan_c)
        kind_c, invoice_c = pcb.start_plan_change(self.sub, plan_c, preview_token=token_a_to_c)
        self.assertEqual(kind_c, "invoice")
        self.assertTrue(invoice_c.is_payable)

        events_before = self.sub.events.filter(
            event_type=SubscriptionEvent.EventType.PLAN_CHANGED,
        ).count()

        token_a_to_d = pcs._preview_token(ent.get_current_subscription(self.store), plan_d)
        with self.assertRaises(pcb.PlanChangeBillingError):
            pcb.start_plan_change(self.sub, plan_d, preview_token=token_a_to_d)

        # Exactly one payable PLAN_CHANGE invoice — still the original C one.
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE,
                status__in=SubscriptionInvoice.PAYABLE_STATUSES,
            ).count(),
            1,
        )
        self.assertFalse(
            SubscriptionInvoice.objects.filter(
                subscription=self.sub, kind=SubscriptionInvoice.Kind.PLAN_CHANGE, plan_version=plan_d,
            ).exists()
        )
        # Subscription never moved off A.
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan_version_id, self.cheap.pk)
        # No new PLAN_CHANGED event was recorded by the rejected attempt.
        events_after = self.sub.events.filter(
            event_type=SubscriptionEvent.EventType.PLAN_CHANGED,
        ).count()
        self.assertEqual(events_before, events_after)
