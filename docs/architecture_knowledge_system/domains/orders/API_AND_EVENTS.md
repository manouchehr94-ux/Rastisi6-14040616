# orders — API & Events

```
domain_id: D6
code_baseline: 5883a140
```

## External API calls (outbound)
- **Zibal** (via `gateways/zibal.py`): `POST /v1/request` (create), `POST /v1/verify` (verify).
  Amounts in Rial (Toman ×10 inside adapter). Config from `PaymentGatewayConfig` (encrypted creds).
- **COD** (`gateways/cod.py`): no external call; offline.

## Inbound callbacks (public)
- `checkout/gateway/callback/<attempt_id>/` — gateway returns the customer; the view triggers
  `process_callback_and_verify` which does the authoritative server-to-server verify. Request body
  is not trusted.
- `checkout/order/<code>/callback/<status>/` — **simulation only**, Http404 in production.

## Events / side effects (no Django signals)
All side effects are explicit `transaction.on_commit` callbacks (fire only if the transaction
commits):
| Trigger | Event | Sender |
|---|---|---|
| `create_order_from_cart` success | `ORDER_PLACED` SMS | `sms.send_event_sms` |
| `change_order_status` (processing/shipped/delivered/canceled) | status SMS (`ORDER_PROCESSING/SHIPPED/DELIVERED/CANCELED`) | `sms.send_event_sms` |
| `simulate_payment` success/failure | `PAYMENT_SUCCESS` / `PAYMENT_FAILED` SMS | `sms.send_event_sms` (`payment_service.py:91-100`) |
| `process_callback_and_verify` success | `PAYMENT_SUCCESS` SMS | `sms.send_event_sms` (`gateway_payment_service.py:353-357`) |

There are **no** `@receiver`/signal handlers in this domain (or anywhere in the codebase).

## Internal service "API" (for other domains)
- `order_service.change_order_status(order, to_status, *, note, store, ...)` — the ONLY sanctioned
  way to change `Order.status` (used by dashboard).
- `refund_service.execute_order_refund(...)`, `return_service.*` — used by dashboard.
- `gateways.registry.get_adapter(code)` — the single adapter entry point.
