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

> The table above is the **definitional** id→subtree mapping (order-independent).
> The **execution order** is the canonical small-first sequence in §2a
> (`A6` first), not the numeric id order.

**Splitting rationale:** each sub-batch is one coherent source subtree, keeps its
retained siblings untouched, is individually reviewable and revertible, and maps
deterministically from the manifest. Provenance is preserved (targets mirror
original paths under `docs/archive/`). D1 remains a single 1476-file sub-batch
because it is one self-contained reference-asset export (`beraito-exact-frontend-v5`);
splitting it internally would fragment a single provenance unit — it is reviewed
as a unit and reverted as a unit.

## 2a. Canonical execution order `[PHASE 8.3]`

There is exactly **one** authoritative order (encoded as `CANONICAL_ORDER` in the
validator), chosen **small-first** so the first live run is the smallest unit:

```
A6 → A5 → A4 → A3 → A2 → A1 → B → C → D5 → D4 → D3 → D2 → D1
(3)  (18) (21) (30) (250)(1086)(1)(28) (1) (27) (49) (75)(1476)
```

**Ambiguity resolved:** earlier drafts contained both an `A1→A2→…` sequence and a
"first smoke may be A6 or D5" note. The canonical order above is now the single
source of truth and **the first live sub-batch is `A6`**.

## 3. Two separate concepts `[PHASE 8.3]`

The harness models **two distinct things** that must never be conflated:

| Concept | Flag | Meaning | Cumulative? |
| --- | --- | --- | --- |
| **Lifecycle state** | `--phase8-state <STATE>` | the ordered set of **completed** execution units (already moved **and committed**) | yes (cumulative) |
| **Staged delta** | `--phase8-current-sub-batch <UNIT>` | the **one** unit whose moves are staged right now (not yet committed) | no (single unit) |

The staged-tree verifier validates **only the current unit's delta** — never the
cumulative completed set. (Conflating them was the Phase-8.3 bug: after `A6` was
committed, staging `A5` would falsely be expected to also re-stage `A6`.)

### State token grammar (strict)

`--phase8-state` is `pre` (nothing done) or a concatenation of **known execution
unit ids** from the canonical order, e.g. `A6`, `A6A5`, `A6A5A4B`. The parser
**consumes the entire expression or rejects it**: units must be known, appear in
**canonical order**, and not repeat. Garbage or any unconsumed character is a hard
error. Rejected examples: `A1XYZ`, `A1-BOGUS`, `Q1`, `A99`, `A6A6` (dup),
`A5A6` (out of order).

## 4. Per-row lifecycle semantics (cumulative `--phase8-state`)

For each row in `13_...`, given the completed-unit set:

| Row's unit completed in STATE? | `source_path` | `target_path` |
| --- | --- | --- |
| **completed** | must **NOT** exist | must **exist** |
| **pending** | must **exist** | must **NOT** exist |

State-independent invariants (every state): `safe_to_move == TRUE`;
`source_path != target_path`; no duplicate source/target; valid `batch`.
A single mismatch FAILs.

## 4a. Transition legality `[PHASE 8.3]`

When a current unit is supplied, the harness also checks the transition
`STATE_BEFORE → CURRENT → STATE_AFTER`:

- `STATE_AFTER` must equal `STATE_BEFORE + [CURRENT]` (canonical order);
- `CURRENT` must be the **next** canonical unit not already in `STATE_BEFORE`
  (no skips, no out-of-order);
- `CURRENT` must not already be completed in `STATE_BEFORE`.

Illegal examples (rejected): `before=pre, current=A5` (A6 must be first);
`before=A6, current=A4` (skips A5).

## 5. Expected results (illustrative)

| Command | Expected |
| --- | --- |
| `--phase8-state pre` | 3065 pending, 0 completed → **PASS** |
| `--phase8-state A6` | A6 (3) completed; 3062 pending → **PASS** (after A6 committed) |
| `--phase8-state A6A5` | A6+A5 (21) completed; rest pending → **PASS** |
| `--phase8-state A6A5A4A3A2A1BCD5D4D3D2D1` | all 3065 completed → **PASS** (full completion) |
| staging A5 with `--phase8-current-sub-batch A5 --phase8-state-before A6` | only A5's moves staged, blob-identity holds → **PASS** |
| staging A5 but `--phase8-current-sub-batch A6` | → **FAIL** (wrong current) |
| `--phase8-state A5` (before=pre) | → **FAIL** (out-of-sequence; A6 first) |

## 6. Execution state sequence (future, not now)

```
pre → A6 → A6A5 → A6A5A4 → A6A5A4A3 → A6A5A4A3A2 → A6A5A4A3A2A1
    → …A1B → …A1BC
    → …CD5 → …CD5D4 → …CD5D4D3 → …CD5D4D3D2 → A6A5A4A3A2A1BCD5D4D3D2D1
```

For each unit: stage its moves, run the staged-tree verifier for that **current
unit** (`--phase8-current-sub-batch`, blob identity + transition legality), run the
core validator, commit, then run `--phase8-state <new cumulative>` post-commit.
Full procedure in `10_ARCHIVE_EXECUTION_PLAN.md §3`.

## 7. Isolation guarantee

The state validator accepts `--phase8-fixture <DIR>` to run against an isolated
throwaway repository. The harness self-test (`tools/docs/phase8_harness_selftest.py`)
uses this to exercise every PASS/FAIL case in a `tempfile.mkdtemp()` sandbox — it
**never** moves a real historical file and creates **no** real `docs/archive/**`.
