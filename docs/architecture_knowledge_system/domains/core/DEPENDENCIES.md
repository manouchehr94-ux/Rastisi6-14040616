# core — Dependencies

```
domain_id: D14
code_baseline: 5883a140
known_risks: M13, M14
```

## core depends ON
| Target | Type | What |
|---|---|---|
| `subscriptions` | reads | `export_service` enforces export budget (entitlement) |
| `stores` | NOT imported (M13) | deliberately avoided (future core→stores FK planned) |

## Depends ON core (widely)
| Source | Type | What |
|---|---|---|
| all apps | uses | `TimeStampedModel` base; `audit_service` |
| `dashboard` | writes + calls | direct `ShopSettings.save()`; `export_service`; audit |
| `sms` | writes | `ShopSettings.smsrasti_device_token` |
| `portal.provisioning_service` | calls | `ShopSettings.provision_for` |
| `portal.session_service` | re-exports | `core.session_service.apply_remember_me` |

## Notes
- **M13:** core does not import stores; the future FK direction is `core → stores`.
- **M14:** export lives here, import in dashboard — asymmetric placement of symmetric features.
