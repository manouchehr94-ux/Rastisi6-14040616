# 09 — Canonical Document Candidates

Documents that are the **best current basis** for a future canonical Architecture Knowledge System
— because they largely MATCH_CODE (Phase 4 doc 02) and carry authoritative design rationale. This
is a *candidate* list; Phase 4 does **not** designate canon or rewrite anything.

Selection criteria: high MATCHES_CODE ratio, breadth of authoritative coverage, and direct linkage
to code (e.g. cited by docstrings).

---

## Tier 1 — Strong canonical candidates (retain + update the few stale spots)

| Doc | Why | Caveat to fix in a later rewrite |
|---|---|---|
| `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` (106 ADRs) | The densest, most code-linked source; docstrings cite ADR-1…ADR-106; 22/32 matrix claims trace here | Mark ADR-93 superseded-by ADR-102 (SU-1); some ADRs describe intent the code partially violates (X2) — annotate, don't rewrite |
| `docs/docs/product/architecture/SAAS_ARCHITECTURE.md` | Accurate tenant/platform model (CL-01/04/06/07) | Drop/stamp the stale PR-status prose (S2) |
| `docs/docs/product/architecture/PAYMENT_ARCHITECTURE.md` | Accurate gateway flow, concurrency, COD, refund scope (CL-09/10/11/12) | Complete the §4 state-ownership to list all 3 payment_status writers + REFUNDED (S1/H1) |
| `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` | Broad platform reference; ownership taxonomy; store-resolution principles | Reconcile PR-numbering vs migration plan (CL-30); it is foundation-era |

## Tier 2 — Canonical for the storefront domain (needs de-confliction)

| Doc | Why | Caveat |
|---|---|---|
| `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` | Explains the current R4/universal-engine architecture's intent (CL-25) | Labelled "Proposed"; is now realized — restamp as realized |
| `docs/architecture/STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md` | Authoritative map of what was retired (matches code: registries absent) | Companion; keep as the de-confliction key for Cluster C1 |

## Tier 3 — Supporting canon
- `docs/docs/product/architecture/SAAS_MIGRATION_PLAN.md` — the migration rationale (mark PR12
  legacy-removal as pending — DI-2).
- `docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md` — operations/config reference
  (referenced by settings; matches env_config surface).
- `docs/third_party/*` notices — licensing canon.

## The authoritative code-derived layer (already canonical within this system)
The Phase 1 (`phase1_code_discovery/`) + Phase 2 (`phase2_validation/`) artifacts are the
**code-derived source of truth**. A future canonical Architecture Knowledge System should pair each
domain's design-intent doc (above) with its Phase 1/2 code-derived doc, keeping the distinction:
- **What the code does** → Phase 1/2 artifacts (authoritative for runtime behavior).
- **Why / intended** → the Tier 1–3 docs above (authoritative for rationale).

## Domains with NO canonical candidate (must be authored later, not selected)
Per doc 08 Part C readiness: **content (D10)**, **notifications (D13)**, **blog (D15)** have no
canonical-candidate doc; **customers (D3)**, **cart (D5)**, **SMS (D12)** are POOR. These are gaps
to fill via future Domain Knowledge Packs, not documents to select now.

---

## Not-canonical (explicitly)
- QA_EVIDENCE (359) and EVIDENCE_ONLY (42) docs — never canonical; evidence only.
- Family-era + superseded V2 phase docs — historical (doc 06); not canonical.
- `docs/README.md` — contradicts code (X1); not canonical until corrected.
