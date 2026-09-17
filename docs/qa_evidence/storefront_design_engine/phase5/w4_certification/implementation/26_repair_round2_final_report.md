# RASTISI PHASE 5 — P5-W4C / Independent Harness Code Review Repair Round 2 — Final Report

This repair addresses IMPLEMENTATION DEFECTS in the harness (the two
authorized files) only. It does not modify production code, and does
not claim the harness or the storefront is fully accessible.

## Safety gate

- BRANCH: `feature/phase5-w4c-all50-certification`
- STARTING RESUME HEAD: `79e83706809e3226ade324c16543caf08f48d330`
- FINAL SOURCE HEAD (last commit touching
  `qa_storefront_builder_r4.py`/`run.mjs`/the test file):
  `5fedd5097aacd3c6d9c22bb46b23cbdb1dfa4a47`
- FINAL BRANCH HEAD: recorded after this evidence commit, below.
- OFFICIAL BRANCH: `3a4fe9070584655548bae5a9bb574f3415bbf580`
- OFFICIAL BRANCH UNCHANGED: YES -- verified via `git rev-parse
  origin/feature/phase5-design-expansion` == the official SHA, and
  `git merge-base --is-ancestor` confirms it is still an ancestor of
  HEAD, never rewritten.
- SOURCE CHANGES AFTER FINAL SOURCE HEAD: 0 -- `git diff --name-status
  5fedd5097aacd3c6d9c22bb46b23cbdb1dfa4a47..79e83706` shows exactly 5
  added files, all under `docs/qa_evidence/.../implementation/`
  (21a-23), no source/test/harness file. Confirmed evidence-only.
- No reset, stash, clean, rebase, amend, or force-push used at any point.

## Repair summary (IMPORTANT 1-6, all implemented and verified)

- **IMPORTANT 1** -- request failures now gate Listing/PDP/Cart/Theme,
  not just Home (`errors.requestFailures.length === 0` in each cell's
  own `passing` computation; exact favicon exclusion retained; no
  broad exclusions added).
- **IMPORTANT 2** -- the full PDP interaction contract: a real variant
  TRANSITION (tracks every option axis's own active control, not just
  the first one found -- a real bug the smoke caught and fixed, see
  below), a real Add-to-Cart effect (`#cart-count` genuinely changes
  after clicking the actual rendered button), real navigation (an
  in-page link resolves 200), and accessibility checks for
  variant/quantity/Add-to-Cart. Fixture now requires >= 2 purchasable
  variants.
- **IMPORTANT 3** -- Listing checks sort/filter/pagination presence,
  wiring, and one bounded real interaction; Cart's remove is a real
  effect (item count genuinely decreases, verified before the
  destructive step per a second smoke-caught ordering bug, see below);
  the Free-Shipping Goal expected state is computed once in Python
  (`Command._w4c_expected_free_shipping_state`) and only verified in
  run.mjs.
- **IMPORTANT 4** -- mobile nav accessibility now checks
  `aria-expanded` toggling, Escape-close, and focus return; added
  Product Card/Quick View, PDP, and Cart control accessibility checks.
- **IMPORTANT 5** -- representative/failure/theme screenshot staging
  under `CAMPAIGN_REPORT_ROOT`; a required screenshot write failure
  forces BLOCKED with a precise reason, never a silent
  `screenshot=null`.
- **IMPORTANT 6** -- the campaign matrix binds itself to the exact
  harness git HEAD at creation, refuses a dirty tracked worktree at
  campaign start, and rejects a resumed batch under a different HEAD;
  `run_started_at`/`run_finished_at` are recorded, the latter only
  once the campaign is genuinely complete.

Full implementation detail: `20_repair_round2_green.txt` and the three
commit messages (`208100c0`, `64dadb82`, `5fedd509`).

## Bugs the bounded smoke found and fixed (TDD: RED test added, then fixed)

