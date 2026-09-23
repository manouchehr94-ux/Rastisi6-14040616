# sms — Services

```
domain_id: D12
code_baseline: 5883a140
source: apps/sms/services/ (5 files)
```

## `sms_service` — the send core
- `get_backend(store)` → `SmsRastiBackend` if `ShopSettings.sms_backend == SMSRASTI`; else
  `portal.owner_sms_service.get_platform_sms_backend()`. (ShopSettings melipayamak/kavenegar creds
  are legacy/ignored; real creds come from `portal.PlatformConfiguration`.)
- **`_dispatch`** — creates `SmsLog` PENDING; reserves credits atomically (OTP overdraft allowed);
  for OTP routes through `portal.owner_sms_service.send_platform_otp` (central provider); else uses
  the resolved backend (Pattern if melipayamak body_id set); **refunds credits on failure**.
- Public: `send_event_sms(event, phone, ctx, *, store)` (renders active SmsTemplate; short-circuits
  if `!shop.sms_enabled`; OTP injects expire_minutes), `send_raw_sms` (notifications, no template),
  `send_test_sms`, `retry_failed_log` (OTP not retryable), `retry_smsrasti_outbox_item`,
  `regenerate_smsrasti_device_token`.

## backends.py
ABC `SmsBackend.send()`. Impls: `UnavailableBackend` (never fakes success), `ConsoleBackend` (dev —
never logs message text/OTP), `MelipayamakBackend` (text + Pattern/BodyId), `KavenegarBackend`
(text + VerifyLookup; redacts api_key), `SmsRastiBackend` (Store-scoped — enqueues `SmsOutboxItem`,
success="queued" not "delivered").

## Other services
`billing_policy_service` (credit reservation/pricing), `balance_service` (SmsBalance),
`sms_admin_service` is in dashboard (read-only).

## Key discipline
- **Single Store-SMS funnel** (`_dispatch`) → credit gate + logging. `send_raw_sms` exists so
  notifications don't bypass the credit gate.
- **OTP structurally diverges** to the central platform provider inside `_dispatch`.
- Console backend never fakes delivery; SmsRasti success means "queued" (device delivers later).
