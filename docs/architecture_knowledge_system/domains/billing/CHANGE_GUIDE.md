# billing — Change Guide

```
domain_id: D8
code_baseline: 5883a140
```

## Recipe: Change subscription renewal
- **READ FIRST:** [FLOWS](FLOWS.md) (Flow 8), `renewal_service`, [TRANSACTIONS_AND_CONCURRENCY](TRANSACTIONS_AND_CONCURRENCY.md).
- **CANONICAL OWNER:** `renewal_service`.
- **LIKELY CODE:** `renewal_service.generate_renewals/_generate_one`; `RASTISI_BILLING_RENEWAL_LEAD_DAYS`.
- **DEPENDENT DOMAINS:** `subscriptions` (change_plan_version for scheduled downgrade), invoice numbering.
- **INVARIANTS:** `uniq_renewal_invoice_per_period`; canonical lock order Subscription→ScheduledPlanChange.
- **TESTS:** `test_renewals.py`. **REGRESSION RISK:** breaking idempotency → duplicate renewal invoices.

## Recipe: Add / change a billing payment provider
- **READ FIRST:** `providers/` (base, registry), [SERVICES](SERVICES.md).
- **LIKELY CODE:** new provider module + registry entry; `RASTISI_BILLING_PROVIDER` selection;
  webhook signature handling in `webhook_service`.
- **INVARIANTS:** verify BEFORE any business mutation; idempotent inbox.
- **TESTS:** `test_provider_and_attempts.py`, `test_zibal_platform_provider.py`.

## Recipe: Change webhook processing
- **READ FIRST:** `webhook_service.ingest_webhook`, [SECURITY](SECURITY.md).
- **INVARIANTS:** signature verify before business change; dedup via `(provider, external_event_id)`;
  size + timestamp tolerance; always return 200.
- **REGRESSION RISK:** weakening dedup/verify → double-apply or spoofed activation.

## Recipe: Change payment confirmation / activation
- **READ FIRST:** `confirmation_service.confirm_payment` + `_activate_or_renew`.
- **⚠️ Cross-domain:** confirmation DRIVES `subscription_service` (activate/renew/change_plan). Keep
  it funneled — never write `subscription.status` directly (M7).
- **INVARIANTS:** one transactional idempotent service; amount+currency vs invoice; never in a view.

## Recipe: Change dunning behavior
- **READ FIRST:** `dunning_service`, `RASTISI_BILLING_DUNNING_SCHEDULE`, [FLOWS](FLOWS.md).
- **INVARIANTS:** stage 0 → past_due + enter_grace; final → suspend + uncollectible.

## Recipe: Change plan-change billing
- **READ FIRST:** `plan_change_billing_service.start_plan_change`, `subscriptions.plan_change_service`.
- **⚠️ Split ownership:** merchant purchase/schedule is here; preview + platform override is in
  `subscriptions`. The primitive is `subscription_service.change_plan_version`. (ADR-72/80: no fake
  proration; upgrade requires payment, downgrade next period.)

## No open DR blocks billing changes
Billing has no DR-1…DR-8 item of its own; M7 (co-ownership of subscription lifecycle) is a documented
coupling to respect, not a blocker.
