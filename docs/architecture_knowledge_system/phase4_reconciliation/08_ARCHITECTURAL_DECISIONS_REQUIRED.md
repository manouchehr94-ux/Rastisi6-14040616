# 08 — Architectural Decisions Required

Phase 4 may **identify** future decisions but must **not** make architecture-remediation changes.
The items below are surfaced by doc↔code disagreements and by Phase 1/2 findings. Each states the
tension and the options — it does **not** choose. These feed a future, separately-authorized
remediation phase.

This document also contains the **documentation-debt analysis** and the **domain-readiness**
assessment mandated for this task.

---

## Part A — Decisions required

> **Count distinction (STEP-0 clarification):**
> - **claim-level `decision_required=YES` flags in `01_CLAIM_RECONCILIATION_MATRIX.csv`: 6.**
> - **total architectural decisions requiring resolution (the DR register): 8 (DR-1…DR-8).**
> The DR register is larger than the 6 flagged claims because several DR items originate from
> Phase 1/2 findings (e.g. DR-8 `require_resolved_store`) rather than from a reconciled document
> claim. Do not conflate "6 flagged claims" with "8 DR items."

The 8 decisions below are surfaced by doc↔code disagreements **and** by Phase 1/2 findings.

### DR-1 — `Order.payment_status`: single canonical writer + transition guard (from H1 / S1 / CL-08)
- **Tension:** 3 writers (gateway conditional-update; simulate direct save; refund direct save),
  no `ALLOWED_TRANSITIONS` guard; PAYMENT_ARCHITECTURE §4 documents only the gateway writer.
- **Options:** (a) introduce a guarded `payment_status` transition service that all three writers
  call; (b) fold simulate into a test-only harness and keep gateway+refund as the two writers with
  an explicit guard; (c) accept and document the current state.
- **Do not decide now.** Financial-integrity sensitive.

### DR-2 — `content` domain write boundary (from H2 / S3 / CL-31)
- **Tension:** content is Store-owned data but has no write service; dashboard views mutate it
  directly (83 sites). Contradicts the service-layer discipline documented for other domains.
- **Options:** (a) extract a `content` service layer; (b) formally sanction dashboard-view-as-
  content-service and document it; (c) partial extraction for the highest-risk content writes.

### DR-3 — Service-layer write discipline for settings/config (from M5 / X2 / CL-22)
- **Tension:** `ShopSettings`, shipping/tax, and `PaymentGatewayConfig` are written directly by
  dashboard views, against ADR-58/69's service-layer intent.
- **Options:** (a) route these through owning-domain services; (b) document the exception.

### DR-4 — Ownership-transfer duplication (from A8 / M6 / C1 correction)
- **Tension:** TWO live owner-transfer paths — `membership_service.transfer_ownership` (dashboard
  `staff/<pk>/transfer-ownership/`) and `ownership_transfer_service` (portal OTP). Different
  guarantees (synchronous vs two-party OTP-gated).
- **Options:** (a) make the OTP flow canonical and route the dashboard path through it; (b) keep
  both with an explicit, documented division of use; (c) deprecate one.

### DR-5 — Dual gateway representation (from M4 / A4 / CL-13)
- **Tension:** `PaymentGateway` (legacy order-chosen slug) vs `PaymentGatewayConfig` (operational
  config); `payment_initiate` fuzzy-matches. ADR-7 separates provider from config but does not
  resolve the dual model.
- **Options:** (a) converge on `PaymentGatewayConfig`; (b) formal mapping contract; (c) document.

### DR-6 — Legacy-path removal (from DI-2 / CL-32 / H1 / H3)
- **Tension:** `SAAS_MIGRATION_PLAN` PR12 = "legacy-path removal," but simulate_payment (gated),
  R3 editor (fail-closed), and legacy `Transaction` still exist.
- **Options:** (a) complete removal; (b) keep as intentional rollback/compat and document the
  policy and its guards.

### DR-7 — `Store` vs `catalog.Vendor` ownership (from A1 / CL-02)
- **Tension:** ADR-1 defers Vendor's final meaning; the ambiguity persists in code.
- **Options:** (a) dedicated catalog-domain review to define Vendor; (b) formally record the
  permanent coexistence contract.

### DR-8 — `require_resolved_store` disposition (from D6)
- **Tension:** no live caller found; may be intentional API scaffolding.
- **Options:** (a) adopt it at the intended boundaries; (b) remove; (c) document as reserved API.

---

## Part B — Documentation-debt analysis (mandated)

