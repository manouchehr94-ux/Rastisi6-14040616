# Template 51 rebuild — result against `REFERENCE_SPEC_51.md`

Source of truth: `REFERENCE_SPEC_51.md`, `forensic_51/reference_template51_full.jpg` and the 25 reference crops.
Final render: 1440 px, demo store, `forensic_51/side_by_side_template51_rebuild_03.jpg` and
`forensic_51/geometry_overlay_template51_rebuild_03.png` (iterations 01–03 are kept next to it).

Template 51 is **not claimed to be exact**; see "Remaining differences".

## Generic primitives added (no template key anywhere in their rules)

| primitive | contract |
|---|---|
| `background.mode = "surface"` | rounded card-surface panel (white by token) for any background-aware section |
| `background.bleed` | for `palette / palette_pattern / color / pattern` fills: the fill spans the viewport width while the content stays in the container (paint-only, no horizontal overflow; `body` gets `overflow-x: clip`) |
| `surface_panel` section | structural, content-free surface with `min_height` (40–600); used for blank pair rows and the blank slot row |
| `product_section.heading_style` | `default` / `plain_outline` / `underlined`; headings with a style always show the outlined «مشاهده همه» pill |
| `category_grid.min_slots` | reserved visible positions; positions without a category render as neutral empty slots (no invented category) |
| `blog_posts.min_slots` + `panel_carousel` | reserved card positions in the panel presentation |
| footer extra block `badge_slots` | N credential squares: real trust badges first, then neutral empty squares |
| footer variant `stationery_dark` | link bar (third/second footer menu, else categories), four columns (links, categories, contact, address), divider, brand + paragraph, badge row, legal row |
| header variant `stationery_search` | three layers 40 / 50 / 75 px, search pill 655 px centred, tall nav chips |
| card `center_stepper` | honours `image_ratio` (square by default) |
| `grey_circles` | product pops out of the 160 px circle |

## 20-section presence and order

All 20 sections exist, in the order of the specification (verified by `ReferenceRebuild51Tests.test_home_section_order_is_the_forensic_order`
and by the live measurement below): header, decor strip, hero + offer, category circles (6 slots), service strip (5), four tiles,
red band, amazing-offer panel, green band, blank pair row A, ochre band, blank pair row B, pair row C, **violet band**, pair row D,
blank 4-box slot row, blue band, brand panel, blog panel (6 slots), footer. Five bands use only `newest / most_viewed / discounted`
so none can disappear in a fresh store.

## Reference vs final geometry (1440 px)

| # | section | ref Y0 | ref H | final Y0 | final H | ΔH | Δ start (pp of page) |
|---|---|---|---|---|---|---|---|
| 1 | header | 0 | 163 | 0 | 166 | +2 % | 0.0 |
| 2 | decor strip | 191 | 52 | 202 | 52 | 0 % | +0.2 |
| 3 | hero + offer | 285 | 405 | 306 | 413 | +2 % | +0.3 |
| 4 | category circles | 722 | 235 | 761 | 231 | −2 % | +0.6 |
| 5 | service strip | 1013 | 67 | 1059 | 66 | −1 % | +0.7 |
| 6 | four tiles | 1133 | 323 | 1188 | 332 | +3 % | +0.8 |
| 7 | band 1 red | 1497 | 509 | 1571 | 505 | −1 % | +1.1 |
| 8 | amazing panel | 2046 | 319 | 2125 | 318 | 0 % | +1.3 |
| 9 | band 2 green | 2413 | 502 | 2501 | 505 | +1 % | +1.4 |
| 10 | blank pair A | 2957 | 256 | 3016 | 256 | 0 % | +1.1 |
| 11 | band 3 ochre | 3254 | 509 | 3323 | 505 | −1 % | +1.3 |
| 12 | blank pair B | 3809 | 237 | 3838 | 237 | 0 % | +0.8 |
| 13 | pair row C | 4100 | 485 | 4139 | 498 | +3 % | +1.0 |
| 14 | band 4 violet | 4613 | 504 | 4621 | 505 | 0 % | +0.7 |
| 15 | pair row D | 5157 | 465 | 5175 | 484 | +4 % | +0.9 |
| 16 | blank slot row | 5693 | 119 | 5629 | 119 | 0 % | −0.1 |
| 17 | band 5 blue | 5865 | 507 | 5811 | 505 | 0 % | +0.1 |
| 18 | brand panel | 6414 | 127 | 6368 | 128 | +1 % | +0.2 |
| 19 | blog panel | 6593 | 427 | 6506 | 417 | −2 % | −0.3 |
| 20 | footer | 7072 | 894 | 6999 | 860 | −4 % | 0.0 |
| — | **page** | | **7978** | | **7899** | **−1.0 %** | |

