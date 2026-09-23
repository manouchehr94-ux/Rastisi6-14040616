# portal — Security

```
domain_id: D2
code_baseline: 5883a140
known_risks: M15
```

## Host isolation (VERIFIED)
- `PlatformHostRoutingMiddleware` routes platform-admin hosts and owner-portal hosts to **disjoint**
  URLconfs. The platform-admin host set is deliberately separate from the platform host set — the
  marketing/portal host must never resolve platform admin.

## Owner auth (VERIFIED)
- Phone OTP: `OwnerOtpChallenge` hashes codes (`make_password`), single-use, 120s TTL, 5 verify
  attempts, rate-limited per phone + IP. Generic login errors (enumeration-safe).
- Email/password: `owner_auth_service` (enumeration-safe generic errors).
- Step-up: session-scoped (action, target) OTP, 900s TTL; required actions from
  `PlatformConfiguration.step_up_actions` (allowlisted).
- Shared identity: `username == phone` unifies owner + customer accounts (ADR-102).

## Platform admin auth (VERIFIED)
- `_is_platform_staff` = authenticated AND `is_staff` AND `is_superuser`. Rate-limited, audited login.

## ⚠️ `is_staff` overloading (M15)
Platform admin **requires** `is_staff`+`is_superuser`; but the merchant dashboard `staff_required`
**ignores** `is_staff` (uses StoreMembership); and `stores.membership_service.add_staff_member`
sets `is_staff=True`. Three meanings — a change to `is_staff` semantics affects all three.

## Secrets
- `PlatformConfiguration` holds central SMS + platform Zibal creds (encrypted). `AdminHandoffTicket`
  is single-use/short-lived. `PlatformAuditLogEntry` for platform operations.

## Turnstile
Public account/contact forms protected by Cloudflare Turnstile (`turnstile_service`).
