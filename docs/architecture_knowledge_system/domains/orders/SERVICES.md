# orders — Services

```
domain_id: D6
code_baseline: 5883a140
source: apps/orders/services/ (9 files) + apps/orders/gateways/
```

| Service | Responsibility | Writes | Txn / lock | Side effects |
|---|---|---|---|---|
| **order_service.create_order_from_cart** | The ONLY production Order creator | Order, OrderItem, OrderStatusHistory(initial), Coupon.used_count, CartItem.unit_price | `@atomic`; select_for_update Product/Variant→Cart→CartItem | reserve+consume inventory; ORDER_PLACED SMS on_commit |
| **order_service.change_order_status** | CANONICAL Order.status transition | Order.status/tracking, OrderStatusHistory; restock on CANCELED | `@atomic`; guards `ALLOWED_TRANSITIONS`+`FINAL_STATUSES` | status SMS on_commit |
| **payment_service.simulate_payment** *(LEGACY)* | Simulated payment (no bank) | Transaction; **Order.payment_status** (direct); → change_order_status(PROCESSING) | `@atomic` (no Order lock) | PAYMENT_SUCCESS/FAILED SMS on_commit; gated by `PAYMENTS_SIMULATION_ENABLED` |
| **gateway_payment_service.initiate_payment** *(NEW)* | Start real payment | PaymentAttempt | `@atomic` | `adapter.create_payment` (external); COD → attempt SUCCEEDED but order stays PENDING |
| **gateway_payment_service.process_callback_and_verify** *(NEW)* | Authoritative confirmation | conditional Order.payment_status PENDING→PAID; PaymentAttempt.status; legacy Transaction | `@atomic` + select_for_update re-lock; idempotent on `is_final` | `adapter.verify_payment` (server-to-server); PAYMENT_SUCCESS SMS |
| **refund_service.plan_order_refund** | Pure calc from Order snapshot | — | — | — |
| **refund_service.execute_order_refund** | Manual refund | Refund(+Item); Order.payment_status→REFUNDED; optional restock | `@atomic`; idempotent on key | GATEWAY method raises |
| **refund_service.record_refund_result** | Guarded final states | Refund.status | — | — |
| **return_service.\*** | Return lifecycle (create/review/approve/reject/mark_received/inspect/complete) | ReturnRequest(+Item) guarded transitions (`ReturnRequest.ALLOWED_TRANSITIONS`) | `@atomic` + select_for_update items | complete → `refund_service.execute_order_refund(key="return:<pk>")` + restock |
| **checkout_service.finalize_order** | Post-order cart teardown | `cart.items.all().delete()` (cross-domain) | within order flow | — |
| **shipping_service / tax_service / best_seller_service** | Quote/calc/report helpers | (read-mostly) | — | — |

## Gateway adapters (`apps/orders/gateways/`)
- **base.py** — abstract `PaymentGatewayAdapter` (`create_payment`, `build_redirect_url`,
  `verify_payment`; result dataclasses; `GatewayError` hierarchy). **Adapters must NOT touch
  Order/PaymentAttempt state** — that is the service's job.
- **registry.py** — `get_adapter(code)` (lazy loaders `_load_zibal`/`_load_cod`, cached);
  `GATEWAY_CHOICES`. "All checkout/payment/admin code goes through `get_adapter(code)`."
- **zibal.py** — online redirect (`/v1/request` + `/v1/verify`, Toman→Rial ×10 inside adapter).
- **cod.py** — offline; attempt SUCCEEDED immediately, order stays PENDING.

## Adding a gateway (from PAYMENT_ARCHITECTURE §10, matches code)
1. `apps/orders/gateways/new_gateway.py` implementing `PaymentGatewayAdapter`.
2. loader in `registry.py`. 3. `GatewayCode` choice on `PaymentGatewayConfig`. 4. migration.
5. no other changes (checkout/admin/callback dispatch automatically). See [CHANGE_GUIDE](CHANGE_GUIDE.md).
