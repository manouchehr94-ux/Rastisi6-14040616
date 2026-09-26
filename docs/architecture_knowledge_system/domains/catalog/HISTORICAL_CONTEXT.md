# catalog — Historical Context

```
domain_id: D4
code_baseline: 5883a140
open_decisions: DR-7
```

Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `SAAS_DOMAIN_DECISIONS.md` ADR-18..31, 38..40, 58, 60 | L3 ADR | MATCHES_CODE — variant identity/reconciliation, inventory ledger, single stock source, reservations, transfers, industry templates, category schema, import discipline | AUTHORITATIVE-INTENT |
| ADR-1 | L3 ADR | Store≠Vendor; Vendor meaning **deferred** — the A1/DR-7 ambiguity is by design | DEFERRED-DECISION |
| `docs/docs/product/reports/PHASE_1C_PRODUCT_MANAGEMENT_REPORT.md`, `PHASE_1D_ATTRIBUTE_VARIANT_ENGINE_REPORT.md`, `PHASE_1E_INDUSTRY_ATTRIBUTE_TEMPLATES_REPORT.md` | L4 report | HISTORICAL — build reports | HISTORICAL |

## Key point
catalog is one of the most ADR-covered domains, and the code faithfully implements the inventory,
variant, and industry-template decisions. The one deliberately-unresolved item is `Vendor`'s final
meaning vs `Store` (ADR-1 → DR-7). There is no single "current catalog architecture" doc beyond the
ADRs + build reports — hence the domain is rated PARTIAL for readiness.
