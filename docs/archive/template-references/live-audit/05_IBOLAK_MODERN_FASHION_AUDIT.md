# 05 — iBolak → `modern_fashion` ("مد امروز") Audit

## 1. URLs and audit timestamp

- Live reference: `https://ibolak.com/` — **inspection attempted 2026-08-09.** Blocked identically to the other four via both Playwright/Chromium and `WebFetch` (`EGRESS_BLOCKED`); no live page rendered — see `00_REPOSITORY_BASELINE.md`.
- Lightweight package: `app.js` (`SPECS.ibolak`, `ibolakHome()`, `standardHead("ibolak")`, `productPage("ibolak")`) and `shared.css` (`.ibolak` block, lines 156-175, `.fashion-gallery`, line 219) — read in full.

## 2. Accessible and inaccessible evidence

Accessible: package structural contract + master-prompt baseline. Inaccessible: live measurements, real fashion photography/model imagery, real size-chart content, real story-rail content.

## 3. Desktop structure

`--content:1380px`, white shell, generous whitespace, base radius **16px** (largest baseline radius among the CSS-token-comparable families, tied for softest look). Two-tier header: main row (logo/large search/login/cart) + a second nav row that also carries social links (`nav` includes "Instagram" per the package's own header text — a fashion-brand-typical pattern, generic enough to keep as a structural nav-slot, not a hard-coded Instagram dependency).

## 4. Tablet structure

Shared 1024px rules; `category-tiles` explicitly forced to 2 columns (`shared.css:233`) from 4.

## 5. Mobile structure

iBolak-specific `@media(max-width:720px)` (`shared.css:276-278`): category tiles become a horizontal rail (68vw cards, min-height 330px); the `fashion-gallery` product-detail layout collapses to 1 column with its thumbnail rail reordered below the main image and made horizontally scrollable (`order:2;overflow:auto`, shared rule at line 286 applying to both `.premium-gallery`/`.fashion-gallery`). Story rail (`.ibolak .story-rail`) is already `overflow:auto` at all widths — it's a horizontal rail by design at every breakpoint, not just mobile.

## 6. Homepage section map (`ibolakHome()` + spec §5)

1. Header (logo/search/login/cart row + nav+social row)
2. **Story rail** — 8 circular "story" bubbles (Instagram-story-style), declared as an independent, optional section (spec: "یک Section مستقل و اختیاری است")
3. Hero (fashion carousel per the fuller spec — the minimal package renders a single static hero slide, not an actual 3-slide carousel; noted as a package-internal simplification, see §18)
4. Category tiles — 4 vertical editorial tiles with an English label under a Persian one (`DRESSES`/`TOPS`/`BOTTOMS`/`SHOES`)
5. "جدیدترین استایل‌ها" product row (renderer: `fashion_portrait_gallery`)
6. "پیشنهادهای این هفته" — a second product row
7. Minimal footer

## 7. Header/navigation contract

Two-tier: (1) a 3-column grid (logo | large search input | login+cart actions), (2) a centered nav row that also lists social/app links. Distinct from Beraito's 3-row commerce header (no separate utility bar here) and from Deeyar's single space-between row (iBolak keeps a full dedicated nav row plus a large, prominent search input, closer in weight to Cactus's header but fashion-styled).

## 8. Hero contract

Declared as a **carousel** in the fuller spec (`fashion_carousel`) but the minimal package build only shows one static slide with a rounded-capsule product image (`border-radius:180px`, echoing Cactus's capsule shape but larger, `font-size:140px` in the emoji placeholder) — carousel controls/autoplay/pause/swipe behavior is asserted by the spec text, not demonstrated in the package's actual DOM/JS. This gap is flagged rather than invented — whether autoplay is wanted, and its pause-on-hover/reduced-motion behavior, needs an explicit decision (tracked in the questions document).

## 9. Category contract

Four tall vertical "editorial" tiles (`min-height:390px` at desktop, `border-radius:16px`), each with a bilingual label (Persian caption + English uppercase micro-label) — this bilingual-label pattern is specific to this family in the package and should not silently be assumed for the other four.

## 10. Product-card contract (`fashion_portrait_gallery`)

- Image ratio **9:12** portrait (`aspect-ratio:9/12`, the only family in the package that declares an explicit CSS `aspect-ratio` property rather than only a `min-height`).
- **Wishlist icon** overlaid top-left on every card (`.ibolak .wishlist`, absolute-positioned circular button) — the only family whose card always carries a wishlist affordance in the package's demo.
- **Split title/price layout**: title on one side, price on the other (`.split-info{display:flex;justify-content:space-between}`) — distinct from Beraito/Deeyar's centered layout and from Nordic's two-line-title-plus-description stack.
- Desktop: thumbnail-reveal/zoom(1.08) on hover; mobile: swipe/tap, never relying on hover (explicit in both package and master prompt: "no essential action may depend on hover").
- Discount styling uses a **pink** accent (`#FF0080`) distinct from the family's own primary accent (`#FCBD15`) — package explicitly warns this pink-for-discount choice must not become a hard-coded platform default ("صورتی hard-coded برای تخفیف" is listed under "avoid").

## 11. Product-page contract

Large gallery with a **vertical thumbnail column** (92px wide, `.fashion-gallery`, marginally wider than Cactus's 84px column — the package encodes this as a real, if small, per-family difference). Color + size selectors, a **size chart/guide** (no such field exists anywhere in the current repo — `01_...GAPS.md` §3.1, a cross-family blocking question, not specific to this family alone but most acutely needed here and in `heritage_premium`). Long editorial description, FAQ, reviews, related products in the same `fashion_portrait_gallery` renderer. Color selection must switch the gallery to the matching variant image, same underlying data-layer capability as Cactus (`ProductImage.variant`/`option_value`).

## 12. Footer contract

"Minimal footer" (`shared.css:174`, `background:#f7f7f7`, thin top border) — the lightest-weight footer of all five families; likely the easiest to express with the platform's existing footer-toggle system if the "how sparse" question (how many of the 9 existing `FOOTER_TOGGLE_FIELDS` this family shows by default) is answered explicitly rather than left ambiguous.

## 13. Motion and interaction contract

Package: "iBolak: zoom و thumbnail reveal" on desktop hover; swipe/tap on mobile; the story rail has no motion beyond native scroll. Zoom factor is explicitly `1.08` (a real declared value, not vague "some zoom").

## 14. Typography, spacing, color, border, radius, shadow findings

Accent `#FCBD15` (mustard/gold), discount pink `#FF0080` (card-local, not primary accent), text `#323232`, radius 16px, content width 1380px — package-declared values only.

## 15. Builder controls required

New/family-specific: an optional, independently-toggleable circular story-rail section; a hero variant that is genuinely a multi-slide carousel with real autoplay/pause/swipe controls (currently no section in `SECTION_REGISTRY` implements carousel *hero* behavior — `image_slider` exists as a general slider section but is not the same anatomy as a hero); vertical editorial category tiles with a bilingual label field; the `fashion_portrait_gallery` card (9:12, wishlist, split title/price, pink discount override scoped to this family only); a 92px vertical thumbnail product-gallery layout; a size-guide content field (shared cross-family blocking question).

## 16. Reusable capabilities required

Existing wishlist mechanism (`apps/customers/partials/wishlist_button.html`, already included in the platform's shared `product_card.html` today per `01_...GAPS.md` §2.2) — the wishlist *affordance* already exists platform-wide; this family just needs it visible by default in its own card anatomy, not a new wishlist feature. Existing `product_section` for both product rows; existing variant/option-value image switching for color-driven gallery updates.

## 17. Content that must not be copied

iBolak's real brand name/logo, real fashion photography/model imagery, real story-rail content, real category label wording beyond generic fashion nouns.

## 18. Conflicts with the lightweight package

The spec text (`IMPLEMENTATION_SPEC_FA.md` §5) declares a 3-slide hero carousel; the package's actual `ibolakHome()` build renders one static slide with no carousel JS/controls. This is a real internal gap in the uploaded evidence, not resolved by this audit — tracked as an open question (is a true auto-advancing carousel required for `modern_fashion`'s hero, and if so what pause/swipe/reduced-motion behavior).

## 19. Unknowns and questions

Real fashion photography direction, real size-chart data model, whether the story rail should read from any real data source (recent orders? curated images? none of the above — currently the package treats it as pure decorative content) — size-guide question is shared cross-family; story-rail data-source question is specific to this family.

## 20. Acceptance checklist for this family

- [ ] Header has a large prominent search input and a nav row carrying social links, distinct from Deeyar's icon-only header and Cactus's centered-nav header.
- [ ] Story rail (circular bubbles) renders as an independent, hideable section.
- [ ] `fashion_portrait_gallery` card is genuinely 9:12 with wishlist + split title/price — distinguishable from every other card renderer with identical palette/demo data.
- [ ] Desktop zoom/thumbnail-reveal on hover has a working swipe/tap mobile equivalent; no essential action is hover-only.
- [ ] Product-page gallery uses a vertical thumbnail column; color selection switches the gallery image.
- [ ] Footer renders visibly lighter/sparser than Beraito's dark footer with identical palette.
- [ ] Discount pink is scoped to this family, not leaked into the shared platform discount-badge default.
