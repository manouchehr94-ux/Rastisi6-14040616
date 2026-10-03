"""Cloned media edit safety — RED/GREEN regression for the confirmed
Publish→Clone cloned-media-edit defect (endpoint layer).

Reproduces the real merchant lifecycle through the actual HTTP endpoint,
never a shortcut:

    Publish a valid, asset-backed section-scoped media Placement
    → reopen a fresh Draft (``layout_service._clone_section_scoped_media``
      clones the MediaAsset FK, never the legacy ``ImageField`` bytes)
    → open the CLONED Placement in the canonical media CRUD endpoint
      (``apps.storefront_builder.media_views.storefront_section_media_form``)
    → change ONLY the title/text, upload NO new file
    → save

Before the repair this raised ``ValidationError`` inside ``obj.full_clean()``
and silently re-rendered the form — the merchant could never save a
title-only edit of an already-published, asset-backed Placement.

See ``apps/content/tests/test_placement_effective_media_validation.py``
for the same defect proven directly at the model layer.
"""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()

HOST = "cloned-media-edit-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _img(name="test.png", color=(10, 20, 30)):
    buf = BytesIO()
    Image.new("RGB", (800, 400), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class _ClonedMediaEditCaseMixin:
    """Publishes a valid, asset-backed section-scoped media Placement, then
    reopens a fresh Draft (the real clone path) — exactly the lifecycle
    that exposes the confirmed defect — then edits ONLY the title/text of
    the CLONED row through the real canonical CRUD endpoint (never a
    shortcut, never a raw ``.save()``)."""

    kind = None
    model = None
    section_key = None
    asset_field = None
    legacy_field = None
    text_field = None  # the model's own secondary text field (subtitle/description), or None
    url_property = None  # "desktop_image_url" or "image_url"

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        self.store.admin_subdomain = HOST.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(
            username=f"cloned_media_owner_{self.kind}", password="pass12345", is_staff=True,
        )
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=HOST)
        self.client.login(username=self.staff.username, password="pass12345")

        layout = svc.get_or_create_layout(self.store)
        layout.r4_editor_enabled = True
        layout.save(update_fields=["r4_editor_enabled"])

        draft = svc.get_or_create_draft(self.store)
        section = StorefrontSection.objects.create(
            version=draft, section_key=self.section_key, order=960,
        )
        self.asset = MediaAsset.objects.create(store=self.store, image=_img())
        create_kwargs = {
            "store": self.store, "section": section, "title": "عنوان اولیه",
            self.asset_field: self.asset, self.legacy_field: _img(),
        }
        if self.text_field:
            create_kwargs[self.text_field] = "متن اولیه"
        self.model.objects.create(**create_kwargs)

        svc.publish(self.store)
        self.layout = layout
        self.layout.refresh_from_db()
        self.published = self.layout.published_version
        self.draft = svc.get_or_create_draft(self.store)
        self.section = self.draft.sections.get(section_key=self.section_key)
        self.placement = self.model.objects.get(section=self.section)

    def _edit_url(self):
        return reverse(
            "dashboard:storefront-builder-section-media-edit",
            kwargs={"pk": self.section.pk, "kind": self.kind, "item_pk": self.placement.pk},
        )

    def _draft_changed(self):
        self.draft.refresh_from_db()
        self.published.refresh_from_db()
        return self.draft.compute_fingerprint() != self.published.compute_fingerprint()

    def _title_only_edit_payload(self, new_title):
        data = {"title": new_title, "is_active": "on"}
        if self.text_field:
            data[self.text_field] = getattr(self.placement, self.text_field) or ""
        return data


class _TitleOnlyEditSucceedsTestsMixin(_ClonedMediaEditCaseMixin):
    """Case B — title-only edit through the canonical endpoint, without
    re-uploading a file, must persist successfully."""

    def test_title_only_edit_of_cloned_placement_succeeds_without_reupload(self):
        # RED before the fix: this used to raise ValidationError inside
        # obj.full_clean() and re-render the form with an error instead of
        # saving — the merchant could never save a title-only edit.
        self.assertTrue(getattr(self.placement, f"{self.asset_field}_id"))
        self.assertFalse(getattr(self.placement, self.legacy_field))

        response = self.client.post(
            self._edit_url(),
            data=self._title_only_edit_payload("عنوان واقعاً تغییریافته"),
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )

        self.assertEqual(response.status_code, 200)
        self.placement.refresh_from_db()
        self.assertEqual(self.placement.title, "عنوان واقعاً تغییریافته")
        # existing MediaAsset FK preserved, never replaced
        self.assertEqual(getattr(self.placement, f"{self.asset_field}_id"), self.asset.pk)
        # no re-upload happened — legacy field stays empty
        self.assertFalse(getattr(self.placement, self.legacy_field))
        # no duplicate MediaAsset created for this store
        self.assertEqual(MediaAsset.objects.filter(store=self.store).count(), 1)
        # rendered media URL remains valid and points at the same asset
        self.assertEqual(getattr(self.placement, self.url_property), self.asset.image.url)


