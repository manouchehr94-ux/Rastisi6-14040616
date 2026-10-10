# Ready Templates 51 / 52 / 53 — fidelity QA (local, not pushed)

Branch `fix/ready-templates-51-52-53-v2`, built on the approved contrast branch
`fix/sitewide-contrast-accessibility-v1` (`00f20e1ab5ca989c80fbce488c288a7dcc161bf6`, an ancestor of HEAD).

Visual source of truth: the three supplied screenshots only
(A = 51 `stationery_spectrum`, B = 52 `magenta_beauty_retail`, C = 53 `pastel_kawaii_stationery`).
Each reference was normalised to a 1440 px page width and each template was rendered through the real
storefront (apply → publish → public home) at 1440 px. Side-by-side images
(REFERENCE | RASTISI RENDER, same effective width): `side_by_side_template5x_NN.jpg` in this folder.

**None of the three templates is claimed to be "exact".** Every template still differs visibly from its reference.
Differences are classified as:

* **DATA** — depends on merchant/demo data (photos, category count, badges, brand logos); the engine does not fabricate it.
* **ENGINE** — the existing section/variant model cannot express it without a new primitive.
* **INTENT** — deliberately different (e.g. a blank lazy-load gap in the capture is not reproduced as an empty panel).

The seeded demo store only has 3 categories, fashion photos and no brands/badges, so every template looks
"more fashion, fewer tiles" than the stationery/beauty references. The reference captures are low resolution
(361 / 517 / 186 px wide), so fine detail (icon art, small text) was not measurable.

## Page-level numbers (normalised 1440)

| | reference | render | main cause of the difference |
|---|---|---|---|
| 51 page height | 7978 | ≈ 6800 | footer 913 vs ≈ 500 (DATA: badges/paragraph), two lazy-load gaps in the capture (INTENTIONAL), top block 1492 vs ≈ 1334 |
| 52 page height | 5571 | ≈ 4260 | footer/newsletter block and "recently viewed" panel (DATA/INTENT), campaign bands +13 % |
| 53 page height | 15484 | ≈ 14410 | content column 1169 px (ref) vs 1148 px (render); image rhythm; reference blog/about blocks |

## Template 51 — `stationery_spectrum` ("تحریر رنگی")

Reference map (A, top → bottom): header (3 rows) · decorative strip banner · hero (≈70 %) + offer card (≈30 %) ·
6 grey category circles · 5-box service strip · 4 coloured tiles · red band · amazing-offer block · green band ·
white paired rails · ochre band · paired rails · violet band · paired rails · blue band · paired rails ·
brands panel · blog panel · dark footer.

Rendered map: `stationery_search` header (165) · strip banner (64) · hero 9 + offer 3 (equal height) ·
`grey_circles` (≈ 230) · 5-box compact features (68) · `tile-4` (≈ 350) · bands 519/519/519/519/456 px
(tone 1…5 + `commerce-doodle`) interleaved with `amazing_offers` (286) and 6/6 paired rails (456) ·
brand carousel (126) · blog grid (264) · `stationery_dark` footer (≈ 500).

| aspect | status | class |
|---|---|---|
| section order, band count, band tones, doodle pattern, band height (519 vs ≈ 511) | matched | — |
| hero/offer split, equal heights, hero ratio | matched | — |
| category circles: 6-track geometry, 156 px circles | matched; only 3 circles shown | DATA |
| four tiles: 4 columns, ratio ≈ 1 : 0.99, bottom title | matched; demo photos instead of art | DATA |
| centre-stepper product cards, no quick view | matched | — |
| strip banner | image banner of 64 px, but demo image, no artwork | DATA |
| paired rails | two lazy-load gaps in the capture are filled with the same rail component | INTENT |
| brand panel: white rounded surface, centred title with accent underline | reproduced (white colour band + generic panel look); brand tiles show names | ASSET (no logos) |
| blog panel: white rounded surface, one row of square-image cards with category badge, 2-line title, action pill | reproduced via the new generic `blog_posts` option `style: panel_carousel`; 4 cards (4 demo posts) instead of 6; no side arrows, no heading icon | DATA (post count) / ENGINE (arrows, icon) |
| footer (links bar, 4th column, paragraph, 5 badge tiles) | structure present, badge row/paragraph absent | DATA |
| header proportions | close, not measured per element | — |

## Template 52 — `magenta_beauty_retail` ("زیبایی ارغوانی")

Reference map (B): header (2 rows) · pink editorial hero (521) · 6 purple icon tiles · magenta campaign band (465) ·
4 gradient text/photo tiles (248) · mint campaign band (465) · brand strip · purple 3-column list wall (510) ·
two pink banners (212) · purple featured-row wall (621) · "recently viewed" heading (empty) · pale newsletter panel ·
4 service boxes · purple footer.

Rendered map: `beauty_search_nav` header (135) · `beauty_editorial` hero (506) · `icon_tiles` (228) · campaign band (528) ·
`gradient_tiles` (270) · campaign band (528) · brand strip (145) · wall `group_columns` (472) · `wide-single` 2 × (682 × 185) ·
wall `featured_row` (563) · newsletter (146) · features (70) · `beauty_retail_columns` footer (411).

| aspect | status | class |
|---|---|---|
| hero height/ratio, dots only | matched (506 vs 521) | — |
| icon tiles: purple glyph tiles, no photos, 6-track geometry | matched; 3 tiles shown | DATA |
| gradient tiles: 4 columns, gap ≈ 32 px, ratio ≈ 1.35, radius 22 px, pink/blue/yellow/indigo order, bold title top-start, picture bottom-end | matched; 3 tiles shown; picture is a rectangular photo (the reference uses cut-out PNGs); the reference's second text line (category description) is not rendered because categories have no description field | ASSET / DATA |
| campaign bands | matched in structure; ≈ 13 % taller than reference | ENGINE (card height) |
| wall / banner pair / featured row | matched in structure and order | — |
| "recently viewed" heading with empty body | omitted — the region is empty in the capture | INTENT |
| final product row | none (capture has none) | — |
| hero/banner imagery | demo photos | DATA |
| footer extras | partly | DATA |

