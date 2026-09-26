# portal — Change Guide

```
domain_id: D2
code_baseline: 5883a140
open_decisions: DR-4
```

## Recipe: Change owner authentication (OTP / password / step-up)
- **READ FIRST:** [SECURITY](SECURITY.md), `owner_otp_service`/`owner_auth_service`/`step_up_service`.
- **CANONICAL OWNER:** those services.
- **INVARIANTS:** OTP hashed, single-use, rate-limited, TTL; enumeration-safe errors; shared identity
  `username == phone` (ADR-102); step-up actions from `PlatformConfiguration.step_up_actions`.
- **⚠️ M15:** do not couple owner auth to `is_staff` (dashboard access uses StoreMembership).
- **TESTS:** `test_owner_otp.py`, `test_owner_auth.py`, `test_unified_login.py`, `test_step_up_billing.py`.
- **REGRESSION RISK:** the shared owner/customer identity — a change can affect customer login too.

## Recipe: Change store provisioning
- **READ FIRST:** `provisioning_service.provision_trial_store` (4-app atomic), canonical Flow 5.
- **⚠️ Cross-domain:** writes stores + core + catalog + subscriptions in ONE transaction. A change
  affects all four. Idempotency is the view's job (session token).
- **INVARIANTS:** per-owner store cap; unique platform_code; admin-subdomain namespace assertion;
  VERIFIED generated_trial domain; fail-open default subscription.
- **TESTS:** `test_provisioning.py`, `test_store_create_view.py`.

## Recipe: Change platform configuration
- **READ FIRST:** `PlatformConfiguration` (pk=1 singleton), `platform_config_service`.
- **INVARIANTS:** pk forced to 1; `step_up_actions` allowlisted; central SMS/Zibal creds encrypted.

## Recipe: Change host routing
- **READ FIRST:** `PlatformHostRoutingMiddleware`, `RASTISI_PLATFORM_HOSTS`/`RASTISI_PLATFORM_ADMIN_HOSTS`.
- **⚠️** platform-admin and portal host sets must stay disjoint. Routing only; never touch request.store.
- **TESTS:** `test_platform_host_routing.py`.

## Recipe: Change ownership transfer (DR-4)
- **⚠️** portal's `ownership_transfer_service` (OTP flow) is one of **two live** transfer paths (the
  other is dashboard-direct `membership_service.transfer_ownership`). Read [`../stores/CHANGE_GUIDE.md`](../stores/CHANGE_GUIDE.md).
- **OPEN DECISION:** DR-4.

## Recipe: Change platform-admin operations
- **READ FIRST:** `platform_admin_views` (gated `_is_platform_staff`).
- **⚠️** these drive stores/subscriptions/billing services — respect those domains' invariants.