1. **Variant-transition tracking bug** (`64dadb82`) -- the check
   tracked only the FIRST active control across all option axes
   combined. Product FSH-003 has a single-value color axis (trivially
   always "active") followed by a 5-value size axis; skipping only
   that one index landed on the size axis's OWN already-selected
   value, so nothing changed. Fixed to track the full active-index SET
   (one per axis). Regression test `test_70b`.
2. **Cart accessibility ordering bug** (`5fedd509`) -- quantity/remove
   control accessibility was checked AFTER the real remove step had
   already emptied the (genuinely single-item) cart, so every check
   came back `n/a`. Reordered to check before the destructive step.
   Regression test `test_84b`.

Full trail: `23_repair_round2_smoke_evidence.md`.

## Two genuine, unresolved production accessibility findings

The bounded smoke's richer diagnostics correctly recorded two
pre-existing production accessibility gaps. These are **not harness
bugs** and were **not fixed** in this round -- fixing either requires
a production-template change outside this round's two authorized
harness files (`qa_storefront_builder_r4.py`, `run.mjs`), which section
8 explicitly forbids touching without a separate, reviewed repair
round. Neither the checks nor the FAIL findings were weakened, removed,
or hidden.

- **Finding A (Listing)** --
  `apps/storefront_builder/templates/storefront_builder/sections/product_listing.html`'s
  `select[name="sort"]` and `select[name="category"]` (in both
  `layout_variant` branches) carry no accessible name at all: no
  associated `<label for>`, no `aria-label`, no `title`. Recorded as
  `accessibility_checks.sort_control` / `.category_filter` = `"FAIL"`
  on every Listing cell.
- **Finding B (PDP)** --
  `apps/storefront_builder/templates/storefront_builder/sections/product_main.html`'s
  `.opt-block .swatch` renders as a plain `<div>` with a `title`
  attribute (so it has an accessible name) but no `tabindex` and no
  button semantics -- it is not keyboard-focusable, unlike its sibling
  `.opt-block .size` `<button>` elements. Recorded as
  `accessibility_checks.variant_control` = `"FAIL"` on every PDP cell
  whose primary option axis renders as swatches.

These findings are why the real 704-cell certification campaign is not
yet cleared to run: the harness now correctly PASSES the 13
page/theme-level cell results in the bounded smoke (see distinction
below), but the accessibility-critical contract it also runs
(IMPORTANT 4, approved by this same review round) surfaces two real,
unresolved defects in the storefront itself.

## Explicit distinction: cell PASS vs. accessibility findings

- **Harness execution smoke: 13/13 cell-level PASS.** Home, Listing,
  PDP, Cart (all 3 viewports each), and the Tier-1 Theme cell all
  computed `result: "PASS"` in their own gating logic, because the
  Listing/PDP accessibility sub-checks above are RECORDED in
  `accessibility_checks` but deliberately do not gate their cell's
  overall PASS/FAIL (the same non-gating treatment repair round 1
  already established for a comparable finding, and consistent with
  section 8's instruction to flag rather than block the whole
  contract on a production gap this round cannot fix).
- **Production accessibility findings: 2 genuine, unresolved gaps**,
  named above, visible in the matrix's own `accessibility_checks`
  fields, never hidden.
- **Therefore:** the harness itself is repaired and verified end-to-end
  (13/13 cells execute their real browser assertions correctly), but
  the full 704-cell certification campaign remains blocked pending a
  separate, Architect-authorized production accessibility repair for
  Findings A and B -- running the full campaign now would certify 50
  Templates' Listing/PDP cells with these two real defects silently
  baked into "PASS" evidence.

## Test results

- FOCUSED W4C TESTS: 102/102 passing (`24b_repair_round2_final_fast_gates_recheck.txt`).
- READY-TEMPLATE REAL-PREVIEW: PASS (32/32, 3 skipped as expected,
  unaffected by this round).
