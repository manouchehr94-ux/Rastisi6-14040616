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

## 9. Section render-precondition classification (SOURCE, not assumption) — PARTIALLY SUPERSEDED, see §12

**Round-2 note:** the `blog_posts` and `promo_cards` rows below were
re-verified against the actual rendered *template* (not just the context
builder) in round 2 and found unfit for different reasons — a dead
placeholder link and functional redundancy with `category_grid`,
respectively. Their "eligible: YES" verdict below is superseded by §12;
this table is kept unedited as the round-1 record, per the design spec's
own audit-trail convention (companion inventory §7 does the same for the
versioning-mechanism correction).

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

**Round-2 update:** per the Independent Architect review's IMPORTANT-3
finding, C10 is no longer left deferred — the repaired design spec now
curates `harbor_imports` (adds `brand_carousel`), which also breaks the
skeleton match. See §12 below and the design spec's repaired closure
matrix.

## 11. Round-2 template-quality audit (rendered `.html`, not just the context builder) — resolves Independent Architect Review round-2 IMPORTANT-1 and IMPORTANT-2(A)

Round 1 classified sections only by their `render_service.py` context
builder (does it auto-populate?). Round 2 additionally reads the actual
rendered Django template for every section touched by the Tier-1 proposal,
because a context builder can auto-populate data into a template that is
itself broken or redundant.

**`blog_posts.html` — confirmed dead primary interaction.** Full file:

```
{% comment %}
Phase 3 — بلوکِ جدیدِ «مطالب وبلاگ»، ساده و قابلِ‌استفاده‌ی مجدد (نه یک
رندرکننده‌ی مختصِ V5). صفحه‌ی جزئیاتِ مطلب هنوز در پروژه وجود ندارد — دقیقاً
همان محدودیتِ ``catalog/home.html``ی قدیمی (``href="#"``).
{% endcomment %}
...
<a class="blog-card" href="#">
```

The template's own comment states the post-detail route does not exist yet
in the project, and every rendered card is an `<a href="#">` — a
placeholder link, not a real navigation. **`blog_posts` is downgraded:
VISIBLE (yes, if `BlogPost` rows exist) but INTERACTIONALLY INCOMPLETE, and
therefore NOT ELIGIBLE as a W4B primary differentiator.** Not fixed in
W4B (no Blog detail subsystem, no Content/CMS widening) — remains a valid,
existing, reusable section that can become eligible once its own
navigation contract is completed in a future workstream.

**`promo_cards.html` — confirmed functional but redundant with
`category_grid`.** Full file:

```
{% if categories %}
<section class="section"><div class="tiles">
  {% for cat in categories %}
  <div class="tile {% cycle 't1' 't2' 't3' %}">
    <span class="wm">{{ cat.icon }}</span>
    <h4>{{ cat.name }}</h4>
    <a class="btn" href="{% url 'catalog:product-list' %}?category={{ cat.slug }}">مشاهده محصولات</a>
  </div>
  {% endfor %}
</div></section>
{% endif %}
```

The link is real (`catalog:product-list?category=slug`), but the markup is
functionally and almost literally identical to `category_grid.html`'s own
default (`else`) branch (`storefront_builder/sections/category_grid.html`
lines 183–194): same `tile`/`t1`/`t2`/`t3` cycling, same `<h4>مشاهده محصولات
{name}</h4>` + `<a class="btn">` pattern, same destination URL. `category_grid`
is present in 49/50 templates (including every Tier-1 candidate). **Adding
`promo_cards` to any template that already has `category_grid` — i.e. every
Tier-1 candidate — would render a second, near-identical block of the same
Store's own Categories.** `promo_cards` is downgraded: functional (no dead
link) but **NOT ELIGIBLE as a W4B primary differentiator on any of the
proposed templates**, because it duplicates `category_grid`'s own function
rather than adding a new one. It remains a legitimate section for a
template that genuinely lacks `category_grid` (none of the Tier-1
candidates qualify — all of them already have `category_grid`).

**Sections re-verified as sound (rendered template read, no defect found):**

- `collection_tiles.html` — real link to `catalog:collection-detail`
  (confirmed live route+view: `apps/catalog/urls.py:14`,
  `path("collections/<uslug:slug>/", views.collection_detail, name="collection-detail")`).
  Distinct from `category_grid`/`product_section` (collections, not
  categories or raw product listings) — no redundancy found in any
  Tier-1 candidate.
