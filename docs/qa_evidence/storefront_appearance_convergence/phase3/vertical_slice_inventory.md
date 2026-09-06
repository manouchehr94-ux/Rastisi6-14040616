# Phase 3 vertical-slice inventory

Date: 2026-09-06. Source baseline: `e244619f395ebf0dbebc77d2033841e17f1cd099`.
Preparation only. Source observations are distinguished from proposed contracts and unexecuted browser assertions. No production or test changes were made.

## Source convention and authority

`B` means `apps/storefront_builder/`; `C` means `apps/catalog/`. Every abbreviated path below expands using those roots. Template names resolve under the owning app's `templates/`. The binding program is `docs/superpowers/specs/2026-09-05-storefront-appearance-convergence-5-phase-design.md`; Phase-2 design, implementation plan and final gate were read. Their old machine paths and interpreter versions are historical, not this workspace's identity. Current execution results are in `baseline.md`.

`CLAUDE.md` requires `.claude/skills/rastisi-code-map/SKILL.md`; it was read. No `graphify-out/graph.json` exists, so the skill's normal source-navigation fallback applies. No AGENTS.md was found in the workspace file census.

## Brand map

| Layer | Exact current implementation and observation |
|---|---|
| Registered section | `B/section_registry.py`: `_BASE_SECTION_REGISTRY['brand_carousel']`, finalized by `_finalize_registry`, accessed by `get_definition`. All six page types allowed; duplicable/removable. “Brand Showcase” is the pilot label, not an additional registered key. |
| Aliases/component registry | No second Brand section alias found. Runtime enumeration of `B/storefront_appearance/registry.py:list_components()` found no entry referencing `brand_carousel`; do not invent `brand.grid.v1` or count a marketing name as a renderer. |
| Variants | `grid`, `carousel`, `beauty_tabs`; `display_mode` is the persisted axis; default `grid`. All `VariantDefinition.renderer` values are absent, hence Pattern A: one template. `B/variant_contract.py:resolve_active_variant`, `resolve_renderer_template` are the shared trusted resolver. |
| Renderer | `B/services/render_service.py:_brand_carousel_context(store, section)` through `_CONTEXT_BUILDERS`, `_build_items_from_sections`, `build_page_render_items`. Template `storefront_builder/sections/brand_carousel.html`. No variant performs an independent query. |
| Domain | `C/models.py:Brand`, ordinary live records; `C/services/brand_service.py` owns business edits. The rendering loader directly queries `Brand`, rather than calling the domain write service. Builder stores IDs and presentation, not name/logo copies. |
| Selection/order | Nonempty `brand_ids`: active, same-store query and reconstruction in requested order; missing/foreign/inactive IDs omitted. Empty list: all active same-store Brands, ordered `sort_order`, `name`. Validation caps manual selection at 24. No runtime limit on auto-all. Per-instance cache includes section PK, preventing sibling selection leakage. |
| Typed source | `B/resource_source.py:ResourceSource`; `brand_resource_source_from_settings`, `brand_resource_source_to_legacy_patch`, `_SECTION_ADAPTERS`. `source` is a typed UI/write projection; persisted `brand_ids` remains authority. Auto `all_active`; manual IDs preserve order. No separate typed render-result DTO: context contains Brand models. |
| Settings | `BRAND_CAROUSEL_SCHEMA`: title/text, source/resource_source, display_mode/choice, show_view_all/boolean. `_validate_brand_carousel_settings`, `default_brand_carousel_settings`; finalized wrappers add supported common blocks. R4 does not expose destination/background/spacing/responsive editing through this schema. |
| Common capabilities | Runtime: background, columns, destination, motion, responsive, spacing. `columns` means stored data capability, not rendered control: no `columns_visual`. Typography local override allowlist currently contains only `hero_banner`. Brand global typography can inherit; local typed typography is not enabled. |
| View-all | Loader resolves a destination only when show_view_all and a non-none destination exist, through `apps/content/services.py:resolve_destination_setting`. Grid/carousel emit the link; beauty_tabs omits it even when the loader supplies it. |
| Legacy write | `B/views.py:storefront_section_settings`, `_get_scoped_section`, `_validate_universal_selection_ownership`, `_record_edit_history`; form in `dashboard/storefront_builder/partials/section_settings_form.html`. Form constructs complete family fields plus common fields, validates, saves current Draft. |
| R4 write | `B/r4_views.py:storefront_r4_mutation` → `B/services/r4_mutation_service.py:apply_mutation` → `_apply_section_update_settings` → `B/settings_schema.py:clean_section_schema_patch` → definition validator. Source ownership checked only when source is touched; unrelated title edit may preserve stale legacy IDs. |
| Lifecycle | `B/models.py:StorefrontSection.settings`, `stable_id`, page→version→layout→store. `layout_service` clones presentation and references for Draft/Published/restore. Domain Brand changes remain live for both versions. `edit_history_service.record_change` owns successful change revision/history increment. |
| Media | `Brand.logo.url`, alt=name; missing logo displays name. CSS object-fit contain, max-width 100%; home.css later overrides max-height 40px to 48px, beauty 36px. No broken-URL onerror fallback in this template. Background URL is separately same-store resolved in `_build_items_from_sections`. |
| JS | No Brand-specific script/init function. Horizontal rails use native overflow and CSS snapping. Preview script supplies editor selection/postMessage behavior; R4 reloads iframe after save. |
| Responsive | Grid inline auto-fill/minmax(120px,1fr), gap 14px: hard-coded, ignores stored columns. Carousel inline flex/overflow, home.css tile width 150px after cascade. beauty_tabs has mobile 128px basis at 680px breakpoint. RTL inherited from base. Common hide flags apply in wrapper. |
| Tests | `test_render_service.BrandCarouselRenderTests`, `test_section_registry`, `test_r4_resource_source`, `test_r4_resource_picker`, `test_r4_settings_schema`, `test_r4_vertical_slice`, `test_u1b1_variant_runtime_wiring`, `test_shared_capabilities`, `test_g23_builder_public_content_appearance`. Domain `C/tests/test_brand_service.py`. |

