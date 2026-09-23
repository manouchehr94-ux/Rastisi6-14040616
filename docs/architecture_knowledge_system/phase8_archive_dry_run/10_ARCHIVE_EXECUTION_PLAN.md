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
- [ ] `03_ARCHIVE_DISPOSITION_MANIFEST.csv` re-verified: 417 `ARCHIVE_CANDIDATE`
  rows, all `link_break_risk = LOW`, `incoming_repo_links_count = 0`.

## 1. Global rules

1. **`git mv` only.** Never `rm`, never `mv` outside git, never delete.
2. **One batch = one commit.** No mixing batches.
3. **Validator gate after every batch.** If not PASS 0/0 → stop, roll back that batch.
4. **No code/test/migration edits.** Production surfaces stay frozen.
5. **No banner insertion during moves** (banners are an optional later step, §7).
6. **Provenance mapping:** `docs/<rel>` → `docs/archive/<rel>` (root-preserving).

## 2. Batch plan (A–E)

Batches are ordered lowest-risk → highest-visibility. Counts come from the manifest.

| Batch | Source scope | Target | Rows | Link risk |
| --- | --- | --- | --- | --- |
| **A** | `docs/qa_evidence/**` (textual + asset collection) | `docs/archive/qa_evidence/**` | 333 | LOW (0 refs) |
| **B** | `docs/architecture_audits/**`, `docs/audits/**` | `docs/archive/architecture_audits/**`, `docs/archive/audits/**` | 10 | LOW |
| **C** | `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_*` (unreferenced) + group-A/B reports in `docs/reports/**`, `docs/docs/product/reports/**` | mirror under `docs/archive/…` | 23 | LOW |
| **D** | Reference material: `docs/reference-kits/**`, `docs/references/**` (unreferenced), `docs/template-references/**`, `docs/prototypes/**` (unreferenced), `docs/docs/product/Final Result At Last/**` | mirror under `docs/archive/…` | 51 | LOW |
| **E** | *(reserved — no auto-archive)* superpowers plans/specs remain `DEFER_REVIEW`; **Batch E is intentionally empty** until human review reclassifies any item | — | 0 | — |
|  | **Total moved** | | **417** | |

> 333 + 10 + 23 + 51 + 0 = **417** = the `ARCHIVE_CANDIDATE` count. Batch E moves
> nothing by design; it exists as the placeholder for post-review plan/spec archiving.

### 2.1 Per-batch derivation of the exact file list

Do **not** hand-type paths. Derive each batch's file set from the manifest:

```bash
# Example: emit the git mv commands for a given batch prefix, from the manifest.
python3 - "$PREFIX" <<'PY'
import csv, sys, shlex
prefix = sys.argv[1]
p = "docs/architecture_knowledge_system/phase8_archive_dry_run/03_ARCHIVE_DISPOSITION_MANIFEST.csv"
for r in csv.DictReader(open(p, encoding="utf-8")):
    if r["proposed_disposition"] != "ARCHIVE_CANDIDATE":
        continue
    src = r["source_path"]
    if "**" in src:            # collection row -> handled by directory-level git mv
        continue
    if not src.startswith(prefix):
        continue
    dst = r["proposed_archive_path"]
    print("mkdir -p", shlex.quote(dst.rsplit('/',1)[0]))
    print("git mv", shlex.quote(src), shlex.quote(dst))
PY
```

Asset **collection** rows (the 6 `**` rows) are moved as whole directories with a
single `git mv <dir> docs/archive/<dir>` after their textual siblings.

## 3. Per-batch procedure (repeat for A→D)

```bash
# 1. Confirm clean tree
git status --porcelain    # expect empty

# 2. Generate + review the batch's git mv script (see §2.1); eyeball it
# 3. Execute the git mv commands for the batch (git mv ONLY)
# 4. Verify nothing left behind / no deletions
git status --porcelain | grep -E '^ ?D' && echo "UNEXPECTED DELETION" && exit 1

# 5. VALIDATOR GATE
python3 tools/docs/validate_architecture_docs.py \
  > docs/architecture_knowledge_system/VALIDATION_RESULTS.txt 2>&1
tail -n 5 docs/architecture_knowledge_system/VALIDATION_RESULTS.txt   # require PASS 0/0

# 6. Commit the batch
git add -A
git commit -m "docs(archive): relocate batch <X> (<n> files) to docs/archive"

# 7. HUMAN REVIEW CHECKPOINT before starting the next batch
```

## 4. Rollback

Per batch, before pushing:

```bash
# Undo an uncommitted batch:
git checkout -- . && git clean -nd     # inspect, then git reset if git mv staged
# Undo a committed-but-unpushed batch:
git revert --no-edit <batch_commit_sha>      # reinstates original paths via git
```

Because every step is a `git mv`, `git revert` of the batch commit fully restores
the original tree. No content is lost.

## 5. Validator gates (mandatory)

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
| G0 | Before batch A | Is execution approved? Baseline still frozen? |
| G1 | After batch A | 333 QA-evidence moves look correct? Validator PASS? |
| G2 | After batch B/C/D | Reports/audits/reference material correct? Validator PASS? |
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
