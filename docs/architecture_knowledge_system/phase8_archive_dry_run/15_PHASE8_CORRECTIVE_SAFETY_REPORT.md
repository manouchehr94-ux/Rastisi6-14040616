# Phase 8 — Corrective Safety Report `[PHASE 8 CORRECTIVE REVIEW]`

> **DRY RUN ONLY. NO ARCHIVE WAS EXECUTED.** No `git mv` was run, no
> `docs/archive/` was created, no historical document was modified, no production
> code/test/migration was touched, DR-1…DR-8 remain OPEN, and no merge/rebase/PR
> was performed. This report records the corrective analysis only.

## 1. Provenance

| Item | Value |
| --- | --- |
| Repository | `manouchehr94-ux/Rastisi6-14040616` |
| Branch (only) | `docs/architecture-knowledge-system` |
| Starting Phase-8 commit | `7cac3326bbdf1eee2fc64f74093c1379b6f80c5f` |
| Ending corrective commit | `docs(architecture): harden archive execution safety` (this commit) |
| Production baseline (frozen) | `5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb` |
| Runtime diff (baseline→HEAD, `apps/ shop_core/ templates/ static/`) | **empty** |

## 2. Why this pass exists

An independent review found execution-safety gaps in the dry-run plan:

- **Blocker 1** — collection rows implied whole-directory `git mv` even where the
  same directory held retained (KEEP) files (`docs/qa_evidence`, `docs/prototypes`,
  `docs/references/beraito-exact-frontend-v5`, …).
- **Blocker 2** — the mandatory repository-root docs `SIX_NEW_FAMILIES_*` were
  omitted (Phase-3 inventory was scoped to `docs/**`).
- **Blocker 3** — the report used **manifest-row counts** ("417") as if they were
  **execution file counts**; several rows each stand for hundreds of real files.

## 3. Blocker 1 — collection expansion & directory-move safety

Every collection row was expanded to its **exact git-tracked files** using
`git ls-files -z` (NUL-delimited, so the **84 space-containing** and **258
non-ASCII / Persian** filenames are exact, never quoted or split). Artifact:
`12_COLLECTION_EXPANSION_MANIFEST.csv` (3048 rows).

| Collection root | Tracked | Safe to move | Retained (KEEP) |
| --- | ---: | ---: | ---: |
| `docs/qa_evidence` | 1416 | 1408 | 8 |
| `docs/references/beraito-exact-frontend-v5` | 1477 | 1476 | 1 |
| `docs/docs/product/Final Result At Last` | 75 | 75 | 0 |
| `docs/reference-kits` | 49 | 49 | 0 |
| `docs/template-references` | 28 | 27 | 1 |
| `docs/prototypes` | 3 | 1 | 2 |

**Directory-move safety** (`14_DIRECTORY_MOVE_SAFETY_CHECK.md`): a whole-directory
`git mv` is allowed **only** if every tracked descendant is `safe_to_move`.

- **Whole-directory move ALLOWED (2):** `docs/docs/product/Final Result At Last`,
  `docs/reference-kits`.
- **Whole-directory move FORBIDDEN (8):** `docs/architecture`, `docs/audits`,
  `docs/docs/product/reports`, `docs/prototypes`, `docs/qa_evidence`,
  `docs/references/beraito-exact-frontend-v5`, `docs/reports`,
  `docs/template-references`.

The execution plan now derives **one `git mv` per exact file** from
`13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`; whole-directory moves are never required.

## 4. Blocker 2 — mandatory root documents dispositioned

Both root docs were read and analysed:

- `family_registry.py` / `preset_registry.py` are **confirmed absent** (family
  architecture retired; superseded by the universal R4 + A8/preset engine).
- `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` self-declares
  `IMPLEMENTATION_INCOMPLETE` / runtime `NOT EXECUTED`.

| Root document | Disposition | Why (not archived merely for age) |
| --- | --- | --- |
| `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` | `KEEP_HISTORICAL_REFERENCE` | Referenced by canonical-support doc `docs/architecture/UNIVERSAL_STOREFRONT_PHASE1_ARCHITECTURE.md` |
| `SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md` | `KEEP_HISTORICAL_REFERENCE` | Cited by test file `apps/cart/tests/test_gift_wrap.py` (`CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY`); sole surviving incomplete-status record |

