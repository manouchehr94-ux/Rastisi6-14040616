# Phase 8 — Correct-In-Place Queue

> **DRY RUN ONLY.** These documents are **not** archived and **not** modified in
> Phase 8. They are queued for an in-place content correction in a **later**
> phase. Listing here is planning, not action.

## 1. What "correct in place" means

Some documents are **live** (they serve as navigational indexes or READMEs) but
their *content* is stale relative to the canonical Architecture Knowledge System.
Archiving them would break navigation; deleting them would remove an entry point.
The correct treatment is to **fix the content where it lives**, in a dedicated
future phase — not to move it.

Disposition: `CORRECT_IN_PLACE_LATER`. These docs are **excluded** from the
archive candidate set and are **not touched** during Phase 8.

## 2. The queue (2)

| # | Document | Why it stays | Correction needed (future phase) |
| --- | --- | --- | --- |
| 1 | `docs/README.md` | Top-level `docs/` index; still the human entry point into the docs tree; referenced by canonical layer | Update to point at `docs/architecture_knowledge_system/README.md` as the canonical entry; refresh/curate its links (some will become `docs/archive/…` after execution) |
| 2 | `docs/docs/README.md` | Stub index for the nested `docs/docs/product/**` tree | Refresh to reflect the protected canonical source docs and the archive relocation |

## 3. Explicit handling of `docs/README.md`

Per the governing instruction, `docs/README.md`:

- disposition = **`CORRECT_IN_PLACE_LATER`** (NOT archive, NOT delete);
- is **not modified in Phase 8**;
- its correction is scheduled for a later, separately-approved documentation
  hygiene phase, *after* archive execution, so that its link list can be updated
  to reflect the final `docs/archive/…` locations in a single consistent edit.

## 4. Correction principles (for the future phase)

1. Preserve the file path (no move).
2. Make the canonical README the primary pointer.
3. Update links en masse *after* archive execution so the index reflects reality.
4. Re-run the validator; require PASS 0/0.
5. Keep edits content-only; no structural/tree changes bundled in.

## 5. Not in this queue

Any doc that is merely historical belongs in `ARCHIVE_CANDIDATE` or
`KEEP_HISTORICAL_REFERENCE`, not here. The correct-in-place queue is reserved for
**live index/README** files with stale content. Exactly 2 documents qualify.
