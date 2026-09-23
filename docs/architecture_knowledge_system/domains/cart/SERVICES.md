# cart — Services

```
domain_id: D5
code_baseline: 5883a140
source: apps/cart/services/ (5 files)
```

| Service | Responsibility | Txn / lock |
|---|---|---|
| **cart_service** | `get_cart` (read/create); `add_item_to_cart` (writes CartItem); `reprice_cart_items` (writes `CartItem.unit_price` to live catalog price) | `@atomic`; `select_for_update` Product/Variant → Cart → CartItem (membership fence) |
| **pricing** | `cart_totals`, `coupon_is_applicable` | read-only |
| **coupon_service** | coupon apply/validate | — |
| **gift_wrap_service** | `resolve_gift_wrap_selection` (server-authoritative; ignores client price) | — |
| **cart_preview** | cart preview rendering | read-only |

## Key discipline
- Prices always come from `catalog...resolve_effective_price` (single source) — the cart never
  trusts a client-supplied price. Gift-wrap price is server-authoritative too.
- The membership-fence lock ordering (Product/Variant → Cart → CartItem) is shared with
  `orders.create_order_from_cart` to avoid deadlocks/races (CAT-002).
