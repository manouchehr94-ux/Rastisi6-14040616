# Domain Map

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 (doc 02) / Phase 2
```

The 15 code-derived domains, their apps, responsibilities, and pack links. Domain IDs (D1–D15) are
stable and consistent with Phase 1 `02_DOMAIN_DISCOVERY.md`. Deep packs live in
[`../domains/<app>/`](../domains/).

---

| ID | Domain | App | Responsibility (owns) | Pack |
|---|---|---|---|---|
| D1 | Tenancy & Store identity | `stores` | Store lifecycle, membership/roles, domains (verify/route/TLS), ownership transfer, Host→Store resolution, authorization | [stores](../domains/stores/README.md) |
| D2 | Platform control & owner identity | `portal` | Platform config singleton, owner/staff auth+OTP+step-up, host routing, provisioning, platform-admin console | [portal](../domains/portal/README.md) |
| D3 | Customer identity & CRM | `customers` | Global shopper account, per-Store CRM projection, segments/tags, addresses, wishlist, guest→user cart merge | [customers](../domains/customers/README.md) |
| D4 | Catalog & inventory | `catalog` | Products/variants/options/attributes, categories/brands, collections, ledgered inventory, industry templates | [catalog](../domains/catalog/README.md) |
| D5 | Cart & pricing | `cart` | Cart, cart pricing/coupons, gift wrap, checkout token | [cart](../domains/cart/README.md) |
| D6 | Orders, checkout, payments | `orders` | Order state machine, two storefront-payment implementations, refunds/returns, shipping/tax config, gateway config+adapters | [orders](../domains/orders/README.md) ★gold-standard |
| D7 | SaaS subscriptions | `subscriptions` | Plans/versions/entitlements, canonical `StoreSubscription` state machine, usage records | [subscriptions](../domains/subscriptions/README.md) |
| D8 | SaaS billing | `billing` | Subscription invoicing, billing payment/confirmation, webhook inbox, dunning, renewals, credit/refund, plan-change billing | [billing](../domains/billing/README.md) |
| D9 | Storefront presentation / builder | `storefront_builder` | Versioned draft/publish layout; R4 editor; A8 ready templates; appearance/theme/palette registries; render path | [storefront_builder](../domains/storefront_builder/README.md) |
| D10 | Content & navigation | `content` | CMS pages, menus, footer settings/media, section-scoped placements, social links, newsletter, media assets | [content](../domains/content/README.md) |
| D11 | Merchant admin (controller) | `dashboard` | Auth-gated orchestration/CRUD over other domains; storefront-builder route delegation. **No models.** | [dashboard](../domains/dashboard/README.md) |
| D12 | Messaging: SMS | `sms` | SMS templates/events, credit accounting, backends, device gateway, OTP codes | [sms](../domains/sms/README.md) |
| D13 | Notifications | `notifications` | Persistent multi-channel notification outbox | [notifications](../domains/notifications/README.md) |
| D14 | Shared / cross-cutting | `core` | ShopSettings (per-Store), TimeStampedModel base, audit log, export/import + private storage, SEO, utilities | [core](../domains/core/README.md) |
| D15 | Blog (near-dead) | `blog` | Single `BlogPost` admin-only model; no urls/views | [blog](../domains/blog/README.md) |

---

## Ownership boundaries at a glance
- **`stores.Store`** is the universal FK root and tenant boundary.
- **`dashboard` owns no models** — it is a controller that writes *other* domains' models (some via
  their services, some directly; see [`MUTATION_AUTHORITY.md`](MUTATION_AUTHORITY.md) and finding H2).
- **`content` has no write service** — its models are Store-owned but mutated by `dashboard` views
  (finding H2, decision DR-2).
- **`orders` and `billing` each own a *separate* payment stack** (two money systems).

## Boundary ambiguities (documented, not resolved)
- **Store vs `catalog.Vendor`** (A1 / DR-7): both represent a "seller-ish" entity; coexistence
  contract not fully expressed in code.
- **Footer ×3** (M2): `StorefrontLayoutVersion.footer_config` vs `content.FooterSettings` vs
  `global_region_registry` footer variant.
- **"Page" ×2** (M3): `storefront_builder.StorefrontPage` vs `content.ContentPage`.
- **Ownership transfer ×2** (A8/M6/DR-4): `stores.membership_service.transfer_ownership`
  (dashboard) **and** `stores.ownership_transfer_service` (portal OTP) — **both live**.

## Cluster diagram
See [`graphs/domain_map.mmd`](graphs/domain_map.mmd) and
[`graphs/domain_dependencies.mmd`](graphs/domain_dependencies.mmd).

## Model/service counts per domain (VERIFIED)
| App | Model classes | Service files |
|---|---:|---|
| stores | 6 | 13 (`services/`) |
| portal | 7 | 10 |
| customers | 9 | 1 |
| catalog | 38 | 31 |
| cart | 3 | 5 |
| orders | 16 | 9 (+ `gateways/`) |
| subscriptions | 7 | 7 |
| billing | 10 | 15 (+ `providers/`) |
| storefront_builder | 7 | 17 |
| content | 13 | **0 `services/`** (single read-only `services.py`) |
| dashboard | 0 | 12 |
| sms | 9 | 5 |
| notifications | 1 | 1 |
| core | 6 | 5 |
| blog | 1 | 0 |

(Model-class counts include abstract bases/mixins where defined in the app's `models.py`.)
