# Storefront Builder V2 — Phase 1B Pre-Implementation Audit

**Branch:** `claude/family-visual-fidelity-fix`
**Base commit:** `99e12fa631d03d038c381fdba0b8585fc565a54d`
**Status:** Read-only audit, produced before any Phase 1B code change. All evidence `SOURCE_ONLY` (obtained by direct source inspection this session; no Django runtime available in this sandbox — see the Phase 0.5/1A reports for the same, still-current constraint).

This document is the mandatory Step 1 deliverable for Phase 1B ("Read-only audit first... continue implementation only if the architecture is clear"). It supersedes nothing in the prior `STOREFRONT_BUILDER_V2_ROUTE_RENDERER_MAP.md` (that document remains factually accurate as of its own commit) — it re-verifies the same routes at current HEAD, after Phase 1A's `StorefrontPage` introduction, and adds the specific facts Phase 1B's implementation depends on.

---

## 1. Public storefront routes/views for all six page types

| Page type | URL pattern | View | Template rendered |
|---|---|---|---|
| `home` | `path("", views.home)` — `apps/catalog/urls.py:8` | `apps.catalog.views.home()` | `catalog/home_visual.html` (published) or `catalog/home.html` (legacy) |
| `product_detail` | `path("products/<uslug:slug>/", views.product_detail)` — `apps/catalog/urls.py:11` | `apps.catalog.views.product_detail()` | `catalog/product_detail.html` |
| `listing` | `path("products/", views.product_list)` — `apps/catalog/urls.py:9` | `apps.catalog.views.product_list()` | `catalog/product_list.html` (or `catalog/partials/product_list_results.html` fragment on `HX-Request`) |
| `collection` | `path("collections/", views.collection_index)` / `path("collections/<uslug:slug>/", views.collection_detail)` — `apps/catalog/urls.py:13-14` | `collection_index()` / `collection_detail()` | `catalog/collection_index.html` / `catalog/collection_detail.html` |
| `search` | **No dedicated route.** Same URL/view as `listing` (`products/`), distinguished only by the presence of a `?q=` querystring parameter, read inside `apps.catalog.views._filtered_products()` | `apps.catalog.views.product_list()` | Same as `listing` |
| `cart` | `path("", views.cart_detail)` mounted at `cart/` — `apps/cart/urls.py:8` | `apps.cart.views.cart_detail()` | `cart/cart_detail.html` |

Category-filtered listing is confirmed to be the same route/view as plain Listing, distinguished only by a `?category=` parameter — not a separate URL, exactly as the prior route map documented. This audit treats "category-filtered listing" and "search" both as variants of the single `listing` route, and maps them onto `StorefrontPage.PageType.LISTING` and `.SEARCH` respectively based on whether a search query is present — this is a Phase 1B design decision, not a pre-existing fact, and is documented as such in the Phase 1B report.

Store/tenant resolution is uniform across all catalog/cart routes: every one of `home`, `product_detail`, `product_list`, `collection_index`, `collection_detail` calls `apps.stores.resolution.resolve_store_for_storefront(request)` at the top of the view — fail-closed (`Http404` for unresolvable host, `PermissionDenied`→403 for a real-but-not-publicly-visible store). `cart_detail` does not call this directly; it resolves the store indirectly via `apps.cart.services.pricing.cart_totals()` → `resolve_store_for_service(request)`, which is the same underlying resolver family but without the 404-vs-500 distinction `resolve_store_for_storefront` adds. This is a pre-existing asymmetry, not something introduced or fixed by Phase 1B.

---

## 2. Every public storefront base template/shell currently used

