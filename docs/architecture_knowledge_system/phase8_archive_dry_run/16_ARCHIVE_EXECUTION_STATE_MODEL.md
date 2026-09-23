# Phase 8.2 — Archive Execution State Model `[PHASE 8.2]`

> **DRY RUN / HARNESS ONLY.** No archive move has been executed. This document
> defines the *lifecycle* the future execution follows and the state-aware
> validation that guards each step. No `git mv` was run; no `docs/archive/**`
> exists.

## 1. Why a state model is needed

The original `--phase8` validator (checks P8-1…P8-10) is **static preflight**: it
asserts that **every execution source path exists** and targets are absent. That
is correct *before* any batch runs, but becomes **wrong after a batch is moved** —
once `docs/qa_evidence/x.jpg` is relocated to `docs/archive/qa_evidence/x.jpg`,
the source no longer exists and a preflight-only validator would falsely FAIL.

Phase 8.2 therefore splits validation into two layers:

| Layer | Flag | When | Asserts |
| --- | --- | --- | --- |
| **Static preflight** | `--phase8` | before any execution | all 3065 sources exist, targets absent, plus P8-1…P8-10 |
| **Execution-state** | `--phase8-state <STATE>` | before/after each batch | per-row existence consistent with which batches are completed |

The core documentation validator (no flag) is unchanged and always runs.

## 2. Batches and sub-batches

Execution is per-file (never whole-directory). Batches are split into coherent,
reversible **sub-batches** by source subtree (see
`13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`, column `sub_batch`):

| Batch | Sub-batch | Source subtree | Exact tracked files |
| --- | --- | --- | ---: |
| A | A1 | `docs/qa_evidence/storefront_design_engine` | 1086 |
| A | A2 | `docs/qa_evidence/storefront_appearance_convergence` | 250 |
| A | A3 | `docs/qa_evidence/ready_template_previews` | 30 |
| A | A4 | `docs/qa_evidence/storefront_builder` | 21 |
| A | A5 | `docs/qa_evidence/site_target_overhaul` | 18 |
| A | A6 | `docs/qa_evidence/phase5_uiux_agent_foundation` | 3 |
| B | B | `docs/audits` (selective) | 1 |
| C | C | `docs/architecture/*PHASE_*` + `docs/reports` + `docs/docs/product/reports` (selective) | 28 |
| D | D1 | `docs/references/beraito-exact-frontend-v5` | 1476 |
| D | D2 | `docs/docs/product/Final Result At Last` | 75 |
| D | D3 | `docs/reference-kits` | 49 |
| D | D4 | `docs/template-references` | 27 |
| D | D5 | `docs/prototypes` (the single archivable prototype asset) | 1 |
| | | **Total** | **3065** |

`1086+250+30+21+18+3 + 1 + 28 + 1476+75+49+27+1 = 3065`.

**Splitting rationale:** each sub-batch is one coherent source subtree, keeps its
retained siblings untouched, is individually reviewable and revertible, and maps
deterministically from the manifest. Provenance is preserved (targets mirror
original paths under `docs/archive/`). D1 remains a single 1476-file sub-batch
because it is one self-contained reference-asset export (`beraito-exact-frontend-v5`);
splitting it internally would fragment a single provenance unit — it is reviewed
as a unit and reverted as a unit.

## 3. State token grammar

`--phase8-state <STATE>` where STATE is either:

- `pre` — nothing executed yet (the current real-repo state); **or**
- a concatenation of **completed** batch letters and/or sub-batch ids, e.g.
  `A1`, `A1A2`, `A` (whole batch A = all A-sub-batches), `AB`, `ABC`, `ABCD`.

Tokenisation: the parser reads maximal `[A-E]\d*` tokens. A bare letter (`A`)
marks the **whole** batch complete; a letter+digits (`A1`) marks that sub-batch
complete. Unknown batches or sub-batch ids are rejected.

## 4. Per-row lifecycle semantics

For each row in `13_...`:

| Row's batch/sub-batch in STATE? | `source_path` | `target_path` |
| --- | --- | --- |
| **completed** | must **NOT** exist | must **exist** |
| **pending** (not completed) | must **exist** | must **NOT** exist |

And in **every** state, for every row (state-independent invariants):

- `safe_to_move == TRUE`
- `source_path != target_path`
- no duplicate `source_path`, no duplicate `target_path` (no target collision)
- `batch` is a valid batch id

A single mismatch makes the state validation FAIL.

## 5. Expected results by state (illustrative)

| Command | Expected |
| --- | --- |
| `--phase8-state pre` | 3065 pending, 0 completed; all sources present, all targets absent → **PASS** |
| `--phase8-state A1` | A1 (1086) completed: sources absent, targets present; the other 1979 pending → **PASS** |
| `--phase8-state A` | all of batch A (1408) completed; B/C/D (1657) pending → **PASS** |
| `--phase8-state ABCD` | all 3065 completed; sources absent, targets present → **PASS** |
| completed row whose target is missing | → **FAIL** (`completed but target absent`) |
| pending row whose source is missing | → **FAIL** (`pending but source absent`) |

## 6. Recommended state sequence for execution (future, not now)

```
pre  →  A1 → A1A2 → A1A2A3 → A1A2A3A4 → A1A2A3A4A5 → A  (all A)
     →  AB  →  ABC  →  ABC D1 → … → ABCD  (all complete)
```

After each sub-batch is staged, the **staged-tree verifier**
(`17_ARCHIVE_STAGED_TREE_VERIFIER.md`, `--phase8-verify-staged`) proves the
staged change is a pure relocation; after each commit, `--phase8-state <prefix>`
proves the on-disk lifecycle is consistent. Both must PASS, plus the core
validator, before proceeding (full procedure in `10_ARCHIVE_EXECUTION_PLAN.md`).

## 7. Isolation guarantee

The state validator accepts `--phase8-fixture <DIR>` to run against an isolated
throwaway repository. The harness self-test (`tools/docs/phase8_harness_selftest.py`)
uses this to exercise every PASS/FAIL case in a `tempfile.mkdtemp()` sandbox — it
**never** moves a real historical file and creates **no** real `docs/archive/**`.
