# subscriptions — Entry Points

```
domain_id: D7
code_baseline: 5883a140
```

`subscriptions` has **no public `urls.py`**. It is reached via services, cron, and admin.

## Management commands
- `evaluate_subscription_states` → `subscription_service.evaluate_subscription_states` (cron; trial
  end, grace, past_due, expire).
- `provision_legacy_subscriptions` → `legacy_service.provision_legacy_real`.
- `seed_default_plans` → seed Plan/PlanVersion/entitlements.
- `verify_subscription_consistency` → `check_subscription_consistency` (read-only).

## Service entry points (called by other domains)
- `subscription_service.*` transitions — called by `billing` (confirmation/dunning/renewal/
  cancellation) and `plan_change_service` override.
- `entitlement_service.get_subscription_access_state` — called by `stores.publication_service`,
  `dashboard` (banner), `core.export_service` (budget), `subscriptions.enforcement`.
- `provision_default_subscription` — called by `portal.provisioning_service`.

## Admin
Django admin, superuser-only; `StoreSubscription.status` is readonly.

## Signals / async
None.
