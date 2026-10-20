"""صفحه اصلی عمومی و سازنده بصری — تصمیم ۳ و ۱۱ کاربر: فروشگاه‌های موجود
تا اولین Publish دستی بدون تغییر از مسیر قدیمی رندر می‌شوند؛ بعد از آن،
صفحه‌ی عمومی همیشه نسخه‌ی منتشرشده را می‌بیند — هرگز Draft را."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

HOST = "sfb-public-home.example.com"


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


@override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
class PublicHomepageIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = Store.objects.get(slug="akhlaghi")
        _verified_domain(self.store, HOST)

    def test_engine_homepage_is_served_even_when_never_published(self):
        """There is no legacy homepage: a Store that never published gets the deterministic engine default."""
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home_visual.html", template_names)
        self.assertNotIn("catalog/home.html", template_names)

    def test_engine_homepage_is_served_while_an_unpublished_draft_exists(self):
        svc.get_or_create_draft(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home_visual.html", template_names)

    def test_visual_homepage_used_after_first_publish(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        template_names = [t.name for t in resp.templates if t.name]
        self.assertIn("catalog/home_visual.html", template_names)
        self.assertNotIn("catalog/home.html", template_names)

    def test_public_page_never_exposes_section_ids(self):
        """چکپوینتِ Direct Visual Editing: data-section-id فقط برایِ
        Preview (staff-only) اضافه می‌شود — صفحه‌ی عمومی هرگز نباید
        شناسه‌ی دیتابیسِ داخلی را در HTML به بازدیدکننده نشان دهد."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "data-section-id")

    def test_public_page_never_exposes_inline_canvas_toolbar(self):
        """Phase 8 P0-6 — ابزارِ شناورِ Canvas هم دقیقاً همان محافظتی را
        دارد که data-section-id دارد: فقط Preview، هرگز صفحه‌ی عمومی."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "sfb-rsec-toolbar")

    def test_public_page_shows_published_content_not_later_draft_edits(self):
        """تصمیم ۱۱ کاربر: صفحه عمومی هرگز Draft را نمی‌بیند — ویرایش‌های
        بعد از Publish تا Publish دوباره روی صفحه عمومی ظاهر نمی‌شوند."""
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=999,
            settings={"body_html": "PUBLIC-SHOULD-NEVER-SEE-THIS-DRAFT-MARKER"},
        )
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "PUBLIC-SHOULD-NEVER-SEE-THIS-DRAFT-MARKER")

    def test_header_config_toggle_hides_cart_icon(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = {**(draft.header_config or {}), "show_cart": False}
        draft.save(update_fields=["header_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, 'id="cart-count"')

    def test_footer_config_toggle_hides_copyright(self):
        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = {**(draft.footer_config or {}), "show_copyright": False}
        draft.save(update_fields=["footer_config"])
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, 'class="copy"')

    def test_visual_footer_uses_live_footer_settings_and_dense_columns(self):
        from apps.content.models import FooterSettings

        fs = FooterSettings.load(store=self.store)
        fs.description = "توضیح اختصاصی فوتر تست"
        fs.address = "تهران، آدرس اختصاصی تست"
        fs.phone = "02112345678"
        fs.working_hours = "شنبه تا چهارشنبه ۹ تا ۱۷"
        fs.copyright_text = "© متن اختصاصی تست"
        fs.save(update_fields=["description", "address", "phone", "working_hours", "copyright_text"])

        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)

        self.assertContains(resp, 'class="footer-col footer-col-address"')
        self.assertContains(resp, "توضیح اختصاصی فوتر تست")
        self.assertContains(resp, "تهران، آدرس اختصاصی تست")
        self.assertContains(resp, "02112345678")
        self.assertContains(resp, "شنبه تا چهارشنبه ۹ تا ۱۷")
        self.assertContains(resp, "© متن اختصاصی تست")

    def test_newsletter_block_requires_both_layout_toggle_and_live_footer_setting(self):
        """چکپوینتِ ۹: قبل از این رفعِ باگ، ``footer_config.show_newsletter``
        هیچ اثری در رندر نداشت (فرگمنتِ خبرنامه اصلاً از این کلید
        استفاده نمی‌کرد) — این آزمون هر دو حالتِ لازم را تأیید می‌کند:
        هر دو باید True باشند تا بلوکِ خبرنامه نمایش داده شود."""
        from apps.content.models import FooterSettings

        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = {**(draft.footer_config or {}), "show_newsletter": True}
        draft.save(update_fields=["footer_config"])
        svc.publish(self.store)

        fs = FooterSettings.load(store=self.store)
        fs.show_newsletter = False
        fs.save(update_fields=["show_newsletter"])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, 'class="news"')

        fs.show_newsletter = True
        fs.newsletter_title = "عضویتِ تستی"
        fs.save(update_fields=["show_newsletter", "newsletter_title"])
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'class="news"')
        self.assertContains(resp, "عضویتِ تستی")

    def test_newsletter_block_hidden_when_layout_toggle_off_even_if_live_setting_on(self):
        from apps.content.models import FooterSettings

        fs = FooterSettings.load(store=self.store)
        fs.show_newsletter = True
        fs.save(update_fields=["show_newsletter"])

        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = {**(draft.footer_config or {}), "show_newsletter": False}
        draft.save(update_fields=["footer_config"])
        svc.publish(self.store)

        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, 'class="news"')

    def test_unknown_section_type_in_published_version_never_crashes_public_page(self):
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(version=draft, section_key="a_removed_legacy_type", order=999)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)

    def test_published_product_section_collection_source_renders_products(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor
        from apps.catalog.services import collection_service

        collection = collection_service.create_collection(self.store, name="وایر شمع صفحه اصلی")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده صفحه اصلی", slug="v-home-ps")
        category = Category.objects.create(store=self.store, name="دسته صفحه اصلی", slug="c-home-ps")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای صفحه اصلی خاص",
            slug="home-ps-p1", sku="SKU-HOME-PS-1", price=Decimal("10000"), status=Product.Status.ACTIVE, stock=5,
        )
        collection_service.add_product(collection, product)

        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=999,
            settings={
                "data_source": "collection", "source_id": collection.pk, "product_ids": [],
                "item_limit": 8, "display_mode": "carousel", "show_view_all": True,
                "title": "وایر شمع", "subtitle": "",
            },
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "وایر شمع")
        self.assertContains(resp, "کالای صفحه اصلی خاص")

    def test_published_product_section_with_deleted_collection_does_not_crash(self):
        """Acceptance Batch 1 (post-U11): a product_section resolving to
        zero products (here: a deleted/nonexistent collection) must still
        never crash — the original point of this test — but now correctly
        keeps its place on the public page with a neutral, non-administrative
        note (owner contract: template-owned sections are never dropped for
        lack of data)."""
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=999,
            settings={
                "data_source": "collection", "source_id": 999999, "product_ids": [],
                "item_limit": 8, "display_mode": "grid", "show_view_all": True,
                "title": "کالکشن حذف‌شده", "subtitle": "",
            },
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "کالکشن حذف‌شده")                     # the section (its title) stays
        self.assertContains(resp, 'data-empty-state="product"')
        self.assertNotContains(resp, "با افزودن کالای واجد شرایط")      # no Studio instruction for shoppers

    def test_view_all_link_actually_renders_on_public_page(self):
        """رگرسیون: ``view_all_url`` قبلاً در include مشترکِ
        home_visual.html/preview.html پاس داده نمی‌شد، پس دکمه‌ی
        «مشاهده همه» هرگز رندر نمی‌شد — با اضافه‌شدنِ
        responsive_section_wrapper.html اصلاح شد."""
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor
        from apps.catalog.services import collection_service

        collection = collection_service.create_collection(self.store, name="کالکشن دکمه مشاهده همه")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده دکمه", slug="v-viewall")
        category = Category.objects.create(store=self.store, name="دسته دکمه", slug="c-viewall")
        product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای دکمه مشاهده همه",
            slug="viewall-p1", sku="SKU-VIEWALL-1", price=Decimal("10000"), status=Product.Status.ACTIVE, stock=5,
        )
        collection_service.add_product(collection, product)

        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=999,
            settings={
                "data_source": "collection", "source_id": collection.pk, "product_ids": [],
                "item_limit": 8, "display_mode": "carousel", "show_view_all": True,
                "title": "دکمه مشاهده همه", "subtitle": "",
            },
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "مشاهده همه")
        from urllib.parse import quote
        self.assertContains(resp, f"/collections/{quote(collection.slug)}/")
