# cart — Boundaries

```
domain_id: D5
code_baseline: 5883a140
known_risks: M9
```

## Owns
`Cart` (+ checkout_token), `CartItem` (server-priced), `Coupon` (store-owned); cart pricing/coupon/
gift-wrap services; the membership-fence add/reprice path.

## Does NOT own
- **The price source** — `catalog.pricing_service` (cart reads effective prices).
- **The order** — `orders`. orders reads and MUTATES the cart at checkout (reprice/delete/coupon
  count — M9); cart does not own that flow.
- **Product/inventory** — `catalog`.

## Cross-domain relationships (M9)
- **In (writers into cart):** `orders` (reprice/delete/coupon used_count), `customers` (guest merge).
- **Out:** cart reads catalog pricing.

## Boundary smell (M9/L2)
orders reaches directly into `cart.items` to delete/reprice; cart exposes no service for that.
`checkout_item_update/remove` mutate CartItem outside the checkout fence (L2). Documented, not resolved.
