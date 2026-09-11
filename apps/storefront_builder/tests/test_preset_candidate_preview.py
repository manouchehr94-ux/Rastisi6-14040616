"""Phase 5, Task 1 — non-mutating candidate template preview
(``preset_service.resolve_preset_candidate``).

TDD RED for the "resolve what would render, without writing it" primitive.
Covers the four required categories from the Task-1 charter:

1. ``CandidateReflectsDeclaredDNATests`` — the resolved/rendered candidate
   actually reflects the previewed Ready Template's own declared DNA (header
   variant, hero style, section composition) — not just "no exception".
2. ``RealDraftUnchangedByCandidatePreviewTests`` — the real Draft is
   byte/field-identical before and after a candidate resolution: no new
   ``StorefrontLayoutVersion``, no History entry, no Section/Container
   mutation, no published-pointer change.
3. ``InvalidCandidateNonMutatingTests`` — an unknown preset key or a
   locked-section conflict fails through the exact same typed errors
   ``apply_preset`` already raises, leaving the Draft unchanged.
4. ``ExistingApplyStillWorksTests`` — the real (writing) ``apply_preset``
   path is unaffected by the shared-preparation refactor this task makes,
   both on its own and immediately after an unrelated candidate resolution.
"""

import dataclasses

from django.test import TestCase

from apps.storefront_builder import layout_preset_registry as lpr
from apps.storefront_builder.models import (
    StorefrontContainer,
    StorefrontEditHistoryEntry,
    StorefrontLayout,
    StorefrontLayoutVersion,
    StorefrontSection,
)
from apps.storefront_builder.services import layout_service as svc
from apps.storefront_builder.services import preset_service, render_service
from apps.storefront_builder.storefront_appearance.rendering import (
    badge_settings_for,
    card_settings_for,
    resolve_store_appearance_render_state,
)
from apps.storefront_builder.storefront_appearance.validation import (
    InvalidStoreAppearanceContract,
)
from apps.stores.models import Store


def _akhlaghi():
    return Store.objects.get(slug="akhlaghi")


def _second_store():
    store, _ = Store.objects.get_or_create(
        slug="phase5-task1-store-b",
        defaults=dict(name="فروشگاه دوم — Task 1 Parity", status=Store.Status.ACTIVE),
    )
    return store


def _snapshot(draft: StorefrontLayoutVersion) -> dict:
    """Everything Task 1's ruling requires to be preserved, read fresh from
    the database (not from the possibly-stale in-memory ``draft`` the test
    already holds)."""
    draft.refresh_from_db()
    return {
        "edit_revision": draft.edit_revision,
        "appearance_config": draft.appearance_config,
        "header_config": draft.header_config,
        "footer_config": draft.footer_config,
        "template_provenance": draft.template_provenance,
        "template_baseline_snapshot": draft.template_baseline_snapshot,
        "sections": list(
            StorefrontSection.objects.filter(page__version=draft)
            .order_by("page_id", "order", "id")
            .values_list("page_id", "section_key", "order", "settings", "is_locked")
        ),
        "container_count": StorefrontContainer.objects.filter(page__version=draft).count(),
        "version_count": StorefrontLayoutVersion.objects.filter(layout_id=draft.layout_id).count(),
        "history_count": StorefrontEditHistoryEntry.objects.filter(draft_version=draft).count(),
        "published_version_id": StorefrontLayout.objects.get(pk=draft.layout_id).published_version_id,
    }


class CandidatePreviewTestCase(TestCase):
    def setUp(self):
        self.store = _akhlaghi()
        self.draft = svc.get_or_create_draft(self.store)


