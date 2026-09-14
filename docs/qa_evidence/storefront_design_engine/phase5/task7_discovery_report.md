# Phase 5 Task 7 — Browse/Search/Filter/Sort Discovery Report

## 1. Certified checkpoint

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Official branch: `feature/phase5-design-expansion`
- `git rev-parse HEAD` = `937b6bd8885d56fee70c0bb9df85493eda6aeade`
- `git rev-parse origin/feature/phase5-design-expansion` = `937b6bd8885d56fee70c0bb9df85493eda6aeade`
- `git status --short` = clean (this task made **no** repository changes)
- Read-only investigation. No production code, tests, migrations, branch, commit, or push.

## 2. Executive finding

Task 7 is **bounded hardening / repair**, not a new subsystem. The Browse/Search/Filter/Sort
pipeline already exists as ONE canonical, tenant-scoped, query/URL-canonical, progressively
enhanced flow owned by `apps/catalog/views.py::build_product_listing_context()` +
`_filtered_products()` + `Paginator`, rendered through the canonical `product_listing` section
into `catalog/partials/product_list_results.html`, reusing the canonical `product_card.html`.

Filter, Sort, Search, Listing/Search Header, Empty State, Product-card reuse, HTMX/no-JS,
tenant isolation and SEO are all **correct and should be reused as-is** (test-gaps only in
a few spots).

There are exactly **two** real gaps, both mobile:

1. **Mobile search discoverability (biggest real gap).** On the `legacy_default` Global Header
   Variant — the default for any store with no `header_variant`, and the variant used by the
   seeded fashion tenant — the header search bar is `display:none` at ≤680px
   (`apps/core/static/css/layout.css:183`), and the canonical Task-5 mobile drawer
   (`templates/partials/mobile_nav_drawer.html`) consumes only NAV authority — it has **no
   search affordance**. Browser-measured at 390px: header search `visible:false`, drawer
   search inputs `0`, drawer search forms `0` → **no discoverable mobile search entry point**.
2. **Mobile pagination at scale.** `product_list_results.html` renders **every** page number
   from `page_obj.paginator.page_range`. With the seeded 100 products (9 pages) the strip
   already wraps to **2 rows at 390px** (browser-measured). It is valid and functional
   (`flex-wrap:wrap` works, no overflow), but a store with 50+ pages would render 50+ numbers —
   genuinely poor mobile UX. This is a **windowing** gap, not a CSS defect.

Everything else: REUSE AS-IS or TEST-GAP-ONLY. Expected migrations: **NONE**.

## 3. Canonical request/data flow

One route serves browse **and** search (no separate search URL):
`apps/catalog/urls.py` → `path("products/", views.product_list, name="product-list")`.

`product_list(request)`:
1. `store = resolve_store_for_storefront(request)` — the single canonical tenant resolver
   (`apps/stores/resolution.py`; source of truth is `StoreDomain.hostname`).
2. `context = build_product_listing_context(request, store)` — the ONE listing pipeline:
   - `_filtered_products(request, store)` builds the queryset from
     `storefront_listing_products(store)` (already tenant + publish scoped),
     `.select_related("brand","category").prefetch_related("images")`, applies q / category /
     brand / min_price / max_price / discounted / in_stock, then `.order_by(order_field,"id")`.
   - `Paginator(qs, PRODUCTS_PER_PAGE=12)` → `paginator.get_page(request.GET.get("page"))`.
   - Server-derived `listing_heading` + `listing_breadcrumbs` (`_resolve_listing_location`) and
     removable `active_filter_chips` (`_build_active_filter_chips`), both tenant-scoped.
   - `querystring` (page-stripped) for link/state preservation.
3. Page type is chosen `SEARCH if context["query"] else LISTING`, then
   `build_universal_storefront_context(...)` composes the Builder shell/sections. The catalog
   query/filter/sort is fully independent of that choice.
4. HTMX vs full-page: on `HX-Request: true` it sets `listing_header_oob=True` and returns the
   **same** `product_list_results.html` partial (out-of-band header refresh); otherwise the full
   `product_list.html`. Both paths run the exact same `build_product_listing_context` — no second
   fragment renderer.

