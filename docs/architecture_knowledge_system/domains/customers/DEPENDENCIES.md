# customers — Dependencies

```
domain_id: D3
code_baseline: 5883a140
```

## customers depends ON
| Target | Type | What |
|---|---|---|
| `cart` | writes (cross-domain) | `merge_guest_cart` |
| `sms` | calls (on_commit) | WELCOME |
| `core` | uses | TimeStampedModel |
| `stores` | reads | Store scope for CustomerProfile |

## Depends ON customers
| Source | Type | What |
|---|---|---|
| `orders` | foreign-key | `Order.customer` |
| `dashboard` | writes (cross-domain) | CRM (customer_crm_service, segment_service) |
| `portal.owner_auth_service` | shares | the same `auth.User` (shared identity) |
| storefront | reads | wishlist/auth context processors |

## Note
`Customer` is global (no store FK); the per-Store view (`CustomerProfile`) is scoped and its stats
are recomputed from `orders` data explicitly.
