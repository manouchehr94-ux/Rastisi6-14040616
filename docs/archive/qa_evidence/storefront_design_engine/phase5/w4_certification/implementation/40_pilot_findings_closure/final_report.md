# RASTISI PHASE 5 — P5-W4C Pilot Findings Closure — Final Report

## P5-W4C PILOT FINDINGS CLOSURE: **COMPLETE**

STARTING HEAD: `0f952194fb46cafbcec17d7fb0306c1823924b8f`
FINAL SOURCE HEAD: `b3f2c43974ffd528a4374fb6a3c35af20314379c`
FINAL BRANCH HEAD (this report's commit's parent): `54697774`
OFFICIAL BASE: `3a4fe9070584655548bae5a9bb574f3415bbf580`
OFFICIAL UNCHANGED: YES
RATE-LIMIT SHARDING STILL APPROVED: YES (untouched this round; `--w4c-tier2-budget`, the 4-key/4-cell process budgets, the controlled `RateLimitExceeded` diagnostic, missing-only resume, and insert-only matrix merge are all unmodified)
PRODUCTION RATE LIMIT CHANGES: 0

HOME EXPECTATION ROOT CAUSE: harness expectation bug, not a rendering regression — `expected_rsec_count`/`hero_expected`/`hero_index` were derived from the RAW pre-filter Ready Template recipe (`preset.pages["home"]`), which still contains `hidden_from_library` entries (`ticker` → `announcement_bar`, superseded by the header's own notification region) that `preset_service.apply_preset` filters out before ever writing a `StorefrontSection` row
premium_leather RAW HOME COUNT: 4
premium_leather CANONICAL PUBLISHED/RENDERABLE COUNT: 3
HOME EXPECTATION SOURCE: CANONICAL PUBLISHED RENDER PIPELINE (`render_service.build_page_render_items` + `hide_empty_public_sections`, identical to `storefront_context_service.py`'s own public-path sequence)
HARDCODED TEMPLATE EXCEPTIONS: 0 (verified by a dedicated source guard test)
street_drop HERO EXPECTATION: PASS
racer_tech HERO EXPECTATION: PASS
anniversary_mosaic HERO EXPECTATION: PASS
READY TEMPLATE PRODUCTION DEFINITIONS MODIFIED: NO (`a8_ready_templates.py`, `section_registry.py`, `preset_service.py` all unchanged)

CART TABLET INITIAL FINDING REPRODUCED: NO (0/3 fresh repetitions reproduced it)
CART ROOT CAUSE: HARNESS SYNCHRONIZATION (Case A) — the real HTMX remove request/DOM update genuinely succeeds; the old fixed 500ms single observation could simply run before it lands
CART CLICK ERROR SWALLOWED: NO (was swallowed before this round; now captured explicitly and never discarded)
CART REMOVE WAIT: CONDITION-BASED (polls the real `.citem` count until it drops below `before`, bounded at a firm 5s timeout — never forever; a failed click short-circuits immediately instead of wasting the wait)
CART TABLET FINAL: PASS (`removed: true`, `click_error: null`, `http_status: 200`, `dom_swap_observed: true`, `elapsed_ms: 524`, in the closure pilot)

FOCUSED W4C TESTS: 140/140 (the full `test_w4c_all50_certification_harness` module as of the code-review-fix commit, including all 18 tests net-new this round)

CODE REVIEW: CRITICAL 0, IMPORTANT 0 (3 correctness findings surfaced at a lower severity — diagnostic-value/efficiency issues, all fixed; 2 hygiene/style notes left as-is with documented reasoning — see `code_review.md`)

CLOSURE PROCESS 1: 52 cells / 8 Node invocations / matches exactly (48 Base + 4 Tier-1, 0 Tier-2 since budget=0)
CLOSURE PROCESS 1 RATE LIMIT: NONE
CLOSURE PROCESS 1 SQLITE RESTORE: PASS

CLOSURE PROCESS 2: 13 new cells / 2 new Node invocations / matches exactly
CLOSURE CUMULATIVE: 65 (matches exactly: 52 + 13)
CLOSURE DUPLICATES: 0
CLOSURE RATE LIMIT: NONE
CLOSURE SQLITE RESTORE: PASS

FULL SUITE EXACT SOURCE HEAD: `b3f2c43974ffd528a4374fb6a3c35af20314379c`
FULL SUITE: 3401 / 30 / 2 / 4 (total/failures/errors/skipped)
NEW W4C-ONLY FAILURE/ERROR IDENTITIES: 0
CHANGED HISTORICAL FAILURE REASONS: 0

FINAL 704-CELL CAMPAIGN RUN: NO
W5 STARTED: NO
MERGED: NO
FINAL WORKTREE CLEAN: YES

## Summary

Section 2 (source inventory) confirmed the Home expectation root cause
exactly, item by item (`source_inventory_and_reclassification.md`):
`premium_leather`'s raw recipe has 4 tokens including `ticker`
(`announcement_bar`, `hidden_from_library=True`, superseded by the
header's own notification region); `preset_service.apply_preset`
filters every hidden entry before writing any `StorefrontSection` row;
the pre-repair harness compared against the raw count instead. The
same raw-recipe bug shifted the Hero index by one position for every
ticker-before-Hero Template (`street_drop`/`racer_tech`/
`anniversary_mosaic`).

Section 4 (strict TDD): 8 genuinely failing RED tests
(`home_expectation_tdd_red.txt`) before any implementation, committed
separately (`6aeb56c9`).

Section 5 (implementation, `qa_storefront_builder_r4.py` only): added
`Command._canonical_home_contract(store)`, reusing the exact same
public render pipeline (`render_service.build_page_render_items` +
`hide_empty_public_sections`) the live storefront itself uses on the
Store's real published Home page, wired into the Base loop's manifest
write, replacing the three raw-recipe-derived values. No hardcoded
Template-key exception; no second hidden-section list. GREEN: 8/8
(`9f0d103e`, `home_expectation_tdd_green.txt`); 130/130 full harness
suite (one pre-existing test needed `_canonical_home_contract` mocked
alongside its other already-mocked Store-mutation steps — a test-only
fix, not a behavior change).

Section 6/7 (Cart investigation): the pilot's `editorial_jewelry` Cart
tablet finding did NOT reproduce in 3/3 fresh repetitions
(`cart_reproduction.md`) — treated as suspected harness flakiness per
the directive's own instruction, not solved, proceeding to
instrumentation rather than declaring it fixed by inaction.

Section 8/9/10 (Cart diagnostics + repair, Case A confirmed): 7
genuinely failing RED tests (`cart_tdd_red.txt`) via real Node
execution of the extracted async helper against a fake Playwright-
shaped page with a scripted DOM timeline — the click-error-swallowing
and fixed-500ms-decision defects proven directly, not by inference.
Repaired `w4cCartRealRemove` to a bounded, condition-based wait with
full diagnostics (`click_error`, `htmx_request_observed`,
`http_status`, `dom_swap_observed`, `after_at_500ms`, `after_eventual`,
`elapsed_ms`); the success criterion remains exactly `after < before`
on the same canonical `.citem .rm` control. GREEN: 7/7 (`48fb3171` RED,
`4ff0ab10` GREEN).

Section 13 (code review): 3 real diagnostic-correctness findings
fixed (`elapsed_ms` wrongly nulled on timeout; `http_status`
attributed to the last POST instead of the first; a failed click still
wasting the full bounded wait) — 3 new regression tests added, 10/10
in the diagnostics suite, `b3f2c439`. Two hygiene/style findings left
as-is with documented reasoning (`code_review.md`).

Section 16/17 (bounded closure pilot, `closure_pilot_summary.md`):
Process 1 (the four affected Templates) recorded 52 cells with every
Home cell genuinely PASS, correct canonical `rsec_count`
(`premium_leather`: 3/3) and correct Hero index (all three
ticker-before-Hero Templates: PASS). Process 2 (`editorial_jewelry`)
recorded 13 new cells (65 cumulative), Cart PASS on all 3 viewports
including Tablet `removed: true` with full honest diagnostics. Zero
`RateLimitExceeded`, zero duplicates, zero new accessibility FAIL,
zero unexpected console/page/request errors, SQLite restore PASS for
every process. **Closure pilot: ACCEPTABLE.**

Section 18 (exact-final-source-head full regression,
`full_suite_output.txt`, `full_suite_identity_comparison.md`): 3401
tests (3383 + this round's 18 new) at HEAD `b3f2c439`; identity- and
reason-level comparison against the certified W4B baseline shows 0
new/missing identities and 0 changed historical reasons.

## FINAL STATUS

**READY FOR INDEPENDENT ARCHITECT PILOT-FINDINGS CLOSURE REVIEW**

STOP.

Do not run the final 704-cell campaign.
Do not merge.
Do not start W5.

Return for Independent Architect review.
