# customers — Services

```
domain_id: D3
code_baseline: 5883a140
source: apps/customers/services/auth_service.py (single service file)
```

## `auth_service` (the domain's only service)
| Function | Responsibility |
|---|---|
| `signup` | create customer account (username=phone); requires store for WELCOME SMS |
| `create_account_for_guest` | random-password account for checkout auto-account |
| `authenticate_customer` / `authenticate_customer_by_identifier` | email or phone; enumeration-safe |
| `merge_guest_cart` | merge session-key guest cart → user cart (select_for_update membership fence, CAT-002); quantity merge then delete guest cart (**cross-domain write into `cart`**) |

Side effect: WELCOME SMS on `transaction.on_commit` (via `sms.send_event_sms`).

## CRM operations live in `dashboard` (not here)
Profile stats refresh, notes, tags, and segments are handled by `dashboard.services`:
`customer_crm_service` (profile get/create, `refresh_customer_profile_stats` — ADR-50 explicit, no
signal; notes/tags CRUD; internal status) and `segment_service` (allowlisted rule engine,
evaluate/preview/refresh membership). These write `customers` models cross-domain.

## No signals
`CustomerProfile` stats are refreshed by an explicit service call (ADR-50), never a signal.
