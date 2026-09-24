# Task 3 — Draft-wide `edit_revision` Stale-Write Convergence (L01)

**Worktree:** `/projects/rastisi5_phase2` · **Branch:** `feature/storefront-lifecycle-safety-phase2`
**Base HEAD:** `aab8f1cf68944ee85f92b0a5b964be302c8d5031`
**Spec (binding):** `docs/superpowers/specs/2026-09-06-storefront-lifecycle-safety-phase2-design.md` §7
**Plan:** `docs/superpowers/plans/2026-09-06-storefront-lifecycle-safety-phase2-implementation-plan.md` → Task 3

---

## 1. Gap (L01)

At baseline, `edit_revision` was an **R4-only** optimistic-concurrency token: only
`r4_mutation_service.apply_mutation` / `apply_history_command` advanced it. Legacy
Appearance/Builder view mutations (wrapped by the `@_record_edit_history(label)`
decorator → `_history_record` → `edit_history_service.record_change`) recorded edit
history but **never advanced `edit_revision`**. Consequence: a concurrent R4 client
holding a `base_revision` could not detect a legacy edit under it → silent
last-writer-wins across the legacy-vs-R4 boundary.

## 2. Design choice — centralize the increment in `record_change`

`record_change` is already the **single** point where a REAL change is detected
(it locks the Draft `select_for_update`, snapshots after-state, and returns `False`
on a semantic no-op where `before_state == after_state`). It is therefore the natural,
coherent convergence point: advance `edit_revision` there, in the same atomic block,
exactly when (and only when) a history entry is appended.

