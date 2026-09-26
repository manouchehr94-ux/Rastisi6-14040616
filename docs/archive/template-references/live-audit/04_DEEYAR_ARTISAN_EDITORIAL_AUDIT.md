# 04 — Deeyar Store → `artisan_editorial` ("روایت هنر") Audit

## 1. URLs and audit timestamp

- Live reference: `https://deeyarstore.com/` — **inspection attempted 2026-08-09.** Blocked identically to the other four (`EGRESS_BLOCKED`/`ERR_TUNNEL_CONNECTION_FAILED`); no live page rendered — see `00_REPOSITORY_BASELINE.md`.
- Lightweight package: `app.js` (`SPECS.deeyar`, `deeyarHome()`, `standardHead("deeyar")`) and `shared.css` (`.deeyar` block, lines 133-154) — read in full.

## 2. Accessible and inaccessible evidence

Accessible: package structural contract + master-prompt baseline. Inaccessible: live measurements, real craft/workshop photography, real maker/region copy, real blog content.

## 3. Desktop structure

Widest range of any family: `--content:1540px` up to "1540–1676px" per the spec's own prose (the package's CSS hardcodes 1540px; the wider figure is the fuller spec document's aspiration, not yet reflected in the minimal build — noted as a package-internal looseness, not a live-site fact). Quiet, two-level header (`.deeyar .main-head{display:flex;justify-content:space-between}` — no 3-row utility/nav split; search/account/cart are inline text links beside the logo, not a search input box). This is the calmest header of all five families.

## 4. Tablet structure

Shared 1024px rules; `banner-grid` (4 category banners) explicitly forced to 2 columns (`shared.css:234`), same treatment as other families' banner grids — no Deeyar-specific tablet override beyond the shared rule.

## 5. Mobile structure

Deeyar-specific `@media(max-width:720px)` (`shared.css:273-275`): the About split becomes single-column; the story/workshop card row becomes a horizontal scroll rail (78vw cards). Package explicitly calls for narrative/story content (not just products) to use a horizontal rail on mobile, distinct from the platform-shared product-grid rail.

## 6. Homepage section map (`deeyarHome()` + spec §5)

1. Quiet two-level header + centered nav (تازه‌ها · صنایع‌دستی · خانه و دکور · هدیه · داستان ما · مجله)
2. Editorial hero (full-bleed image + copy, no rounded capsule, sharp edges — `border-radius:0`)
3. Four artisan category banners (2×2 grid)
4. "تازه‌های کارگاه" product collection (renderer: `artisan_story_card`)
5. **About split** — a full homepage section (image + long-form copy + CTA), *not* a footer afterthought; the spec is explicit that this must remain a real, independently movable/hideable Builder section
6. "مجله و کارگاه‌ها" — 3 story/blog cards (maker interview, materials story, styling-with-craft ideas)
7. Trust/story footer

The fuller spec (`IMPLEMENTATION_SPEC_FA.md` §5) additionally lists "بنر صنایع" and "کالکشن‌های Tabbed" and a "Social gallery" between steps 4 and 6 above that the minimal package build does not actually render — same package-internal looseness noted for Cactus; flagged as an open scope question rather than invented.

## 7. Header/navigation contract

