# Template 51 — engine stabilization (implementation report)

Scope: the approved diagnostic of the Template 51 gate. Engine only; Templates 52/53 were not touched; nothing is pushed.
Visual evidence (this folder, `engine_stabilization/`): `preview_vs_published_51.jpg` (PARITY), `reference_vs_template51_after_engine_fix.jpg`
(FIDELITY), `template51_published_1440.jpg`, `template51_studio_preview_1440.jpg`.

## 1. Root causes fixed

| defect (diagnostic) | fix |
|---|---|
| 5 px horizontal page scroll with classic scrollbars (`100vw` bleed pseudo-element) | bleed is a real `.rsec-bleed` layer bounded by the storefront canvas (`main.sfb-storefront-canvas{overflow-x:clip}`); `body{overflow-x:clip}` removed |
| Preview geometry ≠ Published (cells `display:flex`, container margin/padding/border, add-buttons and empty-section placeholders in flow) | builder chrome is outline / absolute overlay only; the preview-only `[data-height-mode="equal"]` flex rule is gone |
| pair-panel native scroll rails | product-row presentation contract (`desktop_layout`, `overflow_mode`, `show_scrollbar`, `carousel_navigation`, `desktop_columns`, `gap`); pair panels are a 3-card non-scrolling grid |
| thin strip = abused `multi_banner strip-art` (52 px literal) | generic `decorative_strip` primitive; `strip-art` variant and its CSS deleted |
| empty circles although the store has categories | `category_source` (`top_level` default, `leaf`, `all`, `top_then_descendants`); Template 51 uses `top_then_descendants` |
| header overflow at 1024 (side grid columns `1fr` narrower than the account chips) | `minmax(max-content,1fr)` side tracks, search shrinks instead |
| Studio "jump" | atomic preview refresh (below) |
| Studio and public ran different stylesheet URLs (`?v=u2b-footer-v3-…` pinned in preview, none on public) | `sfb_static` (`?v=<mtime>`) on every storefront stylesheet of both surfaces |
| edit-mode chrome re-positioned storefront elements (`[data-admin-edit-kind]{position:relative!important}` broke the absolute hero slides, `header{position:relative}` broke the sticky header) | zero-specificity `:where()` positioning hook |

Deliberate deviation from the brief: the canvas boundary is `overflow-x:clip` on the canvas element, not `container-type:inline-size` + `cqw`.
Layout containment makes the element the containing block of `position:fixed` descendants; the quick-view dialog (inside every product card) and
the PDP mobile add-to-cart bar are fixed descendants of `<main>`. `overflow:clip` creates neither a scroll container nor a containing block.
The clip cannot hide a real defect: the parity test lifts the clip and the bleed layers and still requires `scrollWidth == clientWidth`.

## 2. Architecture

* `semantic_colors.py` — merchant colours are `""` | `token:<palette role>` | `#RRGGBB` (never free CSS); tokens resolve to the appearance variables
  (`--brand-*`, `--theme-*`) with their accessible `*-fg` pair; hex gets `best_foreground`.
* `design_block.py` — the sparse `settings.design` block; ONE registry (`DESIGN_PROPERTIES` / `DESIGN_APPLICABLE`) drives validator, Inspector controls and
  renderer (`data-d` flags + `--d-*` custom properties). Consumers are generic CSS keyed on the flags.
* `shell_geometry.py` — sparse `geometry` block of header/footer config (per variant applicability), rendered as `--gh-*` / `--gf-*`.
* `decorative_strip.py` + `sections/decorative_strip.html` — view model of the new primitive (heights per breakpoint, solid/palette/image/pattern fill,
  image fit/position/repeat, overlay, radius, border, shadow, bleed, alignment, text, per-device visibility).
* `services/category_selection.py` — deterministic Store-scoped selection.
* Inspector: new field types `color` (palette role / custom / automatic), `design` (registry-generated), `media` (Store media picker);
  Global Design panel gets geometry + colour controls for the selected header/footer variant.
* Editor refresh path **was changed** (see §5).

## 3. Measurements (Chromium, classic 10 px scrollbars)

Document horizontal overflow, Published / Preview / Design Studio iframe (1440):

| width | scrollWidth − clientWidth | overflow audit with clip + bleed lifted | Preview vs Published |
|---|---|---|---|
| 1440 | 0 / 0 / 0 | 0 offenders | 0 violations |
| 1024 | 0 / 0 | 0 offenders | 0 violations |
| 768 | 0 / 0 | 0 offenders | 0 violations |
| 390 | 0 / 0 | 0 offenders | 0 violations |

(Before: +5 px at every width, +87 px in Preview at 1024.) Parity compares section order, x, y, width (≤1 px), height (≤2 px), document height,
header/footer rects and the full token set; Rasti Mode Demo full-page 1440 screenshots are both 1440 × 7956 and differ in 0.037 % of pixels
(staff header buttons and the live countdown). `horizontal scroll range` is 0 (`scrollTo(±600,0)` does not move).

Internal boundaries, Rasti Mode Demo 1440 (reference → render):

