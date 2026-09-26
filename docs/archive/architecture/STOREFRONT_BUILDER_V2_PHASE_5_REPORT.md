# Storefront Builder V2 — Phase 5 Completion Report

**Phase**: 5 — Product / Listing / Collection / Search / Cart Composition
**Base SHA**: `034b42d8e54d39e38db8accab325be6eefee03ab` (canonical synchronized HEAD confirmed by owner before this phase)
**Final commit this phase**: `5e5ebc7`
**Commits this phase**: 10 (`c0d1dca` … `5e5ebc7`, listed below)

```
5e5ebc7 Phase 5: fix duplicate breadcrumb on collection page
170b00e Phase 5 Slice 8: end-to-end lifecycle tests for the 5 composed pages
871a11f Phase 5 Slice 7: wire render_items into the 5 public templates + default compositions
b3b0643 Phase 5 Slice 6: cart_items + cart_summary context-aware sections
145fe15 Phase 5 Slice 5: collection_header + collection_products context-aware sections
aa25da5 Phase 5 Slice 4: product_listing context-aware section (listing + search)
fb835d8 Phase 5 Slice 3: product_detail context-aware section types
dd162aa Phase 5 Slice 2: route-context passthrough for context-aware sections
4b3c8a3 Phase 5 Slice 1: page-type allowlist for section types
c0d1dca Phase 5 read-only gap audit: Product/Listing/Collection/Search/Cart
```

## 1. Initial audit findings

Full detail: `docs/architecture/STOREFRONT_BUILDER_V2_PHASE_5_AUDIT.md` (committed `c0d1dca`).

The headline finding: Phase 1B already gave all six `StorefrontPage` types ordered
`StorefrontSection` rows, a shared registry, and a `build_page_render_items()` service
— but the five non-home public templates (`product_detail.html`, `product_list.html`,
`collection_detail.html`, `collection_index.html`, `cart_detail.html`) never consumed
`render_items` at all. Their bodies were 100% hardcoded Django template markup, wired
directly to view-computed context (`product`, `page_obj`, `cart`, …). The builder could
already store composition data for these pages; nothing rendered it. That gap —
"computed but not rendered" — was the single root cause behind every downstream Phase 5
task. No new page types, no new renderer, no new architecture were needed.

Classification per the audit's required breakdown:
- **ALREADY EXISTS**: `StorefrontPage` per-type rows, `StorefrontSection` ordering,
  `section_registry`, `render_service.build_page_render_items` (home-only usage),
  Draft/Published lifecycle, `responsive_section_wrapper.html`, family bypass for
  product_detail (11 templates via `product_page_variant`).
- **PARTIAL**: registry had no page-type restriction (any section type could be added
  to any page); `build_page_render_items` had no route-context passthrough mechanism.
- **MISSING**: 9 new section types (product_main, product_description, product_video,
  related_products, product_listing, collection_header, collection_products, cart_items,
  cart_summary); default non-home compositions; the render_items wiring itself; a
  `build_default_render_items` fallback for never-published stores.
- **OUT OF SCOPE**: refactoring cart/order business logic, refactoring all 11 legacy
  families, a separate `search_results` section type (deliberately shared with
  `product_listing` — see §7).
- **LEGACY COMPATIBILITY BOUNDARY**: documented in full in §9 below.

## 2. Real gaps implemented

1. Page-type allowlist on `SectionDefinition` + server-side enforcement in
   `storefront_section_add` (400 rejection, not just UI hiding).
2. Route-context passthrough: `build_page_render_items(page, store, page_context=None)`
   and a parallel `_CONTEXT_AWARE_BUILDERS` dict so 17 pre-existing section types are
   byte-for-byte unaffected.
3. 9 new section types + templates (see §3).
4. Default non-home compositions, seeded on bootstrap and backfilled via migration
   `0011_seed_default_non_home_sections.py` for pre-existing stores.
5. `build_default_render_items` — synthesizes the same default composition from unsaved
   `StorefrontSection` instances for stores that have never published a V2 layout, so
   legacy body content keeps rendering unchanged (see §10, regression found and fixed).
6. `_render_cart_container` rebuilt so htmx quantity-update/remove round trips re-run the
   full composed render pipeline instead of a hardcoded partial — merchant reorder/hide
   settings now survive every cart interaction, not just the initial page load.

## 3. Section architecture (new types)

| Section key | Page types | removable | Notes |
|---|---|---|---|
| `product_main` | product_detail | No | Gallery, title, price, variant selector, qty, add-to-cart, stock, SKU — kept as **one** structured block per the master prompt's explicit instruction not to split the core purchase area into 15 tiny blocks |
| `product_description` | product_detail | Yes | Long description / specs / reviews tabs |
| `product_video` | product_detail | Yes | Product video block (YouTube/native) |
| `related_products` | product_detail | Yes | Related/recommended grid |
| `product_listing` | listing, search | No | Filters, sort, grid, pagination, promo — **shared** between Listing and Search (see §7) |
| `collection_header` | collection | Yes | Hero image/title/description of the *current* collection |
| `collection_products` | collection | No | Product grid for the current collection |
| `cart_items` | cart | No | Line items, qty controls, remove |
| `cart_summary` | cart | Yes | Subtotal, totals, checkout CTA |