Single row, `justify-content:space-between` — logo on one side, a compact `⌕ جست‌وجو · ♙ حساب · 🛒 سبد` action cluster on the other, and a separate centered nav row below with a top+bottom border (`shared.css:136`). No search *input box* is rendered in the header itself (unlike every other family) — search is presented as a link/icon, consistent with a "quiet, craft-focused" positioning rather than a "search-first" one (contrast directly with Nordic Living's search-first header).

## 8. Hero contract

Full-bleed **editorial hero** — sharp rectangular image (no rounding, `border-radius:0`), asymmetric 1.1:0.9 copy/image split, large serif-scale heading. No carousel implied.

## 9. Category contract

Four square-ish banners with overlay titles (`banner-grid`, 4-up desktop → 2-up tablet/mobile-ready via the shared rule) — text is layered on the image with backdrop-blur per the spec ("Backdrop blur"), not baked into the bitmap.

## 10. Product-card contract (`artisan_story_card`)

- Configurable/adjustable image ratio (the package does not hardcode a single fixed ratio for this family the way Beraito/Cactus/iBolak/Nordic do — `.deeyar .product-card .emoji-media{min-height:280px}` is a minimum, not an aspect-locked value).
- Title **center-aligned**, calm typography, no shouting badges.
- Optional maker/region metadata line ("ساخته‌شده در کارگاه محلی" in the package's demo data) — this optional metadata slot is what most distinguishes this card from a generic card, per both the package and the master prompt ("Metadata کوتاه سازنده/منطقه اختیاری است و کارت را از کارت عمومی جدا می‌کند").
- Very soft border/shadow (`box-shadow:0 18px 50px #544a3210` on the product panel, an unusually soft/large-radius shadow value) and very low motion.

## 11. Product-page contract

Simpler gallery and purchase panel than the "technical" families (Cactus/iBolak) — story/short-narrative content sits close to the title/price/CTA, not relegated below the fold. Wishlist, quantity, related products (same `artisan_story_card` renderer), and long editorial description are present; technical specifications are secondary but not removed ("مشخصات فنی اهمیت ثانویه دارد اما حذف نمی‌شود").

## 12. Footer contract

"Trust/story" footer — similar column structure to the platform-shared footer toggles, warm background tone, no dark-mode treatment (contrast with Beraito).

## 13. Motion and interaction contract

Package: "Deeyar: border/shadow بسیار ملایم" — very gentle border/shadow, minimal motion overall (`motion:"none"` equivalent intent, though this exact family isn't literally one of the 10 existing `TEMPLATE_REGISTRY` entries — see `01_...GAPS.md` §2.2 for why the existing motion token vocabulary, `none|subtle|dynamic`, is reusable here even though the DOM anatomy is not).

## 14. Typography, spacing, color, border, radius, shadow findings

Accent `#888210` (olive), radius 8-15px range (the package explicitly gives a *range* for this family rather than one fixed value, `SPECS.deeyar.components`), warm off-white background (`#faf9f6`/`#ede9df`/`#eee9dd` across sections) — all package-declared values, not live measurements.

## 15. Builder controls required

New/family-specific: a single-row "space-between" header layout distinct from every other family's header row-count; a sharp-edged (no-radius) editorial hero variant; a 2×2 category-banner-with-overlay variant; an `artisan_story_card` renderer with an optional maker/region metadata field; a dedicated, independently-orderable "About split" homepage section (image+long-copy+CTA) — this is not quite the existing generic `image_text` section (which is a general-purpose block, not specifically an "About the maker" composition with a defined image-left/copy-right anatomy) and should be evaluated against reusing `image_text` with a `variant` setting before inventing a new section type.

## 16. Reusable capabilities required

`rich_text`/`image_text` sections (existing) very likely cover the "About split" and "story/workshop cards" needs with new variant settings rather than new section types; `product_section` (existing) for the craft-collection grid; existing sanitized-HTML pipeline for long editorial descriptions.

## 17. Content that must not be copied

Deeyar's real brand name/logo, real artisan/workshop photography, real maker names/regions, real blog/magazine article content. Package explicitly flags: "Blog اجباری" and "Instagram اجباری" and "سبز hard-coded در component" as things to avoid — storytelling content must stay optional and merchant-editable, and the olive accent must stay a palette choice, not a hard-coded component color.

## 18. Conflicts with the lightweight package

The fuller spec's declared section list (§5, ~10 sections) exceeds what the minimal package build actually renders (~7 sections) — see §6 above; flagged, not silently resolved.

## 19. Unknowns and questions

Whether "Tabbed collections" (spec-only, not in the minimal build) is in v1 scope; real workshop/maker photography direction — both tracked centrally.

## 20. Acceptance checklist for this family

- [ ] Header is a single space-between row + separate centered nav row, with search/account/cart as compact icon-links, not an input box — visibly distinct from Nordic Living's search-first header with identical palette.
- [ ] Hero has sharp (unrounded) full-bleed imagery.
- [ ] `artisan_story_card` renders with an optional maker/region metadata line, distinct DOM from `square_centered_commerce`/`catalog_second_image`.
- [ ] An "About" section exists as an independently orderable/hideable homepage section, not hard-coded.
- [ ] Story/workshop cards become a horizontal mobile rail, distinct from the platform-shared product-grid rail treatment.
- [ ] No hard-coded olive color in component CSS (palette-driven only); no mandatory blog/Instagram section.
