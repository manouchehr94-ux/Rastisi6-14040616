# stores — Dependencies

```
domain_id: D1
code_baseline: 5883a140
known_risks: M13
```

## stores depends ON
| Target | Type | What |
|---|---|---|
| `subscriptions` | reads (local import) | `publication_service` reads entitlement/access state |
| `notifications` | calls | `notify_security_event` (deletion/handle/ownership) |
| `portal` | calls | `ownership_transfer_service` → `owner_auth_service.get_or_create_owner_by_phone` |
| `orders` | imports | `orders.encryption` for `StoreIntegrationConnection` credentials |
| `core` | NOT imported (M13) | deliberately avoided; `stores` has its own timestamp base |

## Depends ON stores (everyone)
Every request (middleware → resolution); `dashboard` (membership/integration/resolution/authz);
`portal` (provisioning); `catalog`/`orders`/`content`/`billing`/`subscriptions`/`core` all FK `Store`.

## Cycle-avoidance (M13, VERIFIED)
- `stores` must not import `core` (a future `core.ShopSettings → stores.Store` FK is planned).
- `publication_service` imports `subscriptions` **locally** (inside functions).
- `resolution.py` documents an AKHLAGHI_SLUG duplication of a migration constant (managed).

## Highest structural centrality
`stores.Store` is the universal FK root; changes to Store identity/resolution ripple everywhere.
