# W5B — Source Diff Summary

Full diff: `git diff feature/phase5-design-expansion..feature/phase5-w5b-mobile-bottom-nav-r4-parity`.

```
 apps/storefront_builder/r4_views.py                              |   7 +
 apps/storefront_builder/services/r4_mutation_service.py          |   9 +-
 .../dashboard/storefront_builder/r4/editor.html                  |  20 +
 apps/storefront_builder/tests/test_phase5_w5b_mobile_bottom_nav_r4_parity.py | 454 +++++++++++
 (+ plan/evidence docs, ~1160 lines, docs-only)
 12 files changed, 1653 insertions(+), 1 deletion(-)
```

## Production code (3 files, 36 lines total)

- **`apps/storefront_builder/services/r4_mutation_service.py`** (+8, -1):
  `_FOOTER_UPDATE_ALLOWED_PATCH_KEYS` gains `"mobile_nav_variant"`;
  `_apply_footer_update()` gains one `if "mobile_nav_variant" in patch:
  candidate["mobile_nav_variant"] = patch["mobile_nav_variant"]` block. No
  other line in this file changed — `validate_footer_config`,
  `apply_footer_variant`, `_dispatch_mutation`'s allowlist, and every other
  mutation applier are byte-for-byte unchanged.
- **`apps/storefront_builder/r4_views.py`** (+7): `_build_global_design_context()`
  gains one new `"mobile_nav_variants"` key, a list comprehension over
  `global_region_registry.list_global_variants(GLOBAL_MOBILE_NAV_REGION)`,
  placed immediately after the existing `footer_variants` entry it mirrors.
- **`apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`**
  (+20): one new `<section data-r4-global-mutation="footer.update">`
  sibling, immediately after the existing Footer section, containing one
  `<select data-r4-global-field="mobile_nav_variant">` populated from
  `global_design.mobile_nav_variants`.

## Zero JavaScript changes

`git diff --stat -- '*.js'` between the base and this branch is empty. The
existing generic delegated `change` handler in `r4_editor.js`
(`field.closest('[data-r4-global-mutation]')`) already covers the new
selector automatically.

## Test code

- **`apps/storefront_builder/tests/test_phase5_w5b_mobile_bottom_nav_r4_parity.py`**
  (+454, new file): 24 tests across 9 classes — read projection, selector
  markup, mutation acceptance/fail-closed, sibling-state isolation, stale-
  write/history round-trip, Draft-Preview/Publish/Public lifecycle, tenant
  isolation, zero-migration sanity, and full registered-variant coverage.
  No other existing test file was modified — the new field slots into the
  existing `footer.update` contract without breaking any prior assumption
  about its allowed patch keys.

## Non-production, not part of this diff summary's risk surface

- Plan + evidence documents under `docs/superpowers/plans/` and
  `docs/qa_evidence/.../w5b_mobile_bottom_nav_r4_parity/`.
- `tools/storefront_builder_r4_qa/w5b_mobile_bottom_nav_r4_parity_qa.mjs`
  (new browser QA script, tooling only, not shipped application code).

## Zero migrations

No model field was added, removed, or altered — `mobile_nav_variant` was
already a key inside the existing `footer_config` JSONField before W5B.
`manage.py makemigrations --check --dry-run` reports "No changes detected".
