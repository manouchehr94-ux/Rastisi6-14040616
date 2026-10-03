# Phase 5 Task 7 — Browse/Search/Filter/Sort Bounded Hardening — Implementation Report

## 1. Certified base

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Official branch: `feature/phase5-design-expansion`
- Certified Phase-5 checkpoint (merged Task 6): `937b6bd8885d56fee70c0bb9df85493eda6aeade`
- Working branch: `kiro/phase5-task7-browse-hardening` (created from the exact base above)

## 2. Classification

**BOUNDED HARDENING / REPAIR.** No design spec, no implementation-plan doc, no new
subsystem. Two production repairs + reuse/regression verification + focused test-gap fills.
Expected migrations: **NONE**.

## 3. Approved bounded design (as implemented)

- **Gap #1 — Mobile search discoverability (`legacy_default`).** The `legacy_default` header
  hides its `.search` bar at ≤680px and the shared Task-5 mobile drawer had no search
  affordance. Repair: include the ONE canonical accessible search partial inside the existing
  drawer, posting to the existing `catalog:product-list` endpoint. No new route/backend/form
  authority, no second drawer/overlay.
- **Gap #2 — Elided pagination.** The listing template rendered every page number
  (`page_obj.paginator.page_range`). Repair: keep the canonical Django `Paginator` and use its
  own `get_elided_page_range` to expose a bounded window; render Django's ELLIPSIS sentinel as a
  non-link separator; add the related approved a11y (semantic `<nav aria-label>` + `aria-current`).

## 4. Exact changed files

Production (small):
- `apps/catalog/views.py` — `build_product_listing_context` derives `pagination_range` via
  `paginator.get_elided_page_range(page_obj.number, on_each_side=0, on_ends=1)` and exposes
  `pagination_range` + `pagination_ellipsis` (`Paginator.ELLIPSIS`) in context.
- `apps/catalog/templates/catalog/partials/product_list_results.html` — iterate `pagination_range`
  instead of the full `page_range`; ellipsis is a non-link `<span class="ellipsis" aria-hidden>`;
  current page is `<span class="current" aria-current="page">`; wrapped in
  `<nav class="pagination" aria-label="صفحه‌بندی محصولات">`; numeric links keep the exact prior
  contract (querystring, `hx-get`/`hx-target="#product-results"`/`hx-push-url`/`hx-indicator`,
  no-JS `href`, Persian numerals, `aria-label` per page).
- `apps/catalog/static/css/product_list.css` — one `.pagination .ellipsis` rule (non-interactive
  separator).
- `templates/partials/mobile_nav_drawer.html` — `{% include %}` the canonical
  `_shared/search_form.html` with `field_id="mobile-drawer-search-input"`, before the nav list.
- `apps/core/static/css/layout.css` — minimal drawer-scoped `.mobile-nav-drawer__search` styling
  (inside the existing ≤680px drawer media block).

Tests:
- `apps/content/tests/test_mobile_nav_drawer.py` — `MobileDrawerSearchAffordanceTests` (7 new).
- `apps/catalog/tests/test_task7_pagination_hardening.py` — 13 new (context + template).
- `apps/catalog/tests/test_task7_search_filter_gaps.py` — 4 new (search `.distinct()`, min>max
  empty) — test-gap fills, no production change.

Browser QA:
- `tools/storefront_builder_qa/public_task7_qa.mjs` — extends the existing public storefront
  harness (same chromium/host pattern as `public_task5_qa.mjs`), Task-7 scenario only.

Docs/evidence:
- `docs/qa_evidence/storefront_design_engine/phase5/task7_discovery_report.md` (carried unchanged).
- `docs/qa_evidence/storefront_design_engine/phase5/task7_implementation_report.md` (this file).
- `docs/qa_evidence/storefront_design_engine/phase5/task7_browse_hardening/` (screenshots + JSON).

## 5. TDD RED evidence — mobile search

Before any production change, `MobileDrawerSearchAffordanceTests` failed exactly because the
drawer had no search: e.g. `AssertionError: '.../_shared/search_form.html' not found in [drawer]`
and `'mobile-drawer-search-input' not found`. After including the canonical partial: GREEN
(7/7). Guard tests (endpoint/`q` live in the shared partial; NAV authority preserved) also pass.

## 6. TDD RED evidence — pagination

