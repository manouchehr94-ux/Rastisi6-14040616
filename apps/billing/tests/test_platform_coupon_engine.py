"""Platform (SaaS) coupon engine: calculation, eligibility, invoice snapshot, reservation lifecycle, payment/retry/callback
idempotency, zero-value settlement, refund policy, tenant isolation, concurrency and audit.

Separate from the merchant/store coupon domain in ``apps.cart``."""

import threading
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.billing.models import (
    PlatformCoupon,
    PlatformCouponAuditEvent,
    PlatformCouponRedemption as Redemption,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
)
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    invoice_service,
    payment_flow_service,
    refund_service,
    renewal_service,
)
from apps.billing.services import platform_coupon_service as svc
from apps.billing.services.platform_coupon_service import CouponError
from apps.core.models import AuditLogEntry
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import Plan, PlanVersion, PlanVersionPrice, StoreSubscription
from apps.subscriptions.services import subscription_service as sub_svc

User = get_user_model()
MONTHLY = Decimal("400000")
YEARLY = Decimal("9600000")


def make_plan(code="pc", monthly=MONTHLY, yearly=YEARLY):
    plan = Plan.objects.create(code=code, name=code)
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED, display_price=monthly, currency="IRT",
        billing_interval=PlanVersion.BillingInterval.MONTHLY,
    )
    if yearly is not None:
        PlanVersionPrice.objects.create(plan_version=version, billing_interval="yearly", price=yearly)
    return plan, version


def make_store(slug):
    return Store.objects.create(name=slug, slug=slug, admin_subdomain=slug)


def make_invoice(store, version, *, kind=SubscriptionInvoice.Kind.INITIAL, interval=None, open_=True, subscription=None):
    sub = subscription or StoreSubscription.objects.filter(store=store).first() or sub_svc.create_subscription(store, version)
    inv = invoice_service.create_invoice(
        sub, kind=kind, lines=[invoice_service.plan_line_spec(version, billing_interval=interval)],
    )
    return invoice_service.open_invoice(inv) if open_ else inv


def make_coupon(admin, code="WELCOME20", **kw):
    kw.setdefault("name", code or "auto")
    kw.setdefault("kind", PlatformCoupon.Kind.PERCENT)
    if kw["kind"] == PlatformCoupon.Kind.PERCENT:
        kw.setdefault("percent", 20)
    else:
        kw.setdefault("fixed_amount", Decimal("100000"))
    plans, stores = kw.pop("plans", ()), kw.pop("stores", ())
    return svc.create_coupon(actor=admin, code=code, plans=plans, stores=stores, **kw)


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("pc-admin", password="x", is_staff=True, is_superuser=True)
        self.plan, self.version = make_plan()
        self.store = make_store("pc-a")
        self.store_b = make_store("pc-b")

    def invoice(self, store=None, **kw):
        return make_invoice(store or self.store, self.version, **kw)

    def pay(self, invoice, provider_id="pay-1"):
        invoice.refresh_from_db()
        attempt = attempt_service.create_attempt(invoice, provider="manual")
        confirmation_service.confirm_payment(
            attempt=attempt, amount=invoice.amount_due, currency="IRT", provider_payment_id=provider_id,
        )
        return attempt


