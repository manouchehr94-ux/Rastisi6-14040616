"""Media-publish-dirty repair — TDD regression suite.

Reproduces the real, independently DB-proven Windows Final Visual
Acceptance defect: a section-scoped media write (``HeroSlide``/
``PromotionalBanner``/``StoryRailItem``, made through the existing
canonical inline media manager — ``apps.storefront_builder.media_views``)
was completely invisible to ``StorefrontLayoutVersion.compute_fingerprint``.
The Draft kept reporting "همگام با سایت" (in sync) and the Publish button
stayed disabled even though the Draft's actual, render-visible content
(a brand new Hero Slide) genuinely differed from what was live.

Two independent things are under test here:

1. Server-side dirty detection — ``compute_fingerprint`` now includes
   section-scoped media, fingerprinted by render-visible fields (never a
   row's own ``pk`` — Published and a cloned Draft are separate rows by
   construction), and the live "is the Draft dirty" comparison
   (``r4_views._build_studio_context``) no longer trusts a persisted
   fingerprint that may have been written by an older algorithm.
2. The Studio UI — every successful, persisted, publication-visible media
   write now carries an ``HX-Trigger: r4:media-changed`` response header
   so the shell (``r4_studio.js``) refreshes its own dirty/Publish state
   without requiring a manual reload or an unrelated mutation.
"""

import hashlib
import json
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from apps.content.models import HeroSlide, MediaAsset, PromotionalBanner, StoryRailItem
from apps.storefront_builder.models import StorefrontContainer, StorefrontLayoutVersion, StorefrontSection
from apps.storefront_builder.section_media_contract import placement_semantic_payload
from apps.storefront_builder.services import layout_service as svc

from .test_r4_mutation_api import R4MutationApiTestCase


