# sms — Mutation Authority

```
domain_id: D12
code_baseline: 5883a140
```

| Entity | Canonical writer | Other |
|---|---|---|
| `SmsLog`, credit reservation/refund | `sms_service._dispatch` (single funnel) | — |
| `SmsOutboxItem` | `SmsRastiBackend` (enqueue); `gateway_views` (poll → SENDING, ack → SENT/FAILED) | — |
| `SmsBalance` / `SmsCreditAdjustment` | `billing_policy_service` / `balance_service` (via _dispatch) | Platform Admin (package purchase completion) |
| `OtpCode` | sms OTP path + `owner_otp_service` equivalents | — |
| `core.ShopSettings.smsrasti_device_token` | `sms_service.regenerate_smsrasti_device_token` (CROSS-DOMAIN write into core) | — |

## Send-path map (who triggers SMS)
1. **`send_event_sms`** — called from `orders.order_service` (ORDER_PLACED + status events, on_commit),
   `orders.payment_service`/`gateway_payment_service` (**PAYMENT_SUCCESS/FAILED**, on_commit — LIVE),
   `customers.auth_service` (WELCOME, on_commit).
2. **`send_raw_sms`** — from `notifications.notification_service._deliver_one` (SMS channel).
3. **Platform path** — `portal.owner_sms_service.send_platform_otp` for owner/store OTP (invoked
   inside `_dispatch` and from notification delivery when store_id is null).

## Correction (Phase 2)
`PAYMENT_SUCCESS`/`PAYMENT_FAILED` events are **LIVE** (wired in orders payment services). An earlier
pass flagged them as possibly dead; direct grep disproved that.

## No signals
Sends are triggered by explicit calls + `transaction.on_commit`; no `@receiver`.
