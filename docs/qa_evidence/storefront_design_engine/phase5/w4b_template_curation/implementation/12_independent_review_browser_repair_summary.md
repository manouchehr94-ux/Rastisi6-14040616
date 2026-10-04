# P5-W4B — Independent Review Repair Round 1 — Browser QA Repair Summary

**Reviewed PR head at repair start:** `f5114d838f4509f016046c6fd537bab3e91879c4`
**Review findings addressed:** IMPORTANT 1 (missing v1-vs-v2 browser
comparison), IMPORTANT 2 (incomplete latest-v2 acceptance matrix).
IMPORTANT 3 (self-contradictory clean evidence) is addressed separately
in `13_final_clean_status_review_repair.txt`.

No production code, no Django test code, and no QA authority under
`apps/`/`tools/` changed in this repair. Both scripts below were run from
the session scratchpad (never committed) and call only the existing
canonical `preset_service.apply_preset_with_checkpoint` +
`layout_service.publish` path against the existing shared demo Store
(`rasti-mode-demo`) — the same authority `capture_ready_template_previews.py`
and the original W4B browser QA already used.

## 1. Historical (v1) vs Latest (v2) browser comparison — 21/21 PASS

**Script:** `w4b_history_qa.py` (session scratchpad). For each of the 21
curated keys: resolved `lpr.get_layout_preset_version(key, "1")` and
`lpr.get_layout_preset(key)` (asserted version `"2"`), applied+published
each through the canonical path onto the shared demo Store, and captured
Desktop 1440×900 for both.

Added-section presence was checked two independent ways per pair:

1. **Page-wide selector count** — `a.brand-tile` / `a.pcard` /
   `.story-item`. Confirmed by source inspection
   (`grep` across every template under `apps/storefront_builder/templates/`
   and `apps/catalog/templates/`) that each selector is emitted by exactly
   one section template (`brand_carousel.html`, `collection_tiles.html`,
   `story_rail.html` respectively) — `category_grid.html`'s superficially
   similar class is `category-chocolate-story-item`, a distinct token that
   does not match the CSS class selector `.story-item`; `product_card.html`
   renders `<article class="pcard...">`/`<a class="pcard-hitarea">`, never
   `<a class="pcard">`. So an unscoped page-wide count cannot be confused
   with any other section.
2. **Positional cross-check** — every `.rsec` wrapper
   (`responsive_section_wrapper.html`) is emitted exactly once per Home
   composition item, in document order, so the `.rsec` NodeList index
   equals the composition index. The added section's expected index was
   read directly from `test_w4b_template_curation.EXPECTED_NEW_HOME_SEQUENCE`
   / `EXPECTED_ADDED_SECTION` (already-green contract test source, not
   re-derived), and the matching selector was queried scoped to
   `rsecs[idx]` only.

### Result (`browser_qa_history/summary.json`, 21 entries)

| Check | Result |
|---|---|
| Historical (v1) HTTP 200 | 21/21 |
| Latest (v2) HTTP 200 | 21/21 |
| Historical `dir="rtl"` | 21/21 |
| Latest `dir="rtl"` | 21/21 |
| Historical horizontal overflow | 0/21 |
| Latest horizontal overflow | 0/21 |
| Historical `.rsec` count == certified old sequence length | 21/21 |
| Latest `.rsec` count == approved new sequence length | 21/21 |
| **Historical added-section count (page-wide) = 0** | **21/21** |
| **Latest added-section count (page-wide) > 0** | **21/21** |
| Latest added-section positional count (scoped to expected `.rsec` index) >= 1 | 21/21 |
| Latest dead placeholder `href="#"` | 0/21 |
| Historical/Latest console errors | 0/42 renders |
| Historical/Latest page errors | 0/42 renders |
| Historical/Latest failed requests | 0/42 renders |

Screenshots: `browser_qa_history/<key>_v1_desktop.jpg` and
`<key>_v2_desktop.jpg` for all 21 keys (42 files). Machine-readable:
`browser_qa_history/summary.json`.

## 2. Expanded latest-v2 acceptance matrix — 63/63 PASS

**Script:** `w4b_full_matrix_qa.py` (session scratchpad). For each of the
21 curated keys at Desktop 1440×900 / Tablet 768×1024 / Mobile 390×844:

