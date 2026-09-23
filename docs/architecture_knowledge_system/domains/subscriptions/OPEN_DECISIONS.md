# subscriptions — Open Decisions

```
domain_id: D7
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

## No DR-1…DR-8 item originates in subscriptions
subscriptions has no open architectural decision of its own. Its cross-cutting note is **M7** —
`billing` co-owns the lifecycle by driving it through `subscription_service` (funneled). This is a
documented, disciplined coupling, not an open decision.

## Relevant findings (not DRs)
- **M7** — billing → subscriptions state-machine driver (funneled).
- **M8** — entitlement fail-open propagates to store-visibility failing open (owned by
  `stores.publication_service`, but rooted in subscriptions' fail-open entitlement resolution).

No option is selected.
