# dashboard — Code Map

```
domain_id: D11
code_baseline: 5883a140
```

```
apps/dashboard/
├── models.py             EMPTY (3 lines) — no models
├── urls.py               ~503 lines; app_name="dashboard"; includes storefront_builder route delegation
├── views.py              ~7.7k LOC — thin controller for catalog/orders/staff/import/export;
│                         THICK controller (direct writes) for content (~4705-5610),
│                         ShopSettings (~4308-4458), shipping/tax (~6866-7281),
│                         gateway config (~5726-5784), staff_transfer_ownership (~5896)
├── decorators.py         staff_required (ignores is_staff — M15), permission_required, admin_host_required
├── middleware.py         AdminEmbedFrameOptionsMiddleware
├── forms.py              ~800 lines (shop-info/finance/gift-wrap/SMS templates, etc.)
├── context_processors.py merchant_permissions, platform_link, nav_badges, subscription_banner, ...
├── services/             12 files: catalog_admin, orders_admin, settings_admin, sms_admin,
│                         dashboard_service, report_service, charts, customer_crm, customers_admin,
│                         segment_service, checklist_service, import_service
├── management/commands/  cleanup_import_files, refresh_customer_segments
├── templatetags/
└── tests/                ~17.5k LOC (product/settings/commerce/auth-perm/import-export suites)
```

## Where to look
| Concern | File |
|---|---|
| Auth/authorization | `decorators.py` |
| Content/ShopSettings/config DIRECT writes | `views.py` (see MUTATION_AUTHORITY line refs) |
| Catalog admin ops | `services/catalog_admin_service.py` |
| Import | `services/import_service.py` (export is in core) |
| Stats/reports | `services/dashboard_service.py`, `services/report_service.py` |
| Storefront-builder routes | `urls.py` (delegates to storefront_builder) |
