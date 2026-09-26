# Prototype → Implementation Gap Audit (Rastisi)

**Audit-only.** No application code, models, migrations, tests, or configuration
were modified. Evidence is drawn from the actual routing, views, templates,
models, services, permissions and tests at commit `3f172f1` (Checkpoint 6
final) — not from documentation claims.

Companion matrix: `PROTOTYPE_SCREEN_COVERAGE_MATRIX.md`.

---

## 1. Executive summary

The repository contains **three prototype sets** and **three user-facing
systems**. Their implementation status is sharply uneven:

| System | Prototype screens | Implementation reality |
|---|---|---|
| **A — Rastisi public site & account portal** | 14 (`rastisi-site/`) | **Entirely missing.** No Django app, no URLconf entry, no view, no template. |
| **B — Merchant Store Admin** | 45 (`novinshop-…-x25/`) | **Substantially complete** (~200 routes; 23 Complete + 2 Equivalent), with real gaps in marketing/engagement extras and **no domain/subdomain UI**. |
| **C — Customer Storefront** | 3 (`spec/`) + 1 | **Complete** (Checkpoint 6). |

**The single most important finding:** the platform is a working *multi-tenant
store engine* whose tenants can only be created by a developer or platform
superuser. **The entire customer-acquisition funnel — visit rastisi.ir, register,
get a trial store, see "My Stores", pick a subdomain — does not exist in any
form.** `apps/stores` has models, resolution, hostname normalization and
membership authorization, but **no `urls.py`, no `views.py` and no templates**.

Consequences, stated plainly:

- **Registration → trial store is not wired.** `apps.customers.signup_view`
  creates a *storefront customer* for an already-resolved Store; it never
  creates a Store, a Membership, or a subscription.
- **`provision_default_subscription()` exists but is called from nothing but its
  own tests** (`apps/subscriptions/services/subscription_service.py:299`; the
  only other references are in
  `apps/subscriptions/tests/test_management_and_isolation.py`). It is
  backend-only and unreachable from a browser.
- **The nine-character trial identifier does not exist anywhere** — and, notably,
  **is not in the prototype either**. The authoritative prototype
  (`store-setup.html`, step 3) has the owner *choosing* a human-readable
  subdomain. The nine-character auto-generated trial hostname is a *newer
  requirement* stated in the audit brief with **no prototype backing and no
  implementation**. This conflict needs a product decision before either is
  built.
- **There is no merchant UI anywhere to view or change a subdomain, or to attach
  a custom domain**, despite `StoreDomain` supporting a full verification
  lifecycle at model level.

What *is* genuinely strong: tenant isolation (Host-resolved, fail-closed),
hostname normalization (IDN→punycode, port/scheme/path rejection, reserved
names), the entitlement/usage/limits engine, SaaS billing (invoices, payments,
webhooks, dunning, refunds), and the storefront. The gap is not depth — it is
the **missing front door**.

---

## 2. Prototype source inventory

| Prototype set | Path | Screens | Journey represented | Intended user | Authoritative? | Notes |
|---|---|---|---|---|---|---|
| **rastisi-site** | `docs/docs/product/Final Result At Last/rastisi-site/` | 14 HTML + `assets/` | Rastisi marketing site, owner registration/login, owner dashboard, 5-step store-setup wizard, activation success | Prospective & existing **store owner** | **Yes** — named in `docs/prototypes/README.md` | The only source defining System A. Persian, RTL, `assets/styles.css` design tokens. |
| **merchant-panel-x25** | `docs/docs/product/Final Result At Last/novinshop-video-rich-products/` | 45 HTML + `assets/` (`README-X22…X25.txt`) | Full merchant admin panel + in-panel storefront preview | **Merchant / staff** | **Yes** — named in `docs/prototypes/README.md` as "merchant-panel-x25" | Newer and richer than `spec/shop-admin-panel.html`; supersedes it. |
| **spec (single-store)** | `docs/docs/product/spec/` | 3 HTML + `01-PROJECT-SPEC.md`, `02-BUILD-INSTRUCTIONS.md` | Original generic-retail storefront, admin panel, checkout | Customer + merchant | **Partly** — the two `.md` files are the authoritative *build* spec; `shop-admin-panel.html` is superseded | Spec mandates RTL/Vazirmatn, stable English status codes, no hardcoded template data, HTMX+Alpine — all honoured by the implementation. |
| **pointer** | `docs/prototypes/README.md` (73 bytes) | 0 | — | — | Not a prototype | Contains only: *"Place extracted rastisi-site and merchant-panel-x25 HTML prototypes here."* — this is what establishes which sets are authoritative. |

No screenshots, wireframe images, Figma exports, or archived frontend bundles
were found. No backup directories contain prototypes.

**Prototype sources found: 4 locations · 62 authoritative HTML screens.**

---

## 3. Architecture overview (as built)

