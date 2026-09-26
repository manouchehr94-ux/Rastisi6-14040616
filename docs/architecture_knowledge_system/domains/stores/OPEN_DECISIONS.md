# stores — Open Decisions

```
domain_id: D1
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects stores | Blocks |
|---|---|---|---|
| **DR-4** | Ownership-transfer duplication | TWO live paths: `membership_service.transfer_ownership` (dashboard) + `ownership_transfer_service` (portal OTP) | unifying/choosing the transfer path |
| **DR-7** | Store vs `catalog.Vendor` ownership | ADR-1 defers Vendor's meaning; ambiguity persists | defining Vendor's role |
| **DR-8** | `require_resolved_store` disposition | no live caller found; may be intentional API scaffolding | adopting/removing the helper |

## Related findings (not DRs)
- **M13** — deliberate cycle-avoidance (stores↝core, publication↝subscriptions local imports).
- **M15** — `is_staff` overloaded three ways.
- **M8** — derived store-visibility fails open (publication_service).
- **O4** — historical tenant-bleed fixed (dashboard figures scoping).

No option is selected. This pack maps the impact surface for each.