- **Header exactly once** — `document.querySelectorAll('header').length`.
  Source-confirmed: every `<header>`/`<footer>` tag on the public
  storefront path comes from the shared `page_shell_header.html` /
  `page_shell_footer.html` system (or a global-header/footer variant that
  itself renders exactly one `<header>`/`<footer>`); the only OTHER
  `<header>`/`<footer>` tags anywhere in the template tree are confined to
  the `dashboard/` (admin editor UI) templates, never reached by the
  public `home_visual.html` render path.
- **Footer exactly once** — same method.
- **Bottom Nav (`.gmn`) responsive contract** — read directly from the
  canonical CSS (`storefront_builder.css`, "Mobile bottom-navigation
  system: hidden at desktop/tablet by default" / `@media(max-width:680px)`
  block): `.gmn` must compute `display:none` above 680px (Desktop 1440,
  Tablet 768) and a non-`none` display at/below 680px (Mobile 390).
- **Core Home content** — `.rsec` count under `.wrap.sfb-preview-sections`
  equals the exact registry-known composition length
  (`len(EXPECTED_NEW_HOME_SEQUENCE[key])`) at every viewport (DOM
  structure does not change across viewports; only CSS visibility does).
- **No functional duplication** — counted how many distinct `.rsec`
  blocks contain at least one element matching the added section's own
  selector; required exactly 1 (not 2, which would mean the mechanism
  rendered twice).
- **Real primary-link resolution** — for each key, the first real
  (non-empty) `href` on the added section's elements (resolved to an
  absolute URL via `.href`) was opened in a fresh page at Desktop and its
  HTTP status recorded. `brand_carousel` links resolve to the existing
  `catalog:product-list?brand=...` route; `collection_tiles` links resolve
  to the existing `catalog:collection-detail` route; `story_rail` items
  resolve through the existing `resolve_destination` tag to either a
  product-list route or (for items with no destination) render as a
  non-link `<div>` — never a dead `href="#"`.
- **Dead placeholder `href="#"`** — scanned on every added-section
  element, every viewport.
- **Newsletter terminal (7 keys)** — for `niloufar_glass`, `beauty_dew`,
  `laleh_play`, `almas_luxury`, `green_workshop`, `pine_eco`,
  `mirror_beauty`, confirmed the LAST `.rsec` (index `len(sequence)-1`)
  contains `[id^="newsletter-form-"]` (the newsletter section's own
  source-confirmed DOM marker, from `sections/newsletter.html`), at every
  viewport.
- **Console/page/failed-request errors** — 0 required, every viewport.

### Result (`browser_qa_responsive_repair/summary.json`, 21 keys × 3 viewports = 63 entries)

| Check | Result |
|---|---|
| HTTP 200 | 63/63 |
| `dir="rtl"` | 63/63 |
| Horizontal overflow | 0/63 |
| Header exactly once | 63/63 |
| Footer exactly once | 63/63 |
| Bottom Nav hidden (Desktop+Tablet, 42 checks) | 42/42 |
| Bottom Nav visible (Mobile, 21 checks) | 21/21 |
| Core Home content (`.rsec` count matches) | 63/63 |
| Added section present, exactly 1 duplicate-block count | 63/63 |
| Real primary-link resolution (Desktop, HTTP 200) | 21/21 |
| Dead placeholder `href="#"` | 0/63 |
| Newsletter terminal presence (7 keys × 3 viewports) | 21/21 |
| Console errors | 0/63 |
| Page errors | 0/63 |
| Failed requests | 0/63 |

Screenshots: `browser_qa_responsive_repair/<key>_v2_{desktop,tablet,mobile}.jpg`
(63 files). Machine-readable: `browser_qa_responsive_repair/summary.json`.

## Traceability

- Original (rejected) substitution: `06_bounded_browser_qa_summary.md`,
  "Latest-vs-historical visible comparison" section (left in place, marked
  superseded, not deleted or rewritten).
- This repair's results are also folded into `06_bounded_browser_qa_summary.md`
  under "Independent Review Repair Round 1" and into
  `10_implementation_report.md`.
- No file under `apps/`, `tools/`, or `migrations/` changed in this
  repair. No Django test file changed. Verified: `git diff --stat HEAD`
  (against the repair's starting commit `f5114d83`) touches only files
  under `docs/qa_evidence/storefront_design_engine/phase5/w4b_template_curation/implementation/`.
