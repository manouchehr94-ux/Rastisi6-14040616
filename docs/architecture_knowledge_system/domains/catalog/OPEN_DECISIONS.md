# catalog — Open Decisions

```
domain_id: D4
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects catalog | Blocks |
|---|---|---|---|
| **DR-7** | `Store` vs `catalog.Vendor` ownership | ADR-1 defers Vendor's final meaning; `Order` FKs Vendor; coexistence not fully expressed in code | defining Vendor's role (marketplace seller vs supplier vs …) |

## Related findings (not DRs)
- **M13** — cycle-avoidance: `IndustryTemplate.default_section_keys` validated in storefront_builder,
  not catalog; catalog imports storefront_builder lazily.

No option is selected. Note: `Product` row writes are less single-sourced than stock (dashboard
writes directly), documented in MUTATION_AUTHORITY — not currently a DR, but relevant to any future
catalog service-boundary decision.
