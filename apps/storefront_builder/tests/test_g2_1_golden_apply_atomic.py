"""G2.1 hardening (Issue 2) — the Golden setup must be all-or-nothing.

``layout_service.publish`` commits the new published pointer in its own atomic
block; media attachment happens afterward. If media attachment fails, the store
must NOT be left with a half-set-up Golden version live. ``apply_golden_reference_storefront``
wraps the whole flow (discard/create draft -> baseline apply -> customize ->
publish -> media attach) in one OUTER ``transaction.atomic``, so any failure
rolls back to the exact prior published state.
"""

import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.storefront_builder.services import golden_reference_service, layout_service
from apps.stores.management.commands.seed_ready_template_fashion_demo import STORE_SLUG
from apps.stores.models import Store


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class GoldenApplyAtomicRollbackTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        # Seed catalog/content only (no owner needed for this test).
        call_command("seed_ready_template_fashion_demo", stdout=StringIO())
        self.store = Store.objects.get(slug=STORE_SLUG)

    def test_apply_rolls_back_completely_when_media_attachment_fails(self):
        # 1) Establish a valid previous published Golden version.
        first = golden_reference_service.apply_golden_reference_storefront(self.store)
        layout = layout_service.get_or_create_layout(self.store)
        self.assertIsNotNone(layout.published_version_id)
        self.assertEqual(layout.published_version_id, first.pk)
        prior_published_id = layout.published_version_id

        # 2) Force media attachment to raise AFTER the publish call.
        boom = RuntimeError("forced media-attach failure")
        with mock.patch.object(
            golden_reference_service, "_back_shared_media_with_assets", side_effect=boom
        ):
            # 3/4) The exception must propagate.
            with self.assertRaises(RuntimeError):
                golden_reference_service.apply_golden_reference_storefront(self.store)

        # 5) Refresh the layout from the DB.
        layout = layout_service.get_or_create_layout(self.store)
        layout.refresh_from_db()

        # 6) The previous published version is STILL the published pointer.
        self.assertEqual(
            layout.published_version_id, prior_published_id,
            "a failed Golden apply must not change the published pointer",
        )
        # 7) No half-published Golden version became live: the live version is
        #    exactly the prior one and is renderable.
        self.assertEqual(layout.published_version.pk, prior_published_id)
        self.assertEqual(
            layout.published_version.status,
            layout.published_version.Status.PUBLISHED,
        )
        # The prior published Home composition is intact (12 Golden sections).
        home = layout.published_version.home_page()
        self.assertGreater(home.sections.count(), 0)

    def test_successful_apply_still_publishes_and_keeps_media_shared_and_asset_backed(self):
        # Guard that the atomic wrapper didn't break the happy path. ARCH-02: the store's media
        # stays store-owned (section=NULL) and MediaAsset-backed; it is NOT moved onto the
        # sections of the Golden template.
        from apps.content.models import HeroSlide, PromotionalBanner, StoryRailItem

        published = golden_reference_service.apply_golden_reference_storefront(self.store)
        home = published.home_page()
        hero = next(s for s in home.sections.order_by("order") if s.section_key == "hero_banner")
        self.assertEqual(HeroSlide.objects.filter(section=hero).count(), 0)
        shared = HeroSlide.objects.filter(store=self.store, section__isnull=True)
        self.assertGreater(shared.count(), 0)
        self.assertFalse(shared.filter(desktop_asset__isnull=True).exists())
        self.assertFalse(PromotionalBanner.objects.filter(store=self.store, section__isnull=True, desktop_asset__isnull=True).exists())
        self.assertFalse(StoryRailItem.objects.filter(store=self.store, section__isnull=True, image_asset__isnull=True).exists())
        # idempotent: a second apply neither moves nor duplicates anything
        counts = (HeroSlide.objects.count(), PromotionalBanner.objects.count(), StoryRailItem.objects.count())
        golden_reference_service.apply_golden_reference_storefront(self.store)
        self.assertEqual(counts, (HeroSlide.objects.count(), PromotionalBanner.objects.count(), StoryRailItem.objects.count()))
