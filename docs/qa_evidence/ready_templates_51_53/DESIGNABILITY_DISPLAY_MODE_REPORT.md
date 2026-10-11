# Template 51 — designability + display-mode wiring (after owner manual QA)

Baseline `b88d7e027ec06b81012e5ba3083c35a4caa659fa`. Template 52/53 untouched. Not pushed.

## 1. Root cause of the display-type "no-op"
The value chain was correct end to end: Inspector `change` -> `section.update_settings` {display_mode} -> schema clean ->
`validate_settings` -> `StorefrontSection.settings` (+ `appearance_overrides.variant_explicit`) -> `build_page_render_items` ->
effective settings (the explicit marker already stops the Store-appearance family overlaying it) -> `product_section.html`.
Traced per value (carousel / grid / campaign_band / catalog_grid): DB value, effective render value and markup all followed the choice.

**The editor shell never refreshed the Preview iframe after an accepted `section.update_settings`** (only structural,
global-design and resource-picker writes reloaded it). The Inspector (re-read from the DB) showed "campaign band" while the
visible frame still held the old render. Same cause made every other Inspector control (colours, background, design) look dead.
Fix: `R4.sendMutation` refreshes the Preview (existing atomic twin-iframe refresh, coalesced) for `section.update_settings`,
`container.update_settings`, `section.reset_setting_to_baseline` after the revision cursor advances.
No stale recipe value / override marker / variant projection won anywhere in the chain.

## 2. Background control: existed and was wired — but buried, and the fill was hidden by section CSS
* `background` (label "پس‌زمینه این بخش") was in `BACKGROUND_AWARE_SECTION_KEYS` and in the Inspector, but in the **Advanced** tab.
  It is now in the **Basic** tab for `product_section` (`BACKGROUND_FIELD_BASIC_SECTION_KEYS`); other sections keep Advanced.
* A custom colour on the band only produced a thin edge: a legacy rule painted any non-patterned `center_stepper` product section as a
  white panel, and band heading/padding rules were keyed to `[data-pattern]`. They are now keyed to the background MODE: the panel look
  belongs to `surface` (or no background); palette / colour / image / pattern bands share one band layout and heading style.

## 3. Image background is one block, one authority
`settings.background` (single persistence authority) now also carries `image_fit` (cover/contain), `image_position_x`
(left/center/right), `image_position_y` (top/center/bottom), `overlay_color` (palette token or #RRGGBB), `overlay_opacity` (0–100),
`bleed` (now allowed for `image`). Defaults are never stored; keys are dropped for other modes. Asset is a Store-scoped `MediaAsset`
id only (ownership validated on write, URL resolved Store-scoped at render, foreign id -> 400); no raw-URL field exists.
Render: wrapper inline image (historical output unchanged when nothing customised) or the `.rsec-bleed` layer for bleed, plus a real
`.rsec-overlay` element bounded by the canvas (no pseudo-element, no overflow). Inspector widget: groups shown per mode
(colour / palette / pattern / image+fit+position+overlay / bleed); choosing "image" waits for the Media Library pick.

## 4. Display types are four visibly different compositions
carousel (horizontal row, navigation/scrollbar/overflow), grid (fixed grid, wraps), campaign_band (promo copy region + product grid),
catalog_grid (centred heading + bar, flat grid, closing bar with view-all/pagination). `effective_product_section_settings` makes the
variant primary: row settings of another composition are dormant at render time (stored value kept), so a stale `desktop_layout="grid"`
can never turn a campaign band into the ordinary grid. `gap`/columns now apply to campaign_band and catalog_grid too.

## 5. Context-sensitive Inspector
`SettingsField.visible_when` (generic, schema metadata) + `compute_field_visibility` (server `hidden`) + live `applyFieldVisibility`
(JS). Matrix (real UI, hidden controls): grid hides autoplay/interval/arrows/desktop_layout/overflow/scrollbar/navigation;
campaign_band and catalog_grid also hide header_position/heading_style; carousel shows row controls (autoplay on swaps them for the
slider controls; scrollbar only for a scrolling row).

## 6. Recipe vs merchant
Template 51 only supplies defaults. Regression tests: explicit display_mode/background/design survive Preview reloads, unrelated edits and
the Store-appearance overlay; only re-applying the whole template restores recipe values.

## 7. Results
* Colour round trip (real UI + tests): custom red #D62828 -> blue #2F6FED, palette tone-1 -> tone-4, pattern on/off — Preview changes
  immediately (computed bleed colour verified); `contrast_fg` >= 4.5:1 for 9 custom colours.
* Image background: Media Library asset, contain/cover, left/top, overlay token:text 35–50 % — applied in Preview; bleed layer and overlay
  hidden-clip audit: 0 horizontal overflow at 1440/1024/768/390 (Preview and Published).
* Preview == Published: wrapper signature identical (tests), and live demo store: Rasti Mode Demo band (campaign_band + image + overlay)
  identical computed style and geometry on the Studio preview and the public host (`designability_display_mode/parity_*.jpg`).
* Screenshots: `designability_display_mode/display_modes_51.jpg` (+ per-mode), `band_background_sequence.jpg`, Inspector hidden-control shots.
* Focused suites: 1776 tests, only the known pre-existing failure `test_validate_appearance_config_is_the_validator_boundary`
  (also fails on clean HEAD). Browser (opt-in): 9 OK. `check` clean, `makemigrations --check` no changes, `git diff --check` clean.
