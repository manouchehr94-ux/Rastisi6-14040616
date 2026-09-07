"""G2.2 — Preview Media Render Consistency Repair.

Regression coverage for the HTTP 500 that appeared in the Storefront Builder
Preview *after a Published version was cloned to a Draft*:

    ValueError: The 'desktop_image' attribute has no file associated with it.

Root cause (confirmed in code, not assumed):

* ``HeroSlide`` / ``PromotionalBanner`` / ``StoryRailItem`` carry the canonical
  ``MediaAsset`` FK fields (``desktop_asset`` / ``mobile_asset`` /
  ``image_asset``) *and* the older physical ``ImageField`` values
  (``desktop_image`` / ``mobile_image`` / ``image``).
* The version clone path (``layout_service._clone_section_scoped_media``)
  intentionally clones the ``*_asset`` FK references but intentionally does
  **not** copy the legacy physical ImageField bytes (Owner Decision 5). So a
  cloned Draft placement is MediaAsset-backed with an *empty* legacy
  ImageField.
* Several renderer templates still dereference the legacy field directly
  (``{{ s.desktop_image.url }}``). Django's ``FieldFile.url`` raises
  ``ValueError`` when the field has no file — hence the 500.

Desired canonical resolution order (a single source of truth shared by the
Builder Preview *and* the public storefront, because they render through the
same section templates):

    canonical MediaAsset image  ->  legacy ImageField  ->  safe empty (no crash)

These tests drive the **real** production clone path
(``layout_service.get_or_create_draft`` after ``publish``), render the **real**
production section templates with the **real** context produced by
``render_service.build_page_render_items`` (the single render pipeline both
Preview and the public storefront use), and additionally assert the **real**
preview view (``dashboard:storefront-builder-preview``) returns HTTP 200 — no
mocked helper internals.
"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services.render_service import build_page_render_items
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "sfb-g22-media.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="g22.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (12, 34, 56)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class _RenderMediaTestBase(TestCase):
    """Shared staff/host wiring plus helpers that exercise the real
    production render pipeline."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(
            username="g22_media_owner", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="g22_media_owner", password="pass12345")

    def _publish_section_with(self, section_key, build_placement):
        """Create a Draft with a single ``section_key`` section, let the
        caller create the source placement on it, then publish."""
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(
            version=d1, section_key=section_key, order=0,
        )
        build_placement(section)
        return svc.publish(self.store)

    def _cloned_draft_section(self, section_key):
        """Trigger the REAL Published -> Draft clone and return the cloned
        Draft section."""
        d2 = svc.get_or_create_draft(self.store)
        return d2.sections.get(section_key=section_key)

    def _render_section_html(self, section_key):
        """Render the exact production section template with the exact
        context ``build_page_render_items`` produces for the current Draft —
        the single pipeline shared by Builder Preview and public storefront.

        Returns the section's rendered HTML. Raises whatever the template
        raises (e.g. the ``ValueError`` this ticket is about), so a crash
        surfaces as a test error, exactly like the real 500.
        """
        draft = svc.get_or_create_draft(self.store)
        page = draft.get_page("home")
        items = build_page_render_items(page, self.store)
        item = next(i for i in items if i["section"].section_key == section_key)
        return render_to_string(item["template_name"], item["context"])

    def _assert_preview_200(self):
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "home"},
        )
        self.assertEqual(
            resp.status_code, 200,
            msg="Builder Preview must render HTTP 200 for an asset-backed cloned Draft placement",
        )
        return resp


class HeroClonedDraftAssetBackedTests(_RenderMediaTestBase):
    """Test 1 — HERO / cloned Draft / asset-backed (the observed bug)."""

    def test_cloned_hero_renders_from_asset_and_preview_is_200(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("hero-desktop.png"))

        def build(section):
            # Published, asset-backed, legacy desktop_image intentionally EMPTY
            # (mirrors a placement that was migrated to MediaAsset).
            HeroSlide.objects.create(
                store=self.store, section=section, title="اسلاید کلون",
                desktop_asset=asset,
            )

        self._publish_section_with("hero_banner", build)

        draft_section = self._cloned_draft_section("hero_banner")
        cloned = HeroSlide.objects.get(section=draft_section)
        # Canonical asset reference cloned; legacy file empty (the crash setup).
        self.assertEqual(cloned.desktop_asset_id, asset.pk)
        self.assertFalse(bool(cloned.desktop_image))

        # Real production template + real context: must NOT raise ValueError,
        # and the rendered <img> src must come from the MediaAsset.
        html = self._render_section_html("hero_banner")
        self.assertIn(asset.image.url, html)

        # And the real preview route must return 200 (the observed symptom).
        self._assert_preview_200()


