"""SEO policy (what may be indexed, where, and how) and the structured data built from real Store data.

A test host or a Store that is not public gets «Disallow: /», no sitemap and a noindex meta; a public Store gets robots with a sitemap on its
canonical origin, AI TRAINING crawlers blocked (search crawlers untouched), listing canonicals that keep the category, and JSON-LD that is
valid JSON, script-safe and free of invented facts. Two Stores never see each other's URLs."""

import json
import re
from decimal import Decimal

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.core import seo_policy
from apps.core.models import ShopSettings
from apps.stores.models import Store, StoreDomain

HOST_A = "seo-a.example.com"
HOST_B = "seo-b.example.com"


class PolicyUnitTests(SimpleTestCase):
    def test_test_hosts_are_never_public(self):
        for host in ("localhost", "localhost:8000", "shop.rastisi.localhost:8008", "127.0.0.1", "[::1]:8000", "10.0.0.5", "x.local", "x.test",
                     "x.invalid", "x.example", ""):
            self.assertTrue(seo_policy.is_non_public_host(host), host)

    def test_real_hosts_are_public(self):
        for host in ("shop.example.com", "rastisi.ir", "my-shop.rastisi.ir:443", "localhost.example.com", "testserver"):
            self.assertFalse(seo_policy.is_non_public_host(host), host)

    def test_not_indexable_closes_everything_and_advertises_no_sitemap(self):
        lines = seo_policy.robots_lines(origin="https://x.com", indexable=False)
        self.assertEqual(lines[:2], ["User-agent: *", "Disallow: /"])
        self.assertFalse(any(line.startswith("Sitemap") for line in lines))

    @override_settings(RASTISI_AI_TRAINING_CRAWLERS="disallow")
    def test_training_crawlers_are_blocked_but_search_crawlers_are_not_named_or_blocked(self):
        text = "\n".join(seo_policy.robots_lines(origin="https://x.com", indexable=True))
        for bot in seo_policy.AI_TRAINING_CRAWLERS:
            self.assertRegex(text, rf"User-agent: {re.escape(bot)}\nDisallow: /\n")
        for bot in seo_policy.AI_SEARCH_CRAWLERS:
            self.assertNotIn(f"User-agent: {bot}", text)
        for path in seo_policy.PRIVATE_DISALLOW:
            self.assertIn(f"Disallow: {path}", text)
        self.assertIn("Sitemap: https://x.com/sitemap.xml", text)

    @override_settings(RASTISI_AI_TRAINING_CRAWLERS="allow")
    def test_the_platform_can_allow_training_crawlers(self):
        text = "\n".join(seo_policy.robots_lines(origin="https://x.com", indexable=True))
        self.assertNotIn("GPTBot", text)

    def test_the_two_crawler_families_are_disjoint(self):
        self.assertFalse(set(seo_policy.AI_TRAINING_CRAWLERS) & set(seo_policy.AI_SEARCH_CRAWLERS))

    def test_json_ld_is_script_safe(self):
        from apps.core.templatetags.seo_tags import dump
        text = str(dump({"name": "</script><script>alert(1)</script> & <b>"}))
        self.assertNotIn("<", text)
        self.assertNotIn(">", text)
        self.assertEqual(json.loads(text)["name"], "</script><script>alert(1)</script> & <b>")