class CalculationTests(Base):
    def calc(self, coupon, amount):
        return svc.calculate_discount(coupon, Decimal(amount))

    def test_percent_fixed_cap_min_and_clamp(self):
        pct = make_coupon(self.admin, "P20")
        self.assertEqual(self.calc(pct, "400000"), Decimal("80000"))
        capped = make_coupon(self.admin, "CAP", percent=50, max_discount_amount=Decimal("100000"))
        self.assertEqual(self.calc(capped, "400000"), Decimal("100000"))
        fixed = make_coupon(self.admin, "RASTISI500", kind="fixed", fixed_amount=Decimal("500000"))
        self.assertEqual(self.calc(fixed, "9600000"), Decimal("500000"))
        self.assertEqual(self.calc(fixed, "300000"), Decimal("300000"))        # never exceeds the price
        self.assertEqual(self.calc(fixed, "0"), Decimal("0"))

    def test_rounding_is_integer_toman_rounded_down(self):
        c = make_coupon(self.admin, "R33", percent=33)
        self.assertEqual(self.calc(c, "100001"), Decimal("33000"))             # 33000.33 -> 33000
        self.assertEqual(self.calc(c, "5"), Decimal("1"))

    def test_yearly_and_monthly_prices_come_from_plan_version(self):
        make_coupon(self.admin, "YEARLY30", percent=30, intervals=["yearly"])
        y = svc.evaluate(self.store, plan_version=self.version, interval="yearly", purpose="initial", code="yearly30")
        self.assertTrue(y.ok)
        self.assertEqual((y.original_amount, y.discount_amount, y.final_amount),
                         (YEARLY, Decimal("2880000"), Decimal("6720000")))
        m = svc.evaluate(self.store, plan_version=self.version, interval="monthly", purpose="initial", code="YEARLY30")
        self.assertEqual(m.code, "ineligible_interval")
        self.assertEqual(m.message, svc.MESSAGES["ineligible_interval"])
        q = svc.evaluate(self.store, plan_version=self.version, interval="quarterly", purpose="initial", code="YEARLY30")
        self.assertFalse(q.ok)                                                 # interval not offered by this version

    def test_code_normalisation_case_and_persian_digits(self):
        make_coupon(self.admin, "OFF۲۰")
        self.assertTrue(svc.evaluate(self.store, plan_version=self.version, interval="monthly", purpose="initial", code=" off20 ").ok)
        with self.assertRaises(Exception):
            make_coupon(self.admin, "off20")                                    # unique, case-normalised


