# customers — Entry Points

```
domain_id: D3
code_baseline: 5883a140
```

## Public HTTP (`apps/customers/urls.py`, included at `account/`)
account, login, signup, otp/request, otp/login, otp/reset, logout, profile, addresses, orders,
wishlist.

## Context processors (`apps/customers/context_processors.py`)
`wishlist_membership`, `auth_forms` — injected into storefront templates.

## Called-into (services)
- `auth_service.merge_guest_cart` — called during login/checkout to merge the guest cart.
- CRM operations are entered via `dashboard` (customer CRM/segment views), not customers routes.

## Signals / async
None (CustomerProfile stats refreshed explicitly — ADR-50). WELCOME SMS via `transaction.on_commit`.
