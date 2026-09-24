# Phase 2 — Task 4: Publish / Undo / Redo / Restore / Discard Lifecycle Safety (gaps L02, L03)

Branch: `feature/storefront-lifecycle-safety-phase2`
Worktree: `/projects/rastisi5_phase2`
Base HEAD: `ee13187` (Task 3 — draft edit_revision convergence across legacy and R4)
Python/Django: `/projects/rastisi5_phase2_venv/bin/python` (Python 3.12.13, Django 5.2.17)

## Goal

Make the **legacy** storefront lifecycle entry points reach the same
revision- and lifecycle-safety guarantees the R4 path already had, WITHOUT
changing what publish or undo/redo *mean*, and WITHOUT any schema/migration
change.

- **L02** — legacy `storefront_publish` must reach the same lifecycle
  guarantee as R4 `publish_draft` (atomic; archive previous Published; clear
  draft history + pointer; swap pointers) by delegating to the SAME shared
  `layout_service.publish` contract, and detect a stale publish coherently
  where a base revision is available on the request.
- **L03** — legacy `storefront_undo` / `storefront_redo` must be atomic and
  revision-coherent: a successful undo/redo advances the Draft-wide
  `edit_revision` by exactly 1 (matching R4 `apply_history_command`), while
  still NEVER creating a new undoable history entry.
- Prove restore/discard remain atomic + Draft-lifecycle-correct and recover
  the canonical typed `store_appearance` manifest intact across an
  apply → undo → redo → restore round-trip (structurally byte-for-byte equal),
  revision monotonic where a real change occurred.

## What was RED at baseline (and why)

Legacy `storefront_undo` / `storefront_redo` called `edit_history_service.undo/redo`
directly with **no lock** and **no `edit_revision` advance**. So a successful
legacy undo/redo restored older content but left the Draft-wide revision token
unchanged — undo/redo through the legacy entry point was NOT revision-monotonic
(L03).

`storefront_publish` already delegated to `layout_service.publish` (so its
atomicity / archive / clear-history / pointer-swap lifecycle was already
correct), but it had no optimistic-concurrency (stale) guard, unlike R4
`publish_draft` (L02).

### RED evidence (before the production change)

New tests added to `apps/storefront_builder/tests/test_phase2_lifecycle_safety.py`
were run against the unchanged production code:

```
FAIL: test_successful_undo_advances_edit_revision_by_exactly_one
    self.assertEqual(draft.edit_revision, revision_before + 1)
AssertionError: 2 != 3
FAIL: test_successful_redo_advances_edit_revision_by_exactly_one
    self.assertEqual(draft.edit_revision, revision_before + 1)
AssertionError: 2 != 3
FAIL: test_undo_then_redo_is_revision_monotonic
    self.assertEqual(r1, r0 + 1)
AssertionError: 2 != 3
FAIL: test_store_appearance_manifest_survives_undo_redo_restore_round_trip
    self.assertEqual(draft.edit_revision, rev_after_edit + 1)
AssertionError: 1 != 2
----------------------------------------------------------------------
Ran 8 tests ... FAILED (failures=4)
```

The failures are for exactly the right reason: legacy undo/redo did not advance
`edit_revision` (`2 != 3` / `1 != 2` — the token stayed put). The publish
lifecycle test and the discard test already passed at baseline (publish already
delegated to `layout_service.publish`; discard was already atomic), and the
manifest-content assertions passed — only the *revision-monotonicity* assertion
after a legacy undo failed. This confirms L03 was the live defect and L02's
atomicity/lifecycle was already met (only the stale guard was missing).

## The production change (minimal, GREEN)

### L03 — legacy undo/redo revision coherence

`apps/storefront_builder/services/r4_mutation_service.py` (expose/reuse the
shared history lifecycle contract only — no mutation behavior changed):

- Extracted the existing Undo/Redo execution body of `apply_history_command`
  into a shared `_run_history_command(draft, command)`. This is the ONE place
  that runs `edit_history_service.undo/redo` and owns the single
  `edit_revision += 1` on a successful command (no-op advances nothing;
  Undo/Redo never calls `record_change`, so no new undoable edit is ever
  created). `apply_history_command` (R4) now calls it after locking via
  `_lock_active_draft`.
