# notifications — Services

```
domain_id: D13
code_baseline: 5883a140
source: apps/notifications/services/notification_service.py (single service)
```

| Function | Responsibility |
|---|---|
| `enqueue(...)` | creates a `NotificationOutbox` row (PENDING) — **never sends** |
| `notify_security_event(...)` | no-opt-out security notification — enqueues IN_APP + SMS |
| `_deliver_one(item)` | IN_APP = no-op; SMS → `sms.send_raw_sms` (store) or `portal.owner_sms_service.send_platform_sms` + `record_platform_attempt` (store null); EMAIL → Django `send_mail` |
| `deliver_pending(limit=200)` | **the only sender**; iterates PENDING; increments attempts; marks SENT/FAILED (FAILED on error so nothing is lost) |

## Discipline
- **enqueue never sends.** Delivery is deferred to `deliver_pending`, driven by the
  `process_notification_outbox` command — a persistent-queue design.
- On failure, the item is marked FAILED (retried later) rather than lost.
- SMS delivery goes through `sms.send_raw_sms` (which funnels through the credit gate) or the
  platform provider — never a bypass.