class CandidateReflectsDeclaredDNATests(CandidatePreviewTestCase):
    """RED 1 — proof must be a materially meaningful selection, not HTTP 200."""

    def test_candidate_header_variant_matches_declared_recipe(self):
        preset = lpr.get_layout_preset("editorial_jewelry")
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)
        self.assertEqual(candidate.header_config["header_variant"], "editorial_row")

    def test_candidate_hero_style_setting_matches_declared_recipe(self):
        preset = lpr.get_layout_preset("editorial_jewelry")
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)
        hero_rows = [s for s in candidate.pages["home"].sections if s.section_key == "hero_banner"]
        self.assertEqual(len(hero_rows), 1)
        self.assertEqual(hero_rows[0].settings.get("hero_style"), "luxury_showcase")

    def test_two_different_templates_resolve_to_visibly_different_candidates(self):
        jewelry = preset_service.resolve_preset_candidate(
            self.draft, lpr.get_layout_preset("editorial_jewelry"),
        )
        marketplace = preset_service.resolve_preset_candidate(
            self.draft, lpr.get_layout_preset("dense_marketplace"),
        )
        self.assertNotEqual(
            jewelry.header_config["header_variant"],
            marketplace.header_config["header_variant"],
        )
        jewelry_hero = next(s for s in jewelry.pages["home"].sections if s.section_key == "hero_banner")
        marketplace_hero = next(s for s in marketplace.pages["home"].sections if s.section_key == "hero_banner")
        self.assertNotEqual(
            jewelry_hero.settings.get("hero_style"),
            marketplace_hero.settings.get("hero_style"),
        )

    def test_candidate_renders_through_the_shared_renderer(self):
        """Not just data — the SAME render_service pipeline Preview/Publish/
        Public already use must accept the candidate's unsaved sections and
        produce real render items, proving there is no second renderer."""
        preset = lpr.get_layout_preset("editorial_jewelry")
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)
        items = render_service.build_candidate_render_items(
            candidate.pages["home"].sections, self.store, global_appearance=candidate.appearance_config,
        )
        section_keys = [item["section"].section_key for item in items]
        self.assertIn("hero_banner", section_keys)
        # Every candidate section stays unsaved (pk=None) all the way through
        # rendering — nothing along the way silently persisted it.
        self.assertTrue(all(item["section"].pk is None for item in items))

    def test_candidate_renders_a_story_rail_bearing_template_without_crashing(self):
        """Regression for a CRITICAL finding from the Task-1 independent
        review: ``story_rail``'s context builder does the exact same
        per-section-scoped FK query as hero_banner/single_banner — an
        unguarded candidate (unsaved) section made it raise
        ``ValueError: Model instances passed to related filters must be
        saved.`` ``premium_boutique`` is a real, currently-latest
        ``is_ready_template=True`` preset whose Home composition includes a
        ``story_rail`` section, so this exercises the real registry, not a
        synthetic fixture."""
        preset = lpr.get_layout_preset("premium_boutique")
        self.assertIn(
            "story_rail", [e.section_key for e in preset.pages["home"]],
            "test fixture assumption changed — pick another story_rail-bearing preset",
        )
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)
        items = render_service.build_candidate_render_items(
            candidate.pages["home"].sections, self.store, global_appearance=candidate.appearance_config,
        )
        section_keys = [item["section"].section_key for item in items]
        self.assertIn("story_rail", section_keys)


class RealDraftUnchangedByCandidatePreviewTests(CandidatePreviewTestCase):
    """RED 2 — the real Draft must be unchanged in every dimension Task 1's
    ruling names: appearance/header/footer, provenance/baseline snapshot,
    edit_revision, sections/pages/containers, published pointer, and no new
    History entry or LayoutVersion row."""

    def test_candidate_resolution_leaves_real_draft_byte_identical(self):
        before = _snapshot(self.draft)
        preset = lpr.get_layout_preset("editorial_jewelry")

        preset_service.resolve_preset_candidate(self.draft, preset)

        self.assertEqual(_snapshot(self.draft), before)

    def test_candidate_resolution_for_multiple_templates_still_leaves_draft_unchanged(self):
        before = _snapshot(self.draft)
        for key in ("editorial_jewelry", "dense_marketplace", "warm_boutique"):
            preset_service.resolve_preset_candidate(self.draft, lpr.get_layout_preset(key))
        self.assertEqual(_snapshot(self.draft), before)


class InvalidCandidateNonMutatingTests(CandidatePreviewTestCase):
    """RED 3 — an invalid/unknown candidate must fail through the existing
    typed validation/registry semantics and leave the Draft unchanged."""

    def test_unknown_preset_key_raises_and_does_not_mutate(self):
        before = _snapshot(self.draft)
        with self.assertRaises(preset_service.UnknownPresetError):
            preset_service.resolve_preset_candidate_by_key(self.draft, "__does_not_exist__")
        self.assertEqual(_snapshot(self.draft), before)

    def test_locked_section_conflict_raises_and_does_not_mutate(self):
        home = self.draft.get_page("home")
        StorefrontSection.objects.create(
            page=home, section_key="hero_banner", order=0, is_locked=True, settings={},
        )
        before = _snapshot(self.draft)
        preset = lpr.get_layout_preset("editorial_jewelry")
        with self.assertRaises(preset_service.LockedSectionsPresentError):
            preset_service.resolve_preset_candidate(self.draft, preset)
        self.assertEqual(_snapshot(self.draft), before)


