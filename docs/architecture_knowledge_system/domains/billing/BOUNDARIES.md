# billing — Boundaries

```
domain_id: D8
code_baseline: 5883a140
```

## Owns
SaaS invoicing (`SubscriptionInvoice`+Line), billing payment attempts + confirmation
(`SubscriptionPaymentAttempt`), the webhook inbox (`BillingWebhookEvent`), dunning
(`SubscriptionDunningState`), credit notes/refunds, scheduled plan changes, billing numbering
(`BillingSequence`), and the billing account snapshot (`StoreBillingAccount`). Owns the billing
**providers** (`manual`, `zibal`).

## Does NOT own
- **Subscription lifecycle** — `subscriptions.StoreSubscription` + its state machine. billing
  **drives** it via `subscription_service` but never writes `subscription.status` directly (M7).
- **Storefront / order payments** — `orders` (two separate money systems; ADR-73). Do not reuse
  `orders.PaymentAttempt`/`orders.Refund` here.
- **Entitlements** — `subscriptions.entitlement_service`.

## Cross-domain relationships
- **Out:** drives `subscriptions` transitions (funneled); calls billing providers (external).
- **In:** webhook endpoint (public); cron commands (renewals/dunning); admin actions; portal checkout.

## Two money systems (ADR-73)
`billing` = platform money (merchant pays RastiSi). `orders` = storefront money (customer buys
products). Separate models, providers, refunds. Never conflate.
