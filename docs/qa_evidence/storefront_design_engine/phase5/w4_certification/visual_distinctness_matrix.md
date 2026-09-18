# W4C Rendered Visual Distinctness Review — Final Closure

CAMPAIGN_HEAD: `1e4efad80fbfc998cfd05d79658955193e1799d5`

## Method

Per Independent Architect correction: this review is grounded in the ACTUAL rendered Home Desktop (1440x900) and Mobile (390x844) evidence captured during the certified 704-cell campaign (home_gallery/), not primarily in configuration signatures. Every one of the 50 Templates' Desktop AND Mobile captures was viewed directly (via contact sheets covering all 50 on both viewports, cross-checked with individual full-resolution re-fetches for every Template sharing a hero component with 6+ siblings and for every candidate near-duplicate pair). Configured selections (header/hero/layout/product_view/card/footer/bottom_nav/font/radius/palette) are retained as supporting metadata only, per instruction -- they do not by themselves decide any verdict. Where configured identity and observed rendering disagreed (e.g. tool_finder is configured hero.none.v1 and its real capture confirms no hero at all, matching the certified matrix.json's own hero_expected=False), the observed rendering is what is recorded.

## Important finding: shared hero content

Hero content (product photography, headline copy, CTA text) is Store-level demo content shared by every Template using the same hero component (e.g. all 7 hero.editorial_split.v1 Templates render the literal same jacket/jacket/shoe photos and 'کالکشن پاییز و زمستان Rasti Mode' headline). This is expected given a single shared demo catalog and is NOT by itself a defect. It does mean that for Templates sharing a hero family, the real distinguishing power comes from header structure, secondary-section composition (colour promo blocks vs tag icons vs none), product grid organisation, and Mobile bottom-navigation treatment -- not from the hero photography itself.

## Footer limitation

All 50 Home captures are single-viewport screenshots taken at initial load (1440x900 Desktop, 390x844 Mobile). The footer sits below the fold on every one of the 50 Templates and was never reached by any capture in this campaign. observed_footer is recorded as NOT_VISIBLE for all 50 rather than inferring a footer appearance that was not actually captured. Configured footer selections remain available as supporting metadata.

## Result

- Reviewed Desktop: 50/50
- Reviewed Mobile: 50/50
- Rendered PASS: 44/50
- MANUAL REVIEW REQUIRED: 0
- NEEDS REPAIR: 6
- Config-only PASS decisions: 0

**VERDICT: NEEDS REPAIR**

## NEEDS REPAIR pairs (real, rendered-evidence-grounded findings)

### pine_eco vs green_workshop

- Desktop evidence: `home_gallery/pine_eco_home_desktop.jpg`, `home_gallery/green_workshop_home_desktop.jpg`
- Mobile evidence: `home_gallery/pine_eco_home_mobile.jpg`, `home_gallery/green_workshop_home_mobile.jpg`
- Axes shared: ALL of: header, hero, layout, product_view, bottom_nav (and, for silk_editorial/parnian_editorial and pine_eco/green_workshop, badge/motion/font/radius/density too)
- Axes visibly different: None visible above the fold for pine_eco/green_workshop -- the Desktop and Mobile captures are indistinguishable; card style and footer differ only in configuration, neither is visible in either capture.
- Verdict: **NEEDS_REPAIR**
- Rationale: Materially indistinguishable in the actual rendered Home Desktop+Mobile evidence except for palette/cosmetic differences that are not visible above the fold, per the binding rendered-evidence contract.

### playful_lifestyle vs laleh_play

