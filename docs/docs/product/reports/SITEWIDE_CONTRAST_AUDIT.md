# Site-Wide Colour Contrast & Interactive-State Accessibility Audit

- Branch: `fix/sitewide-contrast-accessibility-v1`
- Starting point: `main` @ `6b1f83a1d183ed2c2fb5e2a3e5c2c97c558bee78` (main had not moved)
- Standard: WCAG 2.2 AA
- Scope: public site, auth, portal/onboarding, platform admin, merchant dashboard, Storefront Builder / Design Studio, and the public storefronts of all 50 Ready Templates.

This report lists only results that were actually produced. Section 11 states exactly which verification runs were completed and which were interrupted.

## 1. Initial problem

The UI used hard-coded text colours on palette-dependent fills, brand hues as text colours, element-level `opacity` to fade disabled/locked text, and hover/active rules that changed only one half of a foreground/background pair. A clean baseline run (1366x768) found:

| Suite | Pages | Unique checks | Raw measurements | Distinct failures | Failing measurements | Focus failures |
|---|---:|---:|---:|---:|---:|---:|
| public | 10 | 338 | 1824 | 8 | 22 | 0 |
| auth | 7 | 126 | 1209 | 3 | 14 | 0 |
| portal / onboarding | 12 | 164 | 1010 | 14 | 77 | 1 |
| platform admin | 11 | 113 | 1014 | 40 | 217 | 0 |
| merchant dashboard | 30 | 427 | 4143 | 97 | 541 | 0 |
| Storefront Builder | 6 | 291 | 1736 | 94 | 502 | 1 |
| storefront (default demo) | 5 | 224 | 1063 | 102 | 517 | 3 |
| **Total** | **81** | | | **358** | **1890** | **5** |

Failing measurements by state: rest 172, toggle 60, hover 59, active 56, focus 9, action 2. By background kind: solid 273, gradient 47, image without scrim 38.

The 50 Ready Templates at baseline (1366x768): **0/50 passing**, 2903 distinct failures, 15,914 failing measurements, 107 focus-indicator failures, 8413 unique checks. The worst were `dense_marketplace` (1587), `roosta_zigzag` (973) and `fashion_promo_catalog` (714).

## 2. Thresholds (WCAG 2.2 AA)

| Content | Required ratio |
|---|---:|
| Normal text | 4.5 : 1 |
| Large text (>= 24px, or >= 18.66px bold) | 3 : 1 |
| Meaningful icon glyphs, UI component boundaries, focus indicators | 3 : 1 |
| Disabled controls (WCAG exempts them; product target) | 3 : 1 |

Derived colours are generated with a small margin (4.55 : 1; header text 5.5 : 1 so hover tints cannot push it under 4.5).

## 3. Root-cause categories

1. Fixed white or dark text on fills that change with the palette or theme.
2. Brand/fill hues (gold, pink, violet, green) used directly as text colour.
3. Element `opacity` used to fade disabled, locked or out-of-stock text, which also fades its background.
4. Link reset `.admin-body a{color:inherit}` outranking `.btn-primary`, `.tab.active` and similar.
5. Browser default placeholder colour on tinted fields.
6. Hover/active states that changed only the background or only the colour.
7. Header/footer role pairing mismatch: `--theme-header-*`/`--theme-footer-*` forced on regions whose own tokens (`--gh-*`, `--gf-*`) were paired to the page background.
8. Chips with a fixed surface carrying theme-dependent text.
9. Text over images with no or too weak a scrim.
10. Single-colour focus rings that vanish on one of the two backdrops.
11. Light/dark palette mismatch (light text token on a light card, and the reverse).

## 4. Contrast architecture

