# sms — Boundaries

```
domain_id: D12
code_baseline: 5883a140
```

## Owns
SMS templates/events (`SmsTemplate`, `events.py`), credit accounting (`SmsBalance`,
`SmsCreditAdjustment`, `SmsBillingPolicy`, `SmsPackage`+Purchase), the send pipeline
(`sms_service`, `backends.py`), the SmsRasti device queue (`SmsOutboxItem`, `gateway_views`), and
OTP codes (`OtpCode`).

## Does NOT own
- **Central platform SMS creds** — `portal.PlatformConfiguration` (sms reads them via
  `owner_sms_service`). ShopSettings' legacy SMS creds are POTENTIALLY_DEAD (ignored except SMSRASTI
  selection).
- **When to send** — orders/customers/notifications/portal decide; sms only sends.

## Cross-domain relationships
- **In (triggers sends):** orders (on_commit), customers (on_commit), notifications
  (`deliver_pending`), portal (OTP).
- **Out:** reads `core.ShopSettings.sms_backend` (for SMSRASTI selection) + writes
  `ShopSettings.smsrasti_device_token` (regenerate); uses `portal.owner_sms_service` for the platform
  path; external providers.

## Send-surface note
There are several public send functions (`send_event_sms`, `send_raw_sms`, `send_test_sms`, retries)
plus the platform `owner_sms_service` — a wide surface, but all Store sends funnel through
`_dispatch` (credit gate). `send_raw_sms` exists specifically to prevent a bypass.
