# Forensic visual specification — Reference A / Template 51 (`stationery_spectrum`)

Status: **measurement document only. No production code was changed.** The owner's judgment ("no visual similarity") overrides every
earlier "matched / close" statement in `DIFFERENCE_REPORT.md`; where that report disagrees with this file, this file wins.

Evidence folder: `docs/qa_evidence/ready_templates_51_53/forensic_51/`

| file | content |
|---|---|
| `reference_template51_full.jpg` | the supplied Reference A, resampled to a 1440 px wide page (7978 px tall) |
| `reference_crops/51-01 … 51-25-*.jpg` | 25 numbered zone crops of the reference (one per visual zone, Y ranges in the tables below) |
| `current_template51_full.jpg` | current Template 51 rendered at 1440 × 6797 (public home, demo store `rasti-mode-demo`) |
| `side_by_side_template51_current.jpg` | REFERENCE (left) \| CURRENT RASTISI RENDER (right), same scale, yellow ticks every 500 px |
| `geometry_overlay_template51.png` | both pages with the 20 section boxes outlined and connected (missing sections marked) |

## 0. Method and measurement precision

* Source image: `1.jpg`, **361 × 2000 px**, RGB. Normalisation factor to a 1440 px page = **3.989**. All Y/X values below are in that
  normalised 1440-px page. One source pixel = ~4 normalised px, so every value is **±4 px**, and text smaller than ~12 px normalised is
  not legible (it is recorded as a text *block*, not read).
* Section boundaries were found from row/column colour profiles of the pixels (`numpy`), then every zone was inspected as a ruled crop.
* The effective viewport width is assumed to be 1440 px (the only width at which the capture reproduces a ~1360 px container); the
  current render was captured at exactly 1440 px.
* Product photography, merchant brand logos and illustration art are content; geometry, colour, density and structure are not.

## 1. Global metrics of the reference

| metric | value |
|---|---|
| page background | `#F4F5F9` (244,245,249) |
| header / panel / card surface | `#FFFFFF`; nav row `#F7F7F7` |
| content container | **x 48 → 1400 (≈ 1352 px, 93.9 % of the page)**; panels with shadow reach x 44 → 1404 |
| outer margin | 48 px left, 40 px right (≈ 3 %) |
| 4-column grid | column ≈ 323 px, gutter ≈ 20 px (hero = 3 cols, offer card = 1 col, tiles = 4 × 1 col) |
| 6-column product grid | card ≈ 205 px, pitch ≈ 227 px, gutter ≈ 22 px |
| 2-column pair grid | panels ≈ 674 px each, gutter ≈ 20 px (x 718 → 738) |
| corner radii | panels 12–14 px, cards 8 px, tiles 12 px, pills fully rounded |
| band colours | red `#ED3A4E`, green `#17BB5E`, ochre `#BD6A02`, violet `#301B93`, blue `#02579B` (full-bleed, 0 → 1440) |
| footer | `#4B4B53` (75,75,83), full-bleed |
| hero art colour | `#FE0000` with a lighter radial centre |
| action green (CTA/stepper cart square) | ≈ `#28A745`-family green |
| page height | **7978 px** (last ~12 px is a black capture strip) |

## 2. Reference section map

Y values are normalised page pixels. “Blank” = a white panel that contains no content in the capture (lazy-loaded area).

