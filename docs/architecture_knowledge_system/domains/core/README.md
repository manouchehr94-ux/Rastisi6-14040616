# Domain: core (D14) — Shared / Cross-cutting

```
domain_id: D14
app: apps/core
status: CANONICAL
readiness: PARTIAL
code_baseline: 5883a140
open_decisions: DR-3
known_risks: M5, M14
```

Cross-cutting foundations: `ShopSettings` (per-Store identity/tax/branding), the shared
`TimeStampedModel` base, the audit log, export/import job records + private storage, SEO
(sitemap/robots), and utility modules (color/theme/phone/URL-converters).

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[DEPENDENCIES](DEPENDENCIES.md) · [SECURITY](SECURITY.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) ·
[CODE_MAP](CODE_MAP.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* STATE_MACHINES (ExportJob/ImportJob status → DATA_MODEL), INVARIANTS/TRANSACTIONS/FLOWS/
API_AND_EVENTS/ARCHITECTURE/TESTING/TROUBLESHOOTING/HISTORICAL_CONTEXT → SERVICES + SECURITY + this README.

## Orientation
- **Owns:** `TimeStampedModel` (abstract base used across apps — but NOT by `stores`, by design M13),
  `ShopSettings` (store-scoped OneToOne), `AuditLogEntry` (immutable), `ExportJob`, `ImportJob`
  (+RowResult); `storage.py` (private_storage), `seo.py` (tenant-safe sitemap/robots),
  `services/` (export/audit/session/csv/rate_limit), utility modules.
- **Does NOT own:** `stores.Store` (core avoids importing stores — M13); import lives in `dashboard`
  (M14 asymmetry with export here).
- **⚠️ ShopSettings write authority is spread (M5/DR-3):** owned by core, but written directly by
  `dashboard.views` and by `sms_service` (device token). Legacy SMS credential fields are
  POTENTIALLY_DEAD (D4).
- **No signals.** `AuditLogEntry` omits IP/UA (ADR-36) and redacts sensitive keys at write time.
