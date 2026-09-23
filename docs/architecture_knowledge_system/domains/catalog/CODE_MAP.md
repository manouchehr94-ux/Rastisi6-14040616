# catalog — Code Map

```
domain_id: D4
code_baseline: 5883a140
```

```
apps/catalog/
├── models.py             38 model classes (Product, ProductVariant(+QuerySet guard), StockMovement,
│                         Category, Brand, Vendor, MerchantCollection(+Item), Warehouse,
│                         WarehouseInventory, InventoryReservation, WarehouseTransfer(+Item),
│                         IndustryTemplate(+family), StoreIndustryInstallation, StoreTemplateUpdate,
│                         Attribute/Value, ProductAttributeValue, ProductOption/Value,
│                         VariantOptionValue, CategoryAttributeSchema, CategoryRecommendedOption,
│                         Specification(+Template/Field), Review, ProductImage/Video, ...)
├── views.py              home / product-list / product-detail / collection-index/detail
├── urls.py               storefront catalog routes (included at /)
├── context_processors.py nav_categories
├── services/             31 files (inventory_service, product_publish/draft, variant/variant_engine,
│                         reservation, warehouse, transfer, industry_template, category_schema,
│                         collection, pricing, template_validation/update, ...)
├── industry_templates/   template data
├── seed_data/
├── templatetags/
├── commands/ + management/commands/  cleanup_stale_product_drafts, expire_inventory_reservations,
│                         seed_industry_templates, validate/verify_inventory_consistency, ...
├── migrations/
└── tests/
```

## Where to look
| Concern | File |
|---|---|
| Stock (the one writer) | `services/inventory_service.py` (+ StockMovement) |
| Product publish/draft | `services/product_publish_service.py` / `product_draft_service.py` |
| Variants | `services/variant_service.py` / `variant_engine_service.py` (+ QuerySet guard in models.py) |
| Industry templates | `services/industry_template_service.py` |
| Pricing (for cart) | `services/pricing_service.py` |
| Storefront home render | `views.py::home` → storefront_builder.render_service |
