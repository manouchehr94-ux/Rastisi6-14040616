# portal — Testing

```
domain_id: D2
code_baseline: 5883a140
source: apps/portal/tests/
```

| Behavior | Test file |
|---|---|
| Provisioning / store-create / onboarding | `test_provisioning.py`, `test_store_create_view.py`, `test_onboarding.py`, `test_onboarding_authorization.py` |
| Owner auth / OTP / unified login | `test_owner_auth.py`, `test_owner_otp.py`, `test_unified_login.py` |
| Step-up (billing) | `test_step_up_billing.py` |
| Host routing | `test_platform_host_routing.py` |
| Platform admin | `test_platform_admin*.py` |
| Central admin login / handoff | `test_central_admin_login.py`, `test_handoff.py`/`test_handoff1.py` |
| Custom domains / handle claim (views) | `test_custom_domain_views.py`, `test_claim_handle_views.py` |
| Ownership transfer (views) | `test_ownership_transfer_views.py`, `test_my_stores.py` |

See canonical [`../../canonical/TESTING_MAP.md`](../../canonical/TESTING_MAP.md).
