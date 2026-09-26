# catalog — Testing

```
domain_id: D4
code_baseline: 5883a140
source: apps/catalog/tests/ + apps/dashboard/tests/ (product suite)
```

- **Catalog services/models:** `apps/catalog/tests/` — product publish/draft, variant engine,
  inventory ledger + reservation, warehouse/transfer, industry template install/validation,
  category schema, collections, pricing.
- **Admin product suite (via dashboard):** the largest test group in the repo lives in
  `apps/dashboard/tests/` — `test_product_views` (770), `test_product_variant_views` (1107),
  `test_product_options_views` (872), `test_product_image_views` (511), entry-draft/quick-add/sku/
  wizard/bulk-actions.
- **Store isolation:** `apps/dashboard/tests/test_catalog_store_isolation.py`.
- **Consistency:** `verify_inventory_consistency` command.

## Coverage posture
Inventory ledger + variant normalization are strongly tested (the money-adjacent invariants).
See canonical [`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
