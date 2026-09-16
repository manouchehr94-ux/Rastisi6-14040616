"""P5-W3 — Design Lab / Random Mix behavioral tests.

The central invariant under test: **Random Mix is a transient experiment, not a
second source of truth.** Before an explicit Apply, ZERO persistent state
changes; after Apply, exactly ONE canonical mutation flows through
``r4_mutation_service.apply_mutation`` -> ``appearance_authority_service`` ->
canonical Draft -> ``edit_history_service``.

These tests are written FIRST (TDD RED). Their failures must be because the
Design Lab behavior is missing (missing module/attributes), never because of
broken setup, imports, fixtures, or URL names — the surrounding canonical
primitives (draft creation, mutation endpoint, manifest persistence, theme
owner) already exist at the certified checkpoint and are exercised here as-is.
"""

import copy
import json

from django.core.cache import cache
from django.urls import reverse

from apps.storefront_builder import layout_preset_registry
from apps.storefront_builder.services import layout_service
from apps.storefront_builder.storefront_appearance.persistence import (
    load_store_appearance_manifest,
    manifest_to_primitive,
)
from apps.stores.models import Store

from .test_views import StorefrontBuilderViewsTestCase


# Families that Design Lab is allowed to randomize as visual DNA. Theme is
# deliberately excluded (orthogonal — §9). mega_menu/layout/motion excluded
# (no meaningful alternatives / not chrome DNA — §6 design decision).
EXPECTED_RANDOMIZABLE = {
    "header",
    "hero",
    "product_view",
    "card",
    "footer",
    "badge",
    "bottom_nav",
}


def _draft_persistent_fingerprint(draft):
    """Everything Design Lab must NOT change before Apply."""
    draft.refresh_from_db()
    return {
        "appearance_config": copy.deepcopy(draft.appearance_config),
        "header_config": copy.deepcopy(draft.header_config),
        "footer_config": copy.deepcopy(draft.footer_config),
        "edit_revision": draft.edit_revision,
        "template_provenance": copy.deepcopy(draft.template_provenance),
        "template_baseline_snapshot": copy.deepcopy(draft.template_baseline_snapshot),
        "manifest": manifest_to_primitive(load_store_appearance_manifest(draft)),
        "page_count": draft.pages.count(),
        "section_count": sum(p.sections.count() for p in draft.pages.all()),
        "history_count": draft.edit_history_entries.count(),
    }


class DesignLabBaseTestCase(StorefrontBuilderViewsTestCase):
    """Common setup: an R4-enabled store on a real Ready Template draft so the
    manifest has diverse family selections to randomize away from."""

    ready_template_key = None  # subclasses may pin a specific template

    def setUp(self):
        super().setUp()
        cache.clear()
        self.layout = layout_service.get_or_create_layout(self.store)
        self.layout.r4_editor_enabled = True
        self.layout.save(update_fields=["r4_editor_enabled"])
        self.draft = layout_service.get_or_create_draft(self.store, user=self.staff)
        # Apply a real Ready Template so we have a non-default, diverse manifest.
        from apps.storefront_builder.services import preset_service

        preset = layout_preset_registry.list_ready_templates()[0]
        if self.ready_template_key:
            preset = layout_preset_registry.get_layout_preset(self.ready_template_key)
        preset_service.apply_preset(self.draft, preset)
        self.draft.refresh_from_db()

    def _current_selections(self):
        # The manifest lives in the draft's appearance_config JSON; reload the
        # in-memory instance so a prior mutation's write is observed.
        self.draft.refresh_from_db()
        return dict(load_store_appearance_manifest(self.draft).selections)


