# P5-W3 — Full Storefront Builder Suite vs Certified Base Comparison (Section 28)

## Method
The full `apps.storefront_builder.tests` suite was run on BOTH:

* **Certified base** `e28b563ca614bd2eafea8ec102ad44cd8a56ae82` — a **separate clean clone**
  at `/projects/sandbox/_base_e28b563` (its own venv, Python 3.12.13 / Django 5.2.17).
  Raw output: `07b_base_e28b563_full_suite.txt`.
* **W3 branch** `feature/phase5-w3-design-lab` (this branch, after the four guardrail
  repairs). Raw output: `07_full_storefront_builder_suite.txt`.

No `git stash` / `reset` / `clean` / `checkout` was used on the active W3 worktree — the
base was a distinct clone (Section 28 requirement).

## Headline numbers

| | tests run | failures | errors | skipped |
|---|---|---|---|---|
| Certified base `e28b563` | 3160 | 30 | 2 | 4 |
| W3 branch | 3197 | 30 | 2 | 4 |

W3 adds 37 tests (`test_w3_design_lab`), so `3197 = 3160 + 37`. The failure/error counts
are **identical** to the base.

## Failure-identity comparison (Class::method for every FAIL/ERROR)

```
W3-only failures (in W3, not in base):   0
BASE-only failures (in base, not in W3): 0
Shared failing tests:                    32  (30 failures + 2 errors)
```

## Failure-reason comparison

Each of the 32 shared failing tests fails for the **same reason** (same exception type +
same assertion message) on both the base and the W3 branch:

```
CHANGED pre-existing failure reasons: 0
SHARED identical reasons:             32
```

**Note on one test's raw text.** `test_views.FullscreenEditorTests.
test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls` is a pre-existing
base failure whose assertion is `':aria-pressed="fullscreen"' not found in '<rendered
editor HTML>'`. On the W3 branch the *rendered HTML haystack* printed after "not found in"
now also contains the new Design Lab panel markup — but the **failure reason is identical**
(the fullscreen topbar still lacks the `aria-pressed="fullscreen"` attribute this
pre-existing failing test expects; W3 did not touch fullscreen behavior). Normalising the
assertion to the reason (dropping the rendered-page haystack that legitimately grows with
any added editor UI) yields exactly **0 changed reasons** and **32 identical reasons**.

## The 32 pre-existing base failures (unchanged by W3)
All belong to Ready-Template *recipe/version* contract suites and pre-existing R4/editor
UI contract expectations that already fail at the certified checkpoint, e.g.:
`test_dark_digital_luxury_v2`, `test_dense_marketplace_beraito_v2`,
`test_editorial_jewelry_saremi_v2`, `test_premium_leather_shokolati_v2`,
`test_warm_boutique_lalerokh_v2` (template version drift like `'3' != '2'` and recipe
composition assertions), plus `test_views.FullscreenEditorTests` and a couple of R4
foundation/inspector/gallery/vertical-slice expectations. None are related to Design Lab,
appearance families, the mutation boundary, Theme, or preview.

## Conclusion (Section 28 release condition)
```
W3-only failing tests:                 NONE
Same pre-existing test, changed W3-
  induced failure reason:              NONE
```
The W3 full-suite failure set reduces **exactly** to the certified base's pre-existing
30 failures + 2 errors. Section 28's release condition is satisfied.

---

## Re-verification after Architect-review repair (commit `40661a7`+)

Full `apps.storefront_builder.tests` re-run on the repaired branch:

| | tests run | failures | errors | skipped |
|---|---|---|---|---|
| Certified base `e28b563` | 3160 | 30 | 2 | 4 |
| W3 branch (post-repair) | 3206 | 30 | 2 | 4 |

W3 now adds 46 tests (`3206 = 3160 + 46`; the repair added 9 endpoint round-trip
tests to the original 37).

Failure identity + reason comparison against the same clean base run
(`07b_base_e28b563_full_suite.txt`):

```
W3-ONLY failures:                 0
BASE-only failures:               0
CHANGED pre-existing reasons:     0
SHARED identical failing tests:   32  (30 failures + 2 errors)
```

The repaired W3 branch's full-suite failure set remains **exactly** the certified
base's pre-existing set. Section 28 release condition still satisfied after the repair.



---

## Final re-verification on the repaired head (`a41531f`)

The full suite was re-run on the FINAL head (after the browser-QA endpoint change
that returns `candidate_selections`/`base_selections`), so this evidence reflects
the exact code being submitted:

| | tests run | failures | errors | skipped |
|---|---|---|---|---|
| Certified base `e28b563` | 3160 | 30 | 2 | 4 |
| W3 branch (final `a41531f`) | 3206 | 30 | 2 | 4 |

```
W3-ONLY failures:              0
BASE-only failures:            0
CHANGED pre-existing reasons:  0
SHARED identical failing:      32
```

The repaired W3 branch's full-suite failure set is **identical** to the certified
base's pre-existing set on the final head. Section 28 release condition satisfied.
