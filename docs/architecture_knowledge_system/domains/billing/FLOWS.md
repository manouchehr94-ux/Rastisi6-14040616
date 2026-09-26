# billing — Flows

```
domain_id: D8
code_baseline: 5883a140
source: Phase 1 doc 08 (Flows 7, 8)
```

## Flow: invoice → payment → subscription activation (Phase 1 Flow 7)
```
plan purchase → plan_change_billing_service.start_plan_change → invoice_service.create/open
             → payment_flow_service.start_payment (provider session; invoice → payment_pending)
provider webhook → billing/webhook/<provider> → webhook_service.ingest_webhook
             (size check; signature verify BEFORE business change; dedup via unique+select_for_update)
             → payment_flow_service.process_webhook_event → confirmation_service.confirm_payment
             (@atomic; select_for_update attempt+invoice; idempotent; amount+currency vs invoice)
             → _activate_or_renew → subscription_service.activate / renew / change_plan_version
```
Principle: browser return is never proof; only signed webhook / server-side pull confirms.

## Flow: renewal + dunning (cron) (Phase 1 Flow 8)
```
generate_subscription_renewals → renewal_service.generate_renewals/_generate_one
   @atomic; select_for_update subscription; apply+delete ScheduledPlanChange via change_plan_version;
   create+open renewal invoice; idempotent via uniq_renewal_invoice_per_period + IntegrityError fallback
   (canonical lock order: Subscription → ScheduledPlanChange)

process_subscription_dunning → dunning_service.process_dunning/_process_invoice
   @atomic; select_for_update invoice+dunning state+subscription
   stage 0 → invoice past_due + subscription enter_grace
   final stage → subscription suspend + invoice uncollectible
```

## Idempotency
attempt `idempotency_key` unique; webhook `(provider, external_event_id)` unique; invoice
`uniq_renewal_invoice_per_period`; SubscriptionRefund `idempotency_key`; confirm short-circuits
already-succeeded/paid.
