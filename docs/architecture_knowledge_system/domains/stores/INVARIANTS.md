# stores — Invariants

```
domain_id: D1
code_baseline: 5883a140
```

## Enforced in code (VERIFIED)
1. **Exactly one active OWNER per Store** — `uniq_active_owner_per_store` (partial constraint).
2. **Store ownership is only via active OWNER membership** — no `Store.owner` field (ADR-2).
3. **`StoreDomain.hostname` is always normalized + globally unique** — save/clean normalize;
   `StoreDomainQuerySet.update(hostname=)` is blocked; bulk_create normalizes.
4. **At most one primary domain per Store** — `uniq_primary_domain_per_store`; a retired domain is
   never primary.
5. **Domain verification lifecycle coherence** — 5 CheckConstraints tie status↔timestamps↔token.
6. **Host→Store resolution is fail-closed** — only ACTIVE store + VERIFIED, non-retired domain routes.
7. **`admin_subdomain`/`platform_code`/`slug`/`public_id` are unique**; `admin_subdomain` is ASCII/DNS-safe.
8. **Membership status coherence** — active requires accepted_at; revoked requires revoked_at.
9. **Deletion is always soft first** — data is not purged until `deletion_scheduled_purge_at`.
10. **`StoreMembership.user` is PROTECT** — a User with memberships cannot be silently deleted.

## Convention-enforced (not a DB constraint)
- **`onboarding_completed_at` is read for visibility ONLY via `publication_service`** (documented
  convention, not a hard guard).

## Ambiguous (documented, not resolved)
- **Store vs `catalog.Vendor`** (A1/DR-7): the coexistence contract is not fully expressed in code.
