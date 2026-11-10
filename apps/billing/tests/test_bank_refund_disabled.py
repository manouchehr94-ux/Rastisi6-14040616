"""Pasargad / Saman / Mellat: AUTOMATIC bank reversals are disabled by default (fail-closed) because no verified idempotency contract
exists. Disabled means: no adapter/credentials/network call, the refund is recorded as manual processing (amount stays reserved), nothing is
marked refunded, the subscription entitlement does not change, repeats and concurrent requests cannot pay twice, and finance completes it
with a bank reference. The enabled path (explicit setting) classifies every doubtful answer as UNKNOWN and never retries.
Synthetic adapters only: no real bank, no network."""

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt, SubscriptionRefund
from apps.billing.providers import bank_refund_policy as policy
from apps.billing.providers import registry
from apps.billing.services import duplicate_payment_service as dups
from apps.billing.services import refund_service
from apps.billing.tests.test_credit_refund import _paid_invoice
from apps.billing.tests.test_phase2_refunds import FakeProvider, ok
from apps.core.models import AuditLogEntry
from apps.orders.gateways.base import GatewayCategory, GatewayConnectionError, PaymentOperation
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
R = SubscriptionRefund.Status
GATEWAYS = ("pasargad", "saman", "mellat")
PLATFORM_HOST = "platformadmins.rastisi.localhost"
AMOUNT = Decimal("400000")


class BankFixture:
    """A paid invoice whose successful attempt went through ``gateway`` and a spy adapter behind the REAL registry provider."""

    def make(self, slug, gateway, cancel=None):
        self.gateway = gateway
        self.store, self.invoice = _paid_invoice(slug)
        SubscriptionPaymentAttempt.objects.filter(invoice=self.invoice).update(
            provider=gateway, provider_payment_id=f"pay-{slug}", provider_session_id=f"sess-{slug}",
            provider_extra={"verified_ref": "REF-1", "urlId": "U1"})
        self.adapter = mock.Mock(name=f"{gateway}-adapter")
        self.adapter.supports.side_effect = lambda op: op == PaymentOperation.CANCEL
        self.adapter.category = GatewayCategory.PSP
        self.adapter.cancel_payment.side_effect = cancel or (lambda **_kw: mock.Mock(success=True, status_code=0))
        self.provider = registry.get_provider(gateway)
        self.get_adapter = mock.Mock(return_value=self.adapter)
        patches = [
            mock.patch.object(self.provider, "_adapter", self.get_adapter),
            mock.patch.object(self.provider, "_credentials", return_value=(self.adapter, {}, True)),
        ]
        for p in patches:
            p.start()
        return self

    def stop(self):
        mock.patch.stopall()

    def bank_calls(self):
        return self.adapter.cancel_payment.call_count + self.get_adapter.call_count

    def refund(self, key=None, amount=AMOUNT, **kw):
        return refund_service.request_refund(
            SubscriptionInvoice.objects.get(pk=self.invoice.pk), amount=Decimal(amount), reason="test",
            idempotency_key=key or f"k-{self.invoice.pk}", **kw)


