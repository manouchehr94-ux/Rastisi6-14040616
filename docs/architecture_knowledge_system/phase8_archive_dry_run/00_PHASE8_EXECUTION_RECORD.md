# Phase 8 — Documentation Archive Dry Run — Execution Record

> **MODE: DRY RUN ONLY.** This phase produces *analysis and planning* artifacts.
> **No documents were moved, renamed, deleted, or `git mv`'d.** No archive tree
> was created. No archive banners were inserted. No documentation Disposition
> Recommendations (DR-1…DR-8) were resolved. No production code, tests, or
> migrations were touched. No merge, rebase, or PR was performed.

## 1. Scope of this record

This document is the audit trail for the Phase 8 dry run: what was analysed,
against which frozen baseline, on which branch, and what the planning artifacts
under `phase8_archive_dry_run/` collectively assert.

## 2. Repository state at execution

| Item | Value |
| --- | --- |
| Repository | `manouchehr94-ux/Rastisi6-14040616` |
| Working branch | `docs/architecture-knowledge-system` |
| Accepted HEAD | `95bfd5c2a62b40a8b733db9e4bc9ee60f2161f64` (canonical-consistency repair) |
| Production baseline (frozen) | `5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb` |
| Baseline delta audit | **Not required** — prod branch confirmed still at the baseline SHA |

### 2.1 Baseline safety check (runtime surfaces unchanged)

```
git diff --stat 5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb HEAD -- apps/ shop_core/ templates/ static/
# → (empty)  : no runtime code/template/static changes between baseline and HEAD
```

The empty diff confirms the accepted HEAD differs from the production baseline
**only** in documentation and tooling under `docs/architecture_knowledge_system/**`
and `tools/docs/**`. Phase 8 therefore reasons about a documentation corpus that
sits on top of a frozen, unchanged runtime.

## 3. Inputs consumed

| Input | Purpose |
| --- | --- |
| `phase3_document_inventory/02_DOCUMENT_INVENTORY.csv` (519 rows) | Authoritative document scope + per-doc classification |
| `phase3_document_inventory/03_DOCUMENT_CLASSIFICATION.md` | Classification semantics |
| `phase4_reconciliation/09_CANONICAL_DOCUMENT_CANDIDATES.md` | Which docs anchor current architecture |
| `phase4_reconciliation/10_ARCHIVE_CANDIDATES.md` | Phase-4 archive candidate groups A–E |
| Canonical layer (`canonical/**`, 15 domain packs) reference scan | Which docs the canonical pack depends on |
| Code / template / script reference scan | Which docs are cited by runtime-adjacent files |

## 4. Method (summary)

1. Took the Phase-3 inventory (519 rows: 513 textual docs + 6 asset collections)
   as the **immutable scope**. Every row receives exactly one disposition.
2. Applied **protection rules first** (Section in `02_RETENTION_AND_PROTECTION_RULES.md`):
   the AKS tree, the eight protected canonical source docs, and third-party /
   legal notices are removed from archive eligibility before any candidate rule runs.
3. Applied the **Phase-4 archive groups** (A–E) to the remaining docs.
4. Applied **reference back-pressure**: any doc referenced by a canonical/domain
   AKS doc *or* by code/templates/scripts is downgraded from `ARCHIVE_CANDIDATE`
   to `KEEP_HISTORICAL_REFERENCE` (never auto-moved) so no live link can break.
5. Applied **conservative PRESERVE defaults** to everything unclassified.
6. Reconciled the six disposition totals back to exactly 519 (Section 6).

## 5. Produced artifacts (this directory)

| File | Contents |
| --- | --- |
| `00_PHASE8_EXECUTION_RECORD.md` | This record |
| `01_ARCHIVE_POLICY.md` | Archive philosophy, disposition vocabulary, decision order |
| `02_RETENTION_AND_PROTECTION_RULES.md` | Protected sets + retention rules |
| `03_ARCHIVE_DISPOSITION_MANIFEST.csv` | Per-document + per-collection dispositions (519 rows) |
| `04_PROPOSED_ARCHIVE_TREE.md` | Chosen archive layout + justification |
| `05_LINK_AND_REFERENCE_IMPACT.md` | Link/reference impact buckets |
| `06_CANONICAL_DEPENDENCY_CHECK.md` | Canonical-pack dependency guard |
| `07_HIGH_RISK_OR_AMBIGUOUS_MOVES.md` | High-risk / ambiguous docs, held back |
| `08_CORRECT_IN_PLACE_QUEUE.md` | Docs to fix in place later (incl. `docs/README.md`) |
| `09_DEFERRED_DOCUMENTS.md` | Docs deferred to human review |
| `10_ARCHIVE_EXECUTION_PLAN.md` | Batched `git mv` execution plan (for a LATER phase) |
| `11_PHASE8_MASTER_DRY_RUN_REPORT.md` | Safety arithmetic + READY / NOT READY verdict |

## 6. Disposition reconciliation (headline)

| Disposition | Count |
| --- | --- |
| `KEEP_CANONICAL_SUPPORT` | 20 |
| `KEEP_HISTORICAL_REFERENCE` | 33 |
| `CORRECT_IN_PLACE_LATER` | 2 |
| `ARCHIVE_CANDIDATE` | 417 |
| `DEFER_REVIEW` | 44 |
| `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` | 3 |
| **Total** | **519** |

> **`[PHASE 8 CORRECTIVE REVIEW]`** The headline totals in this section reflect the
> original dry run (scope 519). They are **superseded** by the corrective pass:
> scope is now **522** logical records (519 inventory + 2 supplemental root docs +
> 1 collection-member), with `ARCHIVE_CANDIDATE` = 406 logical units expanding to
> **3065 exact git-tracked files**. See `15_PHASE8_CORRECTIVE_SAFETY_REPORT.md` and
> the corrective addendum in `11_...`.

20 + 33 + 2 + 417 + 44 + 3 = **519** — exactly the Phase-3 inventory scope, with
no unexplained remainder.

## 7. What this phase explicitly did NOT do

- Did **not** move, rename, copy, or delete any document.
- Did **not** run `git mv` or create `docs/archive/`.
- Did **not** insert archive banners into any document.
- Did **not** modify `docs/README.md` or any doc marked `CORRECT_IN_PLACE_LATER`.
- Did **not** resolve DR-1…DR-8.
- Did **not** modify production code, tests, or migrations.
- Did **not** merge, rebase, or open a pull request.

## 8. Next step (NOT part of this phase)

The batched execution plan in `10_ARCHIVE_EXECUTION_PLAN.md` is written for a
**future, separately-approved** phase. Even if `11_...` returns **READY**, no
execution occurs in Phase 8.
