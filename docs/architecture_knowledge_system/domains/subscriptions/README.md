# Domain: subscriptions (D7) — SaaS Subscriptions & Entitlements

```
domain_id: D7
app: apps/subscriptions
status: CANONICAL
readiness: PARTIAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
open_decisions: —
known_risks: M7
```

Owns the **canonical `StoreSubscription` state machine**, plans/versions/entitlements, and usage
records. The subject that `billing` drives (via `subscription_service`, funneled — M7).

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[STATE_MACHINES](STATE_MACHINES.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [DEPENDENCIES](DEPENDENCIES.md) · [TESTING](TESTING.md) ·
[CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) · [HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) ·
[OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* FLOWS (canonical Flow 9 + billing Flows 7/8), INVARIANTS/TRANSACTIONS/SECURITY/API_AND_EVENTS
→ into STATE_MACHINES + SERVICES (this domain is a tightly-guarded state machine).

## Orientation
- **Owns:** `StoreSubscription` (+ its state machine), `Plan`, `PlanVersion`,
  `EntitlementDefinition`, `PlanEntitlement`, `SubscriptionEvent`, `UsageRecord`; entitlement
  resolution/enforcement.
- **Does NOT own:** invoicing/payment (`billing`), Store identity (`stores`).
- **Canonical service:** `subscription_service` — **the only** legal writer of
  `StoreSubscription.status`, with a module `ALLOWED_TRANSITIONS` table (ADR-66), `select_for_update`,
  and idempotent transitions. `plan_change_service` (preview + platform override) + entitlement/
  usage/enforcement/legacy services support it.
- **Cross-domain:** `billing` drives transitions through `subscription_service`; `stores.publication_service`
  reads entitlement; `dashboard` reads for banners.
- **No public urls.py:** management commands + admin only.