### Brand answers A–G

A. Yes for existing visual variants: all consume `_brand_carousel_context` and the same ordered Brand list. No complete typed family render-result/capability contract is established yet.

B. No independent visual-variant business query was found. Picker queries are admin selection queries, not variant renderers.

C. Variant-only R4 patch merges current state and preserves compatible IDs/common wrapper blocks. Full preservation is **not proven**: an executed pure bridge probe sets `appearance_overrides.variant_explicit=True` on switching to carousel, then loses it after `{'title':'Phase3'}`. Legacy reconstructed forms also do not carry that internal block forward. No current Brand manifest component was found, so an immediate global-variant visual flip is not asserted; loss of canonical local intent is real. Title/source/variant sequences require regression coverage before generalization.

D. Partly: unknown R4 fields reject; invalid stored variants fall back to grid; legacy column controls are hidden using columns_visual. View-all capability requires BOTH a supporting active variant and a trusted current destination that validates and resolves to a non-none URL. R4 exposes show_view_all but no destination authoring; variant support alone is insufficient. Existing typography is not a supported Brand local control.

E. Yes at full component semantic engine level for equivalent presentation and live domain inputs; different Draft/Published versions intentionally differ. Browser/computed-style parity remains unproven, particularly outside Home.

F. There is no dedicated Brand component HTTP fragment endpoint. Brand can nevertheless be placed on Cart and rendered by its real update/remove fragments. Shared wrapper inclusion receives family context, but the Cart fragment omits container projection; raw inner-template rendering also omits wrapper semantics. These are distinct boundaries.

G. A raw fragment does not establish CSS/JS. It inherits outer-page assets. Normal Preview refresh currently reloads the full iframe and establishes assets again.

### Brand View-all capability matrix (V02)

| Resulting active variant | Trusted current destination | Phase-3 R4 control/write contract | Render contract |
|---|---|---|---|
| grid or carousel | Valid, non-none, resolved for the current store | Actionable; show_view_all may be written | Anchor exists when enabled, with the resolved href |
| grid or carousel | Absent, none, invalid, missing/inactive/foreign target | Not actionable; explicit enable rejected before mutation | No View-all anchor |
| beauty_tabs | Any destination | Not actionable; explicit enable rejected before mutation | No View-all anchor |

Rejections leave settings, revision and history unchanged. Switching to beauty_tabs without an enable request preserves compatible stored show_view_all and destination; switching back restores their effect if the destination is still valid. Unrelated edits must not erase dormant settings. Use existing `validate_destination_settings` plus store-scoped `apps/content/services.py:resolve_destination_setting`; the latter alone is not external-URL validation. Client-supplied capability flags, resolved URLs or an unsupported destination patch never grant capability. Preserve legacy/template destination authoring. No general R4 destination editor or second destination authority is introduced; reuse of a canonical generic control is permissible only if already present and evidenced without new authority. Task2 implements the bounded server/inspector check; Task3 proves visible control and rendered anchor truth.

## Collection map

