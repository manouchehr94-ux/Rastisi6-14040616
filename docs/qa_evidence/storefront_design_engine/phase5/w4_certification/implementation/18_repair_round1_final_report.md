# RASTISI PHASE 5 — P5-W4C / Independent Harness Code Review Repair Round 1 — Final Report

This repair addresses IMPLEMENTATION DEFECTS, not design changes. It does
not claim W4C certified.

## Safety gate

- STARTING HEAD (directive's safety gate): `e2f1070e68a259d94092f1c26ecbfe1ab67b19d5`
- STARTING HEAD (this continuation's own starting point -- RED and the
  CRITICAL/IMPORTANT GREEN fix were already committed in the prior part
  of this session): `c00326df4085788dfb2f729e1625ec435df12633`
- FINAL HEAD: `9f6bf48dbb022c5c60f0d8daf6b800a9132717fe`
- OFFICIAL BRANCH UNCHANGED: YES -- `3a4fe9070584655548bae5a9bb574f3415bbf580`
  verified still present and an ancestor of FINAL HEAD (`git merge-base
  --is-ancestor` confirmed); never rewritten, no destructive git
  operations used.

## CRITICAL-1 (stale result rejection)

- CRITICAL-1 REPRODUCED RED: YES (`10_repair_round1_red.txt`, committed
  separately at `e14025d5`)
- CRITICAL-1 FIXED: YES
- RESULT RUN_TOKEN IMPLEMENTED: YES -- `secrets.token_hex(16)` per
  invocation, echoed verbatim by Node into `result.run_token`, validated
  by Python (`_validate_base_result_freshness`/
  `_validate_theme_result_freshness`) against manifest/Template/cell
  identity before merge; previous result file unlinked before every
  real re-run.
- NODE EXIT CORRELATED: YES -- a nonzero exit with no result, a
  malformed/stale/foreign result, or a nonzero exit whose result
  reports no FAIL/BLOCKED cell all raise `CommandError` (BLOCKED); exit
  0 with a missing/malformed/stale/foreign result is likewise rejected.
- INVALID CELL REJECTED: YES -- closed 3-value result enum
  (PASS/FAIL/BLOCKED/N-A handled per §13 schema), unknown/missing
  results rejected before merge.

## IMPORTANT 1-4 (harness/browser contract repairs)

- HOME/LISTING/PDP/CART/THEME CONTRACT IMPLEMENTED: YES -- real
  page-composition checks reusing selectors verified against
  `public_task5_qa.mjs`/`public_task7_qa.mjs`/`public_task8_qa.mjs`/
  `public_w1_qa.mjs` and the production templates (`.rsec`, `article.pcard`,
  `.pdp-tabs`, `.citem`, etc.); rsec/product-card/hero/bottom-nav are now
  required (not merely recorded) for PASS; Hero detection is positional
  (`_home_hero_index`), never the broad `:has-text("")` fallback; Listing
  requires real product cards + a resolving product link; PDP requires
  a non-empty gallery, price, stock text, variant controls, a working
  quantity stepper, and the add-to-cart form; Cart requires a genuinely
  successful add (verified end-to-end in the smoke, not just a caught
  error) plus items/totals/checkout/remove/quantity-update.
- MUHARRAM SAFETY: YES -- `w4cRunThemeCell`'s `muharramSafetyOk` requires
  `rendered.tone === 'mourning'` whenever `activeKey.occasion ===
  'muharram'`, source-backed against `theme_catalog.py`'s tone field, not
  a subjective visual check.
- BOTTOM NAV CONTRACT: YES -- real PASS/FAIL derived from the live
  registry (`_home_bottom_nav_expected`), desktop/tablet require hidden,
  mobile requires visible when the canonical Template declares a
  `bottom_nav_variant`; never a hardcoded key list.
- ACCESSIBILITY CONTRACT: YES -- bounded §10 checks (mobile-nav opener
  accessible name/keyboard focusability/aria-expanded, search input
  labeling) recorded per cell, `n/a` when the control isn't present for
  that template/page.
- MATRIX SCHEMA VALIDATOR: YES -- `_validate_base_cell_schema` enforces
  all required base-cell fields (§13) and the closed result enum before
  any cell is merged.

## IMPORTANT 3 (resume/merge semantics)

- RESUME RUNS ONLY MISSING CELLS: YES -- `_missing_base_cells`/
  `_cell_already_recorded_theme` compute the missing subset before any
  Node invocation; a fully-recorded Template skips Node entirely; a
  partial Template requests only the missing subset.
- ORDINARY RESUME OVERWRITES: NO -- `_merge_base_into_matrix`/
  `_merge_theme_into_matrix` refuse to overwrite any cell already
  carrying a terminal result (PASS or FAIL) in either direction; no
  "recheck" mode exists.
- RECOVERED STATE EVENTS: YES, GENUINELY POPULATED -- confirmed both in
  a unit test (`test_52_recovered_state_event_recorded_on_theme_drift`)
  and in the real bounded smoke's own matrix
  (`_meta.recovered_state_events` in
  `14_repair_round1_smoke_final_matrix.json` records a genuine
  Template-drift repair the harness found and fixed on its own, not an
  initialized-and-never-populated field).

## Test results

- FOCUSED TESTS: 67/67 passing (`11_repair_round1_green.txt`) --
  `test_w4c_all50_certification_harness.py` (67), including 5 tests
  added this round specifically as regressions for what the real
  browser smoke found (source-grep for the listing/theme/cart fixes;
  Python-level in-stock and mixed-stock fixture-selection tests).
- READY-TEMPLATE PREVIEW TESTS: 32/32 passing, 3 skipped as expected
  (unaffected by this round; re-confirmed standalone in
  `11_repair_round1_green.txt`).
- QA HARNESS CONTRACT TESTS: 4/4 passing (unaffected; re-confirmed
  standalone in the same file).
- NODE CHECK: clean (`17_repair_round1_final_gates.txt`).
- DJANGO CHECK: clean, 0 issues.
- MIGRATIONS: `makemigrations --check --dry-run` -- no changes detected.
- GIT DIFF CHECK: clean, no whitespace errors (staged and unstaged).
- FULL SUITE (`apps.storefront_builder.tests`, run against `c00326df`):
  3297 tests / 30 failures / 2 errors / 4 skipped
  (`12_repair_round1_full_suite_output.txt`).
- W4C-ONLY FAILURE/ERROR IDENTITIES vs certified baseline: **0** --
  genuine identity-level diff against
  `.../w4b_template_curation/implementation/05_full_storefront_builder_exact_head.txt`'s
  32 failure/error identities is byte-for-byte empty
  (`13_repair_round1_full_suite_identity_comparison.md`).
- CHANGED HISTORICAL FAILURE REASONS: **0** -- all 32 matched
  failure/error blocks carry identical assertion content; the 5 blocks
  that showed a raw text diff on first pass were confirmed to differ
  only in non-deterministic dumped HTML/CSS content or trailing summary
  lines, never in the actual assertion claim (detailed in
  `13_repair_round1_full_suite_identity_comparison.md`).
  This full-suite run predates this session's 2 follow-on smoke-bug-fix
  commits; those commits' correctness is instead established by the
  67/67 focused run (which includes them), the unaffected
  real-previews/qa-harness-contract suites, and the successful browser
  smoke below -- see the "Scope of this comparison" section of
  `13_repair_round1_full_suite_identity_comparison.md` for why a third
  ~34-minute full run was not additionally executed.

## Bounded smoke (editorial_jewelry, section 11)

- BOUNDED SMOKE RUN: YES, `--only editorial_jewelry`, fresh empty
  campaign root, 5 attempts across this round (details and full output
  in `16_repair_round1_smoke_evidence.md` and `15a`-`15e`).
- CELLS RECORDED: 13/13 (12 Base + 1 Tier-1 Theme), matching the
  expected count exactly.
- NODE INVOCATIONS: 2 (1 base batch + 1 theme cell), matching the
  expected count exactly.
- FINAL RESULT: 13/13 PASS, 0 FAIL, 0 BLOCKED, `cleanup_verified: true`.
- SCHEMA COMPLETENESS: all 12 base cells carry all 17 required fields
  plus a distinct `run_token`; the theme cell carries all 7 required
  fields.
- SQLITE RESTORE PROOF: verified after the final run --
  `pre=<sha256> post=<sha256> match=True`.
- Real bugs found and fixed via this smoke (not present in the RED
  suite, because they only manifest under a real browser + real
  fake-host DNS mapping): listing link relative-URL resolution, PDP
  fixture out-of-stock/mixed-stock product selection, theme identity
  comparison against the wrong string, and (found one layer deeper,
  after the first 3 fixes) both the listing link check and the cart
  add-to-cart POST needing to run inside the page's own JS context
  rather than via `page.request`/`context.request`, because W4C's fake
  customer-facing host resolves only through Chromium's own
  `--host-resolver-rules` launch flag.
- 704-CELL CAMPAIGN RUN: NO.
- STATIC GALLERY REFRESH RUN: NO.
- W5 STARTED: NO.
- NO OTHER TEMPLATE STARTED: confirmed -- only `editorial_jewelry` was
  ever touched by any smoke attempt this round.

## Final state

- FINAL WORKTREE CLEAN: YES (verified via `git status --short` before
  each commit; only intended files staged).
- Commits this round (continuation): `e02c0d17` (3 smoke-discovered
  bug fixes: listing origin-prefix, fixture in-stock filter, theme
  identity), `9f6bf48d` (host-resolution fix for listing+cart via
  `page.evaluate`, fixture mixed-stock predicate tightening). Both
  pushed to `origin/feature/phase5-w4c-all50-certification`.
- Nothing merged. No PR opened this round (none was requested).

## FINAL STATUS

**READY FOR INDEPENDENT ARCHITECT W4C HARNESS RE-REVIEW.**

STOP. Do not run the 704-cell campaign. Do not start W5. Do not merge.
