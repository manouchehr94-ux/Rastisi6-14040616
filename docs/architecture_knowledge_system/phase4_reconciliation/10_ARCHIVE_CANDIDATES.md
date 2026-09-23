# 10 — Archive Candidates

Documents that a future, separately-authorized phase should consider **archiving** (moving to an
`archive/` grouping with a clear label) rather than deleting. **Nothing is archived, moved, or
deleted in Phase 4.** Each candidate states WHY.

Archiving preserves history and rationale while removing the from the "current architecture"
surface so they stop competing with canon.

---

## A — Superseded storefront generations (Cluster C1)

| Candidate | Why archive | Keep because |
|---|---|---|
| Root `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md` + `…REPORT.md` | Family architecture retired (registries deleted); superseded by universal engine (CL-25/26) | Historical record of the pre-reset approach |
| `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_0_5…PHASE_8_*` (report+audit pairs, ~24 docs) | Point-in-time build phase records; superseded by current-state material | Build narrative / rationale |
| Family template partials referenced in the retirement map | Code deleted | Referenced only by the retirement map (which stays as the de-confliction key) |

## B — Pre-launch & product-entry reports

| Candidate | Why archive |
|---|---|
| `docs/reports/PRELAUNCH_PHASE1–5_*` + `PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` | Dated pre-launch reports; "FINAL_AUDIT" name misleads about current authority |
| `docs/reports/PRODUCT_ENTRY_*` (4) + `docs/docs/product/reports/PROTOTYPE_*` | Overlapping historical product-entry/prototype reports |
| `docs/docs/product/reports/PHASE_1B…1F…`, `ADMIN_PANEL_COMPLETION_REPORT.md` | Implementation reports; historical |

## C — QA evidence masquerading as architecture

| Candidate | Why archive |
|---|---|
| `docs/architecture_audits/**` (incl. `final_closure_pack/`) | Point-in-time 2026-09-05 appearance-convergence QA; "final_closure" name overstates authority |
| `docs/audits/**`, `docs/qa_evidence/**` | QA evidence collections; keep as evidence, move out of the architecture surface |
| `docs/architecture/*_PHASE_*_AUDIT.md` | Phase QA, not living architecture |

## D — Reference kits / prototypes

| Candidate | Why archive |
|---|---|
| `docs/docs/product/Final Result At Last/**` | Reference prototypes; folder name misleads as authoritative |
| `docs/reference-kits/**`, `docs/references/**`, `docs/template-references/**` | External/reference design kits; evidence only |
| `docs/prototypes/**` | HTML/UI prototypes |

## E — Misleading-status stubs / plans

| Candidate | Why archive or fix |
|---|---|
| `docs/README.md` | Contradicts code (X1: backend/frontend/infra/docker layout) — **fix** (correct) rather than archive |
| `docs/docs/README.md` | Near-empty stub |
| `docs/superpowers/plans/**` (27) | Dated implementation plans; historical once executed (keep as history) |

---

## Explicitly NOT archive candidates
- Tier 1–3 canonical candidates (doc 09): SAAS_DOMAIN_DECISIONS, SAAS_ARCHITECTURE,
  PAYMENT_ARCHITECTURE, 00_PROJECT_MASTER_REFERENCE, SAAS_MIGRATION_PLAN, PRODUCTION_CONFIGURATION,
  UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC, LEGACY_RETIREMENT_MAP, third_party notices.
- The Phase 1–4 knowledge-system artifacts themselves.

## Guardrail
This list is advisory for a future phase. **Do not** archive/move/delete now. When executed, prefer
`git mv` into an `archive/` tree with a header banner ("ARCHIVED — historical; superseded by …"),
never `rm`, to preserve the record.
