# stores — Entry Points

```
domain_id: D1
code_baseline: 5883a140
```

`stores` has **no `urls.py`** — it is infrastructure consumed by middleware, other apps' views,
and management commands.

## Middleware (run on every request)
- `StoreResolutionMiddleware` — sets `request.store` via `resolve_store_for_request`.
- `StorefrontCanonicalRedirectMiddleware` — 301 platform-subdomain → verified primary custom domain
  (contains DB queries — a "business logic in middleware" note, MEDIUM).

## Consumed by (entry into stores logic)
- `dashboard.decorators.staff_required` → `resolution.resolve_store_for_admin_request` +
  `authorization.get_active_membership`.
- `dashboard` staff views → `membership_service` (incl. `staff_transfer_ownership` → `transfer_ownership`),
  `integration_service`.
- `portal` → `provisioning_service`, `ownership_transfer_service`, `handle_service`,
  `domain_verification_service`, deletion flows.

## Management commands
`purge_deleted_stores` (dry-run default; `--execute` → `deletion_service.purge_due_stores`),
`rename_store_handle`, `verify_domain_consistency`, plus demo/seed commands
(`apply_golden_reference_storefront`, `seed_*`, `refresh_rasti_mode_demo_visuals`, `kianstock_qa_data`).

## Signals / async
None. `stores` services explicitly enqueue `notifications` and call `portal` where needed.

## Admin
Django `/admin/` is superuser-only (`admin_permissions.install()` monkeypatches
`admin.site.has_permission`, ADR-8).
