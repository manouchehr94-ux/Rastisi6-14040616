# subscriptions — Change Guide

```
domain_id: D7
code_baseline: 5883a140
```

## Recipe: Add a subscription state / change a transition
- **READ FIRST:** [STATE_MACHINES](STATE_MACHINES.md), `subscription_service` `ALLOWED_TRANSITIONS`.
- **CANONICAL OWNER:** `subscription_service` (the ONLY writer).
- **LIKELY CODE:** `StoreSubscription.Status` choices; `ALLOWED_TRANSITIONS` table; a public
  transition function; `_transition` guard; `is_current` handling on terminal.
- **DEPENDENT DOMAINS:** `billing` (calls transitions), `stores.publication_service` (may classify
  the new state as public/non-public), `dashboard` (banner), enforcement.
- **INVARIANTS:** transitions idempotent (SubscriptionEvent key); `uniq_current_subscription_per_store`;
  select_for_update.
- **TESTS:** `test_state_machine.py`; billing `test_confirmation_activation.py`.
- **REGRESSION RISK:** a caller in billing that expects the old transition set; publication_service
  visibility classification.

## Recipe: Change entitlements
- **READ FIRST:** `entitlement_service`, `enforcement`, `PlanEntitlement` model.
- **LIKELY CODE:** `EntitlementDefinition`/`PlanEntitlement`; `entitlement_service.get_subscription_access_state`.
- **⚠️ Fail-open (M8):** no subscription → access granted. Changing this affects store visibility.

## Recipe: Change plan-change behavior
- **READ FIRST:** `plan_change_service` (preview + override) AND `billing.plan_change_billing_service`
  (merchant purchase/schedule). Primitive: `subscription_service.change_plan_version`.
- **⚠️ Split ownership** across subscriptions + billing (ADR-72/80: no fake proration).

## Recipe: Change renewal semantics
- **READ FIRST:** `subscription_service.renew_subscription` + `billing.renewal_service`.
- **⚠️ Cross-domain:** billing generates renewal invoices and calls back into subscriptions.

## No open DR blocks subscription changes
subscriptions has no DR-1…DR-8 of its own; respect M7 (billing funnels through subscription_service).
