from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.authorization import STOREFRONT_LAYOUT_MANAGE
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "sfb-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


class StorefrontBuilderViewsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="sfb_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="sfb_owner", password="pass12345")
        # Pre-Task-10 CORRECTIVE closure (Item 2, second legacy retirement
        # pass) — editor.html's own composition/settings/toggle-lock/reset/
        # Appearance-Header-Footer body now renders ONLY for a Store pinned
        # back to the legacy editor (``r4_editor_enabled=False``); a Store
        # on the live default (True) sees the new minimal compatibility
        # surface instead (see editor.html's own top-of-file comment).
        # Every test below this point was written against — and still
        # genuinely exercises — the FULL legacy editor body: that body must
        # keep working correctly for a Store that really is pinned back, so
        # this fixture pins every test in this file (and every file that
        # imports this base case) to that still-required code path, rather
        # than the now-separate minimal-surface behavior EditorAccessTests
        # and R4EditorMinimalCompatibilitySurfaceTests below test directly.
        layout = svc.get_or_create_layout(self.store)
class EditorAccessTests(StorefrontBuilderViewsTestCase):


    def test_anonymous_denied(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/admin-portal/login/", resp.url)
        self.assertIn("admin_return=", resp.url)

    def test_content_editor_without_storefront_permission_denied(self):
        from apps.stores.authorization import ROLE_PERMISSIONS
        self.assertNotIn(STOREFRONT_LAYOUT_MANAGE, ROLE_PERMISSIONS[StoreMembership.Role.ANALYST])
        analyst = User.objects.create_user(username="sfb_analyst", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=analyst, role=StoreMembership.Role.ANALYST,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        client = Client(HTTP_HOST=HOST)
        client.login(username="sfb_analyst", password="pass12345")
        resp = client.get(reverse("dashboard:storefront-builder-editor"))
        self.assertEqual(resp.status_code, 403)


    def test_preview_accessible_to_staff_only(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertEqual(resp.status_code, 200)

    def test_preview_exposes_section_ids_for_direct_selection(self):
        """چکپوینتِ Direct Visual Editing — برخلافِ صفحه‌ی عمومی، Preview
        (فقط staff همین فروشگاه) باید data-section-id داشته باشد تا کلیک
        روی یک section در Preview بتواند تنظیماتِ همان section را باز کند."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-section-id")
        self.assertContains(resp, "data-section-key")

    def test_home_preview_does_not_inject_store_name_title_before_sections(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "home"})
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'class="storefront-page-title"')

    def test_preview_exposes_inline_canvas_toolbar(self):
        """Phase 8 P0-6 — ابزارِ شناورِ روی خودِ section در Canvas؛ فقط
        در Preview (نه صفحه‌ی عمومی)، دقیقاً کنارِ data-section-id."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "sfb-rsec-toolbar")
        self.assertContains(resp, 'data-cmd="duplicate"')
        # A visible placed V3 Block is removed independently from its Cell;
        # clearing the whole Cell remains a separate explicit action used by
        # the Inspector/hidden-content chrome.
        self.assertContains(resp, "data-block-remove=")

    # Phase 4: هدر/فوتر همان دکوریتورهای مشترکِ ``@staff_required`` +
    # ``@permission_required(STOREFRONT_LAYOUT_MANAGE)`` را (که در بالا
    # برای editor/preview اثبات شده) استفاده می‌کنند — این دو تست فقط
    # همان مکانیزم را صراحتاً روی دو Endpoint این فاز هم اثبات می‌کنند.


    def test_preview_never_shows_another_stores_draft(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="sfb-other", admin_subdomain="sfb-other", status=Store.Status.ACTIVE,
        )
        other_staff = User.objects.create_user(username="sfb_other_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=other_store, user=other_staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(version=draft, section_key="rich_text", order=0, settings={"body_html": "SECRET-STORE-A-TEXT"})

        other_store.admin_subdomain = "sfb-other-host"
        other_store.save(update_fields=["admin_subdomain"])
        other_client = Client(HTTP_HOST="sfb-other-host.rastisi.localhost")
        other_client.login(username="sfb_other_owner", password="pass12345")
        resp = other_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertNotContains(resp, "SECRET-STORE-A-TEXT")


class PrototypeV2Phase2InteractionFoundationTests(StorefrontBuilderViewsTestCase):
    """Phase 2.1 — the single-screen builder exposes real section operations
    and reports unsaved inspector edits truthfully without inventing new write paths."""

    def _first_section(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        page = draft.get_page(StorefrontPage.PageType.HOME)
        section = page.sections.order_by("order", "id").first()
        self.assertIsNotNone(section)
        return section


    def test_locked_section_is_visibly_locked_and_cannot_drag_or_remove_from_canvas(self):
        section = self._first_section()
        section.is_locked = True
        section.save(update_fields=["is_locked", "updated_at"])
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, f'data-section-id="{section.pk}"')
        self.assertContains(resp, 'data-section-locked="1"')
        self.assertContains(resp, "sfb-rsec-locked")
        self.assertContains(resp, 'data-cmd="lock"')
        self.assertContains(resp, 'draggable="false"')


class SectionActionTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()


    def test_collapse_toggle_default_is_false(self):
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        self.assertFalse(section.collapsed_in_editor)


class ProductSectionProductSearchTests(StorefrontBuilderViewsTestCase):
    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.section = StorefrontSection.objects.create(version=self.draft, section_key="product_section", order=0)

    def test_empty_query_returns_no_results(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-section-product-search", args=[self.section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"pp-result-row", resp.content)

    def test_matching_query_returns_result(self):
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        vendor = Vendor.objects.create(store=self.store, name="فروشنده جست‌وجو", slug="v-ps-search")
        category = Category.objects.create(store=self.store, name="دسته جست‌وجو", slug="c-ps-search")
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای جست‌وجوی خاص",
            slug="ps-search-p1", sku="SKU-PS-SEARCH-1", price=Decimal("10000"), status=Product.Status.ACTIVE,
        )
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-product-search", args=[self.section.pk]), {"q": "جست‌وجوی خاص"},
        )
        self.assertContains(resp, "کالای جست‌وجوی خاص")

    def test_other_store_section_pk_rejected(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر جست‌وجو", slug="ps-search-other-store", admin_subdomain="ps-search-other-store",
        )
        other_draft = svc.get_or_create_draft(other_store)
        other_section = StorefrontSection.objects.create(version=other_draft, section_key="product_section", order=0)
        resp = self.client.get(
            reverse("dashboard:storefront-builder-section-product-search", args=[other_section.pk]), {"q": "test"},
        )
        self.assertEqual(resp.status_code, 404)


class PublishDiscardRestoreViewTests(StorefrontBuilderViewsTestCase):


    def test_history_lists_versions(self):
        svc.get_or_create_draft(self.store)
        svc.publish(self.store)
        resp = self.client.get(reverse("dashboard:storefront-builder-history"))
        self.assertEqual(resp.status_code, 200)


class HeaderFooterEditorTests(StorefrontBuilderViewsTestCase):


    def test_header_responsive_attribute_reaches_rendered_preview(self):
        draft = svc.get_or_create_draft(self.store)
        draft.header_config = svc.validate_header_config({
            "show_search": True, "show_cart": True,
            "responsive": {"show_search": {"hide_on_tablet": False, "hide_on_mobile": True}},
        })
        draft.save(update_fields=["header_config"])
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-shell-hide-mobile")
        self.assertNotContains(resp, "data-shell-hide-tablet")

    def test_footer_responsive_attribute_reaches_rendered_preview(self):
        draft = svc.get_or_create_draft(self.store)
        draft.footer_config = svc.validate_footer_config({
            "show_copyright": True,
            "responsive": {"show_copyright": {"hide_on_tablet": True, "hide_on_mobile": False}},
        })
        draft.save(update_fields=["footer_config"])
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "data-shell-hide-tablet")

    def test_header_responsive_absent_by_default_no_hide_attributes(self):
        """پیش‌فرض (بدونِ تنظیمِ صریح) یعنی نمایان در همه‌جا — هیچ
        data-shell-hide-* ای نباید رندر شود."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertNotContains(resp, "data-shell-hide-mobile")
        self.assertNotContains(resp, "data-shell-hide-tablet")


class RenderedPreviewIntegrationTests(StorefrontBuilderViewsTestCase):
    """رندرِ واقعیِ HTML از طریقِ preview endpoint — نه صرفاً بررسیِ دیکشنریِ
    context (که ``test_render_service.py`` انجام می‌دهد). این کلاس مشخصاً
    برایِ گرفتنِ باگ‌هایی نوشته شده که فقط در سطحِ template اتفاق می‌افتند —
    مثلاً یک context key که در سرویس درست ساخته می‌شود اما در
    ``{% include ... with %}`` ی ``responsive_section_wrapper.html`` فراموش
    شده باشد (این دقیقاً همان باگی بود که نبودِ این تست باعث شد فاش نشود)."""

    def setUp(self):
        super().setUp()
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from apps.content.models import HeroSlide

        buf = BytesIO()
        Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
        self.img = SimpleUploadedFile("t.png", buf.getvalue(), content_type="image/png")

        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.filter(section_key="hero_banner").delete()
        self.hero_section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=900,
            settings={"autoplay": False, "interval_ms": 4500, "show_arrows": True, "show_dots": True, "loop": True,
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        HeroSlide.objects.create(store=self.store, section=self.hero_section, title="اسلایدِ رندرشده", desktop_image=self.img, is_active=True)
        HeroSlide.objects.create(store=self.store, section=self.hero_section, title="اسلایدِ دوم", desktop_image=self.img, is_active=True)

    def test_hero_slider_settings_reach_the_rendered_html(self):
        """اگر ``slider_settings`` در ``{% include with %}`` فراموش شود،
        تمپلیت به مقدارِ پیش‌فرضِ ``{{ slider_settings.autoplay|yesno }}``
        (رشته‌ی خالی) برمی‌گردد که به ``false`` تفسیر می‌شود — این تست فقط
        وقتی رد می‌شود که واقعاً به مقدارِ *صحیحِ* ذخیره‌شده (این‌جا False)
        برسد، نه به یک پیش‌فرضِ تصادفاً هم‌ارز."""
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "اسلایدِ رندرشده")
        self.assertContains(resp, "autoplay: false")

    def test_image_text_destination_link_reaches_rendered_html(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="image_text", order=901,
            settings={
                "title": "عنوانِ تست", "body_html": "", "image_url": "https://example.com/x.png", "image_position": "right",
                "destination": {"destination_type": "external", "destination_id": None,
                                 "destination_external_url": "https://example.com/landing", "open_in_new_tab": False},
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "https://example.com/landing")

    def test_image_text_search_destination_reaches_rendered_html(self):
        """Phase 3 — مقصدِ جدیدِ ``search`` (بدون‌پارامتر، مثلِ external
        اما بدونِ URL دستی) باید تا HTMLِ رندرشده برسد."""
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="image_text", order=902,
            settings={
                "title": "لینک به جستجو", "body_html": "", "image_url": "https://example.com/y.png", "image_position": "right",
                "destination": {"destination_type": "search", "destination_id": None,
                                 "destination_external_url": "", "open_in_new_tab": False},
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, reverse("catalog:product-list"))

    def test_motion_style_reaches_rendered_data_attribute(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=903,
            settings={
                "title": "", "display_mode": "grid", "category_ids": [],
                "motion": {"style": "fade"},
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, 'data-motion="fade"')

    def test_missing_motion_key_defaults_to_none_in_rendered_html(self):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="rich_text", order=904,
            settings={"body_html": "پیشین"},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, 'data-motion="none"')

    def test_two_duplicated_category_grids_render_different_categories(self):
        """چکپوینتِ ۱۱ — رگرسیونِ همان کلاسِ باگ: اگر ``category_grid_settings``
        در ``{% include with %}`` فراموش شود، هر دو نمونه به رفتارِ auto
        (یکسان) برمی‌گردند، نه انتخابِ per-instance."""
        from apps.catalog.models import Category

        cat_a = Category.objects.create(store=self.store, name="دستهٔ رندرشدهٔ آ", slug="cat-render-a", is_active=True)
        cat_b = Category.objects.create(store=self.store, name="دستهٔ رندرشدهٔ ب", slug="cat-render-b", is_active=True)
        self.draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=901,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_a.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=902,
            settings={"title": "", "display_mode": "grid", "category_ids": [cat_b.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "دستهٔ رندرشدهٔ آ")
        self.assertContains(resp, "دستهٔ رندرشدهٔ ب")

    def test_two_duplicated_brand_carousels_render_different_brands_and_titles(self):
        from apps.catalog.models import Brand

        brand_a = Brand.objects.create(store=self.store, name="برندِ رندرشدهٔ آ", slug="brand-render-a", is_active=True)
        brand_b = Brand.objects.create(store=self.store, name="برندِ رندرشدهٔ ب", slug="brand-render-b", is_active=True)
        self.draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=901,
            settings={"title": "برندهای بخش اول", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_a.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="brand_carousel", order=902,
            settings={"title": "برندهای بخش دوم", "display_mode": "grid", "show_view_all": False, "brand_ids": [brand_b.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "برندِ رندرشدهٔ آ")
        self.assertContains(resp, "برندِ رندرشدهٔ ب")
        self.assertContains(resp, "برندهای بخش اول")
        self.assertContains(resp, "برندهای بخش دوم")


    def test_auto_category_grid_carousel_display_mode_changes_rendered_markup(self):
        from apps.catalog.models import Category

        Category.objects.create(store=self.store, name="خودکار آ", slug="auto-a", is_active=True)
        Category.objects.create(store=self.store, name="خودکار ب", slug="auto-b", is_active=True)
        self.draft.sections.filter(section_key="category_grid").delete()
        StorefrontSection.objects.create(
            version=self.draft, section_key="category_grid", order=905,
            settings={
                "title": "", "display_mode": "carousel", "category_ids": [],
                "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False},
            },
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, 'class="tiles-carousel"')


class NewSectionTypesRenderedPreviewTests(StorefrontBuilderViewsTestCase):
    """چکپوینتِ ۱۲ — همان کلاسِ رگرسیونِ ``RenderedPreviewIntegrationTests``:
    برایِ هر نوعِ section جدید، حداقل یک context key که فقط در سرویس
    ساخته می‌شود باید واقعاً تا HTML رندرشده برسد (نه فقط دیکشنریِ context
    که ``test_render_service.py`` چک می‌کند)."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)

    def test_collection_tiles_reach_rendered_html(self):
        from apps.catalog.models import MerchantCollection

        collection = MerchantCollection.objects.create(
            store=self.store, name="کالکشنِ رندرشده", slug="np-collection", is_active=True,
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="collection_tiles", order=901,
            settings={"title": "", "collection_ids": [collection.pk],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "کالکشنِ رندرشده")
        self.assertContains(resp, "0 کالا")

    def test_quick_links_reach_rendered_html(self):
        from apps.catalog.models import Category
        from apps.content.models import DestinationType, Menu, MenuItem

        category = Category.objects.create(store=self.store, name="دستهٔ دسترسیِ سریع", slug="np-ql-cat", is_active=True)
        menu = Menu.objects.create(store=self.store, title="منوی تست", location=Menu.Location.HEADER, is_active=True)
        MenuItem.objects.create(
            menu=menu, title="لینکِ رندرشده", display_order=0, is_active=True,
            destination_type=DestinationType.CATEGORY, destination_category=category,
        )
        StorefrontSection.objects.create(
            version=self.draft, section_key="quick_links", order=901,
            settings={"title": "", "menu_id": menu.pk,
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "لینکِ رندرشده")

    def test_faq_items_reach_rendered_html(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="faq", order=901,
            settings={"title": "سوالات متداول", "items": [{"question": "سوالِ رندرشده؟", "answer": "پاسخِ رندرشده"}],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "سوالِ رندرشده؟")
        self.assertContains(resp, "پاسخِ رندرشده")

    def test_testimonials_reach_rendered_html(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="testimonials", order=901,
            settings={"title": "نظرات مشتریان", "items": [{"name": "مشتریِ رندرشده", "quote": "نظرِ رندرشده", "role": ""}],
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "مشتریِ رندرشده")
        self.assertContains(resp, "نظرِ رندرشده")

    def test_video_section_reaches_rendered_html(self):
        StorefrontSection.objects.create(
            version=self.draft, section_key="video_section", order=901,
            settings={"title": "", "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "caption": "زیرنویسِ رندرشده",
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "youtube.com/embed/dQw4w9WgXcQ")
        self.assertContains(resp, "زیرنویسِ رندرشده")

    def test_newsletter_reaches_rendered_html(self):
        """Phase 3 — عنوان/زیرعنوان/متنِ دکمه باید تا HTML برسند، و خودِ
        فرم باید به endpointِ عمومیِ ثبتِ ایمیل اشاره کند (نه یک مسیرِ
        داشبورد)."""
        StorefrontSection.objects.create(
            version=self.draft, section_key="newsletter", order=901,
            settings={"title": "عنوانِ خبرنامه", "subtitle": "زیرعنوانِ خبرنامه", "button_label": "عضوِ من کن",
                      "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(resp, "عنوانِ خبرنامه")
        self.assertContains(resp, "زیرعنوانِ خبرنامه")
        self.assertContains(resp, "عضوِ من کن")
        self.assertContains(resp, reverse("content:newsletter-subscribe"))


class PageSwitchingTests(StorefrontBuilderViewsTestCase):
    """Phase 2 (سازنده‌ی تک‌صفحه‌ای): ادیتور اکنون رویِ هر شش نوعِ صفحه
    کار می‌کند — ``?page=<page_type>`` صریحاً در URL، پیش‌فرضِ غایب/
    نامعتبر همیشه ``home`` (سازگاری کامل با رفتارِ پیش از این چکپوینت)."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()
        self.listing_page = self.draft.get_page(StorefrontPage.PageType.LISTING)
        self.home_page = self.draft.home_page()


    def test_preview_shows_requested_pages_sections(self):
        StorefrontSection.objects.create(page=self.home_page, section_key="rich_text", order=0, settings={"body_html": "HOME-PREVIEW-MARKER"})
        StorefrontSection.objects.create(page=self.listing_page, section_key="rich_text", order=0, settings={"body_html": "LISTING-PREVIEW-MARKER"})

        home_resp = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(home_resp, "HOME-PREVIEW-MARKER")
        self.assertNotContains(home_resp, "LISTING-PREVIEW-MARKER")

        listing_resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "listing"})
        self.assertContains(listing_resp, "LISTING-PREVIEW-MARKER")
        self.assertNotContains(listing_resp, "HOME-PREVIEW-MARKER")

    def test_non_home_page_with_no_sections_shows_empty_state(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})
        self.assertEqual(resp.status_code, 200)
        # Container/Cell intentionally keeps empty layout cells visible in the
        # Builder preview so the merchant can add content into them.
        self.assertContains(resp, "sfb-empty-cell-add")
        self.assertContains(resp, "افزودن بخش به این خانه")


class ProductDetailContextAwareSectionsPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: چهار نوعِ context-aware صفحه محصول واقعاً تا HTML رندرشده‌ی
    Preview می‌رسند (نه فقط dict، که test_render_service.py چک می‌کند) —
    Preview یک محصولِ نماینده (جدیدترین) را به‌جایِ «محصولِ جاری» انتخاب
    می‌کند، چون هیچ URLای برایِ یک محصولِ خاص در Preview وجود ندارد."""

    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        self.draft = svc.get_or_create_draft(self.store)
        self.pd_page = self.draft.get_page("product_detail")
        vendor = Vendor.objects.create(store=self.store, name="فروشنده پیش‌نمایش", slug="preview-vendor")
        category = Category.objects.create(store=self.store, name="دسته پیش‌نمایش", slug="preview-cat", is_active=True)
        self.product = Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای پیش‌نمایشِ رندرشده",
            slug="preview-render-product", sku="PREVIEW-RENDER-1", price=Decimal("75000"), stock=4,
            status=Product.Status.ACTIVE, description="توضیحاتِ کاملِ کالای پیش‌نمایش",
        )

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "product_detail"})

    def test_product_main_reaches_rendered_html(self):
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_main", order=0)
        resp = self._preview()
        self.assertContains(resp, "کالای پیش‌نمایشِ رندرشده")
        self.assertContains(resp, "افزودن به سبد خرید")

    def test_product_description_reaches_rendered_html(self):
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_description", order=0)
        resp = self._preview()
        self.assertContains(resp, "توضیحاتِ کاملِ کالای پیش‌نمایش")
        self.assertContains(resp, "مشخصات فنی")

    # ---- Phase 5 Task 5 (PDT) — accessible desktop tabs + mobile accordion ----
    def _one_product_description(self):
        # product_description is max_instances=1; ensure exactly one for a
        # deterministic single-section assertion (the page may be pre-seeded).
        StorefrontSection.objects.filter(page=self.pd_page, section_key="product_description").delete()
        return StorefrontSection.objects.create(page=self.pd_page, section_key="product_description", order=0)

    def test_product_description_panels_are_accessible_tablist(self):
        self._one_product_description()
        resp = self._preview()
        content = resp.content.decode()
        # ARIA tab semantics present.
        self.assertIn('role="tablist"', content)
        self.assertEqual(content.count('role="tab"'), 3)
        self.assertEqual(content.count('role="tabpanel"'), 3)
        self.assertIn('aria-selected="true"', content)
        self.assertIn("aria-controls=", content)
        self.assertIn("aria-labelledby=", content)
        # Real focusable buttons (not clickable div/span).
        self.assertNotIn("<div class=\"t\"", content)

    def test_product_description_panel_ids_are_deterministic_and_unique(self):
        self._one_product_description()
        resp = self._preview()
        content = resp.content.decode()
        import re
        panel_ids = re.findall(r'id="(pdp-panel-[^"]+)"', content)
        tab_ids = re.findall(r'id="(pdp-tab-[^"]+)"', content)
        self.assertEqual(len(panel_ids), 3)
        self.assertEqual(len(tab_ids), 3)
        # unique
        self.assertEqual(len(set(panel_ids)), 3)
        self.assertEqual(len(set(tab_ids)), 3)
        # deterministic: namespaced by the product pk so multiple PDPs never collide
        self.assertTrue(all(str(self.product.pk) in pid for pid in panel_ids))

    def test_product_description_all_three_panes_reachable_no_js(self):
        # Progressive enhancement: every panel's content is present in the DOM
        # (not removed) so a no-JS client still reaches all content.
        self._one_product_description()
        resp = self._preview()
        content = resp.content.decode()
        self.assertIn("توضیحاتِ کاملِ کالای پیش‌نمایش", content)  # desc
        self.assertIn("مشخصات فنی", content)  # spec tab label
        self.assertIn("نظرات کاربران", content)  # review tab label
        # Keyboard handler wired (arrow-key roving).
        self.assertIn("ArrowRight", content)
        self.assertIn("ArrowLeft", content)

    def test_product_description_source_owner_unchanged(self):
        # The content still comes from the canonical PDP context (no second
        # data source): the desc/spec/review data owners are unchanged.
        from pathlib import Path
        from django.conf import settings as dj_settings
        tmpl = Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/templates/storefront_builder/sections/product_description.html",
        ).read_text(encoding="utf-8")
        self.assertIn("spec_variant_summary", tmpl)
        self.assertIn("approved_reviews", tmpl)
        self.assertIn("product.description", tmpl)

    # ---- PDT remediation: REAL mobile accordion structure --------------

    def _pdp_tmpl(self):
        from pathlib import Path
        from django.conf import settings as dj_settings
        return Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/templates/storefront_builder/sections/product_description.html",
        ).read_text(encoding="utf-8")

    def test_markup_is_accordion_native_each_header_immediately_before_its_panel(self):
        # A REAL accordion (not stacked tabs): every header button is
        # IMMEDIATELY followed by its OWN panel in source order, so on mobile
        # each control sits directly above its content. Verify the three
        # header→panel pairs appear in this exact interleaved order.
        self._one_product_description()
        content = self._preview().content.decode()
        pid = self.product.pk
        order = []
        for token in (
            f'id="pdp-tab-desc-{pid}"', f'id="pdp-panel-desc-{pid}"',
            f'id="pdp-tab-spec-{pid}"', f'id="pdp-panel-spec-{pid}"',
            f'id="pdp-tab-review-{pid}"', f'id="pdp-panel-review-{pid}"',
        ):
            idx = content.find(token)
            self.assertNotEqual(idx, -1, f"missing {token}")
            order.append(idx)
        # Strictly increasing => header, panel, header, panel, header, panel.
        self.assertEqual(order, sorted(order),
                         "headers and panels must interleave (accordion-native), not group")
        # There is NO separate tabline wrapper grouping the headers away from
        # their panels (the old stacked-tabs structure).
        self.assertNotIn('class="tabline"', content)

    def test_headers_expose_accordion_aria_expanded_state(self):
        self._one_product_description()
        content = self._preview().content.decode()
        # Accordion semantics: each header conveys expanded/collapsed. The
        # first (open) header is expanded; a dynamic binding keeps it in sync.
        self.assertIn('aria-expanded="true"', content)
        self.assertIn('aria-expanded="false"', content)
        self.assertIn(":aria-expanded=", content)

    def test_single_content_dom_no_duplicate_panels(self):
        # ONE canonical content DOM shared by tabs + accordion: each panel id
        # appears exactly once (no separate mobile copy of the content).
        self._one_product_description()
        content = self._preview().content.decode()
        for key in ("desc", "spec", "review"):
            self.assertEqual(
                content.count(f'id="pdp-panel-{key}-{self.product.pk}"'), 1,
                f"panel {key} must appear exactly once (no mobile duplicate)",
            )

    def test_accordion_css_resets_order_to_natural_flow_on_mobile(self):
        # The mobile breakpoint restores natural document flow (order:0 on the
        # panels) so each panel renders directly after its own header — the
        # structural proof the mobile layout is a real accordion, not the
        # desktop "all headers then one panel" tab row.
        from pathlib import Path
        from django.conf import settings as dj_settings
        css = Path(
            dj_settings.BASE_DIR, "apps/catalog/static/css/product_detail.css",
        ).read_text(encoding="utf-8")
        self.assertIn("@media(max-width:680px)", css)
        # Desktop uses order to lift headers into a row; mobile drops that row.
        self.assertIn("order:0", css)
        self.assertIn(".pdp-tabs::after{display:none}", css)

    def test_persian_copy_has_correct_zwnj(self):
        # The rewrite must not regress Persian ZWNJ/spelling.
        tmpl = self._pdp_tmpl()
        self.assertIn("دسته\u200cبندی", tmpl)   # not the broken "دستهبندی"
        self.assertNotIn("دستهبندی", tmpl)
        self.assertIn("می\u200cدهد", tmpl)       # not the broken "میدهد"
        self.assertNotIn("میدهد", tmpl)

    def test_no_js_panels_are_visible_by_default(self):
        # PROGRESSIVE ENHANCEMENT regression: without JavaScript every PDP
        # panel (description/spec/reviews) MUST stay reachable. The panels carry
        # BOTH classes `tabpane pdp-tab-panel` and have NO static `active`
        # class (Alpine adds it), so a bare `.tabpane{display:none}` rule at
        # equal-or-higher specificity would hide ALL content with JS off. Assert
        # the CSS keeps `.pdp-tab-panel` visible by default (the no-JS state)
        # and only hides panels when JS-driven `x-show`/state applies.
        import re
        from pathlib import Path
        from django.conf import settings as dj_settings
        raw = Path(
            dj_settings.BASE_DIR, "apps/catalog/static/css/product_detail.css",
        ).read_text(encoding="utf-8")
        # Strip CSS comments so we assert against REAL rules, not documentation.
        css = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        compact = css.replace(" ", "")
        # There must be NO unconditional `.tabpane{display:none}` rule that would
        # override the default-visible `.pdp-tab-panel` (equal specificity, so
        # source order + the shared selector both matter).
        self.assertNotIn(".tabpane{display:none}", compact)
        self.assertNotRegex(
            css, r"\.tabpane\s*\{[^}]*display\s*:\s*none",
            "blanket `.tabpane{display:none}` hides all PDP content with JS off",
        )
        # The panels are visible by default via the shared class.
        self.assertIn(".pdp-tab-panel{display:block}", compact)

    def test_no_js_panels_template_has_no_static_hidden_state(self):
        # The template must not stamp a static hiding attribute/class on the
        # panels (only Alpine x-show should hide them once JS runs). x-cloak on
        # the panels is fine (it only hides until Alpine boots and is scoped by
        # the [x-cloak] rule), but there must be no static `hidden`/`display:none`.
        tmpl = self._pdp_tmpl()
        # No inline display:none and no static hidden attribute on the panels.
        self.assertNotIn("style=\"display:none", tmpl)
        self.assertNotRegex(tmpl, r'pdp-tab-panel"[^>]*\shidden\b')

    def test_empty_optional_sections_still_render_valid_accordion(self):
        # A product with NO description / NO reviews still renders all three
        # accessible header→panel pairs (empty content is a valid state).
        self._one_product_description()
        self.product.description = ""
        self.product.save(update_fields=["description"])
        self.product.reviews.all().delete()
        content = self._preview().content.decode()
        self.assertEqual(content.count('role="tab"'), 3)
        self.assertEqual(content.count('role="tabpanel"'), 3)
        self.assertIn("توضیحاتی برای این کالا ثبت نشده است.", content)

    def test_related_products_reaches_rendered_html_when_related_exist(self):
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from apps.catalog.models import Product

        related = Product.objects.create(
            store=self.store, vendor=self.product.vendor, category=self.product.category,
            name="کالای مرتبطِ پیش‌نمایش", slug="preview-related-product", sku="PREVIEW-RELATED-1",
            price=Decimal("20000"), stock=2, status=Product.Status.ACTIVE,
        )
        # Preview انتخابِ «محصولِ جاری» را از رویِ جدیدترینِ محصولِ فروشگاه
        # انجام می‌دهد (``_preview_page_context``) — این تست باید مطمئن
        # باشد ``self.product`` (نه ``related``) همان «جاری» است، تا
        # ``related`` واقعاً در گریدِ محصولاتِ مرتبط ظاهر شود.
        Product.objects.filter(pk=related.pk).update(created_at=timezone.now() - timedelta(days=1))
        StorefrontSection.objects.create(page=self.pd_page, section_key="related_products", order=0)
        resp = self._preview()
        self.assertContains(resp, "کالای مرتبطِ پیش‌نمایش")

    def test_product_video_section_renders_nothing_without_videos(self):
        """محصولِ نماینده هیچ ویدیویی ندارد — section باید بی‌خطا و بدونِ
        هیچ نشانه‌ای از گرید ویدیو رندر شود (fail-safe، نه crash)."""
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_video", order=0)
        resp = self._preview()
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "pdp-video-grid")

    def test_context_aware_sections_absent_on_other_page_tabs(self):
        """این چهار section فقط با ``?page=product_detail`` دیده می‌شوند —
        اگر همان section (با دستکاریِ مستقیم) رویِ صفحه‌ی دیگری بنشیند,
        Preview آن صفحه هرگز آن را رندر نمی‌کند (چون اصلاً section آن
        صفحه نیست)."""
        StorefrontSection.objects.create(page=self.pd_page, section_key="product_main", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})
        self.assertNotContains(resp, "کالای پیش‌نمایشِ رندرشده")

    # ---- Phase 5 Task 8 (SATC) — mobile Sticky Add-to-Cart -------------
    # SATC is PRESENTATION inside the existing canonical Add-to-Cart form:
    # one form, one submitted quantity owner, one cart:add flow. These tests
    # assert that architecture (ONE CONCEPT = ONE CANONICAL OWNER), not
    # fragile visual formatting.

    def _pdp_main_tmpl(self):
        from pathlib import Path
        from django.conf import settings as dj_settings
        return Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/templates/storefront_builder/sections/product_main.html",
        ).read_text(encoding="utf-8")

    def _one_product_main(self):
        # product_main is removable=False / max_instances=1 on a real PDP; the
        # product_detail page is pre-seeded with one. Ensure EXACTLY one for a
        # deterministic single-purchase-form assertion (mirrors the canonical
        # runtime invariant — never two product_main on one PDP).
        StorefrontSection.objects.filter(page=self.pd_page, section_key="product_main").delete()
        return StorefrontSection.objects.create(page=self.pd_page, section_key="product_main", order=0)

    def test_satc_rendered_by_canonical_product_main(self):
        # The sticky Add-to-Cart surface is emitted by the canonical
        # product_main section (not a new section / not a separate renderer).
        self._one_product_main()
        content = self._preview().content.decode()
        self.assertIn("pdp-satc", content)

    def test_satc_submits_the_same_canonical_form_no_second_form(self):
        # SATC lives PHYSICALLY INSIDE the one canonical Add-to-Cart form (the
        # approved preferred design). Because it is position:fixed it does not
        # disturb layout, and being a plain type="submit" of THAT form it reuses
        # the existing variant_id + quantity + the single cart:add pipeline with
        # NO `form=` coupling and NO second form. Assert: exactly ONE cart:add
        # form on the page, the .pdp-satc block is inside it, and there is no
        # `form=` attribute wiring on the sticky button.
        self._one_product_main()
        content = self._preview().content.decode()
        import re
        # exactly ONE canonical purchase pipeline: one form posting to cart:add.
        # (The page has other unrelated forms — search / review / login — but
        # there must be only a single hx-post to the cart-add endpoint.)
        cart_forms = re.findall(r'<form\b[^>]*hx-post="[^"]*/cart/add/[^"]*"[^>]*>', content)
        self.assertEqual(len(cart_forms), 1, "exactly one canonical cart:add form (no second purchase form)")
        # The .pdp-satc block sits INSIDE that form: it appears between the
        # cart:add <form ...> open tag and the next </form>.
        form_open = content.index(cart_forms[0])
        form_close = content.index("</form>", form_open)
        satc_at = content.find("pdp-satc", form_open)
        self.assertTrue(
            0 <= satc_at < form_close,
            "SATC must be physically inside the canonical Add-to-Cart form",
        )
        # No `form=` coupling was introduced (simpler inside-form design).
        self.assertNotIn("pdp-buy-form-", content, "no deterministic-form-id coupling needed")
        self.assertNotRegex(content, r'class="[^"]*pdp-satc-btn[^"]*"[^>]*\sform=', "sticky button uses no form= attr")

    def test_satc_has_no_second_quantity_owner(self):
        # SATC must NOT introduce its own quantity input/selector — the single
        # submitted quantity owner remains the existing stepper input.
        self._one_product_main()
        content = self._preview().content.decode()
        # exactly one quantity input in the whole rendered product_main
        self.assertEqual(content.count('name="quantity"'), 1, "one and only one submitted quantity owner")

    def test_normal_pdp_cta_still_present_alongside_satc(self):
        # SATC is additive: the normal in-flow Add-to-Cart CTA remains. There
        # are exactly TWO Add-to-Cart submit surfaces — the canonical in-flow
        # CTA (.pdp-actions .btn-primary) and the sticky one (.pdp-satc-btn) —
        # both submitting the SAME form (proven by the single-form test above).
        self._one_product_main()
        content = self._preview().content.decode()
        self.assertIn("افزودن به سبد خرید", content)
        # in-flow CTA still present
        self.assertIn('class="pdp-actions"', content)
        # sticky CTA present and is the additive second submit surface
        self.assertIn("pdp-satc-btn", content)

    def test_satc_reuses_canonical_purchasability_state_no_second_calc(self):
        # The sticky button binds to the SAME Alpine getters as the main CTA
        # (canAddToCart / needsSelection / displayStock) — no second stock or
        # purchasability calculation. Template-level proof: within the SATC
        # block, disabled/label bindings reference the canonical getters.
        tmpl = self._pdp_main_tmpl()
        satc_start = tmpl.find("pdp-satc")
        self.assertNotEqual(satc_start, -1, "SATC block must exist in product_main")
        satc_block = tmpl[satc_start:satc_start + 1200]
        self.assertIn("canAddToCart", satc_block)
        self.assertIn("needsSelection", satc_block)
        # SATC introduces no new Alpine component (no second x-data with its own
        # product/variant/quantity state) inside the sticky block.
        self.assertNotIn("x-data", satc_block)

    def test_satc_is_mobile_only_and_below_overlays_in_css(self):
        # SATC presentation is mobile-only and layered BELOW the canonical
        # overlays (login modal z-index:100, drawer 110/120, quick view
        # 1000/1001) and does not cover the bottom nav. Verify via the
        # canonical PDP CSS owner.
        from pathlib import Path
        from django.conf import settings as dj_settings
        css = Path(dj_settings.BASE_DIR, "apps/catalog/static/css/product_detail.css").read_text(encoding="utf-8")
        self.assertIn(".pdp-satc", css)
        # mobile-only: the sticky rule lives under a max-width media query and
        # is hidden by default on desktop.
        self.assertRegex(css, r"@media\s*\(max-width:\s*680px\)")
        # safe-area aware (consumes env(safe-area-inset-bottom)).
        self.assertIn("safe-area-inset-bottom", css)
        # bottom offset derives from the canonical bottom-nav clearance token,
        # not a hard-coded magic number.
        self.assertIn("--gmn-clearance", css)
        # No-obscuration repair: the WHOLE-PDP page container (not just
        # product_main, which is the FIRST section) reserves real bottom space
        # (nav clearance + SATC height) so the genuine final PDP content clears
        # the fixed SATC. The reserve is on the end-of-page owner and derives
        # from canonical geometry, not a random per-template value.
        self.assertRegex(css, r"\.wrap\.pdp-page:has\(\.pdp-satc\)\s*\{[^}]*padding-bottom:calc\(")
        self.assertIn("--satc-height", css)

    def test_bottom_nav_owner_exposes_presentation_clearance_token(self):
        # The canonical mobile bottom-nav CSS owner exposes a presentation-only
        # geometry token that SATC (and anything else) can consume, instead of
        # per-template offsets. One canonical geometry owner.
        from pathlib import Path
        from django.conf import settings as dj_settings
        css = Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/static/css/storefront_builder.css",
        ).read_text(encoding="utf-8")
        self.assertIn("--gmn-clearance", css)

    def test_clearance_is_per_variant_and_safe_area_when_nav_absent(self):
        # --gmn-clearance is NOT a single global constant. Its no-nav/default
        # value is the device safe area alone (so SATC never floats ~88px up for
        # a nav that isn't there, yet still clears the home indicator), and each
        # registered nav variant publishes its OWN geometry off the nav identity
        # class. One canonical geometry source distinguishing every active
        # variant AND the hidden/absent case.
        from pathlib import Path
        from django.conf import settings as dj_settings
        css = Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/static/css/storefront_builder.css",
        ).read_text(encoding="utf-8")
        # default (absent) is the safe area alone — never a bare 0px.
        self.assertRegex(css, r":root\s*\{\s*--gmn-clearance:\s*env\(safe-area-inset-bottom")
        self.assertNotRegex(css, r":root\s*\{\s*--gmn-clearance:\s*0px\s*\}")
        # every registered variant has its own clearance rule keyed off identity
        for variant in [
            "four_item", "five_item", "raised_cart", "floating_dock",
            "glass_dock", "minimal_icons", "wide_cart",
        ]:
            self.assertIn(f":has(.gmn--{variant})", css,
                          f"missing canonical clearance for nav variant {variant}")
        # a generic .gmn rule covers default/luxury (which reuse default geometry)
        self.assertRegex(css, r":root:has\(\.gmn\)\s*\{\s*--gmn-clearance:")

    def test_no_nav_clearance_includes_device_safe_area(self):
        # No-nav safe-area contract: the canonical no-nav/default
        # --gmn-clearance MUST include env(safe-area-inset-bottom) and must NOT
        # be a bare 0px — otherwise, with no bottom nav, a bottom-anchored SATC
        # would sit flush at bottom:0 and be clipped by the iPhone home
        # indicator. Desktop Chromium resolves the inset to 0, so this contract
        # test (not a pixel measurement) guards against regression.
        from pathlib import Path
        from django.conf import settings as dj_settings
        css = Path(
            dj_settings.BASE_DIR,
            "apps/storefront_builder/static/css/storefront_builder.css",
        ).read_text(encoding="utf-8")
        import re
        m = re.search(r":root\s*\{\s*--gmn-clearance:\s*([^}]*?)\s*\}", css)
        self.assertIsNotNone(m, "canonical :root --gmn-clearance declaration must exist")
        no_nav_value = m.group(1).strip()
        self.assertIn("env(safe-area-inset-bottom", no_nav_value,
                      "no-nav --gmn-clearance must clear the device safe area")
        self.assertNotEqual(no_nav_value, "0px",
                            "no-nav --gmn-clearance must not be a bare 0px")
        # Every active variant clearance also includes the safe area exactly
        # once (calc(<n>px + env(safe-area-inset-bottom,0px))) — never doubled.
        for variant in ["four_item", "five_item", "raised_cart", "floating_dock",
                        "glass_dock", "minimal_icons", "wide_cart"]:
            vm = re.search(
                r":root:has\(\.gmn--" + variant + r"\)\s*\{\s*--gmn-clearance:\s*([^}]*?)\s*\}",
                css,
            )
            self.assertIsNotNone(vm, f"missing clearance rule for {variant}")
            val = vm.group(1)
            self.assertEqual(val.count("env(safe-area-inset-bottom"), 1,
                             f"{variant} must count the safe area exactly once")


class ProductListingContextAwareSectionPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: ``product_listing`` تا HTML رندرشده‌ی Preview می‌رسد —
    روی هر دو تبِ listing و search."""

    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from apps.catalog.models import Category, Product, Vendor

        self.draft = svc.get_or_create_draft(self.store)
        vendor = Vendor.objects.create(store=self.store, name="فروشنده لیست", slug="listing-vendor")
        category = Category.objects.create(store=self.store, name="دسته لیست", slug="listing-cat", is_active=True)
        Product.objects.create(
            store=self.store, vendor=vendor, category=category, name="کالای لیستِ رندرشده",
            slug="listing-render-product", sku="LISTING-RENDER-1", price=Decimal("30000"), stock=5,
            status=Product.Status.ACTIVE,
        )

    def test_product_listing_reaches_rendered_html_on_listing_tab(self):
        page = self.draft.get_page("listing")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "listing"})
        self.assertContains(resp, "کالای لیستِ رندرشده")
        self.assertContains(resp, "اعمال فیلتر")

    def test_product_listing_reaches_rendered_html_on_search_tab(self):
        page = self.draft.get_page("search")
        StorefrontSection.objects.create(page=page, section_key="product_listing", order=0)
        resp = self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "search"})
        self.assertContains(resp, "کالای لیستِ رندرشده")


class CollectionContextAwareSectionsPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: ``collection_header``/``collection_products`` تا HTML
    رندرشده‌ی Preview می‌رسند — Preview جدیدترین کالکشنِ فروشگاه را
    به‌عنوانِ «کالکشنِ جاری» نماینده انتخاب می‌کند."""

    def setUp(self):
        super().setUp()
        from apps.catalog.services import collection_service

        self.draft = svc.get_or_create_draft(self.store)
        self.collection_page = self.draft.get_page("collection")
        self.collection = collection_service.create_collection(
            self.store, name="کالکشنِ پیش‌نمایشِ رندرشده", description="توضیحِ کالکشنِ پیش‌نمایش",
        )

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "collection"})

    def test_collection_header_reaches_rendered_html(self):
        StorefrontSection.objects.create(page=self.collection_page, section_key="collection_header", order=0)
        resp = self._preview()
        self.assertContains(resp, "کالکشنِ پیش‌نمایشِ رندرشده")
        self.assertContains(resp, "توضیحِ کالکشنِ پیش‌نمایش")

    def test_collection_products_reaches_rendered_html_and_shows_empty_state(self):
        StorefrontSection.objects.create(page=self.collection_page, section_key="collection_products", order=0)
        resp = self._preview()
        self.assertContains(resp, "فعلاً کالایی در این کالکشن برای نمایش وجود ندارد")


