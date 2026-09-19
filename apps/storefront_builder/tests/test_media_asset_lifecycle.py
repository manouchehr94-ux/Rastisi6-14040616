"""Phase 0.5 — Part 11.B/C/D/E/F/G/H/I/J/K: MediaAsset vs. Placement
lifecycle, Published/Draft independence, and the exact real-bug
reproduction the owner ran locally (kianstock-qa, HeroSlide id=12/13
pointing at an archived section).

These tests were written and read carefully in this session but were NOT
executed — no Django runtime is available in this sandbox (see
STOREFRONT_BUILDER_V2_PHASE_0_5_REPORT.md, section "Tests not executed in
sandbox"). The owner is expected to run them locally alongside the
existing 220-test baseline.
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
from apps.content.services import delete_media_asset_if_unreferenced
from apps.storefront_builder.models import StorefrontSection
from apps.storefront_builder.services import layout_service as svc
from apps.stores.models import Store, StoreMembership

User = get_user_model()
HOST = "sfb-media-lifecycle-test.rastisi.localhost"


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _other_store():
    return Store.objects.create(
        name="فروشگاه رسانه دوم", slug="sfb-media-lifecycle-other", admin_subdomain="sfb-media-lifecycle-other",
    )


def _img(name="test.png"):
    buf = BytesIO()
    Image.new("RGB", (800, 400), (10, 20, 30)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class MediaAssetModelTests(TestCase):
    """Sanity checks on the new MediaAsset model itself."""

    def setUp(self):
        cache.clear()

    def test_asset_not_referenced_by_default(self):
        asset = MediaAsset.objects.create(store=_akhlaghi(), image=_img())
        self.assertFalse(asset.is_referenced())

    def test_asset_referenced_once_a_placement_points_at_it(self):
        store = _akhlaghi()
        asset = MediaAsset.objects.create(store=store, image=_img())
        HeroSlide.objects.create(store=store, desktop_image=_img(), desktop_asset=asset)
        self.assertTrue(asset.is_referenced())


class PublishedDraftMediaIndependenceTests(TestCase):
    """Part 11.B — the core Owner Decision 4 guarantee."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_published_placement_untouched_and_draft_gets_separate_row_sharing_the_asset(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        published_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید یک",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)
        published_slide.refresh_from_db()
        published_section = published_slide.section

        d2 = svc.get_or_create_draft(self.store)
        draft_section = d2.sections.get(section_key="hero_banner")

        draft_slide = HeroSlide.objects.get(section=draft_section)

        # Published placement must still exist, still point at the
        # Published section, and be completely untouched.
        self.assertTrue(HeroSlide.objects.filter(pk=published_slide.pk).exists())
        published_slide.refresh_from_db()
        self.assertEqual(published_slide.section_id, published_section.pk)
        self.assertEqual(published_slide.title, "اسلاید یک")

        # Draft gets a SEPARATE placement row.
        self.assertNotEqual(draft_slide.pk, published_slide.pk)
        self.assertEqual(draft_slide.section_id, draft_section.pk)

        # Both placements reference the SAME MediaAsset.
        self.assertEqual(draft_slide.desktop_asset_id, asset.pk)
        self.assertEqual(published_slide.desktop_asset_id, asset.pk)

    def test_editing_draft_placement_does_not_mutate_published_placement(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        published_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="عنوان اصلی",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        draft_section = d2.sections.get(section_key="hero_banner")
        draft_slide = HeroSlide.objects.get(section=draft_section)
        draft_slide.title = "عنوان تغییریافته در Draft"
        draft_slide.save(update_fields=["title"])

        published_slide.refresh_from_db()
        self.assertEqual(published_slide.title, "عنوان اصلی")


class HeroSlideCloneTests(TestCase):
    """Part 11.C — reproduces the exact real bug class the owner found on
    kianstock-qa (HeroSlide scoped to an archived section, invisible on
    both Published v21 and Draft v22)."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_published_scoped_hero_slide_exists_in_both_versions_as_separate_rows(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید یک",
            desktop_image=_img(), desktop_asset=asset,
        )
        HeroSlide.objects.create(
            store=self.store, section=section, title="عنوان دومی",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        draft_section = d2.sections.get(section_key="hero_banner")

        draft_titles = set(HeroSlide.objects.filter(section=draft_section).values_list("title", flat=True))
        self.assertEqual(draft_titles, {"اسلاید یک", "عنوان دومی"})
        # both draft rows must be genuinely new rows, not the same PKs as
        # the published ones. Phase 1A: the lookup chain grows one hop
        # deeper (section__page__version__status) since StorefrontSection
        # now belongs to a StorefrontPage rather than directly to a
        # StorefrontLayoutVersion.
        published_pks = set(HeroSlide.objects.filter(section__page__version__status="published").values_list("pk", flat=True))
        draft_pks = set(HeroSlide.objects.filter(section=draft_section).values_list("pk", flat=True))
        self.assertEqual(published_pks & draft_pks, set())


class PromotionalBannerCloneTests(TestCase):
    """Part 11.D — same reproduction, for PromotionalBanner."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_scoped_banner_exists_in_both_versions_as_separate_rows(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="single_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        PromotionalBanner.objects.create(
            store=self.store, section=section, title="بنر اصلی",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        draft_section = d2.sections.get(section_key="single_banner")
        self.assertTrue(PromotionalBanner.objects.filter(section=draft_section, title="بنر اصلی").exists())
        self.assertTrue(PromotionalBanner.objects.filter(section__page__version__status="published", title="بنر اصلی").exists())


class StoryRailItemCloneTests(TestCase):
    """Part 11.E — same reproduction, for StoryRailItem."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_scoped_story_item_exists_in_both_versions_as_separate_rows(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="story_rail", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        StoryRailItem.objects.create(
            store=self.store, section=section, title="استوری اصلی",
            image=_img(), image_asset=asset,
        )
        svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        draft_section = d2.sections.get(section_key="story_rail")
        self.assertTrue(StoryRailItem.objects.filter(section=draft_section, title="استوری اصلی").exists())
        self.assertTrue(StoryRailItem.objects.filter(section__page__version__status="published", title="استوری اصلی").exists())


class DraftDiscardMediaSafetyTests(TestCase):
    """Part 11.F — Discard Draft must not damage Published media."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_discard_deletes_only_draft_placement_keeps_published_placement_and_asset(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        published_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید ثابت",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        draft_section = d2.sections.get(section_key="hero_banner")
        draft_slide = HeroSlide.objects.get(section=draft_section)

        svc.discard_draft(self.store)

        self.assertFalse(HeroSlide.objects.filter(pk=draft_slide.pk).exists())
        self.assertTrue(HeroSlide.objects.filter(pk=published_slide.pk).exists())
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())

        # Published still renders its media (proven at the render layer,
        # not just the DB layer).
        from apps.storefront_builder.services.render_service import build_render_items

        layout = svc.get_or_create_layout(self.store)
        items = build_render_items(layout.published_version, self.store)
        hero_item = next(i for i in items if i["section"].section_key == "hero_banner")
        slide_titles = [s.title for s in hero_item["context"]["hero_slides"]]
        self.assertIn("اسلاید ثابت", slide_titles)


class RestoreMediaCloneTests(TestCase):
    """Part 11.G — Restore an archived version into a Draft; assert
    placement clone correctness and Published isolation."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_restore_clones_media_and_does_not_touch_current_published(self):
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        HeroSlide.objects.create(
            store=self.store, section=section, title="نسخه یک",
            desktop_image=_img(), desktop_asset=asset,
        )
        v1 = svc.publish(self.store)

        d2 = svc.get_or_create_draft(self.store)
        d2.sections.filter(section_key="hero_banner").delete()
        v2_section = StorefrontSection.objects.create(version=d2, section_key="hero_banner", order=0)
        HeroSlide.objects.create(
            store=self.store, section=v2_section, title="نسخه دو",
            desktop_image=_img(), desktop_asset=asset,
        )
        v2 = svc.publish(self.store)

        restored = svc.restore_version(self.store, v1.pk)
        restored_section = restored.sections.get(section_key="hero_banner")
        self.assertTrue(HeroSlide.objects.filter(section=restored_section, title="نسخه یک").exists())

        # v2 (still the currently-published version at the time of
        # restore) must be completely unaffected. Phase 1A: one extra hop
        # (section__page__version) since section no longer FKs the
        # version directly.
        v2.refresh_from_db()
        self.assertTrue(HeroSlide.objects.filter(section__page__version=v2, title="نسخه دو").exists())


class ApplyIndustryLayoutMediaSafetyTests(TestCase):
    """Part 11.H — apply_industry_layout replacing an existing Draft must
    not damage Published media assets."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_apply_industry_layout_does_not_damage_published_media(self):
        from apps.catalog.models import IndustryTemplate

        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        section = StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        published_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید امن",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)

        template = IndustryTemplate.objects.create(
            slug="test-apply-industry-media-safety", name="صنف تست",
            default_section_keys=["hero_banner"],
        )
        svc.apply_industry_layout(self.store, template, force=True)

        self.assertTrue(HeroSlide.objects.filter(pk=published_slide.pk).exists())
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())