- **Tenant resolution** — `apps/stores/resolution.py` is the single authority.
  A request's `Host` is matched against `StoreDomain.hostname`; a match only
  counts when `Store.status == ACTIVE` **and**
  `StoreDomain.verification_status == VERIFIED` (fail-closed). Merchant-admin
  hosts resolve separately via
  `{Store.admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`. Checkpoint 6 added
  `resolve_store_for_storefront()`, which converts an unresolved Host into
  `Http404` rather than a 500.
- **Routing** (`shop_core/urls.py`): `/` → storefront (catalog), `/cart/`,
  `/account/` → *storefront customer* account, `/checkout/`, `/admin-portal/` →
  merchant admin, `/admin/` → Django admin (superuser-only), `/pages/`,
  `/billing/` → SaaS webhook, `/sitemap.xml`, `/robots.txt`.
  **No route is reserved for a Rastisi portal.**
- **Authorization** — `apps/stores/authorization.py` maps
  `StoreMembership.Role` → permission sets; `apps/dashboard/decorators.py`
  enforces admin-host + authentication + ACTIVE membership.
- **Subscriptions/entitlements** (5A) and **SaaS billing** (5B) are complete
  domains with merchant-facing UI *inside* the merchant admin.
- **No background task queue** (ADR-49); scheduled work is cron-driven commands.

---

## 4. Three-system separation

### A. Rastisi public website & account portal — **MISSING**

| Capability | Route | View | Template | Service | Model | Status |
|---|---|---|---|---|---|---|
| Homepage / Pricing / Features / Industries / How-it-works / FAQ / About / Contact | ✗ | ✗ | ✗ | ✗ | `Plan`, `PlanVersion`, `IndustryTemplate` exist | **Missing** |
| Owner registration | ✗ | ✗ | ✗ | ✗ | `User`, `Store`, `StoreMembership` exist | **Missing** |
| Owner login / logout / password recovery | ✗ | ✗ | ✗ | OTP infra exists in `customers` | — | **Missing** |
| Owner dashboard / **My Stores** | ✗ | ✗ | ✗ | ✗ | `StoreMembership` supports the query | **Missing** |
| Trial store creation | ✗ | ✗ | ✗ | `provision_default_subscription` (uncalled) | ✓ | **Backend only, unreachable** |
| Subscription purchase (portal-side) | ✗ | ✗ | ✗ | billing services exist | ✓ | **Missing at portal; present inside merchant admin** |
| Profile / Support | ✗ | ✗ | ✗ | ✗ | — | **Missing** |

### B. Merchant Store Admin — **SUBSTANTIALLY COMPLETE**

Present and reachable: store dashboard, products (+images/options/variants/
attributes), categories (+attribute schema), orders, invoices, payments,
customers (+notes/tags/segments), inventory, warehouses, transfers,
reservations, shipping (zones/methods/rate rules), taxes (classes/rates),
coupons, returns, refunds, reports, staff & permissions, settings (shop info,
finance, appearance, gateways, SMS), industry setup/install/update, import/
export, audit log, subscription & usage, billing (invoices/pay/cancel/print).

Absent: **domain & subdomain settings** (no route, no view), brand CRUD,
product-review moderation, abandoned carts, manual order entry, page comments,
wallet/cashback, marketing/Instagram/affiliate, ticketing, learning centre.

### C. Customer Storefront — **COMPLETE**

Home, listing/category/search/filters/sort/pagination, product detail with
multi-axis variants and gallery, cart, multi-step checkout with shipping/
coupon/OTP/gateway, payment result, customer auth, account (profile/addresses/
orders/wishlist), static pages, SEO (sitemap/robots/canonical/JSON-LD),
error/empty states, RTL, mobile.

---

## 5. Primary Rastisi journey audit

Legend: ✓ exists · ✗ absent · ◐ partial/indirect.

