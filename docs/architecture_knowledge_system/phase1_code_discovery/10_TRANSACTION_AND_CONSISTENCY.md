# 10 — Transaction & Consistency Discovery

Atomicity, locking, idempotency, and concurrency behavior for important multi-model operations.
Evidence class legend as in doc 01. `transaction.atomic`/`@atomic` usage was counted per app
(VERIFIED via grep): billing 13 files, catalog 19, stores 9, storefront_builder 8, orders 6,
subscriptions 5, portal 3, sms 3, cart 2, dashboard 2, core 1, customers 1; blog/content/notifications 0.

---

## 1. Strong transaction/consistency boundaries (VERIFIED)

| Operation | Atomicity | Locking | Idempotency |
|---|---|---|---|
| `order_service.create_order_from_cart` | `@atomic` | select_for_update Product/Variant → Cart → CartItem (membership fence) | `idempotency_key` pre-check + DB-unique fallback in savepoint |
| `gateway_payment_service.process_callback_and_verify` | `@atomic` | select_for_update re-lock of Order | attempt `is_final` short-circuit; conditional update on PENDING only |
| `subscription_service._transition` (all transitions) | `@atomic` | select_for_update subscription | no-op if same status + prior event key |
| billing `confirmation_service.confirm_payment` | `@atomic` | select_for_update attempt + invoice | already-succeeded/paid short-circuit; amount+currency validated vs invoice |
| billing `webhook_service.ingest_webhook` | `@atomic` | select_for_update | `(provider, external_event_id)` unique + IntegrityError race fallback; signature verified BEFORE any business change |
| billing `renewal_service._generate_one` | `@atomic` | select_for_update subscription | `uniq_renewal_invoice_per_period` + IntegrityError fallback |
| billing `dunning_service._process_invoice` | `@atomic` | select_for_update invoice + dunning state + subscription | stage-guarded |
| billing numbering (`BillingSequence`) | `@atomic` | select_for_update | race-safe counter |
| `provisioning_service.provision_trial_store` | single `@atomic` across 4 apps | nested atomic retry for platform_code | view-level session idempotency token |
| `domain_verification_service.*` | `@atomic` | select_for_update StoreDomain | recency window for readiness |
| `cart_service.add_item_to_cart` / `merge_guest_cart` | `@atomic` | membership-fence select_for_update | quantity merge |
| `catalog.inventory_service` | `@atomic` | — | StockMovement ledger + WarehouseInventory mirror |

## 2. Weak or missing boundaries (VERIFIED / INFERRED)

| Concern | Detail | Class | Severity |
|---|---|---|---|
| `payment_service.simulate_payment` no Order lock | `@atomic` but **no `select_for_update` on Order** before the already-paid check → theoretical double-processing under simulation | VERIFIED | LOW (simulation is prod-disabled) |
| `refund_service.execute_order_refund` reads refundable then writes without locking Order | Order not `select_for_update`d in the refund path (only gateway path re-locks) | INFERRED | MEDIUM |
| `Order.payment_status` has no transition table | direct assignments across 3 writers; only gateway path is lock+conditional | VERIFIED | HIGH (see doc 06/09/13) |
| Two `Transaction` rows possible for one paid order | legacy simulate + gateway back-compat both create `Transaction` if both paths run | VERIFIED | MEDIUM |
| `orders.views.checkout_item_update/remove` mutate CartItem outside the checkout membership-fence txn | cross-domain direct write at cart stage | VERIFIED | LOW-MEDIUM |
| `content.*` writes via dashboard views | model `full_clean()`/`save()` in views; some multi-object footer/menu edits without an explicit service transaction wrapper | INFERRED | MEDIUM |

## 3. External calls relative to transactions (VERIFIED)
- **Payment gateway `verify_payment`** is a server-to-server call performed **before** the
  `@atomic` block that flips `Order.payment_status` in the gateway path (correct — external I/O
  outside the DB transaction; the transaction only does the conditional local update).
- **DNS/TLS checks** in domain verification are external network calls; state persistence is inside
  `@atomic`.
- **SMS sends** are deferred to `transaction.on_commit`, so a rolled-back order never sends SMS.
- **Billing provider session/refund** calls occur within service flows; webhook signature verify
  happens before any DB business change.

## 4. Idempotency inventory (VERIFIED)
- Order creation: `idempotency_key` (partial unique) from cart `checkout_token`.
- Orders PaymentAttempt: partial uniques on `idempotency_key`, `gateway_track_id`.
- Orders Refund/ReturnRequest: partial unique `idempotency_key` (returns use `return:<pk>`).
- Billing: attempt `idempotency_key` unique; webhook `(provider, external_event_id)` unique;
  invoice `uniq_renewal_invoice_per_period`; SubscriptionRefund `idempotency_key` unique.
- Subscriptions: `SubscriptionEvent (subscription, idempotency_key)` partial unique; transitions
  are idempotent no-ops when repeated.
- Core import: `ImportJob` idempotency unique per store.

## 5. Consistency-verification tooling (VERIFIED)
Read-only consistency checkers + management commands exist:
`billing.consistency_service` / `verify_billing_consistency`,
`subscriptions.check_subscription_consistency` / `verify_subscription_consistency`,
`catalog verify_inventory_consistency`, `stores verify_domain_consistency`. These indicate the
team treats cross-aggregate drift as a known risk and audits it out-of-band rather than only via
DB constraints.

## 6. Summary
Consistency discipline is **strong in the SaaS/billing/subscription and order-creation/gateway
paths** (locks + idempotency + webhook dedup + numbering races handled). It is **weaker in the
legacy order-payment/refund path** (no Order lock; no payment_status transition table) and in the
**content write path** (no service/transaction boundary; dashboard-view mutation). No boundaries
were modified — these are recorded for the future remediation phase only.
