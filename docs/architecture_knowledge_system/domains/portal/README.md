# Domain: portal (D2) — Platform Control & Owner Identity

```
domain_id: D2
app: apps/portal
canonical_pack_status: CANONICAL
phase4_prepack_documentation_readiness: PARTIAL
code_baseline: 5883a140
open_decisions: DR-4
known_risks: M15
```

Owns platform-global config, owner/staff identity + auth (email/password + phone OTP + step-up),
Host-based URLconf routing, store provisioning orchestration, and the platform-admin console.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[DEPENDENCIES](DEPENDENCIES.md) · [SECURITY](SECURITY.md) · [TESTING](TESTING.md) ·
[CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) · [HISTORICAL_CONTEXT](HISTORICAL_CONTEXT.md) ·
[OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* STATE_MACHINES (OTP/handoff lifecycles → SECURITY), FLOWS (canonical Flows 5/6/14),
INVARIANTS/TRANSACTIONS/API_AND_EVENTS/ARCHITECTURE/TROUBLESHOOTING → SERVICES + SECURITY.

## Orientation
- **Owns:** `OwnerProfile`, `OwnerOtpChallenge`, `AdminHandoffTicket`, `PlatformConfiguration`
  (pk=1 singleton), `PlatformAuditLogEntry`, `PlatformInternalNote`, `ContactMessage`; the
  `PlatformHostRoutingMiddleware`; owner auth/OTP/step-up services; **provisioning** (creates
  stores+core+catalog+subscriptions in one atomic).
- **Does NOT own:** Store data (`stores`), storefront customer identity (`customers`), billing.
- **Serves two surfaces:** owner portal (`urls.py` on `RASTISI_PLATFORM_HOSTS`) + platform admin
  (`platform_admin_urls`/`platform_admin_views` on `RASTISI_PLATFORM_ADMIN_HOSTS`).
- **Auth:** owner = phone OTP (primary) + email/password (legacy); shared identity with customer via
  `username == phone` (ADR-102). Platform admin = `is_staff` AND `is_superuser`.
- **Open decisions:** DR-4 (one of the two live ownership-transfer paths calls `owner_auth_service`).