| Layer | Exact implementation and observation |
|---|---|
| Section keys | `collection_tiles` (all six page types), `collection_header` and `collection_products` (collection page only). Header removable; products required/nonremovable; both max_instances=1 and nonduplicable. All use existing Section registry. |
| Related, not aliases | `product_section` with data_source=collection displays products inside a selected Collection; `catalog_product_wall` can group visible Collections. Neither is another tile variant. `/collections/` is a direct index page, not another StorefrontPage type or tile renderer alias. |
| Variants | Tiles `grid`/`carousel`, persisted `tile_style`, default grid, both Pattern A. Header/products have no registered visual variants. No Collection tile entry found by runtime component-registry enumeration. |
| Loaders | `B/services/render_service.py:_collection_tiles_context(store, section)` returns `collection_tiles=[{'collection': MerchantCollection, 'item_count': int}]`; `_collection_header_context(store,section,page_context)` and `_collection_products_context(...)` consume route/representative context. |
| Domain contract | `C/services/collection_service.py:public_collection_queryset(store)` is active+same-store, ordered name; `collection_visible_items(collection,store)` applies storefront_listing_products, then item order,id, with product relations prefetched. `get_scoped_collection` protects lookup. `B/services/section_data_service.py:products_in_collection`, `_resolve_collection`, `resolve_products` consume the domain service for product_section. |
| Tile selection/order | Nonempty collection_ids reconstruct requested order after active+store lookup; cap 12. Empty list queries all active, newest created first. Count uses aggregate Count('items') for already scoped IDs: all membership rows, not only shopper-visible products. The second count query has no explicit store predicate but receives only scoped IDs; not evidence of a tenant leak. |
| Schemas | `_validate_collection_tiles_settings` validates title, collection_ids, tile_style; finalized common wrappers. No R4 SettingsSchema on any of the three Collection keys. ResourceSource accepts kind collection and auto all_active generally, but no section adapter/picker/ownership branch exists for collection tiles. |
| Ownership | MerchantCollection/Item CRUD, activation and order belong to catalog service. Builder stores selection and presentation; Collection detail does not store current route Collection ID in settings. No duplicated business-record ownership found. |
| Legacy/R4 | Legacy section settings supports collection_ids/tile_style plus scoped selection validation. R4 settings mutation rejects section_not_schema_enabled; inspector returns 404. R4 source ownership deliberately has no Collection-kind rule today. Enabling only the schema would be unsafe. |
| Templates | `storefront_builder/sections/collection_tiles.html`, `collection_header.html`, `collection_products.html`; `catalog/collection_detail.html`, `catalog/collection_index.html`. Products include the existing `catalog/partials/product_card.html` with settings.card; preserve ProductCardData/domain behavior. |
| Full Preview | `_preview_page_context`: most recent public Collection, domain visible items, Paginator; shared render pipeline with Draft. It uses request.GET['page'] both for Builder page type and paginator lookup; `page=collection` falls back to page 1. No selectable collection-pagination Preview UI promised here. |
| Public | `C/views.py:collection_detail`: scoped active slug lookup, domain visible items, Paginator, universal context/Published. Index uses domain queryset plus direct cards and universal global context. No dedicated HX branch in either Collection view. Pagination is ordinary navigation. |
| Media | Tile image ImageField URL, cover in .pcard .img; absent image folder glyph. Header image 96x96, cover, omitted if absent. Index ratio16/9. Product media remains shared card media. Missing file URLs are not repaired by these templates. |
| Assets/mobile | Tiles rely on home.css and product_card.css: grid g4 hard-coded; carousel 220px, 180px below680px. Header inline flex-wrap/min-width0. Products use rsec-cols and common desktop/tablet/mobile settings. Preview home.css differs from Collection Public product_list.css. |
| Tests | `test_render_service.CollectionTilesRenderTests`, `CollectionContextAwareSectionsTests`, `test_u4_component_variants.CollectionTilesVariantTests`; catalog `test_collection_service`, `test_collection_public_views`, `test_collection_integration`, `test_collection_models`, `test_legacy_collection_migration`; dashboard `test_collection_views`. |

### Collection answers A–F

A. One domain service for visible Collection products, but no single typed tile resource adapter. Tile query/count and public index/detail semantics differ. The differences must be named, not flattened into one list.

B. No ordinary Collection business-record duplication found in Builder settings. Selected IDs and visual title are presentation, not copied Collection business names.

C. No: legacy tile edit works, R4 tile settings is disabled. Their lifecycle foundations are shared, their family settings surfaces are not convergent.

