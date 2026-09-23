# core — Entry Points

```
domain_id: D14
code_baseline: 5883a140
```

## HTTP (registered directly in `shop_core/urls.py`)
- `favicon.ico` → `core.views.favicon_view`
- `sitemap.xml` → `core.seo.sitemap_xml` (tenant-safe, host-scoped, published only)
- `robots.txt` → `core.seo.robots_txt`
- (core has no `urls.py`; these are wired at the project root.)

## Context processors
`core.context_processors.shop_settings` — injects `ShopSettings` into every template.

## Management commands
- `cleanup_expired_exports` → `export_service.mark_expired_jobs`
- `seed_shop`

## Service entry (called by other domains)
- `audit_service.record_audit_event` — called by services across the codebase.
- `export_service.run_export` — from dashboard export views.
- `session_service.apply_remember_me` — from unified login (re-exported by portal).
- `storage.private_storage` — used by Export/Import file fields.

## Signals / async
None. Exports are synchronous.
