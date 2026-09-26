# 02 — Beraito → `vibrant_catalog` ("کاتالوگ رنگی") Audit

## 1. URLs and audit timestamp

- Live reference: `https://beraito.com/` — **inspection attempted 2026-08-09, this session.** Both a real headless-Chromium/Playwright navigation (`chromium.launch` → `page.goto`) and the `WebFetch` tool returned `net::ERR_TUNNEL_CONNECTION_FAILED` / `EGRESS_BLOCKED` respectively — this execution environment's network egress proxy blocks `beraito.com` (and every other consumer domain tested) at the infrastructure level, not at the target site. See `00_REPOSITORY_BASELINE.md` and the Gate-1 opening message for the full error text. **No page, viewport, or interaction on the live site was actually rendered or observed.**
- Uploaded lightweight package: `docs/template-references/lightweight-package-reference/RastiSi_Lightweight_Five_Template_Spec/` — `app.js` (`SPECS.beraito`, `PRODUCTS.beraito`, `beraitoHome()`, `standardHead("beraito")`) and `shared.css` (`.beraito` rule block, lines 95-115 + responsive blocks 225-289) — **read in full**, not sampled.

## 2. Accessible and inaccessible evidence

- **Accessible:** the lightweight package's structural contract (layout order, ratios, CSS custom-property values, responsive breakpoint behavior, motion notes) and this task's master prompt's own `vibrant_catalog` baseline (design brief text). Both are **provisional/planning evidence** — they describe intended structure, not a pixel-measured live page.
- **Inaccessible:** every live-rendered fact (actual header height in px, real hover/zoom timing, real mobile breakpoint transition point, real product photography crop/art-direction, real copy) — genuinely unknown, not guessed. Any number below labeled "per lightweight package" is the package's own declared value (e.g. its CSS `min-height`), not a measurement of the real Beraito site.

## 3. Desktop structure (per lightweight package + master-prompt baseline)

