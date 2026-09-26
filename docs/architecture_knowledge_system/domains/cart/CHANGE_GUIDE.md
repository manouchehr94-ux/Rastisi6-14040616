# cart — Change Guide

```
domain_id: D5
code_baseline: 5883a140
known_risks: M9, L2
```

## Recipe: Change cart pricing / totals
- **READ FIRST:** `cart_service.reprice_cart_items`, `pricing`, `catalog.pricing_service`.
- **CANONICAL OWNER:** `cart_service` (writes) + catalog `pricing_service` (price source).
- **INVARIANTS:** `CartItem.unit_price` is a server snapshot from catalog — never client price.
- **⚠️ M9:** orders also reprices CartItem at checkout — a pricing change may need to align with
  `orders.create_order_from_cart` reprice logic. Read [`../orders/CHANGE_GUIDE.md`](../orders/CHANGE_GUIDE.md).

## Recipe: Change coupons
- **READ FIRST:** `coupon_service`, `Coupon` model (ADR-32 per-store uniqueness).
- **⚠️** `Coupon.used_count` is incremented by **orders** (`create_order_from_cart`) — a cross-domain
  write. A change to usage accounting spans cart + orders.

## Recipe: Change gift wrap
- **READ FIRST:** `gift_wrap_service` (server-authoritative — ignores client price).

## Recipe: Change add-to-cart / cart item mutation
- **READ FIRST:** `cart_service.add_item_to_cart` (membership-fence lock ordering).
- **⚠️ L2:** `orders.views.checkout_item_update/remove` mutate CartItem outside the checkout fence;
  and `orders` deletes items directly. There is no cart service for orders' deletions (M9). A change
  to cart-item mutation should consider these external writers.

## Recipe: Change checkout idempotency token
- **READ FIRST:** `Cart.checkout_token` (ADR-15), `orders.create_order_from_cart` (consumes it).
- **⚠️** the token is the order idempotency anchor — changing it affects order-creation idempotency.