Targets: starts within ±3 % of page height (max |Δ| 1.4 pp), heights within ±8 % (max |Δ| 4 %), total height within ±8 % (−1.0 %).

| inner measurement | reference | final |
|---|---|---|
| container | 1352 (48–1400) | 1388 (26–1414), +2.7 % |
| search pill | 655 px, centred | 655 px, centred |
| nav row | 75 px | 75 px |
| hero : offer split | 75.7 : 24.3 | 75.7 : 24.3 (1036 : 332) |
| hero | 1005 × 405 | 1036 × 413 (ratio 2.51 vs 2.48) |
| category circles | 6 × Ø160 | 6 slots × Ø160 |
| service cards | ≈ 262 × 66 | 270 × 66 |
| tiles | 323 × 323, gutter 20 | 332 × 332, gutter 20 |
| band card | 205 × ≈ 380 | 210 × 368 (width +2 %, height −3 %) |
| blank panels | 256 / 237 / 119 | 256 / 237 / 119 |
| footer layers | bar 78 · columns 440 · brand ≈ 190 · badges 82 · bottom | bar 73 · columns 440 · brand 169 · badges 105 · bottom 56 |

## Remaining differences (classification: DATA / ENGINE / ASSET / INTENTIONAL)

| severity | difference | class |
|---|---|---|
| CRITICAL | none | — |
| MAJOR | header navigation row: the reference shows ≈ 4 menu links with the two chips next to them; the render shows the Store's 12 category links with the chips at the far end | DATA (merchant menu / 13 categories) + ENGINE (no nav item limit) |
| MINOR | decor strip shows the demo banner photo instead of the illustrated line | ASSET |
| MINOR | hero artwork, tile artwork (no discount badge / mini CTA chip on tiles), category cut-out photos (rectangular photos pop out of the circle) | ASSET |
| MINOR | band card CTA rows: the demo products without an add-to-cart state show the options pill / nothing instead of the reference's mix of pills and steppers | DATA |
| MINOR | blog panel: 4 posts (2 neutral empty slots), no side arrows, no heading icon | DATA / ENGINE |
| MINOR | brand panel shows brand-name tiles (reference body is empty), no icon at the title | DATA |
| MINOR | footer: link bar 3 items (categories) vs 5, fewer links per column, one-line paragraph vs 4 lines, blank white badge squares vs certification artwork, no social icons; height −4 % | DATA / ASSET |
| MINOR | service strip icons smaller than the reference's | ENGINE |
| MINOR | heading ink on the red/green bands is dark (derived accessible foreground); the reference prints white | INTENTIONAL (contrast) |
| MINOR | container 1388 vs 1352 (+2.7 %): the site content-width choices are 1100 / 1200 / 1320 / 1500 | ENGINE |

Mismatch count: **0 CRITICAL, 1 MAJOR, 10 MINOR.**

## Contrast (Template 51 only)

`tools/contrast_audit/run_audit.py --suite storefront-templates --only "stationery_spectrum:" --viewport 1440x900`
(home, listing, product, cart; rest, hover, active, focus, toggles): **1958 measurements, 0 failures, 0 focus failures.**
