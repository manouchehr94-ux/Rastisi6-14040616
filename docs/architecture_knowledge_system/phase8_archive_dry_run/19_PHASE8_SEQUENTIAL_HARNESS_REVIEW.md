# Phase 8.3 — Sequential Harness Review `[PHASE 8.3]`

> **DRY RUN / HARNESS ONLY. NO ARCHIVE WAS EXECUTED.** No `git mv` in the real
> repo, no `docs/archive/**` created, no historical doc / production code / test /
> migration modified, DR-1…DR-8 remain OPEN, no branch/merge/rebase/PR.

## 1. Provenance

| Item | Value |
| --- | --- |
| Repository | `manouchehr94-ux/Rastisi6-14040616` |
| Branch (only) | `docs/architecture-knowledge-system` |
| HEAD at start | `14c9437c` |
| Production baseline (frozen) | `5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb` |
| Runtime diff (baseline→HEAD, `apps/ shop_core/ templates/ static/`) | **empty** |

## 2. The blocker fixed

The Phase-8.2 staged-tree verifier built its **expected staged set** from the
**cumulative completed** lifecycle state:

```
expected = { (source, target) for row in rows if row_completed(row) }
```

Correct for the *first* sub-batch, but wrong from the *second* onward. After `A6`
is committed, staging `A5` in state `A6A5` would treat **both** A6 and A5 as
"completed" and expect **both** to be staged — falsely failing with "expected A6
moves not staged", even though A6 is already committed and must **not** be
re-staged.

**Root cause:** lifecycle *state* (cumulative) and the *staged delta* (one unit)
were conflated. Phase 8.3 models them separately.

## 3. What changed (tooling)

`tools/docs/validate_architecture_docs.py`:

- **Canonical order** `CANONICAL_ORDER = [A6, A5, A4, A3, A2, A1, B, C, D5, D4, D3, D2, D1]`
  — small-first; the single source of truth for execution ordering.
- **New flags:** `--phase8-current-sub-batch <UNIT>` (the one unit staged now),
  `--phase8-state-before <STATE>` (cumulative state before the current unit).
- **Staged verifier expects only the current unit's delta:**
  `expected = {(src,tgt) for row in rows if row["sub_batch"] == CURRENT}`.
  `--phase8-verify-staged` now **requires** `--phase8-current-sub-batch`.
- **Transition legality:** `STATE_AFTER == STATE_BEFORE + [CURRENT]`; `CURRENT`
  must be the next canonical unit not already completed (rejects skips / reorder /
  re-doing a done unit).
- **Strict state parser:** consumes the entire expression or rejects it; known
  units only, canonical order, no duplicates. Rejects `A1XYZ`, `A1-BOGUS`, `Q1`,
  `A99`, `A6A6`, `A5A6`, `A6X`, etc.
- Blob-identity relocation proof and the lifecycle existence checks are retained.

`tools/docs/phase8_harness_selftest.py`: rewritten for the **sequential** model
(commit A6, then stage A5) in an isolated `tempfile` git sandbox.

## 4. Ambiguity resolved (execution order)

Earlier drafts contained both an `A1→A2→…` sequence and a "first smoke may be A6
or D5" note. **Resolved:** the canonical order is small-first and **the first live
sub-batch is `A6`** (3 files). Encoded in `CANONICAL_ORDER` and enforced by the
transition checks; documented in `10_ARCHIVE_EXECUTION_PLAN.md §2.2` and
`16_ARCHIVE_EXECUTION_STATE_MODEL.md §2a`.

## 5. Validation results

Real repo (no execution):

| Command | Result |
| --- | --- |
| `validate_architecture_docs.py` (core) | **PASS — warnings 0, errors 0** |
| `--phase8` (static preflight) | **PASS — warnings 0, errors 0** |
| `--phase8-state pre` | **PASS** — 3065 pending, 0 completed, 0 mismatches |

Isolated sequential harness self-test (`phase8_harness_selftest.py`): **21/21
cases behaved as expected.**

Sequential PASS path:
1. `PRE → PASS`
2. stage A6, `--phase8-current-sub-batch A6` (before=pre) blob-identity → **PASS**
3. commit A6
4. `--phase8-state A6` lifecycle → **PASS**
5. stage A5 **after A6 committed**, `--phase8-current-sub-batch A5` (before=A6, after=A6A5) → **PASS** ← *the fix*
6. A6 **not** staged during A5 → confirmed
7. commit A5
8. `--phase8-state A6A5` lifecycle → **PASS**
9. retained sibling untouched → confirmed

Sequential / transition / parser FAIL cases (all correctly FAIL):
- A5 staged but `--phase8-current-sub-batch A6` (wrong current)
- A5 staged + a re-staged A6 (prior-unit) file
- A5 staged + an unrelated file
- A5 target blob tampered (blob mismatch)
- out-of-order: A5 before A6
- invalid states: `A1XYZ`, `A1-BOGUS`, `Q1`, `A99`, `A6A6`, `A5A6`, `A6X`
- valid state `A6A5` parses (no parser error)
- `--phase8-verify-staged` without `--phase8-current-sub-batch`

No test touched the real historical tree (all in `tempfile.mkdtemp()` sandboxes).

## 6. Guardrail compliance

| Guardrail | Status |
| --- | --- |
| No real archive move / `git mv` | ✅ |
| No real `docs/archive/**` | ✅ |
| No historical doc / production / test / migration change | ✅ (runtime diff empty) |
| DR-1…DR-8 unresolved | ✅ |
| No branch/merge/rebase/PR | ✅ |
| Writes confined to `phase8_archive_dry_run/**`, `tools/docs/**`, `VALIDATION_RESULTS.txt` | ✅ |
| Core validator not weakened (all new checks additive/flag-gated) | ✅ |
| Self-test never touches real tree | ✅ |

## 7. Residual notes

- First live unit is `A6` (3 files) — a genuine smoke test; the harness is identical
  for every subsequent unit up to `D1` (1476 files).
- `D1` remains a single provenance unit; optional finer commits are possible
  without changing `13_...` (mapping stays deterministic) — not required.
- Correctness does not depend on git rename display; blob identity is exact.

## 8. Verdict

> ## `READY_FOR_FIRST_ARCHIVE_SUBBATCH_AUTHORIZATION`
>
> The sequential execution harness is repaired and proven: lifecycle state and
> staged delta are modelled separately, the staged verifier validates only the
> current unit's delta with blob-identity, one canonical small-first order is
> enforced with transition legality, the state parser rejects garbage, and the
> self-test covers the sequential path plus every relevant failure (21/21). The
> data plan (522 records, 3065 safe-to-move files) is unchanged.
>
> **This is NOT permission to execute.** It states only that the harness is ready
> to be independently reviewed before authorizing the **first** archive sub-batch
> (`A6`, 3 files). No archive move occurs until that separate authorization.

## 9. Closing statement

**No archive was executed.** All Phase-8.3 changes are planning + tooling under
`docs/architecture_knowledge_system/phase8_archive_dry_run/**` and `tools/docs/**`.
The plan and harness remain inert until a future, separately-approved execution
phase. **STOP.**
