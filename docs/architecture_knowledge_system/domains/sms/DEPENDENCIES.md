# sms — Dependencies

```
domain_id: D12
code_baseline: 5883a140
```

## sms depends ON
| Target | Type | What |
|---|---|---|
| `portal` | reads/calls | `owner_sms_service` (platform provider) + `PlatformConfiguration` central creds |
| `core` | reads/writes | `ShopSettings.sms_backend` (SMSRASTI selection); writes `smsrasti_device_token` |
| external | external-call | Melipayamak, Kavenegar, SmsRasti device |

## Depends ON sms
| Source | Type | What |
|---|---|---|
| `orders` | calls (on_commit) | ORDER_* / PAYMENT_* events |
| `customers` | calls (on_commit) | WELCOME |
| `notifications` | calls | `send_raw_sms` (SMS channel) |
| `portal` | calls | owner/store OTP (via owner_sms_service) |
| `dashboard` | calls | test-send / retry / regenerate-token |

## Note
The platform OTP path lives in `portal.owner_sms_service` but **reuses `sms.backends` provider
classes** (never a duplicate backend implementation). ShopSettings legacy SMS creds are dead except
the SMSRASTI backend selection.
