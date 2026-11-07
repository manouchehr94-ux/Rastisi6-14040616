"""Review fixes for platform coupons: reservation held across a pending manual card claim, explicit over-redemption policy
(audited), code-attempt throttling, and the expired-reservation sweeper command."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.cache import caches
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.billing.models import PlatformCouponAuditEvent, PlatformCouponRedemption as Redemption
from apps.billing.services import attempt_service, confirmation_service, invoice_service
from apps.billing.services import manual_card_service as mcs
from apps.billing.services import platform_coupon_service as svc
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.billing.tests.test_platform_card_to_card import CardToCardBase
from apps.stores.models import Store


def make_coupon(admin, code, **kw):
    kw.setdefault("name", code)
    kw.setdefault("kind", "percent")
    kw.setdefault("percent", 50)
    return svc.create_coupon(actor=admin, code=code, plans=(), stores=(), **kw)


class CouponReviewBase(CardToCardBase):
    def setUp(self):
        super().setUp()
        caches["ratelimit"].clear()
        self.addCleanup(caches["ratelimit"].clear)
        self.store_b = Store.objects.create(name="B", slug="c2c-b", admin_subdomain="c2c-b")
        _sub, self.invoice_b = open_invoice_for(self.store_b, code="c2cb", price=self.PRICE)

    def claim(self, ref="TRK-4455-6677", invoice=None, **extra):
        inv = invoice or self.invoice
        inv.refresh_from_db()                                    # amount_due changes once a coupon is applied
        return super().claim(ref, invoice=inv, **extra)

    def redemption(self, invoice):
        return Redemption.objects.get(invoice=invoice)


class ReservationHeldDuringClaimTests(CouponReviewBase):
    def test_pending_manual_claim_keeps_the_last_slot_reserved_past_the_normal_lifetime(self):
        coupon = make_coupon(self.finance, "LASTONE", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="LASTONE")
        self.invoice.refresh_from_db()
        claim = self.claim()
        res = self.redemption(self.invoice)
        self.assertGreater(res.expires_at, timezone.now() + timedelta(days=6))
        later = timezone.now() + svc.reservation_lifetime() + timedelta(hours=3)
        self.assertEqual(coupon.counted_redemptions(now=later), 1)
        result = svc.evaluate(self.store_b, plan_version=self.invoice_b.plan_version, interval="monthly", purpose="initial",
                              code="LASTONE", now=later)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "limit_reached")
        self.approve(claim)
        self.assertEqual(self.redemption(self.invoice).status, Redemption.Status.REDEEMED)
        self.assertFalse(PlatformCouponAuditEvent.objects.filter(action="over_redeemed").exists())

    def test_submitting_a_claim_re_reserves_a_lapsed_reservation_when_capacity_remains(self):
        make_coupon(self.finance, "LAPSED", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="LAPSED")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=5))
        self.claim()
        res = self.redemption(self.invoice)
        self.assertEqual(res.status, Redemption.Status.RESERVED)
        self.assertGreater(res.expires_at, timezone.now() + timedelta(days=6))

    def test_claim_is_refused_when_the_lapsed_slot_was_taken_by_someone_else(self):
        make_coupon(self.finance, "TAKEN", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="TAKEN")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=5))
        svc.apply_coupon_to_invoice(self.invoice_b, code="TAKEN")
        with self.assertRaises(mcs.ClaimError):
            self.claim()
        self.assertFalse(mcs.PlatformManualPaymentClaim.objects.exists())

    def test_cancelling_the_claim_returns_the_reservation_to_its_normal_lifetime(self):
        make_coupon(self.finance, "BACK", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="BACK")
        claim = self.claim()
        mcs.cancel_claim(claim, user=self.owner)
        res = self.redemption(self.invoice)
        self.assertLessEqual(res.expires_at, timezone.now() + svc.reservation_lifetime())

    def test_claim_on_an_invoice_without_a_coupon_is_unaffected(self):
        self.claim()
        self.assertFalse(Redemption.objects.exists())


class OverRedemptionPolicyTests(CouponReviewBase):
    def pay(self, invoice):
        invoice.refresh_from_db()
        attempt = attempt_service.create_attempt(invoice, provider="manual")
        confirmation_service.confirm_payment(attempt=attempt, amount=invoice.amount_due, currency="IRT",
                                             provider_payment_id=f"p-{invoice.pk}")

    def test_lapsed_reservation_last_slot_race_honours_paid_discount_and_audits_over_redemption(self):
        coupon = make_coupon(self.finance, "RACE", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="RACE")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=1))
        svc.apply_coupon_to_invoice(self.invoice_b, code="RACE")             # B legitimately takes the freed slot
        self.pay(self.invoice)                                               # A's money arrives anyway
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.invoice.amount_paid, Decimal("150000"))        # recorded discount honoured
        self.assertEqual(self.redemption(self.invoice).status, Redemption.Status.REDEEMED)
        event = PlatformCouponAuditEvent.objects.get(action="over_redeemed", coupon=coupon)
        self.assertEqual((event.detail["scope"], event.detail["from"]), ("total", "reserved"))
        self.assertEqual(event.invoice_id, self.invoice.pk)

    def test_normal_payment_is_not_flagged(self):
        make_coupon(self.finance, "NORMAL", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="NORMAL")
        self.pay(self.invoice)
        self.assertFalse(PlatformCouponAuditEvent.objects.filter(action="over_redeemed").exists())

    def test_per_store_cap_overage_is_flagged_with_store_scope(self):
        make_coupon(self.finance, "PERSTORE", max_per_store=1, allow_renewal=True)
        svc.apply_coupon_to_invoice(self.invoice, code="PERSTORE")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=1))
        second = invoice_service.open_invoice(invoice_service.create_invoice(
            self.sub, kind="renewal", lines=[invoice_service.plan_line_spec(self.invoice.plan_version)]))
        svc.apply_coupon_to_invoice(second, code="PERSTORE")
        self.pay(self.invoice)
        event = PlatformCouponAuditEvent.objects.get(action="over_redeemed")
        self.assertEqual(event.detail["scope"], "store")


class SweeperCommandTests(CouponReviewBase):
    def test_command_releases_only_expired_reservations_and_is_idempotent(self):
        coupon = make_coupon(self.finance, "SWEEP")
        svc.apply_coupon_to_invoice(self.invoice, code="SWEEP")
        svc.apply_coupon_to_invoice(self.invoice_b, code="SWEEP")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=1))
        out = StringIO()
        call_command("release_expired_platform_coupon_reservations", "--dry-run", stdout=out)
        self.assertIn("due=1", out.getvalue())
        self.assertEqual(self.redemption(self.invoice).status, Redemption.Status.RESERVED)
        out = StringIO()
        call_command("release_expired_platform_coupon_reservations", stdout=out)
        self.assertIn("released=1", out.getvalue())
        self.assertEqual(self.redemption(self.invoice).status, Redemption.Status.RELEASED)
        self.assertEqual(self.redemption(self.invoice).end_reason, "expired")
        self.assertEqual(self.redemption(self.invoice_b).status, Redemption.Status.RESERVED)
        out = StringIO()
        call_command("release_expired_platform_coupon_reservations", stdout=out)
        self.assertIn("released=0", out.getvalue())
        self.assertTrue(PlatformCouponAuditEvent.objects.filter(coupon=coupon, action="released").exists())


class AttemptThrottleTests(CouponReviewBase):
    @override_settings(PLATFORM_COUPON_ATTEMPTS_PER_MINUTE=3)
    def test_attempts_are_limited_per_user_and_store_then_other_users_are_unaffected(self):
        for _ in range(3):
            svc.check_attempt_rate(self.owner, self.store)
        with self.assertRaises(svc.CouponError) as ctx:
            svc.check_attempt_rate(self.owner, self.store)
        self.assertEqual(ctx.exception.code, "rate_limited")
        svc.check_attempt_rate(self.finance, self.store)
        svc.check_attempt_rate(self.owner, self.store_b)
