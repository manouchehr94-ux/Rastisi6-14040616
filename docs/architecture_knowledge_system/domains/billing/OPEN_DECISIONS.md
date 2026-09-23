# billing — Open Decisions

```
domain_id: D8
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

## No DR-1…DR-8 item originates in or blocks billing
billing has no open architectural decision of its own. Its cross-cutting note is **M7** — billing
co-owns the `subscriptions` lifecycle by driving it (through `subscription_service`, funneled).
This is a documented, disciplined coupling, not an open decision.

## Relevant finding
- **M7** — billing → subscriptions state-machine driver. Keep it funneled through
  `subscription_service`; never write `subscription.status` directly.

If a future decision proposes merging billing with orders' payment stack, that would be a **new**
decision (and would contradict ADR-73). It is not currently on the register.