class ExistingApplyStillWorksTests(CandidatePreviewTestCase):
    """RED 4 — candidate preview must not weaken or alter real apply_preset
    semantics, whether used on its own or immediately before a real Apply."""

    def test_apply_preset_still_writes_real_sections(self):
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config.get("header_variant"), "editorial_row")
        home = self.draft.get_page("home")
        self.assertTrue(
            StorefrontSection.objects.filter(page=home, section_key="hero_banner").exists()
        )

    def test_candidate_resolution_does_not_leak_into_a_subsequent_real_apply(self):
        preset_service.resolve_preset_candidate(
            self.draft, lpr.get_layout_preset("dense_marketplace"),
        )
        preset = lpr.get_layout_preset("editorial_jewelry")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.header_config.get("header_variant"), "editorial_row")
        home = self.draft.get_page("home")
        hero_settings = StorefrontSection.objects.get(
            page=home, section_key="hero_banner",
        ).settings
        self.assertEqual(hero_settings.get("hero_style"), "luxury_showcase")


class CandidateStoreAppearanceParityTests(CandidatePreviewTestCase):
    """Task-1 corrective gate — the candidate must carry the complete typed
    Store Appearance manifest a real Apply would make authoritative, resolved
    through the SAME pure manifest-to-render-state resolver the persisted
    (public/Preview) path already uses — not a second implementation, and not
    a raw-dict passthrough into an ad-hoc renderer path."""

    def test_candidate_store_appearance_matches_declared_manifest_selections(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)
        self.assertIsNotNone(candidate.store_appearance)
        self.assertEqual(
            dict(candidate.store_appearance.manifest.selections),
            dict(preset.store_appearance["selections"]),
        )

    def test_candidate_store_appearance_differs_for_a_different_template_in_a_render_affecting_family(self):
        jewelry = preset_service.resolve_preset_candidate(
            self.draft, lpr.get_layout_preset("editorial_jewelry"),
        )
        marketplace = preset_service.resolve_preset_candidate(
            self.draft, lpr.get_layout_preset("dense_marketplace"),
        )
        # editorial_jewelry declares badge="none", dense_marketplace badge="sale"
        # (a8_ready_templates.py _SPECS) — a real, render-affecting difference,
        # not just two different opaque component-key strings.
        self.assertNotEqual(
            badge_settings_for(jewelry.store_appearance),
            badge_settings_for(marketplace.store_appearance),
        )

    def test_candidate_rendering_consumes_candidate_store_appearance_not_drafts_persisted_one(self):
        """Real proof, through the actual render call: apply editorial_jewelry
        (badge=none) for real onto the Draft first, then resolve+render a
        CANDIDATE for dense_marketplace (badge=sale) against that same,
        now-mutated Draft. The rendered card-aware section's badge/card
        settings must reflect the CANDIDATE (dense_marketplace), not the
        Draft's own currently-persisted Store Appearance (editorial_jewelry)
        — proving the render call was given the candidate state explicitly,
        not silently re-resolving the Draft's persisted state instead."""
        preset_service.apply_preset(self.draft, lpr.get_layout_preset("editorial_jewelry"))
        self.draft.refresh_from_db()
        persisted_state = resolve_store_appearance_render_state(self.draft)

        candidate = preset_service.resolve_preset_candidate(
            self.draft, lpr.get_layout_preset("dense_marketplace"),
        )
        self.assertNotEqual(
            badge_settings_for(persisted_state), badge_settings_for(candidate.store_appearance),
        )

        items = render_service.build_candidate_render_items(
            candidate.pages["home"].sections,
            self.store,
            global_appearance=candidate.appearance_config,
            store_appearance=candidate.store_appearance,
        )
        product_items = [
            item for item in items if item["section"].section_key == "product_section"
        ]
        self.assertTrue(product_items, "editorial_jewelry/dense_marketplace fixtures must include a product_section")
        rendered_card = product_items[0]["context"]["settings"].get("card") or {}
        expected_candidate_badge = badge_settings_for(candidate.store_appearance)
        for key, value in expected_candidate_badge.items():
            self.assertEqual(
                rendered_card.get(key), value,
                f"rendered card settings for {key!r} must come from the CANDIDATE's "
                f"Store Appearance, not the Draft's currently-persisted one",
            )

    def test_candidate_resolution_with_store_appearance_still_leaves_draft_unchanged(self):
        before = _snapshot(self.draft)
        preset_service.resolve_preset_candidate(self.draft, lpr.get_layout_preset("dense_marketplace"))
        self.assertEqual(_snapshot(self.draft), before)

    def test_real_apply_still_persists_the_same_typed_manifest(self):
        """The real Apply path (persist_store_appearance_manifest, inside
        appearance_authority_service.apply_store_appearance_manifest) is
        untouched by this corrective change — still writes the complete
        declared manifest, unchanged from before."""
        preset = lpr.get_layout_preset("dense_marketplace")
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()
        persisted_state = resolve_store_appearance_render_state(self.draft)
        self.assertEqual(
            dict(persisted_state.manifest.selections),
            dict(preset.store_appearance["selections"]),
        )

    def test_invalid_store_appearance_manifest_fails_through_the_canonical_validator_and_does_not_mutate(self):
        """An incompatible/invalid declared manifest must fail through the
        exact same ``InvalidStoreAppearanceContract`` the real persisted path
        (``validate_store_appearance_manifest``) already raises — not a
        second, more lenient candidate-only validation path — and must leave
        the Draft unchanged."""
        bad_preset = dataclasses.replace(
            lpr.get_layout_preset("dense_marketplace"),
            store_appearance={
                "schema_version": 1,
                "selections": {"badge": "__not_a_real_component_key__"},
            },
        )
        before = _snapshot(self.draft)
        with self.assertRaises(InvalidStoreAppearanceContract):
            preset_service.resolve_preset_candidate(self.draft, bad_preset)
        self.assertEqual(_snapshot(self.draft), before)

    def test_candidate_and_real_apply_resolve_identical_store_appearance_render_state(self):
        """Strongest proof of "Candidate Preview == What Apply Would Render":
        resolve a candidate against one (unmutated) Draft, separately Apply
        the exact same Ready Template for real onto a completely different
        Store's Draft, and assert the two independently-resolved
        ``ResolvedStoreAppearance`` states select identical components for
        every family — without candidate persistence anywhere."""
        preset = lpr.get_layout_preset("dense_marketplace")

        candidate = preset_service.resolve_preset_candidate(self.draft, preset)

        other_store = _second_store()
        other_draft = svc.get_or_create_draft(other_store)
        preset_service.apply_preset(other_draft, preset)
        other_draft.refresh_from_db()
        applied_state = resolve_store_appearance_render_state(other_draft)

        self.assertEqual(
            dict(candidate.store_appearance.manifest.selections),
            dict(applied_state.manifest.selections),
        )
        for family_key in candidate.store_appearance.manifest.selections:
            self.assertEqual(
                candidate.store_appearance.component(family_key).component.key,
                applied_state.component(family_key).component.key,
                family_key,
            )


