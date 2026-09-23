# sms — State Machines

```
domain_id: D12
code_baseline: 5883a140
```

## SmsOutboxItem.status (SmsRasti Android device queue)
```
pending → sending → {sent, failed}
```
- **Two-phase device delivery:** `sms/poll` claims one PENDING (or a stale SENDING) item →
  SENDING (`select_for_update(skip_locked)`, RECLAIM_AFTER_SECONDS=120). `sms/ack` → SENT/FAILED.
  **Poll never marks sent** — only ack does.

## SmsLog.status
```
pending → {sent, failed}
```
Written by `_dispatch` (pending on create; sent/failed on backend result). On failure, reserved
credits are refunded.

## Backend "success" semantics (important)
- Real providers (Melipayamak/Kavenegar): success = provider accepted.
- SmsRasti: success = **"queued"** (enqueued to the device), not delivered — the device delivers
  and acks later.
- Console (dev): logs (never message text/OTP); never a fake production success.
- Unavailable: never fakes success.

## OtpCode
Hashed, single-use, purpose-scoped (login/guest-checkout). OTP is **not retryable** via
`retry_failed_log`.