The only other repo-root markdown is `CLAUDE.md` (agent-instruction file, not
architecture history) — out of archive scope, not a disposition record.

## 5. Blocker 3 — manifest units vs exact tracked files

| Measure | Value |
| --- | --- |
| `ARCHIVE_CANDIDATE` **logical manifest units** (incl. 6 collection pseudo-rows) | **406** |
| `ARCHIVE_CANDIDATE` **exact git-tracked files** to move | **3065** |
| — inside collection roots | 3036 |
| — outside collection roots | 29 |

The authoritative future-execution input is **`13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`**
(one exact path per row, no globs, no pseudo-paths), **not** the logical
`03_ARCHIVE_DISPOSITION_MANIFEST.csv`.

### Per-batch exact file counts

| Batch | Scope | Manifest units | **Exact tracked files** | Retained under same roots |
| --- | --- | ---: | ---: | ---: |
| A | `docs/qa_evidence` (selective) | 1 coll + 332 | **1408** | 8 |
| B | `docs/audits` (selective) | ~3 | **1** | 1 (+8 now-KEEP in architecture_audits) |
| C | `docs/architecture/*PHASE_*` + `docs/reports` + `docs/docs/product/reports` (selective) | ~29 | **28** | 31 |
| D | reference-kits / references / template-references / prototypes / Final Result (selective) | 4 coll + textual | **1628** | 4 |
| E | superpowers plans/specs (reserved, none) | — | **0** | — |
| | **Total** | 406 units | **3065 files** | — |

`1408 + 1 + 28 + 1628 + 0 = 3065`.

## 6. New reference-safety finding (exact-path, disposition-classified)

Re-running the reference scan at **exact-path** granularity (referrers classified
by disposition) found **11 archivable files actually referenced by documents that
stay in place** (retained / canonical / AKS). These would have orphaned a live
link. All 11 were **downgraded `ARCHIVE_CANDIDATE → KEEP_HISTORICAL_REFERENCE`**,
iterated to a **fixpoint** (2 iterations, incl. 1 cascade):

- 8 × `docs/architecture_audits/**` (top-level audit + all 7 `final_closure_pack/*`)
  — cited by the KEEP doc
  `docs/architecture_decisions/2026-09-05-storefront-appearance-convergence-decision-baseline.md`.
- `docs/audits/universal_storefront_engine_u3_u11_execution.md` — cited by the AKS
  Phase-3 inventory (`07_UNCLASSIFIED_OR_AMBIGUOUS_DOCS.md`).
- `docs/prototypes/storefront-builder-v2/rastisi_builder_v2_prototype.html` — cited
  by the canonical `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md`.
- `docs/template-references/live-audit/01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` —
  cited by the KEEP `STOREFRONT_BUILDER_V2_EXISTING_CAPABILITY_AUDIT.md`.
- Cascade: `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_5_AUDIT.md`.

References that remain (from other archive-candidate files that move together, or
from `DEFER_REVIEW` plans/specs reviewed by a human) are **non-blocking** and are
recorded in `13_...incoming_reference_count`.

## 7. Corrected scope & disposition arithmetic (no unexplained remainder)

| Scope term | Value |
| --- | --- |
| `phase3_inventory_units` | 519 |
| `phase8_supplemental_root_documents` | 2 |
| `phase8_supplemental_collection_member_records` | 1 |
| **`phase8_total_disposition_records`** | **522** |

| Disposition | Count |
| --- | --- |
| `ARCHIVE_CANDIDATE` (logical units) | 406 |
| `KEEP_HISTORICAL_REFERENCE` | 47 |
| `KEEP_CANONICAL_SUPPORT` | 20 |
| `DEFER_REVIEW` | 44 |
| `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` | 3 |
| `CORRECT_IN_PLACE_LATER` | 2 |
| **Total** | **522** |

`406 + 47 + 20 + 44 + 3 + 2 = 522`. The 1 supplemental collection-member record is
a file previously represented only by a collection row, promoted to an explicit
`KEEP_HISTORICAL_REFERENCE` row when the exact-path scan showed it is referenced.

`KEEP_HISTORICAL_REFERENCE` composition (47): 33 original + 2 root docs + 11
reference-blocked downgrades + 1 collection-member − 0 = 47.

