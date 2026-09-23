# Dependency Map

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 07) / Phase 2 (doc 05)
open_decisions: —
```

Typed cross-domain dependencies. Types: `calls`, `imports`, `writes` (cross-domain mutation),
`reads`, `foreign-key`, `routes-to`, `renders`, `external-call`.

---

## Key edges (VERIFIED)

| From | To | Type | Evidence |
|---|---|---|---|
| every request | `stores` | calls | `StoreResolutionMiddleware` → `resolve_store_for_hostname` |
| every request | `portal` | routes-to | `PlatformHostRoutingMiddleware` selects urlconf |
| `dashboard` | `catalog` | calls + writes | catalog services + direct Product/Category writes |
| `dashboard` | `orders` | calls | `order_service.change_order_status`, refund/return; direct shipping/tax/gateway-config writes |
| `dashboard` | `content` | writes (cross-domain) | direct `.save()` of all content models (H2; content has no write service) |
| `dashboard` | `core` | writes + calls | direct `ShopSettings.save()`; export_service; audit_service |
| `dashboard` | `stores` | calls | membership_service (incl. `transfer_ownership`), integration_service, resolution/authorization |
| `dashboard` | `subscriptions` | reads | entitlement/enforcement (banners, seat gate) |
| `dashboard` | `sms` | calls | sms_service (test/retry) |
| `dashboard` | `storefront_builder` | routes-to + calls | urls delegate to views/r4_views/media_views |
| `orders` | `cart` | writes (cross-domain) | reprice CartItem, delete items, Coupon.used_count |
| `orders` | `catalog` | writes | reserve/consume inventory + StockMovement |
| `orders` | `sms` | calls (on_commit) | ORDER_*/PAYMENT_* events |
| `orders` (gateways) | external | external-call | Zibal/COD |
| `customers` | `cart` | writes (cross-domain) | merge_guest_cart |
| `customers` | `sms` | calls (on_commit) | WELCOME |
| `billing` | `subscriptions` | writes (cross-domain, funneled) | confirmation/dunning/renewal/cancellation → subscription_service |
| `billing` | external | external-call | provider (manual/zibal) + webhook signature |
| `portal.provisioning_service` | `stores`+`core`+`catalog`+`subscriptions` | writes (cross-domain) | single `@atomic` creating across 4 apps |
| `portal.owner_otp_service` | `sms`/`portal.owner_sms_service` | external-call | OTP SMS |
| `stores` services | `notifications` | calls | notify_security_event (deletion/handle/ownership) |
| `stores` services | `subscriptions` | reads | publication entitlement (local import) |
| `stores.ownership_transfer_service` | `portal.owner_auth_service` | calls | create new-owner User |
| `catalog.home` / `content.page_detail` | `storefront_builder.render_service` | renders (lazy import) | build_render_items |
| `content` models | `storefront_builder.StorefrontSection` | foreign-key (CASCADE) | Hero/Banner/Story placements |
| `sms.sms_service` | `portal.PlatformConfiguration` | reads | central SMS creds |
| `stores.StoreIntegrationConnection` | `orders.encryption` | imports | reuses credential encryption |

## Deliberate cycle-avoidance (VERIFIED, managed but latent — MEDIUM M13)
- `stores` duplicates `core.TimeStampedModel` (avoids future `core→stores` cycle).
- `publication_service` imports `subscriptions` locally.
- `catalog.home`/`content.page_detail` import `storefront_builder` lazily.
- `catalog.IndustryTemplate.default_section_keys` validated in `storefront_builder`, not catalog.

## No signal coupling (VERIFIED)
0 Django signal receivers in production. All cross-domain reactions are explicit service calls or
`transaction.on_commit` callbacks.

## Highest-coupling nodes
1. `stores.Store` (universal FK + resolution).
2. `dashboard` (controller fan-out incl. direct writes to 8+ apps).
3. `portal.provisioning_service` (4-app atomic write).
4. `billing → subscriptions` (state-machine driver).
5. `storefront_builder ↔ content ↔ catalog` (render + FK + registry).

Graphs: [`../phase1_code_discovery/graphs/domain_dependencies.mmd`](../phase1_code_discovery/graphs/domain_dependencies.mmd),
[`../phase1_code_discovery/graphs/service_dependencies.mmd`](../phase1_code_discovery/graphs/service_dependencies.mmd).
