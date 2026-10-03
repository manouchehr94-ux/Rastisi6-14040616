"""Phase 5 Task 5 (PDTX) — the merchant-editable PDP trust/delivery experience.

This is the completion of PDTX (beyond the ownership gate in
``test_pdp_trust_owner_gate.py``). It proves the ACCEPTANCE behaviour:

  1. a merchant can edit PDP trust content through the real R4 mutation path
     (``section.update_settings`` on a product_detail ``trust_features``);
  2. Draft Preview shows the edited content;
  3. the public Published PDP does NOT change before publish;
  4. after publish, the public PDP shows the edited content;
  5. NO Home-page ``trust_features`` is required (the PDP owns its own instance);
  6. unrelated Home ``trust_features`` content never becomes PDP data;
  7. existing stores with NO PDP trust section keep the hard-coded fallback;
  8. no second trust authority/model is introduced (only the guarantee strip
     is suppressed when the canonical section exists — never two at once);
  9. tenant isolation holds (a foreign store's edit never appears on this PDP).

Canonical owner reused: the existing ``trust_features`` section + its schema/
validator, edited via ``r4_mutation_service.apply_mutation`` and published
through the normal Draft lifecycle. No new model, no new endpoint, no new
serializer, no second settings authority.
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import r4_mutation_service
from apps.storefront_builder.services import section_structure_service
from apps.stores.models import Store, StoreDomain, StoreMembership

User = get_user_model()

ADMIN_HOST = "pdtx-edit-admin.rastisi.localhost"
PUBLIC_HOST = "pdtx-edit-public.example.com"

# Marker strings used only in these tests.
_EDITED_TRUST = "ضمانت طلایی پی‌دی‌تی‌ایکس"
_HOME_ONLY_TRUST = "ویژگیِ فقط-صفحه-اصلی"
_HARDCODED_FALLBACK = "ضمانت اصالت کالا"  # the hard-coded guarantee strip


def _akhlaghi() -> Store:
    return Store.objects.get(slug="akhlaghi")


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class PdpTrustIsMerchantEditableTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        self.staff = User.objects.create_user(
            username="pdtx_owner", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="pdtx-e-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="pdtx-e-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالای پی‌دی‌تی‌ایکس", slug="pdtx-e-product", sku="PDTX-E-1",
            price=Decimal("300000"), stock=5, status=Product.Status.ACTIVE,
        )
        self.admin_client = Client(HTTP_HOST=ADMIN_HOST)
        self.admin_client.login(username="pdtx_owner", password="pass12345")
        self.public_client = Client(HTTP_HOST=PUBLIC_HOST)
        self.draft = svc.get_or_create_draft(self.store)

    # ---- helpers -------------------------------------------------------

    def _add_pdp_trust_section(self) -> StorefrontSection:
        return section_structure_service.add_section(
            draft=self.draft,
            section_key="trust_features",
            page_type=StorefrontPage.PageType.PRODUCT_DETAIL,
        )

    def _merchant_edit_trust(self, section, items):
        """Edit trust items through the REAL R4 mutation entry point."""
        self.draft.refresh_from_db()
        return r4_mutation_service.apply_mutation(
            store=self.store,
            actor=self.staff,
            base_revision=self.draft.edit_revision,
            mutation={
                "type": "section.update_settings",
                "section_id": section.pk,
                "patch": {"items": items},
            },
        )

    def _public_pdp(self):
        return self.public_client.get(
            reverse("catalog:product-detail", args=[self.product.slug]),
            HTTP_HOST=PUBLIC_HOST,
        )

    def _preview_pdp(self):
        return self.admin_client.get(
            reverse("dashboard:storefront-builder-preview") + "?page=product_detail",
            HTTP_HOST=ADMIN_HOST,
        )

    # ---- 1. merchant/R4 mutation can edit PDP trust content ------------

    def test_r4_mutation_edits_pdp_trust_items(self):
        section = self._add_pdp_trust_section()
        self._merchant_edit_trust(section, [
            {"icon": "🏅", "title": _EDITED_TRUST, "subtitle": "اصل"},
        ])
        section.refresh_from_db()
        self.assertEqual(
            [i["title"] for i in section.settings["items"]], [_EDITED_TRUST],
        )

    # ---- 2. Draft preview shows edited trust content -------------------

    def test_draft_preview_shows_edited_trust_content(self):
        section = self._add_pdp_trust_section()
        self._merchant_edit_trust(section, [
            {"icon": "🏅", "title": _EDITED_TRUST, "subtitle": "اصل"},
        ])
        resp = self._preview_pdp()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, _EDITED_TRUST)

    # ---- 3 & 4. Published output before/after publish ------------------

    def test_published_output_unchanged_before_publish_then_updates_after(self):
        # A published baseline exists first (so the public storefront resolves).
        svc.publish(self.store)
        baseline = self._public_pdp()
        self.assertEqual(baseline.status_code, 200)
        self.assertNotIn(_EDITED_TRUST, baseline.content.decode())

        # Merchant edits in the DRAFT only — public must not change yet.
        self.draft = svc.get_or_create_draft(self.store)
        section = self._add_pdp_trust_section()
        self._merchant_edit_trust(section, [
            {"icon": "🏅", "title": _EDITED_TRUST, "subtitle": "اصل"},
        ])
        before = self._public_pdp()
        self.assertEqual(before.status_code, 200)
        self.assertNotIn(_EDITED_TRUST, before.content.decode())

        # After publish, the public PDP shows it.
        svc.publish(self.store)
        after = self._public_pdp()
        self.assertEqual(after.status_code, 200)
        self.assertIn(_EDITED_TRUST, after.content.decode())

    # ---- 5. Home-page trust_features is NOT required -------------------

    def test_pdp_trust_does_not_require_a_home_trust_features(self):
        # Remove any default Home trust_features so the ONLY trust_features in
        # play is the PDP's own instance — proving the PDP owns its trust
        # content and does not depend on a Home-page section.
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        home.sections.filter(section_key="trust_features").delete()
        self.assertFalse(
            home.sections.filter(section_key="trust_features").exists(),
        )
        section = self._add_pdp_trust_section()
        self._merchant_edit_trust(section, [
            {"icon": "🏅", "title": _EDITED_TRUST, "subtitle": "اصل"},
        ])
        svc.publish(self.store)
        resp = self._public_pdp()
        self.assertEqual(resp.status_code, 200)
        self.assertIn(_EDITED_TRUST, resp.content.decode())

    # ---- 6. Home trust content does not leak onto the PDP --------------

    def test_home_trust_content_does_not_become_pdp_data(self):
        # A Home trust_features with distinct content (reuse the default Home
        # instance if present — max_instances=1 — else create one).
        home = self.draft.get_page(StorefrontPage.PageType.HOME)
        home_section = home.sections.filter(section_key="trust_features").first()
        if home_section is None:
            home_section = section_structure_service.add_section(
                draft=self.draft,
                section_key="trust_features",
                page_type=StorefrontPage.PageType.HOME,
            )
        self._merchant_edit_trust(home_section, [
            {"icon": "🏠", "title": _HOME_ONLY_TRUST, "subtitle": ""},
        ])
        # A PDP trust_features with its OWN content.
        self.draft.refresh_from_db()
        pdp_section = self._add_pdp_trust_section()
        self._merchant_edit_trust(pdp_section, [
            {"icon": "🏅", "title": _EDITED_TRUST, "subtitle": "اصل"},
        ])
        svc.publish(self.store)
        resp = self._public_pdp()
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(_EDITED_TRUST, body)
        self.assertNotIn(_HOME_ONLY_TRUST, body)

    # ---- 7. existing stores keep the hard-coded fallback ---------------

    def test_store_without_pdp_trust_section_keeps_hardcoded_fallback(self):
        # No trust_features on the PDP at all — publish the default layout.
        self.assertFalse(
            self.draft.get_page(StorefrontPage.PageType.PRODUCT_DETAIL)
            .sections.filter(section_key="trust_features").exists()
        )
        svc.publish(self.store)
        resp = self._public_pdp()
        self.assertEqual(resp.status_code, 200)
        # The hard-coded guarantee strip still renders (backward compatible).
        self.assertIn(_HARDCODED_FALLBACK, resp.content.decode())

    # ---- 8. no two competing trust modules on one PDP ------------------

    def test_canonical_pdp_trust_section_suppresses_the_hardcoded_strip(self):
        section = self._add_pdp_trust_section()
        self._merchant_edit_trust(section, [
            {"icon": "🏅", "title": _EDITED_TRUST, "subtitle": "اصل"},
        ])
        svc.publish(self.store)
        resp = self._public_pdp()
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # The canonical, merchant-edited content shows...
        self.assertIn(_EDITED_TRUST, body)
        # ...and the hard-coded guarantee strip is suppressed (never both).
        self.assertNotIn(_HARDCODED_FALLBACK, body)

    def test_no_second_trust_settings_authority_or_model_is_introduced(self):
        # The ONLY trust settings authority remains the trust_features schema.
        from apps.storefront_builder import section_registry
        definition = section_registry.get_definition("trust_features")
        self.assertIsNotNone(definition.settings_schema)
        # product_main stays a schema-less passthrough (no new schema attached).
        product_main = section_registry.get_definition("product_main")
        self.assertIsNone(product_main.settings_schema)


@override_settings(ALLOWED_HOSTS=[PUBLIC_HOST, "pdtx-foreign.example.com", "testserver"])
class PdpTrustTenantIsolationTests(TestCase):
    """9 — a foreign store's PDP trust edit never appears on this store's PDP."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        StoreDomain.objects.create(
            store=self.store, hostname=PUBLIC_HOST, is_primary=True,
            verification_status=StoreDomain.VerificationStatus.VERIFIED,
            verified_at=timezone.now(),
        )
        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="pdtx-iso-shop")
        self.category = Category.objects.create(store=self.store, name="دسته", slug="pdtx-iso-cat")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالای ایزوله", slug="pdtx-iso-product", sku="PDTX-ISO-1",
            price=Decimal("300000"), stock=5, status=Product.Status.ACTIVE,
        )

        # A DIFFERENT store with its own PDP trust content.
        self.foreign = Store.objects.create(
            name="فروشگاه بیگانه", slug="pdtx-foreign-store", status=Store.Status.ACTIVE,
        )
        foreign_draft = svc.get_or_create_draft(self.foreign)
        foreign_section = section_structure_service.add_section(
            draft=foreign_draft,
            section_key="trust_features",
            page_type=StorefrontPage.PageType.PRODUCT_DETAIL,
        )
        from apps.storefront_builder import section_registry
        foreign_section.settings = section_registry.validate_trust_features_settings(
            {"items": [{"icon": "🕵️", "title": "محتوای فروشگاه بیگانه", "subtitle": ""}]}
        )
        foreign_section.save(update_fields=["settings"])
        svc.publish(self.foreign)

        # This store publishes its own (default) PDP.
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)

    def test_foreign_store_trust_content_never_appears_on_this_pdp(self):
        resp = self.client.get(
            reverse("catalog:product-detail", args=[self.product.slug]),
            HTTP_HOST=PUBLIC_HOST,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("محتوای فروشگاه بیگانه", resp.content.decode())