# ===========================================================================
# A. Transient generator
# ===========================================================================
class DesignLabGeneratorTests(DesignLabBaseTestCase):
    def test_generate_candidate_exists_and_returns_candidate(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=1,
        )
        # Transient dataclass contract (§7).
        self.assertIsInstance(candidate, design_lab_service.DesignLabCandidate)
        self.assertIsInstance(candidate.base_selections, dict)
        self.assertIsInstance(candidate.candidate_selections, dict)
        self.assertIn("header", candidate.candidate_selections)

    def test_randomizable_family_set_is_the_expected_dna_set(self):
        from apps.storefront_builder.services import design_lab_service

        self.assertEqual(
            set(design_lab_service.DESIGN_LAB_RANDOMIZABLE_FAMILIES),
            EXPECTED_RANDOMIZABLE,
        )
        # Theme is never in the default randomizable set (orthogonal).
        self.assertNotIn("theme", design_lab_service.DESIGN_LAB_RANDOMIZABLE_FAMILIES)

    def test_locked_family_never_changes(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()
        # Try many seeds; a locked family must be identical to base every time.
        for seed in range(25):
            candidate = design_lab_service.generate_candidate(
                self.draft,
                randomize_families=set(EXPECTED_RANDOMIZABLE),
                locked_families={"header"},
                seed=seed,
            )
            self.assertEqual(
                candidate.candidate_selections["header"],
                base["header"],
                msg=f"locked header changed at seed={seed}",
            )
            self.assertIn("header", candidate.locked_families)

    def test_unrequested_family_never_changes(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()
        for seed in range(25):
            candidate = design_lab_service.generate_candidate(
                self.draft,
                randomize_families={"footer"},  # only footer requested
                locked_families=set(),
                seed=seed,
            )
            self.assertEqual(candidate.candidate_selections["header"], base["header"])
            self.assertEqual(candidate.candidate_selections["card"], base["card"])

    def test_randomize_one_changes_only_selected_family(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"card"},
            locked_families=set(),
            seed=7,
        )
        changed = [
            f
            for f in base
            if candidate.candidate_selections.get(f) != base.get(f)
        ]
        self.assertTrue(set(changed).issubset({"card"}), msg=f"changed={changed}")

    def test_same_seed_same_candidate(self):
        from apps.storefront_builder.services import design_lab_service

        kwargs = dict(
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=1234,
        )
        a = design_lab_service.generate_candidate(self.draft, **kwargs)
        b = design_lab_service.generate_candidate(self.draft, **kwargs)
        self.assertEqual(a.candidate_selections, b.candidate_selections)

    def test_different_seed_can_produce_different_candidate(self):
        from apps.storefront_builder.services import design_lab_service

        results = set()
        for seed in range(30):
            candidate = design_lab_service.generate_candidate(
                self.draft,
                randomize_families=set(EXPECTED_RANDOMIZABLE),
                locked_families=set(),
                seed=seed,
            )
            results.add(
                tuple(sorted(candidate.candidate_selections.items()))
            )
        # With families having many options, distinct seeds must yield variety.
        self.assertGreater(len(results), 1)

    def test_randomize_prefers_a_different_component_when_alternatives_exist(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()
        # header has 22 options -> a single-family randomize should visibly change it.
        changed_any = False
        for seed in range(15):
            candidate = design_lab_service.generate_candidate(
                self.draft,
                randomize_families={"header"},
                locked_families=set(),
                seed=seed,
            )
            if candidate.candidate_selections["header"] != base["header"]:
                changed_any = True
                break
        self.assertTrue(changed_any, "Randomize never changed header despite alternatives")


# ===========================================================================
# B. Canonical validation
# ===========================================================================
class DesignLabCanonicalValidationTests(DesignLabBaseTestCase):
    def test_candidate_component_keys_originate_from_registry(self):
        from apps.storefront_builder.services import design_lab_service
        from apps.storefront_builder.storefront_appearance.registry import get_component

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=3,
        )
        for family, component_key in candidate.candidate_selections.items():
            component = get_component(component_key)
            self.assertIsNotNone(
                component, msg=f"fabricated component key {component_key!r}"
            )
            self.assertEqual(component.family_key, family)

    def test_candidate_resolves_through_canonical_resolver(self):
        from apps.storefront_builder.services import design_lab_service
        from apps.storefront_builder.storefront_appearance.rendering import (
            ResolvedStoreAppearance,
        )

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=9,
        )
        resolved = design_lab_service.resolve_candidate_appearance(
            self.draft, candidate
        )
        self.assertIsInstance(resolved, ResolvedStoreAppearance)

    def test_candidate_to_preset_builds_canonical_manifest(self):
        from apps.storefront_builder.services import design_lab_service
        from apps.storefront_builder.layout_preset_registry import LayoutPresetDefinition

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header", "footer"},
            locked_families=set(),
            seed=2,
        )
        registry_before = len(layout_preset_registry.list_layout_presets())
        preset = design_lab_service.candidate_to_preset(self.draft, candidate)
        self.assertIsInstance(preset, LayoutPresetDefinition)
        self.assertIsNotNone(preset.store_appearance)
        # candidate_to_preset must NEVER register anything (the transient preset
        # is never added to the canonical registry — registry count unchanged).
        self.assertEqual(
            len(layout_preset_registry.list_layout_presets()), registry_before
        )
        # The transient candidate object is NOT the registered definition:
        # it carries the candidate's own store_appearance manifest.
        self.assertEqual(
            preset.store_appearance["selections"],
            dict(candidate.candidate_selections),
        )

    def test_candidate_preset_accepted_by_resolve_preset_candidate(self):
        from apps.storefront_builder.services import design_lab_service, preset_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=2,
        )
        preset = design_lab_service.candidate_to_preset(self.draft, candidate)
        resolved = preset_service.resolve_preset_candidate(self.draft, preset)
        self.assertIsNotNone(resolved.store_appearance)

    def test_invalid_candidate_fails_through_canonical_contract(self):
        from apps.storefront_builder.services import design_lab_service
        from apps.storefront_builder.storefront_appearance.contracts import (
            InvalidStoreAppearanceContract,
        )

        # Fabricate an invalid candidate (fake component key) and prove it is
        # rejected by the canonical validator, not silently accepted.
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(),
            locked_families=set(),
            seed=1,
        )
        bad_selections = dict(candidate.candidate_selections)
        bad_selections["header"] = "header.totally_fake.v1"
        bad = design_lab_service.DesignLabCandidate(
            base_selections=candidate.base_selections,
            candidate_selections=bad_selections,
            settings=candidate.settings,
            locked_families=candidate.locked_families,
            seed=candidate.seed,
        )
        with self.assertRaises(InvalidStoreAppearanceContract):
            design_lab_service.resolve_candidate_appearance(self.draft, bad)


