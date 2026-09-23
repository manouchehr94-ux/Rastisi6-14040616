# Domain: notifications (D13) — Notification Outbox

```
domain_id: D13
app: apps/notifications
canonical_pack_status: CANONICAL
phase4_prepack_documentation_readiness: MISSING
code_baseline: 5883a140
open_decisions: —
known_risks: —
```

A small, single-model domain: a **persistent multi-channel notification outbox** delivered by a
management command. Documentation readiness was MISSING; this pack is the first documentation.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) ·
[DEPENDENCIES](DEPENDENCIES.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) · [OPEN_DECISIONS](OPEN_DECISIONS.md)

*Not applicable (recorded here, not empty files):* STATE_MACHINES (only NotificationOutbox status
below), CODE_MAP (single service — see below), SECURITY/INVARIANTS/TRANSACTIONS/FLOWS/API_AND_EVENTS/
ARCHITECTURE/TESTING/TROUBLESHOOTING/HISTORICAL_CONTEXT → folded here.

## Everything you need to know
- **Model:** `NotificationOutbox` — channel (IN_APP/SMS/EMAIL), status (PENDING/SENT/FAILED),
  recipient_user/phone/email, store, `is_security`, attempts, metadata. Status:
  `pending → {sent, failed}`.
- **Service:** `notification_service` (`apps/notifications/services/notification_service.py`):
  - `enqueue()` — only creates a row, never sends.
  - `_deliver_one()` — IN_APP = no-op; SMS → `sms.send_raw_sms` (store) or
    `portal.owner_sms_service.send_platform_sms` (+`record_platform_attempt`) when store is null;
    EMAIL → Django `send_mail`.
  - `deliver_pending(limit=200)` — **the only sender**; increments attempts; FAILED on error so
    nothing is lost.
  - `notify_security_event()` — no opt-out; enqueues IN_APP + SMS.
- **Entry point:** management command `process_notification_outbox` → `deliver_pending` (the only
  sender). No urls.py, no views, no signals.
- **Who enqueues:** `stores` services — `deletion_service`, `handle_service`,
  `ownership_transfer_service` (VERIFIED callers; Phase 1 initially couldn't find callers, Phase 2
  located them in `stores`).
- **Mutation authority:** `NotificationOutbox` is written ONLY by `notification_service`
  (enqueue/notify_security_event to create; deliver_pending for status/attempts).
- **Dependencies:** depends on `sms`/`portal` (delivery) + email; depended-on by `stores` (enqueue).
- **Design principle:** enqueue never sends (persistent queue); delivery is a separate command so
  nothing is lost if delivery fails (FAILED, retried).
