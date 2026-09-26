# Phase 1B — Merchant Admin Authorization and Routing Foundation Report

**Branch:** `claude/docs-prototypes-review-jxm6aw`
**Status of this report:** factual, scoped status update. The originating
Phase 1B prompt's "Definition of Complete" (§11) lists several items —
several are done and verified below; one (admin-subdomain-only enforcement)
is deliberately not done this pass, and is named explicitly in §13 rather
than glossed over.

---

## 1. Executive Summary

Delivered, all with real code, tests, and verified full-suite runs:

* Every merchant-admin permission requested in §2 of the prompt that has a
  corresponding existing view is now server-side enforced via a granular
  permission registry (`apps.stores.authorization`), applied to all 83
  `@staff_required` views in `apps.dashboard.views`.
* A role-permission matrix (§3) mapping the existing `StoreMembership.Role`
  choices — no new role system created, as instructed.
* `/admin-portal/` is now the canonical Merchant Admin Portal route (§4);
  `/admin-panel/` is a temporary 302 compatibility redirect.
* `Store.admin_subdomain` (§5): a new, unique, validated, normalized field,
  independent of the public `StoreDomain`, with its own resolver
  (`resolve_store_for_admin_host`).
* The dashboard home page (§7) was audited against real code, not assumed
  correct — and a genuine, previously-unknown cross-Store data leak was
  found and fixed (see §5 below).

**Not done, named explicitly (§13):** admin-subdomain-only enforcement
(blocking a Store's *public* storefront domain from also serving its
`/admin-portal/`) is designed and resolvable but not yet wired into
`staff_required` — see Known Limitations. The admin shell (§6) was verified
against the existing templates rather than rebuilt, since most of it
already existed from prior PRs; the specific gaps found (permission-aware
nav, a 403 page) were built, the rest was confirmed already present.

## 2. Previous Work Verified

