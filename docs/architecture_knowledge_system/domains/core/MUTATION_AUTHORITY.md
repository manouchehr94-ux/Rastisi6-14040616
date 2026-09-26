# core — Mutation Authority

```
domain_id: D14
code_baseline: 5883a140
open_decisions: DR-3
known_risks: M5
```

| Entity | Canonical writer | Other / cross-domain |
|---|---|---|
| **`ShopSettings`** | `ShopSettings.provision_for` (create; via portal provisioning) | **CROSS-DOMAIN/DIRECT:** `dashboard.views.settings_*` (`shop.save()` — ~4308-4458); `sms.sms_service.regenerate_smsrasti_device_token` (writes `smsrasti_device_token`); portal onboarding (INFERRED) |
| `AuditLogEntry` | `audit_service.record_audit_event` (idempotent, redacting) | called by services across domains |
| `ExportJob` | `export_service.run_export` | — |
| `ImportJob` (+RowResult) | `dashboard.import_service` (CROSS-DOMAIN — import lives in dashboard, M14) | — |

## ⚠️ ShopSettings write authority is spread (M5 / DR-3)
`ShopSettings` is **owned by core** but its primary runtime writers are in **other apps**:
`dashboard.views` (settings pages, direct `.save()`) and `sms_service` (device token). There is no
core `settings_service` write layer. Routing these through an owning-domain service is **DR-3
(OPEN)**.

## Legacy dead data (D4)
The `ShopSettings` legacy SMS credential fields (`sms_backend` non-SMSRASTI paths, `melipayamak_*`,
`kavenegar_api_key`) are POTENTIALLY_DEAD — `sms_service` reads `sms_backend` only for the `SMSRASTI`
selection; real creds come from `portal.PlatformConfiguration`.

## No signals
Audit + provisioning are explicit service calls.