# ===========================================================================
# C. No persistence before Apply
# ===========================================================================
class DesignLabNoWriteBeforeApplyTests(DesignLabBaseTestCase):
    def test_full_transient_flow_writes_nothing(self):
        from apps.storefront_builder.services import design_lab_service

        before = _draft_persistent_fingerprint(self.draft)

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families={"footer"},
            seed=5,
        )
        design_lab_service.candidate_to_preset(self.draft, candidate)
        design_lab_service.resolve_candidate_appearance(self.draft, candidate)
        design_lab_service.compare_with_base(candidate)
        design_lab_service.reset_candidate(self.draft)
        design_lab_service.return_to_original_dna(self.draft, candidate)

        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "Design Lab mutated persistent state before Apply")

    def test_registered_preset_count_unchanged_by_candidate_flow(self):
        from apps.storefront_builder.services import design_lab_service

        before = len(layout_preset_registry.list_layout_presets())
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=6,
        )
        design_lab_service.candidate_to_preset(self.draft, candidate)
        design_lab_service.resolve_candidate_appearance(self.draft, candidate)
        after = len(layout_preset_registry.list_layout_presets())
        self.assertEqual(after, before)


# ===========================================================================
# D. Write-time reconciliation (apply_component_variant)
# ===========================================================================
class DesignLabWriteReconciliationTests(DesignLabBaseTestCase):
    def test_apply_component_variant_writes_manifest_selection(self):
        from apps.storefront_builder.services import appearance_authority_service

        # section_variant families whose visual effect lives only in the
        # manifest selections (render-time overlay). Prove the writer reconciles.
        for family, component_key in (
            ("hero", "hero.split.v1"),
            ("product_view", "product_view.grid.v1"),
            ("card", "card.standard.v1"),
            ("badge", "badge.sale.v1"),
        ):
            with self.subTest(family=family):
                self.draft.refresh_from_db()
                appearance_authority_service.apply_component_variant(
                    version=self.draft, family=family, component_key=component_key
                )
                self.draft.refresh_from_db()
                manifest = load_store_appearance_manifest(self.draft)
                self.assertEqual(manifest.selections[family], component_key)

    def test_apply_component_variant_preserves_unrelated_families(self):
        from apps.storefront_builder.services import appearance_authority_service

        before = self._current_selections()
        appearance_authority_service.apply_component_variant(
            version=self.draft, family="card", component_key="card.standard.v1"
        )
        self.draft.refresh_from_db()
        after = dict(load_store_appearance_manifest(self.draft).selections)
        for family in before:
            if family == "card":
                continue
            self.assertEqual(after[family], before[family], msg=f"{family} changed")

    def test_apply_component_variant_rejects_wrong_family(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.storefront_appearance.contracts import (
            InvalidStoreAppearanceContract,
        )

        with self.assertRaises((InvalidStoreAppearanceContract, ValueError)):
            appearance_authority_service.apply_component_variant(
                version=self.draft, family="header", component_key="card.standard.v1"
            )

    def test_resolved_appearance_agrees_with_persisted_after_apply(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.storefront_appearance.rendering import (
            resolve_store_appearance_render_state,
        )

        appearance_authority_service.apply_component_variant(
            version=self.draft, family="hero", component_key="hero.split.v1"
        )
        self.draft.refresh_from_db()
        resolved = resolve_store_appearance_render_state(self.draft)
        self.assertEqual(resolved.manifest.selections["hero"], "hero.split.v1")


# ===========================================================================
# E/F/G/H. Explicit atomic Apply through the canonical mutation boundary
# ===========================================================================
class DesignLabApplyMutationTests(DesignLabBaseTestCase):
    def _mutate(self, mutation, base_revision=None):
        self.draft.refresh_from_db()
        if base_revision is None:
            base_revision = self.draft.edit_revision
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def _apply_candidate_mutation(self, candidate, draft_id=None):
        from apps.storefront_builder.services import design_lab_service

        return design_lab_service.candidate_apply_mutation(
            candidate, draft_id=draft_id if draft_id is not None else self.draft.pk
        )

    def test_atomic_multi_family_apply_persists_all_changes(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header", "footer", "card"},
            locked_families=set(),
            seed=11,
        )
        expected = {
            f: candidate.candidate_selections[f]
            for f in ("header", "footer", "card")
        }
        before_revision = self.draft.edit_revision
        resp = self._mutate(self._apply_candidate_mutation(candidate))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["ok"], True)
        self.draft.refresh_from_db()
        manifest = load_store_appearance_manifest(self.draft)
        for family, key in expected.items():
            self.assertEqual(manifest.selections[family], key)
        # Exactly one revision advance for the whole multi-family apply.
        self.assertEqual(self.draft.edit_revision, before_revision + 1)

    def test_invalid_candidate_apply_persists_nothing(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header", "footer"},
            locked_families=set(),
            seed=11,
        )
        bad_selections = dict(candidate.candidate_selections)
        bad_selections["footer"] = "footer.not_real.v1"
        bad = design_lab_service.DesignLabCandidate(
            base_selections=candidate.base_selections,
            candidate_selections=bad_selections,
            settings=candidate.settings,
            locked_families=candidate.locked_families,
            seed=candidate.seed,
        )
        before = _draft_persistent_fingerprint(self.draft)
        resp = self._mutate(self._apply_candidate_mutation(bad))
        self.assertEqual(resp.status_code, 400, resp.content)
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "partial write on invalid apply")

    def test_stale_revision_rejected_with_zero_partial_writes(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=1,
        )
        stale_revision = self.draft.edit_revision
        # Advance the real draft (revision N -> N+1) with an unrelated edit.
        bump = self._mutate(
            {
                "type": "appearance.component.update",
                "draft_id": self.draft.pk,
                "family": "card",
                "component_key": "card.standard.v1",
            }
        )
        self.assertEqual(bump.status_code, 200, bump.content)
        before = _draft_persistent_fingerprint(self.draft)
        resp = self._mutate(
            self._apply_candidate_mutation(candidate), base_revision=stale_revision
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        self.assertEqual(resp.json()["code"], "stale_revision")
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "stale apply caused a partial write")

    def test_tenant_isolation_foreign_draft_rejected(self):
        from apps.storefront_builder.services import design_lab_service

        other_store = Store.objects.create(
            name="فروشگاه دیگر W3",
            slug="w3-other-store",
            admin_subdomain="w3-other-store",
        )
        other_draft = layout_service.get_or_create_draft(other_store)
        other_before = manifest_to_primitive(load_store_appearance_manifest(other_draft))

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=1,
        )
        # Attempt to apply Store A's candidate against Store B's draft id.
        resp = self._mutate(
            self._apply_candidate_mutation(candidate, draft_id=other_draft.pk)
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertEqual(resp.json()["code"], "draft_not_found")
        other_draft.refresh_from_db()
        self.assertEqual(
            manifest_to_primitive(load_store_appearance_manifest(other_draft)),
            other_before,
        )

    def test_apply_participates_in_history_undo_redo(self):
        from apps.storefront_builder.services import design_lab_service

        base_header = self._current_selections()["header"]
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=4,
        )
        applied_header = candidate.candidate_selections["header"]
        # Ensure the candidate really changes header (pick a seed that does).
        if applied_header == base_header:
            for seed in range(50):
                candidate = design_lab_service.generate_candidate(
                    self.draft,
                    randomize_families={"header"},
                    locked_families=set(),
                    seed=seed,
                )
                applied_header = candidate.candidate_selections["header"]
                if applied_header != base_header:
                    break
        self.assertNotEqual(applied_header, base_header)

        resp = self._mutate(self._apply_candidate_mutation(candidate))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.draft.refresh_from_db()
        self.assertEqual(self._current_selections()["header"], applied_header)

        # Undo restores pre-apply appearance.
        undo = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps(
                {"base_revision": self.draft.edit_revision, "command": "undo"}
            ),
            content_type="application/json",
        )
        self.assertEqual(undo.status_code, 200, undo.content)
        self.draft.refresh_from_db()
        self.assertEqual(self._current_selections()["header"], base_header)

        # Redo restores the applied appearance.
        redo = self.client.post(
            reverse("dashboard:storefront-builder-r4-history"),
            data=json.dumps(
                {"base_revision": self.draft.edit_revision, "command": "redo"}
            ),
            content_type="application/json",
        )
        self.assertEqual(redo.status_code, 200, redo.content)
        self.draft.refresh_from_db()
        self.assertEqual(self._current_selections()["header"], applied_header)


