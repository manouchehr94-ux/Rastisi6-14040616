# Task 5 — Structure-Lock Matrix Convergence + Lifecycle-Safe Template/Reset (L04, L06)

Branch `feature/storefront-lifecycle-safety-phase2`, worktree `/projects/rastisi5_phase2`,
venv `/projects/rastisi5_phase2_venv/bin/python` (Python 3.12.13, Django 5.2.17), base HEAD `e611647`.

## Scope

* **L06** — prove the authoritative structure-lock operation matrix (spec §11) is COMPLETE and
  CONSISTENT across BOTH the R4 structure path (`section_structure_service` behind the R4 mutation
  route) and the legacy views, for both `StorefrontSection.is_locked` and `StorefrontContainer.is_locked`.
* **L04** — legacy template-apply + reset endpoints are atomic, revision-coherent (advance
  `edit_revision` on a REAL change, advance NOTHING on a no-op), and continue to refuse a page with a
  locked section via `LockedSectionsPresentError`. Apply/reset MEANING unchanged (full replacement/reset;
  no content-preserving Switch — deferred to Phase 3).

Structure-lock is a **structural** lock only — it never blocks a content/appearance edit, the visibility
toggles, the lock toggle itself, or duplication (which creates a NEW logical section).

## Files changed

* `apps/storefront_builder/views.py` — reset route only: `storefront_page_reset` now also catches
  `preset_service.InvalidPresetError` (the RED→GREEN gap fix below). No other production file changed —
  every other matrix cell was already guarded.
* `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py` — 32 new tests (8 classes).

No models/migration change (`makemigrations --check --dry-run` → *No changes detected*). No renderer,
no appearance-authority, no business-domain change. No new lock type/field. No new content/appearance lock.

## Matrix verification — per-cell (R4 path + legacy path)

| Operation | Locked: allowed? | Enforcement site | Status |
|---|---|---|---|
| Section move / reorder | NO | `section_structure_service.move_section` (`section_locked`/`target_locked`/`container_locked`); legacy `storefront_section_move` + `_reorder` (`is_locked` + neighbor + reorder-position guard) | **already guarded** — GREEN both paths |
| Section remove | NO | `section_structure_service.remove_section` (`section_locked`/`container_locked`); legacy `storefront_section_remove` (`is_locked`) | **already guarded** — GREEN both paths |
| Block move / remove (within cell) | NO | legacy `storefront_block_move` (`section.is_locked`, `container_service.move_block` `container_locked`), `storefront_block_remove` (`cell.container.is_locked or section.is_locked`) | **already guarded** — GREEN (R4 exposes no block-level mutation) |
| Container settings / layout / move / remove | NO (locked container) | legacy `storefront_container_settings`/`_layout`(`change_container_layout`)/`_move`/`_remove` (`container.is_locked` + neighbor) | **already guarded** — GREEN |
| Cell add-section / clear | NO (locked container) | legacy `storefront_cell_add_section` (`cell.container.is_locked`), `storefront_cell_clear` (`cell.container.is_locked` + per-block `is_locked`); `container_service.add_block`/`clear_cell` | **already guarded** — GREEN |
| Template apply over page w/ locked section | NO | `preset_service.apply_preset` → `LockedSectionsPresentError` (already covered by `test_preset_service.LockedSectionsBlockPresetApplyTests`) | **already guarded** — GREEN |
| Baseline reset over page w/ locked section | NO | `preset_service.apply_baseline_snapshot` / `reset_page_to_baseline` → `LockedSectionsPresentError`; view `storefront_page_reset` | service **already guarded**; **view GAP FOUND + FIXED** (see below) |
| Section settings edit (content/appearance) | YES | not blocked — `section.update_settings` (R4) / `storefront_section_settings` (legacy) | **allowed** — GREEN both paths |
| Toggle active / collapse / lock-toggle | YES | `storefront_section_toggle` / `_collapse_toggle` / `_lock_toggle` (no lock check) | **allowed** — GREEN |
| Section duplicate (new logical section) | YES | `section_structure_service.duplicate_section` (no `section.is_locked` check); legacy `storefront_section_duplicate` | **allowed** — GREEN both paths |

**Result:** every "NO" cell was ALREADY refused-and-atomic on both paths, and every "YES" cell already
succeeds on a locked section — with ONE exception discovered by the RED tests below.

## The one gap found + fixed (RED → GREEN)

**Cell:** *Baseline reset over a page with a locked section* — the **view** boundary of the reset path.

* **RED:** `storefront_page_reset` caught only `preset_service.BaselineResetError`. But
  `LockedSectionsPresentError` subclasses `InvalidPresetError` (NOT `BaselineResetError`), so a page-reset
  on a page carrying a locked section raised an **uncaught** `LockedSectionsPresentError` → **HTTP 500**.
  Verified RED with the fix reverted (`git stash`):

  ```
  ERROR django.request: Internal Server Error: /admin-portal/storefront-builder/page/reset/
      raise LockedSectionsPresentError(
  apps.storefront_builder.services.preset_service.LockedSectionsPresentError: بازنشانی ممکن نیست — صفحه‌ی «صفحه اصلی» بخشِ قفل‌شده دارد؛ ...
  Ran 1 test in 0.587s
  FAILED (errors=1)
  ```

