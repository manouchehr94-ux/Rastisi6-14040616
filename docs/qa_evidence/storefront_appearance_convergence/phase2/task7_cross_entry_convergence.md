# Phase 2 — Task 7: Cross-Entry Lifecycle Convergence + Recovery Proof

**Nature:** VERIFICATION / convergence-proof task (tests-only).
**Branch:** `feature/storefront-lifecycle-safety-phase2` (from HEAD `0eb76fa`).
**Test module extended:** `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`
**Production code changed:** **NONE.** No inconsistency was discovered; Tasks 3–6
already made the legacy and R4 entry points lifecycle- and revision-safe and
closed the media A05 gap. `git diff --name-only` reports only the test file.

---

## What this task proves

Tasks 3–6 converged the two Storefront-Builder entry points step-by-step:

* **Task 3** — `edit_revision` is a single Draft-wide monotonic token; a REAL
  change via EITHER legacy (`@_record_edit_history` →
  `edit_history_service.record_change`) or R4 (`apply_mutation` →
  `record_change`) advances it by exactly 1; a semantic no-op advances nothing.
* **Task 4** — legacy publish routes through the shared `layout_service.publish`
  (atomic; archives previous Published; clears draft history + pointer; swaps
  pointers) and, when a `base_revision` is supplied, through the stale-aware
  `r4_mutation_service.publish_draft`; legacy undo/redo advance `edit_revision`
  by exactly 1 on success and 0 on a no-op and never create a new undoable edit
  (shared `_run_history_command`).
* **Task 5** — the structure-lock operation matrix is consistent across R4 +
  legacy; the lock is structure-only.
* **Task 6** — `MediaAsset.is_referenced()` now sees JSON backgrounds +
  history/baseline snapshots, tenant-scoped + fail-closed; the deletion gate
  refuses a still-referenced/recoverable asset.

Task 7 adds END-TO-END, cross-entry tests that prove the **composite end-state**
converges and that recovery is safe. All scenarios use ONLY real routes /
services / fixtures (Store `akhlaghi` via `StorefrontBuilderViewsTestCase`, the
real R4 mutation/history/publish endpoints, the real legacy section-settings /
undo / redo / publish / restore routes, the real `store_appearance`
persistence, and real `MediaAsset` rows).

---

## Cross-entry scenarios proven

### 1. Full lifecycle convergence (`FullLifecycleConvergenceTests`)
* `test_full_lifecycle_end_state_converges_across_entry_points` — the SAME
  logical sequence (persist canonical typed `store_appearance` manifest →
  mutate a section → revision advances by exactly 1 → publish → previous
  Published archived / draft pointer cleared / promoted version PUBLISHED →
  restore into a fresh Draft) is run once via the LEGACY entry points and once
  via the R4 entry points; the observable end-state (typed manifest byte-for-byte,
  promoted status, published-pointer identity) is asserted **identical** across
  the two entry points.
* `test_undo_redo_after_restore_is_revision_monotonic_and_manifest_intact_both_paths`
  — the sequence continues into undo/redo through BOTH the legacy
  (`storefront-builder-undo`/`-redo`) and the R4 history endpoint
  (`storefront-builder-r4-history`); each successful command advances
  `edit_revision` by exactly 1, restores the expected content, and leaves the
  canonical manifest intact.

### 2. Mixed-sequence safe ordering (`MixedSequenceSafeOrderingTests`)
* `test_legacy_edit_then_stale_r4_replay_is_rejected_and_mutates_nothing` — a
  legacy edit lands on section A, advancing the shared token; an R4 client that
  captured the older revision replays on section B → **409 `stale_revision`**,
  `current_revision` correct, mutating NOTHING (no silent overwrite). The legacy
  edit stands; no lost update.
* `test_r4_edit_then_stale_legacy_publish_is_rejected_and_mutates_nothing` —
  symmetric direction: an R4 edit advances the token under a legacy publisher
  holding an older `base_revision`; the stale legacy publish (routed through the
  shared stale-aware `publish_draft`) is rejected and mutates nothing (Draft not
  promoted); the R4 edit is intact.
* `test_symmetric_safe_ordering_each_write_uses_current_revision_and_both_land`
  — the SAFE ordering: interleaved legacy→R4→legacy→R4 writes that each read the
  current revision immediately before writing all succeed; the token advances
  monotonically by exactly one per real change; every write lands (no lost
  update, no false stale rejection).

### 3. Recovery + media integrity (`RecoveryMediaIntegrityTests`)
All media assertions are **NON-DESTRUCTIVE** — they check `is_referenced()` /
the deletion-gate refusal on THROWAWAY assets (created only for the test, same
store as the referencing section so the tenant-scoped scan matches); they never
destroy a shared fixture.
* `test_manifest_and_referenced_media_survive_undo_redo` — across legacy
  undo/redo the canonical manifest stays intact and a background-referenced
  asset stays `is_referenced()==True` / gate refuses.
* `test_manifest_and_referenced_media_survive_restore` — across publish →
  restore-into-fresh-Draft the manifest survives byte-for-byte and the
  referenced asset stays protected.
* `test_referenced_media_survives_snapshot_only_recovery_reference` — an asset
  referenced ONLY inside an edit-history snapshot (recovery reference, no live
  section) stays protected end-to-end through the real deletion gate.
* `test_manifest_and_referenced_media_survive_baseline_reset` — an asset
  referenced inside a version's `template_baseline_snapshot` (recoverable via
  reset-to-baseline) stays protected; the canonical Appearance stays loadable.

---

## Was any production fix needed?

**No.** This was a pure convergence proof. No cross-entry inconsistency was
discovered. No production file was touched, no migration was produced, and no
new failure signature appeared. `git diff --name-only` shows only
`apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`.

---

## Exact verification outputs

### Primary — lifecycle + media modules (`-v2`)
```
$ /projects/rastisi5_phase2_venv/bin/python manage.py test \
    apps.storefront_builder.tests.test_phase2_lifecycle_safety \
    apps.content.tests.test_phase2_media_reachability -v2
...
Ran 92 tests in 47.293s

OK
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
 OK
System check identified no issues (0 silenced).
```
(83 pre-existing lifecycle+media tests, +9 new Task-7 tests = 92, all OK.)

### Broader regression
```
$ /projects/rastisi5_phase2_venv/bin/python manage.py test \
    apps.storefront_builder.tests.test_r4_mutation_api \
    apps.storefront_builder.tests.test_r4_store_appearance_mutations \
    apps.storefront_builder.tests.test_layout_service \
    apps.storefront_builder.tests.test_phase27_history_identity \
    apps.storefront_builder.tests.test_preset_service
...
Ran 158 tests in 39.811s

OK
Found 158 test(s).
System check identified no issues (0 silenced).
```

### `manage.py check`
```
System check identified no issues (0 silenced).
```

### `makemigrations --check --dry-run`
```
No changes detected
```

### `git diff --check` / `git diff --name-only`
```
$ git diff --check
(clean — no output)

$ git diff --name-only
apps/storefront_builder/tests/test_phase2_lifecycle_safety.py
```

### Known pre-existing failures (NOT touched, NOT in the run scope)
* `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
* 2 FullscreenEditor failures in `test_views`; 1 gallery-label failure in
  `test_u8_template_gallery`.

No new failure signature appeared anywhere in the verification runs above.
