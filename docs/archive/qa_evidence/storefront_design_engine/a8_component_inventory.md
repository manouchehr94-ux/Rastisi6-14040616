# A8 component evidence inventory

## Method and boundary

Evidence inspected on 2026-09-02: the Design Lab prototype at
`C:/Users/hp/Downloads/RastiSi_50_Storefront_Design_Lab_TABBED_THEMES (1).html`,
the R4 Store Appearance registry/adapters, global-region and section registries,
appearance registry, and Ready Template registry. Prototype markup, CSS, JS,
numeric IDs, copied copy, countdowns, and campaign state are evidence only; none
are production payloads. Production identities below are semantic, versioned keys.

Baseline command reported 46 components in ten families: header 10, mega_menu 1,
hero 6, layout 8, product_view 6, card 1, badge 1, motion 3, footer 8, bottom_nav
2. The current official catalog is eight presets: `dense_marketplace@2`,
`premium_leather@2`, `warm_boutique@2`, `fashion_promo_catalog@7`,
`playful_lifestyle@1`, `utility_catalog@1`, `editorial_jewelry@2`, and
`dark_digital@2`.

## Existing production vocabulary (reuse first)

| Family | Existing R4 primitives | A8 decision |
| --- | --- | --- |
| Header | `legacy_default`, `marketplace_search_first`, `premium_three_column`, `boutique_centered`, `dark_tech`, `promo_search_nav`, `beauty_search_nav`, `chocolate_centered_search`, `atelier_nav`, `luxury_search` | Reuse when topology matches; add only generic structural variants. |
| Hero | `legacy_default` plus registered `hero_banner` variants (6 total) | Reuse basic image/split/slider treatment; create semantic generic variants for bento, product-focus, search-first, mosaic, and editorial gallery. Countdown is excluded without domain timing truth. |
| Layout | Existing container layouts (8 total) | Reuse columns, rail, list, bento, and featured composition; generic zigzag/catalog variants only where no current equivalent exists. |
| Product view | `product_section` and `catalog_product_wall` variants (6 total) | Reuse data-backed grid/rail/wall; presentation additions must remain card overlays. |
| Card/badge | `card.legacy_default.v1`, `badge.none.v1`; underlying card styles: `standard`, `compact`, `minimal`, `fashion_sale`, `beauty_retail`, `chocolate_retail`, `retail_list`, `luxury_dark` | Register presentation-only card/badge styles; never change price, stock, variants, URLs, wishlist, rating, or quick-add truth. |
| Motion | `none`, `subtle`, `dynamic` | Reuse, respecting reduced motion. |
| Footer | `legacy_default`, `marketplace_dense`, `premium_columns`, `boutique_editorial`, `dark_tech`, `promo_columns`, `beauty_retail_columns`, `chocolate_dark_columns` | Reuse or add generic minimal/editorial/app/playful structures with real merchant links/data. |
| Bottom nav | `hidden`, one current mobile nav variant (2 total) | Add only accessible generic nav layouts; all use real named URLs/cart count, RTL, safe-area offset, and mobile-only display. |

## Prototype primitive normalization

The following inventory deliberately records prototype aliases as evidence in the
first column only. “New” means a future generic registered component, not a
template-specific partial. All renderer targets are platform-owned partials under
`storefront_builder/partials/` or existing trusted registry renderers.

