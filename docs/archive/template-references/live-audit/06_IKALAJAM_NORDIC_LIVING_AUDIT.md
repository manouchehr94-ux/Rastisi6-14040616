# 06 — IkalaJam → `nordic_living` ("خانه آرام") Audit

## 1. URLs and audit timestamp

- Live reference: `https://www.ikala-jam.ir/` — **inspection attempted 2026-08-09.** Blocked identically to the other four (both Playwright/Chromium and `WebFetch` returned `EGRESS_BLOCKED`/`ERR_TUNNEL_CONNECTION_FAILED`); no live page rendered — see `00_REPOSITORY_BASELINE.md`.
- Lightweight package: `app.js` (`SPECS.ikalajam`, `ikalajamHome()`, `standardHead()` default branch, `productPage("ikalajam")`) and `shared.css` (`.ikalajam` block, lines 177-194, `.nordic-facts`, line 222) — read in full.

## 2. Accessible and inaccessible evidence

Accessible: package structural contract + master-prompt baseline. Inaccessible: live measurements, real home/decor photography, real mega-menu depth, real footer tier count.

## 3. Desktop structure

`--content:1320px` (spec text says "up to 1440px on large displays" — the package's CSS hardcodes 1320px; the wider figure is prose aspiration, same package-internal looseness pattern seen for Cactus/Deeyar, not a live-site fact). Radius is the **tightest of all five families**, `4px` (`shared.css:26`) — a deliberately squared-off, structured look, consistent with "Border/Background مهم‌تر از Shadow" (package). Three-row header: black announcement bar → utility row → main search-first row with a thick 2px bordered search box (`.ikalajam .search{border:2px solid #183e85}`, the only family whose search box gets an accent-colored border rather than a neutral one) → a bordered nav shell below.

## 4. Tablet structure

Shared 1024px rules apply generically; no Nordic-specific tablet override beyond them was found in the package (the spec text's own §7 calls out "زیر 991px" as *this family's* stated mobile-bar threshold, which is different from the platform-shared 1024px/720px breakpoints used everywhere else in the package's actual CSS — a real, if minor, package-internal inconsistency, flagged rather than silently reconciled).

## 5. Mobile structure

Nordic-specific `@media(max-width:720px)` (`shared.css:279-280`): the two-up banner-pair collapses to 1 column; the card's desktop-only `action-rail` (see §10) becomes `position:static` (always visible, not hover-revealed) — this is the explicit, package-encoded touch-fallback for the family's signature hover interaction.

## 6. Homepage section map (`ikalajamHome()` + spec §5)

1. Black announcement bar (short editable text)
2. Utility row (custom-order/support · social/order-tracking)
3. Search-first main header row + grouped mega-nav shell below
4. Neutral, category-led hero (no campaign copy, minimal CTA — "متن کوتاه، فضای سفید و CTA محدود")
5. Service/trust strip
6. "تازه‌های خانه" product collection (renderer: `catalog_second_image`)
7. Two-up thematic banner pair
8. "پرفروش‌های دکور" — a second product collection
9. Multi-tier information footer (dark blue, `#17386f`)

The fuller spec (§5) additionally lists "چهار بنر موضوعی" (four banners) where the minimal package build only renders a **two**-up banner pair — same package-internal looseness pattern as the other three families; flagged, not silently expanded to four.

## 7. Header/navigation contract

Three-row, but distinctly **search-first** rather than commerce-dashboard-first (Beraito) or campaign-first (Cactus): announcement → utility → a prominent bordered search box as the visual anchor of the main row, with account/cart as secondary. The only family whose search input itself carries a strong accent border rather than a neutral one — a genuine, small, real structural/style signal that this family is about depth-of-catalog search, not promotion.

## 8. Hero contract

Neutral, circular-media "living hero" (`border-radius:50%` on the hero image slot, `background:#f8f5ef` — the only family whose hero media is fully circular rather than rectangular/capsule/arched) — deliberately calm, category-led, minimal copy and a single restrained CTA ("مشاهده فضای نشیمن").

## 9. Category contract

No dedicated category-tile/banner-row section in the minimal package build at all — category access for this family is implied to happen through the search-first header's grouped mega-nav, not a homepage category grid. This is a real structural difference from all four other families (which all have an explicit homepage category section) and should be treated as an intentional family trait, not an oversight, unless the owner says otherwise (tracked as a question).

## 10. Product-card contract (`catalog_second_image`)

- Image ratio **~7:8** (`aspect-ratio:7/8`), gentler/less extreme than iBolak's 9:12.
- **Two-line title** + optional short description below the price (package demo: "توضیح کوتاه و اختیاری برای کاربرد محصول") — the only family whose card explicitly reserves space for descriptive text under the price, not just above/beside it.
- Desktop: a bottom **action rail** slides up on hover (`position:absolute; ...; transform:translateY(130%)`, revealed via `:hover{transform:translateY(0)}`) reading "مشاهده سریع · افزودن به سبد" — and, critically, a **second-image crossfade** is implied by the family name/renderer key (`catalog_second_image`) though the minimal package's own card markup does not actually implement a second `<img>`/crossfade transition in its JS (`cards()` function only renders one `media()` call per card) — this is a real gap between the family's *name/intent* and what the package *demonstrates*, flagged rather than invented.
- Card itself has **no hover-lift** (`.ikalajam .product-card:hover{transform:none; background:#f2f2f2}`) — the only family whose card explicitly suppresses the platform-shared hover-lift default in favor of a flat background-tint hover instead.
- Radius 4px, tightest/most "squared" card of the five.

## 11. Product-page contract

Two-column layout: gallery and info are genuinely separate columns (not overlaid), brand name, short description, a 3-cell "facts" strip (`.nordic-facts`: material/dimensions/color, `grid-template-columns:repeat(3,1fr)`, bordered cells — a distinct, real UI element not present in any other family's product-page contract), favorite/wishlist action, longer editorial description below, related/similar products in the same `catalog_second_image` renderer.

## 12. Footer contract

Multi-tier, dark blue (`#17386f`) — information-dense (per the fuller spec, "چندسطحی"), the only family whose footer is a distinct non-neutral brand color (Beraito's is dark grey/black-ish, iBolak's is light grey, Cactus/Deeyar's are light/warm).

## 13. Motion and interaction contract

Package: "IkalaJam: second-image crossfade و action rail" for desktop; mobile replaces the hover action-rail with an always-visible static CTA. As noted in §10, the crossfade half of this contract is asserted by the family's own renderer name but not actually demonstrated in the package's JS — an implementation detail to resolve during Gate 3 build, not something to silently invent as "however the beraito/cactus card image-swap already works" without checking whether such a mechanism exists anywhere in the current repo (it does not — no card in the current `product_card.html` implements any image crossfade today, per `01_...GAPS.md` §2.2).

## 14. Typography, spacing, color, border, radius, shadow findings

Accent `#183E85` (navy), secondary `#FFDB01` (yellow, used as `--accent-2` i.e. a background/highlight tone, not literally as button color), neutral grey `#F2F2F2`, radius 4px, content width 1320px. Package-declared values only.

## 15. Builder controls required

New/family-specific: a genuinely search-first header layout with an accent-bordered search box and no homepage category section (category access via mega-nav only); a circular "living" hero variant; a `catalog_second_image` card renderer with two-line-title + short description + bottom action-rail + (if approved) a real second-image crossfade mechanism; a 3-cell product-facts strip on the product page; a dark-navy footer color scheme.

## 16. Reusable capabilities required

Existing `product_section` (collection/manual/newest data sources) for both homepage product rows; existing responsive/per-section settings for the two-up-to-one-column banner-pair collapse; existing wishlist/favorite mechanism for the product-page favorite action.

## 17. Content that must not be copied

IkalaJam's real brand name/logo, real home/decor photography, real mega-nav taxonomy wording. The package explicitly warns: "وابستگی به نام یا ظاهر IKEA" must be avoided — this family's neutral, structured, home-goods aesthetic must not be built or marketed as visually derivative of a specific well-known third-party retailer's identity.

## 18. Conflicts with the lightweight package

Two internal package gaps flagged above: (a) the spec text's "991px"/"four banners" figures don't match the package's own CSS (720px-breakpoint, two-up banner pair); (b) the `catalog_second_image` renderer name implies a second-image crossfade that the package's demo JS does not actually implement. Neither is a conflict with a live site (which was inaccessible) — both are internal inconsistencies within the uploaded package itself, surfaced so they are resolved by an explicit decision rather than silently picked one way.

## 19. Unknowns and questions

Whether a homepage category section should exist for this family at all (currently absent from the package by design, per §9); the true second-image crossfade mechanism and its data source (does every product need ≥2 images for this to activate, and what's the fallback for products with only one image); real mega-nav depth/grouping.

## 20. Acceptance checklist for this family

- [ ] Header is genuinely search-first (bordered, accent-colored search box as the visual anchor) — distinct from Deeyar's icon-only header and Beraito's dashboard header with identical palette.
- [ ] Hero media is circular, category-led, minimal-copy.
- [ ] No homepage category-grid section renders by default for this family (or, if the owner decides otherwise, one is added deliberately, not defaulted-in silently).
- [ ] `catalog_second_image` card has a two-line title + optional short description, a hover action-rail with a static mobile fallback, and no hover-lift transform.
- [ ] If a second-image crossfade is approved in scope: it activates only when a product genuinely has ≥2 images, with a defined no-crossfade fallback for single-image products.
- [ ] Product page shows a 3-cell facts strip (material/dimensions/color or equivalent) as a distinct UI element.
- [ ] Footer renders dark navy, multi-tier — distinguishable from every other family's footer color with identical palette.
