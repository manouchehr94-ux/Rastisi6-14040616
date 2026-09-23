# dashboard — Change Guide

```
domain_id: D11
code_baseline: 5883a140
open_decisions: DR-2, DR-3, DR-4
```

> dashboard writes many OTHER domains' models. **Before changing a write path, check whether it
> should go through the owning domain's service** (Pattern A) or is a direct view write (Pattern B —
> content/settings/config, H2/M5). Prefer the owning domain's `CHANGE_GUIDE`.

## Recipe: Add / change a merchant admin page (general)
- **READ FIRST:** [ENTRY_POINTS](ENTRY_POINTS.md), [SECURITY](SECURITY.md) (decorators).
- **CANONICAL OWNER:** the OWNING domain's service (Pattern A) — do not add a direct write if a
  service exists.
- **SECURITY:** apply `staff_required` + `permission_required`; keep `request.store` scope.
- **REGRESSION RISK:** tenant-bleed if a query is not store-scoped (see O4). Add an isolation test.

## Recipe: Change a catalog/order/staff/import/export admin flow (Pattern A)
- **CANONICAL OWNER:** catalog/orders/stores/core services. Change the SERVICE, call it from the view.
- **See:** the owning domain's pack (`../orders/CHANGE_GUIDE.md`, `../catalog/CHANGE_GUIDE.md`, etc.).

## Recipe: Change content management (Pattern B — H2 / DR-2)
- **⚠️ No content service.** Content CRUD is direct in `views.py` (~4705-5610). Read
  [`../content/CHANGE_GUIDE.md`](../content/CHANGE_GUIDE.md) and [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md).
- **OPEN DECISION:** DR-2 — creating a content service is that decision.

## Recipe: Change shop settings / shipping / tax / gateway config (Pattern B — M5 / DR-3)
- **⚠️ Direct writes** in `settings_*` views (ShopSettings ~4308-4458; shipping/tax ~6866-7281;
  gateway config ~5726-5784 incl. credential encryption).
- **OPEN DECISION:** DR-3 — routing these through owning-domain services is that decision.

## Recipe: Change staff / ownership transfer (DR-4)
- **⚠️** `staff_transfer_ownership` (~5896) calls `membership_service.transfer_ownership` — one of
  **two live** transfer paths (the other is portal OTP). Read [`../stores/CHANGE_GUIDE.md`](../stores/CHANGE_GUIDE.md).
- **OPEN DECISION:** DR-4.

## Recipe: Change dashboard reports / stats
- **CANONICAL OWNER:** `dashboard_service`/`report_service` (read-only). **⚠️** keep every query
  `store`-scoped (O4 was a cross-store figures bug). Tests: report/dashboard view tests.
