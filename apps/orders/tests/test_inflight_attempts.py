"""Round 3, issue 3: an in-flight (CREATED/REQUESTING, no URL) attempt must never
be returned as redirect-ready, and must never trigger a second create_payment."""

import threading
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.orders.gateways.base import GatewayConnectionError, PaymentCreationResult
from apps.orders.models import PaymentAttempt, PaymentGatewayConfig
from apps.orders.services import gateway_payment_service as svc
from apps.orders.services.gateway_payment_service import (
    PaymentInitiationError,
    PaymentInitiationInProgress,
    initiate_payment,
)
from apps.orders.tests.test_idempotency_tenant import SERVICE, IdempotencyTenantBase, mock_online_adapter
from apps.orders.tests.test_lifecycle import LifecycleBase
from apps.core.tests.serialized_rollback import SerializedRollbackSafeMixin

S = PaymentAttempt.Status


class _NoWait:
    def __enter__(self):
        self.p = patch.object(svc, "INFLIGHT_POLL_INTERVAL", 0)
        self.p.start()

    def __exit__(self, *a):
        self.p.stop()


class InFlightServiceTests(IdempotencyTenantBase):
    def _seed(self, status, **kw):
        return PaymentAttempt.objects.create(
            store=self.store_a, order=self.order_a, gateway_config=self.config_a,
            amount=self.order_a.grand_total, currency="TOMAN", status=status, **kw,
        )

    def _init(self, key="pay-IF"):
        return initiate_payment(
            order=self.order_a, gateway_config=self.config_a,
            callback_url="https://a.example/cb", store=self.store_a, idempotency_key=key,
        )

    def test_created_and_requesting_without_url_are_not_returned(self):
        for st in (S.CREATED, S.REQUESTING):
            PaymentAttempt.objects.filter(order=self.order_a).delete()
            self._seed(st)
            adapter = mock_online_adapter()
            with patch(SERVICE, return_value=adapter), _NoWait():
                with self.assertRaises(PaymentInitiationInProgress):
                    self._init()
            self.assertEqual(adapter.create_payment.call_count, 0, st)
            self.assertEqual(PaymentAttempt.objects.filter(order=self.order_a).count(), 1, st)

    def test_poll_is_bounded(self):
        self._seed(S.REQUESTING)
        with patch(SERVICE, return_value=mock_online_adapter()), \
                patch.object(svc.time, "sleep") as sleep:
            with self.assertRaises(PaymentInitiationInProgress):
                self._init()
        self.assertEqual(sleep.call_count, svc.INFLIGHT_POLL_TRIES)

    def test_attempt_becoming_ready_during_poll_is_returned(self):
        a = self._seed(S.REQUESTING)

        def finish(_):
            PaymentAttempt.objects.filter(pk=a.pk).update(
                status=S.REDIRECT_READY, gateway_track_id="trk-x", gateway_redirect_url="https://gw.example/x",
            )

        adapter = mock_online_adapter()
        with patch(SERVICE, return_value=adapter), patch.object(svc.time, "sleep", side_effect=finish):
            got = self._init()
        self.assertEqual(got.pk, a.pk)
        self.assertEqual(got.status, S.REDIRECT_READY)
        self.assertEqual(adapter.create_payment.call_count, 0)

    def test_stale_inflight_is_expired_and_replaced_without_recalling_old(self):
        a = self._seed(S.REQUESTING)
        PaymentAttempt.objects.filter(pk=a.pk).update(updated_at=timezone.now() - timedelta(hours=1))
        adapter = mock_online_adapter()
        with patch(SERVICE, return_value=adapter), _NoWait():
            new = self._init()
        a.refresh_from_db()
        self.assertEqual(a.status, S.EXPIRED)
        self.assertEqual(a.failure_code, "initiation_stale")
        self.assertNotEqual(new.pk, a.pk)
        self.assertEqual(new.status, S.REDIRECT_READY)
        self.assertEqual(adapter.create_payment.call_count, 1)

    def test_fresh_inflight_is_not_expired(self):
        a = self._seed(S.REQUESTING)
        with patch(SERVICE, return_value=mock_online_adapter()), _NoWait():
            with self.assertRaises(PaymentInitiationInProgress):
                self._init()
        a.refresh_from_db()
        self.assertEqual(a.status, S.REQUESTING)

    def test_reentrant_request_during_create_payment_gets_pending_and_single_call(self):
        """Deterministic stand-in for a concurrent request: while the first
        initiation is inside create_payment (attempt REQUESTING, committed, no
        row lock held), a second same-operation initiation runs."""
        adapter = mock_online_adapter()
        real = adapter.create_payment.side_effect
        seen = {}

        def create(*a, **kw):
            try:
                self._init()
            except PaymentInitiationInProgress as exc:
                seen["exc"] = exc
            return real(*a, **kw)

        adapter.create_payment.side_effect = create
        with patch(SERVICE, return_value=adapter), _NoWait():
            first = self._init()
        self.assertIn("exc", seen)
        self.assertEqual(adapter.create_payment.call_count, 1)
        self.assertEqual(first.status, S.REDIRECT_READY)
        self.assertEqual(PaymentAttempt.objects.filter(order=self.order_a).count(), 1)

    def test_failure_inside_create_payment_is_terminal(self):
        for exc in (GatewayConnectionError("down"), RuntimeError("boom")):
            PaymentAttempt.objects.filter(order=self.order_a).delete()
            adapter = mock_online_adapter()
            adapter.create_payment.side_effect = exc
            with patch(SERVICE, return_value=adapter), _NoWait():
                with self.assertRaises(PaymentInitiationError):
                    self._init()
            a = PaymentAttempt.objects.get(order=self.order_a)
            self.assertEqual(a.status, S.FAILED, repr(exc))

    def test_empty_gateway_response_fails_attempt(self):
        adapter = mock_online_adapter()
        adapter.create_payment.side_effect = lambda *a, **k: PaymentCreationResult(track_id="", gateway_url="", extra=None)
        with patch(SERVICE, return_value=adapter), _NoWait():
            with self.assertRaises(PaymentInitiationError):
                self._init()
        self.assertEqual(PaymentAttempt.objects.get(order=self.order_a).status, S.FAILED)


