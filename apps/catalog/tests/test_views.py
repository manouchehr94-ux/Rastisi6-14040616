from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class HomeViewTests(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.vendor_category = Category.objects.create(store=self.store, name="لوازم خانگی", slug="home-hv", icon="🏠")
        self.sub_category = Category.objects.create(
            store=self.store, name="آشپزخانه", slug="kitchen-hv", icon="🍳", parent=self.vendor_category
        )
        from apps.catalog.models import Vendor

        self.vendor = Vendor.objects.create(store=self.store, name="فروشگاه", slug="shop-hv")
        self.brand = Brand.objects.create(store=self.store, name="برند", slug="brand-hv")
        self.sold_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub_category, brand=self.brand,
            name="محصول پرفروش", slug="best-seller-hv", sku="SKU-HV1",
            price=Decimal("100000"), sold_count=500, views_count=10, discount_percent=0,
            stock=5,  # home rails never pick an unavailable product (owner rule)
        )
        self.discounted_product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.sub_category, name="محصول تخفیف‌دار",
            slug="discounted-hv", sku="SKU-HV2", price=Decimal("200000"), discount_percent=30,
            sold_count=1, views_count=999, stock=5,
        )

    def test_home_page_loads(self):
        response = self.client.get(reverse("catalog:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "محصول پرفروش")
        self.assertContains(response, "آشپزخانه")

    def test_default_home_is_engine_native_and_lists_the_best_seller(self):
        """A Store that never opened the builder is provisioned the ONE engine-native default composition: the best
        sellers section is a real published StorefrontSection, not a hard-coded legacy tab block."""
        from apps.storefront_builder.models import StorefrontLayout, StorefrontSection

        response = self.client.get(reverse("catalog:home"))
        self.assertContains(response, "محصول پرفروش")
        layout = StorefrontLayout.objects.get(store=self.store)
        self.assertIsNotNone(layout.published_version_id)
        keys = set(
            StorefrontSection.objects.filter(page__version=layout.published_version, page__page_type="home")
            .values_list("section_key", flat=True)
        )
        self.assertTrue({"category_grid", "newest_products", "best_sellers"} <= keys)