`removable=False` follows the same precedent as the header's `show_cart`: removing the
section would leave the page unable to fulfill its core function (no purchase path, no
product grid, no way to see/remove cart contents).

## 4. Context-aware rendering architecture

Every context-aware section builder receives the exact `page_context` dict the public
view itself already computed for that route (e.g. `build_product_detail_context`'s
return value) — zero extra queries, same tenant scoping the view already enforced.
Preview reuses the identical builders via `_preview_page_context`, substituting a
representative object (newest product, first collection, etc.) for the route-resolved
one. Transient objects (`current_product`, `current_collection`, search query/queryset,
cart) are **never** persisted into `StorefrontSection.settings` — confirmed by dedicated
tests (`SearchQueryAndCollectionIdentityStayRouteContextTests`) that publish a
composition, change the route context (different product/search term/collection), and
assert the rendered output tracks the new route context rather than anything stored at
publish time.

## 5. Page default compositions

Seeded via `bootstrap_service.apply_default_non_home_sections` (idempotent — only fills
empty pages, never overwrites merchant customization) and backfilled onto all
pre-existing `StorefrontLayoutVersion` rows via migration `0011`. New Draft versions
inherit compositions automatically through the existing generic
`_clone_version_content` mechanism — no new cloning code was needed. Verified: a fresh
store's first Draft has non-empty product_detail/listing/collection/search/cart pages
immediately (`test_first_draft_non_home_pages_are_not_empty_by_default`).

## 6. Allowlist rules

`is_section_allowed_on_page(section_key, page_type)` checks `SectionDefinition.page_types`
(defaults to `ALL_PAGE_TYPES` for the 17 pre-existing general-purpose types, restricted
to specific pages for the 9 new types). Enforced server-side in
`storefront_section_add` (HTTP 400 on violation) — not just hidden in the editor UI.

## 7. Tenant isolation & rendering safety

- All context builders operate only on the `store` and `page_context` passed in; no
  section settings can carry a foreign store's object ID (nothing is stored at all for
  route-resolved objects — see §4).
  `CrossStoreCompositionIsolationTests` publishes divergent compositions on two stores
  and asserts each store's public pages render only its own composition/products.
- Search and Collection deliberately resolve their subject from the **route**, never
  from stored settings: Collection page layout describes *how* a collection renders,
  the URL determines *which* collection (no fixed collection ID in the page structure).
  `product_listing` is intentionally reused for both Listing and Search rather than
  creating a separate `search_results` type — same rendering shape, only the
  view-supplied queryset differs, so a second type would have been pure duplication.
- Fail-safe on absent context: if `page_context` lacks the expected key, context-aware
  builders return an empty/absent render item rather than raising or querying broadly.
- No new raw SQL, no N+1 introduced — all new context builders reuse the exact
  queryset/services the pre-existing hardcoded views already called.

## 8. Draft / Published lifecycle

Verified per page type in `DraftPublishedPreviewPublicLifecycleTests`: builder edits
target Draft only, public routes render Published only, Preview renders Draft (staff-only,
`is_merchant_preview` banner preserved), and `publish()` swaps the pointer atomically —
edits made after a publish are invisible publicly until the *next* publish. Note: since
`publish()` nulls `layout.draft_version`, every subsequent publish in a test must first
call `get_or_create_draft()` — this bit several new tests during development (see git
history) and is now a documented gotcha for Phase 6+.

## 9. Legacy family boundary

Phase 5's render_items wiring applies to the **canonical** (non-family) rendering path
only. The pre-existing 11-family `product_page_variant` bypass for Product Detail is
untouched — those 11 templates still render their own hardcoded bodies exactly as
before Phase 5, independent of `render_items`/section composition. Listing, Collection,
Search, and Cart never had a family-variant bypass to begin with (confirmed via audit),
so Phase 5's composition wiring is simply their only rendering path — no bypass
asymmetry was introduced there. No family template was modified. No 12th family, no
new renderer architecture, no family-specific business logic was added, per standing
policy.

## 10. Product variant / media / cart preservation

- Variant selection (Alpine `variantSelector`), variant-scoped gallery images, price/stock
  updates, and legacy-vs-axis variant handling are unchanged — `product_main.html` is an
  extraction of the pre-existing hardcoded markup, not a rewrite. Verified live in browser
  QA: clicking a color swatch correctly updates the active swatch state, the "رنگ: …"
  label, and the price/stock box via Alpine reactivity, with zero console errors.
- Product video rendering (`product_video.html`) is a verbatim extraction.
- Cart correctness (totals, quantity, coupon/shipping if present) was not touched —
  Phase 5 only changed *how* the cart's existing line-items/summary markup is composed
  and reordered, never the business logic that computes them. The htmx quantity-update/
  remove round trip was rebuilt to re-run the full composed render (`_render_cart_container`)
  instead of a hardcoded partial, so merchant-configured section order survives every
  interaction — verified by both a dedicated Django test
  (`CartItemUpdateUsesComposedCartSectionsTests`) and live Playwright interaction
  (real htmx increment/remove round trips, screenshot-confirmed).
