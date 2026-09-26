# 03 — Cactus Leather → `heritage_premium` ("پرمیوم اصیل") Audit

## 1. URLs and audit timestamp

- Live reference: `https://cactusleather.ir/` — **inspection attempted 2026-08-09.** Both Playwright/Chromium and `WebFetch` were blocked by this environment's network egress proxy (`EGRESS_BLOCKED` / `ERR_TUNNEL_CONNECTION_FAILED`). No live page was rendered or observed — see `00_REPOSITORY_BASELINE.md`.
- Lightweight package: `app.js` (`SPECS.cactus`, `cactusHome()`, `standardHead("cactus")`, `productPage("cactus")`) and `shared.css` (`.cactus` block, lines 116-131, plus `.premium-gallery`, lines 217-218) — read in full.

## 2. Accessible and inaccessible evidence

Accessible: lightweight package's structural contract + master prompt's own `heritage_premium` baseline. Inaccessible: all live-rendered measurements, real leather-goods photography/art-direction, real campaign copy, real size/color inventory data — genuinely unknown.

## 3. Desktop structure

Widest container of all five families: `--content:1600px` (`shared.css:23`), generous white space, calmer rhythm ("چگالی متوسط و ریتم آرام" — package). Sticky-feeling premium header (search input up to 600px wide, centered nav row below with a top border). Full-bleed campaign hero, `min-height:620px`, asymmetric 1.35:0.65 grid, gradient background evoking leather/desert tones — a rounded "capsule" media shape (`border-radius:180px 180px 20px 20px`) for the hero product image, not a plain rectangle.

## 4. Tablet structure

Shared 1024px breakpoint rules apply (nav scroll, 3-col product grid); portrait-category row explicitly forced to 3 columns (`.portrait-cats{grid-template-columns:repeat(3,1fr)!important}`, `shared.css:231`) — package treats this as a real per-family override, not left to the generic 3-column fallback that other grids get automatically.

## 5. Mobile structure

Cactus-specific `@media (max-width:720px)` rules (`shared.css:270-272`): the portrait-category row becomes a horizontal scroll rail with 42vw-wide cards (min-height 210px, down from 260px desktop) — an explicit swipeable rail, not a stacked column. Hero drops to single column with the product capsule shrinking to 300px min-height. Package note: hero "می‌تواند Asset/Crop مخصوص Mobile داشته باشد، بدون Duplicate کامل markup" — a distinct mobile crop is allowed, a duplicated hero markup tree is not.

## 6. Homepage section map (`cactusHome()` + spec §5)

1. Promotion strip (editable campaign text, explicitly *not* baked into an image)
2. Premium header (logo / search / account+cart) + centered category nav
3. Full-bleed campaign hero (copy + rounded product-capsule media)
4. Portrait category row — 6 categories
5. Campaign product grid (renderer note: `premium_campaign` — discount/installment overlay optional)
6. New-arrivals product grid
7. Promotional image grid (declared in spec, not built in the minimal package — flagged below)
8. Service/trust strip
9. Best-sellers grid
10. (optional, spec-only) blog
11. Light, identity-forward footer

## 7. Header/navigation contract