- **`apps/core/color_utils.py`** is the single WCAG implementation: `parse_css_color`, `composite`, `flatten`, `ratio_between`, `required_ratio`, `best_foreground`, `ensure_contrast`, `state_pair`, plus constants `AA_NORMAL_TEXT`, `AA_LARGE_TEXT`, `AA_NON_TEXT`, `DISABLED_TEXT_TARGET`. The older `relative_luminance`, `contrast_ratio` and `foreground_for` now delegate to it.
- **`apps/storefront_builder/accessible_colors.py`** derives accessible *usage* colours from the raw merchant palette (section 6).
- **CSS usage tokens** separate fill from ink:
  - `--violet-text`, `--pink-text`, `--on-violet`, `--on-pink`, `--on-gradient`, `--gradient-end`, `--on-tone-N`;
  - `--focus-ink`, `--focus-halo`, `--disabled-ink`, `--disabled-bg`;
  - `--gh-hdr-ink`, `--gh-hdr-muted`, `--gh-hdr-tint`, `--gh-accent-text`, `--gf-accent-text`, `--gmn-active-ink`, `--gmn-active-ring-*`;
  - dashboard `--*-ink` status tokens and portal/platform token pairs.
- **Fixes are made at the semantic-token level.** No global `!important` was added. The one unavoidable `!important` is on the `.footer-bottom` fixed pair, which sits under a (0,5,2) rule.

## 5. Shared fixes by area

**Buttons and states.** A pair is always re-derived for the state: hover/active background and its foreground move together (`--brand-primary-hover` / `--brand-primary-hover-fg`). `.admin-body a` resets were moved into a zero-specificity `:where(...)` so `.btn-primary`, `.tab.active` and similar keep their own colour. Header link hover is an underline instead of a tint, so the hover background cannot move under derived text.

**Focus.** Every focus ring is two-tone (inner ink plus outer halo) so it holds on light and dark backdrops, declared with zero specificity (`:where(...) :focus-visible`). Bottom navigation items and product-card hit areas received explicit rings.

**Forms, status, badges.** Status colours (success/warn/danger/info) are split into fill and `-ink` tokens, and the dashboard/platform templates that used `color:var(--green)` and similar inline were moved to `-ink`. Placeholders get an explicit colour. Disabled controls use `--disabled-ink`/`--disabled-bg` instead of `opacity`. Admin cover badge and the builder current-template badge have their own fg/bg pairs.

**Merchant dashboard / admin.** `admin.css`, `admin_v2.css`, `campaign_wizard.css`, `product_entry_prototype.css`; locked tile, campaign form, invoice/import/SMS tables.

**Public / auth / portal / platform admin.** Token-source changes in `platform-tokens.css`, `public-site-v2.css`, `public-home-v3.css`, `onboarding.css`, `platform-admin-panel.css`. The portal CSS contract (no literal colours outside `:root`) is kept, and the stylesheet links carry a cache-bust `?v=20261009-a11y`. A late regression where a literal `#000` appeared inside `color-mix` was corrected by using `var(--rs-ink)`.

**Storefront Builder / Design Studio.** `r4_studio.css`, `storefront_builder.css`, `_r3.css`, `_v22.css`: sage literals replaced with tokens, disabled Publish fixed, two-tone focus ring.

## 6. Dynamic storefront palette strategy

Merchant brand colours (`Palette`, `color_overrides`, `theme_overrides`) are **never rewritten**. They are still injected as `--brand-*` unchanged, and the Builder shows them as chosen. In addition, `build_accessible_theme()` (called from `apps/core/context_processors.py::shop_settings` and emitted in `templates/base.html`) derives, per request and server-side:

- `--brand-*-text`: the brand hue minimally nudged toward black or white, hue preserved, until it reaches the target on every surface it can sit on (page background, card surface, themed card). A colour that already passes is returned unchanged, so well-designed templates render identically.
- `--brand-*-fg`: black or white, whichever is higher contrast, for filled controls.
- `--brand-primary-hover(-fg)`, `--brand-gradient-fg/-end`, `--brand-muted-fg`, `--brand-tone-N-fg`, `--theme-header-muted-text`, `--theme-footer-muted-text`, `--theme-price-text`, `--brand-primary-text-dark` (for the fixed dark header shell).
- The `contrast_fg` template filter plus `--sfb-section-fg` handle merchant-coloured section bands.

