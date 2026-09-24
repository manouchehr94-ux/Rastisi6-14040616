# RASTISI PHASE 5 — P5-W4C Rate-Limit-Aware Campaign Sharding Repair — Final Report

## P5-W4C RATE-LIMIT-AWARE SHARDING REPAIR: **COMPLETE**

STARTING HEAD: `f7038cff8fa6e8c12c48fc68ada8a3aab79cb863`
FINAL SOURCE HEAD: `5807847b3606ed36836e9f06ba2530c7c513b1a5`
FINAL BRANCH HEAD (this report's commit's parent): `b2108697`
OFFICIAL BASE: `3a4fe9070584655548bae5a9bb574f3415bbf580`
OFFICIAL UNCHANGED: YES

CACHE BACKEND: `django.core.cache.backends.locmem.LocMemCache` (process-local, confirmed at runtime)
NEW_DRAFT LIMIT: 30 / 3600
PUBLISH LIMIT: 20 / 3600

PRODUCTION RATE LIMIT FILES MODIFIED: NO
QA ACCOUNT BYPASS ADDED: NO
RATE-LIMIT CACHE MANUALLY CLEARED: NO (production runtime — the repository's real cache was never touched; `cache.clear()` appears only inside one test, to correctly simulate a second real `manage.py` process's independent LocMemCache)

--w4c-tier2-budget: IMPLEMENTED
TIER2 BUDGET 0: PASS (unit test + real pilot Process 1, 0 Tier-2 cells recorded)
TIER2 BUDGET 4: PASS (unit test + real pilot Process 2, exactly 4 new Tier-2 cells)

EXPECTED TOTAL CELLS STILL: 704
EXPECTED NODE INVOCATIONS STILL: 154

CONTROLLED RateLimitExceeded DIAGNOSTIC: PASS (unit test: raw exception never escapes, becomes one informative `CommandError`; the key whose apply raised is never merged into the matrix, matrix preserved exactly up to the last successful terminal cell)

FOCUSED W4C TESTS: 122/122 (full harness suite; 111 pre-existing + 11 new sharding tests, `tdd_green.txt`)

PILOT PROCESS 1: 52 cells / 8 Node invocations / matches exactly (4 keys × 12 Base + 4 Tier-1, 0 Tier-2 since budget=0)
PILOT PROCESS 1 RATE LIMIT: NONE
PILOT PROCESS 1 SQLITE RESTORE: PASS

PILOT PROCESS 2: 4 new Tier-2 cells / 4 new Node invocations / matches exactly
PILOT CUMULATIVE CELLS: 56 / matches exactly (52 + 4)
PILOT DUPLICATES: 0
PILOT RATE LIMIT: NONE
PILOT SQLITE RESTORE: PASS

FULL SUITE EXACT SOURCE HEAD: `5807847b3606ed36836e9f06ba2530c7c513b1a5`
NEW W4C-ONLY FAILURE/ERROR IDENTITIES: 0
CHANGED HISTORICAL FAILURE REASONS: 0

ATTEMPT-1 ROOT PRESERVED: YES (`/tmp/rastisi_w4c_campaign_bedcb3b0`, never deleted or reused)
ATTEMPT-1 MATRIX UNCHANGED: YES (sha256 verified byte-identical to the copy committed in `38_full_campaign_attempt1_blocked/matrix_partial.json`)

FINAL 704-CELL CAMPAIGN RUN: NO
W5 STARTED: NO
MERGED: NO
FINAL WORKTREE CLEAN: YES

## Summary

Section 1 (full root cause) confirmed exactly, item by item, in
`root_cause_extension.md`: the `new_draft` (30/3600) and `publish`
(20/3600) limits are both real and independently exhaustible by an
all-in-one campaign; Theme cells can cost up to 3 `publish` + 4
`new_draft` calls each, making an all-in-one 104-Theme-cell process
structurally incompatible with either budget; the cache backend is
confirmed `LocMemCache` (process-local), which is what makes process
sharding — rather than in-process pacing or raising the real limits —
the correct fix.

Section 3 (strict TDD): 11 genuinely failing RED tests
(`tdd_red.txt`) for `--w4c-tier2-budget`'s semantics (budget 0/4/omitted,
already-terminal cells free, resumability, 704-total/Tier-1
non-interference, CLI validation) plus 1 for the controlled
`RateLimitExceeded` diagnostic, committed separately (`059c1065`)
before any implementation.

Section 4/5 (implementation, `apps/storefront_builder/management/
commands/qa_storefront_builder_r4.py` only): added
`--w4c-tier2-budget <N>`, its `Command._validate_w4c_tier2_budget`
validator (integer ≥0, requires `--w4c-all50`, `None` preserves the
pre-repair unbounded behavior), threaded a `tier2_budget` parameter
into `_run_w4c_campaign`'s Tier-2 loop (already-terminal cells
detected via the existing `_run_one_theme_cell` return value never
consume budget), and wrapped the campaign body in a `try/except
RateLimitExceeded` that raises one controlled `CommandError` (selected
keys, cells recorded this invocation, campaign root, safe-resume
guidance) — never a raw traceback, never a cell silently marked PASS,
never a continued iteration after the exhaustion. GREEN: 122/122
(`5807847b`, `tdd_green.txt`). One test (`test_4`) needed a
`cache.clear()` between its two simulated invocations to correctly
model two real, separate `manage.py` processes each with their own
process-local `LocMemCache` — a test-only fix, not an implementation
change, documented in the GREEN commit message.

Section 7 (mutation budget proof, `mutation_budget_proof.md`): derived
from the real call graph, Batch A (4 Base+Tier1 keys, budget 0) costs
24 `new_draft` / 16 `publish` — under 30/20 with exactly the margin the
directive expected (5 keys would land exactly at 30/20, explaining why
4, not 5, is the approved batch size). Batch B (1 key, 4 Tier-2 cells)
costs 13 `new_draft` / 12 `publish` — comfortably under both.

Section 10 (bounded two-process pilot, `pilot_summary.md`,
`pilot_process1_output.txt`, `pilot_process2_output.txt`,
`pilot_matrix.json`): both processes matched their expected outcomes
exactly, with zero `RateLimitExceeded`, zero duplicates, and correct
resumability. The pilot also surfaced two genuine, pre-existing browser
findings unrelated to rate limiting (a `premium_leather` Home
rsec-count mismatch and an `editorial_jewelry` Cart tablet-only remove
failure) — recorded honestly, explicitly out of scope for this round,
not fixed here.

Section 11 (exact-final-source-head full regression,
`full_suite_output.txt`, `full_suite_identity_comparison.md`): 3383
tests (3371 + this round's 12 new tests) at HEAD `5807847b`; identity-
and reason-level comparison against the certified W4B baseline shows 0
new/missing identities and 0 changed historical reasons.

## FINAL STATUS

**READY FOR INDEPENDENT ARCHITECT RATE-LIMIT SHARDING REVIEW**

STOP.

Do not run the final 704-cell campaign.
Do not merge.
Do not start W5.

Return for Independent Architect review.
