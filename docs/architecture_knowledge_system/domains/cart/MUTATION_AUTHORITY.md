# cart — Mutation Authority

```
domain_id: D5
code_baseline: 5883a140
known_risks: M9, L2
```

| Entity | Canonical writer | Cross-domain writers (M9) |
|---|---|---|
| **CartItem** | `cart_service.add_item_to_cart` / `reprice_cart_items` (membership-fence `select_for_update` locking) | `orders.order_service.create_order_from_cart` (reprice `unit_price`); `orders.checkout_service.finalize_order` (`cart.items.all().delete()`); `orders.views.checkout_item_update/remove` (`.save()`/`.delete()` — L2, outside the checkout fence); `customers.auth_service.merge_guest_cart` |
| **Cart** | `cart_service.get_cart` (read/create) | `customers.auth_service.merge_guest_cart` (membership) |
| **Coupon** | `cart.coupon_service` (via dashboard) | `orders.order_service.create_order_from_cart` (`used_count += 1`) |

## ⚠️ Cross-domain reality (M9)
cart is written by **orders** (reprice/delete/coupon count) and **customers** (merge). cart does
**not** expose a deletion service for orders — orders reaches directly into `cart.items`. This is a
documented cross-domain mutation smell (M9); `checkout_item_update/remove` also mutate CartItem
outside the checkout membership-fence transaction (L2).

## Pricing authority
`CartItem.unit_price` is always resolved from `catalog.pricing_service` — the price source of truth
is catalog, not cart.
