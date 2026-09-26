# Domain: stores (D1) — Tenancy & Store Identity

```
domain_id: D1
app: apps/stores
canonical_pack_status: CANONICAL
phase4_prepack_documentation_readiness: READY
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2 / Phase 4
open_decisions: DR-4, DR-7, DR-8
known_risks: M13, M15, O4
```

The SaaS **tenant boundary**. Owns Store lifecycle, membership/roles, domains (verify/route/TLS),
ownership transfer, the authoritative Host→Store resolution, and the authorization matrix.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [STATE_MACHINES](STATE_MACHINES.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[SECURITY](SECURITY.md) · [INVARIANTS](INVARIANTS.md) · [TESTING](TESTING.md) ·
[CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md) ·
[HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md)

*Folded (not empty files):* API_AND_EVENTS (no external API except DNS/TLS in domain_verification —
see SERVICES/EXTERNAL_INTEGRATIONS), FLOWS (see canonical RUNTIME_FLOW_INDEX flows 0/5/12/14),
ARCHITECTURE/TROUBLESHOOTING/TRANSACTIONS (folded into SERVICES + INVARIANTS).

## Orientation
- **Owns:** `Store`, `StoreDomain`, `StoreMembership`, `StoreOwnershipTransfer`,
  `StoreIntegrationConnection`; `resolution.py` (Host→Store), `authorization.py` (role matrix),
  `middleware.py`, `hostnames.py`, `admin_permissions.py`.
- **Does NOT own:** billing/subscription state (`billing`/`subscriptions`), ShopSettings (`core`),
  owner identity (`portal`), catalog Vendor (`catalog` — A1 ambiguity).
- **Canonical services:** `resolution.resolve_store_for_hostname` (sole resolver),
  `publication_service` (visibility), `store_status_service`, `domain_verification_service`,
  `membership_service`, `ownership_transfer_service`, `deletion_service`, `handle_service`,
  `platform_code_service`.
- **State machines:** `Store.status`, `Store.onboarding_stage` (soft), `StoreDomain`
  verification/routing/tls, `StoreMembership.status`, `StoreOwnershipTransfer.status`.
- **Why READY:** strong, code-matching ADR coverage (ADR-1/2/3/11/16/17). It is the best-documented
  domain even before this pack.
- **Open decisions:** DR-4 (two live ownership-transfer paths), DR-7 (Store vs Vendor), DR-8
  (`require_resolved_store` unused).