# ===========================================================================
# I. Compare with Base
# ===========================================================================
class DesignLabCompareTests(DesignLabBaseTestCase):
    def test_compare_reports_changed_families_only(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=7,
        )
        # Force a known change so the diff is deterministic for the assertion.
        forced = dict(candidate.candidate_selections)
        forced["header"] = (
            "header.dark_tech.v1"
            if base["header"] != "header.dark_tech.v1"
            else "header.boutique_centered.v1"
        )
        candidate = design_lab_service.DesignLabCandidate(
            base_selections=candidate.base_selections,
            candidate_selections=forced,
            settings=candidate.settings,
            locked_families=candidate.locked_families,
            seed=candidate.seed,
        )
        diffs = design_lab_service.compare_with_base(candidate)
        changed_families = {d["family"] for d in diffs}
        self.assertIn("header", changed_families)
        # Unchanged families must not appear in the diff.
        self.assertNotIn("card", changed_families)
        # Diff entries expose merchant-facing labels, not just raw keys.
        header_diff = next(d for d in diffs if d["family"] == "header")
        self.assertIn("base_label", header_diff)
        self.assertIn("candidate_label", header_diff)

    def test_compare_empty_when_no_change(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.reset_candidate(self.draft)
        diffs = design_lab_service.compare_with_base(candidate)
        self.assertEqual(diffs, [])


# ===========================================================================
# J. Return to Original DNA
# ===========================================================================
class DesignLabReturnToOriginalTests(DesignLabBaseTestCase):
    def test_return_to_original_dna_returns_to_committed_draft_base(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=13,
        )
        returned = design_lab_service.return_to_original_dna(self.draft, candidate)
        self.assertEqual(dict(returned.candidate_selections), base)

    def test_return_preserves_customization_and_writes_nothing(self):
        from apps.storefront_builder.services import appearance_authority_service
        from apps.storefront_builder.services import design_lab_service

        # Merchant customizes the committed draft first.
        appearance_authority_service.apply_component_variant(
            version=self.draft, family="card", component_key="card.standard.v1"
        )
        self.draft.refresh_from_db()
        base = self._current_selections()
        self.assertEqual(base["card"], "card.standard.v1")

        before = _draft_persistent_fingerprint(self.draft)
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=2,
        )
        returned = design_lab_service.return_to_original_dna(self.draft, candidate)
        # Returns to the merchant's CURRENT committed customization, not a
        # historic template baseline.
        self.assertEqual(returned.candidate_selections["card"], "card.standard.v1")
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before)


