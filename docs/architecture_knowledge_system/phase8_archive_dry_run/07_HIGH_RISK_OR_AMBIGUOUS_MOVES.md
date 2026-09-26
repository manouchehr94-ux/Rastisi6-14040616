# Phase 8 — High-Risk or Ambiguous Moves

> **DRY RUN ONLY.** These items are explicitly **held back** from the archive
> candidate set. Nothing here is moved. This document exists so a human reviewer
> can see exactly what was *not* archived and why.

## 1. High-risk criteria (user-defined)

A document is treated as high-risk / ambiguous — and therefore **not** an
`ARCHIVE_CANDIDATE` — if any of the following hold:

1. Referenced by production code, tests, or config.
2. It is an operational runbook / current deploy or security procedure.
3. It is legal / third-party material.
4. It is the only surviving explanation of an **OPEN** Disposition
   Recommendation (DR-1…DR-8).
5. The canonical pack relies on it for design intent.
6. It is a plan/spec whose completion state cannot be verified in a dry run.

The disposition engine enforces these by routing such docs to
`KEEP_CANONICAL_SUPPORT`, `KEEP_HISTORICAL_REFERENCE`, or `DEFER_REVIEW`.

## 2. Held: referenced by code / templates / scripts (11)

Criterion 1. Held as `KEEP_HISTORICAL_REFERENCE`,
`special_handling = CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY`. Moving these
would require editing code that cites them — out of scope and forbidden.

- `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_1A_REPORT.md`
- `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_7_REPORT.md`
- `docs/reports/PRODUCT_ENTRY_FULL_PAGE_ROOT_CAUSE.md`
- `docs/reports/PRODUCT_ENTRY_FINAL_FUNCTIONAL_REPAIR_AUDIT.md`
- `docs/qa_evidence/storefront_appearance_convergence/phase1/task6_explicit_local_variant.md`
- `docs/qa_evidence/storefront_appearance_convergence/phase2/lifecycle_media_inventory.md`
- `docs/qa_evidence/storefront_appearance_convergence/phase4/pre_task10_r4_cutover.md`
- `docs/qa_evidence/storefront_appearance_convergence/phase4/task9_legacy_retirement.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/00_certified_w4a_fingerprints.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/w4b_curation_inventory.md`
- `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/implementation/23_repair_round2_smoke_evidence.md`

## 3. Held: relied on by the canonical pack for design intent (9)

Criteria 4 & 5. Held as `KEEP_HISTORICAL_REFERENCE`,
`special_handling = REFERENCED_BY_CANONICAL`.

- `docs/reports/PRELAUNCH_PHASE2_SUBSCRIPTIONS_TRIALS.md` — subscriptions/trials design intent (DR-linked billing area)
- `docs/reports/PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md` — platform billing design intent
- `docs/reports/PRELAUNCH_PHASE4_ZIBAL_MERCHANT_PAYMENTS.md` — merchant payments design intent
- `docs/reports/PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` — cross-cutting prelaunch audit
- `docs/docs/product/reports/ADMIN_PANEL_COMPLETION_REPORT.md` — merchant-admin design intent
- `docs/docs/product/reports/PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md` — catalog/product mgmt design intent
- `docs/prototypes/README.md` — prototypes index cited by canonical
- `docs/references/beraito-exact-frontend-v5/README.md` — reference-set index cited by canonical
- `docs/qa_evidence/storefront_design_engine/phase5/w4_certification/failures/README.md` — certification failures index cited by canonical

## 4. Held: protected canonical source / operational / legal

- **Tier P1 (8 docs)** — canonical source-of-truth, incl. the operational runbook
  `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` (criterion 2) and the
  storefront V2 spec + legacy retirement map. All `KEEP_CANONICAL_SUPPORT`.
- **Tier P2 (3 docs)** — `docs/third_party/**` notices (criterion 3),
  `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL`.

## 5. Ambiguous: plans/specs deferred (44)

