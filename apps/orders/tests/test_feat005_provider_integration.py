"""FEAT-005 — integration of all operational providers into checkout + lifecycle.

These tests assert the behavior added by FEAT-005 on top of the existing
orchestrator and checkout service:

- A ready online provider (zarinpal) appears at checkout; a documentation-blocked
  provider (mellat / snappay BNPL) does NOT, and cannot be routed for a real
  payment through the orchestrator.
- initiate_payment + process_callback_and_verify works end-to-end with a mocked
  adapter (PSP-style create/verify AND a BNPL-style create/verify+settle),
  routed through the EXISTING gateway_payment_service — no provider conditionals.
- Cross-tenant config is rejected (a config from Store A is never routable by
  Store B, and never influences Store B's checkout option list).
- Amount tampering in the callback never changes the finalized amount (the
  server-authoritative order grand_total from the DB is used, callback values
  are ignored).

All provider HTTP is mocked; no real provider endpoint is ever contacted.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.catalog.models import Vendor
from apps.customers.models import Customer
from apps.orders.encryption import reset_fernet
from apps.orders.gateways.base import (
    GatewayCategory,
    PaymentCreationResult,
    PaymentGatewayAdapter,
    PaymentOperation,
    PaymentSettleResult,
    PaymentVerificationResult,
)
from apps.orders.models import (
    Order,
    PaymentAttempt,
    PaymentGateway,
    PaymentGatewayConfig,
    ShippingMethod,
    Transaction,
)
from apps.orders.services import checkout_service
from apps.orders.services.gateway_payment_service import (
    PaymentConfigError,
    initiate_payment,
    process_callback_and_verify,
)
from apps.stores.models import Store

User = get_user_model()


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


# ---------------------------------------------------------------------------
# Mock adapters (never hit a real endpoint)
# ---------------------------------------------------------------------------


class _MockPspAdapter(PaymentGatewayAdapter):
    """A fully-ready PSP-style adapter standing in for a verified online gateway."""

    code = "zarinpal"
    display_name = "Mock PSP"

    @property
    def is_online(self):
        return True

    @property
    def required_credentials(self):
        return ["merchant_id"]

    @property
    def category(self):
        return GatewayCategory.PSP

    def validate_credentials(self, credentials):
        return [] if (credentials.get("merchant_id") or "").strip() else ["merchant_id required"]

    def create_payment(self, *, amount, currency, callback_url, credentials, order_code, description="", sandbox=False):
        return PaymentCreationResult(track_id="mock-track-1", gateway_url="https://mock/pay/mock-track-1")

    def build_redirect_url(self, track_id, *, sandbox=False):
        return f"https://mock/pay/{track_id}"

    def verify_payment(self, *, track_id, expected_amount, currency, credentials, callback_data, sandbox=False):
        # Server-authoritative: verify against expected_amount (the order's
        # grand_total), NOT any value carried in callback_data.
        return PaymentVerificationResult(success=True, ref_id="MOCK-REF-1", status_code=100, message="ok")


class _MockBnplAdapter(PaymentGatewayAdapter):
    """A BNPL-style adapter with a DISTINCT, capability-gated settle step.

    Stands in for an operational BNPL provider so the end-to-end settle path
    can be exercised. ``settle_payment`` records that it ran so the test can
    assert the order is only treated as paid after settle.
    """

    settle_calls = 0

    code = "snappay"
    display_name = "Mock BNPL"

    @property
    def is_online(self):
        return True

    @property
    def required_credentials(self):
        return ["client_id", "client_secret"]

    @property
    def category(self):
        return GatewayCategory.BNPL

    @property
    def capabilities(self):
        return frozenset({PaymentOperation.CREATE, PaymentOperation.VERIFY, PaymentOperation.SETTLE})

    def validate_credentials(self, credentials):
        errs = []
        if not (credentials.get("client_id") or "").strip():
            errs.append("client_id required")
        if not (credentials.get("client_secret") or "").strip():
            errs.append("client_secret required")
        return errs

    def create_payment(self, *, amount, currency, callback_url, credentials, order_code, description="", sandbox=False):
        return PaymentCreationResult(track_id="mock-bnpl-1", gateway_url="https://mock/bnpl/mock-bnpl-1")

    def build_redirect_url(self, track_id, *, sandbox=False):
        return f"https://mock/bnpl/{track_id}"

    def verify_payment(self, *, track_id, expected_amount, currency, credentials, callback_data, sandbox=False):
        return PaymentVerificationResult(success=True, ref_id="MOCK-BNPL-REF", status_code=100, message="ok")

    def settle_payment(self, *, track_id, amount, currency, credentials, sandbox=False):
        type(self).settle_calls += 1
        return PaymentSettleResult(success=True, settle_ref="MOCK-SETTLE", status_code=100, message="settled")


class _MockBnplSettleFailsAdapter(_MockBnplAdapter):
    """A BNPL adapter whose verify succeeds but whose SETTLE step FAILS.

    Proves the orchestrator's SETTLE gate: the order must NOT be marked paid
    when settle does not succeed, even though verify reported success.
    """

    settle_calls = 0

    def settle_payment(self, *, track_id, amount, currency, credentials, sandbox=False):
        type(self).settle_calls += 1
        return PaymentSettleResult(success=False, settle_ref="", status_code=0, message="settle declined")


class Feat005TestBase(TestCase):
    def setUp(self):
        reset_fernet()
        self.store = _akhlaghi()
        self.user = User.objects.create_user(username="feat005_user", password="test123")
        self.customer = Customer.objects.create(user=self.user, full_name="مشتری", phone="09120000000")
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده", slug="feat005-vendor")
        self.shipping = ShippingMethod.objects.create(
            store=self.store, name="پست", slug="feat005-post", cost=Decimal("30000"), is_active=True,
        )
        self.legacy_zarinpal = PaymentGateway.objects.create(
            store=self.store, name="زرین‌پال", slug="zarinpal", is_active=True,
        )
        self.legacy_mellat = PaymentGateway.objects.create(
            store=self.store, name="بانک ملت", slug="mellat", is_active=True,
        )
        self.order = Order.objects.create(
            code="DM-F005", store=self.store, customer=self.customer, vendor=self.vendor,
            address={}, shipping_method=self.shipping, payment_gateway=self.legacy_zarinpal,
            items_total=Decimal("200000"), grand_total=Decimal("250000"),
        )

    def tearDown(self):
        reset_fernet()

    def _request(self, store=None):
        factory = RequestFactory()
        request = factory.get("/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = AnonymousUser()
        request.store = store or self.store
        return request

    def _ready_zarinpal_config(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zarinpal", is_active=True, is_sandbox=False,
        )
        config.set_credentials({"merchant_id": "x" * 36})
        config.save()
        return config


# ---------------------------------------------------------------------------
# Checkout option list: ready shows, blocked hides
# ---------------------------------------------------------------------------


class CheckoutOptionReadinessTests(Feat005TestBase):
    def test_ready_online_provider_appears_at_checkout(self):
        self._ready_zarinpal_config()
        gateways = checkout_service.active_payment_gateways(store=self.store)
        slugs = {g.slug for g in gateways}
        self.assertIn("zarinpal", slugs)

    def test_documentation_blocked_provider_excluded_from_checkout(self):
        # A mellat config exists and is "active" but the adapter is
        # documentation-blocked -> readiness DOCUMENTATION_BLOCKED -> not
        # selectable -> excluded from the checkout option list.
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="mellat", is_active=True,
        )
        self._ready_zarinpal_config()
        gateways = checkout_service.active_payment_gateways(store=self.store)
        slugs = {g.slug for g in gateways}
        self.assertIn("zarinpal", slugs)
        self.assertNotIn("mellat", slugs)

    def test_legacy_gateway_without_config_still_shown(self):
        # Backward compatibility: a legacy gateway with no PaymentGatewayConfig
        # keeps its existing (legacy/simulation) behavior.
        other = PaymentGateway.objects.create(
            store=self.store, name="قدیمی", slug="legacy-only", is_active=True,
        )
        gateways = checkout_service.active_payment_gateways(store=self.store)
        self.assertIn(other.slug, {g.slug for g in gateways})

    def test_set_payment_gateway_rejects_blocked(self):
        PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="mellat", is_active=True,
        )
        request = self._request()
        checkout_service.set_payment_gateway(request, self.legacy_mellat.pk)
        selected = checkout_service.get_selected_payment_gateway(request)
        # mellat is blocked -> selection ignored -> falls back to first allowed
        self.assertNotEqual(getattr(selected, "slug", None), "mellat")

    def test_inactive_config_not_selectable(self):
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="zarinpal", is_active=False,
        )
        config.set_credentials({"merchant_id": "x" * 36})
        config.save()
        gateways = checkout_service.active_payment_gateways(store=self.store)
        self.assertNotIn("zarinpal", {g.slug for g in gateways})


# ---------------------------------------------------------------------------
# End-to-end orchestrator flow with mocked adapters (PSP + BNPL)
# ---------------------------------------------------------------------------


class OrchestratorEndToEndTests(Feat005TestBase):
    def test_psp_initiate_and_verify_end_to_end(self):
        config = self._ready_zarinpal_config()
        mock = _MockPspAdapter()
        with patch("apps.orders.services.gateway_payment_service.get_adapter", return_value=mock):
            attempt = initiate_payment(
                order=self.order, gateway_config=config,
                callback_url="https://shop/cb", store=self.store,
            )
            self.assertEqual(attempt.status, PaymentAttempt.Status.REDIRECT_READY)
            self.assertEqual(attempt.gateway_track_id, "mock-track-1")

            result = process_callback_and_verify(
                attempt_public_id=attempt.public_id,
                callback_data={"status": "1"},
                store=self.store,
            )
        result.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(self.order.grand_total, Decimal("250000"))
        self.assertTrue(Transaction.objects.filter(order=self.order, status="ok").exists())

    def test_bnpl_settle_invoked_before_paid(self):
        """BNPL settle (a DISTINCT capability-gated step) runs via the adapter
        before the order is treated as fully paid."""
        _MockBnplAdapter.settle_calls = 0
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=True, is_sandbox=False,
        )
        config.set_credentials({"client_id": "cid", "client_secret": "csecret"})
        config.save()
        mock = _MockBnplAdapter()
        # Patch BOTH dispatch points: the orchestrator's import AND the one the
        # model's readiness_status derivation uses, so the mocked (operational)
        # BNPL adapter — not the real documentation-blocked skeleton — drives
        # readiness and routing for this end-to-end settle test.
        with patch("apps.orders.services.gateway_payment_service.get_adapter", return_value=mock), \
             patch("apps.orders.gateways.get_adapter", return_value=mock):
            attempt = initiate_payment(
                order=self.order, gateway_config=config,
                callback_url="https://shop/cb", store=self.store,
            )
            result = process_callback_and_verify(
                attempt_public_id=attempt.public_id,
                callback_data={"status": "1"},
                store=self.store,
            )
        result.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(result.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        # The capability-gated settle step must have been invoked.
        self.assertEqual(_MockBnplAdapter.settle_calls, 1)

    def test_bnpl_not_marked_paid_when_settle_fails(self):
        """If the DISTINCT settle step does not succeed, the order is NOT marked paid even though verify succeeded — the SETTLE
        gate holds the line. A settle the provider cannot confirm is UNKNOWN (reconciliation), not a definitive failure."""
        _MockBnplSettleFailsAdapter.settle_calls = 0
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="snappay", is_active=True, is_sandbox=False,
        )
        config.set_credentials({"client_id": "cid", "client_secret": "csecret"})
        config.save()
        mock = _MockBnplSettleFailsAdapter()

        with patch("apps.orders.services.gateway_payment_service.get_adapter", return_value=mock), \
             patch("apps.orders.gateways.get_adapter", return_value=mock):
            attempt = initiate_payment(
                order=self.order, gateway_config=config,
                callback_url="https://shop/cb", store=self.store,
            )
            result = process_callback_and_verify(
                attempt_public_id=attempt.public_id,
                callback_data={"status": "1"},
                store=self.store,
            )
        attempt.refresh_from_db()
        self.order.refresh_from_db()
        # settle was attempted (gate engaged) but not proven ...
        self.assertEqual(_MockBnplSettleFailsAdapter.settle_calls, 1)
        self.assertEqual(result.pk, attempt.pk)
        # ... so the attempt is UNKNOWN (no inquiry could prove otherwise), the order is NOT paid, nothing was finalized.
        self.assertEqual(attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assertNotEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertFalse(Transaction.objects.filter(order=self.order, status="ok").exists())

    def test_amount_tampering_in_callback_does_not_change_finalized_amount(self):
        config = self._ready_zarinpal_config()
        mock = _MockPspAdapter()
        with patch("apps.orders.services.gateway_payment_service.get_adapter", return_value=mock):
            attempt = initiate_payment(
                order=self.order, gateway_config=config,
                callback_url="https://shop/cb", store=self.store,
            )
            # Customer-tampered callback claims a different (huge) amount.
            result = process_callback_and_verify(
                attempt_public_id=attempt.public_id,
                callback_data={"status": "1", "amount": "999999999", "grand_total": "1"},
                store=self.store,
            )
        result.refresh_from_db()
        self.order.refresh_from_db()
        # The finalized attempt amount == the server-authoritative order total.
        self.assertEqual(result.amount, Decimal("250000"))
        self.assertEqual(self.order.grand_total, Decimal("250000"))
        tx = Transaction.objects.get(order=self.order)
        self.assertEqual(tx.amount, Decimal("250000"))

    def test_documentation_blocked_provider_cannot_be_routed(self):
        """Even if a config is somehow active, the orchestrator refuses to route
        a documentation-blocked provider for a real payment."""
        config = PaymentGatewayConfig.objects.create(
            store=self.store, gateway_code="mellat", is_active=True,
        )
        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=self.order, gateway_config=config,
                callback_url="https://shop/cb", store=self.store,
            )


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


class CrossTenantTests(Feat005TestBase):
    def setUp(self):
        super().setUp()
        from apps.core.models import ShopSettings

        self.other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="feat005-other", status=Store.Status.ACTIVE,
        )
        ShopSettings.provision_for(self.other_store)

    def test_config_from_other_store_rejected_by_orchestrator(self):
        other_config = PaymentGatewayConfig.objects.create(
            store=self.other_store, gateway_code="zarinpal", is_active=True, is_sandbox=False,
        )
        other_config.set_credentials({"merchant_id": "y" * 36})
        other_config.save()
        with self.assertRaises(PaymentConfigError):
            initiate_payment(
                order=self.order, gateway_config=other_config,
                callback_url="https://shop/cb", store=self.store,
            )

    def test_other_store_config_does_not_affect_this_store_checkout(self):
        # Other store has a ready zarinpal config; THIS store has none.
        other_config = PaymentGatewayConfig.objects.create(
            store=self.other_store, gateway_code="zarinpal", is_active=True, is_sandbox=False,
        )
        other_config.set_credentials({"merchant_id": "y" * 36})
        other_config.save()
        # This store has its own legacy zarinpal gateway but NO config -> legacy
        # behavior (shown). The other store's config must not change that, and
        # must never make THIS store's option readiness-filtered by Store B data.
        gateways = checkout_service.active_payment_gateways(store=self.store)
        self.assertIn("zarinpal", {g.slug for g in gateways})

    def test_callback_bound_to_store_rejects_cross_tenant(self):
        config = self._ready_zarinpal_config()
        mock = _MockPspAdapter()
        with patch("apps.orders.services.gateway_payment_service.get_adapter", return_value=mock):
            attempt = initiate_payment(
                order=self.order, gateway_config=config,
                callback_url="https://shop/cb", store=self.store,
            )
            # A callback resolved to the WRONG store must not find the attempt.
            from apps.orders.services.gateway_payment_service import PaymentVerificationFailed

            with self.assertRaises(PaymentVerificationFailed):
                process_callback_and_verify(
                    attempt_public_id=attempt.public_id,
                    callback_data={"status": "1"},
                    store=self.other_store,
                )