class EligibilityTests(Base):
    def ev(self, code, store=None, interval="monthly", purpose="initial", now=None):
        return svc.evaluate(store or self.store, plan_version=self.version, interval=interval, purpose=purpose, code=code, now=now)

    def test_invalid_inactive_scheduled_expired(self):
        now = timezone.now()
        self.assertEqual(self.ev("NOPE").code, "invalid_code")
        c = make_coupon(self.admin, "A1")
        svc.set_coupon_status(c, "disabled", actor=self.admin)
        self.assertEqual(self.ev("A1").code, "inactive")
        svc.set_coupon_status(c, "active", actor=self.admin)
        self.assertTrue(self.ev("A1").ok)
        make_coupon(self.admin, "FUT", starts_at=now + timedelta(days=1))
        self.assertEqual(self.ev("FUT").code, "not_started")
        make_coupon(self.admin, "OLD", starts_at=now - timedelta(days=3), ends_at=now - timedelta(days=1))
        self.assertEqual(self.ev("OLD").code, "expired")
        self.assertEqual(PlatformCoupon.objects.get(code="FUT").derived_state(), "scheduled")
        self.assertEqual(PlatformCoupon.objects.get(code="OLD").derived_state(), "expired")
        self.assertTrue(self.ev("FUT", now=now + timedelta(days=2)).ok)

    def test_plan_purpose_min_amount(self):
        other_plan, _ = make_plan("other")
        make_coupon(self.admin, "ONLYOTHER", plans=[other_plan])
        self.assertEqual(self.ev("ONLYOTHER").code, "ineligible_plan")
        make_coupon(self.admin, "RENEWONLY", allow_initial=False, allow_renewal=True)
        self.assertEqual(self.ev("RENEWONLY").code, "ineligible_purpose")
        self.assertTrue(self.ev("RENEWONLY", purpose="renewal").ok)
        make_coupon(self.admin, "MIN", min_amount=Decimal("1000000"))
        self.assertEqual(self.ev("MIN").code, "min_amount")
        self.assertTrue(self.ev("MIN", interval="yearly").ok)

    def test_first_purchase_only_uses_paid_history_not_failed_attempts(self):
        make_coupon(self.admin, "FIRST", first_purchase_only=True)
        inv = self.invoice()
        attempt = attempt_service.create_attempt(inv, provider="manual")
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(status="failed")
        self.assertTrue(self.ev("FIRST").ok)                                    # failed payment does not count
        self.pay(inv)
        self.assertEqual(self.ev("FIRST").code, "first_purchase_only")
        self.assertTrue(self.ev("FIRST", store=self.store_b).ok)                 # other merchant unaffected

    def test_private_coupon_is_not_disclosed_to_other_merchants(self):
        make_coupon(self.admin, "VIP", stores=[self.store])
        mine = self.ev("VIP")
        theirs = self.ev("VIP", store=self.store_b)
        unknown = self.ev("DOESNOTEXIST", store=self.store_b)
        self.assertTrue(mine.ok)
        self.assertEqual(theirs.code, "not_authorized")
        self.assertEqual(theirs.message, unknown.message)                       # indistinguishable text

    def test_global_and_per_store_limits_and_derived_exhausted(self):
        make_coupon(self.admin, "ONCE", max_redemptions=1)
        make_coupon(self.admin, "PERSTORE", max_per_store=1)
        inv = self.invoice()
        svc.apply_coupon_to_invoice(inv, code="ONCE")
        self.assertEqual(self.ev("ONCE", store=self.store_b).code, "limit_reached")
        self.assertEqual(PlatformCoupon.objects.get(code="ONCE").derived_state(), "exhausted")
        svc.apply_coupon_to_invoice(inv, code="ONCE")                            # same invoice: idempotent, not "limit reached"
        inv2 = self.invoice()
        svc.apply_coupon_to_invoice(inv2, code="PERSTORE")
        inv3 = self.invoice()
        with self.assertRaises(CouponError) as ctx:
            svc.apply_coupon_to_invoice(inv3, code="PERSTORE")
        self.assertEqual(ctx.exception.code, "store_limit_reached")
        self.assertTrue(self.ev("PERSTORE", store=self.store_b).ok)

    def test_automatic_best_discount_without_code_and_manual_replaces_it(self):
        make_coupon(self.admin, None, name="auto10", is_automatic=True, percent=10)
        make_coupon(self.admin, None, name="auto15", is_automatic=True, percent=15, allow_renewal=True)
        best = self.ev("")
        self.assertTrue(best.ok and best.automatic)
        self.assertEqual(best.discount_amount, Decimal("60000"))
        make_coupon(self.admin, "MANUAL5", percent=5)
        inv = self.invoice()
        self.assertEqual(svc.apply_automatic_to_invoice(inv).discount_amount, Decimal("60000"))
        replaced = svc.apply_coupon_to_invoice(inv, code="MANUAL5")             # explicit code replaces automatic
        self.assertEqual(replaced.discount_amount, Decimal("20000"))
        inv.refresh_from_db()
        self.assertEqual(inv.discount_total, Decimal("20000"))
        self.assertEqual(Redemption.objects.filter(invoice=inv).count(), 1)
        make_coupon(self.admin, "MANUAL6", percent=6)
        with self.assertRaises(CouponError) as ctx:                              # no stacking / manual swap
            svc.apply_coupon_to_invoice(inv, code="MANUAL6")
        self.assertEqual(ctx.exception.code, "incompatible")
        self.assertFalse(svc.STACKING_ALLOWED)

    def test_renewal_automatic_discount_applies_to_that_invoice_only(self):
        make_coupon(self.admin, None, name="renew", is_automatic=True, percent=10, allow_initial=False, allow_renewal=True)
        sub = sub_svc.activate_subscription(sub_svc.create_subscription(self.store, self.version))
        inv = make_invoice(self.store, self.version, kind="renewal", subscription=sub)
        self.assertIsNone(Redemption.objects.filter(invoice=inv).first())        # created directly (no hook)
        self.assertEqual(svc.apply_automatic_to_invoice(inv).discount_amount, Decimal("40000"))
        # next period renewal is a different invoice; nothing recurs on its own
        inv2 = invoice_service.create_invoice(
            sub, kind="renewal", lines=[invoice_service.plan_line_spec(self.version)],
            period_start=timezone.now() + timedelta(days=60),
        )
        self.assertEqual(inv2.discount_total, 0)


