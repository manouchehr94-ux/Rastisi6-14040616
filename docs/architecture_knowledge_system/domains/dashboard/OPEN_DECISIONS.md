# dashboard — Open Decisions

```
domain_id: D11
code_baseline: 5883a140
```

Full detail: [`../../canonical/ARCHITECTURAL_DECISION_REGISTER.md`](../../canonical/ARCHITECTURAL_DECISION_REGISTER.md).

| DR | Title | Why it affects dashboard | Blocks |
|---|---|---|---|
| **DR-2** | content domain write boundary | dashboard views ARE the content write surface (H2) | introducing a content service / refactoring content writes |
| **DR-3** | settings/config service discipline | dashboard writes ShopSettings + shipping/tax/gateway config directly (M5) against ADR-58/69 | routing those writes through owning-domain services |
| **DR-4** | ownership-transfer duplication | dashboard hosts one of the two live transfer paths (`staff_transfer_ownership` → `membership_service.transfer_ownership`) | unifying the transfer path |

## Related findings (not DRs)
- **M14** — import_service (dashboard) vs export_service (core) asymmetry.
- **M15** — `is_staff` overloaded (staff_required ignores it).
- **O4** — historical tenant-bleed in figures, since fixed.

No option is selected.