| Prototype evidence / family | Visual evidence | Nearest R4 primitive / decision | Proposed stable semantic key | Renderer / responsive contract / compatibility | Used by prototype recipes |
| --- | --- | --- | --- | --- | --- |
| h1 row-minimal; header | single quiet row, logo/nav/actions | `atelier_nav`; reuse | `header.editorial_row.v1` | existing global header; collapse nav to menu | 01,04,17,18,23,27,38,50 |
| h2 marketplace-multiline; header | utility/search/category rows | `marketplace_search_first`; reuse | `header.marketplace_search.v1` | existing global header; search stacks on mobile | 02,09,11,20,22,24,29,46 |
| h3 centered-brand; header | announcement + centered logo | `premium_three_column`; reuse | `header.centered_brand.v1` | existing global header; actions retain labels | 06,08,14,31,40,49 |
| h4 floating-pill; header | floating compact nav | no exact match; new generic | `header.floating_compact.v1` | trusted global partial; becomes solid/flow layout on narrow widths | 05,19,23,34,43 |
| h5 sidebar/compact; header | hamburger-led compact shell | `legacy_default`; reuse as compact mode | `header.compact_drawer.v1` | existing header; drawer accessibility required | 16,32,36,39,45 |
| h6 bold-news; header | ticker plus bold nav | `promo_search_nav`; reuse announcement only with real message | `header.promo_bar.v1` | existing global header; no fake scarcity | 07,24,44,48 |
| h7 social-story; header | story shortcut rail | no exact match; new generic discovery strip | `header.community_shortcuts.v1` | trusted partial; horizontally scrollable and labelled | 26 |
| h8 transparent-image; header | overlay row | no exact match; new generic | `header.overlay_transparent.v1` | trusted partial; solid fallback/contrast on mobile | 15,25,33 |
| h9 newspaper; header | masthead and editorial nav | `atelier_nav`; generic editorial variant | `header.editorial_masthead.v1` | trusted partial; hides issue/date metadata unless real | 12,16,27,47 |
| h10 compressed-menu; header | hamburger plus short links | `legacy_default`; reuse | `header.compact_menu.v1` | existing global header; accessible menu | 03,21,28,42 |
| h11 tabbed-nav; header | category tabs | no exact match; new generic | `header.category_tabs.v1` | trusted partial; scrollable tabs on mobile | 13,37 |
| h12 playful-awning; header | decorative canopy | `boutique_centered`; generic playful decoration | `header.playful_canopy.v1` | trusted partial; decoration omitted in reduced/mobile layout | 10,30,35,41 |
| x0–x13; hero | none, immersive, split, bento, type, product, offer, collage, slider, video, calm, search, mosaic, social grid | existing hero where equivalent; otherwise generic, data-backed | `hero.none`, `hero.immersive`, `hero.editorial_split`, `hero.promo_bento`, `hero.typographic`, `hero.product_focus`, `hero.image_collage`, `hero.side_offer_slider`, `hero.media_feature`, `hero.quiet`, `hero.search_first`, `hero.campaign_mosaic`, `hero.social_gallery` (all `.v1`) | trusted section variants; stack/crop safely; media requires merchant media; offer/countdown states are suppressed without truth | all base recipes |
| x14–x19; Lab-only heroes | product orbit, Persian arch, wholesale, social post, triptych, dual deal | evidence only; not selected by base 50 | documented Lab-only | no production renderer in A8 mapping | none |
| circle/tile/arch/chip/list; category discovery | round shortcuts, tiles, arches, pills, numbered list | `category_grid` modes where equivalent; add generic modes as needed | `discovery.circular`, `tile`, `editorial_arch`, `chips`, `indexed_list` (all `.v1`) | section renderers; horizontal scroll or 2-up at mobile | all base recipes |
| icon/strip/mosaic/index/mini; category discovery | compact icons, strip, mosaic, index, mini cards | Lab-only and unused by base 50 | documented Lab-only | no A8 production selection | none |
| c-flat/c-market/c-edit/c-row/c-lux/c-pill/c-glass/c-polaroid/c-price/c-circle/c-index/c-label/c-shelf/c-spec/c-neon/c-brutal; card | sixteen presentation compositions | map to existing styles first; add generic presentation styles where necessary | `card.standard`, `marketplace_price`, `editorial_minimal`, `retail_row`, `luxury_dark`, `soft_capsule`, `beauty_glass`, `paper_frame`, `price_first`, `portrait_round`, `catalog_index`, `shipping_label`, `shelf_editorial`, `technical_spec`, `tech_neon`, `bold_outline` (all `.v1`) | shared product-card partial only; 2-up mobile except list rows; commerce truth unchanged | all base recipes |
| g2/g3/g4/g5/rail/list/bento/feat/zig; product composition | 2–5 columns, rail, list, bento, feature, zigzag | current layouts/product views first; add generic composition variants | `layout.two_column`, `three_column`, `four_column`, `dense_five`, `horizontal_rail`, `catalog_list`, `bento_grid`, `featured_split`, `editorial_zigzag` (all `.v1`) | registered composition; columns reduce to 2/1, rails scroll | all base recipes |
| p01–p10; promotional treatment | flash, coupon, delivery, seasonal, inventory, member, marquee, dual, quiet | generic only; countdown/stock/season claims require real data | `promo.flash`, `coupon`, `delivery_note`, `member_note`, `brand_marquee`, `dual_campaign`, `quiet_notice` (all `.v1`) | trusted sections; conditional omission where truth absent; no occasion overlay | evidence only in base sequence aliases |
| min/mega/edit/story/brutal/center/app/wave; footer | minimal, dense columns, wordmark, story, bold, centered, app, playful | existing footer variants first; generic variants where missing | `footer.minimal`, `marketplace_columns`, `editorial_wordmark`, `brand_story`, `bold_columns`, `centered`, `app_download`, `playful_wave` (all `.v1`) | trusted global partial; columns stack, real links/contact only | all base recipes |
| m4/m5/mfab/mdock/mglass/micon/mbig; mobile nav | 4/5 item, raised cart, floating/glass dock, icon, wide cart | current mobile nav plus generic variants | `bottom_nav.four_item`, `five_item`, `raised_cart`, `floating_dock`, `glass_dock`, `minimal_icons`, `wide_cart` (all `.v1`) | mobile-only, RTL, focus labels, safe-area/content offset, real URLs/cart count | all base recipes |
| palette/type/density/width/radius | 50 palettes; 8 type, 5 density, 5 width, 6 radius concepts | typed appearance registry only | palette slug + registered font/density/content-width/radius | bounded tokens, no raw CSS; mobile width is fluid | all base recipes |
| 38 section sequences | hero/category/product/promo/trust/story/news combinations | existing sections and bounded recipes | `composition.home_*` semantic recipes | merchant-ID-free section entries; no demo data | 01–50 |

