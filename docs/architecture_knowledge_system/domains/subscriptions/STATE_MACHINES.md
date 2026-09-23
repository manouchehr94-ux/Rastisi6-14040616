# subscriptions — State Machines

```
domain_id: D7
code_baseline: 5883a140
```

## StoreSubscription.status — GUARDED (canonical table, ADR-66)
States: `pending`, `trialing`, `active`, `grace_period`, `past_due`, `suspended`, `cancelled`,
`expired`. TERMINAL = {cancelled, expired}.

- Table: module `ALLOWED_TRANSITIONS` in `subscription_service`. Enforced by `_transition`:
  `@atomic` callers, `select_for_update` on the subscription, legality check, **idempotent no-op**
  if same status + a prior event with the same idempotency_key, sets `is_current=False` on terminal,
  writes a `SubscriptionEvent` + audit.
- Public transitions (all `@atomic`): `create_subscription`, `start_trial`, `activate_subscription`,
  `enter_grace_period`, `mark_past_due`, `suspend_subscription`, `resume_subscription`,
  `cancel_at_period_end` (flag only), `cancel_immediately`, `expire_subscription`,
  `renew_subscription` (period advance; grace/past_due→active), `change_plan_version`
  (writes plan_version only), manual trial controls (`extend_trial`/`set_trial_end`/`end_trial_now`),
  `provision_default_subscription` (fail-open).
- Cron scan: `evaluate_subscription_states` → `_due_action`/`_apply_due_action` (trial end, grace,
  past_due, expire).

## Who triggers transitions
- **subscriptions:** `subscription_service` (the writer), `plan_change_service.execute_platform_admin_plan_override`.
- **billing (cross-domain, funneled — M7):** confirmation (activate/renew/change_plan), dunning
  (enter_grace/suspend), cancellation (cancel_*), renewal (change_plan_version).
- **NEVER** a direct `subscription.status =` outside `subscription_service`.

## PlanVersion.status
```
draft → published → retired → archived
```

## Invariant
`uniq_current_subscription_per_store` — exactly one `is_current=True` subscription per Store;
`_transition` clears `is_current` on terminal states.
