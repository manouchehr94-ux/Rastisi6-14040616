# P5-W5A — Canonical Editor Safety / Architecture Closure — Final Report

**This report supersedes the round-1 version of this document.** Round-1
content is preserved elsewhere in this evidence directory (`tdd_red.txt`,
`tdd_green.txt`, and the round-1 sections still present in
`code_review.md`/`concurrency_contract.md`/`route_classification.md`/
`source_diff.md`/`full_suite_identity_comparison.md`) — nothing was erased,
only corrected and extended.

## Round-2 changelog (Independent Architect PR review repair)

The Independent Architect reviewed PR #13 and found **CRITICAL 0, IMPORTANT
2, BLOCKING MINOR 1**:

1. **`storefront_section_collapse_toggle` misclassified as a justified
   Class-A exclusion** — it is a real persisted Draft mutation
   (`collapsed_in_editor` is in `edit_history_service._SECTION_FIELDS`,
   the view is `@_record_edit_history`-decorated), not a cosmetic no-op.
   **Fixed**: now guarded like every other Class-A route.
2. **Class-C precondition was revision-only — an ABA hazard**:
   `edit_revision` defaults to 0 on every new Draft row, so a stale
   client could pass the precondition check against an unrelated Draft
   that replaced the one it actually observed, as long as the replacement
   also happened to be at revision 0. **Fixed**: the precondition now
   binds to BOTH the expected Draft identity (its PK) and its revision.
3. **`RateLimitExceeded` from the existing rate limits escaped as an
   unhandled 500** on both new R4 Class-C JSON endpoints. **Fixed**:
   translated to a controlled `429`, no limit loosened, no new limiter.

All three fixed, verified via genuine RED-then-GREEN (production code
temporarily reverted, new/updated tests observed failing, then restored
and reverified green — `round2_tdd_red.txt`/`round2_tdd_green.txt`), a
full re-audit of every mutating `views.py` route (no further
misclassification found), a real second-Store browser QA scenario for the
R3-pinned rollback editor (previously only Django-test-verified, which the
Architect ruled insufficient), and a clean exact-source full-suite
regression showing 0 new/missing/changed failure identities. Full detail
in each evidence file's own round-2 section.

## Provenance

- Approved Master Plan base SHA: `e88ebac0dc333251e7be0d98f5c0d9fb6cad4efe`
  (`docs(phase5): finalize W5 discovery master plan`, on
  `feature/phase5-design-expansion`).
- W5A implementation branch: `feature/phase5-w5a-canonical-editor-safety`.
- **Final HEAD: `128afd19`** (round 1 concluded at `23660370`).
- Commits (chronological): `19f7b498` (plan) → `9114f2f1` (RED tests) →
  `a4108a15` (implementation) → `f610aa55` (round-1 code-review fixes) →
  `592baa7c` (round-1 evidence) → `bf39b8fb` (fix: legacy-route test
  regressions) → `6019a82e` (fix: correct 3 mis-applied pins) →
  `23660370` (round-1 final report/PR opened as #13) → `0edc258c` (fix:
  Independent-Review repair — collapse-toggle, ABA, rate-limit) →
  `b978ff61` (round-2 evidence) → `128afd19` (fix: 2 more test pins
  surfaced by the round-2 fixes).

## Class A / B / C implementation (final)

