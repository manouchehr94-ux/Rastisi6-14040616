# dashboard — Entry Points

```
domain_id: D11
code_baseline: 5883a140
```

Routes at `/admin-portal/` (`shop_core/urls.py` includes `apps.dashboard.urls`, `app_name="dashboard"`).
All behind `staff_required` (+ `permission_required` per view).

## Route groups (`apps/dashboard/urls.py`, ~503 lines)
- **Auth/shell:** `login/`, `handoff/<token>/`, `exit-support-mode/`, `""` (home), `sales-chart/`.
- **Catalog:** `products/*`, `attributes/*`, `brands/*`, `collections/*`, `categories/*`(+schema).
- **Commerce:** `orders/*`, `invoices/*`, `payments/*`, `customers/*`(+tags/segments), `reports/*`,
  `orders/<code>/refund`, `returns/*`.
- **Settings:** `settings/` + `shop-info/`, `industry/*`, `finance/`, `gift-wrap/`, `appearance/`,
  `gateways/<pk>/toggle`, `gateway-config/<code>/save|toggle`, `shipping/*`, `tax/*`, `sms/*`,
  `integrations/<code>/connect|disconnect|test`.
- **Content:** `pages/*`, `homepage/hero/*`, `homepage/banners/*`, `social-links/*`,
  `menus/*`+`menu-items/*`, `footer/*`.
- **Storefront-builder delegation (~60 routes):** wired directly to
  `apps.storefront_builder.views` (R3), `r4_views` (R4), `media_views`.
- **Ops:** `staff/*` (incl. `staff/<pk>/transfer-ownership/`), `inventory/*`, `coupons/*`,
  `audit-log/*`, `exports/*`, `imports/*`, `warehouses/*`, `reservations/*`, `transfers/*`,
  `subscription/*`, `billing/*`.

## Decorators (`decorators.py`)
- `staff_required` — resolve admin store or 404; unauthenticated → central login handoff; require
  ACTIVE StoreMembership; **does NOT check `is_staff`** (M15). Caches `request.store` +
  `request.store_membership`.
- `permission_required(*perms)` — OR-semantics over `membership_has_permission`; renders 403.

## Middleware
`AdminEmbedFrameOptionsMiddleware` — SAMEORIGIN only for authenticated `?embed=1` dashboard views
(storefront-builder embedding); global default stays DENY.

## Management commands
`cleanup_import_files`, `refresh_customer_segments`.

## Signals / async
None.
