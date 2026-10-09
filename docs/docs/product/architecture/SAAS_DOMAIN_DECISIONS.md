# SaaS Domain Decisions

ADR-style decision record for the SaaS foundation stage. Each decision lists
Context, Decision, Alternatives, Consequences, and Deferred Questions.

---

## ADR-1: Store Is a New Entity, Separate From Vendor

**Context.** The repository has an existing `apps.catalog.Vendor` model
(`name`, `slug`, `owner` FK to `User`, `logo`, `description`, `is_active`),
docstring "فروشنده / فروشگاه — پایه‌ی چند فروشنده‌ای (Multi-Vendor Ready)". It
is referenced by `Product.vendor` and `Order.vendor`. A prior assessment
proposed renaming or reinterpreting `Vendor` as the SaaS tenant.

**Decision.** `Store` is created as an independent new entity in a new
`apps.stores` app. `Vendor` is not renamed, repointed, or reinterpreted in
this PR. `Vendor` remains exactly as it is today.

**Alternatives considered.**
* Rename `Vendor` → `Store`. Rejected: `Vendor` is already a live FK target
  for `Product` and `Order` with existing data and tests; conflating "the
  SaaS tenant" with "a multi-vendor marketplace seller" would force a
  premature, irreversible decision about whether a Store's internal sellers
  (if the platform ever supports multi-vendor marketplaces per Store) are the
  same concept as the tenant itself. They are not obviously the same thing.
* Add a `Store` FK directly to `Vendor` now. Rejected: this PR's scope is
  explicitly limited to the new `apps.stores` app; no existing model gets a
  new FK in this PR (see Out-of-Scope in `SAAS_MIGRATION_PLAN.md`).

