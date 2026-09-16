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

**CORRECTED conclusion (previous design-gate round got this wrong — see the
Independent Architect Review IMPORTANT-1 finding):** `A8_READY_TEMPLATES =
tuple(_build(spec) for spec in _SPECS)` is a **direct 1:1 map over `_SPECS`
with no dedup**. Appending a new row to `_SPECS` while leaving the old row
in place — the previous conclusion — would make `_SPECS` (and therefore
`A8_READY_TEMPLATES`) grow past 50 for every curated key, which
`test_a8_ready_template_catalog.py::test_show_all_is_exactly_the_literal_fifty_key_catalog`
(`len(A8_READY_TEMPLATES) == 50`) would correctly reject. That test reads
`A8_READY_TEMPLATES` itself, not the deduplicated `LAYOUT_PRESET_REGISTRY`,
so the "`list_ready_templates()` dedups by key" argument does not save it.

**Repaired mechanism (still zero new registry, still the same canonical
`register_layout_preset`/`LAYOUT_PRESET_VERSION_REGISTRY`, still confined to
`a8_ready_templates.py` — no `layout_preset_registry.py` change needed):**
add a second, separate, frozen tuple in `a8_ready_templates.py`,
`_HISTORICAL_SPECS`, holding the exact, untouched `_RecipeSpec` for every
key's outgoing version, registered through a second loop that never feeds
`A8_READY_TEMPLATES`:

```python
_SPECS = (
    # ... exactly 50 rows, one per key, always the CURRENT latest version ...
)

_HISTORICAL_SPECS = (
    # one frozen row per curated key's OUTGOING version, added only when
    # that key is curated — copied verbatim from its old _SPECS row and
    # never edited again.
)

A8_READY_TEMPLATES = tuple(_build(spec) for spec in _SPECS)          # stays 50
for _ready_template in A8_READY_TEMPLATES:
    register_layout_preset(_ready_template)

for _historical_spec in _HISTORICAL_SPECS:                            # NEW
    register_layout_preset(_build(_historical_spec))
```

Why this satisfies every constraint the review listed:
1/2. `A8_READY_TEMPLATES` is built from `_SPECS` alone, which always has
   exactly 50 rows (curating a key edits its existing `_SPECS` row in place —
   version bump + new composition — it does not add a row); `list_ready_templates()`
   stays 50 for the same reason plus the existing max-version-wins dedup.
3. Editing a key's `_SPECS` row to a higher version number is exactly "every
   curated key receives a new numeric latest version."
4. The old row, copied verbatim into `_HISTORICAL_SPECS` before being edited
   out of `_SPECS`, is registered via the exact same `register_layout_preset`
   call (routed through the same `_build()` compiler) — `get_layout_preset_version(key, old_version)`
   resolves it forever, byte-for-byte.
5. `_HISTORICAL_SPECS` entries never reach `A8_READY_TEMPLATES`; and because
   their version number is always lower than the corresponding `_SPECS` row,
   `register_layout_preset`'s `_version_number(...) > _version_number(current.version)`
   comparison never lets them claim `LAYOUT_PRESET_REGISTRY[key]` (the
   "latest" slot `list_ready_templates()`/`get_layout_preset()` read) —
   independent of import/registration order.
6/7. Same `LAYOUT_PRESET_VERSION_REGISTRY`/`register_layout_preset` authority,
   same `_build()` compiler, same `_RecipeSpec` dataclass — no second
   registry, no second compiler.
8. The 8 pre-A8 legacy hardcoded blocks in `layout_preset_registry.py` are
   untouched; this mechanism lives entirely in `a8_ready_templates.py` and
   does not interact with them.

This is a strict improvement over both the previous (broken) design and
over literally mirroring the 8 legacy keys' pattern in `layout_preset_registry.py`
(which would require hand-transcribing each curated key's fully-compiled
`PresetSectionEntry` tuple instead of reusing `_build()`) — it is a smaller,
single-file, single-compiler change.

`test_a8_ready_template_catalog.py::EXPECTED_LATEST_VERSIONS` must be
updated for every bumped key in the same commit — routine maintenance,
already performed historically when A8 bumped 5 keys from `@1`/`@2` to
`@3`/`@7`/`@8`. The hardcoded 8-key `HISTORICAL_IDENTITIES` dicts in
`test_a8_ready_template_catalog.py` and `test_a8_ready_template_contracts.py`
are untouched (they enumerate only the 8 pre-A8 keys, never the newly
curated ones) — the new RED/GREEN contract for curated keys is a new test,
not an edit to those two dicts. See the companion design spec §10 for the
exact RED/GREEN contract.

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

## 9. Section render-precondition classification (SOURCE, not assumption)

Read directly from `apps/storefront_builder/section_registry.py`
(`default_*_settings()`) and `apps/storefront_builder/services/render_service.py`
(`_CONTEXT_AWARE_BUILDERS` / the individual `_*_context(store, section)`
functions) for every section named in the Tier-1 proposal, per the
Independent Architect Review IMPORTANT-3 finding.