## Decisions and concerns

* The prototype has 12 headers, 20 heroes, 10 category modes, 16 cards, 9 product
  layouts, 10 promotion treatments, 8 footers, 7 mobile navs, 50 palettes, and 38
  distinct section sequences. It is not a runtime dependency.
* Base recipes use only x0–x13 and category circle/tile/arch/chip/list. x14–x19
  and icon/strip/mosaic/index/mini remain Lab-only evidence.
* Promotional countdown, stock, coupon, occasion, and member claims cannot be
  represented until commerce truth exists. A8 may render only real data-backed
  generic treatments or omit them.

## Exhaustive primitive records

This annex expands the normalization table into one evidence record per prototype
primitive. `TR` means a platform-owned trusted registry/partial; `R` is the
responsive contract. The proposed names are semantic production vocabulary, never
persisted prototype aliases.

### Headers (12)

| Evidence | Visual | Nearest / decision | Semantic key | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| h1 row minimal | logo, nav, action row | atelier_nav / reuse | `header.editorial_row.v1` | global registry; menu collapse | 01,04,17,18,23,27,38,50 |
| h2 marketplace | utility/search/category rows | marketplace_search_first / reuse | `header.marketplace_search.v1` | global registry; search stacks | 02,09,11,20,22,24,29,46 |
| h3 centered brand | announcement and centered mark | premium_three_column / reuse | `header.centered_brand.v1` | global registry; actions collapse | 06,08,14,31,40,49 |
| h4 floating pill | compact floating capsule | no exact / new generic | `header.floating_compact.v1` | TR global partial; solid mobile | 05,19,23,34,43 |
| h5 side compact | hamburger-led compact shell | legacy_default / reuse | `header.compact_drawer.v1` | global registry; labelled drawer | 16,32,36,39,45 |
| h6 news bold | ticker and bold navigation | promo_search_nav / reuse | `header.promo_bar.v1` | global registry; no fake urgency | 07,24,44,48 |
| h7 social stories | community story shortcut rail | no exact / new generic | `header.community_shortcuts.v1` | TR global partial; scroll mobile | 26 |
| h8 image overlay | transparent image-overlay row | no exact / new generic | `header.overlay_transparent.v1` | TR global partial; contrast fallback | 15,25,33 |
| h9 newspaper | masthead/editorial navigation | atelier_nav / new generic | `header.editorial_masthead.v1` | TR global partial; no invented date | 12,16,27,47 |
| h10 compressed menu | burger plus short links | legacy_default / reuse | `header.compact_menu.v1` | global registry; labelled drawer | 03,21,28,42 |
| h11 tabs | category tab strip | no exact / new generic | `header.category_tabs.v1` | TR global partial; scroll mobile | 13,37 |
| h12 canopy | playful decorative awning | boutique_centered / new decoration | `header.playful_canopy.v1` | TR global partial; decoration optional | 10,30,35,41 |

