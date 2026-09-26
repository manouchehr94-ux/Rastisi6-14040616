# catalog — Change Guide

```
domain_id: D4
code_baseline: 5883a140
open_decisions: DR-7
```

## Recipe: Change product inventory / stock
- **READ FIRST:** [INVARIANTS](INVARIANTS.md) (#1/#2), `inventory_service`, [STATE_MACHINES](STATE_MACHINES.md).
- **CANONICAL OWNER:** `inventory_service` (the ONLY stock writer).
- **INVARIANTS:** every stock change needs a `StockMovement`; mirror WarehouseInventory in the same
  transaction; `Product/Variant.stock` is authoritative (ADR-38).
- **⚠️** Do NOT write `stock` directly or via bulk QuerySet — the `ProductVariantQuerySet` blocks it,
  and `Product.stock` should go through inventory_service. Reservations are created+consumed inside
  `orders.create_order_from_cart` (ADR-39).
- **DEPENDENT DOMAINS:** orders (reserve/consume), cart (availability), dashboard (import).
- **TESTS:** catalog inventory tests; `verify_inventory_consistency`.

## Recipe: Change product publish / draft lifecycle
- **READ FIRST:** [STATE_MACHINES](STATE_MACHINES.md) (two axes), `product_publish_service`/`product_draft_service`.
- **⚠️** `status`/`publish_at`/`visibility` and `is_draft_placeholder` are INDEPENDENT axes. Don't
  conflate. `storefront_visible_products` gates on active + not-draft + publish_at.

## Recipe: Change variants / options
- **READ FIRST:** `variant_service`/`variant_engine_service`, [INVARIANTS](INVARIANTS.md) (#3/#5).
- **⚠️** normalization is enforced by the QuerySet; obsolete variants are marked, never hard-deleted (ADR-21).

## Recipe: Change industry templates
- **READ FIRST:** `industry_template_service`, [DATA_MODEL](DATA_MODEL.md), ADR-22/25/29.
- **⚠️** templates are platform-owned/read-only; install deep-copies into Store-owned rows; versions
  immutable; updates default additive-only. `default_section_keys` validated in storefront_builder.

## Recipe: Change categories / attribute schema
- **READ FIRST:** `category_schema_service` (ADR-23 direct-wins; ADR-24 no-delete-on-change).

## Recipe: Change Product↔Vendor↔Store relationship
- **BLOCKED BY DR-7.** ADR-1 defers Vendor's meaning; do not decide here.

## Recipe: Change catalog import
- **READ FIRST:** `dashboard.import_service` + catalog services. **⚠️** ADR-58: import writes ONLY
  through the service/model layer — never a second product-creation path; stock via inventory_service.
