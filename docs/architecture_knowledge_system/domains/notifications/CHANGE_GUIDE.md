# notifications — Change Guide

```
domain_id: D13
code_baseline: 5883a140
```

## Recipe: Change notification delivery
- **READ FIRST:** [SERVICES](SERVICES.md), `notification_service`.
- **CANONICAL OWNER:** `notification_service`.
- **INVARIANTS:** `enqueue` never sends; `deliver_pending` is the only sender; failures → FAILED
  (retried), never lost; SMS goes through `sms.send_raw_sms` (credit gate) or platform provider.
- **DEPENDENT DOMAINS:** `stores` (enqueue callers), `sms`/`portal`/email (delivery).
- **TESTS:** `apps/notifications/tests`.
- **REGRESSION RISK:** bypassing `send_raw_sms` for direct `send_platform_sms` would skip the credit
  gate (that's why `send_raw_sms` exists).

## Recipe: Add a notification channel
- **LIKELY CODE:** `NotificationOutbox.channel` choices; `_deliver_one` branch; delivery transport.
- **INVARIANTS:** keep the enqueue/deliver split; mark FAILED on error.

## Recipe: Add a new enqueue caller
- **CANONICAL:** call `notification_service.enqueue` / `notify_security_event` from the owning
  domain's service (as `stores` services do). Do not create + send inline.

## No open DR
notifications has no DR-1…DR-8 item. Readiness was MISSING only because no doc existed; this pack
resolves that.