class HeroLegacyFallbackTests(_RenderMediaTestBase):
    """Test 2 — LEGACY FALLBACK: a legacy HeroSlide with no MediaAsset but
    with desktop_image must still render (no backwards-compat regression)."""

    def test_legacy_only_hero_still_renders_from_legacy_image(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید قدیمی",
            desktop_image=_img("legacy-hero.png"),
        )
        self.assertTrue(bool(slide.desktop_image))
        self.assertIsNone(slide.desktop_asset_id)

        html = self._render_section_html("hero_banner")
        self.assertIn(slide.desktop_image.url, html)
        self._assert_preview_200()


class HeroMobileMediaTests(_RenderMediaTestBase):
    """Test 3 — MOBILE MEDIA: mobile_asset resolves the responsive source;
    legacy mobile_image remains a fallback."""

    def test_mobile_asset_used_for_responsive_source_when_present(self):
        desktop_asset = MediaAsset.objects.create(store=self.store, image=_img("m-desktop.png"))
        mobile_asset = MediaAsset.objects.create(store=self.store, image=_img("m-mobile.png"))

        def build(section):
            HeroSlide.objects.create(
                store=self.store, section=section, title="اسلاید موبایل",
                desktop_asset=desktop_asset, mobile_asset=mobile_asset,
            )

        self._publish_section_with("hero_banner", build)
        draft_section = self._cloned_draft_section("hero_banner")
        cloned = HeroSlide.objects.get(section=draft_section)
        self.assertEqual(cloned.mobile_asset_id, mobile_asset.pk)
        self.assertFalse(bool(cloned.mobile_image))

        html = self._render_section_html("hero_banner")
        # Responsive <source srcset> must resolve from the mobile MediaAsset.
        self.assertIn(mobile_asset.image.url, html)

    def test_legacy_mobile_image_still_used_when_no_mobile_asset(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        slide = HeroSlide.objects.create(
            store=self.store, section=section, title="موبایل قدیمی",
            desktop_image=_img("d.png"), mobile_image=_img("legacy-mobile.png"),
        )
        html = self._render_section_html("hero_banner")
        self.assertIn(slide.mobile_image.url, html)


class BannerClonedDraftAssetBackedTests(_RenderMediaTestBase):
    """Test 4 — BANNER: asset-backed PromotionalBanner survives the same
    render path without dereferencing an empty legacy ImageField."""

    def test_cloned_banner_renders_from_asset(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("banner-desktop.png"))

        def build(section):
            PromotionalBanner.objects.create(
                store=self.store, section=section, title="بنر کلون",
                desktop_asset=asset,
            )

        self._publish_section_with("single_banner", build)
        draft_section = self._cloned_draft_section("single_banner")
        cloned = PromotionalBanner.objects.get(section=draft_section)
        self.assertEqual(cloned.desktop_asset_id, asset.pk)
        self.assertFalse(bool(cloned.desktop_image))

        html = self._render_section_html("single_banner")
        self.assertIn(asset.image.url, html)


class StoryClonedDraftAssetBackedTests(_RenderMediaTestBase):
    """Test 5 — STORY: asset-backed StoryRailItem survives the same render
    path without dereferencing an empty legacy ImageField."""

    def test_cloned_story_renders_from_asset(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img("story.png"))

        def build(section):
            StoryRailItem.objects.create(
                store=self.store, section=section, title="استوری کلون",
                image_asset=asset,
            )

        self._publish_section_with("story_rail", build)
        draft_section = self._cloned_draft_section("story_rail")
        cloned = StoryRailItem.objects.get(section=draft_section)
        self.assertEqual(cloned.image_asset_id, asset.pk)
        self.assertFalse(bool(cloned.image))

        html = self._render_section_html("story_rail")
        self.assertIn(asset.image.url, html)



class PreviewRouteAcceptanceTests(_RenderMediaTestBase):
    """Phase F — route-level acceptance closest to a browser check the
    sandbox allows: drive the REAL preview route end-to-end for an
    asset-backed cloned Draft hero that is actually PLACED in a container
    cell, so the hero body genuinely renders inside the preview response
    (container layout mode). Proves: HTTP 200, no ValueError, the hero
    <img> is visible, and its src is the MediaAsset URL — and the public
    storefront shares the same resolved media."""

    def test_preview_route_renders_asset_backed_hero_end_to_end(self):
        from apps.storefront_builder.services import container_service

        asset = MediaAsset.objects.create(store=self.store, image=_img("accept-hero.png"))

        def build(section):
            HeroSlide.objects.create(
                store=self.store, section=section, title="اسلاید پذیرش",
                desktop_asset=asset,
            )

        self._publish_section_with("hero_banner", build)

        # REAL Published -> Draft clone, then place the cloned hero section in
        # a real container cell so container-mode preview renders its body.
        draft = svc.get_or_create_draft(self.store)
        page = draft.get_page("home")
        page.containers.all().delete()
        draft_section = draft.sections.get(section_key="hero_banner")
        cloned = HeroSlide.objects.get(section=draft_section)
        self.assertEqual(cloned.desktop_asset_id, asset.pk)
        self.assertFalse(bool(cloned.desktop_image))

        container = container_service.create_empty_container(page, "single")
        container_service.place_section(container.cells.get(), draft_section)

        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "home"},
        )
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        # Hero is visible in the preview and its image src is the MediaAsset URL.
        self.assertIn("hero-media", html)
        self.assertIn(asset.image.url, html)
        # The observed crash string must NOT appear.
        self.assertNotIn("has no file associated with it", html)



