# billing — Historical Context

```
domain_id: D8
code_baseline: 5883a140
```

Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `SAAS_DOMAIN_DECISIONS.md` ADR-72/73/75/76/77/78/79/80/82 | L3 ADR | MATCHES_CODE — separate money system (73), provider-neutral interface with manual first (75), verified idempotent webhook inbox (76), transactional confirmation never in a view (77), renewal lead days (78), dunning schedule (79), plan-change no fake proration (80), tax rate (82) | AUTHORITATIVE-INTENT |
| `docs/reports/PRELAUNCH_PHASE3_ZIBAL_PLATFORM_BILLING.md` | L4 report | HISTORICAL — prelaunch platform-billing report | HISTORICAL |
| `SAAS_MIGRATION_PLAN.md` | L3 plan | billing is downstream of the foundation PRs | CONTEXT |

## Key point
billing's discipline (ADR-76 verified idempotent inbox; ADR-77 transactional confirmation) is
**faithfully implemented** — this is one of the clearest doc↔code matches in the system. The
separation from orders' storefront payments (ADR-73) is likewise realized (distinct models).