class InFlightViewTests(LifecycleBase):
    def _config(self):
        c = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="zibal", is_active=True)
        c.set_credentials({"merchant": "zbl"})
        c.save()
        self.assertTrue(c.is_selectable_at_checkout)
        return c

    def _post(self, order):
        client = Client()
        client.force_login(self.customer.user)
        return client.post(reverse("orders:payment-initiate", args=[order.code]))

    def test_inflight_attempt_never_redirects_to_empty_url(self):
        config = self._config()
        for st in (S.CREATED, S.REQUESTING):
            order = self.new_order()
            PaymentAttempt.objects.create(
                store=self.store, order=order, gateway_config=config,
                amount=order.grand_total, currency="TOMAN", status=st,
            )
            with patch("apps.orders.gateways.zibal.ZibalAdapter.create_payment") as create, _NoWait():
                resp = self._post(order)
            self.assertEqual(resp.status_code, 409, st)
            self.assertFalse(resp.has_header("Location"), st)
            self.assertEqual(resp["Retry-After"], "2")
            create.assert_not_called()

    def test_view_guard_blocks_ready_attempt_without_url_or_track(self):
        config = self._config()
        order = self.new_order()
        PaymentAttempt.objects.create(
            store=self.store, order=order, gateway_config=config, amount=order.grand_total,
            currency="TOMAN", status=S.REDIRECT_READY,
        )
        with _NoWait():
            resp = self._post(order)
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(resp.has_header("Location"))

    def test_concurrent_view_request_during_create_gets_409_and_single_create(self):
        config = self._config()
        order = self.new_order()
        seen = {}

        def create(self_adapter, **kw):
            seen["second"] = self._post(order)
            return PaymentCreationResult(track_id="TRK-OK-1", gateway_url="", extra=None)

        with patch("apps.orders.gateways.zibal.ZibalAdapter.create_payment", autospec=True, side_effect=create) as m, _NoWait():
            first = self._post(order)
        self.assertEqual(m.call_count, 1)
        self.assertEqual(seen["second"].status_code, 409)
        self.assertFalse(seen["second"].has_header("Location"))
        self.assertEqual(first.status_code, 302)
        self.assertTrue(first["Location"].endswith("TRK-OK-1"))


@skipUnless(connection.vendor == "postgresql", "نیازمندِ PostgreSQL")
class InFlightThreadRaceTests(SerializedRollbackSafeMixin, TransactionTestCase):
    """Real OS threads; only meaningful with PostgreSQL row locks.

    TransactionTestCase (no wrapping transaction) so worker threads, which use
    their own connections, can see the committed fixtures.
    """

    serialized_rollback = True

    def setUp(self):
        IdempotencyTenantBase.setUp(self)

    def tearDown(self):
        IdempotencyTenantBase.tearDown(self)

    def test_n_concurrent_same_operation_initiations_call_create_once(self):
        import time as _t

        n = 6
        adapter = mock_online_adapter()
        real = adapter.create_payment.side_effect

        def slow(*a, **kw):
            _t.sleep(0.4)
            return real(*a, **kw)

        adapter.create_payment.side_effect = slow
        barrier = threading.Barrier(n)
        out = []

        def worker():
            try:
                barrier.wait(timeout=10)
                try:
                    r = initiate_payment(
                        order=self.order_a, gateway_config=self.config_a,
                        callback_url="https://a.example/cb", store=self.store_a, idempotency_key="pay-THREADS",
                    )
                    out.append(("ok", r.pk, r.status, bool(r.gateway_redirect_url or r.gateway_track_id)))
                except PaymentInitiationInProgress:
                    out.append(("pending", None, None, None))
            finally:
                close_old_connections()

        with patch(SERVICE, return_value=adapter):
            threads = [threading.Thread(target=worker) for _ in range(n)]
            [t.start() for t in threads]
            [t.join(timeout=60) for t in threads]
        self.assertEqual(len(out), n)
        self.assertEqual(adapter.create_payment.call_count, 1)
        self.assertEqual(PaymentAttempt.objects.filter(order=self.order_a).count(), 1)
        for kind, _pk, status, has_ref in out:
            if kind == "ok":
                self.assertEqual(status, S.REDIRECT_READY)
                self.assertTrue(has_ref)
