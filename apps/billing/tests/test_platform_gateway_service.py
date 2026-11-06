"""Platform-owner payment gateways: eligibility, readiness, secret handling, default selection, legacy Zibal read-through
and the HARD isolation between platform merchant credentials and store merchant credentials."""

from pathlib import Path

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.billing.providers import registry
from apps.billing.tests.platform_payment_support import (
    PLATFORM_MERCHANT, STORE_MERCHANT, ZARINPAL_PLATFORM, ZARINPAL_STORE,
    open_invoice_for, patch_zarinpal, patch_zibal, ready_platform_zarinpal, ready_platform_zibal,
)
from apps.orders.models import PaymentGatewayConfig
from apps.portal.models import PlatformAuditLogEntry, PlatformConfiguration, PlatformGatewayConfig
from apps.portal.services import platform_gateway_service as pgs
from apps.portal.services.platform_config_service import get_platform_configuration
from apps.stores.models import Store


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class EligibilityTests(TestCase):
    IMPLEMENTED = {"zibal", "zarinpal", "pasargad", "snappay", "torobpay", "saman", "mellat", "platform_card"}

    def test_exactly_the_implemented_methods_are_configurable_for_platform_billing(self):
        self.assertEqual({c for c in pgs.ELIGIBLE_CODES if pgs.is_eligible(c)}, self.IMPLEMENTED)

    def test_not_implemented_and_store_only_methods_are_refused_with_a_reason(self):
        for code in ("parsian", "sadad", "tejarat", "cod", "card_to_card", "nope"):
            self.assertFalse(pgs.is_eligible(code), code)
            self.assertTrue(pgs.ineligibility_reason(code), code)
            with self.assertRaises(pgs.PlatformGatewayError, msg=code):
                pgs.save_gateway(code, credentials={}, sandbox=False, enabled=True)
        self.assertFalse(PlatformGatewayConfig.objects.exists())

    def test_catalog_lists_platform_methods_only_and_never_cod_or_store_card_to_card(self):
        states = {s.code: s for s in pgs.catalog()}
        self.assertTrue(all(states[c].eligible for c in self.IMPLEMENTED))
        self.assertFalse(states["parsian"].eligible)
        self.assertEqual(states["parsian"].status, pgs.NOT_IMPLEMENTED)
        self.assertNotIn("cod", states)
        self.assertNotIn("card_to_card", states)
        self.assertEqual(states["platform_card"].kind, "manual")


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class ReadinessTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()

    def test_cannot_enable_without_complete_credentials(self):
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.save_gateway("zibal", credentials={}, sandbox=False, enabled=True)
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.save_gateway("zarinpal", credentials={"merchant_id": "short"}, sandbox=False, enabled=True)
        self.assertEqual(pgs.ready_codes(), [])

    def test_zibal_sandbox_is_ready_without_a_merchant_but_zarinpal_has_no_sandbox(self):
        pgs.save_gateway("zibal", credentials={}, sandbox=True, enabled=True)
        self.assertEqual(pgs.ready_codes(), ["zibal"])
        row = pgs.save_gateway("zarinpal", credentials={"merchant_id": ZARINPAL_PLATFORM}, sandbox=True, enabled=True)
        self.assertFalse(row.sandbox_mode)                    # unsupported ⇒ never silently enabled

    def test_saved_but_disabled_gateway_is_not_ready_and_not_offered(self):
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=False)
        state = pgs.gateway_state("zibal")
        self.assertTrue(state.configured)
        self.assertFalse(state.ready)
        self.assertEqual(pgs.checkout_options(), [])

    def test_blank_secret_keeps_the_stored_value(self):
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=True)
        pgs.save_gateway("zibal", credentials={"merchant": ""}, sandbox=False, enabled=True)
        creds, _sandbox, _src = pgs.credentials_and_mode("zibal")
        self.assertEqual(creds["merchant"], PLATFORM_MERCHANT)

    def test_default_is_reassigned_when_the_default_gateway_becomes_unready(self):
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=True)
        pgs.save_gateway("zarinpal", credentials={"merchant_id": ZARINPAL_PLATFORM}, sandbox=False, enabled=True)
        pgs.set_default("zibal")
        self.assertEqual(pgs.default_code(), "zibal")
        pgs.save_gateway("zibal", credentials={}, sandbox=False, enabled=False)
        self.assertEqual(get_platform_configuration().default_payment_provider, "zarinpal")
        pgs.save_gateway("zarinpal", credentials={}, sandbox=False, enabled=False)
        self.assertEqual(get_platform_configuration().default_payment_provider, "manual")

    def test_set_default_requires_a_ready_gateway(self):
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.set_default("zibal")
        with self.assertRaises(pgs.PlatformGatewayError):
            pgs.set_default("saman")

    def test_checkout_provider_resolution_never_accepts_arbitrary_codes(self):
        ready_platform_zibal(self)
        self.assertEqual(pgs.resolve_checkout_provider(""), "zibal")
        self.assertEqual(pgs.resolve_checkout_provider("zibal"), "zibal")
        for bad in ("zarinpal", "saman", "manual", "../etc", "ZIBAL"):
            with self.assertRaises(pgs.PlatformGatewayError, msg=bad):
                pgs.resolve_checkout_provider(bad)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class SecretHandlingTests(TestCase):
    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()

    def test_credentials_are_encrypted_at_rest_and_absent_from_state_and_audit(self):
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=True)
        raw = PlatformGatewayConfig.objects.get(gateway_code="zibal").encrypted_credentials
        self.assertTrue(raw)
        self.assertNotIn(PLATFORM_MERCHANT, raw)
        state = pgs.gateway_state("zibal")
        self.assertNotIn(PLATFORM_MERCHANT, repr(state))
        self.assertEqual(state.fields[0]["configured"], True)
        blob = " ".join(
            f"{e.before_summary} {e.after_summary} {e.metadata} {e.object_label}" for e in PlatformAuditLogEntry.objects.all()
        )
        self.assertNotIn(PLATFORM_MERCHANT, blob)
        self.assertTrue(PlatformAuditLogEntry.objects.filter(action_code="platform_gateway.saved").exists())

    def test_the_legacy_mirror_never_leaks_into_audit_either(self):
        pgs.save_gateway("zibal", credentials={"merchant": PLATFORM_MERCHANT}, sandbox=False, enabled=True)
        blob = " ".join(f"{e.before_summary} {e.after_summary} {e.metadata}" for e in PlatformAuditLogEntry.objects.all())
        self.assertNotIn(PLATFORM_MERCHANT, blob)


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class LegacyZibalCompatibilityTests(TestCase):
    """QA databases may already hold the pre-existing Zibal platform credentials in PlatformConfiguration."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        config = get_platform_configuration()
        config.default_payment_provider = "zibal"
        config.set_zibal_credentials(merchant=PLATFORM_MERCHANT)
        config.save()
        cache.clear()

    def test_legacy_credentials_are_read_without_any_row_and_are_ready(self):
        self.assertFalse(PlatformGatewayConfig.objects.exists())
        state = pgs.gateway_state("zibal")
        self.assertEqual((state.source, state.ready, state.enabled), ("legacy", True, True))
        self.assertEqual(pgs.ready_codes(), ["zibal"])
        self.assertEqual(registry.active_provider_code(), "zibal")

    def test_first_save_preserves_the_legacy_merchant_and_no_longer_writes_the_legacy_copy(self):
        before = PlatformConfiguration.objects.get(pk=1).encrypted_zibal_credentials
        pgs.save_gateway("zibal", credentials={"merchant": ""}, sandbox=False, enabled=True)
        creds, _sandbox, source = pgs.credentials_and_mode("zibal")
        self.assertEqual((creds["merchant"], source), (PLATFORM_MERCHANT, "row"))
        legacy = PlatformConfiguration.objects.get(pk=1)
        self.assertEqual(legacy.encrypted_zibal_credentials, before)        # frozen rollback copy: never rewritten, never cleared
        pgs.save_gateway("zibal", credentials={"merchant": "ROW-ONLY-NEW"}, sandbox=False, enabled=True)
        self.assertEqual(PlatformConfiguration.objects.get(pk=1).get_zibal_credentials()["merchant"], PLATFORM_MERCHANT)
        self.assertEqual(pgs.credentials_and_mode("zibal")[0]["merchant"], "ROW-ONLY-NEW")

    def test_upgrade_keeps_the_legacy_subscription_flow_working(self):
        fake = patch_zibal(self)
        _sub, invoice = open_invoice_for(Store.objects.create(name="legacy", slug="legacy-zibal", admin_subdomain="legacy-zibal"), code="legacy")
        from apps.billing.services import payment_flow_service

        attempt, session = payment_flow_service.start_payment(invoice, callback_base_url="https://rastisi.test")
        self.assertEqual(fake.calls_to("request")[0]["merchant"], PLATFORM_MERCHANT)
        self.assertEqual(session.redirect_url, "https://gateway.zibal.ir/start/777")


@override_settings(RASTISI_PLATFORM_PRIMARY_HOST="rastisi.ir")
class CredentialIsolationTests(TestCase):
    """A platform purchase must never use a store's merchant; a store order must never use the platform's."""

    def setUp(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.store = Store.objects.create(name="فروشگاه جدا", slug="iso-store", admin_subdomain="iso-store")
        for code, creds in (("zibal", {"merchant": STORE_MERCHANT}), ("zarinpal", {"merchant_id": ZARINPAL_STORE})):
            config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code=code, is_active=True)
            config.set_credentials(creds)
            config.save()
        self.store_snapshot = {
            c.gateway_code: c.encrypted_credentials for c in PaymentGatewayConfig.objects.filter(store=self.store)
        }

    def test_platform_zibal_request_uses_only_the_platform_merchant(self):
        fake = patch_zibal(self)
        ready_platform_zibal(self)
        from apps.billing.services import payment_flow_service

        _sub, invoice = open_invoice_for(self.store, code="iso1")
        payment_flow_service.start_payment(invoice, callback_base_url="https://rastisi.test")
        sent = fake.calls_to("request")[0]
        self.assertEqual(sent["merchant"], PLATFORM_MERCHANT)
        self.assertNotEqual(sent["merchant"], STORE_MERCHANT)

    def test_platform_zarinpal_request_uses_only_the_platform_merchant(self):
        fake = patch_zarinpal(self)
        ready_platform_zarinpal(self, default=True)
        from apps.billing.services import payment_flow_service

        _sub, invoice = open_invoice_for(self.store, code="iso2")
        payment_flow_service.start_payment(invoice, callback_base_url="https://rastisi.test")
        sent = fake.calls[0][1]
        self.assertEqual(sent["merchant_id"], ZARINPAL_PLATFORM)
        self.assertNotEqual(sent["merchant_id"], ZARINPAL_STORE)

    def test_store_gateway_rows_are_untouched_by_every_platform_operation(self):
        patch_zibal(self)
        ready_platform_zibal(self)
        pgs.save_gateway("zibal", credentials={"merchant": "ANOTHER"}, sandbox=True, enabled=False)
        pgs.set_default("manual")
        after = {c.gateway_code: c.encrypted_credentials for c in PaymentGatewayConfig.objects.filter(store=self.store)}
        self.assertEqual(after, self.store_snapshot)
        self.assertEqual(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zibal").get_credentials()["merchant"], STORE_MERCHANT)

    def test_platform_gateways_do_not_enable_or_change_the_store_checkout(self):
        from apps.orders.models import PaymentGateway
        from apps.orders.services.checkout_service import active_payment_gateways

        PaymentGateway.objects.create(store=self.store, name="زیبال", slug="zibal", is_active=True)
        before = [(g.slug, g.name) for g in active_payment_gateways(store=self.store)]
        ready_platform_zibal(self)
        ready_platform_zarinpal(self)
        pgs.save_gateway("zibal", credentials={"merchant": "X"}, sandbox=False, enabled=False)
        after = [(g.slug, g.name) for g in active_payment_gateways(store=self.store)]
        self.assertEqual(before, after)                 # platform readiness never adds/removes a store's methods
        self.assertIn("zibal", [slug for slug, _name in after])
        other = Store.objects.create(name="دیگر", slug="iso-other", admin_subdomain="iso-other")
        self.assertEqual(list(active_payment_gateways(store=other)), [])   # nor does it create methods for other stores

    def test_source_level_guard_keeps_the_two_contexts_apart(self):
        """AST-level (docstrings may mention the names): platform code never touches store gateway configs, and the
        store payment engine never touches platform credentials."""
        import ast

        root = Path(__file__).resolve().parents[3]

        def referenced_names(path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
                elif isinstance(node, ast.alias):
                    names.add(node.name.rsplit(".", 1)[-1])
            return names

        platform_files = [
            *root.joinpath("apps/billing").rglob("*.py"), root / "apps/portal/services/platform_gateway_service.py",
        ]
        for path in platform_files:
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            self.assertNotIn("PaymentGatewayConfig", referenced_names(path), f"{path} must not read store gateway configs")
        forbidden = {"platform_gateway_service", "PlatformGatewayConfig", "credentials_and_mode", "get_zibal_credentials"}
        offenders = [
            str(path) for path in root.joinpath("apps/orders").rglob("*.py")
            if "tests" not in path.parts and "migrations" not in path.parts and referenced_names(path) & forbidden
        ]
        self.assertEqual(offenders, [], "store payment code must never read platform credentials")
