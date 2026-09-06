# Task 1 — RED Lifecycle & Media Characterization (tests only)

Storefront Appearance Convergence — Phase 2 (Lifecycle & Safety).

## Context

| Item | Value |
|---|---|
| Branch | `feature/storefront-lifecycle-safety-phase2` |
| Worktree | `/projects/rastisi5_phase2` |
| Venv | `/projects/rastisi5_phase2_venv` (Python 3.12 / Django 5.2) |
| HEAD before Task 1 | `a1898b58a9d3910dc2bf830ecf7feec7a400fa7b` |
| Scope | **TESTS ONLY** — no production file modified |

Authoritative task: `docs/superpowers/plans/2026-09-06-storefront-lifecycle-safety-phase2-implementation-plan.md`
→ "Task 1 — RED Lifecycle & Media Characterization (tests only)".
Fact source: `docs/qa_evidence/storefront_appearance_convergence/phase2/lifecycle_media_inventory.md`.

## Tests added

Two new test modules (no production code touched):

1. `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`
   - `LegacyPublishedVersionImmutabilityTests.test_legacy_section_settings_post_on_published_section_is_not_found` (L05)
   - `LegacyPublishedVersionImmutabilityTests.test_legacy_section_settings_get_on_published_section_is_not_found` (L05)
   - `LegacyArchivedVersionImmutabilityTests.test_legacy_section_settings_post_on_archived_section_is_not_found` (L05)
   - `LegacyMutationAdvancesEditRevisionTests.test_legacy_real_mutation_advances_edit_revision_by_one` (L01, desired invariant)
   - `LegacyMutationAdvancesEditRevisionTests.test_baseline_legacy_mutation_does_not_advance_edit_revision` (L01, baseline witness)

2. `apps/content/tests/test_phase2_media_reachability.py`  (`apps/content/tests` confirmed to be a package — `__init__.py` present)
   - `JsonOnlyBackgroundReferenceReachabilityTests.test_json_only_referenced_asset_on_draft_is_reachable` (L07/A05)
   - `JsonOnlyBackgroundReferenceReachabilityTests.test_json_only_referenced_asset_on_published_is_reachable` (L07/A05)
   - `SnapshotOnlyReferenceReachabilityTests.test_edit_history_snapshot_only_referenced_asset_is_reachable` (L07/A05)
   - `SnapshotOnlyReferenceReachabilityTests.test_template_baseline_snapshot_only_referenced_asset_is_reachable` (L07/A05)
   - `UnsafeDeletionConsequenceTests.test_gate_must_not_delete_json_only_referenced_asset` (L07/A05, non-destructive throwaway asset)
   - `GenuinelyUnreferencedAssetTests.test_asset_with_no_references_is_not_reachable` (preservation guard)

All tests use real fixtures (Store `akhlaghi` via `StorefrontBuilderViewsTestCase`),
real routes (`dashboard:storefront-builder-section-settings`), and the real
lifecycle service (`layout_service.get_or_create_draft` / `publish`). No
fabricated APIs. Media tests are **non-destructive** — they assert on
`MediaAsset.is_referenced()` (and one throwaway-asset deletion-gate consequence),
never deleting a shared/live fixture asset.

## Exact command

```
/projects/rastisi5_phase2_venv/bin/python manage.py test \
  apps.storefront_builder.tests.test_phase2_lifecycle_safety \
  apps.content.tests.test_phase2_media_reachability \
  --verbosity 2
```

## Result summary

```
Ran 11 tests
FAILED (failures=6)
```

No errors, no exceptions — every failure is an intended RED assertion.

## Per-test result & classification

