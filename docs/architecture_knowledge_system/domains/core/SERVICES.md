# core — Services & Modules

```
domain_id: D14
code_baseline: 5883a140
source: apps/core/services/ (5 files) + top-level modules
```

## services/
| Service | Responsibility |
|---|---|
| **export_service** | 5 export types (products/variants/inventory/customers/orders), all Store-scoped; `run_export` synchronous (no queue); enforces subscription export budget (`subscriptions.enforcement`); writes CSV via `csv_utils` (formula-injection safe); audits; `mark_expired_jobs` deletes expired files |
| **audit_service** | `record_audit_event` (idempotent by request_id; redacts forbidden keys password/token/api_key/card); `list_audit_events`. **"Services (not views) must call this."** |
| **session_service** | `apply_remember_me` (unified login session duration) — re-exported by `portal.session_service` |
| **csv_utils** | `write_csv_rows` (formula-injection-safe CSV) |
| **rate_limit** | rate-limit helpers |

Note: **import lives in `dashboard.import_service`**, not core — M14 asymmetry (export here, import there).

## Top-level modules
| Module | Purpose |
|---|---|
| `storage.py` | `PrivateFileSystemStorage` / `private_storage` singleton (location from `PRIVATE_MEDIA_ROOT`; `.url` raises defensively) — used by Export/Import file fields |
| `seo.py` | request-scoped tenant-safe `sitemap_xml` + `robots_txt` (resolve store from host; only published content) — not django.contrib.sitemaps |
| `color_utils.py` | `safe_hex`, color helpers |
| `theme_presets.py` | `THEME_PRESETS`, `matching_preset_key` |
| `phone.py` | phone normalization |
| `converters.py` | URL path converters |
| `utils.py` | `to_fa_digits`, `normalize_digits`, `normalization_key` |
| `context_processors.py` | `shop_settings` (injects ShopSettings into templates) |

## Key discipline
- `ShopSettings.load(store=)` raises if unprovisioned (never auto-creates on read).
- `audit_service.record_audit_event` redacts sensitive keys and is idempotent; services (not views)
  are expected to call it.
- `private_storage` is deliberately outside `MEDIA_ROOT` (export/import files never publicly served).
