# Template 51 — interaction performance + campaign panel designability

Baseline `1d88d7683fd47767f6febbffb905f3087efd3b56`. Templates 52/53 untouched. Not pushed.

## 1. Dead / mis-wired controls found (real browser, Rasti Mode Demo band) and root causes
Method: every visible control of the product section (Basic + Advanced, every display type, every background mode) was driven through the
real Studio UI; verdict = persisted value changed AND the computed style / geometry of the Preview changed
(`control_audit_before_old_code.log`, `control_audit_after.json`). 390 control checks after the fixes: 344 PASS, 36 N/A at desktop width
(tablet/mobile columns, hide-on-tablet/mobile: verified by unit tests on the `--cols-*` / `data-hide-*` output), 2 skipped (single media asset =
no alternative value), 8 flagged "no effect" that are blind spots of the audit signature (heading `h2` inside `.catalog-grid-head`, the
campaign heading rule `>span`, the catalogue bar) and were each verified directly with computed styles (`token:surface` and hex values change them).

| control | root cause | fix |
|---|---|---|
| show_view_all (campaign band, automatic source) | the panel link needed `view_all_url`, absent for automatic sources: nothing rendered | same fallback to the product listing the other displays use |
| campaign panel copy / icon / media / colours | hard-coded gift SVG + the section title as panel copy, no settings | new `campaign_*` contract (below) |
| background colour / image / overlay on a campaign band | band box filled from the palette role only (`:has(campaign-band)` rule) | band fill is generic: colour, palette, pattern, image + overlay variables |
| design heading_color | `!important` band-ink rules (hs-plain, theme_palette, campaign heading, image scrim) | `--d-heading` consumed by each of them, stronger selector where theme CSS is `!important` |
| design accent_color | no consumer on heading bars / pill / campaign rule | consumers added |
| design radius / border / shadow / surface | bleed band has no box; campaign band's box is `.product-campaign-band`; band layout rule forced `border-radius:0`; colour-mode inline fill | rules target the real box; for a bleed fill the box controls are not offered |
| design align | hs-plain heading forced `justify-content:flex-start` | `var(--d-align,flex-start)` |
| design image_ratio | `center_stepper` card rule outranked it | `!important` consumer |
| design image_fit | card styles force `object-fit:contain!important` | explicit section choice outranks via `--sfb-image-fit` + `!important` |
| design price_color | theme `.pcard .price .now{…!important}` | `!important` consumer |
| design text_color | palette rule later in the cascade | stronger selector + consumers (names, subtitle, campaign copy) |
| design item_width | only carousels have item widths | offered for carousels only |
| display-dependent controls (autoplay, overflow, scrollbar, navigation, subtitle…) | shown for compositions that ignore them | `visible_when` metadata, server + live JS |

## 2. Partial refresh architecture
`section.update_settings` / `container.update_settings` → server validates & persists → **the mutation response carries the canonical
server-rendered fragment** (`render_preview_fragment`: the same `build_page_render_items` restricted to the affected sections via
`only_section_ids`, the same wrapper / container templates as the full Preview) → the Studio swaps only that region inside the Preview iframe:
`Alpine.destroyTree(old)` → `replaceWith` → `Alpine.initTree(new)`, selection re-synced. No rendering logic in JavaScript; tests assert the
fragment is byte-identical (whitespace-normalised) to the section / container in the full Preview.

Full atomic refresh (unchanged twin-iframe swap) remains for: structural mutations (add / remove / move / duplicate / lock / toggle / layout change),
global design (appearance / header / footer / theme / template), Design Lab and template-preview frames, legacy row layouts (no containers), a hidden
block, a fragment containing `<script>`, a refresh already in flight, any render error (never fails the committed write), and Undo / Redo.

Coalescing: writes for the same section/container merge into one mutation holding the latest value of every key; continuous controls (colour
drag, range, typing) go through an `input` phase with a 110 ms debounce; discrete controls flush immediately; keys already sent are not sent
again; non-settings writes flush pending edits first (write order preserved); an older display-type response never overwrites a newer choice.