Criterion 6. All `docs/superpowers/**` plans/specs (41) plus 3 non-superpowers
plan/roadmap docs are `DEFER_REVIEW` — completion vs supersession cannot be proven
in a dry run. Full list in `09_DEFERRED_DOCUMENTS.md`. Two of these superpowers
plans are additionally *cited by code* (golden-reference and appearance-phase1
plans), reinforcing "do not move without review".

## 6. Out-of-scope items observed (not in the inventory)

The two repository-root docs below are **outside** the Phase-3 inventory scope
(`docs/**` only) and therefore are **not** manifest rows and were **not** given a
disposition. They *look* like Phase-4 group-A archive candidates but cannot be
acted on until a future inventory pass brings repo-root docs into scope:

- `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` (repo root)
- `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` (repo root)

**Recommendation:** defer to a future phase; do not archive from this dry run.

## 7. OPEN Disposition Recommendations (DR-1…DR-8)

All eight DRs remain **OPEN** and are **not** resolved here. No document that is
the sole explanation of an OPEN DR is archived; the billing/subscriptions/payments
prelaunch reports (§3) that back the billing-area DRs are explicitly held in place.

## 8. Summary of held-back counts

| Reason | Disposition | Count |
| --- | --- | --- |
| Code-referenced | `KEEP_HISTORICAL_REFERENCE` | 11 |
| Canonical-referenced | `KEEP_HISTORICAL_REFERENCE` | 9 |
| Conservative historical (no ref) | `KEEP_HISTORICAL_REFERENCE` | 13 |
| Protected canonical source | `KEEP_CANONICAL_SUPPORT` | (within 20) |
| Legal / third-party | `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` | 3 |
| Ambiguous plans/specs | `DEFER_REVIEW` | 44 |

(11 + 9 + 13 = 33 = total `KEEP_HISTORICAL_REFERENCE`.)


---

## `[PHASE 8 CORRECTIVE REVIEW]` — root docs dispositioned; new held-back files

### Root mandatory documents (previously "out of scope")

§6 above said the two repository-root docs were out of the Phase-3 inventory and
therefore not dispositioned. **This is now corrected.** Both have been analysed
and added to the manifest as supplemental root records, both
`KEEP_HISTORICAL_REFERENCE` (NOT archived):

| Root document | Disposition | Why held (not archived) |
| --- | --- | --- |
| `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` | `KEEP_HISTORICAL_REFERENCE` | Describes the **retired** family architecture (`family_registry.py`/`preset_registry.py` confirmed **absent**; superseded by the universal R4 + A8/preset engine). Referenced by the canonical-support doc `docs/architecture/UNIVERSAL_STOREFRONT_PHASE1_ARCHITECTURE.md`. Not archived merely for age. |
| `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` | `KEEP_HISTORICAL_REFERENCE` | Self-declared `IMPLEMENTATION_INCOMPLETE` / runtime `NOT EXECUTED`; sole surviving record of that status. Cited in the docstring of the test file `apps/cart/tests/test_gift_wrap.py` (`CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY`). |

### Additional high-risk files held back this pass (11)

The exact-path reference scan found 11 files that looked archivable but are
referenced by retained/canonical/AKS docs that stay in place. All were downgraded
`ARCHIVE_CANDIDATE → KEEP_HISTORICAL_REFERENCE` (fixpoint), e.g. the 7
`docs/architecture_audits/final_closure_pack/*` docs and the top-level audit
(cited by a KEEP decision-baseline doc), `docs/audits/universal_storefront_engine_u3_u11_execution.md`
(cited by the AKS Phase-3 inventory), `docs/prototypes/storefront-builder-v2/rastisi_builder_v2_prototype.html`
(cited by the canonical V2 spec), `docs/template-references/live-audit/01_REPOSITORY_ARCHITECTURE_AND_GAPS.md`,
and `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_5_AUDIT.md` (cascade). Full
per-file reasons are in `03_ARCHIVE_DISPOSITION_MANIFEST.csv`
(`special_handling = REFERENCED_BY_RETAINED_DOC_CORRECTIVE`).