D. Both tile variants consume identical selection/order/count results; Collection page header/products are distinct semantic roles, not visual variants of tiles.

E. Route-selected resource, ordered visible membership, pagination, product cards, count policy and a direct index companion. Brand alone cannot establish those contracts.

F. Reuse source adapters, schema bridge, lifecycle, wrapper and tests. Keep Collection query/page context separate. Do not create a Brand-derived universal catalog engine.

## Shared renderer topology

**Preview:** `dashboard:storefront-builder-preview` (`/admin-portal/storefront-builder/preview/?page=home` or `page=collection`) → staff/permission/store resolution → `views.storefront_preview` → `layout_service.get_or_create_draft` → `draft.get_page` → `_preview_page_context` → `resolve_store_appearance_render_state` → `build_page_render_items` → `_build_items_from_sections` → family loader/variant resolver → `preview.html` → render_containers/render_rows → responsive_section_wrapper → registered component template. Preview GET can create Draft; no live browser GET was performed in preparation.

**Public:** `catalog:home` or `catalog:collection-detail` → store/domain resolution → catalog domain context → `storefront_context_service.build_universal_storefront_context` → `page_resolution_service.resolve_published_page` → same `build_page_render_items` / family loaders / registered templates. `request.storefront_appearance_version` is the selected Published version. Public hides optional empty product sections, Preview retains editor empty containers. Unpublished Home retains legacy fallback; non-Home can use unsaved default sections through `build_default_render_items`. These compatibility paths remain.

**Fragments/HTMX:** `storefront_section_list_partial`, R4 inspector and resource picker are admin fragments; they do not render storefront Brand/Collection components. `r4_editor.js:refreshStructureAndPreview` reloads Preview and extracts the structure panel from a fetched editor page. Both Collection routes lack a special HX component response. Preview wrapper projection uses the existing `responsive_section_wrapper.html` with an item produced by `build_page_render_items`; browser DOM replacement there is a harness operation, not a new endpoint.

**Actual indirect Public fragment:** Brand and tiles are allowed on Cart. `/cart/items/<item_id>/update/` and `/remove/` → `apps/cart/views.py:cart_item_update/cart_item_remove` → `_render_cart_container` → `resolve_published_page` → `build_page_render_items` → group_items_into_rows → `cart/partials/cart_sections_body.html` → render_rows → responsive_section_wrapper. This helper supplies render_items/rows but not render_containers/use_container_layout, unlike full `cart_detail` → build_universal_storefront_context. It also does not set the request appearance-version attribute explicitly. Family effective data/settings are built by the shared service, but container projection is lost after the actual HTMX swap. This is a source-confirmed pilot-reachable A04 gap; do not defer it merely because its host page is Cart. No commerce changes or new fragment endpoint are needed to adapt this presentation boundary.

## Preview/Public and Full/Fragment matrices

| Semantic field | Full Preview | Public | Isolated existing wrapper |
|---|---|---|---|
| Variant | Draft settings, trusted resolver, local intent marker | Published equivalents | Same only if given the resolved item; not raw settings |
| Appearance | Draft effective config + sparse supported local values | Published effective config | Item carries effective values; outer tokens/CSS still required |
| Specific settings | Effective copied section.settings | Same pipeline | Supplied through item.context |
| Brand resources | Ordered active store Brands | Same live domain query | Same resolved item.brands |
| Tile resources | Ordered active store Collections, total memberships | Same | Same resolved collection_tiles |
| Detail resources | Representative newest Collection/page1 | Requested Collection/page number | Explicit collection/products/page_obj required |
| Media | Live domain URLs; store-scoped background | Same | Domain URLs survive; wrapper needed for background |
| Responsive | Wrapper data-hide flags/CSS variables | Same values from Published | Wrapper required; inner include alone is insufficient |
| Identity | Model stable_id retained; DOM editor uses physical PK | Model stable_id retained; editor PK hooks absent | Must preserve logical identity; do not compare cloned PKs |
| Assets | Base+Home+card+Builder+preview CSS; HTMX/Alpine | Home or page-specific envelope | No independent asset establishment |

## A04 conclusion

**PARTIAL for the two-family contract; OPEN program-wide.** Shared render items carry family context and the wrapper passes Brand/Collection fields. The indirect Cart fragment loses container projection for placed pilots; isolated Preview wrapper/replacement proof is also missing. Test both real Public HTMX and harness-only Preview replacement. Original Listing/Newsletter A04 remains Phase4; the Cart presentation boundary is adapted for Brand in Task3, verified for Collection in Task5, and jointly hardened only if needed in Task6. No global A04 closure claim follows. Mapping: V05 (pilot-reachable Cart gap and Preview proof), V09 (remaining program deferral).