def _img(name="slide.png", color=(10, 20, 30)):
    buf = BytesIO()
    Image.new("RGB", (800, 400), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


# ---------------------------------------------------------------- A / B — base fixture


class _PublishedAndFreshDraftCase(R4MutationApiTestCase):
    """``self.draft``/``self.section`` (inherited setUp) are published as-is
    (typically empty of media), then a FRESH Draft is reopened — the normal
    "resume editing after Publish" lifecycle (``get_or_create_draft`` clones
    from ``published_version``). Every test in this fixture starts from a
    genuinely unchanged clone."""

    def setUp(self):
        super().setUp()
        svc.publish(self.store)
        self.layout.refresh_from_db()
        self.published = self.layout.published_version
        self.draft = svc.get_or_create_draft(self.store)
        self.section = self.draft.sections.get(section_key="hero_banner")

    def _draft_changed(self):
        self.draft.refresh_from_db()
        self.published.refresh_from_db()
        return self.draft.compute_fingerprint() != self.published.compute_fingerprint()


class MediaOnlyAddMarksDraftChangedTests(_PublishedAndFreshDraftCase):
    """Case A — RED before the fix: adding a HeroSlide only to the Draft
    (no section/settings mutation at all) must flip ``draft_changed``."""

    def test_media_only_hero_slide_add_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        HeroSlide.objects.create(
            store=self.store, section=self.section, title="اسلاید جدید",
            desktop_image=_img(),
        )
        self.assertTrue(self._draft_changed())


class CloneEqualityTests(R4MutationApiTestCase):
    """Case B — an unchanged clone must fingerprint identically to its
    source, even though every media row got a brand new pk."""

    def test_unchanged_clone_matches_fingerprint_despite_different_pks(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        HeroSlide.objects.create(
            store=self.store, section=self.section, title="ثابت",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)
        self.layout.refresh_from_db()
        published = self.layout.published_version
        draft = svc.get_or_create_draft(self.store)

        self.assertEqual(draft.compute_fingerprint(), published.compute_fingerprint())

        draft_section = draft.sections.get(section_key="hero_banner")
        published_section = published.sections.get(section_key="hero_banner")
        draft_slide = HeroSlide.objects.get(section=draft_section)
        published_slide = HeroSlide.objects.get(section=published_section)
        self.assertNotEqual(draft_slide.pk, published_slide.pk)
        self.assertEqual(draft_slide.desktop_asset_id, published_slide.desktop_asset_id)


# ---------------------------------------------------------------- C / D / E — mutations


class _ExistingSlideCase(_PublishedAndFreshDraftCase):
    """A Draft cloned from a Published version that already has one
    HeroSlide — the fixture every "edit an existing placement" case needs."""

    def setUp(self):
        super().setUp()
        # Re-publish once more with a slide already present, then reopen a
        # fresh (unchanged) Draft — mirrors the real merchant lifecycle
        # (edit an already-published slide) rather than editing something
        # that only ever existed in this Draft.
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        HeroSlide.objects.create(
            store=self.store, section=self.section, title="اولیه",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)
        self.layout.refresh_from_db()
        self.published = self.layout.published_version
        self.draft = svc.get_or_create_draft(self.store)
        self.section = self.draft.sections.get(section_key="hero_banner")
        self.slide = HeroSlide.objects.get(section=self.section)


class MediaOnlyEditMarksDraftChangedTests(_ExistingSlideCase):
    """Case C — editing a render-visible property of an existing Placement."""

    def test_title_edit_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        self.slide.title = "عنوان تغییریافته"
        self.slide.save(update_fields=["title"])
        self.assertTrue(self._draft_changed())


class MediaOnlyImageReplacementMarksDraftChangedTests(_ExistingSlideCase):
    """Case D — replacing the actual media asset (a real re-upload)."""

    def test_desktop_asset_replacement_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        new_asset = MediaAsset.objects.create(store=self.store, image=_img("new.png", (99, 1, 1)))
        self.slide.desktop_asset = new_asset
        self.slide.save(update_fields=["desktop_asset"])
        self.assertTrue(self._draft_changed())


class ToggleReorderDeleteMarkDraftChangedTests(_ExistingSlideCase):
    """Case E — every publication-visible lifecycle operation on an
    existing Placement, one focused test each (no combinatorial explosion)."""

    def test_toggle_active_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        self.slide.is_active = False
        self.slide.save(update_fields=["is_active"])
        self.assertTrue(self._draft_changed())

    def test_reorder_marks_draft_changed(self):
        # Every placement here must carry a real ``desktop_asset`` — a row
        # with none is a genuinely legacy shape that
        # ``layout_service._clone_section_scoped_media`` never clones at
        # all (its own, pre-existing, unrelated limitation); this test
        # needs BOTH slides to actually survive the republish/reclone below
        # to isolate a pure reorder.
        second = HeroSlide.objects.create(
            store=self.store, section=self.section, title="دوم",
            desktop_image=_img(), desktop_asset=MediaAsset.objects.create(store=self.store, image=_img()),
            display_order=1,
        )
        # The second slide's own addition already dirties the Draft — reset
        # the baseline to "just these two slides, in this order" before
        # testing that a pure REORDER (no add/remove) is independently
        # detected too.
        svc.publish(self.store)
        self.layout.refresh_from_db()
        self.published = self.layout.published_version
        self.draft = svc.get_or_create_draft(self.store)
        self.section = self.draft.sections.get(section_key="hero_banner")
        slides = list(HeroSlide.objects.filter(section=self.section).order_by("display_order", "id"))
        self.assertFalse(self._draft_changed())

        a, b = slides[0], slides[1]
        a.display_order, b.display_order = b.display_order, a.display_order
        HeroSlide.objects.bulk_update([a, b], ["display_order"])
        self.assertTrue(self._draft_changed())

    def test_delete_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        self.slide.delete()
        self.assertTrue(self._draft_changed())


# ---------------------------------------------------------------- F — all three families


class AllMediaFamiliesFingerprintCoverageTests(_PublishedAndFreshDraftCase):
    """Case F — the contract covers all three section-scoped media models,
    not only HeroSlide."""

    def test_promotional_banner_only_add_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        PromotionalBanner.objects.create(
            store=self.store, section=self.section, title="بنر جدید",
            desktop_image=_img(),
        )
        self.assertTrue(self._draft_changed())

    def test_story_rail_item_only_add_marks_draft_changed(self):
        self.assertFalse(self._draft_changed())
        StoryRailItem.objects.create(
            store=self.store, section=self.section, title="استوری جدید",
            image=_img(),
        )
        self.assertTrue(self._draft_changed())


# ---------------------------------------------------------------- G — legacy compatibility


class LegacyPersistedFingerprintCompatibilityTests(R4MutationApiTestCase):
    """Case G — MANDATORY regression: a Published version whose STORED
    ``content_fingerprint`` was produced by the pre-fix algorithm (no
    ``media`` key at all) must never force a false "منتشرنشده" on an
    otherwise completely unchanged Draft. The live comparison
    (``r4_views._build_studio_context``) must never trust that stored
    string — it must recompute both sides fresh, under the CURRENT
    algorithm, every time."""

    def _legacy_shape_fingerprint(self, version):
        """Rebuilds exactly the payload ``compute_fingerprint`` produced
        BEFORE this repair — same sections/containers shape, but with no
        ``"media"`` key at all — and hashes it the same way. This is not a
        guess at the old algorithm; it is the old algorithm's own literal
        output shape, reproduced field-for-field from the pre-fix source
        (see this module's own diff for the exact key that was added)."""
        sections = []
        for s in version.sections.select_related("page").order_by("page__page_type", "order", "id"):
            sections.append({
                "page_type": s.page.page_type, "section_key": s.section_key,
                "order": s.order, "is_active": s.is_active, "settings": s.settings,
                "row_key": s.row_key, "row_span": s.row_span,
            })
        containers = []
        qs = (
            StorefrontContainer.objects.filter(page__version=version)
            .select_related("page").prefetch_related("cells__section", "cells__blocks")
            .order_by("page__page_type", "order", "id")
        )
        for container in qs:
            containers.append({
                "page_type": container.page.page_type,
                "order": container.order,
                "layout_key": container.layout_key,
                "settings": container.settings,
                "cells": [
                    {
                        "order": cell.order, "span": cell.span, "settings": cell.settings,
                        "section_stable_id": (
                            str(cell.section.stable_id) if cell.section_id else None
                        ),
                        "blocks": [
                            {"section_stable_id": str(block.stable_id), "cell_order": block.cell_order}
                            for block in cell.blocks.order_by("cell_order", "id")
                        ],
                    }
                    for cell in container.cells.all().order_by("order", "id")
                ],
            })
        payload = {
            "header_config": version.header_config, "footer_config": version.footer_config,
            "appearance_config": version.appearance_config, "sections": sections,
            "containers": containers,
        }
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def test_stale_pre_fix_persisted_fingerprint_does_not_force_false_dirty(self):
        asset = MediaAsset.objects.create(store=self.store, image=_img())
        HeroSlide.objects.create(
            store=self.store, section=self.section, title="ثابت",
            desktop_image=_img(), desktop_asset=asset,
        )
        svc.publish(self.store)
        self.layout.refresh_from_db()
        published = self.layout.published_version

        legacy_fingerprint = self._legacy_shape_fingerprint(published)
        # Sanity: the legacy shape really does differ from the CURRENT
        # algorithm's own output for this same version — otherwise this
        # test would prove nothing.
        self.assertNotEqual(legacy_fingerprint, published.compute_fingerprint())
        StorefrontLayoutVersion.objects.filter(pk=published.pk).update(
            content_fingerprint=legacy_fingerprint,
        )

        # Nothing about the store's content changes here — this is exactly
        # the normal "resume editing" lifecycle, with a persisted fingerprint
        # left over from before this repair shipped.
        svc.get_or_create_draft(self.store)
        response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["studio"]["draft_changed"])


# ---------------------------------------------------------------- H — post-publish sync


class PostPublishSynchronizationTests(R4MutationApiTestCase):
    """Case H — publishing a media-only-dirty Draft, then reopening a fresh
    one, must show fully synced state again."""

    def test_publish_then_reopen_draft_is_synced(self):
        # Real ``desktop_asset`` required — see the comment in
        # ``test_reorder_marks_draft_changed`` above; this test publishes
        # and reclones, so the slide must actually survive that.
        HeroSlide.objects.create(
            store=self.store, section=self.section, title="نهایی",
            desktop_image=_img(), desktop_asset=MediaAsset.objects.create(store=self.store, image=_img()),
        )
        response_before = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertTrue(response_before.context["studio"]["draft_changed"])

        svc.publish(self.store)
        self.layout.refresh_from_db()
        published = self.layout.published_version
        self.assertEqual(
            list(HeroSlide.objects.filter(section__page__version=published).values_list("title", flat=True)),
            ["نهایی"],
        )

        svc.get_or_create_draft(self.store)
        response_after = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(response_after.status_code, 200)
        self.assertFalse(response_after.context["studio"]["draft_changed"])


# ---------------------------------------------------------------- Inline HTMX contract


class MediaWriteHtmxTriggerContractTests(R4MutationApiTestCase):
    """Section 10 — the ONLY signal the R4 shell trusts for "a persisted,
    publication-visible media change happened": the ``HX-Trigger:
    r4:media-changed`` response header. A GET, an invalid submission, or a
    genuine no-op (duplicate reorder ids, an out-of-range move) must never
    carry it."""

    def _add_url(self, kind="hero-slides"):
        return reverse(
            "dashboard:storefront-builder-section-media-add",
            kwargs={"pk": self.section.pk, "kind": kind},
        )

    def _edit_url(self, item_pk, kind="hero-slides"):
        return reverse(
            "dashboard:storefront-builder-section-media-edit",
            kwargs={"pk": self.section.pk, "kind": kind, "item_pk": item_pk},
        )

    def _existing_slide(self):
        return HeroSlide.objects.create(
            store=self.store, section=self.section, title="موجود", desktop_image=_img(),
        )

    def test_valid_add_sets_trigger(self):
        response = self.client.post(
            self._add_url(),
            data={"title": "اسلاید معتبر", "is_active": "on", "desktop_image": _img()},
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")

    def test_invalid_add_does_not_set_trigger(self):
        response = self.client.post(
            self._add_url(),
            data={"title": "بدون تصویر", "is_active": "on"},
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)
        self.assertFalse(HeroSlide.objects.filter(section=self.section).exists())

    def test_get_list_does_not_set_trigger(self):
        response = self.client.get(
            reverse(
                "dashboard:storefront-builder-section-media-list",
                kwargs={"pk": self.section.pk, "kind": "hero-slides"},
            ),
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)

    def test_valid_edit_sets_trigger(self):
        slide = self._existing_slide()
        response = self.client.post(
            self._edit_url(slide.pk),
            data={"title": "ویرایش‌شده", "is_active": "on"},
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")

    def test_valid_delete_sets_trigger(self):
        slide = self._existing_slide()
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-delete",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": slide.pk},
            ),
        )
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")

    def test_valid_toggle_sets_trigger(self):
        slide = self._existing_slide()
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-toggle",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": slide.pk},
            ),
        )
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")

    def test_valid_in_range_move_sets_trigger(self):
        first = self._existing_slide()
        second = HeroSlide.objects.create(
            store=self.store, section=self.section, title="دوم",
            desktop_image=_img(), display_order=1,
        )
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-move",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": second.pk},
            ),
            data={"direction": "up"},
        )
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")

    def test_out_of_range_move_does_not_set_trigger(self):
        first = self._existing_slide()
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-move",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": first.pk},
            ),
            data={"direction": "up"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)

    def test_valid_reorder_sets_trigger(self):
        a = self._existing_slide()
        b = HeroSlide.objects.create(
            store=self.store, section=self.section, title="ب",
            desktop_image=_img(), display_order=1,
        )
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-reorder",
                kwargs={"pk": self.section.pk, "kind": "hero-slides"},
            ),
            data={"item_ids": [str(b.pk), str(a.pk)]},
        )
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")

    def test_reorder_with_duplicate_ids_does_not_set_trigger(self):
        a = self._existing_slide()
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-reorder",
                kwargs={"pk": self.section.pk, "kind": "hero-slides"},
            ),
            data={"item_ids": [str(a.pk), str(a.pk)]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)


