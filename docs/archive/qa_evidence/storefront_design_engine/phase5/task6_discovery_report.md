# Phase 5 Task 6 — Storefront Showcase Discovery Report

> READ-ONLY discovery. No production code, tests, migrations, or branches were
> created. This file is intentionally UNTRACKED and must not be committed.

## 1. Certified checkpoint

- Repository: `manouchehr94-ux/Rastisi6-14040616`
- Official branch: `feature/phase5-design-expansion`
- Verified: `git fetch origin`; local HEAD == `origin/feature/phase5-design-expansion` == `c0ca174475bf19dd5c3ecac3857da479623e1e7d`; working tree clean (`## feature/phase5-design-expansion...origin/feature/phase5-design-expansion`, no dirty files).
- All evidence below reflects code at `c0ca174`.

## 2. Executive finding

**Should RastiSi build a new Showcase *section*? No — not as a new render/data section.** The four canonical families (`category_grid`, `brand_carousel`, `collection_tiles`, `product_section`) already exist as separate, kind-locked, schema-backed, Draft-aware, tenant-scoped sections that share ONE typed selection contract (`ResourceSource`) and ONE ownership validator. A new "Showcase" section that renders products OR categories OR brands OR collections behind one `content_type` switch would have to **re-own four heterogeneous render paths, four bespoke storage shapes, four template families, and four View-All resolvers** — i.e. it structurally pushes toward duplicating existing owners, which the Architecture Law forbids.

The genuine merchant problem the plan describes ("one simple place to add content, choose type/source/layout/title/count/View-All") is a **merchant-UX problem, not a rendering problem**. The cleanest architecture is a thin R4 **creation facade** (Option B) that helps a merchant pick a content type and then creates/configures the correct EXISTING canonical section — no new renderer, no new data authority, ZERO migrations.

A hard blocker also shapes this: **the R4 Inspector has NO conditional-field support** (§10). A single Showcase section with a `content_type` switch that changes which source/layout controls appear is therefore not expressible in the current Inspector without either (a) a new server-side per-section branch (like the existing `brand_carousel` hack) or (b) building conditional-field infrastructure that does not exist. Both are larger than the four sections already solving the same need cleanly.

Recommendation: **Option B (R4 "Showcase" creation facade over the four existing sections)**, or, if the PO wants nothing new at all, **Option A-minus (do not build Showcase; document the four families as the answer)**. Classification: **C (new R4 UX facade), S–M** — see §24/§28.

## 3. Existing equivalent concepts

No section named/equivalent to showcase, storefront_showcase, content_showcase, dynamic_section, universal_section, featured_content, content_block, mixed_content, collection_showcase, catalog_showcase, "section dispatcher", "resource-driven section", or generic content section exists. (`luxury_showcase` is a hero *variant* key; "Product Showcase" is only a doc label.)

`SECTION_REGISTRY` is a static Python allowlist (`_BASE_SECTION_REGISTRY`, `section_registry.py:2532–2966`) of **36 keys**: announcement_bar, hero_banner, fashion_lifestyle_hero, image_slider, single_banner, multi_banner, category_grid, featured_products, newest_products, best_sellers, discounted_products, amazing_offers, brand_carousel, promo_cards, rich_text, image_text, blog_posts, product_section, catalog_product_wall, trust_features, collection_tiles, quick_links, faq, testimonials, video_section, story_rail, newsletter, product_main, product_description, product_video, related_products, product_listing, collection_header, collection_products, cart_items, cart_summary.

Closest to a "dispatcher": `product_section.data_source` switches among `("collection","category","brand","manual","newest","discounted","best_sellers","most_viewed")` — but every branch resolves to **products**; it never renders categories/brands/collections as themselves. So no existing section makes Showcase redundant, and equally none is generic enough to *be* Showcase.

## 4. Canonical content-family inventory

Cross-cutting: the four each have a `settings_schema` (declarative Inspector layer) PLUS an imperative `validate_settings`/`default_settings` (the authority for persisted shape). The schema `source` field (type `resource_source`) is a UI abstraction translated back to legacy keys by `_with_resource_source` before the legacy validator runs. `_RESOURCE_SOURCE_AWARE_SECTION_KEYS = {product_section, brand_carousel, collection_tiles, category_grid}` (`section_registry.py:~778`).

