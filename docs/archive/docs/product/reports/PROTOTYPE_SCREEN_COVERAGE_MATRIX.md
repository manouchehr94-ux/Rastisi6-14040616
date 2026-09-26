# Prototype → Implementation Screen Coverage Matrix

Companion to `PROTOTYPE_IMPLEMENTATION_GAP_AUDIT.md`. Every authoritative
prototype screen, mapped to what actually exists in code at commit `3f172f1`
(Checkpoint 6 final).

**Status vocabulary (only these values are used):** Complete · Equivalent
implementation · Partial · Backend only · UI only · Placeholder · Broken ·
Missing · Obsolete prototype.

A screen is **never** marked Complete merely because a similarly-named template
exists — Complete requires a reachable route, a working view, and a browser-
navigable path from the preceding screen.

---

## System A — Rastisi public website & account portal
Prototype set: `docs/docs/product/Final Result At Last/rastisi-site/` (14 screens)

| # | Prototype screen | Prototype file | Intended URL | Actual URL | Actual view | Actual template | Status | Visual | Functional | Nav | Resp. | RTL | Security | Missing elements | Recommended action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 | Rastisi marketing home | `index.html` | `rastisi.ir/` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page; `/` serves a *storefront*, not Rastisi | Build `apps.portal` public home |
| A2 | Features | `features.html` | `/features` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page | Static marketing page |
| A3 | Industries | `categories.html` | `/industries` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page (`IndustryTemplate` data exists) | Bind to existing IndustryTemplate data |
| A4 | Plans & pricing | `plans.html` | `/plans` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Public plan list; `Plan`/`PlanVersion` exist but are never shown publicly | Render published PlanVersions |
| A5 | How it works | `how-it-works.html` | `/how-it-works` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page | Static marketing page |
| A6 | FAQ | `faq.html` | `/faq` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page | Static marketing page |
| A7 | About | `about.html` | `/about` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page | Static marketing page |
| A8 | Contact | `contact.html` | `/contact` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | Whole page + form | Static page + spam-safe form |
| A9 | **Owner registration** | `register.html` | `/register` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | **P0** | Name/mobile/email/password, terms, OAuth stubs. `customers:signup` is a *storefront customer* signup and creates no Store | Build owner registration + trial provisioning |
| A10 | **Owner login** | `login.html` | `/login` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | **P0** | Rastisi-account login distinct from `dashboard:login` and `customers:login` | Build portal auth |
| A11 | Password recovery | (implied by A10) | `/password-reset` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | P1 | No owner-account recovery | Reuse OTP infrastructure |
| A12 | **Owner dashboard / My Stores** | `dashboard.html` | `/dashboard` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | **P0** | Store card w/ hostname, plan, status, "Enter admin". *Prototype shows a single-store dashboard, not a multi-store list* | Build My Stores (multi-store, per §6) |
| A13 | **Store setup wizard** (5 steps: industry → info → **subdomain** → custom domain → activate) | `store-setup.html` | `/store-setup` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | **P0** | Entire wizard. Industry install exists only *inside* merchant admin | Build wizard; reuse `industry_template_service` |
| A14 | Store activated success | `store-success.html` | `/store-success` | — | — | — | **Missing** | ✗ | ✗ | ✗ | ✗ | ✗ | P1 | Shows final `name.rastisi.ir`, industry, plan | Build confirmation screen |

**System A totals: 14 authoritative screens · 0 Complete · 0 Equivalent · 0 Partial · 14 Missing.**

---

## System B — Merchant Store Admin
Prototype set: `docs/docs/product/Final Result At Last/novinshop-video-rich-products/` (45 screens, "merchant-panel-x25")

