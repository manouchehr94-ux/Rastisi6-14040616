# stores — Historical Context

```
domain_id: D1
code_baseline: 5883a140
```

Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `SAAS_ARCHITECTURE.md` | L3 (CURRENT_CANDIDATE) | MATCHES_CODE on tenant model (Store boundary, platform vs store, status lifecycle). STALE only on in-line PR-status prose (S2) | AUTHORITATIVE-EXCEPT-PR-STATUS |
| `SAAS_DOMAIN_DECISIONS.md` ADR-1/2/3/11/16/17 | L3 ADR | MATCHES_CODE — Store≠Vendor(deferred), ownership via membership, one status field, hostname-authoritative resolution, admin_subdomain, admin-host enforcement | AUTHORITATIVE-INTENT |
| `00_PROJECT_MASTER_REFERENCE.md` §9 (Store Resolution & Tenant Isolation) | L3 | MATCHES_CODE — host authoritative, fail-closed, middleware-not-complete-auth-boundary | AUTHORITATIVE-INTENT |
| `SAAS_MIGRATION_PLAN.md` | L3 plan | Foundation stages realized; PR12 legacy removal pending (DR-6, not stores-specific) | PARTIALLY-REALIZED |

## Key points
- The Store-as-tenant-boundary model, ownership-via-membership, and hostname-authoritative
  resolution are documented AND implemented — this is why the domain is rated READY.
- **ADR-1 explicitly defers `Vendor`'s meaning** (Store is not Vendor) — the ambiguity is by design,
  and remains unresolved in code (DR-7).
- The stores/core cycle-avoidance (StoresTimestampedModel) is documented in the model docstring and
  anticipates a future `core → stores` FK.
