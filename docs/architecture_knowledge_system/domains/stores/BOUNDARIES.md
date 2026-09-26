# stores — Boundaries

```
domain_id: D1
code_baseline: 5883a140
```

## Owns
- The tenant entity `Store` and its lifecycle; `StoreDomain` (hostnames + verification/routing/TLS);
  `StoreMembership` (roles + status); `StoreOwnershipTransfer`; `StoreIntegrationConnection`
  (non-payment integrations: eNamad/Torob/GA/GTM/pixel).
- The **authoritative Host→Store resolution** (`resolution.py`) and the **authorization matrix**
  (`authorization.py`, role→permission).
- Middleware: `StoreResolutionMiddleware`, `StorefrontCanonicalRedirectMiddleware`.
- Django-admin superuser lock (`admin_permissions.py`, ADR-8).

## Does NOT own
- **Owner/staff identity** — `portal` owns `OwnerProfile`/auth; `stores` links Users to Stores via
  `StoreMembership` but does not own the User/identity.
- **ShopSettings** — `core` owns it (stores deliberately does NOT import core — M13 cycle-avoidance).
- **Subscription/billing state** — `subscriptions`/`billing`. `publication_service` *reads*
  subscription entitlement (local import) but does not own it.
- **Payment gateway config** — `orders`. (stores reuses `orders.encryption` for integration creds.)
- **`catalog.Vendor`** — a separate "seller-ish" entity; coexistence is ambiguous (A1/DR-7).

## Cross-domain relationships
- **In:** `dashboard` calls `membership_service` (incl. `transfer_ownership`) + `integration_service`;
  every request calls resolution via middleware.
- **Out:** `provisioning_service` (portal) creates Store/Membership/Domain; `stores` services call
  `notifications.notify_security_event` and `portal.owner_auth_service` (ownership transfer);
  `publication_service` reads `subscriptions` entitlement.

## Deliberate cycle-avoidance (M13)
`stores` defines `StoresTimestampedModel` instead of importing `core.TimeStampedModel`, anticipating
a future `core.ShopSettings → stores.Store` FK that would make `core → stores`.
