# Task 5 — Collection end-to-end and page integration (COLLECTION GATE)

- Starting HEAD: `d3e5c9967b55ea5db94cc25e65b68e5ab2151d25`
- Branch: `feature/storefront-vertical-slice-phase3`
- Environment (resumed session): Python 3.12.13 (venv), Django 5.2.17, Node v22.23.2 (nvm), Chrome for Testing 151 (`/usr/local/bin/chrome`).

## Production files changed
- `apps/storefront_builder/static/css/storefront_builder.css` — Collection-scoped carousel tile-basis rule `.collection-tiles-carousel.tiles-carousel .pcard{flex:0 0 220px;scroll-snap-align:start}` + `@media(max-width:680px){flex-basis:180px}`. Mirrors home.css's SINGLE governing block for that compound selector (no later override → literal=effective), so overriding home.css on Home is a NO-OP (Home unchanged), while non-Home envelopes (which don't load home.css) get correct carousel sizing.
- NO changes to render_service.py, collection section templates, responsive_section_wrapper.html, catalog collection templates, preview.html, or apps/cart/views.py — the existing architecture (incl. Task-3's cart adapter) already supported Collection end-to-end; the new tests prove it.

## Harness files changed (Task-1/3 allowed)
- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` — `_prepare_phase3_collection_gate` fixture (phase3-only): `p3-collection-1/2` + `p3-collection-page2` (13 active visible members → real page2 + 1 inactive member proving item_count total vs visible), deterministically-newest collection, image/no-image collections; collection_tiles (grid+carousel) placed on all six envelope pages; ids threaded into manifest.
- `tools/storefront_builder_r4_qa/run.mjs` — Collection browser matrix (phase3-only, additive). Two harness fixes this task: (1) product-card selector on collection page2 corrected to `a.pcard-hitarea[href*="/products/"]` (product cards are `<article class="pcard">` with an inner `<a class="pcard-hitarea">`); collection-tile selector `a.pcard[href*="/collections/"]` unchanged. (2) Deterministic elimination of a harness-created `net::ERR_ABORTED` on the preview iframe: an in-flight preview-request counter (installed in `attachNetworkInstrumentation`, scoped to the admin page) drained to 0 in `settlePreviewFrame()` before/after every parent navigation, so the app's fire-and-forget preview reload can never be left in-flight for the next navigation to abort. NOT suppressed/allowlisted; `finalInstrumentationAssertions` unweakened.

## Test files changed
test_render_service (context-aware parity assertIs/assertEqual), test_u4_component_variants (both tile variants + title/source edit + publish/restore stable_id + Draft-only isolation), test_g22 (wrapper isolation), test_section_registry (collection six-page membership), test_page_shell (six-page presence/dispatch/shell/assets/E3/E6), test_g23 (CSS RED→GREEN + Home-unchanged guard), catalog test_collection_public_views (?page=2 domain+shared cards+no-HX + E6 index boundary), catalog test_collection_integration (anonymous/foreign-host page2 + foreign 404), apps/cart/tests/test_cart_views (Collection cart HTMX).

## RED → GREEN (controller-run, authoritative)
- CSS: carousel tile-basis rule absent from storefront_builder.css → present (effective/Home-unchanged); Home-unchanged guard test asserts the shared value equals home.css's governing value.
- Both tile variants: grid→`grid g4`, carousel→`tiles-carousel collection-tiles-carousel`.
- Context-aware parity: `collection_products` context `collection`/`products` == domain view's (assertEqual), `page_obj` is the SAME object (assertIs).
- /collections/<slug>/?page=2: domain visible membership + shared product cards + NO HX branch. Browser: `product_card_count=1`, `current_page_text=۲`, full envelope, HX-Request still returns full page.
- E6: collection_index renders own template, no render_items, no storefront_builder.css.
- Real Cart HTMX (Collection): Task-3 adapter SUFFICED (no bounded reopen needed) — tiles survive swap (6→6), hrefs stable, container context present, totals correct.

## Commands + results (controller-run, --keepdb)
- makemigrations --check: No changes detected. Django check: no issues.
- Group 1 (render/variants/media/catalog): **Ran 184, OK (skipped=1 pre-existing)**.
- Group 2 (cart): **Ran 52, OK**.
- Group 3 (six-page + brand): **Ran 334, OK**.
- git diff --check: clean.

## Browser matrix (controller-run, authoritative)
- **16/16 scenarios PASS** incl. phase3-brand-gate (Brand + Collection matrices). `result.request_failures` = **[]** (the harness-created preview abort eliminated at source). DB restore SHA256 pre==post `9e2aa261…` **match=true**.
- Collection coverage: **36 collection variant_checks** (E1-E5 × 3 viewports × 2 tile variants), collection asset-envelope records, collection page2 (`product_card_count=1`), collection cart_htmx (tiles 6→6 stable). Plus the Brand matrix (45 variant checks) still green.
- 94 screenshots under `browser/{brand,collection}/…`, `browser/fragments/cart/…`, `browser/collection/page2/`, `browser/wrapper_projection/`. metrics.json + r4-browser-result.json + db-restore-proof.json + fixture.json committed; transient logs/RECOVERY/FAILURE pngs excluded.

## Collection gate semantics preserved
- Count: item_count = total `Count("items")` (fixture: 14 total vs 13 visible on the page2 collection). Manual order + auto newest-first preserved.
- Collection detail owns current-route collection; tiles are selection/presentation only; pagination + visible membership stay domain-owned; no fabricated current collection on index; no count-meaning change.

## Scope audit
Production: only storefront_builder.css (Collection-scoped, Home no-op). Harness: qa command + runner (phase3-gated; default run unchanged). No migration, no domain ownership change, no new renderer, no new fragment endpoint, no Product redesign, no non-Home R4 UI, no Phase-4 work. Confirmed via git.

## Review
Independent semantic_reviewer verdict recorded in ledger.

## Readiness for Task 6
Both family gates PASS (Brand Task 3, Collection Task 5). Differences documented. READY for shared hardening (only if both pilots justify it).
