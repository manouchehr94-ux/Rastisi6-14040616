# orders — Architecture

```
domain_id: D6
code_baseline: 5883a140
```

## Shape
`orders` is a service-layered Django app. Views (`views.py`) are thin controllers over services
(`services/`); payment gateways are stateless adapters (`gateways/`) behind a registry. The domain
owns the storefront money path end-to-end except inventory truth (catalog) and the cart (cart).

```
checkout views ──► order_service ──► Order / OrderItem / OrderStatusHistory
      │                 │            └► catalog inventory (reserve/consume) + StockMovement
      │                 └► cart (reprice/delete/coupon)  [cross-domain]
      ▼
payment_start ──► (config?) ──► gateway_payment_service ──► gateways/ (zibal|cod) ──► [Zibal API]
      └► (else, gated) ─► payment_service.simulate_payment  [LEGACY]
                 │
                 ▼
        Order.payment_status  ◄── ALSO refund_service   (3 writers, no guard — H1)
```

## Two payment implementations (CURRENT CODE REALITY)
- **Real gateway (canonical for production):** `PaymentAttempt` + `gateway_payment_service` +
  `gateways/`. Lock + conditional update + idempotency. Verified server-to-server.
- **Simulation (legacy, production-gated):** `Transaction` + `payment_service.simulate_payment`.
  Reachable only when `PAYMENTS_SIMULATION_ENABLED` (defaults to DEBUG).
- Both write `Order.payment_status`; the gateway path also creates a legacy `Transaction` for
  dashboard back-compat, so a gateway-paid order has both records (M4/H1/DR-6).

## Layering discipline
- **Order lifecycle** is service-mediated and guarded (`order_service.change_order_status`).
- **Shipping/tax/gateway config** is written **directly by dashboard views** (not an orders
  service) — a discipline gap (M5/DR-3).
- **Inventory** is never written here directly; always via `catalog.inventory_service`.

## Why it looks this way (design intent — see HISTORICAL_CONTEXT)
`PAYMENT_ARCHITECTURE.md` (PR1 foundation) intentionally co-located payment with orders (same
lifecycle + tenant boundary) and kept the simulation path "gated, unchanged" while adding the real
gateway path. The SaaS/platform billing money system is a deliberately separate domain (`billing`,
ADR-73).
