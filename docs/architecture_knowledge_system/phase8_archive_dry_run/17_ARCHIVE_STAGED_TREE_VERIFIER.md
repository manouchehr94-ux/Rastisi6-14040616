# Phase 8.2 — Archive Staged-Tree Verifier `[PHASE 8.2]`

> **DRY RUN / HARNESS ONLY.** Describes how a future execution step is proven to
> be a pure relocation. No `git mv` was run in this phase.

## 1. The problem being fixed (Blocker 3)

The original execution plan's scope check assumed every staged `git mv` appears as
a rename line:

```
R100  old  new
```

in `git diff --cached --name-status`. **This is unsafe.** Git stores tree
snapshots, not rename metadata; renames are *inferred* by diff at display time.
For large batches (A1 = 1086 files, D1 = 1476 files), rename detection can exceed
`diff.renameLimit` or otherwise present a moved file as an independent pair:

```
D  old
A  new
```

even though `git mv` was used. A verifier keyed on `R*` would then either miss
moves or misclassify them, and could wave through an impure change.

## 2. The fix — blob-identity proof (not rename heuristic)

The Phase-8.2 verifier (`--phase8-verify-staged`) proves each move is a **pure
relocation** by comparing **git blob object identity** between the pre-batch
source and the staged target — independent of how git *displays* the change.

For every authorized move `(source_path → target_path)` in the batch:

```
blob( PRE_BATCH_HEAD : source_path )  ==  blob( :target_path )   # ':path' = staged/index blob
```

Object identity (`git rev-parse <ref>:<path>`) is exact: identical blob SHA ⇒
byte-identical content ⇒ the file was relocated, not modified.

## 3. Accepted staged-tree shapes

The verifier reads `git diff --cached --name-status -z` (NUL-delimited, so paths
with spaces / non-ASCII (Persian) names are exact) and accepts a move presented
**either** as:

- `R  source  target`, **or**
- the logically equivalent pair `D source` + `A target`,

and then reconstructs the logical `(source → target)` set by matching against the
authorized batch's expected moves.

## 4. Checks performed (all must hold)

For the batch/sub-batch state under test:

1. **No non-relocation staged change** — any staged `M`/`T`/`C` (modify/typechange/copy)
   status is rejected.
2. **No unexplained staged deletion** — every staged `D` must be the source of an
   authorized reconstructed move.
3. **No unexplained staged addition** — every staged `A` must be the target of an
   authorized reconstructed move.
4. **Every reconstructed move is authorized** — `(source, target)` must be in the
   batch's expected set from `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`.
5. **Every expected move is staged** — nothing authorized is silently omitted.
6. **Blob identity** — for each move, staged `:target` blob SHA equals
   `PRE_BATCH_HEAD:source` blob SHA. Any missing blob or SHA mismatch FAILs.

Together these prove: the staged tree contains **exactly** the authorized batch's
moves, **nothing else** is staged, and **no content changed**.

## 5. Interface

```bash
python3 tools/docs/validate_architecture_docs.py \
    --phase8-state <BATCH_OR_SUBBATCH> \
    --phase8-verify-staged \
    --phase8-pre-head <PRE_BATCH_HEAD_SHA> \
    [--phase8-fixture <DIR>]     # isolated repo for tests; omit for the real repo
```

- Run **after staging** a sub-batch's `git mv`s and **before** committing.
- `--phase8-pre-head` is the HEAD captured immediately before the batch's moves
  (step 2 of the execution procedure in `10_ARCHIVE_EXECUTION_PLAN.md`).
- `--phase8-fixture` points the verifier at a throwaway repo (used by the
  self-test); without it the verifier targets the real repository.

## 6. Proven by self-test

`tools/docs/phase8_harness_selftest.py` builds a throwaway git repo and asserts:

| Case | Expected |
| --- | --- |
| PRE state | PASS |
| staged sub-batch A1 as pure relocation | PASS (blob identity holds) |
| A1 completed lifecycle | PASS |
| completed batch target missing | FAIL |
| pending source missing | FAIL |
| extra unrelated staged path | FAIL |
| staged target content tampered (blob mismatch) | FAIL |
| duplicate target in manifest | FAIL |
| row not `safe_to_move=TRUE` | FAIL |
| all batches completed | PASS |
| retained sibling never moved | holds |

Result: **11/11 cases behaved as expected**, entirely inside a
`tempfile.mkdtemp()` sandbox — the real historical tree is never modified.

## 7. Why blob identity beats similarity

`git`'s rename detection uses a *similarity* score (default 50%) and a candidate
limit. A large batch can silently disable rename detection, and a similarity-based
check could accept a "mostly similar" but altered file. Blob-SHA equality is a
**binary, exact** guarantee: the archived file is bit-for-bit the original. This
is the property the archive must uphold — relocation, never mutation.


---

## `[PHASE 8.3]` — expected staged set is the CURRENT sub-batch delta only

**Correction to §2/§3 above.** The Phase-8.2 verifier derived the expected staged
set from the **cumulative completed** state (`--phase8-state`), i.e.

```python
expected = {(src, tgt) for row in rows if row_completed(row)}   # WRONG for step 2+
```

This is correct only for the very first sub-batch. From the second sub-batch
onward it is a bug: after `A6` is committed, staging `A5` would make the verifier
expect **A6 + A5** to be staged, and it would falsely FAIL because A6 is already
committed (not staged).

The verifier now takes the current unit **explicitly** and expects **only** that
unit's delta:

```python
expected = {(src, tgt) for row in rows if row["sub_batch"] == CURRENT}   # correct
```

Interface (Phase 8.3):

```bash
python3 tools/docs/validate_architecture_docs.py \
    --phase8-state <cumulative AFTER>  \
    --phase8-state-before <cumulative BEFORE> \
    --phase8-current-sub-batch <UNIT> \
    --phase8-verify-staged --phase8-pre-head <PRE_BATCH_HEAD> \
    [--phase8-fixture <DIR>]
```

`--phase8-verify-staged` now **requires** `--phase8-current-sub-batch`. The
lifecycle state (`--phase8-state`) remains cumulative and is validated separately;
the staged delta is single-unit. Blob-identity checking is unchanged.

Additional checks in this mode:

- **No prior-unit path** may be staged (a re-staged already-committed file FAILs).
- **No other-unit / unrelated path** may be staged.
- **Every** move of the current unit must be staged; **no extra** move may appear.
- **Transition legality** (`STATE_AFTER == STATE_BEFORE + [CURRENT]`, canonical
  order, no skips) is enforced.

Proven by the sequential harness self-test (`tools/docs/phase8_harness_selftest.py`,
**21/21**), which stages `A5` **after** `A6` is committed and confirms the verifier
expects only the `A5` delta.
