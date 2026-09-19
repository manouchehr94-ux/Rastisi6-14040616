# P5-W5A — Canonical Editor Safety / Architecture Closure — Final Report

## Provenance

- Approved Master Plan base SHA: `e88ebac0dc333251e7be0d98f5c0d9fb6cad4efe`
  (`docs(phase5): finalize W5 discovery master plan`, on
  `feature/phase5-design-expansion`).
- W5A implementation branch: `feature/phase5-w5a-canonical-editor-safety`,
  created from exactly that commit (pre-flight safety gate verified before
  branch creation: local HEAD == remote HEAD == base SHA, clean worktree).
- Final HEAD: `6019a82e74fb09989b40f1d3828f74f45a70937d`.
- Commits (chronological): `19f7b498` (plan) → `9114f2f1` (RED tests) →
  `a4108a15` (implementation) → `f610aa55` (code-review fixes) →
  `592baa7c` (evidence docs) → `bf39b8fb` (fix: legacy-route test
  regressions from the new guard) → `6019a82e` (fix: correct three
  mis-applied pins in that prior fix, found by an uncontended exact-source
  re-run).

## Class A / B / C implementation

- **Class A** (31 routes inventoried; 30 guarded + 1 justified exclusion —
  `storefront_section_collapse_toggle`, a cosmetic-only write, per the
  master plan's own CANONICAL KEEP disposition): guarded by one new,
  shared decorator, `_require_legacy_editor_active`
  (`apps/storefront_builder/views.py`), applied to an explicit route list
  — never a module-wide guard. Fails closed (`Http404`) when
  `r4_editor_enabled=True`; fully functional when `False`.
- **Class B** (Ready Template Gallery/Apply, Draft Preview, History
  browser, media): verified never blocked — no guard applied, proven by
  dedicated tests (`ClassBSharedCapabilitiesRemainReachableTests`,
  `HistoryBrowserReadOnlyUnderR4Tests`) and the route-classification audit.
- **Class C** (Restore Version, Apply Industry Layout): converged onto two
  new R4-safe endpoints (`storefront-builder-r4-restore`,
  `storefront-builder-r4-apply-industry-layout` in
  `apps/storefront_builder/r4_views.py`), which delegate to new
  `r4_mutation_service.restore_version_safe` /
  `apply_industry_layout_safe` wrappers. Both wrappers call the existing,
  **byte-for-byte unmodified** `layout_service.restore_version()` /
  `apply_industry_layout()` — no duplicated business logic. The legacy
  `storefront_restore` / `storefront_apply_industry_layout` routes are now
  also guarded by `_require_legacy_editor_active` (fail closed under R4),
  remaining the rollback path for `r4_editor_enabled=False` Stores only.

## Concurrency contract

`_lock_layout_for_identity_replacement` (new, in `r4_mutation_service.py`,
distinct from the existing `_lock_active_draft`) takes the row lock
(`select_for_update`) and validates the caller's `base_revision`
expectation — including the **no-active-Draft** precondition (client
expects no Draft; `base_revision=None`) — inside the same
`@transaction.atomic` boundary as the subsequent
`layout_service.restore_version()` / `apply_industry_layout()` call, so
there is no TOCTOU gap between the staleness check and the Draft-identity
replacement. Full wire contract documented in `concurrency_contract.md`
and exercised by `ClassCConcurrencyBoundaryTests`,
`R4SafeRestoreTests`, `R4SafeIndustryApplyTests` (14 tests covering both
the "Draft exists" and "no Draft exists" preconditions and their stale
variants).

## Class-A route audit

`route_classification.md` re-audits the full legacy route table
post-implementation: **0 unclassified mutating routes, 0 Class-A routes
writable under R4, 0 Class-B routes blocked, 0 unsafe Class-C legacy
writes reachable under R4.**

## Restore convergence

`storefront-builder-r4-restore` → `restore_version_safe` →
`layout_service.restore_version()` (unmodified). Legacy `storefront_restore`
guarded; R3-pinned Stores retain it via `R3PinnedClassCRollbackPreservedTests`.
History browsing remains available under R4
(`HistoryBrowserReadOnlyUnderR4Tests`); its Restore button now posts to
the R4-safe endpoint when `r4_editor_enabled=True` (verified in-browser).

## Industry Apply convergence

`storefront-builder-r4-apply-industry-layout` → `apply_industry_layout_safe`
→ `layout_service.apply_industry_layout()` (unmodified). Same guard/legacy
pattern as Restore. Verified in-browser including the real `confirm()`
gate when a Store already has a published version.

## Rollback preservation

R3-pinned Stores (`r4_editor_enabled=False`) retain full, unmodified
access to every legacy route — proven by
`ClassARollbackStillWorksTests`, `R3PinnedClassCRollbackPreservedTests`,
and in-browser scenario 3.

## Style Pack terminology

Only the merchant-facing label of the 10-item `appearance_registry`
style-token selector in `r4/editor.html` was renamed to "بستهٔ سبک" (Style
Pack). `template_slug` / `TEMPLATE_REGISTRY` / `TemplateDefinition` /
persisted fields are untouched; the separate 50-item Ready Template
switcher still says "قالبِ آماده" (Ready Template) — verified by
`StylePackTerminologyTests` (both assertions) and in-browser scenario 9.

## Reserved family disposition

`layout` (RESERVED/INERT) and `mega_menu` (RESERVED/COMPATIBILITY) are
unchanged — no new renderers, no new merchant selectors, no new registry
variants; Design Lab's randomizable-families list still excludes both —
verified by `ReservedFamilyDispositionTests` (3 tests).

## Focused test result

- W5A module: **50/50 pass** (`tdd_green.txt`, re-confirmed at final HEAD:
  `Ran 50 tests in 31.763s — OK`).
- Broader focused regression (R4 mutation service, R4 routes/views, legacy
  disposition/convergence, history/restore, industry layout, Ready
  Template Gallery/Apply, tenant isolation, stale-write behavior, R4
  editor — 20 modules, 943 tests): **0 new failures vs. baseline**
  (`sanity_sweep_v2.txt`; the 10 failures present are all pre-existing
  historical identities).

## Browser QA result

12/12 PASS across all 10 required scenarios (`browser_qa.md`,
`browser_qa_raw_output.txt`), via a workstream-scoped Playwright script
reusing the existing `tools/storefront_builder_r4_qa/` harness
conventions — no second harness. W4C's 704-cell campaign was **not**
rerun (not required; no renderer/Template output was touched).

## Exact-source full regression result

`full_suite_identity_comparison.md`: **`Ran 3468 tests in 2502.003s` —
`FAILED (failures=30, errors=2, skipped=1)`**, run clean (no contending
process) at final HEAD `6019a82e`.

- **NEW FAILURE/ERROR IDENTITIES: 0**
- **MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0**
- **CHANGED HISTORICAL FAILURE/ERROR REASONS: 0** (32/32 identities
  byte-identical to baseline by name; 27/32 bodies byte-identical, 5/32
  differ only in incidental embedded random HTML content with identical
  file/line/exception-type/assertion-message — not a changed reason).
- Test count: 3418 → 3468 (+50, exactly the new W5A tests, all passing).

An intermediate contaminated run (concurrent SQLite test-database access
from an unrelated process) surfaced 25 spurious identities; it was
discarded and not used as evidence. Investigating it found two real bugs
in the interim `bf39b8fb` fix, corrected in `6019a82e`, and reverified by
two further clean full-suite runs — the second (this one) is the evidence
of record.

## Architectural duplication result

**None introduced.** No second Draft model, renderer, Ready Template
registry, history system, mutation dispatcher, restore implementation,
industry-layout implementation, tenant resolver, stale-write contract, or
R3/R4 editor-state flag. Every new Class-C code path is a thin
transaction/validation wrapper delegating to the pre-existing,
byte-for-byte unmodified `layout_service.restore_version()` /
`apply_industry_layout()`.

## Code review gate

Independent code-review pass (`code_review.md`) found 3 findings: 2 real
bugs fixed (a `force` truthy-string coercion bug — `bool("false")` is
`True` in Python — and an unanchored CSRF-token regex in two templates),
1 investigated and correctly left unactioned (a pre-existing, out-of-scope
Class-B gap in Ready Template Apply's stale-write handling, verified via
direct source comparison to be a factually incorrect finding). Final
state: **CRITICAL 0, IMPORTANT 0** open.

## Forbidden-scope check

No change to Ready Template recipes, the 50-template registry membership,
the public renderer, section renderer, Theme architecture, Cart, Product
Card renderer, Bottom Navigation (W5B), Design Lab mutation semantics,
Store Appearance persisted contract, or database schema/migrations.
`manage.py makemigrations --check --dry-run` → "No changes detected" at
final HEAD.

## Final architecture self-audit (§29)

| Question | Answer |
|---|---|
| A second mutation dispatcher introduced? | No — all new Class-C orchestration lives in `r4_mutation_service`, alongside the existing `_lock_active_draft`-based actions. |
| Restore/Industry-Apply business logic duplicated? | No — both new service wrappers delegate to the existing, unmodified `layout_service` functions. |
| A second stale-write/optimistic-concurrency system introduced? | No — `_lock_layout_for_identity_replacement` reuses the same `edit_revision` token, `R4StaleRevision`/`R4MutationError` exception types, and `@transaction.atomic` + `select_for_update` pattern as every existing R4 mutation. |
| A broad, module-level Class-A guard used? | No — `_require_legacy_editor_active` is applied to an explicit, enumerated route list (see `route_classification.md`); one route (`storefront_section_collapse_toggle`) is explicitly, source-justified excluded. |
| Any Class-B route blocked? | No — verified by `ClassBSharedCapabilitiesRemainReachableTests`, `HistoryBrowserReadOnlyUnderR4Tests`, and in-browser scenario 9. |
| Can an R3 (legacy) request mutate an R4-enabled Store via a Class-A route? | No — every Class-A route now 404s under `r4_editor_enabled=True`; proven by `ClassARedundantRoutesFailClosedTests` and in-browser scenario 2. |
| Can legacy Restore/Industry-Apply mutate outside the canonical path under R4? | No — both are now guarded Class-A/C-adjacent routes, fail closed under R4; only the new R4-safe endpoints (which delegate to the same canonical `layout_service` functions) work under R4. |
| Does R3-pinned rollback still work? | Yes — unmodified, proven by `ClassARollbackStillWorksTests`, `R3PinnedClassCRollbackPreservedTests`, and in-browser scenario 3. |
| Is History still readable under R4? | Yes — `HistoryBrowserReadOnlyUnderR4Tests` and in-browser scenario 4. |
| Is Ready Template vs. Style Pack terminology unambiguous? | Yes — `StylePackTerminologyTests` asserts both the renamed label and the untouched Ready Template label in the same run. |
| Do `layout`/`mega_menu` remain reserved without new authority? | Yes — `ReservedFamilyDispositionTests` (3 tests); only non-behavioral disposition comments were added to `families.py`. |

All answers are consistent with the approved Master Plan. No deviation,
no silent redesign of the Class A/B/C classification or the
single-active-write policy.

---

**STOP. Do not merge the PR. Do not start W5B. Return for Independent
Architect review.**
