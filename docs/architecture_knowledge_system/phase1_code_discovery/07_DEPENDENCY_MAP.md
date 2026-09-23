# 07 — Dependency Map

Typed dependencies between domains/apps. Evidence class legend as in doc 01.

Dependency types used: `imports`, `calls`, `owns`, `reads`, `writes`, `foreign-key`,
`routes-to`, `renders`, `configured-by`, `tested-by`, `external-call`, `cross-domain-mutation`.

---

## 1. Import / runtime-call dependencies between apps (VERIFIED / INFERRED)

| From app | To app | Type | Evidence |
|---|---|---|---|
| every request | `stores` | calls | `StoreResolutionMiddleware` → `resolution.resolve_store_for_request` |
| every request | `portal` | routes-to | `PlatformHostRoutingMiddleware` selects urlconf |
| `dashboard` | `catalog` | calls, cross-domain-mutation | catalog services + direct Product/Category writes |
| `dashboard` | `orders` | calls | `order_service.change_order_status`, refund/return services; direct shipping/tax/gateway-config writes |
| `dashboard` | `content` | cross-domain-mutation | direct `.save()` of ContentPage/Menu/Footer/Hero/Banner/Social (no content write-service) |
| `dashboard` | `core` | cross-domain-mutation, calls | direct `ShopSettings.save()`; export_service; audit_service |
| `dashboard` | `stores` | calls | membership_service, integration_service, resolution/authorization |
| `dashboard` | `subscriptions` | calls, reads | entitlement/enforcement (banners, seat gate, export budget) |
| `dashboard` | `sms` | calls | sms_service (test/retry), balance |
| `dashboard` | `storefront_builder` | routes-to, calls | urls delegate to views/r4_views/media_views |
| `orders` | `cart` | cross-domain-mutation | writes CartItem.unit_price, deletes cart items, Coupon.used_count |
| `orders` | `catalog` | calls, writes | inventory reservation/consumption + StockMovement |
| `orders` | `sms` | calls (on_commit) | ORDER_* / PAYMENT_* events |
| `orders` (gateways) | external | external-call | Zibal / COD provider APIs |
| `customers` | `cart` | cross-domain-mutation | merge_guest_cart |
| `customers` | `sms` | calls (on_commit) | WELCOME |
| `billing` | `subscriptions` | cross-domain-mutation (funneled) | confirmation/dunning/renewal/cancellation → subscription_service |
| `billing` | external | external-call | provider (manual/zibal) refund/session; webhook signature |
| `subscriptions` | (self) | owns | canonical StoreSubscription state machine |
| `portal.provisioning_service` | `stores`,`core`,`catalog`,`subscriptions` | cross-domain-mutation | single `@atomic` creates across 4 apps |
| `portal.owner_otp_service` | `sms`/`portal.owner_sms_service` | external-call | OTP SMS |
| `stores` services | `notifications` | calls | notify_security_event (deletion/handle/ownership) |
| `stores` services | `subscriptions` | reads | publication entitlement (local import) |
| `stores.ownership_transfer_service` | `portal.owner_auth_service` | calls | create new-owner User |
| `catalog.home` / `content.page_detail` | `storefront_builder.render_service` | renders (lazy import) | build_render_items / universal context |
| `content` models | `storefront_builder.StorefrontSection` | foreign-key (CASCADE) | Hero/Banner/Story placements |
| `sms.sms_service` | `portal.PlatformConfiguration` | reads | central SMS creds (not ShopSettings) |
| `stores.StoreIntegrationConnection` | `orders.encryption` | imports | reuses credential encryption |

## 2. Database (foreign-key) ownership dependencies (VERIFIED)

- `stores.Store` is the root; nearly every store-scoped model FKs to it (catalog, orders, content,
  core, subscriptions, billing, sms, customers-profile, storefront_builder.StorefrontLayout).
- `content.HeroSlide/PromotionalBanner/StoryRailItem` → `storefront_builder.StorefrontSection`
  (cross-app FK — the tightest content↔builder coupling).
- `orders.Order` → `customers.Customer`, `catalog.Vendor`, `cart.Coupon`, `orders.PaymentGateway`,
  `orders.ShippingMethod` (mostly PROTECT).
- `billing.SubscriptionInvoice` → `subscriptions.StoreSubscription`, `subscriptions.PlanVersion` (PROTECT).
- `auth.User` ← OneToOne from both `portal.OwnerProfile` and `customers.Customer` (shared identity).

## 3. Deliberate dependency-cycle avoidance (VERIFIED)

- **`stores` must not import `core`.** `stores` defines its own `StoresTimestampedModel` instead of
  reusing `core.TimeStampedModel`, anticipating a future `core.ShopSettings → stores.Store` FK that
  would make `core → stores`; importing `core` now would create a cycle.
- **`publication_service` imports `subscriptions` locally** (inside functions) to avoid a module-level
  `stores → subscriptions` import cycle.
- **`catalog.home` / `content.page_detail` import `storefront_builder` lazily** (local imports) to
  avoid module-level cycles with the render layer.
- **`catalog.IndustryTemplate.default_section_keys` is validated against storefront_builder's
  SECTION_REGISTRY in storefront_builder, not catalog** — again to avoid catalog → storefront_builder.

These are managed, not accidental; but they are latent cycle risks (doc 13, MEDIUM).

## 4. Configuration / registry dependencies (VERIFIED)

- Host partitioning `configured-by` settings: `RASTISI_PLATFORM_HOSTS`, `RASTISI_PLATFORM_ADMIN_HOSTS`,
  `RASTISI_ADMIN_DOMAIN_SUFFIX`, `RASTISI_CANONICAL_DOMAIN_SUFFIX`.
- Billing/subscription `configured-by`: `RASTISI_BILLING_PROVIDER`, `RASTISI_DEFAULT_PLAN_CODE`, dunning schedule.
- Payment simulation `configured-by`: `PAYMENTS_SIMULATION_ENABLED`.
- Storefront appearance registries: `storefront_appearance.COMPONENT_REGISTRY` reads
  `appearance_registry` + `palette_pack_64` + `theme_catalog` + `global_region_registry` (registry
  fan-in; duplication concerns in doc 13).

## 5. UI / render dependencies (VERIFIED)
- `templates/storefront_shell.html` + `content.context_processors` (social/footer/menus) render the
  public shell; `storefront_builder.render_service` renders the page body items.
- 18 context processors (settings.py `TEMPLATES`) inject cross-domain view state (cart badge,
  wishlist, nav categories, subscription banner, permissions, footer/nav) into every template.

## 6. Event/signal dependencies (VERIFIED)
- **No signal-based coupling.** All cross-domain reactions are explicit service calls or
  `transaction.on_commit` callbacks (doc 05 §11–12).

## 7. External-integration dependencies (VERIFIED)
- Payment gateways: Zibal, COD (orders); Zibal/manual (billing).
- SMS providers: Melipayamak, Kavenegar, SmsRasti Android device gateway, console (dev).
- DNS/TLS: `dnspython` TXT lookups + raw SSL socket (domain verification).
- Turnstile (Cloudflare) bot protection; SMTP email (owner password reset).

## 8. Highest-coupling nodes (INFERRED from the above)
1. **`stores.Store`** — universal FK + resolution dependency (structural center).
2. **`dashboard`** — calls/writes into 8+ apps (controller fan-out; several direct writes).
3. **`portal.provisioning_service`** — writes 4 apps in one transaction (fan-out mutation).
4. **`billing` → `subscriptions`** — cross-domain state-machine driver.
5. **`storefront_builder` ↔ `content` ↔ `catalog`** — render + FK + registry coupling.
