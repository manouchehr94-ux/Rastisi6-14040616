# dashboard — Testing

```
domain_id: D11
code_baseline: 5883a140
source: apps/dashboard/tests/ (~17.5k test LOC)
```

Major groupings (from Phase 1):
- **Products (largest):** `test_product_views` (770), `test_product_variant_views` (1107),
  `test_product_options_views` (872), `test_product_image_views` (511) + entry-draft/quick-add/sku/
  attribute-form/wizard/bulk-actions/modal.
- **Catalog:** category/brand/collection/attribute/category_schema, `catalog_admin_service`,
  `catalog_store_isolation`.
- **Settings:** `test_settings_views` (1044), `setup_checklist` (633), industry/template-update,
  shipping_setup/tax, integration, payment/gateway.
- **Commerce:** order_views/order_store_isolation, invoice, return_refund, coupon, customer CRM/
  customer_views/segment.
- **SMS:** `test_sms_admin_views` (364).
- **Billing/subscription views:** `test_billing_views`, `test_subscription_views`.
- **Import/export:** `test_import_{product,variant,inventory,views}`, `test_export_views`.
- **Auth/perm:** `test_admin_login`, `test_decorators`, `test_permission_enforcement` (308),
  `test_membership_authorization`, `test_staff_views`.

## Recurring themes
Heavy emphasis on **multi-tenant store isolation** and **permission enforcement** — matching the
security posture in `decorators.py`/services. Content behavior is tested here (via content views)
because content has no service test suite (H2). See canonical
[`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