Before the view/template change, `test_task7_pagination_hardening` had 8 failing tests:
`pagination_range`/`pagination_ellipsis` missing from context, no labelled `<nav>`, no
`aria-current` on the pagination span, ellipsis absent, and all page numbers still rendered
(page 15 of 20 still linked page 3). After GREEN: 13/13.

## 7. GREEN results (focused)

- `apps.content.tests.test_mobile_nav_drawer` — 19 OK (7 new + 12 existing).
- `apps.catalog.tests.test_task7_pagination_hardening` — 13 OK.
- `apps.catalog.tests.test_task7_search_filter_gaps` — 4 OK.

## 8. Regression tests

- Catalog listing/filter/search/chips/collection: `test_product_list_view` +
  `test_u5_listing_filter_search` + `test_g2_listing_context_and_chips` +
  `test_collection_public_views` — 64 OK.
- Drawer + Global Header system: `test_mobile_nav_drawer` + `test_u2a_global_header_system` — 103 OK.
- Product card, store isolation, SEO, tenant routing — see §12 (all OK).
- ZERO new failures introduced.

## 9. Browser QA (public storefront harness)

Real published `legacy_default` fashion tenant (`rastisi-fashion-test.rastisi.localhost`,
94 listing-visible products = 8 pages), bundled chromium, RTL, viewports 1440×900 / 768×1024 /
390×844. **SUMMARY: 33 PASS / 0 FAIL / 3 INFO, console_errors: 0.** Evidence:
`task7_browse_hardening/task7_browser_result.json` + screenshots.

## 10. Actual pagination parameters selected

`get_elided_page_range(number, on_each_side=0, on_ends=1)`.

Evidence-driven tuning (§10 of the prompt): the initial Django-native `on_each_side=1` still
wrapped the control to **2 rows at 390px** on the 8-page fixture (browser-measured:
`numericLinks:5, ellipsis:1, rows:2`). Switching to the tighter native window `on_each_side=0`
brought it to a **single row at every viewport** (`numericLinks:2, ellipsis:2, rows:1`) with no
horizontal overflow — no custom logic and no CSS page-hiding. At page 4 of 8 the window is
`قبلی 1 … 4 … 8 بعدی`.

## 11. Mobile pagination row / control measurements

| Viewport | numeric links | ellipsis | rows | overflow |
|---|---|---|---|---|
| desktop-1440 | 2 | 2 | 1 | none (sw=cw=1440) |
| tablet-768 | 2 | 2 | 1 | none (sw=cw=768) |
| mobile-390 | 2 | 2 | 1 | none (sw=cw=390) |

(Before the repair, discovery measured all 8 page numbers rendered, wrapping to 2 rows at 390px.)
Additional checks: labelled `<nav>` PASS at all viewports; ellipsis-not-link PASS (no `?page=…`);
HTMX Next updates URL to `?page=5` PASS; Prev/Next present PASS.

## 12. Mobile drawer search verification

At 390px: header `.search` is NOT the mobile entry point (`visible:false`); the Task-5 drawer
opens; exactly ONE `form[role="search"]` inside it with input `name="q"`, unique id
`mobile-drawer-search-input`, accessible name present; typing the real Persian query `تیشرت` and
submitting via the existing GET endpoint lands on `/products/?q=%D8%AA%DB%8C%D8%B4%D8%B1%D8%AA`
and renders 5 result cards; Task-5 overlay integrity intact (Escape still closes). Desktop
(1440/768) header search unchanged. Screenshots: `drawer-search-mobile-390.png`,
`drawer-search-results-mobile-390.png`.

## 13. HTMX / no-JS verification

- HTMX: pagination Next click updates the URL to `?page=5` and swaps `#product-results` in place;
  numeric links carry `hx-get`/`hx-target`/`hx-push-url`/`hx-indicator`.
- No-JS (JavaScript disabled context): pagination links keep a real `?page=` `href` (PASS); the
  drawer search form is a `method="get"` form with an `action` (PASS) so it submits normally.

## 14. Tenant-isolation verification

Re-ran `apps.catalog.tests.test_store_isolation` (and SEO/routing) — all OK. No new tenant
validation layer; `resolve_store_for_storefront` + the store-scoped `_filtered_products`
pipeline remain the canonical, untouched owners. (Discovery already browser-verified a
foreign-store category slug yields 0 products.)

## 15. Django / static gates

