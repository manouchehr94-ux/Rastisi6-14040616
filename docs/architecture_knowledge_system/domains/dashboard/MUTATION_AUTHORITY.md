# dashboard — Mutation Authority (cross-domain writer)

```
domain_id: D11
code_baseline: 5883a140
open_decisions: DR-2, DR-3, DR-4
known_risks: H2, M5
```

dashboard owns no models; this page maps **what dashboard writes in OTHER domains** and by which
pattern. Two patterns coexist.

## Pattern A — via the owning app's SERVICE (proper layering)
| Target | Via |
|---|---|
| `orders.Order.status` | `order_service.change_order_status` (the only order-status path from dashboard) |
| `orders` refunds/returns | `refund_service`, `return_service` |
| `catalog` Product/Attribute/Brand/Collection/Variant/Option/Image/Video/Category-schema/Warehouse/Transfer/Reservation | `catalog.services.*` |
| `cart.Coupon` | `cart.coupon_service` |
| `stores` staff/integrations | `stores.membership_service` (incl. `transfer_ownership`), `stores.integration_service` |
| `core` exports | `core.export_service.run_export` |
| imports | `dashboard.import_service` (writes catalog via catalog services) |
| `sms` | `sms.sms_service` (test/retry), balance |

## Pattern B — DIRECT `.save()`/`.delete()` on OTHER apps' models (H2/M5 — DR-2/DR-3)
| Target | View functions (apps/dashboard/views.py) |
|---|---|
| **`content.*`** (ContentPage/HeroSlide/PromotionalBanner/SocialLink/Menu/MenuItem/FooterSettings/TrustBadge/PaymentLogo/StoryRail) | page/hero/banner/social/menu/footer views (~4705-5610) — **no content service** (H2) |
| **`core.ShopSettings`** | `settings_shop_info`/`settings_finance`/`settings_gift_wrap`/appearance/branding (~4308-4458) |
| **`orders` config** (ShippingZone/Method/RateRule, TaxClass/TaxRate, PaymentGatewayConfig) | `settings_*` (~6866-7281), `settings_gateway_config_save/toggle` (~5726-5784, incl. credential encryption) |
| some **`catalog`** direct writes | `_save_product` (~835), variant/category saves (bulk via catalog_admin_service) |
| **`customers.CustomerSegment`** | direct create/save (~3956-4039), though segment_service handles evaluation |

## Own services (`dashboard/services/`) — read/orchestration
`catalog_admin_service` (bulk product ops via `.update()`), `orders_admin_service` (read-only),
`settings_admin_service` (toggle gateway/shipping is_active), `sms_admin_service` (read-only),
`dashboard_service`/`report_service`/`charts` (read-only stats; store-scoped after the O4 fix),
`customer_crm_service`/`customers_admin_service`/`segment_service`, `checklist_service` (read),
`import_service` (writes catalog + core.ImportJob).

## Decisions
- **DR-2** — content has no write service (Pattern B for all content).
- **DR-3** — settings/config written directly (Pattern B) against ADR-58/69 service discipline.
- **DR-4** — `staff_transfer_ownership` (~5896) calls `membership_service.transfer_ownership`
  (one of the two live ownership-transfer paths).
