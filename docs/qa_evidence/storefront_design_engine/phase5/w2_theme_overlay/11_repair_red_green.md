# P5-W2 PR #8 Repair — TDD RED → GREEN (Python 3.12.13)

All repairs followed RED → GREEN. Runtime: Python 3.12.13, Django 5.2.17.

## Repair A — single request-scoped resolved appearance
RED (before repair), `ThemeSingleResolutionTests`:
- `test_one_universal_render_resolves_appearance_only_once` — FAILED: the shell
  context processor called `resolve_store_appearance_render_state` a SECOND time
  (spy `call_count == 2`) after the universal render already resolved once.
- `test_theme_projection_consumes_already_resolved_state` — FAILED
  (`'none' != 'ramadan'`): the projection ignored the resolved appearance
  already on the request and re-derived from scratch.
- `test_malformed_new_manifest_is_not_silently_converted_to_no_theme` — FAILED
  (`InvalidStoreAppearanceContract not raised`): the broad `except Exception:`
  swallowed a malformed NEW manifest into `theme.none`.

GREEN (after repair): added
`render_service.resolved_store_appearance_for_request(request, version)`
(request-scoped memoization on `request.storefront_resolved_appearance`, keyed
by `version.pk`), consumed by both `build_universal_storefront_context` and the
`shop_settings` context processor; removed the broad `except`. All 4
`ThemeSingleResolutionTests` PASS; a malformed new manifest now raises loudly.

## Repair B — real catalog motif
RED: `ThemeMotifTests` — FAILED because `ThemeOverlayState` had no `motif`
field, no `SHOP_OCCASION_MOTIF`, no `data-occasion-motif` in templates, and
`occasion_theme.css` had no `[data-occasion-motif="…"]` hooks.
GREEN: `ThemeOverlayState.motif` added and populated from the catalog;
`SHOP_OCCASION_MOTIF` projected; `data-occasion-motif` emitted on `<html>` and
on `.rsec` section wrappers; `occasion_theme.css` maps all 7 non-noop motif
tokens to distinct bounded CSS decorations (corner ornament per motif; Muharram
`muted_banner` = calm flat band, mourning suppresses the ornament). All 7
`ThemeMotifTests` PASS.

## Repair C — real Undo AND Redo
GREEN: `test_theme_mutation_participates_in_undo_redo` now performs apply Yalda
strong → undo (asserts `theme.none.v1` + no theme settings) → redo (asserts
`theme.yalda.v1` + intensity `strong`). Added `test_clear_theme_participates_in_history`.
Existing history system only.

## Repair D — actual rendered Preview/Public parity
GREEN: `ThemeRenderedPreviewPublicParityTests` renders the REAL
`dashboard:storefront-builder-preview` (Draft) and REAL `catalog:product-list`
(published) routes for the same Theme and asserts identical rendered projection
(theme/tone/intensity/motif/accent) + shell marker + section marker.

## Minor — No Theme == Clear
RED: `ThemeNoneNormalizationTests` — FAILED because selecting `theme.none.v1`
via `apply_theme(intensity=…)` retained a meaningless `settings["theme"]` intensity.
GREEN: `apply_theme("theme.none.v1", …)` now routes to `clear_theme()` (no dead
intensity); the R4 JS routes the "بدون تم مناسبتی" choice to `theme.clear` and
disables the intensity control when No Theme is selected. Both tests PASS.

## Focused suite (Python 3.12.13)
`test_w2_theme_overlay`: 56 tests, all PASS (was 41 pre-repair; +15 repair tests).



---

## Post-review follow-ups (Python 3.12.13)

### Repair-A transient-candidate regression (found, fixed, locked)
An interim full-suite run surfaced 21 errors in the template-Preview modules
(`test_task2_live_demo_template_preview`, `test_task3_merchant_template_preview`,
`test_appearance.NonDestructiveTemplatePreviewTests`). Root cause: the preview
path sets `request.storefront_appearance_version` to a transient candidate
stand-in (`_CandidateAppearanceVersion` / `_ReadyTemplateCandidateAppearanceVersion`)
that has no `pk`; the request-scoped resolver was being called on it. Fixed per
Architect Repair A ("do NOT call the persisted-Version resolver on transient
candidate stand-ins"): the context processor now resolves Theme ONLY for a real
saved `StorefrontLayoutVersion` (`isinstance` + real `pk`); candidate stand-ins
render as no-theme. A malformed NEW persisted manifest on a real Version still
raises loudly (no broad except). Locked by
`ThemeSingleResolutionTests.test_transient_candidate_standin_does_not_call_persisted_resolver`.
After the fix: candidate-preview modules all PASS (task2 13 + NonDestructive 11 = 24; task3 11).

### Task-6 historical guard correction
`test_ready_template_recipe_files_are_untouched_by_task6` re-anchored to the
FIXED Task-6 range `c0ca174…c0024cc0...a757114…0024cc0`
(`c0ca174475bf19dd5c3ecac3857da479623e1e7d...a75711473b791c2add0389913707503bc0024cc0`),
forbidden set unchanged, NO W2 exemptions. See `12_task6_historical_guard.txt`.

### Final focused count
`test_w2_theme_overlay`: **57 tests, all PASS** on Python 3.12.13.



---

## Final review — IMPORTANT 1: normal editor Preview single resolution (TDD RED → GREEN)

### RED
Route: `dashboard:storefront-builder-preview` (the REAL editor Preview route).
Before the fix, `storefront_preview` called `resolve_store_appearance_render_state(draft)`
directly and never cached the result on the request, so the shell context
processor (`shop_settings`) resolved the SAME Draft a second time.

```
Before fix:   resolver call_count = 2
Expected:     resolver call_count = 1
Observed RED: 2 != 1
```
(Counted at the single underlying resolver's source module so both the view's
call and the context processor's call are captured regardless of import name.)

### GREEN
`storefront_preview` now uses
`render_service.resolved_store_appearance_for_request(request, draft)`, so the
view's resolve is cached on `request.storefront_resolved_appearance` and reused
by the context processor.

```
After fix:        resolver call_count = 1
Theme still rendered: yalda / strong  (data-occasion-theme="yalda" in HTML)
```
Locked by `ThemeSingleResolutionTests.test_normal_editor_preview_resolves_appearance_only_once`.
Invariants preserved: public universal render = one resolve; transient candidate
stand-in never passed to the persisted resolver; malformed NEW saved manifest
still fails loudly.

### FINAL focused count (supersedes the 57 above)
`test_w2_theme_overlay`: **58 tests, all PASS** on Python 3.12.13 (adds the
normal-editor-Preview single-resolution regression test).
