# billing — Services

```
domain_id: D8
code_baseline: 5883a140
source: apps/billing/services/ (15 files) + apps/billing/providers/
```

All mutation services use `@transaction.atomic` + `select_for_update` on the mutated aggregate.

| Service | Responsibility | Cross-domain |
|---|---|---|
| **invoice_service** (`create/open/void/add_line`) | invoice lifecycle | — |
| **attempt_service.create_attempt** | billing payment attempt (idempotent; amount/currency from invoice, not browser) | — |
| **confirmation_service.confirm_payment** | THE "payment happened" path: mark attempt SUCCEEDED, add amount_paid, recompute, set PAID; then `_activate_or_renew` | **drives `subscription_service`** activate/renew/change_plan_version |
| **payment_flow_service** (`start_payment/confirm_from_provider_verification/process_webhook_event`) | provider session + verification pull + webhook processing | → confirmation_service |
| **webhook_service.ingest_webhook** | verified idempotent inbox (size check; signature BEFORE any business change; dedup via unique + select_for_update + IntegrityError fallback; redacts payload) | — |
| **renewal_service** (`generate_renewals/_generate_one`) | pre-due renewal invoices; applies+deletes ScheduledPlanChange | → subscription_service.change_plan_version |
| **dunning_service** (`process_dunning/_process_invoice`) | retry/escalation: stage 0 → invoice past_due + subscription enter_grace; final → subscription suspend + invoice uncollectible | → subscription_service |
| **cancellation_service.cancel_subscription_billing** | cancel + void unpaid invoices | → subscription_service cancel_* |
| **refund_service** (`request_refund/complete_refund_manually`) | billing refund; `_sync_invoice_refund_status` | provider.refund_payment (external) |
| **credit_note_service** (`issue/void`) | numbered credit notes | — |
| **plan_change_billing_service.start_plan_change** | canonical merchant plan-change entry: upgrade→PLAN_CHANGE invoice; downgrade/equal→ScheduledPlanChange | — |
| **numbering_service** | invoice/credit numbering via `BillingSequence` (race-safe) | — |
| **account_service / period_utils / consistency_service** | account snapshot / period math / read-only consistency checks | — |

## Providers (`apps/billing/providers/`)
`registry.get_provider`/`active_provider_code`/`webhook_secret`; `manual` (default, no auto-capture),
`zibal`. Selected by `RASTISI_BILLING_PROVIDER`.

## Key discipline (ADR-76/77 — VERIFIED)
- Webhooks are verified + deduped **before** any business mutation.
- `confirm_payment` is one transactional idempotent service, **never in a view**.
- amount + currency validated against the invoice, never the browser.
