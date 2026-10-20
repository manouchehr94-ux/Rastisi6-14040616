"""FOLLOWUP-10 — the trust row must never promise payment/shipping/pickup/guarantees the store cannot back up."""

import re

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import PaymentGateway, ShippingMethod
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import section_structure_service, trust_claims
from apps.storefront_builder.services.render_service import _trust_features_context
from apps.stores.models import Store, StoreDomain

HOST = "followup10.example.com"
OWNER_ITEMS = [  # the five items reported by the owner (Template 51 default content)
    {"icon": "↙", "title": "تضمین بهترین قیمت", "subtitle": "خرید مطمئن"},
    {"icon": "◎", "title": "ضمانت اصالت کالا", "subtitle": "کالای اصل"},
    {"icon": "▣", "title": "پرداخت امن", "subtitle": "درگاه و کارت"},
    {"icon": "⌂", "title": "تحویل حضوری", "subtitle": "دریافت آسان"},
    {"icon": "⇢", "title": "ارسال سریع", "subtitle": "به سراسر کشور"},
]


def _titles(items, key="public_visible"):
    return [i["title"] for i in items if i[key]]


class ClaimResolutionTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        self.other = Store.objects.create(name="B", slug="f10-other")

    def _gateway(self, store=None, active=True):
        return PaymentGateway.objects.create(store=store or self.store, name="درگاه", slug="gw", is_active=active)

    def _method(self, method_type=ShippingMethod.MethodType.FLAT_RATE, active=True, store=None):
        return ShippingMethod.objects.create(
            store=store or self.store, name="روش", slug=f"m-{method_type}", method_type=method_type, is_active=active,
        )

    def test_nothing_is_promised_without_real_state(self):
        items = trust_claims.resolve_items(self.store, {"items": OWNER_ITEMS})
        self.assertEqual(_titles(items), [])
        reasons = {i["title"]: i["hidden_reason"] for i in items}
        self.assertIn("درگاه", reasons["پرداخت امن"])
        self.assertIn("ارسال", reasons["ارسال سریع"])
        self.assertIn("تحویل حضوری", reasons["تحویل حضوری"])
        self.assertIn("تأیید", reasons["ضمانت اصالت کالا"])
        self.assertIn("تأیید", reasons["تضمین بهترین قیمت"])
        self.assertEqual(len(items), 5, "nothing is deleted from the data, only hidden from the public output")

    def test_each_claim_follows_its_own_real_capability(self):
        self._gateway()
        self.assertEqual(_titles(trust_claims.resolve_items(self.store, {"items": OWNER_ITEMS})), ["پرداخت امن"])
        self._method()
        self.assertEqual(_titles(trust_claims.resolve_items(self.store, {"items": OWNER_ITEMS})), ["پرداخت امن", "ارسال سریع"])
        self._method(ShippingMethod.MethodType.LOCAL_PICKUP)
        self.assertEqual(
            _titles(trust_claims.resolve_items(self.store, {"items": OWNER_ITEMS})),
            ["پرداخت امن", "تحویل حضوری", "ارسال سریع"],
        )

    def test_inactive_and_other_store_capabilities_do_not_count(self):
        self._gateway(active=False)
        self._method(active=False)
        self._gateway(store=self.other)
        self._method(store=self.other)
        self.assertEqual(_titles(trust_claims.resolve_items(self.store, {"items": OWNER_ITEMS})), [])

    def test_merchant_verification_publishes_non_operational_claims_only(self):
        items = [dict(OWNER_ITEMS[1], verified=True), dict(OWNER_ITEMS[2], verified=True)]  # «verified» cannot fake a payment gateway
        resolved = trust_claims.resolve_items(self.store, {"items": items})
        self.assertEqual(_titles(resolved), ["ضمانت اصالت کالا"])

    def test_explicit_claim_overrides_title_guessing(self):
        item = {"icon": "x", "title": "خرید راحت", "subtitle": "", "claim": "payment"}
        self.assertEqual(_titles(trust_claims.resolve_items(self.store, {"items": [item]})), [])
        self._gateway()
        self.assertEqual(_titles(trust_claims.resolve_items(self.store, {"items": [item]})), ["خرید راحت"])

    def test_empty_items_use_the_legacy_defaults_but_they_are_gated_too(self):
        resolved = trust_claims.resolve_items(self.store, {})
        self.assertEqual(len(resolved), 4)
        self.assertEqual(_titles(resolved), [])