| # | Y start | Y end | Height | Background | Container width | Columns / items | Structure | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 163 | 163 | white; nav row `#F7F7F7` | full-bleed bar, content 40–1400 | 3 layers | utility strip 0–40, logo/search row 40–88, nav row 88–163 | see §3 |
| 2 | 191 | 243 | 52 | white panel on page bg | x 12 → 1412 (≈ 1400) | 1 | centred green store line, illustrated stationery art at both ends | gap above 28 px, below 42 px |
| 3 | 285 | 690 | 405 | hero red; offer card white | 48–1400 | 2 (3 : 1 cols) | hero 56–1061 (1005 × 405, ratio 2.48) + offer card 1077–1400 (323 × 405) | see §4 |
| 4 | 722 | 957 | 235 | page bg | 48–1400 | **6** | grey circles Ø≈160 (`#E6E7EB`) with the product photo overlapping the circle, bold label 13 px under each, item pitch ≈ 225 | no section title |
| 5 | 1013 | 1080 | 67 | white cards | 48–1400 | **5** | 5 white rounded cards ≈ 262 × 66, gutter ≈ 10, 28 px outline icon at the end + 2-line 11 px text | no section title |
| 6 | 1133 | 1456 | 323 | tile photos: lavender `#B09EEF`, pale-yellow `#FEF0BE`, grey `#E1E1E1`, amber `#FFBE12` | 48–1400 | **4** | tiles 323 × 323 (ratio 1.0), gutter 20, radius 12; round red badge Ø≈48 top corner, black+white mini CTA chip and bold 18 px title at the bottom end | x: 48–371, 391–714, 734–1057, 1077–1400 |
| 7 | 1497 | 2006 | 509 | red band + doodle line icons (≈ 10 % white) | band 0–1440, cards 56–1400 | **6** | heading row, 6 product cards | see §5 |
| 8 | 2046 | 2365 | 319 | white panel, radius ≈ 14 | 56–1402 | 3 zones | image 260 × 260 at the end (x 1120–1390), centred heading + title + price + outline pill, 4-row list at the start (x 54–486) | pink accent rule on first list row |
| 9 | 2413 | 2915 | 502 | green band + pattern | 56–1400 | **6** | as band 1 | §5 |
| 10 | 2957 | 3213 | 256 | two white panels | 44–1404 (718 \| 738 gap) | 2 | **blank** (no heading, no cards) | |
| 11 | 3254 | 3763 | 509 | ochre band + pattern | 56–1400 | **6** | as band 1 | §5 |
| 12 | 3809 | 4046 | 237 | two white panels | 44–1404 | 2 | **blank** | |
| 13 | 4100 | 4585 | 485 | two white panels | 44–1404 | 2 × 3 | each panel: heading row (title + small pill + pink underline across the panel), 3 product cards ≈ 200 wide with image 130–190, 2-line title, price, CTA; chevron at the start edge | |
| 14 | 4613 | 5117 | 504 | violet band + pattern | 56–1400 | **6** | as band 1 | §5 |
| 15 | 5157 | 5622 | 465 | two white panels | 44–1404 | 2 × 3 | same as #13 | |
| 16 | 5693 | 5812 | 119 | four white boxes | 48–1400 | 4 | 323 × 119 each, gutter 20, **blank** | tile-width slots |
| 17 | 5865 | 6372 | 507 | blue band + pattern | 56–1400 | **6** | as band 1 | §5 |
| 18 | 6414 | 6541 | 127 | white panel, radius ≈ 14, shadow | 48–1404 | 1 | centred title with icon at its end and a pink underline ≈ 210 px at Y≈6476; **no brand logos visible** | |
| 19 | 6593 | 7020 | 427 | white panel, radius ≈ 14, shadow | 48–1404 | **6** | title at the end with book icon + pink underline (x 1300–1400, Y 6648–6668); 6 cards: image 180 × 180 radius 10, pink pill badge at the image start corner, 2-line 11 px title, green pill button ≈ 140 × 28; ‹ › arrows at both ends | pitch ≈ 222 |
| 20 | 7072 | 7966 | 894 | `#4B4B53` | content 48–1400 | 4 columns | see §7 | + 12 px black strip |

### Vertical rhythm (gaps between sections)
strip→hero 42 · hero→categories 32 · categories→service 56 · service→tiles 53 · tiles→band1 41 · band1→amazing 40 · amazing→band2 48 ·
band2→pairA 42 · pairA→band3 41 · band3→pairB 46 · pairB→pairC 54 · pairC→band4 28 · band4→pairD 40 · pairD→tile-slots 71 ·
slots→band5 53 · band5→brand 42 · brand→blog 52 · blog→footer 52.

## 3. Header — decomposed