class InvoiceSnapshotTests(Base):
    def test_apply_snapshots_discount_and_edits_do_not_change_invoice(self):
        c = make_coupon(self.admin, "SNAP", percent=25)
        inv = self.invoice()
        redemption = svc.apply_coupon_to_invoice(inv, code="snap", actor=self.admin)
        inv.refresh_from_db()
        self.assertEqual((inv.subtotal, inv.discount_total, inv.grand_total, inv.amount_due),
                         (MONTHLY, Decimal("100000"), Decimal("300000"), Decimal("300000")))
        self.assertEqual(inv.coupon_snapshot["code"], "SNAP")
        self.assertEqual(inv.coupon_snapshot["applies_to"], "this_invoice_only")
        self.assertEqual(redemption.status, Redemption.Status.RESERVED)
        svc.update_coupon(c, actor=self.admin, percent=90)
        svc.set_coupon_status(c, "archived", actor=self.admin)
        inv.refresh_from_db()
        self.assertEqual(inv.grand_total, Decimal("300000"))
        self.assertEqual(inv.coupon_snapshot["percent"], 25)

    def test_paid_invoice_is_never_changed_by_a_coupon(self):
        make_coupon(self.admin, "LATE")
        inv = self.invoice()
        self.pay(inv)
        for call in (lambda: svc.apply_coupon_to_invoice(inv, code="LATE"), lambda: svc.remove_coupon_from_invoice(inv)):
            with self.assertRaises(CouponError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, "invoice_locked")
        inv.refresh_from_db()
        self.assertEqual(inv.grand_total, MONTHLY)
        self.assertEqual(inv.discount_total, 0)

    def test_coupon_removal_before_payment_restores_full_price_and_frees_quota(self):
        make_coupon(self.admin, "RM", max_redemptions=1)
        inv = self.invoice()
        svc.apply_coupon_to_invoice(inv, code="RM")
        removed = svc.remove_coupon_from_invoice(inv, actor=self.admin)
        inv.refresh_from_db()
        self.assertEqual((inv.grand_total, inv.discount_total, inv.coupon_snapshot), (MONTHLY, 0, {}))
        self.assertEqual(removed.status, Redemption.Status.RELEASED)
        self.assertTrue(svc.evaluate(self.store_b, plan_version=self.version, interval="monthly", purpose="initial", code="RM").ok)
        svc.apply_coupon_to_invoice(inv, code="RM")                              # can re-apply (same redemption row reused)
        self.assertEqual(Redemption.objects.filter(invoice=inv).count(), 1)

    def test_no_coupon_regression_and_tampered_inputs_are_ignored(self):
        inv = self.invoice()
        self.assertEqual((inv.discount_total, inv.grand_total, inv.coupon_snapshot), (0, MONTHLY, {}))
        self.pay(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.status, SubscriptionInvoice.Status.PAID)
        self.assertFalse(Redemption.objects.exists())
        # the API takes no price/discount parameters at all
        with self.assertRaises(TypeError):
            svc.apply_coupon_to_invoice(self.invoice(), code="X", discount=Decimal("1"))
        with self.assertRaises(TypeError):
            svc.evaluate(self.store, plan_version=self.version, interval="monthly", purpose="initial", code="X", amount=Decimal("1"))

    def test_discount_never_makes_invoice_negative(self):
        make_coupon(self.admin, "HUGE", kind="fixed", fixed_amount=Decimal("99999999"))
        inv = self.invoice()
        svc.apply_coupon_to_invoice(inv, code="HUGE")
        inv.refresh_from_db()
        self.assertEqual((inv.discount_total, inv.grand_total, inv.amount_due), (MONTHLY, 0, 0))

    def test_unsupported_invoice_shapes_rejected(self):
        make_coupon(self.admin, "OKAY", allow_renewal=True)
        inv = self.invoice(open_=False)
        invoice_service.add_line(inv, {"line_type": "manual_adjustment", "description": "x", "unit_amount": Decimal("5")})
        with self.assertRaises(CouponError) as ctx:
            svc.apply_coupon_to_invoice(inv, code="OKAY")
        self.assertEqual(ctx.exception.code, "unsupported_invoice")
        manual = self.invoice(kind="manual")
        with self.assertRaises(CouponError):
            svc.apply_coupon_to_invoice(manual, code="OKAY")