`accessible_pairs()` is the contract list: the renderer promises these pairs and the tests iterate the same list, so the two cannot drift.

## 7. Text over images

Text over imagery sits on a deterministic scrim in CSS (gradient scrim, e.g. `.tile::after`, `.category-atelier-shade`, hero overlays) rather than relying on image content; where the text colour must be fixed, the pair is chosen against the *darker/lighter bound* of the scrim. The runtime audit treats an unprotected image as a failing background kind (38 failing measurements at baseline).

## 8. Tooling

**Deterministic tests**
- `apps/core/tests/test_contrast_utils.py` (24): the canonical utility.
- `apps/core/tests/css_tokens.py` + `test_css_token_contrast.py` (30): resolves CSS custom properties and asserts each documented token pair.
- `apps/storefront_builder/tests/test_ready_template_contrast.py` (17): all 50 Ready Templates and all 64 palettes, plus dynamic brand-colour edge cases (gold-on-white, near-black to pale gold gradient, etc.).

**Runtime computed-style audit** (`tools/contrast_audit/`, documented in its `README.md`): Playwright/Chromium. For every text node it takes the computed colour times cumulative opacity, then reconstructs the paint stack at the text position (`elementsFromPoint`, ::before/::after overlays, linear-gradient sampled at the text position, images bounded by black and white). The maths is done in Python through `color_utils`, so there is no second implementation. It exercises rest, hover, active, Tab focus (focus indicator >= 3:1 against the backdrop, or a two-tone ring), toggles, dialog/drawer openers and empty-form submit, across suites public/auth/portal/platform-admin/dashboard/builder/storefront/storefront-templates, at 1366x768, 1440x900 and 390px.

## 9. Results (completed runs)

### Non-storefront suites, 1366x768
All suites reached 0 failures after the fixes. The dashboard and builder suites each showed one remaining failure after the main pass (admin cover badge, builder current-template badge); both were fixed in commit `0dd36bb` and re-verified clean.

### Ready Templates, desktop 1366x768 (full run completed)
- **50 / 50 templates passing**; 200 pages, 56,134 raw measurements, 10,214 unique checks, 329 focus components, **0 failures**.
- Baseline for comparison: 0/50, 2903 distinct failures.

### Ready Templates, mobile 390px (completed run)
- 48/50 templates completed the run with **0 text-contrast failures**.
- Focus-indicator failures: 5, in `kite_playful` (`gmn-item`, `pcard-hitarea`) and `racer_tech` (`gmn-item`). Fixed in `dad2953` (two-tone rings for bottom nav and card hit area) and **re-tested individually clean**.
- Earlier 390px text failures were fixed as families: hero copy inheriting its panel colour, quick-view old price/stars/out-of-stock/close chip, bottom-nav labels and active tint, drawer tokens/surface, atelier mobile nav and search panel, category-atelier scrim.

### 1440x900
No completed 1440x900 evidence is claimed in this report. It was **not** run for the 50 templates, and the baseline and final non-storefront numbers above are 1366x768.

### Interactive states
Hover, active and keyboard focus were measured in every audit above (rest/hover/active/focus/toggle/open state classes). The desktop 50-template run reports 0 failures across all of them.

### Representative visual QA (before/after screenshots)
- `dark_digital` («پالس نئون») 1366x768 and 390: promo-tile buttons that were nearly invisible and the faint hero tabs are now readable; the neon/dark identity is unchanged.
- `warm_boutique` («کارگاه لاله») 1366x768 and 390: visually unchanged, since the palette already passed; only edge text/hover pairs moved.
- `dense_marketplace` («بازار مکس») 1366x768 and 390: hero subtitle that was white-on-white at 390 is readable; the dense layout is preserved.
- Dashboard home, products, auth login, public home and the onboarding industry step: before/after pairs captured.
- Demo product images do not load in the sandbox, in both "before" and "after" shots. This is unrelated to the contrast changes.

## 10. Tests