class CrossStoreMediaAssetSafetyTests(TestCase):
    """Part 11.I — a placement for Store A must not be allowed to
    reference a MediaAsset from Store B."""

    def setUp(self):
        cache.clear()
        self.store_a = _akhlaghi()
        self.store_b = _other_store()

    def test_placement_cross_store_asset_rejected_on_full_clean(self):
        from django.core.exceptions import ValidationError

        asset_b = MediaAsset.objects.create(store=self.store_b, image=_img())
        slide = HeroSlide(
            store=self.store_a, title="تلاش برای نفوذ",
            desktop_image=_img(), desktop_asset=asset_b,
        )
        with self.assertRaises(ValidationError):
            slide.full_clean()


class LegacyGlobalMediaFallbackTests(TestCase):
    """Part 11.J — section=NULL (legacy/global) media must retain its
    current fallback behavior, completely unaffected by Phase 0.5."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_global_slide_still_renders_when_section_has_no_scoped_slides(self):
        from apps.storefront_builder.services.render_service import build_render_items

        HeroSlide.objects.create(
            store=self.store, section=None, title="اسلاید سراسری قدیمی", desktop_image=_img(),
        )
        d1 = svc.get_or_create_draft(self.store)
        d1.sections.all().delete()
        StorefrontSection.objects.create(version=d1, section_key="hero_banner", order=0)

        items = build_render_items(d1, self.store)
        hero_item = next(i for i in items if i["section"].section_key == "hero_banner")
        titles = [s.title for s in hero_item["context"]["hero_slides"]]
        self.assertIn("اسلاید سراسری قدیمی", titles)


class SectionDuplicateMediaTests(TestCase):
    """Part 11.K — duplicating a media-capable section."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()
        host = HOST
        self.store.admin_subdomain = host.split(".")[0]
        self.store.save(update_fields=["admin_subdomain"])
        self.staff = User.objects.create_user(username="media_dup_owner", password="pass12345", is_staff=True)
        StoreMembership.objects.create(
            store=self.store, user=self.staff, role=StoreMembership.Role.OWNER,
            status=StoreMembership.MembershipStatus.ACTIVE, accepted_at=timezone.now(),
        )
        self.client = Client(HTTP_HOST=host)
        self.client.login(username="media_dup_owner", password="pass12345")
        self.draft = svc.get_or_create_draft(self.store)
        self.draft.sections.all().delete()

    def test_duplicating_hero_section_duplicates_placements_sharing_the_asset(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        section = StorefrontSection.objects.create(version=self.draft, section_key="hero_banner", order=0)
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        original_slide = HeroSlide.objects.create(
            store=self.store, section=section, title="اسلاید اصلی",
            desktop_image=_img(), desktop_asset=asset,
        )

        self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))

        duplicate_section = self.draft.sections.filter(section_key="hero_banner").exclude(pk=section.pk).get()
        self.assertNotEqual(duplicate_section.stable_id, section.stable_id)

        duplicated_slide = HeroSlide.objects.get(section=duplicate_section)
        self.assertNotEqual(duplicated_slide.pk, original_slide.pk)
        self.assertEqual(duplicated_slide.desktop_asset_id, asset.pk)
        self.assertEqual(duplicated_slide.title, "اسلاید اصلی")

        # Editing the duplicate must not mutate the original.
        duplicated_slide.title = "عنوان ویرایش‌شده"
        duplicated_slide.save(update_fields=["title"])
        original_slide.refresh_from_db()
        self.assertEqual(original_slide.title, "اسلاید اصلی")

    def test_duplicating_non_media_section_does_not_error(self):
        # P5-W5A: this test exercises a legacy Class-A route, which now
        # fails closed under r4_editor_enabled=True (binding policy) --
        # pin explicitly, matching the rollback-editor scenario being tested.
        _w5a_layout = svc.get_or_create_layout(self.store)
        _w5a_layout.r4_editor_enabled = False
        _w5a_layout.save(update_fields=["r4_editor_enabled"])
        section = StorefrontSection.objects.create(version=self.draft, section_key="rich_text", order=0)
        resp = self.client.post(reverse("dashboard:storefront-builder-section-duplicate", args=[section.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.draft.sections.filter(section_key="rich_text").count(), 2)


class DeleteMediaAssetIfUnreferencedServiceTests(TestCase):
    """Part 11.B/H — the explicit cleanup service itself: never deletes an
    asset that is still referenced elsewhere; safely deletes one that
    truly has zero references."""

    def setUp(self):
        cache.clear()
        self.store = _akhlaghi()

    def test_does_not_delete_asset_still_referenced_by_another_placement(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        HeroSlide.objects.create(store=self.store, desktop_image=_img(), desktop_asset=asset)
        deleted = delete_media_asset_if_unreferenced(asset)
        self.assertFalse(deleted)
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())

    def test_deletes_asset_with_zero_references(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        deleted = delete_media_asset_if_unreferenced(asset)
        self.assertTrue(deleted)
        self.assertFalse(MediaAsset.objects.filter(pk=asset.pk).exists())

    def test_none_asset_is_a_safe_noop(self):
        self.assertFalse(delete_media_asset_if_unreferenced(None))
