# Phase 8 — Retention and Protection Rules

> **DRY RUN ONLY.** Defines what must never be archived and how long other
> material is retained. No enforcement action is taken in this phase.

## 1. Protection tiers

Protection is evaluated **before** any archive-candidate rule. A protected unit
can never receive `ARCHIVE_CANDIDATE`.

### Tier P0 — The Architecture Knowledge System tree (absolute)

Everything under `docs/architecture_knowledge_system/**` is **PROTECTED** and
receives `KEEP_CANONICAL_SUPPORT`. This is the canonical layer itself (Phases
1–7 + this phase); it is never archived, moved, or deleted by any archive action.

### Tier P1 — Protected canonical source documents (explicit allowlist)

These eight documents are the source-of-truth architecture docs that the
canonical pack depends on. They receive `KEEP_CANONICAL_SUPPORT` and must **never**
be archived:

| # | Path |
| --- | --- |
| 1 | `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` |
| 2 | `docs/docs/product/architecture/SAAS_ARCHITECTURE.md` |
| 3 | `docs/docs/product/architecture/PAYMENT_ARCHITECTURE.md` |
| 4 | `docs/docs/product/architecture/SAAS_MIGRATION_PLAN.md` |
| 5 | `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` |
| 6 | `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` |
| 7 | `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` |
| 8 | `docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md` |

### Tier P2 — Legal / third-party / vendored (compliance)

Third-party notices, license files, and vendored external documentation receive
`DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` and are retained untouched:

- `docs/third_party/**` (3 notices: `FRONTEND_DESIGN_PLUGIN_NOTICE.md`,
  `UI_UX_PRO_MAX_PALETTES_NOTICE.md`, `UI_UX_PRO_MAX_SKILL_NOTICE.md`)
- Any vendored `docs/ckeditor5/**` documentation
- Any `LICENSE` / `NOTICE` file

### Tier P3 — Reference back-pressure (dynamic protection)

Any document **not** in P0–P2 but **referenced by**:

- a canonical or domain AKS doc, **or**
- code, templates, or scripts

is **downgraded out of `ARCHIVE_CANDIDATE`** to `KEEP_HISTORICAL_REFERENCE`,
regardless of how historical it looks. This guarantees no archive move can break
a canonical cross-reference or force an automatic code edit.

## 2. Live-index correction rule

`docs/README.md` and `docs/docs/README.md` are **live index/README files** that
are known to be stale. They are **not archived** and **not modified in Phase 8**.
They receive `CORRECT_IN_PLACE_LATER`; their content fix is scheduled for a later
phase and tracked in `08_CORRECT_IN_PLACE_QUEUE.md`. The canonical entry point
remains `docs/architecture_knowledge_system/README.md`.

## 3. Retention model (for `ARCHIVE_CANDIDATE` material)

| Property | Rule |
| --- | --- |
| Deletion | **Never.** Archiving relocates via `git mv`; nothing is `rm`'d. |
| History | Preserved by the move; `git log --follow` continues to work. |
| Location | `docs/archive/<original-relative-path>` (provenance-preserving; see `04_PROPOSED_ARCHIVE_TREE.md`). |
| Content edits | None during the move. Optional archive banner is a separate, later, opt-in step. |
| Reversibility | Fully reversible by `git mv` back, or `git revert` of the move commit. |

## 4. Special-handling flags (manifest `special_handling` column)

| Flag | Meaning |
| --- | --- |
| `PROTECTED_AKS_TREE` | Inside the AKS canonical layer (Tier P0). |
| `PROTECTED_CANONICAL_SOURCE` | One of the eight Tier-P1 docs. |
| `LEGAL_OR_EXTERNAL` | Tier-P2 third-party/legal. |
| `REFERENCED_BY_CANONICAL` | Held in place because a canonical/domain AKS doc cites it (Tier P3). |
| `CODE_REFERENCE_DO_NOT_CHANGE_AUTOMATICALLY` | Held in place because code/templates/scripts cite it (Tier P3); code paths must not be auto-changed. |
| `LIVE_INDEX_FIX_LATER` | Live README to be corrected in place later. |
| `COLLECTION_ASSET_BUNDLE` | One of the 6 asset-collection rows. |
| `PLAN_COMPLETION_UNVERIFIED` | Plan/spec whose completion state needs human review. |

## 5. Protected-count summary

| Protection outcome | Disposition | Count |
| --- | --- | --- |
| AKS tree + P1 canonical sources + current-candidates + design/support | `KEEP_CANONICAL_SUPPORT` | 20 |
| Held by reference back-pressure / conservative historical | `KEEP_HISTORICAL_REFERENCE` | 33 |
| Live indexes to fix later | `CORRECT_IN_PLACE_LATER` | 2 |
| Legal / third-party | `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` | 3 |
| **Total protected / retained-in-place** | | **58** |

The remaining **461** units are either `ARCHIVE_CANDIDATE` (417) or `DEFER_REVIEW`
(44). 58 + 461 = **519**.

> ## `[PHASE 8 CORRECTIVE REVIEW]` — updated protected-count summary
>
> After adding 2 supplemental root docs + 1 collection-member record and
> downgrading 11 reference-blocked files to `KEEP_HISTORICAL_REFERENCE`, the
> corrected totals (scope **522**) are:
>
> | Disposition | Count |
> | --- | --- |
> | `KEEP_CANONICAL_SUPPORT` | 20 |
> | `KEEP_HISTORICAL_REFERENCE` | 47 |
> | `CORRECT_IN_PLACE_LATER` | 2 |
> | `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` | 3 |
> | **Retained / in place** | **72** |
> | `ARCHIVE_CANDIDATE` (logical units) | 406 |
> | `DEFER_REVIEW` | 44 |
>
> `72 + 406 + 44 = 522`. The Tier P3 reference back-pressure rule now also fires on
> **exact-path** references from retained/canonical/AKS docs into individual files
> that were previously represented only by a collection row.
