"""رندرِ «تنظیماتِ نمایش در دستگاه‌ها» (فازِ D) — هم از مسیرِ پیش‌نمایشِ
ادیتور (Draft) و هم صفحه‌ی عمومی (منتشرشده)، از طریقِ همان یک partial
مشترک (``responsive_section_wrapper.html``) که هرگز فورک نمی‌شود."""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Product, Vendor
from apps.catalog.services import collection_service
from apps.storefront_builder.models import StorefrontPage, StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreDomain

HOST = "sfb-responsive.example.com"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _verified_domain(store, hostname):
    return StoreDomain.objects.create(
        store=store, hostname=hostname, is_primary=True,
        verification_status=StoreDomain.VerificationStatus.VERIFIED, verified_at=timezone.now(),
    )


def _product(store, slug, *, vendor=None, category=None):
    vendor = vendor or Vendor.objects.create(store=store, name=f"فروشنده {slug}", slug=f"v-{slug}")
    category = category or Category.objects.create(store=store, name=f"دسته {slug}", slug=f"c-{slug}")
    return Product.objects.create(
        store=store, vendor=vendor, category=category, name=f"کالای {slug}", slug=slug,
        sku=f"SKU-{slug}", price=Decimal("10000"), status=Product.Status.ACTIVE,
        # Home product rails never pick an unavailable product (owner rule), so a fixture meant to APPEAR there
        # must be in stock.
        stock=5,
    )


class ResponsiveWrapperRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        from django.test import override_settings
        self._override = override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)
        _verified_domain(self.store, HOST)

    def _publish_hero_banner(self, *, responsive):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=999, settings={"responsive": responsive},
        )
        svc.publish(self.store)

    def test_no_hide_attributes_when_visible_everywhere(self):
        self._publish_hero_banner(responsive={"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "data-hide-desktop")
        self.assertNotContains(resp, "data-hide-tablet")
        self.assertNotContains(resp, "data-hide-mobile")

    def test_hide_mobile_only(self):
        self._publish_hero_banner(responsive={"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": True})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "data-hide-mobile")
        self.assertNotContains(resp, "data-hide-desktop")
        self.assertNotContains(resp, "data-hide-tablet")

    def test_hide_tablet_only(self):
        self._publish_hero_banner(responsive={"hide_on_desktop": False, "hide_on_tablet": True, "hide_on_mobile": False})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "data-hide-tablet")
        self.assertNotContains(resp, "data-hide-desktop")
        self.assertNotContains(resp, "data-hide-mobile")

    def test_hide_desktop_only(self):
        self._publish_hero_banner(responsive={"hide_on_desktop": True, "hide_on_tablet": False, "hide_on_mobile": False})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "data-hide-desktop")
        self.assertNotContains(resp, "data-hide-tablet")
        self.assertNotContains(resp, "data-hide-mobile")

    def test_hide_all_three_combination(self):
        self._publish_hero_banner(responsive={"hide_on_desktop": True, "hide_on_tablet": True, "hide_on_mobile": True})
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "data-hide-desktop")
        self.assertContains(resp, "data-hide-tablet")
        self.assertContains(resp, "data-hide-mobile")

    def test_missing_responsive_key_defaults_to_visible(self):
        """سکشنِ از‌قبل‌موجود بدونِ کلیدِ responsive اصلاً — نه فقط
        default مقادیرِ False — باید همچنان نمایان باشد."""
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=999, settings={})
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "data-hide-desktop")
        self.assertNotContains(resp, "data-hide-tablet")
        self.assertNotContains(resp, "data-hide-mobile")

    def test_is_active_and_responsive_visibility_are_independent(self):
        """is_active=False کلاً از رندر حذف می‌شود (نه فقط پنهانِ CSS) —
        این دو مفهوم نباید با هم قاطی شوند."""
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=999, is_active=False,
            settings={"responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "data-hide-desktop")  # چون اصلاً در render_items نیست، نه چون نمایان است


class ProductSectionColumnRenderingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        from django.test import override_settings
        self._override = override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)
        _verified_domain(self.store, HOST)

    def _settings(self, **overrides):
        base = {
            "data_source": "newest", "source_id": None, "product_ids": [], "item_limit": 8,
            "display_mode": "grid", "show_view_all": True, "title": "ستون‌بندی", "subtitle": "",
            "responsive": {
                "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
                "desktop_columns": 5, "tablet_columns": 3, "mobile_columns": 2,
            },
        }
        base.update(overrides)
        return base

    def test_column_css_variables_rendered(self):
        _product(self.store, "resp-col-p1")
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(version=draft, section_key="product_section", order=999, settings=self._settings())
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        content = resp.content.decode()
        self.assertIn("--cols-desktop:5", content)
        self.assertIn("--cols-tablet:3", content)
        self.assertIn("--cols-mobile:2", content)

    def test_grid_display_mode_gets_rsec_cols_class(self):
        _product(self.store, "resp-col-p2")
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=999,
            settings=self._settings(display_mode="grid"),
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'class="grid rsec-cols"')

    def test_carousel_display_mode_gets_rsec_cols_class(self):
        _product(self.store, "resp-col-p3")
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=999,
            settings=self._settings(display_mode="carousel"),
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'class="pcarousel rsec-cols"')

    def test_collection_backed_product_section_gets_same_column_treatment(self):
        collection = collection_service.create_collection(self.store, name="کالکشن ستون‌بندی")
        product = _product(self.store, "resp-col-coll-p1")
        collection_service.add_product(collection, product)
        draft = svc.get_or_create_draft(self.store)
        StorefrontSection.objects.create(
            version=draft, section_key="product_section", order=999,
            settings=self._settings(
                data_source="collection", source_id=collection.pk,
                responsive={
                    "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
                    "desktop_columns": 6, "tablet_columns": 3, "mobile_columns": 2,
                },
            ),
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        content = resp.content.decode()
        self.assertIn("--cols-desktop:6", content)
        self.assertIn("کالای resp-col-coll-p1", content)

    def test_non_column_aware_type_has_no_rsec_cols_class(self):
        """rich_text (column-unaware) نباید کلاسِ rsec-cols بگیرد — این
        کلاس فقط داخلِ خودِ templateِ انواعِ عضوِ ``COLUMN_VISUAL_SECTION_KEYS``
        نوشته شده، نه توسطِ wrapper، پس به‌طور طبیعی فقط همان انواع را
        تحت تأثیر قرار می‌دهد. Phase 8 P0-2 این مجموعه را به ۶ نوعِ
        محصولیِ دیگر (newest_products/best_sellers/...) هم گسترش داد، پس
        این تست باید فقط صفحه‌ی حاویِ همین یک section را بررسی کند — نه
        کلِ صفحه‌ی اصلیِ پیش‌فرض که حالا آن انواعِ محصولی را هم دارد."""
        draft = svc.get_or_create_draft(self.store)
        home_page = draft.pages.get(page_type=StorefrontPage.PageType.HOME)
        home_page.sections.all().delete()
        StorefrontSection.objects.create(
            version=draft, section_key="rich_text", order=999,
            settings={"body_html": "<p>سلام</p>", "responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(resp, "rsec-cols")


class DraftPreviewPublishResponsiveTests(TestCase):
    """بخشِ ۱۵ مشخصات: Draft/Preview/Publish/Restore برایِ تنظیماتِ ریسپانسیو."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        from django.contrib.auth import get_user_model
        from django.test import Client
        from django.utils import timezone as tz

        from apps.stores.models import StoreMembership

        User = get_user_model()
        self.store.admin_subdomain = "resp-draft-test"
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="resp_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=tz.now(),
        )
        self.admin_client = Client(HTTP_HOST="resp-draft-test.rastisi.localhost")
        self.admin_client.login(username="resp_owner", password="pass12345")

        from django.test import override_settings
        self._override = override_settings(ALLOWED_HOSTS=[HOST, "testserver", "resp-draft-test.rastisi.localhost"])
        self._override.enable()
        self.addCleanup(self._override.disable)
        _verified_domain(self.store, HOST)

    def test_draft_change_visible_in_preview_not_on_live_until_publish(self):
        draft = svc.get_or_create_draft(self.store)
        if not draft.sections.filter(section_key="hero_banner").exists():
            StorefrontSection.objects.create(version=draft, section_key="hero_banner", order=999)
        svc.publish(self.store)  # baseline published version, hero_banner visible everywhere

        draft = svc.get_or_create_draft(self.store)
        section = draft.sections.get(section_key="hero_banner")
        section.settings = {"responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": True}}
        section.save(update_fields=["settings"])

        preview_resp = self.admin_client.get(reverse("dashboard:storefront-builder-preview"))
        self.assertContains(preview_resp, "data-hide-mobile")

        live_resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertNotContains(live_resp, "data-hide-mobile")

        svc.publish(self.store)
        live_resp_after_publish = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(live_resp_after_publish, "data-hide-mobile")

    def test_restore_restores_previous_responsive_settings(self):
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="hero_banner").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="hero_banner", order=999,
            settings={"responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False}},
        )
        v1 = svc.publish(self.store)

        draft2 = svc.get_or_create_draft(self.store)
        section2 = draft2.sections.get(section_key="hero_banner")
        section2.settings = {"responsive": {"hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": True}}
        section2.save(update_fields=["settings"])
        svc.publish(self.store)

        restored = svc.restore_version(self.store, v1.pk)
        restored_section = restored.sections.get(section_key="hero_banner")
        self.assertFalse(restored_section.settings["responsive"]["hide_on_mobile"])


def _banner_image():
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
    return SimpleUploadedFile("banner.png", buf.getvalue(), content_type="image/png")


class MultiBannerColumnRenderingTests(TestCase):
    """Phase 3 — ``multi_banner`` اکنون یک گریدِ واقعاً پارامتری است
    (``COLUMN_VISUAL_SECTION_KEYS``)، دقیقاً همان الگویِ
    ``ProductSectionColumnRenderingTests`` بالا."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        from django.test import override_settings
        self._override = override_settings(ALLOWED_HOSTS=[HOST, "testserver"])
        self._override.enable()
        self.addCleanup(self._override.disable)
        _verified_domain(self.store, HOST)

    def _make_banner_section(self, **responsive_overrides):
        from apps.content.models import PromotionalBanner

        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="multi_banner").delete()
        responsive = {
            "hide_on_desktop": False, "hide_on_tablet": False, "hide_on_mobile": False,
            "desktop_columns": 2, "tablet_columns": 2, "mobile_columns": 1,
        }
        responsive.update(responsive_overrides)
        section = StorefrontSection.objects.create(
            version=draft, section_key="multi_banner", order=999,
            settings={"responsive": responsive},
        )
        PromotionalBanner.objects.create(store=self.store, section=section, title="بنر یک", desktop_image=_banner_image(), is_active=True)
        PromotionalBanner.objects.create(store=self.store, section=section, title="بنر دو", desktop_image=_banner_image(), is_active=True)
        return section

    def test_multi_banner_gets_grid_rsec_cols_class(self):
        """Acceptance Batch 1 (post-U11) correction: this assertion was
        matching the *default bootstrap* ``best_sellers``/
        ``newest_products`` sections' own (unrelated) empty grid div —
        which happens to render the exact literal
        ``class="grid rsec-cols"`` (no extra classes) — never
        ``multi_banner``'s own div (``class="grid rsec-cols promo-grid
        promo-grid--..."``, so the exact-quoted substring never matched
        it). Now that a genuinely empty data-driven section like those two
        is correctly hidden on the public page (see
        ``render_service.hide_empty_public_sections``), that coincidental
        match is gone — so this test is fixed to actually assert against
        ``multi_banner``'s own rendered class, which is what it always
        meant to test."""
        self._make_banner_section()
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, 'class="grid rsec-cols promo-grid promo-grid--default"')

    def test_multi_banner_column_css_variables_rendered(self):
        self._make_banner_section(desktop_columns=2, tablet_columns=2, mobile_columns=1)
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        content = resp.content.decode()
        self.assertIn("--cols-desktop:2", content)
        self.assertIn("--cols-mobile:1", content)

    def test_both_banners_render_inside_the_grid(self):
        self._make_banner_section()
        svc.publish(self.store)
        resp = self.client.get(reverse("catalog:home"), HTTP_HOST=HOST)
        self.assertContains(resp, "بنر یک")
        self.assertContains(resp, "بنر دو")
