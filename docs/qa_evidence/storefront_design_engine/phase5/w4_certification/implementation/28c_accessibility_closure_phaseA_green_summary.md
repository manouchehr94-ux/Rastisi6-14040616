# W4C Accessibility Closure Round — Phase A GREEN

Per Section 1 of the Accessibility Closure Round directive: the shared
helper `w4cAccessibilityChecksPass(checks)` now gates `passing` in every
Base cell runner (Home/Listing/PDP/Cart), Theme deliberately excluded.

## Implementation

- `tools/storefront_builder_r4_qa/run.mjs`: added
  `function w4cAccessibilityChecksPass(checks) { return
  Object.values(checks).every((value) => value !== 'FAIL'); }`,
  inserted immediately before `w4cRunHomeCell`.
- `w4cRunHomeCell`: introduced `homeA11yChecks = { mobile_nav_opener:
  mobileNavA11y }` and `homeA11yOk = w4cAccessibilityChecksPass(homeA11yChecks)`,
  wired `homeA11yOk` into `passing` (replacing the old direct
  `mobileNavA11y !== 'FAIL'` check), return statement now uses
  `accessibility_checks: homeA11yChecks`.
- `w4cRunListingCell`: introduced `listingA11yChecks = { search_input,
  sort_control, category_filter, product_card, quick_view }` and
  `listingA11yOk`, wired into `passing` (replacing the old
  `searchA11y !== 'FAIL'`-only check), return statement now uses
  `accessibility_checks: listingA11yChecks`.
- `w4cRunPdpCell`: added `pdpA11yOk = w4cAccessibilityChecksPass(pdpA11y)`,
  added `&& pdpA11yOk` to `passing`; `accessibility_checks: pdpA11y`
  return field unchanged (already correctly shaped).
- `w4cRunCartCell`: added `cartA11yOk = w4cAccessibilityChecksPass(cartA11y)`,
  added `&& cartA11yOk` to `passing`; `accessibility_checks: cartA11y`
  return field unchanged (already correctly shaped).
- Every non-PASS `reason` string for these four cells now appends
  `accessibility_ok=${...}`.
- `w4cRunThemeCell` left untouched — no reference to
  `w4cAccessibilityChecksPass` added, per the directive's explicit
  exclusion ("public Theme exposes no admin accessibility controls in
  this matrix").

## Verification

- `node --check tools/storefront_builder_r4_qa/run.mjs`: PASS.
- Focused suite `test_w4c_all50_certification_harness`: **110/110
  passing** (full output: `28a_accessibility_closure_phaseA_green_focused.txt`),
  confirming genuine GREEN for all 8 new Phase-A tests (`test_98`-`test_105`)
  and 0 regressions among the 102 pre-existing tests.
- `manage.py check`: 0 issues.
- `makemigrations --check --dry-run`: no changes.
- `git diff --check`: clean.
- `test_ready_template_real_previews` + `test_qa_harness_contract`:
  36/36 passing (3 skipped as expected, unaffected by this change).
- Full fast-gate output: `28b_accessibility_closure_phaseA_green_fastgates.txt`.

## Scope confirmation

Only `tools/storefront_builder_r4_qa/run.mjs` was modified in this
phase. No production template, no Python command file, no test file
(the test file was already committed separately in the RED commit).

## Next step

Task #74 — one fresh bounded smoke (`--only editorial_jewelry`, new
empty campaign root) to prove the gate is now real: Home/Cart/Theme
expected to remain PASS; Listing/PDP expected to now genuinely FAIL,
since their `accessibility_checks` still contain the real, unrepaired
production FAIL values (Findings A and B from Repair Round 2). Phase B
(production template repair) does not begin until this smoke confirms
the gate behaves as expected against current, unrepaired production
markup.
