# sms — Data Model

```
domain_id: D12
code_baseline: 5883a140
source: apps/sms/models.py (9 models) + events.py
```

| Model | Key fields / lifecycle | Notes |
|---|---|---|
| **SmsTemplate** | per-event body; melipayamak body_id/vars_order; kavenegar template; `ensure_defaults()` | one per SmsEvent |
| **SmsBillingPolicy** | pk=1 platform singleton: chars_per_credit / price / otp_overdraft_limit | — |
| **SmsLog** | per-attempt history; `status`; `store` nullable | legacy rows deliberately orphaned & hidden |
| **SmsOutboxItem** | SmsRasti Android queue; `status` (pending→sending→sent/failed) | poll claims one; ack marks sent/failed |
| **SmsBalance** | OneToOne Store credits | OTP overdraft allowed |
| **SmsPackage** (+**Purchase**) | platform-owned credit packages | purchase completion only via Platform Admin |
| **SmsCreditAdjustment** | immutable ledger | credit movements |
| **OtpCode** | hashed code; purpose (login/guest-checkout) | never plaintext |

## events.py
`SmsEvent` (12 events incl. PLATFORM_OWNER_OTP, OTP, ORDER_PLACED/PROCESSING/SHIPPED/DELIVERED/
CANCELED, **PAYMENT_SUCCESS/PAYMENT_FAILED**, WELCOME, NOTIFICATION); `EVENT_VARIABLES` allowlist;
`DEFAULT_TEMPLATES`. Single source of truth for event/variable validation.

## Key facts
- Credit accounting: `SmsBalance` (per-Store) + `SmsCreditAdjustment` (ledger) + `SmsBillingPolicy`
  (platform pricing). OTP is allowed to overdraw (otp_overdraft_limit).
- `SmsLog.store` nullable — old rows orphaned and filtered out of dashboards (multi-tenant safety).
