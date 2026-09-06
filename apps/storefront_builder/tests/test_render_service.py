from decimal import Decimal
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from PIL import Image

from apps.catalog.models import Category, Product, Vendor
from apps.content.models import HeroSlide, PromotionalBanner
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import build_page_render_items, build_render_items, group_items_into_rows
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (100, 50, 200)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class GroupItemsIntoRowsTests(TestCase):
    """Phase 1 (معماریِ Universal Block/Data) — تبدیلِ دادهٔ خالص، بدونِ
    رندرِ HTML. هنوز توسطِ هیچ view/templateای صدا زده نمی‌شود (نگاه کنید
    به docstring خودِ تابع)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_sections_without_row_key_each_become_their_own_row(self):
        StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        StorefrontSection.objects.create(version=self.draft, section_key="trust_features", order=1)
        items = build_render_items(self.draft, self.store)
        rows = group_items_into_rows(items)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["row_key"] == "" for row in rows))
        self.assertTrue(all(len(row["items"]) == 1 for row in rows))

    def test_adjacent_same_row_key_grouped_together(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0, row_key="hero-row", row_span=8,
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="amazing_offers", order=1, row_key="hero-row", row_span=4,
        )
        StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=2)
        items = build_render_items(self.draft, self.store)
        rows = group_items_into_rows(items)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["row_key"], "hero-row")
        self.assertEqual(len(rows[0]["items"]), 2)
        self.assertEqual(rows[1]["row_key"], "")
        self.assertEqual(len(rows[1]["items"]), 1)

    def test_non_adjacent_same_row_key_becomes_two_separate_rows(self):
        """ورودیِ ناسازگار (که ``row_service.validate_page_row_layout`` باید
        پیش‌تر رد کرده باشد) نباید این تابع را کرش بدهد — فقط دو گروهِ
        مجاورِ جدا برمی‌گرداند، نه یک گروهِ اشتباهاً ادغام‌شده."""
        StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=0, row_key="split-row", row_span=6,
        )
        StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=1)
        StorefrontSection.objects.create(
            version=self.draft, section_key="amazing_offers", order=2, row_key="split-row", row_span=6,
        )
        items = build_render_items(self.draft, self.store)
        rows = group_items_into_rows(items)
        self.assertEqual([row["row_key"] for row in rows], ["split-row", "", "split-row"])

    def test_empty_items_returns_empty_rows(self):
        self.assertEqual(group_items_into_rows([]), [])


class BuildRenderItemsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_unknown_section_key_silently_skipped(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="not_a_real_type", order=999)
        items = build_render_items(draft, store)
        self.assertNotIn("not_a_real_type", [i["section"].section_key for i in items])

    def test_inactive_sections_excluded(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        inactive = StorefrontSection.objects.create(
            version=draft, section_key="trust_features", order=999, is_active=False,
        )
        items = build_render_items(draft, store)
        self.assertNotIn(inactive.pk, [i["section"].pk for i in items])

    def test_items_ordered_by_section_order(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        items = build_render_items(draft, store)
        orders = [i["section"].order for i in items]
        self.assertEqual(orders, sorted(orders))

    def test_each_item_carries_own_settings_and_section(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section = StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=1000, settings={"body_html": "hi"},
        )
        items = build_render_items(draft, store)
        item = next(i for i in items if i["section"].pk == section.pk)
        self.assertEqual(item["context"]["settings"], {"body_html": "hi"})
        self.assertEqual(item["context"]["section"].pk, section.pk)

    def test_duplicated_section_type_does_not_duplicate_queries(self):
        """بهینه‌سازی کوئری: دو نمونه از یک section_key یکسان (قابلیت
        پشتیبانی‌شده duplicable) نباید کوئری داده را دو بار اجرا کنند —
        هیچ‌کدام از context builderها به تنظیمات نمونه وابسته نیستند.

        به‌جای یک عدد ثابت (که به وجود/عدم‌وجود محصول در دیتابیس تست
        وابسته است — prefetch وقتی محصولی نیست کوئری اضافه نمی‌زند)،
        کوئری‌های «یک نمونه» را با کوئری‌های «دو نمونه» مقایسه می‌کنیم:
        باید دقیقاً برابر باشند، یعنی نمونه‌ی دوم هیچ کوئری اضافه‌ای
        نزده است."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.all().delete()
        StorefrontSection.objects.create(version=draft, section_key="newest_products", order=0)
        with CaptureQueriesContext(connection) as single_ctx:
            items = build_render_items(draft, store)
            for i in items:
                list(i["context"]["products"])
        single_count = len(single_ctx.captured_queries)

        StorefrontSection.objects.create(version=draft, section_key="newest_products", order=1)
        with CaptureQueriesContext(connection) as double_ctx:
            items = build_render_items(draft, store)
            for i in items:
                list(i["context"]["products"])
        self.assertEqual(len(items), 2)
        self.assertEqual(len(double_ctx.captured_queries), single_count)

    def test_different_instances_of_same_type_share_live_data_correctly(self):
        """اطمینان از این‌که کش سطح-تابع باعث نمایش داده‌ی «چسبیده» از یک
        section دیگر نمی‌شود — هر دو نمونه محتوای صحیح (یکسان، چون از
        همان store می‌آیند) را نشان می‌دهند، نه محتوای خالی/اشتباه."""
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, title="اسلاید تست", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=901)

        items = build_render_items(draft, store)
        hero_items = [i for i in items if i["section"].section_key == "hero_banner"]
        self.assertEqual(len(hero_items), 2)
        for item in hero_items:
            titles = [s.title for s in item["context"]["hero_slides"]]
            self.assertIn("اسلاید تست", titles)


