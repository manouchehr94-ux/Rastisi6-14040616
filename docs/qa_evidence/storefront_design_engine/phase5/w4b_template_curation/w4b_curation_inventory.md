# P5-W4B — 50-Template Curation: Source Inventory

Design/Inventory Gate evidence. **No production code changed by this document.**
All data below is measured directly from source at the certified W4A checkpoint
(`707dd631e851bdd13173bf3950489142f3e526b1`, HEAD of
`feature/phase5-design-expansion` — independently verified: local branch was
fast-forwarded from `e28b563` to `707dd63` and confirmed against
`origin/feature/phase5-design-expansion`).

Sources read: `apps/storefront_builder/a8_ready_templates.py` (full, 288
lines), `apps/storefront_builder/layout_preset_registry.py` (registration/
versioning mechanism, historical pre-A8 blocks), `apps/storefront_builder/
storefront_appearance/inventory.py` (`recipe_signature`, `component_coverage`),
`apps/storefront_builder/section_registry.py` (section catalog), and the
tests listed in the Master Handoff §17. The two 2026-09-03 evidence docs
(`a8_diversity_matrix.md`, `a8_component_coverage.md`) predate the P5-W2
`theme` family and are used only as historical cross-reference, never as the
source of truth — every number in this document was recomputed from the
current `_SPECS` tuple in `a8_ready_templates.py`.

Django was not runnable in this container (no installed dependencies), so a
standalone, dependency-free re-implementation of `_home()`, `_manifest()`,
and `recipe_signature()` was used to reproduce the exact same algorithm
against the exact `_SPECS` literal copied from source (script retained in
the session scratchpad, not committed — it duplicates pure functions only,
introduces no new production logic, and its output is fully cross-checked
against the two source-of-truth files above).

## 1. Catalog integrity (measured)

- Total registered Ready Templates: **50** (matches `A8_READY_TEMPLATES` length and `EXPECTED_LATEST_VERSIONS` in `test_a8_ready_template_catalog.py`).
- Duplicate keys: **none**.
- Pairwise-unique `recipe_signature()` structural signatures: **50 of 50 unique** (re-derived independently of `test_a8_template_diversity.py`, same algorithm: 10 component-family axes — including `theme` fixed at `theme.none.v1` for all 50 — plus the normalized Home section sequence with settings/row placement).

## 2. SOURCE-MEASURED Home section-family usage (supersedes the 2026-09-03 docs)

