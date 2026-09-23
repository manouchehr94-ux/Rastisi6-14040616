# Phase 8 — Archive Policy

> **DRY RUN ONLY.** This document defines the *policy* by which archive
> dispositions were assigned. It authorises no execution.

## 1. Purpose

RastiSi's `docs/` corpus has grown to **519 inventoried units** (513 textual
documents + 6 binary/asset collections), the large majority of which are
historical implementation reports, phase audits, and QA evidence produced during
the storefront-builder and SaaS build-out. The Architecture Knowledge System
(AKS) canonical layer now provides the single source of architectural truth.

The archive policy exists to **reduce navigational noise** in `docs/` *without*
losing history and *without* breaking any live reference — by relocating
superseded material into a provenance-preserving `docs/archive/` tree in a
**later** phase.

## 2. Guiding principles

1. **Preserve by default.** The default disposition for any document whose fate
   is not certain is to *keep* it (in place or as historical reference), never to
   delete. There is **no `DELETE` disposition** in this system.
2. **Never break a live link.** Any document referenced by the canonical pack or
   by code/templates/scripts is held in place. Archiving must never require an
   automatic edit to source code.
3. **History is relocated, never rewritten.** Archiving = `git mv` into
   `docs/archive/`. Content is not altered (banners are a *future*, separate,
   opt-in step). Git history is preserved by the move.
4. **Protection beats candidacy.** Protection rules are evaluated *before*
   archive-candidate rules. A protected doc can never become an archive candidate.
5. **Ambiguity defers to a human.** Documents whose completion/supersession state
   cannot be verified in a dry run are marked `DEFER_REVIEW`, not archived.
6. **Counts must reconcile.** Every inventoried unit gets exactly one disposition;
   the six totals sum to the inventory scope with no remainder.

## 3. Disposition vocabulary (exactly one per unit)

| Disposition | Meaning | Moves in a future phase? |
| --- | --- | --- |
| `KEEP_CANONICAL_SUPPORT` | Actively supports the current/canonical architecture; stays in place | No |
| `KEEP_HISTORICAL_REFERENCE` | Historical, but still referenced or valuable enough to keep in place | No |
| `CORRECT_IN_PLACE_LATER` | Live index/README that is known-stale; content fix scheduled for a later phase | No (fixed, not moved) |
| `ARCHIVE_CANDIDATE` | Superseded/historical, no live dependency; eligible to move to `docs/archive/` | Yes (via `git mv`) |
| `DEFER_REVIEW` | Completion/supersession unverified; needs human judgement before any action | No (pending review) |
| `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL` | Third-party / license / vendored notice; retained untouched for compliance | No |

## 4. Decision order (first match wins)

The disposition engine evaluates each inventory row against these rules **in
order**; the first rule that matches assigns the disposition:

1. **Inside the AKS tree** (`docs/architecture_knowledge_system/**`)
   → `KEEP_CANONICAL_SUPPORT` (PROTECTED).
2. **Third-party / legal / vendored** (`docs/third_party/**`, ckeditor5 vendor
   docs, `LICENSE`/`NOTICE` files) → `DO_NOT_TOUCH_LEGAL_OR_EXTERNAL`.
3. **Protected canonical source doc** (the eight explicit paths in
   `02_RETENTION_AND_PROTECTION_RULES.md`) → `KEEP_CANONICAL_SUPPORT`.
4. **Live index/README known-stale** (`docs/README.md`, `docs/docs/README.md`)
   → `CORRECT_IN_PLACE_LATER`.
5. **Asset collection row** (the 6 `COLLECTION` rows) → `ARCHIVE_CANDIDATE`
   (bundle-archived with provenance).
6. **Phase-4 current-candidate** (`CURRENT_CANDIDATE`) → `KEEP_CANONICAL_SUPPORT`.
7. **Superpowers plan/spec** (`docs/superpowers/**`) → `DEFER_REVIEW`
   (completion unverified in a dry run).
8. **Phase-4 archive group A–E match**:
   - referenced by a canonical/domain AKS doc → `KEEP_HISTORICAL_REFERENCE`;
   - else referenced by code/templates/scripts → `KEEP_HISTORICAL_REFERENCE`
     (HIGH risk; code paths must not be auto-changed);
   - else → `ARCHIVE_CANDIDATE`.
9. **Status fallback** for anything unmatched:
   - `HISTORICAL` / `EVIDENCE_ONLY` / `QA_EVIDENCE` → `KEEP_HISTORICAL_REFERENCE`;
   - `PLAN_ONLY` → `DEFER_REVIEW`;
   - `DESIGN_INTENT` / `SUPPORTING` → `KEEP_CANONICAL_SUPPORT`.
10. **Absolute fallback** → `KEEP_HISTORICAL_REFERENCE` (conservative PRESERVE).

## 5. Phase-4 archive groups (source of `ARCHIVE_CANDIDATE`)

| Group | Description | Example paths |
| --- | --- | --- |
| A `architecture_history` | Superseded architecture history: root six-families plan/report + V2 phase report/audit pairs | `SIX_NEW_FAMILIES_IMPLEMENTATION_*`, `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_*` |
| B `implementation_reports` | Completed implementation / prelaunch / product-entry reports | `docs/reports/PRELAUNCH_*`, `docs/reports/PRODUCT_ENTRY_*`, `reports/PHASE_1[B-F]*`, `ADMIN_PANEL_COMPLETION_REPORT.md` |
| C `audits_qa` | Point-in-time audits + QA evidence | `docs/architecture_audits/**`, `docs/audits/**`, `docs/qa_evidence/**` |
| D `reference_material` | External/reference kits, prototypes, final-result assets | `docs/reference-kits/**`, `docs/references/**`, `docs/template-references/**`, `docs/prototypes/**`, `docs/docs/product/Final Result At Last/**` |
| E `plans` | Superpowers plans/specs — **not archived by policy**; routed to `DEFER_REVIEW` | `docs/superpowers/plans/**`, `docs/superpowers/specs/**` |

> Note: Group E is intentionally *not* auto-archived. Plan/spec completion state
> is not verifiable in a dry run, so every superpowers plan/spec is `DEFER_REVIEW`.

## 6. Confidence scoring

Each manifest row carries a `confidence` field:

- `HIGH` — protection rules and legal/external (deterministic).
- `MEDIUM` — archive candidates and canonical-support inferences.
- `LOW` — deferred items and conservative fallbacks (explicitly needs review).

## 7. Relationship to DR-1…DR-8

This policy does **not** resolve any Disposition Recommendation. Where a document
is the only surviving explanation of an **OPEN** DR, it is held as
`KEEP_HISTORICAL_REFERENCE` or `DEFER_REVIEW` (see `07_HIGH_RISK_OR_AMBIGUOUS_MOVES.md`).