## A06 assets conclusion

### Exact registry page types and Public envelopes

Source verification at preparation commit `c7245dae03f8b5e29189824b9568027767bd50e1`: `B/section_registry.py` defines `ALL_PAGE_TYPES`; both registrations inherit `SectionDefinition.page_types` without override. **Both brand_carousel and collection_tiles allow exactly home, product_detail, listing, collection, search, cart.** Routes are verified in `apps/catalog/urls.py`, `apps/cart/urls.py`, `shop_core/urls.py`; dispatch/template selection is in their views.

All rows inherit `templates/base.html`: CSS `css/tokens.css`, `css/base.css`, `css/layout.css`, then page CSS, then `css/theme_palette.css`; runtime `js/htmx.min.js`, `js/alpine.min.js` (deferred), plus inline CSRF/htmx:configRequest handling. `templates/storefront_shell.html` adds shared header/footer selection, not another external runtime. Hold the selected shell variants constant for envelope comparison and record any conditional assets in rendered HTML. Neither pilot has a dedicated JS initializer.

| Allowed page type (both pilots) | Public route → template envelope | Additional CSS (under css/) | Additional JS/runtime | Builder CSS / required pilot styles | Identical envelope group |
|---|---|---|---|---|---|
| home | `/` → `catalog/home_visual.html` → base, published Builder layout | product_card.css, home.css, storefront_builder.css | No page-specific script | Present; Home rules currently contribute pilot styling | E1 Home |
| product_detail | `/products/<slug>/` → `catalog/product_detail.html` → storefront_shell → base | product_card.css, product_detail.css, storefront_builder.css | Inline Alpine variantSelector/gallery registration; JSON-LD is data | Present; complete pilot rules without Home unproven | E2 Product detail |
| listing | `/products/` (empty q; category filters also use this type) → `catalog/product_list.html` → storefront_shell → base | product_card.css, product_list.css, storefront_builder.css | Inline mobile filter sync and htmx:afterSwap listener | Present; complete pilot rules without Home unproven | E3 Listing/Search |
| search | `/products/?q=phase3` (nonempty q) → same product_list template/shell | product_card.css, product_list.css, storefront_builder.css | Same filter sync/afterSwap runtime | Present; complete pilot rules without Home unproven | E3 Listing/Search; dedup only after per-type assertions |
| collection | `/collections/<slug>/` (including page2) → `catalog/collection_detail.html` → storefront_shell → base | product_card.css, product_list.css, storefront_builder.css | No page-specific script; differs from E3 | Present; complete pilot rules without Home unproven | E4 Collection detail |
| cart | `/cart/` → `cart/cart_detail.html` → storefront_shell → base | cart.css, storefront_builder.css | Shared runtime; real Cart HTMX forms | Present; complete pilot rules without Home unproven | E5 Cart |

Companion boundary E6: `/collections/` uses `catalog/collection_index.html` → storefront_shell → base, adds only product_list.css, no page-specific JS and no storefront_builder.css. The view resolves Collection shell context, but the template renders its direct domain listing and does not consume pilot render_items. Assert this boundary and smoke its existing shell separately; do not fabricate a pilot placement there or silently convert the index to a Builder page. The legacy Home fallback similarly is not the published pilot-placement envelope. If a future observed response renders either pilot through any additional envelope, it must join the certification matrix; inability to prove it blocks PASS.

Mandatory future coverage: automated registry-equality, route/page dispatch, actual pilot presence, shell and asset assertions for **each of the six allowed page types, separately for both families** (Task3 Brand, Task5 Collection). Compare ordered CSS/JS URLs and relevant inline runtime identities, not filenames alone; E3 is the only proposed deduplication. Browser smoke each E1–E5 with the relevant pilot placed there at desktop/mobile/tablet sizes, using E3 Listing plus automated Search equivalence. E6 gets companion shell evidence, not pilot certification. Existing fuller variant/fragment scenarios remain required. Capture `browser/envelopes/{brand,collection}/{E1,E2,E3,E4,E5}/{1440,390,768}.png` with metrics/asset manifest; companion evidence uses `browser/envelopes/collection-index/`.