### Heroes (20)

| Evidence | Visual | Nearest / decision | Semantic key or status | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| x0 none | no lead artwork | existing plain section / reuse | `hero.none.v1` | section registry; no empty region | 04,11,20,32,36 |
| x1 immersive | full-bleed image + copy | hero_banner / new generic | `hero.immersive.v1` | TR hero partial; crop/stack | 01,08,17,27,45,47 |
| x2 split | copy beside product art | existing split / reuse | `hero.editorial_split.v1` | TR hero partial; stack mobile | 03,06,18,21,31,33,42 |
| x3 bento | large offer plus small tiles | no exact / new | `hero.promo_bento.v1` | TR hero partial; 1-up mobile | 02,13,14,24,28,50 |
| x4 type | centered oversized type | basic hero / new generic | `hero.typographic.v1` | TR hero partial; clamp text | 07,12,37 |
| x5 product | one purchasable product focus | existing hero / new generic | `hero.product_focus.v1` | real product state; stack mobile | 15,23,29,34,40,43,44 |
| x6 festival | offer + countdown panel | no truth / excluded countdown | `hero.offer_panel.v1` conditional | TR only with deadline; otherwise omit | 14,24 |
| x7 collage | multi-image editorial collage | no exact / new | `hero.image_collage.v1` | merchant media; 2-up mobile | 10,19,30,35,41 |
| x8 side slider | slider with side offers | existing slider / new generic | `hero.side_offer_slider.v1` | TR slider; scroll/stack mobile | 25 |
| x9 video | media frame with play affordance | no exact / conditional | `hero.media_feature.v1` | real media only; poster fallback | 05,48 |
| x10 quiet | sparse copy and CTA | legacy hero / reuse | `hero.quiet.v1` | TR hero partial; no art required | 16,38,39 |
| x11 search | large category search | no exact / new | `hero.search_first.v1` | real search form; full width mobile | 09 |
| x12 mosaic | campaign image mosaic | no exact / new | `hero.campaign_mosaic.v1` | merchant media; 1-up mobile | 22,46,49 |
| x13 social grid | copy beside square image grid | no exact / new | `hero.social_gallery.v1` | merchant media; stack mobile | 26 |
| x14 orbit | product with floating facts | Lab-only | Lab-only, no A8 selection | no renderer | none |
| x15 Persian arch | arched framed art | Lab-only | Lab-only, no A8 selection | no renderer | none |
| x16 wholesale | tiers/MOQ quotation | Lab-only, requires B2B data | Lab-only, no A8 selection | no renderer | none |
| x17 social post | feed post + stories | Lab-only | Lab-only, no A8 selection | no renderer | none |
| x18 triptych | gallery triptych | Lab-only | Lab-only, no A8 selection | no renderer | none |
| x19 dual deal | paired deal panels | Lab-only, claim-driven | Lab-only, no A8 selection | no renderer | none |

### Discovery modes (10)

