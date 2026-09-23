# billing — Entry Points

```
domain_id: D8
code_baseline: 5883a140
```

## HTTP (`apps/billing/urls.py`, included at `billing/`)
| Path | View | Notes |
|---|---|---|
| `billing/webhook/<provider_code>/` | `views.billing_webhook` | **public, csrf-exempt, POST, always returns 200**; delegates ingest → process_webhook_event |

That is the only billing HTTP route. Merchant plan-purchase/checkout enters via the **portal**
(`portal.urls` billing routes) which calls billing services.

## Management commands
- `generate_subscription_renewals` → `renewal_service.generate_renewals`
- `process_subscription_dunning` → `dunning_service.process_dunning`
- `verify_billing_consistency` → `consistency_service` (read-only)

## Admin actions (`apps/billing/admin.py`)
- `SubscriptionInvoiceAdmin.action_mark_paid` → `confirmation_service.mark_invoice_paid_manually`
- `BillingWebhookEventAdmin.action_retry` → reset to received then reprocess
- Financially-locked fields are readonly; admin is superuser-only.

## Providers (`apps/billing/providers/`)
`get_provider` / `active_provider_code` / `webhook_secret`; `manual` (default), `zibal`.

## Signals / async
None. Cron via management commands; side effects synchronous within `@atomic`.