- Desktop evidence: `home_gallery/playful_lifestyle_home_desktop.jpg`, `home_gallery/laleh_play_home_desktop.jpg`
- Mobile evidence: `home_gallery/playful_lifestyle_home_mobile.jpg`, `home_gallery/laleh_play_home_mobile.jpg`
- Axes shared: ALL of: header, hero, layout, product_view, bottom_nav (and, for silk_editorial/parnian_editorial and pine_eco/green_workshop, badge/motion/font/radius/density too)
- Axes visibly different: Background/accent colour only (palette: mint vs sunset) -- identical arch-cutout hero composition, identical photos, identical header nav items, identical headline/CTA copy and position.
- Verdict: **NEEDS_REPAIR**
- Rationale: Materially indistinguishable in the actual rendered Home Desktop+Mobile evidence except for palette/cosmetic differences that are not visible above the fold, per the binding rendered-evidence contract.

### silk_editorial vs parnian_editorial

- Desktop evidence: `home_gallery/silk_editorial_home_desktop.jpg`, `home_gallery/parnian_editorial_home_desktop.jpg`
- Mobile evidence: `home_gallery/silk_editorial_home_mobile.jpg`, `home_gallery/parnian_editorial_home_mobile.jpg`
- Axes shared: ALL of: header, hero, layout, product_view, bottom_nav (and, for silk_editorial/parnian_editorial and pine_eco/green_workshop, badge/motion/font/radius/density too)
- Axes visibly different: Header bar colour (pale ivory vs solid warm orange/rust) and page background tone (ivory vs warm yellow-cream) -- the hero panel itself (photo, headline, CTA) is identical.
- Verdict: **NEEDS_REPAIR**
- Rationale: Materially indistinguishable in the actual rendered Home Desktop+Mobile evidence except for palette/cosmetic differences that are not visible above the fold, per the binding rendered-evidence contract.

No other pair or cluster in the remaining 44 Templates was found to be materially indistinguishable in their actual rendered Home Desktop+Mobile evidence. Elimination method: every Template sharing a hero component with 6 or more siblings (the `hero.editorial_split.v1` 7-member and `hero.product_focus.v1` 7-member families) plus every algorithmically-detected exact match on (header, hero, layout, product_view, bottom_nav) was individually re-fetched and visually compared at full resolution -- not eliminated by asserting structural-signature uniqueness alone. Where a shared hero family showed genuinely different header structure, secondary-section composition, or background/theme treatment strong enough to read as a different storefront (e.g. dark-navy vs white header on Desktop for `cedar_home` vs `city_classic`; a 2-panel split hero for `roosta_zigzag` vs the 3-arch composition of the rest of the `hero.image_collage.v1` family; a lighter blue-gray ground for `gallery_minimal` vs the dark brown-black ground of the rest of the `hero.immersive.v1` family), it was recorded PASS with the specific distinguishing evidence cited in that Template's `observed_*` fields below, not by silently preferring configuration.

## Per-Template observed rendering (all 50)

