# RastiSi — shokolati Reference Design Contract

Target Ready Template: `premium_leather`
Reference family: `shokolati`
Scope of this contract: Home-first structural rebuild; Listing/PDP are documented for later precision passes.

## 1. Non-negotiable architecture

- Same Universal Storefront Engine and merchant data model.
- No `if template_key == "premium_leather"` in generic render/data services.
- No Store/Product/Category PK hardcoding.
- Reference brand assets, logos, ENAMAD, SnappPay marks, third-party product photography, and fonts are analysis-only and must not be copied into production assets.
- Existing `fashion_promo_catalog` and `warm_boutique` variants stay isolated/frozen.
- Reuse existing registered primitives whenever their semantic and structural contract matches.

## 2. Reference visual DNA

### Palette
- Page field: very pale cool blue, approximately `#EDF6FF` / `#EAF3FC`.
- Primary chrome: chocolate brown, approximately `#7B4417`–`#8A4F1B`.
- Deep footer: near-black `#050505`.
- Warm accent/CTA: caramel-brown / amber, approximately `#8C511C` and `#F3C35C` where a high-emphasis action is needed.
- Card surface: white.
- Text: near-black / warm charcoal.

### Typography
- Persian sans for commerce/body copy.
- Logo may be a real merchant logo; do not fabricate the reference logo.
- Product titles are compact and practical, not editorial/serif-heavy.

### Header
Desktop is a deliberate two-row composition:
1. Brown primary row:
   - visual left: shopper actions/cart/login
   - center: merchant brand/logo
   - visual right: prominent search
2. White navigation row:
   - many category/nav links, horizontal and compact
   - active item receives brown underline/emphasis

Mobile must be a deliberate composition rather than compressed desktop:
- burger + centered/recognizable brand + shopper actions
- search on its own full-width row if necessary
- no overflow or clipped brand

### Home silhouette
1. Story/shortcut rail of circular merchant media.
2. Large rounded hero/carousel, with partial adjacent slides visible on desktop when space permits.
3. Compact hero pagination/dots.
4. Category shortcut field: roughly 12 compact illustrated/media categories, typically two desktop rows, each with a brown pill label.
5. Wide campaign/banner.
6. Product merchandising row (typically 4 cards desktop).
7. Brown promo mosaic / campaign tiles.
8. Another product merchandising row.
9. Two/three editorial/category promo tiles.
10. Social/about/content moment.
11. Further product row(s).
12. Brown promo/card mosaic.
13. Category/promo tiles.
14. Blog/content cards.
15. Black footer with strong separation from pale-blue page field.

### Product cards
- White surface, soft 10–14px corners.
- Large image region, roughly square/4:5 depending merchant media.
- Compact title and price hierarchy.
- Brown pill-style commerce CTA.
- No fabricated quick-add capability: if variants are required, CTA must route to valid option selection/product detail.
- 4 columns is the core Home merchandising density at wide desktop.

### Footer
- Strong near-black field, visually distinct from the pale page.
- Multi-column information/contact/navigation.
- Trust/payment/social content must come only from configured merchant/platform data.
- Reference wavy separator may be approximated with a generic CSS decorative edge; do not copy reference SVG/artwork.

## 3. Reference page notes

### Home reference
- Very long merchandising page (~12.7k px source capture at 1899 px width).
- Pale-blue background is a major family identifier.
- Repeated white card islands and brown promo mosaics create rhythm.
- Hero and story/category discovery dominate the first fold.

### PDP reference
- Brown two-row header is clearly visible.
- Breadcrumb/section transition uses a brown-to-pale gradient.
- Main product image is large with very rounded top/right geometry.
- Product information is contained in a large bordered/rounded panel with warm amber border/accent.
- CTA is a wide warm amber bar.
- Related products are four-across cards on pale-blue background.

### Listing/Search reference
- Pale-blue page field.
- Brown gradient title/breadcrumb zone.
- Product cards are three-across in the captured search result view, with generous gaps and larger imagery.
- Brown pill CTA is repeated consistently.
- Header/nav can remain sticky while scrolling.

## 4. RastiSi reuse map

Reuse directly where semantically correct:
- shared logo/search/account/cart partials
- `story_rail` data primitive
- `catalog_product_wall` runtime source resolver
- `product_card_data` and pricing/stock semantics
- versioned preview pipeline
- generic responsive column controls
- generic destination resolver
- existing `multi_banner` data primitive

New registered presentation variants are justified for:
- chocolate two-row header
- chocolate/black footer
- shokolati-like category shortcut display
- shokolati product card presentation
- hero/carousel presentation if existing overlay/split variants cannot represent the reference silhouette cleanly

## 5. Home v2 acceptance gate

At 1440px:
- brown top header, centered merchant brand, usable prominent search, shopper actions opposite
- separate white nav row
- pale-blue page field
- story rail + large rounded hero + category shortcuts visible before main merchandising
- first merchandising product row is 4-up with white cards and brown CTA
- at least two distinct brown/promo moments lower on page
- page is materially longer/denser than current `premium_leather v1`
- footer reads as black/dark reference family rather than existing light premium columns

At 390px:
- no clipped brand or horizontal overflow
- search remains usable
- story/category discovery scrolls horizontally or wraps intentionally
- product rows become 2 columns or horizontal carousel by registered responsive contract
- CTA remains tappable

## 6. Non-scope of first implementation batch

- Listing precision implementation
- PDP precision implementation
- reference-specific logos/brand images
- SnappPay or ENAMAD imitation
- production deployment