| Group | Result |
|---|---|
| Dedicated contrast modules (utils 24, token CSS 30, Ready Template 17) | 71 tests OK |
| Portal CSS-contract modules (11 modules) | 260 tests OK |
| Settings / theme modules | 228 tests OK |
| `test_u2a_global_header_system` | 84 OK (after pin update) |
| `test_u2b_global_footer_system`, `test_render_service`, `test_phase28c_direct_drawers`, `test_phase33…`, `test_phase36…`, `test_phase39…`, `test_acceptance_batch1`, `test_admin_v22_live_builder`, `test_r32_browser_fix`, `test_storefront_canonical_redirect` | OK |
| `test_g23_builder_public_content_appearance` CSS classes | 10 OK |

**CSS-pin test updates.** Two pre-existing tests pinned exact old CSS fragments and were updated, by reading the diff:
- `test_phase4_task5_cross_page_css.py`: every changed assertion keeps the same selector and the same full rule text; only the contrast-related value changed (e.g. `#ef4444` -> `#c93939` on `.special-kicker`, `.tile::after` scrim stops, `var(--violet)` -> `var(--violet-text,var(--violet))`). They remain exact `assertIn` string pins. None was turned into a generic check.
- `test_u2a_global_header_system.py`: `.gh-shell{--gh-ink:` -> `.gh-shell,.mobile-nav-drawer{--gh-ink:` (the rule now also scopes the drawer), and the dark-shell pin is a regex requiring `.gh-shell--dark{…--gh-ink:#f1f0f5`. The two `assertNotIn` guards are unchanged.
- `test_settings_views` (status green): the pinned `#16a34a` became a regex plus an assertion of >= 4.5:1. `test_terms_page` followed the cache-bust query string.

**Baseline (pre-existing) failures, identical on pristine `6b1f83a`:**
- `test_dark_digital_luxury_v2`: 8 failures (recipe/version/mobile-nav registry).
- `test_dense_marketplace_beraito_v2` + `test_premium_leather_shokolati_v2`: 9 failures + 1 error together.
- `test_g23_builder_public_content_appearance.DefectCSectionBackgroundTests` and `test_views` are seed-heavy and exceeded the time bound here. The former also exceeds it on pristine main. `test_views` was not completed in either tree.

## 11. Interrupted / not completed runs

- A final consolidated rerun (all templates, all viewports, in one pass) and a monolithic all-app test run were **started and did not complete**. Repeated container restarts killed the long-running processes, and a later targeted rerun hung. This is an environment limitation, not a product failure, and **those consolidated runs are not claimed as completed**.
- The earlier completed runs above remain the evidence: full 50-template desktop run, completed 390px run, and individual reruns of the failing templates.
- The last bounded targeted reruns completed for `kite_playful` and `racer_tech` at 390px: **0 failures and 0 focus-indicator failures in both** (kite_playful 1113 measurements / 9 focus components; racer_tech 810 measurements / 8 focus components). Reruns of `dark_digital`, `warm_boutique` and `dense_marketplace` after the last commits were **not** completed (they were stopped); their clean state rests on the full runs plus the manual visual QA.
- The last two commits only changed test pins, so they do not affect rendered output.

## 12. Known limitations

- Only 1366x768 was run for the full 50-template set; 390px was run once for all templates, and later fixes were verified by targeted reruns, not a second full mobile pass. 1440x900 is not claimed anywhere in this report.
- The runtime audit measures what the pages render with the seeded demo content. Pages that need real merchant data or third-party widgets (payment gateway pages, POST-only flows) were not audited. Platform-admin store detail (HTTP 500 in the sandbox) was left out.
- Colours inside merchant-uploaded images cannot be controlled; only text-over-image is protected, via scrims.
- Disabled controls target 3:1 as a product choice; WCAG exempts them.
- The audit tool is a point-in-time scanner, not part of CI; the deterministic tests are the permanent regression guard.
- Evidence JSON/screenshots were produced under the session's scratch area and are not committed (the repo keeps the tool and the tests that regenerate them). Re-run with `tools/contrast_audit/README.md`.
- **Mixed dark/light surfaces.** A merchant may legitimately choose a dark page background with a light card surface. One colour can then clear AA on both only when `(L_light + 0.05) / (L_dark + 0.05) >= 4.5^2` (a near-black page against a near-white card). `ensure_contrast()` now finds that narrow mid-luminance band (an earlier version required pure black or pure white to pass first and could return a 1:1 colour; corrected after independent review, with regression tests). For surface pairs where no single colour can reach the target, it returns the best worst-case (maximin) hue-preserving colour, which can be below 4.5:1 on one surface (e.g. about 4.34:1 for `#0F0F23` + `#FFFFFF`). Such a theme is accepted as-is, not rejected, and the body text colour the merchant chose is still validated by the existing form rules.
- Delivery: the branch was pushed to `origin` for independent review. No pull request has been opened, nothing has been merged and nothing has been deployed.

