# orders — Transactions & Concurrency

```
domain_id: D6
code_baseline: 5883a140
open_decisions: DR-1
```

## Strong (VERIFIED)
| Operation | Atomicity | Locking | Idempotency |
|---|---|---|---|
| `create_order_from_cart` | `@atomic` | select_for_update Product/Variant → Cart → CartItem (membership fence) | idempotency_key pre-check + DB-unique fallback in savepoint |
| `process_callback_and_verify` (success) | `@atomic` | select_for_update re-lock of attempt | `is_final` short-circuit; conditional PENDING→PAID update (`updated==0` guard) |
| `return_service._transition` | `@atomic` | select_for_update items | model `ALLOWED_TRANSITIONS` |
| `execute_order_refund` | `@atomic` | — | idempotent on key |

## Weak / missing (VERIFIED / INFERRED) — feed DR-1
| Concern | Detail | Severity |
|---|---|---|
| `simulate_payment` no Order lock | `@atomic` but no `select_for_update` on Order before the already-paid check → theoretical double-processing under simulation | LOW (prod-gated) |
| `refund_service.execute_order_refund` no Order lock | reads refundable then writes without locking Order | MEDIUM |
| `Order.payment_status` no transition table | plain assignments across 3 writers; only gateway path lock+conditional | HIGH (H1/DR-1) |
| Two `Transaction` rows possible | simulate + gateway back-compat both create | MEDIUM |
| `checkout_item_update/remove` mutate CartItem outside the checkout fence | cross-domain direct write at cart stage | LOW-MEDIUM (L2) |

## External calls vs transactions (VERIFIED)
`adapter.verify_payment` (Zibal) is a server-to-server call performed **before** the `@atomic`
block that flips `payment_status` — external I/O is kept outside the DB transaction; the
transaction only does the conditional local update + Transaction create + status transition.

## SQLite vs PostgreSQL (from PAYMENT_ARCHITECTURE §8, matches code)
`select_for_update()` is a no-op on SQLite (whole-DB write lock). The **application-level** guards
(conditional `.update(...WHERE payment_status=PENDING)`, `is_final` checks, unique constraints) are
the portable safety boundary that works on both backends. Do not rely on row locks alone.

## Idempotency keys in this domain
- Order: `idempotency_key` (from cart `checkout_token`).
- PaymentAttempt: `idempotency_key`, `gateway_track_id` (partial unique).
- Refund / ReturnRequest: `idempotency_key` (returns use `return:<pk>`).
