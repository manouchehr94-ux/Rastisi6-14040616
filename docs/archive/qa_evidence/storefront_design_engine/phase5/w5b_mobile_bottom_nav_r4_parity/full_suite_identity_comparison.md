# W5B — Exact-Source Full Suite Identity Comparison

Per the W5B directive, the full `apps.storefront_builder.tests` suite was run
exact-source (clean worktree, no concurrent process touching the same test
database) at the final W5B source HEAD, and its failure/error identities
compared against the accepted W5A baseline.

## Baseline

- The accepted W5A round-2 final run, at certified source HEAD `128afd19`
  (see `docs/qa_evidence/.../w5a_canonical_editor_safety/full_suite_identity_comparison.md`).
- **3478 tests, 30 failures, 2 errors, 1 skipped.**
- Raw output: `/tmp/w5a-evidence/baseline_full_suite.txt` (QA-scratch,
  reused as-is from the W5A round, not committed — the identity list below
  is the durable evidence).

## Final run

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- Source HEAD: `5ce8bc95` (branch
  `feature/phase5-w5b-mobile-bottom-nav-r4-parity`, off official integration
  HEAD `e8a0a338`).
- Run cleanly with **no concurrent process** touching the shared SQLite test
  database (confirmed via `ps`/`git status` immediately before starting;
  browser QA dev-server startup was deliberately deferred until this run's
  process fully exited, per the SQLite-contention lesson from the W5A round).
- **Result: `Ran 3502 tests in 3939.209s` — `FAILED (failures=30, errors=2,
  skipped=1)`.**
- Test count increased by exactly 24 (3478 → 3502), matching the 24 new
  W5B tests added in `test_phase5_w5b_mobile_bottom_nav_r4_parity.py`, all
  of which pass.

## Identity comparison

Both runs' `FAIL:`/`ERROR:` identity lines were extracted, sorted, and
diffed:

```
NEW FAILURE/ERROR IDENTITIES:              0
MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0
```

`diff` of the sorted 32-identity baseline list against the sorted
32-identity W5B final list is **byte-for-byte identical**.

## Reason-level comparison (not just identity)

Each of the 32 matched failure/error blocks' full body (traceback +
assertion message) was extracted and diffed baseline-vs-final:

- **32 of 32 are byte-identical** — including the 5 identities that in the
  W5A rounds differed only in an embedded, non-deterministic HTML response
  dump; this run happened to reproduce those bytes exactly as well. No
  identity's file, line number, exception type, or assertion message
  differs from baseline in any way.

```
CHANGED HISTORICAL FAILURE/ERROR REASONS: 0
```

## Conclusion

The W5B source change (3 production files, 36 lines, plus 24 new tests) adds
no new failing/erroring test identity and does not alter any historical
failure/error's reason. All 30 historical failures and 2 historical errors
are the same pre-existing, already-accepted identities carried unmodified
from the W5A baseline.
