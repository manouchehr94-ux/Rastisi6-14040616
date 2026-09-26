# sms — Testing

```
domain_id: D12
code_baseline: 5883a140
source: apps/sms/tests/
```

| Behavior | Where |
|---|---|
| `send_event_sms` / template rendering / credit + overdraft | `apps/sms/tests/*` |
| Device gateway poll/ack | `apps/sms/tests/*` (gateway) |
| SMS admin views | `apps/dashboard/tests/test_sms_admin_views.py` |
| Order-status → SMS on_commit | `apps/orders/tests/test_order_service.py` |
| Payment → SMS | `apps/orders/tests/test_payment_service.py` (PAYMENT_SUCCESS/FAILED — LIVE) |

## Coverage posture
Send funnel (credit gate/overdraft) + device poll/ack are tested. See canonical
[`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