- **`templates/base.html`** — the one, universal root template. Every public storefront template `{% extends %}` this, directly or (after Phase 1B) indirectly. Contains its own hardcoded `{% block header %}` (lines ~40-172) and `{% block footer %}` (lines ~175-268) — no `{% if SHOP_FAMILY %}` branching anywhere inside these two blocks.
- **`apps/storefront_builder/templates/storefront_builder/partials/page_shell_header.html`** and **`page_shell_footer.html`** — the shared, Family-aware shell partials. Each starts with `{% if SHOP_FAMILY %}{% include SHOP_FAMILY.header_variant %}{% else %}...canonical shared markup...{% endif %}`. Documented in the partial's own comment as "the single implementation shared by the public Storefront (`home_visual.html`) and the Builder Preview (`preview.html`)" — **prior to Phase 1B, this is true for exactly those two templates and no others.**
- **Confirmed at current HEAD:** `catalog/home_visual.html` and `storefront_builder/preview.html` are the only two templates in the entire repository that `{% include %}` these partials. `catalog/home.html` (legacy), `catalog/product_detail.html`, `catalog/product_list.html`, `catalog/collection_index.html`, `catalog/collection_detail.html`, and `cart/cart_detail.html` all `{% extends "base.html" %}` directly with **zero** `{% block header %}`/`{% block footer %}` override — confirmed by direct inspection of each file's top-level structure this session.

---

## 3. Every place choosing family/template/shell/header/footer/appearance tokens

- **Family (`SHOP_FAMILY`)**: injected by `apps.core.context_processors.shop_settings()` — a context processor registered globally in `shop_core/settings.py`'s `TEMPLATES` config, so it runs on **every** template render regardless of route. It resolves `family_slug` via `_global_identity_version(request, store_id)` (falls back to independently re-querying the store's published `StorefrontLayout` if `request.storefront_appearance_version` isn't set), then `family_registry.get_family(family_slug)`. Dispatch is template-level (`{% if SHOP_FAMILY %}{% include SHOP_FAMILY.header_variant %}`), not a Python `if/elif` anywhere.
- **Global color/font/radius/motion/type-scale tokens**: same `shop_settings()` processor, same `_global_identity_version` source — **already reach every route today**, home or not, published-layout-aware or not (falls back to live `ShopSettings` for stores with no published layout). This part of the "appearance" story is *not* the bug Phase 1B targets.
- **Structural home-only tokens** (`content_width`, `grid_density`, `hero_style`, `card_shadow`, `card_hover` — the legacy 10-Template system's DOM-agnostic CSS tokens): sourced by `_versioned_appearance(request)`, which **only** activates when `request.storefront_appearance_version` is explicitly set. Confirmed: the only two call sites that ever set this attribute are `apps.catalog.views.home()` (published branch, line ~79) and `apps.storefront_builder.views.storefront_preview()`. This is an **explicit, documented architecture decision** (comment in `apps/core/context_processors.py::_versioned_appearance`, citing "هویتِ طراحیِ سراسری در برابرِ ساختارِ صفحه‌ی اصلی" — global identity vs. home-page structure) — Phase 1B must not change this; it is unrelated to the header/footer shell bug and intentionally stays home-only.
- **Header/footer config (`header_config`/`footer_config`)**: only ever read from a `StorefrontLayoutVersion` by the two views above, and only ever passed into a template as `layout_header_config`/`layout_footer_config` by those same two call sites. No other public view reads or passes these today.

---

## 4. Current use of `build_render_items`, `StorefrontLayoutVersion`, `published_version`, `StorefrontPage`, family registry/renderers

- **`build_render_items(version, store)`** (`apps/storefront_builder/services/render_service.py`) — current body calls `version.home_page()` internally, then iterates `home_page.sections.filter(is_active=True).order_by("order", "id")`. Its own docstring explicitly states the signature is frozen at `(version, store)` "because both production call sites pass a version, not a page" — both call sites being `apps.catalog.views.home()` and `apps.storefront_builder.views.storefront_preview()`. **This function today can only ever render the home page's sections — it has no way to target any other `StorefrontPage`.**
- **`StorefrontLayoutVersion.home_page()`** — `self.pages.get(page_type=StorefrontPage.PageType.HOME)`, a hard `.get()` with no `try/except` around it anywhere it's called (relies on `StorefrontPage.ensure_version_pages()` having already guaranteed the row exists via `StorefrontLayoutVersion.save()`'s override).
- **`StorefrontLayoutVersion.sections`** (aggregating `@property`) — spans **all six pages**, kept explicitly only for old test backward-compatibility; its own docstring instructs new code to never use it and to call `version.pages.get(page_type=...).sections` explicitly instead.
- **`StorefrontSection.__init__`'s `version=` kwarg shim** — resolves to `page = version.pages.get(page_type=HOME)` unconditionally. Any Phase 1B (or later) code that constructs a `StorefrontSection` for a non-home page **must** pass `page=` explicitly — passing `version=` would silently misfile it onto Home. Flagged as a standing gotcha in the Phase 1A report; still true, still relevant, since Phase 1B is the first phase where non-home pages become externally observable.
- **`published_version`** — read directly off `StorefrontLayout` by exactly two call sites (`home()`, `_global_identity_version`), both filtering `StorefrontLayout.objects.filter(store=..., uses_visual_storefront_layout=True, published_version__isnull=False)` — this exact filter is duplicated verbatim in both places today. Phase 1B's central resolver (§ Implementation Requirements A/B below) removes this duplication.
- **Family registry / renderers** — `family_registry.py`'s 11 `FamilyDefinition`s are consumed exclusively via the `SHOP_FAMILY` template variable described in §3; no Python code in any view dispatches on family. Phase 1B introduces no new dispatch mechanism and does not touch `family_registry.py`, `preset_registry.py`, or `appearance_registry.py`.