Three-tier header (utility bar → logo/search/cart row → nav/mega-menu shell), content width ≈1140px (package's `--content:1140px` for `[data-template="beraito"]`), page opens with a **promo-dashboard** hero (one large deal tile + two stacked side tiles in a 1.3:0.7 grid — `shared.css:101-107`), not a single cinematic hero image. High density: multiple product collections visible in the first scroll (package: "چند محصول هم‌زمان باید در نخستین اسکرول دیده شود").

## 4. Tablet structure

Per package's `@media (max-width:1024px)` block (`shared.css:225-237`): nav becomes horizontally scrollable instead of wrapping; product grid drops from 4 to 3 columns; quick-category grid stays 4 columns (from 8); promo/portrait/category grids collapse to 2 columns generically. No Beraito-specific tablet override beyond the shared 1024px breakpoint — i.e. the package does not claim Beraito needs a *distinct* tablet treatment beyond the shared rules.

## 5. Mobile structure

Per package's Beraito-specific `@media (max-width:720px)` overrides (`shared.css:261-267`): the deal-hero collapses to 1 column (main tile shrinks to 270px min-height, side tiles become a 2-up row); the quick-category grid becomes a horizontally-scrolling rail (`display:flex;overflow:auto`) instead of a fixed grid; the promo grid becomes 2-up. Product grids platform-wide become a horizontal snap-scroll rail of `70vw`-wide cards below 720px (`shared.css:251-252`, not Beraito-specific — shared across all 5 families). Utility bar and desktop nav-shell are hidden below 720px; header becomes a compact 68px-tall grid with search dropping to its own row.

## 6. Homepage section map (declared order, package `beraitoHome()` + `IMPLEMENTATION_SPEC_FA.md` §5)

1. Utility bar (help/contact/email + free-shipping message)
2. Logo / search / account / cart row
3. Nav shell (categories · deals · stationery · entertainment · gifts · brands)
4. Promo-dashboard hero (deal-main + 2 side tiles)
5. Quick category grid (8 icons)
6. Service/trust strip (shipping, returns, support, authenticity — shared component across families)
7. Dense product collection ("پیشنهادهای امروز", renderer note in package: `square_centered_commerce`)
8. Promo banner grid (4 tiles)
9. A second dense product collection ("محصولات پرفروش")
10. (declared but optional in the spec, not in the minimal package build): brand/blog row
11. Dark, multi-column service footer

## 7. Header/navigation contract

Three-row structure is the defining trait: (1) slim dark utility bar, (2) a 3-column grid (logo | search input | account+cart actions) at ~82px min-height, (3) a white nav shell with a bottom border/shadow, horizontally listing top categories. This is structurally different from every other family's header (see `07_CROSS_REFERENCE_MATRIX.md`) — a single shared `page_shell_header.html` (current repo reality, §2.2 of `01_...GAPS.md`) cannot express 3 rows plus a mega-menu shell for Beraito while simultaneously expressing Deeyar's quiet 2-row header without an explicit per-family branch.

## 8. Hero contract

Not a single hero image — a **promo dashboard**: one large gradient tile (`min-height:340px`) plus two smaller stacked tiles, all treated as swappable media slots (emoji placeholders stand in for real merchant imagery/campaign banners). No carousel/autoplay implied by the package. Package explicitly warns against "متن تبلیغاتی داخل bitmap" (promotional text baked into a bitmap) — text must remain real, structured, editable content, not text-in-image.

## 9. Category contract

An 8-icon "quick category grid" directly below the hero — icon + label, `min-height:102px` icon media, becomes a horizontal scroll rail on mobile. This is a lightweight, icon-first category presentation (contrast with Cactus's large portrait-photo category row, or iBolak's editorial tiles — see matrix).

## 10. Product-card contract (`square_centered_commerce`)

- Image ratio **1:1**.
- Title and price **center-aligned** (package: `.beraito .product-info{text-align:center}`).
- Discount badge (percentage pill) on the second-slot product per the package's demo data.
- Old/new price shown together (`<del>` + bold current price).
- Touch-safe CTA — add-to-cart action must not depend on hover (shared platform rule, `IMPLEMENTATION_SPEC_FA.md` §8).
- Radius ≈10px (family-specific — smaller/tighter than most other families).
- High grid density: intended for large SKU counts, not a small curated catalog.

## 11. Product-page contract

Standard side-by-side gallery + purchase panel (not the large/vertical-thumbnail gallery of Cactus/iBolak). Price and CTA are visually dominant over descriptive text ("اطلاعات تخفیف و قیمت... اولویت بصری دارند" — package). Related products reuse the same `square_centered_commerce` card. No campaign/story content on the product page for this family — it is the most price/speed-led of the five.

## 12. Footer contract

Dark, multi-column footer (4-column grid: about + buying guide + quick links + trust/social) — shared footer *content* pattern is already close to the platform's existing single footer partial's toggleable columns (`FOOTER_TOGGLE_FIELDS`, `01_...GAPS.md` §2.1); the *visual treatment* (dark background, specific column proportions `1.3fr 1fr 1fr 1fr`) is family-specific and not achievable via the current `appearance_config` tokens alone (no "footer background dark vs. light" token exists today).

## 13. Motion and interaction contract

Package: "Beraito: shadow/zoom/shine کوتاه" — short, sales-oriented hover motion (card lift + shadow on hover, per shared `.product-card:hover{transform:translateY(-3px)}` base rule, already platform-shared). No family-specific motion beyond the shared subtle-lift default was declared for this family in the package.

## 14. Typography, spacing, color, border, radius, shadow findings

- Accent `#FD445D`, secondary accent tiles use light blue/gold gradients for the promo dashboard.
- Shell background `#F4F5F9` (cooler/greyer than the platform default).
- Radius 10px, content width 1140px — both narrower/tighter than the platform's `modern` template default (18px radius, 1200px width), consistent with a denser, catalog-style family.
- All values above are the **lightweight package's own declared CSS values** (provisional), not measurements from the live site.

## 15. Builder controls required (cross-ref `01_REPOSITORY_ARCHITECTURE_AND_GAPS.md` §2)

Reusable today: section add/remove/reorder/duplicate, `product_section` with `data_source`+`item_limit`+`display_mode`, responsive per-section visibility/columns, palette/font/radius/motion via `appearance_config`. **New, family-specific, not yet possible:** a "family/template" selector that changes header row-count and nav-shell presence, a promo-dashboard hero variant (asymmetric 2-tile-plus-main layout, distinct from the single hero_banner slider), an 8-icon quick-category grid section variant, dark-footer color-scheme toggle.

## 16. Reusable capabilities required

`MerchantCollection` + `product_section` data sources (existing) for every product row; existing `category_grid` section (existing) likely maps to the quick-category grid with a "compact icon" display mode addition; existing service/trust strip maps to `trust_features` section (existing, already platform-shared).

## 17. Content that must not be copied

Beraito's actual brand name/logo, its real discount percentages/campaign copy, its real product photography, its real category taxonomy wording beyond generic Persian category nouns already used in the lightweight package's own demo data (لوازم تحریر، سرگرمی، هدیه — these are the *package's own* placeholder categories, already genericized, safe to reuse as demo-gallery content only, not as a hard-coded platform default).

## 18. Conflicts with the lightweight package

None identified beyond the platform-wide DOM-fork question already raised in `01_...GAPS.md` §2.3 (not specific to this family).

## 19. Unknowns and questions

- Exact live header height/breakpoint transition points, real photography art direction, real mega-menu depth/content — all **unavailable** (network-blocked), tracked as a single cross-family blocking question in `09_QUESTIONS_FOR_OWNER_FA.md` rather than five duplicate per-family questions.
- Whether the "brand/blog row" (declared optional in `IMPLEMENTATION_SPEC_FA.md` §5 but absent from the package's actual `beraitoHome()` build) is in scope — see cross-family scope question.

## 20. Acceptance checklist for this family

- [ ] Header renders 3 distinct rows (utility/main/nav) with a dark utility bar — not achievable by toggling the current shared header partial's existing config flags.
- [ ] Promo-dashboard hero (asymmetric multi-tile), not the existing single `hero_banner` slider, is available as a distinct hero variant.
- [ ] Product card is 1:1, center-aligned, touch-safe CTA, ~10px radius.
- [ ] Quick category grid (8 icons) renders and collapses to a mobile scroll rail.
- [ ] Dense collections (4-6 columns desktop / 3 tablet / rail mobile) remain visually denser than the other 4 families with identical demo data.
- [ ] Dark multi-column footer.
- [ ] Product page is price/CTA-forward, compact gallery, related products in the same card renderer.
- [ ] No hover-only critical action; reduced-motion respected (already a global platform guarantee per `01_...GAPS.md` §5).
