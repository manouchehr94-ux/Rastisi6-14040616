# dashboard — Security

```
domain_id: D11
code_baseline: 5883a140
known_risks: H2, M5, M15, O4
```

## Auth/authorization (VERIFIED)
- `staff_required`: resolves the admin store or **404** (never leaks store existence for a wrong
  admin host); unauthenticated → redirect to central login with a signed `admin_return` handoff
  token; requires an **ACTIVE `StoreMembership`** (else redirect to storefront). Caches
  `request.store` + `request.store_membership`.
- **⚠️ M15:** `staff_required` deliberately **ignores `is_staff`** (phone/OTP owners never get
  `is_staff=True`). Do not "fix" it to check `is_staff` — that would break tenant-scoped access.
- `permission_required(*perms)`: OR-semantics over `membership_has_permission`; renders 403. Must be
  inside `staff_required`.

## Tenant isolation (VERIFIED, incl. O4 fix)
- All reads/writes are scoped to `request.store`. `dashboard_service`/`report_service` docstrings
  record a **prior cross-store figures bug (O4)**, since fixed by explicit `Order.store` scoping.
- Embed: `AdminEmbedFrameOptionsMiddleware` relaxes X-Frame-Options to SAMEORIGIN only for
  authenticated `?embed=1` dashboard views (storefront-builder embedding).

## Write-boundary risk (H2/M5)
Because dashboard writes content/ShopSettings/config **directly** (no owning-domain service), the
validation/authorization posture for those writes depends on each view remembering Store scope +
`full_clean()`. Centralizing this is DR-2/DR-3.

## Credential handling
Gateway-config credential encryption is orchestrated in the settings view
(`config.set_credentials` / `CredentialEncryptionError`) — a direct write of an encrypted blob
(M5/DR-3).
