# SaaS Foundation Architecture

Status: Foundation stage. PR 2 (`Store`/`StoreDomain`/`StoreMembership`), PR 3
(Store resolution infrastructure, §6 below), and PR 4 (Store ownership for
`ShopSettings`/`FooterSettings`/`FooterTrustBadge`/`FooterPaymentLogo`, §9
below) have merged. PR 4.1 (explicit Store context propagation for pricing
and SMS, §11 below) is implemented on branch
`claude/store-context-service-propagation` and open as a pull request — not
yet merged into the canonical base branch as of this writing. See
`SAAS_MIGRATION_PLAN.md` for the full staged sequence and current status of
each PR.

## 1. Platform vs. Store

The application is not the store. The application is the platform runtime that
hosts one or more Stores. `Store` (`apps.stores.Store`) is the authoritative
tenant and data-ownership boundary for all merchant commerce data.

```text
Commerce SaaS Platform
├── Store: Akhlaghi
├── Future Store B
├── Future Store C
│
├── Merchant Administration
│   └── Store-scoped operational management (per-Store dashboard, catalog, orders)
│
└── Platform Operations
    └── Platform lifecycle and infrastructure management (provisioning,
        billing, cross-Store observability, support tooling)
```

Every future commerce record must be either:

1. platform-global by explicit, documented design (e.g. a shared payment
   provider catalog, platform-level configuration); or
2. owned directly (a foreign key to `Store`) or indirectly (a foreign key to
   something that is itself Store-owned) by exactly one `Store`.

No record may be ambiguously scoped. If ownership is unclear for an existing
model, that is treated as an open risk to resolve in the PR that migrates that
model, not something to paper over with a global default.

## 2. Store as Tenant Boundary

`Store` is a new, independent domain entity. It is **not** `Vendor`. `Vendor`
today is a single-store, multi-seller construct (`apps.catalog.Vendor`) used
inside product/order ownership; it does not represent a tenant and its final
domain meaning (marketplace seller vs. supplier vs. something else) is
deferred to a dedicated catalog-domain review. See
`SAAS_DOMAIN_DECISIONS.md` for the explicit decision record.

`Store` provides:

* a stable, non-guessable public identifier (`public_id`, UUID) for external
  references (APIs, billing, support tooling) that must not leak sequential
  database IDs;
* a platform-global unique `slug` for human-readable identification and
  future path-based routing;
* one explicit lifecycle `status` (`provisioning`, `active`, `suspended`,
  `closed`) — see `SAAS_DOMAIN_DECISIONS.md` for why this replaces ambiguous
  boolean flags.

`Store` intentionally has no owner FK, no billing/subscription/theme/payment
fields, and no domain fields. Those are separate concerns (see below).

## 3. Merchant Administration vs. Platform Operations

Two distinct authorization/operational contexts exist conceptually, though
only the data model for the first is created in this stage:

* **Merchant Administration** — actions scoped to a single Store, performed
  by users who hold a `StoreMembership` in that Store (owner, administrator,
  catalog manager, order manager, content editor, analyst). Merchant
  Administration must never implicitly reach across Stores.
* **Platform Operations** — actions that operate on the platform itself
  (provisioning Stores, suspending a Store, billing, infrastructure). This is
  a Django-admin/operator concern in the current stage. Platform operators do
  not automatically receive unrestricted merchant-data access — that
  boundary is a documented decision (`SAAS_DOMAIN_DECISIONS.md`), not yet
  code-enforced beyond normal Django-admin `is_staff` gating.

Neither authorization enforcement nor dashboard scoping is implemented in
this PR (out of scope — see `SAAS_MIGRATION_PLAN.md`).

