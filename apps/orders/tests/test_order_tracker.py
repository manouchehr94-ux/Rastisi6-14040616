"""Customer order tracker — two independent tracks (payment / fulfilment) built only from real order data."""

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import CardTransferSubmission, Order, OrderStatusHistory
from apps.orders.services import card_transfer_service as svc
from apps.orders.services import order_tracker
from apps.orders.services.order_service import change_order_status
from apps.orders.tests.test_card_transfer import SHOP_HOST, CardTransferBase


def _tracker(order):
    order = Order.objects.select_related("payment_gateway").prefetch_related("status_history", "transactions", "card_transfers").get(pk=order.pk)
    return order_tracker.build(order)


def _states(track):
    return {s.key: s.state for s in track.steps}


@override_settings(ALLOWED_HOSTS=[SHOP_HOST, "testserver", "127.0.0.1", "localhost"])
class OrderTrackerTests(CardTransferBase):
    def approve(self, sub):
        svc.approve(sub.pk, store=self.store, actor=self.user)

    def test_awaiting_transfer_has_no_paid_signal(self):
        t = _tracker(self.make_order())
        self.assertEqual(t.payment.state_key, "awaiting_transfer")
        self.assertEqual(_states(t.payment)["transfer"], "current")
        self.assertEqual(_states(t.payment)["paid"], "todo")
        self.assertTrue(t.can_resubmit)
        self.assertIsNone(t.rejection)

    def test_submitted_is_under_review_and_not_paid(self):
        order = self.make_order()
        self.submit(order)
        t = _tracker(order)
        self.assertEqual(t.payment.state_key, "under_review")
        self.assertEqual(_states(t.payment)["review"], "current")
        self.assertEqual(_states(t.payment)["paid"], "todo")
        self.assertFalse(t.can_resubmit)
        self.assertIn("پرداخت‌نشده", t.summary)

    def test_rejected_shows_reason_and_resubmit_then_clears_after_resubmission(self):
        order = self.make_order()
        sub = self.submit(order)
        svc.reject(sub.pk, store=self.store, actor=self.user, reason="مبلغ واریزی کمتر است")
        t = _tracker(order)
        self.assertEqual(t.payment.state_key, "rejected")
        self.assertEqual(t.rejection.review_note, "مبلغ واریزی کمتر است")
        self.assertTrue(t.can_resubmit)
        self.assertEqual(_states(t.payment)["review"], "failed")
        self.submit(order, last4="5678", tracking="TRK99999")
        t = _tracker(order)
        self.assertEqual(t.payment.state_key, "resubmitted")
        self.assertIsNone(t.rejection)
        self.assertEqual(len(t.submissions), 2)

    def test_paid_and_processing_are_two_separate_states(self):
        order = self.make_order()
        self.approve(self.submit(order))
        order = Order.objects.get(pk=order.pk)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        t = _tracker(order)
        self.assertEqual(t.payment.state_key, "approved")
        self.assertIsNone(t.rejection)
        self.assertFalse(t.can_resubmit)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        f = _states(t.fulfillment)
        self.assertEqual(f["processing"], "current")
        self.assertEqual(f["shipped"], "todo")
        self.assertEqual(t.summary, "پرداخت شما تأیید شده و فروشگاه در حال آماده‌سازی سفارش است.")

    def test_rejection_not_shown_after_a_later_approval(self):
        order = self.make_order()
        svc.reject(self.submit(order).pk, store=self.store, actor=self.user, reason="شماره پیگیری نادرست")
        self.approve(self.submit(order, last4="5678", tracking="TRK88888"))
        self.assertIsNone(_tracker(order).rejection)

    def test_shipped_and_delivered_progress(self):
        order = self.make_order()
        self.approve(self.submit(order))
        order = Order.objects.get(pk=order.pk)
        change_order_status(order, Order.Status.SHIPPED, store=self.store)
        f = _states(_tracker(order).fulfillment)
        self.assertEqual((f["processing"], f["shipped"], f["delivered"]), ("done", "current", "todo"))
        change_order_status(Order.objects.get(pk=order.pk), Order.Status.DELIVERED, store=self.store)
        f = _states(_tracker(order).fulfillment)
        self.assertEqual((f["shipped"], f["delivered"]), ("done", "done"))

    def test_pickup_has_no_shipping_step(self):
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(is_pickup=True)
        steps = [s.key for s in _tracker(order).fulfillment.steps]
        self.assertNotIn("shipped", steps)
        self.assertIn("delivered", steps)
        self.assertIn("حضوری", [s.label for s in _tracker(order).fulfillment.steps][-1])

    def test_canceled_is_a_separate_failed_branch(self):
        order = self.make_order()
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELED)
        t = _tracker(order)
        self.assertEqual(t.fulfillment.state_key, "canceled")
        self.assertEqual(_states(t.fulfillment), {"placed": "done", "canceled": "failed"})
        self.assertFalse(t.can_resubmit)

    def test_legacy_order_without_history_does_not_crash(self):
        order = self.make_order()
        OrderStatusHistory.objects.filter(order=order).delete()
        Order.objects.filter(pk=order.pk).update(status=Order.Status.SHIPPED, payment_status=Order.PaymentStatus.PAID)
        t = _tracker(order)
        self.assertEqual(_states(t.fulfillment)["shipped"], "current")

    def test_no_invented_steps(self):
        labels = " ".join(s.label for s in _tracker(self.make_order()).fulfillment.steps)
        self.assertNotIn("بسته‌بندی", labels)

    # --- rendering
    def _client(self, user=None):
        client = Client(HTTP_HOST=SHOP_HOST)
        client.force_login(user or self.user)
        return client

    def _get(self, order, user=None):
        client = Client()
        client.force_login(user or self.user)
        return client.get(reverse("customers:account-order-detail", args=[order.code]))

    def test_page_renders_tracker_with_escaped_rejection_reason_and_button(self):
        order = self.make_order()
        svc.reject(self.submit(order).pk, store=self.store, actor=self.user, reason="<script>alert(1)</script> کارت دیگر")
        page = self._get(order)
        self.assertContains(page, 'data-testid="order-tracker"')
        self.assertContains(page, 'data-payment-state="rejected"')
        self.assertContains(page, "اصلاح و ثبت مجدد اطلاعات پرداخت")
        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_page_after_approval_has_no_reject_box_and_shows_both_tracks(self):
        order = self.make_order()
        svc.reject(self.submit(order).pk, store=self.store, actor=self.user, reason="دلیل قبلی")
        self.approve(self.submit(order, last4="5678", tracking="TRK77777"))
        page = self._get(order)
        self.assertNotContains(page, 'data-testid="tracker-rejection"')
        self.assertNotContains(page, "اصلاح و ثبت مجدد اطلاعات پرداخت")
        self.assertContains(page, 'data-payment-state="approved"')
        self.assertContains(page, 'data-fulfillment-state="processing"')

    def test_customer_sees_only_own_orders(self):
        from django.contrib.auth import get_user_model
        from apps.customers.models import Customer
        other = get_user_model().objects.create_user(username="other-c", password="pass12345")
        Customer.objects.create(user=other, full_name="دیگری", phone="09121110002")
        order = self.make_order()
        self.assertEqual(self._get(order, other).status_code, 404)
