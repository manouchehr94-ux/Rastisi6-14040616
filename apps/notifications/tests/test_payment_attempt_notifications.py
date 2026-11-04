"""payment.failed from the REAL payment lifecycle: ``process_callback_and_verify`` with only the outbound HTTP call to the gateway mocked.

Only a gateway-confirmed failure of an OPEN attempt notifies (after commit, once per attempt). Timeouts, invalid/ambiguous answers, amount mismatches, a callback that
claims success, canceled attempts, repeated callbacks and rolled-back transitions notify nothing. An attempt failure is never presented as the order's final failure."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.db import transaction

from apps.notifications.models import InboxItem, NotificationEvent
from apps.orders.models import Order, PaymentAttempt
from apps.orders.services.gateway_payment_service import PaymentVerificationFailed, process_callback_and_verify
from apps.orders.tests.test_gateway_payment_service import GatewayPaymentServiceTestBase
from apps.dashboard.tests.test_permission_enforcement import _user_with_role
from apps.stores.models import Store, StoreMembership

ZIBAL = "apps.orders.gateways.zibal.requests.post"
FAIL_CB = {"success": "0", "status": "3"}


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    return r


class _Base(GatewayPaymentServiceTestBase):
    def setUp(self):
        super().setUp()
        self.owner = _user_with_role(self.store, "pa-owner", StoreMembership.Role.OWNER)
        self.order_mgr = _user_with_role(self.store, "pa-om", StoreMembership.Role.ORDER_MANAGER)
        self.content = _user_with_role(self.store, "pa-content", StoreMembership.Role.CONTENT_EDITOR)
        self.other = Store.objects.create(name="Other PA", slug="pa-other", status=Store.Status.ACTIVE)
        self.other_owner = _user_with_role(self.other, "pa-other-owner", StoreMembership.Role.OWNER)
        self.n = 0

    def attempt(self, order=None, status=PaymentAttempt.Status.REDIRECT_READY):
        self.n += 1
        order = order or self.order
        return PaymentAttempt.objects.create(store=self.store, order=order, gateway_config=self.zibal_config, amount=order.grand_total, currency="TOMAN",
                                             status=status, gateway_track_id=f"trk-{order.pk}-{self.n}")

    def callback(self, attempt, payload=None, *, exc=None, data=None):
        with patch(ZIBAL) as post:
            if exc is not None:
                post.side_effect = exc
            else:
                post.return_value = _resp(payload)
            try:
                return process_callback_and_verify(attempt_public_id=attempt.public_id, callback_data=data if data is not None else dict(FAIL_CB), store=self.store)
            except PaymentVerificationFailed:
                return None

    def run_cb(self, *args, **kw):
        with self.captureOnCommitCallbacks(execute=True):
            return self.callback(*args, **kw)

    def events(self):
        return NotificationEvent.objects.filter(type_key="payment.failed")

    def items(self, user):
        return InboxItem.objects.filter(event__type_key="payment.failed", user=user).count()


class ConfirmedFailureTests(_Base):
    def test_a_gateway_confirmed_failed_attempt_notifies_once_with_attempt_scoped_dedupe_and_honest_copy(self):
        a = self.attempt()
        self.run_cb(a, {"result": 202, "status": 3, "message": "پرداخت انجام نشد"})
        a.refresh_from_db()
        self.assertEqual(a.status, PaymentAttempt.Status.FAILED)
        ev = self.events().get()
        self.assertEqual(ev.dedupe_key, f"payattempt:{a.public_id}")
        self.assertEqual(ev.link_kwargs, {"code": self.order.code})
        self.assertIn("سفارش هنوز باز است", ev.summary)                        # an attempt failed — not the order's final failure
        self.assertNotIn("نهایی", ev.title + ev.summary)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)             # the existing lifecycle did not change the order
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PENDING)

    def test_recipients_follow_permissions_and_never_cross_stores(self):
        self.run_cb(self.attempt(), {"result": 202, "status": 3})
        self.assertEqual(self.items(self.owner), 1)
        self.assertEqual(self.items(self.order_mgr), 1)                       # ORDER_VIEW
        self.assertEqual(self.items(self.content), 0)
        self.assertEqual(self.items(self.other_owner), 0)                     # another store's owner never sees it

    def test_a_duplicate_or_late_callback_for_the_same_attempt_creates_no_second_event(self):
        a = self.attempt()
        self.run_cb(a, {"result": 202, "status": 3})
        self.run_cb(a, {"result": 202, "status": 3})                          # attempt is final now → untouched
        self.run_cb(a, {"result": 202, "status": 3})
        self.assertEqual(self.events().count(), 1)
        self.assertEqual(self.events().get().occurrence_count, 1)

    def test_a_retry_after_failure_is_a_new_attempt_grouped_into_the_same_inbox_row(self):
        first, second = self.attempt(), self.attempt()
        self.run_cb(first, {"result": 202, "status": 3})
        self.run_cb(second, {"result": 202, "status": 3})
        ev = self.events().get()
        self.assertEqual(ev.occurrence_count, 2)                              # two attempts, one row with a counter
        self.assertEqual(self.items(self.owner), 1)

    def test_a_later_successful_attempt_still_pays_the_order_and_adds_no_failure_event(self):
        failed, good = self.attempt(), self.attempt()
        self.run_cb(failed, {"result": 202, "status": 3})
        before = self.events().count()
        with patch(ZIBAL) as post, self.captureOnCommitCallbacks(execute=True):
            post.return_value = _resp({"result": 100, "amount": int(self.order.grand_total) * 10, "status": 1, "refNumber": "REF-LATER", "cardNumber": ""})
            process_callback_and_verify(attempt_public_id=good.public_id, callback_data={"success": "1", "status": "1"}, store=self.store)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.events().count(), before)


class NonDefinitiveOutcomesTests(_Base):
    def assertSilent(self):
        self.assertFalse(self.events().exists())

    def test_timeout_connection_error_and_invalid_answers_are_not_definitive(self):
        for exc, payload in ((requests.Timeout("t"), None), (requests.ConnectionError("c"), None)):
            a = self.attempt()
            self.run_cb(a, payload, exc=exc)
        bad = self.attempt()
        with patch(ZIBAL) as post, self.captureOnCommitCallbacks(execute=True):
            r = MagicMock()
            r.json.side_effect = ValueError("not json")
            r.status_code = 200
            post.return_value = r
            try:
                process_callback_and_verify(attempt_public_id=bad.public_id, callback_data=dict(FAIL_CB), store=self.store)
            except PaymentVerificationFailed:
                pass
        missing = self.attempt()
        self.run_cb(missing, {"unexpected": 1})                                # no "result" key
        self.assertSilent()

    def test_a_callback_that_claims_success_but_fails_verification_is_ambiguous(self):
        a = self.attempt()
        self.run_cb(a, {"result": 202, "status": 3}, data={"success": "1", "status": "2", "trackId": a.gateway_track_id})
        self.assertSilent()

    def test_an_amount_mismatch_is_a_reconciliation_case_not_a_failure_notice(self):
        a = self.attempt()
        self.run_cb(a, {"result": 100, "amount": 1, "status": 1, "refNumber": "R", "cardNumber": ""}, data={"success": "1", "status": "1"})
        self.assertSilent()

    def test_a_canceled_attempt_does_not_notify(self):
        paid = self.attempt()
        Order.objects.filter(pk=self.order.pk).update(payment_status=Order.PaymentStatus.PAID)      # the order got paid by another path meanwhile
        self.run_cb(paid, {"result": 202, "status": 3})
        paid.refresh_from_db()
        self.assertEqual(paid.status, PaymentAttempt.Status.CANCELED)
        self.assertSilent()

    def test_an_already_final_attempt_is_not_rewritten_or_announced(self):
        done = self.attempt(status=PaymentAttempt.Status.FAILED)
        self.run_cb(done, {"result": 202, "status": 3})
        self.assertSilent()

    def test_missing_track_id_and_config_errors_are_internal_not_customer_payment_failures(self):
        a = self.attempt()
        PaymentAttempt.objects.filter(pk=a.pk).update(gateway_track_id="")
        self.run_cb(a, {"result": 202})
        self.assertSilent()

    def test_nothing_is_published_before_the_transition_commits_and_a_rollback_publishes_nothing(self):
        a = self.attempt()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.callback(a, {"result": 202, "status": 3})
        self.assertTrue(callbacks)                                              # queued for commit …
        self.assertFalse(self.events().exists())                                # … but not published yet
        b = self.attempt()
        try:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    self.callback(b, {"result": 202, "status": 3})
                    raise RuntimeError("outer business transaction fails")
        except RuntimeError:
            pass
        self.assertFalse(self.events().exists())                                # rolled back ⇒ no phantom notification
        b.refresh_from_db()
        self.assertNotEqual(b.status, PaymentAttempt.Status.FAILED)


class SimulationPathTests(_Base):
    def test_the_simulation_only_path_is_still_supported_and_uses_the_new_honest_copy(self):
        from apps.notifications.services import business_events

        business_events.payment_result(self.order, success=False)
        ev = self.events().get()
        self.assertIn("تلاش پرداخت ناموفق", ev.title)


class CallbackViewReachabilityTests(_Base):
    """RUNTIME evidence: the PUBLIC callback URL (the real production entry point) reaches the notification — not just an AST reference."""

    def test_the_public_gateway_callback_view_notifies_once_even_when_the_callback_is_repeated(self):
        from django.test import Client, override_settings
        from django.urls import reverse
        from django.utils import timezone

        from apps.stores.models import StoreDomain

        host = "pay-cb.brand-example.ir"
        StoreDomain.objects.create(store=self.store, hostname=host, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                                   verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        a = self.attempt()
        url = reverse("orders:gateway-callback", args=[a.public_id]) + "?success=0&status=3"
        client = Client(HTTP_HOST=host)
        client.force_login(self.customer.user)
        with override_settings(ALLOWED_HOSTS=[host, "testserver"]):
            for _ in range(3):
                with patch(ZIBAL, return_value=_resp({"result": 202, "status": 3, "message": "x"})):
                    with self.captureOnCommitCallbacks(execute=True):
                        response = client.get(url)
                self.assertIn(response.status_code, (200, 302))
        self.assertEqual(self.events().count(), 1)
        a.refresh_from_db()
        self.assertEqual(a.status, PaymentAttempt.Status.FAILED)

    def test_a_later_successful_attempt_of_the_same_order_is_not_blocked_by_an_earlier_failure(self):
        first = self.attempt()
        self.run_cb(first, {"result": 202, "status": 3})
        second = self.attempt()
        self.run_cb(second, {"result": 100, "status": 1, "amount": int(self.order.grand_total) * 10, "refNumber": "REF-OK"}, data={"success": "1", "status": "2"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.events().count(), 1)                              # only the genuinely failed attempt