Each distinct pilot envelope must prove required component CSS, shared runtime exactly once, computed layout, decoded media, no Home-only CSS reliance, stable asset counts after wrapper replacement, no document overflow and applicable same-input Preview/Public semantics. Public replacement is a harness projection unless it is the real Cart response; A04 Listing/Newsletter scope is unchanged. **A06 may close only for these two pilot families after every allowed Public pilot envelope has direct browser proof or per-page automated assertions tied to browser proof of an identical envelope. Any unproven allowed pilot envelope leaves A06 PARTIAL/OPEN and blocks full family PASS. Global/all-family A06 remains outside Phase3.** Use the smallest existing Builder stylesheet/envelope mechanism, never import all home.css everywhere.

**OPEN.** Base loads tokens.css, base.css, layout.css, then page CSS, then theme_palette.css; HTMX and Alpine are deferred global scripts. Preview adds product_card.css, home.css, storefront_builder.css, storefront_builder_preview_v22.css. Published Home supplies Home/card/Builder CSS. Published Collection detail supplies card/product_list/Builder, omitting home.css although Brand and tiles are allowed there. Collection index supplies product_list.css only. Thus allowed pilot components can depend on assets absent from a public non-Home envelope. This is source-proven asset-list mismatch; its exact computed-style consequence is unmeasured.

Brand duplicates some layout inline (grid/flex/gap), while later home.css redefines tile sizes/gaps. Collection has no corresponding inline flex fallback. A fragment can behave differently depending on outer CSS even with identical HTML. No pilot JS initializer exists; native scrolling needs none, but editor listeners and shared Alpine/HTMX islands must be tested after repeated replacement. Loading global scripts inside each fragment would risk duplicate initialization; preserve one outer runtime and idempotent use. No blanket CSS rewrite is authorized. Mapping V06.

## Media and responsive classification

| Concern | Classification | Required evidence |
|---|---|---|
| Device hiding; wrapper backgrounds/spacing | Common contract | Same computed wrapper style and visibility before/after replacement |
| Brand grid count | Hard-coded auto-fill | Do not expose column control; check 390/768/1440 widths |
| Brand carousel/beauty rail | Family-specific fixed width + native overflow | Touch scroll, keyboard links, RTL order, long names |
| Collection tile grid/count | Hard-coded g4; no columns_visual | No false editable column claim; compare grid at all viewports |
| Collection product grid | Common rsec-cols | Desktop1–6/tablet1–3/mobile1–2 choices take effect |
| Brand logo | Family-specific contain | Portrait/wide logo, no logo/name fallback, decoded image |
| Collection image | Family-specific cover | Wide/tall, absent image, header96px/index16:9 |
| Broken-file URL | Missing explicit fallback | Record browser network failure; do not equate no-image with broken-image |
| Local typography | Missing pilot typed support | Expose only after resolver+template proof; otherwise hidden |

Phase-2 media lifetime/reachability is untouched. Domain URLs are not versioned media snapshots. Background uses `resolve_background_media_url(store, settings.background)` and rejects foreign/missing assets safely. Preview/Public publication freezes presentation selection, not later domain image/name edits.

## Browser QA capability and future evidence matrix

Existing: `B/management/commands/qa_storefront_builder.py` + `tools/storefront_builder_qa/run.mjs` (legacy); `qa_storefront_builder_r4.py` + `tools/storefront_builder_r4_qa/run.mjs` (R4). Shared `tools/storefront_builder_qa/package.json` owns playwright-core. R4 uses installed Chromium discovery, session-cookie auth, DB backup/restore in finally and runtime manifest; `_prepare_r4_sandbox` places Hero/Brand and creates `t12-brand-1` through `t12-brand-5` and products. Runner currently uses 1440x900, hard-coded Phase-1 screenshot directory, no Collection fixture/matrix.

Current environment: shared node_modules/playwright-core absent; application SQLite has no stores_store table. No live store/user can be verified, and no browser was run. These are environment readiness limitations, not test database failures. Do not claim screenshots exist.

Smallest future extension: extend these same R4 command/runner files; retain restoration and auth; add Collection fixture and pilot matrix, report-dir-based evidence, 390x844 and768x1024 viewports, network/computed-style/image/replacement assertions. No second harness/package/runner. Future disposable DB bootstrap and exact command are in plan Task1. Fixture is migration-seeded store `akhlaghi`, dedicated staff `phase3_qa_owner`, Collections `p3-collection-1` and `p3-collection-2`; these are proposed fixture names, not present records. Server binds127.0.0.1:8765 using existing command's local-store routing setup.

