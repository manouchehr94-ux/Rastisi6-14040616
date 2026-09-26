# 04 — Duplicate and Overlap Clusters

Documents that describe the **same subsystem** in more than one place, or whose scope overlaps
enough to create "which one is authoritative?" confusion. Final DUPLICATE/SUPERSEDED labels are
assigned in Phase 4 (doc 06) after code reconciliation; Phase 3 identifies the clusters.

---

## Cluster C1 — Storefront builder architecture (largest overlap)
The single most over-documented subsystem. At least four overlapping generations describe the
storefront builder:

| Generation | Representative docs | Home |
|---|---|---|
| Families (pre-reset) | root `SIX_NEW_FAMILIES_IMPLEMENTATION_{PLAN,REPORT}.md`; family partials referenced in retirement map | root + `docs/architecture/` |
| Universal V2 reset (design intent) | `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md`, `UNIVERSAL_STOREFRONT_PHASE1_ARCHITECTURE.md`, `…PHASE2_RENDERER.md`, `…U1A_TEMPLATE_REGISTRY_DECISION.md`, `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` | `docs/architecture/`, `docs/specs/` |
| V2 phase build (reports/audits) | `STOREFRONT_BUILDER_V2_PHASE_0_5…PHASE_8_*` (report+audit pairs), `…LEGACY_RETIREMENT_MAP`, `…ROUTE_RENDERER_MAP`, `…REUSE_MATRIX` | `docs/architecture/` |
| R4 / Design Engine / A8 / Phase-5 | `docs/superpowers/plans+specs/*` (many), `docs/architecture_audits/final_closure_pack/*`, `docs/project_status/2026-09-20-…` | `docs/superpowers/`, `docs/architecture_audits/` |

**Overlap risk:** a reader asking "how does the storefront builder work?" faces 60+ documents
across 4 homes and 3 naming conventions. The code reality (Phase 1/2): R4 is canonical, legacy R3
fail-closed, A8 = 50 ready templates, families retired. The *design-intent* docs (Universal V2
spec) and the *retirement map* are the ones that match code direction; the family docs are
superseded; the V2 phase reports are historical.

## Cluster C2 — "Spec" homes (three)
The same "product/builder specification" concept lives in three places:
- `docs/docs/product/spec/{01-PROJECT-SPEC,02-BUILD-INSTRUCTIONS}.md` (foundation era)
- `docs/specs/RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` (2026-08-14)
- `docs/superpowers/specs/*` design charters (2026-08→09)
**Overlap risk:** no single "the spec." Different eras, no cross-references stamped with a code commit.

## Cluster C3 — Audit/evidence homes (four)
`docs/architecture_audits/`, `docs/audits/`, `docs/qa_evidence/`, and `*_AUDIT.md` files under
`docs/architecture/` and `docs/reports/` all hold audit-style content. Several read as
"architecture" but are point-in-time QA. **Risk:** QA evidence functioning as architecture doc.

## Cluster C4 — Payment/SaaS-billing description (two audiences, low duplication)
- `docs/docs/product/architecture/PAYMENT_ARCHITECTURE.md` (orders/storefront payment — PR1)
- `docs/reports/PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md` + `PHASE4_ZIBAL_MERCHANT_PAYMENTS.md`
  (SaaS platform billing vs merchant payments)
These describe the *two separate money systems* Phase 1 identified (storefront vs platform). Not
true duplicates, but a reader must know which is which. Low overlap; both useful.

## Cluster C5 — Master reference vs SaaS architecture
`00_PROJECT_MASTER_REFERENCE.md` (2189L) overlaps `SAAS_ARCHITECTURE.md` on platform/store model.
The master reference is broader; SAAS_ARCHITECTURE is the focused tenant-model doc. Overlap is
complementary, not contradictory — but both are foundation-era and unstamped.

## Cluster C6 — Product-entry (dashboard) reports (five)
`docs/reports/PRODUCT_ENTRY_FINAL_FUNCTIONAL_REPAIR_AUDIT.md`, `…FINAL_IMPLEMENTATION_PLAN.md`,
`…FINAL_PROTOTYPE_GAP_ANALYSIS.md`, `…FULL_PAGE_ROOT_CAUSE.md`, plus `docs/docs/product/reports/
PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md`. Multiple documents on the product-entry UI journey;
overlapping, mostly historical.

## Cluster C7 — Reference kits describing "target" designs (three)
`docs/reference-kits/rastisi-11-families-v3`, `docs/references/beraito-exact-frontend-v5`,
`docs/template-references/*`, plus `docs/reports/REFERENCE_STOREFRONT_EDITABLE_TARGET.md`. Multiple
"what the storefront should look like" reference sets — evidence, not architecture.

---

## Summary of overlap hot-spots
1. **Storefront builder (C1)** — by far the heaviest; ~60+ docs, 4 generations, 3–4 homes.
2. **Spec fragmentation (C2)** — three spec homes.
3. **Audit/evidence sprawl (C3)** — four evidence homes, some masquerading as architecture.

These three drive most of the documentation debt catalogued in Phase 4 (doc 08 debt analysis).
