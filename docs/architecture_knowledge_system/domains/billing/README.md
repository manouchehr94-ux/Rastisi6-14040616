# Domain: billing (D8) — SaaS Billing (platform money)

```
domain_id: D8
app: apps/billing
canonical_pack_status: CANONICAL
phase4_prepack_documentation_readiness: PARTIAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2 / Phase 4
open_decisions: —
known_risks: M7
```

The **platform money** side of RastiSi: how a merchant pays RastiSi for a subscription. Deliberately
**separate** from storefront/orders payments (ADR-73) — separate invoice, payment-attempt, provider,
and refund models. Drives (never bypasses) the `subscriptions` state machine.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [FLOWS](FLOWS.md) · [STATE_MACHINES](STATE_MACHINES.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[TRANSACTIONS_AND_CONCURRENCY](TRANSACTIONS_AND_CONCURRENCY.md) · [SECURITY](SECURITY.md) ·
[TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) ·
[HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* INVARIANTS/API_AND_EVENTS/ARCHITECTURE/TROUBLESHOOTING → into SERVICES + FLOWS +
STATE_MACHINES (this is a strongly-disciplined domain; see below).

## Orientation
- **Owns:** `StoreBillingAccount`, `SubscriptionInvoice`(+Line), `SubscriptionPaymentAttempt`,
  `BillingWebhookEvent`, `SubscriptionDunningState`, `SubscriptionCreditNote`, `SubscriptionRefund`,
  `ScheduledPlanChange`, `BillingSequence`.
- **Does NOT own:** subscription lifecycle (`subscriptions` — billing *drives* it via
  `subscription_service`); storefront/order payments (`orders`).
- **Canonical services (15):** `invoice_service`, `attempt_service`, `confirmation_service`,
  `payment_flow_service`, `webhook_service`, `renewal_service`, `dunning_service`,
  `cancellation_service`, `refund_service`, `credit_note_service`, `numbering_service`,
  `account_service`, `period_utils`, `consistency_service`, `plan_change_billing_service`.
- **Discipline (VERIFIED):** every mutation service is `@atomic` + `select_for_update` on the
  aggregate; webhooks land in a verified idempotent inbox before any business mutation (ADR-76);
  confirmation is one transactional idempotent service, never in a view (ADR-77). This is one of the
  best-guarded domains.
- **Cross-domain:** drives `subscriptions.StoreSubscription` transitions **only** via
  `subscription_service` (M7 — funneled, not direct).
- **Providers:** `manual` (default), `zibal`. Webhook: `billing/webhook/<provider_code>/`.