class PaymentLifecycleTests(Base):
    def setUp(self):
        super().setUp()
        self.coupon = make_coupon(self.admin, "PAYME", max_redemptions=1, percent=50)
        self.inv = self.invoice()
        svc.apply_coupon_to_invoice(self.inv, code="PAYME")
        self.inv.refresh_from_db()

    def redemption(self):
        return Redemption.objects.get(invoice=self.inv)

    def test_success_redeems_once_and_activates_and_duplicate_confirm_is_idempotent(self):
        attempt = self.pay(self.inv)
        self.inv.refresh_from_db()
        self.assertEqual((self.inv.status, self.inv.amount_paid), ("paid", Decimal("200000")))
        self.assertEqual(self.redemption().status, Redemption.Status.REDEEMED)
        self.assertEqual(StoreSubscription.objects.get(pk=self.inv.subscription_id).status, "active")
        for _ in range(2):                                                       # repeated callback / duplicate completion
            confirmation_service.confirm_payment(attempt=attempt, amount=Decimal("200000"), currency="IRT")
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.amount_paid, Decimal("200000"))
        self.assertEqual(self.coupon.counted_redemptions(), 1)
        self.assertEqual(PlatformCouponAuditEvent.objects.filter(action="redeemed").count(), 1)

    def test_failed_attempt_does_not_consume_quota_and_retry_does_not_duplicate_discount(self):
        a1 = attempt_service.create_attempt(self.inv, provider="manual")
        SubscriptionPaymentAttempt.objects.filter(pk=a1.pk).update(status="failed")
        self.assertEqual(self.redemption().status, Redemption.Status.RESERVED)
        later = timezone.now() + svc.reservation_lifetime() + timedelta(minutes=1)
        self.assertEqual(self.coupon.counted_redemptions(now=later), 0)          # expired reservation frees the quota
        self.assertTrue(svc.evaluate(self.store_b, plan_version=self.version, interval="monthly", purpose="initial",
                                     code="PAYME", now=later).ok)
        svc.ensure_reservation_active(self.inv)                                  # retry on the same invoice
        svc.apply_coupon_to_invoice(self.inv, code="PAYME")                      # browser double submit
        self.inv.refresh_from_db()
        self.assertEqual((self.inv.discount_total, self.inv.grand_total), (Decimal("200000"), Decimal("200000")))
        self.assertEqual(Redemption.objects.filter(invoice=self.inv).count(), 1)
        self.pay(self.inv)
        self.assertEqual(self.redemption().status, Redemption.Status.REDEEMED)

    @override_settings(PLATFORM_COUPON_RESERVATION_MINUTES=5)
    def test_reservation_lifetime_is_configurable(self):
        svc.remove_coupon_from_invoice(self.inv)
        row = svc.apply_coupon_to_invoice(self.inv, code="PAYME")
        self.assertEqual(row.expires_at - row.reserved_at, timedelta(minutes=5))
        self.assertEqual(svc.reservation_lifetime(), timedelta(minutes=5))

    def test_default_reservation_lifetime_is_30_minutes(self):
        self.assertEqual(self.redemption().expires_at - self.redemption().reserved_at, timedelta(minutes=30))

    def test_reservation_expiry_and_lost_race_on_retry(self):
        later = timezone.now() + timedelta(minutes=31)
        # another merchant takes the freed quota
        inv_b = self.invoice(self.store_b)
        svc.apply_coupon_to_invoice(inv_b, code="PAYME", now=later)
        self.assertEqual(svc.release_expired_reservations(now=later), 1)
        with self.assertRaises(CouponError) as ctx:
            svc.ensure_reservation_active(self.inv, now=later)
        self.assertEqual(ctx.exception.code, "reservation_lost")
        with self.assertRaises(payment_flow_service.PaymentFlowError):
            payment_flow_service.start_payment(self.inv, now=later)
        svc.remove_coupon_from_invoice(self.inv)                                 # merchant may continue at full price
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.grand_total, MONTHLY)

    def test_expired_reservation_is_reclaimed_when_quota_still_free(self):
        later = timezone.now() + svc.reservation_lifetime() + timedelta(minutes=1)
        self.assertEqual(svc.release_expired_reservations(now=later), 1)
        self.assertEqual(self.redemption().status, Redemption.Status.RELEASED)
        svc.ensure_reservation_active(self.inv, now=later)
        self.assertEqual(self.redemption().status, Redemption.Status.RESERVED)

    def test_payment_already_made_honours_discount_even_if_reservation_was_released(self):
        attempt = attempt_service.create_attempt(self.inv, provider="manual")
        svc.release_expired_reservations(now=timezone.now() + timedelta(days=1))
        confirmation_service.confirm_payment(attempt=attempt, amount=self.inv.amount_due, currency="IRT")
        self.assertEqual(self.redemption().status, Redemption.Status.REDEEMED)

    def test_inflight_payment_blocks_coupon_changes(self):
        attempt_service.create_attempt(self.inv, provider="manual")
        with self.assertRaises(CouponError) as ctx:
            svc.remove_coupon_from_invoice(self.inv)
        self.assertEqual(ctx.exception.code, "payment_in_progress")

    def test_void_releases_reservation(self):
        invoice_service.void_invoice(self.inv)
        self.assertEqual(self.redemption().status, Redemption.Status.RELEASED)
        self.assertEqual(self.coupon.counted_redemptions(), 0)

    def test_audit_trail_names_actor_coupon_and_invoice_without_secrets(self):
        svc.update_coupon(self.coupon, actor=self.admin, percent=40)
        svc.set_coupon_status(self.coupon, "disabled", actor=self.admin)
        self.pay(self.inv)
        actions = list(self.coupon.audit_events.values_list("action", flat=True))
        for expected in ("created", "updated", "disabled", "reserved", "redeemed"):
            self.assertIn(expected, actions)
        created = self.coupon.audit_events.get(action="created")
        self.assertEqual(created.actor, self.admin)
        self.assertEqual(self.coupon.audit_events.get(action="redeemed").invoice, self.inv)
        self.assertEqual(self.coupon.audit_events.get(action="updated").detail["changes"]["percent"], {"from": 50, "to": 40})
        self.assertTrue(AuditLogEntry.objects.filter(store=self.store, action_code="billing.platform_coupon_applied").exists())
        with self.assertRaises(Exception):
            created.save()
        with self.assertRaises(Exception):
            created.delete()
        self.assertEqual(self.coupon.redemptions.count(), 1)
        self.assertEqual(svc.redemptions_for(self.coupon).first().invoice, self.inv)