class MissingMediaSafeBehaviorTests(_RenderMediaTestBase):
    """Phase G follow-up — the "safe empty / no-media" contract from the
    architecture ruling: a placement with NEITHER a MediaAsset NOR a legacy
    ImageField must render without raising ``ValueError`` and must NOT emit
    an empty ``src=""`` (which a browser would resolve to the page URL and
    re-request)."""

    def test_hero_with_no_media_renders_safely_without_empty_src(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید بدون رسانه",
        )
        self.assertIsNone(slide.desktop_asset_id)
        self.assertFalse(bool(slide.desktop_image))
        # Property degrades to empty string, never raising.
        self.assertEqual(slide.desktop_image_url, "")
        self.assertEqual(slide.mobile_image_url, "")

        # Real template render must not raise, and must not emit src="".
        html = self._render_section_html("hero_banner")
        self.assertNotIn('src=""', html)
        self.assertNotIn("has no file associated with it", html)

    def test_banner_with_no_media_renders_safely_without_empty_src(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="single_banner", order=0)
        PromotionalBanner.objects.create(
            store=self.store, section=section, title="بنر بدون رسانه",
        )
        html = self._render_section_html("single_banner")
        self.assertNotIn('src=""', html)

    def test_story_with_no_media_renders_safely_without_empty_src(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="story_rail", order=0)
        StoryRailItem.objects.create(
            store=self.store, section=section, title="استوری بدون رسانه",
        )
        html = self._render_section_html("story_rail")
        self.assertNotIn('src=""', html)

    def test_cloned_hero_desktop_asset_only_omits_mobile_source(self):
        """A cloned Draft hero with a desktop asset but NO mobile media must
        render the desktop <img> from the asset and omit the responsive
        <source> entirely (never emit an empty srcset/src)."""
        desktop_asset = MediaAsset.objects.create(store=self.store, image=_img("d-only.png"))

        def build(section):
            HeroSlide.objects.create(
                store=self.store, section=section, title="فقط دسکتاپ",
                desktop_asset=desktop_asset,
            )

        self._publish_section_with("hero_banner", build)
        draft_section = self._cloned_draft_section("hero_banner")
        cloned = HeroSlide.objects.get(section=draft_section)
        self.assertEqual(cloned.desktop_asset_id, desktop_asset.pk)
        self.assertIsNone(cloned.mobile_asset_id)
        self.assertFalse(bool(cloned.mobile_image))
        self.assertEqual(cloned.mobile_image_url, "")

        html = self._render_section_html("hero_banner")
        self.assertIn(desktop_asset.image.url, html)
        self.assertNotIn("<source", html)
        self.assertNotIn('src=""', html)



