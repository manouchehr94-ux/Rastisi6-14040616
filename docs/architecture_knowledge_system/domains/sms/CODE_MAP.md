# sms — Code Map

```
domain_id: D12
code_baseline: 5883a140
```

```
apps/sms/
├── models.py               9 models (SmsTemplate, SmsBillingPolicy[pk=1], SmsLog, SmsOutboxItem,
│                           SmsBalance, SmsPackage(+Purchase), SmsCreditAdjustment, OtpCode)
├── events.py               SmsEvent enum + EVENT_VARIABLES allowlist + DEFAULT_TEMPLATES
├── services/               sms_service (_dispatch + public send fns), backends.py (5 backends),
│                           billing_policy_service, balance_service, (+1)
├── gateway_views.py        smsrasti_poll / smsrasti_ack (device gateway)
├── urls.py                 sms/ poll + ack
├── admin.py                mark_completed (package purchase)
├── migrations/
└── tests/

# Platform OTP path (reuses sms.backends): apps/portal/services/owner_sms_service.py
# SMS admin (read-only): apps/dashboard/services/sms_admin_service.py
```

## Where to look
| Concern | File |
|---|---|
| Send funnel | `services/sms_service.py::_dispatch` |
| Backends | `services/backends.py` |
| Events/variables | `events.py` |
| Device gateway | `gateway_views.py` |
| Credits | `services/billing_policy_service.py`, `services/balance_service.py` |
| Platform OTP path | `apps/portal/services/owner_sms_service.py` |
