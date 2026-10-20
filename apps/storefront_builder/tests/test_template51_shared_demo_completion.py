"""Ready Template 51 completed over the ONE shared fashion demo (owner rule: one engine, one demo dataset, many recipes).

Template 51 (``stationery_spectrum``) is recipe data. This suite proves that the finished recipe, previewed over the canonical
Rasti Mode fashion demo, is a complete storefront and that nothing about it touches business data:

* the candidate preview renders only real demo catalogue content — no reserved empty placeholders (blank panels, empty blog
  cards, empty credential squares, blank decorative strip) and no vertical-specific (stationery) copy;
* the preview is read-only against the demo: products, prices, stock, categories, brands, media and the demo Draft are
  byte-identical before and after, and two different candidate previews never leak into each other;
* applying Template 51 to another Store is design-only: that Store's and the demo's products / categories / prices / media /
  inventory are unchanged, and the other Store's catalogue never appears in the demo preview.
"""

from django.test import override_settings

from apps.catalog.models import Brand, Category, Product, ProductImage, ProductVariant, WarehouseInventory
from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service
from apps.storefront_builder.views import RASTI_MODE_DEMO_STORE_SLUG
from apps.stores.models import Store

from .test_task2_live_demo_template_preview import (
    ADMIN_HOST,
    DENSE_MARKETPLACE,
    PUBLIC_HOST,
    LiveDemoTemplatePreviewTestCase,
    _snapshot,
)

T51 = "stationery_spectrum"

#: markup that exists only to reserve an empty position (the engine's neutral empty-state squares) or to paint a blank strip
EMPTY_PLACEHOLDER_MARKERS = (
    "blog-card--empty",
    "gf-trust-badge-item--empty",
    "category-grey-item--empty",
    "decor-strip",
    'class="section surface-panel',
)
STATIONERY_WORDS = ("لوازم‌التحریر", "لوازم تحریر", "دفتر و کاغذ", "روبان", "کاردستی", "فلش‌کارت", "چراغ، کابل")


def business_data(store) -> dict:
    """Everything a merchant owns that a design change must never touch, read fresh."""
    return {
        "products": list(Product.objects.filter(store=store).order_by("pk").values_list(
            "pk", "name", "slug", "sku", "price", "discount_percent", "stock", "status", "category_id", "brand_id")),
        "variants": list(ProductVariant.objects.filter(store=store).order_by("pk")
                         .values_list("pk", "product_id", "stock", "extra_price", "is_active")),
        "categories": list(Category.objects.filter(store=store).order_by("pk")
                           .values_list("pk", "name", "parent_id", "image")),
        "brands": list(Brand.objects.filter(store=store).order_by("pk").values_list("pk", "name")),
        "images": list(ProductImage.objects.filter(product__store=store).order_by("pk")
                       .values_list("pk", "product_id", "image", "thumbnail")),
        "warehouse_inventory": list(WarehouseInventory.objects.filter(store=store).order_by("pk")
                                    .values_list("pk", "product_id", "warehouse_id")),
    }


@override_settings(ALLOWED_HOSTS=[ADMIN_HOST, PUBLIC_HOST, "testserver"])
class Template51OverSharedDemoTests(LiveDemoTemplatePreviewTestCase):
    def _html(self, key=T51):
        response = self.admin_client.get(self._preview_url(key))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_preview_is_a_complete_storefront_without_empty_placeholders(self):
        html = self._html()
        self.assertGreaterEqual(html.count('class="pcard'), 20, "the demo catalogue must populate the rails")
        for marker in EMPTY_PLACEHOLDER_MARKERS:
            self.assertNotIn(marker, html, marker)
        for word in STATIONERY_WORDS:
            self.assertNotIn(word, html, word)
        # the recipe's neutral, data-source titles are what the merchant sees (and can edit)
        for title in ("پربازدیدترین‌ها", "جدیدترین محصولات", "تخفیف‌های منتخب"):
            self.assertIn(title, html)

    def test_every_rail_row_has_both_panels(self):
        html = self._html()
        for title in ("تخفیف‌های ویژه", "محبوب‌ترین‌ها", "جدیدترین‌ها", "پیشنهادهای ویژه",
                      "فرصت‌های خرید", "تازه‌های فروشگاه", "پربازدیدها", "قیمت‌های ویژه"):
            self.assertIn(title, html, f"pair panel «{title}» is missing (a rail with no products is hidden)")

    def test_preview_is_read_only_against_the_demo(self):
        demo_draft = svc.get_or_create_draft(self.demo_store)
        before_design = _snapshot(demo_draft)
        before_data = business_data(self.demo_store)
        self.assertGreaterEqual(len(before_data["products"]), 40)
        self.assertGreaterEqual(len(before_data["categories"]), 10)

        self._html()
        self._html()

        self.assertEqual(_snapshot(demo_draft), before_design)
        self.assertEqual(business_data(self.demo_store), before_data)

    def test_candidate_previews_do_not_leak_into_each_other(self):
        first = self._html(T51)
        other = self._html(DENSE_MARKETPLACE)
        self.assertNotEqual(first, other)
        for title in ("فرصت‌های خرید", "قیمت‌های ویژه"):
            self.assertIn(title, first)
            self.assertNotIn(title, other)
        again = self._html(T51)
        for title in ("فرصت‌های خرید", "قیمت‌های ویژه", "جدیدترین محصولات"):
            self.assertIn(title, again)
        # nothing of the other candidate survives into a later Template 51 preview
        self.assertNotIn("brand-carousel--marketplace", again)

    def test_applying_t51_to_another_store_is_design_only(self):
        merchant = Store.objects.get(slug="akhlaghi")
        merchant_before = business_data(merchant)
        demo_before = business_data(self.demo_store)
        merchant_names = [row[1] for row in merchant_before["products"]]

        draft = svc.get_or_create_draft(merchant, user=self.staff)
        preset_service.apply_preset(draft, lpr.get_layout_preset(T51))
        published = svc.publish(merchant, user=self.staff)

        self.assertEqual(business_data(merchant), merchant_before)
        self.assertEqual(business_data(self.demo_store), demo_before)
        # the merchant's own catalogue never shows up in the shared demo preview
        html = self._html()
        for name in merchant_names[:10]:
            self.assertNotIn(name, html)
        self.assertEqual(published.appearance_config.get("palette_slug"), "spectrum-stationery")
        titles = [(s.settings or {}).get("title") for s in published.get_page("home").sections.all()]
        self.assertIn("جدیدترین محصولات", titles)
        self.assertEqual((published.footer_config or {}).get("extra_blocks"), [])

    def test_demo_store_is_the_shared_fashion_demo(self):
        self.assertEqual(self.demo_store.slug, RASTI_MODE_DEMO_STORE_SLUG)
        names = " ".join(Product.objects.filter(store=self.demo_store).values_list("name", flat=True))
        self.assertTrue(any(word in names for word in ("کیف", "کتانی", "شلوار")))