class DisabledByDefaultTests(BankFixture, TestCase):
    def tearDown(self):
        self.stop()

    def test_the_default_setting_enables_nothing_and_unexpected_values_fail_closed(self):
        from django.conf import settings

        self.assertEqual(settings.RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS, "")
        self.assertEqual(policy.enabled_gateways(), frozenset())
        for value in (None, 5, True, {"saman": 1}, "zibal", "snappay, ,", "all", "*"):
            with override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS=value):
                self.assertEqual(policy.enabled_gateways(), frozenset(), value)
        with override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS=" Saman , mellat "):
            self.assertEqual(policy.enabled_gateways(), frozenset({"saman", "mellat"}))
        for code in ("manual", "zibal", "snappay", "torobpay", "zarinpal", "platform_card"):
            self.assertTrue(policy.automatic_refund_allowed(code), code)               # other providers are not governed by this switch
        for code in GATEWAYS:
            self.assertFalse(policy.automatic_refund_allowed(code), code)

    def test_a_refund_is_recorded_as_manual_with_no_bank_call_no_success_and_no_entitlement_change(self):
        for gateway in GATEWAYS:
            with self.subTest(gateway=gateway):
                self.make(f"bd-{gateway}", gateway)
                sub = StoreSubscription.objects.get(pk=self.invoice.subscription_id)
                before_status = sub.status
                refund = self.refund()
                self.assertEqual((refund.status, refund.failure_code), (R.PENDING, policy.AUTOMATIC_REFUND_DISABLED))
                self.assertEqual(refund.failure_message, policy.DISABLED_MESSAGE)
                self.assertEqual(self.bank_calls(), 0)                                   # not even the adapter was resolved
                invoice = SubscriptionInvoice.objects.get(pk=self.invoice.pk)
                self.assertEqual(invoice.status, SubscriptionInvoice.Status.PAID)         # never «refunded»
                self.assertEqual(StoreSubscription.objects.get(pk=sub.pk).status, before_status)
                self.assertEqual(refund_service.refundable_amount(invoice), Decimal("0"))   # the amount stays reserved
                self.assertFalse(SubscriptionRefund.objects.filter(invoice=invoice, status=R.SUCCEEDED).exists())
                self.assertFalse(AuditLogEntry.objects.filter(action_code="billing.refund_entitlement_outcome", object_id=str(invoice.pk)).exists())
                self.stop()

    def test_repeat_requests_and_a_different_key_can_never_reach_the_bank_or_pay_twice(self):
        self.make("bd-repeat", "pasargad")
        first = self.refund()
        again = self.refund()
        self.assertEqual(first.pk, again.pk)
        with self.assertRaises(refund_service.RefundError):                                # fully reserved: a second key is refused
            self.refund(key=f"k2-{self.invoice.pk}")
        with self.assertRaises(refund_service.RefundError):
            self.refund(key=f"k3-{self.invoice.pk}", amount="1")
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self.bank_calls(), 0)

    def test_the_provider_itself_refuses_a_direct_call_before_touching_the_adapter(self):
        for gateway in GATEWAYS:
            with self.subTest(gateway=gateway):
                self.make(f"bd-direct-{gateway}", gateway)
                result = self.provider.refund_payment(
                    provider_payment_id=f"pay-bd-direct-{gateway}", amount=AMOUNT, currency="IRT", idempotency_key="direct")
                self.assertFalse(result.succeeded)
                self.assertTrue(result.raw_summary.get(policy.AUTOMATIC_REFUND_DISABLED))
                self.assertFalse(result.raw_summary.get("unknown"))
                self.assertEqual(self.bank_calls(), 0)
                self.stop()

    def test_the_service_layer_stops_before_the_provider_is_resolved_even_if_the_registry_is_replaced(self):
        self.make("bd-svc", "mellat")
        fake = FakeProvider(ok)
        with mock.patch("apps.billing.services.refund_service.registry.get_provider", return_value=fake) as get_provider:
            refund = self.refund()
        self.assertEqual((refund.status, refund.failure_code), (R.PENDING, policy.AUTOMATIC_REFUND_DISABLED))
        self.assertEqual((fake.calls, get_provider.call_count), ([], 0))

    def test_duplicate_payment_refund_is_manual_idempotent_and_never_calls_the_bank(self):
        self.make("bd-dup", "saman")
        attempt = SubscriptionPaymentAttempt.objects.create(
            store=self.store, invoice=self.invoice, provider="saman", status=SubscriptionPaymentAttempt.Status.REQUIRES_ACTION,
            amount=AMOUNT, currency="IRT", failure_code="duplicate_payment", provider_payment_id="dup-pay-bank",
            idempotency_key="dup-bank-key")
        first = dups.refund_duplicate("subscription", attempt.pk, actor=None, reason="duplicate payment")
        second = dups.refund_duplicate("subscription", attempt.pk, actor=None, reason="duplicate payment")
        self.assertEqual((first[1], second[1]), ("pending_manual", "pending_manual"))
        self.assertEqual(self.bank_calls(), 0)
        attempt.refresh_from_db()
        self.assertFalse(dups.is_resolved(attempt))                                       # stays on finance's work list
        with self.assertRaises(dups.DuplicatePaymentError):
            dups.mark_resolved("subscription", attempt.pk, actor=None, outcome="refunded_external", reference="x")
        dups.mark_resolved("subscription", attempt.pk, actor=None, outcome="refunded_external", reference="BANK-REF-4242")
        attempt.refresh_from_db()
        self.assertTrue(dups.is_resolved(attempt))

    def test_manual_reconciliation_requires_a_bank_reference_and_only_then_changes_the_entitlement(self):
        self.make("bd-manual", "pasargad")
        refund = self.refund()
        sub = StoreSubscription.objects.get(pk=self.invoice.subscription_id)
        with self.assertRaises(refund_service.RefundError):
            refund_service.complete_refund_manually(refund, actor=None, reference="")
        with self.assertRaises(refund_service.RefundError):
            refund_service.complete_refund_manually(refund, actor=None, reference="abc")
        self.assertEqual(StoreSubscription.objects.get(pk=sub.pk).status, sub.status)
        done = refund_service.complete_refund_manually(refund, actor=None, reference="PEP-PANEL-REF-77")
        self.assertEqual(done.status, R.SUCCEEDED)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.REFUNDED)
        self.assertEqual(refund_service.complete_refund_manually(refund, actor=None, reference="PEP-PANEL-REF-77").pk, done.pk)  # idempotent
        self.assertEqual(self.bank_calls(), 0)

    def test_proof_that_nothing_was_refunded_releases_the_reservation_without_a_bank_call(self):
        self.make("bd-release", "saman")
        refund = self.refund()
        with self.assertRaises(refund_service.RefundError):
            refund_service.fail_refund_manually(refund, actor=None, reference="")
        refund_service.fail_refund_manually(refund, actor=None, reference="BANK-PROOF-1")
        self.assertEqual(refund_service.refundable_amount(SubscriptionInvoice.objects.get(pk=self.invoice.pk)), AMOUNT)
        self.assertEqual(self.bank_calls(), 0)

    def test_a_direct_http_post_is_recorded_as_manual_with_a_clear_warning_and_no_bank_call(self):
        self.make("bd-http", "pasargad")
        root = User.objects.create_user(username="bank-root", password="x", is_staff=True, is_superuser=True)
        client = Client(HTTP_HOST=PLATFORM_HOST)
        client.force_login(root)
        response = client.post(f"/payments/invoice/{self.invoice.pk}/refund/",
                               {"amount": "400000", "reason": "direct", "idempotency_key": "http-1"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "غیرفعال است")
        refund = SubscriptionRefund.objects.get(invoice=self.invoice)
        self.assertEqual((refund.status, refund.failure_code), (R.PENDING, policy.AUTOMATIC_REFUND_DISABLED))
        self.assertEqual(self.bank_calls(), 0)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)

    def test_providers_outside_the_switch_still_refund_normally(self):
        store, invoice = _paid_invoice("bd-normal")                                       # provider «manual»
        fake = FakeProvider(ok)
        with mock.patch("apps.billing.services.refund_service.registry.get_provider", return_value=fake):
            refund = refund_service.request_refund(invoice, amount=AMOUNT, idempotency_key="normal")
        self.assertEqual((refund.status, len(fake.calls)), (R.SUCCEEDED, 1))


