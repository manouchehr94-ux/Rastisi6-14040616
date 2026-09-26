# notifications — Data Model

```
domain_id: D13
code_baseline: 5883a140
source: apps/notifications/models.py (1 model)
```

| Model | Key fields / lifecycle | Notes |
|---|---|---|
| **NotificationOutbox** | `channel` (IN_APP/SMS/EMAIL); `status` (PENDING/SENT/FAILED); `recipient_user`/`recipient_phone`/`recipient_email`; `store` (nullable); `is_security`; `attempts`; `metadata` | Persistent queue. Status: `pending → {sent, failed}`; FAILED on delivery error so nothing is lost |

## Notes
- `store` nullable — a null store routes SMS delivery to the platform provider
  (`portal.owner_sms_service`) instead of the store SMS path.
- `is_security` marks security-event notifications (no opt-out).
- `attempts` increments on each delivery attempt.