Per-flow (all share the pipeline above; A–J differ only by query params):
- A plain browse — `/products/`
- B text search — `?q=` (name OR brand.name OR category.name, `.distinct()`)
- C category — `?category=slug` (matches category slug OR its parent slug → subcategory rollup)
- D brand — `?brand=slug`
- E price — `?min_price=&max_price=` (each gated on `.isdigit()`)
- F discounted — `?discounted=1` → `discount_percent__gt=0`
- G in-stock — `?in_stock=1` → `stock__gt=0` (real `Product.stock`, same field as card resolver)
- H sort — `?sort=` (`LIST_SORT_OPTIONS`, invalid → `newest`), always `+ ,"id"` tiebreak
- I pagination — `?page=` (`get_page` clamps invalid/high to last, non-numeric → page 1)
- J combined — all preserved together via `querystring` + `hx-push-url`

**Is there ONE canonical pipeline? YES.** No duplicate listing query service, search backend,
filter engine, sort engine, pagination model, or product-card path was found.

## 4. Filter audit

Owner: `_filtered_products()` + `_build_active_filter_chips()`. Filters: q, category, brand,
min_price, max_price, discounted, in_stock. For each: real DB predicate, tenant-scoped
(`storefront_listing_products(store)` base + `store=store` on Category/Brand lookups), visible
control in `product_listing.html`, removable chip with a "drop only this filter" URL that
preserves the rest, `clear_all_url`, HTMX (`hx-get`/`hx-target=#product-results`/`hx-push-url`),
URL state, back-button honest, empty-result handled.

Special cases (verified in code + browser/tests):
- `min_price > max_price` → both applied → empty result → empty state (no crash).
- non-numeric price (`?min_price=abc`) → `.isdigit()` false → filter not applied AND no chip
  shown (chip gated on the same predicate).
- inactive category/brand → `is_active=True` lookup returns None → no chip; queryset still
  filters by slug so it simply yields the rows for that slug (typically none if inactive is also
  excluded upstream).
- foreign-store category slug → **0 results** (browser-measured `<b>۰</b> کالا یافت شد`) — no
  cross-tenant leak.
- unknown query params → ignored.

Classification: **REUSE AS-IS** (minor test-gap: explicit `min_price>max_price` assertion).

## 5. Sort audit

Owner: `LIST_SORT_OPTIONS` (exact current keys/labels):
- `newest` → `-created_at` ("جدیدترین") — DEFAULT
- `price_asc` → `price` ("ارزان‌ترین")
- `price_desc` → `-price` ("گران‌ترین")
- `popular` → `-sold_count` ("محبوب‌ترین")
- `rating` → `-rating` ("بیشترین امتیاز")

Invalid `?sort=` falls back to `newest`. Every sort appends `, "id"` → stable secondary order.
Sort is retained through filtering, pagination (`querystring`) and HTMX; same results full-page
vs HTMX (same builder). Covered by `test_product_list_view.test_sort_price_ascending`.

Classification: **REUSE AS-IS**.

## 6. Search audit

Owner: `_filtered_products()` q-branch. Fields searched: **Product.name OR Brand.name OR
Category.name** (`icontains`), with `.distinct()` to dedupe the brand/category joins.
Tenant-scoped via the base queryset. Empty/whitespace `q` → `.strip()` → no filter (all
products). Persian text works (browser: `?q=تیشرت` → 5 results). Search paginates, and combines
with filters and sort. SEO: `product_list.html` emits `<meta name="robots" content="noindex,
follow">` when `query or min_price or max_price or discounted_only` (browser-confirmed on
`?q=`), and stays indexable on a plain/category-only listing (browser-confirmed: 0 robots meta).

Classification: **REUSE AS-IS** (test-gap: explicit brand-name / category-name search-match and
`.distinct()` dedupe assertions).

## 7. Pagination audit

Owner: `Paginator(qs, PRODUCTS_PER_PAGE=12)` + `page_obj` + `product_list_results.html`.
Pagination happens at the **queryset** level (before evaluation). Template iterates
`page_obj.paginator.page_range` and renders Previous / all page numbers / Next, with the current
page as `<span class="current">`, Persian numerals via `|fa_number`, `querystring` preserved on
every link, HTMX `hx-get` + `hx-push-url="true"` + `hx-indicator`, and full-page `<a href="?page=">`
fallback for no-JS.

Verified behaviors (tests + browser on 100 products / 9 pages):
- 1 page → no `.pagination` block (`num_pages > 1` guard) — `test_single_page_has_no_pagination_controls`.
- 2 pages / several pages → paginates, page size respected — `test_pagination_respects_page_size`,
  `test_more_than_one_page_worth_paginates`.
- invalid / too-high page → `get_page` clamps to last page (`test_out_of_range_page_returns_last_page`,
  browser `?page=999` → 200).