**Server cost fixed**: every mutation took two full draft snapshots for Undo history — 207 queries / 130 ms each. `snapshot_draft` now loads each table once
(7 queries / 8 ms), output verified identical to the previous implementation on the demo draft.

## 3. Latency (real UI: control event → Preview DOM shows the new canonical state; Playwright, local)
| edit | before (full-frame refresh) median / p95 | after (fragment) median / p95 |
|---|---|---|
| simple setting (41 controls, carousel band) | 689 / 792 ms | 131 / 177 ms (352 writes in the control audit) |
| title | — | 157 / 171 |
| campaign panel title | — | 162 / 187 |
| icon choice | — | 157 / 170 |
| panel toggle | — | 171 / 197 |
| custom colour | — | 157 / 203 |
| display mode (structural) | 711 | 155 / 161 |
Targets (simple ≤200 / 500, structural ≤350 / 800) are met; opt-in browser test records the same numbers (150/156 and 138/153).

## 4. Campaign panel contract (`product_section`, `display_mode = campaign_band`)
`campaign_panel_enabled` (False removes the panel; the product region takes the width), `campaign_panel_title`, `campaign_panel_subtitle`
(independent of the section heading; a legacy section keeps following its title until the first edit pins it), `campaign_visual_mode` (icon / media / none),
`campaign_icon_key`, `campaign_media_asset_id`, `campaign_visual_size`, `campaign_panel_width`, `campaign_panel_align`,
semantic colours `campaign_panel_bg / fg / accent / border_color` (automatic accessible foreground), `campaign_panel_border_width / radius / padding`.
Sparse: only non-default values are stored. The renderer invents no copy (“پیشنهادهای فروشگاه” and the “محصولات” heading fallback of the catalogue
display are gone). Inspector: panel content in Basic, design in Advanced; every campaign control appears only for a campaign band; panel disabled hides
the rest (and the otherwise dead view-all); visual mode selects icon picker vs Media Library picker vs nothing.

## 5. Icon / media architecture
`icon_registry.py`: generic key → label + SVG on a 64 grid with `currentColor` (gift, star, sparkles, shopping_bag, heart, tag, percent, truck, fire, crown);
unknown key renders nothing. Media: Store-scoped `MediaAsset` id only — ownership validated at write time for every schema `media` field (foreign id → 400) and
re-resolved Store-scoped at render (missing / foreign asset → no visual, never a broken image). No raw URL field exists.

## 6. Owner use case, in the real Studio (`campaign_panel_sheet.jpg`, `owner_use_case_log.json`)
rename panel text → remove it → change icon (star) → remove icon → Media Library image → hide whole panel (products 1093 → 1330 px) → restore →
recolour panel (tone-4 background, custom foreground, radius) → change the main title independently (panel title unchanged) → change the section background
independently (panel keeps its colours); all survive a full Preview reload; document overflow 0 throughout.

## 7. Tests
`test_interaction_performance_campaign_panel.py` (fragment parity section + container, request-only / eligible types, rejected write → no fragment, only
requested sections built, Alpine destroy/init order, coalescing contract, constant-query history snapshot, icon registry, no fixed SVG / copy in the template,
independent titles + legacy pinning, no invented copy, panel removal, visual none/icon/media, foreign media 400, no raw URL, colour round trips + clamping,
automatic foreground ≥ 4.5:1, panel colour independent of section background, band fill for colour / palette / image + overlay, Preview == Published,
conditional Inspector matrix, data-driven "every visible control changes the render" for all four display types, design consumers in CSS) and opt-in browser tests
(same document kept + Alpine `go()` works after the swap, 25 input events → ≤2 writes with the last value winning, 40 colour events → ≤3 writes, measured
latency, image-background overflow / parity). Existing suites adjusted only where behaviour intentionally changed (campaign grid column variable, view-all in
the panel, pinned CSS literals now tokenised).