| # | Prototype screen | Prototype file | Actual URL name | Status | Notes |
|---|---|---|---|---|---|
| B1 | Dashboard | `index.html` | `dashboard:dashboard` | **Complete** | Stats, charts, recent orders |
| B2 | All products | `products.html` | `product-list` / `product-table` | **Complete** | Filters, bulk actions |
| B3 | Add product | `product-create.html` | `product-add` | **Complete** | |
| B4 | Edit product | `product-edit.html` | `product-edit` | **Complete** | + images, options, variants |
| B5 | Categories | `categories.html` | `category-list` (+schema) | **Complete** | Exceeds prototype (attribute schema) |
| B6 | Orders list | `orders.html` | `order-list` / `order-detail` | **Complete** | |
| B7 | Customers | `customers.html` | `customer-list` / `customer-detail` | **Complete** | + notes, tags, segments |
| B8 | Invoices | `invoices.html` | `invoice-list` / `invoice-detail` | **Complete** | |
| B9 | Financial transactions | `payments.html` | `payment-list` | **Complete** | |
| B10 | Payment gateways | `payment-settings.html` | `settings-gateway-*` | **Complete** | Encrypted credentials |
| B11 | Logistics & shipping | `shipping-settings.html` | `shipping-zone/method/rate-rule-*` | **Complete** | Exceeds prototype |
| B12 | Bulk product import | `import-products.html` | `import-list`/`upload`/`execute` | **Complete** | Preview+execute engine |
| B13 | Industry & catalog setup | `industry-setup.html` | `settings-industry-install/preview/update` | **Complete** | Reachable only *inside* admin |
| B14 | Site pages | `pages.html` | `page-list`/`add`/`publish` | **Complete** | |
| B15 | Homepage content | `home-page-content.html` | `hero-*` / `banner-*` | **Complete** | |
| B16 | Base settings | `general-configs.html` | `settings` | **Complete** | |
| B17 | Legal/business info | `business-info.html` | `settings-shop-info` | **Complete** | |
| B18 | Subscription plan | `subscription.html` | `subscription-overview`/`plans`/`billing-*` | **Complete** | Exceeds prototype (5A+5B) |
| B19 | System events | `logs.html` | `audit-log-list` | **Complete** | |
| B20 | Merchant login | `login.html` | `dashboard:login` | **Complete** | Host + membership gated |
| B21 | SMS templates | `sms-custom.html` | `sms-template-edit/toggle` | **Complete** | |
| B22 | SMS gateway settings | `sms-gateway-settings.html` | `settings-sms-connection` | **Complete** | |
| B23 | SMS inbox | `sms-list.html` | `sms-log-list` | **Complete** | |
| B24 | Visual design | `appearance-settings.html` | `settings-appearance` | **Equivalent implementation** | Theme via CSS variables (ADR-91) |
| B25 | Banners & discounts | `coupons.html` | `coupon-*` + `banner-*` | **Equivalent implementation** | Prototype merges two concerns |
| B26 | Sales analysis | `order-report.html` | `report-list` / `report-body` | **Partial** | Reports exist; no per-report parity |
| B27 | Product performance | `product-report.html` | `report-list` | **Partial** | Same |
| B28 | Customer behaviour | `customer-report.html` | `report-list` + `segment-*` | **Partial** | Same |
| B29 | SMS statistics | `sms-report.html` | `sms-log-table` | **Partial** | Log table, no aggregate stats |
| B30 | Order rules | `order-settings.html` | `settings` (subset) | **Partial** | No dedicated order-policy screen |
| B31 | Brands | `brands.html` | — | **Backend only** | `Brand` model + storefront filter exist; **no admin CRUD UI** |
| B32 | Product comments | `product-comments.html` | — | **Backend only** | `Review` model + storefront submit; `is_approved` has **no moderation UI** |
| B33 | Abandoned carts | `draft-orders.html` | — | **Missing** | `Cart` exists; no abandoned-cart view |
| B34 | Manual order entry | `order-new.html` | — | **Missing** | No merchant-side order creation |
| B35 | Page comments | `page-comments.html` | — | **Missing** | No model |
| B36 | Wallet transactions | `wallet-transactions.html` | — | **Missing** | No wallet model |
| B37 | Cashback & wallet | `cashback-settings.html` | — | **Missing** | No cashback model |
| B38 | Marketing & growth | `marketing.html` | — | **Missing** | No model |
| B39 | Social/Instagram | `instagram.html` | — | **Missing** | Social *links* exist; no integration |
| B40 | Affiliate/invite | `invite-friends.html` | — | **Missing** | No model |
| B41 | Support ticketing | `ticketing.html` | — | **Missing** | No model |
| B42 | Learning centre | `guide.html` | — | **Missing** | Static content |
| B43 | Store builder studio | `store-editor.html` | — | **Obsolete prototype** | Drag-and-drop builder explicitly out of scope (ADR-91) |
| B44 | Storefront (in-panel) | `storefront.html` | `catalog:home` | **Complete** | Belongs to System C |
| B45 | Storefront brands | `storefront-brands.html` | `product-list?brand=` | **Partial** | Filter works; no brand landing page |
| — | **Domain / subdomain settings** | *(absent from panel prototype; required by `store-setup.html` steps 3–4 and audit §7)* | — | **Missing** | **No merchant UI to view/change a subdomain or attach a custom domain** |