- Added `apply_history_command_current(store, command)` for the legacy path:
  same execution contract, but WITHOUT a client-supplied `base_revision`
  (legacy form POSTs carry none). It `select_for_update()`-locks the store's
  `StorefrontLayout` + its active DRAFT `StorefrontLayoutVersion` and runs the
  SAME `_run_history_command`. Because it locks against the Draft's own state
  (no optimistic base to compare) it can never spuriously reject.

`apps/storefront_builder/views.py`:

- `storefront_undo` / `storefront_redo` now delegate to a shared
  `_legacy_history_command(request, command)` which calls
  `r4_mutation_service.apply_history_command_current(...)`. `get_or_create_draft`
  is still called first so an active Draft always exists (a Draft with no
  recorded history remains a controlled no-op → `ok=False`, exactly as before).
  The JSON payload shape (`history_state` fields + `ok` + `action_label`) is
  unchanged.

### L02 — legacy publish lifecycle + stale guard

`apps/storefront_builder/views.py`:

- `storefront_publish` now reads an OPTIONAL `base_revision` from the request
  (`_optional_base_revision` — absent/blank/malformed → `None`, forward-compatible
  hook; the legacy form has no such field today). When a valid revision is
  present, publish is routed through the shared, stale-aware
  `r4_mutation_service.publish_draft` (which locks/compares via the SAME
  concurrency boundary as every R4 write, then delegates to `layout_service.publish`).
  A stale revision is rejected coherently (Persian error message, mutates
  nothing — the R4 409 `stale_revision` analogue). When no revision is supplied,
  publish stays exactly as before: `layout_service.publish` (already atomic:
  archives previous Published, clears draft history + pointer, swaps pointers).

**Publish and undo/redo semantics are unchanged.** Undo/redo still restore the
recorded before/after content and never append a new undoable history entry;
publish still means "promote the active Draft to Published, archive the previous
Published, clear the short-lived edit history". The only added behavior is the
`edit_revision` advance on legacy undo/redo and the optional stale-publish
rejection.

`layout_service.py` was NOT modified — the shared publish/history lifecycle
contract already lives in `layout_service.publish` / `edit_history_service`, and
this task reuses it rather than duplicating it.

## GREEN evidence + full verification

### Primary + supporting suites

```
$ .../python manage.py test \
    apps.storefront_builder.tests.test_phase2_lifecycle_safety \
    apps.storefront_builder.tests.test_layout_service \
    apps.storefront_builder.tests.test_phase27_history_identity \
    apps.storefront_builder.tests.test_u7_ready_template_baseline -v2
...
Ran 118 tests in 30.904s
OK
System check identified no issues (0 silenced).
```

(`test_phase2_lifecycle_safety` = 41 tests: 31 pre-existing + 10 new for Task 4.)

### R4 regression suites (prove no regression through the shared contract)

```
$ .../python manage.py test \
    apps.storefront_builder.tests.test_r4_mutation_api \
    apps.storefront_builder.tests.test_r4_store_appearance_mutations
Ran 53 tests in 20.664s
OK
```

### `manage.py check`

```
System check identified no issues (0 silenced).
```

### `manage.py makemigrations --check --dry-run` (MUST report no changes)

```
No changes detected
```

### `git diff --check` / `git diff --name-only`

```
$ git diff --check
(clean)
$ git diff --name-only
apps/storefront_builder/services/r4_mutation_service.py
apps/storefront_builder/tests/test_phase2_lifecycle_safety.py
apps/storefront_builder/views.py
```

## Known pre-existing failures (unchanged, NOT introduced here)

Confirmed still failing with the SAME signatures at this HEAD (not regressions):

- `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
  — validator called twice vs once (Ran 88, failures=1).
- `test_views.FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`
  (FAIL) and `...test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route` (ERROR)
  — the 2 FullscreenEditor failures (Ran 213, failures=1 errors=1).
- `test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset`
  — the gallery-label failure (Ran 11, failures=1).

No NEW failure signatures appeared.

## Invariants re-affirmed

- Undo/redo through EITHER entry point (legacy or R4) advances `edit_revision`
  by exactly 1 on success and by 0 on a no-op.
- Undo/redo create NO new undoable history entry (total history-entry count is
  unchanged across a legacy undo/redo — an entry only flips `is_undone`).
- Legacy publish is atomic + lifecycle-correct (delegates to
  `layout_service.publish`), and rejects a stale publish coherently when a base
  revision is provided.
- The canonical typed `store_appearance` manifest survives
  apply → undo → redo → publish → restore byte-for-byte (structurally equal).
- No schema change / migration.