@override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS="pasargad,saman,mellat")
class EnabledPathIsConservativeTests(BankFixture, TestCase):
    """Only reachable by explicitly enabling a gateway. Every doubtful answer is UNKNOWN and is never retried."""

    def tearDown(self):
        self.stop()

    def test_a_plain_zero_success_is_recorded_once_and_a_repeat_never_calls_again(self):
        self.make("be-ok", "saman")
        first = self.refund()
        self.assertEqual(first.status, R.SUCCEEDED)
        self.assertEqual(self.refund().pk, first.pk)
        self.assertEqual(self.adapter.cancel_payment.call_count, 1)

    def test_timeout_provider_error_and_unexpected_exception_are_unknown_reserved_and_never_retried(self):
        def timeout(**_kw):
            raise GatewayConnectionError("timeout", code="timeout")

        def boom(**_kw):
            raise RuntimeError("unexpected")

        for name, behaviour in (("timeout", timeout), ("boom", boom)):
            with self.subTest(name):
                self.make(f"be-{name}", "pasargad", cancel=behaviour)
                refund = self.refund()
                self.assertEqual((refund.status, refund.failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
                self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)
                self.assertEqual(self.refund().pk, refund.pk)                               # same key: no second call
                with self.assertRaises(refund_service.RefundError):                         # other key: blocked while unknown
                    self.refund(key=f"again-{self.invoice.pk}")
                self.assertEqual(self.adapter.cancel_payment.call_count, 1)
                with self.assertRaises(refund_service.RefundError):
                    refund_service.complete_refund_manually(refund, actor=None, reference="")
                self.stop()

    def test_a_non_ok_or_unusual_success_code_is_unknown_not_success_and_not_a_released_failure(self):
        for gateway, result in (
            ("mellat", mock.Mock(success=False, status_code=48)),      # «already reversed»: money may have moved
            ("saman", mock.Mock(success=True, status_code=2)),         # «2» is only documented for verify, never for reverse
            ("pasargad", mock.Mock(success=True, status_code=13033)),  # «reversed» seen on a repeat: not proof WE reversed it
            ("mellat", mock.Mock(success=False, status_code=421)),
        ):
            with self.subTest(gateway=gateway, code=result.status_code):
                self.make(f"be-{gateway}-{result.status_code}", gateway, cancel=lambda _r=result, **_kw: _r)
                refund = self.refund()
                self.assertEqual((refund.status, refund.failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
                self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)
                self.stop()

    def test_enabling_one_gateway_does_not_enable_the_others(self):
        with override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS="saman"):
            self.make("be-only-saman", "pasargad")
            refund = self.refund()
            self.assertEqual(refund.failure_code, policy.AUTOMATIC_REFUND_DISABLED)
            self.assertEqual(self.bank_calls(), 0)


class _Parallel:
    def run_parallel(self, workers, fn):
        barrier = threading.Barrier(workers)

        def worker(i):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                return fn(i)
            except Exception as exc:  # noqa: BLE001
                return type(exc).__name__
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(worker, range(workers)))


