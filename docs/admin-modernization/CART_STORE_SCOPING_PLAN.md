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

Related defect (CONFIRMED end-to-end and FIXED separately, see `CHECKOUT_TOKEN_CYCLE_FIX.md`, independent of this migration): `Cart.checkout_token` was never rotated, so a repeat purchase returned the first order.
Also confirmed on PostgreSQL: two simultaneous first adds create two `Cart` rows for one customer (no unique constraint) — the cause of the 30 carts of one demo customer in the QA copy; the `(customer, store)` constraint below fixes it.

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

## 4. Migration + backfill design (reversible, staged like `cart/0004–0006` for `Coupon.store`) — NOTHING is deleted or merged without an explicit policy you approve
Principles: no cart line is deleted or duplicated; price snapshots (`unit_price`), gift-wrap fields, messages, discounts (session coupon is untouched), and valid `checkout_token`s are preserved; every destructive-looking step is a **policy decision** listed by the read-only audit first.
- **0010 schema**: add `store` NULLABLE + index. No constraints. Reversible (drop column).
- **Backfill** — a re-runnable function exposed as `manage.py backfill_cart_store --dry-run | --apply`. `--apply` is refused unless a policy file (reviewed by you, derived from the audit) is passed and a backup marker exists. Only the **unambiguous** cases are automatic:
  1. *Single-store, non-empty carts* → `store = that store` (no other change).
  2. *Mixed-store carts* (policy: which store keeps the original cart/token; default proposal = store of the most recently touched line): lines of the other stores are **moved** (`CartItem.cart` re-pointed, never copied/deleted) to a new cart `(same customer/session_key, that store, empty token)`.
  3. *Empty carts* → `store` derived only when exact (token ↔ `Order.idempotency_key` of the same customer, else the customer's only order store). Otherwise **left NULL and reported** — they are NOT deleted by the migration; deletion/keep is your policy decision (a separate, explicit, logged cleanup command later).
  4. *Duplicates per (customer, store) / (session_key, store)*: **not merged automatically**. The audit lists them; your policy decides per case (e.g. keep newest + move/merge lines with the `merge_guest_cart` rule: same product+variant adds quantities, destination snapshot price/gift-wrap kept). Until resolved the unique constraint is not created.
  Every applied change is written to a CSV ledger (cart id, action, from→to, line ids) so the whole backfill is auditable and can be reversed by script.
- **0011 constraints**: refuses to run while any `store IS NULL` or any duplicate pair remains (message with counts); then NOT NULL + the three constraints. Reversible (drops the constraints, relaxes NOT NULL).
- Performance: one pass, chunked (`iterator(2000)`); scale known from the audit.

## 5. Rollout gates (each needs your separate approval; Production is out of scope)
1. **Ship the read-only audit command** (`audit_cart_scope`, this branch) to QA-Windows:
   `cd D:\Projects\RastiSi\QA_ADMIN_PANEL_20261029` → stop the 8008 server → `git status --short` (must be clean) → `git fetch origin feature/admin-panel-modernization-20261029` → `git merge --ff-only <SHA I give you after you approve the push>` → run with the QA environment/venv exactly as for the server (same `DJANGO_MEDIA_ROOT` etc.): `python manage.py audit_cart_scope --limit 100 > ..\audit_cart_scope_QA.txt` (a `--json` variant exists). It opens the DB through a read-only guard and prints only counts, internal ids and 8-hex fingerprints — safe to paste back. It needs no migration and does not write.
2. Review the audit together; decide the policies for mixed / duplicate / empty carts.
3. File-level backup of the QA DB (`copy db.sqlite3 db.sqlite3.bak-<yyyymmdd-hhmm>`, verify it opens) — before any real change.
4. `backfill_cart_store --dry-run` → review the ledger → apply on QA-Windows only → run the two-store regression.
5. Production: untouched until a separate decision (pg_dump backup, dry run on a restored copy first).

## 6. Tests to write with the change
Two stores + one shared customer: separate carts per store; badge/mini-cart/cart page/checkout show only the current store; switching host (A↔B) keeps each cart intact; guest cart on A merges only into A's customer cart on login (B's guest cart untouched); logout/login cycle; checkout on A succeeds while B holds items (today: blocked) and does not touch B's cart or stock; coupon applied on A is not applied on B; concurrent `get_cart(create=True)` (get_or_create under the new unique constraint), `merge_guest_cart` + checkout lock-order tests (reuse the CAT-002 ones); backfill: mixed cart split without losing a line/price/gift-wrap/token, duplicates merged, empty carts handled, second run no-op, NOT NULL gate refuses when NULL remain; repeat purchase from the same cart creates a second order (token rotation) while a double-click right after the first order still returns it; no-order-created-cross-store assertions kept.

## 7. Risks
Data merges change quantities (mitigated by the report + backup); the token-rotation fix changes behaviour of a very sensitive path (needs the end-to-end confirmation first); any code that calls `get_cart` outside a request needs an explicit `store` (grep shows none besides views/services listed above).