### Products — `product_section`
- Registry `section_registry.py:2773–2789`: template `sections/product_section.html`; validator `_validate_product_section_settings` (`:297`); defaults `_product_section_defaults` (`:381`); schema `PRODUCT_SECTION_SCHEMA` (`:401`); `max_instances=None`; duplicable/removable True; inherits `ALL_PAGE_TYPES`; variants **3** (`carousel, grid, campaign_band`), `variant_setting_key="display_mode"`, default `carousel`.
- Schema fields: `title`(text), `source`(resource_source kind=product, default auto `newest`), `item_limit`(int 2–24, default 8, basic), `display_mode`(choice ×3), `show_view_all`(bool default True), `subtitle`(text advanced), `carousel_autoplay/interval_ms/show_arrows`(advanced), `header_position`(choice above/inside, advanced).
- Source/selection (richest): `data_source ∈ (collection, category, brand, manual, newest, discounted, best_sellers, most_viewed)`; single-ref sources (collection/category/brand) require `source_id`; `manual` requires `product_ids` (cap 60). Count key `item_limit`.
- Render `_product_section_context` (`render_service.py:518–528`) → `section_data_service.resolve_products(store, settings)` dispatch (`section_data_service.py:322–331`), all Store-scoped via `storefront_listing_products(store)`; unknown source → `([], None)` fail-closed. `PER_INSTANCE_SECTION_KEYS` cache keying.
- Template reuses `catalog/partials/product_card.html` (autoplay branch) and `catalog/partials/product_grid.html` (grid/campaign) — the canonical product card. View All via `resolve_products` per-source URL, overridden by section `destination` block. Empty-state delegated to `product_grid.html`. Mobile via `.rsec-cols` + responsive block.
- **This is the ONLY family that builds/goes through ProductCardData + Task-5 Quick View.**

### Categories — `category_grid`
- Registry `:2646–2684`; validator `_validate_category_grid_settings` (`:1704`); schema `CATEGORY_GRID_SCHEMA` (`:1741`); variants **11** (`grid, carousel, circular, image_strip, fashion_flat, fashion_mosaic, beauty_icons, chocolate_story, chocolate_badges, atelier_mosaic, luxury_shortcuts`), `variant_setting_key="display_mode"`, default `grid`; inherits ALL_PAGE_TYPES.
- Schema: `title`, `source`(kind=category, auto `all_active`), `display_mode`(choice ×11), `item_limit`(int 2–12, advanced).
- Selection: manual `category_ids` (cap 12, ordered) OR empty → active ROOT categories. No product concept.
- Render `_category_grid_context` (`render_service.py:182–226`), Store-scoped; media-first modes set `category.representative_media` (in-memory only). Returns `tiles`, `cream_category`, `top_categories`, `category_grid_settings`. No ProductCardData.
- Template `category_grid.html` (~205 lines): monolithic, branches per `display_mode`; per-tile link to `catalog:product-list?category=slug`; no section View-All; empty guarded by `{% if top_categories %}`.

### Collections — `collection_tiles`
- Registry `:2826–2839`; validator `_validate_collection_tiles_settings` (`:2001`); schema `COLLECTION_TILES_SCHEMA` (`:2033`); variants **2** (`grid, carousel`), **`variant_setting_key="tile_style"`** (note: not `display_mode`), default `grid`; inherits ALL_PAGE_TYPES.
- Schema: `title`, `source`(kind=collection, auto `all_active`), `tile_style`(choice ×2).
- Selection: manual `collection_ids` (cap 12) OR empty → all active collections.
- Render `_collection_tiles_context` (`render_service.py:411–436`): `MerchantCollection.objects.filter(store=store, ...)`; `annotate(item_count=Count("items"))`. Returns `collection_tiles = [{collection, item_count}]`. Renders collections as tiles, NOT the products inside.
- Template `collection_tiles.html` (~25 lines): per-tile link `catalog:collection-detail`; empty guarded by `{% if collection_tiles %}`. No section View-All.

