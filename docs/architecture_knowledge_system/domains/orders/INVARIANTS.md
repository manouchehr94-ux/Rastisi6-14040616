# orders — Invariants

```
domain_id: D6
code_baseline: 5883a140
```

Invariants that must remain true. Sources: model constraints, service guards, ADRs (design intent).

## Enforced in code (VERIFIED)
1. **Order code is unique** (`Order.code` unique).
2. **Order creation is idempotent** — partial `uniq_order_idempotency_key_when_set`; the key comes
   from the cart `checkout_token` (ADR-15).
3. **`vendor.store == order.store`** — enforced in `Order.clean()`.
4. **`Order.status` transitions are legal** — only via `change_order_status` against
   `ALLOWED_TRANSITIONS`; terminal states (delivered/canceled) cannot transition.
5. **Gateway payment marks PAID only from PENDING, under lock** — conditional
   `.filter(payment_status=PENDING).update(...)`; concurrent double-pay yields `updated == 0`.
6. **PaymentAttempt final states are idempotent** — `is_final` short-circuits re-verification;
   `idempotency_key` and `gateway_track_id` are partially unique.
7. **COD never marks the order PAID** — order stays PENDING; merchant confirms via DELIVERED.
8. **Only MANUAL refunds execute** — `refund_service` raises for `method=GATEWAY` (ADR-33).
9. **Refund amounts derive from the immutable Order snapshot**, not live prices (ADR-33/35).
10. **Return transitions are legal** — model-level `ReturnRequest.ALLOWED_TRANSITIONS`.
11. **Inventory changes only via `catalog.inventory_service` (+ StockMovement)** — orders reserves/
    consumes; never writes stock directly (ADR-31/38/39).
12. **Currency conversion (Toman→Rial) happens only inside the Zibal adapter.**

## NOT enforced by a guard (⚠️ — this is H1 / DR-1)
- **`Order.payment_status` transitions are NOT validated against any table.** There is no invariant
  preventing an illegal payment_status transition; the three writers each assign directly (only the
  gateway path is lock-protected). Treat "payment_status is always set through a legal, guarded
  transition" as a **desired** invariant that the code does **not** currently enforce.

## Financial-integrity notes
- Browser return is never treated as payment proof (both gateway and simulation confirm server-side
  or via a controlled flag).
- `amount` is validated against the order/attempt snapshot, not the browser.
