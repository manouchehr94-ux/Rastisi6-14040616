# catalog — Data Model

```
domain_id: D4
code_baseline: 5883a140
source: apps/catalog/models.py (38 model classes)
```

## Core commerce
| Model | Key lifecycle / fields | Constraints |
|---|---|---|
| **Product** | `status` (draft/active/inactive); `visibility` (public/link_only); `publish_at` (scheduled); **`is_draft_placeholder`** (in-progress build, independent of status); `stock` | `uniq(store,slug)`, `uniq(store,sku)`; `clean()` cross-store coherence; category PROTECT (nullable for drafts) |
| **ProductVariant** | price/extra/compare_at/wholesale; `combination_key`; `is_default`/`is_obsolete`; store copied from product | 4 unique constraints; `ProductVariantQuerySet` blocks `update()/bulk_update()/bulk_create()` normalization bypass (`VariantMutationError`) |
| **StockMovement** | append-only ledger | the canonical inventory audit |
| **Category** | tree (self-FK); `source_template_category` | `uniq(store,slug)` |
| **Brand / Vendor** | — | Vendor coexists with `stores.Store` (A1/DR-7) |
| **MerchantCollection** (+Item) | curated products | — |

## Inventory
| Model | Lifecycle |
|---|---|
| **Warehouse / WarehouseInventory** | per-warehouse breakdown (synced from Product/Variant.stock — ADR-38) |
| **InventoryReservation** | `status` (active/consumed/released/expired/cancelled) — reduces "available" (computed), not "on-hand" (ADR-39) |
| **WarehouseTransfer** (+Item) | explicit `ALLOWED_TRANSITIONS` (draft→requested→in_transit→received/cancelled); moves only the per-warehouse breakdown (ADR-40) |

## Templates / attributes / other
`IndustryTemplate` (platform-owned; `Readiness` draft→…→production_ready→deprecated/archived; `content_fingerprint`; `default_section_keys` validated in storefront_builder) + `IndustryTemplateCategory/Attribute/AttributeValue/CategoryAttributeMapping/RecommendedOption`; `StoreIndustryInstallation` (OneToOne store); `StoreTemplateUpdate` (pending/completed/failed, idempotency_key); `Attribute`/`AttributeValue`/`ProductAttributeValue`; `ProductOption`/`ProductOptionValue`/`VariantOptionValue`; `ProductTag`; `ProductMetafield`; `CategoryAttributeSchema`/`CategoryRecommendedOption`; `Specification`/`SpecificationTemplate`/`SpecificationTemplateField`; `Review`; `ProductImage`/`ProductVideo`; `IndustryTemplateValidationResult`.

## Key facts
- **Two orthogonal Product lifecycles:** publish (status/publish_at/visibility) and build
  (`is_draft_placeholder` True→False). Independent.
- **Industry templates are platform-owned, read-only; install deep-copies into Store-owned rows**
  (ADR-22) — never links to the shared template.