class ProductSectionRenderTests(TestCase):
    """product_section به‌عمد جزوِ ``PER_INSTANCE_SECTION_KEYS`` است —
    این کلاس دقیقاً همان چیزی را تأیید می‌کند که آن پرچم برایش اضافه شد:
    دو نمونه‌ی تکرارشده با تنظیماتِ متفاوت (اینجا: دو کالکشنِ متفاوت)
    باید محتوایِ متفاوت نشان دهند، نه محتوایِ «قرض‌گرفته‌شده» از نمونه‌ی
    اول (باگی که کشِ سطح section_key بدونِ این فیکس ایجاد می‌کرد)."""

    def setUp(self):
        cache.clear()

    def _product(self, store, slug, *, vendor=None, category=None):
        from decimal import Decimal

        from apps.catalog.models import Category, Vendor

        vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
        category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
        from apps.catalog.models import Product

        return Product.objects.create(
            store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
            sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )

    def test_two_instances_with_different_collections_do_not_share_products(self):
        from apps.catalog.services import collection_service

        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)

        collection_a = collection_service.create_collection(store, name="کالکشن الف رندر")
        collection_b = collection_service.create_collection(store, name="کالکشن ب رندر")
        product_a = self._product(store, "render-ps-a")
        product_b = self._product(store, "render-ps-b")
        collection_service.add_product(collection_a, product_a)
        collection_service.add_product(collection_b, product_b)

        base_settings = {
            "data_source": "collection", "product_ids": [], "item_limit": 8,
            "display_mode": "carousel", "show_view_all": True, "title": "", "subtitle": "",
        }
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=900,
            settings={**base_settings, "source_id": collection_a.pk},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=901,
            settings={**base_settings, "source_id": collection_b.pk},
        )

        items = build_render_items(draft, store)
        item_a = next(i for i in items if i["section"].pk == section_a.pk)
        item_b = next(i for i in items if i["section"].pk == section_b.pk)
        self.assertEqual([p.pk for p in item_a["context"]["products"]], [product_a.pk])
        self.assertEqual([p.pk for p in item_b["context"]["products"]], [product_b.pk])

    def test_algorithmic_sources_reachable_through_full_pipeline(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        self._product(store, "render-ps-newest")
        section = StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=902,
            settings={
                "data_source": "newest", "source_id": None, "product_ids": [], "item_limit": 8,
                "display_mode": "grid", "show_view_all": True, "title": "جدیدترین", "subtitle": "",
            },
        )
        items = build_render_items(draft, store)
        item = next(i for i in items if i["section"].pk == section.pk)
        self.assertGreaterEqual(len(item["context"]["products"]), 1)
        self.assertIsNone(item["context"]["view_all_url"])

    def test_two_collection_instances_do_not_multiply_queries_per_extra_product(self):
        """رگرسیونِ N+1: کشِ per-instance (نه per-section_key) نباید به
        قیمتِ برگشتن به یک کوئری به‌ازایِ هر کالا تمام شود — هر نمونه
        باید select_related/prefetch_related را حفظ کند. مقایسه‌ی کوئریِ
        «۲ کالا در ۱ نمونه» با «۴ کالا در ۲ نمونه» باید تقریباً برابر
        باشد (همان تعداد کوئریِ ثابت، نه رشدِ خطی با تعدادِ کالا/نمونه)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.catalog.services import collection_service

        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="product_section").delete()

        collection_a = collection_service.create_collection(store, name="کالکشن N+1 الف")
        collection_service.add_product(collection_a, self._product(store, "n1-a1"))
        collection_service.add_product(collection_a, self._product(store, "n1-a2"))
        base_settings = {
            "data_source": "collection", "product_ids": [], "item_limit": 8,
            "display_mode": "carousel", "show_view_all": True, "title": "", "subtitle": "",
        }
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=950,
            settings={**base_settings, "source_id": collection_a.pk},
        )
        with CaptureQueriesContext(connection) as single_ctx:
            items = build_render_items(draft, store)
            for item in items:
                list(item["context"].get("products", []))
        single_count = len(single_ctx.captured_queries)

        collection_b = collection_service.create_collection(store, name="کالکشن N+1 ب")
        collection_service.add_product(collection_b, self._product(store, "n1-b1"))
        collection_service.add_product(collection_b, self._product(store, "n1-b2"))
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=951,
            settings={**base_settings, "source_id": collection_b.pk},
        )
        with CaptureQueriesContext(connection) as double_ctx:
            items = build_render_items(draft, store)
            for item in items:
                list(item["context"].get("products", []))
        double_count = len(double_ctx.captured_queries)

        # یک نمونه‌ی دومِ کامل (کالکشن + کالاهایش) چند کوئریِ ثابتِ اضافه
        # می‌زند (خودِ resolve + prefetch تصاویر) — نه یک کوئری به‌ازایِ
        # هر کالای اضافه‌شده.
        self.assertLessEqual(double_count - single_count, 4)


class ScopedHeroSlidesTests(TestCase):
    """چکپوینتِ ادغامِ اسلایدرِ اصلی در سازنده بصری — اسلایدهایِ مخصوصِ یک
    section در برابرِ fallback به اسلایدهایِ سراسری (رفتارِ قدیمی)."""

    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store, section_key):
        items = build_render_items(draft, store)
        return next(i for i in items if i["section"].section_key == section_key)

    def test_legacy_global_slides_still_render_when_section_has_none_scoped(self):
        """سازگاریِ کامل با گذشته: یک section جدید بدونِ اسلایدِ اختصاصی
        باید همچنان اسلایدهایِ سراسریِ فروشگاه (section=None) را نشان دهد."""
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, section=None, title="اسلایدِ سراسری", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        item = self._items_for(draft, store, "hero_banner")
        self.assertEqual(item["context"]["section"].pk, section.pk)
        titles = [s.title for s in item["context"]["hero_slides"]]
        self.assertIn("اسلایدِ سراسری", titles)

    def test_scoped_slides_take_priority_over_global(self):
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, section=None, title="سراسری", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        HeroSlide.objects.create(store=store, section=section, title="اختصاصی", desktop_image=_img(), is_active=True)
        item = self._items_for(draft, store, "hero_banner")
        titles = [s.title for s in item["context"]["hero_slides"]]
        self.assertEqual(titles, ["اختصاصی"])

    def test_two_independent_hero_sections_show_different_slides(self):
        """الزامِ صریحِ کار: «Hero Slider A و Hero Slider B با اسلایدهایِ
        متفاوت» — قلبِ چکپوینتِ اسلایدرِ اصلی."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        section_b = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=901)
        HeroSlide.objects.create(store=store, section=section_a, title="A1", desktop_image=_img(), is_active=True)
        HeroSlide.objects.create(store=store, section=section_b, title="B1", desktop_image=_img(), is_active=True)

        items = build_render_items(draft, store)
        hero_items = [i for i in items if i["section"].section_key == "hero_banner"]
        self.assertEqual(len(hero_items), 2)
        titles_by_section = {
            i["context"]["section"].pk: [s.title for s in i["context"]["hero_slides"]] for i in hero_items
        }
        self.assertEqual(titles_by_section[section_a.pk], ["A1"])
        self.assertEqual(titles_by_section[section_b.pk], ["B1"])

    def test_slider_settings_default_when_settings_empty(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900, settings={})
        item = self._items_for(draft, store, "hero_banner")
        self.assertIs(item["context"]["slider_settings"]["autoplay"], True)
        self.assertEqual(item["context"]["slider_settings"]["interval_ms"], 4500)

    def test_slider_settings_explicit_false_preserved(self):
        """همان دلیلِ ``effective_header_config`` — False صریح نباید با
        پیش‌فرضِ True بازنویسی شود."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=900,
            settings={"autoplay": False, "interval_ms": 4500, "show_arrows": True, "show_dots": True, "loop": True},
        )
        item = self._items_for(draft, store, "hero_banner")
        self.assertIs(item["context"]["slider_settings"]["autoplay"], False)

    def test_inactive_scoped_slide_falls_back_to_global(self):
        """اگر تنها اسلایدِ اختصاصیِ یک section غیرفعال شود، باید دقیقاً
        مثلِ «هیچ اسلایدِ اختصاصی ندارد» رفتار شود (fail-closed، نه بومِ
        خالی) — نه نمایشِ خالی و نه نمایشِ اسلایدِ غیرفعال."""
        store = _akhlaghi()
        HeroSlide.objects.create(store=store, section=None, title="سراسری", desktop_image=_img(), is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="hero_banner").delete()
        section = StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=900)
        HeroSlide.objects.create(store=store, section=section, title="غیرفعال", desktop_image=_img(), is_active=False)
        item = self._items_for(draft, store, "hero_banner")
        titles = [s.title for s in item["context"]["hero_slides"]]
        self.assertEqual(titles, ["سراسری"])


class ScopedBannersTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_two_multi_banner_sections_show_different_banners(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(version=draft, section_key="multi_banner", order=900)
        section_b = StorefrontSection.objects.create(version=draft, section_key="multi_banner", order=901)
        PromotionalBanner.objects.create(store=store, section=section_a, title="بنر A", desktop_image=_img(), is_active=True)
        PromotionalBanner.objects.create(store=store, section=section_b, title="بنر B", desktop_image=_img(), is_active=True)

        items = build_render_items(draft, store)
        banner_items = [i for i in items if i["section"].section_key == "multi_banner"]
        titles_by_section = {
            i["context"]["section"].pk: [b.title for b in i["context"]["banners"]] for i in banner_items
        }
        self.assertEqual(titles_by_section[section_a.pk], ["بنر A"])
        self.assertEqual(titles_by_section[section_b.pk], ["بنر B"])

    def test_single_banner_takes_first_scoped_banner_only(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section = StorefrontSection.objects.create(version=draft, section_key="single_banner", order=900)
        PromotionalBanner.objects.create(store=store, section=section, title="اول", desktop_image=_img(), is_active=True, display_order=0)
        PromotionalBanner.objects.create(store=store, section=section, title="دوم", desktop_image=_img(), is_active=True, display_order=1)
        items = build_render_items(draft, store)
        item = next(i for i in items if i["section"].section_key == "single_banner")
        titles = [b.title for b in item["context"]["banners"]]
        self.assertEqual(titles, ["اول"])


class CategoryGridRenderTests(TestCase):
    """چکپوینتِ ۱۱: category_grid از یک بلوکِ auto سراسری به یک section
    واقعاً per-instance ارتقا یافت."""

    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "category_grid"]

    def test_empty_selection_falls_back_to_legacy_auto_pick(self):
        """سازگاریِ کامل با گذشته: section بدونِ category_ids دقیقاً همان
        رفتارِ ۳+۱ قبل از این چکپوینت را دارد."""
        from apps.catalog.models import Category

        store = _akhlaghi()
        for i in range(5):
            Category.objects.create(store=store, name=f"دسته {i}", slug=f"cat-{i}", order=i, is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(version=draft, section_key="category_grid", order=900)
        item = self._items_for(draft, store)[0]
        self.assertEqual(len(item["context"]["tiles"]), 3)
        self.assertIsNotNone(item["context"]["cream_category"])

    def test_two_independent_category_grids_show_different_categories(self):
        """الزامِ صریحِ کار: تکرارِ گرید دسته‌بندی باید دسته‌های متفاوت
        نشان دهد — نه همان فهرستِ نمونه‌ی اول."""
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat_a = Category.objects.create(store=store, name="دسته A", slug="cat-a", is_active=True)
        cat_b = Category.objects.create(store=store, name="دسته B", slug="cat-b", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=901,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_b.pk]},
        )
        items = self._items_for(draft, store)
        names_by_section = {i["context"]["section"].pk: [c.name for c in i["context"]["top_categories"]] for i in items}
        self.assertEqual(names_by_section[section_a.pk], ["دسته A"])
        self.assertEqual(names_by_section[section_b.pk], ["دسته B"])

    def test_selection_preserves_merchant_order_not_database_order(self):
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat_a = Category.objects.create(store=store, name="آ", slug="cat-aa", is_active=True)
        cat_b = Category.objects.create(store=store, name="ب", slug="cat-bb", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_b.pk, cat_a.pk]},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual([c.name for c in item["context"]["top_categories"]], ["ب", "آ"])

    def test_inactive_category_silently_excluded(self):
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat = Category.objects.create(store=store, name="غیرفعال", slug="cat-inactive", is_active=False)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat.pk]},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["top_categories"], [])

    def test_fashion_mosaic_attaches_representative_media_from_real_product(self):
        """Micro-fix pass: ``fashion_mosaic`` tiles must read a real
        product's cover image (edge-to-edge), not ``Category.image`` (a
        composed thumbnail with baked-in colored margins)."""
        from apps.catalog.services.product_image_service import add_product_image

        store = _akhlaghi()
        cat = Category.objects.create(store=store, name="موزاییک رندر", slug="cat-mosaic-render", is_active=True)
        product = Product.objects.create(
            store=store,
            vendor=Vendor.objects.create(store=store, name="فروشنده موزاییک رندر", slug="v-mosaic-render"),
            category=cat, name="کالای موزاییک رندر", slug="p-mosaic-render",
            sku="SKU-MOSAIC-RENDER", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        image = add_product_image(product, _img())
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "fashion_mosaic", "category_ids": [cat.pk]},
        )
        item = self._items_for(draft, store)[0]
        rendered_cat = item["context"]["top_categories"][0]
        self.assertEqual(rendered_cat.representative_media.pk, image.pk)

    def test_non_mosaic_display_modes_do_not_attach_representative_media(self):
        """Isolation: the extra per-category product lookup must never run
        for any other ``category_grid`` display_mode (fashion_flat, grid,
        circular, image_strip) — those keep reading ``category.image``
        exactly as before this micro-fix pass."""
        from apps.catalog.models import Category

        store = _akhlaghi()
        cat = Category.objects.create(store=store, name="موزاییک غیر", slug="cat-non-mosaic-render", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="category_grid", order=900,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat.pk]},
        )
        item = self._items_for(draft, store)[0]
        rendered_cat = item["context"]["top_categories"][0]
        self.assertFalse(hasattr(rendered_cat, "representative_media"))


class CatalogProductWallContextTests(TestCase):
    """Site-target-overhaul Part 2D — the generic, ID-free multi-row
    merchandising wall. Every test here proves the same core claim: this
    section resolves the CURRENT Store's real categories/collections at
    render time, with no ``source_id`` stored anywhere, so it is safe for
    ANY Store any Ready Template applies it to."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def _product(self, slug, *, category, price="10000"):
        vendor = Vendor.objects.create(store=self.store, name=f"فروشنده {slug}", slug=f"v-{slug}")
        return Product.objects.create(
            store=self.store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
            sku=f"SKU-{slug}", price=Decimal(price), status=Product.Status.ACTIVE,
        )

    def _wall_item(self, settings=None):
        StorefrontSection.objects.create(
            version=self.draft, section_key="catalog_product_wall", order=900, settings=settings or {},
        )
        items = build_render_items(self.draft, self.store)
        return next(i for i in items if i["section"].section_key == "catalog_product_wall")

    def test_visible_categories_mode_resolves_real_categories_with_products(self):
        cat_a = Category.objects.create(store=self.store, name="دستهٔ آ", slug="wall-cat-a", is_active=True, order=0)
        cat_b = Category.objects.create(store=self.store, name="دستهٔ ب", slug="wall-cat-b", is_active=True, order=1)
        for i in range(3):
            self._product(f"wca-{i}", category=cat_a)
        for i in range(3):
            self._product(f"wcb-{i}", category=cat_b)

        item = self._wall_item({"source_mode": "visible_categories", "minimum_products": 2})
        groups = item["context"]["catalog_product_wall_groups"]
        titles = [g["title"] for g in groups]
        self.assertEqual(titles, ["دستهٔ آ", "دستهٔ ب"])
        self.assertEqual(len(groups[0]["products"]), 3)

    def test_category_below_minimum_products_is_skipped(self):
        cat = Category.objects.create(store=self.store, name="دستهٔ کم‌کالا", slug="wall-cat-sparse", is_active=True)
        self._product("wcs-0", category=cat)  # only 1 product

        item = self._wall_item({"source_mode": "visible_categories", "minimum_products": 3, "skip_empty_groups": True})
        self.assertEqual(item["context"]["catalog_product_wall_groups"], [])

    def test_max_groups_caps_the_result(self):
        for i in range(5):
            cat = Category.objects.create(store=self.store, name=f"دستهٔ {i}", slug=f"wall-cap-{i}", is_active=True, order=i)
            for j in range(3):
                self._product(f"wcap-{i}-{j}", category=cat)

        item = self._wall_item({"source_mode": "visible_categories", "max_groups": 2, "minimum_products": 1})
        self.assertEqual(len(item["context"]["catalog_product_wall_groups"]), 2)

    def test_visible_collections_mode_uses_collections_not_categories(self):
        from apps.catalog.services import collection_service

        cat = Category.objects.create(store=self.store, name="دستهٔ نادیده", slug="wall-ignored-cat", is_active=True)
        for i in range(3):
            self._product(f"wic-{i}", category=cat)
        collection = collection_service.create_collection(self.store, name="کالکشنِ دیوار")
        products = list(Product.objects.filter(store=self.store).order_by("id")[:3])
        collection_service.add_products(collection, products)

        item = self._wall_item({"source_mode": "visible_collections", "minimum_products": 1})
        groups = item["context"]["catalog_product_wall_groups"]
        self.assertEqual([g["title"] for g in groups], ["کالکشنِ دیوار"])

    def test_sibling_product_section_products_are_excluded_from_wall_groups(self):
        """Merchant visual QA (Part 2D) caught a real duplicate-row bug: a
        small demo catalog let a per-category wall group show the exact
        same handful of products (just reordered) as a sibling
        ``product_section``'s generic row. The wall must exclude whatever
        a sibling ``product_section`` on the same page already shows."""
        cat = Category.objects.create(store=self.store, name="دستهٔ مشترک", slug="wall-shared-cat", is_active=True)
        shared = [self._product(f"shared-{i}", category=cat) for i in range(3)]

        StorefrontSection.objects.create(
            version=self.draft, section_key="product_section", order=100,
            settings={"data_source": "newest", "item_limit": 10},
        )
        item = self._wall_item({"source_mode": "visible_categories", "minimum_products": 1, "products_per_group": 10})
        groups = item["context"]["catalog_product_wall_groups"]
        shown_ids = {p.pk for g in groups for p in g["products"]}
        self.assertFalse(shown_ids & {p.pk for p in shared})

    def test_no_categories_or_collections_returns_empty_groups_not_an_error(self):
        item = self._wall_item({"source_mode": "visible_categories"})
        self.assertEqual(item["context"]["catalog_product_wall_groups"], [])


class BrandCarouselRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "brand_carousel"]

    def test_empty_selection_falls_back_to_all_active_brands(self):
        from apps.catalog.models import Brand

        store = _akhlaghi()
        Brand.objects.create(store=store, name="برند فعال", slug="brand-active", is_active=True)
        Brand.objects.create(store=store, name="برند غیرفعال", slug="brand-inactive", is_active=False)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(version=draft, section_key="brand_carousel", order=900)
        item = self._items_for(draft, store)[0]
        self.assertEqual([b.name for b in item["context"]["brands"]], ["برند فعال"])

    def test_two_independent_brand_carousels_show_different_brands(self):
        from apps.catalog.models import Brand

        store = _akhlaghi()
        brand_a = Brand.objects.create(store=store, name="برند A", slug="brand-a", is_active=True)
        brand_b = Brand.objects.create(store=store, name="برند B", slug="brand-b", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900,
            settings={"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=901,
            settings={"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_b.pk]},
        )
        items = self._items_for(draft, store)
        names_by_section = {i["context"]["section"].pk: [b.name for b in i["context"]["brands"]] for i in items}
        self.assertEqual(names_by_section[section_a.pk], ["برند A"])
        self.assertEqual(names_by_section[section_b.pk], ["برند B"])

    def test_view_all_link_absent_without_show_view_all(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(version=draft, section_key="brand_carousel", order=900)
        item = self._items_for(draft, store)[0]
        self.assertIsNone(item["context"]["view_all_url"])

    def test_view_all_link_resolves_when_enabled_with_destination(self):
        from apps.catalog.models import Category

        store = _akhlaghi()
        category = Category.objects.create(store=store, name="همه برندها", slug="all-brands-cat", is_active=True)
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900,
            settings={
                "title": "", "display_mode": "grid", "show_view_all": True, "brand_ids": [],
                "destination": {"destination_type": "category", "destination_id": category.pk, "open_in_new_tab": False},
            },
        )
        item = self._items_for(draft, store)[0]
        self.assertIsNotNone(item["context"]["view_all_url"])
        self.assertIn(category.slug, item["context"]["view_all_url"])

    # --------------------------------------------------------------------
    # Phase 3 characterization: these lock in the CURRENT (correct) resolved
    # behavior of the brand_carousel context builder before any Phase 3
    # variant-preservation change is made. They must be GREEN as-is.
    # --------------------------------------------------------------------

    def _brand_fixture(self):
        """Own store with two active own brands, one inactive own brand, and a
        SECOND explicit store carrying a foreign (cross-store) active brand."""
        from apps.catalog.models import Brand

        store = _akhlaghi()
        own_a = Brand.objects.create(store=store, name="Own A", slug="p3-own-a", is_active=True)
        own_b = Brand.objects.create(store=store, name="Own B", slug="p3-own-b", is_active=True)
        Brand.objects.create(store=store, name="Own Inactive", slug="p3-own-inactive", is_active=False)
        other_store = Store.objects.create(name="Phase3 Other Store", slug="p3-other-store")
        foreign = Brand.objects.create(
            store=other_store, name="Foreign", slug="p3-foreign", is_active=True,
        )
        return store, own_a, own_b, foreign

    def test_manual_order_preserved_and_foreign_inactive_omitted_all_display_modes(self):
        store, own_a, own_b, foreign = self._brand_fixture()
        draft = svc.get_or_create_draft(store)
        for display_mode in ("grid", "carousel", "beauty_tabs"):
            with self.subTest(display_mode=display_mode):
                cache.clear()
                draft.sections.filter(section_key="brand_carousel").delete()
                StorefrontSection.objects.create(
                    version=draft, section_key="brand_carousel", order=900,
                    settings={
                        "title": "", "display_mode": display_mode, "show_view_all": False,
                        # requested order intentionally interleaves a foreign brand
                        "brand_ids": [own_b.pk, foreign.pk, own_a.pk],
                    },
                )
                item = self._items_for(draft, store)[0]
                self.assertEqual(item["context"]["brand_carousel_settings"]["display_mode"], display_mode)
                self.assertEqual(
                    [b.pk for b in item["context"]["brands"]],
                    [own_b.pk, own_a.pk],
                    msg=f"foreign+inactive must be omitted and manual order kept for {display_mode}",
                )

    def test_independent_sibling_sections_do_not_borrow_each_others_data(self):
        store, own_a, own_b, _foreign = self._brand_fixture()
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900,
            settings={"title": "", "display_mode": "grid", "show_view_all": False, "brand_ids": [own_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=901,
            settings={"title": "", "display_mode": "carousel", "show_view_all": False, "brand_ids": [own_b.pk]},
        )
        items = self._items_for(draft, store)
        pks_by_section = {
            i["context"]["section"].pk: [b.pk for b in i["context"]["brands"]] for i in items
        }
        self.assertEqual(pks_by_section[section_a.pk], [own_a.pk])
        self.assertEqual(pks_by_section[section_b.pk], [own_b.pk])

    def test_unknown_persisted_display_mode_falls_back_safely(self):
        store, own_a, own_b, _foreign = self._brand_fixture()
        draft = svc.get_or_create_draft(store)
        draft.sections.filter(section_key="brand_carousel").delete()
        # A persisted (bypassing validation) invalid display_mode must still
        # render without error — the context builder is defensive.
        StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900,
            settings={
                "title": "", "display_mode": "not_a_real_mode", "show_view_all": False,
                "brand_ids": [own_a.pk, own_b.pk],
            },
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual([b.pk for b in item["context"]["brands"]], [own_a.pk, own_b.pk])


class CollectionTilesRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "collection_tiles"]

    def test_empty_selection_falls_back_to_all_active_collections(self):
        from apps.catalog.models import MerchantCollection

        store = _akhlaghi()
        MerchantCollection.objects.create(store=store, name="کالکشن فعال", slug="ct-active", is_active=True)
        MerchantCollection.objects.create(store=store, name="کالکشن غیرفعال", slug="ct-inactive", is_active=False)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="collection_tiles", order=900)
        item = self._items_for(draft, store)[0]
        names = [row["collection"].name for row in item["context"]["collection_tiles"]]
        self.assertEqual(names, ["کالکشن فعال"])

    def test_two_independent_collection_tile_sections_show_different_collections(self):
        from apps.catalog.models import MerchantCollection

        store = _akhlaghi()
        coll_a = MerchantCollection.objects.create(store=store, name="کالکشن A", slug="ct-a", is_active=True)
        coll_b = MerchantCollection.objects.create(store=store, name="کالکشن B", slug="ct-b", is_active=True)
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"title": "", "collection_ids": [coll_a.pk]},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=901,
            settings={"title": "", "collection_ids": [coll_b.pk]},
        )
        items = self._items_for(draft, store)
        names_by_section = {
            i["context"]["section"].pk: [row["collection"].name for row in i["context"]["collection_tiles"]]
            for i in items
        }
        self.assertEqual(names_by_section[section_a.pk], ["کالکشن A"])
        self.assertEqual(names_by_section[section_b.pk], ["کالکشن B"])

    def test_item_count_reflects_real_products_in_collection(self):
        from decimal import Decimal

        from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor

        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="فروشنده ct-count", slug="v-ct-count")
        category = Category.objects.create(store=store, name="دسته", slug="ct-count-cat", is_active=True)
        collection = MerchantCollection.objects.create(store=store, name="کالکشن شمارشی", slug="ct-count", is_active=True)
        for i in range(3):
            product = Product.objects.create(
                store=store, vendor=vendor, category=category, name=f"کالای {i}", slug=f"ct-count-p{i}",
                sku=f"SKU-CT-{i}", price=Decimal("10000"), status=Product.Status.ACTIVE,
            )
            MerchantCollectionItem.objects.create(collection=collection, product=product, order=i)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"title": "", "collection_ids": [collection.pk]},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["collection_tiles"][0]["item_count"], 3)

    def test_item_count_is_total_membership_not_visible_products(self):
        # Task 4 (V03) count-semantics characterization: item_count = TOTAL
        # membership (Count("items")), including a member whose product is
        # NOT storefront-visible. The visible domain list (collection_visible_items)
        # would be strictly smaller.
        from decimal import Decimal

        from apps.catalog.models import (
            Category, MerchantCollection, MerchantCollectionItem, Product, Vendor,
        )
        from apps.catalog.services.collection_service import collection_visible_items

        store = _akhlaghi()
        vendor = Vendor.objects.create(store=store, name="فروشنده ct-total", slug="v-ct-total")
        category = Category.objects.create(store=store, name="دسته ct-total", slug="ct-total-cat", is_active=True)
        collection = MerchantCollection.objects.create(
            store=store, name="کالکشن عضویت", slug="ct-total", is_active=True,
        )
        active_product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای فعال", slug="ct-total-active",
            sku="SKU-CT-ACTIVE", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        inactive_product = Product.objects.create(
            store=store, vendor=vendor, category=category, name="کالای غیرفعال", slug="ct-total-inactive",
            sku="SKU-CT-INACTIVE", price=Decimal("10000"), status=Product.Status.INACTIVE,
        )
        MerchantCollectionItem.objects.create(collection=collection, product=active_product, order=0)
        MerchantCollectionItem.objects.create(collection=collection, product=inactive_product, order=1)

        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"title": "", "collection_ids": [collection.pk]},
        )
        item = self._items_for(draft, store)[0]
        # Total membership = 2 (both members), regardless of product visibility.
        self.assertEqual(item["context"]["collection_tiles"][0]["item_count"], 2)
        # The visible domain list is strictly smaller (1) — the count is NOT
        # the visible-product count.
        visible = list(collection_visible_items(collection, store))
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].product_id, active_product.pk)

    def test_manual_order_is_preserved_and_differs_from_name_index_ordering(self):
        from apps.catalog.models import MerchantCollection

        store = _akhlaghi()
        # Names deliberately sort A < B < C by name, but we request C, A, B.
        coll_a = MerchantCollection.objects.create(store=store, name="AAA", slug="ct-order-a", is_active=True)
        coll_b = MerchantCollection.objects.create(store=store, name="BBB", slug="ct-order-b", is_active=True)
        coll_c = MerchantCollection.objects.create(store=store, name="CCC", slug="ct-order-c", is_active=True)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900,
            settings={"title": "", "collection_ids": [coll_c.pk, coll_a.pk, coll_b.pk]},
        )
        item = self._items_for(draft, store)[0]
        names = [row["collection"].name for row in item["context"]["collection_tiles"]]
        self.assertEqual(names, ["CCC", "AAA", "BBB"])
        # Manual order is NOT the name-alphabetical index ordering.
        self.assertNotEqual(names, sorted(names))

    def test_auto_ordering_is_newest_first_not_name_ordering(self):
        from apps.catalog.models import MerchantCollection

        store = _akhlaghi()
        # Create in an order such that newest-first (-created_at) differs from
        # name-alphabetical. Names ascending Z,Y,X as they are created.
        first = MerchantCollection.objects.create(store=store, name="ZZZ", slug="ct-newest-z", is_active=True)
        second = MerchantCollection.objects.create(store=store, name="YYY", slug="ct-newest-y", is_active=True)
        third = MerchantCollection.objects.create(store=store, name="XXX", slug="ct-newest-x", is_active=True)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="collection_tiles", order=900)
        item = self._items_for(draft, store)[0]
        names = [row["collection"].name for row in item["context"]["collection_tiles"]]
        # Newest-first == reverse creation order (third, second, first).
        self.assertEqual(names, ["XXX", "YYY", "ZZZ"])
        # This happens to also equal name-sorted here (X<Y<Z), so prove the
        # ordering is by created_at, not name, by pk sequence too.
        pks = [row["collection"].pk for row in item["context"]["collection_tiles"]]
        self.assertEqual(pks, [third.pk, second.pk, first.pk])


class QuickLinksRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "quick_links"]

    def test_no_menu_configured_renders_no_items(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="quick_links", order=900)
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["quick_link_items"], [])

    def test_menu_items_resolved_with_real_destination_urls(self):
        from apps.catalog.models import Category
        from apps.content.models import DestinationType, Menu, MenuItem

        store = _akhlaghi()
        category = Category.objects.create(store=store, name="دسته دسترسی سریع", slug="ql-cat", is_active=True)
        menu = Menu.objects.create(store=store, title="دسترسی سریع", location=Menu.Location.HEADER, is_active=True)
        MenuItem.objects.create(
            menu=menu, title="مشاهده دسته", display_order=0, is_active=True,
            destination_type=DestinationType.CATEGORY, destination_category=category,
        )
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="quick_links", order=900,
            settings={"title": "", "menu_id": menu.pk},
        )
        item = self._items_for(draft, store)[0]
        items = item["context"]["quick_link_items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "مشاهده دسته")
        self.assertIn(category.slug, items[0]["url"])

    def test_menu_items_query_count_is_constant_not_per_item(self):
        """رگرسیون: نسخه‌ی اولِ این تابع ``prefetch_related`` را با یک
        ``.filter()`` دیگر رویِ ``menu.items`` ترکیب می‌کرد که کشِ
        prefetch را بی‌اثر می‌گذاشت — این تست تضمین می‌کند تعدادِ کوئریِ
        خودِ این section (نه کلِ صفحه — سکشن‌های bootstrap-شده‌ی دیگر
        کوئریِ خودشان را دارند) با تعدادِ آیتم‌های منو رشد نمی‌کند."""
        from apps.catalog.models import Category
        from apps.content.models import DestinationType, Menu, MenuItem

        def _query_count_for(item_count):
            store = _akhlaghi()
            MenuItem.objects.filter(menu__store=store, menu__location=Menu.Location.HEADER).delete()
            Menu.objects.filter(store=store, location=Menu.Location.HEADER).delete()
            menu = Menu.objects.create(store=store, title="منوی کوئری", location=Menu.Location.HEADER, is_active=True)
            for i in range(item_count):
                category = Category.objects.create(store=store, name=f"دسته {i}", slug=f"ql-q-{item_count}-{i}", is_active=True)
                MenuItem.objects.create(
                    menu=menu, title=f"آیتم {i}", display_order=i, is_active=True,
                    destination_type=DestinationType.CATEGORY, destination_category=category,
                )
            draft = svc.get_or_create_draft(store)
            draft.sections.all().delete()
            StorefrontSection.objects.create(
                version=draft, section_key="quick_links", order=900, settings={"title": "", "menu_id": menu.pk},
            )
            with CaptureQueriesContext(connection) as ctx:
                item = self._items_for(draft, store)[0]
                self.assertEqual(len(item["context"]["quick_link_items"]), item_count)
            return len(ctx.captured_queries)

        small_count = _query_count_for(2)
        large_count = _query_count_for(15)
        self.assertEqual(small_count, large_count)

    def test_menu_from_another_store_never_leaks(self):
        from apps.content.models import Menu

        store = _akhlaghi()
        other_store = Store.objects.exclude(pk=store.pk).first()
        if other_store is None:
            self.skipTest("no second store fixture available")
        other_menu = Menu.objects.create(store=other_store, title="منوی فروشگاه دیگر", location=Menu.Location.HEADER, is_active=True)
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="quick_links", order=900,
            settings={"title": "", "menu_id": other_menu.pk},
        )
        item = self._items_for(draft, store)[0]
        self.assertEqual(item["context"]["quick_link_items"], [])


