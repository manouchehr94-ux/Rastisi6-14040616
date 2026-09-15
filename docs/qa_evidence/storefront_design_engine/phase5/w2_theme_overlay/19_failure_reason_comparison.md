# Pre-existing failures — compared by REASON, not just test name (Python 3.12.13)

IMPORTANT 2 evidence. Full COMPLETE raw stdout/stderr preserved for both runs:
- `17_w2_full_suite_raw.txt` — W2 PR branch (`Ran 3160 tests — FAILED (failures=30, errors=2, skipped=4)`).
- `18_base_full_suite_raw.txt` — clean certified-base clone at
  `b7d8ac281389870877553f5a308af3e77dcdd7f0` (`Ran 3102 tests — FAILED (failures=30, errors=2, skipped=4)`).
  No stash/reset/clean — a separate clone at `/projects/sandbox/base_repro`
  (W2 code absent: `theme_catalog.py` does not exist there).

## Method
Both raw outputs were parsed into per-test failure blocks and compared three ways:
1. **Test-identity diff** (`14_base_312_failures.txt` vs `15_w2_312_failures.txt`):
   W2-only = none, base-only = none. 32 == 32.
2. **Full normalized block diff** (`compare_failures.py`): flagged 5 tests as
   "changed" — ALL only because the assertion's embedded *rendered-HTML/JS
   haystack* differs (W2 legitimately adds `data-occasion-*` markers to
   storefront-shell pages). The assertion itself was unchanged.
3. **Assertion-signature diff** (`compare_reasons2.py` — strips the embedded
   HTML haystack, keeps exception type + searched token/operands + failing
   `self.assert…` call): **31 SAME, 1 "DIFF" which is a false positive** (my
   extractor captured the trailing unified-diff `- 3` line). Manual inspection
   of that one test confirms identical reason.

## The 5 "changed-block" tests — assertion reason IDENTICAL on base and W2
| test | assertion (both base & W2) |
|---|---|
| `MobileBottomNavRenderingTests.test_builder_preview_has_nav_but_never_live_cart_count_badge` | same assertion; only rendered-HTML haystack differs |
| `MobileBottomNavRenderingTests.test_public_home_renders_functional_mobile_nav_and_real_routes` | same assertion; only rendered-HTML haystack differs |
| `AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary` | same assertion; only rendered-HTML haystack differs |
| `TemplateGalleryTests.test_header_footer_variant_labels_shown_for_updated_preset` | same assertion; only rendered-HTML haystack differs |
| `FullscreenEditorTests.test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` | `':aria-pressed="fullscreen"' not found in <html>` — identical; the admin editor `<html>` carries no occasion markers anyway |

## The 1 "signature-DIFF" test — false positive, reason IDENTICAL
`WarmBoutiqueV2ContractTests.test_version_palette_and_global_variants`:
- BASE: `self.assertEqual(self.preset.version, "2")` → `AssertionError: '3' != '2'`
- W2:   `self.assertEqual(self.preset.version, "2")` → `AssertionError: '3' != '2'`
Byte-identical; the "DIFF" was the extractor capturing the trailing unified-diff
`- 3` marker line, not a real reason change.

## Conclusion
- W2-only failing tests: **none**
- base-only failing tests: **none**
- same test, changed failure reason: **none** (the 5 block-diffs and 1
  signature-diff are all incidental rendered-HTML/diff-marker artifacts; every
  assertion type, message and failing call is identical)

**ZERO W2 REGRESSIONS — proven by reason.** The 30 failures + 2 errors are
pre-existing at `b7d8ac28` (frozen preset-version / reference-silhouette /
mobile-nav / fullscreen-topbar / template-gallery / validator-boundary tests),
none touching the Theme family or the appearance engine W2 modifies.
