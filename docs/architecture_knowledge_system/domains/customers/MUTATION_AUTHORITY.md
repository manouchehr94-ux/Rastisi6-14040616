# customers — Mutation Authority

```
domain_id: D3
code_baseline: 5883a140
```

| Entity | Canonical writer | Other / cross-domain |
|---|---|---|
| `Customer` / auth User (customer) | `auth_service` (signup/guest) | `portal.owner_auth_service.get_or_create_owner_by_phone` (shared identity — creates/reuses the same User) |
| `CustomerProfile` (+ stats) | `dashboard.customer_crm_service` (CROSS-DOMAIN; explicit refresh, ADR-50) | — |
| `CustomerTag` / `CustomerNote` | `dashboard.customer_crm_service` (CROSS-DOMAIN) | — |
| `CustomerSegment*` | `dashboard.segment_service` (evaluate/refresh) + `dashboard.views` (direct create/save some segment rows) | — |
| `Address` / `Wishlist` | customer account views | — |
| `cart.Cart/CartItem` | `auth_service.merge_guest_cart` (CROSS-DOMAIN into cart) | — |

## Notes
- The **shared identity** model means a `Customer` and an `OwnerProfile` can hang off the **same**
  `auth.User` (username == phone) — a write to the User in either domain affects both.
- CRM writes (profiles/notes/tags/segments) are performed by **`dashboard` services**, not by a
  customers service — a cross-domain write pattern (similar in spirit to H2, though CRM services do
  exist in dashboard, unlike content which has none).

## No signals
Profile stats refresh is explicit (ADR-50).
