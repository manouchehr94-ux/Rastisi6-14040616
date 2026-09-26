# 03 — Document Classification

Status-candidate classification of the inventoried documents. The machine-readable per-document
registry is `02_DOCUMENT_INVENTORY.csv`; this document explains the buckets and lists the
architecturally-significant members. **Status candidates are provisional** — the authoritative
MATCHES_CODE / STALE / CONTRADICTS_CODE determination is made in Phase 4 against the code-derived
reality; Phase 3 does not judge correctness against code.

Status-candidate vocabulary: CURRENT_CANDIDATE, SUPPORTING, HISTORICAL, SUPERSEDED, DUPLICATE,
EVIDENCE_ONLY, PLAN_ONLY, DESIGN_INTENT, QA_EVIDENCE, UNKNOWN.

---

## 1. Distribution (513 individual textual docs + 6 collections)

| status_candidate | count | meaning |
|---|---:|---|
| QA_EVIDENCE | 359 | Point-in-time QA/audit/harness/certification evidence |
| EVIDENCE_ONLY | 42 | Reference kits / prototypes (design evidence, not system docs) |
| HISTORICAL | 39 | Implementation/phase/status reports describing past work |
| PLAN_ONLY | 31 | Forward plans/roadmaps (intent, may be partly executed) |
| DESIGN_INTENT | 20 | Specs/design charters describing intended architecture |
| SUPPORTING | 17 | Maps/notices/decision records/readmes that support the canon |
| CURRENT_CANDIDATE | 5 | Reads as authoritative current architecture |
| UNKNOWN | 0 | — |
| (collections) | 6 | Asset groups, all reference/evidence |

## 2. CURRENT_CANDIDATE (5) — the authoritative-architecture tier

| Path | Lines | Authored | Note |
|---|---:|---|---|
| `docs/docs/product/00_PROJECT_MASTER_REFERENCE.md` | 2189 | 2026-07-28→08-07 | Platform-wide master reference |
| `docs/docs/product/architecture/SAAS_ARCHITECTURE.md` | 720 | 2026-07-28 | Store tenant model, platform vs store |
| `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md` | 4508 | 2026-07-28→07-31 | The ADR record (ADR-1…ADR-101 cited in code) |
| `docs/docs/product/architecture/PAYMENT_ARCHITECTURE.md` | 229 | 2026-07-28 | Orders payment (PR1 foundation) |
| `docs/docs/product/architecture/SAAS_MIGRATION_PLAN.md` | 449 | 2026-07-28 | Staged PR sequence |

These carry the highest reconciliation priority in Phase 4. All are dated 2026-07-28 (foundation
era) and contain point-in-time PR-status narration — they describe the SaaS foundation as it stood
in late July 2026, not necessarily the frozen `5883a140` snapshot.

## 3. DESIGN_INTENT (20) — intended architecture (storefront reset + design engine)

Representative members:
- `docs/architecture/UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md` (2083L, "Proposed / Architecture
  Reset") — the intent behind the universal engine + presets that the code's R4/A8 now implements.
- `docs/architecture/UNIVERSAL_STOREFRONT_PHASE1_ARCHITECTURE.md`, `…PHASE2_RENDERER.md`,
  `…U1A_TEMPLATE_REGISTRY_DECISION.md`.
- `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` (1638L).
- `docs/superpowers/specs/*` design charters (R4, design engine, appearance convergence).
- `docs/docs/product/spec/{01-PROJECT-SPEC,02-BUILD-INSTRUCTIONS}.md`.
- `docs/storefront_templates/dark_digital_v2_DESIGN_CONTRACT.md`.

## 4. SUPPORTING (17)
Architecture maps and records that support the canon without themselves being the top-level spec:
`STOREFRONT_BUILDER_V2_LEGACY_RETIREMENT_MAP.md`, `…ROUTE_RENDERER_MAP.md`, `…REUSE_MATRIX.md`,
`…EXISTING_CAPABILITY_AUDIT.md`, `…DATA_LIFECYCLE.md`, `…PHASE_8_GAP_MATRIX.md`,
`docs/architecture_decisions/2026-09-05-…decision-baseline.md`,
`docs/docs/product/deployment/PRODUCTION_CONFIGURATION.md`, `docs/third_party/*` notices,
`docs/README.md`, `docs/docs/README.md`.

## 5. HISTORICAL (39)
Implementation/phase/status reports: `docs/docs/product/reports/PHASE_1B…1F…` +
`ADMIN_PANEL_COMPLETION_REPORT`, `PROTOTYPE_*`, `STOREFRONT_*`; `docs/architecture/STOREFRONT_
BUILDER_V2_PHASE_*_REPORT.md` (10); `docs/reports/PRELAUNCH_PHASE1–5…`, `PRODUCT_ENTRY_*`;
`docs/architecture_reviews/…`; `docs/project_status/2026-09-20-…`; root
`SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md`.

## 6. PLAN_ONLY (31)
Forward plans/roadmaps: `docs/superpowers/plans/*` (27), `docs/reports/*ROADMAP*` /
`*IMPLEMENTATION_PLAN*`, root `SIX_NEW_FAMILIES_IMPLEMENTATION_PLAN.md`,
`docs/architecture/STOREFRONT_BUILDER_V2_*IMPLEMENTATION_PLAN.md`.

## 7. QA_EVIDENCE (359) + EVIDENCE_ONLY (42) + collections (6)
QA evidence: `docs/qa_evidence/**` textual (340) + `docs/architecture_audits/**` (8) +
`docs/audits/**` (2) + a few audit-typed under `docs/architecture/`. Reference/prototype:
`docs/reference-kits/**`, `docs/references/**`, `docs/template-references/**`, `docs/prototypes/**`,
`docs/docs/product/Final Result At Last/**`. Asset-heavy groups are the 6 collection rows.

## 8. Notable mis-labeled-by-name docs (see doc 07)
- "Final Result At Last" folder = reference prototypes, not the running system → EVIDENCE_ONLY.
- `PRELAUNCH_PHASES_1_5_FINAL_AUDIT.md` "final audit" = dated pre-launch report → HISTORICAL/QA.
- `docs/architecture/*_AUDIT.md` phase audits = QA_EVIDENCE, not living architecture docs.

## 9. Duplicate/superseded candidates
Flagged provisionally here, detailed in doc 04: the SaaS foundation set (2026-07-28) vs the later
storefront/design-engine sets partly overlap on "storefront/appearance ownership"; multiple
"spec" homes; multiple storefront-builder audit/report generations. Final SUPERSEDED/DUPLICATE
labels are assigned in Phase 4 doc 06 after code reconciliation.
