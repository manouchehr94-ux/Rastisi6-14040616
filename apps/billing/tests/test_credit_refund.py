"""Checkpoint 5B commit 9 (ADR-81): Credit Notes and Subscription Refunds.
Amount bounds, uniqueness, no double refund, provider abstraction, manual
completion, and invoice refunded-status sync."""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import (
    SubscriptionCreditNote,
    SubscriptionInvoice,
    SubscriptionPaymentAttempt,
    SubscriptionRefund,
)
from apps.billing.services import (
    attempt_service,
    confirmation_service,
    credit_note_service,
    invoice_service,
    refund_service,
)
from apps.stores.models import Store
from apps.subscriptions.models import Plan, PlanVersion
from apps.subscriptions.services import subscription_service as sub_svc


def _paid_invoice(slug, *, price="400000"):
    store = Store.objects.create(name="ف", slug=slug, admin_subdomain=slug)
    plan = Plan.objects.create(code=f"pl-{slug}", name="Plan")
    version = PlanVersion.objects.create(
        plan=plan, version_number=1, status=PlanVersion.Status.PUBLISHED,
        display_price=Decimal(price), currency="IRT",
    )
    sub = sub_svc.create_subscription(store, version)
    sub = sub_svc.activate_subscription(sub)
    invoice = invoice_service.create_invoice(
        sub, kind=SubscriptionInvoice.Kind.INITIAL, lines=[invoice_service.plan_line_spec(version)],
    )
    invoice = invoice_service.open_invoice(invoice)
    attempt = attempt_service.create_attempt(invoice)
    confirmation_service.confirm_payment(
        attempt=attempt, amount=invoice.amount_due, currency="IRT", provider_payment_id=f"pay-{slug}",
    )
    invoice.refresh_from_db()
    return store, invoice


class CreditNoteTests(TestCase):
    def setUp(self):
        self.store, self.invoice = _paid_invoice("cn-store")

    def test_issue_credit_note(self):
        cn = credit_note_service.issue_credit_note(self.invoice, amount=Decimal("100000"), reason="خطا")
        self.assertEqual(cn.status, SubscriptionCreditNote.Status.ISSUED)
        self.assertTrue(cn.number.startswith("CN-"))
        self.assertEqual(cn.amount, Decimal("100000"))

    def test_cannot_exceed_paid_amount(self):
        with self.assertRaises(credit_note_service.CreditNoteError):
            credit_note_service.issue_credit_note(self.invoice, amount=Decimal("500000"))

    def test_zero_amount_rejected(self):
        with self.assertRaises(credit_note_service.CreditNoteError):
            credit_note_service.issue_credit_note(self.invoice, amount=Decimal("0"))

    def test_eligible_decreases_after_issue(self):
        credit_note_service.issue_credit_note(self.invoice, amount=Decimal("300000"))
        # Only 100000 left eligible.
        with self.assertRaises(credit_note_service.CreditNoteError):
            credit_note_service.issue_credit_note(self.invoice, amount=Decimal("150000"))
        credit_note_service.issue_credit_note(self.invoice, amount=Decimal("100000"))

    def test_void_credit_note(self):
        cn = credit_note_service.issue_credit_note(self.invoice, amount=Decimal("100000"))
        voided = credit_note_service.void_credit_note(cn)
        self.assertEqual(voided.status, SubscriptionCreditNote.Status.VOID)
        # Voiding frees eligibility again.
        credit_note_service.issue_credit_note(self.invoice, amount=Decimal("400000"))


@override_settings(RASTISI_BILLING_PROVIDER="manual")
class RefundTests(TestCase):
    def setUp(self):
        self.store, self.invoice = _paid_invoice("rf-store")

    def test_request_refund_is_pending_for_manual_provider(self):
        refund = refund_service.request_refund(self.invoice, amount=Decimal("100000"), reason="عودت")
        # Manual provider does not auto-confirm.
        self.assertEqual(refund.status, SubscriptionRefund.Status.PENDING)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PAID)  # not refunded until completed

    def test_manual_completion_updates_invoice(self):
        refund = refund_service.request_refund(self.invoice, amount=Decimal("400000"))
        refund_service.complete_refund_manually(refund)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.REFUNDED)

    def test_partial_refund_marks_partially_refunded(self):
        refund = refund_service.request_refund(self.invoice, amount=Decimal("100000"))
        refund_service.complete_refund_manually(refund)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.Status.PARTIALLY_REFUNDED)

    def test_cannot_exceed_refundable(self):
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(self.invoice, amount=Decimal("500000"))

    def test_no_double_refund_beyond_paid(self):
        refund_service.request_refund(self.invoice, amount=Decimal("300000"), idempotency_key="r1")
        # 300000 already reserved (pending); only 100000 left.
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(self.invoice, amount=Decimal("200000"), idempotency_key="r2")

    def test_idempotent_request(self):
        first = refund_service.request_refund(self.invoice, amount=Decimal("100000"), idempotency_key="same")
        second = refund_service.request_refund(self.invoice, amount=Decimal("100000"), idempotency_key="same")
        self.assertEqual(first.pk, second.pk)


    def test_retry_key_rejects_other_invoice_and_modified_amount(self):
        first = refund_service.request_refund(
            self.invoice, amount=Decimal("100000"), idempotency_key="p0-bill-key",
        )
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(
                self.invoice, amount=Decimal("200000"), idempotency_key="p0-bill-key",
            )
        _other_store, other_invoice = _paid_invoice("p0-bill-other")
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(
                other_invoice, amount=Decimal("100000"), idempotency_key="p0-bill-key",
            )
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=other_invoice).count(), 0)
        self.assertEqual(first.invoice_id, self.invoice.pk)

    def test_foreign_payment_attempt_and_credit_note_rejected(self):
        _other_store, other_invoice = _paid_invoice("p0-bill-related")
        foreign_attempt = SubscriptionPaymentAttempt.objects.get(invoice=other_invoice)
        foreign_credit = credit_note_service.issue_credit_note(other_invoice, amount=Decimal("50000"))
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(
                self.invoice, amount=Decimal("50000"), payment_attempt=foreign_attempt,
            )
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(
                self.invoice, amount=Decimal("50000"), credit_note=foreign_credit,
            )
        self.assertFalse(SubscriptionRefund.objects.filter(invoice=self.invoice).exists())

    def test_retry_key_rejects_changed_reason_or_credit_note(self):
        refund_service.request_refund(
            self.invoice, amount=Decimal("100000"), idempotency_key="p0-bill-meta",
        )
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(
                self.invoice, amount=Decimal("100000"), reason="changed", idempotency_key="p0-bill-meta",
            )
        credit = credit_note_service.issue_credit_note(self.invoice, amount=Decimal("50000"))
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(
                self.invoice, amount=Decimal("100000"), credit_note=credit, idempotency_key="p0-bill-meta",
            )

    def test_zero_amount_rejected(self):
        with self.assertRaises(refund_service.RefundError):
            refund_service.request_refund(self.invoice, amount=Decimal("0"))