| layer | Y range | height | content |
|---|---|---|---|
| utility strip | 0–40 | 40 | white; 4 small text links at the start (x 72–360), phone + e-mail at the end (x 1139–1388) |
| logo / search row | 40–88 | 48 | white; **logo** wordmark + icon at the end, x 1225–1400, Y 41–87; **search pill** x 398–1053 (**655 px wide**, centred on the page, 43 px high, `#EBEBEB`, fully rounded, magnifier icon at the start side, placeholder at the end side); **account button** red `#EF4E66`, x 53–185 (≈ 132 × 30), fully rounded, icon + label |
| divider | ≈ 85–88 | 1–2 | hairline |
| navigation row | 88–163 | 75 | **`#F7F7F7`**; from the end: hamburger + «فروشگاه» menu (x 1150–1385), ~4 text links with icons (x 880–1130), **salmon chip** x 600–834 (≈ 232 × 56, `#F98D8D`/`#FCA8A6`), **green chip** x 507–600 (≈ 93 × 56), cart icon with red badge at the far start (x ≈ 64–110); chips Y 104–160 |
| header bottom | 160–168 | — | soft shadow, then page background |

Search width is 48 % of the page; the logo, search and account button do not share a row with the nav.

## 4. Hero (Y 285 → 690)

| item | measurement |
|---|---|
| hero panel | x 56–1061 (1005 px), Y 285–690 (405 px), ratio **2.48 : 1**, radius ≈ 10 |
| offer card | x 1077–1400 (323 px), same height, white, radius ≈ 12, shadow; hero : card = **75.7 % : 24.3 %** |
| gutter | 16–20 px |
| hero art | full red field; whiteboard product at the start (x 160–380), discount round badge (white, Ø≈ 60) at x 470–540 / Y 315–375, bold 2-line headline + sub-line at the end (x 540–1000, Y 330–470), white pill CTA ≈ 140 × 30 at x 640–780 / Y 548–578 |
| tab bar | inside the hero bottom, Y 642–690 (**48 px**), 6 captions, `#6D717D` translucent, active tab darker; spans the whole hero width |
| offer card content | heading «پیشنهادهای لحظه‌ای …» Y 300–320 centred; red discount badge x 1090–1130 / Y 360–385; product image centred ≈ 165 px high (Y 355–520); 1-line name Y ≈ 575; price block Y 610–645 |
| relationship | hero and card touch the container edges (56 / 1400); 42 px of page background above, 32 px below |

## 5. Product bands — one by one

All five bands are full-bleed colour fields with a white doodle-icon pattern (≈ 10 % opacity, stationery line icons, different arrangement per band),
**509 / 502 / 509 / 504 / 507 px** tall (identical within measurement error), inner content x 56–1400. They are separated by pair rows, not placed back to back.

Common structure (measured on bands 1, 2, 3, 5; band 4 inspected on the ruled crop):
* heading row: title at the **end edge** (≈ 18 px bold white, small icon after it), outline pill «مشاهده همه» (white outline, ≈ 97 × 28) immediately before the title; heading Y = band top + 43 … + 93.
* cards start at band top + **93–104**, bottom ≈ band bottom − 25…32.
* **6 white cards**, width ≈ 205, pitch ≈ 227 (gutter ≈ 22), height **≈ 375–385** (aspect 0.53), radius 8, no visible border.
* card interior: square image zone ≈ 190 × 190 (10 px inset, object-contain), 2-line dark title 12 px, centred bold price 13 px, CTA row 28–36 px.
* a ‹ chevron sits on the start edge over the first card; carousel arrows are visible only at that edge.

| band | order | colour | Y | height | cards | CTA row variants | notes |
|---|---|---|---|---|---|---|---|
| 1 | 7 | red `#ED3A4E` | 1497–2006 | 509 | 6 | cards 1 and 4: wide green pill; cards 2, 3, 5, 6: green cart square + stepper `− 1 +` | heading pill white outline |
| 2 | 9 | green `#17BB5E` | 2413–2915 | 502 | 6 | all six: cart square + stepper | cards start +93 |
| 3 | 11 | ochre `#BD6A02` | 3254–3763 | 509 | 6 | all six: cart square + stepper | image zone has photos with own backgrounds |
| 4 | 14 | violet `#301B93` | 4613–5117 | 504 | 6 | cart square + stepper | cards start +98 |
| 5 | 17 | blue `#02579B` | 5865–6372 | 507 | 6 | cart square + stepper | cards start +95 |