| zone | reference | render |
|---|---|---|
| utility strip / nav row | 40 / 75 | 41 / 75 |
| search pill | 655 × 43 | 655 × 43 |
| chips | 232 × 56, 93 × 56 | 230 × 56, 127 × 56 |
| hero : offer | 75.7 : 24.3 (1005 × 405) | 75.7 : 24.3 (1036 × 413) |
| band heights | 509 / 502 / 509 / 504 / 507 | 505 ×5 |
| band card top offset / card / pitch | 93–104 / 205 × 375–385 / 227 | 100 / 210 × 368 / 232 |
| pair panels C / D | 485 / 465 | 498 / 484 |
| brand / blog | 127 / 427 | 128 / 419 |
| footer: link bar / columns / brand+paragraph / badge row / badge | 78 / 440 / ≈190 / 82 / 62 | 78 / 440 / 189 / 83 / 62 |
| footer legal row | 36 | 56 |
| page | 7978 | 7956 |

## 4. Design Studio control matrix (✓ = an Inspector control exists and the renderer consumes it)

| property | surface_panel | product_section | decorative_strip | category_grid | brand_carousel | blog_posts | amazing_offers |
|---|---|---|---|---|---|---|---|
| background mode | — | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| background colour | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| text / foreground colour | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| accent colour | — | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| border colour | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| border width | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| radius | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| shadow on/off + colour + blur | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| padding | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| margin | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| min height | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| columns (desktop/tablet/mobile) | — | ✓ | — | ✓ | — | ✓ | — |
| gap | — | ✓ | — | ✓ | ✓ | ✓ | — |
| alignment | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| heading style | — | ✓ | — | — | — | ✓ | — |
| heading colour | — | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| image ratio | — | ✓ | — | — | — | ✓ | — |
| image fit / position | — | ✓ | ✓ | ✓ | — | ✓ | — |
| item / card width | — | ✓ | — | ✓ | ✓ | — | — |
| price colour | — | ✓ | — | — | — | — | — |
| button fill / text / border | — | ✓ | — | — | — | ✓ | ✓ |
| overflow mode | — | ✓ | — | — | — | — | — |
| scrollbar visibility | — | ✓ | — | — | — | — | — |
| carousel navigation | — | ✓ | — | — | — | — | — |
| desktop layout (grid ↔ carousel) | — | ✓ | — | — | — | — | — |
| full bleed | — | ✓ | ✓ | ✓ | ✓ | — | ✓ |
| responsive visibility | — | — | ✓ | — | — | — | — |

Header (`stationery_search`): utility/main/nav height, search max width + height, row gap, nav gap, nav item limit, chip count / radius / paddings /
fill / alt fill / text colour. Footer (`stationery_dark`): link-bar height, columns block min height, column count + gap, divider and brand spacing,
badge size / gap / row padding / fill, legal-row height. Controls are offered only for properties the selected variant draws.
Legacy header/footer forms carry the stored geometry through untouched.

## 5. Jump / editor refresh

Cause (measured): every mutation reloaded the visible iframe; during the reload the visible document was half-parsed (17 of 26 sections, 5 651 px →
8 579 px). New behaviour (`runPreviewRefresh`): a transparent twin iframe loads the canonical preview, waits for load + fonts + the images near the
restored viewport (≤2.5 s), restores scroll by the topmost section's **stable id and its own viewport offset**, then swaps atomically. Concurrent
refreshes coalesce. Measured in the real Studio: the visible frame is always `complete` with 26/26 sections, one visible frame at any time, anchor
section top 23 px → 23 px, refresh 0.44 s. No transitions are used to mask anything.

## 6. Colourability

Tokenised: category circle and reserved-slot fill, footer ink / muted / border / accent / badge fill, band-heading ink, header chip fill and text,
blog action pill, brand/blog/heading underline (`--d-accent` → `--pink` = `--brand-accent`), surface shadow colour, bleed fill. The five band colours
remain recipe defaults through palette roles (`palette_role`), editable per section.

Remaining hard-coded colours that affect Template 51 — shared legacy engine components, not Template-51 rules (128 matching rules found by a
computed-rule scan of the rendered page): `.pcard` surface / name / price / stepper ink (`product_card.css`), hero text / CTA / arrows / tabs
(`home.css`, `storefront_builder.css`), the offer-card spotlight (`.product-spotlight-*`), amazing-offer panel (`.special-*`), brand tile, service
strip (`.feat`), promo overlay, blog card, a few shadows. They are verified pairs (light surface + dark ink) and were not changed in this pass;
making them palette-driven needs a pair-aware pass per component and is the next colourability step.

## 7. Remaining fidelity differences (Template 51)

Nav chips are content-sized (127 vs 93 px green chip); band card height −3 %; pair panels +3–4 %; footer legal row 56 vs 36; container 1388 vs 1352
(content-width presets); hero/tile artwork, demo photos and brand logos are assets/data. Heading ink on the red/green bands remains the derived
accessible dark ink (reference prints white) — intentional.

## Final verification (post focus-ring fix)

- Template 51 contrast audit (1440×900, 1923 measurements): 0 text failures, 0 focus-indicator failures. The one earlier focus failure
  (plain-outline "مشاهده همه" pill over a coloured band) is fixed generically: headings on colour/pattern bands use the band's accessible
  foreground (`--sfb-section-fg`) for the focus ring.
- Focused suites: storefront_builder + affected catalog/cart/core suites (802 tests) green after fixing one stale expectation in
  `test_engine_stabilization` (design hide flags); `test_engine_stabilization` + `apps.core.tests.test_css_token_contrast`: 101 OK;
  opt-in browser parity/overflow tests (`SFB_BROWSER_TESTS=1`): 7 OK.
- `manage.py check` clean; `makemigrations --check`: no changes; `git diff --check` clean.
- Pre-existing failure on clean HEAD (unrelated): `test_validate_appearance_config_is_the_validator_boundary`.
