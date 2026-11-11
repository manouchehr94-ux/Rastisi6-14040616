"""Card-to-card has exactly ONE financial authority: CardTransferSubmission + card_transfer_service.

Covers: the complete sequence through the unified ``initiate_payment`` entry point, merchant configurations stored with the alternate
credential naming staying readable/usable, no parallel finalizer anywhere (module / URL / template), the attempt-state guard on approval,
single finalization under concurrent merchants (PostgreSQL), and the card-transfer notification."""

import ast
import pathlib
import threading
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase, TestCase, skipUnlessDBFeature
from django.urls import NoReverseMatch, reverse

from apps.notifications.models import NotificationEvent
from apps.orders.gateways import get_adapter
from apps.orders.models import CardTransferSubmission, Order, PaymentAttempt, PaymentGatewayConfig, Transaction
from apps.orders.services import card_transfer_service as svc
from apps.orders.services.gateway_payment_service import initiate_payment
from apps.orders.tests.test_card_transfer import VALID_CARD, CardTransferBase
from apps.core.tests.serialized_rollback import SerializedRollbackSafeMixin


class UnifiedSequenceTests(CardTransferBase):
    def select_method(self, order):
        return initiate_payment(order=order, gateway_config=self.config, callback_url="https://shop/cb", store=self.store)

    def test_select_submit_approve_pays_exactly_once_with_one_transaction(self):
        order = self.make_order()
        attempt = self.select_method(order)
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)             # selecting the method proves nothing
        self.assertIsNone(attempt.verified_at)
        self.assertEqual(self.select_method(order).pk, attempt.pk)                  # revisiting reuses the same open attempt
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        submission = self.submit(order)
        self.assertEqual(submission.attempt_id, attempt.pk)
        self.assertEqual(Transaction.objects.filter(order=order).count(), 0)
        svc.approve(submission.pk, store=self.store, actor=self.user)
        order.refresh_from_db(); attempt.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual((attempt.status, attempt.gateway_ref_id), (PaymentAttempt.Status.SUCCEEDED, "TRK12345"))
        self.assertEqual(Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1)
        with self.assertRaises(svc.AlreadyDecided):
            svc.approve(submission.pk, store=self.store, actor=self.user)
        self.assertEqual(Transaction.objects.filter(order=order).count(), 1)

    def test_rejection_leaves_the_order_open_and_a_resubmission_can_be_approved(self):
        order = self.make_order()
        attempt = self.select_method(order)
        first = self.submit(order, tracking="BADTRK01")
        svc.reject(first.pk, store=self.store, actor=self.user, reason="واریز دیده نشد")
        order.refresh_from_db(); attempt.refresh_from_db()
        self.assertEqual((order.payment_status, attempt.status), (Order.PaymentStatus.PENDING, PaymentAttempt.Status.PENDING))
        second = self.submit(order, tracking="GOODTRK2")
        self.assertEqual(second.attempt_id, attempt.pk)                              # same attempt, no duplicate attempt
        svc.approve(second.pk, store=self.store, actor=self.user)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 1)

    def test_selecting_card_transfer_never_calls_a_provider_or_creates_a_succeeded_attempt(self):
        order = self.make_order()
        with mock.patch.object(type(get_adapter("card_to_card")), "create_payment") as create:
            attempt = self.select_method(order)
        self.assertFalse(create.called)
        self.assertNotEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)

    def test_approval_refuses_an_attempt_that_is_no_longer_open(self):
        order = self.make_order()
        attempt = self.select_method(order)
        submission = self.submit(order)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentAttempt.Status.EXPIRED)
        with self.assertRaises(svc.CardTransferError):
            svc.approve(submission.pk, store=self.store, actor=self.user)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertEqual(Transaction.objects.filter(order=order).count(), 0)

    def test_approval_refuses_an_attempt_that_already_carries_a_verification(self):
        from django.utils import timezone

        order = self.make_order()
        attempt = self.select_method(order)
        submission = self.submit(order)
        PaymentAttempt.objects.filter(pk=attempt.pk).update(verified_at=timezone.now())
        with self.assertRaises(svc.CardTransferError):
            svc.approve(submission.pk, store=self.store, actor=self.user)

    def test_a_submission_notifies_the_merchant_once(self):
        order = self.make_order()
        self.select_method(order)
        self.submit(order)
        self.assertEqual(NotificationEvent.objects.filter(type_key="payment.card_transfer_submitted").count(), 1)


