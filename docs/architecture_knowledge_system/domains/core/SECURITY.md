# core — Security

```
domain_id: D14
code_baseline: 5883a140
```

## Audit log (VERIFIED — ADR-36)
- `AuditLogEntry` is immutable, store-scoped, **redacts known-sensitive keys at write time**
  (password/token/api_key/card), and **omits IP/UA** (ADR-36). `record_audit_event` is idempotent
  by request_id. Services (not views) are expected to call it.

## Private storage (VERIFIED)
- `PrivateFileSystemStorage` (`private_storage`) uses `PRIVATE_MEDIA_ROOT`, deliberately **outside**
  `MEDIA_ROOT`/`MEDIA_URL` — export/import files are never served through public media. `.url`
  raises defensively (no accidental public URL).

## Export budget
- `export_service.run_export` enforces the subscription export budget (`subscriptions.enforcement`)
  and writes formula-injection-safe CSV (`csv_utils`).

## SEO tenant safety
- `seo.sitemap_xml`/`robots_txt` resolve the Store from the host and expose **only published**
  content — tenant-safe.

## ShopSettings provisioning
- `ShopSettings.load(store=)` raises if unprovisioned — no read-time create, avoiding accidental
  empty settings.

## ⚠️ ShopSettings write-boundary (M5/DR-3)
Because dashboard writes ShopSettings directly (no core write-service), validation depends on the
view. This is DR-3.