- QA HARNESS CONTRACT: PASS (4/4, unaffected).
- NODE CHECK: PASS.
- DJANGO CHECK: PASS, 0 issues.
- MIGRATIONS: 0 -- `makemigrations --check --dry-run` reports no changes.
- GIT DIFF CHECK: clean, no whitespace errors.
- BOUNDED SMOKE: `editorial_jewelry`, fresh empty root, 3 attempts
  (2 real bugs found and fixed via TDD), final attempt 13/13 PASS, 0
  FAIL, 0 BLOCKED, 2 Node invocations (1 base + 1 theme), matching the
  expected 12 Base + 1 Tier-1 Theme exactly.
  - SQLITE RESTORE: PASS (`pre=<sha256> post=<sha256> match=True`).
  - REPRESENTATIVE SCREENSHOTS: PASS -- 2 Home (desktop+mobile) + 3
    representative (Listing/PDP/Cart, desktop) staged under
    `CAMPAIGN_REPORT_ROOT/screenshots/`; no failure or theme
    screenshots (nothing failed, Tier-1 Theme passed).
  - Matrix `w4c_branch_head_sha`: `5fedd5097aacd3c6d9c22bb46b23cbdb1dfa4a47`
    (the exact final source HEAD this smoke ran at).
  - `duplicate_cells`: `[]`. `recovered_state_events`: one genuine
    Template-drift-repair event, populated, not initialized-and-never-used.
- FULL SUITE (exact final source HEAD `5fedd5097aacd3c6d9c22bb46b23cbdb1dfa4a47`):
  3337 tests / 30 failures / 2 errors / 4 skipped
  (`24_repair_round2_full_suite_output.txt`, confirmed complete by its
  own start/end markers, not a truncated tail).
- NEW W4C-ONLY FAILURE/ERROR IDENTITIES vs certified baseline: **0** --
  genuine identity-level diff against the same
  `05_full_storefront_builder_exact_head.txt` baseline (32
  failure/error identities) is byte-for-byte empty
  (`25_repair_round2_full_suite_identity_comparison.md`).
- CHANGED HISTORICAL FAILURE REASONS: **0** -- all 32 matched
  failure/error blocks carry identical assertion content; the one
  block that showed a raw text diff (the last block in both files)
  differs only in the trailing unittest summary line, never in the
  actual assertion.

## Final state

- 704-CELL CAMPAIGN RUN: NO.
- STATIC GALLERY REFRESH RUN: NO.
- W5 STARTED: NO.
- MERGED: NO.
- Production templates: NOT modified. Accessibility checks: NOT
  weakened, removed, or hidden.
- FINAL WORKTREE CLEAN: YES (verified before every commit this
  session).
- Commits this round: `ae95851d` (RED), `208100c0` (GREEN
  implementation), `64dadb82` (variant-transition bug fix, smoke-found),
  `5fedd509` (cart accessibility ordering bug fix, smoke-found),
  `79e83706` (smoke evidence, evidence-only), and this evidence commit.
  All pushed to `origin/feature/phase5-w4c-all50-certification`.

## FINAL STATUS

**BLOCKED — SEPARATE PRODUCTION ACCESSIBILITY REPAIR REQUIRED BEFORE 704-CELL CAMPAIGN**

The harness itself (the two authorized files) is fully repaired against
all 6 IMPORTANT findings, verified by 102/102 focused tests, a clean
identity-and-reason-level full-suite regression, and a genuinely
passing 13/13 bounded smoke. It is NOT yet cleared to run the real
704-cell campaign, because that smoke's own accessibility-critical
contract (this same review round's own IMPORTANT 4) surfaced two real,
unresolved production accessibility defects (Findings A and B above)
that a full campaign run would otherwise silently certify as "PASS"
evidence across 50 Templates.

STOP.

Do not run the 704-cell campaign.
Do not modify production templates.
Do not start W5.
Do not merge.
Return for Independent Architect review.
