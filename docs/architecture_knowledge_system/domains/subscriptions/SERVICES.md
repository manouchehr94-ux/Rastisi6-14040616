# subscriptions — Services

```
domain_id: D7
code_baseline: 5883a140
source: apps/subscriptions/services/ (7 files) + entitlements.py
```

| Service | Responsibility |
|---|---|
| **subscription_service** | THE canonical StoreSubscription state machine (`ALLOWED_TRANSITIONS`, `_transition` with select_for_update + idempotency + SubscriptionEvent). All public transitions (create/start_trial/activate/enter_grace/mark_past_due/suspend/resume/cancel_*/expire/renew/change_plan_version) + manual trial controls + `provision_default_subscription` (fail-open) + `evaluate_subscription_states` (cron) + `check_subscription_consistency` (read-only) |
| **plan_change_service** | `preview_plan_change` (read-only + `_preview_token`), `execute_platform_admin_plan_override` (staff+superuser gate; delegates to `change_plan_version`; supersedes ScheduledPlanChange). Note: the old public `execute_plan_change` was DELETED (good de-dup) |
| **entitlement_service** | resolve entitlements/access state (`get_subscription_access_state`); fail-open for legacy stores |
| **enforcement** | seat/limit enforcement (used by staff add, export budget) |
| **usage_service** | UsageRecord counters |
| **plan_service** | plan/version helpers |
| **legacy_service** | `provision_legacy_real` (legacy store provisioning) |
| **entitlements.py** | entitlement definitions/keys |

## Key discipline
- **`subscription_service` is the ONLY legal writer of `subscription.status`** (module docstring:
  "no view may write subscription.status directly").
- Transitions are idempotent (SubscriptionEvent idempotency_key) and locked (select_for_update).
- Fail-open: `entitlement_service` returns ACTIVE_PAID-equivalent access when no subscription exists
  (legacy/test stores stay usable) — this is also why store-visibility fails open (M8).
