# subscriptions — Historical Context

```
domain_id: D7
code_baseline: 5883a140
```

Evidence/history only — not modified/moved/archived here.

| Document | Level | Relationship to code | Label |
|---|---|---|---|
| `SAAS_DOMAIN_DECISIONS.md` ADR-66 | L3 ADR | MATCHES_CODE — subscription transitions governed by `ALLOWED_TRANSITIONS` | AUTHORITATIVE-INTENT |
| `SAAS_DOMAIN_DECISIONS.md` ADR-72 | L3 ADR | MATCHES_CODE — plan change alters entitlements only; money is billing (5B) | AUTHORITATIVE-INTENT |
| `docs/reports/PRELAUNCH_PHASE2_SUBSCRIPTIONS_TRIALS.md` | L4 report | HISTORICAL — prelaunch subscriptions/trials report | HISTORICAL |

## Key point
The canonical state machine + `ALLOWED_TRANSITIONS` (ADR-66) is faithfully implemented, with
idempotency (SubscriptionEvent) and locking. The "no money moves in plan change" decision (ADR-72)
holds: subscriptions changes entitlements; billing moves money.

## De-dup already done (positive)
`plan_change_service` records that the old public `execute_plan_change` was **deleted** in favor of
the platform-override + billing-driven paths — an example of the codebase resolving a duplication.