**System B totals (45 prototype screens): 23 Complete · 2 Equivalent · 6 Partial · 2 Backend only · 11 Missing · 1 Obsolete.**
Plus 1 non-prototype but journey-required screen (domain settings) = Missing.

**Implemented beyond the prototype** (no prototype screen exists for these):
warehouses, stock transfers, inventory reservations, tax classes/rates, returns,
refunds, staff & permissions, customer segments, data export, audit log,
subscription usage/limits, SaaS billing invoices/payments/refunds/credit notes.

---

## System C — Customer Storefront
Prototype set: `docs/docs/product/spec/` (3 screens) + `novinshop/storefront.html`

| # | Prototype screen | Prototype file | Actual URL | Status | Notes |
|---|---|---|---|---|---|
| C1 | Storefront home | `shop-frontend.html`, `storefront.html` | `catalog:home` | **Complete** | Hero, categories, product rails, brand theming |
| C2 | Listing / category / search / filters | `shop-frontend.html` | `catalog:product-list` | **Complete** | Category via `?category=` (ADR-83) |
| C3 | Product detail + variants | `shop-frontend.html` | `catalog:product-detail` | **Complete** | Gallery, variant groups, reviews, JSON-LD |
| C4 | Cart | `shop-checkout.html` | `cart:detail` | **Complete** | Server-validated (ADR-85) |
| C5 | Checkout + payment | `shop-checkout.html` | `orders:checkout-step1` … `payment-callback` | **Complete** | Idempotent, server-verified |
| C6 | Customer auth | `shop-frontend.html` (modal) | `customers:login`/`signup`/OTP | **Complete** | |
| C7 | Customer account / orders | `shop-frontend.html` | `customers:account`, `account-order-detail` | **Complete** | Owner-scoped |
| C8 | Static/policy pages | `shop-frontend.html` (footer) | `content:page-detail` | **Complete** | Published-only |
| C9 | Admin panel (old single-store) | `shop-admin-panel.html` | `dashboard:*` | **Obsolete prototype** | Superseded by merchant-panel-x25 |

**System C totals (9 mapped screens): 8 Complete · 1 Obsolete.**

---

## Roll-up

| Metric | Count |
|---|---|
| Prototype source locations | 4 (`rastisi-site`, `novinshop-…-x25`, `spec`, `docs/prototypes/README.md` pointer) |
| Authoritative prototype screens | **62** HTML (14 + 45 + 3) |
| Rows in this matrix | 68 (62 prototype + per-system duplicates + 1 journey-required addition) |
| Complete | **31** |
| Equivalent implementation | **2** |
| Partial | **7** |
| Backend only | **2** |
| UI only | **0** |
| Placeholder | **0** |
| Broken | **0** |
| Missing | **26** (14 System A + 11 System B + 1 domain settings) |
| Obsolete prototype | **2** (`store-editor.html`, `shop-admin-panel.html`) |
