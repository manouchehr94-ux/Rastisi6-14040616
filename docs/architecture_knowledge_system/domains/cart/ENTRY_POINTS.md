# cart — Entry Points

```
domain_id: D5
code_baseline: 5883a140
```

## Public HTTP (`apps/cart/urls.py`, included at `cart/`)
cart add / update / remove views (`apps/cart/views.py`), plus the orders checkout views that also
mutate cart (`checkout_item_update/remove` — L2, in the orders app).

## Context processors (`apps/cart/context_processors.py`)
`cart_badge` — injected into storefront templates.

## Called-into (services)
- `cart_service.get_cart/add_item_to_cart/reprice_cart_items` — from cart views and from
  `orders.create_order_from_cart` (reprice).
- `pricing.cart_totals` — from checkout.

## Signals / async
None.