Two-tier, calmer than Beraito: no separate utility bar in the package build (a slim promo strip instead, which is content not utility links), a single main row (logo/search/actions), then a centered nav row with a top border. Distinctly quieter than Beraito's 3-row commerce header, distinctly *not* as minimal as Deeyar's single-row header (Cactus keeps a full dedicated nav row; Deeyar's nav sits directly beside the logo — see matrix).

## 8. Hero contract

Full-bleed **campaign hero** (asymmetric copy+image split), not a slider/carousel in the package's baseline — a static, high-impact campaign statement is the family's signature, in contrast to Beraito's multi-tile promo dashboard or iBolak's 3-slide carousel.

## 9. Category contract

**Portrait category row** — 6 tall image cards (`min-height:260px`, top corners heavily rounded `140px 140px 12px 12px` — an explicit "arched" portrait treatment distinct from any other family's category presentation), each just an image + one-line label.

## 10. Product-card contract — two renderer modes: `premium_portrait` and `premium_campaign`

- Image ratio near **3:4** portrait (`min-height:390px` card media, taller than Beraito's square cards).
- Information sits **below** the image, not overlaid.
- Minimal on-card tooling — package explicitly warns against "Share روی همه کارت‌ها" (a share icon on every card) and "Action فقط Hover" (hover-only actions).
- `premium_campaign` mode adds an optional discount/installment overlay badge — must remain optional and provider-neutral per the master prompt (no hard dependency on a specific payment/installment provider).
- Light, identity-forward footer color (`#f4f1eb` background, dark text) — inverse of Beraito's dark footer.

## 11. Product-page contract

Large **vertical-thumbnail gallery** (`.premium-gallery{grid-template-columns:84px 1fr}`, thumbnails stacked left of the main image — package's thumbnail column is fixed at 84px, distinct from iBolak's 92px fashion-gallery column, a deliberately small but real difference the package encodes). Purchase panel: color + size selection, inventory/availability, price, optional payment/installment info. Tabs for specifications/reviews/**optional product video** (video is explicitly a capability, not a mandatory section, per both the package and the repo's existing `ProductVideo` model — `01_...GAPS.md` §3). Color selection must switch the gallery to the matching variant image — already supported at the data layer today (`ProductImage.variant`/`option_value`, `01_...GAPS.md` §3) and just needs to be wired into this family's gallery renderer.

## 12. Footer contract

Light/warm, identity-led — contact/address/social presented with more visual weight than promotional content (package: "تماس، آدرس و شبکه اجتماعی پررنگ‌تر از تبلیغات"). Structurally similar column layout to the platform's shared footer toggles, but light-background — same token gap as Beraito's dark footer (no existing "footer color scheme" token).

## 13. Motion and interaction contract

Package: "Cactus: side action/fade آرام" — calm, side-positioned action reveal and gentle fades; explicitly no duplicate desktop/mobile markup trees, and any side-positioned desktop-only action must have a touch-equivalent (persistent button) on mobile.

## 14. Typography, spacing, color, border, radius, shadow findings

- Accent `#07705E` (deep green), warm leather-gold companion tone (`~#DDB475`, per `SPECS.cactus.components`), radius 8px (tightest of the "calm" families, second-tightest overall after Beraito), content width 1600px (widest of all five). All values are the package's declared CSS, not live measurements.

## 15. Builder controls required

New/family-specific, not yet possible today: a full-bleed asymmetric campaign-hero variant with a rounded "capsule" media slot; a portrait category-row variant with the arched corner treatment; two distinct product-card render modes (`premium_portrait`/`premium_campaign`) switchable per product-section instance; a light-footer color-scheme toggle; a vertical (left-column) gallery-thumbnail layout for the product page, distinct from a horizontal one.

## 16. Reusable capabilities required

Existing `product_section` (collection/manual data source) for campaign and new-arrivals/best-seller grids; existing size/color variant selection data (`ProductVariant`, `ProductOptionValue`) for the purchase panel; existing `ProductVideo` (YouTube/Aparat) for the optional product video tab; existing responsive/per-section settings for the portrait-row's tablet 3-column override.

## 17. Content that must not be copied

Cactus Leather's real brand name/logo, real leather-goods photography, real campaign copy/discount claims, real address/phone/social handles.

## 18. Conflicts with the lightweight package

The full spec (`IMPLEMENTATION_SPEC_FA.md` §5) lists a "Promotional image grid" section between new-arrivals and the service strip that the package's own `cactusHome()` build does **not** actually render (only 5 of the ~11 declared sections are wired up in the minimal HTML/JS demo). This is a minor internal inconsistency in the uploaded package itself, not a conflict between the package and a live site — flagged so it is not silently "filled in" with an invented design; treated as an open scope question (does the promotional image grid ship in v1 or is it deferred).

## 19. Unknowns and questions

Real product photography/crop, real header height, real size-guide UI (no size-guide field exists anywhere in the repo today — `01_...GAPS.md` §3.1, a cross-family blocking question) — all tracked centrally rather than duplicated five times.

## 20. Acceptance checklist for this family

- [ ] Header is a calm two-tier structure (no dark utility bar, no mega-menu shell) — visibly distinct from Beraito's 3-tier header with identical palette/typography.
- [ ] Hero is a static full-bleed campaign split, not a slider.
- [ ] Portrait category row with arched-corner media renders and becomes a swipeable rail on mobile.
- [ ] Both `premium_portrait` and `premium_campaign` product-card modes exist as real, distinct render branches.
- [ ] Product-page gallery uses a left-column vertical thumbnail rail; color selection switches the visible variant image using existing `ProductImage` data.
- [ ] Footer renders light/warm, not the platform's dark default.
- [ ] No critical action is hover-only; no duplicated desktop/mobile markup tree for the hero.
