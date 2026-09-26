# 05 — Domain → Document Map

Maps each code-derived domain (Phase 1 doc 02, D1–D15) to the documentation that describes it.
"Doc coverage" is a **count/kind** observation here; the READY/PARTIAL/POOR/MISSING/CONFLICTED
readiness rating is assigned in Phase 4 (doc 08 domain readiness) after reconciliation.

Domain-count in the CSV `domain` column is coarse (keyword-based); this table is the curated view.

---

| Code domain (app) | Primary documents | Kind | Coverage observation |
|---|---|---|---|
| **D1 Tenancy & Store** (`stores`) | `SAAS_ARCHITECTURE.md`, `SAAS_DOMAIN_DECISIONS.md` (ADR record), `SAAS_MIGRATION_PLAN.md` | CURRENT_CANDIDATE / SUPPORTING | Strong foundation-era coverage; unstamped vs frozen snapshot |
| **D2 Platform control & owner identity** (`portal`) | `SAAS_ARCHITECTURE.md` (platform ops), `SAAS_DOMAIN_DECISIONS.md` (ADR-93/97/98/101 host+identity), `00_PROJECT_MASTER_REFERENCE.md` | CURRENT_CANDIDATE | Present via ADRs; no dedicated portal doc |
| **D3 Customer identity & CRM** (`customers`) | `00_PROJECT_MASTER_REFERENCE.md`, scattered ADRs (ADR-50/93 customer/owner identity) | mixed | Thin; no dedicated customer/CRM architecture doc |
| **D4 Catalog & inventory** (`catalog`) | `docs/docs/product/reports/PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md`, `PHASE_1D_ATTRIBUTE_VARIANT_ENGINE_REPORT.md`, `PHASE_1E_INDUSTRY_ATTRIBUTE_TEMPLATES_REPORT.md` | HISTORICAL | Reports describe build; no current catalog architecture spec |
| **D5 Cart & pricing** (`cart`) | `00_PROJECT_MASTER_REFERENCE.md` (business defaults), checkout references | mixed | Thin; no dedicated cart doc |
| **D6 Orders/checkout/payments** (`orders`) | `PAYMENT_ARCHITECTURE.md` (CURRENT_CANDIDATE), `docs/reports/PRELAUNCH_PHASE4_ZIBAL_MERCHANT_PAYMENTS.md` | CURRENT_CANDIDATE / HISTORICAL | Payment well-documented; order lifecycle/refund/return thinner |
| **D7 SaaS subscriptions** (`subscriptions`) | `docs/reports/PRELAUNCH_PHASE2_SUBSCRIPTIONS_TRIALS.md`, ADRs (ADR-66 transitions) | HISTORICAL / SUPPORTING | Present; no consolidated subscription state-machine doc |
| **D8 SaaS billing** (`billing`) | `docs/reports/PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md`, ADRs (ADR-76/78/79/82) | HISTORICAL / SUPPORTING | Present via prelaunch report + ADRs |
| **D9 Storefront presentation** (`storefront_builder`) | `UNIVERSAL_STOREFRONT_BUILDER_V2_SPEC.md`, `STOREFRONT_BUILDER_V2_*` set, `docs/superpowers/*`, `final_closure_pack`, `RASTISI_STOREFRONT_BUILDER_FINAL_SPEC_V1_EN.md` | DESIGN_INTENT / HISTORICAL / QA | **Over-documented** (60+ docs, 4 generations) — see doc 04 C1 |
| **D10 Content & navigation** (`content`) | Referenced inside storefront/appearance docs; no dedicated content-domain doc | — | **Sparse**: content mutation authority (Phase 1 H2) is undocumented |
| **D11 Merchant admin** (`dashboard`) | `docs/docs/product/reports/ADMIN_PANEL_COMPLETION_REPORT.md`, `PHASE_1B_ADMIN_FOUNDATION_REPORT.md`, `PROTOTYPE_*`, `docs/reports/PRODUCT_ENTRY_*` | HISTORICAL | Build reports exist; no current dashboard-as-controller doc |
| **D12 SMS** (`sms`) | ADR-93 (owner SMS), scattered; prototype `sms-*` html | SUPPORTING | Thin; device-gateway/credit model undocumented in architecture tier |
| **D13 Notifications** (`notifications`) | none dedicated | — | **MISSING** dedicated doc |
| **D14 Cross-cutting** (`core`) | `PRODUCTION_CONFIGURATION.md`, `00_PROJECT_MASTER_REFERENCE.md` (ShopSettings/business defaults) | SUPPORTING | Partial (ShopSettings, config); export/import/SEO thin |
| **D15 Blog** (`blog`) | none | — | **MISSING** (consistent with near-dead code) |

---

## Observations
- **Best-documented:** D9 storefront presentation (over-documented) and D1/D2 tenancy/platform
  (strong foundation ADRs). D6 payment is well-covered for the orders side.
- **Thinnest / missing:** D10 content (undocumented mutation authority — the Phase 1 H2 smell has
  no doc), D13 notifications (none), D15 blog (none, consistent with near-dead), D3 customers,
  D5 cart, D12 SMS device gateway.
- **ADR record (`SAAS_DOMAIN_DECISIONS.md`, 4508L)** is the single densest architecture source and
  is cited directly by code docstrings (ADR-1…ADR-101). It is the most important document to
  reconcile in Phase 4.