- page after filters / search / sort → `querystring` preserves them.
- Previous / Next / current / numbers / Persian numerals → all present (browser: current page `۵`).
- browser back/forward → `hx-push-url` keeps URL honest; no-JS links navigate normally
  (browser: `href="?page=2/3/4"` present).

Classification: **TEST GAP + SMALL REPAIR** (rendering is correct; windowing at scale — see §8/§22).

## 8. Mobile pagination evidence

Browser baseline (bundled chromium, RTL, real published `rastisi-fashion-test` tenant, 100
products = 9 pages):

| Viewport | pagination children | rows | overflow | numbers rendered |
|---|---|---|---|---|
| desktop-1440 | 10 | 1 | none (sw=cw=1440) | 8 |
| tablet-768 | 10 | 1 | none (sw=cw=768) | 8 |
| mobile-390 | 10 | **2** | none (sw=cw=390) | 8 |

The old plan's "wraps awkwardly" concern is **partly real but not a CSS defect**: `.pagination`
already has `flex-wrap:wrap` and there is no horizontal overflow. At 9 pages the mobile strip
wraps to 2 rows — usable but visually poor. The actual scale problem is that **all** page numbers
are rendered (`page_range`); at 50+ pages the strip becomes unusable on a phone.

Outcome: **B + E** from the prompt's option list (wrapping valid but poor because every page
number is rendered; many pages make it unusable). Recommendation (not implemented): bounded
pagination window — see §22.

## 9. Listing/Search header audit

Owner: `_resolve_listing_location()` → `listing_header.html`. Dynamic heading + breadcrumbs:
- plain listing → "همه‌ی محصولات", crumbs Home → heading.
- search → "نتایج جستجو برای «q»", crumbs Home → Shop → heading.
- parent category → category name, crumbs Home → Shop → name.
- child category → subcategory name, crumbs Home → Shop → parent(link) → child.
- brand → brand name, crumbs Home → Shop → name.

OOB refresh: on HTMX the view sets `listing_header_oob=True`; the results partial re-includes
`listing_header.html with oob=True`, which renders `hx-swap-oob="true"` on `#plp-listing-header`,
so a chip/filter/pagination swap can never leave a stale heading/breadcrumb. Covered by
`test_g2_listing_context_and_chips`.

Classification: **REUSE AS-IS**.

## 10. Empty-state audit

Owner: `product_list_results.html` `{% else %}` branch (`.plp-empty`: 🔍 + "کالایی یافت نشد" +
"فیلترها یا عبارت جستجو را تغییر دهید."). Verified: zero results / zero search results / filters
eliminate all (browser: `.plp-empty` present at all 3 viewports; `test_no_results_shows_empty_state`).
Understandable, RTL-native, inside the shell. Recovery path is guidance text + the still-present
filter form + active-filter chips (each chip removal is a recovery link); there is no explicit
"clear all / go to shop" button inside the empty block itself.

Classification: **REUSE AS-IS** (optional tiny enhancement: a "حذف فیلترها" link inside the empty
block; not required).

## 11. Product-card reuse

`product_list_results.html` renders each result via
`{% include "catalog/partials/product_card.html" with card_settings=card_settings %}`, and the
`product_listing` section threads its resolved merchant card override (`settings.card`) into that
same include — the exact same canonical card / pricing / stock / badges / Quick View path used
elsewhere. No listing-specific card authority exists. Covered by
`HtmxFragmentCardSettingsPropagationTests`.

Classification: **REUSE AS-IS**.

## 12. Mobile filter behavior

`product_listing.html` uses a native `<details class="plp-filters" open>` with a `<summary
class="plp-filters-toggle">`. Progressive enhancement JS in `product_list.html` collapses it at
`≤860px` on load (still one tap to open) and re-syncs after `htmx:afterSwap`; no-JS keeps it open
and fully usable; desktop summary is `display:none`. Browser at 390px/768px: no horizontal
overflow, cards render, HTMX swaps keep the disclosure intact. Keyboard-operable (native
`<summary>`).

Classification: **REUSE AS-IS**.

## 13. Mobile search discoverability — CRITICAL

Canonical header architecture: 10 Global Header Variants (`global_region_registry.py`), default
`legacy_default` = `page_shell_header.html`. Search markup exists when `header_config.show_search`.
The Task-5 mobile drawer (`templates/partials/mobile_nav_drawer.html`) consumes NAV_MOBILE
(fallback NAV_HEADER) only — **no search affordance**.