class LegacyCredentialNamingTests(CardTransferBase):
    """A configuration saved with the alternate naming (card_number / cardholder_name / iban) keeps working, unmodified."""

    def setUp(self):
        super().setUp()
        self.config.set_credentials({"card_number": VALID_CARD, "cardholder_name": "علی رضایی", "iban": "IR062960000000100324200001", "bank_name": "ملی"})
        self.config.save()

    def test_it_validates_is_configured_and_is_the_active_checkout_destination(self):
        config = PaymentGatewayConfig.objects.get(pk=self.config.pk)
        self.assertTrue(config.is_configured)
        self.assertTrue(config.can_activate)
        self.assertEqual(svc.active_config(self.store).pk, config.pk)
        destination = svc.destination_for(config)
        self.assertEqual((destination.card, destination.holder, destination.sheba), (VALID_CARD, "علی رضایی", "IR062960000000100324200001"))
        self.assertTrue(config.is_selectable_at_checkout)

    def test_the_stored_ciphertext_is_untouched_and_a_full_flow_works(self):
        before = PaymentGatewayConfig.objects.get(pk=self.config.pk).encrypted_credentials
        order = self.make_order()
        submission = self.submit(order)
        svc.approve(submission.pk, store=self.store, actor=self.user)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(PaymentGatewayConfig.objects.get(pk=self.config.pk).encrypted_credentials, before)
        self.assertEqual(submission.destination_last4 if False else CardTransferSubmission.objects.get(pk=submission.pk).destination_last4, VALID_CARD[-4:])


class SingleFinancialAuthorityTests(TestCase):
    def test_the_parallel_finalizer_does_not_exist_anywhere(self):
        root = pathlib.Path(__file__).resolve().parents[3]
        self.assertFalse((root / "apps/orders/services/card_to_card_payment_service.py").exists())
        self.assertFalse((root / "apps/dashboard/card_to_card_views.py").exists())
        for name in ("order-card-to-card-payment", "order-card-to-card-reject"):
            with self.assertRaises(NoReverseMatch):
                reverse(f"dashboard:{name}", args=["X"])

    def test_only_the_canonical_service_finalizes_card_transfers(self):
        """AST: every call of apply_payment_success carrying a card method lives in card_transfer_service."""
        root = pathlib.Path(__file__).resolve().parents[3] / "apps"
        offenders = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "CARD_TRANSFER" not in text and "card_xfer" not in text:
                continue
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "apply_payment_success":
                    if "card_transfer_service" not in str(path):
                        offenders.append(str(path))
        self.assertEqual(offenders, [])


class ConcurrentMerchantApprovalTests(SerializedRollbackSafeMixin, TransactionTestCase, ):
    """Two merchants approving the SAME submission at the same instant: one wins, one Transaction (real row locks => PostgreSQL)."""

    serialized_rollback = True

    def test_simultaneous_approvals_create_exactly_one_transaction(self):
        if connection.vendor != "postgresql":
            self.skipTest("real row locks need PostgreSQL (run with DATABASE_URL=postgres://…)")
        base = CardTransferBase()
        base.setUp()
        order = base.make_order()
        initiate_payment(order=order, gateway_config=base.config, callback_url="https://shop/cb", store=base.store)
        submission = base.submit(order)
        results, barrier = [], threading.Barrier(2)

        def worker():
            from django.db import connections
            try:
                barrier.wait(timeout=10)
                svc.approve(submission.pk, store=base.store, actor=base.user)
                results.append("ok")
            except svc.AlreadyDecided:
                results.append("already")
            except Exception as exc:  # noqa: BLE001
                results.append(type(exc).__name__)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        [t.start() for t in threads]; [t.join(30) for t in threads]
        self.assertEqual(sorted(results), ["already", "ok"], results)
        self.assertEqual(Transaction.objects.filter(order=order, status=Transaction.Status.OK).count(), 1)
        self.assertEqual(Order.objects.get(pk=order.pk).payment_status, Order.PaymentStatus.PAID)
