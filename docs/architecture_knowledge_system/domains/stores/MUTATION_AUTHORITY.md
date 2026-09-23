# stores — Mutation Authority

```
domain_id: D1
code_baseline: 5883a140
open_decisions: DR-4
```

| Entity | Canonical writer(s) | Other / cross-domain |
|---|---|---|
| `Store.status` / suspension | `store_status_service` (suspend/activate), `deletion_service` (→closed) | `portal.provisioning_service` (create ACTIVE); `platform_admin_views`; `Store.save()` fallbacks (admin_subdomain/platform_code) |
| `Store.onboarding_*` | portal onboarding views (INFERRED) | `publication_service` reads only |
| `StoreMembership` | `membership_service` (add/change/revoke/reactivate/**transfer_ownership**) | `ownership_transfer_service.accept` (portal OTP flow); `provisioning_service` (initial OWNER) |
| `StoreDomain` verification/routing/tls | `domain_verification_service` | `handle_service` (claim/rename → VERIFIED platform_subdomain); `provisioning_service` (VERIFIED generated_trial); `platform_admin_views` domain check/set-primary |
| `StoreOwnershipTransfer` | `ownership_transfer_service` | — |
| `StoreIntegrationConnection` | `stores.integration_service` (via dashboard) | — |

## ⚠️ Two LIVE ownership-transfer writers (DR-4 / M6)
1. **`membership_service.transfer_ownership`** — LIVE, called from `dashboard/views.py:5896`
   (`staff_transfer_ownership`, route `staff/<pk>/transfer-ownership/`). Synchronous,
   membership-to-membership; demotes OWNER→ADMINISTRATOR, promotes new.
2. **`ownership_transfer_service`** — the portal two-party OTP-gated flow via
   `StoreOwnershipTransfer` (initiate/accept/cancel).

Both are live. Which is canonical is **DR-4 (OPEN)**. (Phase 2 disproved the earlier "possibly
dead" hypothesis for #1.)

## Hostname write guard
`StoreDomainQuerySet.update(hostname=...)` raises `StoreDomainMutationError`; `bulk_create`
normalizes. Hostname must always be the normalized canonical form.

## No signals
All mutations are explicit service calls; `stores` services enqueue `notifications` explicitly.
