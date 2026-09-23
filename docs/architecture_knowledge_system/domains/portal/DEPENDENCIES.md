# portal — Dependencies

```
domain_id: D2
code_baseline: 5883a140
```

## portal depends ON
| Target | Type | What |
|---|---|---|
| `stores` | writes | provisioning creates Store/Membership/Domain; platform admin drives suspend/activate |
| `core` | writes | provisioning `ShopSettings.provision_for` |
| `catalog` | writes | provisioning default Warehouse + optional industry template |
| `subscriptions` | writes | provisioning `provision_default_subscription`; platform admin change-plan |
| `billing` | calls | portal checkout → billing services |
| `sms` | external-call | owner_sms_service reuses sms.backends provider classes |
| `stores.authorization` | reads | portal decorators delegate permission checks |

## Depends ON portal
| Source | Type | What |
|---|---|---|
| every request | routes-to | `PlatformHostRoutingMiddleware` selects urlconf |
| `stores.ownership_transfer_service` | calls | `owner_auth_service.get_or_create_owner_by_phone` |
| `sms.sms_service` | reads/calls | central creds via `PlatformConfiguration`; OTP via owner_sms_service |
| `dashboard.staff_required` | calls | `handoff_service.build_admin_return_token` |

## Note
portal is the widest cross-domain **writer** (provisioning). It sits above stores/core/catalog/
subscriptions/billing in the call graph for platform operations.
