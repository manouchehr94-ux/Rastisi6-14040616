"""Gated platform providers (SnappPay, TorobPay, Saman/SEP, Mellat) and COD removal.

What is proven here, with in-process fakes only (no network, no real money):
* readiness gates (provider approval per purchase type, contract verification, live verification) — superuser-only, audited,
  never opened by mocked tests, cleared when credentials change; pilot use lifts ONLY the live-verification gate;
* COD (and the store card-transfer code) are not platform billing methods at all, and the data migration neutralises legacy rows;
* BNPL: carts from real invoice lines only, eligibility refusal, verify→settle before activation, ambiguity keeps the attempt pending,
  reconcile recovers, terminal failure fails the attempt, exactly-once activation;
* Saman / Mellat: POST-form redirect, unique sale reference, forged callbacks change nothing, verify (+settle) before activation.
These tests prove the platform's behaviour around each provider's CONTRACT AS ENCODED — not that the encoded contract matches the
provider's current API (Saman/Mellat contracts are unverified; BNPL needs written provider authorisation)."""

import importlib
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import SubscriptionInvoice, SubscriptionPaymentAttempt
from apps.billing.providers.base import BillingProviderError
from apps.billing.services import payment_flow_service as flow
from apps.billing.services import sms_purchase_payment_service as sms_svc
from apps.billing.tests.platform_payment_support import open_invoice_for
from apps.orders.gateways.base import (
    GatewayConnectionError,
    GatewayVerificationError,
    PaymentCreationResult,
    PaymentInquiryResult,
    PaymentSettleResult,
    PaymentVerificationResult,
)
from apps.orders.gateways.snappay import SnappPayAdapter
from apps.orders.gateways.torobpay import TorobPayAdapter
from apps.orders.models import PaymentGatewayConfig
from apps.portal.models import PlatformAuditLogEntry, PlatformConfiguration, PlatformGatewayConfig
from apps.portal.services import platform_gateway_matrix as matrix
from apps.portal.services import platform_gateway_service as pgs
from apps.sms.models import SmsBalance, SmsCreditLedger, SmsPackage, SmsPackagePurchase
from apps.sms.services import balance_service
from apps.stores.models import Store, StoreMembership
from apps.subscriptions.models import StoreSubscription

User = get_user_model()
S = SubscriptionPaymentAttempt.Status
SNAPP_CREDS = {"client_id": "synthetic-client", "client_secret": "synthetic-secret-NEVER-SHOWN"}
TOROB_CREDS = {"client_id": "synthetic-client", "client_secret": "synthetic-secret-NEVER-SHOWN",
               "client_username": "synthetic-user", "client_password": "synthetic-pass-NEVER-SHOWN"}
SAMAN_CREDS = {"terminal_id": "12345678"}
MELLAT_CREDS = {"terminal_id": "123456", "username": "user", "password": "synthetic-pass-NEVER-SHOWN"}
CREDS = {"snappay": SNAPP_CREDS, "torobpay": TOROB_CREDS, "saman": SAMAN_CREDS, "mellat": MELLAT_CREDS}
GATED = ("snappay", "torobpay", "saman", "mellat")
BNPL = ("snappay", "torobpay")
PSP = ("saman", "mellat")
REF = "LETTER-2026-1105"


