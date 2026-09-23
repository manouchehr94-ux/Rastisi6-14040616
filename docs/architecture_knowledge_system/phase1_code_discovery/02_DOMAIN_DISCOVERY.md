# 02 — Domain Discovery

Domains below are **derived from code** (app boundaries, model ownership, service
responsibilities, and Host-based routing), not assumed in advance.

Evidence class legend as in doc 01.

---

## 1. The three runtime surfaces (VERIFIED)

The system is one Django project serving three distinct surfaces selected by HTTP Host, via
`apps.portal.middleware.PlatformHostRoutingMiddleware` choosing `request.urlconf`:

| Surface | Host set | URLconf | Purpose |
|---|---|---|---|
| **Per-Store storefront + Merchant Admin** | any other host (falls back to ROOT_URLCONF) | `shop_core.urls` | Public storefront (`/`, cart, checkout, account, pages) + merchant dashboard (`/admin-portal/`) |
| **Platform marketing + Owner Portal** | `RASTISI_PLATFORM_HOSTS` | `shop_core.urls_platform` → `apps.portal.urls` | Marketing site, owner signup/login/OTP, store creation/onboarding, billing checkout, domain/handle management |
| **Platform Admin** | `RASTISI_PLATFORM_ADMIN_HOSTS` | `shop_core.urls_platform_admin` → `apps.portal.platform_admin_urls` | Staff/superuser operational console |

The **tenant boundary** is `apps.stores.Store`; `request.store` is resolved from the Host by
`apps.stores.resolution` (doc 08 §routing). Every commerce record is either platform-global by
design or owned (directly/indirectly) by exactly one Store.

## 2. Discovered domains

### D1 — Tenancy & Store Identity  → `apps/stores` (VERIFIED)
- **Responsibility:** the SaaS tenant boundary; Store lifecycle, membership/roles, domains
  (verification/routing/TLS), ownership transfer, external non-payment integrations, and the
  authoritative Host→Store resolution + authorization matrix.
- **Owned data:** `Store`, `StoreDomain`, `StoreMembership`, `StoreOwnershipTransfer`,
  `StoreIntegrationConnection`.
- **Entry points:** middleware (`StoreResolutionMiddleware`, `StorefrontCanonicalRedirectMiddleware`),
  resolution helpers, management commands (`purge_deleted_stores`, `rename_store_handle`, …).
- **Consumers:** essentially every other app reads `request.store` / Store.
- **Boundary note:** deliberately does **not** import `apps.core` (duplicates the timestamp base)
  to pre-empt a future `core → stores` cycle. AMBIGUOUS_OWNERSHIP vs `catalog.Vendor` (doc 03/13).

### D2 — Platform Control & Owner Identity  → `apps/portal` (VERIFIED)
- **Responsibility:** platform-global config, owner/staff identity & auth (email/password + phone
  OTP + step-up), host routing, store provisioning orchestration, platform-admin console,
  platform-level audit/notes/contact.
- **Owned data:** `OwnerProfile`, `OwnerOtpChallenge`, `AdminHandoffTicket`,
  `PlatformConfiguration` (true pk=1 singleton), `PlatformAuditLogEntry`, `PlatformInternalNote`,
  `ContactMessage`.
- **Entry points:** `portal.urls` (owner portal), `platform_admin_urls`/`platform_admin_views`,
  `PlatformHostRoutingMiddleware`, decorators.
- **Cross-domain writer:** `provisioning_service` writes stores + core + catalog + subscriptions.

### D3 — Storefront Customer Identity & CRM  → `apps/customers` (VERIFIED)
- **Responsibility:** the shopper account (global, phone-keyed), per-Store CRM projection,
  addresses, wishlist, segments/tags, guest→user cart merge, customer auth/OTP.
- **Owned data:** `Customer` (global, no store FK), `CustomerProfile` (store-scoped),
  `CustomerTag`, `CustomerNote`, `CustomerSegment`(+`Rule`/`Membership`), `Address`, `Wishlist`.

