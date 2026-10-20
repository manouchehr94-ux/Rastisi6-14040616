"""Listing page layout contract (measured in a real browser separately — see
docs/qa_evidence/20261013_listing_layout): the filter actions live in ONE flex
container (Apply = primary, Reset = secondary) so they cannot overlap, the loading
indicator does not reserve a row above the grid, and the result count and active
filter chips share one compact row."""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, Vendor
from apps.stores.models import Store


class ListingLayoutContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=self.store, name="ف", slug="shop-plp")
        self.cat = Category.objects.create(store=self.store, name="جین", slug="jeans-plp")
        for i in range(5):
            Product.objects.create(
                store=self.store, vendor=vendor, category=self.cat, name=f"p{i}", slug=f"p{i}-plp",
                sku=f"PLP{i}", price=Decimal("1000"), stock=3,
            )

    def html(self, **params):
        return self.client.get(reverse("catalog:product-list"), params).content.decode()

    def test_apply_and_reset_share_one_actions_container(self):
        html = self.html()
        start = html.index('class="plp-actions"')
        block = html[start:html.index("</div>", start)]
        self.assertIn("plp-apply", block)
        self.assertIn("اعمال فیلتر", block)
        self.assertIn("plp-clear-all", block)
        self.assertIn("حذف همه", block)
        self.assertNotIn('style="width:100%"', block)

    def test_loading_indicator_is_an_overlay_not_a_reserved_row(self):
        html = self.html()
        self.assertIn("plp-loading-overlay", html)
        self.assertNotIn('<div style="display:flex;justify-content:flex-end;margin-bottom:8px">', html)

    def test_count_and_active_chips_share_one_meta_row(self):
        html = self.html(category=self.cat.slug)
        meta = html[html.index('class="plp-meta"'):]
        self.assertLess(meta.index("plp-count"), meta.index("plp-chips"))
        self.assertLess(meta.index("plp-chips"), meta.index("rsec-cols"))

    def test_htmx_partial_has_the_same_meta_row(self):
        html = self.client.get(
            reverse("catalog:product-list"), {"category": self.cat.slug}, HTTP_HX_REQUEST="true",
        ).content.decode()
        self.assertIn('class="plp-meta"', html)

    def test_reset_link_clears_every_filter_and_stays_on_this_store(self):
        html = self.html(category=self.cat.slug, sort="price_asc")
        self.assertIn(f'href="{reverse("catalog:product-list")}" class="plp-reset plp-clear-all"', html)

    def test_apply_filter_still_submits_real_query_parameters(self):
        response = self.client.get(reverse("catalog:product-list"), {"category": self.cat.slug, "in_stock": "1"})
        self.assertContains(response, "p0-plp")
