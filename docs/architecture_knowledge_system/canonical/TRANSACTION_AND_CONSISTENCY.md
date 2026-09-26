# Transaction & Consistency

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 10) / Phase 2 (doc 01)
open_decisions: DR-1
```

Atomicity, locking, idempotency, and concurrency behavior for important multi-model operations.
Authoritative detail: Phase 1
[`../phase1_code_discovery/10_TRANSACTION_AND_CONSISTENCY.md`](../phase1_code_discovery/10_TRANSACTION_AND_CONSISTENCY.md).

`@transaction.atomic` usage per app (VERIFIED, non-test): billing 13, catalog 19, stores 9,
storefront_builder 8, orders 6, subscriptions 5, portal 3, sms 3, cart 2, dashboard 2, core 1,
customers 1; blog/content/notifications 0.

---

## Strong boundaries (VERIFIED)
| Operation | Atomicity | Locking | Idempotency |
|---|---|---|---|
| `order_service.create_order_from_cart` | `@atomic` | select_for_update Product/Variant → Cart → CartItem (membership fence) | `idempotency_key` pre-check + DB-unique fallback in savepoint |
| `gateway_payment_service.process_callback_and_verify` | `@atomic` | select_for_update re-lock of attempt | `is_final` short-circuit; conditional PENDING→PAID update |
| `subscription_service._transition` (all) | `@atomic` | select_for_update subscription | no-op if same status + prior event key |
| billing `confirmation_service.confirm_payment` | `@atomic` | select_for_update attempt + invoice | already-succeeded/paid short-circuit; amount+currency validated vs invoice |
| billing `webhook_service.ingest_webhook` | `@atomic` | select_for_update | `(provider, external_event_id)` unique + IntegrityError fallback; signature verified before any business change |
| billing `renewal_service._generate_one` | `@atomic` | select_for_update subscription | `uniq_renewal_invoice_per_period` + IntegrityError fallback |
| billing numbering (`BillingSequence`) | `@atomic` | select_for_update | race-safe counter |
| `provisioning_service.provision_trial_store` | single `@atomic` across 4 apps | nested atomic retry for platform_code | view-level session idempotency token |
| `domain_verification_service.*` | `@atomic` | select_for_update StoreDomain | recency window |
| `cart_service` / `merge_guest_cart` | `@atomic` | membership-fence select_for_update | quantity merge |
| `catalog.inventory_service` | `@atomic` | — | StockMovement ledger + WarehouseInventory mirror |

## Weak / missing boundaries (VERIFIED / INFERRED) — feed DR-1
| Concern | Detail | Severity |
|---|---|---|
| `payment_service.simulate_payment` no Order lock | `@atomic` but no `select_for_update` on Order before the already-paid check | LOW (prod-gated) |
| `refund_service.execute_order_refund` no Order lock | reads refundable then writes without locking Order | MEDIUM |
| `Order.payment_status` no transition table | plain assignments across 3 writers; only gateway path lock+conditional | HIGH (H1/DR-1) |
| Two `Transaction` rows possible for one paid order | simulate + gateway back-compat both create | MEDIUM |
| `checkout_item_update/remove` mutate CartItem outside checkout fence | cross-domain direct write at cart stage | LOW-MEDIUM |
| `content.*` writes via dashboard views | no service/transaction boundary; multi-object footer/menu edits | MEDIUM (H2) |

## External calls relative to transactions (VERIFIED)
- Gateway `verify_payment` is server-to-server **before** the `@atomic` block that flips
  `payment_status` (correct — external I/O outside the DB transaction).
- DNS/TLS checks external; persistence inside `@atomic`.
- SMS deferred to `transaction.on_commit` (a rolled-back order never sends SMS).
- Billing webhook signature verified before any DB business change.

## Idempotency inventory (VERIFIED)
Order creation (`idempotency_key` from cart `checkout_token`); orders PaymentAttempt (partial
uniques on `idempotency_key`, `gateway_track_id`); orders Refund/ReturnRequest (partial unique
`idempotency_key`, returns use `return:<pk>`); billing attempt/webhook/invoice uniques;
subscriptions `SubscriptionEvent (subscription, idempotency_key)`; core ImportJob idempotency.

## SQLite vs PostgreSQL note (from PAYMENT_ARCHITECTURE, MATCHES code intent)
`select_for_update()` is a no-op on SQLite (whole-DB write lock); the application-level guards
(conditional updates, status checks, unique constraints) are the portable safety boundary.
PostgreSQL adds row-level locking as defense-in-depth.

## Consistency-verification tooling (VERIFIED)
Read-only checkers + commands exist: `verify_billing_consistency`, `verify_subscription_consistency`,
`verify_inventory_consistency`, `verify_domain_consistency`.
