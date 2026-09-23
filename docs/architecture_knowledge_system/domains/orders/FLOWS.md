# orders — Runtime Flows

```
domain_id: D6
code_baseline: 5883a140
source: Phase 1 doc 08 (Flows 2, 3a, 3b, 4)
```

## Flow: Order creation from cart (Phase 1 Flow 2)
```
checkout → orders.views → order_service.create_order_from_cart
  @atomic; lock Product/Variant → Cart → CartItem (membership fence)
  reads Cart/CartItem/Product/Variant/Coupon
  writes Order, OrderItem, OrderStatusHistory(initial), Coupon.used_count+=1, CartItem.unit_price
  reserves + consumes inventory (catalog + StockMovement)
  idempotency: pre-check idempotency_key (from cart checkout_token) + DB-unique fallback in savepoint
  raises LivePriceChangedError / CartMembershipChangedError on drift
  on_commit → ORDER_PLACED SMS
```

## Flow 3a: Storefront payment — SIMULATION (legacy, gated)
```
checkout/order/<code>/start/  → (if no gateway config AND PAYMENTS_SIMULATION_ENABLED)
  → checkout/order/<code>/callback/<status>/  (status is client path segment; Http404 in prod)
  → payment_service.simulate_payment
     @atomic (NO Order lock); if already PAID → ValueError
     creates Transaction; sets Order.payment_status = PAID/FAILED (direct save)
     on success → change_order_status(PROCESSING)
     on_commit → PAYMENT_SUCCESS / PAYMENT_FAILED SMS
```

## Flow 3b: Storefront payment — REAL GATEWAY (Zibal/COD)
```
checkout/order/<code>/initiate/ → gateway_payment_service.initiate_payment
  creates PaymentAttempt; guards already-paid/config/idempotency
  adapter.create_payment (Zibal: POST /v1/request; COD: no external, attempt SUCCEEDED, order stays PENDING)
  → redirect to gateway (Zibal) or result page (COD)

gateway returns → checkout/gateway/callback/<attempt_id>/ → gateway_payment_service.process_callback_and_verify
  pre-check attempt outside atomic; if is_final → return (idempotent)
  if order already PAID → mark THIS attempt CANCELED
  adapter.verify_payment (server-to-server; browser return is NOT proof)
  on success: @atomic + select_for_update(attempt); if attempt.is_final → return
    attempt.status = SUCCEEDED
    conditional Order.objects.filter(pk, payment_status=PENDING).update(payment_status=PAID)
      if updated == 0 → already paid concurrently → return
    create legacy Transaction (dashboard back-compat)
    change_order_status(PROCESSING)
    on_commit → PAYMENT_SUCCESS SMS
```

## Flow 4: Manual refund / return
```
dashboard refund → refund_service.execute_order_refund
  @atomic; idempotent on key; GATEWAY method raises
  creates Refund(+RefundItem); optional restock; if fully refunded → Order.payment_status=REFUNDED

return complete → return_service.complete_return
  @atomic + select_for_update items; restock
  → refund_service.execute_order_refund(idempotency_key="return:<pk>")
```

## Failure / idempotency summary
- Order creation: idempotency_key unique + savepoint IntegrityError fallback.
- Gateway callback: `is_final` short-circuit + conditional PENDING-only update + already-paid → cancel-this-attempt.
- Refund/return: idempotency_key (returns use `return:<pk>`).
- Simulation: `already PAID → ValueError` (but no Order lock — L1).

See [TRANSACTIONS_AND_CONCURRENCY](TRANSACTIONS_AND_CONCURRENCY.md) and canonical
[`../../canonical/RUNTIME_FLOW_INDEX.md`](../../canonical/RUNTIME_FLOW_INDEX.md).
