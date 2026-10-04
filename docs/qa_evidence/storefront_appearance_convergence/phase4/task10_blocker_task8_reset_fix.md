# Phase 4 — Task-10 blocker corrective fix: Task-8 reset classification

Scope note (read first): this is a **narrowly scoped Task-8 corrective
implementation session**, not Task 10. Task 10 correctly FAILED and
STOPPED after finding one genuine new regression in
`reset_storefront_to_baseline()`. This session's only job is to fix that
one regression, prove it, and stop — no unrelated architecture work, no
Phase 5, no Phase-4-final backup. **Task 10 was NOT resumed here. Phase 4
remains NOT CLOSED until Task 10 is rerun.**

## Task-10 failure that triggered this session

Existing regression test, already part of the Task-8 U7 suite (not new):

```
apps.storefront_builder.tests.test_u7_ready_template_baseline.ResetToBaselineTests.test_reset_rejects_unknown_template_key
```

Expected: `UnknownPresetError`.
Actual on `330cbe46df6230e06c10328e96018a48cb8d79bd` (this session's starting
HEAD): `TemplateBaselineVersionChangedError`.

## Phase-3 / prior baseline behavior

Before Task 8's content-preserving Template Switch existed,
`reset_storefront_to_baseline()` had exactly two paths once
`template_provenance` was present: an exact-matching-snapshot restore, or a
legacy Registry-lookup fallback (`UnknownPresetError` if the provenance key
was gone from the Registry, `TemplateBaselineVersionChangedError` if the
key existed but its version differed). A snapshot that existed but simply
*mismatched* current provenance was not a case that could previously arise
at all — nothing before Task 8 ever changed `template_provenance` without
also rebuilding `template_baseline_snapshot` to match it.

## Root cause

