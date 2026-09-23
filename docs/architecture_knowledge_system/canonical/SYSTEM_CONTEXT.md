# System Context

```
status: CANONICAL
code_baseline: 5883a140
last_verified_against_code: 5883a140
source_phases: Phase 1 / Phase 2
open_decisions: —
```

The current runtime shape of RastiSi. Grounded in `shop_core/settings.py`, `shop_core/urls*.py`,
`apps/portal/middleware.py`, `apps/stores/middleware.py`, and `apps/stores/resolution.py`
(Phase 1 docs 01/02/05/08; Phase 2 doc 05).

---

## 1. One project, three Host-partitioned surfaces (CURRENT CODE REALITY)

`apps.portal.middleware.PlatformHostRoutingMiddleware` sets `request.urlconf` per request:

| Host in… | → URLconf | Surface | Entry |
|---|---|---|---|
| `RASTISI_PLATFORM_ADMIN_HOSTS` | `shop_core.urls_platform_admin` | Platform Admin (staff/superuser) | `apps.portal.platform_admin_urls` / `platform_admin_views` |
| `RASTISI_PLATFORM_HOSTS` | `shop_core.urls_platform` | Marketing + Owner Portal | `apps.portal.urls` |
| (any other host) | `shop_core.urls` (ROOT_URLCONF) | Per-Store storefront + Merchant Admin | `apps.catalog.urls` (`/`), `apps.dashboard.urls` (`/admin-portal/`), … |

Middleware order (from `settings.MIDDLEWARE`): `SecurityMiddleware` →
`stores.StoreResolutionMiddleware` → `portal.PlatformHostRoutingMiddleware` →
`stores.StorefrontCanonicalRedirectMiddleware` → session/auth/… →
`dashboard.AdminEmbedFrameOptionsMiddleware`.

## 2. Tenant boundary and Store resolution (CURRENT CODE REALITY)

- The tenant boundary is `apps.stores.Store`. Every commerce record is either platform-global by
  explicit design or owned (directly/indirectly) by exactly one Store.
- `apps.stores.middleware.StoreResolutionMiddleware` sets `request.store` on every request via
  `apps.stores.resolution.resolve_store_for_request` → `resolve_store_for_hostname` (the **sole**
  authoritative Host→Store resolver). Eligibility = `Store.status == ACTIVE` AND a matching
  `StoreDomain` with `verification_status == VERIFIED` AND `retired_at is None`.
- The **merchant admin** host is resolved by a **separate** path,
  `resolve_store_for_admin_host` / `resolve_store_for_admin_request`, matching
  `{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`.
- Store ownership is modeled exclusively by an active `StoreMembership` with `role=OWNER`
  (no `Store.owner` field). See [`DATA_OWNERSHIP.md`](DATA_OWNERSHIP.md) and domain
  [`../domains/stores/`](../domains/stores/).

## 3. Two separate money systems (CURRENT CODE REALITY)

| System | Apps | Payment attempt model | Provider | Refund model |
|---|---|---|---|---|
| **Storefront money** (customer buys products) | `cart` → `orders` (+ `catalog` stock) | `orders.PaymentAttempt` (+ legacy `orders.Transaction`) | `orders/gateways/` (zibal, cod) | `orders.Refund` (MANUAL only) |
| **Platform money** (merchant pays RastiSi) | `subscriptions` ↔ `billing` | `billing.SubscriptionPaymentAttempt` | `billing/providers/` (manual, zibal) | `billing.SubscriptionRefund` |

These are deliberately separate; do not conflate them. (Design intent: ADR-73.)

## 4. Domain clusters (CURRENT CODE REALITY)

- **Identity/tenancy:** `stores`, `portal`, `customers`, `core`.
- **Commerce (storefront money):** `cart` → `orders` (+ `catalog`).
- **SaaS (platform money):** `subscriptions` ↔ `billing`.
- **Presentation:** `storefront_builder` + `content` + `catalog` (render path).
- **Control/messaging:** `dashboard` (controller), `sms`, `notifications`.
- **Near-dead:** `blog`.

## 5. External boundaries (CURRENT CODE REALITY)
Payment gateways (Zibal, COD; Zibal/manual for billing), SMS providers (Melipayamak, Kavenegar,
SmsRasti Android device gateway, console), DNS/TLS (dnspython + SSL socket for custom-domain
verification), SMTP email (owner password reset), Cloudflare Turnstile. See
[`EXTERNAL_INTEGRATIONS.md`](EXTERNAL_INTEGRATIONS.md).

## 6. Scale (VERIFIED)
16 apps under `apps/`; ~213,934 production Python LOC (excl. migrations); 145 service files;
8,665 test functions; 34 management commands; **0 Django signals** (deliberate — side effects via
explicit service calls + `transaction.on_commit`). SQLite (dev/test) / PostgreSQL (prod).

## 7. Canonical graph
See the authoritative Phase 1 source
[`../phase1_code_discovery/graphs/system_context.mmd`](../phase1_code_discovery/graphs/system_context.mmd)
and the canonical navigation graphs in [`graphs/`](graphs/README.md).

---

### Distinctions honored on this page
- **CURRENT CODE REALITY** (above) — verified at `5883a140`.
- **DOCUMENTED DESIGN INTENT** — the SaaS ADR record explains *why* (e.g. ADR-73 two money
  systems, ADR-11 hostname-authoritative resolution); see
  [`DOCUMENTATION_AUTHORITY.md`](DOCUMENTATION_AUTHORITY.md).
- **UNRESOLVED DECISIONS** — none specific to this page; system-wide DRs are in
  [`ARCHITECTURAL_DECISION_REGISTER.md`](ARCHITECTURAL_DECISION_REGISTER.md).
