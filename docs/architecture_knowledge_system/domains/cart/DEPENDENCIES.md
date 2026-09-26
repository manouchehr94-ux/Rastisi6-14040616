# cart — Dependencies

```
domain_id: D5
code_baseline: 5883a140
known_risks: M9
```

## cart depends ON
| Target | Type | What |
|---|---|---|
| `catalog` | reads | `pricing_service` effective price; Product/Variant for CartItem |
| `stores` | reads | Store scope (Coupon store-owned) |
| `core` | uses | TimeStampedModel |

## Depends ON cart (writers into cart — M9)
| Source | Type | What |
|---|---|---|
| `orders.order_service` | writes | reprice CartItem.unit_price; Coupon.used_count += 1 |
| `orders.checkout_service` / `orders.views` | writes | delete cart items (L2 for views) |
| `customers.auth_service` | writes | merge_guest_cart |
| storefront | reads | cart_badge context processor |

## Note
cart is written by two other domains (orders, customers). It has no service that orders calls for
item deletion (orders reaches into `cart.items`) — M9.
