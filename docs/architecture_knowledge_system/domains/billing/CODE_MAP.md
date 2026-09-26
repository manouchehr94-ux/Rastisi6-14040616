# billing — Code Map

```
domain_id: D8
code_baseline: 5883a140
```

```
apps/billing/
├── models.py             10 models (StoreBillingAccount, SubscriptionInvoice(+Line),
│                         SubscriptionPaymentAttempt, BillingWebhookEvent, SubscriptionDunningState,
│                         SubscriptionCreditNote, SubscriptionRefund, ScheduledPlanChange, BillingSequence)
├── views.py              billing_webhook (public, csrf-exempt)
├── urls.py               webhook/<provider_code>/
├── admin.py              action_mark_paid, action_retry (superuser; locked fields readonly)
├── providers/            base, registry, manual (default), zibal
├── services/             15 files: invoice, attempt, confirmation, payment_flow, webhook, renewal,
│                         dunning, cancellation, refund, credit_note, numbering, account,
│                         period_utils, consistency, plan_change_billing
├── management/commands/  generate_subscription_renewals, process_subscription_dunning,
│                         verify_billing_consistency
├── migrations/
└── tests/                12 files (confirmation_activation, webhook_inbox, renewals,
                          dunning_cancellation, credit_refund, plan_change_billing,
                          provider_and_attempts, zibal_platform_provider, invoice_lines_numbering,
                          consistency_isolation, account_and_invoice, billing_admin)
```

## Where to look
| Concern | File |
|---|---|
| "Payment happened" | `services/confirmation_service.py` |
| Webhook inbox | `services/webhook_service.py` |
| Renewals / dunning | `services/renewal_service.py` / `services/dunning_service.py` |
| Invoice numbering | `services/numbering_service.py` + `BillingSequence` |
| Merchant plan change | `services/plan_change_billing_service.py` |
| Provider integration | `providers/` |