class ValidatorAndSchemaTests(TestCase):
    def test_validator_keeps_claim_and_verified_and_drops_junk(self):
        cleaned = section_registry.validate_trust_features_settings({"items": [
            {"title": "a", "claim": "pickup", "verified": True},
            {"title": "b", "claim": "evil", "verified": "on"},
            {"title": "c"},
        ]})["items"]
        self.assertEqual(cleaned[0], {"icon": "", "title": "a", "subtitle": "", "claim": "pickup", "verified": True})
        self.assertEqual(cleaned[1], {"icon": "", "title": "b", "subtitle": "", "verified": True})
        self.assertEqual(cleaned[2], {"icon": "", "title": "c", "subtitle": ""})

    def test_each_item_is_independently_editable_in_the_inspector_schema(self):
        field = {f.key: f for f in section_registry.TRUST_FEATURES_SCHEMA.fields}["items"]
        self.assertEqual([f.key for f in field.repeater_item_fields], ["icon", "title", "subtitle", "claim", "verified"])


class TemplateRenderTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    class _Section:
        def __init__(self, settings):
            self.settings = settings

    def _ctx(self, settings):
        return _trust_features_context(self.store, self._Section(settings))

    def test_public_render_has_no_box_when_nothing_is_backed(self):
        html = render_to_string("storefront_builder/sections/trust_features.html", self._ctx({"items": OWNER_ITEMS}))
        self.assertNotIn("features", html)
        self.assertNotIn("پرداخت امن", html)

    def test_preview_shows_everything_with_a_reason_badge(self):
        ctx = {**self._ctx({"items": OWNER_ITEMS}), "is_builder_preview": True}
        html = render_to_string("storefront_builder/sections/trust_features.html", ctx)
        self.assertEqual(html.count("data-trust-badge"), 5)
        self.assertIn("در فروشگاه عمومی نمایش داده نمی‌شود", html)
        self.assertIn("پرداخت امن", html)

    def test_public_render_lists_only_backed_items(self):
        PaymentGateway.objects.create(store=self.store, name="درگاه", slug="g1", is_active=True)
        html = render_to_string("storefront_builder/sections/trust_features.html", self._ctx({"items": OWNER_ITEMS}))
        self.assertIn("پرداخت امن", html)
        for text in ("تحویل حضوری", "ارسال سریع", "ضمانت اصالت کالا", "تضمین بهترین قیمت"):
            self.assertNotIn(text, html)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PublishedPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        StoreDomain.objects.create(
            store=self.store, hostname=HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
        )
        draft = svc.get_or_create_draft(self.store)
        section = section_structure_service.add_section(
            draft=draft, section_key="trust_features", page_type=StorefrontPage.PageType.CART,
        )
        section.settings = {**section.settings, "items": OWNER_ITEMS}
        section.save(update_fields=["settings"])
        svc.publish(self.store)

    def test_published_page_makes_no_unbacked_promise_and_follows_real_state(self):
        def feats():
            html = self.client.get(reverse("cart:detail"), HTTP_HOST=HOST).content.decode()
            return html, re.findall(r'<div class="feat"[^>]*>.*?<b>(.*?)</b>', html)

        html, titles = feats()
        self.assertEqual(titles, [])
        self.assertNotIn('class="features"', html)
        PaymentGateway.objects.create(store=self.store, name="درگاه", slug="g2", is_active=True)
        self.assertEqual(feats()[1], ["پرداخت امن"])


class FixedStorefrontBlocksTests(TestCase):
    """The fixed (non-editable) PDP strip / footer blocks follow the same rule: no payment/shipping promise without the real service."""

    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")

    def test_service_claims_tag_reads_the_real_state_per_store(self):
        from django.template import Context, Template
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.store = self.store
        render = lambda: Template("{% load storefront_builder_extras %}{% service_claims as c %}{{ c.payment }}|{{ c.shipping }}|{{ c.pickup }}").render(
            Context({"request": request}))
        self.assertEqual(render(), "False|False|False")
        request._service_claims_cache = None
        ShippingMethod.objects.create(store=self.store, name="پست", slug="fx-post", is_active=True)
        self.assertEqual(render(), "False|True|False")
        request._service_claims_cache = None
        PaymentGateway.objects.create(store=self.store, name="درگاه", slug="fx-gw", is_active=True)
        self.assertEqual(render(), "True|True|False")

    def test_no_request_or_store_means_nothing_is_claimed(self):
        from django.template import Context, Template

        out = Template("{% load storefront_builder_extras %}{% service_claims as c %}{{ c.payment }}{{ c.shipping }}").render(Context({}))
        self.assertEqual(out, "FalseFalse")

    def test_templates_no_longer_hard_code_unverified_promises(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "templates/storefront_builder"
        for rel in ("sections/product_main.html", "partials/global_footer/promo_columns.html"):
            text = (root / rel).read_text(encoding="utf-8")
            body = "\n".join(line for line in text.splitlines() if "comment" not in line)
            for promise in ("<span>ضمانت اصالت کالا</span>", "۷ روز ضمانت بازگشت</div>", "<span>۷ روز ضمانت بازگشت کالا</span>", "ارسال سریع و بیمه‌شده</div>", "ارسال سریع و بیمه‌شده</span>"):
                self.assertNotIn(promise, body, f"{rel}: {promise}")
