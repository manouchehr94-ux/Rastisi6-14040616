from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _product(store, slug, *, status=Product.Status.ACTIVE, vendor=None, category=None):
    vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=status,
    )


class CollectionIndexViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_shows_active_collections(self):
        active = svc.create_collection(self.store, name="فعال عمومی")
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, active.name)

    def test_hides_inactive_collections(self):
        inactive = svc.create_collection(self.store, name="غیرفعال عمومی")
        svc.deactivate_collection(inactive)
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertNotContains(resp, inactive.name)

    def test_empty_state(self):
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertContains(resp, "فعلاً کالکشنی")


class CollectionDetailViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()

    def test_active_collection_renders(self):
        collection = svc.create_collection(self.store, name="کالکشن عمومی", description="توضیح تستی")
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کالکشن عمومی")
        self.assertContains(resp, "توضیح تستی")

    def test_inactive_collection_404(self):
        collection = svc.create_collection(self.store, name="غیرفعال جزئیات")
        svc.deactivate_collection(collection)
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_missing_slug_404(self):
        resp = self.client.get(reverse("catalog:collection-detail", args=["does-not-exist"]))
        self.assertEqual(resp.status_code, 404)

    def test_cross_store_slug_404(self):
        other_store = Store.objects.create(name="فروشگاه دیگر عمومی", slug="coll-public-cross", admin_subdomain="coll-public-cross")
        other_collection = svc.create_collection(other_store, name="فروشگاه دیگر")
        resp = self.client.get(reverse("catalog:collection-detail", args=[other_collection.slug]))
        self.assertEqual(resp.status_code, 404)

    def test_only_storefront_visible_products_shown(self):
        collection = svc.create_collection(self.store, name="نمایش کالا")
        visible = _product(self.store, "public-visible")
        hidden = _product(self.store, "public-hidden", status=Product.Status.DRAFT)
        svc.add_product(collection, visible)
        svc.add_product(collection, hidden)
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertContains(resp, visible.name)
        self.assertNotContains(resp, hidden.name)

    def test_manual_order_preserved(self):
        collection = svc.create_collection(self.store, name="ترتیب عمومی")
        p1 = _product(self.store, "public-order-1")
        p2 = _product(self.store, "public-order-2")
        svc.add_product(collection, p1)
        svc.add_product(collection, p2)
        svc.reorder_items(collection, [item.pk for item in collection.items.order_by("-order")])
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        body = resp.content.decode()
        self.assertLess(body.index(p2.name), body.index(p1.name))

    def test_empty_state_when_no_visible_products(self):
        collection = svc.create_collection(self.store, name="خالی عمومی")
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertContains(resp, "فعلاً کالایی")

    def test_seo_fields_rendered(self):
        collection = svc.create_collection(
            self.store, name="سئو عمومی", seo_title="عنوان سئوی تست", seo_description="توضیح متای تست",
        )
        resp = self.client.get(reverse("catalog:collection-detail", args=[collection.slug]))
        self.assertContains(resp, "عنوان سئوی تست")
        self.assertContains(resp, "توضیح متای تست")

    def test_no_n_plus_one_query_growth(self):
        """با رشدِ تعدادِ کالای کالکشن، تعدادِ کوئریِ صفحه نباید رشد کند —
        رشدِ خطی یعنی select_related/prefetch_related جلویِ N+1 را نگرفته."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        small = svc.create_collection(self.store, name="کوئری‌بودجه کوچک")
        for i in range(3):
            svc.add_product(small, _product(self.store, f"query-budget-small-{i}"))

        large = svc.create_collection(self.store, name="کوئری‌بودجه بزرگ")
        for i in range(15):
            svc.add_product(large, _product(self.store, f"query-budget-large-{i}"))

        with CaptureQueriesContext(connection) as small_queries:
            resp_small = self.client.get(reverse("catalog:collection-detail", args=[small.slug]))
        with CaptureQueriesContext(connection) as large_queries:
            resp_large = self.client.get(reverse("catalog:collection-detail", args=[large.slug]))

        self.assertEqual(resp_small.status_code, 200)
        self.assertEqual(resp_large.status_code, 200)
        self.assertEqual(
            len(small_queries.captured_queries), len(large_queries.captured_queries),
            "تعداد کوئری با تعداد کالای کالکشن رشد کرده — احتمال N+1",
        )



class CollectionDetailPaginationDomainTests(TestCase):
    """Task 5 — ``/collections/<slug>/?page=2`` is served ENTIRELY by the
    domain-owned ``collection_detail`` view: it paginates the domain's own
    visible-membership list (``collection_visible_items`` + ``Paginator``),
    renders the shared product card partial, and has NO HTMX fragment branch
    (a normal full-page storefront render even when an HX header is present).
    """

    def setUp(self):
        self.store = _akhlaghi()
        self.collection = svc.create_collection(self.store, name="کالکشن صفحه‌بندی")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده صفحه‌بندی", slug="v-page2")
        category = Category.objects.create(store=self.store, name="دسته صفحه‌بندی", slug="c-page2")
        # 15 visible members => 2 pages at PRODUCTS_PER_PAGE=12 (12 + 3).
        self.products = []
        for i in range(15):
            p = Product.objects.create(
                store=self.store, vendor=vendor, category=category, name=f"کالای صفحه {i:02d}",
                slug=f"page2-p-{i:02d}", sku=f"SKU-PAGE2-{i:02d}", price=Decimal("10000"),
                status=Product.Status.ACTIVE,
            )
            svc.add_product(self.collection, p)
            self.products.append(p)

    def _url(self, page=None):
        url = reverse("catalog:collection-detail", args=[self.collection.slug])
        return f"{url}?page={page}" if page is not None else url

    def test_page2_uses_domain_visible_membership_paginated(self):
        resp = self.client.get(self._url(2))
        self.assertEqual(resp.status_code, 200)
        page_obj = resp.context["page_obj"]
        self.assertEqual(page_obj.number, 2)
        self.assertEqual(page_obj.paginator.num_pages, 2)
        # Page 2 holds the remaining 3 members (manual order preserved).
        self.assertEqual(len(resp.context["products"]), 3)
        # The domain visible-membership list is what was paginated.
        from apps.catalog.services.collection_service import collection_visible_items
        visible = list(collection_visible_items(self.collection, self.store))
        self.assertEqual(len(visible), 15)

    def test_page2_renders_shared_product_card_partial(self):
        resp = self.client.get(self._url(2))
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/partials/product_card.html", template_names)
        # A page-2 product is present; a page-1 product is not.
        self.assertContains(resp, self.products[13].name)
        self.assertNotContains(resp, self.products[0].name)

    def test_page2_has_no_htmx_fragment_branch(self):
        """No HX branch: an HX-Request header must NOT switch the view to a
        partial fragment — it still renders the full storefront envelope
        (shared shell + Builder CSS), unlike the cart's HTMX fragment path."""
        resp = self.client.get(self._url(2), HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/collection_detail.html", template_names)
        body = resp.content.decode()
        # Full envelope, not a bare fragment.
        self.assertIn("css/storefront_builder.css", body)

    def test_out_of_range_page_clamps_gracefully(self):
        """get_page clamps: page=999 returns the last page, never a 404/500."""
        resp = self.client.get(self._url(999))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["page_obj"].number, 2)

    def test_page2_accessible_anonymously(self):
        # No login/session required — public storefront read.
        resp = self.client.get(self._url(2))
        self.assertEqual(resp.status_code, 200)