| # | Journey step | Route | View | Template | Form | Service | Model | Perm | Tenant isol. | Tests | Navigable | Browser-usable | Matches prototype | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `rastisi.ir` landing | ✗ | ✗ | ✗ | — | — | — | — | — | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 2 | Registration | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | — | — | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 3 | Login (owner) | ✗ | ✗ | ✗ | ✗ | ◐ (OTP infra) | ✓ | — | — | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 4 | Account dashboard | ✗ | ✗ | ✗ | — | — | — | — | — | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 5 | List of user's stores | ✗ | ✗ | ✗ | — | ✗ | ✓ | ✓ | ✓ (queryable) | ✗ | ✗ | ✗ | ✗ (prototype shows a single store) | **Missing** |
| 6 | Automatic trial store creation | ✗ | ✗ | ✗ | ✗ | ◐ `provision_default_subscription` (never called) | ✓ | — | — | ◐ service-level only | ✗ | ✗ | ✗ | **Backend only** |
| 7 | Nine-character trial identifier | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | — | ✗ | ✗ | ✗ | **Not in prototype** | **Missing (and unspecified)** |
| 8 | Trial domain `abc23xyz7.rastisi.ir` | ✗ | ✗ | ✗ | ✗ | ✗ (no auto `StoreDomain` creation) | ✓ `StoreDomain` | — | ✓ | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 9 | Store appears in "My Stores" | ✗ | ✗ | ✗ | — | — | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 10 | Enter store admin | ✓ `/admin-portal/` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ◐ **only by typing the admin host** | ✓ | ✓ | **Partial (no entry link)** |
| 11 | Choose industry | ✓ `settings-industry-*` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (inside admin) | ✓ | ◐ (prototype puts it in the signup wizard) | **Equivalent implementation** |
| 12 | Install industry template | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **Complete** |
| 13 | Configure store | ✓ `settings*` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **Complete** |
| 14 | Purchase subscription | ✓ `subscription-plans` → `billing-pay` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (inside admin) | ✓ | ◐ (prototype puts purchase in the portal) | **Equivalent implementation** |
| 15 | Confirmed SaaS billing payment | ✓ webhook + confirmation service | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **Complete** |
| 16 | Entitlement activation | — (service) | — | ✓ (usage UI) | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **Complete** |
| 17 | Choose human-readable subdomain | ✗ | ✗ | ✗ | ✗ | ✗ | ◐ `admin_subdomain` editable only in Django admin | ✗ | ✓ | ◐ model-level | ✗ | ✗ | ✗ | **Missing** |
| 18 | `chosen-name.rastisi.ir` serves storefront | ✗ (requires a `StoreDomain` row someone must create) | — | — | — | ✗ | ✓ | — | ✓ | ◐ resolution tested | ✗ | ✗ | ✗ | **Backend only** |
| 19 | Preserve/redirect original trial domain | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ (no domain history/redirect model) | — | — | ✗ | ✗ | ✗ | ✗ | **Missing** |
| 20 | Connect custom domain | ✗ UI | ✗ | ✗ | ✗ | ✗ (no DNS/HTTP verification networking) | ✓ `StoreDomain` w/ token + status | ✗ | ✓ | ◐ model/constraint tests | ✗ | ✗ | ✗ (prototype step 4) | **Backend only** |

**Journey verdict:** steps 1–9 and 17–20 are not usable in a browser. The journey
is only enterable at step 10, and only by someone who already knows the store's
admin hostname. Steps 10–16 form a solid, working middle.

---

## 6. Trial store provisioning audit (actual behaviour)

| Requirement | Actual | Evidence |
|---|---|---|
| Automatic Store creation after owner registration | **No** | No owner registration exists; `customers.signup` creates a `Customer` only |
| Exactly one default trial Store | **No** | Nothing creates a Store outside Django admin / data migrations / tests |
| Nine-character lowercase alphanumeric identifier | **No** | No generator; nearest is `Store._fallback_admin_subdomain` → `store-{public_id.hex[:12]}` (12 hex chars, prefixed, for the *admin* host) |
| Cryptographically safe / collision-resistant generation | **N/A** | `public_id` is `uuid4` (safe) but is not a 9-char trial id |
| Unique DB constraint on the identifier | **Partial** | `Store.admin_subdomain` is `unique=True`; `StoreDomain.hostname` is unique; no trial-id field exists |
| Retry on collision | **No** | No generation loop exists |
| Trial subscription creation | **Backend only** | `provision_default_subscription()` + `start_trial()` exist; called only by tests |
| Trial start/end dates | **Yes (model)** | `trial_start_at`, `trial_end_at`, `PlanVersion.trial_days` |
| Default owner Membership | **No automatic path** | `StoreMembership` + `uniq_active_owner_per_store` exist; rows are created manually |
| Initial Store status | **`PROVISIONING` default exists** | `Store.Status` = provisioning/active/suspended/closed |
| Initial hostname/subdomain | **Partial** | `admin_subdomain` auto-fills on save; **no public `StoreDomain` is ever auto-created** |
| Industry selection before/after provisioning | **After, inside merchant admin** | `settings-industry-install`; the prototype expects it during signup |
| Safe failure rollback | **N/A** | No provisioning transaction exists |
| Idempotency on retried registration | **N/A** | No registration endpoint |
| Verification-email interaction | **No** | No email verification anywhere; auth is phone/OTP-based |

---

## 7. "My Stores" dashboard audit

**The screen does not exist.** There is no route, view, or template. The data
needed to build it is available
(`StoreMembership.objects.filter(user=…, status=ACTIVE)` joined to `Store`,
`StoreSubscription`, `StoreDomain`).

Every audited element is therefore Missing: store name, trial hostname, custom
hostname, subscription state, trial days remaining, plan, store status, "Open
store", "Enter admin", "Buy subscription", "Renew", restricted/suspended state,
role badge, multi-store support, empty state, unauthorized exclusion, staff vs
owner behaviour, store switching, current-store indicator, pagination, mobile,
RTL, navigation from login, navigation back to the list.

