# W4C Accessibility Closure Round — Phase B GREEN

Per Section 3 of the directive: production repair of Findings A and B,
strict TDD, ONLY the two authorized template files touched.

## Repair — Listing (Finding A)

`apps/storefront_builder/templates/storefront_builder/sections/product_listing.html`:
added an explicit `aria-label` to all six controls, in BOTH layout
branches (`sidebar_dense` and standard):

| control | aria-label |
|---|---|
| `q` | جستجوی محصولات |
| `category` | دسته‌بندی |
| `brand` | برند |
| `min_price` | حداقل قیمت |
| `max_price` | حداکثر قیمت |
| `sort` | مرتب‌سازی |

The two checkboxes (`discounted`, `in_stock`) were not touched — they
already had an accessible name via their `<label class="plp-check">`
wrapper (never flagged as broken). No visual redesign, no duplicate
markup system, no new form/JS.

## Repair — PDP (Finding B)

`apps/storefront_builder/templates/storefront_builder/sections/product_main.html`:
both `.opt-block .swatch` rendering paths (multi_axis and legacy) gained,
on the SAME existing `<div class="swatch">`:

- `role="button"` `tabindex="0"`
- `:aria-label="v.label"`
- `:aria-pressed="selected[axis.id] === v.id"` (multi_axis) /
  `:aria-pressed="selectedVariantId === v.id"` (legacy) — mirrors the
  existing `active` class condition exactly.
- `@keydown.enter.prevent="selectAxisValue(axis.id, v.id)"` /
  `@keydown.enter.prevent="selectLegacy(v.id)"`
- `@keydown.space.prevent="selectAxisValue(axis.id, v.id)"` /
  `@keydown.space.prevent="selectLegacy(v.id)"`

The existing `@click` handler, `:title`, `:style`, and `:class` were left
untouched. Mouse click and keyboard Enter/Space invoke the exact same
existing Alpine selection function (`selectAxisValue`/`selectLegacy`) —
no second state owner, no new Alpine component (there is still exactly
one `x-data="variantSelector("` in the file). The sibling `.opt-block
.size` `<button>` elements (already correct) were not touched.

Full diff: `31b_accessibility_closure_phaseB_template_diff.txt`.

## Verification

- Standalone `test_w4c_accessibility_production_repair`: **26/26
  passing** (`31c_accessibility_closure_phaseB_standalone_green.txt`) —
  all 24 previously-RED assertions now pass; the 8 regression/invariant
  guards remain green.
- Combined regression run — `test_views` + `test_dark_digital_luxury_v2`
  + `test_phase39_full_site_palette_system` +
  `test_w4c_all50_certification_harness` +
  `test_w4c_accessibility_production_repair` (413 tests total):
  **9 failures + 1 error, all 10 identities pre-existing** in the
  certified Round-2 exact-final-head baseline
  (`24_repair_round2_full_suite_output.txt`) — confirmed by exact
  identity-string grep against that baseline, 10/10 matched, 0 new.
  Full output: `31a_accessibility_closure_phaseB_green_related_suites.txt`.
  None of the 10 pre-existing failures touch `product_listing.html` or
  `product_main.html` (they are `test_views`'s fullscreen-editor
  contract and `test_dark_digital_luxury_v2`'s mobile-nav/recipe
  contracts — unrelated markup, unaffected by this repair).
- `node --check tools/storefront_builder_r4_qa/run.mjs`: PASS
  (harness untouched this phase, re-verified anyway).
- `manage.py check`: 0 issues.
- `makemigrations --check --dry-run`: no changes.
- `git diff --check`: clean.

## Scope confirmation

Only the two authorized template files were modified. No renderer, no
registry, no service, no model, no cart logic, no Theme architecture,
no migration, no harness file (`qa_storefront_builder_r4.py` /
`run.mjs`) touched in this phase.

## Next step

Task #77 — a fresh bounded smoke (`--only editorial_jewelry`, new empty
campaign root) expecting genuine 13/13 PASS, 0 FAIL, 0 BLOCKED, with
`matrix.json` directly verified to show Listing/PDP accessibility_checks
all PASS; then the full fast-gate sequence and an exact-final-source-head
full regression against the same W4B baseline file, then the final
structured report.
