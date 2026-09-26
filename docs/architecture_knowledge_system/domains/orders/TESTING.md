# orders — Testing

```
domain_id: D6
code_baseline: 5883a140
source: apps/orders/tests/
```

| Behavior | Test file | Notable cases (from Phase 1) |
|---|---|---|
| Order creation, state machine, restock-on-cancel, coupon | `test_order_service.py` | snapshot, coupon used_count, restock, full transition path, invalid/skip/same transition, SMS on_commit |
| Checkout valuation / price-change review | `test_checkout_*.py`, `test_cat002_checkout_valuation.py` | live-price-changed review |
| Legacy simulated payment | `test_payment_service.py` | success creates ok Transaction + advances order; failure keeps pending; cannot pay already-paid; SMS; detect_bank BIN |
| Real gateway payment + idempotent callback | `test_gateway_payment_service.py` | initiate zibal/cod; already-paid raises; wrong-store config; idempotency-key returns existing; successful callback marks paid; failed verification does not mark paid; duplicate callback idempotent; already-paid-by-another-attempt cancels this; store-own-credential |
| Refund (manual) + tax | `test_refund_service.py`, `test_refund_service_tax.py` | idempotency; GATEWAY raises; fully-refunded → REFUNDED |
| Returns lifecycle | `test_return_service.py` | guarded transitions; complete → restock + refund |

## Coverage gaps (INFERRED — carried from Phase 1; feed DR-1)
- **No single `Order.payment_status` transition-legality test** — because there is no transition
  table to test. The individual writers are tested, but the combined "payment_status only moves
  through legal states" invariant is not proven anywhere. This is the test-shaped shadow of H1/DR-1.
- Parallel "already paid" guards are tested per-path but not as one unified contract (L4).

## Running (informational; do not modify tests)
Orders tests live under `apps/orders/tests/`. Run with the project's Django test runner
(`--run`/single execution). See canonical [`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
