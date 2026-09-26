# Documentation Authority Model

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 3 / Phase 4
```

Defines which sources are authoritative when they disagree. This is the tie-breaker rule for the
entire RastiSi documentation corpus.

---

## The authority hierarchy

```
LEVEL 1  —  Current code + tests at the verified production checkpoint (5883a140)
            The ultimate source of "what the system does right now."

LEVEL 2  —  Canonical Architecture Knowledge System
            docs/architecture_knowledge_system/canonical/** + the Phase 1/2 code-derived
            artifacts (phase1_code_discovery/**, phase2_validation/**) + the domain packs
            (domains/**). Derived from and verified against Level 1.

LEVEL 3  —  Accepted ADR / design-intent sources
            docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md (ADR-1..ADR-106),
            SAAS_ARCHITECTURE.md, PAYMENT_ARCHITECTURE.md, SAAS_MIGRATION_PLAN.md,
            00_PROJECT_MASTER_REFERENCE.md, UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md,
            STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md. Explain WHY; do not override Level 1/2.

LEVEL 4  —  Supporting implementation / QA evidence
            phase/implementation reports, prelaunch reports, audits, qa_evidence/**,
            superpowers/** plans+specs. Historical record of HOW; not current truth.

LEVEL 5  —  Historical / superseded / archive material
            family-era docs, superseded storefront generations, reference kits/prototypes,
            "Final Result At Last" prototypes, stubs. Kept for history only.
```

## How conflicts are resolved
1. **Level 1 wins on runtime behavior.** If a document (any level ≥3) claims behavior that the code
   does not exhibit, the code is authoritative and the document is classified STALE or
   CONTRADICTS_CODE (Phase 4 docs 03/04). The document is **not** edited to match code silently, and
   the code is **not** changed to match the document — the disagreement is recorded and, where a
   decision is needed, raised as a DR item.
2. **Level 2 is the navigation + interpretation layer.** When Level 3+ docs are ambiguous or
   contradictory, the canonical layer (this folder) is the working reference; it cites Level 1 for
   every substantive claim.
3. **Level 3 explains intent, not current state.** ADRs/specs are authoritative for *design
   rationale* and for *why* the architecture is shaped as it is. They may be SUPERSEDED by later
   ADRs (e.g. ADR-93 → ADR-102) or partially unrealized (e.g. SAAS_MIGRATION_PLAN PR12 legacy
   removal pending).
4. **Levels 4–5 never override anything.** They are evidence/history.

## ⚠️ The naming fallacy
> **A document being named `FINAL`, `MASTER`, `SPEC`, `AUDIT`, or `PLAN` does NOT make it
> authoritative.**

Concrete examples in this repo (Phase 3 doc 07):
- `docs/docs/product/Final Result At Last/**` — sounds authoritative; is **reference prototypes** (Level 5).
- `docs/reports/PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` — "final audit"; is a **dated report** (Level 4).
- `docs/architecture/*_PHASE_*_AUDIT.md` — "audit"; is **point-in-time QA** (Level 4).
- `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` — one of **three** "spec" homes (Level 3 intent).
- `docs/README.md` — reads authoritative; **contradicts code** (claims a backend/frontend/infra
  layout that does not exist — Phase 4 X1). Level 5 until corrected.

## Freshness rule
A document is "current" only relative to a code checkpoint. Every canonical/domain document records
`code_baseline` and `last_verified_against_code`. If production advances past `5883a140`, a delta
re-verification is required before trusting Level 2 documents as current.

## Where authority is recorded per document
- Phase 3 inventory: [`../phase3_document_inventory/02_DOCUMENT_INVENTORY.csv`](../phase3_document_inventory/02_DOCUMENT_INVENTORY.csv)
  (status candidates).
- Phase 4 reconciliation buckets: [`../phase4_reconciliation/`](../phase4_reconciliation/)
  (MATCHES_CODE / STALE / CONTRADICTS_CODE / HISTORICAL / DESIGN_INTENT_ONLY / SUPERSEDED /
  DUPLICATE / UNVERIFIABLE).
- Canonical candidates: [`../phase4_reconciliation/09_CANONICAL_DOCUMENT_CANDIDATES.md`](../phase4_reconciliation/09_CANONICAL_DOCUMENT_CANDIDATES.md).

## Handling stale/historical docs (this phase)
Old documents are **not** edited, moved, renamed, archived, or deleted in this phase. Where an old
document is stale, it is **labelled from the new canonical system** (here and in the domain
`HISTORICAL_CONTEXT.md` files), never modified in place. Archive execution is a separate later phase.
