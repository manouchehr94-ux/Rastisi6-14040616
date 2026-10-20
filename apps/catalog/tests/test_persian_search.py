"""RS-09 — Persian-aware product search (owner repro: the hyphenated query returned 0, the spaced one 1)."""

from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product, Vendor
from apps.catalog.services import search_service as ss
from apps.stores.models import Store

TITLE = "کتانی رانینگ مسابقه‌ای مشکی-سفید"   # ZWNJ before «ای» and a hyphen, exactly as stored


class NormaliserUnitTests(SimpleTestCase):
    def test_hyphen_zwnj_arabic_letters_digits_and_spacing_collapse_to_one_form(self):
        forms = [
            "مسابقه‌ای", "مسابقه ای", "مسابقهای", "مسابقه‌ای", "مسابقه  ای",
        ]
        self.assertEqual({ss.normalize_search_text(f) for f in forms[:1] + forms[2:3]}, {"مسابقهای"})
        self.assertEqual(ss.normalize_search_text("مشکي-سفيد"), ss.normalize_search_text("مشکی سفید"))
        self.assertEqual(ss.normalize_search_text("كتاني"), "کتانی")
        self.assertEqual(ss.normalize_search_text("سایز ۴۰"), ss.normalize_search_text("سایز 40"))
        self.assertEqual(ss.normalize_search_text("سایز ٤٠"), "سایز 40")

    def test_tokens_split_on_separators_and_are_bounded(self):
        self.assertEqual(ss.search_tokens("مشکی-سفید / آبی_روشن"), ["مشکی", "سفید", "ابی", "روشن"])
        self.assertEqual(ss.search_tokens("   ---  "), [])
        self.assertEqual(len(ss.search_tokens(" ".join(f"w{i}" for i in range(50)))), ss.MAX_TOKENS)
        self.assertLessEqual(len(" ".join(ss.search_tokens("a" * 5000))), ss.MAX_QUERY_LENGTH)


class SearchViewTests(TestCase):
    def setUp(self):
        self.store = Store.objects.get(slug="akhlaghi")
        vendor = Vendor.objects.create(store=self.store, name="V", slug="v-ps")
        self.shoes = Category.objects.create(store=self.store, name="کفش", slug="shoes-ps")
        self.bags = Category.objects.create(store=self.store, name="کیف", slug="bags-ps")
        brand = Brand.objects.create(store=self.store, name="آریا", slug="arya-ps")
        def mk(name, sku, cat, **kw):
            kw.setdefault("stock", 5)
            return Product.objects.create(
                store=self.store, vendor=vendor, category=cat, name=name, slug=sku.lower(), sku=sku, price=Decimal("100000"), **kw)
        self.target = mk(TITLE, "PS1", self.shoes, brand=brand)
        self.other = mk("کتانی رانینگ آبی", "PS2", self.shoes)
        self.bag = mk("کیف دوشی مشکی", "PS3", self.bags)
        self.out = mk("کتانی مسابقه‌ای قرمز", "PS4", self.shoes, stock=0)
        self.arabic = mk("مانتو كتان مشكي", "PS5", self.bags)   # stored with Arabic ك / ي on purpose

    def names(self, **params):
        r = self.client.get(reverse("catalog:product-list"), params)
        self.assertEqual(r.status_code, 200)
        return {p.name for p in r.context["products"]} if "products" in r.context else {p.name for p in r.context["page_obj"]}

    def test_the_three_owner_cases_find_the_target(self):
        for q in (TITLE, "کتانی رانینگ مسابقه‌ای مشکی سفید", "مسابقه‌ای"):
            with self.subTest(q=q):
                self.assertIn(TITLE, self.names(q=q))

    def test_hyphen_space_zwnj_and_joined_spellings_are_equivalent(self):
        for q in ("مسابقه ای مشکی-سفید", "مسابقهای مشکی سفید", "مشکی-سفید", "سفید مشکی", "رانینگ  مسابقه‌ای"):
            with self.subTest(q=q):
                self.assertIn(TITLE, self.names(q=q))

    def test_results_stay_relevant(self):
        got = self.names(q="مشکی-سفید")
        self.assertEqual(got, {TITLE})
        self.assertEqual(self.names(q="رانینگ مشکی"), {TITLE})

    def test_arabic_and_persian_letter_variants_match_each_other_both_ways(self):
        self.assertIn("مانتو كتان مشكي", self.names(q="مانتو کتان مشکی"))
        self.assertIn(self.target.name, self.names(q="كتاني رانينگ"))

    def test_brand_category_and_sku_are_searched_too(self):
        self.assertIn(TITLE, self.names(q="آریا"))
        self.assertIn("کیف دوشی مشکی", self.names(q="کیف"))
        self.assertIn(TITLE, self.names(q="ps1"))

    def test_search_composes_with_category_and_in_stock_filters(self):
        self.assertEqual(self.names(q="کتانی", category="shoes-ps"), {TITLE, "کتانی رانینگ آبی", "کتانی مسابقه‌ای قرمز"})
        self.assertNotIn("کتانی مسابقه‌ای قرمز", self.names(q="کتانی", category="shoes-ps", in_stock="1"))
        self.assertEqual(self.names(q="مشکی", category="bags-ps"), {"کیف دوشی مشکی", "مانتو كتان مشكي"})  # Arabic-letter product matches too

    def test_hostile_input_is_inert(self):
        for q in ("'; DROP TABLE catalog_product; --", "%", "_", "\\", '"><script>alert(1)</script>', "مشکی%", "a" * 10000):
            with self.subTest(q=q[:20]):
                r = self.client.get(reverse("catalog:product-list"), {"q": q})
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertEqual(Product.objects.count(), 5)

    def test_empty_or_punctuation_only_query_does_not_filter(self):
        total = len(self.names())
        self.assertEqual(len(self.names(q="  - ")), total)

    def test_search_never_changes_stored_names_or_slugs(self):
        self.names(q=TITLE)
        self.target.refresh_from_db()
        self.assertEqual((self.target.name, self.target.slug), (TITLE, "ps1"))

    def test_other_store_products_are_never_returned(self):
        other = Store.objects.create(name="B", slug="ps-other", status=Store.Status.ACTIVE)
        v = Vendor.objects.create(store=other, name="V2", slug="v-ps2")
        c = Category.objects.create(store=other, name="کفش", slug="shoes-ps2")
        Product.objects.create(store=other, vendor=v, category=c, name=TITLE + " دیگر", slug="x-ps", sku="X1", price=Decimal("1"), stock=1)
        mine = ss.apply_product_search(Product.objects.filter(store=self.store), "مشکی-سفید")
        self.assertEqual({p.name for p in mine}, {TITLE})