class CartContextAwareSectionsPreviewTests(StorefrontBuilderViewsTestCase):
    """Phase 5: ``cart_items``/``cart_summary`` تا HTML رندرشده‌ی Preview
    می‌رسند — Preview هرگز سبدِ واقعیِ کاربر را نشان نمی‌دهد (نگاه کنید به
    Phase 4)، پس همیشه حالتِ خالی نشان داده می‌شود."""

    def setUp(self):
        super().setUp()
        self.draft = svc.get_or_create_draft(self.store)
        self.cart_page = self.draft.get_page("cart")

    def _preview(self):
        return self.client.get(reverse("dashboard:storefront-builder-preview"), {"page": "cart"})

    def test_cart_items_shows_empty_state_in_preview(self):
        StorefrontSection.objects.create(page=self.cart_page, section_key="cart_items", order=0)
        resp = self._preview()
        self.assertContains(resp, "سبد خرید شما خالی است")

    def test_cart_summary_renders_nothing_in_preview_empty_state(self):
        # data-section-label (فقط برای Preview، همیشه حاضر تا مرچنت بتواند
        # جایگاهِ خالی را هم انتخاب کند) خودش شاملِ عبارتِ «خلاصه سفارش»ست —
        # این تست باید محتوایِ واقعیِ کارت را چک کند، نه برچسبِ section.
        StorefrontSection.objects.create(page=self.cart_page, section_key="cart_summary", order=0)
        resp = self._preview()
        self.assertNotContains(resp, "جمع قابل پرداخت")
        self.assertNotContains(resp, "ادامه و تسویه‌حساب")


class PrototypeV2Phase25MobileKeyboardAccessibilityTests(StorefrontBuilderViewsTestCase):
    """Phase 2.5 — compact navigation and keyboard/a11y hooks reuse real editor paths."""


    def test_preview_sections_are_keyboard_focusable_regions(self):
        draft = svc.get_or_create_draft(self.store, user=self.staff)
        page = draft.get_page(StorefrontPage.PageType.HOME)
        section = page.sections.order_by("order", "id").first()
        response = self.client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(response, f'data-section-id="{section.pk}"')
        self.assertContains(response, 'role="region"')
        self.assertContains(response, 'tabindex="0"')
        self.assertContains(response, "بخش قابل ویرایش")
        self.assertContains(response, "evt.altKey")
        self.assertContains(response, "'ArrowUp'")
        self.assertContains(response, "'ArrowDown'")
        self.assertContains(response, "aria-current")
        self.assertContains(response, "sfb:historyStep")
