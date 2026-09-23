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

## 3. Per-batch procedure `[PHASE 8 CORRECTIVE REVIEW]` (repeat for A→D)

Staging no longer uses unrestricted `git add -A`. `git mv` already stages the
rename; we then **verify** that every staged path belongs to the authorized
batch and fail otherwise.

```bash
BATCH=A     # then B, C, D

# 1. Record pre-batch HEAD and confirm clean tree
PRE=$(git rev-parse HEAD)
test -z "$(git status --porcelain)" || { echo "TREE NOT CLEAN"; exit 1; }

# 2. Generate the batch git mv script from 13_... (see §2.1) and review it
# 3. Execute the git mv commands for this batch (git mv ONLY; never rm, never add -A)

# 4. Batch-scope verification: EVERY staged path (old + new) must be in this batch.
python3 - "$BATCH" <<'PY'
import csv, subprocess, sys
batch=sys.argv[1]
p="docs/architecture_knowledge_system/phase8_archive_dry_run/13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv"
allowed=set()
for r in csv.DictReader(open(p,encoding="utf-8")):
    if r["batch"]==batch:
        allowed.add(r["source_path"]); allowed.add(r["target_path"])
# staged renames (NUL-safe, -z)
out=subprocess.run(["git","diff","--cached","--name-status","-z"],capture_output=True).stdout.decode()
toks=out.split("\0"); i=0; bad=[]
while i < len(toks) and toks[i]:
    st=toks[i]
    if st.startswith("R"):
        old,new=toks[i+1],toks[i+2]; i+=3
        if old not in allowed or new not in allowed: bad+=[old,new]
    else:
        path=toks[i+1] if i+1<len(toks) else ""; i+=2
        bad.append(path)   # anything not a clean rename is out of scope
bad=[b for b in bad if b and b not in allowed]
if bad:
    print("OUT-OF-SCOPE STAGED PATHS:", *bad, sep="\n  "); sys.exit(1)
print("batch-scope OK: all staged paths belong to batch", batch)
PY
test $? -eq 0 || { echo "SCOPE CHECK FAILED — abort batch"; exit 1; }

# 5. No accidental deletions (a git mv shows as R; a bare D is forbidden)
git diff --cached --name-status | grep -E '^D' && { echo "UNEXPECTED DELETION"; exit 1; }

# 6. VALIDATOR GATE — require PASS 0/0
python3 tools/docs/validate_architecture_docs.py \
  > docs/architecture_knowledge_system/VALIDATION_RESULTS.txt 2>&1
grep -q "RESULT: PASS" docs/architecture_knowledge_system/VALIDATION_RESULTS.txt \
  || { echo "VALIDATOR NOT PASS"; exit 1; }

# 7. Commit ONLY this batch's already-staged renames (do NOT git add -A)
git commit -m "docs(archive): relocate batch $BATCH to docs/archive"

# 8. HUMAN REVIEW CHECKPOINT before the next batch
```

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

## 8. Post-execution (future)

1. Run the correct-in-place phase for `docs/README.md` / `docs/docs/README.md`
   (`08_CORRECT_IN_PLACE_QUEUE.md`) so indexes point at `docs/archive/…`.
2. Re-run the validator; PASS 0/0.
3. Update the AKS registry if any archived path was tracked.

## 9. Phase-8 statement

**None of the above was executed.** No batch ran, no `git mv` occurred, no
`docs/archive/` exists, no banner was inserted. This plan is inert until a future
phase is explicitly approved.
