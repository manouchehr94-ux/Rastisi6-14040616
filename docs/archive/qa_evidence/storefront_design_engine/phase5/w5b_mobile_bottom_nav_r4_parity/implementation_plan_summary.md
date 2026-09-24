# W5B — Implementation Plan Summary

Full plan: `docs/superpowers/plans/2026-09-19-phase5-w5b-mobile-bottom-nav-r4-parity.md`.
This file is the condensed execution record: what the plan said to do, and what
was actually done, so the two can be checked against each other in one place.

## Product goal

Expose the already-existing `GLOBAL_MOBILE_NAV_REGION` capability as a normal
merchant-facing R4 Global Design control. W5B does not create Bottom
Navigation — it closes the one missing R4 merchant-editing vertical slice for
a region that already has a full registry, renderer set, validation path, and
a working R3 (legacy editor) selector.

## Confirmed gaps closed (source-verified before any code was written)

| Gap | Location | Fix |
|---|---|---|
| GAP 1 | `_FOOTER_UPDATE_ALLOWED_PATCH_KEYS` (r4_mutation_service.py) lacked `mobile_nav_variant` | added to the frozenset |
| GAP 2 | `_apply_footer_update()` never read `patch["mobile_nav_variant"]` into `candidate` | added the one-line merge |
| GAP 3 | `_build_global_design_context()` (r4_views.py) had no `mobile_nav_variants` projection | added, registry-driven |
| GAP 4 | `r4/editor.html` had no merchant-facing selector | added one new `<section>` + `<select>` |

## What stayed unchanged (verified, not assumed)

- `layout_service.validate_footer_config()` — already validated `mobile_nav_variant`.
- `appearance_authority_service.apply_footer_variant()` — already accepted
  `mobile_nav_variant` independently of `footer_variant`.
- `_apply_footer_update()`'s call to `apply_footer_variant(...)` — already
  passed `mobile_nav_variant` on every save; W5B only made the value
  changeable, not the sync call itself.
- `r4_editor.js` — zero lines changed; the existing generic
  `data-r4-global-field`/`data-r4-global-mutation="footer.update"` delegated
  handler picked up the new selector with no adaptation needed.
- `preset_service.reset_footer_to_baseline()` — already resets
  `mobile_nav_variant` as part of the whole `footer_config` baseline; no
  separate reset control was added.
- Preview/Public renderers (`preview.html`, `ready_template_live_preview.html`,
  the public storefront path) — already resolved `mobile_bottom_nav_template`
  from the version being rendered, unconditionally.
- The 9-variant registry (`GLOBAL_MOBILE_NAV_REGION`), its renderer templates,
  and the 704-cell Ready Template certification — untouched.

## Actual production diff (matches the plan's "exact vertical slice" exactly)

3 files, 36 lines: `r4_mutation_service.py` (+8/-1), `r4_views.py` (+7),
`r4/editor.html` (+20). See `source_diff.md` for the full breakdown. Zero
JavaScript changes, zero migrations, zero new registry/renderer/mutation-type
entries.

## Deviation from the plan

None. The implementation matches the plan's exact vertical slice; no
unexpected adaptation was required anywhere in the chain (in particular, no
JS change was needed, confirming point 7 of the plan's existing-authority
verification).

## Test-fixture bugs found and fixed during TDD (test code only, not production)

Three iterations of the new test file had fixtures that wrote raw
`footer_config` dict keys without syncing the typed Store Appearance
manifest via `apply_footer_variant()` — inconsistent with how every real
save path behaves. All three were fixture bugs, not production bugs or
weakened assertions; see `sibling_isolation.md` and `tdd_red.txt`/
`tdd_green.txt` for the full account.

## Evidence directory index

`starting_state.md`, `implementation_plan_summary.md` (this file),
`tdd_red.txt`, `tdd_green.txt`, `authority_chain.md`, `sibling_isolation.md`,
`focused_tests.txt`, `browser_qa.md`, `code_review.md`,
`full_suite_identity_comparison.md`, `source_diff.md`, `final_report.md`.
