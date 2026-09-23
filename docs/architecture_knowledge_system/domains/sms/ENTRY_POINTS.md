# sms — Entry Points

```
domain_id: D12
code_baseline: 5883a140
```

## HTTP (`apps/sms/urls.py`, included at `sms/`) — device gateway
| Path | View | Auth |
|---|---|---|
| `sms/…poll` | `gateway_views.smsrasti_poll` (GET) | `?token` == `ShopSettings.smsrasti_device_token`; `select_for_update(skip_locked)` claims one item |
| `sms/…ack` | `gateway_views.smsrasti_ack` (POST) | device token; marks SENT/FAILED |
Both csrf-exempt, device-token-authenticated.

## Service entry (send)
`send_event_sms` / `send_raw_sms` / `send_test_sms` / retries — called by orders/customers
(on_commit), notifications, dashboard (test/retry), portal (OTP via owner_sms_service).

## Admin (dashboard)
SMS connection, package/purchase, smsrasti regenerate-token, templates, test-send, logs, outbox —
via `dashboard.sms_admin_service` (read) + `sms_service` (send/retry). `SmsPackage`/`SmsBillingPolicy`
managed via Django admin (superuser).

## Signals / async
None. Sends via explicit calls + `transaction.on_commit`. Device delivery is poll/ack (async by device).
