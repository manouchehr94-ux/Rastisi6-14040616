# catalog — Entry Points

```
domain_id: D4
code_baseline: 5883a140
```

## Public HTTP (`apps/catalog/urls.py`, included at `/`)
`catalog.views.home` (storefront home → `render_service.build_render_items`), `product-list`,
`product-detail`, `collection-index`/`collection-detail`. Plus `context_processors.nav_categories`.

## Admin entry (via dashboard)
Product/category/brand/collection/attribute/variant/warehouse/transfer/reservation management —
through `catalog.services.*` and some direct dashboard writes (see dashboard pack MUTATION_AUTHORITY).

## Management commands
`cleanup_stale_product_drafts`, `expire_inventory_reservations`, `import_damatajhiz_catalog`,
`migrate_legacy_product_tag_collections`, `provision_default_warehouses`, `reset_store_catalog`,
`seed_industry_templates`, `validate_industry_templates`, `verify_inventory_consistency`.

## Called-into (service entry)
- `pricing_service` (cart price resolution), `inventory_service` (orders reserve/consume),
  `product_publish_service.storefront_visible_products` (storefront), `industry_template_service`
  (provisioning install).

## Signals / async
None. `Warehouse` provisioning is an explicit idempotent service call (ADR-37).
