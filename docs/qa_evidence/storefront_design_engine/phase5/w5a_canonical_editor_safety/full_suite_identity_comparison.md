# W5A — Exact-Source Full Suite Identity Comparison

Per master-plan §25, the full `apps.storefront_builder.tests` suite was run
exact-source (clean worktree, no concurrent process touching the same test
database) at the final HEAD, and its failure/error identities compared
against the accepted W4C baseline.

## Baseline

- Captured earlier in this round at commit `e88ebac0` (approved master-plan
  base), before any W5A source change: `docs/qa_evidence/.../starting_state.md`.
- **3418 tests, 30 failures, 2 errors, 1 skipped.**
- Raw output: `/tmp/w5a-evidence/baseline_full_suite.txt` (QA-scratch, not
  committed — the identity list below is the durable evidence).

## Final run

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- HEAD: `6019a82e74fb09989b40f1d3828f74f45a70937d` (branch
  `feature/phase5-w5a-canonical-editor-safety`, off approved base `e88ebac0`).
- Run cleanly with **no concurrent process** touching the shared SQLite test
  database (an earlier attempt was contaminated by a second, unrelated
  in-flight test run sharing the same `test_db.sqlite3` file and was
  discarded without being used as evidence — see "Contaminated intermediate
  run" below).
- **Result: `Ran 3468 tests in 2502.003s` — `FAILED (failures=30, errors=2,
  skipped=1)`.**
- Test count increased by exactly 50 (3418 → 3468), matching the 50 new
  W5A tests added in `test_phase5_w5a_canonical_editor_safety.py`, all of
  which pass.

## Identity comparison

Both runs' `FAIL:`/`ERROR:` identity lines were extracted, sorted, and
diffed:

```
NEW FAILURE/ERROR IDENTITIES:          0
MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0
```

`diff` of the sorted 32-identity baseline list against the sorted
32-identity final list is **byte-for-byte identical**.

## Reason-level comparison (not just identity)

Beyond identity, each of the 32 matched failure/error blocks' full body
(traceback + assertion message) was diffed baseline-vs-final:

- **27 of 32** are byte-identical.
- **5 of 32** differ only in an embedded, large HTML response body that the
  test's own `AssertionError` message includes verbatim (e.g.
  `test_builder_preview_has_nav_but_never_live_cart_count_badge`,
  `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`,
  `test_version_palette_and_global_variants`,
  `test_public_home_renders_functional_mobile_nav_and_real_routes`,
  `test_header_footer_variant_labels_shown_for_updated_preset`). For all
  five, the **file, line number, exception type, and assertion message
  prefix are identical** between baseline and final — only incidental
  byte-content inside the rendered HTML dump (driven by pre-existing,
  W5A-unrelated non-deterministic Store-appearance seed data in the
  fixture, not by any change in this diff) differs. This is the same class
  of noise present between any two independent runs of these
  already-historical, already-accepted failures — not a changed reason.

```
CHANGED HISTORICAL FAILURE/ERROR REASONS: 0
```

## Contaminated intermediate run (discarded, not used as evidence)

An earlier full-suite attempt was started concurrently with an unrelated
targeted re-check process, both against the same file-backed SQLite test
database (`db.sqlite3` → `test_db.sqlite3`). That run produced 25 spurious
new-looking failure/error identities. Two independent clean re-runs (after
killing the contending process) reproduced the identical 25-identity set,
which disambiguated it from flakiness and pointed to two real, distinct
test-authoring bugs from the interim `bf39b8fb` fix commit:

