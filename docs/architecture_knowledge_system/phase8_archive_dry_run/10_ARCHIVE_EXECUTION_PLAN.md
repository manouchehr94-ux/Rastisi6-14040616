# Phase 8 — Archive Execution Plan (FOR A FUTURE, SEPARATELY-APPROVED PHASE)

> **DRY RUN ONLY. DO NOT EXECUTE ANY STEP IN THIS DOCUMENT DURING PHASE 8.**
> This is the *proposed* procedure for a later phase. It performs relocations via
> `git mv` **only** — never `rm`. Every batch has a validator gate, a rollback,
> and a human review checkpoint.

## 0. Preconditions (must all hold before batch A)

- [ ] Explicit human approval to *execute* the archive (separate from this dry run).
- [ ] Working branch = `docs/architecture-knowledge-system`; clean tree.
- [ ] Baseline still `5883a1404a8b0f1f245f0d8ef17ac5c13e40a7cb`; runtime diff empty:
  `git diff --stat 5883a140… HEAD -- apps/ shop_core/ templates/ static/` → empty.
- [ ] Validator PASS 0/0 at start:
  `python3 tools/docs/validate_architecture_docs.py`
- [ ] `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv` re-verified: every row
  `safe_to_move = TRUE`, no duplicate `source_path`/`target_path`, no
  `source_path == target_path`, every `source_path` exists as a tracked file.

> **`[PHASE 8 CORRECTIVE REVIEW]`** The execution input is now
> `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv` (one exact git-tracked path per row),
> **not** the logical `03_ARCHIVE_DISPOSITION_MANIFEST.csv`. The prior precondition
> ("417 ARCHIVE_CANDIDATE rows, all `link_break_risk = LOW`") confused
> *manifest units* with *files to move* and is superseded — see §2.

## 1. Global rules

1. **`git mv` only.** Never `rm`, never `mv` outside git, never delete.
2. **One batch = one commit.** No mixing batches.
3. **Validator gate after every batch.** If not PASS 0/0 → stop, roll back that batch.
4. **No code/test/migration edits.** Production surfaces stay frozen.
5. **No banner insertion during moves** (banners are an optional later step, §7).
6. **Provenance mapping:** `docs/<rel>` → `docs/archive/<rel>` (root-preserving).

## 2. Batch plan (A–E)

> **`[PHASE 8 CORRECTIVE REVIEW]` — counts are now EXACT TRACKED FILES, not manifest rows.**
> The original table stated "417" as the moved count. **417 was a logical
> manifest-unit count** (which included 6 collection *pseudo-rows* each standing
> for hundreds of real files). The true number of exact git-tracked files to
> `git mv` — after collection expansion, exact-path reference back-pressure, and
> the corrective downgrades — is **3065 tracked files**. All counts below are exact
> tracked-file counts derived from `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`.

| Batch | Source scope | Manifest units | **Exact tracked files** | Retained under same roots | Link risk |
| --- | --- | ---: | ---: | ---: | --- |
| **A** | `docs/qa_evidence/**` (selective; leaves 8 KEEP siblings in place) | 1 collection + 332 textual | **1408** | 8 | none (all `safe_to_move`) |
| **B** | `docs/audits/**` (selective; `architecture_audits/**` now all KEEP) | ~3 | **1** | 1 (+8 in architecture_audits) | none |
| **C** | `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_*` (selective) + `docs/reports/**` + `docs/docs/product/reports/**` (selective) | ~29 | **28** | 31 across those roots | none |
| **D** | `docs/reference-kits/**`, `docs/references/**`, `docs/template-references/**`, `docs/prototypes/**`, `docs/docs/product/Final Result At Last/**` (selective) | 4 collections + textual | **1628** | 4 | none |
| **E** | *(reserved — no auto-archive)* superpowers plans/specs remain `DEFER_REVIEW` | — | **0** | — | — |
|  | **Total moved** | 406 logical units | **3065 files** | — | — |

> 1408 + 1 + 28 + 1628 + 0 = **3065** exact tracked files. The logical
> `ARCHIVE_CANDIDATE` unit total is **406** (incl. 6 collection pseudo-rows).
> Batch E moves nothing by design.
>
> **Directory-level `git mv` is FORBIDDEN for 8 of the source roots** (they contain
> retained/deferred siblings) — see `14_DIRECTORY_MOVE_SAFETY_CHECK.md`. Only
> `docs/reference-kits` and `docs/docs/product/Final Result At Last` are whole-dir
> safe, and even those are executed per-file from `13_...` for uniformity.

