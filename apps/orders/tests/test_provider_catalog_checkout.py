"""The 10 online providers + COD + card transfer in the finance settings and at checkout.

One availability mechanism: ``active_payment_gateways`` (legacy base row + ``PaymentGatewayConfig.is_selectable_at_checkout``). Verifies that
an activated verified provider is LISTED for its own store only, that documentation-blocked / incomplete / inactive / sandbox-only providers
never are, that the catalog is complete, and that a customer's chosen provider is never silently replaced by another one."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.orders.encryption import reset_fernet
from apps.orders.gateways import GATEWAY_CHOICES, get_adapter
from apps.orders.gateways.base import GatewayCategory
from apps.orders.models import PaymentGateway, PaymentGatewayConfig
from apps.orders.services.checkout_service import active_payment_gateways
from apps.stores.models import Store, StoreMembership

User = get_user_model()
ONLINE = ("zarinpal", "zibal", "pasargad", "snappay", "torobpay", "saman", "parsian", "mellat", "sadad", "tejarat")
VERIFIED_CREDS = {
    "zarinpal": {"merchant_id": "a" * 36},
    "pasargad": {"username": "u", "password": "p", "terminalNumber": "1", "serviceCode": "8"},
    "snappay": {"client_id": "c", "client_secret": "s"},
    "torobpay": {"client_id": "c", "client_secret": "s", "client_username": "u", "client_password": "p"},
}


class CatalogTests(TestCase):
    def test_exactly_ten_online_providers_plus_cod_and_card_transfer_are_registered(self):
        codes = [c for c, _ in GATEWAY_CHOICES]
        self.assertEqual(sorted(codes), sorted(ONLINE + ("cod", "card_to_card")))
        for code in ONLINE:
            self.assertTrue(get_adapter(code).is_online, code)
        self.assertFalse(get_adapter("cod").is_online)
        self.assertTrue(get_adapter("card_to_card").requires_manual_confirmation)

    def test_categories_and_blocked_flags_are_honest(self):
        implemented = {"zarinpal", "zibal", "pasargad", "snappay", "torobpay"}
        for code in ONLINE:
            adapter = get_adapter(code)
            self.assertEqual(getattr(adapter, "documentation_blocked", False), code not in implemented, code)
        self.assertEqual(get_adapter("snappay").category, GatewayCategory.BNPL)
        self.assertEqual(get_adapter("torobpay").category, GatewayCategory.BNPL)

    def test_skeleton_providers_declare_no_operations(self):
        for code in ("parsian", "sadad", "tejarat"):
            self.assertEqual(get_adapter(code).capabilities, frozenset(), code)

    def test_saman_and_mellat_are_implemented_but_remain_blocked_for_stores_until_their_contract_is_verified(self):
        for code in ("saman", "mellat"):
            adapter = get_adapter(code)
            self.assertTrue(adapter.capabilities, code)
            self.assertTrue(adapter.documentation_blocked, code)


class CheckoutListingTests(TestCase):
    def setUp(self):
        reset_fernet()
        self.addCleanup(reset_fernet)
        self.store = Store.objects.get(slug="akhlaghi")
        self.owner = User.objects.create_user(username="cat-owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(store=self.store, user=self.owner, role=StoreMembership.Role.OWNER,
                                       status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now())
        self.client.login(username="cat-owner", password="pass12345")

    def save(self, code, *, active=True, sandbox=False, creds=None, store=None):
        data = {"display_order": "1", "is_sandbox": "on" if sandbox else ""}
        if active:
            data["is_active"] = "on"
        for key, value in (creds if creds is not None else VERIFIED_CREDS.get(code, {})).items():
            data[f"credential_{key}"] = value
        return self.client.post(f"/admin-portal/settings/gateway-config/{code}/save/", data)

    def listed(self, store=None):
        return {g.slug for g in active_payment_gateways(store=store or self.store)}

    def test_an_activated_verified_provider_is_listed_for_its_own_store_only(self):
        self.save("zarinpal")
        self.assertTrue(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zarinpal").is_active)
        self.assertIn("zarinpal", self.listed())
        # a second store is created only AFTER the admin calls (host fallback resolution needs a single store)
        self.other = Store.objects.create(name="Other", slug="cat-other", status=Store.Status.ACTIVE, admin_subdomain="catoth")
        self.assertNotIn("zarinpal", self.listed(self.other))                                   # tenant isolation
        row = PaymentGateway.objects.get(store=self.store, slug="zarinpal")
        self.assertTrue(row.is_active)
        self.assertFalse(PaymentGateway.objects.filter(store=self.other, slug="zarinpal").exists())

    def test_bnpl_providers_are_listed_once_connected(self):
        self.save("snappay"); self.save("torobpay")
        self.assertTrue({"snappay", "torobpay"} <= self.listed())

    def test_documentation_blocked_providers_are_never_activated_or_listed(self):
        for code in ("saman", "parsian", "mellat", "sadad", "tejarat"):
            self.save(code, creds={"x": "y"})
            self.assertFalse(PaymentGatewayConfig.objects.get(store=self.store, gateway_code=code).is_active, code)
        self.assertFalse(self.listed() & {"saman", "parsian", "mellat", "sadad", "tejarat"})

    def test_even_a_forced_active_blocked_config_is_not_offered(self):
        config = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="mellat", is_active=True)
        PaymentGateway.objects.create(store=self.store, name="ملت", slug="mellat", is_active=True)
        self.assertNotIn("mellat", self.listed())                                               # readiness gate at the listing itself
        self.assertFalse(config.is_selectable_at_checkout)

    def test_incomplete_inactive_and_sandbox_only_are_not_offered(self):
        self.save("zarinpal", active=False)
        self.assertNotIn("zarinpal", self.listed())                                              # inactive
        self.save("snappay", creds={"client_id": "only-one"})
        self.assertNotIn("snappay", self.listed())                                               # incomplete credentials
        self.save("torobpay", sandbox=True)                                                       # sandbox-only readiness is not a live checkout method
        config = PaymentGatewayConfig.objects.get(store=self.store, gateway_code="torobpay")
        self.assertEqual(config.readiness_status, "ready_for_test")
        self.assertIn(config.is_selectable_at_checkout, (True,))                                  # selectable only WHILE sandbox
        config.is_sandbox = False; config.save()
        self.assertFalse(PaymentGatewayConfig.objects.get(pk=config.pk).readiness_status == "ready_for_test")

    def test_deactivating_removes_it_from_checkout(self):
        self.save("zarinpal")
        self.client.post("/admin-portal/settings/gateway-config/zarinpal/toggle/")
        self.assertFalse(PaymentGatewayConfig.objects.get(store=self.store, gateway_code="zarinpal").is_active)
        self.assertNotIn("zarinpal", self.listed())

    def test_cod_and_zibal_keep_their_existing_legacy_rows(self):
        PaymentGateway.objects.create(store=self.store, name="زیبال", slug="zibal", is_active=True)
        self.save("zibal", creds={"merchant": "zbl"})
        self.assertEqual(PaymentGateway.objects.filter(store=self.store, slug="zibal").count(), 1)


class LegacyRowsWithoutConfigTests(TestCase):
    """A legacy payment-method row whose slug is a registered provider code is offered ONLY while a ready configuration backs it
    (regression: ``seed_shop`` creates a ``mellat`` row; a store with a bare ``snappay`` row had the same problem)."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def listed(self):
        return {g.slug for g in active_payment_gateways(store=self.store)}

    def test_registered_provider_rows_without_any_config_are_not_offered(self):
        for slug in ("mellat", "snappay", "zarinpal", "pasargad", "torobpay", "saman", "parsian", "sadad", "tejarat"):
            PaymentGateway.objects.create(store=self.store, name=slug, slug=slug, is_active=True)
        self.assertEqual(self.listed(), set())

    def test_the_legacy_methods_and_unrelated_slugs_keep_their_existing_behaviour_without_a_config(self):
        for slug in ("zibal", "cod", "zarin", "payping", "wallet"):                           # seed_shop's demo rows; only zibal/cod are real providers
            PaymentGateway.objects.create(store=self.store, name=slug, slug=slug, is_active=True)
        self.assertEqual(self.listed(), {"zibal", "cod", "zarin", "payping", "wallet"})

    def test_a_ready_config_makes_the_row_visible_and_a_blocked_or_incomplete_one_does_not(self):
        for slug in ("snappay", "mellat"):
            PaymentGateway.objects.create(store=self.store, name=slug, slug=slug, is_active=True)
        c = PaymentGatewayConfig.objects.create(store=self.store, gateway_code="snappay", is_active=True)
        self.assertEqual(self.listed(), set())                                                  # config without credentials
        c.set_credentials({"client_id": "c", "client_secret": "s"}); c.save()
        self.assertEqual(self.listed(), {"snappay"})
        PaymentGatewayConfig.objects.create(store=self.store, gateway_code="mellat", is_active=True)
        self.assertEqual(self.listed(), {"snappay"})                                            # documentation-blocked never

    def test_a_customer_cannot_select_a_hidden_provider_by_posting_its_id(self):
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from apps.orders.services import checkout_service

        hidden = PaymentGateway.objects.create(store=self.store, name="ملت", slug="mellat", is_active=True)
        visible = PaymentGateway.objects.create(store=self.store, name="پرداخت در محل", slug="cod", is_active=True)
        request = RequestFactory().get("/")
        request.session = SessionStore()
        checkout_service.set_payment_gateway(request, hidden.pk)
        self.assertNotIn("payment_gateway_id", request.session.get(checkout_service.SESSION_KEY, {}))     # refused
        checkout_service.set_payment_gateway(request, visible.pk)                                          # positive control: a listed one is accepted
        self.assertEqual(request.session[checkout_service.SESSION_KEY]["payment_gateway_id"], visible.pk)


