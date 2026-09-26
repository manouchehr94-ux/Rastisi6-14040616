# core — Code Map

```
domain_id: D14
code_baseline: 5883a140
```

```
apps/core/
├── models.py               6 models (TimeStampedModel[abstract], ShopSettings[store-scoped],
│                           AuditLogEntry, ExportJob, ImportJob(+RowResult))
├── storage.py              PrivateFileSystemStorage / private_storage (outside MEDIA_ROOT)
├── seo.py                  sitemap_xml, robots_txt (tenant-safe)
├── views.py                favicon_view, admin_panel_compat_redirect
├── context_processors.py   shop_settings
├── services/               export_service, audit_service, session_service, csv_utils, rate_limit
├── color_utils.py / theme_presets.py / phone.py / converters.py / utils.py
├── management/commands/     cleanup_expired_exports, seed_shop
├── migrations/
└── tests/

# Import (symmetric feature) lives in: apps/dashboard/services/import_service.py (M14)
# ShopSettings writers (M5): apps/dashboard/views.py (settings_*), apps/sms/services/sms_service.py
```

## Where to look
| Concern | File |
|---|---|
| Per-Store settings | `models.py` (ShopSettings) — writers in dashboard/sms (M5) |
| Audit | `services/audit_service.py` |
| Export | `services/export_service.py` (import in dashboard — M14) |
| Private files | `storage.py` |
| SEO | `seo.py` |
| Shared base | `models.py` (TimeStampedModel — not used by stores, M13) |
