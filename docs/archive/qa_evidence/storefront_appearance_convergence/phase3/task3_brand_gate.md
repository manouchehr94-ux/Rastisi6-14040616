# Task 3 — Brand end-to-end renderer/asset/media proof (BRAND GATE)

- Starting HEAD: `59dbbdd3fec5e9a99b6689d5d6868df3d4046bd7`
- Branch: `feature/storefront-vertical-slice-phase3`
- Environment: Python 3.12.13, Django 5.2.17, Node v22.23.2, Chrome for Testing 151 (`/usr/local/bin/chrome`).

## Production files changed
- `apps/cart/views.py` — `_render_cart_container` now calls `build_universal_storefront_context(request, store, StorefrontPage.PageType.CART, page_context=context)` (V05/A04 adapter). Adds `render_containers`/`use_container_layout`/`store_appearance` and primes `request.storefront_appearance_version`, making the HTMX fragment match the full page. Same template `cart_sections_body.html` → POST-gated OOB counts preserved. `_cart_context`, pricing, stock, and mutation views UNCHANGED.
- `apps/storefront_builder/static/css/storefront_builder.css` — appended Brand-scoped rules mirroring home.css's EFFECTIVE (cascade-resolved) appearance so a brand_carousel on any non-Home envelope (which loads storefront_builder.css but not home.css) gets correct tile/logo sizing. IMPORTANT (review fix round 1): home.css has TWO `.brand-tile` blocks of equal specificity — an early block (40px, radius 12px, var(--card)) and a later "dense" block (48px, radius 6px, #fff, min-height:72px) that WINS on Home by source order. Since storefront_builder.css loads AFTER home.css on Home, the shared rules use the DENSE (effective) per-property values so overriding home.css on Home is a NO-OP (Home pixel-identical: 48px). Final values: `.brand-tile img{max-height:48px}`, `.brand-tile{min-height:72px;padding:10px;border-radius:6px;background:#fff}`, `.brand-carousel{gap:9px;padding-bottom:4px}`, `.brand-carousel .brand-tile{flex:0 0 150px}` plus first-block-only props (display/overflow/scroll-snap/object-fit/border). No global spill; home.css NOT modified.
- No production change needed for V02 renderer (renderer/template already correct — proven by 8 GREEN tests).

## Harness files changed (Task-1 allowed)
- `tools/storefront_builder_r4_qa/run.mjs` — `phase3ResponsiveCapture` replaced with `phase3BrandGate()`, gated behind `if (manifest.phase3)`. Default (non-phase3) run unchanged.
- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` — `_prepare_r4_sandbox(phase3=...)` + `_prepare_phase3_brand_gate` fixture (brand on 5 envelope pages, real logos + one no-logo brand, MerchantCollection host `p3-collection-1`, resolvable View-all destination); ids threaded through manifest `phase3_fixture`.

## Test files changed
test_cart_views (real Cart HTMX fragment RED→GREEN), test_g23 (CSS RED→GREEN + non-home brand route), test_render_service (V02 anchor matrix, 8), test_section_registry (six-page membership equality), test_page_shell (six-page presence/dispatch/shell/asset + E6 boundary), test_phase2_universal_renderer (Draft/Published isolation, 3 variants), test_stable_section_identity (stable_id across clone), test_g22 (wrapper isolation).

## RED → GREEN (controller-run, authoritative)
- Real Cart fragment: context keys `use_container_layout`/`render_containers`/`storefront_page` ABSENT before (a) fix → present after; brand tile + `?brand=<slug>` link render in fragment; OOB `#cart-count` preserved; totals/qty unchanged.
- CSS: 5 `.brand-*` selectors absent from storefront_builder.css → present after (dense/effective values); scope test enforces every added rule `.brand-`-anchored; home.css unchanged; a Home-unchanged guard test asserts the shared value mirrors Home's governing dense value (48px) so the override is a no-op.