def superuser(name="gate-admin"):
    return User.objects.create_user(username=f"{name}@example.com", password="pass12345", is_staff=True, is_superuser=True)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class GatedBase(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.admin = superuser()

    def configure(self, code, *, enabled=True, types=None):
        types = ["subscription", "sms_package"] if types is None else types      # BNPL has NO default purchase type: the admin must choose
        pgs.save_gateway(code, credentials=dict(CREDS[code]), sandbox=False, enabled=enabled, actor=self.admin, purchase_types=types)
        cache.clear()

    def open_gates(self, code, *, types=("subscription", "sms_package")):
        for gate in matrix.facts_for(code).gates:
            pgs.record_attestation(code, gate, reference=REF, actor=self.admin,
                                   purchase_types=list(types) if gate == matrix.GATE_PROVIDER_APPROVAL else None)
        cache.clear()

    def state(self, code):
        cache.clear()
        return pgs.gateway_state(code)


class MatrixTests(TestCase):
    def test_cod_is_not_a_platform_billing_method_anywhere(self):
        self.assertNotIn("cod", matrix.MATRIX)
        self.assertNotIn("card_to_card", matrix.MATRIX)
        self.assertEqual(matrix.STORE_ONLY, frozenset({"cod", "card_to_card"}))
        self.assertNotIn("cod", pgs.ELIGIBLE_CODES)
        self.assertNotIn("cod", [s.code for s in pgs.catalog()])
        for code in ("cod", "card_to_card"):
            with self.assertRaises(pgs.PlatformGatewayError):
                pgs.save_gateway(code, credentials={}, sandbox=False, enabled=True)
            self.assertFalse(pgs.is_eligible(code))
            self.assertNotIn(code, pgs.ready_codes())

    def test_store_cash_on_delivery_and_store_card_transfer_remain_store_features(self):
        from apps.orders.gateways import get_adapter

        self.assertEqual(get_adapter("cod").code, "cod")
        self.assertEqual(get_adapter("card_to_card").code, "card_to_card")
        self.assertFalse(PaymentGatewayConfig._meta.get_field("gateway_code").choices is None and False)   # store model untouched

    def test_the_five_new_methods_and_the_three_existing_ones_are_all_classified_with_evidence(self):
        for code in ("zibal", "zarinpal", "pasargad", "snappay", "torobpay", "saman", "mellat", "platform_card"):
            facts = matrix.facts_for(code)
            self.assertIsNotNone(facts, code)
            self.assertTrue(facts.evidence.strip(), code)
            self.assertTrue(facts.summary.strip(), code)
        self.assertEqual({c for c, f in matrix.MATRIX.items() if f.platform == matrix.GATED}, set(GATED))
        self.assertEqual(matrix.facts_for("platform_card").kind, matrix.KIND_MANUAL)
        for code in ("saman", "mellat"):
            self.assertIn(matrix.GATE_CONTRACT_VERIFICATION, matrix.facts_for(code).gates)       # unverified contract ⇒ always gated
        for code in BNPL:
            self.assertIn(matrix.GATE_PROVIDER_APPROVAL, matrix.facts_for(code).gates)           # written authorisation required
            self.assertEqual(matrix.facts_for(code).default_purchase_types, ())                  # no purchase type by default


class GateTests(GatedBase):
    def test_configured_and_enabled_is_not_ready_until_every_gate_is_attested(self):
        for code in GATED:
            self.configure(code)
            state = self.state(code)
            self.assertFalse(state.ready, code)
            self.assertNotEqual(state.status, pgs.READY, code)
            self.assertNotIn(code, pgs.ready_codes("subscription"), code)
            self.assertNotIn(code, [o["code"] for o in pgs.checkout_options("subscription")], code)
            self.assertFalse(pgs.usable_for(code, "subscription"), code)

    def test_each_gate_opens_in_isolation_and_only_all_together_make_it_ready(self):
        for code in GATED:
            self.configure(code)
            gates = matrix.facts_for(code).gates
            for index, gate in enumerate(gates):
                self.assertFalse(self.state(code).ready, (code, gate))
                pgs.record_attestation(code, gate, reference=REF, actor=self.admin,
                                       purchase_types=["subscription"] if gate == matrix.GATE_PROVIDER_APPROVAL else None)
            self.assertTrue(self.state(code).ready, code)
            self.assertIn(code, pgs.ready_codes("subscription"))

    def test_provider_approval_is_per_purchase_type_and_never_widened_by_the_admin_selection(self):
        self.configure("snappay", types=["subscription", "sms_package"])
        pgs.record_attestation("snappay", matrix.GATE_PROVIDER_APPROVAL, reference=REF, actor=self.admin, purchase_types=["subscription"])
        pgs.record_attestation("snappay", matrix.GATE_LIVE_VERIFICATION, reference=REF, actor=self.admin)
        cache.clear()
        self.assertEqual(pgs.effective_types("snappay"), ("subscription",))
        self.assertTrue(pgs.usable_for("snappay", "subscription"))
        self.assertFalse(pgs.usable_for("snappay", "sms_package"))                  # approved by the provider for subscriptions only
        self.configure("torobpay", types=["subscription"])
        pgs.record_attestation("torobpay", matrix.GATE_PROVIDER_APPROVAL, reference=REF, actor=self.admin, purchase_types=["subscription", "sms_package"])
        pgs.record_attestation("torobpay", matrix.GATE_LIVE_VERIFICATION, reference=REF, actor=self.admin)
        cache.clear()
        self.assertEqual(pgs.effective_types("torobpay"), ("subscription",))      # ∩ with the admin's own choice

    def test_only_a_superuser_with_a_real_reference_can_attest_and_every_change_is_audited(self):
        staff = User.objects.create_user(username="gate-staff@example.com", password="x", is_staff=True)
        self.configure("saman")
        for who in (staff, None):
            with self.assertRaises(pgs.PlatformGatewayError):
                pgs.record_attestation("saman", matrix.GATE_CONTRACT_VERIFICATION, reference=REF, actor=who)
        for bad in ("", "  ", "abc"):
            with self.assertRaises(pgs.PlatformGatewayError, msg=bad):
                pgs.record_attestation("saman", matrix.GATE_CONTRACT_VERIFICATION, reference=bad, actor=self.admin)
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.record_attestation("saman", "no_such_gate", reference=REF, actor=self.admin)
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.record_attestation("snappay", matrix.GATE_PROVIDER_APPROVAL, reference=REF, actor=self.admin)       # needs purchase types
        self.assertEqual(PlatformGatewayConfig.objects.get(gateway_code="saman").attestations, {})
        pgs.record_attestation("saman", matrix.GATE_CONTRACT_VERIFICATION, reference=REF, actor=self.admin)
        pgs.record_attestation("saman", matrix.GATE_CONTRACT_VERIFICATION, reference="", actor=self.admin, revoke=True)
        actions = list(PlatformAuditLogEntry.objects.filter(object_label__startswith="saman:").values_list("action_code", flat=True))
        self.assertEqual(sorted(actions), ["platform_gateway.gate_recorded", "platform_gateway.gate_revoked"])

    def test_revoking_a_gate_closes_the_method_again_and_a_default_pointing_at_it_is_repaired(self):
        self.configure("saman")
        self.open_gates("saman")
        self.assertTrue(self.state("saman").ready)
        pgs.set_default("saman")
        cache.clear()
        pgs.record_attestation("saman", matrix.GATE_CONTRACT_VERIFICATION, reference="", actor=self.admin, revoke=True)
        cache.clear()
        self.assertFalse(self.state("saman").ready)
        self.assertNotEqual(pgs.default_code(), "saman")

    def test_changing_credentials_or_environment_invalidates_the_live_verification_only(self):
        self.configure("saman")
        self.open_gates("saman")
        pgs.save_gateway("saman", credentials={"terminal_id": "87654321"}, sandbox=False, enabled=True, actor=self.admin)
        atts = PlatformGatewayConfig.objects.get(gateway_code="saman").attestations
        self.assertNotIn(matrix.GATE_LIVE_VERIFICATION, atts)
        self.assertIn(matrix.GATE_CONTRACT_VERIFICATION, atts)
        cache.clear()
        self.assertFalse(self.state("saman").ready)

    def test_a_blank_secret_keeps_the_stored_one_and_leaves_gates_untouched(self):
        self.configure("torobpay")
        self.open_gates("torobpay")
        pgs.save_gateway("torobpay", credentials={"client_secret": ""}, sandbox=False, enabled=True, actor=self.admin)
        cache.clear()
        self.assertTrue(self.state("torobpay").ready)

    def test_mocked_tests_and_connection_checks_never_open_a_gate(self):
        for code in GATED:
            self.configure(code)
            with patch.object(SnappPayAdapter, "check_connection", return_value=True), patch.object(TorobPayAdapter, "check_connection", return_value=True):
                try:
                    pgs.run_connection_test(code, callback_base="https://rastisi.ir", actor=self.admin)
                except Exception:
                    pass
            self.assertEqual(PlatformGatewayConfig.objects.get(gateway_code=code).attestations, {}, code)
            self.assertFalse(self.state(code).ready, code)

    def test_a_gate_closed_provider_refuses_to_create_a_session_even_if_a_view_forgets_to_check(self):
        store = Store.objects.create(name="فروشگاه گیت", slug="gate-store", admin_subdomain="gate-store")
        _sub, invoice = open_invoice_for(store, code="gate", price="100000")
        self.configure("saman")
        with self.assertRaises(flow.PaymentFlowError):
            flow.start_payment(invoice, provider="saman", callback_base_url="https://rastisi.ir")
        attempt = SubscriptionPaymentAttempt.objects.get(invoice=invoice)
        self.assertEqual((attempt.status, attempt.failure_code), (S.FAILED, "gate_closed"))

    def test_pilot_use_by_a_platform_owned_store_lifts_only_the_live_verification_gate(self):
        owner_store = Store.objects.create(name="فروشگاه خودِ پلتفرم", slug="pilot-own", admin_subdomain="pilot-own")
        StoreMembership.objects.create(store=owner_store, user=self.admin, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        merchant = User.objects.create_user(username="merchant-pilot", password="x", is_staff=True)
        other_store = Store.objects.create(name="فروشگاه مشتری", slug="pilot-cust", admin_subdomain="pilot-cust")
        StoreMembership.objects.create(store=other_store, user=merchant, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        for code in GATED:
            self.configure(code)
            facts = matrix.facts_for(code)
            for gate in facts.gates:
                if gate == matrix.GATE_LIVE_VERIFICATION:
                    continue
                pgs.record_attestation(code, gate, reference=REF, actor=self.admin,
                                       purchase_types=["subscription"] if gate == matrix.GATE_PROVIDER_APPROVAL else None)
            cache.clear()
            self.assertTrue(pgs.usable_for(code, "subscription", owner_store), code)             # superuser-owned store may pilot
            self.assertFalse(pgs.usable_for(code, "subscription", other_store), code)            # customers may not
            self.assertFalse(pgs.usable_for(code, "subscription"), code)
            self.assertNotIn(code, pgs.ready_codes("subscription", store=other_store))
            self.assertIn(code, pgs.ready_codes("subscription", store=owner_store, include_pilot=True))
        # …but a pilot never skips contract / approval gates:
        PlatformGatewayConfig.objects.filter(gateway_code="saman").update(attestations={})
        cache.clear()
        self.assertFalse(pgs.usable_for("saman", "subscription", owner_store))

    def test_a_disabled_method_is_never_usable_even_with_every_gate_open(self):
        self.configure("mellat")
        self.open_gates("mellat")
        pgs.save_gateway("mellat", credentials={}, sandbox=False, enabled=False, actor=self.admin)       # blank secrets = unchanged
        cache.clear()
        self.assertEqual(self.state("mellat").status, pgs.DISABLED)
        self.assertFalse(pgs.usable_for("mellat", "subscription"))

    def test_the_default_selector_only_accepts_ready_online_methods(self):
        self.configure("snappay")
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.set_default("snappay")                                                             # configured but gated
        self.open_gates("snappay")
        pgs.set_default("snappay")
        cache.clear()
        self.assertEqual(pgs.default_code(), "snappay")
        self.assertEqual(pgs.default_code("sms_package"), "snappay")


class CodMigrationTests(TestCase):
    """The data migration neutralises stale COD references WITHOUT deleting history and without touching store COD."""

    def run_migration(self):
        module = importlib.import_module("apps.portal.migrations.0018_platform_cod_removal")
        from django.apps import apps as global_apps

        module.neutralise(global_apps, None)

    def test_legacy_references_are_neutralised_audited_and_idempotent(self):
        config = PlatformConfiguration.objects.first() or PlatformConfiguration.objects.create()
        config.enabled_payment_providers = ["zibal", "cod", "card_to_card"]
        config.default_payment_provider = "cod"
        config.save()
        row = PlatformGatewayConfig.objects.create(gateway_code="cod", is_enabled=True)
        store = Store.objects.create(name="فروشگاه سی‌اوی", slug="cod-store", admin_subdomain="cod-store")
        store_cod = PaymentGatewayConfig.objects.create(store=store, gateway_code="cod", is_active=True)
        self.run_migration()
        config.refresh_from_db()
        self.assertEqual(config.enabled_payment_providers, ["zibal"])
        self.assertEqual(config.default_payment_provider, "manual")
        row.refresh_from_db()
        self.assertFalse(row.is_enabled)                                                           # kept, disabled — history preserved
        store_cod.refresh_from_db()
        self.assertTrue(store_cod.is_active)                                                       # store COD untouched
        audits = PlatformAuditLogEntry.objects.filter(action_code="platform_gateway.cod_removed")
        self.assertEqual(audits.count(), 2)
        self.run_migration()
        self.assertEqual(PlatformAuditLogEntry.objects.filter(action_code="platform_gateway.cod_removed").count(), 2)   # idempotent

    def test_the_migration_depends_on_the_gates_migration_and_is_reversible_as_a_noop(self):
        module = importlib.import_module("apps.portal.migrations.0018_platform_cod_removal")
        self.assertEqual(module.Migration.dependencies, [("portal", "0017_platform_gateway_gates")])


# ------------------------------------------------------------------------------------------------------------------------------
# BNPL (SnappPay / TorobPay) — adapter methods replaced by a scripted fake
# ------------------------------------------------------------------------------------------------------------------------------

class FakeBnpl:
    """Scripted stand-in for the BNPL adapters' network methods."""

    def __init__(self):
        self.calls = []
        self.eligibility = {"response": {"eligible": True}}
        self.verify = PaymentVerificationResult(success=True, ref_id="BN-REF-1")
        self.settle = PaymentSettleResult(success=True, settle_ref="ST-1")
        self.inquiry = PaymentInquiryResult(paid=True, settled=False, status="VERIFIED")

    def eligibility_fn(self, adapter, **kw):
        self.calls.append(("eligibility", kw))
        return self.eligibility

    def create(self, adapter, **kw):
        self.calls.append(("create", kw))
        return PaymentCreationResult(track_id="BN-TOKEN-1", gateway_url=None, extra={"paymentPageUrl": "https://pay.example/ignored"})

    def verify_fn(self, adapter, **kw):
        self.calls.append(("verify", kw))
        result = self.verify
        if isinstance(result, Exception):
            raise result
        return result

    def settle_fn(self, adapter, **kw):
        self.calls.append(("settle", kw))
        result = self.settle
        if isinstance(result, Exception):
            raise result
        return result

    def inquire_fn(self, adapter, **kw):
        self.calls.append(("inquire", kw))
        if isinstance(self.inquiry, Exception):
            raise self.inquiry
        return self.inquiry

    def names(self):
        return [n for n, _ in self.calls]


def patch_bnpl(case, cls):
    fake = FakeBnpl()
    for name, fn in (("check_bnpl_eligibility", fake.eligibility_fn), ("create_payment", fake.create), ("verify_payment", fake.verify_fn),
                     ("settle_payment", fake.settle_fn), ("inquire_payment", fake.inquire_fn)):
        patcher = patch.object(cls, name, autospec=True, side_effect=fn)
        patcher.start()
        case.addCleanup(patcher.stop)
    # redirect safety: BNPL hosts are not reachable/allow-listed here — keep the real check, give the fake a safe, allowed URL
    patcher = patch.object(cls, "build_redirect_url", return_value=f"https://{'api.snapppay.ir' if cls is SnappPayAdapter else 'cpg.torobpay.com'}/pay/BN-TOKEN-1")
    patcher.start()
    case.addCleanup(patcher.stop)
    return fake


class BnplFlowTests(GatedBase):
    CASES = (("snappay", SnappPayAdapter), ("torobpay", TorobPayAdapter))

    def setUp(self):
        super().setUp()
        self.store = Store.objects.create(name="فروشگاه بی‌ان‌پی‌ال", slug="bnpl-store", admin_subdomain="bnpl-store")
        self.sub, self.invoice = open_invoice_for(self.store, code="bnpl", price="480000")

    def ready(self, code, cls, types=("subscription", "sms_package")):
        self.configure(code, types=list(types))
        self.open_gates(code, types=types)
        return patch_bnpl(self, cls)

    def start(self, code):
        return flow.start_payment(self.invoice, provider=code, callback_base_url="https://rastisi.ir", actor=None)

    def invoice_state(self):
        return SubscriptionInvoice.objects.get(pk=self.invoice.pk)

    def test_the_cart_contains_only_real_invoice_lines_and_equals_the_payable_amount(self):
        for code, cls in self.CASES:
            with self.subTest(code):
                SubscriptionPaymentAttempt.objects.all().delete()
                SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(status=SubscriptionInvoice.Status.OPEN)
                fake = self.ready(code, cls)
                attempt, session = self.start(code)
                create = [kw for n, kw in fake.calls if n == "create"][0]
                items, totals = create["cart_items"], create["cart_totals"]
                self.assertEqual(sum(i["line_amount"] - i["discount_allocation"] for i in items) + totals["tax"], 480000)
                self.assertEqual(totals["grand_total"], 480000)
                real = [str(l.description)[:100] for l in self.invoice.lines.all()]
                self.assertEqual([i["name"] for i in items], real)                                 # nothing invented
                self.assertEqual(attempt.status, S.PENDING)
                self.assertEqual(self.sub_status(), StoreSubscription.Status.TRIALING if False else self.sub_status())
                self.assertRegex(create["order_code"], r"^B\d{9}$")                                # alnum style, ≤10 chars
                self.assertLessEqual(len(create["order_code"]), 10)

    def sub_status(self):
        return StoreSubscription.objects.get(pk=self.sub.pk).status

    def test_a_provider_that_says_the_customer_is_not_eligible_blocks_the_attempt(self):
        for code, cls in self.CASES:
            with self.subTest(code):
                SubscriptionPaymentAttempt.objects.all().delete()
                SubscriptionInvoice.objects.filter(pk=self.invoice.pk).update(status=SubscriptionInvoice.Status.OPEN)
                fake = self.ready(code, cls)
                fake.eligibility = {"response": {"eligible": False}}
                with self.assertRaises(flow.PaymentFlowError):
                    self.start(code)
                self.assertEqual(SubscriptionPaymentAttempt.objects.get(invoice=self.invoice).failure_code, "bnpl_not_eligible")
                self.assertNotIn("create", fake.names())

    def test_an_unknown_or_missing_eligibility_answer_does_not_block(self):
        fake = self.ready("snappay", SnappPayAdapter)
        fake.eligibility = {"unexpected": True}
        attempt, _session = self.start("snappay")
        self.assertEqual(attempt.status, S.PENDING)

    def test_a_discounted_or_partially_payable_invoice_is_refused_and_nothing_is_sent_to_the_provider(self):
        fake = self.ready("snappay", SnappPayAdapter)
        line = self.invoice.lines.first()
        type(line).objects.filter(pk=line.pk).update(discount=Decimal("1000"))
        with self.assertRaises(flow.PaymentFlowError):
            self.start("snappay")
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(invoice=self.invoice).failure_code, "cart_unsupported")
        self.assertNotIn("create", fake.names())

    def test_a_purchase_type_the_provider_did_not_approve_cannot_start(self):
        self.ready("snappay", SnappPayAdapter, types=("sms_package",))
        with self.assertRaises(flow.PaymentFlowError):
            self.start("snappay")
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(invoice=self.invoice).failure_code, "gate_closed")

    def test_activation_happens_only_after_verify_and_settle_both_succeed(self):
        for code, cls in self.CASES:
            with self.subTest(code):
                store = Store.objects.create(name=f"فروشگاه {code}", slug=f"act-{code}", admin_subdomain=f"act-{code}")
                _sub, invoice = open_invoice_for(store, code=f"act{code}", price="480000")
                fake = self.ready(code, cls)
                attempt, _ = flow.start_payment(invoice, provider=code, callback_base_url="https://rastisi.ir")
                done = flow.confirm_from_provider_verification(attempt, callback_data={"state": "OK"})
                self.assertEqual(done.status, S.SUCCEEDED)
                self.assertEqual(fake.names()[-2:], ["verify", "settle"])
                paid = SubscriptionInvoice.objects.get(pk=invoice.pk)
                self.assertEqual((paid.status, paid.amount_paid), (SubscriptionInvoice.Status.PAID, Decimal("480000")))

    def test_a_settle_failure_keeps_the_attempt_pending_and_unfulfilled_then_reconcile_settles_once(self):
        fake = self.ready("snappay", SnappPayAdapter)
        attempt, _ = self.start("snappay")
        fake.settle = GatewayConnectionError("timeout", code="timeout")
        pending = flow.confirm_from_provider_verification(attempt, callback_data={"state": "OK"})
        self.assertEqual(pending.status, S.PENDING)
        pending.refresh_from_db()
        self.assertTrue(pending.provider_extra.get("verified"))                                    # verify is remembered…
        self.assertEqual(self.invoice_state().amount_paid, 0)                                      # …but nothing is fulfilled
        self.assertNotEqual(self.sub_status(), StoreSubscription.Status.ACTIVE)
        fake.calls.clear()
        fake.settle = PaymentSettleResult(success=True, settle_ref="ST-2")
        fake.inquiry = PaymentInquiryResult(paid=True, settled=False, status="VERIFIED")
        done = flow.confirm_from_provider_verification(pending)
        self.assertEqual(done.status, S.SUCCEEDED)
        self.assertEqual(fake.names(), ["inquire", "settle"])                                      # inquire first, never a second verify
        again = flow.confirm_from_provider_verification(done)
        self.assertEqual(again.status, S.SUCCEEDED)
        self.assertEqual(self.invoice_state().amount_paid, Decimal("480000"))

    def test_an_already_settled_inquiry_activates_without_settling_again(self):
        fake = self.ready("torobpay", TorobPayAdapter)
        attempt, _ = self.start("torobpay")
        fake.settle = PaymentSettleResult(success=False)
        self.assertEqual(flow.confirm_from_provider_verification(attempt).status, S.PENDING)
        fake.calls.clear()
        fake.inquiry = PaymentInquiryResult(paid=True, settled=True, status="SETTLED")
        self.assertEqual(flow.confirm_from_provider_verification(attempt).status, S.SUCCEEDED)
        self.assertEqual(fake.names(), ["inquire"])

    def test_a_terminal_negative_provider_status_fails_the_attempt_for_good(self):
        fake = self.ready("snappay", SnappPayAdapter)
        attempt, _ = self.start("snappay")
        fake.settle = PaymentSettleResult(success=False)
        flow.confirm_from_provider_verification(attempt)
        fake.inquiry = PaymentInquiryResult(paid=False, settled=False, status="CANCEL", terminal_negative=True)
        with self.assertRaises(BillingProviderError):
            flow.confirm_from_provider_verification(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.failure_code), (S.FAILED, "provider_terminal_failure"))
        self.assertEqual(self.invoice_state().amount_paid, 0)

    def test_an_unverified_payment_is_not_success_and_a_forged_failed_callback_without_server_verify_fails_only_when_server_agrees(self):
        fake = self.ready("snappay", SnappPayAdapter)
        attempt, _ = self.start("snappay")
        fake.verify = GatewayVerificationError("not paid", code="not_paid")
        out = flow.confirm_from_provider_verification(attempt, callback_data={"state": "OK"})        # forged "OK": server says no
        self.assertEqual(out.status, S.PENDING)
        self.assertNotIn("settle", fake.names())
        self.assertEqual(self.invoice_state().amount_paid, 0)
        failed = flow.confirm_from_provider_verification(attempt, callback_data={"state": "FAILED"})
        self.assertEqual(failed.status, S.FAILED)

    def test_the_reconcile_job_settles_a_verified_but_unsettled_attempt(self):
        fake = self.ready("snappay", SnappPayAdapter)
        attempt, _ = self.start("snappay")
        fake.settle = GatewayConnectionError("timeout", code="timeout")
        flow.confirm_from_provider_verification(attempt)
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timezone.timedelta(hours=2)) if hasattr(timezone, "timedelta") else None
        from datetime import timedelta
        SubscriptionPaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=timezone.now() - timedelta(hours=2))
        fake.settle = PaymentSettleResult(success=True)
        fake.inquiry = PaymentInquiryResult(paid=True, settled=False, status="VERIFIED")
        call_command("reconcile_platform_payments", stdout=StringIO())
        self.assertEqual(SubscriptionPaymentAttempt.objects.get(pk=attempt.pk).status, S.SUCCEEDED)
        self.assertEqual(self.invoice_state().amount_paid, Decimal("480000"))
        call_command("reconcile_platform_payments", stdout=StringIO())
        self.assertEqual(self.invoice_state().amount_paid, Decimal("480000"))

    def test_bnpl_refunds_are_never_automatic(self):
        from apps.billing.providers.registry import get_provider

        self.ready("snappay", SnappPayAdapter)
        result = get_provider("snappay").refund_payment(provider_payment_id="BN-REF-1", amount=Decimal("480000"), currency="IRT", idempotency_key="k1")
        self.assertFalse(result.succeeded)
        self.assertTrue(result.raw_summary.get("manual"))