class VideoSectionRenderTests(TestCase):
    def setUp(self):
        cache.clear()

    def _items_for(self, draft, store):
        items = build_render_items(draft, store)
        return [i for i in items if i["section"].section_key == "video_section"]

    def test_no_url_renders_nothing(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(version=draft, section_key="video_section", order=900)
        item = self._items_for(draft, store)[0]
        self.assertIsNone(item["context"]["video_embed_url"])
        self.assertFalse(item["context"]["video_is_instagram"])

    def test_youtube_url_produces_embed_url(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=900,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "caption": ""},
        )
        item = self._items_for(draft, store)[0]
        self.assertIn("youtube.com/embed/dQw4w9WgXcQ", item["context"]["video_embed_url"])

    def test_instagram_url_never_produces_an_iframe_only_a_permalink(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=900,
            settings={"title": "", "video_url": "https://instagram.com/p/ABC123xyz/", "caption": ""},
        )
        item = self._items_for(draft, store)[0]
        self.assertIsNone(item["context"]["video_embed_url"])
        self.assertTrue(item["context"]["video_is_instagram"])
        self.assertIsNotNone(item["context"]["video_permalink"])

    def test_two_independent_video_sections_show_different_videos(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section_a = StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=900,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "caption": ""},
        )
        section_b = StorefrontSection.objects.create(
            version=draft, section_key="video_section", order=901,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "caption": ""},
        )
        items = self._items_for(draft, store)
        urls_by_section = {i["context"]["section"].pk: i["context"]["video_embed_url"] for i in items}
        self.assertIn("aaaaaaaaaaa", urls_by_section[section_a.pk])
        self.assertIn("bbbbbbbbbbb", urls_by_section[section_b.pk])