## 6. Lower half (below the last tile row)

Order after band 3: blank pair row B → pair row C (content) → **violet band 4** → pair row D (content) → blank 4-box slot row → **blue band 5** →
brand panel → blog panel → footer. Details of every block are in the table of §2 (rows 12–19). Nothing in the reference lower half is a plain
“product grid on page background”; every non-band block is a **white rounded surface panel** (radius 12–14, soft shadow).

## 7. Footer (Y 7072 → 7966, 894 px, `#4B4B53`)

| zone | Y | content |
|---|---|---|
| link bar | 7072–7150 | 5 text links spread across the width (x ≈ 1340, 1000, 700, 500, 150); hairline divider at ≈ 7140 |
| columns | 7150–7590 | **4 columns** (end → start): service links (heading + ≈ 7 links), quick access (heading + 5 links), contact (heading, phone, e-mail, hours), store address (heading + 4-line address) |
| divider | 7590–7598 | full-width hairline |
| brand + paragraph | 7600–7790 | wordmark logo with tagline at the end (x 1195–1400, Y 7610–7665); justified paragraph 3–4 lines (Y 7680–7745) across the full width; divider ≈ 7790 |
| badges | 7798–7880 | **5 white rounded squares ≈ 62 × 62** centred (cluster ≈ 480 px wide) with certification art |
| bottom bar | 7930–7966 | copyright text at the end, 3 social icons + credit text at the start; final 12 px black strip (capture edge) |

## 8. Current render (Template 51 at HEAD `afa6617`)

* viewport 1440, page **6797 px** tall, container x 26 → 1414 (**1388 px**), demo store `rasti-mode-demo`.
* header 0–165: search pill **x 211–1224 (1013 px)** beside the account pill, logo x 1242–1414, nav row 109–165 with 12 category links + 2 green chips.
* strip banner 64 px tall (photo collage), hero 271–685 (1039 × 414), 3 category circles (data), 5 compact service boxes (270 × 44),
  4 tiles 340 × 336 with a 10 px gutter, bands at 1369 / 2195 / 3190 / 5117 (**four** bands), amazing-offer 286 px, brand panel 177 px,
  blog panel 379 px (4 cards), footer 501 px.
* band cards 221 × 441 (image zone 219 × 263), pitch 229.5.

## 9. Geometry deltas (reference → current)

Y values in page pixels; “pp” = difference of the section's relative position in its own page (start Y ÷ page height).

