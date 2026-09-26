# customers — Boundaries

```
domain_id: D3
code_baseline: 5883a140
```

## Owns
The global shopper account (`Customer`), the per-Store CRM projection (`CustomerProfile`),
tags/notes, segments (+rules/membership), addresses, wishlist, and customer authentication
(signup/guest/login + guest→user cart merge).

## Does NOT own
- **Owner/staff identity** — `portal` (though they share `auth.User` via `username == phone`).
- **Orders** — `orders` (CustomerProfile stats are computed *from* the Store's Orders).
- **The cart** — `cart` (customers *merges* the guest cart into the user cart, cross-domain).
- **CRM write operations' home** — those services live in `dashboard`, not customers.

## Cross-domain relationships
- **In:** `dashboard.customer_crm_service`/`segment_service` write CustomerProfile/tags/notes/segments;
  `orders` provides the data for profile stats; `portal.owner_auth_service` shares the User.
- **Out:** `auth_service.merge_guest_cart` writes `cart`; WELCOME SMS via `sms`.

## Identity model (ADR-6/50/93/102)
`Customer` is global (no store FK); a person's owner + customer identity share one `auth.User`
keyed by phone. ADR-6 recorded the direction; ADR-102 finalized shared phone identity.
