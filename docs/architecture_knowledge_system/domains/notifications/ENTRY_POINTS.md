# notifications — Entry Points

```
domain_id: D13
code_baseline: 5883a140
```

## Management command (the only sender)
- `process_notification_outbox` → `notification_service.deliver_pending`. This is the **only**
  place notifications are actually delivered.

## Service entry (enqueue)
- `notification_service.enqueue` / `notify_security_event` — called by `stores` services
  (`deletion_service`, `handle_service`, `ownership_transfer_service`).

## No HTTP / no signals
notifications has no `urls.py`, no views, and no signals. It is a persistent outbox delivered by a
scheduled command.