## Review fix round 1 (CRITICAL resolved)
Independent reviewer found: the first CSS attempt copied home.css's FIRST brand block (40px) into storefront_builder.css, which loads AFTER home.css, overriding Home's DENSE block and changing Home (48px→40px etc.) — violating "Home unchanged". FIX: shared rules now carry the DENSE/effective per-property values (48px logo, 6px radius, #fff, min-height 72px, gap 9px, flex 150px). Browser metric re-run confirms Home `.brand-tile img` computedMaxHeight = **48px** (unchanged from pre-Phase-3), and non-home envelopes also 48px via storefront_builder.css. Test updated to assert 48px + added `test_brand_shared_rules_are_noop_over_home_effective_cascade`.

## Focused-suite results (controller-run, --keepdb)
- Cart (test_cart_views + test_cart_security + test_phase2_universal_renderer): **68 OK** (baseline 59).
- Six-page/shell (test_section_registry + test_page_shell + test_g23): **52 OK** (section_registry 2 + page_shell/g23 50).
- Main (test_render_service + test_g22 + test_public_homepage_integration + test_responsive_rendering + test_stable_section_identity): **139 OK, 1 pre-existing skip** (QuickLinks second-store). No new failures.

## Browser matrix (controller-run, authoritative)
Command: `qa_storefront_builder_r4 --store-slug akhlaghi --username phase3_qa_owner --port 8765 --browser-channel auto --phase3 --report-dir .../phase3/browser`
- **16/16 scenarios PASS**, including `phase3-brand-gate`.
- **DB backup/restore**: pre==post SHA256 `82bf5503…` match=true (db-restore-proof.json). Outer empty-baseline backup retained at `/projects/rastisi5_phase3_qa_backups/`.
- Coverage: **45 variant checks** (E1–E5 × {desktop 1440x900, mobile 390x844, tablet 768x1024} × {grid, carousel, beauty_tabs}), **15 asset-envelope records**, **45 V02 anchor records**, **3 cart HTMX flows**, **1 wrapper projection**.
- **A06 metric** (after fix round 1): non-home envelopes `home_css=0`, `sb_css=1`, htmx=1, alpine=1 (brand CSS applies WITHOUT home.css); bounded `.brand-tile img` height **48px on Home AND non-home** (dense/effective value; Home unchanged). No duplicate assets.
- **No document horizontal overflow**: scrollWidth ≤ clientWidth+1 on every envelope/viewport.
- **V02**: grid/carousel render View-all anchor `href=/collections/p3-collection-1/`; beauty_tabs renders none.
- **Wrapper projection**: 3× replacement, brand hrefs identical, asset count 10→10 stable (scripts not executed).
- **Cart HTMX**: real update/remove, badge ۲→۳→۰, 15 brand tiles stable, hrefs stable across swap, item_count_after_remove=0.
- **0 console/page/request errors** across the whole matrix.
- Artifacts: `browser/brand/{variant}/{viewport}/{envelope}-public.png`, `browser/fragments/cart/{viewport}/{before,update,remove}.png`, `browser/wrapper_projection/`, `browser/metrics.json`, `browser/r4-browser-result.json`, `browser/db-restore-proof.json`, `browser/fixture.json`. Transient runtime logs (runserver/browser/RECOVERY) excluded from commit.

## A04 (pilot) / A06 (pilot) status after Task 3
- A04 pilot: Brand real Cart fragment container projection PROVEN (V05 Brand portion). Preview wrapper projection PROVEN. Global/Listing/Newsletter A04 remains deferred (V09).
- A06 pilot: Brand proven on all six allowed envelopes (E1–E5 browser + E3 listing/search equivalence; E6 companion boundary asserted, no pilot placement). A06 for Brand family: proven; Collection pending Task 5.

## Scope audit
Production: only apps/cart/views.py (adapter) + storefront_builder.css (brand-scoped). Harness: run.mjs + qa command (phase3 branch). No new renderer/route/engine/variant/migration. R3 phase1 evidence PNGs restored (not part of Phase 3). Confirmed via git.

## Review
Independent semantic_reviewer verdict recorded in ledger.

## Readiness for Task 4
Brand family gate PASS. Only now permit Collection generalization. READY.