class RefundPolicyTests(Base):
    def paid(self, code="RF"):
        make_coupon(self.admin, code, max_redemptions=1)
        inv = self.invoice()
        svc.apply_coupon_to_invoice(inv, code=code)
        self.pay(inv)
        inv.refresh_from_db()
        return inv

    def test_full_refund_within_window_reverses_and_frees_quota(self):
        inv = self.paid()
        refund_service.request_refund(inv, amount=inv.amount_paid, idempotency_key="rf-1")
        refund_service.complete_refund_manually(inv.refunds.get())
        inv.refresh_from_db()
        self.assertEqual(inv.status, "refunded")
        self.assertEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.REVERSED)
        self.assertTrue(svc.evaluate(self.store_b, plan_version=self.version, interval="monthly", purpose="initial", code="RF").ok)

    def test_partial_refund_and_late_full_refund_keep_it_consumed(self):
        inv = self.paid("RF2")
        refund_service.request_refund(inv, amount=Decimal("1000"), idempotency_key="rf-p")
        refund_service.complete_refund_manually(inv.refunds.get())
        self.assertEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.REDEEMED)
        SubscriptionInvoice.objects.filter(pk=inv.pk).update(paid_at=timezone.now() - timedelta(days=3))
        refund_service.request_refund(inv, amount=inv.amount_paid - Decimal("1000"), idempotency_key="rf-q")
        refund_service.complete_refund_manually(inv.refunds.get(idempotency_key="rf-q"))
        self.assertEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.REDEEMED)
        self.assertTrue(PlatformCouponAuditEvent.objects.filter(action="refund_kept_consumed").exists())

    def test_credit_note_does_not_change_consumption(self):
        from apps.billing.services import credit_note_service

        inv = self.paid("RF3")
        credit_note_service.issue_credit_note(inv, amount=Decimal("1000"), reason="x")
        self.assertEqual(Redemption.objects.get(invoice=inv).status, Redemption.Status.REDEEMED)


