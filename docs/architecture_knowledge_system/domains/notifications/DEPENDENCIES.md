# notifications — Dependencies

```
domain_id: D13
code_baseline: 5883a140
```

## notifications depends ON
| Target | Type | What |
|---|---|---|
| `sms` | calls | `send_raw_sms` (store SMS channel) |
| `portal` | calls | `owner_sms_service.send_platform_sms` + `record_platform_attempt` (store null) |
| Django email | external | `send_mail` (EMAIL channel) |
| `core` | uses | TimeStampedModel |

## Depends ON notifications
| Source | Type | What |
|---|---|---|
| `stores` services | calls | `enqueue` / `notify_security_event` (deletion/handle/ownership) |
| cron | calls | `process_notification_outbox` → `deliver_pending` |

## Note
notifications is a thin orchestration layer over `sms`/`portal`/email. It owns the persistence +
retry semantics, not the transport.