## 13. Follow-up: live Template switching in Design Studio

An owner QA of Design Studio found a defect the static/per-template audit could not: switching an existing light Draft to a dark
Template left the category labels nearly black on the black page.

**Switch semantics (existing contract, unchanged).** `r4_mutation_service.switch_template` -> `preset_service.switch_ready_template_preserving`
on the SAME Draft: appearance (palette slug, colour/role overrides, template slug, typed manifest), header/footer config, provenance and baseline
are REPLACED by the target Ready Template's (old colour overrides are dropped); a proven-pristine page is replaced by the target composition, a
merchant-modified page keeps its sections together with their presentation settings (e.g. `display_mode`).

**Reproduced in the real browser** (Design Studio, `?panel=appearance`; light `editorial_jewelry`, home category rail set to `image_strip`, then Apply `night_catalog`):
persisted palette `atelier-ivory` -> `theme-black-gold`, `color_overrides {}`, rail presentation still `image_strip`; preview tokens were all correct
(`--brand-text #FFE76A`, `--brand-background #070707`) but `.category-image-label` computed `rgb(37,40,45)` on `rgb(7,7,7)` = **1.36:1**.

**Root cause: wrong semantic token, exposed by preservation (not a stale-token bug).** Tokens refreshed correctly; the components hard-coded dark text
(`.category-image-tile{color:#25282d}`, `.category-chocolate-story-item{color:#33271d}`, `.tile-circle-label{color:#333}`) or used the page-only `--ink`/`--brand-text`
while sitting on a page that a Template switch had made dark (or on a merchant band). Also found: the owner's admin shortcut label inherited the header ink
on the primary fill (3.4:1 on `atelier-ivory`, equal-specificity reset in `.gh :where(a,button)`), and the mosaic chevron used palette muted text on its fixed white tile (1.2:1 on dark).

**Fix (surface ownership).** Text on the page or a band: `color:var(--sfb-section-fg,var(--brand-text,<fallback>))` (band foreground when a band defines it, accessible page text otherwise);
own fixed tile: a fixed colour verified on that tile; filled control: its own `-fg` token at every state. No global white/forced section colour. Applied identically in `home.css` and `storefront_builder.css`.

**Evidence.** `run_audit.py --suite template-switch` (new; 7 switches, 4 template classes, every category presentation, band cases, publish): before the fix 46 distinct failures
(worst 1.0:1, includes the reported 1.36:1); after: **0 text failures, 0 focus failures, 0 stale tokens, 0 errors, preview tokens == published tokens**. Published anonymous storefront for the formerly failing rail:
`rgb(255,231,106)` on `rgb(7,7,7)` = 16.2:1, identical to the preview. Deterministic regression tests: `test_template_switch_contrast` (11: light<->dark, custom mixed-surface palette -> template, A->B->A, 8-step walk, preserved presentations on the new palette),
`CategoryComponentSurfaceOwnershipTests` (5 scenarios incl. bands). These fail on the previous CSS (1.36:1).

**Limitation.** The cross-product (preserved presentation x new palette) was audited for the category rail, which the defect concerned; other section types were measured on whole-page switches only, not per presentation variant.
