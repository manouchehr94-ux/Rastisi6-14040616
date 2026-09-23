# catalog — Services

```
domain_id: D4
code_baseline: 5883a140
source: apps/catalog/services/ (31 files)
```

Key services (the rest are supporting: attribute/brand/tag/metafield/sku/specification/product_image/
video/completion/html_sanitizer/product_card/template_comparison/customization/preview/legacy_collection_migration):

| Service | Responsibility | Writes |
|---|---|---|
| **inventory_service** | THE single atomic stock-mutation ledger; never changes stock without a `StockMovement`; mirrors into default `WarehouseInventory` in the same transaction | Product/Variant.stock + StockMovement + WarehouseInventory |
| **product_publish_service** | `validate_product_for_publish` (required category-schema attrs + price>0); `storefront_visible_products`/`storefront_listing_products` (status=active + not draft-placeholder + publish_at gate) | read-only |
| **product_draft_service** | `get_or_create_product_draft` (real `Product(is_draft_placeholder=True)` with subscription-cap enforcement), discard, cleanup_stale | Product row + deletes image files |
| **variant_service / variant_engine_service** | variant CRUD + multi-axis generation | ProductVariant (normalized) |
| **reservation_service** | inventory reservations (active→consumed/released) | InventoryReservation |
| **warehouse_service / transfer_service** | warehouse + transfers (guarded transitions) | Warehouse*/Transfer* |
| **industry_template_service** | install platform template → deep-copy into Store-owned rows | Category/Attribute/CategoryAttributeSchema |
| **category_schema_service** | category attribute schema resolution (direct mappings win — ADR-23) | schema rows |
| **collection_service** | `searchable_products`; collection membership | MerchantCollection* |
| **pricing_service** | effective price resolution (used by cart) | read-only |
| **template_validation_service / template_update_service** | industry template quality + updates (ADR-26/29) | validation results / StoreTemplateUpdate |

## Key discipline
- **Stock only via `inventory_service`** (+ StockMovement). ADR-31/38/39/40.
- **Inventory reservation is created + consumed synchronously inside `order_service.create_order_from_cart`'s
  transaction** (ADR-39) — never held open across requests.
- **Import routes through services** (ADR-58) — `dashboard.import_service` calls catalog services.