### 2.1 Per-batch derivation of the exact file list `[PHASE 8 CORRECTIVE REVIEW]`

Do **not** hand-type paths, and **do not** use `**`, globs, or whole-directory
`git mv`. Derive each batch's file set from the **exact-path** manifest
`13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`, one `git mv` per row:

```bash
# Emit git mv commands for a given batch from the EXACT-PATH manifest.
# Every row is already proven safe_to_move=TRUE; we re-assert it here.
python3 - "$BATCH" <<'PY'
import csv, sys, shlex, os
batch = sys.argv[1]
p = "docs/architecture_knowledge_system/phase8_archive_dry_run/13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv"
for r in csv.DictReader(open(p, encoding="utf-8")):
    if r["batch"] != batch:
        continue
    assert r["safe_to_move"] == "TRUE", f"UNSAFE ROW LEAKED: {r['source_path']}"
    src, dst = r["source_path"], r["target_path"]
    assert src != dst and "**" not in src and "**" not in dst
    print("mkdir -p", shlex.quote(os.path.dirname(dst)))
    print("git mv --", shlex.quote(src), shlex.quote(dst))
PY
```

- **No whole-directory move.** Even for the 2 whole-dir-safe roots, moves are
  per-file so a later reclassification cannot silently sweep a protected sibling.
- Filenames with spaces / non-ASCII (Persian) characters are handled correctly
  because the paths come verbatim from `git ls-files -z` expansion (see
  `12_COLLECTION_EXPANSION_MANIFEST.csv`) and are `shlex.quote`d.

### 2.2 Canonical execution order `[PHASE 8.3]`

There is **one** authoritative execution order (encoded as `CANONICAL_ORDER` in
`tools/docs/validate_architecture_docs.py` and enforced by transition-legality
checks). It is **small-first**, so the first live run is the smallest unit and any
harness surprise surfaces on 3 files, not 1000+:

```
A6  (3)  →  A5 (18)  →  A4 (21)  →  A3 (30)  →  A2 (250)  →  A1 (1086)
    →  B (1)  →  C (28)
    →  D5 (1)  →  D4 (27)  →  D3 (49)  →  D2 (75)  →  D1 (1476)
```

> **Ambiguity resolved `[PHASE 8.3]`.** Earlier drafts mentioned both an
> `A1→A2→…` sequence and a "first smoke may be A6 or D5" note. This is now
> settled: **the canonical order is the small-first list above, and the first
> live sub-batch is `A6`.** The lifecycle model represents state as the ordered
> set of **completed execution units** (not an alphabetical prefix); `--phase8-state`
> is parsed strictly against this order (out-of-order or unknown tokens are
> rejected). See `16_ARCHIVE_EXECUTION_STATE_MODEL.md`.

## 3. Per-sub-batch procedure `[PHASE 8.2]` (repeat for each sub-batch A1…A6, B, C, D1…D5)

> **`[PHASE 8.2]` supersedes the earlier §3.** Three hardenings:
> (1) staging never uses `git add -A`; (2) the staged-tree verifier proves a
> **pure relocation by blob identity**, not the `R*` rename heuristic; (3) **no
> tracked validation-output file is written between staging and commit** — the
> validators print to the console / a temp file only.

> **`[PHASE 8.3]` supersedes the §3 command block below.** Two corrections:
> (1) the **staged-tree verifier now takes the CURRENT sub-batch explicitly**
> (`--phase8-current-sub-batch`) and validates **only that unit's delta** — the
> earlier version derived the expected staged set from the cumulative
> `--phase8-state`, which wrongly required already-committed sub-batches to be
> re-staged; (2) execution follows **one canonical order** (§2.2) and each step
> asserts transition legality via `--phase8-state-before`.

The unit of execution is a **sub-batch** = one canonical execution unit
(`sub_batch` column of `13_...`). `STATE_BEFORE` is the cumulative completed
prefix **before** this unit; `STATE_AFTER = STATE_BEFORE + CURRENT`.

