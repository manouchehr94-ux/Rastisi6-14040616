# Code Review Gate

Ran `/code-review --level high` twice against this round's diff.

## Pass 1 — against `0898c31b..316b7332` (initial repair)

Two findings:

| # | File | Summary | Disposition |
|---|---|---|---|
| 1 | `a8_ready_templates.py` | `parnian_editorial` v3's chosen hero (`editorial_split`) resolves to the same rendered `hero_style` ("split") as `artisan_grain`'s hero (`typographic`), and they also share the same header (`editorial_masthead`), layout (`two_column`), and product_view (`editorial_grid`) — silently recreating the exact "materially indistinguishable above the fold" defect this round exists to close, against a different, unchecked sibling. | **Fixed** — see below |
| 2 | `a8_ready_templates.py` | The independent `_appearance()` hero_style grouping (tall/split/wide) changes as a side effect of the hero-family swap for `laleh_play` (tall->wide) and `parnian_editorial` (tall->split), and this was unverified by any test. | **Fixed** — new explicit assertions added |

### Fix for finding 1

Added `test_no_new_rendered_hero_style_collision_among_all_fifty`, which
reads the REAL rendered `hero_style` off each preset's own built
`pages["home"]` (not a private mapping) rather than comparing raw hero
KEY strings. Proven genuinely RED against the `editorial_split` choice
(the `parnian_editorial`/`artisan_grain` collision) before switching
`parnian_editorial`'s hero to `product_focus`, verified collision-free
against all 50 on both the original and the stricter signature.

This stricter check also surfaced two **pre-existing, out-of-scope**
4-axis near-collisions that predate this round entirely
(`handmade_luxe`/`mist_quiet`, `tower_department`/`harbor_imports`) —
recorded explicitly in the test file
(`_PRE_EXISTING_OUT_OF_SCOPE_4AXIS_COLLISIONS`) as excluded from this
round's "no NEW collision" assertion, not silently fixed, not hidden.
They are not part of the three pairs the Independent Architect
authorized for repair and are left for a separate, future round.

### Fix for finding 2

Added `AppearanceHeroStyleIsIntentionallyRecomputedTests` (3 tests)
pinning the exact `appearance["hero_style"]` value for all three
targets, making the recomputation a verified, intentional part of the
repair rather than an unverified side effect. Per the round's own
Section 5, "major above-fold layout" is an explicitly acceptable
distinguishing axis, so this recomputation was not reverted — the
targets genuinely benefit from it as additional real distinctness on
top of the hero-component swap.

## Pass 2 — against `0898c31b..6074424b` (post-correction)

One finding, already anticipated and pre-authorized by this round's own
Section 19:

> Bumping `green_workshop`/`laleh_play`/`parnian_editorial` to version 3
> drops their real captured static-Gallery screenshots back to the
> abstract SVG placeholder (`resolve_real_screenshot` looks for
> `v3.webp`, but only `v2.webp` exists on disk for these three keys).

This is not a new, unaddressed defect — it is exactly the consequence
Section 19 of this round's directive explicitly anticipated
("STATIC GALLERY — DO NOT REFRESH YET... Record that fact. Do NOT
refresh them in this repair round") and instructed to record, not fix,
this round. Recorded here and in `final_report.md`; the static preview
refresh is deferred to a future, separately-authorized round per the
directive.

## Verification after both passes

`CRITICAL = 0`, `IMPORTANT = 0` remaining unresolved. Both real findings
from Pass 1 were fixed with genuine RED-before-fix proof; the single
Pass 2 finding is a pre-authorized, explicitly-deferred, already-recorded
consequence, not an unresolved defect.
