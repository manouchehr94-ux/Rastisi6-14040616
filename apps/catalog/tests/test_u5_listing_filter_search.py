"""U5 — Universal Listing / Filter / Search Experience.

Audit finding: the reusable listing shell (`build_product_listing_context`,
result count / sort / pagination / empty state / product-card rendering,
and the composable `render_items` wiring for `product_list.html`/
`collection_detail.html`/`product_detail.html`) already existed before this
phase. The two concrete, real gaps this phase closes:

- an "availability" (in-stock only) facet, using the existing real
  `Product.stock` field — no fabricated data;
- a genuinely usable mobile filter affordance (a collapsible `<details>`
  disclosure — the filter panel previously always rendered above the
  product grid on a phone with no way to collapse it out of the way).

`collection_index` remains deliberately outside the composable
`render_items` architecture (documented pre-existing boundary — it has no
"current collection" to be context-aware about) — not touched this phase.
"""

from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.catalog.views import _filtered_products
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class InStockFilterTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشنده یو۵", slug="u5-vendor")
        category = Category.objects.create(store=self.store, name="دسته یو۵", slug="u5-cat")
        self.in_stock = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای موجود یو۵",
            slug="u5-in-stock", sku="U5-SKU-1", price=Decimal("100000"), stock=5,
        )
        self.out_of_stock = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای ناموجود یو۵",
            slug="u5-out-of-stock", sku="U5-SKU-2", price=Decimal("100000"), stock=0,
        )

    def test_default_listing_shows_both_in_and_out_of_stock(self):
        """No regression: a store that never touches the new filter must see
        exactly the same products as before this phase."""
        response = self.client.get(reverse("catalog:product-list"))
        self.assertContains(response, "کالای موجود یو۵")
        self.assertContains(response, "کالای ناموجود یو۵")

    def test_in_stock_filter_excludes_zero_stock(self):
        response = self.client.get(reverse("catalog:product-list"), {"in_stock": "1"})
        self.assertContains(response, "کالای موجود یو۵")
        self.assertNotContains(response, "کالای ناموجود یو۵")

    def test_in_stock_checkbox_reflects_selection(self):
        response = self.client.get(reverse("catalog:product-list"), {"in_stock": "1"})
        self.assertContains(response, 'name="in_stock" value="1" checked')

    def test_in_stock_checkbox_unchecked_by_default(self):
        response = self.client.get(reverse("catalog:product-list"))
        self.assertNotContains(response, 'name="in_stock" value="1" checked')

    def test_in_stock_combines_with_existing_filters_without_extra_queries(self):
        """The new facet is one additional ``.filter()`` clause on the same
        queryset — must not introduce any new query."""
        with CaptureQueriesContext(connection) as baseline:
            self.client.get(reverse("catalog:product-list"), {"category": "u5-cat"})
        with CaptureQueriesContext(connection) as with_facet:
            self.client.get(reverse("catalog:product-list"), {"category": "u5-cat", "in_stock": "1"})
        self.assertEqual(len(with_facet), len(baseline))

    def test_in_stock_filter_never_crosses_store_boundary(self):
        """Function-level proof (avoids the HTTP host-resolution fixture a
        second real ``Store`` row would need): ``_filtered_products`` starts
        from ``storefront_listing_products(store)`` — already store-scoped —
        and the new facet is only ever chained onto that same queryset, so
        it cannot by construction surface another store's rows. Verified
        directly here rather than assumed."""
        other_store = Store.objects.create(name="فروشگاه دیگر یو۵", slug="u5-other-store", status=Store.Status.ACTIVE)
        other_vendor = Vendor.objects.create(store=other_store, name="فروشنده دیگر", slug="u5-other-vendor")
        other_category = Category.objects.create(store=other_store, name="دسته دیگر", slug="u5-other-cat")
        Product.objects.create(
            store=other_store, vendor=other_vendor, category=other_category, name="کالای فروشگاه دیگر",
            slug="u5-other-store-product", sku="U5-OTHER-SKU", price=Decimal("100000"), stock=99,
        )
        request = RequestFactory().get("/", {"in_stock": "1"})
        qs, _sort_key, _query = _filtered_products(request, self.store)
        self.assertNotIn("کالای فروشگاه دیگر", [p.name for p in qs])
        self.assertIn("کالای موجود یو۵", [p.name for p in qs])


class MobileFilterAffordanceTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_filter_panel_is_a_collapsible_disclosure(self):
        response = self.client.get(reverse("catalog:product-list"))
        self.assertContains(response, '<details class="plp-filters" open>')
        self.assertContains(response, '<summary class="plp-filters-toggle">')

    def test_filters_still_render_inside_disclosure(self):
        """Not just a bare toggle — the real filter form must still be there,
        so this is additive UX, not a regression that hides the filters."""
        response = self.client.get(reverse("catalog:product-list"))
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'name="brand"')
        self.assertContains(response, 'name="min_price"')
        self.assertContains(response, 'name="sort"')


class CollectionIndexPaginationTests(TestCase):
    """U5 — closes the documented known-technical-debt item: `collection_index`
    previously rendered every active collection on one unpaginated page."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_single_page_has_no_pagination_controls(self):
        collection_service.create_collection(self.store, name="تک کالکشن یو۵")
        response = self.client.get(reverse("catalog:collection-index"))
        self.assertNotContains(response, 'class="pagination"')

    def test_more_than_one_page_worth_paginates(self):
        for i in range(13):
            collection_service.create_collection(self.store, name=f"کالکشن یو۵ شماره {i}")
        first_page = self.client.get(reverse("catalog:collection-index"))
        self.assertContains(first_page, 'class="pagination"')
        self.assertEqual(len(first_page.context["collections"]), 12)

        second_page = self.client.get(reverse("catalog:collection-index"), {"page": 2})
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.context["collections"]), 1)


class HtmxFragmentCardSettingsPropagationTests(TestCase):
    """Phase 4 (Task 3E) — the Listing/Search HTMX filter/pagination
    fragment (``catalog/partials/product_list_results.html``) returned
    before the canonical context builder ran, so it never received the
    merchant's ``product_listing`` section card-style override — a real
    context-propagation gap, not a parallel renderer (both paths now share
    the exact same ``build_universal_storefront_context`` call)."""

    def setUp(self):
        from apps.storefront_builder.models import StorefrontPage, StorefrontSection
        from apps.storefront_builder.services import layout_service

        self.store = _akhlaghi()
        vendor = Vendor.objects.create(store=self.store, name="فروشنده سه‌ای", slug="task3e-vendor")
        category = Category.objects.create(store=self.store, name="دسته سه‌ای", slug="task3e-cat")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای سه‌ای",
            slug="task3e-product", sku="TASK3E-SKU-1", price=Decimal("50000"), stock=5,
        )

        draft = layout_service.get_or_create_draft(self.store)
        listing_page = draft.get_page(StorefrontPage.PageType.LISTING)
        listing_section = listing_page.sections.get(section_key="product_listing")
        listing_section.settings = {"card": {"card_style": "compact"}}
        listing_section.save(update_fields=["settings"])
        layout_service.publish(self.store)

    def test_full_page_load_applies_the_card_override(self):
        response = self.client.get(reverse("catalog:product-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "style-compact")

    def test_htmx_fragment_also_applies_the_card_override(self):
        response = self.client.get(reverse("catalog:product-list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "style-compact")
        # Genuinely the fragment template, not the full page (sanity check
        # that this test exercises the actual HTMX code path).
        template_names = [t.name for t in response.templates if t.name]
        self.assertIn("catalog/partials/product_list_results.html", template_names)
        self.assertNotIn("catalog/product_list.html", template_names)

    def test_htmx_search_fragment_also_applies_the_card_override(self):
        from apps.storefront_builder.models import StorefrontPage
        from apps.storefront_builder.services import layout_service

        draft = layout_service.get_or_create_draft(self.store)
        search_page = draft.get_page(StorefrontPage.PageType.SEARCH)
        search_section = search_page.sections.get(section_key="product_listing")
        search_section.settings = {"card": {"card_style": "compact"}}
        search_section.save(update_fields=["settings"])
        layout_service.publish(self.store)

        response = self.client.get(
            reverse("catalog:product-list"), {"q": "سه‌ای"}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "style-compact")
