# billing — Dependencies

```
domain_id: D8
code_baseline: 5883a140
known_risks: M7
```

## billing depends ON
| Target | Type | What |
|---|---|---|
| `subscriptions` | writes (funneled via subscription_service) | activate/renew/change_plan/enter_grace/suspend/cancel (M7) |
| providers (manual/zibal) | external-call | session create, verify, refund; webhook signature |
| `portal.PlatformConfiguration` | reads | platform provider creds (zibal) |
| `core` | uses | TimeStampedModel, audit |

## Depends ON billing
| Source | Type | What |
|---|---|---|
| webhook (public) | routes-to | `billing_webhook` |
| cron | calls | renewal/dunning commands |
| `portal` | calls | checkout/plan-change → billing services |
| admin | calls | mark-paid / retry actions |

## Relationship to subscriptions (M7)
billing effectively **co-owns** the subscription lifecycle, but always through
`subscription_service` (no direct `subscription.status` write). Plan-change logic is split:
`billing.plan_change_billing_service` (merchant purchase/schedule) vs
`subscriptions.plan_change_service` (preview + platform override); the low-level primitive is
`subscription_service.change_plan_version`.

## Not a dependency
`orders` (separate money system).
