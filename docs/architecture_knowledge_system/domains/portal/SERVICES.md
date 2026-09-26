# portal — Services

```
domain_id: D2
code_baseline: 5883a140
source: apps/portal/services/ (10 files)
```

| Service | Responsibility | Cross-domain |
|---|---|---|
| **provisioning_service.provision_trial_store** | Full trial store creation in ONE `@atomic`: enforce per-owner store cap → create Store (ACTIVE + unique platform_code) → assert admin-subdomain namespace → ACTIVE OWNER StoreMembership → VERIFIED GENERATED_TRIAL StoreDomain → `ShopSettings.provision_for` → default Warehouse → optional industry template → `provision_default_subscription` (fail-open) → audit | **writes stores + core + catalog + subscriptions** |
| **owner_auth_service** | owner email/password register/login/reset; `authenticate_owner_by_identifier` (email OR phone); **`get_or_create_owner_by_phone`** (shared identity: username==phone unifies owner & customer) | creates auth User + OwnerProfile |
| **owner_otp_service** | `request_otp` (IP + per-phone rate limits, hashed code, 120s TTL, SMS), `verify_otp` (single-use, 5 attempts) | SMS via owner_sms_service |
| **step_up_service** | session-scoped step-up OTP for sensitive actions keyed by (action, target); `is_step_up_required` reads PlatformConfiguration.step_up_actions | — |
| **owner_sms_service** | the platform SMS path (`send_platform_sms`/`send_platform_otp`, `get_platform_sms_backend`) using PlatformConfiguration creds | reuses `sms.backends` provider classes |
| **platform_config_service** | `get_platform_configuration` (cached), `record_platform_audit_event` | — |
| **handoff_service** | `build_admin_return_token`, `issue_support_ticket`, `consume_admin_handoff` (AdminHandoffTicket) | — |
| **turnstile_service** | Cloudflare Turnstile verification | external |
| **session_service** | thin re-export of `core.services.session_service.apply_remember_me` (shim) | — |

## Key discipline
- `provisioning_service` is the single 4-app atomic store-creation path (idempotency is the view's
  job via a session token).
- Owner OTP codes are hashed (make_password), rate-limited, single-use.
- Platform SMS (owner OTP) uses PlatformConfiguration creds, independent of any Store (ADR-93).
