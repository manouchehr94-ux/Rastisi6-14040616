# orders — Entry Points

```
domain_id: D6
code_baseline: 5883a140
source: apps/orders/urls.py, apps/orders/views.py
```

Routes are included at `checkout/` in `shop_core/urls.py` (`path("checkout/", include("apps.orders.urls"))`).

## HTTP routes (`apps/orders/urls.py`)
| Path (under `checkout/`) | View | Purpose |
|---|---|---|
| `""` | `checkout_step1` | checkout step 1 |
| `pay/` | `checkout_pay` | payment step |
| `pay/otp/{verify,resend,cancel}/` | `checkout_verify_otp` / `checkout_resend_otp` / `checkout_otp_cancel` | checkout OTP |
| `items/<id>/update/` , `items/<id>/remove/` | `checkout_item_update` / `checkout_item_remove` | **cross-domain cart mutation** (L2) |
| `shipping/<method_id>/` | `checkout_set_shipping` | select shipping |
| `payment/<gateway_id>/` | `checkout_set_payment` | select gateway |
| `coupon/apply/` , `coupon/remove/` | `checkout_apply_coupon` / `checkout_remove_coupon` | coupon |
| `order/<code>/start/` | `payment_start` | routes to real `payment-initiate` if a config exists, else simulation (gated) |
| `order/<code>/callback/<status>/` | `payment_callback` | **SIMULATION only**; `status` is a client-controlled path segment → **Http404 in production** |
| `order/<code>/result/` | `payment_result` | result page |
| `order/<code>/initiate/` | `payment_initiate` | real gateway initiation |
| `gateway/callback/<attempt_id>/` | `gateway_callback` | **public, server-to-server verify** → `process_callback_and_verify` |

## Admin entry points (from `dashboard`)
- Order detail / status change → `order_service.change_order_status`.
- Refund → `refund_service.execute_order_refund`. Returns → `return_service.*`.
- Shipping/tax/gateway-config settings → **direct writes** in `dashboard/views.py` (DR-3).

## Management commands
- `apps/orders/management/commands/seed_default_shipping_methods.py` (seed only).

## Signals / async
- **None.** Side effects fire via `transaction.on_commit` (SMS) — see [API_AND_EVENTS](API_AND_EVENTS.md).

## Security notes on entry points
- `gateway_callback` requires no auth (public gateway callback) but trusts **only** the
  server-to-server `verify_payment`, never the request body.
- `payment_callback` simulation is Http404 in production (`PAYMENTS_SIMULATION_ENABLED`); its
  `status` path segment is client-controlled and must never be reachable in a real deployment.
