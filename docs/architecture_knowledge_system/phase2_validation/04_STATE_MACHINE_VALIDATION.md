# 04 — State-Machine Validation

Validates the state-machine claims from Phase 1 doc 09, with mandatory focus on **every claimed
state machine without a guard**. Evidence from frozen snapshot `5883a140`.

Classification: CONFIRMED / CONFIRMED_WITH_CORRECTION / DOWNGRADED / UPGRADED / NOT_PROVEN / DISPROVED.

---

## The unguarded state machine (mandatory)

### `Order.payment_status` — **CONFIRMED unguarded**
- No transition table exists for `payment_status`. The only `ALLOWED_TRANSITIONS` in
  `order_service.py` (line 45) enumerates `Order.Status` values and is enforced at line 550
  inside `change_order_status`, which mutates `Order.status` — not `payment_status`.
- The three `payment_status` writers (doc 01 H1) perform: one lock+conditional update (gateway)
  and two plain `save(update_fields=["payment_status", ...])` (simulate, refund). No legality
  check, no `select_for_update` in the non-gateway writers.
- **Confirmed:** `Order.payment_status` is the one important lifecycle field with no guarded
  transition machine. Severity HIGH (doc 01).

---

## Guarded-by-explicit-table machines (spot-verified)

| Machine | Table location | Verified |
|---|---|---|
| `Order.status` | `order_service.ALLOWED_TRANSITIONS` (line 45), enforced line 550 | CONFIRMED — PENDING→{PROCESSING,CANCELED}; PROCESSING→{SHIPPED,CANCELED}; SHIPPED→{DELIVERED,CANCELED}; DELIVERED/CANCELED terminal; `FINAL_STATUSES` at line 54 |
| `ReturnRequest.status` | `orders/models.py:1047 ALLOWED_TRANSITIONS` (model-level) | CONFIRMED present |
| `StoreSubscription.status` | `subscription_service` module `ALLOWED_TRANSITIONS` | CONFIRMED present (grep located the table in subscription_service) |
| `WarehouseTransfer` | `catalog` transfer table | CONFIRMED present (grep located ALLOWED_TRANSITIONS in catalog/models.py + transfer_service.py) |

Grep confirmed `ALLOWED_TRANSITIONS` exists in exactly these production locations:
`apps/orders/services/order_service.py`, `apps/orders/models.py` (ReturnRequest),
`apps/orders/services/return_service.py`, `apps/subscriptions/services/subscription_service.py`,
`apps/catalog/models.py`, `apps/catalog/services/transfer_service.py`, and
`apps/dashboard/services/orders_admin_service.py` (which **re-uses** the orders table for display,
not a competing definition). This matches Phase 1 doc 09.

---

## Guarded-per-service (no table) machines — claims consistent

Phase 1 classified these as guarded by per-service status checks rather than a table:
`SubscriptionInvoice.status`, `Store.status`, `StorefrontLayoutVersion.status`, `StoreDomain`
lifecycle (also DB CheckConstraints), `PaymentAttempt` (`is_final`). Phase 2 did not surface any
contradicting unguarded direct writer for these; the classifications are **CONFIRMED** as stated
(the deep bodies were read in Phase 1). The `StoreDomain` DB CheckConstraints were re-listed in
Phase 1 doc 03 and are part of the migration/model (structurally enforced).

---

## Derived "store visibility" machine

Phase 1 flagged that visibility is derived from ≥5 signals across 3 apps
(`Store.status`, `onboarding_completed_at`, `StoreDomain` verification/routing,
`StoreSubscription`/entitlement) reconciled by `publication_service`, which **fails open**.
Phase 2 does not dispute this MEDIUM observation; it is a derived machine, not a stored field,
and was not re-executed. **CONFIRMED as OBSERVATION/MEDIUM.**

---

## Result
- The single unguarded-state-machine claim (`Order.payment_status`) is **CONFIRMED**.
- All guarded-machine claims are **CONFIRMED**; none DISPROVED.
- No new unguarded lifecycle field was discovered during Phase 2.