class PageContextPassthroughTests(TestCase):
    """Phase 5: ``build_page_render_items``یِ ``page_context`` را عیناً و
    بدونِ کوئریِ اضافه به سازنده‌یِ context-awareِ همان section_key پاس
    می‌دهد — این تست مکانیزم را مستقل از هر نوعِ section واقعیِ آینده
    اثبات می‌کند (با یک builderِ آزمایشی موقت در ``_CONTEXT_AWARE_BUILDERS``)."""

    def setUp(self):
        cache.clear()
        from apps.storefront_builder.services import render_service
        self.render_service = render_service

    def test_page_context_reaches_a_context_aware_builder_unchanged(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        page = draft.get_page("cart")
        page.sections.all().delete()
        StorefrontSection.objects.create(page=page, section_key="trust_features", order=0)

        received = {}

        def _fake_builder(store_arg, section_arg, page_context_arg):
            received["store"] = store_arg
            received["page_context"] = page_context_arg
            return {"marker": "PAGE-CONTEXT-REACHED"}

        with mock.patch.dict(
            self.render_service._CONTEXT_AWARE_BUILDERS, {"trust_features": _fake_builder},
        ):
            sentinel = {"cart": "SENTINEL-CART-OBJECT"}
            items = self.render_service.build_page_render_items(page, store, page_context=sentinel)

        self.assertEqual(received["store"], store)
        self.assertIs(received["page_context"], sentinel)
        self.assertEqual(items[0]["context"]["marker"], "PAGE-CONTEXT-REACHED")

    def test_missing_page_context_defaults_to_empty_dict_not_none(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        page = draft.get_page("cart")
        StorefrontSection.objects.create(page=page, section_key="trust_features", order=0)

        received = {}

        def _fake_builder(store_arg, section_arg, page_context_arg):
            received["page_context"] = page_context_arg
            return {}

        with mock.patch.dict(
            self.render_service._CONTEXT_AWARE_BUILDERS, {"trust_features": _fake_builder},
        ):
            self.render_service.build_page_render_items(page, store)

        self.assertEqual(received["page_context"], {})

    def test_non_context_aware_sections_unaffected_by_page_context(self):
        """بخش‌هایِ معمولی (مثلِ trust_features واقعی، بدونِ mock) باید
        دقیقاً همان context را بگیرند، صرف‌نظر از اینکه page_context چه
        باشد — مکانیزمِ جدید نباید رفتارِ ۱۷ نوعِ موجود را تغییر دهد."""
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        page = draft.get_page("home")
        StorefrontSection.objects.create(page=page, section_key="trust_features", order=0)

        without = self.render_service.build_page_render_items(page, store)
        with_noise = self.render_service.build_page_render_items(
            page, store, page_context={"anything": "irrelevant-to-trust-features"},
        )
        self.assertEqual(without[0]["context"]["settings"], with_noise[0]["context"]["settings"])


class ProductDetailContextAwareSectionsTests(TestCase):
    """Phase 5: چهار نوعِ context-aware صفحه محصول — داده از
    ``page_context`` می‌آید (شبیه‌سازیِ همان دیکشنری که
    ``build_product_detail_context`` واقعاً می‌سازد)، هرگز کوئریِ تازه."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.vendor = Vendor.objects.create(store=self.store, name="فروشنده رندر", slug="render-vendor")
        self.category = Category.objects.create(store=self.store, name="دسته رندر", slug="render-cat", is_active=True)
        self.product = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای رندر",
            slug="render-product", sku="RENDER-1", price=Decimal("50000"), stock=3, status=Product.Status.ACTIVE,
        )
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page("product_detail")
        # Phase 5: از فازِ ۹ به بعد این صفحه چیدمانِ پیش‌فرضِ خودش را دارد
        # (product_main/product_description/...) — این کلاس هر بار دقیقاً
        # یک section مشخص می‌سازد و انتظار دارد ``len(items) == 1`` باشد،
        # پس باید ابتدا آن پیش‌فرض‌ها را پاک کند.
        self.page.sections.all().delete()

    def _page_context(self, **overrides):
        base = {
            "product": self.product,
            "variant_selector": {"mode": "none"},
            "product_price_json": {"price": 50000, "regular": 50000, "savings": 0, "stock": 3, "sku": "RENDER-1"},
            "gallery_slides": [],
            "review_count": 2,
            "spec_variant_summary": {},
            "approved_reviews": [],
            "rating_breakdown": [],
            "can_review": False,
            "product_videos": [],
            "related_products": [],
        }
        base.update(overrides)
        return base

    def _item_for(self, section_key, page_context):
        StorefrontSection.objects.create(page=self.page, section_key=section_key, order=0)
        items = build_page_render_items(self.page, self.store, page_context=page_context)
        self.assertEqual(len(items), 1)
        return items[0]

    def test_product_main_receives_the_current_product(self):
        item = self._item_for("product_main", self._page_context())
        self.assertEqual(item["context"]["product"], self.product)
        self.assertEqual(item["context"]["review_count"], 2)

    def test_product_main_fails_safe_without_a_product(self):
        item = self._item_for("product_main", {})
        self.assertNotIn("product", item["context"])

    def test_product_description_receives_review_and_spec_data(self):
        item = self._item_for("product_description", self._page_context(spec_variant_summary={"رنگ": "قرمز"}))
        self.assertEqual(item["context"]["product"], self.product)
        self.assertEqual(item["context"]["spec_variant_summary"], {"رنگ": "قرمز"})

    def test_product_description_fails_safe_without_a_product(self):
        item = self._item_for("product_description", {})
        self.assertNotIn("product", item["context"])

    def test_product_video_passes_through_video_list(self):
        item = self._item_for("product_video", self._page_context(product_videos=[{"title": "v"}]))
        self.assertEqual(item["context"]["product_videos"], [{"title": "v"}])

    def test_product_video_fails_safe_without_a_product(self):
        item = self._item_for("product_video", {})
        self.assertNotIn("product_videos", item["context"])

    def test_related_products_passes_through_queryset(self):
        other = Product.objects.create(
            store=self.store, vendor=self.vendor, category=self.category, name="کالای مرتبط",
            slug="render-related", sku="RENDER-2", price=Decimal("10000"), stock=1, status=Product.Status.ACTIVE,
        )
        item = self._item_for("related_products", self._page_context(related_products=[other]))
        self.assertEqual(list(item["context"]["related_products"]), [other])

    def test_related_products_fails_safe_without_a_product(self):
        item = self._item_for("related_products", {})
        self.assertNotIn("related_products", item["context"])

    def test_context_aware_sections_only_resolve_on_product_detail_page(self):
        """صفحاتِ دیگر (مثلاً cart) اصلاً امکانِ داشتنِ این section_key را
        ندارند (allowlist سمتِ سرور در ``storefront_section_add`` رد
        می‌کند) — این تست خودِ لایه‌یِ رندر را مستقل اثبات می‌کند: حتی اگر
        یک ردیفِ StorefrontSection نامعتبر (دستکاریِ مستقیمِ دیتابیس) روی
        صفحه‌ی اشتباه بنشیند، رندر همچنان بدونِ کرش کار می‌کند."""
        cart_page = self.draft.get_page("cart")
        cart_page.sections.all().delete()
        StorefrontSection.objects.create(page=cart_page, section_key="product_main", order=0)
        items = build_page_render_items(cart_page, self.store, page_context={"cart": None})
        self.assertEqual(len(items), 1)
        self.assertNotIn("product", items[0]["context"])


class ProductListingContextAwareSectionTests(TestCase):
    """Phase 5: ``product_listing`` روی هر دو نوعِ صفحه (listing/search)
    مجاز است و همیشه (حتی بدونِ هیچ کلیدی در page_context) بی‌خطا رندر
    می‌شود — برخلافِ چهار نوعِ صفحه محصول، هیچ «شیءِ لازم»ی ندارد."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)

    def test_receives_listing_context_unchanged(self):
        page = self.draft.get_page("listing")
        page.sections.all().delete()
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        page_context = {
            "page_obj": "PAGE-OBJ-SENTINEL", "products": ["p1"], "query": "", "sort_key": "newest",
            "sort_options": {"newest": ("x", "جدیدترین")}, "filter_categories": [], "brands": [],
            "selected_category": "", "selected_brand": "", "min_price": "", "max_price": "",
            "discounted_only": False, "querystring": "",
        }
        items = build_page_render_items(page, self.store, page_context=page_context)
        self.assertEqual(items[0]["context"]["page_obj"], "PAGE-OBJ-SENTINEL")
        self.assertEqual(items[0]["context"]["products"], ["p1"])

    def test_allowed_on_search_page_too(self):
        page = self.draft.get_page("search")
        page.sections.all().delete()
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        items = build_page_render_items(page, self.store, page_context={})
        self.assertEqual(len(items), 1)

    def test_missing_page_context_keys_default_safely(self):
        page = self.draft.get_page("listing")
        page.sections.all().delete()
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        items = build_page_render_items(page, self.store, page_context={})
        context = items[0]["context"]
        self.assertEqual(context["query"], "")
        self.assertEqual(context["discounted_only"], False)
        self.assertIsNone(context["page_obj"])


class CollectionContextAwareSectionsTests(TestCase):
    """Phase 5: ``collection_header``/``collection_products`` — «کالکشنِ
    جاری» همیشه از ``page_context`` می‌آید، هرگز از یک ID در settings."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page("collection")
        self.page.sections.all().delete()

    def _item_for(self, section_key, page_context):
        StorefrontSection.objects.create(page=self.page, section_key=section_key, order=0)
        items = build_page_render_items(self.page, self.store, page_context=page_context)
        self.assertEqual(len(items), 1)
        return items[0]

    def test_collection_header_receives_current_collection(self):
        from apps.catalog.services import collection_service

        collection = collection_service.create_collection(self.store, name="کالکشنِ رندر هدر")
        item = self._item_for("collection_header", {"collection": collection})
        self.assertEqual(item["context"]["collection"], collection)

    def test_collection_header_fails_safe_without_a_collection(self):
        item = self._item_for("collection_header", {})
        self.assertNotIn("collection", item["context"])

    def test_collection_products_receives_products_and_page_obj(self):
        from apps.catalog.services import collection_service

        collection = collection_service.create_collection(self.store, name="کالکشنِ رندر محصولات")
        item = self._item_for(
            "collection_products", {"collection": collection, "products": ["p1"], "page_obj": "OBJ"},
        )
        self.assertEqual(item["context"]["collection"], collection)
        self.assertEqual(item["context"]["products"], ["p1"])
        self.assertEqual(item["context"]["page_obj"], "OBJ")

    def test_collection_products_fails_safe_without_a_collection(self):
        item = self._item_for("collection_products", {})
        self.assertNotIn("collection", item["context"])
        self.assertNotIn("products", item["context"])


class CartContextAwareSectionsTests(TestCase):
    """Phase 5: ``cart_items``/``cart_summary`` — سبد همیشه در page_context
    حاضر است (حتی سبدِ خالی/None، که ``_cart_context`` خودش fail-safe
    مدیریت می‌کند)، پس این دو (برخلافِ چهار نوعِ صفحه محصول) هرگز نیازی
    به یک early-return «چیزی رندر نکن» ندارند — خودِ template تصمیم
    می‌گیرد."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.page = self.draft.get_page("cart")
        self.page.sections.all().delete()

    def _item_for(self, section_key, page_context):
        StorefrontSection.objects.create(page=self.page, section_key=section_key, order=0)
        items = build_page_render_items(self.page, self.store, page_context=page_context)
        self.assertEqual(len(items), 1)
        return items[0]

    def test_cart_items_passes_through_items_and_count(self):
        item = self._item_for("cart_items", {"cart": "CART", "cart_items": ["i1"], "item_count": 3})
        self.assertEqual(item["context"]["cart"], "CART")
        self.assertEqual(item["context"]["cart_items"], ["i1"])
        self.assertEqual(item["context"]["item_count"], 3)

    def test_cart_items_defaults_safely_on_empty_page_context(self):
        item = self._item_for("cart_items", {})
        self.assertIsNone(item["context"]["cart"])
        self.assertEqual(item["context"]["cart_items"], [])
        self.assertEqual(item["context"]["item_count"], 0)

    def test_cart_summary_passes_through_totals(self):
        item = self._item_for("cart_summary", {"cart": "CART", "item_count": 2, "totals": {"grand_total": 5000}})
        self.assertEqual(item["context"]["totals"], {"grand_total": 5000})
        self.assertEqual(item["context"]["item_count"], 2)


class BuildDefaultRenderItemsTests(TestCase):
    """Phase 5: Storeای که هرگز Storefront V2 منتشر نکرده باید هنوز هم
    دقیقاً همان محتوایِ سخت‌کدشده‌ی قدیمی را رویِ پنج صفحه‌ی محصول/لیست/
    کالکشن/جستجو/سبد ببیند — بدونِ نیاز به هیچ ``StorefrontPage``/
    ``StorefrontSection`` واقعی در دیتابیس."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_returns_same_keys_as_build_default_non_home_sections(self):
        from apps.storefront_builder.services import bootstrap_service
        from apps.storefront_builder.services.render_service import build_default_render_items

        for page_type in ("product_detail", "listing", "collection", "search", "cart"):
            items = build_default_render_items(page_type, self.store)
            expected_keys = [s["section_key"] for s in bootstrap_service.build_default_non_home_sections(page_type)]
            self.assertEqual([i["section"].section_key for i in items], expected_keys, page_type)

    def test_home_returns_empty_list(self):
        from apps.storefront_builder.services.render_service import build_default_render_items
        self.assertEqual(build_default_render_items("home", self.store), [])

    def test_synthesized_sections_are_never_persisted(self):
        from apps.storefront_builder.models import StorefrontSection
        from apps.storefront_builder.services.render_service import build_default_render_items

        before = StorefrontSection.objects.count()
        items = build_default_render_items("cart", self.store)
        after = StorefrontSection.objects.count()
        self.assertEqual(before, after)
        for item in items:
            self.assertIsNone(item["section"].pk)

    def test_page_context_still_reaches_context_aware_builders(self):
        from apps.storefront_builder.services.render_service import build_default_render_items

        items = build_default_render_items("cart", self.store, page_context={"cart": "SENTINEL", "item_count": 4})
        cart_items_item = next(i for i in items if i["section"].section_key == "cart_items")
        self.assertEqual(cart_items_item["context"]["cart"], "SENTINEL")
        self.assertEqual(cart_items_item["context"]["item_count"], 4)



class BrandCarouselViewAllAnchorTests(TestCase):
    """V02 — the "مشاهده همه" (view-all) anchor contract across the three
    Brand display variants and the destination resolution rules:

      * grid / carousel with a RESOLVED destination  -> anchor present.
      * beauty_tabs, even with a resolved destination  -> anchor ABSENT
        (suppressed in the template's beauty_tabs branch).
      * grid / carousel with no / "none" / invalid destination -> anchor
        ABSENT (never a dead button).

    Drives the real ``_brand_carousel_context`` (view_all_url resolution)
    AND the real ``brand_carousel.html`` template (anchor rendering), so
    both the context decision and the presentation decision are proven.
    """

    def setUp(self):
        from apps.catalog.models import Brand

        cache.clear()
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()
        Brand.objects.create(store=self.store, name="برند V02", slug="v02-brand", is_active=True)

    def _context(self, *, display_mode, show_view_all, destination):
        from apps.storefront_builder.services.render_service import _brand_carousel_context

        section = StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=0,
            settings={
                "display_mode": display_mode,
                "show_view_all": show_view_all,
                "brand_ids": [],
                "destination": destination,
            },
        )
        return _brand_carousel_context(self.store, section)

    def _html(self, ctx, *, display_mode):
        from django.template.loader import render_to_string

        settings = {**ctx["brand_carousel_settings"], "display_mode": display_mode}
        return render_to_string(
            "storefront_builder/sections/brand_carousel.html",
            {
                "brands": ctx["brands"],
                "brand_carousel_settings": settings,
                "view_all_url": ctx["view_all_url"],
            },
        )

    # -- resolved destination (search -> product-list url) -------------------
    _SEARCH_DEST = {"destination_type": "search"}

    def test_grid_with_resolved_destination_shows_anchor(self):
        ctx = self._context(display_mode="grid", show_view_all=True, destination=self._SEARCH_DEST)
        self.assertIsNotNone(ctx["view_all_url"])
        html = self._html(ctx, display_mode="grid")
        self.assertIn('class="more"', html)
        self.assertIn("مشاهده همه", html)

    def test_carousel_with_resolved_destination_shows_anchor(self):
        ctx = self._context(display_mode="carousel", show_view_all=True, destination=self._SEARCH_DEST)
        self.assertIsNotNone(ctx["view_all_url"])
        html = self._html(ctx, display_mode="carousel")
        self.assertIn('class="more"', html)
        self.assertIn("مشاهده همه", html)

    def test_beauty_tabs_suppresses_anchor_even_with_resolved_destination(self):
        ctx = self._context(display_mode="beauty_tabs", show_view_all=True, destination=self._SEARCH_DEST)
        # The context still resolves a real url...
        self.assertIsNotNone(ctx["view_all_url"])
        # ...but the beauty_tabs template branch never renders the anchor.
        html = self._html(ctx, display_mode="beauty_tabs")
        self.assertNotIn('class="more"', html)
        self.assertNotIn("مشاهده همه", html)

    # -- no / none / invalid destination -> no anchor ------------------------
    def test_grid_with_none_destination_has_no_anchor(self):
        ctx = self._context(
            display_mode="grid", show_view_all=True, destination={"destination_type": "none"},
        )
        self.assertIsNone(ctx["view_all_url"])
        html = self._html(ctx, display_mode="grid")
        self.assertNotIn('class="more"', html)

    def test_carousel_with_missing_destination_has_no_anchor(self):
        ctx = self._context(display_mode="carousel", show_view_all=True, destination={})
        self.assertIsNone(ctx["view_all_url"])
        html = self._html(ctx, display_mode="carousel")
        self.assertNotIn('class="more"', html)

    def test_grid_with_invalid_destination_reference_has_no_anchor(self):
        """A destination pointing at a non-existent (or other-store) resource
        resolves to url=None — never a dead anchor."""
        ctx = self._context(
            display_mode="grid", show_view_all=True,
            destination={"destination_type": "brand", "destination_id": 99999999},
        )
        self.assertIsNone(ctx["view_all_url"])
        html = self._html(ctx, display_mode="grid")
        self.assertNotIn('class="more"', html)

    def test_show_view_all_false_never_resolves_url_even_with_destination(self):
        ctx = self._context(display_mode="grid", show_view_all=False, destination=self._SEARCH_DEST)
        self.assertIsNone(ctx["view_all_url"])
        html = self._html(ctx, display_mode="grid")
        self.assertNotIn('class="more"', html)

    def test_resolved_anchor_href_points_at_the_resolved_destination(self):
        from django.urls import reverse

        ctx = self._context(display_mode="grid", show_view_all=True, destination=self._SEARCH_DEST)
        html = self._html(ctx, display_mode="grid")
        self.assertIn(f'href="{reverse("catalog:product-list")}"', html)