- `image_slider.html` — `{% include "storefront_builder/partials/hero_slider_body.html" %}`,
  the exact shared partial `hero_banner.html` also uses; same
  already-proven, already-shipped interaction (whatever `hero_banner`'s
  own slides link to, `image_slider`'s slides link to identically).
- `story_rail.html` — uses `{% resolve_destination_item %}`; renders a
  plain non-link block when an item has no destination (never a
  placeholder `href="#"`) — confirmed no dead-link pattern.
- `brand_carousel.html` — real link to `catalog:product-list?brand=slug`;
  its own comment states the explicit rule "هرگز دکمه‌ی بی‌اثر" ("never an
  ineffective button") — the "View all" link only renders when a real
  destination exists. Distinct from `category_grid`/`promo_cards`
  (Brand-scoped, not Category-scoped) — no redundancy found.
- `trust_features.html` — **strongest visibility guarantee of any
  candidate section:** with `settings.items` empty (the neutral default),
  it renders 4 **static, hardcoded, universal** trust badges (fast
  shipping / authenticity guarantee / 24-7 support / 7-day returns) —
  requires **zero Store data and zero shared QA fixture content** to be
  visible. No link at all (pure informational strip) — nothing to be
  dead. No redundancy risk (no other section renders this content).

## 12. Corrected section eligibility table (supersedes §9's `blog_posts`/`promo_cards` rows) — resolves Independent Architect Review round-2 IMPORTANT-2(B) — `image_slider` AND `trust_features` ROWS FURTHER SUPERSEDED, see §13–§14

| section_key | visible with shared fixture? | primary links/actions functional? | tenant/store scoping correct? | semantic data source | duplicates another section already in the target recipe? | eligible as primary W4B differentiator? |
|---|---|---|---|---|---|---|
| `faq` | NO (empty by default) | N/A (nothing rendered) | N/A | none (merchant-authored only) | N/A | **NO** |
| `testimonials` | NO (empty by default) | N/A | N/A | none (merchant-authored only) | N/A | **NO** |
| `video_section` | NO (empty by default) | N/A | N/A | none (merchant-authored only) | N/A | **NO** |
| `quick_links` | NO (empty by default) | N/A | Correct when configured (`Menu.objects.filter(store=store, ...)`) | none until merchant picks an existing Menu | N/A | **NO** |
| `blog_posts` | YES, if `BlogPost` rows exist | **NO — confirmed `href="#"` placeholder, detail route does not exist** | N/A (intentionally global/platform feed, not Store-scoped — by design, not a leak) | platform `BlogPost` (global) | not checked further — disqualified on interaction alone | **NO** |
| `promo_cards` | YES (Store's own Categories) | YES (`catalog:product-list?category=slug`, real route) | Correct (`Category.objects.filter(store=store, is_active=True)`) | Store `Category` | **YES — duplicates `category_grid`'s own function in every Tier-1 candidate (49/50 templates already have `category_grid`)** | **NO** |
| `collection_tiles` | YES, once fixture has ≥1 active `MerchantCollection` | YES (`catalog:collection-detail`, real route+view) | Correct (`MerchantCollection.objects.filter(store=store, ...)`) | Store `MerchantCollection` | No | **YES** |
| `image_slider` | YES, once fixture has ≥1 `HeroSlide` on the section (same precondition `hero_banner` already carries in 45/50 templates) | YES (identical to `hero_banner`'s own already-proven slide destinations) | Correct (`_scoped_hero_slides`, same as `hero_banner`) | Store `HeroSlide` | No | **YES** |
| `story_rail` | YES, once fixture has ≥1 active `StoryRailItem` | YES (`{% resolve_destination_item %}`; renders a safe non-link when no destination — never dead) | Correct (`StoryRailItem.objects.filter(section=section, ...)` + Store-wide fallback) | Store `StoryRailItem` | No | **YES** |
| `brand_carousel` | YES, once fixture has ≥1 active `Brand` | YES (`catalog:product-list?brand=slug`; "View all" only shown when a real destination exists — explicit no-dead-button rule in the template's own comment) | Correct (`Brand.objects.filter(store=store, is_active=True)`) | Store `Brand` | No | **YES** |
| `trust_features` | **YES unconditionally — static default, zero fixture dependency** | N/A (informational strip, no links) | N/A (no query at all under default settings) | none needed (static copy) or merchant-authored `settings.items` | No | **YES** |

**Zero prior usage was never the selection criterion — it is not one now
either.** `trust_features` (11/50 baseline uses), `brand_carousel` (already
registered, used implicitly via its own family), `collection_tiles`,
`image_slider`, and `story_rail` are the 5 sections that pass every
functional test above; `blog_posts` and `promo_cards` do not, regardless of
their zero prior usage in the catalog, and are excluded from the repaired
Tier-1 proposal entirely (design spec §8).

## 13. Round-3 template-quality audit — `image_slider` redundancy and `trust_features` business-claim finding (resolves Independent Architect Review round-3 IMPORTANT-1 and IMPORTANT-2)

**`image_slider` is byte-identical to `hero_banner` — round-2's "no
redundancy found" verdict on this pair was wrong.** Full file contents,
both templates, in their entirety:

```
apps/storefront_builder/templates/storefront_builder/sections/hero_banner.html:
{% include "storefront_builder/partials/hero_slider_body.html" %}

apps/storefront_builder/templates/storefront_builder/sections/image_slider.html:
{% include "storefront_builder/partials/hero_slider_body.html" %}
```

Both sections render the exact same shared partial
(`storefront_builder/partials/hero_slider_body.html`) — same markup, same
Alpine.js slider behavior, same CSS classes (`section hero`). Round 2's
`render_service.py`-level check (`_image_slider_context` **is**
`_hero_banner_context`) correctly showed they share a context builder, but
that observation should have been followed all the way to the rendered
template, which shows they are not merely similarly-behaved — they are the
identical UI. Every Tier-1 candidate that received `image_slider` in round
2 (`premium_leather_noir`, `coastal_product`, `kamand_artisan`,
`beauty_dew`, `mirror_beauty`) already has `hero_banner` in its
composition, so adding `image_slider` there is a second instance of the
literal same slider block — disqualified as redundant under the design's
own rule ("no duplicated/redundant section without a specific purpose").
`image_slider` is **removed from every current W4B assignment**. It
remains available in principle for a template that genuinely lacks
`hero_banner` — none of the 50 current recipes qualify (`hero` is absent
from composition in only `premium_leather`, `utility_catalog`,
`tool_finder`, `mother_utility`, `collection_index` — none of which are in
this proposal — and even for those, `hero.none.v1` already means "no
hero," so adding a slider there would be a bigger structural decision than
this bounded pass should make unprompted).

**`trust_features`'s default is not merchant-neutral.** Full default
branch, `apps/storefront_builder/templates/storefront_builder/sections/trust_features.html`
(already quoted in §11; repeated here for the specific claims):

```
<b>ارسال سریع</b><small>به سراسر کشور</small>            (fast shipping, nationwide)
<b>ضمانت اصالت</b><small>کالای اورجینال</small>            (authenticity guarantee, original goods)
<b>پشتیبانی ۲۴/۷</b><small>پاسخگویی همه‌روزه</small>        (24/7 support, daily response)
<b>۷ روز ضمانت بازگشت</b><small>بدون دردسر</small>          (7-day hassle-free returns)
```

These are business-policy claims (nationwide shipping, a specific
authenticity guarantee, 24/7 support, a 7-day no-hassle return window) that
not every merchant has actually committed to. Publishing them by default
inside a Ready Template's baked-in DNA — i.e. before any merchant has
configured `settings.items` — risks stating a policy the merchant never
agreed to. Reclassification: **VISIBLE BY DEFAULT: YES; MERCHANT-NEUTRAL BY
DEFAULT: NO; ELIGIBLE AS A NEW W4B PRIMARY DIFFERENTIATOR: NO.**
`trust_features` is **removed from every new W4B assignment**
(`city_classic`, `laleh_play`, `green_workshop`). It is **not** removed
from the 11 existing baseline recipes that already carry it (`cedar_home`,
`simorgh_market`, `search_market`, `tool_finder`, `mother_utility`,
`rayan_tech`, `tower_department`, `harbor_imports`'s own pre-curation
baseline, etc.) — those are certified, pre-existing, out of this
workstream's scope; W4B only avoids *expanding* the section's footprint.

**Surviving eligible mechanisms: `collection_tiles`, `story_rail`,
`brand_carousel`** — all three were independently re-verified against the
rendered template (not just the context builder) in §11/§12 and found
functionally and structurally distinct from every section already present
in every template they are assigned to in the repaired §15 matrix below;
none makes a business-policy claim (no static default copy at all — they
render only real Store data or nothing).

## 14. Re-run eligibility — the 3 surviving mechanisms against the round-3 six-point test

| Check | `collection_tiles` | `story_rail` | `brand_carousel` |
|---|---|---|---|
| 1. Rendered output materially distinct from another section already in every recipe it's assigned to (verified per-template in §15) | YES — own `.pcard`/`grid g4` collection-tile layout, distinct from `category_grid`, `product_section`, `image_text`, `hero_banner` | YES — circular story-avatar rail, distinct from all others | YES — brand-logo tile grid/carousel, distinct from all others |
| 2. Default/fixture behavior makes no merchant-business claim | YES — renders only real `MerchantCollection` rows or nothing; no static copy | YES — renders only real `StoryRailItem` rows or nothing; no static copy | YES — renders only real `Brand` rows or nothing; no static copy |
| 3. Primary link/action is real, not `#` | YES — `catalog:collection-detail` (live route+view) | YES — `{% resolve_destination_item %}`; a safe non-link when no destination, never `href="#"` | YES — `catalog:product-list?brand=slug`; template's own comment states the explicit no-dead-button rule |
| 4. Tenant scoping correct where Store-scoped | YES — `MerchantCollection.objects.filter(store=store, ...)` | YES — `StoryRailItem.objects.filter(section=section, ...)` + Store-wide fallback | YES — `Brand.objects.filter(store=store, is_active=True)` |
| 5. No merchant-specific ID required in Template DNA | YES — default `collection_ids: []` = "show whatever the Store has" | YES — no settings at all (`_empty_defaults()`) | YES — default `brand_ids: []` = "show whatever the Store has" |
| 6. Addition makes sense for the target template's identity | Verified per-template, §15 | Verified per-template, §15 | Verified per-template, §15 |

All three pass all six checks unconditionally (checks 1–5); check 6 is
necessarily per-template and is recorded in §15's implementation matrix.

## 15. Final implementation matrix — resolves Independent Architect Review round-3 §3A/3B

**Placement rule, corrected in the newsletter-order micro repair (removes
all implementation-time ordering discretion) — supersedes the "every
addition is appended as the last entry" statement previously here, which
was not, in fact, the catalog's actual convention:**

Checking the certified composition tokens of every existing recipe whose
Home ends in `"newsletter"` (12 of them: `warm_boutique`, `dark_digital`,
`playful_lifestyle`, `pixel_play`, `niloufar_glass`, `green_workshop`,
`beauty_dew`, `laleh_play`, `almas_luxury`, `pine_eco`, `mirror_beauty`,
`anniversary_mosaic`) shows `newsletter` is consistently the catalog's own
terminal Home block wherever it is present — never followed by another
section. `newsletter` renders an email-subscription CTA/form; moving a
discovery/merchandising block after it would turn an established terminal
CTA into a mid-page block, which no existing recipe does.

- **If the key's certified composition ends in `"newsletter"`:** the
  W4B-added token is inserted **immediately before** `"newsletter"`;
  `newsletter` remains the final Home section. Applies to 7 of the 21
  curated keys: `niloufar_glass`, `beauty_dew`, `laleh_play`,
  `almas_luxury`, `green_workshop`, `pine_eco`, `mirror_beauty`.
- **For every other curated key** (no `newsletter` in its composition):
  the W4B-added token is appended as the last entry — this mirrors the
  existing, already-certified pattern the catalog's own richest recipes
  use for their extra distinguishing sections — `dense_marketplace`
  appends `brand_carousel` then `testimonials` after its
  `catalog_product_wall`+`trust_features` core; `ferdowsi_department`
  appends `brand_carousel` then `trust_features` after its
  `featured_products`+`product_grid` core. Applies to the other 14
  curated keys, including `harbor_imports` (C10).

No other reordering of existing content in either branch.

All 21 curated keys are currently version `"1"`; every one bumps to
version `"2"` (none of the 21 collides with an already-versioned key —
`editorial_jewelry`, `dense_marketplace`, `warm_boutique`, `premium_leather`,
`dark_digital`, `fashion_promo_catalog`, `playful_lifestyle`,
`utility_catalog` are not in this proposal).

| # | Key | Old→New ver | Old composition tokens (exact, from certified `_SPECS`) | New composition tokens (**bold** = W4B-added token; position per the corrected placement rule above) | Old Home section_key sequence | New Home section_key sequence | Mechanism | Fixture dependency |
|---|---|---|---|---|---|---|---|---|
| 1 | `premium_leather_noir` | 1→2 | `("hero","arch_categories","product_grid","brand_story")` | `(..., "brand_story", **"brands"**)` | hero_banner→category_grid→product_section→image_text | + brand_carousel | brand_carousel | ≥1 active Brand |
| 2 | `artisan_grain` | 1→2 | `("hero","indexed_categories","product_grid","brand_story")` | `(..., **"collection_tiles"**)` | hero_banner→category_grid→product_section→image_text | + collection_tiles | collection_tiles | ≥1 active MerchantCollection |
| 3 | `coastal_product` | 1→2 | `("hero","chip_categories","product_grid","brand_story")` | `(..., **"collection_tiles"**)` | hero_banner→category_grid→product_section→image_text | + collection_tiles | collection_tiles | ≥1 active MerchantCollection |
| 4 | `handmade_luxe` | 1→2 | `("hero","indexed_categories","product_grid","brand_story")` | `(..., **"brands"**)` | hero_banner→category_grid→product_section→image_text | + brand_carousel | brand_carousel | ≥1 active Brand |
| 5 | `watchmaker_round` | 1→2 | `("hero","indexed_categories","product_grid","brand_story")` | `(..., **"brands"**)` | hero_banner→category_grid→product_section→image_text | + brand_carousel | brand_carousel | ≥1 active Brand |
| 6 | `horizon_story` | 1→2 | `("hero","chip_categories","product_grid","brand_story")` | `(..., **"community_gallery"**)` | hero_banner→category_grid→product_section→image_text | + story_rail | story_rail | ≥1 active StoryRailItem |
| 7 | `silk_editorial` | 1→2 | `("hero","indexed_categories","product_grid","brand_story")` | `(..., **"collection_tiles"**)` | hero_banner→category_grid→product_section→image_text | + collection_tiles | collection_tiles | ≥1 active MerchantCollection |
| 8 | `city_classic` | 1→2 | `("hero","circular_categories","product_grid","brand_story")` | `(..., **"collection_tiles"**)` | hero_banner→category_grid→product_section→image_text | + collection_tiles | collection_tiles | ≥1 active MerchantCollection |
| 9 | `kamand_artisan` | 1→2 | `("hero","indexed_categories","product_grid","brand_story")` | `(..., **"community_gallery"**)` | hero_banner→category_grid→product_section→image_text | + story_rail | story_rail | ≥1 active StoryRailItem |
| 10 | `parnian_editorial` | 1→2 | `("hero","arch_categories","product_grid","brand_story")` | `(..., **"community_gallery"**)` | hero_banner→category_grid→product_section→image_text | + story_rail | story_rail | ≥1 active StoryRailItem |
| 11 | `niloufar_glass` | 1→2 | `("hero","circular_categories","product_grid","newsletter")` | `("hero","circular_categories","product_grid",` **`"collection_tiles"`**`,"newsletter")` | hero_banner→category_grid→product_section→newsletter | hero_banner→category_grid→product_section→**collection_tiles**→newsletter | collection_tiles | ≥1 active MerchantCollection |
| 12 | `beauty_dew` | 1→2 | `("hero","circular_categories","product_rail","newsletter")` | `("hero","circular_categories","product_rail",` **`"community_gallery"`**`,"newsletter")` | hero_banner→category_grid→product_section→newsletter | hero_banner→category_grid→product_section→**story_rail**→newsletter | story_rail | ≥1 active StoryRailItem |
| 13 | `laleh_play` | 1→2 | `("hero","chip_categories","product_grid","newsletter")` | `("hero","chip_categories","product_grid",` **`"brands"`**`,"newsletter")` | hero_banner→category_grid→product_section→newsletter | hero_banner→category_grid→product_section→**brand_carousel**→newsletter | brand_carousel | ≥1 active Brand |
| 14 | `almas_luxury` | 1→2 | `("hero","circular_categories","product_grid","newsletter")` | `("hero","circular_categories","product_grid",` **`"community_gallery"`**`,"newsletter")` | hero_banner→category_grid→product_section→newsletter | hero_banner→category_grid→product_section→**story_rail**→newsletter | story_rail | ≥1 active StoryRailItem |
| 15 | `green_workshop` | 1→2 | `("hero","tile_categories","product_grid","brand_story","newsletter")` | `("hero","tile_categories","product_grid","brand_story",` **`"brands"`**`,"newsletter")` | hero_banner→category_grid→product_section→image_text→newsletter | hero_banner→category_grid→product_section→image_text→**brand_carousel**→newsletter | brand_carousel | ≥1 active Brand |
| 16 | `pine_eco` | 1→2 | `("hero","tile_categories","product_grid","brand_story","newsletter")` | `("hero","tile_categories","product_grid","brand_story",` **`"collection_tiles"`**`,"newsletter")` | hero_banner→category_grid→product_section→image_text→newsletter | hero_banner→category_grid→product_section→image_text→**collection_tiles**→newsletter | collection_tiles | ≥1 active MerchantCollection |
| 17 | `mirror_beauty` | 1→2 | `("hero","circular_categories","product_grid","brand_story","newsletter")` | `("hero","circular_categories","product_grid","brand_story",` **`"community_gallery"`**`,"newsletter")` | hero_banner→category_grid→product_section→image_text→newsletter | hero_banner→category_grid→product_section→image_text→**story_rail**→newsletter | story_rail | ≥1 active StoryRailItem |
| 18 | `cedar_home` | 1→2 | `("hero","tile_categories","product_grid","trust_features")` | `(..., **"collection_tiles"**)` | hero_banner→category_grid→product_section→trust_features | + collection_tiles | collection_tiles | ≥1 active MerchantCollection |
| 19 | `simorgh_market` | 1→2 | `("hero","circular_categories","product_grid","trust_features")` | `(..., **"brands"**)` | hero_banner→category_grid→product_section→trust_features | + brand_carousel | brand_carousel | ≥1 active Brand |
| 20 | `rayan_tech` | 1→2 | `("hero","tile_categories","product_grid","service_strip")` | `(..., **"community_gallery"**)` | hero_banner→category_grid→product_section→trust_features | + story_rail | story_rail | ≥1 active StoryRailItem |
| 21 | `harbor_imports` | 1→2 | `("hero","tile_categories","product_grid","sale_products","trust_features")` | `(..., "trust_features", **"brands"**)` | hero_banner→category_grid→product_section→product_section→trust_features | + brand_carousel | brand_carousel | ≥1 active Brand |

Final mechanism distribution: `collection_tiles`×7, `brand_carousel`×7,
`story_rail`×7 — this even split is **incidental**, not a re-imposed
quota: it is simply how 21 templates' own identity-driven mapping landed
once `blog_posts`/`promo_cards` (round 2) and `image_slider`/`trust_features`
(round 3) were excluded, leaving exactly 3 eligible mechanisms. No template
below was assigned a mechanism to balance a count.

Per-template identity rationale (why mechanism 6 in §14 is satisfied) and
interactive-behavior/non-redundancy notes are in the design spec §8's
matrix, cross-referenced to this table by key.

## 16. Newsletter-terminal ordering contract (newsletter-order micro repair)

**New implementation acceptance requirement:** for every latest Ready
Template whose composition contains `newsletter`, `newsletter` must
remain the final Home section. At minimum, test the 7 W4B-curated
newsletter recipes in row 11–17 above:

```python
NEWSLETTER_TERMINAL_CURATED_KEYS = (
    "niloufar_glass", "beauty_dew", "laleh_play", "almas_luxury",
    "green_workshop", "pine_eco", "mirror_beauty",
)

def test_newsletter_stays_the_final_home_section(self):
    for key in NEWSLETTER_TERMINAL_CURATED_KEYS:
        preset = lpr.get_layout_preset(key)
        with self.subTest(key=key):
            self.assertEqual(preset.pages["home"][-1].section_key, "newsletter")
```

Ordering contract only — `newsletter`'s own section code/behavior is not
touched by this repair or by W4B.
