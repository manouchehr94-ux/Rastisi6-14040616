# Plan: store-scoped carts (`Cart.store`) — AUDIT + MIGRATION/BACKFILL PLAN (nothing implemented, nothing migrated)

Status: proposal for approval. No migration has been created or run anywhere; QA-Windows and Production are untouched. This document was prepared against HEAD `ae83ab0d`.

## 1. Audit — what is wrong today
`apps/cart/models.py::Cart` = `customer` (nullable FK, global) + `session_key` + `checkout_token`; **no store, no unique constraint**. `Customer` is global by design, so a customer shared by two stores has ONE cart.

| Place | Today | Effect |
|---|---|---|
| `cart_service.get_cart` | customer: `get_or_create(customer=…)` / `.filter(customer=…).first()`; guest: `(session_key, customer=None)` | same cart for every store; `get_or_create` raises `MultipleObjectsReturned` if a customer has 2 carts |
| `auth_service.merge_guest_cart` (login, OTP login, checkout OTP, checkout_pay) | merges the guest cart of the session into the customer's single cart | a guest cart built on store A is merged into the cart that store B also uses |
| `cart_preview._resolve_existing_cart`, `cart/context_processors.cart_badge` | same lookups | badge/mini-cart count other stores' items (badge already scoped by `product__store` in the account fix, as a stop-gap) |
| `cart/views._cart_context`, `checkout_service.build_context` | `cart.items.all()` | store B's product names/prices appear in store A's cart/checkout |
| `checkout_service.finalize_order` → `order_service.create_order_from_cart` | refuses items of another store ("کالا متعلق به این فروشگاه نیست") | no cross-store ORDER is possible, but a foreign line **blocks the customer's checkout** with an error they cannot fix on that storefront |
| coupons | applied code is kept in the session and always re-resolved with `store=` (ADR-32) | already safe; must keep working per store cart |
| `seed_shop` | `Cart.objects.create(customer=…)` | needs `store` |

QA data audit (isolated copy of the QA DB, read-only): 34 carts / 31 items; 32 customer carts, 2 guest carts; **1 customer with 2 carts**; 0 carts mixing stores; 0 carts with a `checkout_token`; 3 empty carts. The Windows QA/Production data must be audited with the same read-only command BEFORE any migration (§5).

Related latent defect found while reading `checkout_service.finalize_order` (to be confirmed end-to-end before fixing): `Cart.checkout_token` is created once and never rotated. A service-level probe (create order from a cart, delete its items, add an item, create the order again with the same token) returned the **first order** and created no second one — i.e. a repeat purchase from the same cart row would be treated as a replay. Proposed fix (inside this change set): clear the token in `add_item_to_cart` when the cart is empty (a new purchase cycle starts when the first item is added), which keeps double-click replay protection right after an order.

## 2. Target model
- `Cart.store` FK → `stores.Store` (`on_delete=CASCADE`, `related_name="carts"`, indexed).
- `UniqueConstraint(customer, store)` where `customer IS NOT NULL` → `uniq_cart_customer_store`.
- `UniqueConstraint(session_key, store)` where `customer IS NULL AND session_key != ""` → `uniq_cart_session_store`.
- `CheckConstraint`: `customer IS NOT NULL OR session_key != ""` (a guest cart must be addressable).
- Keep `checkout_token` on the cart (idempotency unchanged).

## 3. Code changes (after approval)
1. `get_cart(request, create=False, *, store=None)`: store = `resolve_store_for_service(request)`; unresolved host ⇒ `Http404` for storefront views / `None` for read-only badge paths. Customer path: `(customer, store)`; guest path: `(session_key, store)`.
2. `merge_guest_cart(request, customer, *, store)`: merges only the guest cart of `(session_key, store)` into `(customer, store)`; keeps the existing lock order (Product/Variant → Cart → CartItem) and `select_for_update` on the user cart; callers pass `store`.
3. `cart_preview`, `cart_badge`: filter by store; the interim `product__store` badge filter stays as a belt-and-braces check.
4. `add_item_to_cart`: refuse a product whose `store_id != cart.store_id` (defence); rotate empty-cart token as above.
5. `create_order_from_cart`: add `cart.store_id == store.pk` assertion next to the existing item check; no change to the locking/idempotency algorithm.
6. `finalize_order`, cart views, coupon code: unchanged apart from receiving the store-scoped cart; coupon stays session-based and store-validated.
7. `seed_shop`, Django admin (`list_display`/filters) get `store`.

