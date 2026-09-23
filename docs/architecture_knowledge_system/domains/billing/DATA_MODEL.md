# billing — Data Model

```
domain_id: D8
code_baseline: 5883a140
source: apps/billing/models.py (10 models)
```

| Model | Key fields / lifecycle | Constraints |
|---|---|---|
| **StoreBillingAccount** | OneToOne Store; `snapshot()` for invoice embedding | — |
| **SubscriptionInvoice** | `status` (draft/open/payment_pending/paid/past_due/void/uncollectible/refunded/partially_refunded); `kind` (initial/renewal/plan_change/manual); `FINANCIALLY_LOCKED_STATUSES`, `PAYABLE_STATUSES` frozensets; immutable account snapshot | `number` unique (numbering_service); partial `uniq_renewal_invoice_per_period` (subscription, billing_period_start) where kind=renewal; amount checks (`amount_paid ≤ grand_total`) |
| **SubscriptionInvoiceLine** | `line_type` (plan/proration_*/discount/tax/manual_adjustment) | — |
| **SubscriptionPaymentAttempt** | `status` (created/pending/requires_action/succeeded/failed/cancelled/expired; FINAL set) | `public_token` unique; `idempotency_key` unique; partial `(provider, provider_payment_id)` |
| **BillingWebhookEvent** | `processing_status` (received/processed/failed/ignored); redacted payload | `uniq(provider, external_event_id)` (dedup) |
| **SubscriptionDunningState** | `status` (active/resolved/exhausted); stage/attempt_count/next_retry_at | OneToOne invoice |
| **SubscriptionCreditNote** | `status` (draft/issued/void) | amount>0 check; `number` unique |
| **SubscriptionRefund** | `status` (requested/pending/succeeded/failed/cancelled); OPEN_STATUSES | `idempotency_key` unique; partial provider_refund_id; amount>0 check. **Never uses order Refund models** |
| **ScheduledPlanChange** | next-period downgrade | OneToOne subscription |
| **BillingSequence** | race-safe counter | select_for_update |

## Separation from orders (ADR-73)
billing has its **own** payment-attempt (`SubscriptionPaymentAttempt`) and refund
(`SubscriptionRefund`) models. Do not use `orders.PaymentAttempt`/`orders.Refund` for SaaS billing.
