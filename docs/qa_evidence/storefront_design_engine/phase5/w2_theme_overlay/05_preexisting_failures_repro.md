# Pre-existing failures — independently reproduced against the certified base

Per the P5-W2 execution rule (§30): any unrelated failure claimed as pre-existing
MUST be independently reproduced against `b7d8ac281389870877553f5a308af3e77dcdd7f0`
before it may be classified as pre-existing.

## Method
1. Ran the full `apps.storefront_builder.tests` suite on the W2 branch:
   `Ran 3143 tests — FAILED (failures=30, errors=2, skipped=4)`.
2. `git stash push -u` to revert the worktree to the exact certified base
   (`git rev-parse HEAD` == `b7d8ac281389870877553f5a308af3e77dcdd7f0`, W2 code
   fully removed, including `theme_catalog.py`, the `theme` family, the CSS, the
   test file, and all edits).
3. Re-ran the union of the failing test modules on the clean base.

## Result — IDENTICAL failure set (32 total)
The clean certified base produces the **exact same** 30 failures + 2 errors,
with none of the W2 Theme code present. Therefore all 32 are **pre-existing at
`b7d8ac28`** and are NOT introduced by P5-W2.

Base-repro run summary:
```
Ran 234 tests in 65.677s
FAILED (failures=30, errors=2)
```

The 32 pre-existing failures (identical on base and on W2 branch), all in
Ready-Template *reference contract* / mobile-nav / fullscreen-topbar / template
gallery tests that assert frozen preset versions and reference silhouettes —
none touch the Theme family, the appearance manifest engine, validation,
rendering, mutation, or the R4 appearance pipeline W2 modifies:

- test_warm_boutique_lalerokh_v2: 6 (version "3" vs asserted "2", card/silhouette)
- test_dense_marketplace_beraito_v2: 7 (incl. 1 error: brand/blog discovery)
- test_dark_digital_luxury_v2: 8 (mobile-nav recipe/persist/render/switch)
- test_editorial_jewelry_saremi_v2: 4
- test_premium_leather_shokolati_v2: 3
- test_u8_template_gallery: 1 (variant labels for updated preset)
- test_r4_vertical_slice: 1 (validator-boundary contract)
- test_views.FullscreenEditorTests: 2 (1 error, 1 fail — topbar/route shape)

## W2-owned tests
Every W2 Theme test (41) and every targeted-regression appearance/registry/
render/preset test PASSES on the W2 branch — see `02_green_focused.txt` and
`03_targeted_regression.txt` (186 OK, 1 skipped).

Conclusion: W2 introduces ZERO regressions. The 32 failures are a pre-existing
condition of the certified checkpoint, unrelated to the Theme overlay.
