# portal — Mutation Authority

```
domain_id: D2
code_baseline: 5883a140
open_decisions: DR-4
```

| Entity | Canonical writer | Other |
|---|---|---|
| `PlatformConfiguration` | `platform_config_service` / `platform_admin_views` | — |
| `OwnerProfile` / auth User (owner) | `owner_auth_service` (register / get_or_create_by_phone) | `stores.membership_service.add_staff_member` (creates is_staff User — cross-domain) |
| `OwnerOtpChallenge` | `owner_otp_service` | — |
| `AdminHandoffTicket` | `handoff_service` | — |
| `PlatformAuditLogEntry` | `platform_config_service.record_platform_audit_event`; `stores.deletion_service` (purge audit) | — |

## Cross-domain writes performed BY portal
- **`provisioning_service`** writes across **stores + core(ShopSettings) + catalog(Warehouse/
  template) + subscriptions** in one atomic — the widest cross-domain write in the system.
- **platform_admin_views** trigger store suspend/activate/extend-trial/change-plan (via
  `stores`/`subscriptions`/`billing` services), user activate/suspend, domain check/set-primary.

## Ownership transfer (DR-4)
`ownership_transfer_service` (in `stores`) calls `portal.owner_auth_service.get_or_create_owner_by_phone`
to create the new-owner User. portal is thus part of the OTP transfer path (one of the two live
paths — DR-4).

## No signals
All mutations are explicit service calls.