- `python manage.py check` → System check identified no issues (0 silenced).
- `python manage.py makemigrations --check --dry-run` → No changes detected.
- `git diff --check` → clean.

## 16. Migration proof

No model field/Meta changes; `makemigrations --check --dry-run` reports no changes. **Migrations: NONE.**

## 17. Architecture diff gate

`git diff --name-status <base>...HEAD` touches only: `apps/catalog/views.py`,
`apps/catalog/templates/catalog/partials/product_list_results.html`,
`apps/catalog/static/css/product_list.css`, `templates/partials/mobile_nav_drawer.html`,
`apps/core/static/css/layout.css`, three catalog/content test modules, the public QA harness,
and docs/evidence. Explicitly:
- no model changes / no migration
- no new route (search still `catalog:product-list`; no url change)
- no new search backend/service; `_filtered_products` q/category/brand/price/discounted/in_stock/
  sort logic unchanged
- no duplicate search-form authority — the canonical `_shared/search_form.html` is reused
- no second drawer
- Django `Paginator` still canonical; `get_elided_page_range` is Django's own — no custom window
  algorithm, no client-side pagination
- ProductCard authority unchanged (`product_card.html` still the single card path)
- tenant resolver unchanged
- Ready Template / registry / render_service / resource_source / models unchanged
- Task 8 not started

## 18. Final-review remediation — legacy base.html live-search context

**Defect found in independent Architect review (one blocker).** The canonical
search partial the drawer now reuses renders its REAL enabled GET form only when
`is_live_storefront` is truthy; otherwise it renders the disabled Builder
Preview branch. The universal shell passes `is_live_storefront=True` in its own
header include, but the **public legacy fallback** (`uses_universal_shell == False`,
where `templates/storefront_shell.html` renders `{{ block.super }}` → the
`templates/base.html` header) included the shared drawer **without** that flag,
and no context processor supplies it. So on the real legacy public path the
drawer search silently rendered the disabled preview form. This path was not
covered by the initial Task-7 browser QA.

**Root cause confirmed:** `templates/base.html` drawer `{% include %}` lacked the
live-storefront context; `grep is_live_storefront apps/*/context_processors.py`
→ not supplied anywhere.

**RED test (rendered-template):** `apps/content/tests/test_mobile_nav_drawer.py`
`LegacyBaseHtmlDrawerSearchIsLiveTests` — (a) rendering the drawer partial WITHOUT
the flag yields the disabled preview input (`...-preview`, `disabled`,
`onsubmit="return false"`) — reproducing the defect; (b) WITH the flag it renders
the live `role="search"` GET form to `/products/` with an enabled `name="q"`
input; (c) `base.html`'s include must pass `is_live_storefront=True`. Test (c)
failed RED before the fix.

**Minimal fix:** `templates/base.html` — change the drawer include to
`{% include "partials/mobile_nav_drawer.html" with is_live_storefront=True is_builder_preview=False %}`
(mirrors exactly what the universal shell passes to its own header include).
The canonical search partial was NOT modified; no duplicate markup; no context
processor added; no second drawer.

**Both public paths browser-verified at 390px (0 console errors):**
- **A. Universal `legacy_default`** (`page_shell_header`, `uses_universal_shell=True`,
  real fashion tenant) — drawer search live, `?q=تیشرت` → 5 results (§9/§12).
- **B. Legacy fallback** (`uses_universal_shell=False`, base.html `block.super`) —
  header search hidden; burger opens drawer; exactly one usable LIVE search form
  (`name="q"`, accessible name, NOT disabled); typed `تیشرت` → URL
  `/products/?q=%D8%AA%DB%8C%D8%B4%D8%B1%D8%AA` → 12 result cards; Task-5 Escape
  still closes the drawer. Result: **30 PASS / 0 FAIL / 0 console errors**.
  Evidence: `task7_browse_hardening/fallback/` (drawer-search + results screenshots +
  `task7_browser_result.json`). (Path B exercised via a throwaway unpublished
  store in the dev DB only — no seed/migration/committed fixture.)

**Remediation scope:** only `templates/base.html` (one include) + the RED
regression test + this report/evidence update. Pagination unchanged. No new
route/backend/service; canonical search partial still reused; Django Paginator
still canonical; no models/migrations; Ready Templates unchanged.

Final HEAD after remediation is recorded in the PR and the final response.

## 19. Task 8

TASK 8 NOT STARTED.
