# Domain: orders (D6) — Orders, Checkout & Storefront Payments ★ GOLD-STANDARD PACK

```
domain_id: D6
app: apps/orders
canonical_pack_status: CANONICAL
phase4_prepack_documentation_readiness: PARTIAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2 / Phase 4
open_decisions: DR-1, DR-5, DR-6
known_risks: H1, M4, M9, L1, L2, L4
```

> This is the **gold-standard reference** Domain Knowledge Pack. It is the highest-risk domain
> (storefront money). **The single most important fact: `Order.payment_status` has THREE writers
> and NO transition guard** (finding H1 / decision DR-1). Read [`MUTATION_AUTHORITY.md`](MUTATION_AUTHORITY.md)
> and [`CHANGE_GUIDE.md`](CHANGE_GUIDE.md) before changing anything payment-related.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [ARCHITECTURE](ARCHITECTURE.md) · [DATA_MODEL](DATA_MODEL.md) ·
[SERVICES](SERVICES.md) · [ENTRY_POINTS](ENTRY_POINTS.md) · [API_AND_EVENTS](API_AND_EVENTS.md) ·
[FLOWS](FLOWS.md) · [STATE_MACHINES](STATE_MACHINES.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [INVARIANTS](INVARIANTS.md) ·
[TRANSACTIONS_AND_CONCURRENCY](TRANSACTIONS_AND_CONCURRENCY.md) · [SECURITY](SECURITY.md) ·
[TESTING](TESTING.md) · [**CHANGE_GUIDE**](CHANGE_GUIDE.md) · [TROUBLESHOOTING](TROUBLESHOOTING.md) ·
[CODE_MAP](CODE_MAP.md) · [HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

## The 18 domain questions (answered here + linked)
1. **What does it own?** Order lifecycle, storefront payment (two implementations), refunds/returns,
   shipping/tax config, gateway config + adapters. See [BOUNDARIES](BOUNDARIES.md).
2. **What does it NOT own?** SaaS/platform billing (that is `billing`); the cart itself (`cart`);
   inventory truth (`catalog`); customer identity (`customers`). See [BOUNDARIES](BOUNDARIES.md).
3. **Which models?** `Order`, `OrderItem`, `OrderStatusHistory`, `Transaction` (legacy),
   `PaymentAttempt` (new), `PaymentGatewayConfig` + `PaymentGateway` (dual — M4), `Refund`(+Item),
   `ReturnRequest`(+Item), `ShippingZone/Method/RateRule`, `TaxClass/TaxRate`. See [DATA_MODEL](DATA_MODEL.md).
4. **Which services are canonical?** `order_service` (order lifecycle), `gateway_payment_service`
   (real payment), `refund_service`, `return_service`. See [SERVICES](SERVICES.md).
5. **Which non-domain code writes its models?** `dashboard` (order status via `change_order_status`;
   shipping/tax/gateway-config **directly**). See [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md).
6. **Who calls it?** `dashboard` (admin), checkout views, gateway callback, cron (none for orders).
7. **What does it call?** `cart` (reprice/delete — cross-domain), `catalog` (reserve/consume stock),
   `sms` (on_commit), payment gateways (Zibal/COD). See [DEPENDENCIES](DEPENDENCIES.md).
8. **Runtime entry points?** `apps/orders/urls.py` (checkout + payment routes), gateway callback,
   simulation callback (gated). See [ENTRY_POINTS](ENTRY_POINTS.md).
9. **State machines?** `Order.status` (GUARDED), **`Order.payment_status` (NOT guarded)**,
   `PaymentAttempt.status`, `Refund.status`, `ReturnRequest.status` (model-level table). See
   [STATE_MACHINES](STATE_MACHINES.md).
10. **Invariants?** See [INVARIANTS](INVARIANTS.md).
11. **Transaction/concurrency guarantees?** See [TRANSACTIONS_AND_CONCURRENCY](TRANSACTIONS_AND_CONCURRENCY.md).
12. **External services?** Zibal, COD. See [API_AND_EVENTS](API_AND_EVENTS.md).
13. **Trust/security boundaries?** Browser return is never proof; server-side verify only. See
    [SECURITY](SECURITY.md).
14. **Tests per behavior?** See [TESTING](TESTING.md).
15. **Known smells?** H1, M4, M9, L1, L2, L4. See [OPEN_DECISIONS](OPEN_DECISIONS.md) + canonical KNOWN_ARCHITECTURE_RISKS.
16. **Open DR decisions?** DR-1, DR-5, DR-6. See [OPEN_DECISIONS](OPEN_DECISIONS.md).
17. **Historical docs?** `PAYMENT_ARCHITECTURE.md` (mostly matches; STALE on payment_status writers).
    See [HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md).
18. **Read before changing?** [CHANGE_GUIDE](CHANGE_GUIDE.md).

## One-paragraph orientation
`orders` owns the storefront money path. An order is created from a cart by
`order_service.create_order_from_cart` (atomic, locked, idempotent via the cart `checkout_token`).
Payment has **two coexisting implementations**: a legacy **simulation** (`payment_service`,
production-gated) and a real **gateway** path (`gateway_payment_service` + `gateways/` adapters for
Zibal and COD). Both write `Order.payment_status`; so does `refund_service`. `Order.status`
transitions only through `order_service.change_order_status` (guarded). Refunds are MANUAL-only;
returns have their own model-level state machine. SMS side effects fire on `transaction.on_commit`.
