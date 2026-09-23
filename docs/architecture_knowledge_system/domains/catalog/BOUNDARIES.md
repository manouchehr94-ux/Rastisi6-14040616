# catalog — Boundaries

```
domain_id: D4
code_baseline: 5883a140
open_decisions: DR-7
```

## Owns
Products/variants/options/attributes, categories/brands, `Vendor`, collections, ledgered inventory
(warehouses/inventory/reservations/transfers + `StockMovement`), industry templates (platform-owned)
+ installs, specs, reviews, product media.

## Does NOT own
- **Store identity** — `stores`. (Note: `Vendor` vs `Store` ambiguity — A1/DR-7.)
- **Render layer** — `storefront_builder` (catalog.home calls render_service).
- **Cart** — `cart` (catalog provides pricing via `pricing_service`).
- **Order-time stock decisions** — orders *calls* catalog inventory/reservation services.

## Cross-domain relationships
- **In:** `dashboard` (product/category/etc. writes, some direct); `orders` (reserve/consume stock);
  `portal.provisioning_service` (default Warehouse + industry template install).
- **Out:** `storefront_builder.render_service` (lazy import for home render);
  `storefront_builder` SECTION_REGISTRY (validates `IndustryTemplate.default_section_keys` there).

## Ambiguity (DR-7)
`Vendor` vs `stores.Store`: ADR-1 says Store is not Vendor and defers Vendor's final meaning
(marketplace seller vs supplier vs …). The coexistence contract is not fully expressed in code.
