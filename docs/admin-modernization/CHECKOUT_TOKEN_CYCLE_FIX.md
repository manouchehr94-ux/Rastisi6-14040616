# P0 — repeat purchase returned the FIRST order (`Cart.checkout_token` never rotated)

Local commit, not pushed (awaits approval). No migration. Independent of `Cart.store`.

## What was wrong (confirmed end-to-end over the real HTTP views)
`Cart.checkout_token` is minted lazily at checkout and used as `Order.idempotency_key`, so a double click / network retry returns the first order instead of creating a second. It was **never cleared**, and a customer keeps ONE `Cart` row for life, so:
cart A → pay (order 1) → cart B → pay ⇒ `finalize_order` found `Order(idempotency_key=token)` and returned **order 1**; no second order, no stock deduction, the customer was sent to the old order. Reproduced for: logged-in customer, a guest who just got an auto-created account, the same product twice, three cycles in a row (`1 != 2`, `1 != 3` in `test_checkout_token_cycle` against the pre-fix code; 6 of the 8 first tests failed). Real-browser run (Chromium, isolated QA copy): before the fix the 2nd/3rd checkout would collapse; after it, 3 distinct orders (double-click in cycle 1 still created ONE order), one `order_placed` stock movement of −1 per order.

## Fix
1. **New purchase cycle = first item added to an empty cart.** `cart_service.start_new_checkout_cycle_if_empty(locked_cart)` clears a stale token. It runs in `add_item_to_cart` (after the existing `select_for_update` on the Cart row — the membership fence — so it is serialized with a concurrent checkout) and in `merge_guest_cart` (guest items entering an empty customer cart), the only two writers of cart membership.
2. **The token is NOT cleared on success**: a replay right after the order still returns that order (verified, also under concurrency).
3. **Token creation under the Cart row lock** (`get_or_create_checkout_token`, short transaction, released before the order transaction — the global lock order Product/Variant → Cart → CartItem is unchanged): two simultaneous first checkouts converge on one token instead of minting two.
4. **Lookup scoped to customer + store**: `finalize_order` and `create_order_from_cart` (both lookups, incl. the `IntegrityError` re-fetch) only treat an order as a replay if it belongs to the same customer and store; a token that collides with someone else's order is rotated, never returned.
No change to order creation, price confirmation, stock, coupon or payment code; `Order.idempotency_key` uniqueness constraint untouched.

## Tests (`apps/orders/tests/test_checkout_token_cycle.py`, 16)
HTTP: replay → first order and no second stock deduction; new item → independent second order (own lines, totals, key, stock); same product twice; replay after the second order returns the second; 3 cycles = 3 keys; a failed attempt does not burn the token; guest-created account second purchase; foreign-token collision. Service: stale instances converge on one token; token survives the order and is cleared only by the next cycle's first item (second item does not rotate again); guest-merge starts a new cycle; foreign order key is rotated. **Concurrency on a real PostgreSQL 16** (throw-away instance, 6 simultaneous double-submits ⇒ exactly 1 order and 1 deduction; replay racing the next purchase ⇒ never merged/duplicated, distinct keys, consistent stock; two simultaneous first items ⇒ both lines, token cleared once) — skipped on SQLite like the project's other concurrency tests.
Regression: `apps.cart apps.orders apps.customers` on SQLite 928 tests OK; on PostgreSQL checkout/price-confirmation/cat002/coupon-concurrency/cart 289 of 290 — the one failure (`test_coupon_concurrency.ConcurrentCampaignExecutionTests.test_overlapping_runs_issue_each_customer_once`, 0 outbox e-mails) fails identically on the commit before this fix.

## Found on the way (not fixed here — belongs to the Cart.store step)
Two simultaneous FIRST adds for a customer without a cart create TWO `Cart` rows (`get_or_create(customer=…)` has no unique constraint; reproduced on PostgreSQL). It is the same defect that left one demo customer with 30 carts in the QA copy. The `(customer, store)` unique constraint of the plan fixes it; until then `get_cart` can raise `MultipleObjectsReturned`.