**Prototype conflict worth flagging:** `rastisi-site/dashboard.html` is a
**single-store** owner dashboard (KPI tiles, recent orders, "your store is active
at novinshop.rastisi.ir"), *not* a multi-store list. The audit brief's "list of
the user's stores" is a newer, broader requirement. The data model supports
multi-store ownership; the prototype does not depict it.

---

## 8. Domain & subdomain lifecycle audit

| # | Capability | Status | Evidence |
|---|---|---|---|
| 1 | Generated trial hostname `<9 chars>.rastisi.ir` | **Missing** | No generator, no auto `StoreDomain` |
| 2 | Human-readable paid hostname `store.rastisi.ir` | **Backend only** | Works *if* a verified `StoreDomain` row is created manually |
| 3 | Custom domain `example.com` | **Backend only** | Same; no UI, no DNS check |
| 4 | Primary-domain selection | **Model-enforced** | `uniq_primary_domain_per_store` partial unique on `is_primary=True` |
| 5 | Previous-domain history | **Missing** | No history/alias model |
| 6 | Redirect of old hostname | **Missing** | No redirect logic; an old host simply stops resolving (404) |
| 7 | Reserved-name protection | **Partial** | `RESERVED_ADMIN_SUBDOMAINS` (www, admin, api, app, rastisi, panel, portal, billing, payments, …) guards *admin* subdomains only; **no equivalent guard for public storefront subdomains** |
| 8 | Case normalization | **Complete** | `normalize_hostname()` lowercases; `QuerySet.update()` on `hostname` is blocked to protect the invariant |
| 9 | IDN/punycode policy | **Complete** | `value.encode("idna").decode("ascii")`; rejects malformed labels, >253 chars, >63-char labels |
| 10 | DNS verification | **Missing (documented)** | Model docstring states it *"does not implement DNS/HTTP verification networking"* |
| 11 | Domain ownership verification | **Data-only** | `verification_status` (unverified/pending/verified), `verification_token` (unique when set), `verification_requested_at`, `verified_at`, with CheckConstraints binding the lifecycle — but nothing performs the check |
| 12 | TLS/certificate provisioning | **Missing** | No assumption documented or implemented |
| 13 | Duplicate hostname prevention | **Complete** | `StoreDomain.hostname` unique |
| 14 | Cross-store takeover prevention | **Complete** | Unique hostname + verified-only resolution + normalization-on-save guard |
| 15 | Suspended/expired store behaviour | **Complete** | Non-ACTIVE stores never resolve → clean 404 (ADR-83) |

**Can a subdomain be changed today?** Only by a **platform superuser editing
`Store.admin_subdomain` in Django admin** — and that changes the *admin* host,
not the storefront host. It is therefore: not available to trial users, not
available to paid owners, **not entitlement-controlled, not owner-accessible, no
cooldown, not audited as a domain event, not reversible via UI, and not
redirect-safe.**

---

## 9. Screen-by-screen comparison

See `PROTOTYPE_SCREEN_COVERAGE_MATRIX.md` for the full 68-row table with
visual / functional / navigation / responsive / RTL / security columns.

---

## 10. Navigation graph (as built)

| Role | Entry page | Available navigation | Redirect after login | Store selection | Unauthorized behaviour | Dead ends / gaps |
|---|---|---|---|---|---|---|
| **Anonymous Rastisi visitor** | *(none)* — `rastisi.ir/` serves a **storefront**, or 404 if no store matches the host | — | — | — | 404 | **Entire funnel missing.** Cannot discover plans, register, or create a store. |
| **Registered user, no store** | *(none)* | — | — | — | — | **No portal.** Such a user has nowhere to go. |
| **Trial store owner** | Must type `<admin_subdomain>.rastisi.ir/admin-portal/` | Full merchant admin | `dashboard:dashboard` | Implicit — derived from the Host | Non-member → redirect to `catalog:home` | **No "My Stores"; no way to discover the admin URL; no domain settings.** |
| **Paid store owner** | Same as trial | Same + subscription/billing pages | Same | Host-derived | Same | Same; plus **cannot choose a subdomain after paying**. |
| **Staff member** | Same host | Role-filtered nav (`merchant_permissions` context processor hides items) | `dashboard:dashboard` | Host-derived | 403 page for member-with-wrong-role; redirect for non-member | No store switcher for staff of multiple stores. |
| **Platform superuser** | `/admin/` | Django admin (all models incl. `Store`, `StoreDomain`, plans, billing) | Django admin index | N/A (global) | Non-superuser fully denied | **Currently the only way to create a Store or set a hostname.** |
| **Storefront customer** | `<store host>/` | Storefront nav, cart, account | Stays on storefront (HX-Refresh) | Host-derived | Own-records-only; foreign order → 404 | Complete. |

**Login-surface separation (verified, and correct):**

- `customers:login` — storefront customer, modal on the storefront, per-store.
- `dashboard:login` — merchant staff, **only on the admin host**; requires an ACTIVE `StoreMembership`.
- `/admin/` — Django platform admin, superuser-only (`apps/stores/admin_permissions.py`).
- **Rastisi owner login — does not exist.**

There is deliberately **no storefront→admin link** (verified: zero references to
`admin-portal` in storefront templates), which is right for tenant hygiene — but
with no portal it means the merchant admin has **no discoverable entry point at
all**. The admin does link back to the storefront.

---

## 11. Data & ownership analysis

Actual relationships:

- `User` (Django auth) ←→ `Store` **many-to-many via `StoreMembership`**
  (`role`, `status`, `invited_by`, `accepted_at`, `revoked_at`).
- `StoreMembership` constraints: `uniq_membership_per_store_user` (one row per
  user+store) and `uniq_active_owner_per_store` (**exactly one ACTIVE owner per
  store**).
- `Store` 1—1 `ShopSettings`, `FooterSettings`, `StoreBillingAccount`.
- `Store` 1—* `StoreDomain` (one `is_primary` per store, partial-unique).
- `Store` 1—* `StoreSubscription`, exactly one of which is `is_current`
  (partial-unique); `StoreSubscription` → `PlanVersion` (PROTECT) → `Plan`.
- `SubscriptionInvoice` → store + subscription + plan version, with frozen
  snapshots.
- `Customer` is a **storefront** identity, scoped per store — unrelated to the
  owner `User`.
- `IndustryTemplate` → `StoreIndustryInstallation` records what was installed.

Answers:

| Question | Answer |
|---|---|
| Can one user own multiple stores? | **Yes** — nothing prevents multiple OWNER memberships across different stores. |
| Can one user be staff in multiple stores? | **Yes.** |
| Can a store have multiple owners? | **No** — exactly one ACTIVE owner (DB-enforced); ownership moves via `transfer_ownership`. |
| What happens when an owner registers? | **Nothing** — there is no owner registration. |
| What happens when a store is created? | `admin_subdomain` auto-fills if omitted; `ShopSettings`/`FooterSettings` need explicit `provision_for`; no subscription, no membership and no domain are created automatically. |
| What happens when a subscription is purchased? | Invoice → payment attempt → server-verified confirmation → subscription activated/renewed → entitlements refreshed (5B). **No hostname change is triggered.** |
| What event permits a hostname change? | **None is implemented.** The prototype implies "after plan selection"; the brief implies "after confirmed payment". |
| Who may rename the store? | `Store.name` via merchant settings (`settings-shop-info`); `admin_subdomain` only via Django admin (superuser). |
| What identifier is permanent? | `Store.public_id` (UUID4, `editable=False`). `slug` and `admin_subdomain` are mutable by a superuser. |

**Prototype ↔ data-model conflicts:**

1. Prototype `dashboard.html` = one store per owner; data model = many.
2. Prototype `store-setup.html` = owner **chooses** the subdomain at signup;
   brief = **auto-generated 9-char trial** then rename after payment;
   implementation = neither.
3. Prototype has **no domain-history/redirect** concept; the brief requires
   preserving/redirecting the trial hostname; the model has no alias/history
   table.

---

## 12. Test coverage map (journey-critical steps)

| Journey step | Unit | Service | View | Tenant isolation | Security/adversarial | Browser/E2E | Manual QA |
|---|---|---|---|---|---|---|---|
| Rastisi landing/marketing | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Owner registration | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Owner login | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| My Stores | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Trial store provisioning | ✗ | ◐ (`test_management_and_isolation.py` covers `provision_default_subscription` in isolation) | ✗ | ✗ | ✗ | ✗ | ✗ |
| 9-char trial id | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Trial hostname | ✗ | ✗ | ✗ | ◐ (resolution tests use hand-made domains) | ✗ | ✗ | ✗ |
| Enter store admin | ✓ | ✓ | ✓ (`test_admin_host_enforcement`, `test_admin_superuser_gate`) | ✓ | ✓ | ✗ | ✓ |
| Industry install | ✓ | ✓ (`test_industry_template_service`) | ✓ | ✓ | ◐ | ✗ | ✓ |
| Configure store | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| Purchase subscription | ✓ | ✓ | ✓ (`test_billing_views`) | ✓ | ✓ | ✗ | ✓ |
| Payment confirmation | ✓ | ✓ (`test_confirmation_activation`) | ✓ | ✓ | ✓ (webhook adversarial) | ✗ | ✓ |
| Entitlement activation | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| Subdomain choice | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Trial-host redirect | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Custom domain | ◐ (model/constraint/normalization tests) | ✗ | ✗ | ◐ | ◐ | ✗ | ✗ |

Explicit classifications:

- **Not tested at all:** registration, owner login, My Stores, end-to-end trial
  provisioning, 9-char id, subdomain choice, trial-host redirect.
- **Only indirectly tested:** trial hostname (only as a pre-made `StoreDomain` in
  resolution tests).
- **Tested only at model level:** the custom-domain verification lifecycle
  (constraints/normalization) — no service or view exercises it.
- **Tested without browser navigation:** `provision_default_subscription`.
- **SQLite-only caveat:** the whole suite runs on SQLite; one billing
  numbering-contention test is **PostgreSQL-specific** and is skipped
  (`skipUnless(connection.vendor == "postgresql")`).
- **No browser/E2E tests exist** for any journey step (ADR-92 records this as a
  deliberate complement-not-substitute stance; the manual QA checklist is the
  human E2E script).

**The 3046-test baseline must not be read as journey completeness** — it covers
the *implemented middle* (systems B and C) densely and the *missing funnel*
(system A) not at all.

---

## 13. Security findings

Positive (verified):

- Fail-closed Host→Store resolution; inactive/suspended/unknown → 404, never a
  cross-tenant render.
- Hostname normalization rejects scheme/credentials/path/query/fragment/port,
  lowercases, converts IDN→punycode, enforces DNS lengths; bulk `update()` on
  `hostname` is blocked to protect the invariant.
- Merchant admin requires admin-host + authentication + ACTIVE membership;
  Django admin is superuser-only.
- Storefront: server-side price/variant validation, own-orders-only account,
  CSRF throughout, signature-verified billing webhooks.

Findings:

| ID | Severity | Finding |
|---|---|---|
| SEC-1 | **High (latent)** | **No public-subdomain reserved-name protection.** `RESERVED_ADMIN_SUBDOMAINS` guards only `admin_subdomain`. When storefront subdomain selection is built, an owner could otherwise claim `www`, `api`, `mail`, `billing`, or `rastisi` as a public host. Must be enforced *before* shipping subdomain choice. |
| SEC-2 | **High (latent)** | **Domain ownership is never actually verified.** `verification_status` can be set to `verified` with no DNS/HTTP proof. Any code path (or admin action) flipping that flag effectively grants a hostname. Shipping a custom-domain UI without a real verifier would enable domain hijack of a host the merchant does not own. |
| SEC-3 | Medium | **Store creation is superuser-only today** — safe now, but the future registration endpoint becomes a new unauthenticated attack surface (mass store creation / resource exhaustion). Rate limiting and idempotency must be designed in, not bolted on. |
| SEC-4 | Medium | **No trial-host redirect** means renaming a store silently breaks every existing link and indexed SEO URL; with no history table, the abandoned hostname could later be claimed by a *different* store. |
| SEC-5 | Low | No TLS/certificate provisioning story is documented for custom domains; a partially-configured domain will surface a certificate error rather than a controlled message. |

---

## 14. UX findings

- **No front door.** The merchant admin is unreachable without knowing a
  hostname. This is the dominant UX failure.
- **Industry choice happens late.** The prototype makes industry the *first*
  signup step; the implementation buries it in `settings/industry/…` after the
  store already exists. Functionally equivalent, experientially different.
- **Subscription purchase lives in the merchant admin**, not the portal, so a
  prospective customer cannot compare or buy plans before having a store.
- **No store switcher** for owners/staff with multiple stores.
- **Domain settings are invisible to merchants** — the single most-expected
  self-service setting on a SaaS store builder.
- Prototype extras absent from the panel (wallet/cashback, marketing, affiliate,
  ticketing, learning centre, abandoned carts, manual orders, brand CRUD, review
  moderation) each represent a merchant expectation the prototype sets.

---

## 15. Missing functionality (gap register)

| Gap ID | Pri | System | Prototype ref | Current implementation | Required change | Dependencies | Security risk | Data-migration risk | Slice | Required tests |
|---|---|---|---|---|---|---|---|---|---|---|
| **G-01** | **P0** | A | `register.html` | None; `customers.signup` is storefront-only | Owner registration (name/mobile/email/password, terms) creating a `User` | New `apps.portal` | Rate-limiting, enumeration-safe errors, CSRF | New models only | Portal app + auth | Unit, view, adversarial (duplicate/rate/enumeration) |
| **G-02** | **P0** | A | `login.html` | None | Owner login/logout/password recovery distinct from the other two logins | G-01 | Open redirect on `next`, session fixation | None | Portal auth | View, redirect-safety, role-confusion |
| **G-03** | **P0** | A | `store-setup.html`, `store-success.html` | `provision_default_subscription` uncalled | Transactional trial provisioning: Store + OWNER Membership + trial subscription + settings + default warehouse + public hostname; idempotent with rollback | G-01, subscriptions | Mass-creation abuse | Creates tenants | Provisioning service | Service, idempotency, rollback, isolation |
| **G-04** | **P0** | A | *(brief only — no prototype)* | None | **Product decision first:** auto 9-char trial id vs the prototype's owner-chosen subdomain. Then implement the chosen scheme with a unique constraint + collision retry | G-03 | Predictable ids enable enumeration | New field/index | Identifier scheme | Unit (collision/format), constraint |
| **G-05** | **P0** | A | `dashboard.html` (+ multi-store) | None | "My Stores": all ACTIVE memberships with name, hostname, plan, status, trial days, role, and Enter-admin/Open-store/Buy actions | G-01, G-03 | Must exclude non-member stores | None | Portal dashboard | View, isolation (foreign store absent), empty state |
| **G-06** | **P0** | A/B | `store-setup.html` step 3 | Superuser-only `admin_subdomain` edit | Owner-facing storefront subdomain selection: entitlement-gated, reserved-name-blocked, audited | G-03, G-04, SEC-1 | **Reserved-name takeover** | Creates `StoreDomain` | Subdomain service + UI | Unit (reserved/format), permission, audit, isolation |
| **G-07** | **P1** | A/B | `store-setup.html` step 3 → success | No redirect/history | Preserve the old hostname and 301 to the new primary; prevent reuse by another store | G-06 | Hostname reuse/hijack | New history model | Domain history | Redirect, reuse-prevention, isolation |
| **G-08** | **P1** | B | `store-setup.html` step 4 | `StoreDomain` model only | Merchant domain-settings UI + **real DNS/HTTP verification** before `verified` | G-06, SEC-2 | **Domain hijack if unverified** | None | Domain UI + verifier | Verification success/failure, adversarial claim |
| **G-09** | **P1** | A | `plans.html`, `index.html`, `features.html`, `how-it-works.html`, `faq.html`, `about.html`, `contact.html`, `categories.html` | None | Public marketing pages; plans rendered from published `PlanVersion`; industries from `IndustryTemplate` | G-01 | Contact-form spam | None | Marketing pages | View, published-only, SEO |
| **G-10** | **P1** | A | `store-setup.html` step 5 / `subscription.html` | Purchase exists only inside the merchant admin | Portal-side plan selection and purchase entry handing off to existing billing | G-05, billing | Price integrity (server-side only) | None | Portal→billing bridge | View, price-forgery, idempotency |
| **G-11** | **P2** | B | `brands.html` | `Brand` model + storefront filter | Brand CRUD in merchant admin | — | Low | None | Brand admin | CRUD, isolation |
| **G-12** | **P2** | B | `product-comments.html` | `Review.is_approved` with no UI | Review moderation queue | — | Low | None | Moderation UI | View, permission |
| **G-13** | **P2** | B | `draft-orders.html` | None | Abandoned-cart list | — | PII exposure | None | Abandoned carts | View, isolation |
| **G-14** | **P2** | B | `order-new.html` | None | Merchant-side manual order entry | inventory/pricing | Price/stock bypass | None | Manual orders | Service, stock, price |
| **G-15** | **P2** | B | `order-report.html`, `product-report.html`, `customer-report.html`, `sms-report.html` | Generic reports | Per-report parity with the prototype | — | Low | None | Reports | View, bounded queries |
| **G-16** | **P2** | B | `order-settings.html` | Scattered across settings | Dedicated order-policy screen | — | Low | Possibly | Order settings | View |
| **G-17** | **P2** | A/B | — | Superuser-only store creation | Rate limiting + abuse controls on registration/provisioning | G-01, G-03 | **Resource exhaustion** | None | Abuse controls | Rate-limit tests |
| **G-18** | **P3** | B | `wallet-transactions.html`, `cashback-settings.html` | No models | Wallet/cashback domain | Large | Financial correctness | New models | Wallet domain | Full domain suite |
| **G-19** | **P3** | B | `marketing.html`, `instagram.html`, `invite-friends.html` | None | Growth/marketing tooling | — | Low | New models | Marketing | View |
| **G-20** | **P3** | B | `ticketing.html` | None | Support ticketing | — | PII | New models | Ticketing | View, isolation |
| **G-21** | **P3** | B | `guide.html` | None | Learning centre | CMS | Low | None | Static | View |
| **G-22** | **P3** | B/C | `storefront-brands.html`, `page-comments.html` | Filter only / none | Brand landing page; page comments | — | Low | Maybe | Storefront extras | View, SEO |
| **G-23** | **P3** | A/B | — | None | Store switcher for multi-store owners/staff | G-05 | Wrong-tenant action | None | Switcher | View, isolation |
| **G-24** | **P3** | All | — | No E2E | Browser E2E for the full funnel once it exists | G-01…G-06 | — | None | E2E harness | Playwright journey |

**P0 = 6 · P1 = 4 · P2 = 7 · P3 = 7 · Total = 24.**

---

## 16. Obsolete prototype elements

| Element | Why obsolete |
|---|---|
| `docs/docs/product/spec/shop-admin-panel.html` | Superseded by the richer `merchant-panel-x25` set; the implemented admin already exceeds it. |
| `novinshop-…/store-editor.html` ("استودیو ساخت فروشگاه") | A drag-and-drop visual page builder — explicitly ruled out by ADR-91 (theming is per-store CSS variables, not a builder). Should be formally retired or re-scoped. |
| `rastisi-site/dashboard.html` (as a *single-store* dashboard) | Partially obsolete: both the data model and the audit brief assume multi-store ownership. Keep the visual language; discard the single-store assumption. |
| `rastisi-site/checkout.html`, `rastisi-site/categories.html` | Duplicate storefront concerns already delivered by System C; as *Rastisi-site* screens they look like leftovers from the template kit rather than portal requirements. |

---

## 17. Recommended implementation sequence

Each step is a shippable, testable slice.

1. **Product decision (no code):** resolve the G-04 conflict — auto 9-char trial
   hostname *or* the prototype's owner-chosen subdomain (or both: auto-assign at
   creation, rename after payment). Record it as an ADR. Everything below
   depends on this.