* **GREEN (minimal fix):** add `except preset_service.InvalidPresetError` to `storefront_page_reset`,
  mirroring the already-correct `storefront_reset_to_baseline` (and the apply-preset view). The service
  (`reset_page_to_baseline` / `reset_page_with_checkpoint`, both `@transaction.atomic`) already raised the
  refusal and rolled back any checkpoint — only the view crashed. After the fix the refusal is a clean
  302 + Persian `messages.error`, the locked section (and every sibling) is intact, and no new checkpoint
  Draft is created.

  ```
  Ran 1 test in 0.635s
  OK
  ```

This is structure-only: the lock does not block the reset because the *reset* is disallowed — it blocks
because the reset would structurally delete + rebuild a page that contains a locked section, exactly the
same protection `storefront_section_remove` and `apply_preset` already enforce.

## L04 — revision coherence confirmation

* **In-place granular resets** (`storefront_section_field_reset`, `storefront_appearance_field_reset`,
  and the section/header/footer resets) mutate the SAME active Draft, so they route through the
  `@_record_edit_history` decorator → `edit_history_service.record_change` (the single Task-3
  revision-advance contract):
  * a **real** reset advances `edit_revision` by **exactly 1** AND appends **exactly one** history entry;
  * a **no-op** reset (field already equal to baseline) advances **nothing** and records **nothing**.
* **Checkpoint-based apply/whole-storefront reset** (`apply_preset_with_checkpoint`,
  `reset_storefront_with_checkpoint`, `reset_page_with_checkpoint`) preserve the previous Draft as a
  recoverable **ARCHIVED** checkpoint and rebuild on a fresh active Draft. The Published version is never
  touched, the operation never auto-publishes, and it is atomic (a refused/locked apply creates no new
  Draft and leaves the active Draft pointer unchanged). Apply/reset MEANING (full replacement/reset) is
  unchanged.

## Lock stayed structure-only (positive proof)

On a **locked** section, all "YES" operations still succeed (proven both R4 + legacy where applicable):
settings edit (content/appearance), toggle active, collapse, lock-toggle (unlocks it), and duplicate
(creates a NEW logical section with a fresh `stable_id`, itself unlocked; the source stays locked/intact).

## New tests added (`test_phase2_lifecycle_safety.py`, 32 tests, 8 classes)

* `R4StructureLockNegativeTests` (4) — R4 `section.remove`/`section.move` refused on locked
  source/target/container (`section_locked`/`target_locked`/`container_locked`), atomic (no revision/history).
* `R4StructureLockPositiveTests` (2) — R4 settings edit + duplicate succeed on a locked section.
* `LegacySectionStructureLockNegativeTests` (6) — legacy section remove/move(×2)/reorder + block move/remove
  refused on locked section, no revision/history advance.
* `LegacyContainerStructureLockNegativeTests` (6) — legacy container settings/layout/move/remove + cell
  add-section/clear refused on locked container, no advance.
* `LegacyStructureLockPositiveTests` (5) — settings edit / toggle / collapse / lock-toggle / duplicate all
  succeed on a locked section.
* `BaselineResetLockRefusalTests` (3) — `apply_baseline_snapshot` + `reset_page_to_baseline` refuse a
  locked page atomically; the `storefront_page_reset` VIEW now refuses cleanly (the RED→GREEN gap).
* `LegacyInPlaceResetRevisionCoherenceTests` (4) — section-field + appearance-field reset advance
  `edit_revision` by exactly 1 (+1 history) on a real change, and by nothing on a no-op.
* `LegacyCheckpointApplyLifecycleTests` (2) — apply-preset view over existing content is atomic + checkpoints
  (new Draft, prior Draft ARCHIVED, provenance recorded, published untouched); refuses a locked page (no new Draft).

## Verification output

* `test_phase2_lifecycle_safety test_preset_service test_u7_ready_template_baseline test_phase5_composition_lifecycle -v2` → **Ran 139 tests … OK** (`System check identified no issues`).
* Regression `test_r4_mutation_api test_r4_store_appearance_mutations` → **Ran 53 tests … OK**.
* `test_phase2_lifecycle_safety` alone → **Ran 73 tests … OK**.
* `manage.py check` → **System check identified no issues (0 silenced).**
* `manage.py makemigrations --check --dry-run` → **No changes detected**.
* `git diff --check` → clean. `git diff --name-only` → `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`, `apps/storefront_builder/views.py`.

No NEW test-failure signature outside the KNOWN pre-existing list (those modules were not run/altered here).
