# dashboard — Historical Context

```
domain_id: D11
code_baseline: 5883a140
open_decisions: DR-2, DR-3
```

Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `docs/docs/product/reports/ADMIN_PANEL_COMPLETION_REPORT.md`, `PHASE_1B_ADMIN_FOUNDATION_REPORT.md` | L4 report | HISTORICAL — how the admin was built | HISTORICAL |
| `docs/docs/product/reports/PROTOTYPE_*` (gap audit / coverage matrix) | L4 | HISTORICAL — prototype coverage | HISTORICAL |
| `docs/reports/PRODUCT_ENTRY_*` (functional repair audit / implementation plan / gap analysis / root cause) | L4 | HISTORICAL — product-entry UI journey (overlapping, Cluster C6) | HISTORICAL |
| `SAAS_DOMAIN_DECISIONS.md` ADR-8/58/69 | L3 ADR | ADR-8 (superuser-only Django admin) MATCHES; ADR-58/69 (service-layer writes) **contradicted** by dashboard's direct content/config writes (Phase 4 X2 / DR-2/DR-3) | MIXED |

## Key point
The ADRs express a service-layer write discipline (ADR-58/69). dashboard honors it for
high-risk domains (inventory, orders) but **not** for content/settings/config (X2). That gap is
DR-2/DR-3. The old admin/prototype reports are historical build records, not current architecture.