| Evidence | Visual | Nearest / decision | Semantic key/status | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| circle | circular image shortcuts | category_grid / reuse | `discovery.circular.v1` | section registry; scroll/2-up | 02,03,09,10,14,19,23,26,31,34,35,41,43,50 |
| tile | image category tiles | category_grid / reuse | `discovery.tile.v1` | section registry; 2-up | 06,11,13,20,21,22,28,29,42,46,49 |
| arch | editorial arches | no exact / new | `discovery.editorial_arch.v1` | TR section partial; 2-up | 08,47 |
| chip | compact category pills | category_grid / reuse | `discovery.chips.v1` | section registry; horizontal scroll | 04,05,07,15,24,25,30,36,37,38,44,48 |
| list | numbered textual list | category_grid / new | `discovery.indexed_list.v1` | TR section partial; one column | 01,12,16,17,18,27,32,33,39,40,45 |
| icon | compact icon shortcuts | Lab-only | Lab-only, no A8 selection | no renderer | none |
| strip | horizontal discovery strip | Lab-only | Lab-only, no A8 selection | no renderer | none |
| mosaic | image mosaic | Lab-only | Lab-only, no A8 selection | no renderer | none |
| index | catalogue index | Lab-only | Lab-only, no A8 selection | no renderer | none |
| mini | mini category cards | Lab-only | Lab-only, no A8 selection | no renderer | none |

### Card presentations (16)

| Evidence | Visual | Nearest / decision | Semantic key | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| c-flat | flat product tile | standard / reuse | `card.standard.v1` | shared product card; 2-up | 04,06,15,21,25,31,38 |
| c-lux | dark premium card | luxury_dark / reuse | `card.luxury_dark.v1` | shared card; 2-up | 01,08,18,28 |
| c-market | price-led marketplace | compact/fashion_sale / new overlay | `card.marketplace_price.v1` | shared card; 2-up | 02,14,22,35,49 |
| c-edit | editorial minimal | minimal / reuse | `card.editorial_minimal.v1` | shared card; 2-up | 12,17,27,33,39,45 |
| c-row | horizontal row | retail_list / reuse | `card.retail_row.v1` | shared card; one column | 11,16 |
| c-brutal | bold outlined | no exact / new overlay | `card.bold_outline.v1` | shared card; 2-up | 07,44 |
| c-glass | translucent beauty | beauty_retail / new overlay | `card.beauty_glass.v1` | shared card; 2-up | 19,23,43 |
| c-pill | rounded soft card | standard / new overlay | `card.soft_capsule.v1` | shared card; 2-up | 10,13,26,41,42 |
| c-polaroid | paper-framed image | no exact / new overlay | `card.paper_frame.v1` | shared card; 2-up | 03,30 |
| c-price | price priority | compact / new overlay | `card.price_first.v1` | shared card; 2-up | 09,24,37 |
| c-circle | portrait circle | no exact / new overlay | `card.portrait_round.v1` | shared card; 2-up | 40 |
| c-index | numbered catalogue | no exact / new overlay | `card.catalog_index.v1` | shared card; 2-up | 32,50 |
| c-label | shipping label | no exact / new overlay | `card.shipping_label.v1` | shared card; 2-up | 46 |
| c-shelf | shelf/editorial | minimal / new overlay | `card.shelf_editorial.v1` | shared card; 2-up | 34,47 |
| c-spec | technical specs | compact / new overlay | `card.technical_spec.v1` | shared card; 2-up | 20,29,36,48 |
| c-neon | neon technology | no exact / new overlay | `card.tech_neon.v1` | shared card; 2-up | 05 |

### Product layouts (9)

