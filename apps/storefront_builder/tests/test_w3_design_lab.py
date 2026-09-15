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
        preset = design_lab_service.candidate_to_preset(self.draft, candidate)
        self.assertIsInstance(preset, LayoutPresetDefinition)
        self.assertIsNotNone(preset.store_appearance)
        # Candidate preset must NOT be registered.
        self.assertIsNone(layout_preset_registry.get_layout_preset(preset.key))

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