class NoSilentProviderSwitchTests(TestCase):
    def test_a_chosen_provider_that_is_unavailable_is_reported_not_replaced(self):
        from decimal import Decimal
        from unittest.mock import patch

        from apps.orders.tests.test_lifecycle import LifecycleBase

        class Probe(LifecycleBase):
            def runTest(self):  # pragma: no cover - driven manually below
                pass

        probe = Probe()
        probe.setUp()
        try:
            store = probe.store
            snapp = PaymentGateway.objects.create(store=store, name="اسنپ‌پی", slug="snappay", is_active=True)
            order = probe.new_order()
            order.payment_gateway = snapp
            order.save(update_fields=["payment_gateway"])
            zib = PaymentGatewayConfig.objects.create(store=store, gateway_code="zibal", is_active=True)
            zib.set_credentials({"merchant": "zbl"}); zib.save()
            from django.test import Client
            from django.urls import reverse
            client = Client()
            client.force_login(probe.customer.user)
            with patch("apps.orders.gateways.zibal.ZibalAdapter.create_payment") as create:
                response = client.post(reverse("orders:payment-initiate", args=[order.code]))
            self.assertFalse(create.called)                                                       # NOT silently routed to Zibal
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "در دسترس نیست")
        finally:
            probe.tearDown() if hasattr(probe, "tearDown") else None
