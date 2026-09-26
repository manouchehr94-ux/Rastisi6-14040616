# orders — Historical Context

```
domain_id: D6
code_baseline: 5883a140
```

Historical/design-intent documents that explain *why* orders/payments looks the way it does.
These are **evidence/history, not current runtime truth** (see
[`../../canonical/DOCUMENTATION_AUTHORITY.md`](../../canonical/DOCUMENTATION_AUTHORITY.md)). They are
**not** modified, moved, or archived here — only labelled from the canonical system.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `docs/docs/product/architecture/PAYMENT_ARCHITECTURE.md` | L3 design intent (CURRENT_CANDIDATE) | Mostly MATCHES_CODE (gateway flow §5, concurrency §8, COD §6, "no auto refunds" §11). **STALE on one point:** §4 "State Ownership" lists only the gateway writer of `Order.payment_status` and omits `simulate_payment` + `refund_service` and the REFUNDED state (Phase 4 S1). | ACCURATE-EXCEPT-§4 |
| `SAAS_DOMAIN_DECISIONS.md` ADR-7/9/14/33/34/35 | L3 ADR | MATCHES_CODE — payment provider vs config separation, funds flow, `Order.store` FK, MANUAL-only refund, ReturnRequest own machine, order financial state in dedicated fields | AUTHORITATIVE-INTENT |
| `docs/reports/PRELAUNCH_PHASE4_ZIBAL_MERCHANT_PAYMENTS.md` | L4 report | HISTORICAL — prelaunch merchant-payments report | HISTORICAL |
| `SAAS_MIGRATION_PLAN.md` (PR7 order/payment separation; PR12 legacy removal) | L3 plan | PR7 realized; **PR12 legacy-path removal NOT done** (simulation + legacy Transaction still present) — DI-2/DR-6 | PARTIALLY-REALIZED |

## Key historical points
- **Simulation predates the real gateway.** `PAYMENT_ARCHITECTURE.md` explicitly kept
  `payment_service` (simulation) "gated, unchanged" while adding `gateway_payment_service`. This is
  why two implementations coexist (H1) and why the legacy `Transaction` is still written for
  dashboard back-compat.
- **Two money systems by design (ADR-73).** SaaS/platform billing was deliberately separated into
  `billing`; do not merge order payments with subscription billing.
- **Refund scope was deliberately limited (ADR-33).** GATEWAY refunds were explicitly out of scope;
  the code raising for `method=GATEWAY` is intentional, not a bug.

## Where the doc disagrees with code (do not "fix" the doc here)
`PAYMENT_ARCHITECTURE.md §4` is STALE about `payment_status` writers. The canonical truth is
[`MUTATION_AUTHORITY.md`](MUTATION_AUTHORITY.md) (3 writers). The doc is not edited in this phase;
a future canonical-rewrite phase should complete §4.
