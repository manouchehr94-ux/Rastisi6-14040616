"""Phase 5 Task 5 (PDTX) — the Draft-aware canonical owner gate for
product-detail-page trust/guarantee content.

PDTX is a GATE, not a free-build: before any trust/guarantee content on the
PDP may be made merchant-editable, there MUST already exist a canonical
settings owner that flows through the storefront Draft → validate → publish
→ render lifecycle. Creating a NEW model / NEW schema for this is forbidden.

This module is the permanent proof that such an owner exists and is the
``trust_features`` section:

  * it carries a real validating settings schema (NOT a passthrough / NOT
    an immediate-live singleton like ``ShopSettings``),
  * it is allowed on the ``product_detail`` page (inherits ALL_PAGE_TYPES),
  * its ``items`` survive the full draft → validate → publish → render chain
    on a product_detail page.

If this contract ever regresses (trust_features loses its schema, or stops
being allowed on the PDP), PDTX would once again require an architectural
decision — so these tests fail loudly to force that conversation.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.core.models import ShopSettings
from apps.storefront_builder import section_registry
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import section_structure_service
from apps.stores.models import Store, StoreDomain

HOST = "pdtx-gate.example.com"


def _akhlaghi() -> Store:
    return Store.objects.get(slug="akhlaghi")


class PdpTrustOwnerIsDraftAwareTests(TestCase):
    """The gate proper — is there a Draft-aware canonical owner at all?"""

    def test_trust_features_is_a_real_settings_owner_not_a_passthrough(self):
        definition = section_registry.get_definition("trust_features")
        # A real, editable settings owner (has a form + a schema), unlike the
        # deliberately setting-less context-aware ``product_main``.
        self.assertTrue(definition.has_settings_form)
        self.assertIsNotNone(definition.settings_schema)
        # The registry decorates validators (spacing/responsive wrappers), so
        # assert behaviour, not object identity: the definition's validator
        # enforces the trust-item business rule (blank title rejected).
        with self.assertRaises(section_registry.TrustFeaturesSettingsError):
            definition.validate_settings({"items": [{"title": "  "}]})

    def test_trust_features_validator_cleans_items_through_the_schema(self):
        cleaned = section_registry.validate_trust_features_settings(
            {"items": [{"icon": "🚚", "title": "ارسال سریع", "subtitle": "سراسر کشور"}]}
        )
        self.assertEqual(
            cleaned,
            {"items": [{"icon": "🚚", "title": "ارسال سریع", "subtitle": "سراسر کشور"}]},
        )

    def test_trust_features_is_allowed_on_the_product_detail_page(self):
        self.assertTrue(
            section_registry.is_section_allowed_on_page(
                "trust_features", StorefrontPage.PageType.PRODUCT_DETAIL
            )
        )

    def test_shop_settings_is_not_the_draft_aware_owner(self):
        # ShopSettings.free_shipping_threshold is immediate-live business
        # config (no draft/publish) — it is explicitly NOT acceptable as the
        # PDP trust owner. It carries no storefront draft/version linkage.
        field_names = {f.name for f in ShopSettings._meta.get_fields()}
        self.assertIn("free_shipping_threshold", field_names)
        self.assertNotIn("draft", field_names)
        self.assertNotIn("version", field_names)


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class TrustContentSurvivesTheDraftLifecycleOnPdpTests(TestCase):
    """End-to-end: trust settings placed on the PDP draft survive
    validate → publish → public render — no new model, no new endpoint."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname=HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="pdtx-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="pdtx-category")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالای اعتماد", slug="pdtx-product", sku="PDTX-1",
            price=Decimal("300000"), stock=5, status=Product.Status.ACTIVE,
        )
        self.draft = svc.get_or_create_draft(self.store)

    def test_trust_items_edited_on_pdp_draft_render_on_the_public_product_page(self):
        section = section_structure_service.add_section(
            draft=self.draft,
            section_key="trust_features",
            page_type=StorefrontPage.PageType.PRODUCT_DETAIL,
        )
        # A merchant edits the trust rows (through the canonical validator).
        section.settings = section_registry.validate_trust_features_settings(
            {"items": [
                {"icon": "🛡️", "title": "ضمانت اصالت کالای پی‌دی‌تی‌ایکس", "subtitle": "اورجینال"},
            ]}
        )
        section.save(update_fields=["settings"])
        svc.publish(self.store)

        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product.slug]),
            HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # The draft-owned, published trust content is on the live PDP.
        self.assertIn("ضمانت اصالت کالای پی‌دی‌تی‌ایکس", html)

    def test_unpublished_draft_edits_do_not_leak_to_the_public_pdp(self):
        section = section_structure_service.add_section(
            draft=self.draft,
            section_key="trust_features",
            page_type=StorefrontPage.PageType.PRODUCT_DETAIL,
        )
        section.settings = section_registry.validate_trust_features_settings(
            {"items": [{"icon": "🚫", "title": "پیش‌نویسِ منتشرنشده", "subtitle": ""}]}
        )
        section.save(update_fields=["settings"])
        # NOTE: no publish() — the edit stays in the draft only.

        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product.slug]),
            HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("پیش‌نویسِ منتشرنشده", response.content.decode())
