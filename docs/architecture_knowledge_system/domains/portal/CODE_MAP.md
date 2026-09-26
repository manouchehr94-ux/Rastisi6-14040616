# portal — Code Map

```
domain_id: D2
code_baseline: 5883a140
```

```
apps/portal/
├── models.py                 7 models (OwnerProfile, OwnerOtpChallenge, AdminHandoffTicket,
│                             PlatformConfiguration[pk=1], PlatformAuditLogEntry,
│                             PlatformInternalNote, ContactMessage)
├── urls.py                   owner portal routes (marketing + owner app + billing + domains + transfer)
├── views.py                  owner portal views (+ not_found handler for urls_platform)
├── platform_admin_urls.py    platform-admin routes
├── platform_admin_views.py   platform-admin console (_is_platform_staff gate)
├── middleware.py             PlatformHostRoutingMiddleware
├── decorators.py             owner_required, portal_action(s)_allowed
├── phone.py                  phone normalization
├── context_processors.py     turnstile, platform_enamad_verification
├── services/                 10 files: provisioning_service, owner_auth_service, owner_otp_service,
│                             step_up_service, owner_sms_service, platform_config_service,
│                             handoff_service, turnstile_service, session_service (shim), rate_limit
├── migrations/
└── tests/                    provisioning, owner_auth/otp, unified_login, step_up_billing,
                              platform_host_routing, platform_admin*, handoff, custom_domain_views,
                              claim_handle_views, ownership_transfer_views, my_stores
```

## Where to look
| Concern | File |
|---|---|
| Which surface is this host? | `middleware.py` (PlatformHostRoutingMiddleware) |
| Owner auth / OTP / step-up | `services/owner_auth_service.py`, `owner_otp_service.py`, `step_up_service.py` |
| Store creation | `services/provisioning_service.py` |
| Platform config singleton | `models.py` (PlatformConfiguration) + `services/platform_config_service.py` |
| Platform admin console | `platform_admin_views.py` |
| Central SMS path | `services/owner_sms_service.py` |
