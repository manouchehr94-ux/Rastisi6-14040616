# catalog — Mutation Authority

```
domain_id: D4
code_baseline: 5883a140
```

| Entity | Canonical writer | Other / cross-domain |
|---|---|---|
| **`Product.stock` / `ProductVariant.stock`** | `inventory_service` (ONLY; ledgered via `StockMovement`) | — (QuerySet blocks bulk bypass) |
| `Product` (row) | `product_draft_service` (draft placeholder) | `dashboard.views._save_product` (DIRECT); `dashboard.catalog_admin_service` bulk `.update()`; `import_service`; `industry_template_service` (install) |
| `ProductVariant` | `variant_service`/`variant_engine_service` | (QuerySet blocks raw bulk bypass) |
| `Category` | `dashboard.views` + `catalog_admin_service` | `industry_template_service` (install deep-copy); `category_schema_service` |
| inventory reservation/consumption | `reservation_service` / `inventory_service` | `orders.order_service.create_order_from_cart` (cross-domain reserve+consume) |
| `IndustryTemplate` (platform) | admin / `seed_industry_templates` command; `industry_template_service` install → Store-owned rows | — |
| `WarehouseTransfer` | `transfer_service` (guarded ALLOWED_TRANSITIONS) | — |

## Key rules
- **Stock is single-sourced through `inventory_service`** (+ StockMovement ledger). `Product`/
  `ProductVariant.stock` is the authoritative sellable field (ADR-38); `WarehouseInventory` is a
  synced breakdown, not a competing source.
- **`ProductVariant` normalization cannot be bypassed** — the custom QuerySet blocks `update()`,
  `bulk_update()`, `bulk_create()` (raises `VariantMutationError`).
- **`Product` has mixed writers** (draft service + dashboard direct + import + template install) —
  MEDIUM; the stock field is the strongly-guarded part.

## No signals
`Warehouse` provisioning is an explicit idempotent service call, never a Django signal (ADR-37).