class CollectionIndexBoundaryTests(TestCase):
    """Task 5 (E6) — the collection index (``/collections/``) is a SEPARATE
    direct listing: it lists collections (no per-collection products) and
    fabricates NO "current" collection (a Builder ``collection_header`` /
    ``collection_products`` on the shared COLLECTION page must render nothing
    there, because there is no resolved current collection)."""

    def setUp(self):
        self.store = _akhlaghi()

    def test_index_lists_collections_without_a_current_collection(self):
        c = svc.create_collection(self.store, name="کالکشنِ فهرست", description="توضیحِ فهرست")
        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, c.name)
        # No fabricated "current collection" object on the index view context.
        self.assertIsNone(resp.context.get("collection"))
        # The index carries a collections listing + its own paginator.
        self.assertIn("collections", resp.context)
        self.assertIn("page_obj", resp.context)

    def test_index_does_not_load_builder_css_or_render_items(self):
        svc.create_collection(self.store, name="کالکشنِ مرزی")
        resp = self.client.get(reverse("catalog:collection-index"))
        body = resp.content.decode()
        self.assertNotIn("css/storefront_builder.css", body)
        # It renders its own hardcoded grid template, not the shared render_rows.
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/collection_index.html", template_names)
        self.assertNotIn("storefront_builder/partials/render_rows.html", template_names)

    def test_index_paginates_its_own_collection_listing(self):
        # More collections than one page (PRODUCTS_PER_PAGE=12) => 2 pages.
        for i in range(15):
            svc.create_collection(self.store, name=f"کالکشنِ فهرستِ {i:02d}")
        resp = self.client.get(reverse("catalog:collection-index") + "?page=2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["page_obj"].number, 2)
        self.assertEqual(resp.context["page_obj"].paginator.num_pages, 2)

    def test_editing_collection_detail_section_composition_never_leaks_into_index(self):
        """Phase 4 (Task 3D, Ruling L) — end-to-end proof of the boundary
        both prior tests approach only structurally: a merchant customizing
        the shared ``StorefrontPage.PageType.COLLECTION`` section
        composition (which is Collection DETAIL's, per Ruling L) must never
        become visible on Collection Index, even though both routes resolve
        the exact same page_type/context builder call."""
        from apps.storefront_builder.models import StorefrontPage, StorefrontSection
        from apps.storefront_builder.services import layout_service

        svc.create_collection(self.store, name="کالکشنِ مرزیِ سه")
        draft = layout_service.get_or_create_draft(self.store)
        collection_page = draft.get_page(StorefrontPage.PageType.COLLECTION)
        marker_section = StorefrontSection.objects.create(
            page=collection_page, section_key="rich_text", order=999,
            settings={"body_html": "<p>PHASE4-TASK3D-DETAIL-ONLY-MARKER</p>"},
        )
        layout_service.publish(self.store)

        resp = self.client.get(reverse("catalog:collection-index"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "PHASE4-TASK3D-DETAIL-ONLY-MARKER")

        # Sanity check: the marker section IS real, on the correct page —
        # this proves the test would have caught a leak, not that the
        # section was silently never created.
        self.assertTrue(
            StorefrontSection.objects.filter(pk=marker_section.pk, page=collection_page).exists()
        )

    def test_index_uses_canonical_global_header_and_footer(self):
        """Ruling L — Collection Index stays on the shared storefront shell
        (canonical Global Appearance/Header/Footer), it just never resolves
        a "current" collection or Builder section composition of its own."""
        resp = self.client.get(reverse("catalog:collection-index"))
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("storefront_shell.html", template_names)