Actual rendered `section_key` after `_home()` mapping (i.e. what a merchant's Home page really composes — this is the number that matters for "zero usage," not the pre-mapping composition token):

| section_key | recipes using it |
|---|---:|
| `category_grid` | 49 |
| `product_section` | 47 |
| `hero_banner` | 45 |
| `image_text` | 17 |
| `catalog_product_wall` | 13 |
| `newsletter` | 12 |
| `trust_features` | 11 |
| `rich_text` | 7 |
| `testimonials` | 6 |
| `announcement_bar` | 4 |
| `brand_carousel` | 2 |
| `story_rail` | 1 |

**Confirmed still zero usage** (Master Plan §P5-W4B claim re-verified against current source, not the 2026-09-03 snapshot):
`faq`, `video_section`, `blog_posts`, `promo_cards`, `quick_links`, `collection_tiles`, `image_slider` — all **0**.

All seven are legitimate, already-registered, merchant-content-driven section
types in `section_registry.py` (`faq`, `video_section`, `blog_posts`,
`collection_tiles`, `quick_links`, `promo_cards`, `image_slider` — confirmed
by direct read of their `SectionDefinition` entries: each has its own
`validate_settings`/`default_settings`/`settings_schema`, Farsi label, and
(for `blog_posts`) `max_instances=1` mirroring the existing
`trust_features`/`newsletter`/`story_rail` singleton pattern). None require
a new section type, a new renderer, or any merchant/tenant ID — every
default is neutral/empty and merchant-editable after apply, consistent with
§14 of the Master Handoff (Template DNA stays merchant-ID-free).

## 3. Component-family axis usage (measured, palette/font excluded per the diversity test's own exclusion)

| Family | Value counts |
|---|---|
| header | marketplace_search:7, editorial_row:6, centered_brand:6, floating_compact:5, compact_menu:4, promo_bar:4, playful_canopy:4, editorial_masthead:4, compact_drawer:4, overlay_transparent:3, category_tabs:2, community_shortcuts:1 |
| hero | editorial_split:7, product_focus:7, immersive:6, promo_bento:6, none:5, image_collage:5, typographic:3, quiet:3, campaign_mosaic:3, media_feature:2, search_first:1, side_offer_slider:1, social_gallery:1 |
| layout | four_column:13, three_column:12, two_column:8, catalog_list:5, horizontal_rail:4, dense_five:3, bento_grid:3, editorial_zigzag:1, featured_split:1 |
| product_view | standard_grid:19, editorial_grid:14, catalog_list:5, carousel:4, dense_grid:3, bento:3, featured_wall:2 |
| card | standard:7, editorial_minimal:6, marketplace_price:5, soft_capsule:5, luxury_dark:4, technical_spec:4, price_first:3, beauty_glass:3, paper_frame:2, bold_outline:2, retail_row:2, catalog_index:2, shelf_editorial:2, tech_neon:1, portrait_round:1, shipping_label:1 |
| badge | none:35, sale:15 |
| motion | subtle:20, none:15, dynamic:15 |
| footer | minimal:11, marketplace_columns:11, brand_story:8, editorial_wordmark:7, centered:6, playful_wave:3, bold_columns:2, app_download:2 |
| bottom_nav | minimal_icons:13, four_item:9, floating_dock:8, five_item:7, raised_cart:7, wide_cart:4, glass_dock:2 |

No family axis is degenerate (every family has ≥2 distinct values in active use; `badge`/`motion` are the most concentrated but still exercise all their advertised values).

## 4. Home-composition length distribution

| Length (# home sections) | # templates |
|---|---:|
| 3 | 4 |
| 4 | 32 |
| 5 | 11 |
| 6 | 2 |
| 7 | 1 |

**64% of the catalog (32/50) uses exactly 4 Home sections.** This is the primary quantitative signal behind the repetition analysis in §6.

## 5. Full 50-row inventory

`Cluster` groups templates whose **Home section_key skeleton is byte-identical** (ignoring settings values) — i.e. the same sequence of section types, regardless of which component/card/hero style fills each slot. A shared skeleton is not itself a diversity-test failure (the signature still differs via component selections + settings), but it is exactly the "too close / repetitive" signal the Design Gate is required to surface.

| # | Key@Version | label_fa | header | hero | layout | product_view | card | badge | motion | footer | bottom_nav | palette | Cluster (size) | Home skeleton (section_key sequence) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01 | `editorial_jewelry@3` | آتلیه نوآر | `editorial_row` | `immersive` | `three_column` | `editorial_grid` | `luxury_dark` | `none` | `none` | `minimal` | `minimal_icons` | `atelier-ivory` | C22 (1) | hero_banner → category_grid → product_section → image_text → rich_text |
| 02 | `dense_marketplace@3` | بازار مکس | `marketplace_search` | `promo_bento` | `dense_five` | `dense_grid` | `marketplace_price` | `sale` | `dynamic` | `marketplace_columns` | `five_item` | `marketplace-spectrum` | C21 (1) | hero_banner → category_grid → product_section → catalog_product_wall → trust_features → brand_carousel → testimonials |
| 03 | `warm_boutique@3` | کارگاه لاله | `compact_menu` | `editorial_split` | `three_column` | `editorial_grid` | `paper_frame` | `none` | `subtle` | `brand_story` | `floating_dock` | `terracotta` | C27 (1) | hero_banner → image_text → product_section → testimonials → newsletter |
| 04 | `premium_leather@3` | مونو | `editorial_row` | `none` | `four_column` | `standard_grid` | `standard` | `none` | `none` | `minimal` | `minimal_icons` | `mono` | C12 (1) | announcement_bar → category_grid → product_section → rich_text |
| 05 | `dark_digital@3` | پالس نئون | `floating_compact` | `media_feature` | `horizontal_rail` | `carousel` | `tech_neon` | `sale` | `dynamic` | `marketplace_columns` | `glass_dock` | `theme-purple-neon` | C23 (1) | hero_banner → category_grid → product_section → product_section → newsletter |
| 06 | `cedar_home@1` | سدر | `centered_brand` | `editorial_split` | `four_column` | `standard_grid` | `standard` | `none` | `subtle` | `centered` | `four_item` | `forest` | C4 (3) | hero_banner → category_grid → product_section → trust_features |
| 07 | `street_drop@1` | خیابان | `promo_bar` | `typographic` | `horizontal_rail` | `carousel` | `bold_outline` | `sale` | `dynamic` | `bold_columns` | `wide_cart` | `theme-graphite-orange` | C5 (2) | announcement_bar → hero_banner → category_grid → product_section → product_section |
| 08 | `premium_leather_noir@1` | زر | `centered_brand` | `immersive` | `two_column` | `editorial_grid` | `luxury_dark` | `none` | `none` | `editorial_wordmark` | `minimal_icons` | `theme-black-gold` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 09 | `search_market@1` | میدان | `marketplace_search` | `search_first` | `dense_five` | `dense_grid` | `price_first` | `sale` | `subtle` | `marketplace_columns` | `raised_cart` | `theme-cobalt-snow` | C19 (1) | hero_banner → category_grid → catalog_product_wall → trust_features |
| 10 | `playful_lifestyle@2` | غنچه | `playful_canopy` | `image_collage` | `three_column` | `standard_grid` | `soft_capsule` | `none` | `dynamic` | `playful_wave` | `five_item` | `mint` | C26 (1) | hero_banner → category_grid → product_section → testimonials → newsletter |
| 11 | `utility_catalog@2` | نسخه | `marketplace_search` | `none` | `catalog_list` | `catalog_list` | `retail_row` | `none` | `none` | `centered` | `four_item` | `slate` | C15 (1) | category_grid → catalog_product_wall → trust_features |
| 12 | `artisan_grain@1` | دانه | `editorial_masthead` | `typographic` | `two_column` | `editorial_grid` | `editorial_minimal` | `none` | `none` | `brand_story` | `floating_dock` | `olive` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 13 | `pixel_play@1` | پیکسل | `category_tabs` | `promo_bento` | `bento_grid` | `bento` | `soft_capsule` | `sale` | `dynamic` | `minimal` | `raised_cart` | `violet-pop` | C16 (1) | hero_banner → category_grid → catalog_product_wall → newsletter |
| 14 | `simorgh_market@1` | سیمرغ | `centered_brand` | `promo_bento` | `four_column` | `standard_grid` | `marketplace_price` | `sale` | `subtle` | `marketplace_columns` | `five_item` | `royal` | C4 (3) | hero_banner → category_grid → product_section → trust_features |
| 15 | `coastal_product@1` | موج | `overlay_transparent` | `product_focus` | `four_column` | `standard_grid` | `standard` | `none` | `subtle` | `centered` | `wide_cart` | `ocean` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 16 | `literary_catalog@1` | کتابخانه | `editorial_masthead` | `quiet` | `catalog_list` | `catalog_list` | `retail_row` | `none` | `none` | `editorial_wordmark` | `minimal_icons` | `amber` | C8 (2) | hero_banner → category_grid → catalog_product_wall → rich_text |
| 17 | `gallery_minimal@1` | گالری آب | `editorial_row` | `immersive` | `catalog_list` | `catalog_list` | `editorial_minimal` | `none` | `none` | `minimal` | `minimal_icons` | `theme-ice-cyan` | C8 (2) | hero_banner → category_grid → catalog_product_wall → rich_text |
| 18 | `handmade_luxe@1` | چرم دست | `editorial_row` | `editorial_split` | `three_column` | `editorial_grid` | `luxury_dark` | `none` | `subtle` | `brand_story` | `floating_dock` | `theme-terracotta-cream` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 19 | `niloufar_glass@1` | نیلوفر | `floating_compact` | `image_collage` | `three_column` | `standard_grid` | `beauty_glass` | `none` | `subtle` | `centered` | `raised_cart` | `rose` | C2 (4) | hero_banner → category_grid → product_section → newsletter |
| 20 | `tool_finder@1` | آچار | `marketplace_search` | `none` | `four_column` | `standard_grid` | `technical_spec` | `none` | `none` | `marketplace_columns` | `four_item` | `navy` | C6 (2) | category_grid → product_section → trust_features |
| 21 | `green_workshop@1` | سبزه | `compact_menu` | `editorial_split` | `three_column` | `standard_grid` | `standard` | `none` | `subtle` | `brand_story` | `floating_dock` | `sage` | C3 (3) | hero_banner → category_grid → product_section → image_text → newsletter |
| 22 | `tower_department@1` | برج | `marketplace_search` | `campaign_mosaic` | `four_column` | `standard_grid` | `marketplace_price` | `sale` | `dynamic` | `marketplace_columns` | `five_item` | `theme-crimson-charcoal` | C10 (2) | hero_banner → category_grid → product_section → product_section → trust_features |
| 23 | `beauty_dew@1` | شبنم | `floating_compact` | `product_focus` | `horizontal_rail` | `carousel` | `beauty_glass` | `none` | `subtle` | `minimal` | `raised_cart` | `beauty-magenta` | C2 (4) | hero_banner → category_grid → product_section → newsletter |
| 24 | `fashion_promo_catalog@8` | تندر | `promo_bar` | `promo_bento` | `dense_five` | `dense_grid` | `price_first` | `sale` | `dynamic` | `marketplace_columns` | `raised_cart` | `magenta-pop` | C20 (1) | hero_banner → category_grid → product_section → catalog_product_wall |
| 25 | `horizon_story@1` | افق | `overlay_transparent` | `side_offer_slider` | `two_column` | `editorial_grid` | `standard` | `none` | `subtle` | `brand_story` | `four_item` | `peach` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 26 | `mina_community@1` | مینا | `community_shortcuts` | `social_gallery` | `two_column` | `editorial_grid` | `soft_capsule` | `none` | `dynamic` | `app_download` | `floating_dock` | `uupm-social-rose` | C24 (1) | hero_banner → category_grid → product_section → story_rail |
| 27 | `silk_editorial@1` | ابریشم | `editorial_masthead` | `immersive` | `two_column` | `editorial_grid` | `editorial_minimal` | `none` | `none` | `editorial_wordmark` | `minimal_icons` | `atelier-ivory` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 28 | `tuska_bento@1` | توسکا | `compact_menu` | `promo_bento` | `bento_grid` | `bento` | `luxury_dark` | `sale` | `dynamic` | `minimal` | `four_item` | `plum` | C18 (1) | hero_banner → category_grid → catalog_product_wall → testimonials |
| 29 | `rayan_tech@1` | رایان | `marketplace_search` | `product_focus` | `four_column` | `standard_grid` | `technical_spec` | `none` | `subtle` | `app_download` | `four_item` | `theme-midnight-electric` | C4 (3) | hero_banner → category_grid → product_section → trust_features |
| 30 | `laleh_play@1` | لاله‌زار | `playful_canopy` | `image_collage` | `three_column` | `standard_grid` | `paper_frame` | `none` | `dynamic` | `playful_wave` | `five_item` | `sunset` | C2 (4) | hero_banner → category_grid → product_section → newsletter |
| 31 | `city_classic@1` | شهر | `centered_brand` | `editorial_split` | `four_column` | `standard_grid` | `standard` | `none` | `subtle` | `brand_story` | `four_item` | `uupm-professional-navy` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 32 | `collection_index@1` | کلکسیون | `compact_drawer` | `none` | `catalog_list` | `catalog_list` | `catalog_index` | `none` | `none` | `minimal` | `minimal_icons` | `catalog-colorful` | C14 (1) | category_grid → catalog_product_wall → rich_text |
| 33 | `kamand_artisan@1` | کمند | `overlay_transparent` | `editorial_split` | `three_column` | `editorial_grid` | `editorial_minimal` | `none` | `subtle` | `brand_story` | `floating_dock` | `terracotta` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 34 | `almas_luxury@1` | الماس | `floating_compact` | `product_focus` | `three_column` | `editorial_grid` | `shelf_editorial` | `none` | `subtle` | `marketplace_columns` | `glass_dock` | `theme-ice-cyan` | C2 (4) | hero_banner → category_grid → product_section → newsletter |
| 35 | `roosta_zigzag@1` | روستا | `playful_canopy` | `image_collage` | `editorial_zigzag` | `featured_wall` | `marketplace_price` | `none` | `subtle` | `brand_story` | `four_item` | `forest` | C7 (2) | hero_banner → category_grid → catalog_product_wall → image_text |
| 36 | `mother_utility@1` | مادر | `compact_drawer` | `none` | `four_column` | `standard_grid` | `technical_spec` | `none` | `none` | `minimal` | `minimal_icons` | `slate` | C6 (2) | category_grid → product_section → trust_features |
| 37 | `aftab_price@1` | آفتاب | `category_tabs` | `typographic` | `four_column` | `standard_grid` | `price_first` | `sale` | `dynamic` | `minimal` | `raised_cart` | `amber` | C9 (2) | hero_banner → category_grid → product_section → product_section |
| 38 | `mist_quiet@1` | مه | `editorial_row` | `quiet` | `three_column` | `editorial_grid` | `standard` | `none` | `none` | `minimal` | `minimal_icons` | `mono` | C11 (2) | hero_banner → category_grid → product_section → rich_text |
| 39 | `night_catalog@1` | شبگرد | `compact_drawer` | `quiet` | `two_column` | `editorial_grid` | `editorial_minimal` | `none` | `none` | `editorial_wordmark` | `minimal_icons` | `theme-black-gold` | C11 (2) | hero_banner → category_grid → product_section → rich_text |
| 40 | `watchmaker_round@1` | ساعت‌ساز | `centered_brand` | `product_focus` | `two_column` | `editorial_grid` | `portrait_round` | `none` | `subtle` | `centered` | `minimal_icons` | `uupm-gold-purple-tech` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 41 | `kite_playful@1` | بادبادک | `playful_canopy` | `image_collage` | `four_column` | `standard_grid` | `soft_capsule` | `none` | `dynamic` | `playful_wave` | `five_item` | `uupm-playful-orange` | C25 (1) | hero_banner → category_grid → product_section → testimonials |
| 42 | `pine_eco@1` | کاج | `compact_menu` | `editorial_split` | `three_column` | `standard_grid` | `soft_capsule` | `none` | `subtle` | `centered` | `floating_dock` | `sage` | C3 (3) | hero_banner → category_grid → product_section → image_text → newsletter |
| 43 | `mirror_beauty@1` | آینه | `floating_compact` | `product_focus` | `three_column` | `standard_grid` | `beauty_glass` | `none` | `subtle` | `minimal` | `raised_cart` | `beauty-magenta` | C3 (3) | hero_banner → category_grid → product_section → image_text → newsletter |
| 44 | `charcoal_grill@1` | زغال | `promo_bar` | `product_focus` | `four_column` | `standard_grid` | `bold_outline` | `sale` | `dynamic` | `bold_columns` | `wide_cart` | `theme-graphite-orange` | C9 (2) | hero_banner → category_grid → product_section → product_section |
| 45 | `calligraphy_paper@1` | خط | `compact_drawer` | `immersive` | `catalog_list` | `catalog_list` | `editorial_minimal` | `none` | `none` | `editorial_wordmark` | `minimal_icons` | `mono` | C7 (2) | hero_banner → category_grid → catalog_product_wall → image_text |
| 46 | `harbor_imports@1` | بندر | `marketplace_search` | `campaign_mosaic` | `four_column` | `standard_grid` | `shipping_label` | `sale` | `subtle` | `marketplace_columns` | `four_item` | `navy` | C10 (2) | hero_banner → category_grid → product_section → product_section → trust_features |
| 47 | `parnian_editorial@1` | پرنیان | `editorial_masthead` | `immersive` | `two_column` | `editorial_grid` | `shelf_editorial` | `none` | `none` | `editorial_wordmark` | `minimal_icons` | `uupm-bakery-cream` | **C1 (10)** | hero_banner → category_grid → product_section → image_text |
| 48 | `racer_tech@1` | تک‌سوار | `promo_bar` | `media_feature` | `horizontal_rail` | `carousel` | `technical_spec` | `sale` | `dynamic` | `marketplace_columns` | `wide_cart` | `uupm-gaming-neon` | C5 (2) | announcement_bar → hero_banner → category_grid → product_section → product_section |
| 49 | `ferdowsi_department@1` | فردوسی | `centered_brand` | `campaign_mosaic` | `featured_split` | `featured_wall` | `marketplace_price` | `sale` | `subtle` | `marketplace_columns` | `five_item` | `uupm-burgundy-gold` | C17 (1) | hero_banner → category_grid → catalog_product_wall → product_section → brand_carousel → trust_features |
| 50 | `anniversary_mosaic@1` | پنجاه | `editorial_row` | `promo_bento` | `bento_grid` | `bento` | `catalog_index` | `sale` | `dynamic` | `editorial_wordmark` | `floating_dock` | `uupm-creative-pink` | C13 (1) | announcement_bar → hero_banner → category_grid → catalog_product_wall → testimonials → newsletter |

## 6. Cluster summary (repetition signal)

| Cluster | Size | Skeleton | Keys |
|---|---:|---|---|
| **C1** | **10** | `hero_banner → category_grid → product_section → image_text` | premium_leather_noir, artisan_grain, coastal_product, handmade_luxe, horizon_story, silk_editorial, city_classic, kamand_artisan, watchmaker_round, parnian_editorial |
| C2 | 4 | `hero_banner → category_grid → product_section → newsletter` | niloufar_glass, beauty_dew, laleh_play, almas_luxury |
| C3 | 3 | `hero_banner → category_grid → product_section → image_text → newsletter` | green_workshop, pine_eco, mirror_beauty |
| C4 | 3 | `hero_banner → category_grid → product_section → trust_features` | cedar_home, simorgh_market, rayan_tech |
| C5 | 2 | `announcement_bar → hero_banner → category_grid → product_section → product_section` | street_drop, racer_tech |
| C6 | 2 | `category_grid → product_section → trust_features` | tool_finder, mother_utility |
| C7 | 2 | `hero_banner → category_grid → catalog_product_wall → image_text` | roosta_zigzag, calligraphy_paper |
| C8 | 2 | `hero_banner → category_grid → catalog_product_wall → rich_text` | literary_catalog, gallery_minimal |
| C9 | 2 | `hero_banner → category_grid → product_section → product_section` | aftab_price, charcoal_grill |
| C10 | 2 | `hero_banner → category_grid → product_section → product_section → trust_features` | tower_department, harbor_imports |
| C11 | 2 | `hero_banner → category_grid → product_section → rich_text` | mist_quiet, night_catalog |
| C12–C27 | 1 each | (unique skeleton) | editorial_jewelry, dense_marketplace, warm_boutique, premium_leather, dark_digital, search_market, playful_lifestyle, utility_catalog, pixel_play, fashion_promo_catalog, mina_community, tuska_bento, collection_index, kite_playful, ferdowsi_department, anniversary_mosaic (16 templates) |

34 of 50 templates (68%) share their Home skeleton with at least one other template; 16 already have a unique skeleton. **C1 (10 templates, 20% of the whole catalog) is the single largest and most repetitive cluster** — every one of the 10 differs only by component-family selection (header/hero style/layout/product_view/card/footer/bottom_nav/palette), never by *what kinds of content* the Home page shows. This is the primary curation target; see the companion design spec for the per-template proposal.

## 7. Versioning mechanism (source-verified — resolves Master Handoff §8 without a Product Owner decision)

`apps/storefront_builder/layout_preset_registry.py::register_layout_preset` (lines 190–205):
- Rejects a duplicate exact `(key, version)` pair (`InvalidLayoutPresetError`).
- `LAYOUT_PRESET_VERSION_REGISTRY[(key, version)]` is populated for **every** registered definition and is never overwritten or removed — this is the permanent, immutable historical store (`get_layout_preset_version`).
- `LAYOUT_PRESET_REGISTRY[key]` (the "latest" pointer used by `list_ready_templates()`/`get_layout_preset()`, i.e. the merchant-facing catalog of exactly 50) is reassigned only when a newly registered version's numeric value is greater than the currently stored one.

The 8 pre-A8 keys (`dense_marketplace`, `premium_leather`, `warm_boutique`, `fashion_promo_catalog`, `playful_lifestyle`, `utility_catalog`, `editorial_jewelry`, `dark_digital`) already exercise this exact mechanism: their **old** exact versions (e.g. `dense_marketplace@2`, confirmed at `layout_preset_registry.py:904`) are hardcoded as separate, untouched `LayoutPresetDefinition(...)` registrations directly in `layout_preset_registry.py`, while `a8_ready_templates.py`'s `_SPECS` registers only the current/latest version (`@3`, `@8`, etc.) for the same key. Both remain independently resolvable; `list_ready_templates()` still returns exactly 50 (one latest per key — extra historical versions never inflate this count, since `LAYOUT_PRESET_REGISTRY` is a dict keyed by `key`).

**Conclusion for W4B implementation:** for every curated key, ADD a new `_RecipeSpec` row to `_SPECS` at the next integer version; do **not** edit the existing row in place. The existing row stays byte-for-byte unchanged (preserving `get_layout_preset_version(key, old_version)` exactly as today), and `register_layout_preset`'s max-version-wins logic automatically promotes the new row into the merchant-facing catalog. This requires no change to `layout_preset_registry.py` and no new registration mechanism — it is the same pattern already proven by the 8 legacy keys, just expressed as two `_RecipeSpec` tuple rows instead of two hardcoded `LayoutPresetDefinition` blocks. `test_a8_ready_template_catalog.py::EXPECTED_LATEST_VERSIONS` (and any other test literal keyed on a bumped version) must be updated in the same commit — this is the same routine maintenance already performed when A8 bumped 5 keys from `@1`/`@2` to `@3`/`@7`/`@8`.

## 8. Notable pre-existing observation (not a W4B defect)

`apps/storefront_builder/tests/test_u10_ready_template_catalog.py` and
`test_a8_ready_template_contracts.py::test_historical_ready_versions_have_complete_manifests_after_task_four`
assert historical-version resolvability for the 8 legacy keys specifically —
consistent with §7 above and unaffected by anything in this inventory. No
discrepancy was found once the actual historical-registration blocks in
`layout_preset_registry.py` (not just `a8_ready_templates.py`) were located
and read; the earlier working hypothesis that historical versions were
unrecoverable was disproven by that read and is recorded here only so a
future reviewer does not re-open the same dead end.