class CandidateContainerSettingsParityTests(CandidatePreviewTestCase):
    """Task-1 corrective (independent review item 11) — the candidate must
    not silently discard the per-row-run Container settings
    ``_prepare_preset_application`` already computes; a real Apply persists
    these onto ``StorefrontContainer`` rows and the public/Preview render
    path groups sections into rows using exactly this data
    (``render_service.build_container_render_items``). Dropping it from the
    candidate would leave Tasks 2/3 unable to preview multi-column/row
    layouts faithfully."""

    def test_candidate_exposes_container_settings_alongside_sections(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)
        home = candidate.pages["home"]
        self.assertTrue(home.container_settings, "candidate must expose non-empty container settings")
        self.assertIsInstance(home.sections, list)
        self.assertIsInstance(home.container_settings, list)

    def test_candidate_container_settings_match_what_a_real_apply_persists(self):
        preset = lpr.get_layout_preset("dense_marketplace")
        candidate = preset_service.resolve_preset_candidate(self.draft, preset)

        other_store = _second_store()
        other_draft = svc.get_or_create_draft(other_store)
        preset_service.apply_preset(other_draft, preset)
        other_draft.refresh_from_db()
        home = other_draft.get_page("home")
        persisted_container_settings = list(
            StorefrontContainer.objects.filter(page=home).order_by("order", "id")
            .values_list("settings", flat=True)
        )

        self.assertEqual(
            candidate.pages["home"].container_settings, persisted_container_settings,
        )