### Brands — `brand_carousel`
- Registry `:2718–2732`; validator `_validate_brand_carousel_settings` (`:1937`); schema `BRAND_CAROUSEL_SCHEMA` (`:1969`); variants **3** (`grid, carousel, beauty_tabs`), `variant_setting_key="display_mode"`, default `grid`; inherits ALL_PAGE_TYPES.
- Schema: `title`, `source`(kind=brand, auto `all_active`), `display_mode`(choice ×3), `show_view_all`(bool default False).
- Selection: manual `brand_ids` (cap 24) OR empty → all active brands.
- Render `_brand_carousel_context` (`render_service.py:388–409`), Store-scoped; View-All only when `show_view_all` AND `destination.destination_type != "none"` → `resolve_destination_setting`. Returns `brands`, `brand_carousel_settings`, `view_all_url`. No ProductCardData.
- Template `brand_carousel.html` (~43 lines): per-brand link `catalog:product-list?brand=slug`; empty guarded by `{% if brands %}`.

## 5. Source/selection contracts

`ResourceSource` (`resource_source.py`) is a pure, typed, JSON-serializable value: `kind ∈ (product, category, brand, collection)`, `mode ∈ (auto, manual)`, `auto_rule`, `auto_parameters`, `manual_ids`. Manual caps `_MANUAL_ID_CAPS = {product:60, brand:24, category:12, collection:12}`. Auto rules per kind: product = `{newest, discounted, best_sellers, most_viewed}` ∪ `{by_category, by_brand, by_collection}` (source_id-param); brand/category/collection = `{all_active}` only.

**Heterogeneous underneath.** `ResourceSource` is an Inspector-facing façade over four bespoke persisted shapes: product↔`data_source`/`source_id`/`product_ids`; brand↔`brand_ids`; category↔`category_ids`; collection↔`collection_ids`. None of the four render builders import `resource_source`; they read the legacy keys directly. So the contract *spans* all four kinds, but the RENDER-time selection is genuinely per-domain. A Showcase must respect this — it cannot assume one normalized source format resolves all four; it must route to the right domain resolver. (Products are far richer: 8 sources incl. manual/dynamic/reference; the other three are only manual-ids-or-all-active.)

## 6. Layout taxonomy audit

Verified at `c0ca174` (old-plan numbers are correct but the enums are **not compatible**):
- Products (`display_mode`): `carousel, grid, campaign_band` (3)
- Categories (`display_mode`): `grid, carousel, circular, image_strip, fashion_flat, fashion_mosaic, beauty_icons, chocolate_story, chocolate_badges, atelier_mosaic, luxury_shortcuts` (11)
- Collections (`tile_style`): `grid, carousel` (2)
- Brands (`display_mode`): `grid, carousel, beauty_tabs` (3)

**Are these compatible behind one Showcase layout selector? NO.** The enums overlap only trivially (`grid`/`carousel`), the KEY differs (`tile_style` vs `display_mode`), and category's 11 modes are category-specific (circular icons, mosaics, story rails) that are meaningless for products/brands. A flat universal "layout" enum would be architecturally misleading and lossy.
Answer to §5's critical question: **Option C — no new Showcase layout taxonomy.** Expose the canonical underlying variant/layout field per content type (content-type-specific layout choices), reusing the existing enum values verbatim. Do NOT create a second parallel taxonomy.

## 7. Compatibility matrix

| | canonical section | source contract | layouts (existing enum) | title | count | View-All | destination block | background/spacing | appearance overrides | surfaces | product card |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Products | product_section | resource_source kind=product (8 data_sources + manual) | display_mode: carousel/grid/campaign_band | yes | item_limit 2–24 | yes (`show_view_all`) | yes (DESTINATION_AWARE) | yes | yes (CARD_AWARE) | HOME…all | YES (canonical card + Quick View) |
| Categories | category_grid | resource_source kind=category (manual ids / all_active) | display_mode ×11 | yes | item_limit 2–12 | no (per-tile links) | no | yes | no | all | no |
| Collections | collection_tiles | resource_source kind=collection (manual ids / all_active) | tile_style ×2 | yes | (no explicit count key) | no (per-tile links) | no | yes (APPEARANCE_OVERRIDE member) | yes | all | no |
| Brands | brand_carousel | resource_source kind=brand (manual ids / all_active) | display_mode ×3 | yes | (no explicit count key) | yes (`show_view_all`+destination) | yes (DESTINATION_AWARE) | yes | yes (APPEARANCE_OVERRIDE member) | all | no |

