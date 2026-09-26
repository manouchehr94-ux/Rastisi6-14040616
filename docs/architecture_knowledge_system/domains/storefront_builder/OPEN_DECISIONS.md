# storefront_builder — Open Decisions

```
domain_id: D9
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects storefront_builder | Blocks |
|---|---|---|---|
| **DR-6** | Legacy-path removal | The R3 legacy editor is retained fail-closed; SAAS_MIGRATION_PLAN PR12 "legacy-path removal" is unrealized (also covers orders' simulation/Transaction) | retiring the R3 editor |

## Related findings (documented smells, not DRs)
- **H3** — three editor/template generations coexist (R3/R4/A8).
- **M1** — duplicate appearance/theme/palette sources (registries + mirrored header/footer_config).
- **M2** — footer represented 3 ways (also content + registry).
- **M10** — dual settings validation (settings_schema + legacy validate_settings, Strangler).
- **M11** — dual placement media (content).
- **M12** — three coexisting section-placement mechanisms.

M1/M2/M10/M11/M12 are documented duplications. Consolidating them (e.g. collapsing appearance
sources, or unifying footer) would be a **new** architecture decision, not one of DR-1…DR-8. This
pack records them precisely; it selects no option.
