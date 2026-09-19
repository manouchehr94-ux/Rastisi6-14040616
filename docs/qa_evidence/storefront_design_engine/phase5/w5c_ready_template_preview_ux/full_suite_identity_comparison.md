# W5C — Exact-Source Full Suite Identity Comparison

Per the W5C directive, the full `apps.storefront_builder.tests` suite was
run exact-source (clean worktree, no concurrent process touching the same
test database) at the final W5C source HEAD, and its failure/error
identities compared against the accepted baseline.

## Baseline

- The accepted W5A round-2 / W5B baseline, at certified source HEAD
  `128afd19` (W5A) / re-confirmed unchanged through W5B's own
  identity-comparison round (`0359851b`).
- **3478 tests, 30 failures, 2 errors, 1 skipped.**
- Raw output: `/tmp/w5a-evidence/baseline_full_suite.txt` (QA-scratch,
  reused as-is across W5A/W5B/W5C, not committed — the identity list
  below is the durable evidence).

## Final run

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- Source HEAD: `20306214` (branch
  `feature/phase5-w5c-ready-template-preview-ux`, off official
  integration HEAD `3125a325`).
- Run cleanly with **no concurrent process** touching the shared SQLite
  test database (confirmed via `ps`/`git status` immediately before
  starting; browser QA dev-server startup deliberately deferred until
  this run's process fully exited, per the established SQLite-contention
  lesson).
- **Result: `Ran 3525 tests in 3965.271s` — `FAILED (failures=30, errors=2,
  skipped=1)`.**
- Test count increased by exactly 23 (3502 → 3525), matching the 23
  new W5C tests in `test_phase5_w5c_ready_template_preview_ux.py`, all of
  which pass.

## Identity comparison

Both runs' `FAIL:`/`ERROR:` identity lines were extracted, sorted, and
diffed:

```
NEW FAILURE/ERROR IDENTITIES:              0
MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0
```

`diff` of the sorted 32-identity baseline list against the sorted
32-identity W5C final list is **byte-for-byte identical**.

## Reason-level comparison (not just identity)

Each of the 32 matched failure/error blocks' full body (traceback +
assertion message) was extracted and diffed baseline-vs-final:

**32 of 32 are byte-identical.** No identity's file, line number,
exception type, or assertion message differs from baseline in any way.

```
CHANGED HISTORICAL FAILURE/ERROR REASONS: 0
```

## Conclusion (Round 1)

The W5C source change (3 non-test production files — `template_gallery.html`,
`template_gallery_preview.js`, `views.py`'s one-decorator addition — plus
23 new tests and one updated pre-existing test) adds no new failing/
erroring test identity and does not alter any historical failure/error's
reason. All 30 historical failures and 2 historical errors are the same
pre-existing, already-accepted identities carried unmodified from the
baseline, through W5A, W5B, and now W5C.

---

# Round 2 — Independent Architect repair (AUTHORITATIVE)

Because production source (`views.py`, `apply_golden_reference_storefront.py`,
`template_gallery_preview.js`) and Django tests (both the new module and
`test_task2_live_demo_template_preview.py`) all changed in this repair,
round 1's 3525-test run was no longer exact-source. One new, clean,
uncontended full regression was run per the repair directive's §13.

## Accepted immediate baseline (pre-W5C)

**3502 tests, 30 historical failures, 2 historical errors, 1 skip** — the
figure certified after W5B, before any W5C change. (The older raw
identity-comparison baseline file referenced above, at 3478 tests, is
the W5A-round figure this same 32-identity set has already been proven
unchanged against, transitively, at every phase since; it remains the
source of the 32 `FAIL:`/`ERROR:` identity lines themselves, since no
identity has changed shape since then — only the total test count has
grown as each phase adds tests.)

## Final repair run

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- Source HEAD: `bfcedb96` (branch
  `feature/phase5-w5c-ready-template-preview-ux`).
- Run cleanly with **no concurrent process** touching the shared SQLite
  test database (confirmed via `ps`/`git status` immediately before
  starting).
- **Result: `Ran 3531 tests in 4008.719s` — `FAILED (failures=30, errors=2,
  skipped=1)`.**
- Test count increased by exactly 29 over the accepted immediate
  baseline (3502 → 3531), matching all 29 tests now in
  `test_phase5_w5c_ready_template_preview_ux.py` (23 from round 1 + 6
  new repair-round tests: `PreviewMethodContractTests` ×2,
  `DemoPreviewNoBootstrapTests` ×1, `SeededDemoPreviewNonMutationTests`
  ×2, `MerchantPreviewNoBootstrapRegressionTests` ×1), all of which pass.

## Identity comparison (Round 2)

```
NEW FAILURE/ERROR IDENTITIES:              0
MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0
```

`diff` of the sorted 32-identity baseline list against the sorted
32-identity repair-round final list is **byte-for-byte identical** (same
outcome as round 1).

## Reason-level comparison (Round 2)

**32 of 32 are byte-identical.** No identity's file, line number,
exception type, or assertion message differs from baseline in any way.

```
CHANGED HISTORICAL FAILURE/ERROR REASONS: 0
```

## Conclusion (Round 2)

The repair's production changes (a method restriction, a persistence-
path swap to an already-existing non-creating function, a same-origin
iframe Escape listener, and one seeding command's post-publish step) —
plus 6 new tests and one pre-existing test's fixture fix — add no new
failing/erroring test identity and do not alter any historical failure/
error's reason. All 30 historical failures and 2 historical errors
remain the exact same pre-existing, already-accepted identities.