## 4. Migration + backfill design (reversible, in the same 3-step pattern as `cart/0004–0006` for `Coupon.store`)
- **0010 schema**: add `store` NULLABLE + index. No constraints yet. Reversible (drop column).
- **Backfill** (idempotent function, also exposed as `manage.py backfill_cart_store --dry-run | --apply`, which prints a per-cart report and writes a CSV next to the DB backup; the data migration calls the same function):
  1. **Mixed-store carts**: group items by `product.store`. The group of the most recently touched item stays on the original cart (keeps id and `checkout_token`); every other group moves to a NEW cart `(same customer/session_key, store=that store, empty token)`. Items are re-pointed (`CartItem.cart`), never copied or deleted: quantity, `unit_price` snapshot, variant, gift-wrap fields and messages are untouched. Order/Transaction rows are not linked to carts (only `Order.idempotency_key == token`), so no financial record changes.
  2. **Single-store carts**: `store = that store`.
  3. **Empty carts**: customer carts → store of the order whose `idempotency_key == checkout_token` if any, else the customer's latest order store, else the customer's only `CustomerProfile` store, else delete (no items ⇒ no data); guest empty carts ⇒ delete unless they hold a token (then store from the order by token).
  4. **Duplicates per `(customer, store)` or `(session_key, store)`** (e.g. the QA customer with 2 carts): merge into the newest cart; same `(product, variant)` lines add their quantities (same rule as `merge_guest_cart`), destination snapshot price/gift-wrap kept; the retained cart keeps its token; a checkout token of a cart that already produced an order is preserved on the surviving cart. Merging may exceed stock — the customer sees the normal stock error at checkout (existing behaviour).
  5. Everything runs in `transaction.atomic()` per customer/session; the function is re-runnable (second run = no changes).
- **0011 constraints**: refuses to run if any `store IS NULL` remains (clear message with the count), then sets NOT NULL and adds the three constraints. Reversible (drops constraints, makes the column nullable).
- Performance: one pass over carts; QA scale is trivial; production scale to be read from the audit (§5) — chunked by `iterator(2000)`.

## 5. Rollout gates (each needs your separate approval)
1. Read-only audit command on the Windows QA DB (counts above + the list of mixed/duplicate carts) — no writes.
2. File-level backup of the QA DB (`copy db.sqlite3 db.sqlite3.bak-<timestamp>`) and verification that it opens.
3. `backfill_cart_store --dry-run`, review the report, then migrate on QA-Windows only.
4. Production: untouched until a separate decision (pg_dump backup, dry-run on a restored copy first).

## 6. Tests to write with the change
Two stores + one shared customer: separate carts per store; badge/mini-cart/cart page/checkout show only the current store; switching host (A↔B) keeps each cart intact; guest cart on A merges only into A's customer cart on login (B's guest cart untouched); logout/login cycle; checkout on A succeeds while B holds items (today: blocked) and does not touch B's cart or stock; coupon applied on A is not applied on B; concurrent `get_cart(create=True)` (get_or_create under the new unique constraint), `merge_guest_cart` + checkout lock-order tests (reuse the CAT-002 ones); backfill: mixed cart split without losing a line/price/gift-wrap/token, duplicates merged, empty carts handled, second run no-op, NOT NULL gate refuses when NULL remain; repeat purchase from the same cart creates a second order (token rotation) while a double-click right after the first order still returns it; no-order-created-cross-store assertions kept.

## 7. Risks
Data merges change quantities (mitigated by the report + backup); the token-rotation fix changes behaviour of a very sensitive path (needs the end-to-end confirmation first); any code that calls `get_cart` outside a request needs an explicit `store` (grep shows none besides views/services listed above).
