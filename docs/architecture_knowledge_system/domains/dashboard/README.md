# Domain: dashboard (D11) — Merchant Admin (controller)

```
domain_id: D11
app: apps/dashboard
status: CANONICAL
readiness: PARTIAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
open_decisions: DR-2, DR-3, DR-4
known_risks: H2, M5, M14, M15, O4
```

The merchant-facing admin at `/admin-portal/`. It **owns no models** (`models.py` is empty). It is a
controller/orchestration layer that authenticates + authorizes merchant staff and then writes
**other domains'** models — some via their services, some **directly**. It is the **de-facto write
surface for `content`, `core.ShopSettings`, and orders' shipping/tax/gateway config** (H2/M5).

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [SERVICES](SERVICES.md) · [ENTRY_POINTS](ENTRY_POINTS.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [DEPENDENCIES](DEPENDENCIES.md) · [SECURITY](SECURITY.md) ·
[TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) ·
[HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded/not-applicable:* DATA_MODEL (no models — see this README), STATE_MACHINES (none — dashboard
triggers others' machines), FLOWS/API_AND_EVENTS/INVARIANTS/TRANSACTIONS/ARCHITECTURE/TROUBLESHOOTING
→ folded into SERVICES + MUTATION_AUTHORITY + CHANGE_GUIDE.

## Orientation
- **Owns:** no models. Owns `urls.py`, a large `views.py` (~7.7k LOC), `decorators.py`,
  `middleware.py` (AdminEmbedFrameOptions), `forms.py`, `context_processors.py`, and a 12-file
  `services/` package (admin-side read/orchestration services).
- **Auth gate:** `staff_required` (resolve admin store or 404; require ACTIVE `StoreMembership`;
  **ignores `is_staff`** — M15) + `permission_required` (OR-semantics, inside staff_required).
- **Two write patterns:** (A) via the owning app's service (orders status, catalog, refunds/returns,
  staff, exports); (B) **direct** `.save()` on other apps' models (content, ShopSettings,
  shipping/tax/gateway config) — H2/M5, DR-2/DR-3.
- **Storefront-builder delegation:** ~60 routes wired to `storefront_builder.views/r4_views/media_views`.
- **Open decisions:** DR-2 (content boundary), DR-3 (settings/config service discipline), DR-4
  (ownership transfer — dashboard hosts one of the two live paths).
