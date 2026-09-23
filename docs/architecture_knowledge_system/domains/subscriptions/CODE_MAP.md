# subscriptions — Code Map

```
domain_id: D7
code_baseline: 5883a140
```

```
apps/subscriptions/
├── models.py             7 models (StoreSubscription, Plan, PlanVersion, EntitlementDefinition,
│                         PlanEntitlement, SubscriptionEvent, UsageRecord)
├── entitlements.py       entitlement definitions/keys
├── services/             7 files:
│   ├── subscription_service.py   ALLOWED_TRANSITIONS + _transition (THE state machine)
│   ├── plan_change_service.py    preview + platform override (old public execute_plan_change DELETED)
│   ├── entitlement_service.py    access-state resolution (fail-open)
│   ├── enforcement.py            seat/limit enforcement
│   ├── usage_service.py          UsageRecord
│   ├── plan_service.py           plan/version helpers
│   └── legacy_service.py         provision_legacy_real
├── management/commands/  evaluate_subscription_states, provision_legacy_subscriptions,
│                         seed_default_plans, verify_subscription_consistency
├── admin.py              StoreSubscription status readonly (superuser)
├── migrations/
└── tests/                test_state_machine, test_plan_change, test_manual_trial_controls,
                          test_management_and_isolation
```

## Where to look
| Concern | File |
|---|---|
| Subscription state machine | `services/subscription_service.py` |
| Entitlement resolution | `services/entitlement_service.py` |
| Plan change | `services/plan_change_service.py` (+ billing plan_change_billing_service) |
| Enforcement (seats/limits) | `services/enforcement.py` |