@skipUnless(connection.vendor == "postgresql", "needs PostgreSQL row locks / real concurrency")
class PostgresConcurrentBankRefundTests(BankFixture, _Parallel, TransactionTestCase):
    def tearDown(self):
        self.stop()

    def test_disabled_8_same_key_and_6_different_keys_make_one_row_and_zero_bank_calls(self):
        self.make("bc-off", "pasargad")
        pks = self.run_parallel(8, lambda _i: self.refund(key=f"same-{self.invoice.pk}").pk)
        self.assertEqual(len(set(pks)), 1, pks)
        outcomes = self.run_parallel(6, lambda i: self.refund(key=f"other-{self.invoice.pk}-{i}").pk)
        self.assertTrue(all(isinstance(o, str) for o in outcomes), outcomes)               # all refused (RefundError): fully reserved
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self.bank_calls(), 0)
        self.assertEqual(SubscriptionInvoice.objects.get(pk=self.invoice.pk).status, SubscriptionInvoice.Status.PAID)

    @override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS="saman")
    def test_enabled_8_same_key_call_the_bank_once_and_6_different_keys_never_pay_twice(self):
        self.make("bc-on", "saman")
        pks = self.run_parallel(8, lambda _i: self.refund(key=f"same-{self.invoice.pk}").pk)
        self.assertEqual(len(set(pks)), 1, pks)
        self.assertEqual(self.adapter.cancel_payment.call_count, 1)
        self.run_parallel(6, lambda i: self.refund(key=f"other-{self.invoice.pk}-{i}"))
        self.assertEqual(self.adapter.cancel_payment.call_count, 1)
        self.assertEqual(SubscriptionRefund.objects.filter(invoice=self.invoice).count(), 1)

    @override_settings(RASTISI_BANK_AUTOMATIC_REFUND_GATEWAYS="mellat")
    def test_enabled_timeout_under_concurrency_leaves_one_unknown_row_and_one_bank_call(self):
        def timeout(**_kw):
            raise GatewayConnectionError("timeout", code="timeout")

        self.make("bc-unk", "mellat", cancel=timeout)
        self.run_parallel(6, lambda i: self.refund(key=f"u{self.invoice.pk}-{i}"))
        rows = list(SubscriptionRefund.objects.filter(invoice=self.invoice))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].status, rows[0].failure_code), (R.PENDING, refund_service.UNKNOWN_OUTCOME))
        self.assertEqual(self.adapter.cancel_payment.call_count, 1)