Per-variant mobile-search behavior at 390px (grouped by actual behavior, not brute-forced):

| Variant | Mobile search entry point | Class |
|---|---|---|
| **legacy_default** (default) | header `.search` is `display:none` ≤680px (`layout.css:183`); drawer has no search | **D — none** |
| marketplace_search_first | `.gh--marketplace .gh-search` stays visible on mobile (grid-area:search) | A — visible |
| boutique_centered | `.gh-boutique-search-panel .gh-search` visible on mobile | A — visible |
| atelier_nav | `gh-atelier-search-toggle` button opens a search panel | B — icon opens |
| premium_three_column | dedicated `.gh-mobile-search` block shows on mobile | A/B — visible |
| dark_tech | dedicated `.gh-mobile-search` block | A/B — visible |
| promo_search_nav | dedicated `.gh-mobile-search` block | A/B — visible |
| beauty_search_nav | `.gh-beauty-mobile-search` block | A/B — visible |
| chocolate_centered_search | `.gh-mobile-search` block | A/B — visible |
| luxury_search | `.gh-mobile-search` block | A/B — visible |

Browser evidence (legacy_default fashion tenant, 390px):
`plp:mobile-header-search-visible` → `{present:true, visible:false}`;
`plp:mobile-drawer-search-affordance` → `{searchInputs:0, searchForms:0}` (**FAIL**).

**Conclusion:** only `legacy_default` has no discoverable mobile search — and it is exactly the
variant that includes the shared mobile drawer. This makes the repair small and safe.

Smallest architecture-safe options (not implemented):
- **Option A** — keep search in header responsive rendering (would require un-hiding `.search`
  on mobile in `layout.css`, which risks crowding the compact 58px legacy header row).
- **Option B (recommended)** — add ONE search `<form role="search" method="get"
  action="{% url 'catalog:product-list' %}">` (name `q`) inside the existing
  `mobile_nav_drawer.html`, posting to the SAME endpoint. One repair covers the default variant
  and any header that uses the shared drawer.
- **Option C** — another mechanism already solves it: true only for the 9 non-legacy variants.

Strong rules honored: no new search route, no new backend, no second drawer.

## 14. Header variant impact

- The shared `mobile_nav_drawer.html` is included by exactly two shells: `templates/base.html`
  and `storefront_builder/partials/page_shell_header.html` (the `legacy_default` renderer).
- The 8 sibling storefront_builder header variants render their OWN mobile nav (`gh-mobile-nav`,
  `ghMobileOpen`) and their own mobile search (`.gh-mobile-search` / search panel / visible
  `.gh-search`) — they do NOT include the shared drawer.
- Therefore a single Option-B repair inside `mobile_nav_drawer.html` fixes `legacy_default` (the
  default, and the only variant currently missing mobile search) and any legacy `base.html` page,
  at the most canonical shared layer — without touching the 9 variants that already work.

## 15. HTMX / no-JS progressive enhancement

With JS/HTMX: filter (`hx-trigger="submit, change"`), sort, chip remove, clear-all, pagination
all `hx-get` → `#product-results` swap + `hx-push-url` (browser + `test_htmx_request_returns_partial_without_layout`).
Without JS: the filter `<form method="get">` submits normally; pagination `<a href="?page=">`
links navigate (browser-confirmed); chips/clear-all are plain `<a href>`; `<details>` filter stays
open and usable. JS is never mandatory.

Classification: **REUSE AS-IS**.

## 16. Accessibility findings (concrete gaps only)

- Header search inputs have `sr-only` labels in `_shared/search_form.html`; the `legacy_default`
  inline `.search` input in `page_shell_header.html` has **no associated `<label>`/aria-label**
  (placeholder only) — minor gap; if Option-B adds a drawer search, give it a real label.
- Pagination: current page is `<span class="current">` but has **no `aria-current="page"`**
  (breadcrumb current crumb does use `aria-current`); Previous/Next disabled states use
  `<span class="disabled">` (removed from tab order) — acceptable, but `aria-current` is a small
  gap. Consider `aria-label="صفحه‌بندی"` on the `.pagination` container.
- Filter disclosure is a native `<details>/<summary>` — good semantics.
- Sort/filter form controls have visible `<h3>` group headings; individual `<select>`/inputs rely
  on those headings, not `<label for>` — minor.