Invalid combinations typed validation must reject (evidence-based): a product content_type paired with category-only layouts (`circular/image_strip/fashion_*/beauty_icons/chocolate_*/atelier_*/luxury_shortcuts`) is INVALID; `beauty_tabs` is brand-only; `campaign_band` is product-only; a `tile_style` value on a non-collection type is INVALID. Count control only meaningfully applies to products (2–24) and categories (2–12); brands/collections have no count key today. View-All exists only for products & brands.

## 8. Render-service / data-loader reuse

`_CONTEXT_BUILDERS` (`render_service.py:717–743`, signature `(store, section)`) maps category_grid→`_category_grid_context`, brand_carousel→`_brand_carousel_context`, collection_tiles→`_collection_tiles_context`, product_section→`_product_section_context`. `_CONTEXT_AWARE_BUILDERS` (`:704–714`, signature `(store, section, page_context)`) are the PDP/listing/cart sections.

**Would calling these private builders from a Showcase be safe?** They are low-coupling but each: (a) is keyed to its own `section.settings` shape and legacy keys; (b) returns a *family-named* context key (`category_grid_settings`, `brand_carousel_settings`, `collection_tiles`, `products`) consumed by that family's template; (c) is Store-scoped via `store=section`'s store. They do not mutate persisted data (category media set in-memory only). Directly dispatching to them from a Showcase context builder is *technically* possible but creates **brittle template coupling**: the Showcase template would then need to branch on content_type and emit the matching family template's expected context keys — i.e. Showcase would re-implement each family's template contract. The clean latent extraction (if a real Showcase section were built) is a small `resolve_family(store, content_type, settings) -> (items, view_all_url, family_settings)` dispatcher that returns each family's existing context untouched — but that still leaves the TEMPLATE problem (§9). **Do not implement now.** This coupling is a strong argument for Option B (facade that just creates a real section) over Option A (dispatcher section).

## 9. Template/partial reuse