| # | section | ref Y0 | ref Y1 | ref H | cur Y0 | cur Y1 | cur H | ΔY0 | ΔH | Δ relative start |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | header | 0 | 163 | 163 | 0 | 165 | 165 | +0 | +2 (+1 %) | +0.0 pp |
| 2 | decor strip banner | 191 | 243 | 52 | 181 | 245 | 64 | -10 | +12 (+23 %) | +0.3 pp |
| 3 | hero + offer card | 285 | 690 | 405 | 271 | 685 | 414 | -14 | +9 (+2 %) | +0.4 pp |
| 4 | category circles | 722 | 957 | 235 | 703 | 918 | 215 | -19 | -20 (-9 %) | +1.3 pp |
| 5 | service strip | 1013 | 1080 | 67 | 929 | 997 | 68 | -84 | +1 (+1 %) | +1.0 pp |
| 6 | four tiles | 1133 | 1456 | 323 | 1015 | 1351 | 336 | -118 | +13 (+4 %) | +0.7 pp |
| 7 | band 1 red | 1497 | 2006 | 509 | 1369 | 1888 | 519 | -128 | +10 (+2 %) | +1.4 pp |
| 8 | amazing-offer panel | 2046 | 2365 | 319 | 1898 | 2184 | 286 | -148 | -33 (-10 %) | +2.3 pp |
| 9 | band 2 green | 2413 | 2915 | 502 | 2195 | 2714 | 519 | -218 | +17 (+3 %) | +2.0 pp |
| 10 | pair row A (blank panels) | 2957 | 3213 | 256 | 2724 | 3180 | 456 | -233 | +200 (+78 %) | +3.0 pp |
| 11 | band 3 ochre | 3254 | 3763 | 509 | 3190 | 3709 | 519 | -64 | +10 (+2 %) | +6.1 pp |
| 12 | pair row B (blank panels) | 3809 | 4046 | 237 | 3719 | 4175 | 456 | -90 | +219 (+92 %) | +7.0 pp |
| 13 | pair row C | 4100 | 4585 | 485 | 4185 | 4641 | 456 | +85 | -29 (-6 %) | +10.2 pp |
| 14 | band 4 violet | 4613 | 5117 | 504 | — | — | — | — | **MISSING** | — |
| 15 | pair row D | 5157 | 5622 | 465 | 4651 | 5107 | 456 | -506 | -9 (-2 %) | +3.8 pp |
| 16 | tile-slot row (blank) | 5693 | 5812 | 119 | — | — | — | — | **MISSING** | — |
| 17 | band 5 blue | 5865 | 6372 | 507 | 5117 | 5636 | 519 | -748 | +12 (+2 %) | +1.8 pp |
| 18 | brand panel | 6414 | 6541 | 127 | 5646 | 5823 | 177 | -768 | +50 (+39 %) | +2.7 pp |
| 19 | blog panel | 6593 | 7020 | 427 | 5833 | 6212 | 379 | -760 | -48 (-11 %) | +3.2 pp |
| 20 | footer | 7072 | 7966 | 894 | 6256 | 6757 | 501 | -816 | -393 (-44 %) | +3.4 pp |
| — | **page** | | | **7978** | | | **6797** | | **-1181 (-14.8 %)** | |

Inner-geometry deltas:

| item | reference | current | delta |
|---|---|---|---|
| container width | 1352 (48–1400) | 1388 (26–1414) | +36 px (+2.7 %) |
| header search pill | 655 × 43, centred | 1013 × 42, x 211–1224, off-centre | +358 px (+55 %) |
| nav row | 75 px, `#F7F7F7`, ≈ 6 items + 2 chips | 56 px, 12 links + 2 chips | −19 px (−25 %) |
| strip banner | 1400 × 52 panel | 1388 × 64 image | +12 px |
| hero | 1005 × 405 (2.48) | 1039 × 414 (2.51) | ratio +1 % |
| hero : offer split | 75.7 : 24.3 | 75.3 : 24.7 | within ±5 % |
| tile | 323 × 323, gutter 20 | 340 × 336, gutter 10 | width +5 %, height +4 %, gutter −50 % |
| service card | ≈ 262 × 66, gutter 10 | 270 × 44, gutter 9 | height −33 % |
| band card | 205 × ≈ 380 (0.54) | 221 × 441 (0.50) | width +8 %, height +16 % |
| band image zone | ≈ 190 × 190 (square) | 219 × 263 (portrait 1.2) | aspect +30 % |
| category circles shown | 6 | 3 | −3 (data) |
| footer columns | 4 + link bar + paragraph + 5 badges | 3 columns + service strip + identity row | −393 px |

## 10. Mismatch table

Severity: CRITICAL = composition visibly different; MAJOR = a block is visibly different; MINOR = small deviation.

