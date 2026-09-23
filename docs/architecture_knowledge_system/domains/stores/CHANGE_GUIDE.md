# stores — Change Guide

```
domain_id: D1
code_baseline: 5883a140
open_decisions: DR-4, DR-7, DR-8
```

## Recipe: Add a new Store status
- **READ FIRST:** [STATE_MACHINES](STATE_MACHINES.md), [DATA_MODEL](DATA_MODEL.md), `publication_service`.
- **CANONICAL OWNER:** `store_status_service` / `deletion_service`.
- **LIKELY CODE:** `Store.Status` choices; `store_status_service`; **`publication_service`**
  (visibility derivation — a new status must be classified public/non-public); resolution eligibility
  (`domain_is_eligible_for_routing` checks `status==ACTIVE`).
- **DEPENDENT DOMAINS:** everything that reads `Store.status` for visibility (storefront render,
  dashboard gating). `publication_service.NON_PUBLIC_STATES` must be updated.
- **INVARIANTS:** resolution routes only ACTIVE stores; a new status is non-routable unless added.
- **TESTS:** `test_publication_service.py`, `test_resolution.py`, `test_deletion_service.py`.
- **REGRESSION RISK:** forgetting `publication_service`/resolution → store silently public or dark.

## Recipe: Change Host→Store resolution
- **READ FIRST:** `resolution.py` (docstring forbids other resolvers), [SECURITY](SECURITY.md).
- **CANONICAL OWNER:** `resolve_store_for_hostname` (sole resolver) + `resolve_store_for_admin_request`.
- **INVARIANTS:** fail-closed; VERIFIED non-retired domain + ACTIVE store; admin host is a separate path.
- **REGRESSION RISK:** a resolution bug is a tenant-isolation bug (cross-store data exposure).
- **OPEN DECISION:** DR-8 (`require_resolved_store` unused helper) — do not adopt/remove without deciding.

## Recipe: Change ownership transfer
- **⚠️ DR-4:** there are **two live** paths — `membership_service.transfer_ownership` (dashboard)
  and `ownership_transfer_service` (portal OTP). A change likely must touch **both** or explicitly
  pick one. Read [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md).
- **INVARIANTS:** exactly one active OWNER; demote-then-promote to respect the constraint.

## Recipe: Change domain verification
- **READ FIRST:** `domain_verification_service`, [STATE_MACHINES](STATE_MACHINES.md) (5 CheckConstraints).
- **INVARIANTS:** real DNS/TLS checks (never self-mark verified); hostname normalized/unique;
  retired domains never route/primary.
- **EXTERNAL:** dnspython + SSL socket.

## Recipe: Change membership roles / permissions
- **READ FIRST:** `authorization.py` role matrix, `dashboard.decorators.permission_required`.
- **⚠️ M15:** do not conflate `is_staff` with dashboard access (staff_required uses StoreMembership).
- **REGRESSION RISK:** reserved/inert permission keys exist (D7) — adding a real view for one changes behavior.

## Recipe: Change Store vs Vendor relationship
- **BLOCKED BY DR-7.** ADR-1 defers Vendor's meaning; do not decide here.
