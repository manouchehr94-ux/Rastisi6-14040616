# billing — Mutation Authority

```
domain_id: D8
code_baseline: 5883a140
known_risks: M7
```

| Entity | Canonical writer(s) |
|---|---|
| `SubscriptionInvoice.status` | `invoice_service` (draft/open/void), `confirmation_service` (→paid), `dunning_service` (→past_due/uncollectible), `refund_service._sync_invoice_refund_status` (→refunded/partially), `payment_flow_service.start_payment` (→payment_pending). No single table; each guarded by `is_payable`/`is_financially_locked` |
| `SubscriptionPaymentAttempt` | `attempt_service` (create), `confirmation_service` (succeeded), `payment_flow_service` (pending/session) |
| `BillingWebhookEvent` | `webhook_service` |
| `SubscriptionDunningState` | `dunning_service` |
| `SubscriptionCreditNote` / `SubscriptionRefund` | `credit_note_service` / `refund_service` |
| `ScheduledPlanChange` | `plan_change_billing_service` (create/supersede), `renewal_service` (apply+delete) |

## Cross-domain writes performed BY billing (M7 — funneled)
billing drives the **subscription** state machine, but **only** through `subscription_service`
(never a direct `subscription.status =`):
- `confirmation_service._activate_or_renew` → activate / renew / change_plan_version.
- `dunning_service` → enter_grace / suspend.
- `cancellation_service` → cancel_immediately / cancel_at_period_end.
- `renewal_service` → change_plan_version (scheduled downgrade).

## No writes INTO billing from other domains
Admin actions (`action_mark_paid` → `mark_invoice_paid_manually` → confirmation_service;
`action_retry` → reprocess webhook) go through billing services. No direct external writers.

## Admin actions (VERIFIED)
`billing/admin.py`: `action_mark_paid`, `action_retry` (both funnel through services; financially-
locked fields are readonly).
