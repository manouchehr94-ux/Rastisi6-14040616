# Tenant-isolation verification — 2026-11-06

Branch `security/tenant-isolation-20261106`, based on the pushed Checkout branch `dev/platform-checkout-unify-20261106` (`8ad4b687`). Local only.

The three test IDs below come from an external audit harness; they do not exist in this repository's history. Each scenario was therefore
reproduced independently against the current code (`apps/orders/tests/test_tenant_isolation_regression.py`, PostgreSQL 16.15).

| Finding | Result | Evidence |
|---|---|---|
| `service_order_lookup_cross_tenant` | **NOT_REPRODUCED** | Every order lookup in non-test code is store-scoped (`_get_own_order` filters `store` + `customer`; dashboard views `get_object_or_404(..., store=store)`; `card_transfer_service.submit(order_id, store=...)`; `execute_order_refund` rejects a foreign store; the checkout idempotency-token replay returns an order only for the same customer **and** store). Tests: `ServiceOrderLookupCrossTenantTests`. |
| `http_payment_result_other_store_same_user` | **NOT_REPRODUCED** | Same global Customer on Store B's host requesting Store A's order code: 404 for result/start/initiate. Different user, anonymous, and an unknown host: no order data. The 404 page only echoes the *requested* URL (canonical/og:url), never order data. Positive control: owners still see their own result page. Tests: `HttpPaymentResultOtherStoreSameUserTests`. |
| `refund_idempotency_cross_tenant` | **REPRODUCED (low/medium) and FIXED** | No foreign refund was ever returned or mutated, but the idempotency-key namespace was **global** (lookup and DB constraint `uniq_refund_idempotency_key_when_set`). The key is client-supplied (`POST token`, ≤64 chars), so Store B reusing a key used by Store A was refused with a "does not match" error — a cross-tenant collision and a one-bit existence oracle. |

## Fix for `refund_idempotency_cross_tenant`

* Lookups in `execute_order_refund` (both the pre-check and the `IntegrityError` race path) are now `Refund.objects.filter(store=store, idempotency_key=…)`.
* Constraint replaced with `UniqueConstraint(store, idempotency_key)` — migration `orders.0022_refund_idempotency_key_per_store`. The new constraint is strictly weaker
  than the old one, so every existing row satisfies it (no data change). Reversing it fails only if two stores have since used the same key.
* Behaviour now: same store + same key + same request → the same refund (idempotent retry, unchanged); same store + same key + different request/order → refused (unchanged);
  different store + same key → an independent refund (changed, intended). Store A's refund is never read, changed or described.
* `test_refund_service.test_retry_key_rejects_other_store_and_order` encoded the earlier "reject" mitigation. Its invariant (a store never obtains or alters another store's refund)
  still holds and is asserted more strongly; the same-store/different-order rejection is asserted explicitly.
* PostgreSQL concurrency: two stores racing on one key → two independent refunds, no error; one store racing three times on one key → exactly one refund.

## Out of scope / residual

* `Order.idempotency_key` (checkout token) and `PaymentAttempt.idempotency_key` keep a global constraint; they are server-generated high-entropy tokens, and the replay path
  already compares customer and store (existing `test_idempotency_tenant`, `test_checkout_token_cycle`). Not changed.
* This is code-level and test-level verification on synthetic fixtures; no production data or real gateway was involved.
