# Domain: customers (D3) — Customer Identity & CRM

```
domain_id: D3
app: apps/customers
status: CANONICAL
readiness: POOR
code_baseline: 5883a140
open_decisions: —
known_risks: —
```

Owns the **global** shopper account (`Customer`, phone-keyed, no store FK), the per-Store CRM
projection (`CustomerProfile`), segments/tags, addresses, wishlist, and customer auth (+ guest→user
cart merge). Readiness POOR: only scattered ADRs, no consolidated CRM doc — this pack fills the gap.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[DEPENDENCIES](DEPENDENCIES.md) · [SECURITY](SECURITY.md) · [TESTING](TESTING.md) ·
[CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* STATE_MACHINES (only `CustomerProfile.internal_status`), FLOWS/INVARIANTS/TRANSACTIONS/
API_AND_EVENTS/ARCHITECTURE/TROUBLESHOOTING/HISTORICAL_CONTEXT → into SERVICES + SECURITY + this README.

## Orientation
- **Owns:** `Customer` (global), `CustomerProfile` (store-scoped), `CustomerTag`, `CustomerNote`,
  `CustomerSegment`(+Rule/+Membership), `Address`, `Wishlist`.
- **Does NOT own:** owner identity (`portal`), orders, the cart (customers merges guest cart into
  the user cart — cross-domain).
- **Canonical service:** `auth_service` (signup / guest account / authenticate / merge_guest_cart).
  CRM operations (profile stats, notes, tags, segments) live in `dashboard.services`
  (customer_crm_service / segment_service) — a cross-domain write pattern.
- **Identity:** `Customer` is global (ADR-50/93); `username == phone`; shared with owner identity
  (ADR-102). `CustomerProfile` stats refreshed **explicitly**, no signals (ADR-50).
- **Historical:** ADR-6 (customer identity deferred, direction recorded), ADR-50/93/102.
