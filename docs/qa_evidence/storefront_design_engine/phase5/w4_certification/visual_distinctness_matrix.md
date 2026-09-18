# Final Repaired-Source Rendered Visual Distinctness -- Rebuild

FINAL_CAMPAIGN_HEAD: `0d2ab09ed40c9df566b9bc551e3065ecf95ce281`

## Method

Real Home Desktop(1440x1100)+Mobile(390x844) screenshots from THIS final campaign only (report-dir /tmp/rastisi_w4c_final_repaired_0d2ab09e), reviewed via labelled contact sheets (all 50, both viewports) plus full-resolution originals for the 3 repair pairs and their config cross-reference.

This is a full rebuild from this final campaign's own 50 Home Desktop +
50 Home Mobile screenshots -- it does NOT reuse the earlier closure round's
evidence (that evidence was captured against the old, unrepaired source and
is preserved separately as historical). Config data (registry axes) is used
only to explain and cross-check the real rendered evidence, never to
substitute for it.

## Result summary

- Rendered PASS: 50/50
- NEEDS REPAIR: 0/50
- MANUAL REVIEW REQUIRED: 0/50
- Config-only PASS decisions: 0/50

## Special closure checks (Independent Architect Section 12)

### green_workshop vs pine_eco: **DISTINCT**

Anchor: 3-panel framed carousel, external cream text column, no arrow nav, compact_menu header w/ inline search bar + text login link. Target: full-bleed carousel w/ arrow nav + bottom tab-label strip, text OVERLAID on the image with a dark scrim, no external text column. Config: identical header/layout/product_view/bottom_nav; only hero (editorial_split/split -> product_focus/beauty_editorial) differs, confirming a genuine above-the-fold structural change.

### laleh_play vs playful_lifestyle: **DISTINCT**

Anchor: 3 arch-cutout images on olive/khaki bg with teal arch borders. Target: 3-panel framed carousel (rectangular, no arches) on cream/peach bg. Completely different hero shape and background. Config: identical header/layout/product_view/bottom_nav; only hero (image_collage/atelier_triptych -> typographic/split) differs.

### parnian_editorial vs silk_editorial: **DISTINCT**

Anchor: single dark-framed jacket photo + dark brown-black text panel with badge and thumbnail rail. Target: full-bleed multi-image carousel with arrow nav + tab dots, text overlaid with scrim, warm cream/yellow page background. Config: identical header/layout/product_view/bottom_nav; only hero (immersive/luxury_showcase -> product_focus/beauty_editorial) differs.

### Repaired-targets cross-check

- **green_workshop_vs_parnian_editorial**: Both use the product_focus/beauty_editorial hero family (shared archetype), but differ in header (compact_menu, white chrome vs editorial_masthead, cream/tan chrome with icon row), layout (three_column vs two_column), product_view (standard_grid vs editorial_grid), and page background (light gray vs warm cream/yellow) -- config-confirmed and visually confirmed distinguishable from each other.

## Per-template observed axes (all 50)

Contact sheets: `visual_review/desktop_01.jpg`..`desktop_05.jpg` (10 Templates
each), `visual_review/mobile_01.jpg`..`mobile_07.jpg` (8 Templates each, last
sheet 2). Full-resolution originals for the 3 repair pairs cross-checked
directly from `/tmp/rastisi_w4c_final_repaired_0d2ab09e/screenshots/home/`.

