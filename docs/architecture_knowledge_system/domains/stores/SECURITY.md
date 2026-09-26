# stores — Security

```
domain_id: D1
code_baseline: 5883a140
known_risks: M15
```

## Tenant isolation (the domain's core security job)
- `resolve_store_for_hostname` is the **sole** authoritative Host→Store resolver; the module
  docstring forbids any other code guessing a Store from host/user/session. Fail-closed: unresolved
  host → `request.store=None`.
- Admin-host resolution is a **separate** path (`resolve_store_for_admin_request`); a wrong admin
  host returns 404 (never leaking store existence).
- Storefront visibility gated by `publication_service` (but fails open — M8).

## Authorization
- `authorization.py` role→permission matrix; consumed by `dashboard.decorators.permission_required`.
- Some permission constants are reserved/inert forward-design (D7 dead-code, not a vulnerability).

## ⚠️ `is_staff` overloaded three ways (M15)
- `membership_service.add_staff_member` sets `User.is_staff=True` for dashboard staff.
- `dashboard.staff_required` **ignores** `is_staff` (uses StoreMembership).
- Platform admin **requires** `is_staff` + `is_superuser`; Django `/admin/` requires superuser.
A change to `is_staff` semantics affects all three surfaces. See canonical
[`../../canonical/SECURITY_AND_TRUST_BOUNDARIES.md`](../../canonical/SECURITY_AND_TRUST_BOUNDARIES.md).

## Domain verification integrity
A merchant can never self-mark a domain verified — `domain_verification_service` performs real DNS
TXT + SSL socket checks.

## Ownership / deletion
- Exactly one active OWNER per Store (`uniq_active_owner_per_store`).
- Deletion is soft then scheduled purge; `purge_due_stores` logs a PlatformAuditLogEntry BEFORE the
  real delete (store-owned AuditLogEntry cascades).
- `StoreMembership.user` is PROTECT (deleting a User with memberships raises ProtectedError).

## Integration credentials
`StoreIntegrationConnection` credentials encrypted via `orders.encryption` (Fernet).