| Area | Reference | Current render | Severity | Root cause |
|---|---|---|---|---|
| Violet band 4 | present (4613–5117) | absent (its product source returns nothing in the demo store, so the section is hidden) | **CRITICAL** | missing section (recipe depends on a data source that can be empty) |
| Section order lower half | pairC → band4 → pairD → slots → band5 | pairC → pairD → band5 | **CRITICAL** | wrong section / missing section |
| Blank pair rows A, B | two blank white panels, 256 / 237 px | filled 456 px product rails | **CRITICAL** | wrong content density (reference shows lazy-load gaps; owner decision needed) |
| Blank 4-slot row | 4 blank boxes 323 × 119 | absent | MAJOR | missing section |
| Footer | 894 px, 4 columns, link bar, paragraph, badges row, bottom bar | 501 px, 3 columns, strip, identity row | **CRITICAL** | wrong header/footer variant (layers missing), data limitation for badges/paragraph |
| Header search + account | pill 655 centred, account pill at the far start | pill 1013 beside account | MAJOR | wrong geometry |
| Header nav | 75 px grey row, ≈ 6 items, salmon + green chips | 56 px row, 12 links | MAJOR | wrong geometry / data (category count) |
| Decor strip | white 52 px panel, centred line + art | 64 px image collage | MAJOR | wrong geometry; art = asset limitation |
| Category circles | 6, 225 pitch, products overlapping the circle | 3, products inside the circle | MAJOR | data limitation (3 categories) + wrong component variant (pop-out image) |
| Service strip | 5 cards 262 × 66 | 5 boxes 270 × 44 | MINOR | wrong geometry |
| Tiles | 323 × 323, gutter 20, bottom-end title, mini CTA chip | 340 × 336, gutter 10, title overlay | MINOR | wrong geometry; photos = asset |
| Hero + offer | 1005 × 405 + 323 card | 1039 × 414 + 340 card | MINOR | geometry within ±5 %; art = asset |
| Hero tab bar | 48 px, 6 captions | 48 px, captions | MINOR | — |
| Product bands (heights) | 502–509 | 519 | MINOR | wrong geometry (+2–3 %) |
| Band card | 205 × 380, square image zone | 221 × 441, portrait image | MAJOR | wrong geometry (card image ratio / padding) |
| Band heading row | plain title + white-outline pill, 93 px row | capsule chip heading | MAJOR | wrong component variant |
| Band pattern | white doodle icons ≈ 10 % | doodle pattern present, different density | MINOR | asset/pattern limitation |
| Amazing-offer panel | 319 px: 260 × 260 image + text + list | 286 px; the image zone exists but the photo is a washed-out white ghost, so the end third looks blank | MAJOR | wrong geometry / wrong content density |
| Pair rows C, D | 2 panels, heading + small pill + pink underline ≈ 300–390 px wide, 3 cards each (485 / 465 px) | 2 panels, 3 cards each, heading with a short (≈ 80 px) red underline, no pill (456 px) | MINOR | wrong component variant (heading detail) |
| Brand panel | 127 px, centred title + underline, empty body | 177 px, brand-name tiles | MINOR | wrong content density (data) |
| Blog panel | 427 px, 6 cards, arrows, icon | 379 px, 4 cards, no arrows | MAJOR | data limitation (4 posts) + missing engine primitive (arrows) |
| Container | 1352 | 1388 | MINOR | wrong geometry |
| Total page height | 7978 | 6797 (−14.8 %) | **CRITICAL** | missing sections + footer |

Counts: 5 CRITICAL, 9 MAJOR, 9 MINOR rows. 10 of the 20 mapped sections carry a CRITICAL or MAJOR structural finding (50 %: strip, categories, amazing panel, pair rows A and B, band 4, pair row D order, slot row, blog, footer); the four present bands additionally carry a MAJOR card-geometry finding.

## 11. Decision

**B. REBUILD TEMPLATE 51 COMPOSITION.**
More than 30 % of the section structure is wrong (10 of 20 sections, plus card geometry in every band), the lower-half order is wrong, and the missing/blank rows cannot be fixed by
adjusting spacing. Header, hero, offer card, tiles and band shells can be reused as components; the page composition, the pair/panel rows, the
band card geometry, the footer and the data-source choices must be re-authored against this specification.

## 12. Engine gap report

