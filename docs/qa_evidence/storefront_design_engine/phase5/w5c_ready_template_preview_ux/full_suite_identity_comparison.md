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

## Conclusion

The W5C source change (3 non-test production files — `template_gallery.html`,
`template_gallery_preview.js`, `views.py`'s one-decorator addition — plus
23 new tests and one updated pre-existing test) adds no new failing/
erroring test identity and does not alter any historical failure/error's
reason. All 30 historical failures and 2 historical errors are the same
pre-existing, already-accepted identities carried unmodified from the
baseline, through W5A, W5B, and now W5C.
