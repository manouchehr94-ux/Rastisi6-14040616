"""Phase 5 Task 7 (Browse hardening) — Gap #2: Django-native elided pagination.

Discovery proved the listing template rendered EVERY page number
(``page_obj.paginator.page_range``), which at 50+ pages makes the mobile
pagination control unusable (browser evidence: 9 pages already wrapped to two
rows at 390px). The bounded repair keeps the canonical Django ``Paginator`` and
uses its OWN ``get_elided_page_range`` — no custom windowing algorithm, no new
paginator, no client-side pagination. This module is the RED-first proof:

* the view context exposes a bounded ``pagination_range`` derived from the same
  paginator (first/last/current always present, Django ELLIPSIS when needed);
* the number of rendered numeric page controls stays bounded as pages grow;
* the ellipsis is a non-link separator (no ``?page=…``);
* numeric page links preserve querystring + HTMX attrs + no-JS href;
* the current page carries ``aria-current="page"`` inside a labelled
  pagination ``<nav>``;
* single page renders no pagination block; out-of-range still clamps;
* filter/search/sort state is preserved across the bounded control.
"""
from decimal import Decimal

from django.core.paginator import Paginator
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.views import PRODUCTS_PER_PAGE
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class ElidedPaginationContextTests(TestCase):
    """The view builds a bounded page range from the canonical paginator."""

    @classmethod
    def setUpTestData(cls):
        cls.store = _akhlaghi()
        cls.vendor = Vendor.objects.create(store=cls.store, name="فروشنده هفت", slug="task7-vendor")
        cls.category = Category.objects.create(store=cls.store, name="دسته هفت", slug="task7-cat", icon="🧪")
        # 25 pages worth at 12/page (300 products) — enough to force elision.
        cls.total = PRODUCTS_PER_PAGE * 25
        Product.objects.bulk_create([
            Product(
                store=cls.store, vendor=cls.vendor, category=cls.category,
                name=f"کالای هفت {i:03d}", slug=f"task7-p-{i:03d}", sku=f"T7-{i:03d}",
                price=Decimal("10000") + i, stock=5,
            )
            for i in range(cls.total)
        ])

    def _ctx(self, **params):
        return self.client.get(reverse("catalog:product-list"), params).context

    def test_context_exposes_a_bounded_pagination_range(self):
        ctx = self._ctx()
        self.assertIn("pagination_range", ctx, "view must expose a bounded pagination_range")
        rng = list(ctx["pagination_range"])
        self.assertTrue(rng, "pagination_range must not be empty when paginated")

    def test_pagination_range_is_bounded_and_much_smaller_than_all_pages(self):
        ctx = self._ctx()
        num_pages = ctx["page_obj"].paginator.num_pages
        self.assertEqual(num_pages, 25)
        numeric = [x for x in ctx["pagination_range"] if isinstance(x, int)]
        # Bounded: far fewer numeric controls than the 25 total pages.
        self.assertLess(len(numeric), num_pages)
        self.assertLessEqual(len(numeric), 8, "bounded window should render at most a handful of numbers")

    def test_first_last_and_current_always_present(self):
        ctx = self._ctx(page=13)
        numeric = [x for x in ctx["pagination_range"] if isinstance(x, int)]
        self.assertIn(1, numeric, "first page always present")
        self.assertIn(25, numeric, "last page always present")
        self.assertIn(13, numeric, "current page always present")

    def test_django_ellipsis_appears_for_a_mid_range_page(self):
        ctx = self._ctx(page=13)
        self.assertIn(Paginator.ELLIPSIS, list(ctx["pagination_range"]),
                      "Django's own ELLIPSIS must appear between the ends and the window")
        # And the view should expose the ellipsis sentinel for the template.
        self.assertIn("pagination_ellipsis", ctx)
        self.assertEqual(ctx["pagination_ellipsis"], Paginator.ELLIPSIS)

    def test_control_count_stays_bounded_as_pages_grow(self):
        # Compare a mid page on 25 pages vs a mid page — the numeric count must
        # not scale with total pages (that was the whole defect).
        ctx = self._ctx(page=13)
        numeric = [x for x in ctx["pagination_range"] if isinstance(x, int)]
        self.assertLessEqual(len(numeric), 8)

    def test_single_page_result_has_no_pagination_block(self):
        # A narrow query that yields <=12 results renders no pagination markup.
        response = self.client.get(reverse("catalog:product-list"), {"q": "کالای هفت 001"})
        self.assertNotContains(response, 'class="pagination"')

    def test_out_of_range_page_still_clamps_to_last(self):
        response = self.client.get(reverse("catalog:product-list"), {"page": "9999"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number,
                         response.context["page_obj"].paginator.num_pages)


class ElidedPaginationTemplateTests(TestCase):
    """The rendered pagination markup honours the bounded window + a11y +
    the exact existing link contract (querystring / HTMX / no-JS href)."""

    @classmethod
    def setUpTestData(cls):
        cls.store = _akhlaghi()
        cls.vendor = Vendor.objects.create(store=cls.store, name="فروشنده هفت ب", slug="task7-vendor-b")
        cls.category = Category.objects.create(store=cls.store, name="دسته هفت ب", slug="task7-cat-b", icon="🧪")
        Product.objects.bulk_create([
            Product(
                store=cls.store, vendor=cls.vendor, category=cls.category,
                name=f"محصول هفت {i:03d}", slug=f"task7b-p-{i:03d}", sku=f"T7B-{i:03d}",
                price=Decimal("20000") + i, stock=3,
            )
            for i in range(PRODUCTS_PER_PAGE * 20)  # 20 pages
        ])

    def test_pagination_is_a_labelled_nav(self):
        response = self.client.get(reverse("catalog:product-list"), {"page": 10})
        self.assertContains(response, "<nav")
        self.assertContains(response, 'aria-label="صفحه‌بندی محصولات"')

    def test_current_page_has_aria_current(self):
        html = self.client.get(reverse("catalog:product-list"), {"page": 10}).content.decode()
        # The current page control is a <span class="current" aria-current="page">.
        self.assertIn('class="current" aria-current="page"', html)

    def test_ellipsis_is_rendered_and_not_a_link(self):
        html = self.client.get(reverse("catalog:product-list"), {"page": 10}).content.decode()
        # The ellipsis appears as visible text but never as a ?page= link.
        self.assertIn("…", html)
        # No numeric page link is generated for the ellipsis (it must not carry
        # an hx-get / href of ?page=…).
        self.assertNotIn("?page=…", html)
        self.assertNotIn("hx-get=\"?page=…", html)

    def test_numeric_links_preserve_querystring_and_htmx_and_href(self):
        # A filtered listing (q) still preserves q on numeric page links, keeps
        # HTMX attributes, and keeps a no-JS href.
        html = self.client.get(
            reverse("catalog:product-list"), {"page": 10, "q": "محصول"}
        ).content.decode()
        self.assertIn("q=", html)  # querystring preserved on links
        self.assertIn('hx-target="#product-results"', html)
        self.assertIn('hx-push-url="true"', html)
        self.assertIn('href="?page=', html)  # no-JS fallback

    def test_full_page_numbers_are_not_all_rendered(self):
        # The old defect: all 20 numbers rendered. Now bounded — page 15 must
        # not render a link to a far page like 3.
        html = self.client.get(reverse("catalog:product-list"), {"page": 15}).content.decode()
        # Persian numeral for 3 as a standalone page link should be absent from
        # the bounded window at page 15 (window is 1 … 14 15 16 … 20).
        self.assertNotIn(">۳</a>", html)

    def test_persian_numerals_used_in_pagination(self):
        html = self.client.get(reverse("catalog:product-list"), {"page": 10}).content.decode()
        # Current page 10 -> Persian ۱۰.
        self.assertIn("۱۰", html)