2. **`apps.portal` skeleton + owner auth (G-01, G-02).** Registration, login,
   logout, recovery on a dedicated route namespace, deliberately separate from
   `customers` and `dashboard`. Enumeration-safe errors and `next` validation.
3. **Trial provisioning service (G-03, G-04, G-17).** One atomic, idempotent
   service: Store + OWNER Membership + `ShopSettings`/`FooterSettings` + default
   warehouse + trial subscription + initial public `StoreDomain`, with rollback
   and rate limiting. Wire it to registration.
4. **My Stores (G-05).** The first screen that makes the platform navigable;
   include the Enter-admin link that currently exists nowhere.
5. **Subdomain selection + reserved names (G-06, SEC-1).** Entitlement-gated,
   owner-only, audited.
6. **Hostname history + redirects (G-07, SEC-4).**
7. **Custom-domain UI + real verification (G-08, SEC-2).** Do not ship the UI
   before the verifier.
8. **Marketing pages + portal purchase bridge (G-09, G-10).**
9. **Merchant-admin parity gaps (G-11…G-16).**
10. **E2E funnel coverage (G-24)**, then P3 items as product priorities dictate.

---

## 18. Exact validation results

All commands run at commit `3f172f1`, read-only, on SQLite. No test or
application file was modified during this audit.

