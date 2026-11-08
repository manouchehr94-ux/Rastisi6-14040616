"""Targeted regression tests for the remaining manual-claim and existing-invoice coupon failure paths."""

from datetime import timedelta

from django.utils import timezone

from apps.billing.models import PlatformCouponAuditEvent, PlatformCouponRedemption as Redemption
from apps.billing.services import manual_card_service as mcs
from apps.billing.services import platform_coupon_service as svc
from apps.billing.tests.test_platform_coupon_review_fixes import CouponReviewBase, make_coupon


class ClaimClosingRestoresLifetimeTests(CouponReviewBase):
    def test_rejecting_a_claim_returns_the_reservation_to_its_normal_lifetime(self):
        make_coupon(self.finance, "REJ", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="REJ")
        claim = self.claim()
        self.assertGreater(self.redemption(self.invoice).expires_at, timezone.now() + timedelta(days=6))
        mcs.reject_claim(claim, reviewer=self.finance, reason="no match")
        res = self.redemption(self.invoice)
        self.assertEqual(res.status, Redemption.Status.RESERVED)
        self.assertLessEqual(res.expires_at, timezone.now() + svc.reservation_lifetime())

    def test_expiring_a_stale_claim_returns_the_reservation_to_its_normal_lifetime(self):
        make_coupon(self.finance, "EXP", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="EXP")
        self.claim()
        later = timezone.now() + timedelta(days=mcs.REVIEW_WINDOW_DAYS, hours=1)
        self.assertEqual(mcs.expire_stale_claims(now=later), 1)
        res = self.redemption(self.invoice)
        self.assertLessEqual(res.expires_at, later + svc.reservation_lifetime())
        self.assertEqual(res.coupon.counted_redemptions(now=later + svc.reservation_lifetime() + timedelta(minutes=1)), 0)


class ClaimOnExistingInvoiceFailureTests(CouponReviewBase):
    def test_disabled_coupon_with_lapsed_reservation_refuses_the_claim_and_creates_nothing(self):
        coupon = make_coupon(self.finance, "OFF", max_redemptions=5)
        svc.apply_coupon_to_invoice(self.invoice, code="OFF")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=5))
        svc.set_coupon_status(coupon, "disabled", actor=self.finance)
        self.invoice.refresh_from_db()
        status_before, due_before = self.invoice.status, self.invoice.amount_due
        with self.assertRaises(mcs.ClaimError):
            self.claim()
        self.assertFalse(mcs.PlatformManualPaymentClaim.objects.exists())
        self.invoice.refresh_from_db()
        self.assertEqual((self.invoice.status, self.invoice.amount_due), (status_before, due_before))
        self.assertNotEqual(self.redemption(self.invoice).status, Redemption.Status.REDEEMED)

    def test_refused_claim_leaves_the_invoice_payable_and_a_later_claim_can_succeed_after_slot_frees(self):
        make_coupon(self.finance, "RETRY", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="RETRY")
        Redemption.objects.filter(invoice=self.invoice).update(expires_at=timezone.now() - timedelta(minutes=5))
        svc.apply_coupon_to_invoice(self.invoice_b, code="RETRY")
        with self.assertRaises(mcs.ClaimError):
            self.claim()
        self.invoice.refresh_from_db()
        self.assertTrue(self.invoice.is_payable)
        svc.release_for_invoice(self.invoice_b, "test")
        claim = self.claim()
        self.assertEqual(claim.status, mcs.PlatformManualPaymentClaim.Status.PENDING_REVIEW)
        self.assertEqual(self.redemption(self.invoice).status, Redemption.Status.RESERVED)

    def test_approval_after_pinned_reservation_is_lost_to_release_is_audited_not_silent(self):
        coupon = make_coupon(self.finance, "LATE", max_redemptions=1)
        svc.apply_coupon_to_invoice(self.invoice, code="LATE")
        claim = self.claim()
        # operator error / data repair released the pinned reservation, and the slot was re-sold
        Redemption.objects.filter(invoice=self.invoice).update(status=Redemption.Status.RELEASED, end_reason="manual")
        svc.apply_coupon_to_invoice(self.invoice_b, code="LATE")
        self.approve(claim)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(self.redemption(self.invoice).status, Redemption.Status.REDEEMED)
        self.assertEqual(PlatformCouponAuditEvent.objects.filter(action="over_redeemed", coupon=coupon).count(), 1)
        self.assertEqual(coupon.redemptions.filter(status=Redemption.Status.REDEEMED).count(), 1)
