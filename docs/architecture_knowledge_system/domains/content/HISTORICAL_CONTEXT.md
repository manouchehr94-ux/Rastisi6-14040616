# content — Historical Context

```
domain_id: D10
code_baseline: 5883a140
open_decisions: DR-2
```

Historical/design-intent documents. Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `SAAS_MIGRATION_PLAN.md` (PR 8: "Content, navigation, homepage, blog and media ownership") | L3 plan | Ownership FKs delivered, BUT the service discipline applied to other domains was **not** applied to content — content has no write service (Phase 4 S3 / H2) | PARTIALLY-REALIZED |
| `SAAS_DOMAIN_DECISIONS.md` (DestinationMixin/cross-store ownership framing) | L3 ADR | MATCHES_CODE — cross-store destination ownership enforced in `clean()` | AUTHORITATIVE-INTENT |
| Storefront/appearance docs referencing footer/placements | L3/L4 | Explain the content↔storefront_builder coupling (footer ×3 M2; placements FK sections) | CONTEXT |

## Key historical point
Content ownership (the Store FKs) was modeled per the migration plan, but the platform's
service-layer write discipline (see ADR-58/69 for the analogous catalog/import intent) was **not**
extended to content. The result is H2: content data is owned here, but written by dashboard views.
Whether to close that gap is **DR-2 (OPEN)**.

## Do not "fix" the doc here
Where SAAS_MIGRATION_PLAN implies a content service boundary that does not exist, that is recorded
as STALE (Phase 4 S3). The old doc is not edited in this phase.