class ZeroValueSettlementTests(Base):
    def setUp(self):
        super().setUp()
        make_coupon(self.admin, "FREE100", percent=100)
        self.inv = self.invoice()
        svc.apply_coupon_to_invoice(self.inv, code="FREE100")
        self.inv.refresh_from_db()
        self.owner = User.objects.create_user("pc-owner", password="x", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.outsider = User.objects.create_user("pc-out", password="x", is_staff=True)
        StoreMembership.objects.create(store=self.store_b, user=self.outsider, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())

    def test_full_discount_gives_zero_payable_invoice(self):
        self.assertEqual((self.inv.grand_total, self.inv.amount_due, self.inv.discount_total), (0, 0, MONTHLY))

    def test_owner_settles_without_gateway_and_activates_exactly_once(self):
        with mock.patch("apps.billing.providers.registry.get_provider") as provider:
            settled = svc.settle_zero_value_invoice(self.inv, actor=self.owner)
            again = svc.settle_zero_value_invoice(self.inv, actor=self.owner)       # repeated settlement
            confirmation_service.settle_zero_due_invoice(self.inv, actor=self.owner)
        provider.assert_not_called()
        self.assertEqual(settled.status, "paid")
        self.assertEqual(again.status, "paid")
        self.assertEqual(SubscriptionPaymentAttempt.objects.filter(invoice=self.inv).count(), 1)
        attempt = SubscriptionPaymentAttempt.objects.get(invoice=self.inv)
        self.assertEqual((attempt.provider, attempt.amount, attempt.status), ("manual", 0, "succeeded"))
        self.assertEqual(StoreSubscription.objects.get(pk=self.inv.subscription_id).status, "active")
        self.assertEqual(Redemption.objects.get(invoice=self.inv).status, Redemption.Status.REDEEMED)
        self.assertEqual(PlatformCouponAuditEvent.objects.filter(action="zero_value_settled").count(), 1)
        self.assertTrue(AuditLogEntry.objects.filter(action_code="billing.zero_invoice_settled", actor=self.owner).exists())

    def test_platform_staff_allowed_other_tenant_and_anonymous_denied(self):
        for actor in (self.outsider, None, User.objects.create_user("plain", password="x")):
            with self.assertRaises(CouponError) as ctx:
                svc.settle_zero_value_invoice(self.inv, actor=actor)
            self.assertEqual(ctx.exception.code, "forbidden")
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.status, "open")
        self.assertEqual(svc.settle_zero_value_invoice(self.inv, actor=self.admin).status, "paid")

    def test_partially_discounted_invoice_cannot_use_zero_settlement(self):
        make_coupon(self.admin, "HALF", percent=50)
        inv = self.invoice(self.store)
        svc.apply_coupon_to_invoice(inv, code="HALF")
        with self.assertRaises(CouponError) as ctx:
            svc.settle_zero_value_invoice(inv, actor=self.admin)
        self.assertEqual(ctx.exception.code, "not_zero_value")
        inv.refresh_from_db()
        self.assertEqual(inv.status, "open")

    def test_invoice_without_coupon_cannot_use_coupon_settlement(self):
        inv = self.invoice()
        with self.assertRaises(CouponError):
            svc.settle_zero_value_invoice(inv, actor=self.admin)

    def test_zero_payable_invoice_cannot_be_forged_through_normal_confirm_with_amount(self):
        attempt = attempt_service.create_attempt(self.inv, provider="manual")
        with self.assertRaises(confirmation_service.ConfirmationError):
            confirmation_service.confirm_payment(attempt=attempt, amount=MONTHLY, currency="IRT")

    def test_checkout_view_path_also_redeems_the_coupon(self):
        confirmation_service.settle_zero_due_invoice(self.inv, actor=self.owner)
        self.assertEqual(Redemption.objects.get(invoice=self.inv).status, Redemption.Status.REDEEMED)