class BrandCarouselWrapperConsistencyTests(_RenderMediaTestBase):
    """Phase 3 characterization — the responsive_section_wrapper is the single
    shared wrapper both Builder Preview and the public storefront include. This
    locks in the CURRENT (correct) baseline: for a brand_carousel item built by
    the real ``build_page_render_items`` pipeline, rendering the wrapper with
    ``is_preview=True`` preserves the item's identity (section key/id), its
    title/brand resource links, its background styling, and its responsive
    hide flags — consistent with the persisted section settings. GREEN as-is.
    """

    def _brand_carousel_item(self, settings):
        from apps.catalog.models import Brand

        Brand.objects.create(
            store=self.store, name="برند رپر", slug="p3-wrapper-brand", is_active=True,
        )
        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="brand_carousel").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="brand_carousel", order=900, settings=settings,
        )
        page = draft.get_page("home")
        items = build_page_render_items(page, self.store)
        return next(i for i in items if i["section"].section_key == "brand_carousel")

    def test_wrapper_preserves_identity_title_links_and_flags(self):
        settings = {
            "title": "برندهای فاز سه",
            "display_mode": "grid",
            "show_view_all": False,
            "brand_ids": [],
            # responsive hide flag that the shared wrapper must surface
            "responsive": {"hide_on_mobile": True},
            # a solid background color the wrapper renders inline
            "background": {"mode": "color", "color": "#123456"},
        }
        item = self._brand_carousel_item(settings)

        html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True},
        )

        # Identity: the wrapper stamps preview-only section metadata.
        self.assertIn('data-section-key="brand_carousel"', html)
        self.assertIn(f'data-section-id="{item["section"].pk}"', html)

        # Title from the section settings survives into the rendered body.
        self.assertIn("برندهای فاز سه", html)

        # Resource link: the one active brand's product-list link is present.
        self.assertIn("?brand=p3-wrapper-brand", html)
        self.assertIn("برند رپر", html)

        # Background styling is applied inline, consistent with settings.
        self.assertIn("background-color:#123456", html)

        # Responsive hide flag is surfaced as a data attribute.
        self.assertIn("data-hide-mobile", html)
        # Flags NOT set must be absent (no over-hiding).
        self.assertNotIn("data-hide-desktop", html)
        self.assertNotIn("data-hide-tablet", html)

        # No crash string from the media resolution contract.
        self.assertNotIn("has no file associated with it", html)

    def test_wrapper_public_variant_omits_preview_only_identity_hooks(self):
        settings = {
            "title": "بدون پیش‌نمایش",
            "display_mode": "grid",
            "show_view_all": False,
            "brand_ids": [],
        }
        item = self._brand_carousel_item(settings)

        html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": False},
        )

        # Baseline: public (non-preview) render never leaks the DB id / edit hooks.
        self.assertNotIn("data-section-id", html)
        self.assertNotIn("data-section-key", html)
        # But the actual section body (title + brand link) still renders.
        self.assertIn("بدون پیش‌نمایش", html)
        self.assertIn("?brand=p3-wrapper-brand", html)

    def test_wrapper_hidden_mobile_and_image_background_match_full_preview(self):
        """Wrapper isolation (Brand end-to-end gate): a brand_carousel item
        with a hidden-on-mobile responsive flag AND an image background must
        surface the SAME wrapper data attributes / inline background URL /
        resource anchors whether rendered as a standalone wrapper include or
        inside the full Builder Preview response — the wrapper is the single
        shared surface, so the two must not diverge."""
        asset = MediaAsset.objects.create(store=self.store, image=_img("brand-bg.png"))
        settings = {
            "title": "برند پس‌زمینه‌دار",
            "display_mode": "grid",
            "show_view_all": False,
            "brand_ids": [],
            "responsive": {"hide_on_mobile": True},
            "background": {"mode": "image", "media_asset_id": asset.pk},
        }
        item = self._brand_carousel_item(settings)

        # The render pipeline resolves the store-scoped background URL onto
        # the item context (never a raw settings URL).
        self.assertEqual(item["context"]["background_media_url"], asset.image.url)

        # 1. Standalone shared-wrapper render (is_preview=True).
        wrapper_html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True},
        )
        # Wrapper data attributes.
        self.assertIn("data-hide-mobile", wrapper_html)
        self.assertNotIn("data-hide-desktop", wrapper_html)
        self.assertNotIn("data-hide-tablet", wrapper_html)
        self.assertIn('data-bg-mode="image"', wrapper_html)
        self.assertIn(f'data-section-id="{item["section"].pk}"', wrapper_html)
        self.assertIn('data-section-key="brand_carousel"', wrapper_html)
        # Inline background URL + resource anchors + title.
        self.assertIn(f"background-image:url('{asset.image.url}')", wrapper_html)
        self.assertIn("?brand=p3-wrapper-brand", wrapper_html)
        self.assertIn("برند پس‌زمینه‌دار", wrapper_html)

        # 2. Full Builder Preview response — place the same section in a
        #    container cell so the preview renders its body, then assert the
        #    SAME attributes/URL/anchors appear (no divergence between the
        #    isolated wrapper and the full preview surface).
        from apps.storefront_builder.services import container_service

        draft = svc.get_or_create_draft(self.store)
        page = draft.get_page("home")
        page.containers.all().delete()
        draft_section = draft.sections.get(pk=item["section"].pk)
        container = container_service.create_empty_container(page, "single")
        container_service.place_section(container.cells.get(), draft_section)

        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"), {"page": "home"},
        )
        self.assertEqual(resp.status_code, 200)
        preview_html = resp.content.decode("utf-8")
        self.assertIn("data-hide-mobile", preview_html)
        self.assertIn('data-bg-mode="image"', preview_html)
        self.assertIn(f'data-section-id="{draft_section.pk}"', preview_html)
        self.assertIn(f"background-image:url('{asset.image.url}')", preview_html)
        self.assertIn("?brand=p3-wrapper-brand", preview_html)
        self.assertIn("برند پس‌زمینه‌دار", preview_html)
        self.assertNotIn("has no file associated with it", preview_html)