```bash
CUR=A6                                   # canonical first unit (§2.2); then A5, A4, …
STATE_BEFORE=pre                         # cumulative completed BEFORE this unit
STATE_AFTER=A6                           # == STATE_BEFORE + CUR (canonical order)
TMP="$(mktemp -d)"                       # external scratch — never inside the repo

# 1. Clean tree
test -z "$(git status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }

# 2. Capture pre-batch HEAD (used by the blob-identity verifier and rollback)
PRE="$(git rev-parse HEAD)"

# 3. Lifecycle preflight for the state BEFORE this unit -> must PASS
python3 tools/docs/validate_architecture_docs.py --phase8-state "$STATE_BEFORE" \
  > "$TMP/state_before.txt" 2>&1
grep -q "RESULT: PASS" "$TMP/state_before.txt" || { echo "PRE-STATE NOT PASS"; exit 1; }

# 4. Emit + review the exact git mv commands for THIS unit (from 13_..., see §2.1)
#    (filter on sub_batch == "$CUR"); execute them — git mv ONLY, never rm, never add -A.

# 5. Staged-tree verifier: validate ONLY this unit's delta, prove PURE RELOCATION
#    by blob identity (not R*). Transition legality is checked here too.
python3 tools/docs/validate_architecture_docs.py \
    --phase8-state "$STATE_AFTER" --phase8-state-before "$STATE_BEFORE" \
    --phase8-current-sub-batch "$CUR" \
    --phase8-verify-staged --phase8-pre-head "$PRE" \
    > "$TMP/staged.txt" 2>&1
grep -q "RESULT: PASS" "$TMP/staged.txt" || { echo "STAGED-TREE VERIFY FAILED"; cat "$TMP/staged.txt"; exit 1; }

# 6. Core documentation validator -> must PASS (printed to temp, NOT a tracked file)
python3 tools/docs/validate_architecture_docs.py > "$TMP/core.txt" 2>&1
grep -q "RESULT: PASS" "$TMP/core.txt" || { echo "CORE VALIDATOR NOT PASS"; exit 1; }

# 7. Commit ONLY this unit's already-staged renames (NO git add -A; NO tracked
#    validation-output file is part of this commit).
git commit -m "docs(archive): relocate sub-batch $CUR to docs/archive"

# 8. Post-commit lifecycle validator for the NEW cumulative state -> must PASS
python3 tools/docs/validate_architecture_docs.py --phase8-state "$STATE_AFTER" \
  > "$TMP/state_after.txt" 2>&1
grep -q "RESULT: PASS" "$TMP/state_after.txt" || { echo "POST-STATE NOT PASS"; exit 1; }

# 9. HUMAN REVIEW CHECKPOINT (review "$TMP" reports + the committed rename list)

# 10. Clean tree again; discard scratch
test -z "$(git status --porcelain)" || { echo "TREE NOT CLEAN AFTER COMMIT"; exit 1; }
rm -rf "$TMP"
```

> **Validation output must never contaminate a batch commit.** Steps 3, 5, 6, 7
> write to `$TMP` (an external `mktemp -d`), never to the tracked
> `docs/architecture_knowledge_system/VALIDATION_RESULTS.txt`. That tracked file
> is refreshed **once**, in a **separate final documentation commit**, only after
> **all** archive batches are complete (see §8).

## 4. Rollback `[PHASE 8 CORRECTIVE REVIEW]`

The prior rollback (`git checkout -- . && git clean`) was **insufficient**: it
restores the worktree but leaves staged `git mv` renames in the index, so a
partly-applied batch would not be cleanly undone. Use an index+worktree reset.

**Uncommitted batch** (safe only on this isolated documentation branch/worktree,
and only after confirming the batch contains no unrelated user work):

```bash
# Restores BOTH index and worktree to the pre-batch HEAD recorded in step 1.
git reset --hard "$PRE"      # $PRE = pre-batch HEAD; discards the staged renames
git status --porcelain       # expect empty
```

Preconditions for the hard reset:
- current branch is `docs/architecture-knowledge-system` (a dedicated docs branch);
- `git status` before the batch was clean (no unrelated staged/worktree changes);
- `$PRE` was captured in step 1 and is the immediate pre-batch HEAD.

**Committed-but-unpushed batch** (preferred; never rewrite history):

```bash
git revert --no-edit <batch_commit_sha>   # reinstates original paths via a new commit
```

Because every step is a `git mv`, a `git revert` of the batch commit fully
restores the original tree with no content loss.

## 5. Validator gates (mandatory)

> **`[PHASE 8 CORRECTIVE REVIEW]`** In addition to the core doc validator, run the
> Phase-8 execution-safety checks (`--phase8` mode of
> `tools/docs/validate_architecture_docs.py`, added in this corrective pass): they
> assert exact-path source existence, no source/target collision, no duplicate
> source/target, no execution path from a KEEP/DEFER/LEGAL source, no unsafe
> whole-directory move, and that the root mandatory documents are dispositioned.
> The execution gate requires BOTH the core validator **and** the Phase-8 checks
> to pass.