| Scenario | Exact future URL/action | Viewports | Assertions | Evidence under Phase3 report-dir |
|---|---|---|---|---|
| Brand Preview | `/admin-portal/storefront-builder/preview/?page=home` via R4 iframe |1440x900,390x844,768x1024|All3 variants; IDs/order; title/logo fallback; effective wrappers; no document overflow|`brand/{variant}/{viewport}/preview.png`, `metrics.json`|
| Brand Public | `/` after harness publish |same|Published matches published Preview fixture; later Draft-only edit invisible|`brand/{variant}/{viewport}/public.png`|
| Brand replacement | Fetch same Preview URL, extract resolved `.rsec`, replace matching original in harness |same|Same resources/geometry/visibility; one editor selection action; assets don't multiply|`brand/{variant}/{viewport}/fragment.png`|
| Collection tiles Preview/Public |same Home URLs, both tile_style choices|same|IDs/order/title/image; counts identified as total membership; missing/inactive/foreign exclusions|`collection/{variant}/{viewport}/{preview,public}.png`|
| Collection detail Preview/Public |`/admin-portal/storefront-builder/preview/?page=collection`, `/collections/p3-collection-1/`, `?page=2`|same|Set representative newest fixture to Collection1; compare same domain input; visible membership/order/pagination; shared cards/media|`collection/detail/{viewport}/{preview,public,page2}.png`|
| Collection replacement |Same harness extraction/replacement of existing wrapper|same|collection/products/page_obj survive; image decoded; repeated replacement idempotent|`collection/{variant}/{viewport}/fragment.png`|
| Actual Public HTMX |`/cart/` with both pilots placed; real item update/remove URLs above, IDs read from fixture DOM|same|Container placement, source/order/settings/background/media survive the server response and swap; cart outcomes unchanged|`fragments/cart/{viewport}/{before,update,remove}.png`, `metrics.json`|
| Admin HTMX |Existing settings/inspector/picker URLs resolved by reverse/data attributes|desktop/mobile|Same source/order after field edits, no leaked unsupported controls, iframe refresh is observed|`controls/{family}-{viewport}.png`|
| Cross-host isolation |Existing verified-domain pattern from test_u4_component_variants; negative Django client requests|test client + browser route checks|Foreign domain/ID never selects another store; anonymous Preview denied|`tenant.md`|

Variant names and viewport labels expand to concrete filenames in runner loops; braces above are filename grammar, not missing decisions. Browser JSON must record actual URL, viewport, store PK, logical stable_id and physical PK mapping, asset URLs/status, console failures and assertion results. Runtime cookies never enter committed evidence.

## Capability and legacy/R4 decisions

Brand show_view_all is supported only grid/carousel with valid destination; retain stored value when switching to beauty_tabs, hide its control there and reject attempts to set unsupported active-variant values. Do not erase compatible configuration on switch. Brand column storage is not UI support. Collection tiles exposes title/source/tile_style after schema+ownership+picker convergence; page header/products remain route-owned, legacy-editable common presentation. Non-Home R4 expansion is Phase4. Typed source selection must never accept domain names/images/business edits.

| Active path | Role | Canonical state/shared rendering/reason retained |
|---|---|---|
| Brand R4 settings/picker | ADAPT | Same Draft JSON and lifecycle; preserve intent/capability truth |
| Brand legacy settings | ADAPT | Same validator and revision/history; preserve existing data during mixed edits |
| Collection legacy tile settings | ADAPT | Sole current tile settings UI; bridge into same contract, never remove |
| Collection future R4 tile path | ADAPT | Existing mutation engine; add only family adapter/schema/ownership |
| Collection header/products legacy controls | KEEP | Route-owned content and common wrapper; shared renderer; non-Home R4 UI Phase4 |
| Catalog Brand/Collection dashboard CRUD | KEEP | Live domain-owned writes; not Builder canonical mutation scope |
| product_section collection source | CHARACTERIZE | Existing domain product service and shared card; do not redesign Product |
| Collection index direct template | CHARACTERIZE | Companion page/global shell, not tile alias; retain route |
| Preview iframe refresh/admin partials | KEEP | Existing refresh and renderer; isolated fragment proof uses harness |
| Unpublished Home/default non-Home | KEEP | Stored-data compatibility, same existing fallback decisions |
| Other-family fragments/legacy editors | DEFER | Phase4 migration; no removal in Phase3 |

## Gap register

Severity describes architecture/user risk; proof gaps are not claims of observed production incidents. No P0 discovered.