# ---------------------------------------------------------------- Final hardening — semantic no-op gating


class IdenticalEditDoesNotMarkDraftChangedTests(_ExistingSlideCase):
    """Correction 3 — ``r4:media-changed`` must mean a publication-semantic
    change actually happened, not merely that ``.save()`` ran. An EDIT that
    re-submits the exact same render-visible values (same title, same
    active state, no new/removed file, no destination change) must NOT
    carry the trigger, must NOT change ``compute_fingerprint()``'s output,
    and must NOT make the Studio transiently report the Draft as
    unpublished."""

    def setUp(self):
        super().setUp()
        # Test-fixture-only workaround for a SEPARATE, pre-existing,
        # out-of-scope defect (documented separately as a Final-Freeze
        # blocker, not touched by this repair): ``_clone_section_scoped_
        # media`` deliberately never copies the legacy ``ImageField`` bytes
        # on clone (see its own docstring), so a freshly-cloned row like
        # ``self.slide`` fails ``full_clean()`` the instant it's re-saved
        # through the edit form — regardless of whether anything actually
        # changed. Restoring a legacy image directly on the row here is
        # purely test setup, never a production change: it's invisible to
        # ``compute_fingerprint()`` (the shared semantic payload only ever
        # falls back to the legacy file when ``desktop_asset_id`` is unset;
        # here it's already set, so this write can't move the fingerprint).
        # It exists only so this test can exercise a genuinely healthy,
        # previously-synced Placement without going anywhere near that
        # other defect.
        self.slide.desktop_image = _img("healed.png", (5, 5, 5))
        self.slide.save(update_fields=["desktop_image"])
        self.assertFalse(self._draft_changed())

    def test_identical_edit_does_not_set_trigger_or_mark_draft_changed(self):
        self.assertFalse(self._draft_changed())
        fp_before = self.draft.compute_fingerprint()

        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-edit",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": self.slide.pk},
            ),
            data={"title": self.slide.title, "is_active": "on"},
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)

        self.slide.refresh_from_db()
        fp_after = self.draft.compute_fingerprint()
        self.assertEqual(fp_before, fp_after)
        self.assertFalse(self._draft_changed())

        studio_response = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(studio_response.status_code, 200)
        self.assertFalse(studio_response.context["studio"]["draft_changed"])

    def test_real_edit_after_identical_edit_still_sets_trigger(self):
        # Guards against an over-broad fix (e.g. accidentally disabling the
        # event entirely) — a genuinely different value must still trigger,
        # even right after a no-op identical save on the same row.
        self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-edit",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": self.slide.pk},
            ),
            data={"title": self.slide.title, "is_active": "on"},
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-edit",
                kwargs={"pk": self.section.pk, "kind": "hero-slides", "item_pk": self.slide.pk},
            ),
            data={"title": "عنوانِ واقعاً تغییریافته", "is_active": "on"},
            HTTP_HX_REQUEST="true", HTTP_HX_R4_INLINE="1",
        )
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")
        self.assertTrue(self._draft_changed())


