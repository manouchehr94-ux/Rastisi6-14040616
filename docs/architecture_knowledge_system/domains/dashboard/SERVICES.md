# dashboard — Services

```
domain_id: D11
code_baseline: 5883a140
source: apps/dashboard/services/ (12 files)
```

These are admin-side read/orchestration services. Note: heavy domain writes for content/settings/
config are **in `views.py`**, not here (H2/M5).

| Service | Responsibility | Writes |
|---|---|---|
| `catalog_admin_service` | slug gen, default vendor, product filtering/sorting (SQLi-safe whitelist), bulk status/delete/assign (`Product.objects.filter(store=…).update()`), category tree, reorder | catalog.Product/Category; audit |
| `orders_admin_service` | read-only order/invoice/transaction filtering + status counts + timeline | none (delegates transitions to order_service) |
| `settings_admin_service` | `toggle_gateway`/`toggle_shipping_method` (is_active); gateway_configs_context | orders.PaymentGateway/ShippingMethod is_active |
| `sms_admin_service` | read-only templates/logs/outbox | none |
| `dashboard_service` | home stats/chart/donut/top-sellers/low-stock (store-scoped after O4) | read-only |
| `report_service` | reports (reuses dashboard_service); range summary/category/top-customers | read-only |
| `charts` | SVG line/donut builders (pure) | none |
| `customer_crm_service` | profile get/create, refresh stats (no-signal ADR-50), notes/tags CRUD, internal status | customers.CustomerProfile/Note/Tag; audit |
| `customers_admin_service` | read-only annotated customers (scoped via `orders__store`) | none |
| `segment_service` | allowlisted rule engine (no eval), evaluate/preview/refresh membership | customers.CustomerSegmentMembership; audit |
| `checklist_service` | store-setup checklist (pure detect) | none |
| `import_service` | CSV import (products/variants/inventory); dry-run + execute share validation | catalog via catalog services + core.ImportJob/RowResult; audit |

## Note on import/export asymmetry (M14)
`import_service` lives here (dashboard), but `export_service` lives in `core/services` — symmetric
features, split ownership.

## Where the domain WRITES live (not here)
content/ShopSettings/shipping-tax/gateway-config writes are direct in `views.py`
(see [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md)).