- **Regression found and fixed proactively** (not by the user): naively wiring
  `render_items` into the 5 templates would have made any store that has *never*
  published a Storefront V2 layout render **blank** product/listing/collection/cart
  pages — this content was previously unconditional, gated on nothing. Caught by the
  pre-existing `LegacyStoreRoutesUnaffectedTests` contract. Fixed via
  `render_service.build_default_render_items`, which synthesizes the same default
  composition from unsaved `StorefrontSection` instances with zero new template code.
  The identical gap independently existed in `dashboard/views.py::product_preview`
  (staff-only unpublished-product preview never called
  `build_universal_storefront_context` at all) — fixed the same way.

## 11. Search / Collection route-context discipline

Confirmed via `SearchQueryAndCollectionIdentityStayRouteContextTests`: a search term or
collection identity is never written into `StorefrontSection.settings` at any point —
publishing a composition and then issuing requests with different search terms /
different collection slugs produces correctly different rendered output, proving the
subject is resolved fresh from the route on every request.

## 12. Tests run

- New: `test_phase5_composition_lifecycle.py` (16 tests: Draft/Published/Preview/Public
  lifecycle, cross-store isolation, search/collection route-context discipline,
  reorder/hide/responsive settings reaching the public page).
- New/extended: `test_section_registry.py`, `test_render_service.py`, `test_views.py`,
  `test_cart_views.py::CartItemUpdateUsesComposedCartSectionsTests`,
  `test_bootstrap_service.py::DefaultNonHomeSectionsTests`,
  `test_page_backfill_migration.py::SeedDefaultNonHomeSectionsMigrationFunctionTests`.
- Fixed (pre-existing tests whose "5 non-home pages always start empty" assumption
  Phase 5 deliberately supersedes): 4 tests in `test_family_default_section_reset.py`,
  1 in `test_page_backfill_migration.py`, `test_phase_1b_render_and_context.py`'s
  `BuildPageRenderItemsForNonHomePagesTests`.
- Full `apps.storefront_builder` suite (814 tests): **OK** — run twice this phase given
  the broad blast radius of the default-composition change (justified as
  directly-affected given scale, not routine practice).
- Cross-app `apps.catalog apps.cart apps.dashboard` suite: run in background, completed
  with no visible failures.
- `manage.py check` and `makemigrations --check --dry-run`: clean throughout.
- Targeted re-run after the final breadcrumb fix (23 tests: collection context-aware
  render/preview + full lifecycle suite): OK.

## 13. Browser QA

Playwright, desktop (1440×900) and mobile (375×812), against a dedicated QA store
(`sfb-phase4-qa`) with variant, video, and plain fixture products:

- **Product Detail (variant product)**: gallery, 4 thumbnails, red/blue color swatches,
  price/stock box, quantity stepper, add-to-cart, trust badges, description/spec/review
  tabs, related-products grid — all present both viewports. Live swatch-click
  interaction confirmed: clicking a swatch updates the active swatch ring, the
  "رنگ: …" label, and the price/stock box reactively via Alpine, zero console errors.
- **Product Detail (video product)**: product-video section renders with YouTube badge.
- **Listing**: filter form, sort, product grid populated, pagination — both viewports.
- **Search**: query executes, status 200, both viewports.
- **Collection**: hero (image/title/description), product grid — both viewports. Found
  and fixed a duplicate-breadcrumb bug (`collection_header.html` was rendering its own
  breadcrumb in addition to the wrapping template's) via screenshot inspection;
  re-verified fixed with a single breadcrumb row after the fix.
- **Cart**: add-to-cart → view → htmx quantity increment (totals update in place) → htmx
  remove (empty-cart state shown) — all via live round trips, both viewports.
- Zero console errors / zero page errors across every page and viewport tested.

## 14. Known limitations

- The 11-family `product_page_variant` bypass for Product Detail remains entirely
  outside Phase 5's composition system, by design (see §9).
- Variant-specific gallery image swapping was not deepened in this phase — the QA
  fixture's two variants share the same product image set, so only price/stock/label
  reactivity was directly re-verified live; the underlying `variantSelector` component
  itself was not modified from its pre-Phase-5 behavior.
- No new automated test asserts against visual duplication (the breadcrumb bug was only
  caught via screenshot review) — this class of bug is inherently outside what the
  Django test suite can catch; browser QA remains the relevant gate for it.

## 15. Phase 6 prerequisites

Section registry, allowlists, context-aware builder pattern, and default-composition
mechanism are all now generalized and reusable — Phase 6 (Preset System) can define
presets as data (ordered section-key + settings lists per page type) without needing any
further renderer or registry changes.

## Owner-local Heavy Gate (PowerShell)

```powershell
cd <repo-root>
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.storefront_builder
python manage.py test apps.catalog apps.cart apps.dashboard
```

## Report status

`IMPLEMENTATION_COMPLETE`
`TARGETED_RUNTIME_VERIFIED`
`BROWSER_VERIFIED`
`OWNER_HEAVY_GATE_PENDING`