| # | reference structure | nearest current primitive | why insufficient | smallest generic primitive |
|---|---|---|---|---|
| 1 | white rounded **surface panel** (radius 12–14, shadow) around any section: pair rows, amazing panel, brand panel, blog panel, slot boxes | white colour band (`background.mode = color #FFFFFF`) + CSS keyed to the brand carousel; `blog_posts panel_carousel` special-case | not available to arbitrary sections; radius/shadow/padding differ per case; no min-height | background mode `surface` (token surface, radius, shadow, padding) usable by every background-aware section |
| 2 | **blank/skeleton panel** (white panel with reserved height, no content) | none (empty sections are hidden) | engine hides empty sections by design | optional `min_height` on the surface panel; whether to reproduce a blank area at all is an owner decision |
| 3 | section heading **plain title + outline “see all” pill (+ icon) and a pink accent underline under the heading block** | capsule chip heading (`.rsec[data-pattern]` rule) and `sec-head` with a short underline | one fixed look per context; no outline-pill / wide-underline variant | `heading_style` option for product/blog/brand sections: `capsule \| plain_outline \| underlined` |
| 4 | **product card with square image zone and fixed CTA row** (cart square + stepper, or full pill) at 205 × 380 | `center_stepper` card | image ratio follows the product photo (portrait), card height 441 | `card.image_ratio` honoured by `center_stepper` + card padding tokens (settings, not a new component) |
| 5 | **category circle with pop-out product image** | `grey_circles` (image clipped inside the circle) | product cannot overflow the circle | `media_style: popout` flag on the circle presentation |
| 6 | **amazing-offer panel** with a 260 × 260 image zone, 4-row list | `amazing_offers` | image zone exists but renders as a pale ghost and the panel is 33 px shorter | image-zone sizing/contrast option on the block (or a verified fix) |
| 7 | **carousel arrows / heading icon** on a blog row | static `.blog-panel-row` | no arrows; icons absent | blog `display_mode: carousel` reusing the existing carousel arrows |
| 8 | **footer**: link bar, 4 columns, paragraph, badge row, bottom bar | `stationery_dark` | link bar only via a merchant text block; badge row needs uploaded badges; 3 columns | footer region options: `link_bar` from nav items; column count 4 |
| 9 | nav row `#F7F7F7` with chip links and **centred 655 px search** | `stationery_search` | search flexes to fill the row | header setting `search_max_width` |
| 10 | strip banner as a 52 px white panel with centred line | `multi_banner strip-art` | image only, 64 px | none (asset) — a height token only |
| 11 | sections whose data source is empty must still hold place | hidden when empty | band 4 disappeared | none required; recipe must pick sources that exist, or the owner accepts hidden sections |

## 13. Acceptance targets for the next implementation phase

Geometry targets, not pixel identity (merchant-specific photography and brand logos excluded):

1. **Section order identical** to §2 rows 1–20 (blank rows are included unless the owner decides they are dropped, which must be recorded).
2. **Visible column counts identical:** categories 6, service 5, tiles 4, bands 6 cards each, pair panels 2 × 3, slots 4, blog 6, footer 4 columns + 5 badges.
3. **Section start positions** within ±3 % of the page height (±240 px at 7978 px).
4. **Section heights** within ±8 % (bands 502–509 → 470–550; hero 405 → 373–437; footer 894 → 822–966).
5. **Container width** 1352 ± 3 % (1311–1393 px); outer margins 48 / 40 ± 12.
6. **Hero split** 75.7 : 24.3 ± 5 %; hero ratio 2.48 ± 5 %.
7. **Card aspect ratios** ± 5 %: band card 0.54, tile 1.0, offer card 0.80, blog image 1.0, circle 1.0.
8. **Total page height** 7978 ± 8 % (7340–8616) **excluding missing merchant content** (list the excluded items explicitly).
9. Dominant section colours visually equivalent (token mapping of the five band colours + footer `#4B4B53`, page `#F4F5F9`).
10. **No invented sections, no omitted visible sections** — the 20 rows of §2 are the complete list.
11. Header decomposed into the three layers of §3 with search 655 ± 5 % and nav row 75 ± 8 %.
12. Contrast and tenant-isolation rules from the contrast branch stay in force.