Chosen approach (the plan's preferred "cleaner path"):

1. **`edit_history_service.record_change`** — after appending the history entry and
   before returning `True`, advance the token atomically on the locked instance
   (`F("edit_revision") + 1`, save `update_fields=["edit_revision"]`, refresh) and
   mirror the new value onto the caller's `draft` instance so callers observe it
   without a manual refresh. A no-op still returns `False` early → **no** advance,
   **no** history.
2. **`r4_mutation_service.apply_mutation`** — **de-duplicated**: removed its separate
   `draft.edit_revision += 1; save(...)`. It now simply calls `record_change` (which
   performs the single increment) and returns `draft.edit_revision`. This prevents a
   double-increment (advance-by-2).
3. **`r4_mutation_service.apply_history_command`** (Undo/Redo) — **left intact**. It
   deliberately never calls `record_change` (routing Undo/Redo through the normal
   history path would make Undo itself an undoable edit and corrupt history
   semantics), so it keeps its own single `edit_revision += 1`. It is unaffected by
   the advance added in `record_change`.

Both entry points now advance the Draft-wide token by **exactly 1 on a real change,
0 on a no-op**, and history + revision can never drift apart.

**Residual (documented, accepted per §7):** legacy form POSTs still do not accept a
client-supplied `base_revision` (no UI change), so two *legacy* tabs racing remain
last-writer-wins — a bounded risk that does not corrupt lifecycle state. The primary
convergence (legacy edits are now visible to R4's optimistic check) is achieved.

## 3. Production diff summary

| File | Change |
|------|--------|
| `apps/storefront_builder/services/edit_history_service.py` | `record_change`: after the history append, atomically `edit_revision = F("edit_revision") + 1`, save + refresh the locked draft, mirror onto caller's instance. No-op path (`before == after`) returns `False` unchanged → no advance. Docstring documents the single-token contract. |
| `apps/storefront_builder/services/r4_mutation_service.py` | `apply_mutation`: removed the separate `edit_revision += 1; save(...)` (now done inside `record_change`); returns `draft.edit_revision`. No behaviour change for a no-op. `apply_history_command` untouched. |
| `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py` | Flipped the obsolete anti-invariant witness; added no-op test; added cross-path stale-detection test (see §5). |

No changes to: `views.py` (the legacy decorator path benefits automatically because
`record_change` now advances the shared instance/row), `layout_service.py`,
`appearance_authority_service.py`, `render_service.py`, `settings_schema.py`,
`models.py`, templates/CSS/JS. **No DB migration** (`edit_revision` already exists).

## 4. RED → GREEN

**RED (baseline, before fix)** —
`LegacyMutationAdvancesEditRevisionTests.test_legacy_real_mutation_advances_edit_revision_by_one`:
```
AssertionError: 0 != 1
```
(Its baseline-witness companion `test_baseline_legacy_mutation_does_not_advance_edit_revision`
PASSED, asserting the defect — no advance.)

**GREEN (after fix)** — the desired L01 test passes; the obsolete witness was replaced
(see §5). Full `LegacyMutationAdvancesEditRevisionTests` +
`LegacyEditMakesConcurrentR4BaseRevisionStaleTests`:
```
Ran 4 tests ... OK
```

## 5. Test changes / additions

- **Flipped the obsolete witness.** `test_baseline_legacy_mutation_does_not_advance_edit_revision`
  asserted the L01 defect (no advance). It is now removed and replaced by
  `test_legacy_real_mutation_records_exactly_one_history_entry_and_one_revision`, which
  asserts the correct post-fix coherence: exactly **one** history entry AND exactly
  **one** revision advance. No test asserts the defect anymore.
- **(a) legacy real mutation advances by exactly 1** —
  `test_legacy_real_mutation_advances_edit_revision_by_one` (GREEN).
- **(b) legacy no-op advances nothing + records no history** —
  `test_legacy_noop_mutation_advances_nothing_and_records_no_history`: re-submits the
  IDENTICAL section body; asserts `edit_revision` and history count both unchanged (GREEN).
- **(c) R4 mutation still advances by exactly 1 (not 2)** — existing R4 tests assert
  `new_revision == starting + 1` and `draft.edit_revision == starting + 1`, e.g.
  `test_r4_mutation_api.SuccessfulSchemaMutationTests.test_autoplay_toggle_increments_revision_and_persists`
  (GREEN in the module run below). This is the R4 no-double-increment proof.
- **(d) undo/redo still advance by 1** —
  `test_r4_vertical_slice.UndoTests.test_undo_restores_prior_state_and_increments_revision_once`
  and `RedoTests.test_redo_restores_after_state_and_increments_revision_again`
  assert `new_revision == prior + 1` (GREEN — see §7).
- **(e) cross-path stale detection** —
  `LegacyEditMakesConcurrentR4BaseRevisionStaleTests.test_legacy_edit_makes_prior_r4_base_revision_stale`:
  an R4 client captures `base_revision`; a legacy edit lands on the same Draft
  (advancing the token); the R4 client's replay with the now-stale `base_revision` is
  rejected **409 `stale_revision`** with `current_revision == base + 1` and mutates
  nothing (GREEN).

## 6. Required module run (plan step 5)

```
manage.py test \
  apps.storefront_builder.tests.test_phase2_lifecycle_safety \
  apps.storefront_builder.tests.test_r4_mutation_api \
  apps.storefront_builder.tests.test_r4_store_appearance_mutations \
  apps.storefront_builder.tests.test_phase27_history_identity \
  apps.storefront_builder.tests.test_u1a_preset_edit_history_characterization \
  --verbosity 1
=> Ran 92 tests ... OK
```
(The L07 media REDs live in `apps.content.tests.test_phase2_media_reachability`, a
different module owned by Task 6 — not run or fixed here.)

## 7. Broader regression (plan step 6)

```
manage.py test \
  apps.storefront_builder.tests.test_preset_service \
  apps.storefront_builder.tests.test_u7_ready_template_baseline \
  apps.storefront_builder.tests.test_layout_service \
  --verbosity 1
=> Ran 112 tests ... OK
```

Additional undo/redo evidence (R4 history path unaffected):
```
manage.py test \
  apps.storefront_builder.tests.test_r4_vertical_slice.UndoTests \
  apps.storefront_builder.tests.test_r4_vertical_slice.RedoTests \
  apps.storefront_builder.tests.test_r4_vertical_slice.NoOpHistoryCommandTests \
  --verbosity 2
=> Ran 8 tests ... OK
```

### Pre-existing baseline failure (NOT caused by this task, NOT in scope)
`test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
fails asserting `validate_appearance_config` was called once but was called twice.
Proven pre-existing by re-running it with this task's changes stashed on clean HEAD
`aab8f1c` — it fails identically. This module is in NEITHER the step-5 required list
nor the step-6 regression list; it was run only voluntarily to gather undo/redo
evidence. Not a regression from Task 3.

## 8. check / migrations (plan step 7)

```
manage.py check                        => System check identified no issues (0 silenced).
manage.py makemigrations --check --dry-run => No changes detected
```
No migration was created (none required — `edit_revision` already exists).

## 9. Scope

`git diff --check` clean; changed files limited to the two allowed production files
plus the Task-3 test file:
- `apps/storefront_builder/services/edit_history_service.py`
- `apps/storefront_builder/services/r4_mutation_service.py`
- `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`
- `docs/qa_evidence/.../phase2/task3_revision_convergence.md` (this evidence)

`_sdd_ledger.md` is intentionally NOT staged. No push.