| Evidence | Visual | Nearest / decision | Semantic key | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| g2 | two columns | container layout / reuse | `layout.two_column.v1` | composition registry; 1-up | 08,12,16,25,26,27,39,40,47 |
| g3 | three columns | container layout / reuse | `layout.three_column.v1` | composition registry; 2-up | 01,03,10,18,19,21,30,33,34,38,42,43 |
| g4 | four columns | container layout / reuse | `layout.four_column.v1` | composition registry; 2-up | 04,06,14,15,20,22,29,31,36,37,41,44,46 |
| g5 | five dense columns | container layout / reuse | `layout.dense_five.v1` | composition registry; 2-up | 02,09,24 |
| rail | horizontal rail | product section / reuse | `layout.horizontal_rail.v1` | horizontal scroll mobile | 05,07,23,48 |
| list | list rows | container layout / reuse | `layout.catalog_list.v1` | one column | 11,16,17,32,45 |
| bento | mosaic product grid | no exact / new | `layout.bento_grid.v1` | composition registry; 1-up | 13,28,50 |
| feat | featured split | existing composition / reuse | `layout.featured_split.v1` | stack mobile | 49 |
| zig | editorial zigzag | no exact / new | `layout.editorial_zigzag.v1` | stack mobile | 35 |

### Promotional treatments (10)

| Evidence | Visual | Nearest / decision | Semantic key/status | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| p01 flash countdown | timed flash-sale banner | no deadline / conditional | `promo.flash.v1` conditional | TR section; omit without deadline | evidence only |
| p02 coupon | first-order coupon ticket | promotion truth / conditional | `promo.coupon.v1` conditional | TR section; omit without code | evidence only |
| p03 free shipping | delivery message | shipping rules / conditional | `promo.delivery_note.v1` conditional | TR section; wrap/stack | evidence only |
| p04 Nowruz | seasonal Nowruz treatment | occasion overlay excluded | excluded from A8 | no renderer | evidence only |
| p05 Yalda | seasonal Yalda treatment | occasion overlay excluded | excluded from A8 | no renderer | evidence only |
| p06 low stock | scarcity stock bar | inventory truth / conditional | `promo.inventory_note.v1` conditional | TR section; omit without truth | evidence only |
| p07 members | member-price message | entitlement truth / conditional | `promo.member_note.v1` conditional | TR section; omit without truth | evidence only |
| p08 marquee | moving brand statement | motion token / new generic | `promo.brand_marquee.v1` | TR section; static reduced-motion | evidence only |
| p09 dual deals | two campaigns | promotion truth / conditional | `promo.dual_campaign.v1` conditional | TR section; stack mobile | evidence only |
| p10 quiet | restrained delivery note | existing banner / reuse | `promo.quiet_notice.v1` | TR section; stack mobile | evidence only |

### Footers (8) and mobile navigation (7)

| Evidence | Visual | Nearest / decision | Semantic key | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| min footer | minimal links | legacy footer / reuse | `footer.minimal.v1` | global registry; stack | 01,04,13,17,23,28,32,36,37,38,43 |
| mega footer | dense commercial columns | marketplace_dense / reuse | `footer.marketplace_columns.v1` | global registry; stack | 02,05,09,14,20,22,24,34,44,46,48,49 |
| edit footer | editorial wordmark | boutique_editorial / reuse | `footer.editorial_wordmark.v1` | global registry; stack | 08,16,27,39,45,47,50 |
| story footer | brand narrative | promo_columns / reuse | `footer.brand_story.v1` | global registry; stack | 03,12,18,21,25,30,31,33,35 |
| brutal footer | bold columns | no exact / new | `footer.bold_columns.v1` | TR global partial; stack | 07,44 |
| center footer | centered compact | legacy footer / new generic | `footer.centered.v1` | TR global partial; stack | 06,11,15,19,40,42 |
| app footer | app/QR support | no exact / conditional | `footer.app_download.v1` | real app URLs only; stack | 26,29 |
| wave footer | playful wave | no exact / new | `footer.playful_wave.v1` | TR global partial; decoration optional | 10,41 |
| m4 nav | four destinations | existing mobile nav / reuse | `bottom_nav.four_item.v1` | global registry; RTL/safe-area | 06,11,20,25,28,29,31,35,46 |
| m5 nav | five destinations | existing mobile nav / new generic | `bottom_nav.five_item.v1` | TR global partial; RTL/safe-area | 02,10,14,22,30,41,49 |
| mfab nav | raised cart action | no exact / new | `bottom_nav.raised_cart.v1` | TR global partial; RTL/safe-area | 09,13,19,23,24,37,43 |
| mdock nav | floating dock | no exact / new | `bottom_nav.floating_dock.v1` | TR global partial; RTL/safe-area | 03,12,18,21,26,33,42,50 |
| mglass nav | glass dock | no exact / new | `bottom_nav.glass_dock.v1` | TR global partial; RTL/safe-area | 05,34 |
| micon nav | minimal icons | existing mobile nav / reuse | `bottom_nav.minimal_icons.v1` | global registry; RTL/safe-area | 01,04,08,16,17,27,32,36,38,39,40,45,47 |
| mbig nav | wide cart | no exact / new | `bottom_nav.wide_cart.v1` | TR global partial; RTL/safe-area | 07,15,44,48 |

