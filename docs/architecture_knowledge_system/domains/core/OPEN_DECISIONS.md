# core — Open Decisions

```
domain_id: D14
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects core | Blocks |
|---|---|---|---|
| **DR-3** | service-layer write discipline for settings/config | `ShopSettings` (owned by core) is written directly by `dashboard.views` + `sms_service` (M5); no core write-service | routing ShopSettings writes through an owning-domain service |

## Related findings (not DRs)
- **M13** — `stores` avoids importing core (future `core → stores` FK planned).
- **M14** — export in core, import in dashboard (asymmetric).
- **D4** — `ShopSettings` legacy SMS credential fields POTENTIALLY_DEAD.

No option is selected.
