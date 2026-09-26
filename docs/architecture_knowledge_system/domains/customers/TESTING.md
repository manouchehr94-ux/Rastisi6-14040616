# customers — Testing

```
domain_id: D3
code_baseline: 5883a140
```

| Behavior | Test file |
|---|---|
| Auth service (signup/guest/authenticate/merge_guest_cart) | `apps/customers/tests/test_auth_service.py` |
| Auth views (login/signup/OTP) | `apps/customers/tests/test_auth_views.py` |
| CRM / segments (in dashboard) | `apps/dashboard/tests/` (customer CRM / customer_views / segment) |

## Coverage posture
Customer auth + guest-cart merge are tested in customers; CRM/segment behavior is tested through
dashboard (since those services live in dashboard). See canonical
[`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