> **Update (Merchant Admin Authorization and Routing Foundation, "Phase
> 1B"):** Merchant Administration authorization described above is now
> implemented: `apps.stores.authorization` enforces exactly the
> `StoreMembership` role list named here (owner/administrator/catalog
> manager/order manager/content editor/analyst) via a granular permission
> registry, applied to every merchant dashboard view. Platform Operations
> (`/admin/`) is still Django-admin `is_staff`/`is_superuser` gating only,
> as described above — that boundary is unchanged by this update. See
> ADR-16 in `SAAS_DOMAIN_DECISIONS.md` for the admin-subdomain/routing side
> of this same PR.

## 4. Store Ownership: Direct and Indirect

* **Direct ownership**: a model has a `ForeignKey(Store)`.
* **Indirect ownership**: a model is owned by something that is itself
  Store-owned (e.g. a future `OrderItem` owned via `Order.store`).

Every model that is added or migrated in later PRs must be classified as one
or the other, or explicitly declared platform-global with a written
rationale. "No FK, no rationale" is not an acceptable end state for a
commerce record.

## 5. Shared PostgreSQL Tenancy

The chosen tenancy strategy is a **shared database** with explicit ownership,
not schema-per-tenant or database-per-tenant, and not a third-party
multi-tenancy framework (see `SAAS_DOMAIN_DECISIONS.md` for the full
rejection list and rationale). This keeps operational complexity low for a
platform with a small number of Stores in its early life, while remaining
compatible with PostgreSQL Row-Level Security (RLS) as a future
defense-in-depth layer — RLS is explicitly not implemented in this stage.

Isolation is layered:

1. **Service-layer authority** — Store-scoped services are the authoritative
   place that resolves "which Store" for every read/write. Views and
   templates must not independently decide Store scope once later PRs
   introduce Store-scoped models.
2. **Model validation** — `clean()`/constraint-level checks as defense in
   depth against a service-layer bug, not the primary mechanism.
3. **Database constraints** — `UniqueConstraint`s and, where representable,
   `CheckConstraint`s enforce invariants the database can actually express
   (e.g. one primary domain per Store). Plain `ForeignKey` existence is not,
   by itself, tenant-integrity enforcement — a FK only proves a related row
   exists, not that it belongs to the same Store as its parent.
4. **Adversarial tests** — every future Store-scoped feature must ship with
   tests that attempt cross-tenant access and assert it is rejected.
5. **Future RLS** — a defense-in-depth layer to be added once the
   application-level model above is proven, not a substitute for it.

## 6. Request Store Context

Implemented (PR — "Store Resolution Infrastructure in Compatibility Mode").

### 6.1 Resolution flow

`apps.stores.resolution` is the single authoritative module that decides
"which Store does this request belong to." `StoreResolutionMiddleware`
(`apps.stores.middleware`) runs this resolution once per request and
attaches the result to `request.store` (a `Store` instance, or `None`).

The resolution source of truth is **the HTTP `Host` header, resolved
through `StoreDomain`** — nothing else. Concretely, for a given
`request.get_host()` value:

1. the port is stripped safely (including bracketed IPv6 literals);
2. if the resulting host is on the (small, centralized, overridable)
   development-host allowlist, the request goes through the compatibility
   fallback (§6.3) instead of the authoritative path below;
3. otherwise, the host is normalized via the existing authoritative
   `apps.stores.hostnames.normalize_hostname`;
4. the normalized hostname is looked up against `StoreDomain.hostname`
   (globally unique, so this lookup can never be ambiguous);
5. a match resolves only if it passes the **routing eligibility policy**
   (§6.2); anything else — no match, or a match that fails eligibility —
   resolves to `None` for callers that want a non-raising result, or a
   specific, distinguishable exception for callers (tests, future services)
   that need to know why.

Hostname is the authoritative **storefront** tenant source: a caller can
never supply a Store ID, and resolution never consults the authenticated
user, session state, `Vendor`, `Product`, `Cart`, `StoreMembership`, or any
other business data. See §6.4 for why that separation matters.

### 6.2 Routing eligibility policy

A `StoreDomain` may route a request only when **both**:

* its Store's `status` is `ACTIVE` (not `provisioning`, `suspended`, or `closed`);
* its own `verification_status` is `VERIFIED` (not `unverified`, `pending`, or `failed`).

This is deliberately conservative: an unverified, pending, or failed domain,
or a domain whose Store is not active, never resolves — even though the
hostname row genuinely exists. This is the same "fail closed rather than
guess" posture the compatibility fallback also follows (§6.3).

### 6.3 Temporary Akhlaghi / local-development compatibility mode

Akhlaghi must keep working locally before it has a real, verified
`StoreDomain`. A narrow, explicitly isolated fallback allows a fixed
allowlist of development hosts (`localhost`, `127.0.0.1`, `[::1]`,
`testserver` — Django's own test-client host) to resolve to the Akhlaghi
Store, but **only** when all of the following hold at resolution time:

* the (port-stripped) host is an **exact** match to an entry in the
  development-host allowlist — checked first, and *instead of* the
  authoritative `StoreDomain` lookup, not after it fails. A real, verified
  `StoreDomain` row happening to exist for one of these exact strings
  (e.g. `"127.0.0.1"`, which is unusually a syntactically valid hostname)
  would never be consulted — the compatibility path always wins for an
  exact allowlist match, and the authoritative lookup is never attempted
  for it. No legitimate merchant would ever use a loopback address as a
  real custom domain, so this is an accepted, tested quirk of the
  isolation design, not a tenant-isolation risk;
* the match is exact, never a substring or suffix — `localhost.example.com`
  and `127.0.0.1.example.com` are *not* development hosts and go through
  the authoritative path like any other hostname (adversarially tested);
* exactly one `Store` exists in the entire database, **regardless of that
  Store's own status** — a second Store that is merely provisioning,
  suspended, or closed still disables the fallback, exactly like an active
  one (adversarially tested per status);
* that sole Store's slug is `"akhlaghi"`;
* that sole Store is `ACTIVE`.

**This is temporary and fails closed, not a permanent behavior.** The
instant a second `Store` is created anywhere on the platform, the fallback
stops resolving anything — it does not fall back to "the first Store" or
any other heuristic; it raises internally and callers see `None`. This
property is directly tested (`apps.stores.tests.test_resolution.
CompatibilityModeTests`) and must not be weakened by any later change.

**Allowlist configuration safety.** `STORES_DEVELOPMENT_HOST_ALLOWLIST`
must be a list/tuple/set of hostnames. A bare string is rejected with
`django.core.exceptions.ImproperlyConfigured` rather than silently accepted
— Python iterates a string character-by-character, so a naive
`STORES_DEVELOPMENT_HOST_ALLOWLIST = "prod.example.com"` would otherwise
silently decompose into single-character "hosts" that can never match a
real Host header, quietly disabling the allowlist instead of doing what
was obviously intended. Misconfiguration fails loudly (every request
raises) rather than failing silently.

### 6.4 Separation from authentication and authorization

Tenant resolution, authentication, authorization, and data filtering are
four separate concerns, and this PR implements **only the first**:

* **Tenant resolution** (this middleware) — which Store is this request for?
* **Authentication** (`AuthenticationMiddleware`) — who is the user?
* **Authorization** (not implemented anywhere yet) — what may they do in
  this Store?
* **Data filtering** (not implemented anywhere yet) — which rows may this
  operation read or mutate?

`StoreResolutionMiddleware` never reads `request.user`, never touches the
session, never consults `StoreMembership`, and never makes an authorization
decision or redirects — it only ever sets `request.store`. Nothing in the
codebase consumes `request.store` yet; it is infrastructure for future PRs.

### 6.5 Middleware ordering

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.stores.middleware.StoreResolutionMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
```

`StoreResolutionMiddleware` runs immediately after `SecurityMiddleware`
(Django's own host/security processing) and, critically, **before**
`SessionMiddleware` and `AuthenticationMiddleware`. This is deliberate: it
structurally guarantees Store resolution cannot depend on session or
authentication state, since neither has run yet when this middleware
executes — the ordering itself enforces the §6.4 separation, rather than
relying on code review to keep it that way.

### 6.6 Reverse-proxy trust boundary (operational precondition, not code in this PR)

Resolution trusts `request.get_host()` completely — Django's own Host-header
parsing and `ALLOWED_HOSTS` validation. That trust model has one sharp edge
that is not, and cannot be, fixed by application code alone: Django's
`USE_X_FORWARDED_HOST` setting. Verified in this repository's
`shop_core/settings.py`: it is **not set**, so Django's default (`False`)
applies, and `get_host()` uses only the actual `Host` header — an
`X-Forwarded-Host` header is inert (directly demonstrated by
`apps.stores.tests.test_resolution.ForwardedHostTests.
test_x_forwarded_host_is_ignored_by_default`).

If this platform is ever deployed behind a reverse proxy and
`USE_X_FORWARDED_HOST = True` is set to make `get_host()` see the proxy's
original-request hostname, `get_host()` switches to preferring
`X-Forwarded-Host` over `Host`
(`test_x_forwarded_host_is_honored_once_explicitly_enabled` demonstrates
this with Django's own machinery, unmodified by this PR). **This is only
safe if the proxy is trusted to set or strip that header on every request
it forwards** — otherwise any client that can reach the application
directly (or send an arbitrary `X-Forwarded-Host` through a
misconfigured/permissive proxy) can influence Store resolution as
completely as if `ALLOWED_HOSTS` didn't exist. This is a deployment/proxy
configuration responsibility, not something `apps.stores.resolution` can
verify at runtime — do not enable `USE_X_FORWARDED_HOST` without first
confirming the fronting proxy strips client-supplied `X-Forwarded-Host`
headers.

`SECURE_PROXY_SSL_HEADER` is unrelated to this concern — it affects only
`request.is_secure()`/scheme detection, not `get_host()` or Store
resolution, and is unset unless `DJANGO_SECURE_PROXY_SSL_HEADER` is configured.
When it is configured, `apps.core.middleware.TrustedProxyHeaderMiddleware`
(first in `MIDDLEWARE`) removes that header from every request whose direct peer
is not in `DJANGO_TRUSTED_PROXY_CIDRS`, so a client reaching Django directly
cannot spoof HTTPS detection. Client-IP trust (`apps.core.services.client_ip`) is
likewise independent of Store/host resolution, which is unchanged. A production
system check also rejects `USE_X_FORWARDED_HOST = True`.

### 6.7 Explicit non-goals of this PR

* No `Store` foreign key was added to any existing commerce/content model.
* `ShopSettings`/`FooterSettings` were not split or tenant-scoped.
* No caching was introduced — resolution is a bounded query every time
  (see the PR's own report for exact query counts).
* No DNS/HTTP domain-verification networking.
* No dashboard authorization changes, and `StoreMembership` is not consulted.
* No second real Store was provisioned, and no production domain was
  invented for Akhlaghi.

## 7. Media, Cache, Session and Background-Job Isolation Principles

These are documented now as forward-looking principles; none are implemented
in this PR:

* **Media**: future Store-owned media (product images, logos, etc.) must be
  stored under a path or storage backend that is unambiguously attributable
  to a Store, so that a misconfigured storage backend cannot serve one
  Store's media as another's.
* **Cache**: any cache key that stores or serves Store-scoped data must
  include the Store identifier in the key. Global cache keys (e.g. the
  current singleton `ShopSettings.load()` cache-like `get_or_create(pk=1)`
  pattern) must not be reused unscoped once `ShopSettings` becomes
  Store-owned.
* **Sessions**: user sessions may span multiple Store memberships (a user
  can belong to several Stores); session data must not assume a single
  implicit Store for a user.
* **Background jobs**: none exist in the current codebase. Any future
  background job that touches Store-owned data must carry an explicit Store
  identifier as a job argument — never inferred from ambient/global state.

## 8. What PR 3 Did Not Change

PR 3 added a new, self-contained `apps/stores` app. It did not add a
`Store` foreign key to any existing model, did not change any existing
migration, view, template, service, or middleware behavior, and did not
change `INSTALLED_APPS` request/response behavior. The application behaved
exactly as it did before that PR. §9 below describes the first PR that
does add `Store` foreign keys to existing models.

## 9. Store Ownership for Core Settings and Footer Configuration

Implemented (PR 4 — "Tenant Ownership for Existing Core and Footer
Settings"; see `SAAS_MIGRATION_PLAN.md` PR 4 for status).

### 9.1 What became Store-owned

* `apps.core.ShopSettings` — a `OneToOneField("stores.Store", related_name="shop_settings")`.
  Exactly one row per `Store`, never a platform-wide singleton. No field was
  renamed, moved, or removed; branding/theme tokens and SMS credentials stay
  on this model exactly as ADR-10 recorded (splitting `ShopSettings` remains
  a separate, later decision).
* `apps.content.FooterSettings` — the same `OneToOneField` pattern, same
  rationale, same "no split" constraint.
* `apps.content.FooterTrustBadge` / `apps.content.FooterPaymentLogo` — a
  plain (non-unique) `ForeignKey("stores.Store")` directly on each model,
  **not** mediated through `FooterSettings`. Both models were, and remain,
  independently queried and independently managed rows (their own dashboard
  list/create/edit/delete/toggle views, never joined through
  `FooterSettings` to reach them) — direct Store ownership matches how they
  are actually used, rather than inferring ownership from the fact that the
  storefront happens to render them inside the same footer region as
  `FooterSettings`.

`SocialLink`, `Menu`/`MenuItem`, `ContentPage`, `HeroSlide`, and
`PromotionalBanner` explicitly did **not** gain Store ownership in this PR —
scoping those remains PR 8's job (`SAAS_MIGRATION_PLAN.md`).

### 9.2 Migration sequence

Each app follows the same three-migration, expand-contract sequence used
throughout this plan (see "Cross-cutting distinctions" in
`SAAS_MIGRATION_PLAN.md`):

1. **Schema** — add the `store` field as nullable.
2. **Backfill** (`RunPython`, historical models via `apps.get_model`) —
   resolve Akhlaghi by exact slug (`Store.objects.get(slug="akhlaghi")`,
   never `.first()`, never a hard-coded primary key) and assign every
   currently-unowned row to it. Zero or more-than-one Akhlaghi Store raises
   `RuntimeError` — the migration refuses to guess or to silently create a
   second Akhlaghi Store. The reverse of the backfill only clears the
   `store` reference (`update(store=None)`) — it never deletes a
   `ShopSettings`/`FooterSettings`/`FooterTrustBadge`/`FooterPaymentLogo`
   row, because those are real merchant configuration data, not disposable
   scaffolding.
3. **Non-null enforcement** — once backfill has run, `AlterField` makes
   `store` mandatory. Unlike PR 3's `Store` foundation, this enforcement is
   not deferred to PR 12: with only Akhlaghi as a tenant today, the
   backfill migration itself guarantees zero unowned rows remain before
   this step runs, so there is no reason to leave the column nullable in
   the interim.

### 9.3 Retrieval and the temporary compatibility mode

`ShopSettings.load(store=None)` and `FooterSettings.load(store=None)` share
one contract:

* **Explicit `store` given** — returns only that Store's row, or raises a
  dedicated `*NotProvisionedError` if it has none yet. It never falls back
  to another Store's row and never materializes one at read time.
* **No `store` given (compatibility mode)** — delegates to the same
  `apps.stores.resolution.resolve_compatibility_store()` fail-closed check
  PR 3's compatibility fallback already uses (exactly one, active,
  `"akhlaghi"`-slugged Store). The function was promoted from private
  (`_resolve_compatibility_store`) to public for exactly this reuse — it is
  still narrowly the "is there exactly one active Akhlaghi Store" check,
  not a general-purpose "give me a default Store" helper, and no behavior
  of PR 3's own hostname resolution changed. The moment a second `Store`
  exists, this path raises `CompatibilityFallbackUnavailableError` instead
  of guessing.

This replaces the previous, permanent `get_or_create(pk=1, defaults=...)`
singleton pattern, which is now removed from both models' runtime code:
missing provisioning is a visible, distinct error, not something that
silently repairs itself the next time the row is read.

### 9.4 Provisioning boundary

`ShopSettings.provision_for(store)` and `FooterSettings.provision_for(store)`
are the one explicit, sanctioned way to create a new Store's settings rows.
Both are `get_or_create`-based classmethods: atomic, idempotent, and never
overwrite an existing row's values. Neither creates any `FooterTrustBadge`
or `FooterPaymentLogo` rows — no default trust badges or payment logos are
implied by provisioning a Store, since none were approved as a genuine
default. Nothing on the read path calls `provision_for` automatically;
provisioning a Store's settings is a distinct, explicit step, not a hidden
side effect of the next page render.

### 9.5 Request-time integration

`apps.core.context_processors.shop_settings` and
`apps.content.context_processors.footer_settings` resolve
`ShopSettings.load(store=getattr(request, "store", None))` /
`FooterSettings.load(store=getattr(request, "store", None))` — `request.store`
comes only from PR 3's `StoreResolutionMiddleware`, never from the
authenticated user or `StoreMembership`. The dashboard settings views and
the footer trust-badge/payment-logo CRUD views follow the same rule via a
small `_resolve_dashboard_store(request)` helper (`request.store`, falling
back to the same compatibility check). All existing template context keys
(store name, tagline, contact info, logo, favicon, theme color tokens, tax,
free-shipping threshold, footer settings, trust badges, payment logos) are
unchanged — no storefront template needed to know tenancy was added.

### 9.6 Write-path isolation

Every dashboard endpoint that reads, creates, edits, toggles, or deletes a
`FooterTrustBadge`/`FooterPaymentLogo` row scopes its lookup with the
authoritative Store from `_resolve_dashboard_store(request)` —
`get_object_or_404(FooterTrustBadge, pk=pk, store=store)`, never a bare
`pk` lookup. A caller-supplied object ID for another Store's row resolves
to a 404, not the object. This is adversarially tested (a Store A dashboard
request cannot edit, reorder, enable/disable, or delete a Store B object).
No dashboard authorization policy changed — the existing `@staff_required`
gate is unchanged; tenant scope was added on top of it, not instead of it.

### 9.7 Explicit non-goals of this PR

* No catalog, cart, order, customer, vendor, payment-gateway,
  shipping-method, or SMS-template model gained Store ownership.
* `SocialLink`, `Menu`/`MenuItem`, `ContentPage`, `HeroSlide`, and
  `PromotionalBanner` were not touched.
* `ShopSettings` was not split (ADR-10 still applies unchanged); SMS
  credentials remain on `ShopSettings` for now (PR 9's job).
* No dashboard tenant-switching UI was introduced, and `StoreMembership`
  was not consulted anywhere in this PR.
* No caching was introduced.

## 10. What This PR Does Not Change

Beyond §9.7: no `StoreDomain` resolution policy changed, no
`StoreMembership`/plan/subscription/billing/platform-admin/feature-flag
behavior changed, and no secret-encryption work was done (the
`melipayamak_password` plaintext-rendering issue noted independently of
this PR remains deferred to its own small security PR). See
`SAAS_MIGRATION_PLAN.md` for the staged sequence that will change this
incrementally.

## 11. Explicit Store Context Propagation for Pricing and SMS

Implemented (PR 4.1 — see `SAAS_MIGRATION_PLAN.md` for status).

### 11.1 The problem PR 4 left open

§9.3 made `ShopSettings.load()` fail closed instead of silently returning
Akhlaghi's row once a second `Store` exists — correct for isolation, but it
meant every production caller that still called `ShopSettings.load()` with
no Store (`apps.cart.services.pricing`, `apps.sms.services.sms_service`)
would break — hard-failing (pricing) or silently no-op'ing (SMS) — the
moment a real second Store existed, even for that Store's own,
already-resolved, otherwise-valid request.

### 11.2 Store authority rules

An authoritative `Store` for a tenant-sensitive service call may only come
from: an already Store-owned aggregate or related object; `request.store`
at the HTTP boundary; an explicit `Store` argument supplied by a trusted
caller that already resolved one; or a job payload whose Store identity was
recorded server-side (no such jobs exist in this codebase — see §7). A
caller-supplied `store_id` (POST body, query parameter, or any other
client-controlled input) is never authoritative, and an already-resolved
explicit Store is never silently replaced by the Akhlaghi compatibility
fallback.

### 11.3 Resolve once, at the boundary

`apps.stores.resolution.resolve_store_for_service(request)` is the shared
helper: returns `request.store` if already resolved, otherwise falls back
to the same `resolve_compatibility_store()` check used everywhere else.
Called exactly once per request — at a view, or at a service function that
already receives `request` (e.g. `apps.orders.services.checkout_service`'s
functions) — never re-derived deeper inside a domain service. Deeper,
non-request-aware service functions (`cart_totals`, `send_event_sms`,
`create_order_from_cart`, `change_order_status`, `simulate_payment`,
`otp_service.request_otp`, `auth_service.signup`/`create_account_for_guest`)
take a required, keyword-only `store` argument instead — no default, so a
caller cannot silently omit it and fall into compatibility mode by
accident. `apps.dashboard.views._resolve_dashboard_store` (from PR 4) now
delegates to this same shared function.

### 11.4 Deterministic failure, never a cross-Store fallback

`cart_totals`/`_free_shipping_threshold`/`_tax_percent` raise `ValueError`
immediately if `store` is `None` — pricing failures are never swallowed.
`send_event_sms` logs a clear error and returns `None` for `store=None`,
consistent with its pre-existing "never raise" contract (SMS is
fire-and-forget by design) — it never falls back to Akhlaghi or guesses
another Store. `transaction.on_commit` closures capture the resolved
`store` by value at scheduling time, so a deferred SMS send always uses the
Store that was resolved when the triggering request was handled.

### 11.5 What this PR does not change

No `store` FK was added to `Cart`, `Order`, `Customer`, `SmsTemplate`, or
`SmsLog` — none proved necessary, since every touched call site already had
an authoritative Store resolvable from the triggering request. SMS
credentials remain on `ShopSettings` (PR 9's job); no encryption-at-rest
work was done. `Cart`/`Order`/`Customer` themselves remain unscoped until
PR 6/7/10.

## 12. Catalog Tenant Boundary Hardening

Implemented (PR 5 — see `SAAS_MIGRATION_PLAN.md` for status).

### 12.1 Aggregate Root vs. child-through-parent vs. redundant child

This PR introduces a three-way classification for every model a Store-scoped
domain touches, used to decide whether it needs its own `store` FK at all:

* **Aggregate Root** — independently queryable and mutable outside its
  "parent's" own scoped lookups (has its own dashboard CRUD, its own
  storefront URL, or its own uniqueness constraint that must hold
  per-Store). Gets a direct `store` FK.
* **Store-owned child through an authoritative parent** — only ever
  reached, listed, or mutated via a parent that is itself Store-owned and
  already enforces the relationship (e.g. `product.images.all()`); adding a
  redundant `store` FK here would be pure duplication with no new
  invariant to enforce. No `store` FK.
* **Redundant child with an explicit DB-level invariant** — a child that is
  reached only through its parent in every code path, but needs its own
  `store` FK anyway because a real database constraint cannot otherwise be
  expressed (typically because the constraint would need to span a join,
  which SQLite's `UniqueConstraint` cannot do). Requires: the field is never
  independently settable by any caller, is always recomputed from the
  parent at save time, and any bulk-mutation path is guarded against
  setting it directly.

### 12.2 Catalog ownership graph

| Model | Classification | Ownership |
|---|---|---|
| `Vendor` | Aggregate Root | direct `store` FK |
| `Category` | Aggregate Root | direct `store` FK |
| `Brand` | Aggregate Root | direct `store` FK |
| `Product` | Aggregate Root | direct `store` FK |
| `ProductVariant` | Redundant child (SKU uniqueness needs a non-join DB constraint) | denormalized `store` FK, always mirrors `product.store`, never independently editable |
| `ProductImage` | Child through `Product` | no `store` FK |
| `Specification` | Child through `Product` | no `store` FK |
| `Review` | Child through `Product` | no `store` FK |
| `SpecificationTemplate` / `SpecificationTemplateField` | Deferred — zero merchant-facing exposure today (Django admin only) | no `store` FK, explicitly out of scope for this PR |

`Vendor` becoming a Store-owned Aggregate Root (rather than a tenant
concept of its own) settles `SAAS_DOMAIN_DECISIONS.md` ADR-1: a Vendor is
still not a `Store` — multi-vendor-within-a-Store remains a distinct,
unbuilt future feature — but it is now unambiguously owned by exactly one
Store, like every other catalog Aggregate Root.

### 12.3 Why SQLite forces a denormalized field on `ProductVariant`

A per-Store-unique SKU constraint on `ProductVariant` is naturally
"`(product__store, sku)` must be unique," but Django's `UniqueConstraint`
can only reference columns physically present on the constrained table —
it cannot span the `product__store` join. The only way to get a real,
DB-enforced, Store-scoped SKU constraint in SQLite is to duplicate `store`
onto `ProductVariant` itself. To keep this from becoming a second,
independently-driftable source of truth, `_normalize_variant_fields`
recomputes `variant.store_id = variant.product.store_id` unconditionally on
every `save()`/`bulk_create()` path (the same normalization pass that
already owns `attribute`/`value`/`sku` casing/digit normalization), and the
variant queryset blocks any `update()`/`bulk_update()` that tries to touch
`store`/`store_id` directly — exactly the same guard already protecting
`attribute`/`value`/`sku`/`normalized_attribute`/`normalized_value`. The
only way to change a variant's Store is to change its Product's Store.

### 12.4 Application-layer cross-FK consistency

SQLite cannot express a `CHECK` constraint spanning two tables, so
"`product.vendor.store == product.store`" (and the equivalent for
`category`/`brand`, and `category.parent.store == category.store`) is
enforced in `Product.clean()`/`Category.clean()` instead — intentional,
not an oversight, and exercised both directly (model-level tests) and
indirectly (`ProductForm`/`SubCategoryForm` scope every relation
`ModelChoiceField`'s queryset to the resolved Store first, so a crafted
POST referencing another Store's category/vendor/brand/parent is rejected
by Django's own "not a valid choice" validation before `clean()` would even
need to run — `clean()` remains the defense-in-depth layer for any path
that bypasses the form, such as a management command or a future API).

### 12.5 Query conversion surface

Every production access path that reads or writes `Vendor`/`Category`/
`Brand`/`Product`/`ProductVariant` now resolves its Store the same way PR
4.1 established — once, at the boundary, via
`resolve_store_for_service(request)` (storefront, cart) or
`_resolve_dashboard_store(request)` (dashboard, itself a thin wrapper over
the same function) — and threads it down as a plain argument, never
re-deriving it deeper in a service. This covers: `apps.catalog.views`
(`home`, `product_list`, `product_detail`, `product_review_create`, the
`_best_products`/`_filtered_products` helpers), `apps.catalog.context_processors.nav_categories`,
`apps.cart.views.cart_add`, `apps.orders.services.order_service.create_order_from_cart`
(a new defensive per-line Store check — see §12.6), and every catalog
dashboard view/service in `apps.dashboard` (`catalog_admin_service`'s slug
generation, default-vendor lookup, category tree, and product filtering;
every product/category/image/variant CRUD view).

### 12.6 Cart/order boundary — no new Cart/Order schema

Consistent with PR 4.1's precedent, this PR does **not** add a `store` FK
to `Cart` or `Order` — `apps.cart.views.cart_add` already scopes its
`Product` lookup by the resolved Store (`get_object_or_404(Product, slug=slug, store=store, ...)`),
so no cart line can reference another Store's Product through the normal
add-to-cart path. `create_order_from_cart` adds one small, explicit,
documented defensive check anyway — rejecting any cart line whose
`product.store_id` does not match the order's Store — as a last line of
defense against a cart line that reached this function through some path
other than `cart_add` (there is currently no such path; the check exists
for the same reason PR 4.1's SMS/pricing functions validate their `store`
argument instead of trusting every caller transitively). This is
explicitly not full `Cart`/`Order` tenantization — that remains PR 6/PR 7's
job.

### 12.7 Proven defects found and fixed by full-suite verification

Running every affected app's test suite together (not one app at a time)
surfaced two real cross-Store leaks outside `apps.catalog` itself, both
fixed in this PR rather than deferred, since both are direct consequences
of `Product` becoming Store-scoped:

* `apps.customers.views.wishlist_toggle` resolved `Product` by slug with no
  Store scoping — a customer browsing Store A could add Store B's product
  to their wishlist by slug alone. Fixed with the same
  `resolve_store_for_service(request)` + Store-scoped `get_object_or_404`
  pattern used everywhere else.
* `apps.dashboard.services.dashboard_service`'s `stat_cards`,
  `low_stock_products`, and `build_dashboard_context`'s `nav_product_count`
  queried `Product` platform-globally — every merchant's dashboard home
  page showed a low-stock count/list and product count mixed across every
  Store. Fixed by threading the resolved Store through all three. The
  Order/Customer-based widgets on the same page are intentionally left
  unscoped (Order/Customer tenant-scoping is PR 6/7/10's job, not
  available to reference here).

### 12.8 What this PR does not change

No `apps.content` model (`HeroSlide`, `PromotionalBanner`, `MenuItem`) is
touched — their `destination_category`/`destination_product`/
`destination_brand` FKs remain unscoped, and are explicitly PR 8's job; this
is a real, documented cross-boundary risk now that the catalog objects
those FKs point to are Store-scoped (a content author could, today,
attach a destination pointing at any Store's category/product/brand and no
Store check would catch it), but fixing it means Store-scoping the content
models themselves, which is out of this PR's scope. No generic
repository/service layer was introduced. No Inventory Ledger was
introduced — price and stock remain plain fields on `Product`/
`ProductVariant`, exactly as before. No import/export feature exists in
this codebase today (confirmed absent by inspection, not built here). No
Django admin (`/admin/`) tenant-isolation querying (Store-scoped querysets
or `formfield_for_foreignkey` filtering) was added — the catalog
`ModelAdmin`s gained only the minimal `store` field exposure needed to keep
existing CRUD functional now that `store` is a required field. See §12.9 for
why unscoped admin access to this now-real multi-Store data could not be
left as-is.

### 12.9 Django Admin restricted to superusers only

Independent post-merge-request review of this PR found that
`apps.dashboard`'s `staff_required` decorator and Django's own `AdminSite`
shared the identical `is_staff` gate, with no other distinction — meaning
any account given merchant-dashboard access could also reach `/admin/` and
see or mutate **every Store's** catalog data through the unscoped
`ModelAdmin`s described above. ADR-8 already recorded this class of gap as
a known, deferred, *unresolved* security boundary — not, as an earlier
draft of this section implied, an accepted design. Before this PR, the gap
was latent (only Akhlaghi's catalog data ever existed to leak); this PR is
what makes it real, since it is what first makes genuine multi-Store
catalog data coexist.

Remediation (same PR, not deferred): `apps.stores.admin_permissions`
overrides `has_permission` on the one `django.contrib.admin.site` instance
every app's `admin.py` registers onto by default (`apps.catalog`,
`apps.stores`, `apps.orders`, `apps.blog`, `apps.customers`, `apps.cart`),
restricting it to `request.user.is_active and request.user.is_superuser`.
Installed once, centrally, via `StoresConfig.ready()` — no per-`ModelAdmin`
patch, no new `AdminSite` subclass, no change to `shop_core/urls.py`'s
`admin.site.urls` mount, and no change to the merchant dashboard's own
`is_staff` contract (a Store's dashboard staff keep using the dashboard
exactly as before; they simply can no longer also reach `/admin/`). This is
still not Store-aware admin scoping — a platform superuser sees every
Store's data in `/admin/` undifferentiated, same as always — it only closes
the specific "merchant staff leaks into platform admin" path.
`StoreMembership`-based dashboard authorization and full Store-aware admin
query-scoping both remain deferred to PR 11.