Task-8 review-fix commit `18bedd18026cbacebcb2433259c4d4617a502d9b`
introduced exactly that new state: `switch_template_preserving_content`
deliberately updates `template_provenance` to the new Template (Template B)
while leaving `template_baseline_snapshot` untouched (still describing
Template A) — because rebuilding the snapshot would mean fabricating an
exact historical baseline for composition the content-preserving switch
never actually applied (see that function's own docstring). Commit
`18bedd1` correctly added protection for this new state: a mismatched
snapshot now refuses the unsafe full reset with
`TemplateBaselineVersionChangedError` instead of silently wiping the
switch's preserved content.

The bug: the guard was `if snapshot: raise TemplateBaselineVersionChangedError(...)`
— unconditional on *any* mismatch, with no check of whether the current
provenance `template_key` was still a real, registered Template at all.
That collapsed two genuinely different situations into one error:

- A real Template-Switch mismatch (Template B still registered) — correctly
  `TemplateBaselineVersionChangedError`.
- A mismatched snapshot whose provenance key no longer exists in the
  Registry at all (e.g. a Draft whose provenance was corrupted/rewritten to
  point at a preset key that was never real, or a retired preset) — this
  was misclassified the same way, when it should be `UnknownPresetError`,
  exactly like the pre-existing legacy no-snapshot fallback already does
  for the identical condition (missing key -> `UnknownPresetError`).

## Three-case contract (A/B/C)

- **CASE A** — `snapshot.template_key == provenance.template.key` AND
  `snapshot.template_version == provenance.template.version`: restore
  directly from the immutable `template_baseline_snapshot`
  (`apply_baseline_snapshot`), never touching the live
  `layout_preset_registry` for content. The Registry is consulted only
  afterwards, only for the (optional) metadata return value. This branch
  was not touched by this fix and remains fully independent of later
  Registry changes.
- **CASE B** — snapshot exists but mismatches provenance, AND the current
  provenance `template_key` **is still registered**: `TemplateBaselineVersionChangedError`
  (the Task-8 content-preserving-switch protection — unchanged).
- **CASE C** — snapshot exists but mismatches provenance, AND the current
  provenance `template_key` **is NOT registered**: `UnknownPresetError`
  (the Task-10 regression — now fixed).

## RED evidence

```
.venv/bin/python manage.py test apps.storefront_builder.tests.test_u7_ready_template_baseline.ResetToBaselineTests.test_reset_rejects_unknown_template_key -v 2
```
```
FAIL/ERROR: apps.storefront_builder.services.preset_service.TemplateBaselineVersionChangedError:
عکسِ baselineِ ذخیره‌شده‌یِ این Draft برایِ «dense_catalog» است، نه «this-preset-key-does-not-exist» — ...
Ran 1 test in 0.171s
FAILED (errors=1)
```

Also confirmed, before any change, that the Task-8 safety test was (and
had to remain) green:
```
.venv/bin/python manage.py test apps.storefront_builder.tests.test_r4_vertical_slice -k test_reset_storefront_after_switch_is_rejected_not_silently_destructive -v 2
...
Ran 1 test in 1.695s
OK
```

## Fix

`apps/storefront_builder/services/preset_service.py`,
`reset_storefront_to_baseline()`: in the mismatched-snapshot branch, check
`layout_preset_registry.get_layout_preset(template_key)` for existence
**before** raising. Missing -> `UnknownPresetError` (same message pattern
as the pre-existing legacy fallback's equivalent check). Still registered
-> the original, unchanged `TemplateBaselineVersionChangedError`. The
exact-matching-snapshot branch (CASE A) was left completely untouched —
no Registry lookup was hoisted ahead of it.

New regression test added:
`test_reset_from_exact_matching_snapshot_survives_registry_disappearance`
— applies a preset (creating an exact-matching snapshot), deletes the
Draft's home-page sections, patches `layout_preset_registry.get_layout_preset`
to return `None` (simulating the Registry no longer resolving that key),
and asserts the reset still restores the Draft's content from the
immutable snapshot (the metadata return value alone comes back `None`).
This locks CASE A's independence from the Registry and guards against the
"obvious over-fix" of hoisting the Registry lookup ahead of the
exact-match branch.

## GREEN evidence

```
.venv/bin/python manage.py test apps.storefront_builder.tests.test_u7_ready_template_baseline -v 2
```
```
Ran 12 tests in 0.711s
OK
```
Includes: `test_reset_rejects_unknown_template_key` (originally-failing
test, now green), `test_reset_from_exact_matching_snapshot_survives_registry_disappearance`
(new CASE A guard), and all pre-existing U7 tests unaffected.

```
.venv/bin/python manage.py test apps.storefront_builder.tests.test_r4_vertical_slice.TemplateSwitchPreservingContentTests -v 2
```
```
Ran 9 tests in 12.858s
OK
```
Includes `test_reset_storefront_after_switch_is_rejected_not_silently_destructive`
(Task-8 CASE B protection) — confirmed still green, unweakened.

## Targeted regression results

```
.venv/bin/python manage.py test apps.storefront_builder.tests.test_acceptance_batch2 \
  apps.storefront_builder.tests.test_preset_service apps.storefront_builder.tests.test_r4_mutation_api \
  apps.storefront_builder.tests.test_r4_vertical_slice apps.storefront_builder.tests.test_u7_ready_template_baseline \
  apps.storefront_builder.tests.test_u8_template_gallery -v 1
```
```
Ran 344 tests in 394.016s
FAILED (failures=2)
```
The 2 failures are:
- `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
  (`validate_appearance_config` mock called 2 times instead of once)
- `test_u8_template_gallery.TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset`
  (a Persian label string not found in the rendered response)

Both are unrelated to `reset_storefront_to_baseline`/`preset_service`'s
reset-classification logic. Verified pre-existing (not introduced by this
fix) by `git stash`-ing both changed files back to the unmodified starting
HEAD (`330cbe46`) and re-running these exact two tests in isolation — they
fail identically on unmodified HEAD with the same assertion errors. Zero
new regressions from this corrective fix.

`manage.py check`: `System check identified no issues (0 silenced).`
`manage.py makemigrations --check --dry-run`: `No changes detected` (no
migration files changed or needed — this is a pure classification-order
fix, no model changes).
`git diff --check`: clean (no output).

## Reviewer verdict

One fresh, read-only-in-spirit reviewer, dispatched in an isolated git
worktree against commit `7ebc402` (this fix), independently re-ran:
```
.venv/bin/python manage.py test apps.storefront_builder.tests.test_u7_ready_template_baseline \
  apps.storefront_builder.tests.test_r4_vertical_slice.TemplateSwitchPreservingContentTests -v 2
```
Result: **Ran 21 tests — OK** (0 failures, 0 errors).

Verdicts:
- UNKNOWN KEY CLASSIFICATION: **PASS**
- TEMPLATE-SWITCH RESET SAFETY: **PASS**
- IMMUTABLE SNAPSHOT INDEPENDENCE: **PASS**
- NO PARALLEL AUTHORITY: **PASS**
- SCOPE DISCIPLINE: **PASS**

CRITICAL: **0**. IMPORTANT: **0**. (One process-only note about confirming
the branch gets pushed along the intended path — addressed by this
session's own Step 7 push/backup, not a code defect.)

## Explicit status

- **TASK 10: NOT RESUMED.** This session did not rerun or continue Task
  10's exhaustive suite; it only fixed the one blocker Task 10 found.
- **PHASE 4: NOT CLOSED YET.** Closure requires Task 10 to be rerun
  end-to-end against this corrected HEAD.
- **PHASE 5: NOT STARTED.**
