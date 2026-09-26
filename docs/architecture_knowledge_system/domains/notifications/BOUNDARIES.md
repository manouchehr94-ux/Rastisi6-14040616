# notifications — Boundaries

```
domain_id: D13
code_baseline: 5883a140
```

## Owns
The persistent notification outbox (`NotificationOutbox`) and its delivery service
(`notification_service`). One model, one service, one delivery command.

## Does NOT own
- **The actual send transport** — SMS via `sms`/`portal.owner_sms_service`; EMAIL via Django mail.
  notifications enqueues + orchestrates delivery; it does not implement SMS backends.
- **When to notify** — callers (`stores` services) decide; notifications persists + delivers.

## Cross-domain relationships
- **In (enqueue):** `stores.deletion_service`, `stores.handle_service`,
  `stores.ownership_transfer_service` call `notify_security_event`/`enqueue`.
- **Out (deliver):** `sms.send_raw_sms` (store SMS), `portal.owner_sms_service.send_platform_sms`
  (platform SMS when store is null), Django `send_mail` (EMAIL). IN_APP is a no-op.

## Design principle
`enqueue` never sends; `deliver_pending` (management command) is the only sender; failures mark
FAILED (retried) so nothing is lost.
