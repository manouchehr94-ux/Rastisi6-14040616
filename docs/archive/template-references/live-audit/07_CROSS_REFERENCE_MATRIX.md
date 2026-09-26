# 07 — Cross-Reference Matrix

All entries are sourced from the uploaded lightweight package (`app.js`/`shared.css`) and this task's master prompt, per family, cross-referenced against `01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` for repository reality. Live-site columns are not populated — see each per-family doc's §1/§2 for the recorded access blocker (network egress denied to all five domains, tested via both Playwright/Chromium and `WebFetch`, 2026-08-09).

## Matrix A — structural contract per family

| | `vibrant_catalog` (Beraito) | `heritage_premium` (Cactus) | `artisan_editorial` (Deeyar) | `modern_fashion` (iBolak) | `nordic_living` (IkalaJam) |
|---|---|---|---|---|---|
| Header rows | 3 (utility / main / nav-mega) | 2 (promo-strip+main / nav) | 2 (space-between main / nav) | 2 (main+search / nav+social) | 3 (announce / utility / search-first main+nav) |
| Search presence | input box, medium | input box, medium | icon/link only, no box | input box, **large**, prominent | input box, **accent-bordered**, anchor of row |
| Hero variant | promo-dashboard (multi-tile) | full-bleed campaign (static split) | editorial (sharp full-bleed split) | carousel (declared) / static single slide (built) | neutral circular "living" hero |
| Hero media shape | rounded tiles (12px) | rounded "capsule" (180/180/20/20) | sharp rectangle (0 radius) | rounded "capsule" (180px, larger) | circle (50%) |
| Category presentation | quick icon grid (8, small) | portrait row (6, tall, arched top) | banner grid (4, overlay title) | vertical editorial tiles (4, bilingual label) | **none on homepage** (nav-only) |
| Product-card renderer | `square_centered_commerce` | `premium_portrait` / `premium_campaign` | `artisan_story_card` | `fashion_portrait_gallery` | `catalog_second_image` |
| Card image ratio | 1:1 | ~3:4 | flexible/unlocked | 9:12 | ~7:8 |
| Card title/price alignment | centered | below image, left-flow | centered | split (title one side, price other) | two-line title + optional short desc |
| Card signature interaction | shadow/zoom "shine" on hover | side action reveal, gentle fade | very soft border/shadow, minimal motion | desktop zoom 1.08 + thumbnail reveal; mobile swipe/tap | bottom action-rail slide-up; **no** hover-lift |
| Second/variant image on card | no | no (variant image lives on product page) | no | yes (multi-image on desktop) | yes (declared: second-image crossfade — **not demonstrated in package JS**, see doc 06 §10/§18) |
| Default grid density (desktop) | high (4-6 col) | medium (4 col, tall cards) | medium (varies) | medium (varies, rail-friendly) | medium (varies) |
| Product-page gallery | standard side-by-side | vertical thumbnail column (84px) | simple/warm | vertical thumbnail column (92px) | two-column, separated |
| Product-page purchase panel emphasis | price/CTA dominant | color+size+inventory+optional campaign | short story near CTA | color+size+size-chart | brand+short facts+favorite |
| Product-page distinct element | — | optional video tab | maker/region metadata | size chart (no data field exists) | 3-cell facts strip |
| Footer color | dark, multi-column | light/warm, identity-led | warm, story-forward | light, minimal/sparse | dark navy, multi-tier |
| Radius (package-declared) | 10px | 8px | 8-15px | 16px | 4px |
| Content width (package-declared) | 1140px | 1600px | 1540px | 1380px | 1320px |
| Accent color | `#FD445D` | `#07705E` | `#888210` | `#FCBD15` | `#183E85` |
| Mobile card layout | horizontal snap rail (shared rule) | horizontal snap rail (shared rule) | horizontal rail for story cards (narrative content, not product cards) | horizontal rail for category tiles + story rail always-rail | banner-pair stacks 1-col; action-rail becomes static |
| Live evidence URL / date | `https://beraito.com/` — inspection blocked 2026-08-09 | `https://cactusleather.ir/` — inspection blocked 2026-08-09 | `https://deeyarstore.com/` — inspection blocked 2026-08-09 | `https://ibolak.com/` — inspection blocked 2026-08-09 | `https://www.ikala-jam.ir/` — inspection blocked 2026-08-09 |

## Matrix B — required Builder settings / commerce fields / optional capabilities / fallback