- `product_section` already reuses the canonical `catalog/partials/product_card.html` + `product_grid.html` — a real reusable body partial for products.
- `category_grid` / `brand_carousel` / `collection_tiles` each render a **monolithic section template** (no separate reusable body partial); category_grid especially is a big per-variant `<section>` switch.
- A dispatcher Showcase would therefore either (a) `{% include %}` the four full section templates — producing **nested section wrappers** (Showcase wrapper → responsive_section_wrapper → each family's `<section>`), which breaks R4 editor selection and doubles spacing/background wrappers; or (b) require extracting reusable *body* partials from category_grid/brand_carousel/collection_tiles (a non-trivial refactor of 11+3+2 layout variants). Neither is small.
- Cleanest current pattern: `product_section`'s "include a body partial, not a section" is the model. Only products already have it. **This is the single biggest hidden cost of a real Showcase section** and the reason Option B (no new template) is preferred.

## 10. R4 inspector capabilities — CONDITIONAL FIELDS DO NOT EXIST (highest risk)

`SettingsField` (`settings_schema.py:100–121`) has NO `depends_on`/`show_if`/`visible_when`/`condition`/`enabled_if`/dynamic-choices attribute. Grouping is only two flat tabs (`basic`/`advanced`). The Inspector renders once via `require_GET` `storefront_r4_section_inspector` (`r4_views.py:632`) → `section_inspector.html` → `settings_field.html`, which branches **only on `field.field_type`, never on section_key or another field's value**. Editing a field does NOT re-fetch/re-render the inspector; the JS posts `section.update_settings` and reloads the preview iframe only.

The ONLY existing "show/hide based on state" precedent is a **hardcoded server-side branch**: `brand_carousel`'s `show_view_all` is filtered out at inspector-render time by `_brand_view_all_control_offered(...)` (`r4_views.py:606–618`) keyed on persisted DB state — not generic, not reactive.

**Implication:** a single Showcase section whose controls change with `content_type` cannot be expressed cleanly. Options: (i) build generic conditional-field support (does not exist — large, out of Task-6 scope); (ii) copy the brand_carousel per-section server branch (a growing hack); (iii) avoid the problem entirely with Option B, where the merchant first picks a content type in a lightweight chooser and R4 then opens the EXISTING section's inspector (which already shows exactly the right controls). **Flag prominently: no conditional-field infrastructure.** Do NOT invent a second R4 form renderer.

## 11. Minimal merchant UX (proposed field map — only if a section were built)

If a Showcase section were built anyway, the smallest schema (smaller than the union of four) would be:

Basic:
- `content_type` — choice(products/categories/brands/collections) — universal — controls everything else — **BUT requires conditional fields (see §10)**
- `source` — resource_source, `kind` bound to `content_type` — maps to existing per-kind picker
- `layout` — choice, content-type-specific enum (reuse existing display_mode/tile_style values) — **not universal**
- `title` — text — universal (reuse `_MAX_SECTION_TITLE_LENGTH`)
- `count` — integer — products 2–24 / categories 2–12 only; omit for brands/collections
- `show_view_all` — boolean — products/brands only

Advanced (all AUTOMATIC via `_finalize_registry` if the key is added to the right frozensets — §14): `background`, `spacing`, `responsive`, `motion`, `appearance_overrides`, `destination`.

Net: the merchant-facing schema is smaller than the union, but the `content_type`→(source,layout,count,view_all) dependency is exactly what the Inspector cannot render conditionally today.

## 12. Page/surface compatibility

Page types are exactly **6** (`StorefrontPage.PageType`, `models.py:540–546`; mirror `PAGE_TYPE_*` + `ALL_PAGE_TYPES`, `section_registry.py:51–60`): `home, product_detail, listing, collection, search, cart`.

Old-plan surfaces vs reality:
- Home → `home` ✅
- Category → **no `category` page type**; closest is `listing` (product-list, filtered by `?category=`) — a real surface.
- Brand → **NO brand page type**. Brand is only a `?brand=` filter on `listing`. There is no brand landing page.
- Campaign Landing → **NO campaign/landing page type exists at all.**

All four families inherit `ALL_PAGE_TYPES` (allowed on all 6). Do NOT expand `ALL_PAGE_TYPES` to invent brand/campaign surfaces. Recommended Showcase surface allowlist = the real surfaces where merchandising belongs: `home`, `listing`, `collection` (and inherit ALL_PAGE_TYPES only if PO confirms cart/search/PDP placement is desired). "Campaign landing" is a **Product-Owner question** — it is not a current concept.

## 13. View-All / destination ownership

Canonical destination resolver: `apps/content/services.py:84 resolve_destination_setting(store, destination)`. Sections opt in via `DESTINATION_AWARE_SECTION_KEYS` (`section_registry.py:705`; includes product_section, brand_carousel). Per-source product View-All URLs are built in `section_data_service._resolve_*` (`reverse("catalog:collection-detail")`, `reverse("catalog:product-list")+?category=/?brand=`). Per-item links are the families' own template hrefs (`catalog:product-list?category=`, `?brand=`, `catalog:collection-detail`). **Showcase must reuse these; do NOT create a second URL/destination authority.**

## 14. Task-4 capability reuse

`_finalize_registry` (`section_registry.py:3038–3080`) runs at import over every section and composes `_with_resource_source → _with_destination → _with_responsive → _with_motion → _with_card → _with_layout → _with_background → _with_spacing → _with_appearance_overrides → _with_variant_validation`, then `_with_background_schema_field`, then unions `capabilities`.

- `responsive` (device hide/show) is **universal/automatic** for every section.
- Everything else is **automatic only for members** of the relevant allowlist frozenset: `BACKGROUND_AWARE_SECTION_KEYS` (`:967`), `SPACING_AWARE_SECTION_KEYS` (alias of background), `MOTION_AWARE_SECTION_KEYS` (`:1417`), `CARD_AWARE_SECTION_KEYS` (`:862`), `LAYOUT_WIDTH/HEIGHT_AWARE_SECTION_KEYS` (`:1351`/`:1359`), `DESTINATION_AWARE_SECTION_KEYS` (`:705`), `APPEARANCE_OVERRIDE_AWARE_SECTION_KEYS` (`:1273`), `_RESOURCE_SOURCE_AWARE_SECTION_KEYS` (`:778`).
- "Scope labels" (فقط این بخش) are automatic for every field.

So a new schema-backed section auto-gets `responsive`; to get background/spacing/appearance/motion/destination/card/resource_source it must be **explicitly added to those frozensets** (small, declarative, no new authority). Adding to `BACKGROUND_AWARE_SECTION_KEYS` grants both the validator block and the auto-projected background picker field. **No Showcase-specific background/typography/spacing/media authority should ever be created.**

## 15. Task-5 primitive reuse

`catalog/partials/product_card.html` is the single canonical product card; the Task-5 Quick View + `sfbOverlay` + `cart:add` + ProductCardData/pricing/badges/instance-safe `x-id` all live INSIDE it. `product_grid.html` renders through it. Every product rendering path goes through `product_card.html` (product_section grid/carousel/campaign all include it). **Therefore Showcase-in-Product-mode inherits ALL Task-5 behavior for free IFF it renders products through `product_section`'s existing path (product_card/product_grid).** There must be NO Showcase-specific product card. This is another argument for reusing `product_section` rather than a new renderer.

## 16. Tenant isolation (HIGH-RISK)

ONE shared DB-backed ownership guard: `section_data_service.validate_resource_source_ownership(*, store, source)` (fail-closed; `_require_owned_resource(model, store=store, source_id)` does a single Store-scoped `.exists()`; foreign and nonexistent ids fail identically). It is called by BOTH the legacy settings-save path and the R4 mutation service (`r4_mutation_service._validate_resource_source_ownership`, invoked only when the patch touches `source`). Per kind: products→`searchable_products(store)`; by_category/by_brand/by_collection→Category/Brand/MerchantCollection; brand/category/collection manual ids→their Store-scoped querysets. Render builders additionally filter `store=store`.

**Risk:** a Showcase must route every id through this SAME validator. If a dispatcher introduced its own validation boundary (or forgot to call it for a content_type), it would create a Store-A → Store-B leak vector. Option B eliminates this risk entirely (it reuses each section's existing mutation path unchanged). Any Option A/C design MUST reuse `validate_resource_source_ownership` verbatim and be covered by an explicit cross-store RED test per content_type.

## 17. Edge states

Already owned by canonical layers — do NOT reinvent:
- zero items / fewer than count: each family template guards `{% if top_categories/brands/collection_tiles/products %}`; product_grid has its own empty `<p>`.
- deleted/foreign/stale ids: `validate_resource_source_ownership` fail-closed at write; render querysets filter `is_active=True` + `store=store` so a since-deleted/deactivated id silently drops.
- inactive/out-of-stock product, missing brand/category image: handled inside `product_card.html` / each family template today.
- collection with no products: `item_count` annotation = 0, tile still renders (links to its page).
- invalid source/layout: coerced to safe defaults by each validator (`display_mode`→default, unknown data_source→`([],None)`).

## 18. Performance / query risks

Each builder is already bounded: category_grid slices `[:item_limit]`; brand/collection use single Store-scoped querysets; collection_tiles uses `annotate(Count("items"))` (no N+1); product_section goes through `resolve_products` + `storefront_listing_products(store)` (the canonical listing queryset with its select/prefetch). A dispatcher that calls the existing builders inherits their query shape unchanged. Material risk only if a Showcase re-implemented selection instead of delegating. No optimization needed now.

## 19. Ready-Template / DNA impact

The four families are composed in `layout_preset_registry.py` (PresetSectionEntry rows for the golden/industry presets) and `a8_ready_templates.py` (`A8_READY_TEMPLATES`). Industry template DNA also lives under `apps/catalog/industry_templates/` + `seed_industry_templates`. **Strong default: Task 6 should be ADDITIVE only** — do NOT rewrite existing preset/Ready-Template compositions to use Showcase. Recipe adoption (if ever) belongs to later curation (Task 10/13/16). Replacing the four families in presets would destroy template DNA and is out of scope.

## 20. Existing test inventory

storefront_builder/tests: `test_section_registry.py`, `test_render_service.py`, `test_r4_settings_schema.py`, `test_r4_inspector.py`, `test_r4_mutation_api.py`, `test_r4_resource_source.py`, `test_r4_resource_picker.py`, `test_phase4_task2_resource_source_ownership.py`, `test_r4_store_appearance_*` (validation/mutations/rendering/persistence/registry/contracts/compatibility), `test_r4_foundation.py`, `test_r4_vertical_slice.py`, `test_r4_appearance_overrides.py`.
catalog/tests: `test_a8_product_card_presentations.py`, `test_product_card_service.py`, `test_product_card_cover_image.py`, `test_collection_service.py`/`test_collection_models.py`/`test_collection_integration.py`/`test_collection_public_views.py`, `test_brand_service.py`, `test_category_schema_service.py`, `test_product_detail_view.py`, `test_product_list_view.py`.

## 21. Minimal future TDD plan (for whichever option is approved)

HIGH-RISK (must be RED first):
- Cross-store tenant isolation: chosen source id from Store B never resolves/renders on Store A — one test per content_type (or per created section type in Option B). Reuse `validate_resource_source_ownership`.
- Data authority: the created/dispatched content resolves through the EXISTING resolver (no second Product/Category/Brand/Collection query authority); ZERO migrations assertion.
- Draft/publish lifecycle: edit in draft → preview shows → public unchanged until publish → shows after publish.

MEDIUM-RISK:
- content_type → correct source/layout controls (Option B: correct existing section is created; Option A/C: dispatch picks correct family builder).
- typed content/layout compatibility rejection (e.g. product + category-only layout rejected).
- R4 control flow (Option B: chooser creates the right section; Option A/C: conditional-field mechanism if built).

LOW-RISK:
- layout presentation per content type; mobile; visual variants (source-contract/markup tests + one browser scenario).

## 22. Fast-Track browser-QA recommendation (lightest sufficient)

Do NOT inherit the 4×2×3×surfaces matrix (that is Task 16). Minimum representative set:
- Products mode renders through the canonical card + inherits Quick View (1 viewport open/close) — reuse Task-5 harness assertions.
- One materially different layout per the other three content types renders (categories grid, brands carousel, collections grid) — 1 desktop + 1 mobile (390) RTL.
- R4 control switching works (Option B: chooser creates correct section and its inspector opens; Option A/C: switch content_type → controls update).
- One non-Home surface (`listing` or `collection`) renders the chosen content.
- Tenant/store data correct (marker product/category from the seeded tenant).
Target ≈ 12–18 checks across 1440 + 390 RTL, reusing `tools/storefront_builder_qa/public_task5_qa.mjs` (extend, do not fork).

## 23. Architecture options

### Option A — new thin `storefront_showcase` section dispatching to existing domain loaders/templates
- Architecture: one new registered schema-backed section; context builder dispatches on `content_type` to `_category_grid_context`/`_brand_carousel_context`/`_collection_tiles_context`/`_product_section_context`; template branches on content_type.
- Reuses: ResourceSource, ownership validator, the four builders, product_card (product mode).
- Files: `section_registry.py` (+1 def, +membership in ~7 frozensets), `render_service.py` (+dispatcher builder), a new `sections/storefront_showcase.html`, `resource_source.py` (+adapter routing), tests.
- Migrations: ZERO.
- Duplication risk: **HIGH** — template nesting (§9), a new (5th) merchant-facing way to express the same thing, and the conditional-field gap (§10) forces either nested full section templates or a per-section inspector hack.
- Future flexibility: medium. R4 UX simplicity: LOW (conditional fields missing). 50-template compat: additive OK. Tasks 10/13/15: neutral. Complexity: **L**. Risk: **HIGH** (tenant + template + inspector).

### Option B — R4 "Showcase" creation FACADE over the four existing sections (RECOMMENDED)
- Architecture: NO new renderer/section. A lightweight R4 "Add Showcase" flow: merchant picks a `content_type`; R4 creates/opens the corresponding EXISTING section (`product_section`/`category_grid`/`brand_carousel`/`collection_tiles`) via the existing `section.add` mutation, and shows that section's existing inspector (which already renders exactly the right source/layout/title/count/View-All controls). Optionally a small library-grouping/label so the four appear under one friendly "Showcase / نمایش محتوا" entry point.
- Reuses: EVERYTHING — all four renderers, templates, schemas, validators, ownership guard, destination resolver, product_card/Quick View, Draft/publish, preview — unchanged.
- Files: likely `section_registry.py` library-category/grouping metadata only, an R4 editor "Add Showcase" UI affordance (`r4_views.py`/editor template + `r4_editor.js`), maybe a tiny chooser partial. NO new section, NO new context builder, NO new template.
- Migrations: ZERO.
- Duplication risk: **LOW** (no new owner). R4 UX simplicity: HIGH (each existing inspector already shows the right controls; sidesteps the conditional-field gap). 50-template compat: fully additive. Tasks 10/13/15: aligned. Complexity: **S–M**. Risk: **LOW**.
- Trade-off: it does not produce a *single* section instance that can later switch content_type in place — but that switching is exactly what the Inspector cannot do today, and merchants rarely convert a product row into a brand row.

### Option C — deeper generic content-section abstraction / shared-renderer refactor (+ conditional-field infra)
- Architecture: build generic conditional-field support in `settings_schema.py`/inspector, extract reusable body partials from the four families, and a true generic content section over a shared loader.
- Reuses: the domain models/validators, but introduces new shared render/inspector infrastructure.
- Files: `settings_schema.py`, `r4_views.py`, inspector templates, `r4_editor.js`, `render_service.py`, four template refactors, `section_registry.py`, tests.
- Migrations: ZERO (but large surface).
- Duplication risk: medium (done well, reduces long-term duplication). R4 UX simplicity: HIGH (once built). Complexity: **L (largest)**. Risk: **HIGH** (touches the R4 form renderer + four templates). This is really a platform investment, not a Task-6 feature.

## 24. Recommended architecture

**Option B — an R4 "Showcase" creation facade over the four existing canonical sections.** It delivers the merchant intent ("one simple place to add and configure a content block") with ZERO new renderers/data authorities/templates/migrations, fully reuses Task-4 capabilities and Task-5 product-card/Quick View, and cleanly sidesteps the missing conditional-field infrastructure (each existing section's inspector already shows exactly the right controls). Keep the four sections first-class canonical primitives (no deprecation). If the PO insists on a single in-place content_type-switchable section, that requires Option A + the §10 conditional-field gap → escalate to Option C scope (a platform task), not Task-6-sized.

## 25. Expected changed files (prediction, for Option B; NO code changed now)

- `apps/storefront_builder/section_registry.py` — library-category/grouping + friendly label metadata so the four appear under one "Showcase / نمایش محتوا" entry (no new section).
- `apps/storefront_builder/r4_views.py` — the "Add Showcase" chooser view/context (read-only helper listing the four content types).
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/...` — a small chooser partial + editor affordance.
- `apps/storefront_builder/static/.../r4_editor.js` — wire the chooser to the existing `section.add` mutation.
- Tests: `apps/storefront_builder/tests/test_r4_*` (facade creates the correct section per content_type; tenant isolation reused; no new section registered).
- (If Option A were chosen instead: add `sections/storefront_showcase.html`, a `_storefront_showcase_context` in `render_service.py`, and frozenset memberships — flagged HIGH risk.)

## 26. Expected migrations

**NONE.** Every option reuses existing models (`Product`, `Category`, `Brand`, `MerchantCollection`), the existing `StorefrontLayoutVersion` Draft/publish, and JSON `section.settings`. If any proposed design appears to need a model/migration, that is an architectural warning to STOP — not something to solve in Task 6.

## 27. Risks / blockers / questions for Product Owner

1. **Conditional-field infrastructure does not exist** (§10). A single content_type-switchable Showcase section is not cleanly expressible today. PO decision: accept Option B (facade, no conditional fields needed) OR fund conditional-field infra (Option C, platform-scale)?
2. **"Brand landing" and "Campaign landing" surfaces do not exist** (§12). Only `home/product_detail/listing/collection/search/cart`. PO must clarify whether "Category/Brand/Campaign" placement means "the `listing` page with `?category=`/`?brand=`" (real) or a new page-type (a separate, larger task — do NOT invent here).
3. **Five ways to express one thing** (§18/23): introducing any Showcase must not deprecate the four canonical sections nor duplicate them. Confirm Showcase is additive-only for Task 6.
4. **Layout enums are incompatible** (§6): confirm content-type-specific layout choices (reuse existing enums), not a universal layout taxonomy.
5. **Ready-Template DNA** (§19): confirm Task 6 does NOT rewrite the 50 recipes.

## 28. Final classification

**Classification: C — new R4 UX facade over existing canonical section types.** (If the PO instead mandates a single new in-place switchable section: that is **D** at best and realistically **E** because of the conditional-field gap.)

**Complexity: S–M** for the recommended Option B. (Option A = L/HIGH; Option C = L/HIGH.)

TASK 6 IMPLEMENTATION STARTED: NO
