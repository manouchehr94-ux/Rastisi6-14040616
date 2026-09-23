# subscriptions — Dependencies

```
domain_id: D7
code_baseline: 5883a140
known_risks: M7
```

## subscriptions depends ON
| Target | Type | What |
|---|---|---|
| `stores` | foreign-key | `StoreSubscription.store` |
| `core` | uses | TimeStampedModel, audit |

subscriptions does **not** call billing (billing calls subscriptions). It does not move money.

## Depends ON subscriptions
| Source | Type | What |
|---|---|---|
| `billing` | writes (funneled, M7) | confirmation/dunning/renewal/cancellation → subscription_service transitions |
| `stores.publication_service` | reads (local import) | entitlement/access state |
| `dashboard` | reads | subscription banner, seat gate |
| `core.export_service` | reads | export budget entitlement |
| `portal.provisioning_service` | calls | provision_default_subscription |
| cron | calls | evaluate_subscription_states |

## Relationship note (M7)
The subscription lifecycle is effectively co-owned with `billing`, but the boundary is clean:
billing calls `subscription_service`; there is no direct status write from billing.
