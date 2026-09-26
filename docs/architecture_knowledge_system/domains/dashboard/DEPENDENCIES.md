# dashboard — Dependencies

```
domain_id: D11
code_baseline: 5883a140
known_risks: H2, M5, M14
```

## dashboard depends ON (fan-out — the highest in the system)
| Target | Type | What |
|---|---|---|
| `catalog` | calls + writes | services + direct Product/Category writes |
| `orders` | calls + writes | order_service (status), refund/return; direct shipping/tax/gateway-config writes |
| `content` | writes (DIRECT — H2) | all content CRUD |
| `core` | writes + calls | direct `ShopSettings.save()`; export_service; audit_service |
| `stores` | calls | membership_service (incl. transfer_ownership), integration_service, resolution/authz |
| `subscriptions` | reads | entitlement/enforcement (banner, seat gate) |
| `sms` | calls | sms_service (test/retry), balance |
| `storefront_builder` | routes-to + calls | registers builder routes |
| `customers` | calls + writes | CRM services + some direct segment writes |

## Depends ON dashboard
Merchant admin host requests only. No other domain imports dashboard (it is a leaf controller).

## Notes
- **M14** — `import_service` is in dashboard while `export_service` is in core (asymmetric).
- dashboard is a leaf: it is the top of the call graph for merchant-admin operations; nothing calls
  *into* dashboard services from other domains.
