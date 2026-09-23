# billing — Security

```
domain_id: D8
code_baseline: 5883a140
```

## Webhook trust (VERIFIED)
- `billing/webhook/<provider>/` is public + csrf-exempt but **signature-verified before any
  business mutation** (ADR-76). Bodies over `RASTISI_BILLING_MAX_WEBHOOK_BYTES` are rejected;
  timestamp tolerance `RASTISI_BILLING_WEBHOOK_TOLERANCE_SECONDS`. Payload is redacted before store.
- Always returns 200 (so the provider does not retry-storm) but only processes verified, deduped events.

## Payment-integrity trust (VERIFIED)
- Browser return is never proof; only signed webhook or server-side pull (`fetch_payment_status`)
  confirms.
- amount + currency validated against the invoice, never the browser.
- `confirm_payment` is one transactional idempotent service, **never in a view** (ADR-77).

## Secrets
- Platform provider (zibal) credentials on `portal.PlatformConfiguration` (encrypted); webhook
  secret from `RASTISI_BILLING_WEBHOOK_SECRET`. Secrets never from the database-as-plaintext or code.

## Tenancy
Invoices/attempts are Store-scoped (via subscription/account). Admin is superuser-only;
financially-locked fields are readonly in admin.

## No known HIGH security risk in this domain
The billing domain's discipline (verified idempotent inbox, transactional confirmation) is a model
the rest of the codebase is measured against. Its main cross-cutting note is M7 (co-owns
subscription lifecycle) — a coupling, not a vulnerability.
