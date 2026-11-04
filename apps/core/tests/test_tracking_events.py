"""Canonical e-commerce tracking events: server-resolved money (Toman → IRR via apps.core.currency), no PII, tenant isolation, emission only at real events, nothing on previews or
when tracking is inactive, and NO Purchase emission anywhere (durable dedupe needs an approved ledger table)."""

import json
import re
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant, Vendor
from apps.core import tracking_events
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain, StoreIntegrationConnection

HOST_A = "shop-a.brand-example.ir"
HOST_B = "shop-b.brand-example.ir"
SUFFIX = "panel.brand-example.ir"
EVENTS_RE = re.compile(r'<script id="rs-track-events" type="application/json">(.*?)</script>', re.S)


def connect(store, ga4):
    conn = StoreIntegrationConnection.objects.create(store=store, provider_code="google_analytics", is_active=True)
    conn.set_credentials({"measurement_id": ga4})
    conn.save()


def make_store(slug, host, ga4=None):
    store = Store.objects.get(slug="akhlaghi") if slug == "akhlaghi" else Store.objects.create(name=slug, slug=slug, status=Store.Status.ACTIVE, admin_subdomain=slug[:6])
    ShopSettings.provision_for(store) if slug != "akhlaghi" else None
    StoreDomain.objects.create(store=store, hostname=host, is_primary=True, domain_type=StoreDomain.DomainType.CUSTOM_DOMAIN,
                               verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
    if ga4:
        connect(store, ga4)
    vendor = Vendor.objects.create(store=store, name=f"v-{slug}", slug=f"v-{slug}")
    cat = Category.objects.create(store=store, name="c", slug=f"c-{slug}")
    product = Product.objects.create(store=store, vendor=vendor, category=cat, name=f"کالا {slug}", slug=f"p-{slug}", sku=f"SKU-{slug}", price=Decimal("125000"), stock=10)
    return store, product


def events_in(response):
    match = EVENTS_RE.search(response.content.decode())
    return json.loads(match.group(1)) if match else []


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"], RASTISI_ADMIN_DOMAIN_SUFFIX=SUFFIX, RASTISI_STOREFRONT_TRACKING_ENABLED=True)
class TrackingEventsBase(TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch("apps.stores.services.publication_service.is_publicly_visible", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.a, self.pa = make_store("akhlaghi", HOST_A, "G-AAAA1111")
        self.b, self.pb = make_store("evt-b", HOST_B, "G-BBBB2222")
        self.client_a = Client(HTTP_HOST=HOST_A)
        self.client_b = Client(HTTP_HOST=HOST_B)


class BuilderTests(TrackingEventsBase):
    def test_amounts_are_server_resolved_toman_converted_to_iso_irr(self):
        event = tracking_events.build_view_item(self.a, self.pa)
        self.assertEqual((event["name"], event["currency"], event["value"]), ("view_item", "IRR", 1250000))
        self.assertEqual(event["items"], [{"item_id": "SKU-akhlaghi", "item_name": self.pa.name, "price": 1250000, "quantity": 1}])

    def test_variant_is_reported_and_must_belong_to_the_product(self):
        variant = ProductVariant.objects.create(product=self.pa, attribute="رنگ", value="سرخ", sku="V-RED", price=Decimal("130000"), stock=3)
        self.assertEqual(tracking_events.build_view_item(self.a, self.pa, variant)["items"][0]["item_variant"], "V-RED")
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_view_item(self.a, self.pa, ProductVariant.objects.create(product=self.pb, attribute="x", value="y", sku="V-OTHER", price=Decimal("1"), stock=1))

    def test_a_product_of_another_store_is_refused(self):
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_view_item(self.a, self.pb)

    def test_unknown_source_currency_is_refused_not_guessed(self):
        for bad in ("USD", "EUR", "", None):
            with self.assertRaises(tracking_events.TrackingEventError):
                tracking_events.iso_amount(1000, bad)
        self.assertEqual(tracking_events.iso_amount(1000, "IRT"), 10000)
        self.assertEqual(tracking_events.iso_amount(Decimal("1000"), "TOMAN"), 10000)
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.iso_amount(-1)

    def test_add_to_cart_uses_the_quantity_added_and_the_given_server_price(self):
        event = tracking_events.build_add_to_cart(self.a, self.pa, None, 3, Decimal("125000"))
        self.assertEqual((event["value"], event["items"][0]["quantity"]), (3750000, 3))
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_add_to_cart(self.a, self.pa, None, 0, Decimal("125000"))

    def test_events_carry_no_personal_data_keys(self):
        event = tracking_events.build_view_item(self.a, self.pa)
        flat = json.dumps(event)
        for forbidden in ("email", "phone", "mobile", "name_first", "address", "user", "customer", "ip", "session"):
            self.assertNotIn(f'"{forbidden}"', flat)
        self.assertLessEqual(set(event), {"name", "id", "currency", "value", "items", "once"})

    def test_purchase_builder_refuses_unpaid_cross_store_and_non_gateway_orders(self):
        from apps.orders.models import Order

        order = Order(store=self.a, payment_status=Order.PaymentStatus.PENDING, code="X1")
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_purchase(self.a, order)
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_purchase(self.b, order)
        order.payment_status = Order.PaymentStatus.PAID                # paid but unsaved → no verified gateway transaction
        order.store_id = self.b.pk
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_purchase(self.a, order)


class ViewItemTests(TrackingEventsBase):
    def test_product_page_prints_one_view_item_for_its_own_store(self):
        events = events_in(self.client_a.get(f"/products/{self.pa.slug}/"))
        self.assertEqual([e["name"] for e in events], ["view_item"])
        self.assertEqual(events[0]["items"][0]["item_id"], "SKU-akhlaghi")
        self.assertEqual(events[0]["value"], 1250000)

    def test_a_product_of_another_store_is_404_and_prints_nothing(self):
        response = self.client_b.get(f"/products/{self.pa.slug}/")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("SKU-akhlaghi", response.content.decode())

    def test_each_store_only_ever_sees_its_own_item(self):
        self.assertEqual(events_in(self.client_b.get(f"/products/{self.pb.slug}/"))[0]["items"][0]["item_id"], "SKU-evt-b")

    @override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=False)
    def test_nothing_when_the_platform_switch_is_off(self):
        html = self.client_a.get(f"/products/{self.pa.slug}/").content.decode()
        self.assertNotIn("rs-track-events", html)
        self.assertNotIn("rs-consent-config", html)

    def test_nothing_when_the_store_has_no_provider(self):
        StoreIntegrationConnection.objects.filter(store=self.a).delete()
        html = self.client_a.get(f"/products/{self.pa.slug}/").content.decode()
        self.assertNotIn("rs-track-events", html)

    def test_listing_and_home_do_not_emit_view_item(self):
        for path in ("/", "/products/"):
            self.assertEqual(events_in(self.client_a.get(path)), [], path)


class AddToCartTests(TrackingEventsBase):
    def post(self, client, product, **data):
        return client.post(f"/cart/add/{product.slug}/", {"quantity": "2", **data}, HTTP_HX_REQUEST="true")

    def trigger(self, response):
        return json.loads(response["HX-Trigger"]) if response.has_header("HX-Trigger") else {}

    def test_success_adds_one_event_alongside_the_existing_toast(self):
        trig = self.trigger(self.post(self.client_a, self.pa))
        self.assertIn("toast", trig)
        self.assertEqual(trig["rsTrack"]["name"], "add_to_cart")
        self.assertEqual((trig["rsTrack"]["value"], trig["rsTrack"]["items"][0]["quantity"]), (2500000, 2))

    def test_price_comes_from_the_server_never_from_post(self):
        trig = self.trigger(self.post(self.client_a, self.pa, price="1", unit_price="1", value="1", currency="USD"))
        self.assertEqual(trig["rsTrack"]["items"][0]["price"], 1250000)
        self.assertEqual(trig["rsTrack"]["currency"], "IRR")

    def test_failed_adds_never_emit(self):
        for data in ({"quantity": "abc"}, {"quantity": "0"}, {"quantity": "-3"}, {"quantity": "999"}):
            response = self.post(self.client_a, self.pa, **data)
            self.assertNotIn("rsTrack", self.trigger(response), data)
        self.assertFalse(CartItem.objects.filter(product=self.pa).exists())

    def test_unknown_product_or_other_store_product_emits_nothing(self):
        response = self.post(self.client_b, self.pa)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("rsTrack", self.trigger(response))

    def test_inactive_tracking_leaves_the_response_exactly_as_before(self):
        StoreIntegrationConnection.objects.filter(store=self.a).delete()
        self.assertEqual(list(self.trigger(self.post(self.client_a, self.pa))), ["toast"])

    @override_settings(RASTISI_STOREFRONT_TRACKING_ENABLED=False)
    def test_platform_switch_off_emits_nothing(self):
        self.assertEqual(list(self.trigger(self.post(self.client_a, self.pa))), ["toast"])


class BeginCheckoutTests(TrackingEventsBase):
    def fill(self, client, product=None, qty=2):
        client.post(f"/cart/add/{(product or self.pa).slug}/", {"quantity": str(qty)}, HTTP_HX_REQUEST="true")

    def test_checkout_entry_emits_begin_checkout_with_the_cart_lines(self):
        self.fill(self.client_a)
        events = events_in(self.client_a.get("/checkout/"))
        self.assertEqual([e["name"] for e in events], ["begin_checkout"])
        self.assertEqual((events[0]["value"], events[0]["items"][0]["quantity"], events[0]["once"]), (2500000, 2, True))

    def test_refreshing_the_same_checkout_keeps_the_same_identity(self):
        self.fill(self.client_a)
        first = events_in(self.client_a.get("/checkout/"))[0]["id"]
        self.assertEqual(events_in(self.client_a.get("/checkout/"))[0]["id"], first)

    def test_an_empty_cart_emits_nothing(self):
        self.assertEqual(events_in(self.client_a.get("/checkout/")), [])

    def test_other_store_items_in_the_cart_are_never_reported(self):
        cart = Cart.objects.create(session_key="x" * 32)
        CartItem.objects.create(cart=cart, product=self.pb, quantity=1, unit_price=Decimal("125000"))
        self.assertIsNone(tracking_events.build_begin_checkout(self.a, cart))

    def test_inactive_tracking_prints_nothing_on_checkout(self):
        self.fill(self.client_a)
        StoreIntegrationConnection.objects.filter(store=self.a).delete()
        self.assertNotIn("rs-track-events", self.client_a.get("/checkout/").content.decode())


class NoPurchaseEmissionTests(TrackingEventsBase):
    def test_nothing_in_the_storefront_code_queues_or_prints_a_purchase(self):
        import ast
        import pathlib

        offenders = []
        for path in pathlib.Path("apps").rglob("*.py"):
            if "tests" in path.parts or path.name == "tracking_events.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "build_purchase":
                    offenders.append(str(path))
        self.assertEqual(offenders, [], "build_purchase must stay unwired until a durable TrackingEmission ledger is approved")


class ConsentJsDispatchContractTests(TestCase):
    """The browser behaviour is exercised in Chromium with mocked providers (apps/core/tests/browser/tracking_dispatch_qa.js); these pin the source-level invariants."""

    JS = (__import__("pathlib").Path(__file__).resolve().parents[1] / "static" / "core" / "consent.js").read_text(encoding="utf-8")

    def test_only_the_three_non_financial_events_are_dispatchable(self):
        self.assertIn("var EVENTS = { view_item: 'ViewContent', add_to_cart: 'AddToCart', begin_checkout: 'InitiateCheckout' }", self.JS)
        self.assertNotIn("Purchase", self.JS)

    def test_events_are_validated_listened_for_through_htmx_and_never_queued_or_replayed(self):
        self.assertIn("document.addEventListener('rsTrack'", self.JS)
        self.assertIn("function cleanEvent", self.JS)
        self.assertIn("never queued", self.JS)
        self.assertNotIn("sessionStorage", self.JS)
        for forbidden in ("setTimeout", "setInterval", "pendingEvents", "replay("):
            self.assertNotIn(forbidden, self.JS)

    def test_ga4_direct_is_suppressed_when_gtm_serves_it_and_meta_gets_an_event_id(self):
        self.assertIn("else if (!ids.gtm && allowed('ga4'))", self.JS)
        self.assertIn("{ eventID: ev.id }", self.JS)

    def test_gpc_overrides_a_stored_marketing_grant(self):
        self.assertIn("if (gpc) c.m = 0", self.JS)


class ReviewFindingsTests(TrackingEventsBase):
    def test_a_zero_priced_product_reports_no_event(self):
        Product.objects.filter(pk=self.pa.pk).update(price=Decimal("0"))
        self.assertEqual(events_in(self.client_a.get(f"/products/{self.pa.slug}/")), [])
        with self.assertRaises(tracking_events.TrackingEventError):
            tracking_events.build_add_to_cart(self.a, self.pa, None, 1, Decimal("0"))

    def test_the_hx_trigger_header_is_ascii_safe_and_keeps_the_toast_consumer_contract(self):
        response = self.client_a.post(f"/cart/add/{self.pa.slug}/", {"quantity": "1"}, HTTP_HX_REQUEST="true")
        raw = response["HX-Trigger"]
        raw.encode("ascii")                                    # Persian product names must be \u-escaped, never raw bytes in a header
        trigger = json.loads(raw)
        self.assertEqual(trigger["toast"]["type"], "ok")
        self.assertIn(self.pa.name, trigger["toast"]["message"])
        self.assertEqual(set(trigger), {"toast", "rsTrack"})

    def test_a_non_htmx_post_still_works_and_cart_state_is_unchanged_by_tracking(self):
        response = self.client_a.post(f"/cart/add/{self.pa.slug}/", {"quantity": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.get(product=self.pa).quantity, 2)
