# core — Boundaries

```
domain_id: D14
code_baseline: 5883a140
known_risks: M5, M13, M14
```

## Owns
`TimeStampedModel` (shared base), `ShopSettings` (per-Store), `AuditLogEntry`, `ExportJob`,
`ImportJob`(+RowResult); private storage; tenant-safe SEO (sitemap/robots); color/theme/phone/
URL-converter utilities; export/audit/session/csv/rate-limit services.

## Does NOT own
- **`stores.Store`** — core deliberately does **not** import stores (M13), anticipating a future
  `core.ShopSettings → stores.Store` FK direction.
- **Import** — `dashboard.import_service` (M14 asymmetry: export is here, import is in dashboard).
- **Platform-global config** — `portal.PlatformConfiguration`.
- **ShopSettings write path** — de-facto in `dashboard.views` (M5/DR-3), though core owns the model.

## Cross-domain relationships
- **In:** dashboard writes ShopSettings/runs export; sms writes device token; every app uses
  TimeStampedModel + audit.
- **Out:** `export_service` reads subscription export budget; SEO reads published content.

## Cycle-avoidance (M13)
`stores` duplicates `TimeStampedModel` to avoid a future `core → stores` cycle; core is expected to
gain a `stores` dependency later, not the reverse.