| Debt type | Instances | Evidence |
|---|---|---|
| Multiple docs describing the same subsystem differently | Storefront builder (Cluster C1, 60+ docs, 4 generations) | Phase 3 doc 04 |
| Stale plans that look authoritative | `SAAS_MIGRATION_PLAN` (PR12 legacy-removal implies done); "FINAL_AUDIT"/"Final Result At Last" naming | doc 03 S2/DI-2; Phase 3 doc 07 |
| Duplicate architecture specifications | 3 spec homes (C2); master-ref vs SaaS-arch overlap (C5) | Phase 3 doc 04 |
| QA evidence functioning as architecture doc | 4 evidence homes (C3); `*_PHASE_*_AUDIT.md`, `final_closure_pack` | Phase 3 doc 04/07 |
| Implementation reports that should stay historical | `PHASE_1B…1F`, `PRELAUNCH_*`, V2 phase reports (39 HISTORICAL) | doc 05 |
| Canonical-looking docs that contradict live code | `docs/README.md` (layout X1); ADR-58/69 implied discipline (X2) | doc 04 |
| Abandoned plans | Family-era `SIX_NEW_FAMILIES_*` (superseded by universal engine) | doc 06 |
| Misleading-name docs | "Final Result At Last", "FINAL_AUDIT", 3 "FINAL_SPEC"/spec homes | Phase 3 doc 07 |
| Docs with no clear owner/domain | `docs/superpowers/**` (cross-cutting); `docs/audits/…u3_u11_execution` | Phase 3 doc 07 |
| Docs that should be archived (not deleted) | Family-era + superseded V2 phase docs; prelaunch reports | doc 10 |
| **Missing docs for important code domains** | **content (D10 — undocumented mutation authority), notifications (D13), blog (D15), thin: customers/cart/SMS device gateway** | Phase 3 doc 05 |

The single largest debt is **storefront-builder over-documentation** (competing generations) paired
with **content-domain under-documentation** (the H2 mutation authority has no doc at all).

---

## Part C — Domain documentation readiness (mandated)

Rating = *documentation* readiness for a future engineer to safely modify the domain (NOT code
quality). Scale: READY / PARTIAL / POOR / MISSING / CONFLICTED.

| Domain (app) | Readiness | What's missing / why |
|---|---|---|
| D1 Tenancy & Store (`stores`) | **READY** | Strong ADR coverage (ADR-1/2/3/11/16/17); matches code |
| D2 Platform control (`portal`) | **PARTIAL** | Covered via ADRs (93/97/98/101/102); no consolidated portal doc |
| D3 Customer & CRM (`customers`) | **POOR** | Only scattered ADRs; no CRM/segment architecture doc |
| D4 Catalog & inventory (`catalog`) | **PARTIAL** | Strong ADRs (18–31/38–40) + historical reports; no single current catalog doc |
| D5 Cart & pricing (`cart`) | **POOR** | Only ADR-15/32 + business defaults; no cart doc |
| D6 Orders/payments (`orders`) | **PARTIAL** | PAYMENT_ARCHITECTURE strong but STALE on payment_status writers (S1); order lifecycle thinner |
| D7 SaaS subscriptions (`subscriptions`) | **PARTIAL** | ADR-66/72 + prelaunch report; no consolidated state-machine doc |
| D8 SaaS billing (`billing`) | **PARTIAL** | ADR-72–82 + prelaunch report; strong but spread |
| D9 Storefront presentation (`storefront_builder`) | **CONFLICTED** | Over-documented across 4 generations; reader cannot tell which is current without the retirement map |
| D10 Content & navigation (`content`) | **POOR** | Scattered design-intent/ownership references exist (PR-8 ownership, ADR framing) but no adequate current content-domain doc; H2 mutation authority undocumented |
| D11 Merchant admin (`dashboard`) | **PARTIAL** | Build reports exist; no current "dashboard as controller / direct-write surface" doc |
| D12 SMS (`sms`) | **POOR** | ADR-93 owner SMS only; device gateway/credit model undocumented |
| D13 Notifications (`notifications`) | **MISSING** | No doc |
| D14 Cross-cutting (`core`) | **PARTIAL** | ShopSettings/config covered; export/import/SEO thin |
| D15 Blog (`blog`) | **MISSING** | No doc (consistent with near-dead code) |

**Readiness summary (single-value vocabulary; totals sum to exactly 15 domains):**

```
READY:      1   (D1 stores)
PARTIAL:    7   (D2 portal, D4 catalog, D6 orders, D7 subscriptions, D8 billing, D11 dashboard, D14 core)
POOR:       4   (D3 customers, D5 cart, D10 content, D12 sms)
MISSING:    2   (D13 notifications, D15 blog)
CONFLICTED: 1   (D9 storefront_builder)
TOTAL:      15
```

This directly scopes the future Domain Knowledge Packs: prioritize **content (D10)**,
**storefront de-confliction (D9)**, and the POOR/MISSING domains (D3, D5, D12, D13, D15).

> **[STEP-0 CORRECTION]** An earlier draft rated D10 as "POOR/MISSING" and summed PARTIAL to 8
> (totalling 16). Corrected: D10 = **POOR** (scattered intent exists, no adequate current doc);
> the seven PARTIAL domains are enumerated explicitly above; totals now sum to 15.