| # | key | verdict | observed_header | observed_hero_or_absence | observed_bottom_navigation |
|---|---|---|---|---|---|
| 1 | `dense_marketplace` | PASS | OBSERVED: light header, full category nav row, red search button... | OBSERVED: no photographic hero -- 3 colour promo blocks (pink/navy/teal) directly under he... | OBSERVED: flat dark bar, teal highlighted icon |
| 2 | `premium_leather` | PASS | OBSERVED: light header, full category nav row, red search button... | OBSERVED: intentional absence confirmed (hero_expected=False in certified matrix.json); pa... | OBSERVED: flat dark bar, teal highlighted icon |
| 3 | `warm_boutique` | PASS | OBSERVED: cream/beige header, overflow nav, red search button... | OBSERVED: 3-panel jacket/jacket/shoe carousel in a brown picture-frame, headline 'کالکشن پ... | OBSERVED: dark bar, ORANGE highlighted icon |
| 4 | `fashion_promo_catalog` | PASS | OBSERVED: light header, full nav, red search button... | OBSERVED: 3-panel carousel (editorial_split-style content) directly under header... | OBSERVED: dark bar, YELLOW highlighted icon |
| 5 | `playful_lifestyle` | NEEDS_REPAIR | OBSERVED: dark navy top bar, same nav item list as laleh_play... | OBSERVED: 3 arch-cutout product cutouts (boots/bag/jacket) on an OLIVE/KHAKI background wi... | OBSERVED: NOT_VISIBLE in this capture (crop ends at hero) |
| 6 | `utility_catalog` | PASS | OBSERVED: cream header, full nav, dark search button... | OBSERVED: intentional absence (hero_expected=False); opens on 3 tag icons then a category-... | OBSERVED: dark bar, teal highlighted icon |
| 7 | `editorial_jewelry` | PASS | AMBIGUOUS: header not fully visible in this capture (hero fills most of the viewport)... | OBSERVED: single large dark-framed product photo (left) + 'Rasti Mode' heading/CTA (right)... | NOT_VISIBLE in this capture |
| 8 | `dark_digital` | PASS | OBSERVED: dark theme header, full nav, dark search area... | OBSERVED: 3-panel carousel (same editorial-style demo photos) on dark background... | OBSERVED: glassy dark dock, neon-purple accent |
| 9 | `cedar_home` | PASS | OBSERVED: white minimal header, SHORT 4-item nav + hamburger, no visible search button (ic... | OBSERVED: same editorial_split hero content as warm_boutique/green_workshop/pine_eco/handm... | OBSERVED: dark bar, ORANGE rounded highlighted icon |
| 10 | `street_drop` | PASS | OBSERVED: dark theme header... | OBSERVED: typographic-style hero, dark background, single product image, bold headline... | OBSERVED: dark bar with orange square 'خرید' label -- distinct labelled-button treatment |
| 11 | `premium_leather_noir` | PASS | AMBIGUOUS: header largely out of frame... | OBSERVED: same hero.immersive.v1 split-hero family as editorial_jewelry, dark warm-brown b... | NOT_VISIBLE in this capture |
| 12 | `search_market` | PASS | OBSERVED: light blue-tinted background, PROMINENT centred search bar in header -- header s... | OBSERVED: small centred carousel hero, secondary to the search bar... | OBSERVED: blue circular floating cart button |
| 13 | `artisan_grain` | PASS | OBSERVED: light cream header, full nav... | OBSERVED: single large product photo + text hero on cream ground (typographic/quiet-family... | OBSERVED: purple circular floating cart button |
| 14 | `pixel_play` | PASS | OBSERVED: light header... | OBSERVED: promo_bento-family hero -- carousel with visible arrow-nav controls, small grid ... | NOT_VISIBLE in this capture |
| 15 | `simorgh_market` | PASS | OBSERVED: light header... | OBSERVED: same 3-panel carousel family, small grid thumbnails visible at bottom edge... | NOT_VISIBLE in this capture |
| 16 | `coastal_product` | PASS | OBSERVED: dark theme header... | OBSERVED: product_focus-family hero, dark background, promo blocks below (pink/navy/teal)... | OBSERVED: wide dark cart bar -- distinct 'wide_cart' mobile nav treatment |
| 17 | `literary_catalog` | PASS | OBSERVED: light cream header... | OBSERVED: quiet-family hero, centred single image, generous whitespace, minimal copy... | OBSERVED: orange square highlighted icon on flat bar |
| 18 | `gallery_minimal` | PASS | OBSERVED: light blue-gray background, minimal header... | OBSERVED: same hero.immersive.v1 split-hero family as editorial_jewelry/premium_leather_no... | OBSERVED: teal square highlighted icon |
| 19 | `handmade_luxe` | PASS | OBSERVED: dark maroon/brown full-width header bar -- distinct from the cream/white headers... | OBSERVED: same editorial_split hero content as warm_boutique/cedar_home/green_workshop/pin... | NOT_VISIBLE in this capture |
| 20 | `niloufar_glass` | PASS | OBSERVED: light header over a warm terracotta/rust hero band... | OBSERVED: same arch-cutout 3-product hero family as playful_lifestyle/laleh_play/mina_comm... | OBSERVED: magenta/purple circular floating cart button |
| 21 | `tool_finder` | PASS | OBSERVED: light blue-gray header, dark navy search button... | OBSERVED: intentional absence confirmed (hero_expected=False in certified matrix.json); op... | OBSERVED: teal square highlighted icon |
| 22 | `green_workshop` | NEEDS_REPAIR | OBSERVED: white header, full long nav list, GREEN search button... | OBSERVED: byte-for-byte identical hero to pine_eco on both Desktop and Mobile -- same phot... | OBSERVED: floating dock, identical to pine_eco on the captured Mobile evidence |
| 23 | `tower_department` | PASS | OBSERVED: dark header, arched-cutout hero on a crimson/red background -- campaign_mosaic-f... | OBSERVED: 3 arch-cutout products, red background... | NOT_VISIBLE in this capture |
| 24 | `beauty_dew` | PASS | OBSERVED: dark header (floating_compact family)... | OBSERVED: product_focus-family hero, dark ground, promo blocks below... | OBSERVED: red/crimson circular floating cart button -- distinct accent colour from coastal_product/rayan_tech's own product_focus siblings |
| 25 | `horizon_story` | PASS | OBSERVED: light header... | OBSERVED: side_offer_slider hero -- unique among all 50 (single-key family), single image ... | OBSERVED: flat dark bar |
| 26 | `mina_community` | PASS | OBSERVED: crimson/red full-width header -- distinct from the other arch-cutout Templates' ... | OBSERVED: social_gallery hero -- unique among all 50 (single-key family); arch-cutout comp... | OBSERVED: flat dark bar with orange square highlight |
| 27 | `silk_editorial` | NEEDS_REPAIR | OBSERVED: light cream/ivory header, barely-visible border... | OBSERVED: same hero.immersive.v1 split-hero content (photo+headline+CTA) as parnian_editor... | NOT_VISIBLE in this capture |
| 28 | `tuska_bento` | PASS | OBSERVED: light header... | OBSERVED: promo_bento-family hero with visible bento-style tiled composition... | NOT_VISIBLE in this capture |
| 29 | `rayan_tech` | PASS | OBSERVED: dark header... | OBSERVED: product_focus-family hero, dark ground... | NOT_VISIBLE in this capture |
| 30 | `laleh_play` | NEEDS_REPAIR | OBSERVED: dark navy top bar, identical nav item list to playful_lifestyle... | OBSERVED: identical arch-cutout composition and photos to playful_lifestyle, on a vivid OR... | NOT_VISIBLE in this capture |
| 31 | `city_classic` | PASS | OBSERVED: DARK NAVY full-width header on Desktop (same 4-item nav list and hamburger posit... | OBSERVED: same editorial_split hero content as cedar_home/warm_boutique/green_workshop/pin... | OBSERVED: 4-item bar, identical style to cedar_home on Mobile |
| 32 | `collection_index` | PASS | OBSERVED: light header, full nav... | OBSERVED: intentional absence confirmed (hero_expected=False); opens on a category/collect... | NOT_VISIBLE in this capture |
| 33 | `kamand_artisan` | PASS | OBSERVED: light cream/peach MINIMAL header -- icon-only, NO category nav row at all, disti... | OBSERVED: same editorial_split hero content as the rest of this cluster... | NOT_VISIBLE in this capture |
| 34 | `almas_luxury` | PASS | OBSERVED: dark header... | OBSERVED: product_focus-family hero, dark ground, light-blue-tinted page area below... | NOT_VISIBLE in this capture |
| 35 | `roosta_zigzag` | PASS | OBSERVED: dark header, orange/gold accent controls... | OBSERVED: image_collage-family hero, but a 2-image left/right split rather than the 3-arch... | NOT_VISIBLE in this capture |
| 36 | `mother_utility` | PASS | OBSERVED: light header, promo blocks (pink/navy/teal), grid of clothing items... | OBSERVED: intentional absence confirmed (hero_expected=False)... | NOT_VISIBLE in this capture |
| 37 | `aftab_price` | PASS | OBSERVED: dark header, typographic-family hero (large price/offer-led headline)... | OBSERVED: typographic hero, price-forward messaging... | NOT_VISIBLE in this capture |
| 38 | `mist_quiet` | PASS | OBSERVED: light cream header... | OBSERVED: quiet-family hero, centred, minimal, same restrained treatment as literary_catal... | NOT_VISIBLE in this capture |
| 39 | `night_catalog` | PASS | OBSERVED: dark header... | OBSERVED: quiet-family hero on a dark ground -- same restrained composition as literary_ca... | NOT_VISIBLE in this capture |
| 40 | `watchmaker_round` | PASS | OBSERVED: dark header... | OBSERVED: product_focus-family hero, dark ground, circular/round accent motifs... | NOT_VISIBLE in this capture |
| 41 | `kite_playful` | PASS | OBSERVED: orange header bar... | OBSERVED: same arch-cutout 3-product hero family as playful_lifestyle/laleh_play/niloufar_... | OBSERVED: purple circular floating cart button |
| 42 | `pine_eco` | NEEDS_REPAIR | OBSERVED: white/cream header, full long nav list, GREEN search button... | OBSERVED: byte-for-byte identical hero to green_workshop on both Desktop and Mobile... | OBSERVED: floating dock, identical to green_workshop on the captured Mobile evidence |
| 43 | `mirror_beauty` | PASS | OBSERVED: dark purple/violet header... | OBSERVED: product_focus-family hero, dark violet ground... | NOT_VISIBLE in this capture |
| 44 | `charcoal_grill` | PASS | OBSERVED: dark header... | OBSERVED: product_focus-family hero, dark charcoal ground... | NOT_VISIBLE in this capture |
| 45 | `calligraphy_paper` | PASS | OBSERVED: warm olive/tan header... | OBSERVED: same hero.immersive.v1 split-hero family as editorial_jewelry/premium_leather_no... | NOT_VISIBLE in this capture |
| 46 | `harbor_imports` | PASS | OBSERVED: light header... | OBSERVED: same arch-cutout hero family as playful_lifestyle/laleh_play/niloufar_glass/mina... | NOT_VISIBLE in this capture |
| 47 | `parnian_editorial` | NEEDS_REPAIR | OBSERVED: solid warm ORANGE/RUST header bar -- clearly distinct from silk_editorial's pale... | OBSERVED: same hero.immersive.v1 split-hero content (identical photo+headline+CTA) as silk... | NOT_VISIBLE in this capture |
| 48 | `racer_tech` | PASS | OBSERVED: dark purple header... | OBSERVED: media_feature-family hero (same family as dark_digital), dark purple ground... | NOT_VISIBLE in this capture |
| 49 | `ferdowsi_department` | PASS | OBSERVED: pink/magenta header... | OBSERVED: same arch-cutout hero family as playful_lifestyle/laleh_play/niloufar_glass/mina... | NOT_VISIBLE in this capture |
| 50 | `anniversary_mosaic` | PASS | OBSERVED: light header... | OBSERVED: promo_bento-family hero (bento-tiled), same family as dense_marketplace/fashion_... | NOT_VISIBLE in this capture |

Full per-Template detail (all 9 observed axes, configured supporting metadata, and evidence paths) is in `visual_distinctness_matrix.json`.

## Certification closure requirement

rendered_pass_count = 44 (required: 50), manual_review_required_count = 0 (required: 0), needs_repair_count = 6 (required: 0). **Not satisfied.** Per this round's own binding rule, the W4C final certification status is downgraded to **NEEDS REPAIR** on visual distinctness grounds alone -- the 704/704 browser certification result itself (FAIL=0, BLOCKED=0, accessibility FAIL=0, 0 unexpected errors, Theme cleanup 104/104) is unaffected and remains frozen/accepted per Section 2 of this round's directive.

