# Domain: sms (D12) — Messaging: SMS

```
domain_id: D12
app: apps/sms
status: CANONICAL
readiness: POOR
code_baseline: 5883a140
open_decisions: —
known_risks: —
```

Owns SMS templates/events, credit accounting, backends (console / Melipayamak / Kavenegar /
SmsRasti Android device gateway), the send pipeline, and OTP codes. Store SMS funnels through a
single dispatch; OTP routes to the platform provider.

## Pack contents
[BOUNDARIES](BOUNDARIES.md) · [DATA_MODEL](DATA_MODEL.md) · [SERVICES](SERVICES.md) ·
[ENTRY_POINTS](ENTRY_POINTS.md) · [STATE_MACHINES](STATE_MACHINES.md) ·
[MUTATION_AUTHORITY](MUTATION_AUTHORITY.md) · [DEPENDENCIES](DEPENDENCIES.md) ·
[TESTING](TESTING.md) · [CHANGE_GUIDE](CHANGE_GUIDE.md) · [CODE_MAP](CODE_MAP.md) ·
[OPEN_DECISIONS](OPEN_DECISIONS.md)

*Folded:* SECURITY/INVARIANTS/TRANSACTIONS/FLOWS/API_AND_EVENTS/ARCHITECTURE/TROUBLESHOOTING/
HISTORICAL_CONTEXT → SERVICES + this README.

## Orientation
- **Owns:** `SmsTemplate`, `SmsBillingPolicy` (pk=1 platform singleton), `SmsLog`, `SmsOutboxItem`
  (device queue), `SmsBalance`, `SmsPackage`(+Purchase), `SmsCreditAdjustment`, `OtpCode`;
  `events.py` (SmsEvent + variable allowlist); `gateway_views.py` (device poll/ack).
- **Canonical send funnel:** `sms_service._dispatch` (create SmsLog, reserve credits, route OTP to
  platform, backend send, refund credits on failure). Public: `send_event_sms`, `send_raw_sms`,
  `send_test_sms`, retries.
- **Backends:** console (dev, never fakes delivery), Melipayamak (Pattern/BodyId), Kavenegar
  (VerifyLookup), SmsRasti (enqueues `SmsOutboxItem` for an Android device gateway; success="queued").
- **Callers:** `orders`/`customers` on_commit; `notifications.deliver_pending`; `portal` OTP.
- **PAYMENT_SUCCESS/FAILED events are LIVE** (wired in orders payment services — Phase 2 corrected
  an earlier "possibly dead" note).