**Consequences.** Two parallel concepts exist for a period: `Vendor` (legacy,
unscoped) and `Store` (new, tenant boundary). This is intentional and
temporary. A later, dedicated catalog-domain PR must decide Vendor's final
meaning (e.g. "Vendor becomes a Store-scoped marketplace seller" or "Vendor
is deprecated in favor of Store" or "Vendor and Store coexist for
multi-vendor Stores") before catalog ownership is migrated (PR 5).

**Deferred questions.** What does "Vendor" mean once a Store can itself host
multiple internal sellers? Is single-seller-per-Store the only supported
model for the first SaaS version? These are explicitly out of scope here.

**Resolution (PR 5 — Catalog Tenant Boundary Assessment and Hardening).**
`Vendor` becomes a Store-owned Aggregate Root: a direct, non-nullable
`store` FK, with `slug` uniqueness re-derived as Store-scoped
(`UniqueConstraint(fields=["store", "slug"])` instead of platform-global
`unique=True`). This settles the "final meaning" question deferred above as
narrowly as the evidence supports: `Vendor` is not itself a tenant, and
multi-vendor-within-a-Store (a Store hosting more than one internal seller)
remains a distinct, unbuilt future feature — today's dashboard has no UI to
create a second `Vendor` for a Store at all (only `seed_shop` or Django
admin can). What this resolves is narrower and more urgent: every `Vendor`
row must belong to exactly one Store, so that Store A can never see,
reassign, or collide slugs with Store B's Vendor. Full multi-vendor-per-
Store product ownership semantics remain deferred, unchanged from this
ADR's original scope.

---

## ADR-2: Store Ownership Uses StoreMembership, Not a Store.owner Field

**Context.** A tenant needs an authoritative notion of "who owns this
Store." Two competing designs are possible: a direct `Store.owner` FK, or an
owner represented as a role within a membership table.

**Decision.** Store ownership is represented exclusively through an active
`StoreMembership` row with `role=owner`. No `Store.owner` field is added.

**Alternatives considered.**
* `Store.owner` FK to `User`, in addition to `StoreMembership`. Rejected:
  this creates two sources of truth that can silently disagree (owner FK
  says user A, membership table says user B is the active Owner). Every
  future authorization check would need to reconcile both, which is
  itself a class of bug.
* `Store.owner` FK only, no `StoreMembership` in this stage. Rejected: a
  Store must support multiple members with different roles from the start
  (StoreMembership is explicitly foundation-stage per the task program),
  and ownership transfer/co-ownership cannot be modeled by a single FK
  without a subsequent migration anyway.

**Consequences.** "Who owns Store X" is always answered by querying
`StoreMembership.objects.filter(store=X, role=OWNER, status=ACTIVE)`. This
query is expected to return at most one row (enforced by a partial unique
constraint, see ADR-3), but the enforcement mechanism is the constraint, not
a denormalized field.

Because ownership lives exclusively in `StoreMembership`, deleting a `User`
must not be allowed to silently delete their membership rows — that could
delete a Store's only active Owner membership as a side effect of an
unrelated user-deletion action, orphaning the Store. `StoreMembership.user`
therefore uses `on_delete=PROTECT`, not `CASCADE`: deleting a User who still
holds any membership raises `ProtectedError` rather than deleting the
membership row. `StoreMembership.store` still uses `CASCADE` — a membership
has no meaning without its Store, so deleting the Store deleting its
memberships is correct. `StoreMembership.invited_by` remains `SET_NULL`,
since losing a record of *who sent an invitation* is not a safety concern.
Formal user-account deletion for a user who holds memberships requires a
future, explicit membership-revocation/ownership-transfer service to run
first; this PR does not implement that service.

---

## ADR-3: Store Has One Explicit Status Field

**Context.** The prior assessment suggested boolean flags such as
`is_active` / `is_suspended`, which can independently be set to
contradictory combinations (e.g. both true).

**Decision.** `Store.status` is a single `TextChoices` field:
`provisioning`, `active`, `suspended`, `closed`.

**Alternatives considered.** Multiple booleans — rejected for the reason
above. A richer state machine with billing/deletion sub-states — rejected as
premature; this PR does not implement billing or deletion lifecycle.

**Consequences.** Any future state transition (e.g. suspend, reactivate,
close) is a single-field update with a well-defined value set, and is a
natural place to hang a future service-layer transition function. No
transition logic or validation of legal transitions is implemented yet.

**Deferred questions.** Legal transition rules (e.g. can a `closed` Store
return to `active`?) and billing-driven transitions are deferred to the
billing/lifecycle work, not this foundation PR.

---

## ADR-4: StoreDomain Stores Normalized Hostnames, With One Primary per Store

**Context.** Custom domains are a standard SaaS requirement, and hostname
input is an XSS/SSRF/host-header-confusion-adjacent surface if accepted
loosely (schemes, paths, credentials, ports embedded in a "hostname" field).

**Decision.** `StoreDomain.hostname` stores only a normalized hostname
(lowercased, trimmed, trailing dot removed, validated as a syntactically
valid hostname). Scheme, path, query, fragment, credentials, and port are
rejected at write time by the model's `clean()`/normalization path, not only
by a form. This guarantee covers `instance.save()`, `full_clean()`, and
`StoreDomain.objects.bulk_create()` (which normalizes and validates each
instance before insertion, since `bulk_create()` never calls `save()`).
`StoreDomain.objects.filter(...).update(hostname=...)` is the one write path
that cannot be normalized this way — a raw SQL `UPDATE` runs no Python code —
so it is rejected outright with `StoreDomainMutationError` rather than being
allowed to persist an un-normalized value. Hostname is platform-globally
unique. At most one `is_primary=True` `StoreDomain` per Store is enforced by
a partial (conditional) database `UniqueConstraint`.

**Alternatives considered.** Storing a full URL and parsing it downstream
wherever needed — rejected: this multiplies the number of places that must
agree on what counts as "the same domain," which is exactly the kind of
duplicate-source-of-truth problem this program is meant to avoid.
Form-level-only validation — rejected: bypassable via the admin, shell, data
migrations, or a future API, so it is not authoritative. Relying on
`Model.save()`/`clean()` alone — rejected once identified that
`QuerySet.update()` and `QuerySet.bulk_create()` bypass both entirely; a
dedicated `StoreDomainQuerySet` closes that gap for `bulk_create()` and
blocks the un-normalizable `update(hostname=...)` path outright.

**Consequences.** Internationalized (IDN) domains are accepted only as their
ASCII-compatible (Punycode/IDNA) form; normalization decodes/encodes
consistently so visually-identical Unicode variants cannot collide with or
bypass uniqueness. This is a normalization decision, not a full IDNA
homograph-attack mitigation (e.g. this PR does not attempt to block
confusable-Unicode-lookalike domains beyond IDNA syntax rules) — flagged as
a deferred question below.

**Deferred questions.** IDNA homograph/lookalike mitigation beyond syntactic
IDNA validation. DNS/HTTP verification networking (deferred to a later PR by
explicit program instruction).

---

## ADR-5: Domain Verification Is a Small Lifecycle, Not a Boolean

**Context.** "Is this domain verified" needs more than a boolean once a
verification flow (token issuance, retry, expiry) exists.

**Decision.** `StoreDomain` carries `verification_status`
(`unverified`/`pending`/`verified`/`failed`), a `verification_token`,
`verification_requested_at`, and `verified_at`. No DNS/HTTP verification
networking is implemented; only the model foundation. Coherence between
these four fields is enforced twice, deliberately: as database
`CheckConstraint`s (authoritative — hold even against direct SQL or a bug in
application code) and mirrored in `clean()` (defense in depth, for a
friendlier `ValidationError` before the database is even touched). The
enforced rules are exactly:

* `verified` requires `verified_at` to be set.
* Any non-`verified` status must **not** retain `verified_at` (so a domain
  that later moves from `verified` to `failed` must have `verified_at`
  cleared by the caller, not left stale).
* `pending` requires `verification_requested_at` to be set.
* `pending` requires a non-empty `verification_token`.
* The existing uniqueness rule for non-empty `verification_token` values is
  unchanged.

**Consequences.** A later PR can implement the actual verification checker
against this schema without another migration to add lifecycle fields. The
rules above are intentionally the minimum needed for internal coherence of
the four fields — they are not a claim that the verification *process*
(retry limits, token expiry, re-verification after a hostname change) is
fully modeled; that is still future work for the verification-checker PR.

---

## ADR-6: Customer Identity — Deferred, Direction Recorded Only

**Context.** `apps.customers.Customer` today is a 1:1 extension of
`django.contrib.auth.User` with no Store scoping. Deciding its final shape
touches authentication, privacy, and cross-Store data-sharing questions that
are out of scope for this PR.

**Decision.** No changes to `Customer` in this PR. The recorded future
direction is:

```text
Global authentication identity (the Django User / login credential)
+
Store-specific commerce customer profile (order history, addresses,
wishlist, VIP status, spend totals — all Store-scoped)
```

i.e. a person can log in once (global identity) but has a distinct
commerce profile — and distinct privacy boundary — per Store they have
shopped at. This mirrors the Store/StoreMembership split already adopted for
staff-side identity.

**Alternatives considered.** Fully global Customer (one profile shared
across all Stores) — rejected as a final design because it would leak
one Store's purchase history/VIP status/spend into another Store's view of
the same person, which is a cross-tenant data leak by definition. Fully
duplicated User-per-Store — rejected as unnecessarily duplicating
authentication identity and complicating login.

**Deferred questions.** Exact mechanism for "same login, N Store profiles";
whether `OtpCode` is platform-global (plausible, since it verifies a phone
number, not a Store relationship) or needs a Store dimension for
rate-limiting/audit purposes — not decided here. `OtpCode` is explicitly
**not** declared platform-global by this document; that determination is
deferred to the customer-identity PR (PR 10).

---

## ADR-7: Payment Provider and Store Payment Configuration Are Separate Concepts

**Context.** `apps.orders.PaymentGateway` today mixes what looks like a
provider definition (`name`, `slug`, `icon`, `fee_percent`) with what will
need to become per-Store enablement/credentials once Stores have their own
payment configuration. Adding a `Store` FK directly to `PaymentGateway`
would conflate "this payment method exists on the platform" with "this
Store has enabled and configured it."

**Decision.** No change to `PaymentGateway` in this PR. The recorded future
direction is three separate concepts:

```text
PaymentProvider              — platform-global integration definition
StorePaymentConfiguration    — Store-specific credentials and enablement
PaymentTransaction           — order/payment attempt and result
```

**Alternatives considered.** Add `Store` FK to the existing
`PaymentGateway` — rejected: `PaymentGateway` must first be audited to
determine which of its current fields are really provider-level (global)
versus configuration-level (per-Store), which this PR does not do.

**Deferred questions.** The `PaymentGateway` audit itself; how
`fee_percent` splits between platform-level default and Store-level
override, if at all.

---

## ADR-8: Platform Operators Do Not Automatically Get Unrestricted Merchant-Data Access

**Context.** Django's `is_staff`/`is_superuser` flags currently grant full
admin access to all data through the Django admin, with no Store-scoping
concept.

**Decision.** Being a platform operator (however that role is eventually
modeled) must not be conflated with "can read/write any Store's commerce
data unrestricted." Any future platform-operator tooling that needs
cross-Store visibility must be an explicit, audited capability, not an
incidental side effect of Django-admin `is_staff`.

**Consequences.** This PR does not implement any enforcement of this
decision (no authorization code changes at all). It is recorded so that
later PRs (dashboard authorization, PR 11) are not designed against an
assumption that staff access already implies "trusted with all merchant
data."

**Deferred questions.** Concrete mechanism (separate permission model,
audit-logged elevated access, etc.) — not decided here.

**Addendum (PR 5 — Catalog Tenant Boundary Assessment and Hardening).**
This ADR's "not implemented, not to be assumed safe" framing was
subsequently misquoted in `SAAS_MIGRATION_PLAN.md` as an "already-accepted"
scope — it was not; the text above has always meant the opposite. Once PR 5
gave `Product`/`Category`/`Brand`/`Vendor` a real, non-nullable `store` FK,
the gap this ADR describes stopped being latent (there was only ever one
Store's catalog data to leak before) and became a live cross-Store exposure
the moment any second Store's dashboard staff existed, since
`apps.dashboard`'s `is_staff`-gated authorization and Django's own
`AdminSite` shared the identical flag. PR 5 closes the immediate exposure,
without resolving this ADR's deferred questions: Django Admin is now
restricted to active superusers only (`apps.stores.admin_permissions`).
Platform-operator tooling still has no Store-scoped, audited,
narrower-than-superuser capability — that remains exactly as open as this
ADR originally left it, and is still PR 11's job.

---

## ADR-9: Merchant Sales Funds Flow Directly to Merchant-Owned Payment Accounts

**Context.** A marketplace-style platform could route customer payments
through a platform-owned account before disbursing to merchants
(platform-as-merchant-of-record), or let each Store's payment configuration
point directly at that Store's own payment-provider account.

**Decision.** For the first SaaS version, the recorded direction is that
funds flow directly to merchant-owned payment accounts (the platform is not
a merchant-of-record / money-transmitter in v1). This has no code impact in
this PR; it constrains the design of `StorePaymentConfiguration` and
`PaymentTransaction` in the future payment-domain PR (PR 7).

**Alternatives considered.** Platform-as-merchant-of-record with internal
ledgering/payouts — rejected for v1 due to the additional regulatory and
reconciliation complexity, revisit once the platform has multiple Stores and
a real payments requirement.

**Deferred questions.** Whether/when a payout/ledger model becomes
necessary as the platform grows.

---

## ADR-10: Store Configuration Is Modeled as Direct Domain Models, Not a Generic StoreConfiguration Table

**Context.** `apps.core.ShopSettings` today bundles four unrelated
concerns in one singleton row: store identity/contact, tax/shipping
defaults, SMS provider credentials, and branding/theme tokens. A dedicated
Store Configuration Architecture Assessment evaluated five alternatives
(one god model; a generic `StoreConfiguration` aggregate table plus
domain-specific one-to-ones; `Store` as aggregate root with direct
domain-specific models and no umbrella table; JSON documents; a relational
+ namespaced-JSON hybrid) against this repository's actual field inventory
— not generic SaaS theory.

**Decision.** `Store` is the aggregate root. No generic `StoreConfiguration`
database table is introduced. Configuration domains are modeled as direct,
independently-owned models attached straight to `Store` (mirroring how
`FooterSettings`, `SocialLink`, and `Menu` already exist as separate
top-level models today, not sub-documents of one settings blob). Domain
models are introduced incrementally, driven by fields that actually exist
in the codebase — not speculatively for every domain named in the platform
roadmap (SEO, notifications, checkout rules, order numbering, invoicing,
and email do not have a single field in this codebase today, so no models
are created for them yet). Current `ShopSettings` is **not split** in the
resolution-infrastructure PR that introduced this ADR; a future PR will
tenant-scope it as-is (add a `store` FK, no field reorganization), with any
eventual split treated as its own, separately-reviewed decision.

**Alternatives considered.** See the full assessment for the five-way
comparison; in short: one god model was rejected as reproducing the exact
problem this ADR exists to prevent; a generic `StoreConfiguration`
aggregate table was rejected because it would add a table with no real
column content of its own, existing only to be pointed at; JSON-only was
rejected because this codebase's existing settings fields all have strict,
already-relied-upon per-field validation (hex colors, decimal ranges,
choices) that JSON would weaken.

**Consequences.** Splitting `ShopSettings` (identity/commerce-defaults vs.
branding/theme vs. SMS credentials) is deferred to a dedicated future PR,
sequenced after the tenant-scoping-without-split PR described in
`SAAS_MIGRATION_PLAN.md`. The merchant-facing admin UI's existing five
sections (general, finance, delivery-payment, sms, appearance) remain the
UX contract regardless of how many models eventually back them — database
table boundaries must never dictate a fragmented admin experience. The
tenant-scoping-without-split PR referenced above is PR 4
(`SAAS_MIGRATION_PLAN.md`); see ADR-12 for the specific ownership shape it
gave `ShopSettings`/`FooterSettings`/`FooterTrustBadge`/`FooterPaymentLogo`.

**Deferred questions.** Exact field boundary between "identity" and
"commerce-defaults" if/when `ShopSettings` is split; timing of the SMS
credential extraction (a real, already-identified plaintext-handling issue
independent of tenancy); whether feature flags/experimental configuration
ever gets a minimal JSON column on `Store` itself, once such fields
actually exist.

---

## ADR-11: Store Resolution Is Hostname-Authoritative, With a Fail-Closed Compatibility Fallback

**Context.** Every future Store-scoped model, view, and service needs a
single, trustworthy answer to "which Store is this request for?" before
any of them can be built safely. `StoreDomain` existed as a data model
since the foundation PR but nothing consumed it.

**Decision.** `apps.stores.resolution` is the sole authoritative resolver:
it maps `request.get_host()` → normalized hostname (via the existing
`normalize_hostname`) → `StoreDomain.hostname` lookup → the associated
`Store`, gated by a routing-eligibility policy (Store `ACTIVE` and domain
`VERIFIED` — see `SAAS_ARCHITECTURE.md` §6.2). `StoreResolutionMiddleware`
runs this once per request and attaches the result to `request.store`
(`Store` or `None`), positioned before `SessionMiddleware` and
`AuthenticationMiddleware` in `MIDDLEWARE` so tenant resolution is
structurally independent of session/auth state, not just independent by
convention. A narrow, explicitly isolated, temporary compatibility fallback
lets a fixed development-host allowlist resolve to the Akhlaghi Store, but
only while exactly one, active, `"akhlaghi"`-slugged Store exists — it
fails closed the instant a second Store is created, rather than falling
back to "the first Store" or any other heuristic.

**Alternatives considered.** Deriving Store from the authenticated user's
`StoreMembership` — rejected for storefront resolution: a storefront
visitor is usually unauthenticated, and even when authenticated, "which
Store am I browsing" must not depend on "which Store(s) am I staff of" —
those are different questions (tenant resolution vs. authorization, see
`SAAS_ARCHITECTURE.md` §6.4). Accepting a caller-supplied Store ID (query
param, header, session key) — rejected outright as trivially spoofable;
verified directly by adversarial tests
(`apps.stores.tests.test_resolution.IsolationAdversarialTests`). A single
`Store.objects.first()`-style fallback — rejected; this is precisely the
class of singleton assumption flagged as unsafe in the prior Tenant
Ownership assessment, and the narrow, multi-condition compatibility check
in this ADR exists specifically to avoid it.

**Consequences.** No existing view, template, or business query was
changed — `request.store` is set on every request but consumed nowhere
yet. A Django system check for "middleware omitted" or "unsafe
compatibility configuration in production" was considered and explicitly
declined for this PR: no such setting (e.g. a "strict tenant mode" flag)
exists yet to check against, and the compatibility fallback's own
multi-condition gate already fails closed structurally, so no additional
check could add a reliable, non-noisy signal beyond what the fallback's own
logic already guarantees.

**Deferred questions.** When request-time resolution becomes a *hard*
requirement for a given model (i.e., when its own PR removes any
compatibility fallback) is decided per-model, not by this ADR. Whether a
future "strict tenant mode" setting is introduced, and a matching system
check with it, is left open.

---

## ADR-12: `ShopSettings`/`FooterSettings` Are One-Row-Per-Store; Trust Badges and Payment Logos Own Their Store Directly

**Context.** ADR-10 decided `ShopSettings` and `FooterSettings` would
eventually be tenant-scoped without a field split. PR 4
(`SAAS_MIGRATION_PLAN.md`) is the PR that actually does this, and had to
answer two concrete questions ADR-10 left open: (1) what field/constraint
shape enforces "one row per Store" instead of "one row for the whole
platform," and (2) whether `FooterTrustBadge`/`FooterPaymentLogo` should
gain their own `store` FK or be reached only through `FooterSettings`.

**Decision.** `ShopSettings.store` and `FooterSettings.store` are each a
`OneToOneField("stores.Store")` — the database itself enforces at most one
row per Store, not just applic­ation-level convention. `FooterTrustBadge`
and `FooterPaymentLogo` each get a plain, non-unique
`ForeignKey("stores.Store")` directly, independent of `FooterSettings`:
inspection of every call site showed both are queried and managed
independently today (their own dashboard list/create/edit/delete/toggle
views, filtered directly by `store`, never joined through
`FooterSettings`) — inferring their ownership from the fact that the
storefront renders them inside the same footer region as `FooterSettings`
would have been ownership-by-visual-adjacency, not ownership-by-actual-use.
Retrieval for both settings models follows one shared contract:
`load(store=...)` (explicit, authoritative, raises a dedicated
`*NotProvisionedError` rather than ever returning another Store's row or
auto-creating one) and `load()` (temporary compatibility mode, delegating
to PR 3's `resolve_compatibility_store()` fail-closed check). Provisioning
a new Store's rows is a separate, explicit, idempotent `provision_for(store)`
classmethod — never a signal, never invoked implicitly on read.

**Alternatives considered.** A shared, unique `store` FK plus
`FooterTrustBadge`/`FooterPaymentLogo` reached only via
`FooterSettings.trust_badges`/`payment_logos` reverse relations — rejected
because it does not match how these models are actually used in this
codebase today and would require a speculative redesign of their own
dashboard views as part of a PR whose stated scope is tenant-scoping, not
redesigning. Enforcing "one row per Store" purely at the application layer
(`unique=True` alone, or a service-layer check) instead of a
`OneToOneField` — rejected: a plain unique constraint plus a bug in the
service layer could still create a second row per Store, whereas
`OneToOneField`'s own DB-level unique index makes that a hard constraint
violation, not a bug waiting to happen. Auto-provisioning a Store's
settings via `get_or_create()` inside `load()` itself — rejected outright
per this PR's own governing instructions: that would permanently hide a
genuinely missing provisioning step behind a silent read-time side effect,
the same failure mode the removed platform-wide `get_or_create(pk=1)`
singleton exhibited, just re-scoped per-Store instead of fixed.

**Consequences.** The previous `save()` override that forced `pk=1` on
every `ShopSettings`/`FooterSettings` instance is removed entirely from
both models — a Store's settings row can have any primary key, and no code
anywhere may assume otherwise. `resolve_compatibility_store()` was promoted
from a resolver-module-private helper (`_resolve_compatibility_store`) to
a public function specifically so this compatibility contract has exactly
one implementation, shared by hostname resolution (PR 3) and settings
retrieval (PR 4) — not two independently-maintained copies of the same
fail-closed rule that could quietly drift apart. `SocialLink`, `Menu`,
`ContentPage`, `HeroSlide`, and `PromotionalBanner` were deliberately left
un-scoped in this PR; that remains PR 8's job.

**Deferred questions.** Whether `FooterTrustBadge`/`FooterPaymentLogo`
should ever gain a display-order uniqueness constraint per Store (today,
duplicate `display_order` values within a Store are allowed and broken
only by `id` as a tiebreaker) is left open — no requirement for it exists
today. Whether provisioning should ever be triggered automatically as part
of a future "create Store" service/admin action (rather than an explicit,
separate call) is left to whichever PR introduces that service.

---

## ADR-13: Tenant-Sensitive Services Take an Explicit Store Argument, Resolved Once at the Boundary

**Context.** ADR-12's fail-closed compatibility check (§ ADR-12) meant
`apps.cart.services.pricing` and `apps.sms.services.sms_service` — which
still called `ShopSettings.load()` with no Store — would break the moment
a second, real `Store` existed, even for that Store's own valid request.
Neither `Cart`, `Order`, `Customer`, nor `SmsTemplate`/`SmsLog` carry a
`store` FK yet (that is PR 6/7/9/10's job), so these services had no
model-level way to derive "which Store" on their own.

**Decision.** Every tenant-sensitive service function that reads
`ShopSettings` takes a required, keyword-only `store` argument — no
default, so a caller cannot silently omit it and fall into compatibility
mode by accident. A new shared helper,
`apps.stores.resolution.resolve_store_for_service(request)`, resolves the
authoritative Store exactly once, at the HTTP boundary (a view, or a
service function that already receives `request`): `request.store` if
already resolved, otherwise the same `resolve_compatibility_store()`
fail-closed check used everywhere else. The resolved, concrete `Store`
object is then threaded down explicitly as a plain function argument
through every deeper call (`cart_totals` → `_free_shipping_threshold`/
`_tax_percent`; `create_order_from_cart`/`change_order_status`/
`simulate_payment` → `send_event_sms` → `get_backend`) — none of those
deeper functions ever call `resolve_store_for_service` or
`resolve_compatibility_store` themselves, and none accept a caller-supplied
Store ID from request data (POST body, query parameter) as authoritative.

**Alternatives considered.** Giving `cart_totals`/`send_event_sms` an
optional `store=None` that falls back to compatibility mode internally —
rejected: that would re-introduce exactly the "quietly using Akhlaghi" risk
ADR-12 exists to close off, just moved one layer deeper, and would make an
explicit `store=None` call indistinguishable from "caller forgot to
resolve one." Adding a `store` FK to `Cart`/`Order` now, ahead of PR 6/7,
to give these services a model-level Store — rejected as unnecessary and
out of scope: every call site already has an authoritative Store available
from the triggering request, so no schema change was needed to make these
services Store-explicit. Passing `request` itself into every deep service
function instead of a resolved `Store` — rejected for the leaf functions
(`cart_totals`, `send_event_sms`, etc.): they are pure business-logic
functions with no reason to depend on Django's request object, and passing
the already-resolved `Store` keeps them independently testable without a
request/response cycle.

**Consequences.** `apps.dashboard.views._resolve_dashboard_store`
(introduced in PR 4) now delegates to `resolve_store_for_service` instead
of duplicating the same "request.store, else compatibility check" logic. A
handful of service functions without prior `request` access
(`create_order_from_cart`, `change_order_status`, `simulate_payment`,
`otp_service.request_otp`, `auth_service.signup`/`create_account_for_guest`)
gained a `store` parameter; their callers across `apps.orders`,
`apps.customers`, `apps.sms`, and `apps.dashboard` were all updated
accordingly — none of those apps' models changed. `apps.core.management.commands.seed_shop`
(no request context) resolves Akhlaghi explicitly by slug rather than via
the request-shaped compatibility check, since it only ever seeds Akhlaghi
demo data.

**Deferred questions.** Whether `resolve_store_for_service` should move out
of `apps.stores.resolution` (a module whose docstring frames it around
"request-time" resolution, even though this function and
`resolve_compatibility_store` are not themselves request-specific) into a
more neutrally-named module is left open — a naming/layering question, not
a functional one, and not worth a file move bundled into this PR.

---

## ADR-14: `Order` Gets a Direct `store` FK (Redundant Store-Owned Child), Not Just `vendor.store`

**Context.** PR#20/ADR-13 deliberately gave `Cart`/`Order` no `store` FK,
since every call site already had an authoritative `Store` available from
the triggering request and `Order.vendor` (itself Store-scoped since PR#21)
made the ownership derivable. PR23 found this indirection was a real,
exploited gap in practice: `apps.dashboard.services.orders_admin_service`/
`customers_admin_service` queried `Order.objects`/`Transaction.objects`
completely unscoped by Store — the exact bug class ADR-13 and PR#21 already
fixed once for catalog, recurring here because there was no `Order.store`
column to filter on directly, only a join through `vendor__store` that
every call site would have had to remember to add correctly, forever.

**Decision.** `Order.store` is now a direct, required
(`on_delete=PROTECT`) foreign key to `Store` — the same "Redundant
Store-owned Child" category as `apps.catalog.ProductVariant.store` (see
`00_PROJECT_MASTER_REFERENCE.md` §8's four-category ownership model): the
authoritative source is still `Order.vendor.store`, but a direct column
exists because per-Store filtering/reporting on `Order` is a proven,
constant need (every dashboard order/invoice/payment/customer query), not
a hypothetical one. `on_delete=PROTECT` — not `CASCADE` like catalog's
Store-owned content — because an `Order` is an immutable financial/
historical record; deleting a `Store` must never silently delete its order
history. The invariant `order.store_id == order.vendor.store_id` is
enforced at two layers: `apps.orders.services.order_service.create_order_from_cart`
(the sole Production write path for `Order` creation) raises `ValueError`
on mismatch before ever touching the database, and `Order.clean()` is a
second, model-level defensive check mirroring `apps.catalog.models.Product.clean()`'s
already-established pattern. A database-level `CheckConstraint` was
considered and rejected — Django's `CheckConstraint` cannot compare two
different tables' columns, and neither SQLite nor the project's intended
production database (PostgreSQL) supports a cross-table CHECK constraint
either, so no implementation would actually provide DB-level enforcement
here; claiming one exists would be a false statement about the schema.

**Migration.** Staged exactly like catalog's original backfill
(`0006`→`0007`→`0008`): `0003_store_scope_orders_schema` (nullable FK +
new `idempotency_key`/`OrderItem.sku`/`OrderItem.variant_label` fields +
`PaymentGateway`/`ShippingMethod.store`, also nullable, plus their new
per-Store slug-uniqueness constraints) → `0004_backfill_orders_store`
(data migration) → `0005_store_scope_orders_enforce_not_null` (NOT NULL).
Unlike catalog's original backfill, `Order.store` did **not** need an
Akhlaghi-guess fallback: every existing `Order` already had a required,
non-null `vendor`, and every `Vendor` already had a required, non-null
`store` (enforced since catalog's own `0008`) — so the backfill derives
`Order.store` deterministically from `Order.vendor.store` for every row,
never guessing or falling back to Akhlaghi. `PaymentGateway`/
`ShippingMethod` had no prior Store relationship at all (the same
situation catalog's `Vendor`/`Category`/`Brand` were originally in), so
their backfill does use the Akhlaghi-exact-slug-or-fail pattern, identical
in shape to `apps/catalog/migrations/0007_backfill_catalog_store.py`.

**Alternatives considered.** Leaving `Order` without a direct `store` field
and instead auditing every dashboard query to join through `vendor__store`
correctly — rejected: this is exactly the "remember to do it everywhere,
forever" pattern that already failed once (the gap this ADR fixes). Giving
`Transaction` its own direct `store` FK too — rejected as unnecessary
duplication: `Transaction.order` is a required FK, and `Order.store` is
now itself required and authoritative, so `Transaction`'s Store is already
unambiguously reachable via `transaction.order.store`; dashboard payment
queries filter via `order__store=store` rather than a redundant column.

**Consequences.** `apps.dashboard.services.orders_admin_service`,
`customers_admin_service`, and `settings_admin_service` all now require an
explicit `store` keyword argument, resolved once per request via
`apps.dashboard.views._resolve_dashboard_store` (already the established
pattern), and every dashboard order/invoice/payment/customer/gateway/
shipping list, detail, and mutation endpoint is Store-scoped — a Store A
user requesting a Store B `Order`/`Transaction`/gateway/shipping-method by
ID or code now gets the repository's standard safe denial (404), not the
object. `Customer` deliberately still has no `store` field (see ADR-6,
still deferred) — `customers_admin_service.annotated_customers` instead
scopes by the existing `orders__store` relationship, so a customer is only
visible in a given Store's dashboard if they have at least one `Order`
there, and their `order_count`/`paid_total` aggregates are computed with
that same Store filter, never a global total.

---

## ADR-15: Checkout Idempotency — a Server-Held Token on `Cart`, Not a Client-Echoed Field or a Random-Code `.exists()` Check

**Context.** The pre-PR23 order-code generator
(`f"{ORDER_CODE_PREFIX}-{random.randint(10000, 99999)}"`, checked via a
plain, non-locked `Order.objects.filter(code=code).exists()`) was never a
real idempotency mechanism — it only avoided colliding on the *code*
string; nothing prevented two Orders being created from one legitimate
checkout submission (double-click, browser retry, network retry). A real
mechanism was needed that: requires no client cooperation (nothing a
compromised or buggy client could omit, forge, or replay across a
different Cart/Store); works identically on SQLite (tests) and PostgreSQL
(production) without relying on Redis or a process-local lock (both
explicitly out of scope for this PR); and closes the concurrent-race
window, not just the easy sequential-retry case.

**Decision.** `Cart` gained a `checkout_token` field
(`secrets.token_urlsafe(32)`, generated server-side, once, lazily, the
first time `apps.orders.services.checkout_service.get_or_create_checkout_token`
is called for that Cart — never read from or influenced by client input).
Because every checkout attempt for the same guest session or logged-in
Customer resolves the *same* `Cart` row (the existing, unchanged
`apps.cart.services.cart_service.get_cart` lookup), a double-click or
retry naturally reads back the identical token with zero new state to
manage and nothing for a client to submit or tamper with. `Order` gained a
matching `idempotency_key` (blank-by-default, uniqueness enforced only
when set — the same `condition=~Q(field="")` partial-uniqueness pattern
already used for `ProductVariant.sku`, so the many existing tests/services
that create Orders without a token are entirely unaffected).
`apps.orders.services.checkout_service.finalize_order` checks for an
existing `Order` with that token *before* checking whether the Cart is
empty (a same-Cart replay after a first, already-successful submission
would otherwise see an emptied cart and wrongly report "cart is empty"
instead of returning the original Order). `apps.orders.services.order_service.create_order_from_cart`
itself repeats that check, then — for the genuine concurrent-race window,
where two requests both pass that check before either commits — wraps
only the `Order.objects.create(...)` call in a nested `transaction.atomic()`
savepoint and catches `IntegrityError`: the losing request's savepoint
rolls back (not the whole transaction), and it re-queries and returns the
winning request's `Order` instead of raising, creating a duplicate, or
double-decrementing stock (the item/stock loop never runs for the losing
attempt, since the `Order.objects.create()` call happens first and fails
before it).

**Alternatives considered.** A hidden form field echoed back by the
client — rejected: requires template changes, and trusts a client-supplied
value's *presence* even if not its content, for no benefit over reading
the value straight off the server-held `Cart` row the request already
resolves. A dedicated `CheckoutAttempt` model — rejected as unnecessary
duplication: `Cart.checkout_token` + `Order.idempotency_key` already give
a complete request → in-flight-attempt → completed-Order chain without a
third table. A process-local lock (e.g. a `threading.Lock` keyed by
Cart ID) — rejected per this PR's explicit scope: it wouldn't work across
multiple application processes/workers in real production deployment, and
the database-level unique-constraint approach above is strictly stronger
(works correctly regardless of process/worker topology) at no extra cost.

**Consequences.** A "true" concurrent-race test cannot be exercised
deterministically against SQLite (its whole-database write lock
effectively serializes concurrent writers rather than reproducing
PostgreSQL's row-level contention) — `apps/orders/tests/test_checkout_correctness.py::CheckoutIdempotencyServiceTests.test_concurrent_race_simulated_via_preexisting_conflicting_order`
instead deterministically pre-creates the "winning" Order with the same
key and asserts the losing call's `IntegrityError`-catch-and-refetch path
behaves correctly — this exercises the exact code path a real race would
hit, without depending on real thread/process timing. Verifying the
mechanism's behavior under genuine PostgreSQL row-level lock contention is
listed as a pre-launch verification item, not something SQLite testing can
substitute for (see `00_PROJECT_MASTER_REFERENCE.md`'s SQLite-vs-PostgreSQL
concurrency-limitation note).

---

## ADR-16: Merchant Admin Portal Domain and Routing — `Store.admin_subdomain` Is a Platform-Assigned Field, Independent of `StoreDomain`; `/admin-portal/` Is the Canonical Route

**Context.** The originating Phase 1B request specifies a target
architecture where a merchant's public storefront
(`https://<public-domain>`) and merchant admin portal
(`https://<admin-subdomain>.rastisi.ir/admin-portal/`) are independent:
changing or losing the public domain must never affect the stable admin
host. Before this PR, the codebase had no concept of an admin subdomain at
all — Host-based Store resolution only ever produced a Store from a
verified `StoreDomain` row (a merchant-supplied, DNS/HTTP-verified public
domain) or the narrow single-Store development fallback. Nothing
distinguished "this Host is this Store's public storefront" from "this
Host is this Store's admin portal" — the same resolved Store served both
purposes through one mechanism. The dashboard itself was also still
mounted at `/admin-panel/`, not the target `/admin-portal/` path.

**Decision.**

1. `Store` gains a new `admin_subdomain` field: a single DNS label
   (`CharField`, `max_length=63`, globally unique, ASCII-only, normalized
   lowercase, validated against a reserved-word list), independent of
   `StoreDomain` — it lives directly on `Store`, not as a `StoreDomain`
   row, precisely because it is platform-assigned and never subject to the
   merchant DNS/HTTP verification lifecycle `StoreDomain` implements.
   `Store.save()` auto-derives a value from `slug` (or, if `slug` isn't a
   valid ASCII DNS label — `Store.slug` allows Unicode — from `public_id`)
   when a caller doesn't supply one explicitly, so every existing
   `Store.objects.create(name=..., slug=...)` call site across the
   codebase and test suite keeps working unmodified; a real
   merchant-onboarding flow can always set an explicit, chosen value later.
   `apps.stores.resolution.resolve_store_for_admin_host(raw_host)` resolves
   a Store from a Host of the exact shape
   `f"{admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"`
   (`RASTISI_ADMIN_DOMAIN_SUFFIX` defaults to `"rastisi.ir"`, environment-overridable).
2. `/admin-portal/` becomes the canonical Merchant Admin Portal URL prefix
   (`shop_core/urls.py`); the previous `/admin-panel/` prefix is kept alive
   only as a 302 (not 301 — deliberately not permanent/cacheable)
   backward-compatible redirect to the equivalent `/admin-portal/` path via
   `apps.core.views.admin_panel_compat_redirect`, preserving both sub-path
   and query string. `admin-portal` (alongside the pre-existing
   `admin-panel`) is added to `apps.content.models.RESERVED_SLUGS` so a
   merchant-authored `ContentPage` can never claim either path.

**What this PR deliberately does NOT do.** `resolve_store_for_admin_host`
is new, tested, standalone infrastructure — like
`StoreResolutionMiddleware`'s own `request.store` before it, it is not yet
*consumed* by `apps.dashboard.decorators.staff_required` to enforce "this
request must have arrived via the admin subdomain, not a public storefront
domain." Wiring that enforcement in is the one remaining piece of "public
storefront domains must not expose the merchant admin portal" from the
Phase 1B request. It was deliberately deferred rather than rushed, because
doing it safely requires first migrating every existing multi-Store
dashboard test's Host fixtures (currently generic hosts like
`dash-a.example.com`, chosen before this ADR existed) to real
admin-subdomain-shaped hosts, and deciding how the existing
single-Store `testserver`/`localhost` development compatibility fallback
(`apps.stores.resolution.resolve_compatibility_store`) should interact with
admin-host enforcement — both are separate, sizeable pieces of follow-up
work of their own, tracked in the Phase 1B report's Known Limitations
rather than done under time pressure in the same pass as the schema and
routing changes.

**Alternatives considered.** Deriving the admin host directly from
`Store.slug` with no separate field — rejected: `slug` is
`allow_unicode=True` (Persian slugs are an explicit product requirement),
so it cannot always serve as a DNS label without a second, independent,
ASCII-only field. Making `/admin-panel/` a permanent (301) alias instead of
a temporary compatibility redirect — rejected: a 301 gets cached by
browsers/proxies indefinitely, which would make the old prefix effectively
permanent infrastructure instead of the removable shim it's meant to be.

**Consequences.** Every `reverse("dashboard:...")` call across the
entire codebase and test suite kept working unchanged through the route
rename, since the URL prefix is defined in exactly one place
(`shop_core/urls.py`'s `include("apps.dashboard.urls")`); only the
hardcoded literal path strings (a handful of test assertions and the
login-redirect logic in `apps.dashboard.decorators`/`apps.dashboard.views.admin_login`)
needed updating. The admin-subdomain-only enforcement gap above means that,
as of this PR, a Store's dashboard is still reachable through any Host that
resolves to it via `apps.stores.resolution.resolve_store_for_service`
(including a verified public `StoreDomain`) — `StoreMembership`
authorization (ADR-13's Phase 1/1A work) still fully prevents cross-Store
data access regardless of which Host was used to get there; what remains
open is only "should this Host be allowed to serve the admin portal for
*any* Store at all," not tenant isolation itself.

## ADR-17: Admin-Subdomain Enforcement Closes the ADR-16 Gap via `resolve_store_for_admin_request`, Not by Changing `resolve_store_for_admin_host`

**Context.** ADR-16 shipped `Store.admin_subdomain` and
`resolve_store_for_admin_host(raw_host)` as new, tested, standalone
infrastructure but explicitly did not wire it into
`apps.dashboard.decorators.staff_required`, leaving the dashboard reachable
through any Host that resolved to a Store at all — including a merchant's
public `StoreDomain`. Phase 1C's mandate was to close that gap first,
before any further Product Management work, without breaking the existing
single-Store `testserver`/`localhost` developer-compatibility fallback that
`resolve_compatibility_store()` provides for local development and the bulk
of the test suite.

**Decision.** A new function,
`apps.stores.resolution.resolve_store_for_admin_request(request)`, is the
single call site `staff_required`/`admin_host_required` use. It tries
`resolve_store_for_admin_host(request.get_host())` first; only if that
returns `None` *and* the Host is one of the recognized development hosts
(`testserver`, `localhost`, etc.) does it fall through to
`resolve_store_for_request(request)` (the general public-domain-or-compat
resolver). Any other unresolved Host is a hard `Http404` — never a redirect,
never a fallback guess. `resolve_store_for_admin_host` itself is
unchanged from ADR-16; the new function composes it with the existing
development allowlist rather than teaching the admin-only resolver about
development hosts directly, keeping "what counts as an admin host in
production" and "what the dev/test convenience fallback allows" as two
separately reasoned concerns.

**Consequences.** A request to the dashboard over a Host that is a
verified public `StoreDomain` (but not that Store's `admin_subdomain`) now
404s instead of rendering the dashboard — verified by
`apps/stores/tests/test_admin_host_enforcement.py`. Six existing
multi-Store dashboard test files that previously used arbitrary
`*.example.com`-shaped Hosts (`test_membership_authorization.py`,
`test_catalog_store_isolation.py`, `test_order_store_isolation.py`,
`test_gateway_shipping_store_isolation.py`, `test_admin_superuser_gate.py`,
`test_footer_config.py`) were migrated to set a real `admin_subdomain` and
request against a `*.rastisi.ir`-shaped Host, since a Host that resolves to
*no* Store's admin subdomain now correctly 404s rather than serving the
dashboard by accident. A related, previously-latent production bug was
found and fixed in the same pass: `apps.core.context_processors.shop_settings`,
`apps.catalog.context_processors.nav_categories`, and
`apps.content.context_processors.footer_settings` all called into
`ShopSettings.load()`/`FooterSettings.load()`/`resolve_store_for_service()`
unconditionally, which raised an unhandled `StoreResolutionError` — and
therefore a 500, not a 404 — whenever Django's own 404 handler tried to
render a page for an unresolvable Host with two or more Stores in the
database. All three now catch `StoreResolutionError` (and the relevant
not-provisioned error) and return an empty context, so an unresolvable Host
reliably 404s end-to-end instead of 500ing on whichever template happens to
render first.

**Alternatives considered.** Teaching `resolve_store_for_admin_host` itself
to accept development hosts — rejected: it would blur "the shape of a real
admin host" with "what a developer's machine is allowed to pretend," and
every non-admin caller of `resolve_store_for_admin_host` (there are none
today, but the function is public API) would inherit the dev-only
behavior. Redirecting an unresolvable admin Host to `catalog:home` instead
of 404ing — rejected: it would need to resolve *some* Store to build that
redirect, which is exactly the ambiguity a fail-closed design must refuse
to guess at; a wrong-membership Host still redirects to `catalog:home`
(the user has a Store to go back to), but an unresolvable Host has none.

## ADR-18: Variant-Specific Product Images Are `ProductImage.variant` (Nullable FK, `SET_NULL`), Not a Separate Model

**Context.** Phase 1C's Product Management scope required merchants to be
able to associate specific gallery images with a specific `ProductVariant`
(e.g., a red T-shirt's photos distinct from the blue one's), while the
existing `ProductImage` gallery (product-level, ordered, one designated
cover) had no notion of variants at all. The prototype under review shows
per-variant image swapping on the storefront product page.

**Decision.** `ProductImage` gains one new field: `variant = ForeignKey
("ProductVariant", null=True, blank=True, on_delete=SET_NULL,
related_name="images")`. A blank `variant` means "general product image,
shown regardless of selected variant" (the existing, pre-Phase-1C
behavior); a set `variant` means "specific to this variant only."
`ProductImage.clean()` rejects a `variant` that does not belong to
`self.product` — the same defense-in-depth pattern `Product.clean()`
already uses for `brand`/`category`/`vendor`. `ProductVariant.display_image`
is a new convenience property: the variant's own first image if one
exists, otherwise the product's `cover_image` — so every code path that
wants "the one image to show for this variant" (the dashboard variant
table, and any future storefront variant-switcher) has a single fallback
rule to depend on, rather than re-implementing the "does this variant have
its own image?" check at every call site. No new upload path exists for
variant images: merchants upload into the same product-level gallery as
before and then assign an existing image to a variant via a
`<select>` per image (`dashboard:product-image-variant`), rather than a
separate per-variant upload form — reusing the existing validated/resized
upload pipeline (`apps.catalog.services.product_image_service`) instead of
duplicating it.

**Consequences.** Deleting a `ProductVariant` never deletes its images —
`SET_NULL` demotes them back to general product images automatically at
the database level, with no application code needed to "rescue" them; this
was a deliberate choice over `CASCADE`, since a merchant deleting one color
variant should not silently lose photography that may still be reusable.
Because `related_name="images"` is added to `ProductVariant` (mirroring
`Product.images`), `variant.images.all()` and `product.images.all()`
coexist without collision — a `ProductImage` always belongs to exactly one
`Product` (unchanged) and *optionally* to one of that same `Product`'s
`ProductVariant`s.

**What this PR deliberately does NOT do.** The storefront product-detail
page does not yet swap displayed images when a shopper selects a variant —
this phase only builds the admin-side association (upload → assign →
persist, all tenant/product-isolated and tested) and the data model
(`display_image`) a storefront feature would consume. Wiring
`display_image` into the actual storefront variant-selector UI is
out of scope for Phase 1C and is recorded as a remaining gap in the Phase
1C report.

**Alternatives considered.** A separate `VariantImage` model (own table,
own upload form) — rejected: it would duplicate the entire validated
upload/resize/thumbnail pipeline in `product_image_service.py` for no
behavioral gain, since "an image that may or may not belong to a variant"
is exactly what a nullable FK expresses. Storing multiple images per
variant via a many-to-many instead of each `ProductImage` pointing at one
variant — rejected: the prototype and the existing product gallery both
model "one image, one owner, explicit order/cover flag"; a M2M would need
its own through-model to carry per-pair ordering, which is exactly the
`ProductImage.order`/`is_cover` shape already in place, just duplicated.

---

## ADR-19: Descriptive Attributes and Variant-Generating Options Are Separate Models That Optionally Share One `Attribute` Definition

**Context.** Phase 1D requires two behaviorally distinct concepts the prompt
itself insists must not be merged: a *descriptive attribute* ("Material:
Cotton") that describes a product but never creates a purchasable row, and
a *variant-generating option* ("Color: Green/Blue/Yellow") whose values are
combined into `ProductVariant` rows. The existing codebase already has one
single-axis, ad-hoc variant mechanism (`ProductVariant.attribute`/`.value`,
free-text CharFields, no shared definition, no descriptive-attribute
concept at all) — extending it in place to also mean "the reusable
Store-wide catalog of attribute definitions" would conflate a per-product
label with a Store-owned, reusable schema.

**Decision.** A new Store-owned `Attribute` model is the single reusable
definition: name, code, data type, display type, unit, and boolean flags
including `is_variant_axis` (whether this attribute is *eligible* to
generate variants — eligibility, not a commitment; a Store can define
"Material" once and use it descriptively on some products while never
using it as a variant axis, and use "Color" both descriptively on
non-variable products and as a variant axis on others). Two separate
product-scoped models consume it for the two distinct behaviors:
`ProductAttributeValue` (a Product's descriptive assignment: one row per
product+attribute for scalar types, multiple rows for multi-select) and
`ProductOption` (a Product's variant-generating axis — `position`-ordered,
own `ProductOptionValue` children). Both `ProductAttributeValue.attribute`
and `ProductOption.attribute` are optional FKs to the same `Attribute`
row — a merchant *may* pick "Color" from the shared definition, or a
`ProductOption` may be created with only a free-text `label` and no linked
`Attribute` at all (matching the prototype's own "custom variant attribute"
flow, where a merchant types an arbitrary axis name with no schema
behind it).

**Consequences.** The existing single-axis `ProductVariant.attribute`/
`.value` fields are *not* removed or migrated — see ADR-20's "Consequences"
for why they are repurposed as generated display fields rather than
identity. A Store's `Attribute` catalog and a specific Product's
`ProductOption` axes can diverge in the ordinary case (most attributes are
descriptive-only, never linked to any `ProductOption`), which is the
correct shape: not every attribute is a variant axis, and the eligibility
flag exists precisely so the admin UI can filter "attributes worth
offering as a variant axis" without a second registry.

**Alternatives considered.** One unified `Attribute`-with-variant-behavior
model, distinguishing descriptive vs. variant-generating only by whether
any `ProductOption` row references it — rejected: it would make "is this
attribute currently a variant axis" a derived, per-product fact instead of
a Store-level eligibility declaration, so the admin attribute-list page
could never show "eligible for variants" as a stable column without an
expensive per-row subquery, and a merchant could not mark an attribute
variant-*ineligible* (e.g. "Warranty" should never be offered as an axis)
without it being enforced anywhere. Two entirely disconnected schemas (no
shared `Attribute` at all, `ProductOption.label` and
`ProductAttributeValue`'s type both free-text per product) — rejected: it
would mean re-typing "Color" with a fresh, unrelated spelling on every
product, with no Store-wide filterable/searchable/comparable attribute
catalog at all, which the prompt's Attribute Definitions section (§7)
explicitly requires.

## ADR-20: Stable Variant Combination Identity Is a `VariantOptionValue` Through-Table Plus a Derived `combination_key`, Not the Legacy `attribute`/`value` Strings

**Context.** `ProductVariant.attribute`/`.value` (pre-existing) are
free-text `CharField`s with a `normalized_attribute`/`normalized_value`
uniqueness constraint — adequate for one axis, but the prompt explicitly
forbids using a display string as multi-axis identity ("Green / M" must
not be the source of truth), since renaming a value or reordering axes
must never be mistaken for a new combination.

**Decision.** A new `VariantOptionValue` model is the real, normalized
per-axis relation: one row per `(ProductVariant, ProductOption,
ProductOptionValue)`, so a three-axis variant has exactly three rows, each
pointing at an immutable `ProductOptionValue` primary key — renaming a
value's label or an option's label changes no `VariantOptionValue` row at
all. `UniqueConstraint(variant, option)` guarantees a variant has at most
one value per axis; `UniqueConstraint(variant, option_value)` is a second,
redundant safety net. Because comparing sets of FK rows on every
generation/reconciliation pass is not cheap and cannot be expressed as a
single database uniqueness constraint, `ProductVariant` also gets a
derived `combination_key`: a deterministic string built by the generation
service from the *sorted* `ProductOptionValue` primary keys of a
combination (e.g. `"14-27-31"` — sorted so that submission order of
`Color=Green, Size=M` vs. `Size=M, Color=Green` produce the identical
key). `UniqueConstraint(product, combination_key, condition=~Q
(combination_key=""))` (the same `~Q(field="")`-guarded-blank pattern
`ProductVariant.sku`'s own uniqueness constraint already uses) then gives
duplicate-combination prevention a real database constraint, not just
service-layer diligence. `combination_key` is written *only* by the
generation service, alongside the `VariantOptionValue` rows it is derived
from — it is never a directly user-editable field.

**Consequences.** Legacy single-axis variants (created via the
pre-existing `bulk_create_variants`/`create_variant` service, unchanged by
this phase) simply never get a `combination_key` — it stays `""`, exempt
from the new constraint, and the new generation/reconciliation engine
explicitly excludes `combination_key=""` rows from its own bookkeeping
(`ProductVariant.objects.exclude(combination_key="")`), so a Product using
the legacy mechanism is completely invisible to — and completely
unaffected by — the new engine. `ProductVariant.attribute`/`.value`
survive as generated *display* fields for multi-axis variants too
(populated by joining each axis's/value's label, e.g. `attribute="رنگ /
سایز"`, `value="سبز / M"`) purely so every existing template, the order
snapshot fields, and `__str__` keep working unmodified — but they carry no
identity weight for multi-axis variants; only `combination_key` and the
`VariantOptionValue` rows do. A Product cannot mix the legacy single-axis
flow and the new `ProductOption` flow at the same time — `add_product_
option` refuses to create the first axis while any `combination_key=""`
variant still exists on that Product, so a merchant must first clear
legacy variants before opting into multi-axis (or vice versa is simply
never necessary, since generation never touches legacy rows). This is a
deliberate simplification recorded here, not a silent gap: mixed-mode
products (some variants legacy, some multi-axis, on the same Product) are
out of scope.

**Alternatives considered.** Hashing the combination with a cryptographic
hash (e.g. SHA-1 of sorted IDs) instead of a plain sorted join — rejected:
a plain sorted join of small integer IDs is already short, human-
debuggable in the Django admin/shell, and collision-free by construction
(distinct ID sets always sort to distinct strings), so a hash would only
add opacity with no benefit. Relying on `VariantOptionValue` rows alone
(a `GROUP BY`/`HAVING` query comparing per-variant ID sets) instead of a
denormalized `combination_key` column — rejected: the reconciliation
service runs a "does this desired combination already exist" lookup once
per combination on every `generate_variants()` call (up to the
performance test's 125 combinations), and a single indexed string-equality
lookup is a straightforward, obviously-correct way to keep that lookup a
single query instead of N relational comparisons.

## ADR-21: Variant Reconciliation Never Hard-Deletes — Obsolete Combinations Are Marked, Never Removed, and Axis Removal Requires an Explicit Regeneration Pass

**Context.** Changing a Product's options after variants already exist —
adding a value, removing a value, removing an entire axis, renaming,
reordering — can each change which combinations *should* exist, while
existing `ProductVariant` rows may already carry real SKUs, prices,
inventory, images, and (via `OrderItem`) irreversible historical sales
records. The prompt is explicit that guessing which data to keep, or
silently merging/deleting, is unacceptable.

**Decision.** `generate_variants(product)` is the only place combinations
are ever created or retired, and it follows one rule for every scenario:
compare the *desired* set of combinations (the Cartesian product of
currently-active axes × currently-active values) against the *existing*
set (`ProductVariant` rows with a non-blank `combination_key` on this
Product); a combination present in both is preserved byte-for-byte (same
primary key, SKU, price, `compare_at_price`, `cost`, stock, images,
`created_at` — nothing about the row is touched beyond, if needed,
clearing an `is_obsolete` flag); a combination only in *desired* gets a
newly created `ProductVariant`; a combination only in *existing* is marked
`is_obsolete=True` and `is_active=False` — **never deleted**. `is_obsolete`
is a distinct field from the pre-existing `is_active` specifically so the
admin UI can tell "a merchant turned this off" apart from "this
combination no longer matches the Product's current options" — the latter
is reported back to the merchant as an explicit, named list
(`GenerationResult.obsoleted`) after every regeneration, not silently
absorbed. Removing an axis is not a separate code path: a merchant
deactivates a `ProductOption` (`is_active=False`) — which by itself changes
nothing — and then must explicitly re-run `generate_variants()`, which
naturally treats every combination that included that axis's values as no
longer desired and marks them obsolete, following the exact same rule as
removing one value. This is the prompt's own suggested safe policy ("block
destructive axis removal until the merchant confirms... document a
deterministic policy") implemented as "nothing destructive happens until
an explicit regeneration action, and that action's only behavior is mark-
obsolete, never delete."

**Consequences.** Renaming a `ProductOptionValue.label` or a
`ProductOption.label` touches no `combination_key` (ADR-20) and is
therefore invisible to reconciliation — the desired/existing comparison
is keyed on primary keys, not labels, so a rename can never look like "this
combination no longer exists, create a new one." Reordering `ProductOption
.position` changes which order `generate_variants()` iterates axes in
(affecting new variants' generated `attribute`/`value` display strings and
every variant's recomputed `display_order` — see ADR-20's Alternatives),
but never changes any `combination_key`, since the key is built from
*sorted* value IDs, independent of axis order. An obsoleted variant that
was the Product's `is_default` variant is never left dangling: `generate_
variants()` always ends by calling the same default-selection routine
`add_product_image`'s cover-image "steal the flag" pattern uses — if no
active, non-obsolete variant currently holds `is_default=True`, the first
one (by the freshly recomputed `display_order`) is promoted automatically,
so a Product with any active variant always has exactly one default,
enforced by `UniqueConstraint(product, condition=Q(is_default=True))` at
the database layer too. Because obsolete variants are never deleted,
`OrderItem.variant` (a `PROTECT`/`SET_NULL` FK depending on the pre-
existing order-history design — unchanged by this phase) is never left
pointing at a vanished row, and a merchant who removed a value by mistake
can simply re-add it: the next `generate_variants()` run finds the old
`ProductOptionValue`/combination still exists (values are soft-deactivated,
not hard-deleted either — see §8/§14) and clears `is_obsolete` on the
original row instead of creating a duplicate.

**Alternatives considered.** Hard-deleting obsolete variants with no order
history — rejected: even a variant with zero orders may still hold a
merchant-uploaded image or a manually-set price the merchant would
reasonably expect to survive a value being removed and re-added a minute
later; "no orders reference it yet" is not the same guarantee as "this
data is safe to discard," and the mark-obsolete rule needs no special case
for that distinction, which is itself a simplicity win. Automatically
merging an axis-removal's collapsed combinations (e.g. "Color+Size"
becoming "Color only" summing the removed Sizes' stock into the surviving
Color row) — rejected: the prompt explicitly prohibits silently merging
inventory, SKU, pricing, or media, and no business rule for *which* of N
now-redundant rows' SKU/price/image should "win" can be inferred safely
without asking the merchant, which this phase's UI does not yet build (see
Known Limitations in the Phase 1D report) — today, axis removal always
produces obsoleted rows the merchant must manually review, never an
automatic merge.

---

## ADR-22: Industry Templates Are Platform-Owned and Read-Only; Installation Deep-Copies Into Store-Owned Records, Never Links to the Shared Template

**Context.** Phase 1E needs a library of reusable per-industry catalog
structures (categories, attributes, values, category→attribute mappings,
recommended variant options) that a merchant can install into their Store
to avoid designing a catalog from scratch. The obvious risk: if a Store's
catalog structure is represented as *live references* into shared
`IndustryTemplate` rows, any future edit to the template (fixing a typo,
adding a value) could silently ripple into every Store that installed it,
and a Store's own customization (renaming a category, disabling an
optional attribute) would either be impossible to express or would corrupt
the shared template for every other Store.

**Decision.** `IndustryTemplate` and its children
(`TemplateCategory`, `TemplateAttribute`, `TemplateAttributeValue`,
`TemplateCategoryAttributeMapping`, `TemplateRecommendedOption`) are
platform-owned, have no `store` FK anywhere in the chain, and are never
writable through any Store-scoped/`StoreMembership`-gated code path — only
Django admin (superuser) or a management command touches them (§26).
`apps.catalog.services.industry_template_service.install_industry_template
(store, industry_template)` performs a **deep copy**: it creates genuinely
new, Store-owned `Category`, `Attribute`, `AttributeValue`,
`CategoryAttributeSchema`, and `CategoryRecommendedOption` rows, one for
one, from the template's data. After installation, a Store's catalog rows
have **no live FK back to the template rows that produced them** for
day-to-day operation — the only connection is a nullable, purely
informational traceability FK (`Category.source_template_category`,
`Attribute.source_template_attribute`, both `SET_NULL` on template
deletion) plus one `StoreIndustryInstallation` row recording which
template (and which version) a Store installed and when. Editing a
`Category`, `Attribute`, or `CategoryAttributeSchema` row after
installation is *ordinary Store-owned catalog editing* — the exact same
code path (`attribute_service`, the Category views) a merchant who never
installed any template uses. There is no special "templated" mode a
Category can be in.

**Consequences.** A future edit to a platform `IndustryTemplate` can never
affect an already-installed Store, by construction — there is no
mechanism by which it could, since nothing in a Store's catalog holds a
live reference to template data at query time. This also means Phase 1E
does not need to build any "protect template-derived fields from merchant
edits" enforcement: a merchant can rename, reorder, archive, or add to
their installed categories/attributes exactly as freely as anything they
built by hand, because after installation there is no meaningful
distinction left to protect. The cost of this choice is real duplication:
ten Stores installing the same "Clothing" template each get their own
full copy of every category/attribute/value row — accepted deliberately,
since SQLite/Postgres row counts at this scale are not a concern, and the
alternative (shared/linked records with an override layer) is
categorically more complex to build correctly and query efficiently.
`install_industry_template` also **reuses** an existing Store `Attribute`
by `code` instead of creating a duplicate if one already exists with a
matching code (`get_or_create`) — this is the one place a merchant's
*pre-existing* catalog data intentionally interacts with installation, and
it only ever reuses, never overwrites, an existing row's other fields.

**Alternatives considered.** Live FK from Store `Category` to
`TemplateCategory` with a per-Store override table layered on top —
rejected: correctly resolving "effective" values through an override layer
at every read (product form load, category list, schema resolution) adds
real query complexity for a benefit (saving template-update propagation)
this phase's own §23 (versioning) explicitly says must *not* happen
automatically anyway — the override layer would exist only to prevent a
behavior the product spec says should never occur, making it pure
unrewarded complexity. A "linked copy with detach-on-edit" hybrid
(reference the template until the merchant's first edit, then fork) —
rejected as needless statefulness: every code path that touches a
Category/Attribute would need to first check "is this still linked or has
it forked," for a benefit no requirement asks for.

## ADR-23: Category Attribute Schema Resolution — Direct Mappings Always Win Over Inherited Ones; Inheritance Is Opt-Out Per Mapping, Not Per Category

**Context.** Phase 1E's Category hierarchy (pre-existing, two levels:
parent/child `Category` rows) needs Attribute schema *inheritance* — an
Attribute assigned to "Clothing" should apply to "Clothing → T-Shirts" —
while guaranteeing the Product form is handed one normalized list with no
duplicate Attribute entries when the same Attribute is reachable through
more than one path (assigned directly on the child *and* inherited from
the parent).

**Decision.** Each `CategoryAttributeSchema` row (the mapping of one
`Attribute` onto one `Category`) carries its own
`is_inherited_by_children` boolean (default `True`) — inheritance is a
property of the *mapping*, not a category-wide switch, so a merchant can
mark one specific Attribute assignment as "just for this category, don't
propagate to children" without affecting any other mapping on the same
category. `apps.catalog.services.category_schema_service.resolve_category_schema
(category)` walks from `category` up through every ancestor
(`category.parent`, `category.parent.parent`, …), collecting: (a) *every*
`CategoryAttributeSchema` row directly on `category` itself, regardless of
that row's own `is_inherited_by_children` value (a category always uses
its own direct mappings — that flag only ever governs propagation
*downward* to children, never affects the category the row lives on), and
(b) for each ancestor, only the ancestor's rows where
`is_inherited_by_children=True`. When the same `Attribute` appears from
more than one source (e.g. a direct mapping on the child *and* an
inherited one from the parent), **the most specific mapping wins** — the
child's own direct row (if any) is used verbatim (its `group`/`order`/
`is_required`/help text/etc.), and the ancestor's row for that same
Attribute is discarded entirely rather than merged field-by-field. Direct
mappings are looked up first (closest ancestor — the category itself —
wins over anything further up), so a two-level-removed grandparent's
mapping loses to a parent's mapping for the same Attribute, which in turn
loses to the category's own.

**Consequences.** The Product form, `build_product_specification`, and
publish validation all consume the single list `resolve_category_schema`
returns and never need to reason about inheritance themselves — each
`ResolvedSchemaEntry` in that list already carries a resolved
`is_required`/`group`/`display_order`/etc. and a `source_category`
(which category in the chain the winning mapping actually came from) plus
an `is_inherited` boolean, purely for UI display ("این ویژگی از «پوشاک»
به ارث رسیده" badges) — never for re-deriving behavior. A merchant who
wants a child category to *not* show a parent's optional Attribute cannot
do so by editing the child (there is no child-side "hide this inherited
Attribute" row in this phase) — only by editing the parent mapping's
`is_inherited_by_children` flag directly (which affects *all* of that
parent's children uniformly). This is a deliberate, named scope
reduction — a proper per-child "hide this one inherited Attribute"
override is listed as a remaining gap in the Phase 1E report rather than
built now, since it would require a third kind of record (a child-level
suppression row) whose interaction with future re-installation/versioning
was not resolvable within this phase's time.

**Alternatives considered.** Category-wide `inherits_from_parent` boolean
(all-or-nothing per category) — rejected: too coarse for the concrete
prompt example (a Store wants "Country of Manufacture" inherited
everywhere but "Season" only on seasonal subcategories), which needs
per-mapping control. Field-by-field merge of parent and child mappings for
the same Attribute (e.g. take the child's `group` but the parent's
`is_required`) — rejected: unpredictable and hard to explain to a
merchant ("why is this field required here but its help text is from
somewhere else?"); "closest mapping wins outright" is a rule a UI badge
can state in one sentence.

## ADR-24: Product Attribute Values Are Never Deleted on Category Change — They Become Invisible (Not in the New Schema) Until an Explicit Cleanup Action Is Taken

**Context.** Changing a Product's Category changes which
`CategoryAttributeSchema` entries apply to it. A `ProductAttributeValue`
row that was valid under the old Category (e.g. "Sleeve Type: Long" on a
T-Shirt) may not correspond to any Attribute in the new Category's schema
(e.g. after moving the Product to "Shoes"). The prompt is explicit:
existing data must never be silently deleted, and any destructive cleanup
needs an explicit merchant confirmation.

**Decision.** No new field or flag is added to `ProductAttributeValue`
for this. Changing `Product.category` is an ordinary field update — it
does not trigger any automatic deletion, migration, or mutation of
existing `ProductAttributeValue` rows at all. Instead,
`apps.catalog.services.category_schema_service.orphaned_product_attribute_values
(product)` computes, on demand (at product-edit-page render time and
before publish), the set of a Product's existing `ProductAttributeValue`
rows whose `attribute` is *not* present in `resolve_category_schema
(product.category)`'s current result — these are "orphaned," not
deleted, not hidden from the database, simply no longer part of what the
current Category's schema asks for. `build_product_specification`
(§ "Product Specifications") only ever renders schema-membership-filtered
values, so an orphaned value never appears in specification output or the
active product-edit form automatically — but it still physically exists
and is trivially recoverable (e.g. switching the Category back). Deleting
an orphaned value is only ever a distinct, explicit action
(`cleanup_orphaned_attribute_values(product)`) the product-edit UI offers
behind its own confirmation, never something a Category-change save does
by itself.

**Consequences.** A Category change is always non-destructive and instant
— there is no "are you sure, this might delete data" interstitial on the
save action itself, because the save action provably cannot delete
anything. The product-edit page, after a Category change, shows a
distinct "این مقادیر دیگر با دسته‌بندی فعلی مطابقت ندارند" (these values
no longer match the current category) panel listing exactly the orphaned
values with a manual "پاک‌سازی" (cleanup) button — the warning the prompt
requires exists at the point of *consequence* (viewing the product after
the change) rather than *action* (the change itself), which is simpler to
reason about and impossible to accidentally skip past (unlike a
confirm-dialog a merchant might reflexively click through). Publish
validation (§ "Draft and Publish Validation") only checks *required*
attributes of the *current* schema — an orphaned value from the old
Category, being outside the current schema entirely, is never counted
toward or against publish-readiness either way.

**Alternatives considered.** A `ProductAttributeValue.is_orphaned` boolean
flag, set automatically on Category change — rejected: it would need to be
kept in sync any time *either* the Product's Category *or* the Category's
own schema changes (e.g. a merchant removes an Attribute mapping from a
Category entirely, orphaning it for every Product in that Category at
once) — computing it on demand from the current schema is simpler,
always-correct by construction, and never goes stale. Hard-blocking a
Category change until the merchant manually resolves every orphaned value
first — rejected: the prompt explicitly asks that old values be
*preservable*, not that a Category change be blocked by pre-existing data,
and forcing resolution up front would make Category changes needlessly
disruptive for what is very often a harmless, later-cleaned-up situation.

## ADR-25: Industry Template Versions Are Immutable Snapshots; Existing Installations Never Auto-Update, and No Update-Application UI Ships This Phase

**Context.** Industry templates will need to evolve over time (a new
recommended Attribute, a corrected category name) without ever silently
mutating a Store's already-installed, possibly-customized catalog — the
prompt's §23 explicitly forbids automatic overwrites of merchant changes.

**Decision.** `IndustryTemplate.version` is a plain `PositiveIntegerField`,
and `(slug, version)` is unique — a "new version" of an industry is
authored as an **entirely new `IndustryTemplate` row** (new PK, new full
tree of `TemplateCategory`/`TemplateAttribute`/etc.), never an in-place
edit of an existing template's children. This makes every
`IndustryTemplate` row, once created, an immutable historical snapshot by
construction — there is no code path in this phase that mutates a
`TemplateCategory`/`TemplateAttribute`/etc. row after creation (the seed
management command, per ADR-below-on-idempotency, only ever creates
missing rows, never edits existing ones — see the Phase 1E report §5).
`StoreIndustryInstallation.installed_version` records exactly which
version a Store installed. A Store may only ever install **one**
`IndustryTemplate`, period, for its entire lifetime — see the Phase 1E
report's Industry Change Policy: `install_industry_template` rejects any
call once a `StoreIndustryInstallation` row already exists for that Store
(enforced by service-level check plus a `UniqueConstraint(fields=["store"])`
as a database-level backstop), regardless of whether the new call targets
the same industry, a newer version of it, or an entirely different
industry. This is deliberately the strictest of the prompt's own
explicitly-acceptable §22 options ("Block change after installation"),
chosen because it requires no new merge/reconciliation logic at all — the
one thing every other listed option (additional-template-without-deleting,
required-migration-workflow, empty-catalog-required) would need.

**Consequences.** "Existing Stores keep their copied records; new Stores
receive the latest template" (the prompt's own preferred default in §23)
holds trivially: a new `IndustryTemplate` version is simply a new row that
future installations pick, and no existing `StoreIndustryInstallation` or
the Store-owned rows it produced are ever touched by that new row's
existence. No "review available updates and apply them selectively" UI is
built this phase — the data model (`installed_version` vs. the current
max version for that `slug` being queryable) supports building one later
without a schema change, and this gap is named explicitly in the Phase 1E
report rather than left ambiguous. A Store that installs the wrong
industry, or whose business changes industries entirely, has no supported
in-product path to switch in this phase — a platform operator would need
to intervene directly (e.g. via Django admin) — a real, named limitation,
not an oversight.

**Alternatives considered.** Mutable templates with a `version` field that
increments in place on edit — rejected: it reintroduces exactly the
"does an edit affect already-installed Stores" ambiguity ADR-22 exists to
foreclose; an editor could all too easily "fix a typo" on a live template
row believing it only affects future installs, when in a mutable-row
design the meaning of "already installed" vs. "the template" is not
statically distinguishable without extremely careful, easy-to-get-wrong
discipline. Allowing a Store to install additional templates alongside its
first (union of multiple industries' structures) — rejected for this
phase specifically because merging two industries' category trees and
attribute schemas without collision (two industries both wanting a
"Color" attribute with different `data_type`s, for instance) is a real
design problem the prompt itself does not resolve, and the single-
installation-only policy sidesteps it entirely without losing any
capability a Store lacks another way (a merchant can always build
additional categories/attributes by hand after installing their one
template — nothing is blocked, only *automatic* multi-industry merging
is).

---

## ADR-26: Industry Template Quality Is a Structured, Reusable Validation Service — Not a Vanity Score

**Context.** Phase 1F must scale the Industry Template catalog from 10 to
30 (and eventually further), which makes it realistic that a future
template author writes something structurally broken (a dangling parent
reference, a required Attribute with no obtainable choice Values) or
merely shallow (a Category with no Attribute mappings at all). The prompt
explicitly warns against "a fake quality score" that could make severe
errors invisible behind a high aggregate number.

**Decision.** `apps.catalog.services.template_validation_service.validate_industry_template(template)`
returns a structured `TemplateValidationResult` dataclass: a list of
typed `ValidationIssue` entries (`code`, `severity` — `error`/`warning`/
`info`, `message`, `model_type`, `identifier`, `remediation`), a
`metrics` dict (category/attribute/value/mapping/recommendation counts),
and a derived `readiness` recommendation. **Any `error`-severity issue
unconditionally blocks `production_ready`**, regardless of how many other
dimensions pass — there is no numeric score that can average away a
structural defect. A secondary, explicitly-documented `quality_score`
(0–100, weighted: structure 25 / attribute completeness 20 / schema
quality 20 / variant recommendations 15 / merchant usefulness 10 /
installability 10 — see `QUALITY_SCORE_WEIGHTS` in the service module) is
computed *only* from `warning`/`info`-level findings once zero errors are
present, and is advisory metadata, never a gate — a template with 0
errors and a low score is still eligible for `production_ready` review
if a platform operator explicitly promotes it; the score is a triage aid
for operators comparing templates, not an automated pass/fail threshold
on its own.

**Consequences.** The same service function is called identically by the
`validate_industry_templates` management command, the Django admin
action, the seed command (to set initial `readiness`), and every test —
one source of truth for "what makes a template good," matching the
prompt's explicit requirement that validation logic must not live inside
a view or command. Adding a new quality rule means adding one function to
`_STRUCTURAL_CHECKS`/`_CONTENT_CHECKS` in the service module and it is
immediately live everywhere.

**Alternatives considered.** A single opaque 0–100 score as the only
output — rejected outright per the prompt's explicit prohibition and
because it cannot express "which specific thing is wrong," which is what
a template author actually needs to fix it. Silent logging-only
validation with no persisted/queryable result — rejected because
platform operators need to inspect *why* a template is not
`production_ready` without re-running validation by hand each time (see
ADR context in §11 of the Phase 1F report for the persistence policy).

### ADR-26 addendum — Merchant-completeness gate (REVIEW_REQUIRED)

**Context.** Structural validity is necessary but is not "a merchant can start
selling with this". A template with one generic category and three free-text
fields passes every structural check yet gives a clothing/food/electronics
merchant nothing they could not type themselves. Before this addendum 101 of
107 latest templates were `production_ready`, of which ~75 were that skeletal
pattern.

**Decision.** `validate_industry_template` additionally evaluates a
*sector-aware completeness profile* (`completeness_profile_for(sector)`):

| Profile | Sectors | Needs |
|---|---|---|
| `product` | retail, digital, food, home, beauty, sport, culture, auto, industry | ≥4 categories, ≥5 attributes, ≥8 category↔attribute mappings, schema coverage (with parent inheritance) on ≥50% of leaf categories and ≥2 mapped categories, ≥1 choice attribute with ≥2 values; **retail** also ≥1 recommended variant axis |
| `service` | services | ≥3 service categories; product attributes/mappings/variant axes are not required (and not prohibited) |
| `free_form` | other | deliberately generic; structural validity only |

Gaps are `review`-severity issues (`COMPLETENESS_*`), kept apart from
`errors`. Recommended readiness: any error → `validation_failed`; else any gap →
`review_required`; else `production_ready`. The advisory `quality_score` is
capped at 69 while gaps exist. "No filterable mapping" stays a warning, not a gap.
Strict global mode is **not** enabled. `validate_and_persist` stores the gap list
under `metrics["completeness"]`; `deprecated`/`archived` stay operator decisions.

**Consequences.** Merchant-facing selectors (`offerable_industry_templates`,
onboarding, store creation, public supported-industries page) already offer only
`production_ready`, so `review_required` templates simply stop being offered
for **new** installations. Existing `StoreIndustryInstallation` rows and the
Categories/Attributes copied to a Store are never deleted or rewritten — readiness
governs new installs only. `seed_industry_templates` runs `validate_and_persist`
for every entry, and `audit_industry_templates --apply` does the same for
platform rows already in the database, so an existing environment converges
without manual DB editing. Enriching a template (editing the registry entry) and
re-running seed promotes it automatically.
The backlog is in `docs/docs/product/reports/INDUSTRY_TEMPLATE_COMPLETENESS_AUDIT.md`.

## ADR-27: Template Versioning Stays on `IndustryTemplate.(slug, version)` — No Separate Version-Family Model

**Context.** Phase 1F requires representing "Industry family identity,
multiple versions, one version installed in a Store, a newer version
available, comparison between versions" — the prompt suggests a
`IndustryTemplate` → `IndustryTemplateVersion` split as one *possible*
shape, but explicitly permits keeping the existing architecture if it
"already supports this safely."

**Decision.** Phase 1E's `IndustryTemplate` model, with `slug` as the
family identity and `version` as a per-family incrementing integer
(`UniqueConstraint(slug, version)`), already satisfies every requirement
above without a new model: the "family" is simply
`IndustryTemplate.objects.filter(slug=slug)`, "current recommended
version for new installs" is computed on demand (not stored) as
`IndustryTemplate.objects.filter(slug=slug, readiness=PRODUCTION_READY).order_by("-version").first()`
(`latest_production_version(slug)` in `template_validation_service`), and
"a newer version is available for an installed Store" is
`installation.industry_template.version < latest_production_version(installation.industry_template.slug).version`.
No new model was introduced; `IndustryTemplate` gains two new fields
instead: `readiness` (the lifecycle state — §ADR-26/28) and
`content_fingerprint` (a cached, deterministic content hash — see below).

**Consequences.** Zero migration risk to the 10 existing Phase 1E
templates or their installations beyond two new nullable/defaulted
columns — no data restructuring, no re-keying of any child row's FK.
"Current recommended version" being *computed*, not stored, means there
is no mutable-flag invariant to maintain (no risk of two rows both
claiming `is_recommended=True` for one family) — a `production_ready`
template simply is or is not the highest-versioned one in its family
that has reached that state, evaluated fresh on every read. A template's
`content_fingerprint` (`apps.catalog.services.template_validation_service.compute_template_fingerprint`)
is a SHA-256 over a canonical JSON structure built entirely from stable
identifiers (`slug`/`code`/labels/ordering/flags) — explicitly excluding
every database primary key, `created_at`, and `updated_at` — so two
`IndustryTemplate` rows seeded with byte-identical content always fingerprint
identically regardless of DB insert order, and re-running the seed
command against unchanged data never appears to "drift." The fingerprint
is computed once (at validation time, cached on the `IndustryTemplate`
row) rather than on every read, since template child rows are immutable
after creation (ADR-25) — there is no code path that could make a cached
fingerprint stale without also creating a *new* `IndustryTemplate` row
(which computes its own fresh fingerprint).

**Alternatives considered.** A dedicated `IndustryTemplateVersion` model
wrapping a stable `IndustryTemplate` family row — rejected for this phase
as the disruptive redesign the prompt explicitly permits avoiding: it
would require re-pointing every one of `IndustryTemplateCategory`/
`IndustryTemplateAttribute`/etc.'s `industry_template` FK, plus a backfill
migration, for a capability (family-vs-version distinction) the existing
`(slug, version)` compound key already provides without it. If a future
phase needs first-class "family" metadata that varies independently of
any specific version (e.g., a family-level icon that should not require
a new version row to change), that would be the concrete trigger to
revisit this decision — not before.

## ADR-28: Store Customization Detection Compares Live Fields Against the Immutable Source Template — No Snapshot Table

**Context.** The safe-update workflow (ADR-29) must never silently
overwrite a value a merchant deliberately changed after installing a
template. Detecting "has this Store-owned record been customized"
normally requires either an explicit dirty flag maintained on every write
path, or a stored snapshot of the record's state at install time to diff
against.

**Decision.** Because `IndustryTemplate*` rows are immutable once created
(ADR-25/27), the *source template row itself* already **is** the
install-time snapshot — there is no need to copy it a second time into a
separate snapshot table. `apps.catalog.services.template_customization_service`
detects customization by directly comparing each Store-owned record's
current field values against its `source_template_*` FK target's current
field values: `is_category_customized(category)` compares `name`/`icon`/
parent-identity against `category.source_template_category`;
`is_attribute_customized(attribute)` compares `label`/`data_type`/
`display_type`/`unit`/`is_variant_axis` against
`attribute.source_template_attribute`; `is_schema_entry_customized(entry)`
compares `group`/`is_required`/the three override flags/`help_text`/
`placeholder` against `entry.source_template_mapping`. A record with no
`source_template_*` FK (merchant-created from scratch, or installed
before Phase 1F added a given traceability FK) is always treated as
customized/merchant-owned — never eligible for silent update overwrite,
the conservative default the prompt requires. `AttributeValue` gained a
new `source_template_value` FK (mirroring `Category`/`Attribute`'s
existing pattern) specifically so *value-level* customization (a
merchant renaming or deleting a template-provided choice value) is
detectable the same way; Phase 1E installations predate this FK and are
`NULL` on it, so their existing `AttributeValue` rows are conservatively
treated as customized by the same "no source FK means owned" rule above.

**Consequences.** No new snapshot storage, no risk of a snapshot silently
drifting out of sync with what was "actually installed," and detection
logic automatically improves for future installations as more
`source_template_*` FKs are added, with old installations safely
defaulting to "assume customized" rather than "assume safe to overwrite."
The cost: a customization check requires a live read of the source
template row (cheap — `IndustryTemplate*` rows are small, and the update
planning service prefetches them in bulk, not per-record).

**Alternatives considered.** A dirty-bit (`is_customized` boolean) set by
every mutating service call that touches an installed record — rejected:
it requires disciplined maintenance across every future write path
touching `Category`/`Attribute`/`CategoryAttributeSchema` (including
Django admin edits, which bypass service functions entirely), and a
missed call silently mis-flags a customized record as pristine — exactly
the "silently overwrite merchant customization" failure the prompt
prohibits. A full point-in-time snapshot copy at install time — rejected
as redundant, since the immutable source template already serves that
role at zero extra storage cost.

## ADR-29: Template Updates Default to Additive-Only Auto-Apply; Everything Else Requires Explicit Merchant Review, Nothing Is Ever Auto-Applied Destructively

**Context.** The prompt's §19 draws a three-way line: changes safe to
apply automatically, changes requiring merchant review, and changes that
must never be applied automatically. Phase 1F must implement a real,
transactional update-application path that respects this line without
degenerating into "sync everything" (which would silently clobber
customization) or "do nothing" (which would make the whole feature a
placeholder).

**Decision.** `apps.catalog.services.template_update_service.plan_template_update(installation, target_template)`
classifies every diff entry from `compare_template_versions` (ADR-27's
comparison service) into exactly one bucket:

* **`safe_additive`** — a new template Category/Attribute/Value/mapping/
  recommendation with no Store-owned counterpart yet. These are
  auto-selected by default in the plan and applied by
  `apply_template_update` **only if the merchant does not deselect them**
  — the merchant still confirms the batch, but no individual review is
  required per item, matching the prompt's "Add a new optional Attribute"
  example category exactly.
* **`review_required`** — a changed field on an *existing, uncustomized*
  Store-owned record (matched via `source_template_*`) — e.g. the
  template's newer version renamed a Category the Store never touched.
  These are listed but **not pre-selected**; the merchant must explicitly
  check each one.
* **`blocked`** — anything touching a Store-owned record this phase's
  `template_customization_service` (ADR-28) determines is customized, or
  any requested change this phase does not support applying at all
  (label conflicts with an existing unrelated Attribute of a different
  `data_type`, for instance). Blocked entries are never selectable and
  are always shown with a reason string.

`apply_template_update` **only ever applies `safe_additive` entries in
this phase** — `review_required` entries can be selected in the plan UI
for future extension, but the Phase 1F implementation of the apply
service raises `TemplateUpdateError` if a caller attempts to select one,
rather than silently downgrading it to "creates" behavior or silently
ignoring the selection. This is a deliberate, named scope line (see the
Phase 1F report's Known Limitations): the additive path is the one the
prompt's own worked example (§19 "Automatically safe") fully specifies
end-to-end; applying a *review-required* rename/retype safely (which
existing Product data might depend on) is a strictly harder problem
(e.g., changing an Attribute's `data_type` after Products already hold
typed `ProductAttributeValue` rows against it) that deserves its own
dedicated design pass rather than a rushed implementation inside this
phase.

**Consequences.** A merchant can safely accept "add everything new" in
one confirmed action with zero risk of losing customization (verified by
dedicated tests asserting a customized Category's `name` is byte-identical
before and after an update that adds new sibling Categories). Every
application is wrapped in one `@transaction.atomic` block, keyed by an
idempotency key (`f"{installation.pk}:{target_template.pk}"` plus a
per-call selection hash) recorded on the new `StoreTemplateUpdate` history
row *before* any Store-owned row is touched, so a duplicate/retried
request against an already-`completed` update of the same
(installation, target_template) pair is rejected outright rather than
double-applying. `installation.installed_version` is updated to the
target template's version only on a fully successful apply.

**Alternatives considered.** Applying `review_required` changes too, gated
only by a merchant checkbox per item — rejected for this phase because
several of those change types (data-type change, required-Category
removal) have no safe, generally-correct "apply" implementation yet
without also deciding what happens to existing `Product`/
`ProductAttributeValue` rows that depend on the old shape; shipping a
checkbox that silently does the wrong thing on `apply` would be worse
than not offering the option. A full three-way merge/diff resolution UI
(à la source control) — rejected as disproportionate scope for this
phase; the additive-first slice already delivers the update workflow's
primary value (new template content becomes available without
re-installation) safely.

---

## ADR-30: Staff Management Grants Immediate Active Access; Token-Based Invitation Acceptance Is Out of Scope

**Context.** `StoreMembership` (ADR-2/ADR-4) has carried `invited_at`/
`accepted_at`/`revoked_at` and an `INVITED` status since Phase 1B, but its
own docstring explicitly deferred "invitation delivery, tokenized
acceptance, owner transfer, ... and dashboard integration" to a later PR.
No route, view, or template referencing membership management existed
anywhere in `apps.dashboard` before this phase — `STAFF_MANAGE` was a
permission key with no feature behind it. The Admin Panel Completion
Program requires this gap closed with real persistence, real permission
enforcement, and real tests — not a mock or a placeholder screen.

**Decision.** `apps.stores.services.membership_service.add_staff_member`
creates (or reactivates) a `StoreMembership` row with
`status=ACTIVE` and `accepted_at=now()` **immediately**, with no
intervening `INVITED` state the target user must separately accept. The
`Owner` (the only role granted `STAFF_MANAGE`, since it is in
`_OWNER_ONLY`) is adding a specific person they already know — an
employee — not sending cold outreach to a stranger who must opt in. A
`User` row is created (with an unusable password) if the phone number has
no existing account, and `is_staff=True` is set so the account can pass
`staff_required`'s Django-level staff gate the next time that person logs
in (via the existing OTP/password flow in `apps.customers.services.auth_service`
— unchanged by this phase).

This sidesteps a real chicken-and-egg problem: `staff_required` denies
access to *every* admin-portal route, including a hypothetical "accept your
invitation" page, to anyone without an already-`ACTIVE` membership in that
exact Store. A safe, reachable, tokenized acceptance flow (e.g., a signed
link mailed/texted to the invitee, verified without requiring a prior
session) is a legitimate, separate feature — it needs its own delivery
channel decision (SMS vs. email), token model, and expiry policy — and is
documented as a limitation in the Admin Panel Completion Report rather than
built as a rushed, half-covered addition here.

The `INVITED` status and its fields remain fully supported by the model and
`membership_service` (`list_memberships` still sorts and displays `INVITED`
rows distinctly, `revoke_membership`/`reactivate_membership` operate on
them too) for any row created by a future acceptance-flow feature or
directly via Django admin — this phase does not remove or weaken that
state, it simply never creates one itself.

**Consequences.** A merchant can add a working team member in one step
with no delivery-channel dependency (no SMS/email plumbing needed for the
core feature to be real and usable today). The tradeoff is explicit and
documented: there is currently no "pending invite the recipient must
approve" moment — whoever holds the phone number gains access as soon as
the Owner submits the form, so Owners must only enter numbers they intend
to grant access to right away.

**Alternatives considered.** Building a full tokenized email/SMS
acceptance flow in this same phase — rejected as disproportionate scope
that would also require solving the reachability problem above (a new,
unauthenticated-but-token-gated route class that does not yet exist
anywhere in `apps.dashboard`) and a new SMS event/template plus its own
test surface, none of which the rest of this phase's checkpoints depend on.
Making `is_staff` alone sufficient (dropping the `StoreMembership` check)
— rejected outright: this is exactly the tenant-isolation vulnerability
`apps.stores.authorization`'s own module docstring was written to close.

---

## ADR-31: Inventory Is a Ledger (`StockMovement`), Not a Bare Counter — and Order-Level Stock Mutation Targets the Correct Field

**Context.** Before this phase, `Product.stock`/`ProductVariant.stock` were
plain `PositiveIntegerField` counters mutated directly (via `F()` updates)
with no audit trail, and auditing revealed two real correctness bugs in
`apps.orders.services.order_service`:

1. `create_order_from_cart` decremented `Product.stock` **unconditionally**
   for every order line, even when the line was for a specific
   `ProductVariant`. For a variable product, `ProductVariant.stock` (the
   Phase 1D variant engine's own counter) was never touched by checkout —
   only the parent `Product.stock` was, regardless of which variant was
   actually ordered. `_lock_and_revalidate_items` had the matching bug on
   the validation side: it checked `item.quantity > product.stock`, so an
   order for a variant with `stock=0` could still pass validation as long
   as the *parent* `Product.stock` happened to be positive.
2. `change_order_status` had no restock path at all — canceling a
   `PENDING`/`PROCESSING`/`SHIPPED` order permanently "lost" the stock that
   was decremented when the order was placed; it was never returned.

Both bugs are silent under the platform's own test suite prior to this
phase because every existing checkout test used simple (non-variant)
products, so `product.stock` was always the correct target by coincidence,
and no test asserted post-cancellation stock levels.

**Decision.** `apps.catalog.models.StockMovement` is the single, append-only
ledger every stock mutation must pass through — enforced by convention (no
code outside `apps.catalog.services.inventory_service` performs a raw `F()`
stock update) rather than by a database trigger, matching this codebase's
existing pattern of enforcing invariants in one service layer
(`template_update_service`, `membership_service`) rather than in triggers.
Each row records `store`, `product`, `variant` (nullable — null means the
movement targets the product's own counter, not a specific variant's),
`reason` (`order_placed` / `order_canceled` / `manual_adjustment`), signed
`delta`, and `stock_before`/`stock_after` — enough to reconstruct the exact
state of any counter at any point in time without recomputing it from
scratch.

`apps.catalog.services.inventory_service.decrement_stock_for_order_item`
is now the only place `create_order_from_cart` decrements stock: it targets
`variant.stock` when the order line has a variant, `product.stock`
otherwise — fixing bug (1) at its root, not by adding a special case.
`_lock_and_revalidate_items`'s pre-checkout stock check was fixed the same
way (`available_stock = variant.stock if variant is not None else
product.stock`). `restock_order` is called from `change_order_status`
whenever an order transitions to `CANCELED`, reversing every
`ORDER_PLACED` movement for that order's items — fixing bug (2). Because
`CANCELED` is one of `order_service.FINAL_STATUSES` with no outgoing
transitions (ADR predates this document but is enforced by
`ALLOWED_TRANSITIONS`), `restock_order` runs at most once per order.

**Consequences.** Every unit of stock ever decremented by a real order is
now provably returned on cancellation, and a merchant (or platform
operator, via the read-only `StockMovementAdmin`) can answer "why does this
product show 7 in stock" by reading the ledger instead of trusting an
opaque counter. The dashboard's new Inventory Ledger page
(`apps.dashboard.views.inventory_list`) surfaces this history directly to
the merchant, filterable by product/SKU and reason. `adjust_stock_manually`
is provided for a future manual-recount UI but is not wired to a dashboard
view in this phase — this phase's scope was the order-lifecycle
correctness fix and its supporting audit trail, not a full manual
stock-adjustment workflow (documented as a limitation in the Admin Panel
Completion Report).

**Alternatives considered.** Fixing only the `Product.stock`-vs-
`ProductVariant.stock` targeting bug without introducing a ledger —
rejected because the prompt's own explicit prohibition ("do not mutate
inventory without a ledger") and the restock-on-cancel bug are the same
class of problem (stock mutated with no auditable trail of *why*); fixing
one without the other would leave the other bug in place and undiscovered
by tests. A database trigger-based ledger (writing `StockMovement` rows
automatically on any `UPDATE` to `stock`) — rejected as inconsistent with
every other invariant in this codebase, all of which are enforced in
Python service layers precisely so the reasoning is visible in one place
and covered by ordinary Django tests, not hidden in database-specific
trigger SQL that would also have to be reproduced for SQLite (tests) and
PostgreSQL (production) separately.

---

## ADR-32: Coupon Is Store-Owned — Code Uniqueness Is Per-Store, Not Global

**Context.** The Admin Panel Completion Report (checkpoint 1) named
`Coupon` having no `store` FK at all as a real, live cross-tenant leak:
`Coupon.code` was globally unique, and both `checkout_service.apply_coupon`
and `get_applied_coupon` looked up `Coupon.objects.filter(code=code)` with
no Store filter whatsoever. In practice this meant any Store's checkout
could apply any other Store's coupon code, and two Stores could never both
use a common, obvious code like `WELCOME10` — the second one to try would
simply fail with "code already exists," attributed to a stranger's Store.

**Decision.** `Coupon` gets a required `store` FK (`on_delete=CASCADE`,
matching every other Store-owned aggregate in this codebase) and the
uniqueness constraint moves from a bare `unique=True` on `code` to
`UniqueConstraint(fields=["store", "code"])`. The migration follows the
same three-step safe pattern already established for `Product`/`Category`/
`Vendor` Store-scoping (`apps/catalog/migrations/0006-0008`): (1) add the
FK nullable and drop the old global-unique constraint, (2) backfill every
pre-existing `Coupon` row to the Akhlaghi Store (the platform's only
pre-existing Store, the sole deterministic choice — mirrors
`apps/catalog/migrations/0007_backfill_catalog_store.py`'s own reasoning),
(3) enforce `NOT NULL` and add the per-Store unique constraint. Every
lookup site (`checkout_service.apply_coupon`, `get_applied_coupon`,
`order_service.create_order_from_cart`'s new defensive check,
`membership`-style dashboard views) now filters or validates by `store`
explicitly — checkout resolves the Store once at the HTTP boundary
(`resolve_store_for_service`) and passes it down, matching this codebase's
standing rule that deeper service functions never re-derive a Store
themselves.

**Consequences.** Two Stores can now both run a `WELCOME10` campaign
independently; a coupon code leaking into another Store's checkout is now
structurally impossible (enforced by the query filter, verified by
`CouponTenantIsolationTests` in `apps/orders/tests/test_checkout_service.py`
using two Stores with the *same* code string). A previously undiscovered
class of bug (checking `product.stock` regardless of variant is the direct
analogue in ADR-31) is closed the same way: fix the query, not just the
symptom.

**Alternatives considered.** Scoping only at the checkout-lookup layer
(add a `store` filter to the two call sites) without touching the model —
rejected because the underlying data model would still allow a genuine
data-integrity violation (two Stores literally unable to pick the same
code) and would leave the Django Admin / any future direct-model access
path unscoped. Making `Coupon` a subclass of a generic "Promotion" model
with Product/Category scope fields — out of scope for this checkpoint;
this codebase's `Coupon` has never had per-product/per-category scoping
fields at all (verified by reading the full model before this change), so
introducing them now would be new functionality, not a tenant-isolation
fix — tracked as a follow-up in the Admin Panel Completion Report, not
invented here.

---

## ADR-33: Refund Financial Integrity — Amounts Computed From the Immutable Order Snapshot; Only `MANUAL` Execution Is Real

**Context.** Checkpoint 2 requires refund planning and execution that
cannot over-refund, double-refund, or refund against the wrong Store/
currency — and this platform has no payment gateway integration capable of
actually pushing money back to a customer (`PaymentGatewayConfig`/
`PaymentAttempt` model the *forward* payment flow only). Silently
pretending a `GATEWAY` refund succeeded would be dishonest and would
corrupt the ledger with a claim this codebase cannot back up.

**Decision.** `apps.orders.services.refund_service` computes every amount
from `Order.grand_total`/`shipping_cost` and `OrderItem.unit_price` — the
snapshot already frozen at checkout time (`create_order_from_cart`) —
never from `Product.price`, which can change after the order was placed.
`refundable_amount(order)` = `paid_amount(order)` (the full `grand_total`
if `payment_status` is `PAID`/`REFUNDED`, else zero — this codebase does
not model partial payment at the Order level) minus the sum of every
non-final-failed/cancelled `Refund`'s amount already committed against
this order. `plan_order_refund` is a pure, side-effect-free computation
(no DB writes) used both by the dashboard form (to show the merchant the
real maximum before they submit) and by `execute_order_refund` itself (so
the two can never disagree). `execute_order_refund` re-validates
everything server-side from POST data containing only *quantities* and a
*shipping toggle* — never a client-supplied amount — before creating the
`Refund`/`RefundItem` rows inside one atomic transaction.

Only `refund_method=Refund.Method.MANUAL` is actually executable:
`execute_order_refund` immediately marks it `SUCCEEDED` with
`completed_at=now()`, which is an honest statement ("the merchant just
told this system they paid the customer back outside of it"), never a
claim that this platform moved money. Requesting
`refund_method=Refund.Method.GATEWAY` raises `RefundError` immediately,
with a message that says why, surfaced directly in the dashboard UI —
per this checkpoint's own explicit instruction not to claim money was
transferred when it wasn't. `record_refund_result` exists as the future
integration point for a real gateway webhook, and refuses to modify a
`Refund` that has already reached one of `FINAL_STATUSES` (`SUCCEEDED`/
`FAILED`/`CANCELLED`) — a completed refund's amount is a historical fact,
correctable only by a new `Refund` row, never an edit.

**Consequences.** Over-refund, duplicate-refund (via `idempotency_key`,
mirroring `Order.idempotency_key`'s own pattern), cross-Store refund, and
refunding a quantity beyond what was purchased (accounting for *all*
already-refunded quantity across every non-cancelled refund on that line,
not just the most recent one) are all provably impossible — verified by
adversarial tests in `test_refund_service.py`. The dashboard refund form
never has an amount input field at all; it only collects quantities and a
shipping toggle, so there is nothing for a manipulated request to lie
about.

**Alternatives considered.** Modeling a fake "gateway success" for
`GATEWAY` refunds so the UI always looks fully automated — rejected
outright as dishonest and explicitly prohibited by this checkpoint's own
instructions. Tracking partial payment at the `Order` level to make
`paid_amount` more granular — out of scope; this codebase's `Order` has
always treated payment as binary (`PaymentStatus.PENDING`/`PAID`/`FAILED`/
`REFUNDED`), and changing that is a separate, larger payment-domain
decision this checkpoint does not make.

---

## ADR-34: Return Requests Get Their Own Explicit State Machine, Separate From `Order.status`

**Context.** `Order.status` (ADR predates this document; enforced by
`order_service.ALLOWED_TRANSITIONS`) is fulfillment-focused — pending
through delivered/canceled — and has no room for "a customer wants to send
part of this delivered order back." Overloading it with return-related
values would conflict with `FINAL_STATUSES` semantics (a `DELIVERED` order
is done, but a return against it is only just starting) and would make
`ALLOWED_TRANSITIONS` express two unrelated concerns in one field.

**Decision.** `ReturnRequest` is a separate model with its own
`Status` (`requested → under_review → approved/rejected → in_transit →
received → inspected → completed/cancelled`) and its own
`ALLOWED_TRANSITIONS`/`FINAL_STATUSES` pair, built with exactly the same
shape as `order_service`'s (a dict of legal next-states, a frozenset of
terminal ones) — a deliberate architectural echo, not a coincidence, so
anyone who already understands the Order state machine immediately
recognizes this one. Every transition goes through
`apps.orders.services.return_service`, never a raw `.status = X; .save()`
in a view: `review_return_request`, `approve_return_request` (validates
per-item approved quantity never exceeds requested), `reject_return_request`
(requires a reason), `mark_return_received`, `inspect_return_items`
(records condition/restockability/resolution per item), and
`complete_return` (triggers inventory restock and, where the merchant's
per-item resolution was "refund," an actual `Refund` via
`refund_service.execute_order_refund`). A `ReturnRequest.order` can have
*multiple* `ReturnRequest`s over its lifetime (a customer might return two
different items on two different days) — quantity reservation is tracked
per-`OrderItem` across all non-rejected/non-cancelled returns
(`_reserved_return_quantity`), not per-Order, so this is provably safe
against double-counting.

**Consequences.** `Order.status` needed no changes at all — it remains
purely about fulfillment, exactly as before. A return can be created,
approved, rejected, received, inspected, and completed with a fully
auditable trail (`approved_at`/`received_at`/`completed_at`/`rejected_at`
timestamps plus an `AuditLogEntry` at every transition) independent of
whatever the Order's own fulfillment status is.

**Alternatives considered.** Adding `partially_returned`/`returned` values
directly to `Order.Status` — rejected because a `DELIVERED` order (a
`FINAL_STATUSES` member with no outgoing transition in
`order_service.ALLOWED_TRANSITIONS`) would need to somehow also become
`returned` without violating that finality, which would require weakening
an existing, tested invariant just to shoehorn an unrelated concern into
the same field. See ADR-35 for the matching decision on financial state.

---

## ADR-35: Order Financial/Return State Is Tracked in Dedicated Fields and Related Rows, Not Folded Into `Order.status`

**Context.** Checkpoint 2 explicitly asks whether an Order should be able
to become `partially_refunded`/`refunded`/`partially_returned`/`returned`,
or whether that state should live separately from the existing
fulfillment-focused status. This is the direct financial-state
counterpart to ADR-34's fulfillment/return-workflow split.

**Decision.** Financial and return state stay **out of** `Order.status`
entirely. `Order.payment_status` gains its natural final value
(`REFUNDED`) exactly once already-supported by the model — no new status
values were added anywhere on `Order` itself. The complete financial
picture is always *derived*, on demand, from real rows: `paid_amount`,
`refunded_total`, `refundable_amount` (all in `refund_service`, ADR-33)
compute directly from `Order.grand_total` plus the live set of
non-cancelled `Refund` rows; return state is the live set of
`ReturnRequest` rows linked to the order (`order.return_requests`). The
dashboard's Order Financial Summary (`_order_detail_context`) simply
surfaces these computed values and the related querysets — there is no
stored, cacheable "is this order returned" boolean anywhere that could
drift out of sync with the underlying `Refund`/`ReturnRequest` rows.

**Consequences.** There is exactly one source of truth for "how much of
this order has been refunded" (the `Refund` rows themselves), so it can
never disagree with itself. Adding a future reporting need (e.g., "list
all partially-refunded orders") is a query over `Refund`, not a migration
to add and backfill a new `Order` field. The tradeoff is that "is this
order returned" is a computed property, not an indexed column — acceptable
at this codebase's scale (matching the same tradeoff already accepted for
`refundable_amount` itself).

**Alternatives considered.** Adding `financial_status`/`return_status`
fields directly to `Order` — rejected for the same reason ADR-34 rejected
folding return workflow into `Order.status`: it would require keeping a
denormalized field in sync with the real `Refund`/`ReturnRequest` rows on
every write path, a second source of truth that can drift, for a
computation that is already cheap and correct today.

---

## ADR-36: Audit Log Is Store-Scoped, Redacts Known-Sensitive Keys at Write Time, and Deliberately Omits IP/User-Agent

**Context.** Checkpoint 2 requires a reusable audit trail for sensitive
merchant-admin actions (staff changes, inventory adjustments, order
cancellation, refund/return lifecycle, coupon changes) with explicit
before/after summaries, while never storing passwords, gateway secrets,
card data, or auth tokens — and the request notes IP/User-Agent logging
is conditional on "existing privacy policy" support.

**Decision.** `apps.core.models.AuditLogEntry` is a new, Store-scoped,
append-only model (no `updated_at` at all — a correction is a new row,
never an edit of history) with `store`, `actor` (nullable — some events
are system-initiated), `action_code`, a loose `object_type`/`object_id`
(plain strings, not Django `ContentType`, so this model never needs to
import or depend on whichever app owns the object it's describing —
important since it is written from `apps.stores`, `apps.catalog`, and
`apps.orders` services alike), `object_label`, `before_summary`/
`after_summary` (JSON-serialized, redacted), `metadata` (`JSONField`,
redacted), `request_id` (for idempotent-on-retry writes), and `result`.
The single write path, `apps.core.services.audit_service.record_audit_event`,
redacts any key matching a hardcoded forbidden-key list (`password`,
`token`, `secret`, `api_key`, `card_number`, `cvv`, and their common
variants) inside `metadata`/`before`/`after` **before** the row is ever
written — a defense-in-depth measure, not a substitute for callers simply
not passing secrets in the first place. Passing a `request_id` makes the
call idempotent: a retried operation with the same id returns the
already-existing entry instead of writing a duplicate.

`ip_address`/`user_agent` fields were **deliberately not added**. This
codebase has never adopted a privacy policy governing retention of end-user
network metadata (verified by inspecting `apps.customers`, `apps.orders`,
and every existing model for any precedent — there is none), so adding
IP/User-Agent collection now, with no policy decision behind it, would be
unpoliced personal-data collection introduced as a side effect of an
unrelated feature. The checkpoint's own instruction ("only if existing
privacy policy supports it") is read literally: no policy exists, so
nothing is collected.

The Merchant Admin Audit Log UI (`apps.dashboard.views.audit_log_list`)
is gated by the new `AUDIT_LOG_VIEW` permission, granted to `Owner`,
`Administrator` (via `ALL_PERMISSIONS - _OWNER_ONLY`), and `Analyst`
(read-only reporting, per this checkpoint's own suggested role policy) —
`Catalog Manager`/`Order Manager`/`Content Editor` do not get it, matching
the centralized `apps.stores.authorization` registry every other
permission in this codebase goes through.

**Consequences.** Every sensitive action integrated this checkpoint
(staff add/role-change/revoke/reactivate/ownership-transfer, manual
inventory adjustment, order cancellation, refund completion, every return
transition, coupon create/update/toggle/archive) now produces a
searchable, Store-scoped, tamper-evident trail with no secret material at
rest. Redaction is unit-tested directly (`test_audit_service.py`) rather
than trusted to caller discipline alone.

**Alternatives considered.** Using Django's built-in `ContentType`/
`GenericForeignKey` for `object_type`/`object_id` — rejected as
unnecessary coupling; this log is deliberately a write-mostly, read-by-
humans record, not a queryable-by-relation index, so a plain string pair
is simpler and avoids a hard dependency from `apps.core` back onto every
app it audits. Logging IP/User-Agent "since it might be useful later" —
rejected per the reasoning above; it is easier to add a field later behind
an actual privacy-policy decision than to have collected it without one
from day one.

---

## ADR-37: `Warehouse` Provisioning Is an Explicit, Idempotent Service Call — Never a Django Signal

**Context.** Every Store needs exactly one default `Warehouse` to exist
before any inventory/order operation can attribute stock to a location.
This is the same shape of problem `ShopSettings.provision_for`/
`FooterSettings.provision_for` already solved for their respective
Store-scoped singletons, both predating this checkpoint.

**Decision.** `provision_default_warehouse(store)` follows that exact,
established precedent: an explicit, idempotent, plain Python function —
called from the data migration (`0018_provision_default_warehouses`, for
Stores that existed before this checkpoint), from the
`provision_default_warehouses` management command (for ops/future Stores),
and available for any future Store-creation code path to call directly —
never a `post_save` signal on `Store`. This codebase has no signal-based
provisioning anywhere (verified across `apps.stores`, `apps.core`,
`apps.content` before adding this), so introducing one exception here
for warehouses would be a new, inconsistent pattern for the one place
that happens to need it most recently.

**Consequences.** Warehouse provisioning is easy to reason about, easy to
call from a script or a one-off shell, and impossible to trigger
accidentally as an invisible side effect of an unrelated `Store.save()`.
The cost — matching the cost already accepted for `ShopSettings`/
`FooterSettings` — is that any *new* Store-creation code path that
forgets to call `provision_default_warehouse` will simply not have a
warehouse until something calls it; `provision_default_warehouses` (the
management command) exists as an idempotent, safe-to-rerun backstop for
exactly that scenario.

**Alternatives considered.** A `post_save` signal on `Store` — rejected
solely for consistency with the two directly analogous precedents this
codebase already chose not to signal-provision; introducing signals for
warehouses alone would make this the only Store-scoped singleton
provisioned differently from the other two, for no functional benefit.

---

## ADR-38: `Product`/`ProductVariant.stock` Remains the Single Authoritative Sellable-Stock Field; `WarehouseInventory` Is a Synced Per-Warehouse Breakdown, Not a New Source of Truth

**Context.** Checkpoint 3 asks for a Warehouse/stock-location domain with
per-warehouse balances. The "obvious" design flips authority: delete the
aggregate `stock` field and make `WarehouseInventory` (summed across a
product's warehouses) the only truth. That is the textbook multi-warehouse
model — but this codebase has ~2,400 existing passing tests that create
`Product`/`ProductVariant` rows and assert directly against `.stock`
before, during, and after checkout, returns, and refunds (`decrement_stock_for_order_item`,
`restock_order`, `restock_return_item`, `restock_refund_item`,
`adjust_stock_manually` — all of `apps.catalog.services.inventory_service`
predate this checkpoint and are exercised by that entire existing suite).

**Decision.** `Product.stock`/`ProductVariant.stock` **stay** the single
authoritative field for "how much of this can currently be sold" — exactly
as before this checkpoint. `Warehouse` and `WarehouseInventory` are new,
additive models: every warehouse-aware balance changes (`_sync_warehouse_balance`
in `inventory_service`) alongside the aggregate field, in the same
transaction, whenever `decrement_stock_for_order_item`/`restock_order`/
`restock_return_item`/`restock_refund_item`/`adjust_stock_manually` runs —
so `WarehouseInventory.on_hand` summed across a product's warehouses is
kept equal to `Product.stock`/`ProductVariant.stock` by construction, not
by a periodic reconciliation job. `verify_inventory_consistency
--strict` (a new, read-only management command) exists specifically to
catch drift if that invariant is ever violated by a future bug, but it is
a safety net, not the mechanism that keeps the two in sync.

A direct consequence of this decision: every order-driven inventory-service
call that touches `_sync_warehouse_balance` — `decrement_stock_for_order_item`
(checkout), `restock_order` (cancellation), `restock_return_item`,
`restock_refund_item`, and `adjust_stock_manually` — always resolves and
credits/debits the Store's *default* warehouse, unconditionally, via
`_resolve_default_warehouse`. None of them ask "which warehouse actually
fulfilled this order" because nothing in this codebase's `Order`/`OrderItem`
model records that yet — fulfillment-warehouse selection is out of scope
for this checkpoint. This is a deliberate, narrow policy for return/refund
restocking specifically: a returned or refunded item always goes back into
the Store's default warehouse's balance, regardless of which (if any)
non-default warehouse a merchant may have manually shipped it from via a
`WarehouseTransfer`. The only way stock moves into or out of a *non*-default
warehouse's balance is an explicit `WarehouseTransfer` (ADR-40) — order
fulfillment itself is single-warehouse-implicit today.

**Consequences.** Every existing test that asserts against `Product.stock`/
`ProductVariant.stock` continues to pass unmodified — this checkpoint adds
a parallel, synced breakdown rather than migrating the meaning of an
already-load-bearing field. The cost is that `WarehouseInventory` is
"derived-but-stored" rather than the single source of truth a textbook
warehouse model would prefer — a store that somehow bypassed
`inventory_service` and wrote to `Product.stock` directly would silently
desync the two (mitigated by `verify_inventory_consistency` and by the
fact that nothing in this codebase, before or after this checkpoint,
writes to `.stock` outside that service module).

**Alternatives considered.** Making `WarehouseInventory` the sole
authority and deriving `Product.stock` as a computed property — rejected:
it would require rewriting every existing inventory-service function and
every one of the ~2,400 tests that construct a `Product`/`ProductVariant`
with a `stock=` kwarg and assert against it after a save, for a benefit
(single source of truth) this codebase does not yet need at its current
scale — no multi-warehouse store exists yet, `provision_default_warehouse`
provisions exactly one warehouse per Store today. Revisiting this decision
is explicitly a candidate for a *future* checkpoint once a store actually
operates multiple warehouses with independent, warehouse-specific sellable
quantities (e.g. "in stock at warehouse A, sold out at warehouse B").

---

## ADR-39: Inventory Reservation Reduces "Available" (Computed), Not "On-Hand" (Stored) — and Is Created and Consumed Synchronously Within `create_order_from_cart`'s Own Transaction, Never Held Open Across Requests

**Context.** Checkpoint 3 asks for atomic inventory reservation with
idempotent retries, reservation release, and reservation expiration —
language that, in most e-commerce systems, implies a reservation created
at "add to cart" or "begin checkout" time and held open across a
multi-step, multi-request checkout flow (address entry, payment redirect,
gateway callback) until the order is confirmed or the reservation expires.
This codebase's existing checkout (`checkout_service.finalize_order` →
`order_service.create_order_from_cart`), predating this checkpoint, is a
single synchronous call: lock rows, validate, create the `Order` and all
`OrderItem`s, decrement stock, done — all inside one `transaction.atomic()`
block, already covered by a large existing test suite
(`test_checkout_correctness.py`, `test_checkout_integrity.py`,
`test_checkout_service.py`, `test_checkout_views.py`) that asserts on this
exact synchronous behavior, including its idempotency-key retry handling.

**Decision.** `InventoryReservation` is a real, first-class model with its
own lifecycle (`ACTIVE`/`CONSUMED`/`RELEASED`/`EXPIRED`/`CANCELLED`), and
`reserve_inventory` only ever reduces *available* quantity — computed as
`on_hand − sum(active reservations)` — never `on_hand` itself. But the
checkpoint's own synchronous, single-request checkout flow is preserved
unchanged: `create_order_from_cart`'s per-item loop calls
`reserve_inventory` and then, in the same atomic transaction, immediately
`consume_inventory_reservation` (which is what actually decrements
`on_hand`/`Product.stock`/`ProductVariant.stock` via the existing
`decrement_stock_for_order_item`, writing the usual `StockMovement`).
Reservation idempotency keys are derived per-cart-item
(`f"{idempotency_key}:{item.pk}"`) from the existing
`Order.idempotency_key`, so a retried checkout submission (already
tested — see `test_checkout_integrity.py`) hits the reservation's own
idempotency short-circuit and returns the already-created reservation
instead of double-reserving or double-consuming.

The `ttl_minutes`/`expires_at`/`expire_inventory_reservations` machinery
this ADR describes is real and independently tested
(`test_reservation_service.py`), and is available today for any future
caller that *does* want a reservation held open across requests (e.g. a
future "hold my cart for 20 minutes" feature, or a future asynchronous/
redirect-based payment gateway flow) — `reserve_inventory` defaults to a
20-minute TTL when called without `ttl_minutes=None`, and
`create_order_from_cart` is the one caller that explicitly opts out of
that default (`ttl_minutes=None`) because it consumes the reservation
before the transaction that created it ever commits.

**Consequences.** Existing checkout behavior — timing, error messages,
idempotency-retry semantics, the entire existing checkout test suite — is
unchanged byte-for-byte; reservation is an internal accounting step
inserted transparently into an already-correct flow, not a rewrite of
that flow's request/response shape. The cost is that this checkpoint does
not deliver a "hold stock while the customer is on the payment gateway's
site" feature — today's payment flow does not have a redirect-and-return
window that would need one (verified against `apps.orders.services.checkout_service`
and the `PaymentGateway`/payment views: gateway selection happens before
`create_order_from_cart`, not after). If a future gateway integration
adds a genuine redirect-based flow, the reservation service already has
the primitives (`ttl_minutes`, `expire_inventory_reservations`) that flow
would need — no new model would be required, only a new caller.

**Alternatives considered.** Reserving at "add to cart" time and holding
the reservation open until checkout completes or the cart is abandoned —
rejected for this checkpoint as a materially larger, riskier change (every
cart mutation would need to reserve/release, `CartItem` quantity edits
would need to adjust reservations, and abandoned-cart expiry would need
to run continuously in production) than what today's actual synchronous
checkout flow requires; the model and service already support this mode
for a future, explicitly-scoped follow-up.

---

## ADR-40: Warehouse Transfers Move Only the Per-Warehouse Breakdown; the Aggregate `Product`/`ProductVariant.stock` Is Untouched by an Internal Transfer

**Context.** `WarehouseTransfer` moves quantity from a source to a
destination warehouse of the same Store through an explicit state machine
(`DRAFT → REQUESTED → IN_TRANSIT → RECEIVED`, with `CANCELLED` reachable
from any non-final state). Every other `StockMovement` reason
(`ORDER_PLACED`, `RETURN_RESTOCK`, `MANUAL_ADJUSTMENT`, etc.) records
`stock_before`/`stock_after` against the aggregate `Product`/`ProductVariant.stock`,
because those events actually change how much of the product is
sellable in total.

**Decision.** A transfer between two warehouses of the *same* Store never
changes how much is sellable in total — it only changes *where* it
physically sits — so `ship_transfer`/`receive_transfer`/a cancelled
in-transit transfer's compensating restock touch only `WarehouseInventory.on_hand`
for the two warehouses involved; `Product.stock`/`ProductVariant.stock`
(ADR-38's single authoritative field) is never written by
`apps.catalog.services.transfer_service`. Consequently, the
`WAREHOUSE_TRANSFER_OUT`/`WAREHOUSE_TRANSFER_IN` `StockMovement` rows this
service writes record `stock_before`/`stock_after` against the *warehouse's*
`on_hand`, not the product aggregate — a deliberate, documented exception
to every other `StockMovement` reason's convention, made explicit in
`transfer_service`'s module docstring so a future reader does not assume
it is a bug. `ship_transfer`/`receive_transfer` are only reachable from
one specific prior status each (`REQUESTED`→ship, `IN_TRANSIT`→receive),
so a retried request after a successful transition is rejected by the
state machine itself rather than re-applying the balance change — the
same idempotent-on-retry shape as this checkpoint's reservation-consume
path (ADR-39).

**Consequences.** `test_transfer_service.py`'s
`test_full_happy_path_moves_balance` asserts the aggregate `Product.stock`
is unchanged across a complete ship→receive cycle, which is the concrete,
tested expression of this decision. Cancelling an `IN_TRANSIT` transfer
restores the shipped quantity to the source warehouse's balance (since it
never reached the destination) — also with no effect on the aggregate.

**Alternatives considered.** Treating a transfer as a restock-then-decrement
pair against the aggregate field (mirroring `RETURN_RESTOCK`) — rejected
because it would imply the total sellable quantity of a product
transiently drops while a transfer is `IN_TRANSIT`, which is not true: the
stock still belongs to the Store and is not sellable-elsewhere-in-the-
meantime in any way this codebase's single-Store-front checkout models —
only its warehouse location is provisionally ambiguous.

---

## ADR-41: Shipping Zone Matching Uses Only Address Dimensions This Codebase Actually Has (Province/City/Postal Code), With a Documented Precedence and No Country Tier

**Context.** Checkpoint 3B asks for Store-owned Shipping Zones matched by
country, region/province, city, and postal code, with a documented
precedence policy and an optional fallback zone. This codebase's only
address model, `apps.customers.models.Address`, has `province`, `city`,
and `postal_code` fields — there is no `country` field anywhere in this
codebase, because Rastisi is an Iran-only platform (verified: no country
field on `Address`, `Store`, `Order`, or anywhere else; every phone number
field assumes the Iranian mobile format).

**Decision.** `ShippingZone` matches on exactly the three dimensions that
exist — `provinces`, `cities`, `postal_codes` (each a plain JSON list of
strings, plus `excluded_provinces`/`excluded_cities` for exceptions) — and
the "country" precedence tier from the request's own suggested order is
simply omitted, not stubbed out with a fake always-Iran country field.
`resolve_shipping_zone` (`apps.orders.services.shipping_service`)
implements the precedence: exact postal-code match → city match →
province match → the Store's single `is_fallback=True` zone (DB-enforced
"at most one fallback zone per Store" via the same conditional
`UniqueConstraint` pattern as `Warehouse.is_default`/`TaxClass.is_default`)
→ no match. Within a tier, ties break by `(priority, pk)` — lower
`priority` wins, then the lower, stable primary key, exactly the same
final tie-break idiom used by `ShippingRateRule` (ADR-42) and `TaxRate`
resolution (ADR-45).

**Consequences.** Zone matching is deterministic and fully tested
(`test_shipping_service.py::ResolveShippingZoneTests`) without inventing
unsupported geography infrastructure. A `ShippingMethod` with no `zone`
set (every row that existed before this checkpoint, since the field is
new and nullable) is always available regardless of address — zone
restriction is opt-in per method, not a retroactive requirement on
existing data.

**Alternatives considered.** Adding a `country` field "for completeness"
even though every real Store on this platform is Iran-only — rejected as
speculative infrastructure with no current caller and no test that could
exercise it meaningfully; adding it later if Rastisi ever expands beyond
Iran is a small, additive migration, not a redesign.

---

## ADR-42: Shipping Rate Rule Selection — Priority, Then Specificity, Then Primary Key; Falling Back to the Legacy Flat `ShippingMethod.cost` When No Rule Matches

**Context.** `ShippingRateRule` (bounded by subtotal range, weight range,
an optional rule-specific free-shipping threshold, and an active window)
can have multiple rows attached to one `ShippingMethod`, and more than one
could match the same cart (e.g., a wide-open "default" rule and a
narrower "over 500,000 Toman" rule both covering the same subtotal).

**Decision.** `resolve_best_rate_rule` (`shipping_service`) selects by
`(priority, -specificity, pk)` ascending: lower numeric `priority` wins
first (matching the request's own recommendation); if two active,
matching rules tie on `priority`, the more specific one wins —
`ShippingRateRule.specificity` is simply a count of how many of the four
bound fields (`min_subtotal`/`max_subtotal`/`min_weight_grams`/
`max_weight_grams`) are non-null, so a rule bounded on both subtotal and
weight beats one bounded on neither; a final tie breaks on the stable
`pk`. Bounds are inclusive on both ends (`min <= value <= max`), the
"recommended interval policy" the request itself suggests. When a
`ShippingMethod` has **no** active, matching `ShippingRateRule` at all —
the state of every `ShippingMethod` row that existed before this
checkpoint, since none had rate rules — `calculate_shipping_rate` falls
back to the pre-checkpoint `ShippingMethod.cost` unchanged.

**Consequences.** `test_shipping_service.py::ResolveBestRateRuleTests`
and `CalculateShippingRateTests` test every boundary (inclusive min/max,
priority tie-break, specificity tie-break, inactive/expired/future rules,
weight bounds) directly. Because the fallback is exact and
unconditional, every existing checkout/pricing test — none of which ever
create a `ShippingRateRule` — continues to compute shipping cost via the
identical `method.cost` path, verified by re-running the entire existing
suite with zero changes after this checkpoint's model additions.

**Alternatives considered.** "Most specific always wins regardless of
priority" — rejected in favor of the request's own explicit recommendation
(priority first) since a merchant should be able to force a coarse rule to
override a narrow one if they set priorities that way; specificity is
only the tie-breaker, not the primary key.

---

## ADR-43: Checkout Always Recalculates Shipping Server-Side From the Resolved Address; a Client-Submitted Method Foreign to the Store, Inactive, or Out of Zone Is Rejected at Order Creation, Not Just at Selection Time

**Context.** The pre-existing checkout flow already filtered the
selectable `ShippingMethod` list by `store` (ADR from Phase 1/checkpoint
1's tenant-isolation work) but had no concept of zones, and — more
importantly — `order_service.create_order_from_cart` trusted whatever
`shipping_method` object its caller (`checkout_service.finalize_order`)
handed it, without re-validating that method against the *final* resolved
address at the exact moment of order creation.

**Decision.** `create_order_from_cart` now independently re-derives
`province`/`city`/`postal_code` from the `Address` it is about to
snapshot, and — for any non-pickup method — calls
`shipping_service.get_available_shipping_methods` itself and rejects with
`ValueError` if the given `shipping_method` is not in that freshly
computed list, in addition to the pre-existing `store_id` and `is_active`
checks. This closes the gap where a method could pass an earlier
zone-check (e.g. in `checkout_service.build_context`, rendered from a
slightly stale session address) but no longer be valid by the time the
order is actually created — the *last* check, inside the same function
and same transaction that writes the `Order` row, is authoritative.
`checkout_service.active_shipping_methods`/`set_shipping_method` also
route through the same `get_available_shipping_methods` function (not a
second, hand-rolled filter), so there is exactly one implementation of
"which methods are valid for this address," not two that could drift.

**Consequences.** A manipulated POST that names a shipping method
belonging to another Store, an inactive method, or a zone-restricted
method that does not cover the checkout address is rejected with a clear
message before any `Order`/`OrderItem`/`StockMovement`/reservation-consume
side effect occurs — verified directly by
`test_order_service_shipping_tax.py::ShippingMethodValidationTests`. Pickup
methods (`is_pickup=True`) are exempted from the zone check since they are
not tied to a delivery destination at all.

**Alternatives considered.** Re-validating only in `checkout_service`
(the layer above) and trusting `order_service` to accept whatever it is
given — rejected because `order_service.create_order_from_cart` is
documented elsewhere in this codebase as "the only Production path that
creates an `Order`" (see its own docstring and ADR-33/38/39), so it is
exactly the place that must not trust a caller-supplied object without
its own re-check, the same discipline already applied there to `vendor`
and `coupon`.

---

## ADR-44: Tax Configuration Lives on the Existing `ShopSettings` Model, Not a New Table — and `tax_enabled` Defaults to `True`, Not `False`

**Context.** `ShopSettings.tax_percent` already existed before this
checkpoint and was applied unconditionally by `cart_totals` on every cart,
for every Store, with no on/off switch. Checkpoint 3B asks for a proper
Tax Settings surface (`tax_enabled`, `prices_include_tax`,
`shipping_taxable`, a default `TaxClass`, a rounding policy) and suggests
a "OneToOne Store-owned settings model unless the existing Store settings
model is more appropriate."

**Decision.** The existing `ShopSettings` model — already the single
Store-scoped settings surface for pricing, branding, and SMS — gains the
new tax fields directly, rather than introducing a second Store-scoped
settings singleton alongside it. Critically, `tax_enabled` defaults to
**`True`**, not the more "conservative-sounding" `False`: this is not a
new feature being cautiously opt-in, it is a literal description of
behavior that has always existed on this platform (a flat percentage
always applied) — defaulting it to `False` would have been a silent,
platform-wide tax cut for every existing Store the moment this migration
ran. `prices_include_tax` defaults to `False` and `shipping_taxable`
defaults to `False` for the same reason: both describe the *exact*
pre-checkpoint arithmetic (`cart_totals` added tax on top of the
post-discount subtotal and never touched shipping), so defaulting them to
match that history is the only choice that changes zero existing Stores'
computed totals on migration day.

**Consequences.** Every Store that existed before this checkpoint gets the
new fields with defaults that reproduce its exact prior tax behavior,
verified by the entire pre-existing `test_pricing.py` suite passing
unmodified. A merchant explicitly disabling tax, switching to
tax-inclusive pricing, or making shipping taxable is now a deliberate,
recorded settings change (audited via `record_audit_event`, action code
`tax_settings.updated`), not an accidental side effect of this migration.

**Alternatives considered.** A separate `TaxSettings` OneToOne model —
rejected for the same reason `ShopSettings` itself was never split
further in ADR-10: these are all still "Store-wide pricing/identity
knobs," and splitting tax settings into their own table would mean two
places (`ShopSettings.tax_percent` and the new model) both claim to
describe "this Store's tax behavior," with the flat `tax_percent` field
now oddly homeless. Keeping everything on `ShopSettings` keeps exactly
one place answering "how does this Store compute tax."

---

## ADR-45: Tax Resolution Falls Back to the Flat Rate Only When a Store Has Zero `TaxRate` Rows At All; Once *Any* `TaxRate` Exists, an Uncovered Product/Province Is Zero-Taxed, Not Silently Flat-Rated — and Tax-Inclusive Pricing Extracts Rather Than Adds

**Context.** `TaxClass`/`TaxRate` are new, Store-scoped, opt-in models.
Every Store that existed before this checkpoint has zero rows in either
table. The calculation service needs one rule for "what happens when a
specific product's resolved tax class has no matching rate" that does not
quietly reintroduce two different, disagreeing tax computations on the
same order.

**Decision (fallback boundary).** `tax_service.calculate_order_taxes`
checks `store_has_granular_tax_rates(store)` — literally "does this Store
have at least one `TaxRate` row, for any `TaxClass`, anywhere" — exactly
once, for the whole order, not per line. If **no** `TaxRate` rows exist
for the Store at all, every line uses the old flat
`ShopSettings.tax_percent` formula, byte-identical to the formula
`cart_totals` used before this checkpoint (`_legacy_flat_tax`). If the
Store has **any** `TaxRate` row (meaning a merchant has explicitly opted
into granular, per-jurisdiction tax), then `_granular_tax` runs for every
line, and a line whose resolved `TaxClass` (the product's own, or the
Store's `default_tax_class` if the product has none) has no matching,
active, in-window `TaxRate` for the given province gets **zero** tax for
that line — it does *not* silently fall back to the flat percentage.
Mixing "some products get precise per-jurisdiction rates" with "products
the merchant forgot to configure quietly get the old flat rate instead"
would be a confusing, undocumented hybrid that could misstate tax on
receipts without any visible warning. `resolve_tax_rate` itself matches
exact province first, then the Store-wide `province=""` row, then `None`.

**Decision (inclusive vs. exclusive).** `prices_include_tax=False`
(default, matching every pre-checkpoint Store): tax is computed and
*added* to the line subtotal — unchanged from before.
`prices_include_tax=True`: the line subtotal is already assumed to
contain tax, so the tax portion is *extracted* —
`line_subtotal × rate / (100 + rate)` instead of `line_subtotal × rate /
100` — and that extracted amount is **not** added again when assembling
`grand_total` (`tax_added_to_grand_total` is `0` for the product-tax
portion in inclusive mode). Shipping tax is always computed and added
exclusively, regardless of `prices_include_tax`, on the theory that
shipping is quoted and charged separately from item prices in this
codebase (`shipping_cost` is never bundled into `items_total`) — a
merchant configuring inclusive item pricing is describing how their
product prices are quoted, not how their shipping fee is quoted.

**Consequences.** `test_tax_service.py`'s `CalculateOrderTaxesGranularTests.
test_line_without_matching_rate_is_zero_not_flat_fallback` and
`InclusiveTaxTests` assert both halves of this decision directly. A Store
can adopt granular tax incrementally (configure a few `TaxClass`/`TaxRate`
rows for the jurisdictions it actually needs) without every other,
not-yet-configured product silently reverting to a possibly-wrong flat
rate — the zero-tax result is visible and points the merchant at exactly
what to configure next.

**Alternatives considered.** Falling back to the flat rate per-line
when that specific line's class/province has no rate, even inside
granular mode — rejected because it would make a Store's tax behavior
depend on an invisible, per-product mix of "granular" and "still flat,"
impossible to audit from the merchant UI without inspecting each
product's resolved class one at a time.

---

## ADR-46: Tax Rounding Is a Per-Store Policy (`on_total`/`per_line`), Defaulting to `on_total` to Match the Flat-Rate Formula's History Exactly

**Context.** The pre-checkpoint flat-rate formula rounded exactly once,
on the whole after-discount total (`_round(after_coupon * tax_percent /
100)`). A per-line-rounding policy (round each line's tax independently,
then sum) is the more common professional pattern but produces a
different total by a few Toman on multi-item carts whenever the
per-line roundings don't cancel out exactly the way one whole-total
rounding would.

**Decision.** `ShopSettings.tax_rounding_policy` is an explicit two-value
choice (`ON_TOTAL`/`PER_LINE`), defaulting to `ON_TOTAL` — the only value
that reproduces the pre-checkpoint formula's exact arithmetic for every
existing Store. The legacy flat-rate path (`_legacy_flat_tax`) always
computes on the aggregate `taxable_total`, ignoring the rounding-policy
setting entirely, since it is describing history, not a configurable
computation — this is deliberate, not an oversight: the policy field
only takes effect once a Store has opted into the granular path
(`_granular_tax`), which honors `PER_LINE` by rounding and summing each
line's tax independently, or `ON_TOTAL` by summing raw (unrounded)
per-line tax and rounding once at the end.

**Consequences.** No existing Store's tax total can change by adopting
this checkpoint's code alone — the rounding policy field exists and is
settable, but its *effect* only begins the moment a Store also adds its
first `TaxRate` row, at which point the merchant has already made an
active decision to configure granular tax and can review the resulting
totals.

**Alternatives considered.** Applying the rounding policy to the legacy
flat path too (for symmetry) — rejected because the legacy path's whole
purpose is to be a frozen, exact reproduction of pre-checkpoint behavior;
making it "configurable" would reintroduce the same regression risk this
entire fallback design exists to avoid.

---

## ADR-47: Order and OrderItem Shipping/Tax Snapshots Are Independent Denormalized Fields, Not Live References — Changing or Archiving a `ShippingMethod`/`ShippingZone`/`TaxClass`/`TaxRate` Never Alters an Existing Order

**Context.** `Order` already snapshotted its address as a plain
`JSONField` (`address`) rather than only keeping a live FK to a mutable
`Address` row — precedent this checkpoint extends to shipping and tax.
Checkpoint 3B explicitly requires that historical orders remain readable
and numerically unchanged after a merchant edits or archives a
`ShippingMethod`, `ShippingZone`, `TaxClass`, or `TaxRate`.

**Decision.** `Order` gains plain-value snapshot fields
(`shipping_method_name`/`_code`, `shipping_zone_name`/`_code`,
`shipping_rate_rule_label`, `min_delivery_days`/`max_delivery_days`,
`is_pickup`, `pickup_warehouse_name`, `pickup_address`,
`prices_include_tax`, `tax_rounding_policy`, `shipping_tax`) populated
once, at order-creation time, by `create_order_from_cart` — alongside the
pre-existing live `shipping_method` FK (kept for referential/reporting
convenience, `on_delete=PROTECT`, so a method in use can't be hard-deleted
underneath an order, but its *display* never depends on that FK still
matching current data). `OrderItem` gains the equivalent per-line tax
snapshot (`taxable_amount`, `tax_class_code`/`_name`, `tax_rate_percent`,
`unit_tax`, `total_tax`, `discount_allocation`) and a
`fulfillment_warehouse` snapshot (ADR-48). None of these fields are
derived at display time from the live `ShippingMethod`/`ShippingZone`/
`TaxClass`/`TaxRate`/`Warehouse` rows — they are written once and read
verbatim forever after.

**Consequences.** `test_order_service_shipping_tax.py::
test_changing_default_warehouse_later_does_not_alter_historical_snapshot`
is the concrete, tested expression of this decision for warehouses; the
same principle holds for every other snapshot field by construction (none
of them are computed properties or `select_related` lookups at render
time). The cost is the usual one for denormalization: these fields must
be written correctly and completely at creation time (they are, inside
the same transaction as the rest of order creation) since nothing will
ever "self-heal" them later if a bug omits one.

**Alternatives considered.** Reading shipping/tax display values live
from the current `ShippingMethod`/`TaxClass`/etc. rows at Order-detail
render time — rejected outright; the request's own definition of
"complete" explicitly forbids this ("do not rely on live Shipping Method
rows to display historical Orders"), and it would mean editing today's
shipping cost retroactively changes yesterday's invoices.

---

## ADR-48: Return/Refund Restock Warehouse Selection — Explicit Merchant Choice, Then the Order Item's Own Fulfillment Warehouse, Then the Store Default; Never a Silent, Unrelated Warehouse

**Context.** Before this checkpoint, `restock_return_item`/
`restock_refund_item` always resolved the Store's *current* default
warehouse (ADR-38's addendum), with no way to record or choose otherwise.
Checkpoint 3B asks for deterministic, explicit restock-warehouse selection
that does not depend on whatever happens to be the default warehouse at
the moment of restocking (which could differ from the warehouse that
originally shipped the item, especially once transfers or a default-
warehouse change have occurred in between).

**Decision.** `OrderItem.fulfillment_warehouse` is a new snapshot field —
populated once, at order-creation time, with whichever warehouse
`_sync_warehouse_balance` actually debited for that line (today, always
the Store's default warehouse at that moment, per ADR-38, but the field
itself does not assume that will always be true — it records the *real*
warehouse, whatever resolves it). `ReturnItem.restock_warehouse` is a new,
merchant-settable field for return inspection/completion — explicit
override, `None` by default. `inventory_service._resolve_restock_warehouse`
implements the exact three-tier priority the request specifies: (1) an
explicit `ReturnItem.restock_warehouse`, if set and still active,
(2) `OrderItem.fulfillment_warehouse`, if set and still active,
(3) the Store's current default warehouse. An explicit or fulfillment
warehouse belonging to a *different* Store, or archived
(`is_active=False`), is rejected (`InvalidRestockWarehouseError`) or
silently skipped down to the next tier (an archived fulfillment warehouse
falls through to the Store default; an archived or foreign *explicit*
choice is a hard error, since that one was chosen by a human this time,
not inherited from history) rather than restocking into it.

**Consequences.** A return can restock into the exact warehouse the item
actually shipped from, months after the Store's default warehouse has
since changed (`test_return_warehouse_policy.py::
test_uses_original_fulfillment_warehouse_when_no_explicit_choice`), or a
merchant handling an in-person return at a different location can
override that explicitly. `restock_refund_item` (the no-formal-return
quick-refund path) gets the same two-tier fallback (explicit choice is
not offered there today, since that UI does not exist — see the report's
"not delivered" list) minus the merchant-override tier.

**Alternatives considered.** Always restocking to whichever warehouse is
currently the Store default (the pre-checkpoint behavior) — rejected as
the exact gap this ADR closes: it can silently restock into the wrong
physical location once a Store operates (or has ever operated) more than
one warehouse and changed its default in between order and return.

---

## ADR-49: Export/Import Jobs Execute Synchronously In-Request — No Background Task Queue Exists in This Codebase

**Context.** Checkpoint 4 asks for `ExportJob`/`ImportJob` models with
`pending`/`processing`/`completed`/`failed` status fields, which reads like
a background-worker design. This codebase has no Celery (or any other) task
queue — `requirements.txt` confirms only Django/jdatetime/Pillow/requests/
cryptography/psycopg/beautifulsoup4/PySocks — and introducing one is far
outside a single checkpoint's blast radius (new infra dependency, a worker
process to deploy/monitor, broker configuration).

**Decision.** `run_export` (and, when built, the import execution service)
performs the entire job — row generation, CSV writing, file save — inside
one synchronous call, within the same request/response cycle that
triggered it. The status field still transitions `pending → processing →
completed`/`failed`, and the job row is still written first (so a crash
mid-generation leaves a `processing` row behind, not silence), but there is
no real concurrency or queueing behind those states today. This is recorded
here explicitly rather than left to be discovered: a job row's
`started_at`/`completed_at` being seconds apart is not a monitoring bug,
it is the actual, honest execution model.

**Consequences.** Very large exports (tens of thousands of rows) block the
requesting worker process for the duration of generation — acceptable for
this checkpoint's scope (`iterator()`-based, chunked queries keep memory
bounded, just not wall-clock time), but a real background queue is the
correct next step before this is exposed to Stores with very large
catalogs/order histories. `cleanup_expired_exports` (a management command,
not a signal) is how expired files actually get reclaimed, since there is
no worker to run a periodic task automatically — see the production
configuration doc for the cron/systemd-timer scheduling this still requires
operationally.

**Alternatives considered.** Faking asynchronicity with a `threading.Thread`
— rejected: Django's request/response cycle and test client both assume
the response body is complete when the view returns, and an unmanaged
background thread has no supervision, no error surface, and would silently
diverge from the job's recorded status the moment the request completed
before the thread did.

---

## ADR-50: Customer Export Reuses Per-Store Order Aggregation — Never `Customer.orders_count`/`Customer.total_spent`

**Context.** `Customer` is deliberately global (no `store` FK — see the
Customer-identity entry in the summary table below), and it carries two
static fields, `orders_count`/`total_spent`, that a naive Customer export
might reach for directly. Those fields are cross-Store aggregates (or, per
`apps.dashboard.services.customers_admin_service`'s own docstring, seed-only
values never updated by the real checkout flow) — exporting them from a
single Store's admin panel would leak another Store's purchase totals for
any Customer who has ever ordered from more than one Store on this
platform, a direct tenant-isolation violation dressed up as a normal field
read.

**Decision.** `_customers_rows` in `export_service.py` computes
`order_count`/`paid_total`/`last_order_at` the same way
`customers_admin_service.annotated_customers` already does for the
customer-list page: `Count`/`Sum`/`Max` annotations filtered to
`orders__store=store`. Every number in a Customer export row is therefore
provably scoped to the exporting Store's own Orders, never the Customer's
platform-wide history.

**Consequences.** A Customer who ordered from two Stores exports different
(correct, Store-scoped) totals from each Store's admin panel — matching the
same "two Stores, two independent views of one shared identity" model the
customer-list page already established. Any future Customer CRM field
(`CustomerProfile` cached stats, checkpoint 4 §14) must follow the same
rule: compute from Store-filtered Orders, never read a bare `Customer`
field that isn't itself Store-scoped.

**Alternatives considered.** Adding a `store` FK to `Customer` to make this
automatic — explicitly out of scope per the existing, pre-checkpoint
architectural decision recorded in the Customer-identity entry below; this
checkpoint works within that decision, it does not revisit it.

---

## ADR-51: CSV Injection Protection Is One Shared Utility, Applied at Write Time to Every Cell of Every Export

**Context.** Any CSV a merchant might open in Excel/Google Sheets is a
classic CSV-formula-injection vector (OWASP): a cell value starting with
`=`, `+`, `-`, or `@` — trivially reachable via an ordinary Product name,
SKU, or customer note — is interpreted as a formula by the spreadsheet
application, not displayed as literal text, and can execute arbitrary
formulas (including `=cmd|'/c calc'!A1`-style command execution in older
Excel configurations) the moment the file is opened.

**Decision.** `apps.core.services.csv_utils.sanitize_csv_cell` is the single
place this platform decides what "safe to write as a CSV cell" means:
any value whose string form starts with one of the four formula-trigger
characters gets a leading single-quote (`'`) prefix, which spreadsheet
software renders as literal text instead of evaluating as a formula.
`write_csv_rows` applies this to the header row and every data row's every
cell — no export or (future) import-preview code is permitted to call
`csv.writer` directly; `run_export`'s row builders never sanitize
themselves, by design, so there is exactly one place this protection can
regress.

**Consequences.** A Product deliberately or accidentally named
`=1+1` (or any SKU/customer name/tag starting with `=`/`+`/`-`/`@`) exports
as `'=1+1` — visibly, harmlessly literal in any spreadsheet, verified by
`test_csv_injection_formula_prefix_neutralized`. This is a write-time
concern only; reading a CSV back in (the future import path) does not need
to strip the leading quote, since `read_csv_rows`'s `DictReader` returns
the field exactly as stored and import validation operates on that string
directly (a leading `'` in an *input* file is a data question for the
import validator, not a security concern this module owns).

**Alternatives considered.** Wrapping every cell in `="..."` (Excel's own
"treat as text" escape) — rejected: it changes the visible cell content
for every value, not just the dangerous ones, making the exported file
confusing to read normally. Rejecting/blocking export of any row containing
a formula-prefixed value — rejected as unnecessarily destructive: an
export's job is to faithfully represent Store data, not silently drop rows
because a Product name happens to start with a minus sign.

---

## ADR-52: Export Files Are Private, Time-Limited, and Served Only Through an Authenticated, Store-Scoped Download View

**Context.** An `ExportJob.file` can contain Customer PII (Checkpoint 4's
Customer export) or full Order financial detail — the kind of data this
platform has never before written to a location reachable by a plain URL.
Django's default `MEDIA_ROOT`/`MEDIA_URL` serve everything under it to
anyone with the URL, forever — wrong for this class of file on every axis
(no authentication, no Store check, no expiration).

**Decision.** `PRIVATE_MEDIA_ROOT` (a new setting, separate from
`MEDIA_ROOT`) backs a dedicated `apps.core.storage.private_storage`
instance (`FileSystemStorage(base_url=None)`), which raises `ValueError`
the instant anything calls `.url` on a file stored through it — a
deliberate crash-not-leak guard, not a soft convention. The only sanctioned
read path is `dashboard:export-download`
(`apps.dashboard.views.export_download`): `staff_required` (authenticated
merchant-admin member) → `permission_required` (per export-type permission,
`IMPORT_EXPORT_VIEW` or the separately-gated `CUSTOMER_EXPORT`) →
`get_object_or_404(ExportJob, pk=pk, store=store)` (a foreign Store's job
ID 404s exactly like a nonexistent one, revealing nothing) → `FileResponse`
streamed directly from disk. Every `ExportJob` also gets an `expires_at`
(7 days from creation); `mark_expired_jobs`/`cleanup_expired_exports`
(management command) deletes the on-disk file and flips the row to
`expired` once past that date — an expired job's row survives as history,
but its file does not linger on disk indefinitely.

**Consequences.** There is no public URL for any export file, ever — not a
signed URL, not a predictable path, nothing guessable or shareable outside
the platform's own authenticated session. A merchant who wants to hand a
file to someone outside the admin panel must download it themselves first
and share it through their own channel, which is the correct boundary for
platform-generated PII exports.

**Alternatives considered.** Django signed URLs with a short-lived token
— rejected for this checkpoint as unnecessary complexity: this platform has
no CDN/external-storage layer that would need a bearer-token-style URL, and
every export downloader is already an authenticated dashboard session, so
route-level auth is sufficient and simpler. `django-storages`-backed S3
with private ACLs — reserved for whenever this platform actually adopts
S3/object storage generally (it does not today; `FileSystemStorage` matches
every other file field in this codebase).

---

## ADR-53: Customer Segments — Allowlisted Rule Fields/Operators, Per-Rule Independent Queries Combined by Set Algebra, and Query-Based Preview With Explicitly-Refreshed Materialized Membership

**Context.** Checkpoint 4 asks for a Customer Segment rule engine (order
count, total spent, last/first order date, has-purchased-Product/Category,
has-used-Coupon, customer tag, no-purchase-for-N-days, refund count) that is
"real" but explicitly *not* an arbitrary expression language, must not
evaluate large datasets row-by-row in Python, and needs a documented,
honest answer for how a `dynamic` segment's live membership relates to a
materialized list usable by (future) bulk actions.

**Decision.** `apps.dashboard.services.segment_service.ALLOWED_FIELDS` is a
closed dict mapping each of the nine specified fields to its value type and
its own allowed operator subset (e.g. `has_purchased_product` only accepts
`contains`, never `greater_than`); `validate_rule` is the single choke point
both the rule-builder form and the evaluator call, so a rule can never be
saved with a field/operator pairing the evaluator would then refuse to run.
Every rule becomes its own independent, Store-scoped Django queryset that
returns a *set of Customer primary keys* — never a shared multi-`annotate`
queryset joined across rules, which is the well-known Django trap that
silently multiplies row counts (fan-out) when more than one `Count`/`Sum`
annotation touches the same one-to-many relation in one query. Combining a
segment's rules is therefore plain Python set algebra: intersection for
`match_mode=all`, union for `match_mode=any` — over integer ID sets, which
is not "row-by-row business-logic evaluation in Python," it is picking
which of several already-computed, DB-filtered ID sets to combine.
`preview_segment` for a `dynamic` segment always re-evaluates live (what you
see on the segment detail page is never stale); `CustomerSegmentMembership`
rows are a separate, explicitly-materialized cache, written only by
`refresh_segment_membership` (called from the "Refresh Membership" button or
the `refresh_customer_segments` management command) — the two are
deliberately decoupled so the detail page is always trustworthy even if a
merchant never clicks refresh, while a *future* bulk-action feature has a
stable snapshot to act against instead of re-evaluating rules mid-operation.

**Consequences.** Adding a tenth allowed field is a one-line addition to
`ALLOWED_FIELDS` plus one new branch in `_matching_customer_ids` — the
allowlist shape makes "what can a segment rule check" auditable at a
glance, unlike a free-form query builder. Because there is no background
task queue (ADR-49), `refresh_customer_segments` must be scheduled
externally (cron/systemd timer) exactly like `cleanup_expired_exports` —
until scheduled, a `dynamic` segment's *materialized* membership (relevant
only to future bulk actions) goes stale, though its *displayed* preview
never does. `customer_tag` rules resolve through `CustomerProfile.tags`
Store-scoped exactly like every other Customer CRM query (ADR-50's
pattern), so a rule can never match on another Store's tag.

**Alternatives considered.** A single combined queryset with one `annotate`
per numeric field plus `Exists()` subqueries for the reference fields —
rejected: correct in isolation but fragile to get right for arbitrary
rule combinations without careful `Subquery`/`Exists` wrapping per rule,
and far harder to unit-test each field in isolation the way the current
one-query-per-rule design allows. Storing an always-fresh materialized
membership via a Django signal on every `Order`/`Refund`/`CustomerTag`
write — rejected: exactly the kind of implicit, hard-to-reason-about
freshness this codebase has avoided everywhere else (see ADR-37's
"provisioning is an explicit call, never a signal" and `CustomerProfile`'s
own cached-stats documentation) — the explicit refresh model is the same
established discipline, not a new one invented for segments alone.

---

## ADR-54: CSV Import (Product/Variant/Inventory) Is Explicitly Deferred Out of Checkpoint 4 — Not Implemented, Not Partially Implemented, Named Here as a Gap

> **Superseded by checkpoint 4B (ADR-55 through ADR-62).** This ADR
> recorded, honestly, that Import was deferred out of checkpoint 4. It was
> then delivered in full in checkpoint 4B along the exact plan sketched in
> its "what a future Import checkpoint needs" section. Kept here unedited as
> the historical record of the deferral decision; the live design is ADR-55+.


**Context.** Checkpoint 4's request specifies a large, genuinely
high-risk Import domain: `ImportJob`/`ImportRowResult` models, a
dry-run-preview engine that shares its exact validation path with
execution, three explicit write modes (`create_only`/`update_only`/
`upsert`), Store-scoped stable-identity resolution, per-batch-atomic
execution with idempotency-key-based replay protection, and — critically
— Product/Variant/Inventory writes that must never bypass the existing
Variant Engine reconciliation rules or write `Product.stock`/
`ProductVariant.stock` directly, instead routing every inventory change
through `apps.catalog.services.inventory_service` so `StockMovement`/
`WarehouseInventory`/`InventoryReservation` all stay consistent (the exact
invariant `verify_inventory_consistency --strict` checks).

**Decision.** This checkpoint delivers Export (all five types, real
services, real UI, real tests), the Customer CRM foundation
(`CustomerProfile`/`CustomerNote`/`CustomerTag`), Customer Segments (a
genuine allowlisted rule engine with preview/refresh and full Merchant
Admin UI), Customer bulk actions, the Product bulk Tax Class gap-closer,
the full checkpoint 4 permission registry, and the associated management
commands/ADRs/tests — but does **not** implement CSV Import. No
`ImportJob`/`ImportRowResult` model exists; no import preview/execution
service exists; no import upload UI exists. This is a deliberate scope
decision, not an oversight: Import is the single largest and highest-risk
remaining piece specifically *because* it writes to Product/Variant/
Inventory — the same subsystems every prior checkpoint (3A's Warehouse/
Reservation engine, 1D's Variant Engine) went to considerable, carefully
tested effort to keep internally consistent. A rushed Import
implementation that wrote stock incorrectly, bypassed reservation
consistency, or created duplicate variants on a malformed CSV would risk
exactly the kind of silent data corruption this codebase's entire
Store-scoping/inventory-ledger discipline exists to prevent — and that
risk is not proportional to fitting Import into the same checkpoint as
five other, already-substantial deliverables.

**Consequences.** Every reference to "Import" in this checkpoint's own
documentation (completion report, this file) names it explicitly as **not
delivered**, not as "partially implemented" or "models only" — per the
request's own instruction not to claim completion on a feature that has
no real evaluation service and UI, the same standard applied to Segments.
A merchant cannot bulk-upload Products/Variants/Inventory changes via CSV
today; every catalog/inventory write still goes through the existing
one-row-at-a-time admin forms and bulk *actions* (status/category/tax
class), which remain fully functional and unaffected by this decision.
The Export domain's file-format/CSV-utilities/private-storage
infrastructure built this checkpoint (`csv_utils.py`, `private_storage`,
`ExportJob`) is deliberately reusable by a future Import checkpoint without
rework — the CSV injection-protection utility, private file storage, and
authenticated-download pattern all transfer directly to an eventual
upload-and-validate flow.

**What a future Import checkpoint needs, concretely** (so this is a plan,
not just a gap): `ImportJob`/`ImportRowResult` models mirroring
`ExportJob`'s shape; a shared preview/execute validation function per
import type (Product/Variant/Inventory) that never diverges between
dry-run and real execution; Product/Variant writes through
`variant_engine_service`'s existing reconciliation entry points, never
direct field assignment; Inventory writes through
`inventory_service.adjust_stock_manually`/the reservation-aware helpers,
never direct `Product.stock`/`ProductVariant.stock` writes; per-batch
transactions sized to avoid loading the whole file into memory
(`csv_utils.read_csv_rows` already streams); an `idempotency_key` column
on `ImportJob` checked before any row is applied, exactly like
`Order.idempotency_key`'s existing pattern.

**Alternatives considered.** Implementing a minimal, Product-only import
(skipping Variant/Inventory) to be able to claim partial delivery —
rejected: the request's own completion checklist explicitly rules out
claiming any credit for a feature that doesn't fulfil its own dry-run/
atomicity/idempotency/tenant-isolation requirements end to end, and a
Product-only slice would still need every one of those mechanisms built
correctly to be honestly called "delivered," at which point it is not
actually a smaller task than the full Import domain.

---

## ADR-55: Import Job Lifecycle — Upload → Synchronous Dry-Run Preview → Explicit Execute, All In-Request

**Context.** Checkpoint 4B asks for an Import domain with a job model whose
statuses read like an async pipeline (`uploaded`/`validating`/
`preview_ready`/`processing`/`completed`/`completed_with_errors`/`failed`/
`cancelled`). This platform has no background task queue (ADR-49) — the
same constraint that shaped `ExportJob`.

**Decision.** `ImportJob` mirrors `ExportJob`: the file is uploaded and
stored privately (`create_import_job`), then a **dry-run preview**
(`run_preview`) parses and validates every row and records an
`ImportRowResult` per row **without touching catalog/inventory data** —
the job lands in `preview_ready`. Only an explicit, separate merchant
action (`run_execution`, behind a confirmation button) re-runs the *same*
validation-and-apply path with `dry_run=False`, mutating data and landing
the job in `completed`/`completed_with_errors`/`failed`. Every transition
happens synchronously within the request that triggered it; the statuses
are history/UI markers, not a real queue. `validating`/`processing` are
transient in-request states set before the work and overwritten after.

**Consequences.** A merchant always sees exactly what will happen before
anything changes — the preview is not an estimate, it is the same code that
executes, so a row shown as "will create" in preview is created on execute
(barring a concurrent external change). Very large files block the worker
for the duration; a real queue is the documented next step before exposing
this to Stores with huge catalogs. `cancel_import_job` lets a
`preview_ready` job be abandoned without executing.

**Alternatives considered.** A single upload-and-apply action with no
preview — rejected: the whole point of the checkpoint is a safe,
reviewable import; applying 20,000 catalog mutations sight-unseen is
exactly what the dry-run exists to prevent.

---

## ADR-56: Import Executes Per-Batch-Atomic, With Row-Level Results and a Shared Preview/Execute Validation Path

**Context.** Checkpoint 4B §16 requires per-batch atomic execution
(default 100 rows), row-level result recording, a failed batch rolling back
without losing other successful batches, and — critically — preview and
execution using the *same* parser and validation code, never a second
divergent implementation.

**Decision.** `run_import` is a single generic engine used by all three
import types and by both preview and execution. It streams rows
(`read_csv_rows_bounded`, never loading the whole file into memory),
chunks them into batches of `DEFAULT_BATCH_SIZE=100`, and runs each batch
inside its own `transaction.atomic`. Each type provides one
`_validate_*_row` function (called identically in preview and execute) and
one `_apply_*_row` function (called only when `dry_run=False`); a row that
fails to apply is caught, recorded as `failed` with its error, and the
batch continues — the per-row apply for products/variants uses nested
atomics (`full_clean`/service calls) so one bad row's writes roll back to a
savepoint without poisoning the batch. Job counters (`total`/`valid`/
`invalid`/`created`/`updated`/`skipped`/`failed`) and final status are
derived from the actual `ImportRowResult` outcomes: all-clean →
`completed`, some invalid/failed but some applied → `completed_with_errors`,
nothing applied → `failed`.

**Consequences.** A single malformed row never aborts a 10,000-row import;
the merchant gets a precise per-row report and a downloadable error CSV of
just the problem rows. Because preview and execute share the validation
function, "validated one way, executed another" drift is structurally
impossible. `MAX_IMPORT_ROWS` (20,000) and `MAX_STORED_ERROR_ROWS` bound
resource use.

**Alternatives considered.** Whole-file single transaction — rejected: one
bad row on row 9,999 would roll back 9,998 good rows, the opposite of the
"preserve successful batches" requirement. Per-row transactions — rejected
as needlessly slow (a savepoint per row) versus per-batch, which the
request explicitly recommends.

---

## ADR-57: Import Stable-Identity Resolution — Store-Scoped ID, Then Store-Scoped SKU, Never Name/Slug; Cross-Store IDs Hard-Rejected

**Context.** An import row must be matched to an existing record (for
update) or recognized as new (for create), deterministically, without ever
letting one Store touch another's data.

**Decision.** Product identity precedence is: (1) a Store-scoped
`product_id` — an integer PK that must resolve to a Product *in this
Store*; a PK belonging to another Store is a hard row error, never a silent
fall-through to SKU; (2) a Store-scoped `sku` — matched only within this
Store's Products; (3) otherwise no match (create, or reject under
`update_only`). Name and slug are never update-identity keys. Variant
identity adds `variant_id`/`variant_sku` (Store-scoped, and consistent with
the row's product) plus the stable option-combination key derived from the
Variant Engine; a `variant_id` alone implies its parent product.
`create_only`/`update_only`/`upsert` are always explicit — the mode is
never inferred from whether a match was found.

**Consequences.** A merchant re-importing an export of their own catalog
updates in place (IDs round-trip); a merchant importing a supplier's file
without IDs matches on SKU within their own Store only. A hostile file
carrying another Store's product/variant/brand/category/tax-class/warehouse
ID gets a row error, never a cross-tenant write — proven by the tenant-
isolation tests.

**Alternatives considered.** Matching on name — rejected explicitly by the
request (names are not stable identity). An `external_id` column — reserved
for a future checkpoint; Product has no such field today, so implementing
it would be speculative scope.

---

## ADR-58: Product Import Writes Only Through the Existing Service/Model Layer — Never a Second Product-Creation Path; Stock Always Through the Inventory Service

**Context.** §10 forbids a second Product-creation system that bypasses
existing invariants, and §8 forbids writing stock directly when warehouse
inventory is enabled.

**Decision.** `_apply_product_row` sets fields on a `Product` instance (new
or fetched), assigns Store-scoped Brand/Category/TaxClass resolved from the
bulk-prefetched lookup cache, generates a unique slug via the existing
`catalog_admin_service.generate_unique_slug`, and calls `product.full_clean()`
(excluding `stock`) then `save()` — the same validation path the admin form
uses, so `Product.clean()`'s cross-Store FK guards and every field
validator run. Stock is applied separately through
`inventory_service.adjust_stock_manually`, which creates the `StockMovement`
and keeps `WarehouseInventory` consistent — the import service never assigns
`Product.stock` directly. Brand/Category/TaxClass are resolved by
**Store-scoped stable code** (`brand_code`=slug, `category_code`=leaf
category slug, `tax_class_code`=code), never by display name; a missing or
foreign reference is a row error, and import never auto-creates categories
or brands.

**Consequences.** Import cannot produce a Product that the admin form would
reject; existing variants, images, historical Order references, and
template-source metadata on an updated Product are untouched (only the
columns present are written). The inventory ledger stays consistent after
import (`verify_inventory_consistency --strict` passes).

**Alternatives considered.** `bulk_create` for speed — rejected: it
bypasses `full_clean` and per-instance slug generation, exactly the
invariants this ADR exists to preserve. Resolving references by name —
rejected by §9.

---

## ADR-59: Variant Import Drives the Existing Variant Engine — Combinations Are Materialized by `generate_variants`, Never Hand-Built

**Context.** §12 requires Variant Import to use the existing Variant Engine,
build the stable combination key, reject duplicate combinations, preserve
existing variant PKs/SKUs/images/Order references, respect the 3-axis cap,
never mix legacy and multi-axis modes, never hard-delete, and never create
`VariantOptionValue` rows in a way that bypasses the engine.

**Decision.** Variant Import resolves each row's option axes/values by
**normalized-label match against the product's already-active
`ProductOption`s/values** (this codebase has no separate option "code"
field — `normalized_label` is the stable identity), builds the combination
key from the resolved value PKs, and — for a combination that does not yet
have a `ProductVariant` — calls the real
`variant_engine_service.generate_variants(product)` **once per product**
(idempotent; it exhaustively materializes all active combinations without
deleting or duplicating any). It then applies the row's SKU/price/stock/
active fields to the resolved variant via `full_clean()`/`save()` and
`adjust_stock_manually`, and routes `is_default` through
`set_default_variant`. Import never creates axes or values, never writes
`VariantOptionValue` directly, and rejects a legacy (single-axis) product,
a foreign product/variant, or a variant whose product doesn't match the
row.

**Consequences.** Every reconciliation rule, the 3-axis cap, the
default-variant single-flag constraint, and the no-hard-delete policy hold
because the engine — not the import code — owns combination identity.
Updating a variant preserves its PK, its images (variant-linked
`ProductImage` rows are untouched), and its SKU when the column is blank.

**Alternatives considered.** Hand-creating `ProductVariant` +
`VariantOptionValue` rows for speed — rejected explicitly by §12; it would
duplicate the engine's combination-key logic and risk divergence from
`generate_variants`' reconciliation.

---

## ADR-60: Inventory Import Routes Every Row Through a Warehouse-Aware Inventory Service Call That Enforces Reservation Safety

**Context.** §13/§14 require every inventory row to use the inventory
service (creating a `StockMovement`, recording warehouse/actor/reason/note,
keeping aggregate stock correct, preserving reservation consistency) and
never to write `WarehouseInventory`/`Product.stock`/`ProductVariant.stock`
directly — and to reject any reduction that would drop available stock
below the active reservation total.

**Decision.** A new `inventory_service.adjust_warehouse_stock` is the single
entry point: it locks the target row (`select_for_update`), computes the
delta (`adjustment` = signed quantity; `set_on_hand` = target minus that
warehouse's current on-hand), rejects a negative aggregate result and —
critically — rejects any result below the sum of **active reservations**
(`available = aggregate − reserved`), then writes the `WarehouseInventory`
balance, the aggregate `Product`/`ProductVariant.stock`, and a
`StockMovement` (reason `IMPORT_ADJUSTMENT`, actor recorded, CSV
reason+note preserved in the movement note) atomically. Inventory Import's
`_apply_inventory_row` only calls this service; a zero-delta row is
`skipped`, not failed. Warehouse/product/variant are all Store-scoped;
cross-Store references and variant-belongs-to-other-product are rejected.

**Consequences.** An import can never oversell — reducing stock below what
carts/orders have already reserved is refused at the row level (adversarial
tests cover both `adjustment` and `set_on_hand`). The reservation model this
codebase tracks per Store/Product (ADR-39), not per warehouse, is honored:
availability is checked against the aggregate, matching how checkout
reserves. The ledger stays consistent (`verify_inventory_consistency
--strict`).

**Alternatives considered.** Per-warehouse reservation checking — rejected:
this codebase reserves at the Product/Store level, not per warehouse, so a
per-warehouse available check would be inventing a model that doesn't
exist. Writing `WarehouseInventory` directly for speed — rejected by §13.

---

## ADR-61: Import Idempotency — Optional Per-Store Key at Upload, Final-Status Guard at Execute

**Context.** §17 requires that a completed job cannot execute twice, a
browser retry cannot duplicate products, inventory is not applied twice,
and variant rows are not duplicated.

**Decision.** Two complementary guards. (1) An optional `idempotency_key`
on `ImportJob`, unique per Store (partial DB constraint when non-empty,
exactly like `Order.idempotency_key`) — a repeat upload with the same key
is rejected at `create_import_job`. (2) `run_execution` refuses to run when
the job is already in `ImportJob.FINAL_STATUSES`
(`completed`/`completed_with_errors`/`failed`/`cancelled`) — so a
double-clicked execute button, or a retry after a partial failure, changes
nothing; the second call raises before reading the file. Because
create/update decisions are re-derived from stable identity (ADR-57) each
run, even a *new* job re-importing the same file updates in place rather
than duplicating.

**Consequences.** The three "retry" scenarios (duplicate execute request,
retry after partial failure, retry after success) are all no-ops on the
same job; a fixed-and-re-uploaded file is a new job that upserts, not
duplicates. Inventory replay is prevented because the same job can't
re-execute, and a corrected re-upload's `set_on_hand` rows are absolute
(idempotent by nature) while `adjustment` rows are the merchant's explicit
new delta.

**Alternatives considered.** Per-row operation keys stored across jobs —
rejected as overkill for this checkpoint; the job-level final-status guard
plus stable-identity upsert covers every replay scenario the request
enumerates.

---

## ADR-62: Import Files Are Private, Filename-Sanitized, Size/Row/Field-Bounded, and Retention-Cleaned Like Exports

**Context.** An uploaded import file is attacker-influenced input
(§22: formula injection, path traversal, oversized files, excessive rows,
invalid UTF-8, null bytes, HTML/script, resource exhaustion) and its stored
copy plus generated error report can contain merchant catalog data.

**Decision.** Import source files and error reports use the same
`private_storage` as exports (ADR-52) — never under `MEDIA_ROOT`, never a
public URL; the only read path is an authenticated, Store-scoped download
view. On-disk filenames are random UUIDs (`import_job_upload_path`), so the
user-supplied filename never reaches the filesystem. `validate_csv_upload`
enforces extension/content-type/size (`MAX_IMPORT_FILE_SIZE_BYTES`=10 MB)
and rejects path/null-byte filenames; `read_csv_rows_bounded` enforces
`MAX_IMPORT_ROWS`=20,000, truncates fields past `MAX_FIELD_LENGTH`=2,000,
strips null bytes, and surfaces invalid UTF-8 as a clean error. The error
report is written through the CSV-injection-safe `write_csv_rows`
(ADR-51) and never contains a raw traceback. `cleanup_import_files` (a
management command, cron-scheduled like the other checkpoint-4 commands)
deletes source and error files past a 30-day retention window while
preserving the `ImportJob` record and its row results.

**Consequences.** CSV parsing (`csv.DictReader`) never evaluates formulas or
interprets HTML — the data is always literal text — so a malicious cell is
inert on import and neutralized on any re-export. No import file is ever
web-reachable; a foreign Store's job/source/error 404s. Disk is bounded by
the size/row limits and reclaimed by the retention command (which, like
exports, requires external scheduling since there is no task queue).

**Alternatives considered.** Trusting the browser-supplied filename or
content-type — rejected: both are client-controlled; the UUID path and the
`csv` parser (not the extension) are the real protections. Keeping import
files forever — rejected: they are regeneratable/re-uploadable, not the
sole copy of any data, so retention cleanup is safe.

---

## ADR-63: A Plan Is a Stable Code; Its Priced Terms Live in Immutable Published PlanVersions

**Context (checkpoint 5A).** A SaaS plan's price, trial length, and included
entitlements change over time, but a store that subscribed under old terms
must keep those terms — history cannot be rewritten by a later edit.

**Decision.** `Plan` holds only stable identity (`code`, display metadata,
`is_active`, `is_publicly_selectable`). All priced/functional terms live on
`PlanVersion` (price, `billing_interval`, `trial_days`, `grace_period_days`,
and the M2M `PlanEntitlement` set). A version has a status
(draft→published→retired/archived); **once published it is immutable** —
enforced server-side, not just in the UI: `plan_service` refuses to mutate a
published version's entitlements, and the Django Admin (`PlanVersionAdmin`)
makes every priced field readonly and blocks deletion once status ≠ draft.
Merchants never see plan administration at all — it lives only in Django
Admin behind superuser (ADR-8's boundary).

**Consequences.** A subscription references an exact `PlanVersion`, so its
terms are frozen regardless of later plan edits. New terms mean a new version.
Because published versions are immutable, entitlement resolution can safely
cache per-version.

**Alternatives considered.** Editable plans with a price field — rejected:
silently rewrites the terms every existing subscriber agreed to.

---

## ADR-64: Entitlements Are the Single Source of Truth — Never `plan.code == "pro"`

**Context.** Feature/limit checks scattered as plan-name comparisons rot the
moment a plan is renamed or a new tier appears.

**Decision.** A central `entitlement_service` answers "what does this store
have access to?" keyed on stable `EntitlementDefinition` keys (registered once
in `entitlements.py`), never on a plan name. Booleans resolve via
`has_entitlement`; numeric caps via `get_entitlement_limit` (`None`=unlimited,
`0`=disabled, else the integer). Resolution reads the store's current
subscription → effective `PlanVersion` → `PlanEntitlement`, with a per-
version cache invalidated by `updated_at` (safe because published versions are
immutable, ADR-63).

**Consequences.** Adding a plan or renaming one changes no code. A view or
service asks about an entitlement key, never a tier.

**Alternatives considered.** `if plan.name == "pro"` — rejected as the exact
anti-pattern this ADR exists to forbid.

---

## ADR-65: Fail-Open Fallback and Legacy Grandfathering — Existing Stores Are Never Silently Restricted

**Context.** Introducing subscriptions onto a live platform must not, on
deploy, strip capabilities from stores that predate the concept.

**Decision.** Entitlement resolution is **fail-open**: a store with no current
subscription, or a plan version that does not define a given key, resolves to
unlimited/enabled — while `get_subscription_access_state` still reports the
true state honestly. Separately, migration `0003` (and the idempotent
`provision_legacy_subscriptions` command, sharing one `provision_legacy`
helper) creates a hidden, non-publicly-selectable **Legacy** plan with a
published version where every feature is enabled and every limit is unlimited,
and gives **every** existing store an active legacy subscription. Existing
stores are never assigned a limited Starter plan.

**Consequences.** Deploy day changes nothing for existing stores. Only
genuinely new stores (via `provision_default_subscription`, ADR-72-adjacent)
land on a configured default plan.

**Alternatives considered.** Defaulting existing stores to the entry tier —
rejected: it is a silent downgrade of paying-in-kind incumbents.

---

## ADR-66: One Explicit Subscription State Machine; No View Writes `status` Directly

**Context.** Subscription lifecycle (pending/trialing/active/grace/past_due/
suspended/cancelled/expired) is exactly the kind of state that drifts into
inconsistency if any view can poke `status`.

**Decision.** `subscription_service` is the only path that changes state. Every
transition goes through `_transition`: `select_for_update`, an
`ALLOWED_TRANSITIONS` legality check, idempotent same-status no-op, keeping
`is_current=False` for terminal states, and recording both a
`SubscriptionEvent` and an audit-log entry. Exactly one current subscription
per store is a conditional DB unique constraint on `is_current=True`.

**Consequences.** Illegal transitions (e.g. `expired→active`) are impossible.
State and `is_current` never disagree. Django Admin makes `status` readonly so
even a superuser cannot bypass the machine.

---

## ADR-67: One Trial Per Store; A Plan Change Never Resets the Trial

**Decision.** Trial length comes from the `PlanVersion.trial_days`; a store
trials once. `change_plan_version` alters only the plan version and records a
`plan_changed` event — it never touches `trial_start_at`/`trial_end_at`, so
switching plans mid-trial cannot farm a fresh trial. Grace length likewise
comes from `grace_period_days` and is entered explicitly.

**Consequences.** Trial abuse via plan-hopping is structurally impossible.

---

## ADR-68: Usage Is Live Counts for Resources and Period Counters for Actions

**Decision.** `usage_service` measures two kinds of usage. **Live-count**
metrics (products, variants, staff seats, warehouses, segments) are computed
by querying the current rows on demand — there is no separate counter to drift.
**Period** metrics (monthly import rows, monthly exports) are calendar-month
`UsageRecord` counters incremented atomically (`F()` + `select_for_update`),
consumed by the acting service exactly once per operation. Reading over-limit
usage always works; only creation is gated.

**Consequences.** A downgrade that leaves a store over a limit is fully
readable; the numbers are always truthful because live counts cannot desync.

---

## ADR-69: Limits Are Enforced in the Service Layer, So Imports and Bulk Actions Cannot Bypass Them

**Decision.** Creation limits and subscription-state gates live in
`enforcement.py` and are called from the **service layer** (warehouse, staff,
variant, product, segment creation; product/variant/inventory import; export),
never only in a view. Each gate is three layers: subscription state allows
growth → feature enabled → numeric limit not exceeded. Updates to existing
records and reads of over-limit data are never gated — only creation. Bulk and
generation paths check the **total** requested increment up front and never
silently truncate; an import that would exceed a resource limit fails the
overflow rows individually (updates still apply) while an over-quota monthly
import is rejected whole.

**Consequences.** A direct POST, a CSV import, or a Cartesian variant
generation is subject to the same ceiling as the dashboard form. There is no
back door around a plan limit.

---

## ADR-70: Plan Change Is Preview-Then-Execute With Stale-Preview Protection

**Decision.** Changing a plan is two steps. `preview_plan_change` computes the
entitlement diff and over-limit downgrade warnings and returns a **preview
token** fingerprinting the subscription's current state and the target version.
`execute_plan_change` applies the change only if the presented token still
matches — otherwise `StalePreviewError`, because the subscription moved since
the preview and the merchant would be deciding on stale data. Plan selection is
restricted server-side to publicly-selectable published versions, so a merchant
cannot POST an arbitrary or hidden version id.

**Consequences.** A merchant always confirms against an accurate diff. A
concurrent change can't be silently overwritten by an old preview.

---

## ADR-71: SubscriptionEvent Is Immutable Domain History, Alongside (Not Instead Of) the Audit Log

**Decision.** Every subscription transition and plan change records a
`SubscriptionEvent` (from/to status, from/to plan version, actor, reason,
metadata, optional idempotency key) **and** a general audit-log entry. The
event stream is domain history specific to billing lifecycle; the audit log is
the cross-cutting security record. Both are append-only; Django Admin blocks
changing or deleting events.

**Consequences.** Billing history is queryable on its own terms (the merchant
history page) without trawling the global audit log, and neither can be
rewritten.

---

## ADR-72: No Money Moves in 5A — Plan Change Alters Entitlements Only; Payment Is 5B

**Decision.** Checkpoint 5A implements the *shape* of subscriptions —
plans, versions, entitlements, usage, limits, trials, state machine, merchant
visibility, and plan change — but collects **no** money. `change_plan_version`
and `provision_default_subscription` alter entitlements/state only; there is no
gateway integration, no stored card, no automated charge, no webhook. The
`external_reference` field is a reserved, gateway-agnostic string for 5B.
Online payment collection, card storage, automated charging, and webhooks are
explicitly out of scope and deferred to Checkpoint 5B.

**Consequences.** Activation is an administrative/service act in 5A. The
domain is payment-ready (a subscription references an exact priced version)
without any premature coupling to a specific payment provider.

---

## ADR-73: SaaS Billing Is a Separate Domain From Merchant Commerce Payments

**Context (checkpoint 5B).** The platform charges merchants for their
subscription, and separately merchants' customers pay for storefront orders
(`apps.orders`: `PaymentGateway`, `PaymentAttempt`, `Refund`). Conflating the
two would let a customer order masquerade as a subscription invoice and tangle
two unrelated money flows.

**Decision.** A new `apps.billing` app owns SaaS billing end to end
(`StoreBillingAccount`, `SubscriptionInvoice`/`Line`, `SubscriptionPaymentAttempt`,
`BillingWebhookEvent`, `SubscriptionCreditNote`, `SubscriptionRefund`,
`SubscriptionDunningState`, `ScheduledPlanChange`). It never reuses a merchant
`Order`, the storefront `PaymentAttempt`, or the storefront `Refund`. One
`StoreBillingAccount` per store answers who/where is billed; every invoice
freezes a snapshot of it so later edits never rewrite history. All money is
`Decimal` (IRT, `decimal_places=0`, matching `PlanVersion.display_price`).

**Consequences.** The two payment domains evolve independently; a bug or schema
change in one cannot corrupt the other. Platform billing lives only in Django
Admin behind superuser (ADR-8).

---

## ADR-74: Invoice Lifecycle Is Draft → Open → Paid, With Immutable Snapshots and Sequence-Backed Numbering

**Decision.** An invoice is created `draft` (lines mutable), then `open`
(issued, financially immutable), then `paid`/`past_due`/`void`/`uncollectible`/
`refunded`/`partially_refunded`. Totals are always computed from the lines, not
from client input. Each invoice freezes a plan-version snapshot and a
billing-account snapshot at creation. Numbers come from a persistent
`BillingSequence` advanced under `select_for_update` (`INV-YYYY-NNNNNN`) —
never from a table `COUNT(*)`, which repeats under concurrency/retry. DB
constraints enforce unique numbers, non-negative amounts, `amount_paid <=
grand_total`, and one renewal invoice per `(subscription, period)`.

**Consequences.** A finalized invoice's amounts and snapshots never change; the
service refuses to add lines to a non-draft invoice. Numbering is race-safe and
human-readable.

---

## ADR-75: Payments Go Through a Provider-Neutral Interface; the First Provider Is an Honest Manual One

**Decision.** `apps.billing.providers.base.BillingPaymentProvider` defines
`create_payment_session` / `verify_webhook` / `parse_webhook_event` /
`fetch_payment_status` / `refund_payment` with structured result dataclasses.
Provider-specific code lives only behind this interface, resolved via a
registry keyed on `settings.RASTISI_BILLING_PROVIDER`. The default `manual`
provider is deliberately honest: it never fakes a production payment — it does
real HMAC-SHA256 webhook verification and requires either a signed webhook or an
explicit admin action to confirm payment; refunds are manual. A real gateway
plugs in behind the same interface later. Secrets come only from the
environment, never the database or code; raw card data is never stored.

**Consequences.** Swapping or adding a gateway touches one file. No part of the
system pretends a payment succeeded without real confirmation.

---

## ADR-76: Webhooks Land in a Verified, Idempotent Inbox Before Any Business Mutation

**Decision.** Every provider webhook is size-checked, signature-verified, and
timestamp-checked **before** any domain change, then parsed and stored in
`BillingWebhookEvent` (unique on `provider` + `external_event_id`, so duplicate
delivery is idempotent). Payloads are stored with sensitive keys recursively
redacted; raw secrets are never persisted. Invalid-signature or oversized
requests are rejected (400/413) and store nothing. The endpoint is the only
CSRF-exempt billing route — it authenticates by signature, not session. Failed
processing is recorded on the event (visible to platform admin, retriable), and
the endpoint returns 200 for any stored event so the provider does not retry a
recorded business error.

**Consequences.** Replay, tampering, out-of-order, and duplicate deliveries are
all handled safely; nothing an attacker sends mutates billing state without a
valid signature.

---

## ADR-77: Payment Confirmation Is One Transactional, Idempotent Service — Never in the View

**Decision.** `confirmation_service.confirm_payment` is the single path from
"provider says paid" to domain effect. It locks the attempt and invoice,
verifies currency and amount against the invoice (rejecting mismatches), marks
the attempt succeeded once, applies the payment once, marks the invoice paid
when fully covered, and then activates or renews the subscription — all in one
transaction, idempotent against duplicate webhook delivery. The webhook view
merely stores the event and hands off to this service.

**Consequences.** A subscription is activated only after confirmed payment,
never on browser return. Re-delivering the same webhook never double-charges or
double-activates.

---

## ADR-78: Renewal Invoices Are Generated Ahead of Period End, Exactly One Per Period

**Decision.** `generate_subscription_renewals` (cron, no task queue — ADR-49)
finds current non-terminal subscriptions whose period ends within a configurable
lead window (`RASTISI_BILLING_RENEWAL_LEAD_DAYS`), skipping cancel-at-period-end
and none-interval subscriptions, and creates exactly one open renewal invoice
per `(subscription, period)` — idempotent via the DB constraint plus an
existence check. Amount and currency are frozen on the invoice from the current
plan version.

**Consequences.** Renewals are predictable, non-duplicated, and safe to re-run.

---

## ADR-79: Dunning Is a Deterministic Schedule; the Grace → Suspend Escalation Reuses the 5A State Machine

**Decision.** `process_subscription_dunning` (cron) walks a configurable
day-offset schedule (`RASTISI_BILLING_DUNNING_SCHEDULE`, default `0,3,7,14`).
The first stage past-dues the invoice and moves the subscription to grace (the
5A restricted-state UX); the final stage suspends the subscription and marks the
invoice uncollectible. Progression is gated by `next_retry_at` (no stage twice);
paid/void invoices are never dunned. Because the manual provider cannot
auto-charge, dunning keeps an honest `SubscriptionDunningState` "retry-required"
record and exposes the manual payment link, rather than faking a charge.

**Consequences.** Failed renewals degrade access predictably and reversibly;
data is preserved throughout, and a payment at any stage resolves the dunning.

---

## ADR-80: Plan-Change Billing Has No Fake Proration — Upgrade Requires Payment, Downgrade Takes Effect Next Period

**Decision.** No proration is computed. An **upgrade** (higher-priced target)
creates an open plan-change invoice for the target's full amount and does not
switch the plan version until that invoice is fully paid (the switch happens in
`confirm_payment`). A **downgrade** (lower/equal price) is recorded as a
`ScheduledPlanChange` and applied when the next renewal invoice is generated —
no charge, no immediate entitlement reduction. Cancellation voids unpaid
invoices and preserves paid ones, with no automatic refund. The 5A
stale-preview token protection is retained.

**Consequences.** Merchants are never charged an invented prorated amount;
entitlements never become paid-active before payment; downgrades don't strip
access mid-period.

---

## ADR-81: Credit Notes and Refunds Are Distinct — a Document vs. Actual Money Movement

**Decision.** `SubscriptionCreditNote` is a historical document (unique
`CN-YYYY-NNNNNN`, amount ≤ eligible paid amount) that does not by itself move
money. `SubscriptionRefund` moves money through the provider abstraction (never
the storefront-order refund models), bounded by the refundable amount (paid
minus succeeded+open refunds), idempotent, and unable to refund twice. The
manual provider does not auto-confirm, so a refund stays `pending` until an
explicit manual completion, at which point the invoice syncs to `refunded` /
`partially_refunded`.

**Consequences.** Issuing a credit note and actually returning money are
separate, auditable acts; neither can exceed what was paid.

---

## ADR-82: Billing Currency Is Plan-Fixed; Tax Is Off by Default and Not a Compliance Guarantee

**Decision.** The plan version fixes an invoice's currency; a payment attempt
must match it; renewals use the current plan version's currency; there is no
FX conversion in this checkpoint, and a cross-currency plan change requires a
fresh invoice. Historical currency is immutable. Tax fields and snapshots
exist, but SaaS billing tax defaults to zero (`RASTISI_BILLING_TAX_RATE`); when
enabled it is a single flat platform-wide rate, **not** a jurisdiction-derived
VAT engine. The platform makes no automatic legal tax-compliance guarantee.

**Consequences.** Money math stays in one currency per invoice with `Decimal`
precision; tax is honest about its (deliberately minimal) scope.

---

## ADR-83: Tenant-Safe Storefront Routing — Host-Resolved, Fail-Closed, Clean 404 for Unknown/Inactive Stores

**Context (checkpoint 6).** The public storefront serves many stores from one
codebase. A customer request must render exactly the store its Host belongs to,
and never leak another store's catalog — and an unknown, inactive, suspended,
or closed store must degrade gracefully.

**Decision.** Every storefront view resolves its store from the request Host via
`apps.stores.resolution`, which only matches a `StoreDomain` whose store is
`ACTIVE` and whose domain is `VERIFIED` (fail-closed). Checkpoint 6 adds
`resolve_store_for_storefront`, which converts an unresolved Host into a clean
`Http404` instead of the 500 that the service resolver's single-store
compatibility fallback raises when multiple stores exist. Category pages are the
product list filtered on `?category=` (with parent→child expansion), a
deliberate query-param design rather than a separate template tree. The merchant
admin host and Django admin host are resolved by separate functions and are
isolated from the storefront.

**Consequences.** A customer on an inactive/suspended/unknown host sees a normal
not-found page; no request can surface another store's products, and deep
service code still receives a concrete `Store` passed down explicitly.

---

## ADR-84: RTL-First Storefront Design System on Tokens + HTMX + Alpine

**Decision.** The storefront uses one token-based design system
(`core/static/css/tokens.css` + `base.css` + `layout.css`) with per-store brand
CSS variables, RTL-first Persian layout, and the repo's existing HTMX + Alpine
conventions for interactivity — no new frontend framework. Reusable template
partials (product card/grid, forms, empty states) avoid duplicated markup; store
branding is data-driven (never hardcoded), so Store A's look never appears on
Store B.

**Consequences.** A coherent, maintainable storefront that stays consistent with
the merchant-admin conventions and needs no build pipeline.

---

## ADR-85: Variant Selection Is Validated Server-Side; Add-to-Cart Never Trusts the Browser

**Decision.** The browser selects a variant, but the server is authoritative.
`cart_add` resolves the product scoped to the Host store and `ACTIVE`, and the
variant scoped to that product AND `is_active=True` — rejecting cross-store,
cross-product, or inactive variant ids with a 404. Price is resolved server-side
(`product.final_price`), never from POST; quantity is coerced and clamped.

**Consequences.** A forged price, a foreign variant id, or an inactive variant
can never enter a cart; the frontend selector is a convenience, not a trust
boundary.

---

## ADR-86: Variant-Specific Images Fall Back to the Product Gallery, Never a Foreign Image

**Decision.** A variant with a dedicated image shows it; a variant without one
falls back to the product's gallery. The product gallery stays accessible, alt
text is meaningful, and the image never changes to another product's image.
Missing images degrade to a tinted emoji placeholder (`_gallery_slides`).

**Consequences.** Image presentation is always correct and store-safe, with a
graceful fallback at every level.

---

## ADR-87: One Storefront Price Presenter — Server-Owned, Zero-Decimal IRT

**Decision.** Prices are server-owned (`Product.price`/`final_price`, discount
percent) and presented consistently through the shared Persian/`toman`
formatting helpers in zero-decimal IRT. The browser never supplies a price;
cart and checkout re-resolve totals server-side. Compare-at/discount is shown
only when real.

**Consequences.** Consistent price formatting across home, list, detail, cart,
and checkout, with no browser-trusted amounts.

---

## ADR-88: Cart and Checkout Are Idempotent and Server-Revalidated

**Decision.** Checkout submission is idempotent server-side (the existing
`Cart.checkout_token` + `Order.idempotency_key`, checkpoint-era design),
protecting against duplicate clicks and payment retries. Stock and price are
re-validated at cart and checkout against the inventory/pricing services (the
source of truth), and the browser return from payment is treated as
informational only — payment is confirmed server-side.

**Consequences.** No double orders, no stale-price/oversold checkouts, and no
payment "success" inferred from a browser redirect.

---

## ADR-89: Customer Account Isolation — Own Records Only, Store-Scoped Orders

**Decision.** A customer sees only their own records; order lookups are scoped to
the authenticated customer (guessing an order id/code exposes nothing), and an
order is bound to its store so it never appears in another store's context.
Order detail exposes customer-facing fields only — never internal staff notes,
fraud fields, warehouse internals, raw gateway payloads, or audit records.
Customer authentication is separate from merchant-admin authorization.

**Consequences.** Cross-customer and cross-store account access is structurally
impossible; internal data never leaks to the storefront.

---

## ADR-90: Storefront SEO Is Tenant-Scoped to the Request Host

**Decision.** Because `django.contrib.sites` is not installed, sitemap and
robots are request-scoped views (`apps/core/seo.py`) that resolve the store from
the Host: the sitemap lists only that store's home, list, active categories, and
`ACTIVE` (never draft) products plus published CMS pages, on the tenant's own
domain; robots disallows cart/checkout/account/admin and links the same-host
sitemap. Canonical URLs, Open Graph, and JSON-LD (Product with real
price/availability, BreadcrumbList, Organization) use the request Host; private
pages and search/price-filter permutations are `noindex`.

**Consequences.** Structured data reflects real price/stock, canonical URLs use
the tenant domain, and no cross-store URL or draft product is ever exposed to
crawlers.

---

## ADR-91: Theme Settings via Per-Store CSS Variables

**Decision.** Store branding (name, logo, favicon, brand/secondary colors,
header/footer, contact, social, hero, announcement) is driven by existing
per-store settings surfaced as CSS custom properties on the storefront root
element. A missing logo falls back gracefully; historical orders are unaffected
by later theme changes; Store A's branding never renders on Store B. No
drag-and-drop page builder is introduced.

**Consequences.** Merchants restyle safely within bounds, and theming stays a
narrow, data-driven concern.

---

## ADR-92: Browser/E2E Testing Strategy — Service + View Tests First, Playwright When Warranted

**Decision.** The storefront's correctness is guarded primarily by Django
service- and view-level tests (the storefront suites, tenant-isolation, SEO,
cart-security), which run in CI without a browser. Full browser/E2E automation
uses the repo's pre-installed Playwright/Chromium when a real end-to-end pass is
needed, but browser tests never replace the service/view tests, and no driver
binaries, browser profiles, or screenshots are committed. A manual QA checklist
(`STOREFRONT_MANUAL_QA_CHECKLIST.md`) documents the human end-to-end scenarios.

**Consequences.** Fast, deterministic coverage in CI, with browser testing as a
complementary layer rather than a fragile substitute.

---

## ADR-93: Owner Identity Is Email/Password, Structurally Separate From Storefront Customer Identity

**Decision.** The platform ("System A": public site + owner portal) authenticates
Store owners with `User.username = email` (lowercased, validated unique at the
service layer) and Django's ordinary password auth. This is a deliberately
different identifier scheme from `apps.customers.services.auth_service`, which
authenticates storefront customers with `User.username = phone`. No new
`AUTH_USER_MODEL` or parallel user table is introduced — both identities are
plain `django.contrib.auth.User` rows; owners never get a `Customer` profile as
a side effect of registering, and customers never get `is_staff` or a
`StoreMembership` as a side effect of shopping. The two flows share nothing
except the `User` table itself, so a person who happens to use the same phone
number as their email's local part (or otherwise ends up as both an owner and a
customer somewhere) simply has two independent capabilities on the same
underlying account — not a collision, not a bug.

Password reset for owners reuses Django's standard token-based email flow
(`django.contrib.auth.tokens.PasswordResetTokenGenerator`), delivered via
`django.core.mail`. This is intentionally NOT SMS-based: `apps.sms.services.
sms_service.send_event_sms` is Store-scoped by construction (it loads
`ShopSettings.load(store=...)` for per-store templates/branding) and owner
registration/reset happens before any Store exists, or independent of any one
Store — extending Store-scoped SMS infrastructure to a Store-less platform
identity would blur a boundary this codebase otherwise keeps sharp. `EMAIL_
BACKEND` follows the existing environment-driven settings pattern: console
backend in dev/test (visible in logs, never silently "sent"), SMTP via
`DJANGO_EMAIL_*` env vars in production — never a fake "email sent" result.

**Consequences.** Registration/login forms are ordinary email+password, matching
the visual reference. No SMS provider dependency for the owner-identity layer.
Production deployments must configure real SMTP env vars or password reset
mail is only visible in server logs — documented in the local-dev/deployment
docs, not silently broken.

---

## ADR-94: Store Gets a Permanent, Human-Typable 9-Character Platform Code

**Decision.** `Store.platform_code` (new field, `CharField(max_length=9,
unique=True, editable=False)`) is generated once, at provisioning time, from
the alphabet `abcdefghjkmnpqrstuvwxyz23456789` (32 symbols, excludes `0/o/1/l/i`
to avoid visual ambiguity) with collision-checked retry. It is distinct from
both existing identifiers on `Store`:

* `public_id` (UUID4) — opaque, for API/billing/support cross-reference, never
  shown as a hostname;
* `admin_subdomain` — the *merchant admin* host label, independent of any
  public storefront domain (ADR-16), never shown to storefront visitors.

`platform_code` is the seed of the trial storefront hostname
(`{platform_code}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`) and is never reused, reissued,
or shown to a different Store, even after the owner later claims a
human-readable subdomain — it is the one identifier that outlives every
hostname change a Store ever makes (see ADR-95). Existing pre-migration Stores
(the seeded Akhlaghi row) are backfilled deterministically in a data migration,
mirroring the exact 3-step schema/backfill/enforce-not-null pattern
`admin_subdomain` already used (migrations `0003`-`0005`).

**Consequences.** "My Stores" and support tooling can always identify a Store
by one short, typable, collision-free code, independent of whatever hostname(s)
happen to be attached to it today.

---

## ADR-95: `StoreDomain` Gains `domain_type` and `retired_at` — No Second Hostname Table

**Amended by ADR-101** — the field originally shipped here as `is_redirect`
was replaced with `retired_at` before any real caller ever set it; the
description below reflects the current, corrected shape.

**Decision.** Rather than introduce a competing model for
trial/platform/custom hostnames, `StoreDomain` (already the single source of
truth for request-time hostname resolution, ADR-4/ADR-5) gains two fields:

* `domain_type` — `generated_trial` / `platform_subdomain` / `custom_domain`.
  Purely descriptive (what kind of hostname this is, for UI and consistency
  checks); it does not change routing eligibility, which stays exactly
  `domain_is_eligible_for_routing` (Store `ACTIVE` + domain `VERIFIED` +
  not `retired_at`). Platform-issued hostnames (`generated_trial`,
  `platform_subdomain`) are created already `VERIFIED` — Rastisi controls the
  wildcard DNS for its own suffix, so merchant DNS/HTTP verification (ADR-5's
  deliberately unimplemented networking) makes no sense for them; only
  `custom_domain` rows go through the real verification lifecycle (see
  ADR-97/ADR-101 §12).
* `retired_at` — when set, this hostname never resolves again, for anything
  — not storefront content, not a redirect (ADR-101 explicitly overrides the
  original `is_redirect`-forever design below). `domain_is_eligible_for_
  routing` excludes any domain with `retired_at` set, so a retired hostname
  falls through the exact same fail-closed path an unverified/unknown host
  already uses — a clean 404, with no dedicated middleware needed.

Backfilled data migration: every pre-existing `StoreDomain` row defaults to
`domain_type="custom_domain"` (the conservative assumption for hostnames that
predate this whole scheme — treat them as merchant-supplied unless the
platform code proves otherwise) and `retired_at=NULL`.

**Consequences.** One hostname model keeps meaning "the authoritative mapping
from a real HTTP Host to a Store," exactly as ADR-4/ADR-5 established; the new
fields only add descriptive/lifecycle metadata on top.

---

## ADR-96 (SUPERSEDED BY ADR-101): Old Hostnames Become Permanent Redirecting Aliases, Never Reused

**This decision was reversed before any real caller ever exercised it** — see
ADR-101. Kept here, struck through in effect but not in text, as an honest
record of the design this codebase briefly held and why it changed: an
explicit product decision determined that a retired generated trial hostname
must go silently inactive, not redirect (a redirect implicitly confirms to
an outside observer that "this Store used to be reachable here, and is now
reachable at X" — for a temporary internal identifier that was never meant
to be a public, permanent address, that is more information than the
product wants to leak, and it kept the temporary code alive as a
forever-working entry point instead of retiring it).

Original text (no longer the implemented behavior): "When a paying owner
claims a human-readable subdomain (or, later, a custom domain) as their new
primary `StoreDomain`, the previous primary hostname is not deleted and not
detached from the Store — it is kept as a non-primary `StoreDomain` row with
`is_redirect=True`, permanently redirecting ... to the new primary domain
... Because `StoreDomain.hostname` is globally unique, a hostname that ever
belonged to Store A can never be claimed by Store B."

The one part of this ADR that **still holds** under ADR-101: `StoreDomain.
hostname`'s global uniqueness means a retired hostname can never be
reassigned to a different Store either — retirement makes it permanently
inert, not available for reuse.

---

## ADR-97: Platform-Level Hosts Get Their Own URLconf, Not a New Store Concept

**Decision.** Three kinds of platform-owned hosts exist alongside per-Store
hosts, none of which are `StoreDomain`/`admin_subdomain` rows and none of
which go through `StoreResolutionMiddleware`'s per-Store lookup for routing
purposes:

1. the bare marketing + owner-portal host (`rastisi.ir`, `www.rastisi.ir` in
   production; `rastisi.localhost` in local dev) — public site at `/`, owner
   portal at `/app/`;
2. the platform-admin host (`platform.rastisi.ir` / `platform.rastisi.
   localhost`) — staff/superuser-only, no tenant resolution at all;
3. every other host keeps resolving exactly as before (per-Store public
   domain, or `{admin_subdomain}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`).

This is implemented with a new, additive `PlatformHostRoutingMiddleware` that
sets Django's per-request `request.urlconf` (the standard, documented Django
mechanism for host-based URLconf selection) to `shop_core.urls_platform` or
`shop_core.urls_platform_admin` when the Host matches an explicit, configured
allowlist (`RASTISI_PLATFORM_HOSTS` / `RASTISI_PLATFORM_ADMIN_HOSTS`); every
other Host leaves `request.urlconf` untouched, so `ROOT_URLCONF` (the existing
Store-scoped catalog/dashboard routes) keeps handling it exactly as before.
`ALLOWED_HOSTS` gains a single dev-only wildcard entry (`.rastisi.localhost`)
when `DEBUG=True`; production hosts (including the `.rastisi.ir` wildcard)
must be set explicitly via `DJANGO_ALLOWED_HOSTS`, matching how every other
production host value in this codebase is environment-driven, never
hardcoded.

**Consequences.** Zero changes to the existing per-Store URLconf, middleware
order, or any of the ~3000 pre-existing tests; the platform layer is additive
infrastructure that only activates on hosts nothing else has ever claimed.

---

## ADR-98: Merchant-Admin Handoff via a Signed, Single-Use, DB-Backed Ticket

**Decision.** Since `SESSION_COOKIE_DOMAIN` is unset (host-only cookies, by
design — no code in this repo assumes cross-subdomain session sharing), the
owner portal's "Enter Admin" action cannot rely on the browser simply
carrying an existing session cookie from `rastisi.ir`/`app.rastisi.ir` onto a
Store's distinct `{admin_subdomain}.rastisi.ir` host. A new, narrow
`AdminHandoffTicket` model (`apps.portal`) carries: a cryptographically random
token (`secrets.token_urlsafe`), the requesting `user`, the target `store`, a
short (60s) expiry, and a nullable `consumed_at`. Issuing a ticket requires an
active `StoreMembership` for that exact (user, store) pair, checked at issue
time. Consuming it (`GET {admin_subdomain}.../admin-portal/handoff/<token>/`)
is one atomic `select_for_update` read-and-mark-consumed; a ticket already
consumed, expired, or for the wrong store 404s exactly like `staff_required`'s
other fail-closed paths — never a redirect that reveals which case it was.
On success it calls Django's `login()` for that Store's admin host and
redirects into `/admin-portal/`. The existing `staff_required`/`permission_
required` decorators and `StoreMembership` checks are entirely unchanged and
still run on every subsequent admin-portal request — the ticket only bridges
the initial cross-host authentication gap, it is not a new authorization
mechanism.

**Consequences.** No shared-cookie-domain security tradeoff is introduced;
each handoff is single-use and expires quickly even if a URL leaks (e.g. via
browser history or a proxy log).

---

## ADR-99: Trial Store Provisioning Activates Immediately; Onboarding Is a Separate, Optional Follow-Up

**Decision.** `apps.portal.services.provisioning_service.provision_trial_store`
is a single `transaction.atomic` call that takes an owner and a store name
(plus an optional `IndustryTemplate`) and returns a fully `ACTIVE` Store —
not `PROVISIONING` pending a later "activation" step. It creates, in order:
an anti-abuse-capped Store (`RASTISI_MAX_STORES_PER_OWNER`, a platform-wide
safety limit — `apps.subscriptions` has no per-owner store-count
entitlement to reuse), an `ACTIVE` `OWNER` `StoreMembership`, an already-
`VERIFIED` `generated_trial` `StoreDomain` at
`{platform_code}.{RASTISI_ADMIN_DOMAIN_SUFFIX}` (platform-owned DNS, so
real verification networking would be meaningless here — ADR-95), a
`ShopSettings` row, a default `Warehouse`, an optional industry-template
install, and the default subscription (fail-open per ADR-65 if no default
plan is configured). Any failure anywhere rolls back the whole thing —
there is no partially-provisioned Store state a user can ever observe.

The wider program's "onboarding wizard" (Section D: theme, contact info,
preview, ...) is deliberately a *separate*, optional, later flow that
edits an already-live Store — it is not a gate the trial has to pass
through before the storefront becomes reachable. This mirrors the
prototype's own `store-success.html`, which shows the live hostname
immediately after the short setup flow, not after a separate activation
step.

Double-submission protection (Section G) is a per-session, single-use
token rotated the instant a submission is accepted (same shape as
`Cart.checkout_token`/`Order.idempotency_key` elsewhere in this codebase)
— sufficient against back-button/double-click resubmits, not a DB-level
mutex against a truly concurrent double-submit from the same session
(accepted, documented tradeoff: the worst case is an extra Store, not
data corruption or a security issue).

**Consequences.** A new owner goes from "click create" to a real, live,
reachable trial storefront in one request, with no waiting/polling for a
background activation step (this codebase has none — ADR-49) and no way
to observe a half-built Store.

---

## ADR-100: Domain Consistency Verification Mirrors the Existing Consistency-Command Shape

**Decision.** `apps.stores.services.domain_consistency_service.
check_domain_consistency()` / `manage.py verify_domain_consistency
[--strict]` are read-only and return the exact same `{"severity":
"error"|"warning", "message": str}` list shape as `check_subscription_
consistency`, `check_billing_consistency`, and the inventory equivalent —
one consistent pattern for every domain's health-check command, not a
one-off. It checks: duplicate normalized hostnames, a Store missing its
`platform_code`, more than one primary `StoreDomain` per Store, a
`is_redirect` alias whose Store has no primary domain to redirect to
(broken target), a `StoreDomain` hostname whose leftmost label collides
with the new `RESERVED_PLATFORM_SUBDOMAINS` list (Section K's product
decision, `apps.stores.hostnames`), a public `StoreDomain` colliding with
a *different* Store's admin host, and (warning-level) an `ACTIVE` Store
with no `generated_trial` domain at all — expected for every Store that
predates the portal (the seeded Akhlaghi Store), not an error.

`RESERVED_PLATFORM_SUBDOMAINS` (verbatim product-decision list, unioned
with `RESERVED_ADMIN_SUBDOMAINS`) and `normalize_platform_subdomain_
label` are added now, ahead of the paid-subdomain-claim UI itself (Section
J), so the consistency checker and that future UI share one validation
function instead of two independently-maintained copies of the same
reserved-word rule.

**Consequences.** One more read-only, CI-runnable health check, in the
same family as the three that already exist; no write path, no
migration risk.

---

## ADR-101: Retired Trial/Platform Hostnames Go Silently Inactive, Never Redirect (Overrides ADR-96)

**Decision (approved product decision, RASTISI COMPLETE IMPLEMENTATION
spec §3.5).** ADR-96's "old hostname redirects forever" design is reversed
before it ever had a real caller. The corrected lifecycle for a Store's
generated trial hostname (`{platform_code}.{RASTISI_ADMIN_DOMAIN_SUFFIX}`):

* it works normally — full storefront access — for as long as it is the
  Store's `is_primary` domain (during trial/onboarding);
* the moment a paid owner claims a permanent handle (Section 11, a later
  slice) and that new hostname becomes `is_primary`, the trial hostname's
  `StoreDomain` row is marked `retired_at=<now>` and `is_primary=False` in
  the same transaction;
* a retired hostname never serves content and never redirects — requests to
  it fail the exact same `domain_is_eligible_for_routing` check an
  unverified/unknown host already fails, landing on the same clean 404 via
  `resolve_store_for_storefront`. No dedicated middleware is needed for
  this — the corrected `HostnameRedirectMiddleware` (which used to issue
  301/308s) has been **deleted**, not merely disabled, since redirecting is
  now explicitly the wrong behavior, not a config toggle;
* `StoreDomain.hostname`'s global uniqueness constraint still guarantees the
  retired hostname can never be reassigned to a different Store — retirement
  makes it permanently inert, not available for reuse;
* the Store's permanent `platform_code` itself (distinct from the hostname
  built from it, ADR-94) is untouched by retirement — it remains the
  Store's internal, permanent identifier for support/audit purposes forever,
  it is simply no longer exposed as a working public hostname.

Schema change: `StoreDomain.is_redirect` (never used by any real code path)
is removed outright and replaced with `StoreDomain.retired_at` (nullable
`DateTimeField`); `domain_is_eligible_for_routing` gains a third condition
(`retired_at is None`); the `redirect_alias_domain_is_never_primary`
`CheckConstraint` is replaced with an equivalent `retired_domain_is_never_
primary` one over the new field. `verify_domain_consistency` is updated
to check for the state this correction is meant to prevent (an `ACTIVE`
Store with no live primary domain at all, or a retired domain that is
still marked `is_primary`) instead of the now-removed "redirect target
missing" check.

This is also the point where `RASTISI_PLATFORM_ADMIN_HOSTS`' default moves
from `platform.rastisi.ir` to the approved `platformadmins.rastisi.ir`
(spec §3.12/§3.13) — a deliberately less-guessable direct-URL-only host,
never linked from any public page, portal page, or Merchant Admin page.

**Consequences.** A visitor who bookmarks or shares a Store's temporary
trial address before the owner goes fully live loses that link once the
Store activates — an accepted tradeoff of not permanently exposing the
platform-generated identifier as a real address. Section J (paid
human-readable subdomain claim) and Section 11 (permanent handle claim)
must both call the retirement step explicitly when they land; neither is
implemented yet in this slice.

---

## ADR-102: Platform Configuration Singleton, and Owner Identity Becomes Mobile OTP (Shared With Customer Phone Identity by Design)

**Decision (approved product decision, spec §Section 2 and §Section 3).**
Two related additions:

**Platform configuration.** `apps.portal.models.PlatformConfiguration` is a
`pk=1` singleton read through a cached `get_platform_configuration()` (never
queried per-render). It holds every cross-cutting platform tunable the spec
calls for now: default trial days, deletion retention days (180-365
enforced), brand colors, a temporary text brand mark with a real-logo
`ImageField` ready for later use without any template rewrite, support
contact info, a whitelisted step-up-OTP action policy
(`STEP_UP_ACTION_CHOICES` — not every key has an enforcement point wired
yet; that lands with the sections that need it), and default/enabled
payment providers. Editable only via Platform Admin by a superuser, every
change audited through a new `PlatformAuditLogEntry` — deliberately
separate from the existing Store-owned `AuditLogEntry` (ADR-36), which
requires a `store` and stays untouched.

**Owner identity is now mobile OTP, not email+password.** `/register/` and
`/login/` on the owner-portal host now collect a phone number, normalized
via `apps.portal.phone.normalize_iranian_phone` (accepts `09...`,
`+98...`, `0098...`, bare `98...`/`9...`, Persian/Arabic digits), send a
6-digit code (hashed at rest with Django's own password hasher, 2-minute
TTL, 3 requests per phone per 10 minutes, 10 requests per IP per 10
minutes, 5 verify attempts before permanent invalidation, single-use).
Email+password **login** is not deleted: existing email accounts and
platform superusers still sign in through the unified `/login/` (password
tab) and recover via `/reset-password/`. *(Update, owner-registration audit:
anonymous email+password **registration** was removed. `/register-email/` and
`/login-email/` are now pure compatibility redirects to `/register/` and
`/login/`; new Owners are created only through a verified mobile OTP —
`/register/`, or `/login/` → `/signup/complete/`. `register_owner()` remains
an internal service function with no public route.)*

**The shared-identity decision.** `apps.customers.services.auth_service`
already uses `User.username = phone` for storefront customers. Rather than
inventing a second, incompatible phone-identity scheme for owners, an
OTP-verified owner login/register uses the exact same natural key. A
phone number that already belongs to a Customer-linked `User` therefore
resolves to that same `User` row — `apps.portal.services.owner_auth_
service.get_or_create_owner_by_phone` adds an `OwnerProfile` to it rather
than creating a second, orphaned account. This is a deliberate decision,
not an accidental merge (the spec explicitly warns against merging
customer/owner identity "casually"): an OTP-verified phone is at least as
strong a proof of identity as the password a Customer account already
uses, so the same real person simply gains owner capability on the one
account already tied to their verified phone. The `Customer` row itself
(and its Store-scoped `CustomerProfile` history) is never read or modified
by this path. A returning-login call never overwrites an already-set
`OwnerProfile.full_name` with an empty one just because a bare login
(as opposed to registration) didn't collect a name.

Platform-level OTP SMS reuses `apps.sms.services.backends`' existing
provider abstraction (`ConsoleBackend` for dev, `MelipayamakBackend` for
production) through a new, Store-independent selector
(`apps.portal.services.owner_sms_service`) — consistent with ADR-93's
reasoning for why `apps.sms.services.sms_service.send_event_sms` (Store-
scoped) cannot be reused for platform identity.

**Consequences.** The visible primary merchant authentication is now
mobile OTP, matching the approved product decision and the Iran-only
target market (spec §3.18-3.19). Auto-provisioning a trial Store at
registration (spec §3.1, "onboarding mode C") landed in the very next
slice — see ADR-103.

---

## ADR-103: Registration Auto-Provisions One Trial Store; Publication State Is Computed, Not a New Status Field

**Decision (approved product decision, spec §3.1 "onboarding mode C" and
§Section 6).** Two tightly-coupled additions:

**Auto-provisioning at registration.** The first time `get_or_create_
owner_by_phone` returns `created=True` (a brand-new phone, whether reached
via `/register/` or `/login/` — they converge on the same OTP-verify step,
ADR-102), the OTP-verify view immediately calls `provisioning_service.
provision_trial_store(owner=user, name="فروشگاه من")` and redirects into
`/app/stores/<id>/onboarding/` — never straight to an empty My Stores
page. A registration that fails to provision (should not happen under
normal operation, since a fresh owner is always under
`RASTISI_MAX_STORES_PER_OWNER`) degrades gracefully to My Stores rather
than blocking login.

**One authoritative publication-state service, no new Store status
field.** `apps.stores.services.publication_service.get_store_publication_
state(store)` computes one of `onboarding` / `trial_private` /
`trial_public` / `active_paid` / `restricted` / `suspended` / `inactive`
purely from existing signals: `Store.status`, the new `Store.onboarding_
completed_at` (nullable — the *only* new field this ADR adds, since
"has initial setup finished" is not represented by anything that already
exists), and the existing Checkpoint-5A `get_subscription_access_state`.
Explicitly does **not** duplicate `StoreSubscription.status` or invent a
second state machine — this is a read-only projection over the existing
ones, matching the spec's own instruction to avoid "conflicting
duplicated status fields."

A Store with **no subscription at all** always resolves to `active_paid`
(publicly visible) regardless of `onboarding_completed_at` — deliberately
fail-open. `onboarding_completed_at` is only ever set by the provisioning/
onboarding flow itself; gating on it for a Store that never went through
that flow (every ad hoc `Store.objects.create(...)` throughout the ~3000-
test pre-existing suite, and any legacy Store) would have silently
restricted all of them the moment this field shipped — the exact failure
ADR-65 already forbids for entitlements. `Store.onboarding_completed_at`
is backfilled to `created_at` for every pre-existing row for the same
reason.

**Wiring into routing.** `apps.stores.resolution.resolve_store_for_
storefront` (Checkpoint 6's canonical public-storefront entry point) now
raises `django.core.exceptions.PermissionDenied` — not `Http404` — when a
resolved, real Store is not currently publicly visible. Django's own
`handler403` already renders `templates/403.html`; that template now
branches on the exception message to show trial/restricted-specific
copy and a link into the owner portal, instead of the generic "access
denied" text, while leaving the generic 403 path (used by unrelated
`PermissionDenied`s elsewhere) untouched. This intentionally only gates
the small set of canonical storefront-entry views that already call
`resolve_store_for_storefront` (home/list/detail/search, plus SEO); cart/
checkout/account views reached only after already being on a resolved
product page are not separately re-gated in this slice.

**Consequences.** A newly registered owner goes straight from OTP
verification to naming their one auto-provisioned Store, and that Store's
public storefront correctly stays invisible to anonymous visitors until
they finish that one required step — with zero regression risk to the
pre-existing test suite's many ad hoc, subscription-less Stores.

---

## ADR-104: Four Seeded Plans via an Idempotent Command, Never Overwriting a Customized Version

**Decision (approved product decision, spec §Section 7).**
`manage.py seed_default_plans` creates the four approved starting Plans
(`trial`/`basic`/`professional`/`enterprise`, Persian public titles
آزمایشی/پایه/حرفه‌ای/سازمانی) using the existing `Plan`/`PlanVersion`/
`EntitlementDefinition`/`PlanEntitlement` machinery — no new models. Real
entitlement keys only (`catalog.products`, `staff.members`, `inventory.
warehouses`, `customers.segments`, `domains.custom`, `reports.advanced`,
`catalog.import`/`export`) — never an invented one.

Idempotency has two independent layers, both required by the spec's "do
not overwrite customized Plans on repeated execution":
`Plan.objects.get_or_create` (a re-run never touches an existing Plan's
other fields — `defaults` only apply on the `CREATE` branch), and — more
importantly — **a Plan that already has any `PlanVersion` at all never
gets a second one seeded**. This is a direct consequence of ADR-63
(published-version immutability): if a superuser edits a seeded plan's
price/entitlements later (via a new version, through the existing
`plan_service.create_plan_version`/publish flow — no new Platform Admin
UI for this ships in this slice), re-running the seed command must never
create a competing version or resurrect the original numbers.

The `trial` plan's `trial_days` is read from `PlatformConfiguration.
default_trial_days` (ADR-102/Section 2) at seed time — not a hardcoded
`30` — satisfying the spec's explicit "do not scatter the number 30
across the codebase." `RASTISI_DEFAULT_PLAN_CODE` (existing 5A setting)
is deliberately **not** changed to `"trial"` by this command or by
default: flipping that env var is what actually makes `provision_
default_subscription` start assigning real subscriptions to every new
Store, and doing that unconditionally would change behavior for the
~3000 pre-existing tests that assume a bare `Store.objects.create(...)`
has no subscription. This stays an explicit, documented deployment
decision (`.env`/`DJANGO_...`), exactly like every other production-only
setting in this codebase — tested directly via `override_settings` in
`test_full_chain_with_real_default_plan_configured` instead.

**Consequences.** The full trial→restricted→public chain (ADR-103) is now
genuinely exercisable end-to-end once a deployment sets `RASTISI_DEFAULT_
PLAN_CODE=trial` after running this command; until then, the codebase's
existing fail-open behavior (ADR-65/ADR-103) is exactly preserved.

---

## ADR-105: Portal Subscription Purchase (Section 8/9) Duplicated the Pre-Existing `apps.billing` Domain — Documented, Not Silently Reconciled

**This is a mistake record, not a design decision** — written the moment
the duplication was discovered (mid-Section-14), because hiding it would
violate the explicit "do not hide partial implementation" instruction
this whole build has operated under.

**What happened.** Sections 8/9 (this same build phase, committed before
this ADR) added `apps.subscriptions.models.PlatformInvoice` /
`PlatformPaymentAttempt`, `apps.subscriptions.services.billing_service`,
and `apps.subscriptions.services.payment_providers` (a `"dev"` provider) —
a complete, independent, tested invoice → payment-attempt → activation
pipeline, reachable from a new portal purchase flow
(`/app/stores/<id>/billing/...`). Sections 10 (step-up OTP), 11 (permanent
handle claim), and 12 (custom domain activation) were then built on top of
it, gating on `StoreSubscription.status == ACTIVE` and, for Section 10
specifically, on `billing_checkout`'s own step-up wiring.

**The problem.** A full `apps.billing` domain already existed before this
build phase (Checkpoint 5B, ADR-73 through ADR-82): `StoreBillingAccount`,
`SubscriptionInvoice`/`Line` (draft→open→paid lifecycle, immutable
snapshots, sequence-backed numbering — ADR-74), `SubscriptionPaymentAttempt`,
a provider-neutral interface with an honest `manual` provider (ADR-75),
a verified webhook inbox (ADR-76), one idempotent confirmation service
(ADR-77), renewal invoices (ADR-78), dunning (ADR-79), and — the one that
matters most here — `apps.billing.services.plan_change_billing_service.
start_plan_change`, which already creates a real, open `SubscriptionInvoice`
for a plan upgrade and hands it to `payment_flow_service.start_payment`
for a redirect-based payment session. All of this is already wired into
real, working, `staff_required`-gated Merchant Admin views in
`apps.dashboard` (`billing-overview`, `billing-invoices`, `billing-pay`,
`billing-payment-result`, `billing-cancel`) — just never into the owner's
account **portal** (`apps.portal`), and never with a "buy this plan for
the first time" self-service entry point, since existing invoices are
otherwise only created by the renewal/plan-change jobs, not a merchant
clicking "purchase."

Section 9's own spec line — "portal subscription purchase wired to
**existing** billing" — was, in hindsight, an instruction to add exactly
that missing self-service entry point on top of `apps.billing`'s existing
`plan_change_billing_service`/`payment_flow_service`, plus a genuine new
`"dev"` provider implementing `apps.billing.providers.base.
BillingPaymentProvider` for instant self-serve pay/fail in
development/test (something that did **not** already exist — the existing
`manual` provider deliberately requires a real admin action to confirm,
per ADR-75, so it does not by itself satisfy §3.10's "dev/test provider"
requirement). Instead, Sections 8/9 built a second, parallel invoice/
payment-attempt/provider stack from scratch, unaware `apps.billing`
existed, because nothing surfaced it during that slice's own
"inspect existing code" step.

**Why this was not reverted/rewritten once discovered.** By the time this
was found, Sections 10, 11, and 12 already depended on the new
`billing_checkout` view and its step-up wiring, all shipped, tested, and
pushed. A same-session rewrite of a financially-sensitive purchase flow,
done hastily to hit a deadline, is exactly the kind of rushed change the
"implement sensitive functionality more carefully, not abandoned" and
"do not hide partial implementation" instructions both warn against —
ripping it out under time pressure risked replacing one incomplete state
with a differently-broken one, with less time left to test it. Severity
is bounded, not critical: neither system moves real money yet (only a
`manual` provider requiring human confirmation on one side, and a
`"dev"` fake-pay provider on the other) — both ultimately drive the same
`apps.subscriptions.services.subscription_service` state machine, so
`StoreSubscription.status` (what Sections 11/12's paid-gate checks) stays
correct either way. What is genuinely wrong is bookkeeping fragmentation:
a Store's billing history can now be split across `apps.billing.
SubscriptionInvoice` and `apps.subscriptions.PlatformInvoice` depending on
which path was used, and Platform Admin/Django Admin surfaces both as if
they were independent stores of truth.

**Decision.** Leave both systems in place for now, exactly as built;
do not silently merge or delete either. This ADR is the flag. The correct
follow-up (not done in this build phase) is: retire `PlatformInvoice`/
`PlatformPaymentAttempt`/`billing_service`/`payment_providers`, move the
portal's `/billing/` views onto `plan_change_billing_service.
start_plan_change` + `payment_flow_service.start_payment`, add a real
`"dev"` `BillingPaymentProvider` implementation to `apps.billing.
providers` for instant self-serve pay/fail in non-production environments,
and re-point Section 10's step-up wiring at that flow instead. This is
explicitly called out again in the final build report as a live piece of
architectural debt, not resolved here.

**Consequences.** Two independent billing histories exist per Store until
the follow-up above lands. `StoreSubscription` activation itself is not
at risk (both paths route through the same state machine), but any
future Platform Admin billing report must union both invoice tables, not
just one, until they're reconciled.

---

## ADR-106: ADR-105's Duplication Resolved — `apps.billing` Is Now the Portal's Only Billing System

**Status update, not a new decision** — this is the follow-up ADR-105
explicitly deferred, carried out as a dedicated technical-consolidation
pass once the portal's own core journeys (Sections 10-19) no longer
depended on same-session churn to the purchase flow.

**What changed.** `apps.subscriptions.models.PlatformInvoice`/
`PlatformPaymentAttempt`, `apps.subscriptions.services.billing_service`,
and `apps.subscriptions.services.payment_providers` are deleted outright
(migration `subscriptions.0006_remove_platform_invoice_and_attempt`; zero
rows existed in any environment, so no data migration was needed). The
portal's `/app/stores/<id>/billing/...` views
(`apps.portal.views.billing_plans`/`billing_checkout`/
`billing_step_up_verify`/`billing_return`) now call
`apps.billing.services.plan_change_billing_service.start_plan_change` and
`apps.billing.services.payment_flow_service.start_payment` directly —
exactly the same services `apps.dashboard`'s Merchant Admin billing views
already used. A Store's very first paid purchase is modeled as an
"upgrade" out of its free trial `PlanVersion`, the same mechanism Merchant
Admin plan changes use for any other upgrade.

**One real gap this surfaced and fixed in `apps.billing` itself.**
`confirmation_service._activate_or_renew`'s `PLAN_CHANGE` branch only ever
called `subscription_service.change_plan_version` — which changes
`plan_version` but never touches `status` — because every existing test/
caller of `plan_change_billing_service` assumed an already-`ACTIVE`
subscription changing between two paid plans. Section 8/9's own
now-deleted `billing_service.confirm_payment_attempt` had independently
special-cased exactly this ("if the subscription is still
`PENDING`/`TRIALING`, activate it too") to make its own parallel system
work for a trial-to-paid conversion — which is exactly what exposed that
`plan_change_billing_service`, as it stood, could not have supported the
portal's core purchase journey at all. Fixed by extending that same branch
to also call `subscription_service.activate_subscription` when the
subscription is still `PENDING`/`TRIALING` (a distinct idempotency key is
used for the two calls, since `SubscriptionEvent` enforces a
`(subscription, idempotency_key)` uniqueness constraint that would
otherwise collide). Covered by a new focused test,
`apps.billing.tests.test_plan_change_billing.
TrialToPaidUpgradeBillingTests`.

**Deliberate deviation from ADR-105's suggested follow-up.** ADR-105
proposed adding "a real `dev` `BillingPaymentProvider` implementation ...
for instant self-serve pay/fail" as part of the eventual fix. That was
*not* built. On inspection, the existing `manual` provider
(`apps.billing.providers.manual.ManualProvider`) is a deliberate, honest
design (ADR-75): it never auto-succeeds, and confirmation only ever comes
from a signed provider webhook or an explicit Platform Admin action.
Adding a second, weaker, auto-succeeding provider just for the portal
would have reintroduced a parallel, less-secure confirmation path —
precisely the kind of duplication this consolidation pass exists to
remove, not add back under a different name. The portal's checkout flow
now creates the invoice/attempt and shows accurate pending/paid/failed
state (read from the server record, never the browser's own return, per
`payment_flow_service`'s existing contract); completing a purchase in a
non-production environment without a real gateway means posting a signed
webhook to the existing `apps.billing:webhook` endpoint — exactly what
`apps.billing`'s own `WebhookToActivationTests` and the portal's
`test_billing_views.BillingWebhookConfirmationViewTests`/
`test_end_to_end_journeys.JourneyATestCase` now do. This is a real,
narrower capability than Section 8/9's fake bank page offered (no
one-click "pay" button in the portal UI itself), disclosed here rather
than hidden.

**What did not change.** `apps.dashboard`'s Merchant Admin billing views
are untouched — they were never part of the duplication. `StoreSubscription`
correctness was never at risk in either direction; this pass only
collapses two billing-history bookkeeping paths into one.

**Consequences.** Exactly one invoice model (`SubscriptionInvoice`), one
payment-attempt model (`SubscriptionPaymentAttempt`), one payment-provider
abstraction, and one webhook endpoint now exist for the whole platform.
Platform Admin's store-detail invoice list (`apps.portal.
platform_admin_views.store_detail`) reads `store.subscription_invoices`
(the `apps.billing` related name) instead of the now-deleted
`store.platform_invoices`.

---


## ADR-107: New Owners Must Explicitly Accept a Versioned Terms Document — Durable `OwnerTermsAcceptance`, Bound to the Server-Side OTP Session

**Decision.** `apps.portal.terms.CURRENT_TERMS_VERSION` (currently `2026-10-v1`) is the single source of the
Terms version: shown on `/terms/`, rendered on `/register/` and `/signup/complete/`, and stored on every
acceptance. `/register/` and `/signup/complete/` require a checkbox (`accept_terms`, only the exact value `"1"`
counts) validated server-side; unchecked ⇒ no OTP, no challenge, no `User`/`OwnerProfile`/Store. For
`/register/` the accepted version is written into the server-side OTP session
(`portal_otp_accepted_terms_version`) — `/verify/` never reads a version from the client and fails closed (clears
state, redirects to `/register/`, burns no OTP) if it is missing or no longer the current version.
`OwnerTermsAcceptance(user, terms_version, accepted_at, source)` (unique on `(user, terms_version)`) is written
inside `resolve_owner_identity_by_phone`'s transaction **only for the request that really creates the
`OwnerProfile`** (`get_or_create` ⇒ idempotent under replay/races; rolled back with the Owner on failure).

**Not done (by design).** Existing owners are not blocked and no acceptance is fabricated for them; a
re-acceptance workflow for a future Terms version is a separate task. No IP/User-Agent is collected.


**Addendum — registration credentials + server-authoritative OTP resend.**
*Credentials.* A brand-new Owner is created only after OTP verification **and** a required «اطلاعات حساب» step
(`/signup/complete/`, `OwnerAccountCompletionForm`): email + password + confirmation. `/register/` (Terms + name + phone → OTP) and
`/login/` with an unknown phone converge on that one step. Email is required, trimmed, lower-cased, validated, max 254 chars, and
protected case-insensitively (`iexact`) against every other user under the `owner_account_email:` advisory lock. The password goes
through `AUTH_PASSWORD_VALIDATORS` (Persian messages) and is hashed only when the Owner is created — it is never put in the session,
a pending row, a log, a URL, a hidden field or client storage. The OTP proof (`_SIGNUP_PENDING_KEY`, 600 s, server-side) survives
validation errors so a typo never forces a new SMS. No User / OwnerProfile / Store / Terms row exists before the step succeeds, and
the Terms contract (server-bound version, explicit checkbox, one transaction) is unchanged. A phone that already belongs to a shared
User (e.g. a storefront customer) keeps its usable password and existing email: only missing credentials are filled in, and an email
owned by another user is rejected, never reassigned. Existing-Owner OTP login is unchanged. No email-verification flow is added.
*Resend.* The cooldown is `RESEND_COOLDOWN_SECONDS = 120` — ONE constant, independent of the code's validity (`OTP_TTL_SECONDS`, whose
default happens to be the same) — enforced by the server per (phone, purpose). **Anchor: the moment the server accepts the request**
(`OwnerOtpChallenge.created_at`, created under the advisory lock before any SMS is sent); never the browser click, provider completion,
activation, `expires_at` or `updated_at`. T=0 accept, T=15 provider answers ⇒ resend at T=120 (not 135); a delivered code may outlive
the countdown by the provider latency, which is intended. It is checked first outside and again inside the lock (`OtpCooldownError`,
an `OtpRateLimitError`), so a forged POST, a second tab or a concurrent request cannot bypass it (at most one accepted send per window);
`resend_timing()` is the only source of the UI countdown (no second literal in view/template/JS). The window limits SEND REQUESTS, so a
successful verification/consumption does **not** release it early (`consumed_at` plays no part in the decision), for every purpose.
*State transition.* Accepted request → row with `expires_at = PENDING_EXPIRES_AT` (cooldown + per-phone quota start at `created_at`;
never verifiable) → on delivery success `expires_at = now + OTP_TTL_SECONDS` (active; `created_at` unchanged) → on delivery failure, a
provider exception or an activation error the row is **kept** as the never-verifiable pending marker, so the 120 s window is not
silently reset and a failing provider cannot be hammered (a failed request still counts toward the 3-per-10-minute phone budget; the
old still-valid code is untouched). A request rejected before issuance (validation, IP/phone budget, cooldown) creates no row and no
cooldown. No migration. The password-reset flow judges its session countdown from the same acceptance moment and renders the same
`cooldown_seconds` metadata (enumeration-safe: known and unknown phones render the same page).

## ADR-108: Owner Onboarding Chooses a Ready Template (the ONE 50-template catalog), Applied by Storefront Builder Services, and Final Publish Publishes the Storefront Draft

**Decision.** Onboarding has five steps (معرفی · صنف · قالب فروشگاه · برند · بازبینی); `Store.OnboardingStage.TEMPLATE`
is new (choices-only migration `stores/0019`, no data change). The Template step is **required** (no skip) and lists exactly
`layout_preset_registry.list_ready_templates()` through the shared read-only `ready_template_card_service` (extracted from
`storefront_builder.views`, which re-exports it) — one catalog, one thumbnail authority (`template_preview_service`).
A POST carries only `template_key`; the version is always the current registry version. Application is orchestrated by
`storefront_builder.services.store_template_service.select_ready_template`: an untouched first bootstrap Draft gets
`preset_service.apply_preset` (the exact template, no hybrid with legacy content); any other state goes through
`r4_mutation_service.switch_template_current` (preservation-first). The portal contains no section/provenance/baseline logic.
Final onboarding Publish (`portal.services.onboarding_publish_service.complete_onboarding`) is one transaction under a Store row lock:
require an applied Ready Template (read from the real layout provenance), publish the Draft via `layout_service.publish`, then set
`onboarding_completed_at`/`DONE`; any failure rolls everything back (still private/incomplete); an already-completed Store is a no-op.

**Compatibility.** Completed Stores are never sent back; an unpublished Store at branding/review with no applied template is routed
through the Template step by the dispatcher (stored progress untouched); nothing is auto-applied. **Not done:** industry→template
recommendations (no authoritative mapping exists), live iframe previews (Merchant Admin preview is staff/host-bound).

**Pre-publish privacy (hardening).** A Store created by the modern portal provisioning flow is never public before the final Publish,
regardless of subscription/billing configuration. The durable modern-vs-legacy signal is the new nullable
`Store.onboarding_required_at` (migration `stores/0020`, schema only — existing rows stay NULL, no backfill), set only by
`provisioning_service.provision_trial_store` at creation. `publication_service.get_store_publication_state` returns `TRIAL_PRIVATE`
when it is set and `onboarding_completed_at` is NULL, **before** the ADR-65 `AccessState.NONE` fail-open (a genuinely restricted/expired
subscription is still reported as `RESTRICTED`). After Publish the normal policy applies unchanged. Legacy/ad-hoc Stores (no signal) are untouched.

**Historical template UX.** A gallery card is selected/current only when BOTH key and version match the applied template. A Store on a
historical version (key X, v2) shows an informational «قالب فعلی شما» panel and an «ادامه با همین قالب» (`action=keep_current`) form;
`keep_current` is accepted only when `store_template_service.get_applied_template` is not None, mutates nothing in the Storefront (only
`onboarding_stage` advances), and the upgrade to the latest version happens only when the owner explicitly selects that card.

**Delivered-storefront fidelity (ADR-108 addendum).** The Ready Template is applied/published exactly; a new Store is simply empty, so
the data-driven composition (hero slides, category rail, product rows) disappeared and canonical previews (captured from the populated
Rasti Mode Demo store) were not labelled as sample content. Resolution: non-persistent first-run structural placeholders on the public
home of modern-portal Stores with no listable product (`first_run_placeholder_service`, tokens-only, never creates records), truthful
"sample content" labelling, and an unmistakable explicit select/apply UX. Investigation: `ONBOARDING_TEMPLATE_FIDELITY_INVESTIGATION.md`.

**Industry step UX and onboarding density (ADR-108 addendum).** The «صنف» step is one flow: a 4/3/2/1-column card grid (icon, name,
sector, short authoritative description, category count) with search + sector chips, a strong selected state, and ONE compact
confirmation («صنف انتخاب‌شده: …», «این صنف را برای فروشگاهم نصب کن») next to the CTA in a footer that is sticky only on wide screens.
The split master/detail layout, sticky preview and category/attribute dump (and `_template_preview.html`, used only by this step) are
removed; the server still requires the exact value `"1"` and installs once. Vertical density: compact header (53 px), one-row
title + stepper on desktop, 16 px page padding, tighter card/head/actions rhythm — no `translateY`, negative margins or fixed heights;
mobile (≤720 px) keeps a current-step summary and every label for assistive tech. *First-run placeholders* now judge readiness per
section: hero/category placeholders apply only while the storefront is still the as-delivered composition, and product rows only
while no product is listable — adding a first product no longer collapses the hero/categories, and a deliberate edit ends them.

## Summary Table

| Decision | Status |
|---|---|
| Store is separate from Vendor | Decided |
| Vendor final meaning | Deferred to catalog-domain PR |
| Store ownership via StoreMembership only | Decided |
| Store has one explicit status field | Decided |
| StoreDomain stores normalized hostnames | Decided |
| At most one primary domain per Store | Decided (DB-enforced) |
| Customer direction: global identity + Store profile | Decided, implemented (`CustomerProfile`, checkpoint 4, ADR-50) |
| PaymentProvider vs StorePaymentConfiguration split | Recorded, not implemented |
| Platform operators ≠ unrestricted merchant-data access | Recorded, not enforced |
| Merchant funds flow directly to merchant accounts (v1) | Recorded |
| Store is aggregate root; no generic StoreConfiguration table | Decided |
| Store resolution is hostname-authoritative, fail-closed compatibility fallback | Decided, implemented |
| ShopSettings/FooterSettings: OneToOneField per Store; trust badges/payment logos: direct Store FK | Decided, implemented |
| Tenant-sensitive services resolve Store once at the boundary, never re-derive it deeper | Decided, implemented |
| `Order` gets a direct `store` FK (redundant, PROTECT) alongside `vendor` | Decided, implemented |
| Checkout idempotency via server-held `Cart.checkout_token` + `Order.idempotency_key` | Decided, implemented |
| `Store.admin_subdomain` is a platform-assigned field, independent of `StoreDomain` | Decided, implemented |
| `/admin-portal/` is the canonical Merchant Admin Portal route; `/admin-panel/` is a temporary 302 redirect | Decided, implemented |
| Admin-subdomain-only enforcement (block public storefront domains from serving the admin portal) | Decided, implemented |
| Variant-specific product images via `ProductImage.variant` (nullable FK, `SET_NULL`) | Decided, implemented |
| Descriptive `Attribute` and variant-generating `ProductOption` are separate models sharing one optional `Attribute` definition | Decided, implemented |
| Variant combination identity is `VariantOptionValue` + derived `combination_key`, not display strings | Decided, implemented |
| Variant reconciliation never hard-deletes; obsolete combinations are marked, axis removal requires explicit regeneration | Decided, implemented |
| Industry templates are platform-owned/read-only; installation deep-copies into Store-owned records, no live template FK | Decided, implemented |
| Category Attribute schema inheritance: direct mapping always wins, opt-out is per-mapping not per-category | Decided, implemented |
| Category change never deletes `ProductAttributeValue`; orphaned values are computed on demand, cleanup is explicit | Decided, implemented |
| Industry template versions are immutable snapshots; a Store may install at most one template, ever (no auto-update) | Decided, implemented |
| Industry template quality is a structured, reusable validation service, not a vanity score | Decided, implemented |
| Template versioning stays on `IndustryTemplate.(slug, version)`; no separate version-family model | Decided, implemented |
| Store customization detection compares live fields against the immutable source template; no snapshot table | Decided, implemented |
| Template updates: additive changes auto-apply by default, everything else requires explicit review or is blocked | Decided, implemented |
| Staff management grants immediate ACTIVE access on add; token-based invitation acceptance is out of scope | Decided, implemented |
| Inventory is an append-only `StockMovement` ledger; order stock mutation targets variant stock when a variant is ordered, and cancellation restocks | Decided, implemented |
| Coupon is Store-owned; code uniqueness is per-Store, not global | Decided, implemented |
| Refund amounts computed from immutable Order snapshot; only manual refund execution is real, gateway execution honestly rejected | Decided, implemented |
| Return requests get their own explicit state machine, separate from Order.status | Decided, implemented |
| Order financial/return state is derived from Refund/ReturnRequest rows, never folded into Order.status | Decided, implemented |
| Audit log is Store-scoped, redacts secrets at write time, deliberately omits IP/User-Agent (no privacy policy backs it) | Decided, implemented |
| Warehouse provisioning is an explicit, idempotent service call, never a Django signal | Decided, implemented |
| `Product`/`ProductVariant.stock` remains the sole authoritative sellable-stock field; `WarehouseInventory` is a synced per-warehouse breakdown | Decided, implemented |
| Inventory reservation reduces computed "available", never stored `on_hand`; reserved and consumed synchronously within order creation, not held across requests | Decided, implemented |
| Warehouse transfers move only the per-warehouse breakdown; the aggregate `Product`/`ProductVariant.stock` is untouched by an internal transfer | Decided, implemented |
| Shipping Zones match only province/city/postal code (no invented country tier); deterministic postal > city > province > fallback precedence | Decided, implemented |
| Shipping Rate Rules select by priority, then specificity, then primary key; fall back to legacy flat `ShippingMethod.cost` when no rule matches | Decided, implemented |
| Checkout always re-validates the shipping method against the Store/zone at Order-creation time, not only at selection time | Decided, implemented |
| Tax configuration lives on `ShopSettings`; `tax_enabled` defaults `True` to match pre-checkpoint always-on flat-tax behavior | Decided, implemented |
| Tax falls back to the flat rate only when a Store has zero `TaxRate` rows at all; once any exist, an uncovered line is zero-taxed, not flat-rated | Decided, implemented |
| Tax rounding is a per-Store `on_total`/`per_line` policy, defaulting to `on_total` to match the legacy formula exactly | Decided, implemented |
| Order/OrderItem shipping and tax fields are independent snapshots, never live references to mutable Shipping/Tax rows | Decided, implemented |
| Return/refund restock warehouse: explicit merchant choice, then the item's original fulfillment warehouse, then the Store default | Decided, implemented |
| Export/Import jobs execute synchronously in-request; no background task queue exists in this codebase | Decided, implemented |
| Customer export computes order count/total spent from Store-filtered Orders, never `Customer.orders_count`/`total_spent` | Decided, implemented |
| CSV injection protection is one shared utility (`sanitize_csv_cell`), applied at write time to every export cell | Decided, implemented |
| Export files are private (`PRIVATE_MEDIA_ROOT`), time-limited (7-day `expires_at`), and served only through an authenticated Store-scoped download view | Decided, implemented |
| Customer Segment rules are an allowlisted field/operator registry; each rule is an independent Store-scoped query combined by ID-set algebra, never a multi-annotate join | Decided, implemented |
| Dynamic segment preview is always a live query; materialized `CustomerSegmentMembership` is a separate cache written only by explicit refresh (button or management command) | Decided, implemented |
| CSV Import (Product/Variant/Inventory) is explicitly deferred out of checkpoint 4 — no model, no service, no UI | Superseded by checkpoint 4B (ADR-55+) |
| Import job lifecycle: upload → synchronous dry-run preview → explicit execute, all in-request (no task queue) | Decided, implemented |
| Import executes per-batch-atomic with row-level results; preview and execute share one validation path | Decided, implemented |
| Import stable identity: Store-scoped ID then Store-scoped SKU, never name/slug; cross-Store IDs hard-rejected | Decided, implemented |
| Product Import writes only through the existing service/model layer; stock always via the inventory service | Decided, implemented |
| Variant Import drives the existing Variant Engine; combinations materialized by generate_variants, never hand-built | Decided, implemented |
| Inventory Import routes every row through a warehouse-aware inventory service call enforcing reservation safety | Decided, implemented |
| Import idempotency: optional per-Store key at upload + final-status guard at execute | Decided, implemented |
| Import files are private, filename-sanitized, size/row/field-bounded, and retention-cleaned like exports | Decided, implemented |
| A Plan is a stable code; priced/functional terms live on immutable published PlanVersions (server-enforced immutability, superuser-only admin) | Decided, implemented (5A, ADR-63) |
| Entitlements are the single source of truth, keyed on stable keys — never `plan.code == "pro"` | Decided, implemented (5A, ADR-64) |
| Fail-open fallback + Legacy grandfathering: existing stores are never silently restricted or assigned a limited Starter plan | Decided, implemented (5A, ADR-65) |
| One explicit subscription state machine; no view writes `status` directly; one current subscription per store (DB-enforced) | Decided, implemented (5A, ADR-66) |
| One trial per store; a plan change never resets the trial | Decided, implemented (5A, ADR-67) |
| Usage is live counts for resources, calendar-month period counters for actions; over-limit data stays readable | Decided, implemented (5A, ADR-68) |
| Limits enforced in the service layer so imports/bulk/direct-POST cannot bypass; only creation gated, no silent truncation | Decided, implemented (5A, ADR-69) |
| Plan change is preview-then-execute with stale-preview token protection; selection restricted to publicly-selectable published versions | Decided, implemented (5A, ADR-70) |
| SubscriptionEvent is immutable domain history, alongside (not instead of) the audit log | Decided, implemented (5A, ADR-71) |
| No money moves in 5A — plan change alters entitlements only; online payment/cards/charging/webhooks are deferred to 5B | Decided, implemented (5A, ADR-72) |
| SaaS billing is a separate domain (apps.billing) — never reuses merchant Order/PaymentAttempt/Refund | Decided, implemented (5B, ADR-73) |
| Invoice lifecycle draft→open→paid with immutable snapshots; sequence-backed race-safe numbering | Decided, implemented (5B, ADR-74) |
| Provider-neutral payment interface; first provider is an honest manual one that never fakes success | Decided, implemented (5B, ADR-75) |
| Webhooks land in a verified, idempotent inbox (size/signature/timestamp) before any business mutation; redacted payloads | Decided, implemented (5B, ADR-76) |
| Payment confirmation is one transactional, idempotent service — never in the view; activation only after confirmed payment | Decided, implemented (5B, ADR-77) |
| Renewal invoices generated ahead of period end, exactly one per period, idempotent | Decided, implemented (5B, ADR-78) |
| Dunning is a deterministic schedule; grace→suspend reuses the 5A state machine; no faked auto-charge on the manual provider | Decided, implemented (5B, ADR-79) |
| Plan-change billing has no fake proration — upgrade requires payment, downgrade effective next period | Decided, implemented (5B, ADR-80) |
| Credit Notes (document) are distinct from Refunds (money movement via provider abstraction); both bounded by paid amount | Decided, implemented (5B, ADR-81) |
| Billing currency is plan-fixed (no FX); tax off by default and not a legal compliance guarantee | Decided, implemented (5B, ADR-82) |
| Tenant-safe storefront routing — Host-resolved, fail-closed, clean 404 for unknown/inactive stores | Decided, implemented (6, ADR-83) |
| RTL-first storefront design system on tokens + HTMX + Alpine (no new framework) | Decided, implemented (6, ADR-84) |
| Variant selection validated server-side; Add-to-Cart never trusts the browser price/id | Decided, implemented (6, ADR-85) |
| Variant-specific images fall back to the product gallery, never a foreign image | Decided, implemented (6, ADR-86) |
| One storefront price presenter — server-owned, zero-decimal IRT | Decided, implemented (6, ADR-87) |
| Cart and checkout are idempotent and server-revalidated; browser return isn't payment proof | Decided, implemented (6, ADR-88) |
| Customer account isolation — own records only, store-scoped orders, no internal fields | Decided, implemented (6, ADR-89) |
| Storefront SEO is tenant-scoped to the request Host; drafts/private pages excluded | Decided, implemented (6, ADR-90) |
| Theme settings via per-store CSS variables; no page builder | Decided, implemented (6, ADR-91) |
| Browser/E2E testing complements (never replaces) service+view tests; no driver/profile/screenshot artifacts | Decided, implemented (6, ADR-92) |
| Owner identity is email/password, structurally separate from phone-based storefront customer identity | Decided, implemented (Portal, ADR-93) |
| `Store.platform_code`: permanent, human-typable 9-char identifier, distinct from `public_id`/`admin_subdomain` | Decided, implemented (Portal, ADR-94) |
| `StoreDomain` gains `domain_type`/`retired_at`; no second hostname table | Decided, implemented (Portal, ADR-95, amended ADR-101) |
| Old hostnames become permanent redirecting aliases, never reused by another Store | Superseded by ADR-101 (Portal, ADR-96) |
| Platform-level hosts (marketing/portal, platform-admin) get their own URLconf via `request.urlconf`, additive to existing routing | Decided, implemented (Portal, ADR-97) |
| Merchant-admin handoff via a signed, single-use, DB-backed ticket (no cross-subdomain cookie sharing) | Decided, implemented (Portal, ADR-98) |
| Trial Store provisioning activates immediately in one atomic call; onboarding is a separate, optional, later flow | Decided, implemented (Portal, ADR-99) |
| `verify_domain_consistency --strict` is read-only, mirrors the billing/subscription/inventory consistency-command shape exactly; a wider `RESERVED_PLATFORM_SUBDOMAINS` list (Section K's product decision) guards future paid subdomain claims and is checked here today | Decided, implemented (Portal, ADR-100) |
| Retired trial/platform hostnames go silently inactive and never redirect (overrides ADR-96); Platform Admin host is `platformadmins.rastisi.ir` | Decided, implemented (Portal, ADR-101) |
| `PlatformConfiguration` singleton for platform-wide tunables; owner identity is mobile OTP sharing `User.username=phone` with storefront customers by deliberate design (email+password kept as secondary/recovery) | Decided, implemented (Portal, ADR-102) |
| Registration auto-provisions exactly one trial Store (onboarding mode C); one computed publication-state service (no duplicated status field) gates storefront visibility until onboarding completes | Decided, implemented (Portal, ADR-103) |
| Four seeded Plans via an idempotent command; trial_days sourced from PlatformConfiguration, never a second hardcoded 30; a Plan with any existing version is never reseeded | Decided, implemented (Portal, ADR-104) |
| **Mistake record**: portal purchase (Section 8/9) built a parallel `PlatformInvoice`/`PlatformPaymentAttempt` stack instead of reusing the pre-existing `apps.billing` domain (Checkpoint 5B) | **Resolved** — duplicate stack deleted, portal now consumes `apps.billing` directly (ADR-105/ADR-106) |