1. A wrong module alias in the AST patch script's `ALIASES` map for
   `test_phase2c_content_preserving_layout_changes.py` (`layout_service`
   instead of the file's actual `layout_service as svc` import) —
   `NameError` in all 14 patched methods.
2. A blanket "pin `r4_editor_enabled=False` at the top of the method"
   approach broke 11 tests (across `test_phase2_lifecycle_safety.py` and
   `test_phase4_task6_group_f_reconciliation.py`) that deliberately
   exercise **both** a legacy route and an R4 route in the same method to
   prove cross-mode revision-staleness/convergence invariants — the
   blanket pin blocked the R4-route half. Two of those eleven additionally
   targeted the wrong Store (`self.store` instead of
   `self.foreign_store`, the actual target of the test's
   `foreign_client`).

Both classes of bug were fixed precisely (see commit `6019a82e`) and
verified: (a) the 33 tests across all affected classes pass together with
no collateral breakage of sibling tests, (b) a broader 943-test sanity
sweep across the originally-affected 17 files plus the W5A suite, showed
zero new identities versus baseline, and (c) round 1's final exact-source
run confirmed zero new/missing/changed at full scale (`3468 tests,
failures=30, errors=2, skipped=1`, at HEAD `6019a82e`). The contaminated
run's output file was not used for any pass/fail determination.

## Round 2 — Independent-Review repair final run

The Independent Architect's PR review of #13 found IMPORTANT 2 / BLOCKING
MINOR 1 (collapse-toggle misclassification, the Class-C ABA hazard, and an
unhandled 500 on rate-limit exhaustion — see `code_review.md`). Fixing them
added 10 more W5A regression tests (50 → 60) and touched `views.py`,
`r4_views.py`, `r4_mutation_service.py`, two templates, and 18 test files
(2 more pinned test methods on top of round 1's 88, surfaced by the newly
guarded collapse-toggle route and the changed Class-C wire contract —
see `code_review.md`'s round-2 section and commits `0edc258c`/`128afd19`).

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- HEAD: `128afd19` (branch `feature/phase5-w5a-canonical-editor-safety`).
- Run cleanly with **no concurrent process** touching the shared SQLite test
  database (confirmed via `ps`/`git status` immediately before starting).
- **Result: `Ran 3478 tests in 2323.931s` — `FAILED (failures=30, errors=2,
  skipped=1)`.**
- Test count increased by exactly 60 versus the original baseline
  (3418 → 3478), matching the 60 W5A tests now in
  `test_phase5_w5a_canonical_editor_safety.py` (50 from round 1 + 10 new
  round-2 regression tests), all of which pass.

### Identity comparison (round 2)

```
NEW FAILURE/ERROR IDENTITIES:              0
MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0
```

`diff` of the sorted 32-identity baseline list against the sorted
32-identity round-2 final list is **byte-for-byte identical** (same
outcome as round 1).

### Reason-level comparison (round 2)

- **27 of 32** byte-identical to baseline.
- **5 of 32** differ only in the same embedded, non-deterministic HTML
  response body noted in round 1 (`test_builder_preview_has_nav_but_never_
  live_cart_count_badge`, `test_fullscreen_button_is_in_v3_topbar_with_
  device_and_zoom_controls`, `test_version_palette_and_global_variants`,
  `test_public_home_renders_functional_mobile_nav_and_real_routes`,
  `test_header_footer_variant_labels_shown_for_updated_preset`) — same
  file, same line, same exception type, same assertion-message prefix,
  reconfirmed by direct comparison against round 1's own final run.

```
CHANGED HISTORICAL FAILURE/ERROR REASONS: 0
```

### Two more regressions found and fixed en route to this clean run

A 1047-test focused sanity sweep run before this final full-suite pass
(after the round-2 production fixes but before the exact-source run)
surfaced 2 new-vs-baseline identities, both caused by the round-2 fixes
themselves, not the original W5A implementation:

1. `FullLifecycleConvergenceTests._run_lifecycle_via_r4`'s Restore call
   (added in round 1) still sent the pre-repair bare `{"base_revision":
   null}` payload; the round-2 Class-C wire-contract change rejected it as
   `invalid_precondition` (missing `base_draft_id`). Fixed by adding
   `base_draft_id: null` alongside it.
2. `LegacyStructureLockPositiveTests.test_collapse_toggle_on_locked_
   section_succeeds` exercises the legacy collapse-toggle route directly
   without pinning `r4_editor_enabled=False`; it never needed the pin
   before because the route was unguarded, and now does, matching its
   sibling tests in the same class.

Both fixed in commit `128afd19`, verified via a 141-test targeted re-check,
then a full 1047-test sanity-sweep re-run showing 0 new identities versus
baseline, before this document's final exact-source run.
