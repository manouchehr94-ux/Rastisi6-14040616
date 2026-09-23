# subscriptions — Data Model

```
domain_id: D7
code_baseline: 5883a140
source: apps/subscriptions/models.py (7 models)
```

| Model | Key fields / lifecycle | Constraints |
|---|---|---|
| **StoreSubscription** | `status` (pending/trialing/active/grace_period/past_due/suspended/cancelled/expired; TERMINAL={cancelled,expired}); `source` (legacy/default/admin/self_service); `is_current`; `cancel_at_period_end`; period/trial/grace timestamps; `external_reference` | **`uniq_current_subscription_per_store`** (partial, `is_current=True`) |
| **Plan** | `code` unique slug (immutable post-use) | — |
| **PlanVersion** | `status` (draft/published/retired/archived); `billing_interval` (monthly/yearly/none); display_price; trial_days; grace_period_days | `uniq(plan, version_number)` |
| **EntitlementDefinition** | `entitlement_type` (boolean/integer_limit/decimal_limit/text_value); `key` | `key` unique |
| **PlanEntitlement** | value columns + `is_unlimited`; `resolved_limit()` | `uniq(plan_version, entitlement)`; integer_limit≥0 check; `clean()` type match |
| **SubscriptionEvent** | immutable domain history; large `EventType` enum | partial unique `(subscription, idempotency_key)` |
| **UsageRecord** | period counters | `uniq(store, metric_key, period_start)` |

## Key facts
- `StoreSubscription.status` is the canonical platform-billing lifecycle; `is_current` backs the
  one-current-subscription-per-store constraint (set False on terminal transitions).
- `SubscriptionEvent` provides idempotency + audit for every transition.