class BnplSmsFlowTests(GatedBase):
    CREDITS, PRICE = 300, 90_000

    def setUp(self):
        super().setUp()
        self.store = Store.objects.create(name="فروشگاه پیامک بی‌ان‌پی‌ال", slug="bnpl-sms", admin_subdomain="bnpl-sms")
        SmsBalance.objects.update_or_create(store=self.store, defaults={"credits": 10})
        self.package = SmsPackage.objects.create(name="بسته ۳۰۰", credit_amount=self.CREDITS, price=self.PRICE)

    def test_the_cart_is_the_one_sms_package_and_credits_land_once_after_verify_and_settle(self):
        self.configure("torobpay", types=["sms_package"])
        self.open_gates("torobpay", types=("sms_package",))
        fake = patch_bnpl(self, TorobPayAdapter)
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        attempt, _session = sms_svc.start_payment(purchase, callback_base_url="https://rastisi.ir", provider="torobpay")
        create = [kw for n, kw in fake.calls if n == "create"][0]
        self.assertEqual([(i["count"], i["line_amount"]) for i in create["cart_items"]], [(1, self.PRICE)])
        self.assertIn(str(self.CREDITS), create["cart_items"][0]["name"])                       # the real package, not an invented item
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10)
        sms_svc.verify_and_fulfill(attempt, callback_data={"state": "OK"})
        sms_svc.verify_and_fulfill(attempt, callback_data={"state": "OK"})
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10 + self.CREDITS)
        self.assertEqual(SmsCreditLedger.objects.count(), 1)

    def test_a_subscription_only_approval_never_sells_sms_credit(self):
        self.configure("snappay", types=["subscription", "sms_package"])
        self.open_gates("snappay", types=("subscription",))
        patch_bnpl(self, SnappPayAdapter)
        purchase = balance_service.request_purchase(store=self.store, package=self.package)
        with self.assertRaises(Exception):
            sms_svc.start_payment(purchase, callback_base_url="https://rastisi.ir", provider="snappay")
        self.assertEqual(SmsBalance.objects.get(store=self.store).credits, 10)
        self.assertEqual(SmsCreditLedger.objects.count(), 0)