- HTMX loading indication exists (`#plpLoading` `hx-indicator`), but there is **no
  focus-management after swap** and no `aria-live` on `#product-results` / the count — screen-reader
  users are not told results changed. Small gap.

None require a framework; all are small, optional hardening.

## 17. Tenant isolation

Canonical resolver: `resolve_store_for_storefront` → `apps/stores/resolution.py` (single source of
truth, `StoreDomain.hostname`). Every listing/search/filter query is built from
`storefront_listing_products(store)`, and Category/Brand lookups are `store=store` filtered.
Browser cross-tenant probe (foreign category slug on the fashion store) → **0 products** (`<b>۰</b>`)
— no leak. Covered by `test_store_isolation` (33 tests pass). No new resolver needed.

Classification: **REUSE AS-IS**.

## 18. Performance / query findings

`_filtered_products` uses `.select_related("brand","category")` and `.prefetch_related("images")`;
`build_product_listing_context` also `Prefetch`es category children for the filter tree.
Pagination is applied at the queryset level (`Paginator(qs, 12)` before evaluation). No material
N+1 observed for the card grid (brand/category/images covered). `paginator.count` triggers one
COUNT query — expected. No speculative optimization warranted.

Classification: **REUSE AS-IS**.

## 19. Existing test coverage matrix

| Area | Status | Evidence |
|---|---|---|
| product_list route (full + HTMX) | COVERED | `test_product_list_view` (partial-without-layout, full-layout) |
| search | PARTIALLY COVERED | name-match covered; brand/category-name match + `.distinct()` not asserted |
| filter (category/brand/price/discounted/in_stock) | PARTIALLY COVERED | `test_u5_listing_filter_search`; `min_price>max_price` edge not asserted |
| sort | COVERED | `test_sort_price_ascending` (+ invalid fallback via code) |
| pagination (size, out-of-range, single/multi) | COVERED | `test_pagination_respects_page_size`, `test_out_of_range_page_returns_last_page`, `test_more_than_one_page_worth_paginates` |
| pagination windowing / Persian numerals in strip | NOT COVERED | (behavior verified only in browser) |
| HTMX partial | COVERED | `test_htmx_request_returns_partial_without_layout` |
| active chips | COVERED | `test_g2_listing_context_and_chips` (remove-one-preserves-sort-drops-page) |
| listing/search header (heading + breadcrumb + OOB) | COVERED | `test_g2_listing_context_and_chips` |
| empty state | COVERED | `test_no_results_shows_empty_state` |
| mobile filter disclosure | PARTIALLY COVERED | CSS/markup; no dedicated interaction test |
| Header search markup | COVERED | `test_u2a_global_header_system` |
| Task-5 mobile drawer | COVERED (nav only) | `test_mobile_nav_drawer` — asserts NAV authority, **no search assertion** |
| **mobile search discoverability (drawer)** | **NOT COVERED** | new gap |
| tenant isolation | COVERED | `test_store_isolation` |
| SEO noindex/follow | COVERED | `test_seo` |

Focused run this session: `test_product_list_view` + `test_u5_listing_filter_search` +
`test_g2_listing_context_and_chips` + `test_mobile_nav_drawer` + `test_u2a_global_header_system`
= **138 tests OK**; `test_store_isolation` + `test_seo` + `test_tenant_routing_seo` = **33 OK**.

The old plan's "pagination lacked independent certification": pagination is now
server/context-certified (3 tests). What is STILL uncertified at 937b6bd: page-number
**windowing** at scale and mobile-search discoverability.

## 20. Browser baseline

Read-only, bundled chromium (`/opt/playwright/chromium-1232/chrome-linux64/chrome`),
`--host-resolver-rules=MAP rastisi-fashion-test.rastisi.localhost 127.0.0.1`, real published
tenant (100 products), RTL, viewports 1440×900 / 768×1024 / 390×844. **console_errors: 0**, no
horizontal overflow anywhere. Temporary harness was created and **deleted** (untracked; working
tree clean).

| Check | 1440 | 768 | 390 |
|---|---|---|---|
| PLP status | 200 | 200 | 200 |
| cards rendered (page 1) | 12 | 12 | 12 |
| pagination present / numbers | 10 / 8 | 10 / 8 | 10 / 8 |
| pagination rows | 1 | 1 | **2** |
| page=5 status / current | 200 / ۵ | 200 / ۵ | 200 / ۵ |
| search `?q=تیشرت` results | 5 | 5 | 5 |
| empty state (`?q=zzz`) | present | present | present |
| header search visible (mobile) | — | — | **false** |
| burger present | — | — | yes |
| **drawer search affordance** | — | — | **FAIL (0/0)** |