| Command | Result | Exit |
|---|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` | 0 |
| `python manage.py makemigrations --check` | `No changes detected` | 0 |
| `python manage.py migrate` | applied cleanly to a fresh dev DB (the container had been reset) | 0 |
| `python manage.py verify_subscription_consistency --strict` | `هیچ ناسازگاری‌ای یافت نشد.` | 0 |
| `python manage.py verify_billing_consistency --strict` | `هیچ ناسازگاریِ صورتحسابی یافت نشد.` | 0 |
| `python manage.py verify_inventory_consistency --strict` | `موجودیِ همه‌ی کالاها/تنوع‌ها با انبارها سازگار است.` | 0 |
| `python manage.py validate_industry_templates --strict` | `هیچ قالبی با این فیلتر یافت نشد.` | 0 |
| `python manage.py test apps.stores apps.subscriptions apps.billing apps.customers` | **Ran 537 tests — OK (skipped=1)** | 0 |
| `python manage.py test apps.dashboard apps.catalog apps.cart apps.orders apps.content` | **Ran 2322 tests — OK** | 0 |

The first suite covers stores, membership, tenant routing, domain handling,
subscriptions, billing and storefront-customer authentication. The single skip
is the PostgreSQL-only billing invoice-numbering contention test
(`skipUnless(connection.vendor == "postgresql")`).

The second suite covers the merchant dashboard, industry installation, the
storefront, cart, checkout and CMS. Together these two focused runs execute
**2859 tests, all passing**, which is consistent with the 3046-test Checkpoint 6
full-suite baseline (the remainder lives in `apps.core`, `apps.blog` and
`apps.sms`, not re-run here).

*Honest note on a discarded result:* an earlier attempt at the second suite was
executing when the container wiped and restored the working tree mid-run; it
reported `Ran 1343 tests — FAILED (errors=59)`. Those errors were artefacts of
the files disappearing underneath the running process, **not** real defects —
the clean re-run above found 2322 tests with no import errors and zero failures.
The failing figure is recorded here only so it is not mistaken for a finding if
it is seen in logs.

**Git state at audit time:** the container reset the local checkout to an old
commit (twice) with a clean working tree; it was restored each time with
`git fetch origin` + `git reset --hard origin/claude/docs-prototypes-review-jxm6aw`
to `3f172f1`. No uncommitted work existed, so nothing was discarded.