| section_key | default settings | render precondition | auto-source? | visible on a standard populated Store with zero manual per-section edit? | requires merchant-specific config (an ID/URL/menu the merchant must pick)? | eligible as PRIMARY differentiator? |
|---|---|---|---|---|---|---|
| `faq` | `{"title": "سوالات متداول", "items": []}` | `items` non-empty | No — `_static_context` returns `{}`; template renders only whatever is in `section.settings.items` | **NO** | Yes (merchant must author Q&A pairs) | **NO** |
| `testimonials` | `{"title": "نظرات مشتریان", "items": []}` | `items` non-empty | No — `_static_context` returns `{}` | **NO** | Yes (merchant must author quotes) | **NO** |
| `video_section` | `{"title": "", "video_url": "", "caption": ""}` | non-empty, provider-recognized `video_url` | No — `_video_section_context` returns null embed fields when `video_url` is empty | **NO** | Yes (merchant must supply a real video URL) | **NO** |
| `quick_links` | `{"title": "", "menu_id": None}` | `menu_id` must reference an existing, active Store `Menu` | No — `_quick_links_context` returns `quick_link_items: []` when `menu_id` is unset | **NO** | Yes (merchant must pick an existing Menu) | **NO** |
| `blog_posts` | `{"item_limit": 6, "title": ""}` | platform `BlogPost` table (global, no Store FK — same query `catalog.views.home` already runs) has ≥1 entry | **Yes** — `_blog_posts_context` auto-queries `BlogPost.objects.order_by("-published_at")[:item_limit]` | **YES**, once the shared fixture/platform has ≥1 published post | No | **YES** |
| `promo_cards` | `{"item_limit": 4}` | Store has ≥1 active `Category` | **Yes** — `_category_context_for_promo_cards` auto-queries the Store's own active Categories | **YES** — every Ready Template that already uses `category_grid` (49/50) already depends on this same precondition | No | **YES** |
| `collection_tiles` | `{"title": "", "collection_ids": [], "tile_style": "grid"}` | Store has ≥1 active `MerchantCollection` (empty `collection_ids` = auto: all active) | **Yes** — `_collection_tiles_context` auto-queries the Store's own active Collections | **YES**, once the shared fixture defines ≥1 Collection | No | **YES** |
| `image_slider` | `default_slider_settings()` (autoplay/interval/arrows/…, no image data) | ≥1 `HeroSlide` scoped to the section | **Yes** — `_image_slider_context` **is** `_hero_banner_context` (identical function) | **YES**, under the exact same precondition `hero_banner` already carries in 45/50 templates today (confirmed by `test_u10_ready_template_catalog.py::ApplyAndRenderSmokeTests`, which creates one `HeroSlide` after Apply specifically so the smoke test has visible content) | No | **YES** |
| `story_rail` | `_empty_defaults()` → `{}` | ≥1 active `StoryRailItem` scoped to the section (or Store-wide fallback) | **Yes** — `_story_rail_context` auto-queries `StoryRailItem` | **YES**, once the shared fixture defines ≥1 StoryRailItem (already required today for `mina_community`'s existing `story_rail` usage) | No | **YES** |

**Conclusion:** `faq`, `testimonials`, `video_section`, and `quick_links`
("Group B") render nothing under neutral default settings and must never be
the *sole* reason a Tier-1 template is called materially curated (repaired
design spec §5 applies this). `blog_posts`, `promo_cards`, `collection_tiles`,
`image_slider`, and `story_rail` ("Group A") are auto-sourced from real
Store/platform data with no merchant-specific ID required in Template DNA,
and become visible under a standard, shared, controlled QA fixture — exactly
the same precondition class the catalog already accepts for `hero_banner`/
`category_grid`/`product_section`.

## 10. Tier-2 / remaining shared-skeleton clusters — per-axis structural diff (evidence for the design spec's closure matrix)

For each of the 7 size-2 clusters left unchanged or deferred, the count of
differing values (out of the 7 non-palette/non-font family axes: header,
hero, layout, product_view, card, footer, bottom_nav — read directly from
the §5 table above):

| Cluster | Pair | Differing axes | Count | Shared axes |
|---|---|---|---:|---|
| C10 | `tower_department` / `harbor_imports` | card, bottom_nav | **2/7 (weakest)** | header, hero, layout, product_view, footer |
| C5 | `street_drop` / `racer_tech` | hero, card, footer | 3/7 | header, layout, product_view, bottom_nav |
| C6 | `tool_finder` / `mother_utility` | header, footer, bottom_nav | 3/7 | hero, layout, product_view, card |
| C8 | `literary_catalog` / `gallery_minimal` | header, hero, card, footer | 4/7 | layout, product_view, bottom_nav |
| C11 | `mist_quiet` / `night_catalog` | header, layout, card, footer | 4/7 | hero, product_view, bottom_nav |
| C9 | `aftab_price` / `charcoal_grill` | header, hero, card, footer, bottom_nav | 5/7 | layout, product_view |
| C7 | `roosta_zigzag` / `calligraphy_paper` | header, hero, layout, product_view, card, footer, bottom_nav | **7/7 (strongest)** | (none — only the raw skeleton shape is shared) |

`C10` (`tower_department`/`harbor_imports`) is honestly the weakest-justified
"leave unchanged" pair in the whole catalog — the two differ only in card
style (`marketplace_price` vs `shipping_label`) and bottom-nav variant. The
repaired design spec's closure matrix (§8) flags this explicitly rather than
asserting "no change" without qualification.
