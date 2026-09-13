"""Phase 5, Task 3 — RED contract for Merchant-data Ready Template preview.

This module is intentionally written BEFORE Task-3 production code.
It exercises the existing Task-2 live preview route with ``?data=merchant``;
at the certified Task-2 checkpoint that query parameter is ignored, so the
missing Task-3 behaviours must fail for real product/tenant reasons rather
than because a route does not exist.
"""

from io import StringIO
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.storefront_builder.models import (
    StorefrontContainer,
    StorefrontEditHistoryEntry,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service
from apps.storefront_builder.views import RASTI_MODE_DEMO_STORE_SLUG
from apps.stores.models import Store, StoreMembership


User = get_user_model()

ADMIN_HOST = "sfb-task3-merchant.rastisi.localhost"
EDITORIAL_JEWELRY = "editorial_jewelry"
DENSE_MARKETPLACE = "dense_marketplace"
WARM_BOUTIQUE = "warm_boutique"

STORE_A_CATEGORY = "TASK3-A-CATEGORY-ONLY"
STORE_A_BRAND = "TASK3-A-BRAND-ONLY"
STORE_A_PRODUCT = "TASK3-A-PRODUCT-ONLY"
STORE_A_PRICE = 987654

STORE_B_CATEGORY = "TASK3-B-CATEGORY-SECRET"
STORE_B_BRAND = "TASK3-B-BRAND-SECRET"
STORE_B_PRODUCT = "TASK3-B-PRODUCT-SECRET"

# Seeded only in the canonical Demo Store by the Golden Reference fixture.
DEMO_ONLY_HERO_TITLE = "کالکشن پاییز و زمستان Rasti Mode"


def _draft_snapshot(draft: StorefrontLayoutVersion) -> dict:
    """Full Task-2-style lifecycle snapshot for non-mutation proof."""
    draft.refresh_from_db()
    return {
        "edit_revision": draft.edit_revision,
        "appearance_config": draft.appearance_config,
        "header_config": draft.header_config,
        "footer_config": draft.footer_config,
        "template_provenance": draft.template_provenance,
        "template_baseline_snapshot": draft.template_baseline_snapshot,
        "sections": list(
            StorefrontSection.objects.filter(page__version=draft)
            .order_by("page_id", "order", "id")
            .values_list("page_id", "section_key", "order", "settings", "is_locked")
        ),
        "container_count": StorefrontContainer.objects.filter(page__version=draft).count(),
        "version_count": StorefrontLayoutVersion.objects.filter(layout_id=draft.layout_id).count(),
        "history_count": StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count(),
        "published_version_id": StorefrontLayout.objects.get(pk=draft.layout_id).published_version_id,
    }


def _item_contexts(response):
    for row in response.context["rows"]:
        for item in row["items"]:
            yield item["context"]


def _rendered_product_ids(response) -> set[int]:
    ids: set[int] = set()
    for context in _item_contexts(response):
        for product in context.get("products") or ():
            ids.add(product.pk)
        product = context.get("product")
        if product is not None:
            ids.add(product.pk)
        for group in context.get("catalog_product_wall_groups") or ():
            for product in group.get("products") or ():
                ids.add(product.pk)
    return ids


def _rendered_brand_ids(response) -> set[int]:
    ids: set[int] = set()
    for context in _item_contexts(response):
        for brand in context.get("brands") or ():
            ids.add(brand.pk)
    return ids


def _resource_store_ids(response) -> set[int]:
    """Collect concrete Store ownership visible in resolved section contexts."""
    store_ids: set[int] = set()
    collection_keys = (
        "products",
        "brands",
        "categories",
        "top_categories",
        "hero_slides",
        "banners",
        "story_items",
    )
    for context in _item_contexts(response):
        for key in collection_keys:
            for obj in context.get(key) or ():
                store_id = getattr(obj, "store_id", None)
                if store_id is not None:
                    store_ids.add(store_id)
        product = context.get("product")
        if product is not None and getattr(product, "store_id", None) is not None:
            store_ids.add(product.store_id)
        for group in context.get("catalog_product_wall_groups") or ():
            for product in group.get("products") or ():
                if getattr(product, "store_id", None) is not None:
                    store_ids.add(product.store_id)
    return store_ids


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, "testserver"])
class MerchantDataReadyTemplatePreviewREDTests(TestCase):
    """Task-3 desired behaviour against the real Task-1/Task-2 pipeline."""

    @classmethod
    def setUpTestData(cls):
        # Reuse the repository's canonical Demo Store fixture exactly as Task 2.
        call_command("apply_golden_reference_storefront", stdout=StringIO())

    def setUp(self):
        cache.clear()

        # Store A is the authenticated merchant Store used by the proven Task-2
        # admin-host test setup. Add unmistakable Store-A-only commerce data.
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_a.admin_subdomain = ADMIN_HOST.split(".")[0]
        self.store_a.save(update_fields=["admin_subdomain"])

        self.staff = User.objects.create_user(
            username="task3_merchant_owner",
            password="pass12345",
            is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store_a,
            user=self.staff,
            role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE,
            accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=ADMIN_HOST)
        self.assertTrue(self.client.login(username="task3_merchant_owner", password="pass12345"))

        self.vendor_a = Vendor.objects.create(
            store=self.store_a, name="Task3 Vendor A", slug="task3-vendor-a"
        )
        self.category_a = Category.objects.create(
            store=self.store_a,
            name=STORE_A_CATEGORY,
            slug="task3-a-category",
            order=0,
            is_active=True,
        )
        self.brand_a = Brand.objects.create(
            store=self.store_a,
            name=STORE_A_BRAND,
            slug="task3-a-brand",
            sort_order=0,
            is_active=True,
        )
        self.product_a = Product.objects.create(
            store=self.store_a,
            vendor=self.vendor_a,
            category=self.category_a,
            brand=self.brand_a,
            name=STORE_A_PRODUCT,
            slug="task3-a-product",
            sku="TASK3-A-SKU",
            price=STORE_A_PRICE,
            stock=10,
            discount_percent=100,
            status=Product.Status.ACTIVE,
            visibility=Product.Visibility.PUBLIC,
        )

        # Store B exists in the same database with unmistakable secret data.
        # It is never the authenticated/request-resolved Store.
        self.store_b = Store.objects.create(
            name="Task3 Other Tenant B",
            slug="task3-other-tenant-b",
            status=Store.Status.ACTIVE,
        )
        self.vendor_b = Vendor.objects.create(
            store=self.store_b, name="Task3 Vendor B", slug="task3-vendor-b"
        )
        self.category_b = Category.objects.create(
            store=self.store_b,
            name=STORE_B_CATEGORY,
            slug="task3-b-category",
            order=0,
            is_active=True,
        )
        self.brand_b = Brand.objects.create(
            store=self.store_b,
            name=STORE_B_BRAND,
            slug="task3-b-brand",
            sort_order=0,
            is_active=True,
        )
        self.product_b = Product.objects.create(
            store=self.store_b,
            vendor=self.vendor_b,
            category=self.category_b,
            brand=self.brand_b,
            name=STORE_B_PRODUCT,
            slug="task3-b-product",
            sku="TASK3-B-SKU",
            price=123456,
            stock=10,
            discount_percent=100,
            status=Product.Status.ACTIVE,
            visibility=Product.Visibility.PUBLIC,
        )

        self.demo_store = Store.objects.get(slug=RASTI_MODE_DEMO_STORE_SLUG)

        # Task-3 merchant preview is a read-only projection over an already
        # established merchant lifecycle. Bootstrap that normal lifecycle in
        # test setup; the preview request itself must never create or mutate it.
        self.merchant_draft = layout_service.get_or_create_draft(
            self.store_a, user=self.staff
        )

    def _merchant_preview_url(self, key, **extra_query):
        query = {"data": "merchant", **extra_query}
        return (
            reverse("dashboard:storefront-builder-template-live-preview", kwargs={"key": key})
            + "?"
            + urlencode(query)
        )

    def test_merchant_mode_uses_authenticated_store_not_demo_store(self):
        response = self.client.get(self._merchant_preview_url(EDITORIAL_JEWELRY))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["store"].pk, self.store_a.pk)
        self.assertNotEqual(response.context["store"].pk, self.demo_store.pk)

    def test_merchant_mode_nav_categories_are_store_a_scoped(self):
        response = self.client.get(self._merchant_preview_url(EDITORIAL_JEWELRY))
        self.assertEqual(response.status_code, 200)
        nav_categories = list(response.context["nav_categories"])
        nav_ids = {category.pk for category in nav_categories}
        nav_store_ids = {category.store_id for category in nav_categories}
        self.assertIn(self.category_a.pk, nav_ids)
        self.assertNotIn(self.category_b.pk, nav_ids)
        self.assertEqual(nav_store_ids, {self.store_a.pk})

    def test_merchant_product_content_is_store_a_scoped(self):
        # editorial_jewelry contains a newest-product section; Product A was
        # created after the seed data, so it must be visible for Store A.
        response = self.client.get(self._merchant_preview_url(EDITORIAL_JEWELRY))
        self.assertEqual(response.status_code, 200)
        product_ids = _rendered_product_ids(response)
        self.assertIn(self.product_a.pk, product_ids)
        self.assertNotIn(self.product_b.pk, product_ids)

    def test_merchant_brand_content_is_store_a_scoped(self):
        # dense_marketplace has a real brand_carousel section.
        response = self.client.get(self._merchant_preview_url(DENSE_MARKETPLACE))
        self.assertEqual(response.status_code, 200)
        brand_ids = _rendered_brand_ids(response)
        self.assertIn(self.brand_a.pk, brand_ids)
        self.assertNotIn(self.brand_b.pk, brand_ids)

    def test_merchant_mode_never_leaks_demo_hero_content(self):
        response = self.client.get(self._merchant_preview_url(DENSE_MARKETPLACE))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(DEMO_ONLY_HERO_TITLE, html)
        self.assertNotIn(self.demo_store.pk, _resource_store_ids(response))

    def test_request_cannot_override_merchant_store_with_ids_or_slugs(self):
        response = self.client.get(
            self._merchant_preview_url(
                DENSE_MARKETPLACE,
                store_id=self.store_b.pk,
                tenant_id=self.store_b.pk,
                store=self.store_b.slug,
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["store"].pk, self.store_a.pk)
        self.assertNotIn(self.store_b.pk, _resource_store_ids(response))

    def test_same_merchant_data_renders_under_two_distinct_template_dnas(self):
        jewelry = self.client.get(self._merchant_preview_url(EDITORIAL_JEWELRY))
        warm = self.client.get(self._merchant_preview_url(WARM_BOUTIQUE))
        self.assertEqual(jewelry.status_code, 200)
        self.assertEqual(warm.status_code, 200)

        self.assertIn(self.product_a.pk, _rendered_product_ids(jewelry))
        self.assertIn(self.product_a.pk, _rendered_product_ids(warm))
        self.assertEqual(jewelry.context["store"].pk, warm.context["store"].pk)
        self.assertNotEqual(
            jewelry.context["header_variant_template"],
            warm.context["header_variant_template"],
        )

    def test_merchant_preview_does_not_mutate_real_merchant_draft(self):
        draft = self.merchant_draft
        before = _draft_snapshot(draft)

        response = self.client.get(self._merchant_preview_url(DENSE_MARKETPLACE))
        self.assertEqual(response.status_code, 200)

        after = _draft_snapshot(draft)
        self.assertEqual(after, before)
        # This also prevents a false-positive non-mutation test that merely
        # rendered the Demo Store instead of actually entering Merchant mode.
        self.assertEqual(response.context["store"].pk, self.store_a.pk)


    def test_merchant_preview_never_creates_layout_or_draft(self):
        # A GET preview must not bootstrap persistence. If a merchant has no
        # existing Builder lifecycle yet, fail closed rather than creating a
        # StorefrontLayout/Draft as a side effect of browsing a template.
        StorefrontLayout.objects.filter(store=self.store_a).delete()
        self.assertFalse(StorefrontLayout.objects.filter(store=self.store_a).exists())

        response = self.client.get(self._merchant_preview_url(DENSE_MARKETPLACE))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(StorefrontLayout.objects.filter(store=self.store_a).exists())
        self.assertEqual(
            StorefrontLayoutVersion.objects.filter(layout__store=self.store_a).count(),
            0,
        )

    def test_merchant_preview_requires_existing_draft_and_never_uses_published_version(self):
        """Task-1 candidate resolution is Draft-based; preview must not bypass
        that lifecycle contract by treating Published as an editable candidate
        base, and it must never create a replacement Draft as a GET side effect.
        """
        published = layout_service.publish(self.store_a, user=self.staff)
        layout = StorefrontLayout.objects.get(store=self.store_a)
        self.assertIsNone(layout.draft_version_id)
        self.assertEqual(layout.published_version_id, published.pk)
        version_count_before = StorefrontLayoutVersion.objects.filter(
            layout=layout
        ).count()

        response = self.client.get(
            self._merchant_preview_url(DENSE_MARKETPLACE)
        )

        self.assertEqual(response.status_code, 404)
        layout.refresh_from_db()
        self.assertIsNone(layout.draft_version_id)
        self.assertEqual(layout.published_version_id, published.pk)
        self.assertEqual(
            StorefrontLayoutVersion.objects.filter(layout=layout).count(),
            version_count_before,
        )

    def test_gallery_exposes_separate_demo_and_my_store_preview_choices(self):
        response = self.client.get(reverse("dashboard:storefront-builder-templates"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("مشاهده با اطلاعات نمایشی", html)
        self.assertIn("مشاهده با اطلاعات فروشگاه من", html)
        self.assertIn("data=merchant", html)
