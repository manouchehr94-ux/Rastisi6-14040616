# P5-W3 final repair — full-suite base comparison

Compares the final repaired code (branch `feature/phase5-w3-design-lab`,
commit `e9551ff`) against the certified Phase-5 checkpoint
`e28b563ca614bd2eafea8ec102ad44cd8a56ae82`, using a clean secondary git
worktree checked out at that exact SHA (never resetting the W3 working tree).

Runtime for both runs: Python 3.12.3, Django 5.2.17, `shop_core.settings`,
same shared virtualenv.

## Raw counts

| Run | Tests | Failures | Errors | Skipped |
|---|---|---|---|---|
| Final W3 code (`19_final_full_storefront_builder_suite.txt`) | 3210 | 30 | 2 | 4 |
| Certified base `e28b563` (`19b_final_base_e28b563_full_suite.txt`) | 3160 | 30 | 2 | 4 |

Test count differs by exactly 50 — the W3 focused suite
(`apps.storefront_builder.tests.test_w3_design_lab`) itself, which does not
exist at the base checkpoint. No other test module gained or lost tests.

## Identity-level comparison

Extracted every `FAIL:`/`ERROR:` block from both raw logs (32 in each run)
and compared:

- **Failing/erroring test identities**: **identical set**, 32/32, both
  directions (`only in final` = `{}`, `only in base` = `{}`).
- **Exception/assertion types and messages**: compared block-by-block after
  stripping only the traceback `File "..."` frame lines (which differ solely
  because the base run's traceback originates from a different checkout path
  — the *content* of every other line, including the exact `AssertionError`
  text, was compared verbatim).
- Of the 32, **26 blocks were byte-identical** after that path normalization.
  The remaining **6** showed textual differences that were individually
  root-caused:
  - `test_version_palette_and_global_variants` — the apparent diff was an
    artifact of the extraction script (the trailing `Ran N tests in ...s`
    summary line bleeding into the last block); the actual assertion
    (`AssertionError: '3' != '2'`) is byte-identical in both runs.
  - The remaining 5 (`test_builder_preview_has_nav_but_never_live_cart_count_badge`,
    `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`,
    `test_header_footer_variant_labels_shown_for_updated_preset`,
    `test_public_home_renders_functional_mobile_nav_and_real_routes`, and one
    duplicate path-only diff) differ **only** in the value of one or more
    `csrfmiddlewaretoken` hidden-input values embedded in the rendered HTML
    body under assertion — a fresh, random, per-request token Django's own
    CSRF middleware generates on every single render regardless of any code
    change. After masking every 40–80 character alphanumeric run (the shape
    of a `django.middleware.csrf.get_token()` value) in both bodies, all 6
    blocks become byte-identical. None of these tests are related to the
    Design Lab feature (Dark Digital luxury mobile-nav rendering, the R4
    fullscreen editor topbar, and the Template Gallery's Warm Boutique
    contract) — their failure reason (an unrelated, pre-existing template/DOM
    assertion) is unchanged.

## Verdict

```
W3-only failures = 0
Base-only unexplained failures = 0
Changed pre-existing failure reasons = 0
```

The certified base's own 30 failures + 2 errors + 4 skips are a pre-existing,
unrelated baseline (unrelated legacy template/inspector/version-string
assertions) that this repair does not touch, worsen, or fix.
