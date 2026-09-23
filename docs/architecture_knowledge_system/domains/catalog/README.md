# Domain: catalog (D4) — Catalog & Inventory

```
domain_id: D4
app: apps/catalog
status: CANONICAL
readiness: PARTIAL
code_baseline: 5883a140
open_decisions: DR-7
known_risks: M13
```

The largest data domain (38 model classes, 31 services). Owns products/variants/options/attributes,
categories/brands, collections, **ledgered inventory**, industry templates, specs, and reviews.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [STATE_MACHINES](STATE_MACHINES.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[INVARIANTS](INVARIANTS.md) · [TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) ·
[CODE_MAP](CODE_MAP.md) · [HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* FLOWS (canonical Flows 1/2/11), SECURITY/TRANSACTIONS/API_AND_EVENTS/ARCHITECTURE/
TROUBLESHOOTING → INVARIANTS + SERVICES.

## Orientation
- **Owns:** `Product` (+ status/stock/draft lifecycle), `ProductVariant` (+ normalization-guarding
  QuerySet), `StockMovement` (ledger), `Category`, `Brand`, `Vendor`, `MerchantCollection`,
  `Warehouse`/`WarehouseInventory`/`InventoryReservation`/`WarehouseTransfer`, `IndustryTemplate`
  (platform-owned) + install, specs/attributes/options/reviews.
- **Does NOT own:** Store identity (`stores`), the render layer (`storefront_builder`), the cart.
- **Canonical services:** `inventory_service` (the ONLY stock writer, ledgered), `product_publish_service`,
  `product_draft_service`, variant services, `industry_template_service`, + ~25 more.
- **Key invariant:** stock never changes without a `StockMovement` (ADR-31/38/39).
- **Ambiguity:** `Vendor` vs `stores.Store` (A1/DR-7) — ADR-1 defers Vendor's meaning.
