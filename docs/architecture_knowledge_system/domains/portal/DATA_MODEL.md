# portal — Data Model

```
domain_id: D2
code_baseline: 5883a140
source: apps/portal/models.py (7 models)
```

| Model | Key fields | Notes |
|---|---|---|
| **OwnerProfile** | OneToOne User; `phone` unique/nullable | portal-only identity extension (ADR-93/102), separate from `customers.Customer` |
| **OwnerOtpChallenge** | `code_hash` (never plaintext); `purpose` (register/login/step_up); `attempt_count`; `expires_at`; `consumed_at`; `is_usable` | 6-digit, 120s TTL, 5 verify attempts, single-use |
| **AdminHandoffTicket** | single-use, short-lived; `issued_by_platform_admin` | bridges portal-host auth → Store admin host (support login, ADR-98) |
| **PlatformConfiguration** | pk forced to 1 in `save()` | **TRUE platform singleton**: trial defaults, `deletion_retention_days`, `step_up_actions` (allowlisted), central SMS backend + encrypted creds, platform Zibal creds, maintenance_mode, registration flag, enamad |
| **PlatformAuditLogEntry** | platform-level audit | not store-owned; used for purge/config/plan changes |
| **PlatformInternalNote** | CheckConstraint: exactly one of store/about_user | — |
| **ContactMessage** | marketing contact form | — |

## Key facts
- `PlatformConfiguration` is the platform-global config (contrast `core.ShopSettings` which is
  per-Store). It holds the central SMS creds that `sms_service` uses (not ShopSettings' legacy fields).
- Owner identity is `auth.User` + `OwnerProfile`; shared with customer identity by `username == phone`.