class CollectionTilesWrapperConsistencyTests(_RenderMediaTestBase):
    """Task 5 (wrapper isolation, mirror of BrandCarouselWrapperConsistencyTests):
    the ``responsive_section_wrapper`` is the single shared wrapper both
    Builder Preview and the public storefront include. For a ``collection_tiles``
    item built by the real ``build_page_render_items`` pipeline, rendering the
    wrapper preserves the item's identity, its tile links / count / image /
    title, and its responsive/background flags — consistent with the persisted
    settings. Also proves the collection-page context-aware header/products
    render from the SAME shared items under one page context.
    """

    def _collection_tiles_item(self, settings, *, with_image=False):
        from decimal import Decimal

        from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor

        collection = MerchantCollection.objects.create(
            store=self.store, name="کالکشنِ رپر", slug="p3-wrapper-collection", is_active=True,
        )
        if with_image:
            collection.image = _img("collection-cover.png")
            collection.save(update_fields=["image"])
        # Two real members => item_count == 2 (TOTAL membership).
        vendor = Vendor.objects.create(store=self.store, name="فروشنده رپر", slug="v-wrap-coll")
        category = Category.objects.create(store=self.store, name="دسته رپر", slug="c-wrap-coll", is_active=True)
        for i in range(2):
            product = Product.objects.create(
                store=self.store, vendor=vendor, category=category, name=f"کالای رپر {i}", slug=f"wrap-coll-p{i}",
                sku=f"SKU-WRAPCOLL-{i}", price=Decimal("10000"), status=Product.Status.ACTIVE,
            )
            MerchantCollectionItem.objects.create(collection=collection, product=product, order=i)

        draft = svc.get_or_create_draft(self.store)
        draft.sections.filter(section_key="collection_tiles").delete()
        StorefrontSection.objects.create(
            version=draft, section_key="collection_tiles", order=900, settings=settings,
        )
        page = draft.get_page("home")
        items = build_page_render_items(page, self.store)
        return collection, next(i for i in items if i["section"].section_key == "collection_tiles")

    def test_wrapper_preserves_tile_links_count_image_and_title(self):
        settings = {
            "title": "کالکشن‌های رپر",
            "tile_style": "grid",
            "collection_ids": [],
            "responsive": {"hide_on_mobile": True},
        }
        collection, item = self._collection_tiles_item(settings, with_image=True)

        html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True},
        )
        # Identity.
        self.assertIn('data-section-key="collection_tiles"', html)
        self.assertIn(f'data-section-id="{item["section"].pk}"', html)
        # Title + tile link + collection name.
        self.assertIn("کالکشن‌های رپر", html)
        self.assertIn(f"/collections/{collection.slug}/", html)
        self.assertIn("کالکشنِ رپر", html)
        # Count reflects TOTAL membership (2 کالا).
        self.assertIn("2 کالا", html)
        # Image: the real cover renders (not the folder-glyph fallback).
        self.assertIn(collection.image.url, html)
        self.assertNotIn("🗂️", html)
        # Responsive flag surfaced; others absent.
        self.assertIn("data-hide-mobile", html)
        self.assertNotIn("data-hide-desktop", html)
        self.assertNotIn("has no file associated with it", html)

    def test_wrapper_folder_glyph_fallback_when_no_image(self):
        settings = {"title": "بدون تصویر", "tile_style": "grid", "collection_ids": []}
        collection, item = self._collection_tiles_item(settings, with_image=False)
        html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True},
        )
        self.assertIn("کالکشنِ رپر", html)
        # No cover image => the folder-glyph fallback is shown.
        self.assertIn("🗂️", html)

    def test_wrapper_carousel_variant_container_class(self):
        settings = {"title": "کاروسل رپر", "tile_style": "carousel", "collection_ids": []}
        _collection, item = self._collection_tiles_item(settings)
        html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": item, "is_preview": True},
        )
        self.assertIn("tiles-carousel collection-tiles-carousel", html)

    def test_collection_header_and_products_render_under_same_page_context(self):
        """Wrapper isolation for the collection-page context-aware sections:
        header + products + paginator all render from the SAME shared items
        built with ONE ``page_context`` (the shape ``collection_detail``
        produces), through the shared wrapper."""
        from decimal import Decimal

        from django.core.paginator import Paginator

        from apps.catalog.models import Category, MerchantCollection, MerchantCollectionItem, Product, Vendor
        from apps.catalog.services.collection_service import collection_visible_items

        collection = MerchantCollection.objects.create(
            store=self.store, name="کالکشنِ صفحه", slug="p3-wrapper-detail", is_active=True,
            description="توضیحِ کالکشنِ رپر",
        )
        vendor = Vendor.objects.create(store=self.store, name="فروشنده صفحه", slug="v-wrap-detail")
        category = Category.objects.create(store=self.store, name="دسته صفحه", slug="c-wrap-detail", is_active=True)
        for i in range(15):
            product = Product.objects.create(
                store=self.store, vendor=vendor, category=category, name=f"کالای صفحه {i:02d}",
                slug=f"wrap-detail-p{i:02d}", sku=f"SKU-WRAPDET-{i:02d}", price=Decimal("10000"),
                status=Product.Status.ACTIVE,
            )
            MerchantCollectionItem.objects.create(collection=collection, product=product, order=i)

        draft = svc.get_or_create_draft(self.store)
        page = draft.get_page("collection")
        page.sections.all().delete()
        StorefrontSection.objects.create(page=page, section_key="collection_header", order=0)
        StorefrontSection.objects.create(page=page, section_key="collection_products", order=1)

        # collection_detail's exact page_context, on page 2.
        items = collection_visible_items(collection, self.store)
        paginator = Paginator(items, 12)
        page_obj = paginator.get_page("2")
        products = [it.product for it in page_obj.object_list]
        page_context = {"collection": collection, "products": products, "page_obj": page_obj}

        render_items = build_page_render_items(page, self.store, page_context=page_context)

        header_item = next(i for i in render_items if i["section"].section_key == "collection_header")
        products_item = next(i for i in render_items if i["section"].section_key == "collection_products")

        header_html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": header_item, "is_preview": True},
        )
        products_html = render_to_string(
            "storefront_builder/partials/responsive_section_wrapper.html",
            {"item": products_item, "is_preview": True},
        )
        # Header: name + description of the resolved current collection.
        self.assertIn("کالکشنِ صفحه", header_html)
        self.assertIn("توضیحِ کالکشنِ رپر", header_html)
        # Products: a page-2 product present, a page-1 product absent, and a
        # paginator (2 pages => "بعدی"/"قبلی" controls rendered).
        self.assertIn("کالای صفحه 13", products_html)
        self.assertNotIn("کالای صفحه 00", products_html)
        self.assertIn("pagination", products_html)