### D4 — Catalog & Inventory  → `apps/catalog` (VERIFIED)
- **Responsibility:** products/variants/options/attributes, categories/brands, collections,
  inventory (warehouses, movements, reservations, transfers), industry templates & installs,
  specifications, reviews, tax classes are referenced here but the config lives in orders.
- **Owned data:** ~30 models incl. `Product`, `ProductVariant`, `Category`, `Brand`, `Vendor`,
  `Warehouse`, `WarehouseInventory`, `InventoryReservation`, `StockMovement`, `MerchantCollection`,
  `IndustryTemplate` (+ family), `StoreIndustryInstallation`, `StoreTemplateUpdate`.
- **Notable:** custom `ProductVariantQuerySet`/manager blocks normalization-bypassing bulk writes;
  inventory mutation is ledgered through `StockMovement`.

### D5 — Cart & Pricing  → `apps/cart` (VERIFIED)
- **Responsibility:** the shopping cart, cart pricing/coupons, gift wrap, checkout token.
- **Owned data:** `Cart`, `CartItem`, `Coupon`.
- **Boundary note:** `orders` reaches into cart items (reprice + delete) — cross-domain (doc 06/13).

### D6 — Orders, Checkout, Payments (storefront money)  → `apps/orders` (VERIFIED)
- **Responsibility:** order creation from cart, order state machine, storefront **payment**
  (two coexisting implementations), refunds/returns, shipping & tax configuration, payment gateway
  config & adapters.
- **Owned data:** `Order`, `OrderItem`, `OrderStatusHistory`, `Transaction` (legacy), `PaymentAttempt`
  (new), `PaymentGatewayConfig`, `PaymentGateway` (legacy), `Refund`(+`Item`), `ReturnRequest`(+`Item`),
  `ShippingZone/Method/RateRule`, `TaxClass/TaxRate`.
- **Adapters:** `gateways/` (zibal, cod) behind an abstract `PaymentGatewayAdapter`.

### D7 — SaaS Subscriptions (platform money — entitlements)  → `apps/subscriptions` (VERIFIED)
- **Responsibility:** plans/versions/entitlements, the canonical `StoreSubscription` state machine,
  usage records, entitlement resolution & enforcement.
- **Owned data:** `Plan`, `PlanVersion`, `EntitlementDefinition`, `PlanEntitlement`,
  `StoreSubscription`, `SubscriptionEvent`, `UsageRecord`.

### D8 — SaaS Billing (platform money — invoicing/payment)  → `apps/billing` (VERIFIED)
- **Responsibility:** subscription invoicing, billing payment attempts & confirmation, webhooks
  inbox, dunning, renewals, credit notes/refunds, plan-change billing, numbering.
- **Owned data:** `StoreBillingAccount`, `SubscriptionInvoice`(+`Line`), `SubscriptionPaymentAttempt`,
  `BillingWebhookEvent`, `SubscriptionDunningState`, `SubscriptionCreditNote`, `SubscriptionRefund`,
  `ScheduledPlanChange`, `BillingSequence`.
- **Cross-domain driver:** billing services drive the subscription state machine (via
  `subscription_service`, funneled) — doc 06/07/08.

### D9 — Storefront Presentation / Builder  → `apps/storefront_builder` (VERIFIED)
- **Responsibility:** the visual storefront layout system — versioned draft/publish snapshots,
  pages/sections/containers/cells, appearance/theme/palette registries, R4 editor, A8 ready
  templates, render path, edit history/undo.
- **Owned data:** `StorefrontLayout`, `StorefrontLayoutVersion`, `StorefrontPage`,
  `StorefrontSection`, `StorefrontContainer`, `StorefrontCell`, `StorefrontEditHistoryEntry`.
- **Notable:** three editor generations coexist (legacy R3, R4 default, A8) — doc 13.