| key | v | role | header | hero family -> rendered style | layout | product_view | observed above-the-fold hero | verdict |
|---|---|---|---|---|---|---|---|---|
| dense_marketplace | 3 | unaffected | header.marketplace_search.v1 | hero.promo_bento.v1 -> chocolate_carousel | layout.dense_five.v1 | product_view.dense_grid.v1 | 3-panel framed carousel (jacket/jacket/shoe), 3 orange circular tag badges below, no arrow nav visible | PASS |
| premium_leather | 3 | unaffected | header.editorial_row.v1 | hero.none.v1 -> None | layout.four_column.v1 | product_view.standard_grid.v1 | no large hero banner; 3 colour pill CTAs directly under header, then a 4-card product grid | PASS |
| warm_boutique | 3 | unaffected | header.compact_menu.v1 | hero.editorial_split.v1 -> split | layout.three_column.v1 | product_view.editorial_grid.v1 | single large jacket photo (left) + external cream text column (right) in dark frame, tag icons below | PASS |
| fashion_promo_catalog | 8 | unaffected | header.promo_bar.v1 | hero.promo_bento.v1 -> chocolate_carousel | layout.dense_five.v1 | product_view.dense_grid.v1 | 3-panel framed carousel w/ arrow nav + bottom tab-label strip, overlaid text on frame, 3 pills below | PASS |
| playful_lifestyle | 2 | repair_anchor | header.playful_canopy.v1 | hero.image_collage.v1 -> atelier_triptych | layout.three_column.v1 | product_view.standard_grid.v1 | 3 arch-cutout images (boots/bag/jacket) on olive/khaki bg, teal arch borders, headline inset top-right | PASS |
| utility_catalog | 2 | unaffected | header.marketplace_search.v1 | hero.none.v1 -> None | layout.catalog_list.v1 | product_view.catalog_list.v1 | no hero banner; 3 colour pill CTAs then product grid directly | PASS |
| editorial_jewelry | 3 | unaffected | header.editorial_row.v1 | hero.immersive.v1 -> luxury_showcase | layout.three_column.v1 | product_view.editorial_grid.v1 | single dark jacket photo (left) + dark brown/black text panel (right), CTA button, no thumbnail rail | PASS |
| dark_digital | 3 | unaffected | header.floating_compact.v1 | hero.media_feature.v1 -> overlay | layout.horizontal_rail.v1 | product_view.carousel.v1 | 3-panel framed carousel w/ arrow nav, dark header chrome, 3 pills below | PASS |
| cedar_home | 2 | unaffected | header.centered_brand.v1 | hero.editorial_split.v1 -> split | layout.four_column.v1 | product_view.standard_grid.v1 | 3-panel framed carousel, external text column, white header, 3 pills below | PASS |
| street_drop | 1 | unaffected | header.promo_bar.v1 | hero.typographic.v1 -> split | layout.horizontal_rail.v1 | product_view.carousel.v1 | single jacket photo (left) + dark text panel (right), dark red header badge, pills below | PASS |
| premium_leather_noir | 2 | unaffected | header.centered_brand.v1 | hero.immersive.v1 -> luxury_showcase | layout.two_column.v1 | product_view.editorial_grid.v1 | single jacket photo + dark orange/gold text panel with CTA, 3 small thumbnails below | PASS |
| search_market | 1 | unaffected | header.marketplace_search.v1 | hero.search_first.v1 -> split | layout.dense_five.v1 | product_view.dense_grid.v1 | single jacket photo + light-blue text panel, prominent inline search bar in header, tag icons | PASS |
| artisan_grain | 2 | unaffected | header.editorial_masthead.v1 | hero.typographic.v1 -> split | layout.two_column.v1 | product_view.editorial_grid.v1 | single jacket photo + cream text panel (editorial_masthead header), tag icons below | PASS |
| pixel_play | 1 | unaffected | header.category_tabs.v1 | hero.promo_bento.v1 -> chocolate_carousel | layout.bento_grid.v1 | product_view.bento.v1 | 3-panel framed carousel w/ arrow nav, category-tab header, 3 pills below | PASS |
| simorgh_market | 2 | unaffected | header.centered_brand.v1 | hero.promo_bento.v1 -> chocolate_carousel | layout.four_column.v1 | product_view.standard_grid.v1 | 3-panel framed carousel, centered-brand header, 3 pills below | PASS |
| coastal_product | 2 | unaffected | header.overlay_transparent.v1 | hero.product_focus.v1 -> beauty_editorial | layout.four_column.v1 | product_view.standard_grid.v1 | full-bleed carousel w/ arrow nav + tab labels, overlaid text w/ scrim, transparent-overlay header | PASS |
| literary_catalog | 1 | unaffected | header.editorial_masthead.v1 | hero.quiet.v1 -> split | layout.catalog_list.v1 | product_view.catalog_list.v1 | single jacket photo + cream serif-leaning text panel, no product grid visible above fold | PASS |
| gallery_minimal | 1 | unaffected | header.editorial_row.v1 | hero.immersive.v1 -> luxury_showcase | layout.catalog_list.v1 | product_view.catalog_list.v1 | single jacket photo + dark teal text panel, minimal catalog-list layout below | PASS |
| handmade_luxe | 2 | unaffected | header.editorial_row.v1 | hero.editorial_split.v1 -> split | layout.three_column.v1 | product_view.editorial_grid.v1 | single jacket photo + cream text panel, editorial_row header, tag icons below | PASS |
| niloufar_glass | 2 | unaffected | header.floating_compact.v1 | hero.image_collage.v1 -> atelier_triptych | layout.three_column.v1 | product_view.standard_grid.v1 | 3 arch-cutout images on orange/rust bg, floating-compact header | PASS |
| tool_finder | 1 | unaffected | header.marketplace_search.v1 | hero.none.v1 -> None | layout.four_column.v1 | product_view.standard_grid.v1 | no hero banner; 3 colour pills then bag product grid | PASS |
| green_workshop | 3 | repair_target | header.compact_menu.v1 | hero.product_focus.v1 -> beauty_editorial | layout.three_column.v1 | product_view.standard_grid.v1 | full-bleed carousel w/ arrow nav + bottom tab-label strip, text OVERLAID on image w/ dark scrim, white head... | PASS |
| tower_department | 1 | unaffected | header.marketplace_search.v1 | hero.campaign_mosaic.v1 -> atelier_triptych | layout.four_column.v1 | product_view.standard_grid.v1 | 3 arch-cutout images on red/pink bg, marketplace-search header | PASS |
| beauty_dew | 2 | unaffected | header.floating_compact.v1 | hero.product_focus.v1 -> beauty_editorial | layout.horizontal_rail.v1 | product_view.carousel.v1 | single jacket photo + dark text panel, floating-compact header, tag icons | PASS |
| horizon_story | 2 | unaffected | header.overlay_transparent.v1 | hero.side_offer_slider.v1 -> chocolate_carousel | layout.two_column.v1 | product_view.editorial_grid.v1 | 3-panel framed carousel, transparent-overlay header, pills below | PASS |
| mina_community | 1 | unaffected | header.community_shortcuts.v1 | hero.social_gallery.v1 -> atelier_triptych | layout.two_column.v1 | product_view.editorial_grid.v1 | 3 arch-cutout images on magenta/purple bg, community-shortcuts header icons | PASS |
| silk_editorial | 2 | repair_anchor | header.editorial_masthead.v1 | hero.immersive.v1 -> luxury_showcase | layout.two_column.v1 | product_view.editorial_grid.v1 | single dark-framed jacket photo (left) + dark brown-black text panel (right) w/ badge + thumbnail rail | PASS |
| tuska_bento | 1 | unaffected | header.compact_menu.v1 | hero.promo_bento.v1 -> chocolate_carousel | layout.bento_grid.v1 | product_view.bento.v1 | 3-panel framed carousel, bento-grid layout below, compact_menu header | PASS |
| rayan_tech | 2 | unaffected | header.marketplace_search.v1 | hero.product_focus.v1 -> beauty_editorial | layout.four_column.v1 | product_view.standard_grid.v1 | full-bleed carousel w/ arrow nav + tabs, overlaid scrim text, marketplace-search header, dark theme | PASS |
| laleh_play | 3 | repair_target | header.playful_canopy.v1 | hero.typographic.v1 -> split | layout.three_column.v1 | product_view.standard_grid.v1 | 3-panel framed carousel on cream/peach bg, playful_canopy header, 3 pills below | PASS |
| city_classic | 2 | unaffected | header.centered_brand.v1 | hero.editorial_split.v1 -> split | layout.four_column.v1 | product_view.standard_grid.v1 | single big framed jacket photo, centered-brand header, no external text column visible | PASS |
| collection_index | 1 | unaffected | header.compact_drawer.v1 | hero.none.v1 -> None | layout.catalog_list.v1 | product_view.catalog_list.v1 | no hero banner; product grid directly (4 cards: shoes/bag/etc.) | PASS |
| kamand_artisan | 2 | unaffected | header.overlay_transparent.v1 | hero.editorial_split.v1 -> split | layout.three_column.v1 | product_view.editorial_grid.v1 | single jacket photo + cream text panel, overlay-transparent header, tag icons | PASS |
| almas_luxury | 2 | unaffected | header.floating_compact.v1 | hero.product_focus.v1 -> beauty_editorial | layout.three_column.v1 | product_view.editorial_grid.v1 | full-bleed carousel w/ scrim text, teal floating-compact header | PASS |
| roosta_zigzag | 1 | unaffected | header.playful_canopy.v1 | hero.image_collage.v1 -> atelier_triptych | layout.editorial_zigzag.v1 | product_view.featured_wall.v1 | full-bleed banner (arch-cutout triptych) on olive/green bg, playful_canopy header | PASS |
| mother_utility | 1 | unaffected | header.compact_drawer.v1 | hero.none.v1 -> None | layout.four_column.v1 | product_view.standard_grid.v1 | no hero banner; 3 pills then bag product grid | PASS |
| aftab_price | 1 | unaffected | header.category_tabs.v1 | hero.typographic.v1 -> split | layout.four_column.v1 | product_view.standard_grid.v1 | single jacket photo + cream text panel, category-tabs header | PASS |
| mist_quiet | 1 | unaffected | header.editorial_row.v1 | hero.quiet.v1 -> split | layout.three_column.v1 | product_view.editorial_grid.v1 | single jacket photo + cream text panel (intentionally quiet/minimal), editorial_row header | PASS |
| night_catalog | 1 | unaffected | header.compact_drawer.v1 | hero.quiet.v1 -> split | layout.two_column.v1 | product_view.editorial_grid.v1 | 2-panel image (jacket+shoe) side by side, dot-pagination nav, dark header | PASS |
| watchmaker_round | 2 | unaffected | header.centered_brand.v1 | hero.product_focus.v1 -> beauty_editorial | layout.two_column.v1 | product_view.editorial_grid.v1 | full-bleed carousel w/ scrim text, orange/yellow centered-brand header | PASS |
| kite_playful | 1 | unaffected | header.playful_canopy.v1 | hero.image_collage.v1 -> atelier_triptych | layout.four_column.v1 | product_view.standard_grid.v1 | 3 arch-cutout images on purple bg, orange playful_canopy header | PASS |
| pine_eco | 2 | repair_anchor | header.compact_menu.v1 | hero.editorial_split.v1 -> split | layout.three_column.v1 | product_view.standard_grid.v1 | 3-panel framed carousel, external cream text column (right), white compact_menu header w/ inline search bar... | PASS |
| mirror_beauty | 2 | unaffected | header.floating_compact.v1 | hero.product_focus.v1 -> beauty_editorial | layout.three_column.v1 | product_view.standard_grid.v1 | full-bleed carousel w/ scrim text, white floating-compact header | PASS |
| charcoal_grill | 1 | unaffected | header.promo_bar.v1 | hero.product_focus.v1 -> beauty_editorial | layout.four_column.v1 | product_view.standard_grid.v1 | full-bleed carousel w/ scrim text, dark-red promo_bar header | PASS |
| calligraphy_paper | 1 | unaffected | header.compact_drawer.v1 | hero.immersive.v1 -> luxury_showcase | layout.catalog_list.v1 | product_view.catalog_list.v1 | single dark jacket photo + dark text panel, compact_drawer header | PASS |
| harbor_imports | 2 | unaffected | header.marketplace_search.v1 | hero.campaign_mosaic.v1 -> atelier_triptych | layout.four_column.v1 | product_view.standard_grid.v1 | single big product photo (boots) + text below, brown/tan marketplace-search header | PASS |
| parnian_editorial | 3 | repair_target | header.editorial_masthead.v1 | hero.product_focus.v1 -> beauty_editorial | layout.two_column.v1 | product_view.editorial_grid.v1 | full-bleed carousel w/ arrow nav + tab dots, overlaid scrim text, cream/tan editorial_masthead header w/ ic... | PASS |
| racer_tech | 1 | unaffected | header.promo_bar.v1 | hero.media_feature.v1 -> overlay | layout.horizontal_rail.v1 | product_view.carousel.v1 | full-bleed carousel w/ scrim text, purple/dark promo_bar header | PASS |
| ferdowsi_department | 1 | unaffected | header.centered_brand.v1 | hero.campaign_mosaic.v1 -> atelier_triptych | layout.featured_split.v1 | product_view.featured_wall.v1 | single big product photo (boots) + text panel, dark orange/brown centered-brand header | PASS |
| anniversary_mosaic | 1 | unaffected | header.editorial_row.v1 | hero.promo_bento.v1 -> chocolate_carousel | layout.bento_grid.v1 | product_view.bento.v1 | 3-panel framed carousel, pink editorial_row header, tag icons below | PASS |

## Footer / bottom-nav note

As in the earlier closure round, the footer is below the fold on every
single-viewport Home capture for all 50 Templates (`observed_footer:
NOT_VISIBLE` uniformly) -- this is a real capture limitation, not a defect.
Bottom navigation (Mobile only) was reviewed via the mobile contact sheets
and the config `bottom_nav` column above; no new bottom-nav collision was
found among the repaired Templates or their anchors.

## Conclusion

All 50 Templates PASS rendered visual distinctness review against this
final campaign's own real evidence. The 3 repairs this round exists to
close are confirmed genuinely DISTINCT from their anchors on real rendered
evidence (not configuration alone), and the two repaired Templates that
share a hero family with each other (`green_workshop`, `parnian_editorial`)
are confirmed distinguishable from each other. No new rendered collision was
found among the other 47 Templates during this full review.
