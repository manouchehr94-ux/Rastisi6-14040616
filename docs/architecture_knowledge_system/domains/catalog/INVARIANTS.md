# catalog — Invariants

```
domain_id: D4
code_baseline: 5883a140
```

## Enforced in code (VERIFIED)
1. **Stock never changes without a `StockMovement`** — `inventory_service` is the only writer; it
   mirrors into `WarehouseInventory` in the same transaction (ADR-31/38).
2. **`Product`/`ProductVariant.stock` is the single authoritative sellable field** — `WarehouseInventory`
   is a synced breakdown, not a competing source (ADR-38).
3. **Variant normalization cannot be bypassed** — `ProductVariantQuerySet` blocks
   `update()`/`bulk_update()`/`bulk_create()` (`VariantMutationError`).
4. **`uniq(store,slug)` and `uniq(store,sku)` for Product**; cross-store coherence in `clean()`.
5. **Variant reconciliation never hard-deletes** — obsolete combinations are marked, not removed
   (ADR-21).
6. **Inventory reservation reduces computed "available", not stored "on-hand"**, and is created +
   consumed synchronously inside `create_order_from_cart`'s transaction (ADR-39) — never held open.
7. **Warehouse transfers move only the per-warehouse breakdown**; aggregate stock untouched (ADR-40).
8. **Industry templates are platform-owned/read-only**; install deep-copies into Store-owned rows,
   never links to the shared template (ADR-22); template versions are immutable (ADR-25).
9. **Category attribute schema:** direct mappings win over inherited (ADR-23); product attribute
   values are never deleted on category change — they become invisible until explicit cleanup (ADR-24).
10. **Import writes only through the service/model layer** — never a second product-creation path;
    stock always through inventory service (ADR-58/60).

## Note
Product **row** writes are less strongly single-sourced than stock (dashboard writes directly), but
the stock field, variants, and inventory ledger are the strongly-guarded core.
