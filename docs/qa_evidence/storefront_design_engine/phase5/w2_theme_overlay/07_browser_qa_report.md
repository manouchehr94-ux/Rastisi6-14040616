# P5-W2 Browser QA Report (Repair E) — Reversible Theme Overlay

Real server-rendered public storefront (`manage.py runserver`, DEBUG, Python
3.12.13) for the demo Store `rasti-mode-demo`, public page `/products/` (a
universal-shell page). Headless Chromium via `agent-browser` through a localhost
reverse proxy that injects the demo Store Host (works around the headless-CDP
forbidden-`Host`-header quirk; Django still resolves the Store by Host as in
production). Theme applied via the canonical `appearance_authority_service.apply_theme`
+ real Draft publish for each case.

## Materially different Ready Templates exercised (2)
- **Template A — `dense_marketplace`** (dense commerce grid, marketplace cards).
- **Template B — `editorial_jewelry`** (luxury editorial / jewelry-boutique DNA).

Template independence is therefore demonstrated: the SAME occasion markers,
motif tokens, CSS variables and behavior appear on both, with no per-template
Theme fork.

## Full logical matrix (programmatic) — 2 templates × 3 themes × 3 intensities × 3 viewports = 54 cases
Themes: **Yalda** (Iranian festive), **Ramadan** (Islamic / restrained),
**Muharram/Ashura** (mourning). Intensities: subtle / balanced / strong.
Viewports: desktop 1440×900, tablet 768×1024, mobile 390×844.

For EVERY one of the 54 cases the served DOM carried the correct
`data-occasion-theme / -tone / -intensity / -motif`, and:

| check | result (all 54 cases) |
|---|---|
| horizontal overflow (`scrollWidth - innerWidth`) | **-10px** (none) at every viewport |
| console errors | none |
| resolved motif token | Yalda→`pomegranate_night`, Ramadan→`crescent_lantern`, Muharram→`muted_banner` |
| intensity scales `--occasion-motif-opacity` | subtle 0.06 · balanced 0.12 · strong 0.20 |
| RTL (`dir="rtl"`) | intact |

Raw per-case output: `10_browser_qa_matrix_raw.txt`.

## Representative screenshots (`screenshots/`)
Template A (dense_marketplace): `A-yalda-strong-desktop/tablet/mobile`,
`A-yalda-subtle-desktop` (intensity contrast), `A-ramadan-balanced-desktop`,
`A-muharram-strong-desktop`, `A-none-restore-desktop`.
Template B (editorial_jewelry): `B-yalda-strong-desktop/tablet/mobile`,
`B-ramadan-balanced-desktop`, `B-muharram-subtle-desktop`, `B-none-restore-desktop`.

These prove:
- **Same Theme across two materially different Templates** (A vs B Yalda strong).
- **subtle vs strong** intensity contrast (A-yalda-subtle vs A-yalda-strong).
- **Yalda motif**: crimson top accent band + `pomegranate_night` corner
  ornament (radial crimson glow, top-inline-end) — reads as Yalda, not "a red line".
- **Ramadan motif**: restrained teal crescent (`crescent_lantern`) — Islamic identity, no festive particles.
- **Muharram mourning restraint**: a single calm flat `muted_banner` band, no
  corner ornament, no festive shapes, no animation — respectful.
- **Desktop / Tablet / Mobile** (Yalda strong on both templates, all 3 viewports).
- **Global chrome + real section decoration** from ONE resolved theme
  (`data-occasion-motif` on `<html>` and on `.rsec` section wrappers).
- **Theme none restoration**: `A-/B-none-restore-desktop` show no accent band and
  no motif ornament — visually identical to the pre-theme baseline.

## Actual Preview/Public parity
Automated integration test
`ThemeRenderedPreviewPublicParityTests.test_actual_preview_and_public_render_the_same_theme`
renders the REAL editor Preview route (`dashboard:storefront-builder-preview`,
Draft) and the REAL public route (`catalog:product-list`, published) for the
same Theme and asserts the full rendered occasion projection
(theme/tone/intensity/motif/accent + shell marker + section marker) is identical.
No new preview route, no editor-only or public-only Theme rendering.

## Per-case gate checks (all cases)
no horizontal overflow · no console errors · no failed relevant requests · RTL
intact · header readable · bottom-navigation usable (mobile) · contrast/
readability acceptable (accent is a decorative edge/wash + bounded corner
ornament, never a merchant-content text/background swap) · layout not corrupted
· Theme none restores base appearance · mourning theme restrained/non-celebratory.

## Public-home shell limitation (deferred to P5-W4A)
W2 Theme is certified on current universal-shell surfaces (product list, and
every page that extends `storefront_shell.html`/`base.html`). The standalone
`catalog/home.html` public home does not yet use the universal shell; that
public-shell convergence is deferred to **P5-W4A**. W2 does not claim complete
all-public-page Theme coverage before W4A.

Conclusion: Browser QA PASS across 2 materially different templates × 3 themes
× 3 intensities × 3 viewports, with real motif decoration, template
independence, mourning restraint, none-restoration, and actual Preview/Public
render parity.