### D10 — Content & Navigation  → `apps/content` (VERIFIED)
- **Responsibility:** CMS pages, navigation menus, footer settings/media, section-scoped
  placements (hero/banner/story), social links, newsletter, media assets.
- **Owned data:** `ContentPage`, `Menu`, `MenuItem`, `FooterSettings`, `FooterTrustBadge`,
  `FooterPaymentLogo`, `HeroSlide`, `PromotionalBanner`, `StoryRailItem`, `SocialLink`,
  `MediaAsset`, `NewsletterSubscriber`.
- **Boundary note:** placements FK **into** `storefront_builder.StorefrontSection`; has **no write
  service** — mutated wholesale by `dashboard` views (doc 12/13). Overlaps storefront_builder on
  "pages"/"navigation"/"footer" (AMBIGUOUS_OWNERSHIP, doc 13).

### D11 — Merchant Admin (controller)  → `apps/dashboard` (VERIFIED)
- **Responsibility:** the merchant-facing admin at `/admin-portal/`. Auth gating (staff_required +
  permission_required over StoreMembership), and orchestration/CRUD across catalog, orders, content,
  settings, staff, imports/exports, storefront-builder delegation.
- **Owned data:** none (models.py empty).
- **Smell:** thick controller for content/settings/shipping/tax/gateway (direct writes) — doc 13.

### D12 — Messaging: SMS  → `apps/sms` (VERIFIED)
- **Responsibility:** SMS templates/events, credit accounting, backends (console/Melipayamak/
  Kavenegar/SmsRasti Android gateway), send pipeline, OTP codes.
- **Owned data:** `SmsTemplate`, `SmsBillingPolicy`, `SmsLog`, `SmsOutboxItem`, `SmsBalance`,
  `SmsPackage`(+`Purchase`), `SmsCreditAdjustment`, `OtpCode`.
- **Entry points:** `gateway_views` (device-token poll/ack). Store SMS funnels through `_dispatch`.

### D13 — Notifications (outbox)  → `apps/notifications` (VERIFIED)
- **Responsibility:** persistent multi-channel notification outbox (in-app/SMS/email) delivered by
  a management command; security-event notifications.
- **Owned data:** `NotificationOutbox`.
- **Callers:** `stores` services (deletion/handle/ownership-transfer) enqueue security events.

### D14 — Shared/Cross-cutting  → `apps/core` (VERIFIED)
- **Responsibility:** `ShopSettings` (per-Store identity/tax/branding), shared `TimeStampedModel`
  base, audit log, export/import job records + private storage, SEO (sitemap/robots), color/theme/
  phone/URL-converter utilities, session "remember me".
- **Owned data:** `ShopSettings`, `AuditLogEntry`, `ExportJob`, `ImportJob`(+`RowResult`).
- **Note:** `ShopSettings` is store-scoped despite a singleton-style `load()` API; carries legacy
  SMS fields now superseded by `PlatformConfiguration` (POTENTIALLY_DEAD fields — doc 13).

### D15 — Blog (near-dead)  → `apps/blog` (VERIFIED)
- **Responsibility:** a single `BlogPost` model administered via Django admin. No `urls.py`,
  `views.py` is a stub, not referenced by any URLconf. POTENTIALLY_DEAD (doc 13).

## 3. Domain-cluster summary

- **Identity/tenancy cluster:** stores, portal, customers, core.
- **Commerce cluster (storefront money):** cart → orders (+ catalog for stock/pricing).
- **SaaS cluster (platform money):** subscriptions ↔ billing.
- **Presentation cluster:** storefront_builder + content + catalog (render path).
- **Control/messaging:** dashboard (controller), sms, notifications.

Two deliberately separate "money" systems exist and must not be conflated: **storefront money**
(customer buys products: cart/orders) vs **platform money** (merchant pays Rastisi:
subscriptions/billing). They have separate payment-attempt models, separate providers, and
separate refund models (VERIFIED from model docstrings).