| | Required Builder settings (new, beyond current registry) | Required Product/Variant fields | Optional capabilities | Fallback behavior when data is missing |
|---|---|---|---|---|
| `vibrant_catalog` | promo-dashboard hero variant; quick-icon-grid category variant; dark-footer color scheme | none new — uses existing `Product`/`ProductVariant`/`MerchantCollection` | brand/blog row (spec-only, not in minimal package — scope question) | missing image → existing product-card fallback icon (already implemented, `product_card.html:9`) |
| `heritage_premium` | full-bleed campaign hero variant; portrait-category-row variant; `premium_portrait`/`premium_campaign` card modes; light-footer scheme; vertical gallery thumbnails | **size-guide content field (does not exist — blocking)**; optional installment/campaign data (does not exist as real data — currently a hardcoded fake countdown in an unrelated section, `render_service.py:155`, must not be copied) | optional product video (already supported, `ProductVideo`) | no campaign data → card renders without the optional overlay, never a fake countdown |
| `artisan_editorial` | space-between single-row header variant; sharp-edge editorial hero; 2×2 overlay-banner category variant; `artisan_story_card` with optional maker/region metadata; independently-orderable "About" section | optional maker-name/region field on `Product` or `Vendor` (does not exist — needs a decision: new field vs. reuse `Vendor`/description text) | none mandatory | no maker/region set → metadata line simply omitted, card layout unaffected |
| `modern_fashion` | search+social two-row header; real carousel hero (autoplay/pause/swipe) or confirmed single-slide baseline; bilingual-label category tiles; `fashion_portrait_gallery` card (wishlist, split layout, scoped pink discount); vertical gallery thumbnails (92px) | **size-guide content field (shared with `heritage_premium` — same blocking question, not two separate ones)** | optional independent story-rail data source (currently pure decorative content in the package — needs a decision if it should ever read real data) | no size-chart data → selector still renders, size-chart panel omitted |
| `nordic_living` | search-first anchor header (accent-bordered search); circular living hero; **no default homepage category section** (or an explicit opt-in one, per owner decision); `catalog_second_image` card (two-line title, action-rail, no hover-lift, optional real crossfade); 3-cell facts strip | optional second product image required for crossfade to activate — needs an explicit **no-crossfade-with-one-image fallback rule** | none mandatory | product has 1 image → card renders without crossfade, single static image, no error |

## Matrix C — same palette/typography/demo data: what keeps each family recognizable

Per the master prompt's explicit requirement ("Add a second matrix that compares all five families using the same palette, typography, and demo data"): the repository's own recent commit history (`01_...GAPS.md` §2.2) already proves, empirically, that palette/typography/radius/motion/density alone are **not sufficient** to keep families distinguishable at the anatomy level the master prompt requires — the existing 10 `appearance_registry.py` templates vary exactly those tokens today and share one header, one footer, one product-card, one product-page DOM. With identical palette and typography forced across all five new families, what must still visibly differ, per the evidence above, is:

1. **Header row count and composition** — 3 rows with a utility bar (Beraito/Nordic) vs. 2 rows with no utility bar (Cactus/Deeyar/iBolak) vs. presence/absence of a search input box at all (Deeyar has none; every other family does).
2. **Hero media shape and type** — rounded tile grid vs. capsule vs. sharp rectangle vs. circle vs. carousel — a geometry/DOM difference, not a color difference.
3. **Presence/absence of a homepage category section at all** — four families have one, `nordic_living` structurally does not (nav-only).
4. **Product-card image aspect ratio and information layout** — 1:1-centered vs. 3:4-info-below vs. flexible-centered-with-optional-metadata vs. 9:12-split-with-wishlist vs. 7:8-two-line-title-with-description — five genuinely different anatomies, independently of any single color token.
5. **Presence of family-unique elements with no cross-family equivalent** — Cactus/iBolak's optional video tab and size-chart vs. Deeyar's maker/region metadata vs. Nordic's 3-cell facts strip vs. Beraito's price/CTA-forward compactness — these are content-slot differences, not stylistic ones.

Conclusion carried into `08_TARGET_ARCHITECTURE_AND_FILE_PLAN.md`: the five families cannot be implemented as five more entries in the existing CSS-token `TEMPLATE_REGISTRY` — they require a genuinely new, DOM-forking concept for header/hero/category/card/product-page anatomy, with the *existing* `appearance_registry.py` remaining the correct mechanism for palette/typography/radius/motion/density **within** whichever family is active.