class AdminPermissionTests(Base):
    def test_only_platform_staff_can_manage_coupons(self):
        merchant = User.objects.create_user("merchant", password="x", is_staff=True)
        staff_only = User.objects.create_user("st", password="x", is_staff=True)
        for actor in (merchant, staff_only, None):
            with self.assertRaises(CouponError) as ctx:
                svc.create_coupon(actor=actor, code="HACK", name="h", kind="percent", percent=99)
            self.assertEqual(ctx.exception.code, "forbidden")
        c = make_coupon(self.admin, "OK1")
        with self.assertRaises(CouponError):
            svc.update_coupon(c, actor=merchant, percent=99)
        with self.assertRaises(CouponError):
            svc.set_coupon_status(c, "disabled", actor=merchant)
        self.assertFalse(PlatformCoupon.objects.filter(code="HACK").exists())

    def test_model_validation_and_unknown_fields(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            svc.create_coupon(actor=self.admin, code="BAD", name="b", kind="percent", percent=101)
        with self.assertRaises(ValidationError):
            svc.create_coupon(actor=self.admin, code="BAD2", name="b", kind="fixed", fixed_amount=Decimal("0"))
        with self.assertRaises(ValidationError):
            svc.create_coupon(actor=self.admin, code="BAD3", name="b", kind="percent", percent=5, intervals=["weekly"])
        with self.assertRaises(CouponError):
            svc.create_coupon(actor=self.admin, code="BAD4", name="b", kind="percent", percent=5, created_by=self.admin)


class CartIsolationTests(TestCase):
    def test_store_coupon_domain_is_separate(self):
        from apps.cart import models as cart_models

        self.assertNotIn(PlatformCoupon, vars(cart_models).values())
        self.assertNotEqual(PlatformCoupon._meta.db_table, getattr(getattr(cart_models, "Coupon", None), "_meta", PlatformCoupon._meta).db_table)


class ContentionTests(Base):
    def test_final_allocation_sequential_atomic(self):
        """Deterministic stand-in for the race: the second merchant cannot take the single remaining allocation."""
        make_coupon(self.admin, "LAST", max_redemptions=1)
        a, b = self.invoice(self.store), self.invoice(self.store_b)
        svc.apply_coupon_to_invoice(a, code="LAST")
        with self.assertRaises(CouponError) as ctx:
            svc.apply_coupon_to_invoice(b, code="LAST")
        self.assertEqual(ctx.exception.code, "limit_reached")
        b.refresh_from_db()
        self.assertEqual((b.discount_total, b.coupon_snapshot), (0, {}))
        self.assertFalse(Redemption.objects.filter(invoice=b).exists())
        self.assertEqual(PlatformCoupon.objects.get(code="LAST").counted_redemptions(), 1)

    def test_failed_apply_rolls_back_everything(self):
        make_coupon(self.admin, "ROLL")
        inv = self.invoice()
        with mock.patch.object(svc, "_coupon_event", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                svc.apply_coupon_to_invoice(inv, code="ROLL")
        inv.refresh_from_db()
        self.assertEqual((inv.discount_total, inv.coupon_snapshot), (0, {}))
        self.assertFalse(Redemption.objects.exists())


class PostgresContentionTests(TransactionTestCase):
    """Real-thread race for the last allocation; needs row locks, so PostgreSQL only."""

    def test_two_merchants_race_for_last_allocation(self):
        if connection.vendor != "postgresql":
            self.skipTest("requires PostgreSQL select_for_update")
        admin = User.objects.create_user("race-admin", password="x", is_staff=True, is_superuser=True)
        plan, version = make_plan("race")
        make_coupon(admin, "RACE", max_redemptions=1)
        invoices = [make_invoice(make_store(f"race-{i}"), version) for i in range(2)]
        results, barrier = [], threading.Barrier(2)

        def work(invoice):
            from django.db import connection as conn

            try:
                barrier.wait()
                svc.apply_coupon_to_invoice(invoice, code="RACE")
                results.append("ok")
            except CouponError as exc:
                results.append(exc.code)
            finally:
                conn.close()

        threads = [threading.Thread(target=work, args=(i,)) for i in invoices]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(results), ["limit_reached", "ok"])
        self.assertEqual(Redemption.objects.count(), 1)


class RenewalHookTests(Base):
    def test_renewal_generation_applies_automatic_campaign_once(self):
        make_coupon(self.admin, None, name="auto-renew", is_automatic=True, percent=10, allow_initial=False,
                    allow_renewal=True)
        sub = sub_svc.activate_subscription(sub_svc.create_subscription(self.store, self.version))
        StoreSubscription.objects.filter(pk=sub.pk).update(current_period_end=timezone.now() - timedelta(days=1))
        result = renewal_service.generate_renewals(store=self.store)
        result2 = renewal_service.generate_renewals(store=self.store)
        inv = SubscriptionInvoice.objects.get(subscription=sub, kind="renewal")
        self.assertEqual(result["created"], 1)
        self.assertEqual(result2["created"], 0)
        self.assertEqual((inv.discount_total, inv.grand_total), (Decimal("40000"), Decimal("360000")))
        self.assertEqual(Redemption.objects.filter(invoice=inv).count(), 1)