# ===========================================================================
# K. Reset Candidate
# ===========================================================================
class DesignLabResetTests(DesignLabBaseTestCase):
    def test_reset_candidate_equals_committed_draft_no_write(self):
        from apps.storefront_builder.services import design_lab_service

        before = _draft_persistent_fingerprint(self.draft)
        base = self._current_selections()
        candidate = design_lab_service.reset_candidate(self.draft)
        self.assertEqual(dict(candidate.candidate_selections), base)
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before)


# ===========================================================================
# L. Remove Theme (uses W2 clear_theme owner on Apply)
# ===========================================================================
class DesignLabRemoveThemeTests(DesignLabBaseTestCase):
    def _mutate(self, mutation, base_revision=None):
        self.draft.refresh_from_db()
        if base_revision is None:
            base_revision = self.draft.edit_revision
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    def test_remove_theme_is_transient_then_applies_via_clear_theme(self):
        from apps.storefront_builder.services import design_lab_service

        # Merchant enables a real Theme + a non-theme customization first.
        self._mutate(
            {
                "type": "appearance.component.update",
                "draft_id": self.draft.pk,
                "family": "card",
                "component_key": "card.standard.v1",
            }
        )
        self._mutate(
            {
                "type": "theme.apply",
                "draft_id": self.draft.pk,
                "component_key": "theme.yalda.v1",
                "intensity": "strong",
            }
        )
        self.draft.refresh_from_db()
        manifest = load_store_appearance_manifest(self.draft)
        self.assertEqual(manifest.selections["theme"], "theme.yalda.v1")

        # Transient Remove Theme on the candidate — writes nothing yet.
        before = _draft_persistent_fingerprint(self.draft)
        candidate = design_lab_service.reset_candidate(self.draft)
        candidate = design_lab_service.remove_theme(candidate)
        self.assertEqual(candidate.candidate_selections["theme"], "theme.none.v1")
        self.assertNotIn("theme", candidate.settings)
        # Non-theme state preserved in the candidate.
        self.assertEqual(candidate.candidate_selections["card"], "card.standard.v1")
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "Remove Theme wrote before Apply")

        # Explicit Apply routes through the canonical W2 clear_theme path.
        resp = self._mutate(
            design_lab_service.candidate_apply_mutation(
                candidate, draft_id=self.draft.pk
            )
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.draft.refresh_from_db()
        manifest = load_store_appearance_manifest(self.draft)
        self.assertEqual(manifest.selections["theme"], "theme.none.v1")
        self.assertNotIn("theme", manifest.settings)
        # Non-theme state exactly preserved through the apply.
        self.assertEqual(manifest.selections["card"], "card.standard.v1")


# ===========================================================================
# M. Preview pipeline (existing storefront_preview + canonical renderer)
# ===========================================================================
class DesignLabPreviewPipelineTests(DesignLabBaseTestCase):
    def test_candidate_preview_uses_existing_storefront_preview_route(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header", "footer"},
            locked_families=set(),
            seed=8,
        )
        token = design_lab_service.encode_candidate_token(candidate)
        before = _draft_persistent_fingerprint(self.draft)
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"),
            {"page": "home", "design_lab": token},
        )
        self.assertEqual(resp.status_code, 200, resp.content[:500])
        # Preview must not persist anything.
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "candidate preview persisted state")

    def test_candidate_preview_rejects_untrusted_component_keys(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(),
            locked_families=set(),
            seed=1,
        )
        bad = design_lab_service.DesignLabCandidate(
            base_selections=candidate.base_selections,
            candidate_selections={**candidate.candidate_selections, "header": "header.evil.v1"},
            settings=candidate.settings,
            locked_families=candidate.locked_families,
            seed=candidate.seed,
        )
        token = design_lab_service.encode_candidate_token(bad)
        resp = self.client.get(
            reverse("dashboard:storefront-builder-preview"),
            {"page": "home", "design_lab": token},
        )
        # Server-side validation: an untrusted key must not render as if valid.
        self.assertIn(resp.status_code, (400, 422))