class IdenticalReorderDoesNotMarkDraftChangedTests(R4MutationApiTestCase):
    """Correction 3 — if the requested valid reorder already equals the
    CURRENT effective order, nothing changed: no trigger, and (narrowly)
    no unnecessary DB write either."""

    def test_identical_reorder_does_not_set_trigger_or_write(self):
        a = HeroSlide.objects.create(
            store=self.store, section=self.section, title="اول",
            desktop_image=_img(), display_order=0,
        )
        b = HeroSlide.objects.create(
            store=self.store, section=self.section, title="دوم",
            desktop_image=_img(), display_order=1,
        )

        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-reorder",
                kwargs={"pk": self.section.pk, "kind": "hero-slides"},
            ),
            data={"item_ids": [str(a.pk), str(b.pk)]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.display_order, 0)
        self.assertEqual(b.display_order, 1)

    def test_reorder_to_a_genuinely_different_order_still_sets_trigger(self):
        # Sibling positive control — the same two rows, in the OTHER order,
        # must still trigger (proves the no-op guard isn't over-broad).
        a = HeroSlide.objects.create(
            store=self.store, section=self.section, title="اول",
            desktop_image=_img(), display_order=0,
        )
        b = HeroSlide.objects.create(
            store=self.store, section=self.section, title="دوم",
            desktop_image=_img(), display_order=1,
        )
        response = self.client.post(
            reverse(
                "dashboard:storefront-builder-section-media-reorder",
                kwargs={"pk": self.section.pk, "kind": "hero-slides"},
            ),
            data={"item_ids": [str(b.pk), str(a.pk)]},
        )
        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.display_order, 0)
        self.assertEqual(a.display_order, 1)


