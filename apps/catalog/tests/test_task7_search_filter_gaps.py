"""Phase 5 Task 7 (Browse hardening) — focused test-gap fills ONLY.

Discovery classified Filter/Search as REUSE AS-IS but noted a few missing
assertions. These tests pin down existing behavior — they make NO production
change and are not a reason to redesign the query pipeline:

* text search must not emit duplicate Product rows (the q-branch uses
  ``.distinct()`` across the brand/category joins);
* ``min_price > max_price`` is a valid, non-crashing query that yields an
  empty result set (and the empty state).

Brand-name and category-name search matches are already covered by
``apps/catalog/tests/test_product_list_view.py`` (test_search_matches_brand_name /
test_search_matches_category_name) — not duplicated here.
"""
from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.catalog.views import _filtered_products
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class SearchDistinctTests(TestCase):
    """A product whose name AND brand AND category all match the query must
    appear exactly once (no join fan-out duplicates)."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده تطبیق", slug="t7-match-vendor")
        # The token "آبی" appears in the product name, the brand name AND the
        # category name — a triple join match that would duplicate without
        # DISTINCT.
        self.category = Category.objects.create(store=self.store, name="کفش آبی", slug="t7-blue-cat", icon="👟")
        self.brand = Brand.objects.create(store=self.store, name="برند آبی", slug="t7-blue-brand")
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, brand=self.brand,
            name="کتانی آبی", slug="t7-blue-shoe", sku="T7-BLUE-1", price=Decimal("500000"), stock=4,
        )

    def test_triple_match_query_returns_the_product_once(self):
        rf = RequestFactory()
        request = rf.get(reverse("catalog:product-list"), {"q": "آبی"})
        qs, _sort, _query = _filtered_products(request, self.store)
        ids = list(qs.values_list("id", flat=True))
        self.assertEqual(ids.count(self.product.id), 1, "search must not duplicate a multi-join match")
        self.assertEqual(len(ids), len(set(ids)), "search result set must contain no duplicate product ids")

    def test_triple_match_renders_exactly_one_card(self):
        response = self.client.get(reverse("catalog:product-list"), {"q": "آبی"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # Exactly one canonical product card <article class="pcard ..."> for the
        # single matching product (no join-fanout duplicate).
        self.assertEqual(html.count('<article class="pcard'), 1)
        self.assertContains(response, "کتانی آبی")


class PriceRangeEdgeTests(TestCase):
    """min_price > max_price is a valid empty result, not an error."""

    def setUp(self):
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده قیمت", slug="t7-price-vendor")
        self.category = Category.objects.create(store=self.store, name="دسته قیمت", slug="t7-price-cat", icon="🏷️")
        Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category,
            name="کالای قیمت‌دار", slug="t7-priced", sku="T7-PRICE-1", price=Decimal("300000"), stock=2,
        )

    def test_min_greater_than_max_yields_empty_result(self):
        rf = RequestFactory()
        request = rf.get(reverse("catalog:product-list"), {"min_price": "900000", "max_price": "100000"})
        qs, _sort, _query = _filtered_products(request, self.store)
        self.assertEqual(qs.count(), 0)

    def test_min_greater_than_max_renders_empty_state(self):
        response = self.client.get(
            reverse("catalog:product-list"), {"min_price": "900000", "max_price": "100000"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کالایی یافت نشد")