# ===========================================================================
# N/O. Registry safety + 50-template invariant
# ===========================================================================
class DesignLabR4UITests(DesignLabBaseTestCase):
    def test_r4_editor_renders_design_lab_controls(self):
        resp = self.client.get(reverse("dashboard:storefront-builder-r4-editor"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("data-r4-design-lab-panel", body)
        self.assertIn("data-r4-design-lab-random-mix", body)
        self.assertIn("data-r4-design-lab-apply", body)
        self.assertIn("آزمایشگاه طراحی", body)
        self.assertIn("ترکیب تصادفی", body)

    def test_design_lab_endpoint_random_mix_returns_token_no_write(self):
        before = _draft_persistent_fingerprint(self.draft)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-r4-design-lab"),
            data=json.dumps({"action": "random_mix", "locked_families": ["header"]}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIs(data["ok"], True)
        self.assertTrue(data["token"])
        self.assertIn("header", data["locked_families"])
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "design-lab endpoint wrote state")

    def test_design_lab_apply_payload_builds_canonical_mutation(self):
        from apps.storefront_builder.services import design_lab_service

        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families={"header"},
            locked_families=set(),
            seed=3,
        )
        token = design_lab_service.encode_candidate_token(candidate)
        resp = self.client.post(
            reverse("dashboard:storefront-builder-r4-design-lab"),
            data=json.dumps({"action": "apply_payload", "candidate_token": token}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        mutation = resp.json()["mutation"]
        self.assertEqual(mutation["type"], "design_lab.apply_candidate")
        self.assertEqual(mutation["draft_id"], self.draft.pk)
        self.assertIn("header", mutation["selections"])


class DesignLabRegistrySafetyTests(DesignLabBaseTestCase):
    def test_exactly_50_ready_templates_remain(self):
        self.assertEqual(len(layout_preset_registry.list_ready_templates()), 50)

    def test_design_lab_never_registers_a_ready_template(self):
        from apps.storefront_builder.services import design_lab_service

        before = len(layout_preset_registry.list_ready_templates())
        candidate = design_lab_service.generate_candidate(
            self.draft,
            randomize_families=set(EXPECTED_RANDOMIZABLE),
            locked_families=set(),
            seed=6,
        )
        design_lab_service.candidate_to_preset(self.draft, candidate)
        design_lab_service.resolve_candidate_appearance(self.draft, candidate)
        after = len(layout_preset_registry.list_ready_templates())
        self.assertEqual(after, before)
        self.assertEqual(after, 50)



# ===========================================================================
# ARCHITECT REPAIR — real HTTP endpoint round-trip state-machine tests.
#
# These exercise encode -> /design-lab/ endpoint -> decode round-trips (NOT
# direct Python-object calls), proving the transient candidate preserves its
# original Base, base settings, base_revision, and draft identity across the
# token transport, that chained operations evolve the CURRENT candidate, that
# Lock preserves the current candidate value, and that a stale candidate Apply
# is rejected through the real flow.
# ===========================================================================
class DesignLabEndpointRoundTripTests(DesignLabBaseTestCase):
    def _design_lab(self, action, *, token=None, family=None, locked=None):
        body = {"action": action}
        if token is not None:
            body["candidate_token"] = token
        if family is not None:
            body["family"] = family
        if locked is not None:
            body["locked_families"] = locked
        resp = self.client.post(
            reverse("dashboard:storefront-builder-r4-design-lab"),
            data=json.dumps(body),
            content_type="application/json",
        )
        return resp

    def _mutate(self, mutation, base_revision=None):
        self.draft.refresh_from_db()
        if base_revision is None:
            base_revision = self.draft.edit_revision
        return self.client.post(
            reverse("dashboard:storefront-builder-r4-mutation"),
            data=json.dumps({"base_revision": base_revision, "mutation": mutation}),
            content_type="application/json",
        )

    # ---- RED A — real Compare round-trip reports the actual A -> B diff -----
    def test_compare_after_real_http_roundtrip_reports_A_to_B(self):
        base = self._current_selections()  # A
        # Random Mix -> candidate B (server-issued token).
        mix = self._design_lab("random_mix", locked=[])
        self.assertEqual(mix.status_code, 200, mix.content)
        token = mix.json()["token"]
        # Compare using that token — must report the real A -> B changes.
        cmp = self._design_lab("compare", token=token)
        self.assertEqual(cmp.status_code, 200, cmp.content)
        diffs = cmp.json()["diffs"]
        self.assertTrue(diffs, "compare produced no diff after a real round-trip")
        for d in diffs:
            # base side of each diff must equal the committed Draft base (A),
            # NOT the candidate value (self-compare bug).
            self.assertEqual(
                d["base_key"], base.get(d["family"]),
                msg=f"compare base for {d['family']} is not the original Base A",
            )
            self.assertNotEqual(
                d["base_key"], d["candidate_key"],
                msg="diff entry has identical base/candidate (self-compare)",
            )

    # ---- RED B — real Return-to-DNA round-trip yields A ---------------------
    def test_return_to_dna_after_real_http_roundtrip_yields_base(self):
        base = self._current_selections()  # A
        mix = self._design_lab("random_mix", locked=[])
        token = mix.json()["token"]
        ret = self._design_lab("return_to_dna", token=token)
        self.assertEqual(ret.status_code, 200, ret.content)
        # Compare must now be empty (candidate == base).
        self.assertEqual(ret.json()["diffs"], [], "return-to-DNA left a diff")
        # And the candidate selections themselves must equal A — decode the
        # returned token and check the actual candidate, not just the UI copy.
        from apps.storefront_builder.services import design_lab_service

        returned = design_lab_service.decode_candidate_token(ret.json()["token"])
        self.assertEqual(dict(returned.candidate_selections), base)

    # ---- RED C — settings comparison (theme intensity) ---------------------
    def test_compare_detects_settings_difference(self):
        # Give the committed Draft an active Theme with a specific intensity so
        # the candidate's settings differ from base on a canonical typed setting.
        self._mutate(
            {
                "type": "theme.apply",
                "draft_id": self.draft.pk,
                "component_key": "theme.yalda.v1",
                "intensity": "strong",
            }
        )
        base = self._current_selections()
        self.assertEqual(base["theme"], "theme.yalda.v1")
        # Build a candidate that keeps every selection but changes ONLY the
        # theme intensity setting, then compare through the endpoint round-trip.
        from apps.storefront_builder.services import design_lab_service

        reset = self._design_lab("reset")
        token = reset.json()["token"]
        cand = design_lab_service.decode_candidate_token(token)
        new_settings = dict(cand.settings)
        new_settings["theme"] = {"intensity": "subtle"}
        changed = design_lab_service.DesignLabCandidate(
            base_selections=cand.base_selections,
            base_settings=cand.base_settings,
            candidate_selections=cand.candidate_selections,
            candidate_settings=new_settings,
            settings=new_settings,
            locked_families=cand.locked_families,
            seed=cand.seed,
            base_revision=cand.base_revision,
            draft_id=cand.draft_id,
        )
        diffs = design_lab_service.compare_with_base(changed)
        theme_diff = [d for d in diffs if d["family"] == "theme"]
        self.assertTrue(
            theme_diff, "compare did not detect a theme intensity settings change"
        )

    # ---- Chaining: Randomize One after Random Mix preserves other families --
    def test_randomize_one_after_random_mix_preserves_other_candidate_families(self):
        from apps.storefront_builder.services import design_lab_service

        mix = self._design_lab("random_mix", locked=[])
        token_b = mix.json()["token"]
        b = design_lab_service.decode_candidate_token(token_b)
        # Randomize only footer, starting FROM candidate B.
        one = self._design_lab("randomize_one", token=token_b, family="footer", locked=[])
        self.assertEqual(one.status_code, 200, one.content)
        c = design_lab_service.decode_candidate_token(one.json()["token"])
        for family in EXPECTED_RANDOMIZABLE:
            if family == "footer":
                continue
            self.assertEqual(
                c.candidate_selections[family],
                b.candidate_selections[family],
                msg=f"{family} was reset to Draft base instead of preserving candidate B",
            )

    # ---- Chaining: Lock after Randomize preserves CURRENT candidate value ---
    def test_lock_after_randomize_preserves_current_candidate_value(self):
        from apps.storefront_builder.services import design_lab_service

        base_header = self._current_selections()["header"]  # H0
        # Randomize header until it changes to H1.
        token = self._design_lab("reset").json()["token"]
        h1 = base_header
        for _ in range(30):
            one = self._design_lab("randomize_one", token=token, family="header", locked=[])
            token = one.json()["token"]
            h1 = design_lab_service.decode_candidate_token(token).candidate_selections["header"]
            if h1 != base_header:
                break
        self.assertNotEqual(h1, base_header, "could not randomize header to H1")
        # Lock header + Random Mix repeatedly; header must stay H1 (current
        # candidate value), NOT revert to the committed Draft H0.
        for _ in range(4):
            mix = self._design_lab("random_mix", token=token, locked=["header"])
            token = mix.json()["token"]
            cur = design_lab_service.decode_candidate_token(token).candidate_selections["header"]
            self.assertEqual(cur, h1, "locked header did not preserve the CURRENT candidate value")

    def test_multiple_candidate_operations_preserve_original_base_for_compare(self):
        from apps.storefront_builder.services import design_lab_service

        base = self._current_selections()  # A
        token = self._design_lab("random_mix", locked=[]).json()["token"]
        token = self._design_lab("randomize_one", token=token, family="footer").json()["token"]
        token = self._design_lab("randomize_one", token=token, family="card").json()["token"]
        cand = design_lab_service.decode_candidate_token(token)
        # The original Base must be intact after several chained operations.
        self.assertEqual(dict(cand.base_selections), base)

    # ---- Real-flow stale candidate Apply through the endpoints --------------
    def test_real_flow_stale_candidate_apply_is_rejected(self):
        # 1. Design-Lab random_mix at revision N.
        self.draft.refresh_from_db()
        n = self.draft.edit_revision
        mix = self._design_lab("random_mix", locked=[])
        token = mix.json()["token"]
        self.assertEqual(mix.json()["base_revision"], n)
        # 3. A real canonical R4 mutation advances the Draft to N+1.
        bump = self._mutate(
            {
                "type": "appearance.component.update",
                "draft_id": self.draft.pk,
                "family": "card",
                "component_key": "card.standard.v1",
            }
        )
        self.assertEqual(bump.status_code, 200, bump.content)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, n + 1)
        before = _draft_persistent_fingerprint(self.draft)
        # 4. apply_payload with the OLD (revision-N) token must be rejected as
        #    stale, before producing any accepted apply mutation.
        ap = self._design_lab("apply_payload", token=token)
        self.assertIn(ap.status_code, (409, 400), ap.content)
        self.assertIn(ap.json().get("code"), ("stale_revision", "stale_candidate"))
        # 6/7/8 — no apply happened; the N+1 edit is preserved; no partial write.
        after = _draft_persistent_fingerprint(self.draft)
        self.assertEqual(after, before, "stale apply caused a write")
        self.assertEqual(self.draft.edit_revision, n + 1)

    def test_apply_payload_current_candidate_succeeds_atomically(self):
        # A fresh candidate at the current revision applies through the
        # canonical mutate endpoint and advances the revision by exactly one.
        self.draft.refresh_from_db()
        n = self.draft.edit_revision
        mix = self._design_lab("random_mix", locked=[])
        token = mix.json()["token"]
        ap = self._design_lab("apply_payload", token=token)
        self.assertEqual(ap.status_code, 200, ap.content)
        mutation = ap.json()["mutation"]
        self.assertEqual(mutation["type"], "design_lab.apply_candidate")
        applied = self._mutate(mutation, base_revision=n)
        self.assertEqual(applied.status_code, 200, applied.content)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.edit_revision, n + 1)

    def test_candidate_token_is_integrity_protected(self):
        # A tampered token (editing the base64 JSON) must be rejected, not
        # trusted — the token carries correctness-critical base/revision truth.
        from apps.storefront_builder.services import design_lab_service

        token = self._design_lab("random_mix", locked=[]).json()["token"]
        tampered = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
        with self.assertRaises(ValueError):
            design_lab_service.decode_candidate_token(tampered)