### Appearance concepts and section sequences

| Evidence | Visual | Nearest / decision | Semantic key/status | TR / R | Recipes |
| --- | --- | --- | --- | --- | --- |
| palettes 01–50 | distinct token palettes | typed palette registry / map each | `palette.<registered-slug>` | CSS tokens only; fluid mobile | 01–50 |
| types vazir, markazi, lalezar, space, playfair, cormorant, dm, mono | eight type voices | typed font choices / allowlist | `type.<registered-font>` | appearance token; fallbacks | 01–50 |
| density xs,s,m,d,xl | five spacing rhythms | density choices / reuse | `density.relaxed|normal|compact` | appearance token | 01–50 |
| width narrow,compact,standard,wide,full | 960–1440 content widths | content-width choices / bounded | `content_width.<registered>` | max width; fluid mobile | 01–50 |
| radius none,tiny,medium,round,large,pill | six corner systems | radius choices / bounded | `radius.<registered>` | token only | 01–50 |
| sequence 01–38 | all prototype section orders | bounded section entries / normalize | `composition.home_01` … `composition.home_38` | section registry; each stacks mobile | see exhaustive sequence list below |

The 38 distinct prototype sequences are recorded individually as bounded semantic
composition records (all use existing section registry entries and mobile stacking):

`home_01` hero/cats/grid/story/edito; `home_02` hero/cats/flash/grid/svc/brands/testi;
`home_03` hero/story/grid/testi/news; `home_04` ticker/cats/grid/edito;
`home_05` hero/cats/grid/flash/news; `home_06` hero/cats/grid/trust;
`home_07` ticker/hero/cats/rail/flash; `home_08` hero/arch-cats/grid/story;
`home_09` hero/cats/grid/trust; `home_10` hero/cats/grid/testi/news;
`home_11` cats/list/svc; `home_12` hero/cats/grid/story; `home_13` hero/cats/bento/news;
`home_14` hero/cats/grid/trust; `home_15` hero/cats/grid/story;
`home_16` hero/cats/list/edito; `home_17` hero/cats/list/edito;
`home_18` hero/cats/grid/story; `home_19` hero/cats/grid/news;
`home_20` cats/grid/trust; `home_21` hero/cats/grid/story/news;
`home_22` hero/cats/grid/flash/trust; `home_23` hero/cats/rail/news;
`home_24` hero/cats/flash/grid; `home_25` hero/cats/grid/story;
`home_26` hero/cats/grid/community; `home_27` hero/cats/grid/story;
`home_28` hero/cats/bento/testi; `home_29` hero/cats/grid/svc;
`home_30` hero/cats/grid/news; `home_31` hero/cats/grid/story;
`home_32` cats/list/edito; `home_33` hero/cats/grid/story;
`home_34` hero/cats/grid/news; `home_35` hero/cats/zig/story;
`home_36` cats/grid/trust; `home_37` hero/cats/grid/flash;
`home_38` ticker/hero/cats/bento/testi/news. These map prototype sequence usages
across recipes 01–50; duplicate visual orders share their normalized semantic
composition rather than creating duplicate production components.
