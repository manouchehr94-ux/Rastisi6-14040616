# cart — Data Model

```
domain_id: D5
code_baseline: 5883a140
source: apps/cart/models.py (3 models)
```

| Model | Key fields | Notes |
|---|---|---|
| **Cart** | `customer` (nullable), `session_key`, **`checkout_token`** (server-generated idempotency key) | No status field. `checkout_token` is the order-creation idempotency anchor consumed by orders (ADR-15) |
| **CartItem** | `product` (CASCADE), `variant` (SET_NULL), `quantity`, `unit_price` (server snapshot), gift-wrap fields | No unique constraints; `gift_wrap_line_total` property. Price always from catalog resolver |
| **Coupon** | `type` (percent/fixed/free_ship), `value`, `min_order`, `usage_limit`, `used_count`, `expires_at`, `is_active` | `uniq_coupon_code_per_store` (ADR-32); `save()` upper-cases code. Store-owned |

## Key facts
- `CartItem.unit_price` is a **server snapshot** from `catalog.pricing_service` — never client-supplied.
- `checkout_token` (on Cart) is the idempotency anchor for `orders.create_order_from_cart` (ADR-15).
- `Coupon` is store-scoped (code uniqueness per store, ADR-32).
