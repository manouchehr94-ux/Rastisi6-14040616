"""Storefront tenant-isolation tests — real Host-based Store resolution.

These tests use two real ``Store`` rows, each with its own real, verified
``StoreDomain``, and distinct ``Host`` headers on real HTTP requests through
the full middleware chain (``request.store`` is never mocked). This proves
the storefront (home/list/detail/search/review) can never leak or accept a
cross-Store reference, matching the same real-Host methodology already used
in ``apps.stores.tests.test_middleware``.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.content.models import FooterSettings
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

HOST_A = "shop-a.example.com"
HOST_B = "shop-b.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store,
        hostname=hostname,
        is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED,
        verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class StorefrontTwoStoreIsolationTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="store-b", status=Store.Status.ACTIVE)
        _verified_domain(self.store_a, HOST_A)
        _verified_domain(self.store_b, HOST_B)
        ShopSettings.provision_for(self.store_b)
        FooterSettings.provision_for(self.store_b)

        self.category_a = Category.objects.create(
            store=self.store_a, name="Electronics A", slug="electronics-a", is_active=True
        )
        self.brand_a = Brand.objects.create(store=self.store_a, name="Brand A", slug="brand-a")
        self.vendor_a = Vendor.objects.create(store=self.store_a, name="Vendor A", slug="vendor-a")
        self.product_a = Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a, brand=self.brand_a,
            name="Store A Exclusive Phone", slug="store-a-phone", sku="SKU-ISO-A",
            price=Decimal("100000"), status=Product.Status.ACTIVE, stock=5,
        )

        self.category_b = Category.objects.create(
            store=self.store_b, name="Electronics B", slug="electronics-b", is_active=True
        )
        self.brand_b = Brand.objects.create(store=self.store_b, name="Brand B", slug="brand-b")
        self.vendor_b = Vendor.objects.create(store=self.store_b, name="Vendor B", slug="vendor-b")
        self.product_b = Product.objects.create(
            store=self.store_b, vendor=self.vendor_b, category=self.category_b, brand=self.brand_b,
            name="Store B Exclusive Phone", slug="store-b-phone", sku="SKU-ISO-B",
            price=Decimal("200000"), status=Product.Status.ACTIVE, stock=5,
        )

    # ------------------------------------------------------------ home

    def test_store_a_home_shows_only_its_own_product(self):
        response = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Store A Exclusive Phone")
        self.assertNotContains(response, "Store B Exclusive Phone")

    def test_store_b_home_shows_only_its_own_product(self):
        response = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Store B Exclusive Phone")
        self.assertNotContains(response, "Store A Exclusive Phone")

    def test_store_a_home_categories_isolated(self):
        response = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
        self.assertContains(response, "Electronics A")
        self.assertNotContains(response, "Electronics B")

    def test_store_b_home_categories_isolated(self):
        response = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_B)
        self.assertContains(response, "Electronics B")
        self.assertNotContains(response, "Electronics A")

    def test_engine_default_home_sections_are_isolated(self):
        response = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST_A)
        self.assertContains(response, "Store A Exclusive Phone")
        self.assertNotContains(response, "Store B Exclusive Phone")

    # ------------------------------------------------------------ product list / search / category / brand

    def test_product_list_isolated(self):
        response = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST_A)
        self.assertContains(response, "Store A Exclusive Phone")
        self.assertNotContains(response, "Store B Exclusive Phone")

    def test_search_isolated_even_for_matching_query(self):
        """Searching on Store A's host for Store B's exact product name must not find it."""
        response = self.client.get(reverse("catalog:product-list"), {"q": "Store B Exclusive"}, HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Store B Exclusive Phone")

    def test_category_filter_with_other_stores_slug_yields_no_results(self):
        """Filtering by another Store's category slug must not leak that Store's products."""
        response = self.client.get(
            reverse("catalog:product-list"), {"category": self.category_b.slug}, HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Store B Exclusive Phone")
        self.assertNotContains(response, "Store A Exclusive Phone")

    def test_brand_list_isolated(self):
        response = self.client.get(reverse("catalog:product-list"), HTTP_HOST=HOST_A)
        self.assertContains(response, "Brand A")
        self.assertNotContains(response, "Brand B")

    def test_brand_filter_with_other_stores_slug_yields_no_results(self):
        response = self.client.get(
            reverse("catalog:product-list"), {"brand": self.brand_b.slug}, HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Store A Exclusive Phone")

    # ------------------------------------------------------------ product detail — cross-Store PK/slug

    def test_product_detail_own_store_slug_succeeds(self):
        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product_a.slug]), HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Store A Exclusive Phone")

    def test_product_detail_cross_store_slug_returns_404(self):
        """Store A's host must not be able to resolve Store B's product by slug."""
        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product_b.slug]), HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 404)

    def test_product_detail_cross_store_slug_returns_404_reverse_direction(self):
        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product_a.slug]), HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_store_view_does_not_increment_views_count(self):
        """A denied cross-Store detail lookup must not mutate the other Store's product."""
        before = self.product_b.views_count
        self.client.get(reverse("catalog:product-detail", args=[self.product_b.slug]), HTTP_HOST=HOST_A)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.views_count, before)

    def test_related_products_never_cross_store(self):
        """A same-slug-named category on Store B must never leak into Store A's related products."""
        Product.objects.create(
            store=self.store_a, vendor=self.vendor_a, category=self.category_a, brand=self.brand_a,
            name="Store A Sibling Phone", slug="store-a-sibling-phone", sku="SKU-ISO-A2",
            price=Decimal("90000"), status=Product.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("catalog:product-detail", args=[self.product_a.slug]), HTTP_HOST=HOST_A
        )
        self.assertContains(response, "Store A Sibling Phone")
        self.assertNotContains(response, "Store B Exclusive Phone")

    # ------------------------------------------------------------ review creation cross-Store

    def test_review_create_cross_store_product_returns_404(self):
        response = self.client.post(
            reverse("catalog:product-review-create", args=[self.product_b.slug]),
            {"rating": "5", "text": "test"}, HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------ unknown Host fails closed

    def test_disallowed_host_fails_closed_with_no_store_data(self):
        """A Host Django itself disallows must never render either Store's storefront."""
        with self.settings(ALLOWED_HOSTS=[HOST_A, HOST_B]):
            response = self.client.get(reverse("catalog:home"), HTTP_HOST="attacker.example.com")
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "Store A Exclusive Phone", status_code=400)
        self.assertNotContains(response, "Store B Exclusive Phone", status_code=400)
