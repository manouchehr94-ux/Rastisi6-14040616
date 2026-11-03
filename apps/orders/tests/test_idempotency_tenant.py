"""FEAT-005 (BLOCKER 4) — idempotency key + tenant/operation ownership tests.

These prove three properties of ``gateway_payment_service.initiate_payment``:

1. Tenant + operation isolation. The dedupe lookup is scoped by the FULL
   operation identity (store, order, gateway_config, amount) in addition to the
   idempotency key. A reused key that was created for a DIFFERENT
   store/order/gateway/amount must NOT surface the foreign attempt — the caller
   gets a fresh attempt for its OWN operation and the foreign attempt is left
   untouched.

2. Single external charge on legitimate retry. Re-initiating the SAME operation
   (same store/order/gateway/amount, same deterministic key) returns the SAME
   attempt and makes exactly ONE external ``create_payment`` call.

3. Concurrent same-operation initiation. Two initiations for the same operation
   create exactly one attempt and one external create call. The serialization
   is provided by a ``select_for_update`` on the order row plus a re-check
   inside the lock. True OS-thread parallelism requires a database with
   row-level locking (PostgreSQL); the sandbox has no Postgres binaries, so the
   OS-thread-parallelism sub-assertion is reported UNVERIFIED and the guarantee
   is instead demonstrated deterministically through the lock/re-check path.

External gateway calls are never made for real — ``get_adapter`` is patched to
return a mock online adapter whose ``create_payment`` call count is asserted, so
"exactly one external charge" is proven directly.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.encryption import reset_fernet
from apps.orders.gateways.base import PaymentCreationResult
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGateway,
    PaymentGatewayConfig,
    ShippingMethod,
)
from apps.orders.services.gateway_payment_service import initiate_payment
from apps.stores.models import Store

User = get_user_model()

SERVICE = "apps.orders.services.gateway_payment_service.get_adapter"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


_TRACK_COUNTER = {"n": 0}


def mock_online_adapter():
    """A mock online adapter whose create_payment we can count.

    Each call returns a UNIQUE track_id so distinct operations never collide on
    the unique(gateway_track_id) constraint (a real gateway also mints a unique
    track id per create).
    """
    adapter = MagicMock()
    adapter.is_online = True
    adapter.auto_collects_offline = False

    def _create(*args, **kwargs):
        _TRACK_COUNTER["n"] += 1
        tid = f"trk-mock-{_TRACK_COUNTER['n']}"
        return PaymentCreationResult(
            track_id=tid, gateway_url=f"https://gateway.example/pay/{tid}", extra=None
        )

    adapter.create_payment.side_effect = _create
    return adapter


class IdempotencyTenantBase(TestCase):
    """Two independent stores, each with its own order and online gateway."""

    def setUp(self):
        reset_fernet()
        self.store_a = _akhlaghi()
        self.store_b = Store.objects.create(
            name="Store B", slug="idem-store-b", status=Store.Status.ACTIVE
        )

        self.user = User.objects.create_user(username="idem_user", password="test12345")
        self.customer_a = Customer.objects.create(
            user=self.user, full_name="مشتری الف", phone="09120000011"
        )
        user_b = User.objects.create_user(username="idem_user_b", password="test12345")
        self.customer_b = Customer.objects.create(
            user=user_b, full_name="مشتری ب", phone="09120000022"
        )

        self.vendor_a = Vendor.objects.create(store=self.store_a, name="فروشنده الف", slug="idem-v-a")
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="فروشنده ب", slug="idem-v-b")
        self.shipping_a = ShippingMethod.objects.create(
            store=self.store_a, name="پست", slug="idem-post-a", cost=Decimal("0")
        )
        self.shipping_b = ShippingMethod.objects.create(
            store=self.store_b, name="پست", slug="idem-post-b", cost=Decimal("0")
        )
        self.gateway_a = PaymentGateway.objects.create(store=self.store_a, name="درگاه", slug="idem-gw-a")
        self.gateway_b = PaymentGateway.objects.create(store=self.store_b, name="درگاه", slug="idem-gw-b")

        self.order_a = Order.objects.create(
            code="DM-IDEM-A", store=self.store_a, customer=self.customer_a,
            vendor=self.vendor_a, address={}, shipping_method=self.shipping_a,
            payment_gateway=self.gateway_a,
            items_total=Decimal("200000"), grand_total=Decimal("250000"),
        )
        self.order_b = Order.objects.create(
            code="DM-IDEM-B", store=self.store_b, customer=self.customer_b,
            vendor=self.vendor_b, address={}, shipping_method=self.shipping_b,
            payment_gateway=self.gateway_b,
            items_total=Decimal("100000"), grand_total=Decimal("130000"),
        )

        self.config_a = PaymentGatewayConfig.objects.create(
            store=self.store_a, gateway_code="zibal", is_active=True
        )
        self.config_a.set_credentials({"merchant": "merch-a"})
        self.config_a.save()
        self.config_b = PaymentGatewayConfig.objects.create(
            store=self.store_b, gateway_code="zibal", is_active=True
        )
        self.config_b.set_credentials({"merchant": "merch-b"})
        self.config_b.save()

    def tearDown(self):
        reset_fernet()


class ReusedKeyAcrossTenantsTests(IdempotencyTenantBase):
    """A reused idempotency key must never surface a foreign attempt."""

    def test_same_key_for_different_store_order_does_not_return_foreign_attempt(self):
        shared_key = "pay-SHARED-KEY-REUSED"

        with patch(SERVICE, return_value=mock_online_adapter()) as get_a:
            attempt_a = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=shared_key,
            )
        # Store B reuses the SAME key but for its OWN order/gateway/amount.
        with patch(SERVICE, return_value=mock_online_adapter()) as get_b:
            attempt_b = initiate_payment(
                order=self.order_b, gateway_config=self.config_b,
                callback_url="https://b.example/cb", store=self.store_b,
                idempotency_key=shared_key,
            )

        # Each attempt belongs to its own tenant + operation — no leakage.
        self.assertNotEqual(attempt_a.pk, attempt_b.pk)
        self.assertEqual(attempt_a.store_id, self.store_a.pk)
        self.assertEqual(attempt_a.order_id, self.order_a.pk)
        self.assertEqual(attempt_b.store_id, self.store_b.pk)
        self.assertEqual(attempt_b.order_id, self.order_b.pk)
        self.assertEqual(attempt_b.amount, Decimal("130000"))

        # The foreign (store A) attempt was never touched by store B's request.
        attempt_a.refresh_from_db()
        self.assertEqual(attempt_a.store_id, self.store_a.pk)
        self.assertEqual(attempt_a.amount, Decimal("250000"))

        # Each operation triggered exactly one external create_payment call.
        self.assertEqual(get_a.return_value.create_payment.call_count, 1)
        self.assertEqual(get_b.return_value.create_payment.call_count, 1)

    def test_same_key_different_amount_same_store_order_is_not_reused(self):
        """A reused key whose amount no longer matches the operation identity
        must not be treated as the same operation (scoped by amount)."""
        key = "pay-AMOUNT-SCOPED"
        with patch(SERVICE, return_value=mock_online_adapter()):
            first = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )
        # The order amount changes (e.g. cart edited) — same key reused.
        self.order_a.grand_total = Decimal("999000")
        self.order_a.save(update_fields=["grand_total"])
        with patch(SERVICE, return_value=mock_online_adapter()) as get2:
            second = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.amount, Decimal("999000"))
        # The newer operation still made its own single external call.
        self.assertEqual(get2.return_value.create_payment.call_count, 1)


class LegitimateRetrySingleChargeTests(IdempotencyTenantBase):
    """Retrying the SAME operation reuses the attempt and charges once."""

    def test_same_operation_retry_returns_same_attempt_and_single_create(self):
        adapter = mock_online_adapter()
        key = "pay-RETRY-SAME-OP"
        with patch(SERVICE, return_value=adapter):
            first = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )
            second = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            PaymentAttempt.objects.filter(order=self.order_a).count(), 1
        )
        # The crux: exactly ONE external charge for the whole operation.
        self.assertEqual(adapter.create_payment.call_count, 1)

    def test_live_attempt_in_redirect_ready_is_reused_without_recharge(self):
        adapter = mock_online_adapter()
        key = "pay-REDIRECT-READY-REUSE"
        with patch(SERVICE, return_value=adapter):
            first = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )
            self.assertEqual(first.status, PaymentAttempt.Status.REDIRECT_READY)
            # A second request for the same op finds the live attempt and
            # returns it without re-engaging the gateway.
            again = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(adapter.create_payment.call_count, 1)


class ConcurrentInitiationTests(IdempotencyTenantBase):
    """Concurrent same-operation initiation must yield one attempt, one charge.

    NOTE ON PARALLELISM: true OS-thread parallelism with contended row locks
    requires PostgreSQL. The sandbox has NO Postgres binaries, so the
    OS-thread-contention sub-assertion is UNVERIFIED here. SQLite does not prove
    PostgreSQL row-level locking. What we CAN prove deterministically on SQLite
    is that the select_for_update + in-lock re-check path returns the existing
    attempt (and does not re-charge) once a live attempt already exists — which
    is exactly the branch a blocked concurrent loser takes after the winner
    commits.
    """

    def test_second_initiation_after_winner_committed_reuses_single_attempt(self):
        """Simulate the loser's path: after the winner has committed its live
        attempt, a second same-operation initiation must reuse it (the in-lock
        re-check branch) and must not call the gateway again."""
        adapter = mock_online_adapter()
        key = "pay-CONCURRENT-SIM"
        with patch(SERVICE, return_value=adapter):
            # Winner: creates the attempt and makes the single external call.
            winner = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )
            # Loser (unblocked after winner's commit): same operation identity.
            loser = initiate_payment(
                order=self.order_a, gateway_config=self.config_a,
                callback_url="https://a.example/cb", store=self.store_a,
                idempotency_key=key,
            )

        self.assertEqual(winner.pk, loser.pk)
        self.assertEqual(
            PaymentAttempt.objects.filter(
                store=self.store_a, order=self.order_a,
                gateway_config=self.config_a, amount=self.order_a.grand_total,
            ).count(),
            1,
        )
        self.assertEqual(adapter.create_payment.call_count, 1)

    def test_unique_idempotency_constraint_blocks_duplicate_committed_row(self):
        """Backstop proof that even across separate DB sessions a duplicate
        attempt for the same deterministic key cannot be committed: the
        existing partial unique(idempotency_key) constraint rejects it. This is
        the DB-level guarantee that the select_for_update path relies on."""
        from django.db import IntegrityError, transaction

        key = "pay-UNIQUE-BACKSTOP"
        PaymentAttempt.objects.create(
            store=self.store_a, order=self.order_a, gateway_config=self.config_a,
            amount=self.order_a.grand_total, currency="TOMAN",
            status=PaymentAttempt.Status.REDIRECT_READY, idempotency_key=key,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PaymentAttempt.objects.create(
                    store=self.store_a, order=self.order_a, gateway_config=self.config_a,
                    amount=self.order_a.grand_total, currency="TOMAN",
                    status=PaymentAttempt.Status.CREATED, idempotency_key=key,
                )
