# notifications — Mutation Authority

```
domain_id: D13
code_baseline: 5883a140
```

| Entity | Canonical writer |
|---|---|
| `NotificationOutbox` (create) | `notification_service.enqueue` / `notify_security_event` |
| `NotificationOutbox` (status/attempts) | `notification_service.deliver_pending` (the only sender) |

## Callers (enqueue) — VERIFIED
- `stores.deletion_service` (store deletion request)
- `stores.handle_service` (handle claim/rename)
- `stores.ownership_transfer_service` (ownership transfer events)

(Phase 1 initially could not locate callers; Phase 2 located them in `stores` services.)

## No signals
Enqueue + delivery are explicit; there is no `@receiver`.
