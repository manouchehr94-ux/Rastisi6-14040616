# Beraito → `dense_marketplace` Design Contract

## Scope

Reference family for the `dense_marketplace` Ready Template. The goal is
structural/visual fidelity to the supplied Beraito screenshots without copying
Beraito branding, product photography, fonts, logos, trust marks, addresses or
commercial claims.

## Authoritative evidence

- `atlas-home-desktop.jpg` — 1353 × 7503, Home silhouette and merchandising rhythm.
- `atlas-product-desktop.jpg` — 1353 × 2514, PDP reference for a later precision pass.

Home is the current v2 implementation scope. PDP remains on the shared product
business/data model and can receive a separate precision pass later.

## Home visual signature

1. White/light-grey commerce shell with a dense, search-first header.
2. Slim utility/announcement region, prominent search, merchant identity and
   shopper actions, followed by a practical category/navigation row.
3. First fold combines a wide hero with a narrow live-product offer panel.
4. Compact image/category discovery row directly below the first fold.
5. Five commerce/service promises in one tight strip.
6. Four promotional tiles before the first major product band.
7. Repeated six-card merchandising rows; several use strong colour fields
   (red, green, amber, violet, blue) with subtle commerce-doodle patterns.
8. White paired merchandising blocks/banners between coloured rows.
9. Compact product cards: square/contained media, short title hierarchy, real
   price/discount semantics and an honest green quick-add affordance when the
   product is actually eligible.
10. Long, dense page silhouette; density comes from reusable sections and real
    Store data, not duplicated/hard-coded product IDs.
11. Dark practical multi-column footer with trust/payment/legal regions.

## RastiSi implementation mapping

The platform already contains a generic internal preset named
`v5_golden_homepage`, explicitly built as the approved dense-commerce reference
composition. `dense_marketplace` v2 reuses that pure-data Home tuple and layers
its own registered Ready Template identity on top:

- palette: `marketplace-spectrum`
- header: `marketplace_search_first`
- footer: `marketplace_dense`
- product card: existing generic `compact`
- category discovery: existing `image_strip`
- reusable coloured backgrounds: `palette_pattern` + `commerce-doodle` +
  semantic `tone-1` … `tone-5`
- product sources: `newest`, `discounted`, `best_sellers`, `most_viewed`

No `if template_key == "dense_marketplace"` renderer branch is allowed.
No Store/Product/Category/Collection primary key is allowed in the preset.

## Palette intent

`marketplace-spectrum` is a dedicated merchant-selectable generic U10 palette
for this dense catalogue language. It deliberately does not reuse the internal
pre-U10 `catalog-colorful` palette:

- commerce action green: `#158A52`
- blue support/accent: `#156FA8`
- promotional red: `#E13D58`
- page field: `#F5F6F8`
- surface: `#FFFFFF`
- dark footer role: `#464B53`
- semantic section tones cover red / green / amber / violet / blue

## Responsive contract

- Desktop product bands target six cards per row.
- Tablet product bands target three cards per row.
- Mobile product bands target two cards per row.
- Marketplace search remains full-width on the mobile second row; burger,
  identity and shopper actions remain usable above it.
- No horizontal document overflow.

## Acceptance gates

1. Registry import and Django system check pass.
2. Existing `fashion_promo_catalog`, `warm_boutique` and `premium_leather`
   registry contracts remain unchanged.
3. `dense_marketplace` reports version 2 and `marketplace-spectrum`.
4. Official preview pipeline emits `dense_marketplace/v2.webp` + v2 metadata.
5. Merchant/browser QA confirms first fold, dense coloured product rhythm,
   mobile layout and footer without interaction regressions.


## Final density polish

The full-page QA gate adds two already-registered generic closing moments:
`brand_carousel` and `blog_posts`, matching the reference's brand/editorial
closure without fabricating merchant data. `marketplace_dense` also consumes
the editable footer theme role so the commercial footer can be dark and dense
without a Ready-Template-specific color branch.
