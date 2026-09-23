# cart — Open Decisions

```
domain_id: D5
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

## No DR-1…DR-8 item originates in cart
cart has no open architectural decision from the DR register.

## Relevant findings (not DRs)
- **M9** — orders→cart cross-domain mutation (reprice CartItem, delete items, Coupon.used_count).
  cart exposes no service for orders' deletions.
- **L2** — `orders.views.checkout_item_update/remove` mutate CartItem outside the checkout
  membership-fence transaction.

These are documented smells. Whether to introduce a cart-owned mutation API for orders would be a
**new** decision (not on the current register). No option is selected.