## Template 53 — `pastel_kawaii_stationery` ("کاغذ پاستلی")

Reference map (C): red double top bar · header (centred logo, search, nav) · rounded poster hero (≈ 1 : 1.89) ·
4 pastel mini banners · 6 pastel category tiles · groups of 4-column square products (12/24/16/8…) each followed by a
pager bar · plain image + text blocks · blog row · avatar testimonials · minimal footer.

Rendered map: `kawaii_center` header (187 incl. bars) · `poster_wide` hero (1148 × 607) · `mini-4` banners (226) ·
`pastel_tiles` (325) · `catalog_grid` groups (1525 / 2769 / 1970 / 1080 × 4 / 543) with pager bars · two plain image/text blocks (525) ·
blog (376) · avatar testimonials (340) · `kawaii_minimal` footer (79).

| aspect | status | class |
|---|---|---|
| group count/rhythm, 4 columns, square tinted images | matched | — |
| pager bar | order, proportions and states now follow the reference (disabled previous-page control at the start edge, page box with «صفحه … از ۱» in the centre, purple action button at the end edge, ≈ 56 px bar); colours come from palette tokens | — |
| plain image/text block | plain image box + placeholder structure | — |
| content column width | 1148 px vs 1169 px (−2 %) | ENGINE (width presets) |
| hero offset above first section | ≈ 50 px larger than reference | not tuned |
| tiles/banners count and art | 3 demo categories, demo photos | DATA |
| quick-view buttons | suppressed (reference shows none) | — |

## v1 approximations — status in v2

| # | v1 approximation | v2 |
|---|---|---|
| 51 | decorative strip no longer text-only | **YES** (64 px image banner via `strip-art`; demo image) |
| 51 | blog / brand boxes closer to reference | **PARTIAL → YES for structure** (both panels reproduced in the closure pass; arrows, heading icon, card count and brand logos still differ) |
| 51 | band heights / order / patterns closer | **YES** |
| 52 | purple icon category tiles | **YES** (`icon_tiles`, no photos) |
| 52 | four coloured editorial tiles | **PARTIAL** (geometry, gap, radius, colour order, text placement matched in the closure pass; cut-out artwork and subtitle line are missing) |
| 52 | unrelated final product row removed | **YES** |
| 53 | pager closer | **YES** (closure pass) |
| 53 | image/text blocks no longer generic tan boxes | **YES** |
| 53 | invented placeholder marketing copy removed/reduced | **YES** (closure pass: testimonials now carry only the neutral labels «مشتری» / «نظر مشتری»; block placeholders are editor instructions «عنوان بخش» / «متن این بخش را از ویرایشگر وارد کنید.»; no person names or marketing sentences) |
| 53 | generic extra feature boxes removed | **YES** |
| 53 | quick-view buttons suppressed | **YES** (generic `show_quick_view` card option, set false only in 51/52/53) |

## Final closure pass (this commit)

| item | status |
|---|---|
| Template 51 blog/brand panels | **PARTIAL** (structure fixed; arrows/heading icon = ENGINE, 4 of 6 cards = DATA, brand logos = ASSET) |
| Template 52 editorial tiles | **PARTIAL** (cut-out artwork = ASSET, category subtitle = DATA) |
| Template 53 pager | **FIXED** |
| Template 53 placeholder copy | **FIXED** (neutral structural labels only) |
| Template-switch step-5 failure | **FIXED** (real defect, not an artifact — see below) |

New generic primitive in this pass: `blog_posts.style = "panel_carousel"` (written only when selected; exposed as a choice in the settings schema).
Brand panel uses the existing white colour band (no new setting).

### Step-5 root cause
Transition `stationery_spectrum → night_catalog`, category presentation `chocolate_story`, rest state, page `#070707`:
selector `section.category-chocolate-story-section > div.chocolate-section-title > h2`, foreground `#3C2B1D`, background
`#070707`, ratio 1.49:1 (need 4.5). It is a real, pre-existing defect class: `.chocolate-section-title h2` painted a fixed brown on the
**page** surface. It only appeared at step 5 because a preserved title-bearing category section (templates 52/53 carry a category title;
template 51 has none) met a dark palette. Fixed by painting the title with the page ink token (`--sfb-section-fg`, else `--ink`).
Reproduced and re-verified with only that transition (steps 1–5 replayed at service level, step 5 measured with all 11 category
presentations plus the 6 band presentations on the published page): **0 failures**.

## Contrast verification (honest status)

* Runtime `storefront-templates` audit (home, listing, product, cart; rest state) on the final code, 1440 px:
  **51 = 0 failures, 52 = 0 failures, 53 = 0 failures**. Hover/active/focus/toggle sweeps were not repeated in the closure pass
  (they passed in the previous full runs; no interactive-state CSS changed except the pager, which is not interactive on a single page).
* Deterministic tests (`test_css_token_contrast`, `test_ready_template_contrast`, `test_template_switch_contrast`, `test_section_registry`,
  `test_reference_templates_51_53`): 349 tests OK.
* Full 7-step `template-switch` suite: **not completed**. Its second run was stopped after step 3 (steps 1–3 clean); the only finding it
  had logged by step 5 is the one diagnosed and fixed above. Steps 4–7 and the final preview-vs-published token comparison were not re-run.