---

## 5. Where the same Store currently renders different shells depending on route — the exact bug

For a single Store that has published a Builder layout (`uses_visual_storefront_layout=True`, `published_version` set) **and** has a `family_slug` configured:

- **Home** (`catalog/home_visual.html`) renders through `page_shell_header.html`/`page_shell_footer.html`, which resolve `{% include SHOP_FAMILY.header_variant %}` — a genuinely different DOM file per family (e.g. `storefront_builder/partials/families/modern_fashion/header.html`).
- **Product Detail, Product Listing, Search, Collection Index/Detail, Cart** all render `base.html`'s own literal, hardcoded header/footer markup — the exact same DOM for every store, every family, with zero `{% if SHOP_FAMILY %}` branching inside those two blocks.
- **Legacy Home** (`catalog/home.html`, rendered for any store that has never published a layout) *also* gets `base.html`'s hardcoded shell — consistent with the other five routes, but inconsistent with the *same store's own* published-Home shell once it does publish.

This is the precise, confirmed mechanism behind the browser-QA observation this phase exists to eliminate: **a single store's Home and Collection pages can show genuinely different header/footer DOM**, not just different colors — because only two templates in the whole repository were ever wired to the shared shell partials, and every other public route independently extends `base.html` with no override at all.

---

## 6. Existing test coverage relevant to this bug/fix

- **`apps/storefront_builder/tests/test_page_shell.py`** — asserts the shared shell partials are used by both `storefront_preview` (staff Draft preview) and `catalog:home` (published) — **Home-route-only**, no assertion touches Product Detail/Listing/Collection/Cart.
- **`apps/storefront_builder/tests/test_public_homepage_integration.py`** — asserts legacy-vs-visual Home template dispatch, Draft/Published isolation on the public Home route, header/footer toggle behavior — again **Home-route-only**.
- **`apps/storefront_builder/tests/test_render_service.py`** — unit-tests `build_render_items(draft/published, store)` directly; assumes (and will continue to require) that calling it with a bare version always means "the home page's sections." Phase 1B's `render_service.py` change must preserve this exact external behavior for the existing function name/signature.
- **No existing test anywhere asserts anything about Product Detail's, Listing's, Collection's, or Cart's header/footer shell** — confirming this is a real, previously-uncovered gap, not a regression risk in the sense of "something already tested differently." Any Phase 1B test added here is net-new coverage, not a change to an existing contract.

---

## 7. Conclusion — architecture is clear, proceeding to implementation

The audit confirms:
1. The bug is exactly and only "only two templates ever wired to the shared shell" — not a deeper architectural problem requiring new models or a new render pipeline.
2. `StorefrontPage` (Phase 1A) already provides everything needed to resolve a page-type-scoped render target; no schema change is required for Phase 1B.
3. The fix can be additive and store-scoped-conditional: stores that have never published a Builder layout must keep rendering exactly as today (per the explicit non-goal "do NOT yet force every public route through the final V2 universal shell if that would visually change legacy stores").
4. `build_render_items`'s frozen signature can be preserved via a thin compatibility wrapper around a new, genuinely page-aware function — satisfying the explicit instruction not to break existing callers while still introducing a page-aware API.

Proceeding to implementation as scoped in the Phase 1B Implementation Plan / Report.
