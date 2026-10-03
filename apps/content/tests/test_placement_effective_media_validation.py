"""RED/GREEN regression — the confirmed Publish→Clone cloned-media-edit
defect (Model layer).

Canonical lifecycle that exposes the bug:

    Published Placement (asset-backed — has a ``MediaAsset`` FK)
    → ``layout_service._clone_section_scoped_media`` clones it into a new
      Draft: the ``MediaAsset`` FK is copied verbatim, but the legacy
      ``ImageField`` bytes are deliberately NEVER copied (documented in
      that function's own docstring — a clone is only meaningful for a
      Placement already migrated to Phase 0.5's asset model).
    → the cloned Draft row therefore has its asset FK populated and its
      legacy ``ImageField`` empty.
    → any subsequent ``obj.full_clean()`` on that row — the canonical
      media CRUD endpoint's own validation step
      (``apps.storefront_builder.media_views.storefront_section_media_form``)
      — used to raise, because the legacy field was ``blank=False``
      unconditionally, even though the model's OWN renderer
      (``_resolve_placement_media_url`` — MediaAsset first, legacy file
      second) and the clone contract itself both already treat the
      MediaAsset as fully sufficient on its own.

These tests operate directly on the model layer (``full_clean()``),
independent of the HTTP endpoint —
``apps/storefront_builder/tests/test_cloned_media_edit_safety.py`` covers
the same defect through the real canonical CRUD view instead.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png", color=(10, 20, 30)):
    buf = BytesIO()
    Image.new("RGB", (800, 400), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class _ClonedAssetBackedPlacementCaseMixin:
    """Builds a genuinely cloned, asset-backed Draft Placement for each of
    the three section-scoped media models — the exact real-world shape
    ``layout_service._clone_section_scoped_media`` produces (asset FK
    copied, legacy ``ImageField`` bytes never copied). Never touches the
    HTTP layer — a real Publish/reopen-Draft round trip through the real
    service functions, exactly as the Studio does it."""

    model = None
    section_key = None
    asset_field = None
    legacy_field = None

    def _build_cloned_placement(self):
        store = _akhlaghi()
        draft = svc.get_or_create_draft(store)
        section = StorefrontSection.objects.create(
            version=draft, section_key=self.section_key, order=950,
        )
        asset = MediaAsset.objects.create(store=store, image=_img())
        self.model.objects.create(
            store=store, section=section, title="اولیه",
            **{self.asset_field: asset, self.legacy_field: _img()},
        )

        svc.publish(store)
        new_draft = svc.get_or_create_draft(store)
        new_section = new_draft.sections.get(section_key=self.section_key)
        return self.model.objects.get(section=new_section)


class HeroSlideClonedAssetBackedFullCleanTests(_ClonedAssetBackedPlacementCaseMixin, TestCase):
    model = HeroSlide
    section_key = "hero_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"

    def test_cloned_placement_has_asset_but_empty_legacy_field(self):
        cloned = self._build_cloned_placement()
        self.assertTrue(cloned.desktop_asset_id)
        self.assertFalse(cloned.desktop_image)

    def test_cloned_asset_backed_placement_passes_full_clean(self):
        cloned = self._build_cloned_placement()
        cloned.full_clean()  # must not raise


class PromotionalBannerClonedAssetBackedFullCleanTests(_ClonedAssetBackedPlacementCaseMixin, TestCase):
    model = PromotionalBanner
    section_key = "multi_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"

    def test_cloned_placement_has_asset_but_empty_legacy_field(self):
        cloned = self._build_cloned_placement()
        self.assertTrue(cloned.desktop_asset_id)
        self.assertFalse(cloned.desktop_image)

    def test_cloned_asset_backed_placement_passes_full_clean(self):
        cloned = self._build_cloned_placement()
        cloned.full_clean()


class StoryRailItemClonedAssetBackedFullCleanTests(_ClonedAssetBackedPlacementCaseMixin, TestCase):
    model = StoryRailItem
    section_key = "story_rail"
    asset_field = "image_asset"
    legacy_field = "image"

    def test_cloned_placement_has_asset_but_empty_legacy_field(self):
        cloned = self._build_cloned_placement()
        self.assertTrue(cloned.image_asset_id)
        self.assertFalse(cloned.image)

    def test_cloned_asset_backed_placement_passes_full_clean(self):
        cloned = self._build_cloned_placement()
        cloned.full_clean()


class MissingBothMediaSourcesRemainsInvalidTests(TestCase):
    """Case C — the repair must NOT make an image-less Hero/Banner/Story
    Placement valid: the "asset OR legacy file" rule still requires AT
    LeAST one of the two to exist."""

    def test_hero_slide_without_asset_or_legacy_image_is_invalid(self):
        slide = HeroSlide(store=_akhlaghi(), title="بدون رسانه")
        with self.assertRaises(ValidationError) as ctx:
            slide.full_clean()
        self.assertIn("desktop_image", ctx.exception.message_dict)

    def test_promotional_banner_without_asset_or_legacy_image_is_invalid(self):
        banner = PromotionalBanner(store=_akhlaghi(), title="بدون رسانه")
        with self.assertRaises(ValidationError) as ctx:
            banner.full_clean()
        self.assertIn("desktop_image", ctx.exception.message_dict)

    def test_story_rail_item_without_asset_or_legacy_image_is_invalid(self):
        item = StoryRailItem(store=_akhlaghi(), title="بدون رسانه")
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("image", ctx.exception.message_dict)


class AssetStoreOwnershipRegressionTests(TestCase):
    """Case D — cross-store ``MediaAsset`` protection
    (``_validate_asset_store_ownership``) must remain fully intact,
    unaffected by relaxing the legacy-field requirement."""

    def test_hero_slide_rejects_asset_from_another_store(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="pemv-other-store-hero", status=Store.Status.ACTIVE,
        )
        foreign_asset = MediaAsset.objects.create(store=other_store, image=_img())
        slide = HeroSlide(store=_akhlaghi(), title="X", desktop_asset=foreign_asset)
        with self.assertRaises(ValidationError) as ctx:
            slide.full_clean()
        self.assertIn("desktop_asset", ctx.exception.message_dict)

    def test_promotional_banner_rejects_asset_from_another_store(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="pemv-other-store-banner", status=Store.Status.ACTIVE,
        )
        foreign_asset = MediaAsset.objects.create(store=other_store, image=_img())
        banner = PromotionalBanner(store=_akhlaghi(), title="X", desktop_asset=foreign_asset)
        with self.assertRaises(ValidationError) as ctx:
            banner.full_clean()
        self.assertIn("desktop_asset", ctx.exception.message_dict)

    def test_story_rail_item_rejects_asset_from_another_store(self):
        other_store = Store.objects.create(
            name="فروشگاه دیگر", slug="pemv-other-store-story", status=Store.Status.ACTIVE,
        )
        foreign_asset = MediaAsset.objects.create(store=other_store, image=_img())
        item = StoryRailItem(store=_akhlaghi(), title="X", image_asset=foreign_asset)
        with self.assertRaises(ValidationError) as ctx:
            item.full_clean()
        self.assertIn("image_asset", ctx.exception.message_dict)