class _CloneIndependenceTestsMixin(_ClonedMediaEditCaseMixin):
    """Case E — editing the cloned Draft's title must never mutate the
    Published Placement (Published/Draft remain fully separate rows)."""

    def test_editing_cloned_draft_title_does_not_mutate_published(self):
        published_placement = self.model.objects.get(section__page__version=self.published)
        original_published_title = published_placement.title

        response = self.client.post(
            self._edit_url(),
            data=self._title_only_edit_payload("فقط پیش‌نویس تغییر کرد"),
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.status_code, 200)

        published_placement.refresh_from_db()
        self.assertEqual(published_placement.title, original_published_title)
        self.placement.refresh_from_db()
        self.assertEqual(self.placement.title, "فقط پیش‌نویس تغییر کرد")
        self.assertNotEqual(self.placement.pk, published_placement.pk)
        # MediaAsset sharing itself is the existing, unchanged canonical
        # behavior — both rows may still point at the SAME asset.
        self.assertEqual(
            getattr(self.placement, f"{self.asset_field}_id"),
            getattr(published_placement, f"{self.asset_field}_id"),
        )


class _DirtyStateIntegrationTestsMixin(_ClonedMediaEditCaseMixin):
    """Case F — a real title-only edit of a cloned Placement must persist,
    fire the EXISTING ``r4:media-changed`` semantic event, and make the
    Studio report ``draft_changed=True`` with Publish enabled — reusing
    the already-shipped dirty-state contract, never a second copy of it."""

    def test_title_only_edit_emits_media_changed_and_marks_draft_dirty(self):
        self.assertFalse(self._draft_changed())

        response = self.client.post(
            self._edit_url(),
            data=self._title_only_edit_payload("تغییرِ واقعی برایِ Dirty State"),
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")
        self.assertTrue(self._draft_changed())

        studio_response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(studio_response.status_code, 200)
        self.assertTrue(studio_response.context["studio"]["draft_changed"])


class HeroSlideTitleOnlyEditSucceedsTests(_TitleOnlyEditSucceedsTestsMixin, TestCase):
    kind = "hero-slides"
    model = HeroSlide
    section_key = "hero_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"
    text_field = "subtitle"
    url_property = "desktop_image_url"


class PromotionalBannerTitleOnlyEditSucceedsTests(_TitleOnlyEditSucceedsTestsMixin, TestCase):
    kind = "banners"
    model = PromotionalBanner
    section_key = "multi_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"
    text_field = "description"
    url_property = "desktop_image_url"


class StoryRailItemTitleOnlyEditSucceedsTests(_TitleOnlyEditSucceedsTestsMixin, TestCase):
    kind = "story-items"
    model = StoryRailItem
    section_key = "story_rail"
    asset_field = "image_asset"
    legacy_field = "image"
    text_field = None
    url_property = "image_url"


class HeroSlideCloneIndependenceTests(_CloneIndependenceTestsMixin, TestCase):
    kind = "hero-slides"
    model = HeroSlide
    section_key = "hero_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"
    text_field = "subtitle"


class PromotionalBannerCloneIndependenceTests(_CloneIndependenceTestsMixin, TestCase):
    kind = "banners"
    model = PromotionalBanner
    section_key = "multi_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"
    text_field = "description"


class StoryRailItemCloneIndependenceTests(_CloneIndependenceTestsMixin, TestCase):
    kind = "story-items"
    model = StoryRailItem
    section_key = "story_rail"
    asset_field = "image_asset"
    legacy_field = "image"
    text_field = None


class HeroSlideDirtyStateIntegrationTests(_DirtyStateIntegrationTestsMixin, TestCase):
    kind = "hero-slides"
    model = HeroSlide
    section_key = "hero_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"
    text_field = "subtitle"


class PromotionalBannerDirtyStateIntegrationTests(_DirtyStateIntegrationTestsMixin, TestCase):
    kind = "banners"
    model = PromotionalBanner
    section_key = "multi_banner"
    asset_field = "desktop_asset"
    legacy_field = "desktop_image"
    text_field = "description"


class StoryRailItemDirtyStateIntegrationTests(_DirtyStateIntegrationTestsMixin, TestCase):
    kind = "story-items"
    model = StoryRailItem
    section_key = "story_rail"
    asset_field = "image_asset"
    legacy_field = "image"
    text_field = None
