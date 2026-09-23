# portal — Boundaries

```
domain_id: D2
code_baseline: 5883a140
```

## Owns
Platform-global config (`PlatformConfiguration` singleton), owner/staff identity + auth
(email/password + phone OTP + step-up), Host→URLconf routing (`PlatformHostRoutingMiddleware`),
store **provisioning orchestration**, the platform-admin console, platform audit/notes/contact,
and the central platform SMS path (`owner_sms_service`).

## Does NOT own
- **Store data** — `stores` (portal *creates* stores via provisioning but does not own the entity).
- **Storefront customer identity** — `customers`. (Owner and customer share `auth.User` by
  `username == phone`, ADR-102, but the profiles are separate.)
- **Billing/subscriptions** — portal checkout *calls* those domains.
- **ShopSettings** — `core` (provisioning calls `ShopSettings.provision_for`).

## Cross-domain relationships
- **Out:** provisioning writes stores/core/catalog/subscriptions; platform admin drives store/
  subscription/billing operations; owner_otp uses SMS.
- **In:** every request hits `PlatformHostRoutingMiddleware`; `stores.ownership_transfer_service`
  calls `owner_auth_service`.

## Two hosts, one app
The owner portal and the platform admin are **disjoint** host sets and URLconfs; the platform-admin
host must never also resolve the owner portal (deliberate separation).