| ID/severity/owner | Evidence and exact site | User/architecture risk; invariant | Proposed task; tests; browser; defer |
|---|---|---|---|
|V01 P1 Brand/shared|Executed `clean_section_schema_patch` variant→title probe drops internal marker; settings_schema.py and section_registry.py validators; legacy storefront_section_settings reconstructs JSON|Local intent lost on unrelated edit; preserve server-derived intent and compatible fields, reject client spoofing|T1 RED,T2 Brand,T4 Collection,T6 cross-family; test_r4_settings_schema/test_phase1_appearance_authority/test_views; switch→title→reload browser; not deferred|
|V02 P2 Brand|BRAND_CAROUSEL_SCHEMA exposes show_view_all without destination editing; grid/carousel require resolved destination, beauty_tabs omits anchor|Actionability requires supporting variant AND trusted valid resolved destination; reject explicit unsupported enable atomically; preserve dormant values across roundtrip|T2–T3; schema/inspector/mutation tests for valid/absent/invalid/spoofed destinations and both variant directions; browser control+anchor truth; no broad destination editor; not deferred|
|V03 P1 Collection|No tile SettingsSchema/ResourceSource adapter; R4 inspector404, mutation section_not_schema_enabled; ownership Collection-kind no-op|No canonical typed R4 tile editing; unsafe to enable schema alone|T4–T5; test_r4_resource_source/test_r4_resource_picker/test_r4_mutation_api; source/order roundtrip; not deferred|
|V04 P2 Collection|_collection_tiles_context Count(items) vs collection_visible_items visibility filtering; query ordering differs index/tiles|Count may exceed visible products; accidental convergence could alter commerce semantics|T4 characterize total membership explicitly, T5 detail proof; test_render_service/test_collection_service; active/inactive member browser record; changing count meaning deferred product decision|
|V05 P1 shared A04|apps/cart/views.py:_render_cart_container supplies rows but omits full container projection for pilot sections; Preview wrapper replacement unproven|Placed pilot composition changes after actual HTMX; same resolved-item semantics and placement must survive|T1 characterization,T3 Brand adapter/proof,T5 Collection proof,T6 combined hardening,T7 real HTMX/browser; test_g22_preview_media_render_consistency/test_render_service plus apps/cart/tests/test_cart_views.py; remaining A04 V09|
|V06 P1 shared A06|Preview home.css vs Collection detail product_list.css; Brand/tiles allowed non-Home; inline Brand fallback duplicates CSS|Same HTML can differ by outer assets; declared pilot asset requirement must reach each allowed envelope|T3/T5 scoped fixes,T6 two-family proof,T7; test_page_shell/test_g23_builder_public_content_appearance; computed styles/network/replacement; global CSS redesign Phase4|
|V07 P2 shared|Only hero_banner APPEARANCE_OVERRIDE_AWARE; Brand inline grid ignores columns; tile grid hard-coded; media fallback partial|False common-control claim, mobile/media surprises; publish only supported controls and retain common wrapper state|T2/T3/T4/T5; test_shared_capabilities/test_responsive_rendering/test_g22_preview_media_render_consistency; RTL/long names/image/390px; broad responsive redesign deferred|
|V08 P1 QA platform|Existing R4 runner desktop/Brand only, absent dependencies, application DB empty|No reproducible cross-family certification; reuse runner with safe disposable fixtures|T1 harness setup,T3/T5/T7; test_qa_harness_contract; complete screenshot+metrics matrix; not deferred|
|V09 P2 shared deferred|Audit Report05 and current catalog/views.py HX early branch; Listing/Newsletter A04 scope|Program-wide fragment risk persists outside pilots; no claim of global closure|Phase4; characterize link in T8 final gate, no production change; later family tests/browser|
|V10 P3 deferred|Phase2 final_gate R6(a), two-legacy-tab accepted limitation; broad families/non-Home R4 absent|Error-response nit/migration debt outside pilot; preserve closed safety baseline|Phase4/optional approved cleanup; T8 ledger carry-forward; no Phase3 fix|

## Chosen architecture and deferrals

A, independent family fixes, is small initially but risks duplicate mutation/render/asset rules. B, platform-first rewrite, exceeds scope and generalizes without evidence. C, hybrid/vertical-first, proves Brand using existing contracts, then lets Collection refine the abstraction. Shared extraction is permitted only after both families need it; independent data queries remain family/domain-owned. No universal Brand framework, no new renderer, no new fragment engine.

Defer all-family schemas, other-family A04 closure, global CSS redesign, Header/Footer/Hero/Product redesign, non-Home R4 UI, broad Page Override, Template Switch, legacy retirement and deployment usage migration to Phase4 or separate approved decisions. Design expansion/new variants/Ready Templates/50-template certification belong to Phase5. Media cleanup/TTL remains a separate product decision, not this phase.