> **`[PHASE 8.2]`** The per-batch gate now uses the **lifecycle-aware**
> `--phase8-state <STATE>` validator (not the static `--phase8`, which is
> preflight-only and would falsely FAIL once a source has been relocated) plus the
> **`--phase8-verify-staged`** blob-identity staged-tree verifier. Static
> `--phase8` is used **only** at `pre` (before any batch). All validator output
> during batches goes to an external temp file, **never** to a tracked file
> (see §3). The harness is proven by `tools/docs/phase8_harness_selftest.py`
> (11/11 cases). See `16_ARCHIVE_EXECUTION_STATE_MODEL.md` and
> `17_ARCHIVE_STAGED_TREE_VERIFIER.md`.

> **`[PHASE 8.3]`** The staged-tree gate now **requires** `--phase8-current-sub-batch <UNIT>`
> and validates **only that unit's delta** (the previous gate wrongly expected the
> whole cumulative completed set to be staged, so the 2nd sub-batch onward would
> falsely FAIL). The gate also passes `--phase8-state-before` so transition
> legality (canonical order, no skips) is enforced. The sequential harness is
> proven by `tools/docs/phase8_harness_selftest.py` (**21/21** cases, incl. a
> committed A6 followed by a staged A5). See `19_PHASE8_SEQUENTIAL_HARNESS_REVIEW.md`.

- After **each** batch: validator must report **PASS, 0 errors / 0 warnings**.
- The validator's `EXPECTED_ABSENT` allowlist
  (`apps/storefront_builder/family_registry.py`,
  `apps/storefront_builder/preset_registry.py`, `apps/blog/urls.py`,
  `apps/orders/gateways/new_gateway.py`) is unrelated to archiving and must remain
  unchanged.
- If the validator flags a broken link after a move, the move introduced a
  reference that the dry-run analysis said was absent → **stop**, roll back, and
  re-run `05_LINK_AND_REFERENCE_IMPACT.md` / `06_CANONICAL_DEPENDENCY_CHECK.md`.

## 6. Review gates (human)

| Gate | When | Question |
| --- | --- | --- |
| G0 | Before batch A | Is execution approved? Baseline still frozen? `13_...` all `safe_to_move`? |
| G1 | After batch A | 1408 QA-evidence file moves correct; 8 KEEP siblings untouched? Validator PASS? |
| G2 | After batch B/C/D | Reports/audits/reference material (1+28+1628 files) correct; retained siblings untouched? Validator PASS? |
| G3 | Before batch E | Has each deferred plan/spec been individually reviewed? |
| G4 | Before push | Squash/keep batch commits? Update `docs/README.md` in the follow-up correct-in-place phase? |

## 7. Archive banner template (OPTIONAL — later, not during the move)

If, in a still-later step, banners are desired, prepend this block to each archived
Markdown doc. **Do not insert during the `git mv` batches** (keeps moves as pure
renames and diffs reviewable):

```markdown
> **📦 ARCHIVED DOCUMENT**
> This document was archived on <YYYY-MM-DD> from its original location
> `<original/path>`. It is retained for historical reference and is **not**
> maintained. For the current architecture, see the canonical layer at
> `docs/architecture_knowledge_system/README.md`.
> Superseded by: `<canonical-doc-or-"n/a">`.
```

## 8. Post-execution (future) `[PHASE 8.2]`

1. Refresh the tracked `docs/architecture_knowledge_system/VALIDATION_RESULTS.txt`
   **once**, in a **separate, dedicated documentation commit** made **after all
   archive batches are complete** — never as part of a batch commit. Suggested
   message: `docs(architecture): refresh validation results post-archive`.
2. Run the correct-in-place phase for `docs/README.md` / `docs/docs/README.md`
   (`08_CORRECT_IN_PLACE_QUEUE.md`) so indexes point at `docs/archive/…`.
3. Re-run the core validator and `--phase8-state ABCD` (full-completion state);
   both PASS 0/0.
4. Update the AKS registry if any archived path was tracked.

## 9. Phase-8 statement

**None of the above was executed.** No batch ran, no `git mv` occurred, no
`docs/archive/` exists, no banner was inserted. `[PHASE 8.2]` added only planning
+ tooling (lifecycle/staged-tree validation, sub-batches, self-test); the plan
remains inert until a future phase is explicitly approved.