Plus curl checks: search/filtered = `noindex,follow`; plain listing indexable; no-JS
`href="?page=N"` links present; foreign-store category slug → 0 products.

## 21. Actual-gaps-only classification

| Area | Classification |
|---|---|
| Filter | REUSE AS-IS (minor test gap) |
| Sort | REUSE AS-IS |
| Pagination | SMALL REPAIR (windowing) + TEST GAP |
| Listing Header | REUSE AS-IS |
| Search Header | REUSE AS-IS |
| Empty State | REUSE AS-IS |
| Mobile Filter | REUSE AS-IS |
| **Mobile Search Entry** | **SMALL REPAIR** (biggest gap) |
| HTMX progressive enhancement | REUSE AS-IS |

No area is BLOCKED / ARCHITECTURE QUESTION. No LARGER REPAIR.

## 22. Recommended bounded design

**Mobile Search (biggest gap):**
- Option A — un-hide header `.search` on mobile.
- **Option B — RECOMMENDED** — add ONE `<form role="search" method="get"
  action="{% url 'catalog:product-list' %}">` with a labeled `<input type="search" name="q">`
  and a submit button, inside the existing `templates/partials/mobile_nav_drawer.html` (above the
  nav list). Posts to the SAME endpoint; no new route/backend/drawer. Fixes the default variant
  and any base.html page at the shared layer.
- Option C — no change (rejected: `legacy_default` genuinely has no mobile search).

**Pagination:**
- Option A — no change (functional but poor at scale).
- Option B — CSS-only (e.g. cap width / scroll) — doesn't fix "50 numbers".
- **Option C — RECOMMENDED** — bounded pagination window in `product_list_results.html`
  (e.g. `1 … 6 7 8 … 50`), keeping Previous/Next/Persian numerals/`querystring`/HTMX/no-JS links
  unchanged. Template-only; no view/model/migration change.

**Recommended ONE per gap:** Mobile Search → **Option B**; Pagination → **Option C**.
Plus TEST-GAP fills (brand/category-name search + `.distinct()`, `min_price>max_price`,
pagination windowing, mobile-drawer-search discoverability). YAGNI: no empty-state rebuild, no
accessibility framework, no filter-schema, no query-service.

## 23. Expected files

Minimum likely-changed files (predicted, **not edited**):
- `templates/partials/mobile_nav_drawer.html` — add the shared mobile search form (Option B).
- `apps/catalog/templates/catalog/partials/product_list_results.html` — bounded pagination window
  (Option C).
- `apps/storefront_builder/static/css/storefront_builder.css` and/or
  `apps/catalog/static/css/product_list.css` — small styling for the drawer search / windowed
  pagination (ellipsis).
- Existing focused tests: `apps/content/tests/test_mobile_nav_drawer.py` (drawer search
  discoverability), `apps/catalog/tests/test_product_list_view.py` /
  `test_u5_listing_filter_search.py` (pagination windowing, search-field, price-edge).
- Optionally the existing public browser QA harness under `tools/storefront_builder_qa/`.

Not proposed: new models, migrations, services, routes, or search backend.

## 24. Expected migrations

**NONE.**

## 25. Risks / blockers

- No blockers. No architecture question.
- Option B risk: the drawer only exists on `legacy_default`/base.html — it does NOT cover the 9
  storefront_builder sibling variants, but those already have mobile search, so this is correct
  scoping, not a miss. (If a future ruling wants a single mobile-search authority across ALL
  variants, that would be a separate, larger task — out of Task 7 scope.)
- Option C risk: pure template windowing must preserve exact query-string/HTMX/no-JS/Persian-numeral
  behavior; keep `page_range` semantics, just render a bounded slice + ellipses.
- Two stores exist in the QA DB, so tenant resolution must use the exact host
  `rastisi-fashion-test.rastisi.localhost` (compatibility fallback is off) — noted for any
  implementation browser QA.

## 26. Final classification

Task 7 = **BOUNDED HARDENING / REPAIR**, migrations NONE. Two SMALL REPAIRS
(mobile search entry via the existing drawer; bounded pagination window) + targeted test-gap
fills. Everything else REUSE AS-IS. The canonical pipeline, tenant isolation, SEO, HTMX/no-JS,
product-card reuse and header/empty-state authorities are all sound and must not be duplicated.

TASK 7 IMPLEMENTATION STARTED: NO
