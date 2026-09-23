# Phase 8 — Proposed Archive Tree

> **DRY RUN ONLY.** The tree below is *proposed*. It is **not** created in this
> phase. No directories exist yet under `docs/archive/`.

## 1. The two candidate layouts

### Option A — Flat thematic buckets

```
docs/archive/
├── architecture_history/
├── implementation_reports/
├── qa_evidence/
├── plans/
├── prototypes/
└── reference_material/
```

*Pros:* short paths; groups material by theme.
*Cons:* **loses original provenance** (you can no longer tell where a file lived);
requires per-file path decisions (increases move ambiguity and link-mapping work);
name collisions across source subtrees; harder to reverse cleanly.

### Option B — Provenance-preserving mirror (**CHOSEN**)

```
docs/archive/<original-relative-path-under-docs/>
```

Every archived unit keeps its original subtree, simply re-rooted under
`docs/archive/`. Example moves (illustrative, not executed):

```
docs/qa_evidence/…                         → docs/archive/qa_evidence/…
docs/architecture/STOREFRONT_BUILDER_V2_PHASE_7_REPORT.md
                                            → docs/archive/architecture/STOREFRONT_BUILDER_V2_PHASE_7_REPORT.md
docs/reference-kits/…                       → docs/archive/reference-kits/…
docs/docs/product/Final Result At Last/…    → docs/archive/docs/product/Final Result At Last/…
```

> **Scope note.** The Phase-3 inventory (this phase's authoritative scope of 519
> units) covers `docs/**` only. The two repository-root docs
> `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` and `…_REPORT.md` are **outside**
> that inventory scope, so they are **not** manifest rows and are **not**
> archived by this dry run. They are noted in `07_HIGH_RISK_OR_AMBIGUOUS_MOVES.md`
> as out-of-scope items for a future inventory pass.

*Pros:*
- **Provenance is self-documenting** — the archive path *is* the original path.
- **Deterministic move mapping** — `source → docs/archive/ + source[len("docs/"):]`;
  no per-file judgement, so the execution plan is mechanical and auditable.
- **Trivially reversible** — the inverse mapping restores the original path.
- **Link rewriting is a pure prefix insertion** (`docs/…` → `docs/archive/…`),
  which is easy to validate.

*Cons:* deeper paths; the `docs/archive/docs/product/…` double-`docs` segment
looks odd (it faithfully reflects the pre-existing `docs/docs/product/…` layout,
which is itself a historical quirk — Phase 8 does not "fix" it, to preserve provenance).

## 2. Decision

**Option B (provenance-preserving mirror) is chosen.** Safety and reversibility
outweigh path aesthetics. The manifest's `proposed_archive_path` column already
encodes this mapping for every `ARCHIVE_CANDIDATE` row.

## 3. Proposed archive tree (as populated by the 417 archive candidates)

Counts are the number of manifest `ARCHIVE_CANDIDATE` rows mapping under each
top-level archive subtree (the 6 asset-collection rows are counted within their
subtree):

```
docs/archive/
├── qa_evidence/                 (333)   ← group C: QA evidence textual + asset collection
├── architecture/                ( 19)   ← group A: V2 phase report/audit pairs (unreferenced)
├── reference-kits/              ( 19)   ← group D: reference kit assets + collection
├── template-references/         ( 16)   ← group D: template reference assets + collection
├── docs/product/Final Result At Last/  ( 12)  ← group D: novinshop + rastisi-site assets + collection
├── architecture_audits/         (  8)   ← group C: architecture audit pack + final_closure_pack
├── reports/                     (  4)   ← group B: implementation/product-entry/prelaunch reports (unreferenced)
├── references/                  (  3)   ← group D: beraito-exact-frontend reference assets + collection
├── audits/                      (  2)   ← group C: audit docs
└── prototypes/                  (  1)   ← group D: prototype assets collection
                                 ─────
                                  417
```

> The per-subtree numbers sum to **exactly 417**
> (333 + 19 + 19 + 16 + 12 + 8 + 4 + 3 + 2 + 1). `docs/archive/docs/` holds the
> `docs/docs/product/Final Result At Last/**` material (the double-`docs` segment
> faithfully mirrors the pre-existing layout). Exact per-row targets are
> authoritative in the manifest CSV `proposed_archive_path` column, not this summary.

## 4. Provenance & banner (future, not now)

When execution eventually happens (a **separate** approved phase), each moved doc
*may* optionally receive an archive banner (template in
`10_ARCHIVE_EXECUTION_PLAN.md §Archive banner template`). **No banner is inserted
in Phase 8**, and banners are an opt-in follow-up even during execution.

## 5. What is NOT in the archive tree

- The AKS tree (`docs/architecture_knowledge_system/**`).
- The eight protected canonical source docs.
- The 3 third-party/legal notices.
- The 33 `KEEP_HISTORICAL_REFERENCE` docs (stay at their original paths).
- The 2 `CORRECT_IN_PLACE_LATER` READMEs.
- The 44 `DEFER_REVIEW` plans/specs.


---

## `[PHASE 8 CORRECTIVE REVIEW]` — revisions to this document

The provenance-preserving scheme (Option B) is unchanged and remains correct.
The following statements above are **revised**:

- **"417 archive candidates" → the archive-candidate *logical* unit total is now
  406** (after adding 2 supplemental root docs as KEEP and downgrading 11
  reference-blocked files to KEEP). The true number of **exact git-tracked files**
  that would move is **3065**, not 417 — see
  `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv` and `10_ARCHIVE_EXECUTION_PLAN.md §2`.
- The per-subtree counts in §3 were **manifest-unit** counts. Exact tracked-file
  counts per source root are authoritative in `12_COLLECTION_EXPANSION_MANIFEST.csv`
  (e.g. `docs/qa_evidence` expands to 1408 archivable files, not 333 units;
  `docs/references/beraito-exact-frontend-v5` to 1476).
- A move mapping is **per-file** (`docs/<rel>` → `docs/archive/<rel>`); **no
  whole-directory `git mv`** is used for the 8 mixed source roots (see
  `14_DIRECTORY_MOVE_SAFETY_CHECK.md`).