Before any change: confirmed current branch
(`claude/docs-prototypes-review-jxm6aw`), clean working tree, latest commit
(`dd04e5c`, the prior phase's StoreMembership-authorization work), and
re-ran `apps.stores.tests.test_authorization`,
`apps.dashboard.tests.test_membership_authorization`, and
`apps.dashboard.tests.test_decorators` — all passing (28/28) before this
phase's changes began. `apps/stores/authorization.py` and
`apps/dashboard/decorators.py` were extended in place, not replaced — no
concrete defect was found in the prior implementation that required
discarding it.

## 3. Role-Permission Matrix

`StoreMembership.Role` (unchanged — no new role added) mapped to the
prompt's requested role names, and to a granular permission registry in
`apps/stores/authorization.py`:

| Prompt's role name | `StoreMembership.Role` | Permissions |
|---|---|---|
| Owner | `OWNER` | All permissions, including ownership-tier (staff/domain/subscription management) |
| Administrator / Manager | `ADMINISTRATOR` | All permissions except ownership-tier |
| Product Manager | `CATALOG_MANAGER` | Product view/create/edit/delete, category, attribute*, variant, inventory*, media, reports (view) |
| Order Manager | `ORDER_MANAGER` | Order view/status-change, customer view/edit*, reports (view) |
| Content Manager | `CONTENT_EDITOR` | Content management, media |
| Analyst / Read-Only | `ANALYST` | Dashboard, reports, product/order/customer **view only** — no mutation permission of any kind |

`*` = permission key defined and mapped to a role, but no corresponding
view exists yet (see §13 — attributes, inventory-as-a-separate-feature,
and customer-editing are not yet real dashboard features; the permission
keys exist so the day they are built they only need a decorator, not a
registry redesign).

Full permission key list (22 keys): `DASHBOARD_VIEW`, `PRODUCT_VIEW`,
`PRODUCT_CREATE`, `PRODUCT_EDIT`, `PRODUCT_DELETE`, `CATEGORY_MANAGE`,
`ATTRIBUTE_MANAGE`, `VARIANT_MANAGE`, `INVENTORY_MANAGE`, `MEDIA_MANAGE`,
`ORDER_VIEW`, `ORDER_STATUS_CHANGE`, `CUSTOMER_VIEW`, `CUSTOMER_EDIT`,
`REPORTS_VIEW`, `DISCOUNT_MANAGE`, `SETTINGS_MANAGE`,
`PAYMENT_SETTINGS_MANAGE`, `SMS_SETTINGS_MANAGE`, `CONTENT_MANAGE`,
`STAFF_MANAGE`, `DOMAIN_MANAGE`, `SUBSCRIPTION_MANAGE`.

Permission keys with **no corresponding view in this codebase at all**
(defined and role-mapped, but nothing to attach a decorator to yet):
`ATTRIBUTE_MANAGE` (no attribute feature), `DISCOUNT_MANAGE` (no discount
admin UI beyond the existing basic Coupon model), `CUSTOMER_EDIT` (only
customer *viewing* exists), `STAFF_MANAGE` (no membership-management UI),
`DOMAIN_MANAGE` (no domain-management UI), `SUBSCRIPTION_MANAGE` (no
billing model at all — matches the master reference doc's own "Absent"
status for SaaS Billing).

## 4. Views and APIs Protected

All 83 `@staff_required`-decorated view functions in
`apps/dashboard/views.py` now also carry `@permission_required(...)`:
product list/create/edit/delete (`PRODUCT_VIEW`/`PRODUCT_CREATE`/
`PRODUCT_EDIT`/`PRODUCT_DELETE`), product images (`MEDIA_MANAGE`),
variants (`VARIANT_MANAGE`), categories (`CATEGORY_MANAGE`), orders/
invoices/payments (`ORDER_VIEW`), order status change specifically
(`ORDER_STATUS_CHANGE` — checked inline inside `order_detail`'s POST
branch, since GET/view and POST/status-change share one view function),
customers (`CUSTOMER_VIEW`), reports (`REPORTS_VIEW`), settings/finance/
appearance (`SETTINGS_MANAGE`), gateway/shipping toggles and gateway config
(`PAYMENT_SETTINGS_MANAGE`), SMS settings/templates/logs
(`SMS_SETTINGS_MANAGE`), and all content management — pages, hero,
banners, social links, menus, footer settings/trust-badges/payment-logos
(`CONTENT_MANAGE`).

Denial is an actual HTTP 403 (new `apps/dashboard/templates/dashboard/403.html`,
extending the admin shell), rendered by `permission_required` — distinct
from `staff_required`'s existing redirect-to-storefront for "not a member
of this Store at all." A member with the wrong role sees a real 403 page,
not a silent bounce.

## 5. A Real Bug Found and Fixed: Dashboard/Report Cross-Store Data Leak

While verifying the dashboard home page against the prompt's requested
metric list (§7 — "Add tests for: Store scoping... Cross-store
isolation"), direct code inspection of
`apps/dashboard/services/dashboard_service.py` found that its own
docstring said Order/Customer-based figures were "deliberately not
Store-scoped... `Order` isn't Store-scoped yet in this PR." That was true
when originally written, but `Order.store` has existed as a direct,
mandatory field since a later PR (ADR-14) — this service was never
updated. Concretely, before this fix: **today's sales, today's order
count, customer counts, the sales trend chart, the order-status donut
chart, "recent orders," "top-selling products," and every figure in the
Reports page (`apps/dashboard/services/report_service.py`, which wraps
`dashboard_service`) summed every Store's orders together**, not just the
current Store's. Any merchant viewing their own dashboard was seeing
numbers polluted by every other Store on the platform.

Fixed: every function in both services now takes an explicit `store`
argument and filters accordingly; `Customer` (which has no direct `store`
FK by deliberate ADR-pending decision) is scoped via the same
`orders__store` relation `customers_admin_service.annotated_customers`
already established. New cross-Store isolation tests were added to
`test_dashboard_service.py` and `test_report_service.py` proving another
Store's paid orders/order-items no longer affect these figures. This was
an unplanned discovery during verification, not something the prompt
explicitly asked to hunt for — but it directly serves the same
tenant-isolation goal the prompt's §7 testing requirement names.

## 6. Admin Domain and Routing (§4–§5 of the prompt)

* **`Store.admin_subdomain`** (new field, `apps/stores/models.py`): unique,
  ASCII-only, normalized-lowercase `CharField`. `Store.save()` auto-derives
  it from `slug` (or, when `slug` isn't ASCII-safe — `slug` allows Unicode
  — from `public_id`) when not supplied explicitly, so every existing
  `Store.objects.create(...)` call site across the codebase and test suite
  needed zero changes. Validated against a reserved-word list
  (`apps.stores.hostnames.RESERVED_ADMIN_SUBDOMAINS`: `www`, `admin`,
  `api`, `dashboard`, `panel`, `portal`, `rastisi`, etc.).
* **Migrations** (staged, matching the project's own established
  nullable→backfill→enforce pattern): `stores/0003` (add nullable+unique),
  `stores/0004` (data migration — backfills the seeded Akhlaghi row),
  `stores/0005` (enforce not-null). `makemigrations --check --dry-run`
  confirms these exactly match the model state.
* **`resolve_store_for_admin_host(raw_host)`** (`apps/stores/resolution.py`):
  resolves a Store from a Host of the shape
  `f"{admin_subdomain}.{settings.RASTISI_ADMIN_DOMAIN_SUFFIX}"`
  (`RASTISI_ADMIN_DOMAIN_SUFFIX` setting, default `"rastisi.ir"`,
  environment-overridable — added to `shop_core/settings.py`,
  `.env.example`, and `PRODUCTION_CONFIGURATION.md`).
* **`/admin-portal/`** is now the canonical mount in `shop_core/urls.py`.
  `/admin-panel/` 302-redirects to the equivalent `/admin-portal/` path
  (new `apps.core.views.admin_panel_compat_redirect`), preserving sub-path
  and query string — deliberately 302, not 301, so it stays a removable
  shim rather than a browser-cached permanent alias. `admin-portal` was
  added to `apps.content.models.RESERVED_SLUGS` alongside the pre-existing
  `admin-panel`.
* Full ADR written: ADR-16 in
  `docs/docs/product/architecture/SAAS_DOMAIN_DECISIONS.md`.

**What this explicitly does not do yet:** `resolve_store_for_admin_host`
is new, tested, standalone infrastructure — not yet consumed by
`staff_required` to reject a request that reached the dashboard through a
Store's *public* `StoreDomain` instead of its admin subdomain. See §13.

## 7. Admin Shell (§6 of the prompt)

Verified against the existing codebase before building anything new — most
of the shell already existed from prior PRs (`base_admin.html`: sidebar,
header, store/user identity, theme toggle, logout, "back to storefront"
link; `login.html`; `confirm_delete.html` for confirmation dialogs;
`partials/` templates already implementing the reusable table/form-shell
pattern; root `templates/404.html`/`500.html`). Built this phase:

* Permission-aware navigation: `apps/dashboard/context_processors.py`
  (`merchant_permissions`, reads the already-resolved
  `request.store_membership` — zero extra queries) + `base_admin.html`
  sidebar now wraps each nav section in `{% if can_view_products %}` etc.,
  so a Content Editor no longer sees a Products link they'd get a 403 on.
* `dashboard/403.html` — new, extending the shell.

**Not built:** breadcrumbs (the shell's existing `page_title`/`page_sub`
header blocks already communicate location; a full breadcrumb trail would
require passing structured breadcrumb data through every one of the 83
views and was judged lower-value than the security-enforcement work this
phase prioritized — left as a follow-up, not silently dropped).

## 8. Dashboard Home Page (§7 of the prompt)

Verified against the requested metric list using real code inspection, not
assumption:

| Requested metric | Status |
|---|---|
| Order count | Present (`stat_cards.today_orders`, now Store-scoped — see §5) |
| Revenue | Present (`stat_cards.today_sales`) |
| Product count | Present (`nav_product_count`) |
| Customer count | Present (`stat_cards.customers_total`, now Store-scoped) |
| Low-stock products | Present (`low_stock_rows`/`low_stock_count`) |
| Recent orders | Present (now Store-scoped) |
| Recent products/activity | Present (`top_products`, now Store-scoped) |
| Store status | **Added this phase** — `store_status_display` in context, rendered as a badge next to the page subtitle |
| Subscription status | **Not added** — no subscription/billing model exists anywhere in this codebase (confirmed absent; matches the master reference doc's own "Absent" status for SaaS Billing). Inventing a fake status would violate the prompt's own "do not invent metrics the data model cannot support" instruction. |
| Setup checklist | **Not added** — no onboarding/checklist data model exists; same reasoning as above |

Query optimization: `recent_orders`/`top_selling_products` already used
`select_related`/aggregation before this phase; the Store-scoping fix
added `.filter(store=store)` to the same queries without changing their
shape.

## 9. Files Created

* `apps/stores/tests/test_admin_subdomain.py`, `apps/stores/migrations/0003_store_admin_subdomain_schema.py`, `0004_backfill_store_admin_subdomain.py`, `0005_store_admin_subdomain_enforce_not_null.py`
* `apps/dashboard/context_processors.py`
* `apps/dashboard/templates/dashboard/403.html`
* `apps/dashboard/tests/test_permission_enforcement.py`, `test_admin_panel_compat_redirect.py`
* `docs/docs/product/reports/PHASE_1B_ADMIN_FOUNDATION_REPORT.md` (this file)

## 10. Files Modified (grouped)

* **Authorization core:** `apps/stores/authorization.py` (granular registry), `apps/dashboard/decorators.py` (`permission_required` now variadic/OR, real 403, caches membership on `request.store_membership`)
* **Views:** `apps/dashboard/views.py` (83 `permission_required` decorators added, `order_detail` inline status-change check, store-scoped dashboard/report calls)
* **Services:** `apps/dashboard/services/dashboard_service.py`, `apps/dashboard/services/report_service.py` (Store-scoping fix, §5)
* **Domain/routing:** `apps/stores/models.py` (`admin_subdomain` field), `apps/stores/hostnames.py` (`normalize_admin_subdomain`, reserved list), `apps/stores/resolution.py` (`resolve_store_for_admin_host`), `shop_core/urls.py` (canonical mount + compat redirect), `shop_core/settings.py` (`RASTISI_ADMIN_DOMAIN_SUFFIX`, new context processor registration), `apps/core/views.py` (`admin_panel_compat_redirect`), `apps/content/models.py` (`RESERVED_SLUGS`)
* **Templates:** `apps/dashboard/templates/dashboard/base_admin.html` (permission-aware nav), `dashboard.html` (store status badge)
* **~25 existing test files:** updated for the new route (`/admin-panel/` → `/admin-portal/` in hardcoded path assertions) and, where applicable, new Store-scoping/permission assertions
* **Docs:** `00_PROJECT_MASTER_REFERENCE.md`, `SAAS_DOMAIN_DECISIONS.md` (ADR-16), `SAAS_ARCHITECTURE.md`, `PRODUCTION_CONFIGURATION.md`, `.env.example`, `apps/content/README.md`

## 11. Database Changes

* New model field: `Store.admin_subdomain` (`CharField(max_length=63, unique=True)`)
* 3 migrations (staged nullable→backfill→enforce, per project convention)
* No fields removed, no other schema changes

## 12. Commands Actually Executed and Results

```text
python manage.py check                              → System check identified no issues (0 silenced)  [run repeatedly through the phase]
python manage.py makemigrations --check --dry-run   → No changes detected  [run repeatedly through the phase]
python manage.py migrate stores                     → all 5 stores migrations applied OK (local smoke check)
```

Test runs (all executed, all green; run in batches due to full-suite runtime, never to skip anything):

| Batch | Tests | Result |
|---|---|---|
| Pre-phase verification: `test_authorization` + `test_membership_authorization` + `test_decorators` | 28 | OK |
| New `test_authorization.py` (rewritten with per-role coverage) | 23 | OK |
| New `test_permission_enforcement.py` | 34 | OK |
| New `test_admin_subdomain.py` (+ `test_models.py`) | 45 | OK |
| New `test_admin_panel_compat_redirect.py` + `test_admin_login` + `test_middleware` + `test_admin_subdomain` | 53 | OK |
| `test_dashboard_service.py` + `test_report_service.py` + `test_report_views.py` (Store-scoping fix) | 32 | OK |
| `test_views.py` + `test_dashboard_service.py` (store-status addition) | 25 | OK |
| Full `apps.dashboard` + `apps.content` + `apps.orders.tests.test_gateway_admin` + `apps.stores.tests.test_admin_superuser_gate` (pre-route-rename) | 899 | OK |
| Full `apps.dashboard` + `apps.content` + `apps.orders` + `apps.stores` (post-route-rename) | 1352 | OK |
| **Full suite, pre-route-rename** (`python manage.py test`) | 1817 | OK |
| **Full suite, final** (`python manage.py test`) | 1824 | OK — 0 failures, 0 errors |

One real regression was caught and fixed during this verification, not
hidden: an early draft of a test fixture (`test_admin_superuser_gate.py`
carried over from the prior phase) would have needed two `OWNER`+`ACTIVE`
memberships on one Store — this was caught in the *previous* phase, not
this one; this phase's own self-caught issue was the `resolve_store_for_admin_host`
test fixtures initially omitting `status=Store.Status.ACTIVE` (defaults to
`PROVISIONING`), correctly triggering the resolver's own fail-closed
`ACTIVE`-only policy — fixed by setting the status explicitly in the test
fixture, not by weakening the resolver.

## 13. Known Limitations

* **Admin-subdomain-only enforcement is not wired in.** As of this PR, a
  Store's dashboard remains reachable through *any* Host that resolves to
  it via `resolve_store_for_service` — including a verified public
  `StoreDomain` — not only its `admin_subdomain` host.
  `StoreMembership` authorization still fully prevents any cross-Store
  data access regardless of which Host was used; what's open is only
  "should this Host serve the admin portal for any Store at all," not
  tenant isolation. Wiring this in safely requires first migrating every
  existing multi-Store dashboard test fixture (`test_catalog_store_isolation.py`,
  `test_order_store_isolation.py`, `test_membership_authorization.py`, and
  others) from generic hosts (`dash-a.example.com`) to real
  admin-subdomain-shaped hosts, and deciding how the existing
  single-Store `testserver`/`localhost` compatibility fallback should
  interact with admin-host enforcement — both sizeable, separate pieces of
  work, not rushed into this same pass.
* **`permission_required` is coarse per resource, not per exact prototype
  action.** E.g. all product-image endpoints share `MEDIA_MANAGE`; all
  content-management endpoints (pages/hero/banners/menus/footer) share
  `CONTENT_MANAGE`. Splitting further (e.g. a role that can view but not
  reorder banners) was not requested with enough specificity to invent
  without guessing, and the prompt's own permission list groups these the
  same way.
* **Six permission keys have no view to attach to** (`ATTRIBUTE_MANAGE`,
  `DISCOUNT_MANAGE`, `CUSTOMER_EDIT`, `STAFF_MANAGE`, `DOMAIN_MANAGE`,
  `SUBSCRIPTION_MANAGE`) — see §3. Building those views is out of this
  phase's scope (they are the Phase 1 report's already-documented
  "remaining work": attributes/variants matrix, wallet/cashback/referral,
  staff invitation lifecycle, domain lifecycle UI, subscription/billing).
* **No breadcrumb component** — see §7.
* **Login view (`admin_login`) still gates on `is_staff` only**, independent
  of `StoreMembership` — a known asymmetry already documented in the Phase
  1 report, unchanged by this phase.

## 14. Remaining Work (unchanged scope from the Phase 1 report, priority order)

Attribute/variant matrix, inventory ledger, full order lifecycle
(fulfillment/refund/invoice), customer-ownership ADR, cart/coupon full
tenantization, discounts/campaigns, cashback, wallet, referral, industry
setup templates, rich product content/videos, CMS/page-builder versioning,
reports beyond the existing basic charts, SaaS billing/subscription. None
of these were in Phase 1B's scope and none were started.

## 15. Recommended Next Phase

Two candidates, in order:

1. **Admin-subdomain-only enforcement** (§13) — the one explicitly
   incomplete piece of this phase's own stated scope, and now that the
   field/resolver/ADR exist, the remaining work is bounded: migrate
   existing multi-Store test fixtures + decide the dev-fallback
   interaction + wire the check into `staff_required`.
2. Then, per the Phase 1 report's own recommendation (still valid):
   begin net-new feature build-out (attributes/variants first, since
   inventory and several other permission keys depend on that data model
   existing) now that the authorization layer that gates it is fully wired.

## 16. Commit, Branch, and Push Status

* **Branch:** `claude/docs-prototypes-review-jxm6aw`
* **Commit hash / push status:** recorded after this report is committed — see the commit that includes this file for the exact hash; pushed to `origin/claude/docs-prototypes-review-jxm6aw` in the same operation.
