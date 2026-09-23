# 06 — Superseded and Duplicate Documents

`SUPERSEDED` = a later document (or a later decision within the same document) replaces an earlier
one. `DUPLICATE` = two+ documents describe the same subsystem such that they compete for "which is
authoritative." Phase 4 identifies these; **no archive/move/delete is performed** (that is a later,
separately-authorized phase).

---

## Superseded

### SU-1 — CL-23 — ADR-93 superseded by ADR-102 (owner identity)
```
EARLIER (ADR-93): "Owner Identity Is Email/Password, Structurally Separate From Storefront
  Customer Identity."
LATER (ADR-102): "Platform Configuration Singleton, and Owner Identity Becomes Mobile OTP
  (Shared With Customer Phone Identity by Design)."
CODE REALITY: The code implements the ADR-102 model — mobile-OTP owner auth and
  get_or_create_owner_by_phone shared-identity (username == phone). Email/password remains a
  legacy owner login path but the shared phone identity is the current design.
CLASSIFICATION: SUPERSEDED (within the ADR record itself). ADR-93 should be marked superseded-by
  ADR-102, not deleted (ADRs are an append-only decision log by convention).
```

### Document-level supersession (from Phase 3 clusters)
- **Family-era storefront docs** (root `SIX_NEW_FAMILIES_*`, family partials referenced in the
  retirement map) are **SUPERSEDED** by the Universal V2 / R4 / A8 generation (CL-25/26). The
  retirement map itself documents the supersession.
- **`STOREFRONT_BUILDER_V2_PHASE_*` report/audit pairs** are progressively superseded by the later
  Phase-5 / final_closure_pack material for "current state" purposes (they remain historical).
- **`docs/docs/product/spec/{01-PROJECT-SPEC,02-BUILD-INSTRUCTIONS}`** (foundation era) are
  superseded for the storefront by `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` and
  `RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md`.

## Duplicate / overlapping (no single authoritative source)
From Phase 3 doc 04 clusters — these are *document-level* duplication, not claim-level:

| Cluster | Overlap | Note |
|---|---|---|
| C1 Storefront builder | 60+ docs, 4 generations, 3–4 homes | Heaviest duplication; latest (R4/A8) matches code, earlier superseded |
| C2 Spec homes | 3 "spec" homes (product/spec, docs/specs, superpowers/specs) | No single "the spec" |
| C3 Audit/evidence | 4 evidence homes (architecture_audits, audits, qa_evidence, *_AUDIT.md) | Several read as architecture but are QA |
| C5 Master-ref vs SaaS-arch | 00_PROJECT_MASTER_REFERENCE overlaps SAAS_ARCHITECTURE on platform/store model | Complementary, not contradictory |
| C6 Product-entry reports | 5 overlapping product-entry docs | Mostly historical |
| C7 Reference "target" kits | 3+ reference design kits + REFERENCE_STOREFRONT_EDITABLE_TARGET | Evidence, not architecture |

No claim in the matrix was classified `DUPLICATE` because duplication here is a **document-set**
property (same subsystem, many docs), not a single-claim property. The formal DUPLICATE
determination for archival is captured at document/cluster level in doc 10 (archive candidates).

## Internal doc-vs-doc inconsistency (not code-reconcilable)
- **CL-30** — `00_PROJECT_MASTER_REFERENCE.md` narrates foundational PRs as **#19/#20/#21** while
  `SAAS_MIGRATION_PLAN.md` numbers the same foundation work as **PR 1–14**. This is an internal
  numbering inconsistency between two docs (`UNVERIFIABLE` against code; see doc 07). It does not
  affect the code but would confuse a reader trying to trace "which PR added what."

---

## Handling guidance (for a later, authorized phase — not now)
- Mark ADR-93 as superseded-by ADR-102 **in place** (append a note), preserving the log.
- Family-era + early V2 storefront docs → archive-in-place with a "superseded by Universal/R4/A8"
  banner; keep as history.
- Consolidate the 3 spec homes and 4 evidence homes under the future canonical taxonomy.
- Reconcile the PR-numbering narrative between master-ref and migration-plan.
