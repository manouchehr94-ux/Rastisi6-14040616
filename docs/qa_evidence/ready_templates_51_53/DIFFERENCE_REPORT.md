# Ready Templates 51 / 52 / 53 — fidelity QA (local, unpushed)

Visual source of truth: the three supplied screenshots only (A = 51 `stationery_spectrum`,
B = 52 `magenta_beauty_retail`, C = 53 `pastel_kawaii_stationery`).
Each reference was normalised to a 1440 px page width; each template was rendered through the real
storefront (apply → publish → public home) at 1440 px on a seeded demo store.
Side-by-side images (REFERENCE | RASTISI RENDER, same effective width): `side_by_side_template5x_NN.jpg`.

Demo products/categories/banners are the seeded demo store's own media (fashion photos), so *content imagery* always
differs from the references; this report compares **structure and geometry**. No marketing copy, quick-view buttons,
CTAs, badges or feature boxes were added that the reference does not show.

## Page-level numbers

| | reference (normalised 1440) | render | note |
|---|---|---|---|
| 51 page height | 7978 | ≈6630 | footer is data-dependent (see below) |
| 52 page height | 5571 | ≈4263 | footer/recently-viewed panel |
| 53 page height | 15484 | ≈14492 | reference content column 132–1301 (1169 px) vs 146–1294 (1148 px) |

## Template 51 — `stationery_spectrum` (reference A)

| section | reference geometry | rendered geometry | main mismatch | status |
|---|---|---|---|---|
| decorative strip banner | one full-width 64 px banner | one full-width 64 px banner (`strip-art`) | demo image instead of the artwork | corrected (was text-only before) |
| hero + side offer | hero ≈ 70 % / offer card ≈ 30 %, equal height, hero ratio ≈ 1.9 | 9/3 row, equal height, same ratio | slide art is demo media | corrected |
| category circles | 6 grey circles per row, pitch ≈ 1/6 of width, circle ≈ 156 px | 6-track geometry, circle 156 px, labels 13 px, row centred | demo store has only 3 categories → 3 circles shown | corrected (geometry), count is data-bound |
| service strip | 5 outlined boxes | 5 boxes (`trust_features`, compact) | icon glyphs | corrected |
| four tiles | 4 columns, tile ratio ≈ 1/0.99, title bottom, badge | `tile-4` 4 columns, same ratio | demo photos | corrected |
| coloured bands ×5 (red/green/ochre/violet/blue) | ≈511 px, doodle pattern, 6 stepper cards | 519 px, same pattern/tones, 6 `center_stepper` cards | none significant | corrected |
| amazing-offer block | wide white panel with list + image | `amazing_offers` | list density | partly (generic block) |
| white paired rails | two 50 % panels | 6/6 paired rails | the capture shows two lazy-load gaps (empty white panels); render fills the pair with the same rail component | not reproduced exactly (blank panels are not a design element) |
| brands panel / blog panel | white panels with title chip, 6 blog cards in a carousel with button | brand carousel + 5-column blog grid | blog panel wrapper and card button not reproduced | not corrected |
| footer | tall dark footer: links bar, 4 columns, paragraph, 5 badge tiles | dark footer: service strip, columns, identity, legal | badge row/paragraph need merchant data (badges are never fabricated) | not corrected (data-dependent) |

## Template 52 — `magenta_beauty_retail` (reference B)

| section | reference geometry | rendered geometry | main mismatch | status |
|---|---|---|---|---|
| header | two compact rows | 135 px beauty header | logo art | corrected |
| hero | soft pink editorial banner, text on one side, dots only | 506 px (ref ≈ 521) `beauty_editorial`, dots | demo slide image | corrected |
| category tiles | 6 purple icon tiles with labels (no photos) | `icon_tiles`: 6-track geometry, purple glyph tiles | 3 demo categories | corrected (was photo tiles) |
| magenta / mint campaign bands | ≈465 px, 4 cards + gift panel | 528 px, 4 cards + gift panel | band ≈ 13 % taller | partly (card height) |
| four coloured gradient tiles | gradient tile with text + product picture | `gradient_tiles`, 4 columns | 3 demo categories | corrected (was banner images) |
| brands strip | logo strip + button | beauty brand strip | brand logos are merchant data | corrected |
| purple wall (3 list columns) | 510 px | 472 px | — | corrected |
| two pink banners | two 50 % tiles | `wide-single`, 2 × 682 × 185 | demo banner art | corrected |
| featured row wall | purple panel + capsule heading + 5 cards | same | — | corrected |
| "recently viewed" heading + empty body | heading only | omitted | region is empty in the capture → intentionally not filled | not reproduced (by rule) |
| last product row | none (capture ends in newsletter) | none | — | corrected (previous version filled it with products) |
| newsletter / features / footer | pale panel, 4 service boxes, purple footer | same structure | footer extras are data-dependent | partly |

## Template 53 — `pastel_kawaii_stationery` (reference C)

| section | reference geometry | rendered geometry | main mismatch | status |
|---|---|---|---|---|
| header | red double bar, centred logo, search, nav row | same (`kawaii_center`) | — | corrected |
| hero | rounded poster ≈ 1:1.89 | `poster_wide`, 1148 × 607 | content column 2 % narrower | corrected |
| mini banners | 4 pastel banners | `mini-4` | demo art | corrected |
| category tiles | 6 pastel tiles | `pastel_tiles`, 6 tracks | 3 demo categories | corrected |
| product groups | 4-column, square tinted images, 12/24/16/8… rhythm | `catalog_grid` 4 columns, same counts | image content | corrected |
| pager bar | purple button, page numbers, next | real pager bar (`catalog-grid-bar-row`) | button carries the generic "view all" URL | corrected (was a simplified bar) |
| image/text blocks | plain image box + text placeholder | `image_text` plain block with placeholder structure (no invented copy) | — | corrected (was a tan box) |
| blog / testimonials | blog row; avatar grid | blog grid; avatar grid with neutral "نام مشتری" placeholders | — | corrected |
| quick-view buttons | not on cards in the capture | removed via the generic `show_quick_view` card option | — | corrected |

## Contrast verification

See the final report; summary commands are recorded in the commit messages and in `tools/contrast_audit`.
