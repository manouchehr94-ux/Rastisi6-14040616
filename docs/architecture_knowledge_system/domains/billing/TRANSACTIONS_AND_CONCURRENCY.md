# billing — Transactions & Concurrency

```
domain_id: D8
code_baseline: 5883a140
```

Billing is one of the **strongest** domains for consistency discipline (VERIFIED).

| Operation | Atomicity | Locking | Idempotency |
|---|---|---|---|
| `confirmation_service.confirm_payment` | `@atomic` | select_for_update attempt + invoice | already-succeeded/paid short-circuit; amount+currency validated vs invoice |
| `webhook_service.ingest_webhook` | `@atomic` | select_for_update | `(provider, external_event_id)` unique + IntegrityError race fallback; signature verified BEFORE any business change |
| `renewal_service._generate_one` | `@atomic` | select_for_update subscription | `uniq_renewal_invoice_per_period` + IntegrityError fallback |
| `dunning_service._process_invoice` | `@atomic` | select_for_update invoice + dunning state + subscription | stage-guarded |
| `attempt_service.create_attempt` | `@atomic` | — | idempotent; amount/currency from invoice not browser |
| numbering (`BillingSequence`) | `@atomic` | select_for_update | race-safe counter |

## Canonical lock order
`renewal_service` / `plan_change_billing_service` use the documented order **Subscription →
ScheduledPlanChange** (repair for a prior lock-order issue).

## External calls vs transactions
Provider session/verify/refund calls occur within service flows; webhook signature verification
happens **before** any DB business change. Browser return is never proof.

## SQLite vs PostgreSQL
As elsewhere, `select_for_update` is a no-op on SQLite; the unique constraints + IntegrityError
fallbacks + status checks are the portable safety boundary.