class MoveSemanticNoOpTests(R4MutationApiTestCase):
    """MOVE semantic-event gap (final-review finding) — an in-range
    positional swap alone is never proof anything publication-visible
    changed. ``storefront_section_media_move`` must compare the CANONICAL
    ORDERED SEQUENCE of ``placement_semantic_payload`` values (never a raw
    numeric ``display_order`` inequality — no DB constraint prevents two
    rows in the same section from already sharing one) before vs. after
    the swap, and only persist/emit ``r4:media-changed`` when that
    sequence genuinely differs."""

    def _move_up_url(self, item_pk, kind="hero-slides"):
        return reverse(
            "dashboard:storefront-builder-section-media-move",
            kwargs={"pk": self.section.pk, "kind": kind, "item_pk": item_pk},
        )

    def test_equal_display_order_move_does_not_set_trigger_or_change_order(self):
        # Two rows already sharing a display_order — reachable because no
        # UniqueConstraint on this field exists (confirmed: HeroSlide's own
        # Meta declares only ``ordering``, never a uniqueness constraint).
        a = HeroSlide.objects.create(
            store=self.store, section=self.section, title="اول",
            desktop_image=_img(), display_order=0,
        )
        b = HeroSlide.objects.create(
            store=self.store, section=self.section, title="دوم",
            desktop_image=_img(), display_order=0,
        )
        fp_before = self.draft.compute_fingerprint()

        response = self.client.post(self._move_up_url(b.pk), data={"direction": "up"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.display_order, 0)
        self.assertEqual(b.display_order, 0)
        self.assertEqual(self.draft.compute_fingerprint(), fp_before)

    def test_semantically_identical_placements_move_does_not_set_trigger(self):
        # Different display_order values (0/1 — a naive numeric-inequality
        # check would treat this as "changed"), but every OTHER
        # render-visible field (title/subtitle/button/active/destination/
        # the shared MediaAsset) matches exactly, so swapping them produces
        # the exact same canonical ordered sequence: this collapses to the
        # SAME "no real change" outcome as case #1, proven here via a
        # distinct row shape (matching asset, not matching display_order)
        # so the two tests exercise genuinely different code paths through
        # ``placement_semantic_payload`` (the legacy-fallback-free asset-id
        # branch) rather than duplicating the same scenario.
        shared_asset = MediaAsset.objects.create(store=self.store, image=_img())
        a = HeroSlide.objects.create(
            store=self.store, section=self.section, title="یکسان",
            desktop_image=_img(), desktop_asset=shared_asset, display_order=0,
        )
        b = HeroSlide.objects.create(
            store=self.store, section=self.section, title="یکسان",
            desktop_image=_img(), desktop_asset=shared_asset, display_order=1,
        )
        related_name = "hero_slides"
        before_sequence = [
            placement_semantic_payload(row, related_name)
            for row in HeroSlide.objects.filter(section=self.section).order_by("display_order", "id")
        ]

        response = self.client.post(self._move_up_url(b.pk), data={"direction": "up"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("HX-Trigger", response.headers)
        after_sequence = [
            placement_semantic_payload(row, related_name)
            for row in HeroSlide.objects.filter(section=self.section).order_by("display_order", "id")
        ]
        self.assertEqual(after_sequence, before_sequence)

    def test_publication_distinct_placements_move_sets_trigger_and_persists(self):
        # Positive control — two rows with genuinely different render-visible
        # content (different titles) and normal distinct orders: the move
        # must still persist and still fire the event exactly as before this
        # fix (guards against an over-broad no-op that would silently break
        # every real reorder).
        a = HeroSlide.objects.create(
            store=self.store, section=self.section, title="اول",
            desktop_image=_img(), display_order=0,
        )
        b = HeroSlide.objects.create(
            store=self.store, section=self.section, title="دوم",
            desktop_image=_img(), display_order=1,
        )
        fp_before = self.draft.compute_fingerprint()

        response = self.client.post(self._move_up_url(b.pk), data={"direction": "up"})

        self.assertEqual(response.headers.get("HX-Trigger"), "r4:media-changed")
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(b.display_order, 0)
        self.assertEqual(a.display_order, 1)
        self.assertNotEqual(self.draft.compute_fingerprint(), fp_before)


class MediaFingerprintQueryRegressionTests(R4MutationApiTestCase):
    """Correction 2 — ``compute_fingerprint()``'s own ``prefetch_related``
    must not be defeated by a subsequent queryset-modifying call (the
    well-known Django gotcha: ANY further call like ``.order_by()`` on a
    prefetched manager bypasses the prefetch cache and re-queries). Query
    count must be bounded by the number of media families (fixed — 3),
    not linear in the number of media-bearing sections."""

    def _hero_section_with_slide(self, order):
        section = StorefrontSection.objects.create(
            version=self.draft, section_key="hero_banner", order=order,
        )
        HeroSlide.objects.create(
            store=self.store, section=section, title=f"اسلاید {order}",
            desktop_image=_img(),
            desktop_asset=MediaAsset.objects.create(store=self.store, image=_img()),
        )
        return section

    def test_query_count_bounded_by_media_family_not_section_count(self):
        with CaptureQueriesContext(connection) as ctx_one:
            self.draft.compute_fingerprint()
        one_section_queries = len(ctx_one.captured_queries)

        for i in range(1, 6):
            self._hero_section_with_slide(order=i)

        with CaptureQueriesContext(connection) as ctx_many:
            self.draft.compute_fingerprint()
        many_section_queries = len(ctx_many.captured_queries)

        self.assertEqual(
            one_section_queries, many_section_queries,
            "compute_fingerprint()'s query count must not grow with the "
            "number of media-bearing sections (N+1 regression) — got "
            f"{one_section_queries} for 1 section vs {many_section_queries} "
            "for 6.",
        )


class R4PreviewRefreshJsSourceContractTests(R4MutationApiTestCase):
    """Correction 1 — a pure, reusable ``R4.refreshPreview()`` exists in
    ``r4_editor.js`` (reusing the SAME ``#r4PreviewFrame`` authority every
    other preview-reload call site already uses — never a second iframe/
    renderer), and ``r4_studio.js``'s own ``r4:media-changed`` listener
    actually calls it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor_js_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_editor.js",
        ).read_text(encoding="utf-8")
        cls.studio_js_source = Path(
            settings.BASE_DIR,
            "apps/storefront_builder/static/storefront_builder/r4_studio.js",
        ).read_text(encoding="utf-8")

    def test_refresh_preview_defined_on_r4(self):
        self.assertIn("R4.refreshPreview = function", self.editor_js_source)

    def test_refresh_preview_reuses_existing_preview_frame_authority(self):
        # Same idiom used everywhere else in this file — never a second
        # iframe/renderer/mock preview.
        marker = self.editor_js_source.index("R4.refreshPreview = function")
        body = self.editor_js_source[marker:marker + 300]
        self.assertIn("previewFrame", body)
        self.assertIn("previewFrame.contentWindow.location.reload()", body)

    def test_media_changed_listener_calls_refresh_preview(self):
        marker = self.studio_js_source.index("addEventListener('r4:media-changed'")
        body = self.studio_js_source[marker:marker + 400]
        self.assertIn("R4.refreshPreview", body)
