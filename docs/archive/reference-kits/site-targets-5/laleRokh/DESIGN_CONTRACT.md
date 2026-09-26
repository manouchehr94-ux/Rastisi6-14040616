# warm_boutique v2 — laleRokh reference design contract

This contract is the implementation-facing summary for the `warm_boutique`
reference family.  It follows the useful part of the OpenDesign workflow:
extract a design contract first, map it to reusable primitives second, then
implement/diff-test.  **OpenDesign is not a runtime dependency of RastiSi.**

## Authority order

1. Merchant-provided laleRokh screenshots.
2. Real RastiSi browser output from the same viewport.
3. Measured DOM/layout evidence.
4. This document.

Do not copy laleRokh logos, photography, fonts, trust marks, or other brand
assets into production.  The target is composition/geometry/visual weight.

## Source screenshot set

- `ref_02.png` — Home, 1898 × 7341 (primary Home authority)
- `ref_01.png` — Listing, 1898 × 3412
- `ref_03.png` — PDP, 1898 × 1960
- `ref_04.png` — Listing/scrolled state, 1898 × 3332

## Visual identity

- Background: overwhelmingly white.
- Primary emphasis: deep magenta / aubergine.
- Secondary emphasis: bright magenta.
- Commerce action: vivid green.
- Product price: magenta, not green.
- Borders/shadows: light and practical rather than luxurious/editorial.
- Density: real retail density; compact but readable.
- Typography: Persian-first sans-serif hierarchy.

RastiSi palette mapping introduced for this family:

- primary `#8A007A`
- secondary `#C90A8B`
- accent/commerce `#63CF70`
- price emphasis uses primary `#8A007A` (plain-palette contract; no independent theme role)
- page/surface `#FFFFFF`

## Desktop Home silhouette

1. Search-first two-row header.
   - visual right: Store brand/logo
   - center: dominant search
   - visual left: shopper actions
   - row 2: navigation plus account/login affordance
2. Wide, relatively short image-first Hero.
3. Six-item visual category shortcut row.
4. Strong magenta campaign product band with white product cards.
5. Four promotional image/banner cells.
6. Strong green campaign product band with white product cards.
7. Horizontal ``محبوب‌ترین برندها`` brand-discovery row.
8. Deep-aubergine category-special block: three compact product groups in
   parallel white panels, driven by current-Store category/collection data.
9. Two wide pink promotional banners.
10. Deep-aubergine framed suggested-products row with five dense retail cards.
11. The reference has a ``آخرین محصولات مشاهده شده`` heading but no visible
    product content in the supplied capture. RastiSi currently has no true
    recently-viewed Storefront primitive, so v2 deliberately does **not** fake
    this with ``most_viewed`` or another semantically different source.
12. Gray newsletter/information strip near the end.
13. Guarantee/capability row immediately before a light multi-column footer.

## Product card contract

- White bordered card.
- Product image dominates the upper area; `contain` is preferred for packaged
  beauty products.
- Small, pill-like status/discount badges.
- Product title supports two lines.
- Price emphasis is magenta.
- Primary action is a full-width green button at the bottom.
- One-click add is rendered only when `product_card_data.is_quick_add_eligible`
  is true.  Otherwise the same visual slot becomes `انتخاب گزینه‌ها` and links
  to the PDP.  Visual fidelity must never fabricate an unavailable capability.

## Responsive contract

At phone width (~390px):

- main header row is not a squeezed desktop row;
- RIGHT burger, CENTER recognizable brand, LEFT cart/account actions;
- search moves to a full-width row below;
- category shortcuts become horizontal scroll;
- product grids keep two columns where appropriate;
- no horizontal document overflow;
- cart/account/hamburger keep usable touch targets.

## Mapping to RastiSi primitives

- `beauty-magenta` — reusable palette.
- `beauty_editorial` — registered `hero_banner.hero_style`; same Store HeroSlide data, light editorial campaign treatment.
- `beauty_search_nav` — registered Global Header Variant.
- `beauty_retail_columns` — registered Global Footer Variant.
- `beauty_icons` — registered `category_grid.display_mode`.
- `beauty_retail` — registered universal product-card style.
- `campaign_band` — registered `product_section.display_mode`; promotional rail beside a real product grid.
- `catalog_product_wall` — reused ID-free current-Store runtime resolver from
  the completed ibolak/fashion_promo_catalog work, extended with registered
  generic structural layouts `group_columns` and `featured_row`.
- `retail_list` — reusable compact horizontal product-card presentation used
  inside grouped category spotlights; no quick-add semantics are fabricated.
- `beauty_tabs` — registered `brand_carousel.display_mode`; flat bordered merchant-brand discovery row.
- existing `hero_banner`, `multi_banner`, `brand_carousel`, `newsletter` and section
  background/palette-role contracts are reused rather than forked.

## Isolation rules

- No `if template_key == "warm_boutique"` in render/data services.
- No Store slug/PK, Category PK, Product PK or reference merchant asset.
- `fashion_promo_catalog` v7 remains unchanged/frozen.
- Batch 1 changes Home only; Listing and PDP remain on the standard U10
  composition until their dedicated reference passes.
