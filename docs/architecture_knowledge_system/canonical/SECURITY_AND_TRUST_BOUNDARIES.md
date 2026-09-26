# Security & Trust Boundaries

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (docs 02/05/08) / Phase 2 (doc 05)
```

Tenant isolation, authentication surfaces, and trust boundaries. Grounded in code; not a security
audit (no penetration testing performed).

---

## 1. Tenant isolation (CURRENT CODE REALITY)
- **Boundary:** `apps.stores.Store`. Store-scoped data carries a `store` FK (directly or via a
  Store-owned parent).
- **Request scoping:** `request.store` set by `StoreResolutionMiddleware` from the Host via the
  sole authoritative resolver `resolve_store_for_hostname`. Unresolved/ineligible host →
  `request.store = None`; storefront views `Http404`/`403`.
- **Merchant admin scoping:** a separate resolver (`resolve_store_for_admin_request`) matches the
  admin subdomain; `dashboard.decorators.staff_required` requires an ACTIVE `StoreMembership` for
  that Store (returns 404 for a wrong admin host, never leaking existence).
- **Historical tenant-bleed:** `dashboard_service`/`report_service` docstrings record a prior
  cross-store figures bug, since fixed by explicit `Order.store` scoping (OBSERVATION O4).

## 2. Authentication surfaces (CURRENT CODE REALITY)
- **Auth model:** Django's default `auth.User` (`USERNAME_FIELD == "username"`), extended by two
  optional OneToOne profiles: `portal.OwnerProfile` and `customers.Customer`. A person may have
  either/both (shared identity via `username == phone`, ADR-102).
- **Owner/staff (portal):** phone + OTP (`owner_otp_service`, hashed codes, rate-limited,
  single-use) + legacy email/password (`owner_auth_service`). Sensitive actions gated by
  session-scoped step-up OTP (`step_up_service`).
- **Storefront customer:** phone + password / OTP (`customers.auth_service`); guest checkout
  auto-creates accounts.
- **Platform admin:** same `auth.User` but gated on `is_staff` **AND** `is_superuser`
  (`_is_platform_staff`). Django `/admin/` is superuser-only (`stores.admin_permissions`).

## 3. ⚠️ `is_staff` is overloaded (three meanings — MEDIUM M15)
1. `membership_service.add_staff_member` sets `User.is_staff=True` for dashboard staff.
2. `dashboard.staff_required` deliberately **ignores** `is_staff` (uses StoreMembership instead).
3. Platform admin **requires** `is_staff` + `is_superuser`; Django `/admin/` requires superuser.

A change to `is_staff` semantics can silently affect all three. See
[`../domains/stores/SECURITY.md`](../domains/stores/SECURITY.md) and DR context.

## 4. Authorization (CURRENT CODE REALITY)
- Merchant permissions: `stores.authorization` role→permission matrix; `dashboard.decorators.
  permission_required` (OR-semantics) inside `staff_required`; `context_processors.merchant_permissions`
  maps to `can_*` template flags. Some permission keys are reserved/inert forward-design (D7 dead-code).

## 5. Credential & secret handling (CURRENT CODE REALITY)
- Payment/integration credentials encrypted at rest (`orders.encryption` Fernet, key
  `PAYMENT_CREDENTIAL_KEY`; missing in prod → fail-closed startup).
- Central SMS/platform creds on `portal.PlatformConfiguration` (encrypted); legacy `ShopSettings`
  SMS credential fields are POTENTIALLY_DEAD (ignored except `SMSRASTI` selection).
- Audit log redacts known-sensitive keys at write time and omits IP/UA (ADR-36); OTP codes hashed.

## 6. Public / unauthenticated endpoints (attack surface)
- Public storefront (`/`, product/collection pages, `pages/`), cart/checkout, customer account.
- `billing/webhook/<provider>/` (csrf-exempt, signature-verified, always 200).
- `checkout/gateway/callback/<attempt_id>` (public; server-to-server verify; no client trust).
- `checkout/payment-callback/<status>` (SIMULATION only; `status` is a client-controlled path
  segment → **Http404 in production** via `PAYMENTS_SIMULATION_ENABLED`).
- `sms/` device poll/ack (device-token authenticated).
- SEO `sitemap.xml`/`robots.txt` (tenant-safe, host-scoped).

## 7. Trust principles enforced in code (CURRENT CODE REALITY)
- Browser return is **never** payment proof (both orders and billing); only server-side verify /
  signed webhook confirms.
- DNS ownership is never self-asserted (real DNS/TLS checks).
- Amount/currency validated against the server-side invoice/order, never the browser.
- Host resolution is fail-closed.

## 8. Known security-relevant risks (see KNOWN_ARCHITECTURE_RISKS.md)
- H1 unguarded `Order.payment_status` (financial-integrity risk surface).
- H2 content mutation authority in the view layer (no service boundary).
- M15 `is_staff` overloading (authorization footgun).