| Test | Result | Gap | Classification |
|---|---|---|---|
| `LegacyPublishedVersionImmutabilityTests.test_legacy_section_settings_post_on_published_section_is_not_found` | ok | L05 | **EXPECTED GREEN** |
| `LegacyPublishedVersionImmutabilityTests.test_legacy_section_settings_get_on_published_section_is_not_found` | ok | L05 | **EXPECTED GREEN** |
| `LegacyArchivedVersionImmutabilityTests.test_legacy_section_settings_post_on_archived_section_is_not_found` | ok | L05 | **EXPECTED GREEN** |
| `LegacyMutationAdvancesEditRevisionTests.test_baseline_legacy_mutation_does_not_advance_edit_revision` | ok | L01 | **EXPECTED GREEN** (baseline witness) |
| `GenuinelyUnreferencedAssetTests.test_asset_with_no_references_is_not_reachable` | ok | L07 | **EXPECTED GREEN** (preservation guard) |
| `LegacyMutationAdvancesEditRevisionTests.test_legacy_real_mutation_advances_edit_revision_by_one` | FAIL (`0 != 1`) | L01 | **EXPECTED RED** |
| `JsonOnlyBackgroundReferenceReachabilityTests.test_json_only_referenced_asset_on_draft_is_reachable` | FAIL (`False is not true`) | L07 | **EXPECTED RED** |
| `JsonOnlyBackgroundReferenceReachabilityTests.test_json_only_referenced_asset_on_published_is_reachable` | FAIL (`False is not true`) | L07 | **EXPECTED RED** |
| `SnapshotOnlyReferenceReachabilityTests.test_edit_history_snapshot_only_referenced_asset_is_reachable` | FAIL (`False is not true`) | L07 | **EXPECTED RED** |
| `SnapshotOnlyReferenceReachabilityTests.test_template_baseline_snapshot_only_referenced_asset_is_reachable` | FAIL (`False is not true`) | L07 | **EXPECTED RED** |
| `UnsafeDeletionConsequenceTests.test_gate_must_not_delete_json_only_referenced_asset` | FAIL (`True is not false`) | L07 | **EXPECTED RED** |

**Totals:** 5 EXPECTED GREEN, 6 EXPECTED RED, 0 UNEXPECTED.

This matches the plan's exact expectation: Published/Archived immutability
characterization PASSES (already-correct behaviour); L01 revision-advance and
all L07 media-reachability desired-invariant assertions FAIL (intended RED).

## Root cause per RED

### L01 — legacy mutations do not advance `edit_revision` (P1)

- **File:line:** `apps/storefront_builder/views.py:68-104` — the
  `_record_edit_history` decorator (and `_history_record`) that wraps every
  legacy write view records an undo/redo history entry but never advances the
  Draft's `edit_revision`. The `+1` increment exists only on the R4 path
  (`apps/storefront_builder/services/r4_mutation_service.py`, via
  `_lock_active_draft` / `apply_mutation`).
- **Observed baseline:** after a real legacy `storefront_section_settings`
  POST that changes `rich_text.body_html`, `draft.edit_revision` stays at `0`
  (asserted by `test_baseline_legacy_mutation_does_not_advance_edit_revision`),
  so the desired `+1` invariant fails with `0 != 1`.
- **Convergence:** Task 3.

### L07 / A05 — `MediaAsset.is_referenced()` blind to JSON + snapshots (P0)

- **File:line:** `apps/content/models.py:418-431` — `is_referenced()` ORs only
  the five direct FK placement reverse relations (`hero_placements`,
  `banner_desktop_placements`, `banner_mobile_placements`,
  `hero_mobile_placements`, `story_placements`). It cannot see:
  - JSON reference class #2 — `StorefrontSection.settings["background"]["media_asset_id"]`
    (written by `apps/storefront_builder/views.py:_extract_background_raw` ~:1066;
    rendered by `apps/content/services.py:resolve_background_media_url` ~:131).
  - Recovery reference class #4 — asset ids captured in
    `StorefrontEditHistoryEntry.before_state`/`after_state` snapshots and in a
    version's `template_baseline_snapshot`.
- **Consumer:** `apps/content/services.py:211-243`
  `delete_media_asset_if_unreferenced` gates physical deletion solely on
  `is_referenced()`, so a JSON-only / snapshot-only referenced asset is reported
  deletable — proven by `test_gate_must_not_delete_json_only_referenced_asset`
  (`delete_media_asset_if_unreferenced` returns `True` at baseline).
- **Convergence:** Task 6 (P0).

## Scope confirmation — NO production code changed

`git status --short`:

```
?? apps/content/tests/test_phase2_media_reachability.py
?? apps/storefront_builder/tests/test_phase2_lifecycle_safety.py
?? docs/qa_evidence/storefront_appearance_convergence/phase2/_sdd_ledger.md
```

`git diff --check` — clean (no whitespace errors).
`git diff --name-only` — empty (no tracked file modified).

- Only **2 new test files** + **this 1 new evidence doc** are introduced by Task 1.
- `_sdd_ledger.md` was already present (untracked) at session start and is **NOT** part of this task's commit.
- **Zero production `.py` files changed.** No migration created. No renderer /
  authority-service / schema change.
