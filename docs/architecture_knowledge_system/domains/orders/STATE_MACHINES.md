# orders — State Machines

```
domain_id: D6
code_baseline: 5883a140
open_decisions: DR-1
```

## Order.status — GUARDED (table)
```
pending    → {processing, canceled}
processing → {shipped, canceled}
shipped    → {delivered, canceled}
delivered  → (terminal)
canceled   → (terminal)
```
- Table: `order_service.py:45` `ALLOWED_TRANSITIONS`; `FINAL_STATUSES` at `:54`; enforced at
  `:550` inside `change_order_status` (the sole writer). Illegal/same-state transitions raise.
- Transition sites: create (initial pending), payment success (→processing), dashboard order_detail.

## ⚠️ Order.payment_status — NOT GUARDED (no table) — H1 / DR-1
```
pending → paid      (gateway conditional update; simulate direct save)
pending → failed    (simulate direct save)
paid    → refunded  (refund_service direct save)
```
- **No `ALLOWED_TRANSITIONS` and no central guard.** Three writers (see
  [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md)). Only the gateway path locks the Order and updates
  conditionally on `payment_status=PENDING`; simulate/refund do plain `save()`.
- **Consequence for change:** there is no single place to add a new payment state or enforce a
  legal transition. Adding a state (e.g. `partially_refunded`) touches all three writers and every
  reader. This is the crux of DR-1.

## PaymentAttempt.status — GUARDED (is_final)
```
created → requesting → redirect_ready → pending → {succeeded, failed, canceled, expired}
```
FINAL = {succeeded, failed, canceled, expired}. `is_final` short-circuits re-processing in
`gateway_payment_service`.

## Refund.status — GUARDED (final-state checks)
```
pending → approved → processing → {succeeded, failed, cancelled}
```
`method` ∈ {manual, gateway}; **gateway raises (not implemented, ADR-33)**.

## ReturnRequest.status — GUARDED (model-level table)
```
requested → under_review → approved → in_transit → received → inspected → completed
          ↘ rejected                                                    ↘ cancelled
```
- Table: `orders/models.py:1047` `ReturnRequest.ALLOWED_TRANSITIONS`; enforced in
  `return_service._transition` (`return_service.py:90`) under `@atomic` + select_for_update.
- `complete_return` restocks + calls `refund_service.execute_order_refund(key="return:<pk>")`.

## Interaction: payment success → order status
On successful payment (either path), `change_order_status(order, PROCESSING)` is called — this is
the one bridge from `payment_status`=PAID to `status`=processing. COD does **not** mark paid, so it
does not auto-advance status.