- **Class A** — **31 routes, all 31 guarded, 0 exclusions** (round-2
  correction: `storefront_section_collapse_toggle` moved from "justified
  exclusion" into the guarded table). Guarded by the same single shared
  decorator, `_require_legacy_editor_active`, applied to an explicit
  route list — never module-wide.
- **Class B** (Ready Template Gallery/Apply, Draft Preview, History
  browser, media) — verified never blocked. Round-2 re-audit confirmed
  `storefront_apply_layout_preset` and the 6 `media_views.py` routes are
  genuinely shared infrastructure (R4's own editor renders `hx-get`/
  `hx-post` calls to the same media routes; no parallel R4-native media
  mutation path exists) — not further collapse-toggle-style mistakes.
- **Class C** (Restore Version, Apply Industry Layout) — converged onto
  two R4-safe endpoints delegating to the existing, unmodified
  `layout_service.restore_version()`/`apply_industry_layout()`. Round-2:
  the precondition contract corrected to bind to Draft identity + revision
  (see `concurrency_contract.md`).

## Concurrency contract (final)

`_lock_layout_for_identity_replacement` takes the row lock
(`select_for_update`) and validates the caller's `(base_draft_id,
base_revision)` expectation — including the no-active-Draft precondition
(`null`/`null`) — inside the same `@transaction.atomic` boundary as the
subsequent `layout_service` call: no TOCTOU gap. Round-2: identity is
checked before revision, closing the ABA hazard; a mismatch on either
raises `R4StaleRevision` with both `current_revision` and
`current_draft_id`. Full wire contract in `concurrency_contract.md`,
exercised by 25 tests across `R4SafeRestoreTests` (11),
`R4SafeIndustryApplyTests` (14), and `ClassCConcurrencyBoundaryTests` (2).

## Class-A route audit (final)

`route_classification.md`: **0 unclassified mutating routes, 0 Class-A
routes writable under R4, 0 Class-B routes blocked, 0 unsafe Class-C
legacy writes reachable under R4, 0 Class-A exclusions** (round-2:
collapse-toggle reclassified; down from round 1's "1 justified
exclusion").

## Restore / Industry Apply convergence

Unchanged from round 1: both new endpoints delegate to the pre-existing
unmodified `layout_service` functions. History remains readable; its
Restore control posts to the R4-safe endpoint under R4 (now carrying
`base_draft_id` too). Rollback preserved for R3-pinned Stores — proven
both by the Django suite and, new this round, by a real browser session.

## Style Pack terminology / Reserved family disposition

Unchanged from round 1, unaffected by the round-2 repair — see round-1
detail preserved in `route_classification.md`/the W5A test suite
(`StylePackTerminologyTests`, `ReservedFamilyDispositionTests`).

## Focused test result (final)

- W5A module: **60/60 pass** (50 round-1 + 10 round-2 regression tests:
  3 for collapse-toggle, 4 for the ABA hazard + precondition-shape
  rejection split across Restore/Industry-Apply, 2 for rate-limit
  translation, plus round-1's existing coverage extended with
  `current_draft_id` assertions).
- Broader focused regression (22 modules including R4 mutation service,
  R4 routes/views, legacy disposition/convergence, history/restore,
  industry layout, Ready Template Gallery/Apply, tenant isolation,
  stale-write behavior, R4 editor, `test_layout_service`,
  `test_media_views` — 1047 tests): **0 new failures vs. baseline** on
  the final re-run (an intermediate run surfaced 2 regressions from the
  round-2 fixes themselves, both fixed in commit `128afd19` — see
  `full_suite_identity_comparison.md`).

## Browser QA result (final)

**14/14 PASS** across all 10 required scenarios plus the round-2 addition
(`browser_qa.md`, `browser_qa_raw_output.txt`) — including, new this
round, a **real** R3-pinned rollback-editor scenario (a second Store
fixture, a second real login on its own admin host, a real legacy
Class-A POST, and direct database verification that `is_active` actually
flipped) — the Architect ruled the round-1 Django-test-only verification
of this scenario insufficient, and it is not re-used as evidence here.
W4C's 704-cell campaign was **not** rerun (no renderer/Template output
touched).

## Exact-source full regression result (final)

`full_suite_identity_comparison.md`, round-2 section: **`Ran 3478 tests
in 2323.931s` — `FAILED (failures=30, errors=2, skipped=1)`**, run clean
(no contending process) at final HEAD `128afd19`.

- **NEW FAILURE/ERROR IDENTITIES: 0**
- **MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0**
- **CHANGED HISTORICAL FAILURE/ERROR REASONS: 0** (32/32 identities
  byte-identical to baseline by name; 27/32 bodies byte-identical, 5/32
  differ only in incidental embedded random HTML content with identical
  file/line/exception-type/assertion-message — reconfirmed against
  round-1's own final run too).
- Test count: 3418 (baseline) → 3478 (final), +60 — exactly the W5A
  suite's final size, all passing.

## Architectural duplication result

**None introduced**, unchanged from round 1: no second Draft model,
renderer, Ready Template registry, history system, mutation dispatcher,
restore implementation, industry-layout implementation, tenant resolver,
stale-write contract, or R3/R4 editor-state flag. The round-2 ABA fix
reuses the existing Draft PK as identity — no new concurrency token or
model. `RateLimitExceeded` translation reuses the existing, unmodified
rate limits — no new limiter.

## Code review gate (final)

Round 1: 3 findings, 2 fixed, 1 correctly left unactioned (CRITICAL 0,
IMPORTANT 0 at round-1 close). Round 2 (Independent Architect PR review):
CRITICAL 0, IMPORTANT 2, BLOCKING MINOR 1 — all three fixed and verified
this round. **Final: CRITICAL 0, IMPORTANT 0, BLOCKING MINOR 0.**
Test-modification re-review (§11 of the repair directive) completed: `git
diff` against the pre-W5A base across all 18 pinned test files shows 581
insertions / 5 deletions, the 5 being one deliberately strengthened
assertion — no assertion was weakened anywhere to force green.

## Forbidden-scope check

Unchanged: no change to Ready Template recipes, the 50-template registry
membership, the public renderer, section renderer, Theme architecture,
Cart, Product Card renderer, Bottom Navigation (W5B), Design Lab mutation
semantics, Store Appearance persisted contract, or database
schema/migrations. `manage.py makemigrations --check --dry-run` → "No
changes detected" at final HEAD.

## Final architecture self-audit (repair directive §29-equivalent)

| Question | Answer |
|---|---|
| A second mutation dispatcher introduced? | No — round-2 orchestration stays inside `r4_mutation_service`. |
| Restore/Industry-Apply business logic duplicated? | No — both wrappers still delegate to the unmodified `layout_service` functions. |
| A second stale-write/optimistic-concurrency system introduced? | No — the ABA fix extends the existing `_lock_layout_for_identity_replacement`/`R4StaleRevision` machinery (adding `current_draft_id`, backward-compatible), reusing the existing Draft PK as identity; no new token/model. |
| A broad, module-level Class-A guard used? | No — `_require_legacy_editor_active` remains on an explicit, enumerated route list; round-2 added exactly one route (`storefront_section_collapse_toggle`) to that list, removed the one prior exclusion, added none broader. |
| Any Class-B route blocked? | No — re-audited and reconfirmed for `storefront_apply_layout_preset` and all 6 `media_views.py` routes this round specifically. |
| Can an R3 (legacy) request mutate an R4-enabled Store via a Class-A route? | No — including, now, `storefront_section_collapse_toggle`. |
| Can legacy Restore/Industry-Apply mutate outside the canonical path under R4? | No — unchanged from round 1. |
| Does R3-pinned rollback still work? | Yes — now proven in a real browser session too, not only the Django test suite. |
| Is History still readable under R4? | Yes — unchanged. |
| Is Ready Template vs. Style Pack terminology unambiguous? | Yes — unchanged. |
| Do `layout`/`mega_menu` remain reserved without new authority? | Yes — unchanged. |
| A new concurrency token/model introduced for the ABA fix? | No — the existing Draft PK is reused as identity. |
| Was the existing rate limit loosened, or a second limiter created? | No — the existing `storefront_layout.restore`/`storefront_layout.new_draft` limits are unchanged; only the HTTP-layer translation of `RateLimitExceeded` is new. |

All answers are consistent with the approved Master Plan and the
Independent Architect's repair directive. No deviation, no silent
redesign of the Class A/B/C classification or the single-active-write
policy.

---

**STOP. Do not merge the PR. Do not start W5B. Return for Independent
Architect re-review.**
