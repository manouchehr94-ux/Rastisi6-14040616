# subscriptions — Mutation Authority

```
domain_id: D7
code_baseline: 5883a140
known_risks: M7
```

| Entity | Canonical writer | Other |
|---|---|---|
| **StoreSubscription.status** | `subscription_service` transitions (ONLY) | billing (funneled via subscription_service); `plan_change_service` override (via change_plan_version) |
| `SubscriptionEvent` | `subscription_service._record_event` | — |
| `UsageRecord` | `usage_service` | — |
| `Plan` / `PlanVersion` / `EntitlementDefinition` / `PlanEntitlement` | admin / `plan_service` / `seed_default_plans` command | — |

## The rule
**No code outside `subscription_service` writes `StoreSubscription.status` directly.** billing
(confirmation/dunning/renewal/cancellation) and `plan_change_service` all call subscription_service
transitions. This is the cross-domain coupling M7 — disciplined, not a direct-write violation.

## Admin
`StoreSubscriptionAdmin` makes `status` **readonly** (superuser-only) — reinforcing that the service
is the only mutator.

## No signals
Transitions are explicit service calls; no `@receiver`.
