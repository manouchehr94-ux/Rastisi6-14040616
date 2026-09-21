"""Phase 0.5 — Part 5: new media write path establishes MediaAsset
references on create/edit, without duplicating physical uploads.

Written and read carefully this session; NOT executed (no Django runtime
available in this sandbox).
"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "sfb-media-writepath-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class MediaWritePathAssetCreationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="writepath_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username="writepath_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.filter(section_key__in=["hero_banner", "multi_banner"]).delete()
        self.hero_section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=900)
        self.banner_section = StorefrontSection.objects.create(version=self.draft, section_key="multi_banner", order=901)

    def test_add_slide_creates_a_desktop_asset_pointing_at_the_uploaded_file(self):
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "اسلاید با asset", "destination_type": "none", "desktop_image": _img(), "is_active": "on"},
        )
        slide = HeroSlide.objects.get(section=self.hero_section)
        self.assertIsNotNone(slide.desktop_asset_id)
        asset = MediaAsset.objects.get(pk=slide.desktop_asset_id)
        self.assertEqual(asset.store_id, self.store.pk)
        self.assertEqual(asset.image.name, slide.desktop_image.name)

    def test_add_slide_with_both_images_creates_two_assets(self):
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {
                "title": "اسلاید دوتصویری", "destination_type": "none",
                "desktop_image": _img("d.png"), "mobile_image": _img("m.png"), "is_active": "on",
            },
        )
        slide = HeroSlide.objects.get(section=self.hero_section)
        self.assertIsNotNone(slide.desktop_asset_id)
        self.assertIsNotNone(slide.mobile_asset_id)
        self.assertNotEqual(slide.desktop_asset_id, slide.mobile_asset_id)

    def test_editing_title_only_does_not_create_a_new_asset(self):
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "اولیه", "destination_type": "none", "desktop_image": _img(), "is_active": "on"},
        )
        slide = HeroSlide.objects.get(section=self.hero_section)
        original_asset_id = slide.desktop_asset_id
        asset_count_before = MediaAsset.objects.count()

        self.client.post(
            reverse("dashboard:storefront-builder-section-media-edit", args=[self.hero_section.pk, "hero-slides", slide.pk]),
            {"title": "عنوان جدید", "destination_type": "none", "is_active": "on"},
        )
        slide.refresh_from_db()
        self.assertEqual(slide.desktop_asset_id, original_asset_id)
        self.assertEqual(MediaAsset.objects.count(), asset_count_before)

    def test_replacing_the_image_creates_a_new_asset_and_does_not_delete_the_old_one_if_still_referenced(self):
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "اولیه", "destination_type": "none", "desktop_image": _img("first.png"), "is_active": "on"},
        )
        slide = HeroSlide.objects.get(section=self.hero_section)
        old_asset_id = slide.desktop_asset_id

        # Simulate the old asset still being referenced elsewhere (e.g. a
        # Published placement) by creating a second placement pointing at
        # the same asset before the edit happens.
        old_asset = MediaAsset.objects.get(pk=old_asset_id)
        HeroSlide.objects.create(store=self.store, desktop_image=_img(), desktop_asset=old_asset)

        self.client.post(
            reverse("dashboard:storefront-builder-section-media-edit", args=[self.hero_section.pk, "hero-slides", slide.pk]),
            {"title": "اولیه", "destination_type": "none", "desktop_image": _img("second.png"), "is_active": "on"},
        )
        slide.refresh_from_db()
        self.assertNotEqual(slide.desktop_asset_id, old_asset_id)
        # old asset must still exist — it's still referenced by the other
        # placement created above.
        self.assertTrue(MediaAsset.objects.filter(pk=old_asset_id).exists())

    def test_add_banner_creates_asset(self):
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.banner_section.pk, "banners"]),
            {"title": "بنر با asset", "destination_type": "none", "desktop_image": _img(), "is_active": "on"},
        )
        banner = PromotionalBanner.objects.get(section=self.banner_section)
        self.assertIsNotNone(banner.desktop_asset_id)


class MediaDeleteReferenceSafetyTests(TestCase):
    """Part 8 — safe deletion via storefront_section_media_delete.

    MED-001 (Retention-First, architect decision): deleting a Placement
    row via this real endpoint MUST NOT physically delete reusable media
    bytes, nor destroy the MediaAsset metadata row it referenced — even
    when that asset has zero remaining references at the moment of
    deletion. See ``apps.content.services`` for the binding policy this
    proves."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = "sfb-media-delete-safety-test".split(".")[0]
        self.store.admin_subdomain = "sfb-media-delete-safety-test"
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="delete_safety_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST="sfb-media-delete-safety-test.rastisi.localhost")
        self.client.login(username="delete_safety_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.filter(section_key="hero_banner").delete()
        self.hero_section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=900)

    def test_deleting_a_slide_retains_its_previously_unreferenced_asset_row_and_bytes(self):
        """MED-001 Retention-First (supersedes the old, pre-MED-001
        ``test_deleting_a_slide_deletes_its_unreferenced_asset``, which
        proved the now-retired destructive contract): the real
        ``storefront_section_media_delete`` endpoint deletes the
        Placement row, but the ``MediaAsset`` it referenced — even though
        it now has zero remaining references — is intentionally RETAINED,
        both as a metadata row and as physical bytes."""
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "برای حذف", "destination_type": "none", "desktop_image": _img(), "is_active": "on"},
        )
        slide = HeroSlide.objects.get(section=self.hero_section)
        asset_id = slide.desktop_asset_id
        asset = MediaAsset.objects.get(pk=asset_id)
        physical_name = asset.image.name
        storage = asset.image.storage
        self.assertTrue(storage.exists(physical_name))

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse(
                    "dashboard:storefront-builder-section-media-delete",
                    args=[self.hero_section.pk, "hero-slides", slide.pk],
                ),
            )

        self.assertFalse(HeroSlide.objects.filter(pk=slide.pk).exists())
        # Retention-First: the now-unreferenced MediaAsset row AND its
        # physical bytes both survive.
        self.assertTrue(MediaAsset.objects.filter(pk=asset_id).exists())
        self.assertTrue(storage.exists(physical_name))

    def test_deleting_a_slide_does_not_delete_asset_still_used_by_another_placement(self):
        self.client.post(
            reverse("dashboard:storefront-builder-section-media-add", args=[self.hero_section.pk, "hero-slides"]),
            {"title": "مشترک", "destination_type": "none", "desktop_image": _img(), "is_active": "on"},
        )
        slide = HeroSlide.objects.get(section=self.hero_section)
        shared_asset = MediaAsset.objects.get(pk=slide.desktop_asset_id)
        # another placement (e.g. a Published one) referencing the same asset
        HeroSlide.objects.create(store=self.store, desktop_image=_img(), desktop_asset=shared_asset)

        self.client.post(
            reverse("dashboard:storefront-builder-section-media-delete", args=[self.hero_section.pk, "hero-slides", slide.pk]),
        )
        self.assertTrue(MediaAsset.objects.filter(pk=shared_asset.pk).exists())
