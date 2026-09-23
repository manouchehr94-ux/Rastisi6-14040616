# orders — Data Model

```
domain_id: D6
code_baseline: 5883a140
source: apps/orders/models.py (16 model classes); line ranges approximate past ~640
```

| Model | Key fields / lifecycle | Constraints | Notes |
|---|---|---|---|
| **Order** | `status` (pending/processing/shipped/delivered/canceled — **guarded**); **`payment_status`** (pending/paid/failed/refunded — **NOT guarded**, H1); money snapshots; FKs store/customer/vendor/shipping_method/payment_gateway/coupon | `code` unique; partial `uniq_order_idempotency_key_when_set` | `clean()` enforces `vendor.store == order.store` |
| **OrderItem** | product/sku/variant + price/tax snapshots; `fulfillment_warehouse` | — | immutable line snapshot |
| **OrderStatusHistory** | from/to status, changed_by, note | — | order audit trail (written by `change_order_status`) |
| **Transaction** *(LEGACY payment)* | `status` (ok/pending/fail/refund), amount, ref_id | `code` unique | created by BOTH simulate + gateway back-compat (M4/H1) |
| **PaymentAttempt** *(NEW payment)* | `status` (created/requesting/redirect_ready/pending/succeeded/failed/canceled/expired; FINAL={last 4}); immutable snapshots (public_id, amount, currency) | partial uniques on `idempotency_key`, `gateway_track_id` | `is_final`/`is_successful` props |
| **PaymentGatewayConfig** *(NEW)* | `gateway_code` (zibal/cod), `is_active`, `encrypted_credentials` | `uniq(store, gateway_code)` | per-store operational config; Fernet-encrypted creds |
| **PaymentGateway** *(LEGACY)* | order-chosen gateway slug | — | dual with PaymentGatewayConfig (M4/DR-5) |
| **Refund** (+**RefundItem**) | `status` (pending/approved/processing/succeeded/failed/cancelled); `method` (manual/gateway) | non-negative CheckConstraints; partial unique `idempotency_key` | **MANUAL only** (GATEWAY raises — ADR-33) |
| **ReturnRequest** (+**ReturnItem**) | full `status` machine | model-level `ALLOWED_TRANSITIONS` (`models.py:1047`) | requested/under_review/approved/rejected/in_transit/received/inspected/completed/cancelled |
| **ShippingZone / ShippingMethod / ShippingRateRule** | store-scoped shipping config | — | written directly by dashboard (DR-3) |
| **TaxClass / TaxRate** | store-scoped tax config | — | written directly by dashboard (DR-3) |

## Currency (from PAYMENT_ARCHITECTURE, matches code)
DB (Order, PaymentAttempt) stores **Toman** (Decimal 0 places). Zibal API uses **Rial**; the
Toman→Rial ×10 conversion happens **only inside the Zibal adapter**. PaymentAttempt snapshots both
`amount` and `currency` at creation.

## The three `Order.payment_status` writers (H1 — memorize)
| Writer | File:line | Mechanism |
|---|---|---|
| `gateway_payment_service.process_callback_and_verify` | `gateway_payment_service.py:313-316` | conditional `.filter(...PENDING).update(PAID)` under lock |
| `payment_service.simulate_payment` | `payment_service.py:86-98` | direct `order.save(...)` PAID/FAILED (no Order lock) |
| `refund_service.execute_order_refund` | `refund_service.py:234` | direct `order.save(...)` → REFUNDED |

No `ALLOWED_TRANSITIONS` table exists for `payment_status`. See [STATE_MACHINES](STATE_MACHINES.md).
