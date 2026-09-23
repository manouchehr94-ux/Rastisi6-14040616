# Phase 8 — Directory-Move Safety Check `[PHASE 8 CORRECTIVE REVIEW]`

> **DRY RUN ONLY.** No directory was moved. This check *proves*, per source
> directory, whether a whole-directory `git mv` is safe, and forbids it wherever
> a directory contains any tracked descendant that is not authorized to move.

## 1. Rule

A whole-directory `git mv <dir> docs/archive/<dir>` is **allowed only if**:

```
archive_descendant_count == tracked_descendant_count
AND retained_descendant_count == 0
AND deferred_descendant_count == 0
AND other_descendant_count == 0
```

If even one tracked descendant is retained (KEEP/legal/correct-in-place),
deferred, or otherwise not `safe_to_move`, the whole-directory move is
**FORBIDDEN**; that directory must be archived by **selective per-file moves**
(from `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`) that leave the protected files at
their original paths.

`tracked_descendant_count` is measured with `git ls-files -z` (NUL-delimited) so
that filenames containing spaces or non-ASCII (Persian) characters are counted
exactly and never split or quoted.

## 2. Results

| Source directory | Tracked | Archive | Retained | Deferred | Other | Whole-dir move |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| `docs/architecture` | 32 | 18 | 13 | 1 | 0 | **NO** |
| `docs/audits` | 2 | 1 | 1 | 0 | 0 | **NO** |
| `docs/docs/product/Final Result At Last` | 75 | 75 | 0 | 0 | 0 | **YES** |
| `docs/docs/product/reports` | 12 | 6 | 6 | 0 | 0 | **NO** |
| `docs/prototypes` | 3 | 1 | 2 | 0 | 0 | **NO** |
| `docs/qa_evidence` | 1416 | 1408 | 8 | 0 | 0 | **NO** |
| `docs/reference-kits` | 49 | 49 | 0 | 0 | 0 | **YES** |
| `docs/references/beraito-exact-frontend-v5` | 1477 | 1476 | 1 | 0 | 0 | **NO** |
| `docs/reports` | 18 | 4 | 12 | 2 | 0 | **NO** |
| `docs/template-references` | 28 | 27 | 1 | 0 | 0 | **NO** |

- **Whole-directory move ALLOWED (2):** `docs/docs/product/Final Result At Last`,
  `docs/reference-kits`. (Every tracked descendant is `safe_to_move`.)
- **Whole-directory move FORBIDDEN (8):** `docs/architecture`, `docs/audits`,
  `docs/docs/product/reports`, `docs/prototypes`, `docs/qa_evidence`,
  `docs/references/beraito-exact-frontend-v5`, `docs/reports`,
  `docs/template-references`.

> Even for the 2 "allowed" directories, execution derives its `git mv` commands
> from the exact per-file rows in `13_...` — the whole-directory shortcut is
> permitted but **not required**, and the per-file manifest remains authoritative.

## 3. Why the previously-`PURE` audit directories are now FORBIDDEN / absent

The original dry run treated `docs/architecture_audits/**` and `docs/audits/**`
as fully archivable. The corrective reference scan (path-exact) found that
**8 files under `docs/architecture_audits/`** (the top-level audit plus all 7
`final_closure_pack/` docs) and **1 file under `docs/audits/`** are cited by a
**retained** doc that stays in place
(`docs/architecture_decisions/2026-09-05-storefront-appearance-convergence-decision-baseline.md`
and the AKS Phase-3 inventory). Those files were **downgraded to
`KEEP_HISTORICAL_REFERENCE`**. As a result:

- `docs/architecture_audits/` no longer has any archivable descendant, so it is
  not even a move candidate (removed from the table).
- `docs/audits/` now has 1 archivable + 1 retained → **mixed → FORBIDDEN**.

This is exactly the class of unsafe whole-directory move the corrective pass was
asked to eliminate.

## 4. Blocking-reference safety proof

For every one of the **3065** rows in `13_ARCHIVE_EXECUTION_PATH_MANIFEST.csv`,
`safe_to_move = TRUE` and there is **no blocking incoming reference** (no
reference from live code/scripts/templates, and no reference from a retained /
canonical / AKS document). References that exist only from **other
archive-candidate documents** (which move together) or from **`DEFER_REVIEW`
plans/specs** (which a human reviews before any move) are non-blocking and are
recorded in the manifest's `incoming_reference_count` for transparency.

## 5. Conclusion

No unsafe whole-directory move remains in the plan. The 8 mixed/forbidden
directories will be archived by selective per-file `git mv` operations that
leave every protected/retained/deferred file untouched at its original path.
