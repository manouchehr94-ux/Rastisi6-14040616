# orders — Mutation Authority

```
domain_id: D6
code_baseline: 5883a140
open_decisions: DR-1, DR-5, DR-6
```

Classification: CANONICAL / SECONDARY / DIRECT / CROSS-DOMAIN (see canonical
[`../../canonical/MUTATION_AUTHORITY.md`](../../canonical/MUTATION_AUTHORITY.md)).

---

## ⚠️ `Order.payment_status` — 3 writers, NO transition guard (H1 / DR-1)
| Writer | Class | File:line | Guard |
|---|---|---|---|
| `gateway_payment_service.process_callback_and_verify` | CANONICAL (intended) | `gateway_payment_service.py:313-316` | `select_for_update` re-lock of attempt + conditional `Order.objects.filter(pk=…, payment_status=PENDING).update(payment_status=PAID)` |
| `payment_service.simulate_payment` | SECONDARY | `payment_service.py:86-98` | none (plain `save`); no Order lock; prod-gated by `PAYMENTS_SIMULATION_ENABLED` |
| `refund_service.execute_order_refund` | SECONDARY | `refund_service.py:234` | none (plain `save` → REFUNDED); idempotent on refund key |

**There is no `ALLOWED_TRANSITIONS` for `payment_status`.** Any code that changes payment state
must update ALL THREE writers and cannot rely on a central guard. This is DR-1.

## `Order.status` — single guarded writer (LOW risk)
| Writer | Class | Evidence |
|---|---|---|
| `order_service.change_order_status` | CANONICAL | `order_service.py:45` `ALLOWED_TRANSITIONS`, enforced `:550`; writes status + `OrderStatusHistory` |

Callers (all funnel here): `payment_service.simulate_payment` (→PROCESSING),
`gateway_payment_service.process_callback_and_verify` (→PROCESSING), `dashboard.views.order_detail`.
Initial status set by `create_order_from_cart` (also via service). On CANCELED → restock.

## `Transaction` (legacy) — two create paths (M4/H1)
- `payment_service.simulate_payment` (creates on pay).
- `gateway_payment_service.process_callback_and_verify` (creates "for dashboard back-compat").
→ a gateway-paid order has both a `PaymentAttempt` and a `Transaction`.

## `PaymentAttempt` — CANONICAL: `gateway_payment_service` (initiate/process). LOW.

## `Refund` / `ReturnRequest` — CANONICAL: `refund_service` / `return_service` (guarded finals).

## Config models (Shipping*/Tax*/PaymentGatewayConfig) — CROSS-DOMAIN / DIRECT (DR-3)
Written directly by `dashboard.views.settings_*` (incl. credential encryption via
`config.set_credentials`) and toggled by `dashboard.settings_admin_service`. No orders service
mediates these writes.

## Cross-domain writes performed BY orders (M9)
| Target | Writer | Mechanism |
|---|---|---|
| `cart.CartItem.unit_price` | `order_service.create_order_from_cart` (`_lock_cart_items_and_resolve_final_prices`) | reprice |
| `cart` items (delete) | `checkout_service.finalize_order`; `views.checkout_item_update/remove` | `.delete()` |
| `cart.Coupon.used_count` | `order_service.create_order_from_cart` | `+=1` |
| `catalog` inventory (+StockMovement) | `order_service.create_order_from_cart` | reserve + consume via catalog reservation/inventory service |

## Summary
| Entity | Writers | Guarded? | Severity | DR |
|---|---|---|---|---|
| Order.payment_status | 3 | NO table | HIGH | DR-1 |
| Transaction (legacy) | 2 create | n/a | MEDIUM | DR-6 |
| gateway model (dual) | — | — | MEDIUM | DR-5 |
| Order.status | 1 (funneled) | yes | LOW | — |
| PaymentAttempt / Refund / ReturnRequest | 1 each | yes | LOW | — |
| Shipping/Tax/GatewayConfig | dashboard direct | model validation | MEDIUM | DR-3 |