## 8. Execution-path integrity checks (all pass)

| Check | Result |
| --- | --- |
| `13_...` rows with `safe_to_move = TRUE` | **3065 / 3065** |
| Duplicate source paths | **0** |
| Duplicate target paths | **0** |
| Rows with `source_path == target_path` | **0** |
| Sources not present as tracked files | **0** |
| Execution paths mapping to a KEEP/DEFER/LEGAL source | **0** |
| Execution paths with a blocking canonical/code reference | **0** |
| Unsafe whole-directory moves in the plan | **0** (per-file only; 8 dirs forbidden) |
| Root mandatory docs dispositioned | **YES (2/2)** |

## 9. Validator results

Artifact: `docs/architecture_knowledge_system/VALIDATION_RESULTS.txt` (contains
both sections).

- **Core validator** (`python3 tools/docs/validate_architecture_docs.py`) —
  **PASS, warnings: 0, errors: 0** (unchanged: 435 internal links, 120 code-path
  references, 15 domains, 8 DRs, 15 registry semantic fields, 15 conforming READMEs).
- **Phase-8 checks** (`--phase8`) — **PASS, warnings: 0, errors: 0**. The 10 checks
  (P8-1…P8-10) were **negative-tested**: injecting a `source==target` row, an
  unsafe row, and duplicate sources produced 5 ERRORs and `RESULT: FAIL`; removing
  them restored PASS. The `--phase8` block is **additive** — when the flag is
  absent, the validator behaves exactly as before (existing checks unchanged).

## 10. Execution-plan changes (exact)

- Execution input switched from the logical `03_...` to the exact-path `13_...`.
- Batch table now states **exact tracked-file counts** (A 1408 / B 1 / C 28 / D 1628
  / E 0 = 3065), with logical-unit totals shown separately (406).
- Per-batch derivation emits **one `git mv` per exact path**; **no `**`, no glob,
  no whole-directory move**.
- Staging: **`git add -A` removed**. `git mv` stages the rename; a **batch-scope
  verification** step (NUL-safe, reads `git diff --cached --name-status -z`) fails
  if any staged old/new path is outside the batch's exact manifest, and any non-rename
  status aborts the batch.
- Rollback: uncommitted batch → `git reset --hard <pre-batch-HEAD>` (restores
  **both index and worktree**, with documented preconditions on this isolated docs
  branch); committed batch → `git revert <batch_commit>` (no history rewrite).
- Added the `--phase8` validator gate to the mandatory per-batch gates.

## 11. Guardrail compliance

| Guardrail | Status |
| --- | --- |
| No archive move / `git mv` executed | ✅ |
| No `docs/archive/**` created | ✅ |
| No historical document modified | ✅ |
| No production code/test/migration modified | ✅ (runtime diff empty) |
| DR-1…DR-8 unresolved | ✅ (all OPEN) |
| No merge / rebase / PR | ✅ |
| Writes confined to `docs/architecture_knowledge_system/phase8_archive_dry_run/**`, `tools/docs/**`, `VALIDATION_RESULTS.txt` | ✅ |
| Previous conclusions preserved, revisions visibly annotated `[PHASE 8 CORRECTIVE REVIEW]` | ✅ |
| Core validator PASS 0/0; Phase-8 checks PASS 0/0 | ✅ |

## 12. Verdict

> ## `READY_FOR_ARCHIVE_EXECUTION_REVIEW`
>
> The revised plan is based on the **exact execution-path manifest**
> (`13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`, 3065 files, every row
> `safe_to_move = TRUE`), with directory-move safety proven
> (`14_...`), collection rows fully expanded (`12_...`), the mandatory root
> documents dispositioned, and both validators passing 0/0. Reference safety is
> proven at exact-path granularity; no move would break a live code reference or a
> retained/canonical link.
>
> **This verdict is NOT authorization to execute.** It states only that the
> exact-path plan is safe to hand to an independent execution-authorization review.
> Batch E (superpowers plans/specs) remains `DEFER_REVIEW` pending per-document
> human review.

## 13. Closing statement

**No archive was executed.** All corrective artifacts (`12`–`15`) and the updated
`00`–`11` + validator are planning-only. The plan is inert until a future,
separately-approved execution phase. **STOP.**
