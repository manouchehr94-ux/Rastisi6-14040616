# sms — Change Guide

```
domain_id: D12
code_baseline: 5883a140
```

## Recipe: Change SMS sending
- **READ FIRST:** [SERVICES](SERVICES.md) (`sms_service._dispatch`), [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md).
- **CANONICAL OWNER:** `sms_service._dispatch` (the single Store-SMS funnel).
- **INVARIANTS:** all Store sends funnel through `_dispatch` (credit gate + logging); OTP routes to
  the platform provider; console never fakes delivery; SmsRasti success = "queued".
- **⚠️** callers are `orders`/`customers` (on_commit), `notifications`, `portal`. A change to send
  behavior affects all. `send_raw_sms` must keep going through the credit gate (don't bypass to
  `send_platform_sms`).
- **TESTS:** `apps/sms/tests/*`, `apps/orders/tests/test_order_service.py` (status SMS).

## Recipe: Add / change a backend (provider)
- **READ FIRST:** `backends.py` (ABC `SmsBackend.send`), `get_backend`.
- **INVARIANTS:** never fake success (UnavailableBackend/Console); redact secrets in logs; SmsRasti
  enqueues an `SmsOutboxItem`.
- **⚠️** the platform OTP path (`portal.owner_sms_service`) reuses these backend classes — keep them
  reusable, don't duplicate.

## Recipe: Change credit accounting
- **READ FIRST:** `billing_policy_service`, `SmsBalance`/`SmsCreditAdjustment`/`SmsBillingPolicy`.
- **INVARIANTS:** OTP overdraft allowed (otp_overdraft_limit); refund credits on send failure;
  ledger is immutable (`SmsCreditAdjustment`).

## Recipe: Change the device gateway (SmsRasti poll/ack)
- **READ FIRST:** `gateway_views` (poll/ack), [STATE_MACHINES](STATE_MACHINES.md).
- **INVARIANTS:** poll never marks sent (only ack does); device-token auth;
  `select_for_update(skip_locked)`; RECLAIM_AFTER_SECONDS reclaims stale SENDING.

## Recipe: Add / change an SMS event
- **READ FIRST:** `events.py` (SmsEvent + EVENT_VARIABLES allowlist + DEFAULT_TEMPLATES).
- **INVARIANTS:** variable allowlist per event; `SmsTemplate.ensure_defaults()`.
- **Note:** PAYMENT_SUCCESS/FAILED are LIVE (wired in orders) — don't assume payment events are dead.
