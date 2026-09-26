# billing — State Machines

```
domain_id: D8
code_baseline: 5883a140
```

## SubscriptionInvoice.status — guarded per-service (no single table)
```
draft → open → payment_pending → paid
             ↘ past_due → uncollectible
             ↘ void
paid → refunded / partially_refunded
```
Guarded by `is_payable` / `is_financially_locked` (`PAYABLE_STATUSES`, `FINANCIALLY_LOCKED_STATUSES`
frozensets) checked in each service before writing. Writers: invoice_service, confirmation_service,
dunning_service, refund_service, payment_flow_service (see MUTATION_AUTHORITY).

## SubscriptionPaymentAttempt.status — guarded by is_final + confirm idempotency
```
created → pending → requires_action → {succeeded, failed, cancelled, expired}
```

## BillingWebhookEvent.processing_status
```
received → {processed, failed, ignored}
```
Dedup via `uniq(provider, external_event_id)`.

## SubscriptionDunningState.status
```
active → {resolved, exhausted}   (stage / attempt_count / next_retry_at)
```

## SubscriptionCreditNote.status / SubscriptionRefund.status
```
CreditNote: draft → issued → void
Refund:     requested → pending → {succeeded, failed, cancelled}
```

## Cross-domain effect
Invoice/dunning transitions **drive** subscription transitions (via `subscription_service`):
paid → activate/renew; dunning stage 0 → enter_grace; final stage → suspend. See the
`subscriptions` pack for the StoreSubscription machine.