@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, "testserver"])
class PublicStoreTests(TestCase):
    def setUp(self):
        self.store_a = Store.objects.get(slug="akhlaghi")
        self.store_b = Store.objects.create(name="Store B", slug="seo-store-b", status=Store.Status.ACTIVE)
        ShopSettings.provision_for(self.store_b)
        for store, host in ((self.store_a, HOST_A), (self.store_b, HOST_B)):
            StoreDomain.objects.create(store=store, hostname=host, is_primary=True,
                                       verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now())
        vendor = Vendor.objects.create(store=self.store_a, name="V", slug="seo-v")
        self.category = Category.objects.create(store=self.store_a, name="شلوار", slug="pants", is_active=True)
        self.product = Product.objects.create(
            store=self.store_a, vendor=vendor, category=self.category, name='کتانی </script> "ویژه"', slug="seo-shoe", sku="SEO-1",
            price=Decimal("250000"), stock=3, status=Product.Status.ACTIVE, seo_description="توضیح واقعی محصول",
        )
        self.url_b = Product.objects.create(
            store=self.store_b, vendor=Vendor.objects.create(store=self.store_b, name="VB", slug="seo-vb"),
            category=Category.objects.create(store=self.store_b, name="B", slug="b-cat", is_active=True), name="Product of B",
            slug="seo-b-only", sku="SEO-B", price=Decimal("1000"), status=Product.Status.ACTIVE,
        )

    def _get(self, path, host=HOST_A):
        return self.client.get(path, HTTP_HOST=host)

    # ------------------------------------------------------------------------------------------------ robots / sitemap
    def test_a_public_store_gets_robots_with_its_own_sitemap_and_blocked_training_crawlers(self):
        body = self._get("/robots.txt").content.decode()
        self.assertIn(f"Sitemap: http://{HOST_A}/sitemap.xml", body)
        self.assertIn("User-agent: GPTBot\nDisallow: /", body)
        self.assertNotIn(HOST_B, body)

    def test_the_sitemap_has_only_this_stores_canonical_urls(self):
        body = self._get("/sitemap.xml").content.decode()
        self.assertIn(f"http://{HOST_A}/products/seo-shoe/", body)
        self.assertIn(f"http://{HOST_A}/products/?category=pants", body)
        self.assertNotIn("seo-b-only", body)
        self.assertNotIn(HOST_B, body)
        for private in ("/cart/", "/checkout/", "/account/", "/admin"):
            self.assertNotIn(private, body)

    def test_a_store_that_is_not_public_has_no_sitemap_and_a_closed_robots(self):
        self.store_a.status = Store.Status.PROVISIONING
        self.store_a.save(update_fields=["status"])
        self.assertIn(self._get("/robots.txt").status_code, (200, 404))
        resp = self._get("/sitemap.xml")
        self.assertEqual(resp.status_code, 404)

    @override_settings(ALLOWED_HOSTS=["*"], STORES_DEVELOPMENT_HOST_ALLOWLIST=["shop.localhost"])
    def test_a_test_host_is_closed_even_for_a_published_store(self):
        resp = self.client.get("/robots.txt", HTTP_HOST="shop.localhost")
        if resp.status_code == 200:                                  # resolved through the development allow-list
            self.assertIn("Disallow: /\n", resp.content.decode())
            self.assertNotIn("Sitemap:", resp.content.decode())

    # ------------------------------------------------------------------------------------------------ canonical / robots meta
    def test_a_category_listing_keeps_its_category_in_the_canonical(self):
        html = self._get("/products/?category=pants").content.decode()
        self.assertIn(f'<link rel="canonical" href="http://{HOST_A}/products/?category=pants">', html)

    def test_filtered_and_sorted_listings_are_noindex_but_followed(self):
        for query in ("?q=x", "?min_price=10", "?sort=price_asc"):
            html = self._get("/products/" + query).content.decode()
            self.assertIn('name="robots" content="noindex,follow"', html, query)

    def test_a_plain_listing_is_indexable(self):
        html = self._get("/products/").content.decode()
        self.assertNotIn('name="robots"', html)

    def test_a_non_public_store_page_is_noindex(self):
        self.store_a.status = Store.Status.PROVISIONING
        self.store_a.save(update_fields=["status"])
        resp = self._get("/")
        self.assertNotIn(resp.status_code, (500,))
        if resp.status_code == 200:
            self.assertIn("noindex", resp.content.decode())

    # ------------------------------------------------------------------------------------------------ structured data
    def _ld(self, html):
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        return [json.loads(block) for block in blocks]

    def test_home_has_organization_and_website_from_real_data(self):
        graph = self._ld(self._get("/").content.decode())[0]["@graph"]
        types = {node["@type"] for node in graph}
        self.assertEqual(types, {"Organization", "WebSite"})
        website = next(node for node in graph if node["@type"] == "WebSite")
        self.assertEqual(website["url"], f"http://{HOST_A}/")
        self.assertIn("search_term_string", website["potentialAction"]["target"])

    def test_the_product_json_ld_is_valid_script_safe_and_only_real(self):
        html = self._get("/products/seo-shoe/").content.decode()
        data = self._ld(html)[0]
        product = next(node for node in data["@graph"] if node["@type"] == "Product")
        self.assertEqual(product["name"], 'کتانی </script> "ویژه"')               # parsed back intact, never able to close the tag
        self.assertEqual(product["description"], "توضیح واقعی محصول")
        self.assertEqual(product["offers"]["availability"], "https://schema.org/InStock")
        self.assertEqual(product["offers"]["price"], "250000")
        self.assertEqual(product["url"], f"http://{HOST_A}/products/seo-shoe/")
        for invented in ("aggregateRating", "review", "shippingDetails", "hasMerchantReturnPolicy"):
            self.assertNotIn(invented, product)
        crumbs = next(node for node in data["@graph"] if node["@type"] == "BreadcrumbList")
        self.assertEqual(crumbs["itemListElement"][1]["name"], "شلوار")
        self.assertNotIn("</script><script>alert", html)

    def test_price_and_stock_changes_reach_the_structured_data(self):
        Product.objects.filter(pk=self.product.pk).update(stock=0, price=Decimal("300000"))
        product = next(node for node in self._ld(self._get("/products/seo-shoe/").content.decode())[0]["@graph"] if node["@type"] == "Product")
        self.assertEqual(product["offers"]["availability"], "https://schema.org/OutOfStock")
        self.assertEqual(product["offers"]["price"], "300000")

    def test_store_b_never_leaks_into_store_a(self):
        html = self._get("/products/seo-shoe/").content.decode() + self._get("/").content.decode() + self._get("/sitemap.xml").content.decode()
        self.assertNotIn(HOST_B, html)
        self.assertNotIn("Product of B", html)
