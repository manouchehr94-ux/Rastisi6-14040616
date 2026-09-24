# Task 3 — Page Appearance + R4 non-Home + live entry

## Status: 3A/3B/3D/3E COMPLETE and verified below. 3C (Page Appearance inheritance tier) NOT YET DONE — tracked separately, to follow as its own commit per the Master Prompt's explicit "two commits if the page-appearance persisted-state decision is substantial" allowance.

## 3A — Real dashboard entry point for R4

**Decision:** keep `StorefrontLayout.r4_editor_enabled` defaulting to `False` (unchanged) rather than
flipping it globally. R4 does not yet have Container/Cell/media/recovery parity with legacy (Task 7,
not started) — flipping every store to R4-by-default now would expose merchants to a materially
incomplete editor. Instead, added a real, discoverable link from the legacy editor
(`dashboard/storefront_builder/editor.html`) to the R4 route, **conditionally rendered only when
`layout.r4_editor_enabled` is true** — using the `layout` object the legacy editor view already
resolves (zero new query, zero context-processor change, same `STOREFRONT_LAYOUT_MANAGE`
permission gate the whole page is already behind). This closes the audit's "R4 has zero live UI
entry point" finding for any store that opts in via the existing flag, without prematurely exposing
an incomplete editor to every store. By Phase-4 final certification (Task 10), once Task 7 (R4
parity) and Task 9 (legacy retirement) are done, this flag's default can be safely flipped — that
decision is deferred to those later tasks, not made here.

Tests: `test_views.EditorAccessTests.test_r4_editor_link_hidden_when_gate_disabled` /
`test_r4_editor_link_shown_when_gate_enabled` (2 new tests, both pass).

## 3B — Generalize R4 away from Home-only

**Root cause (confirmed exactly as the audit described):** `section_structure_service.py` hardcoded
`StorefrontPage.PageType.HOME` in two places (`_home_page`, `_scoped_section`'s page_type filter);
`r4_views.py::storefront_r4_editor` hardcoded it in three (draft page resolution, library scoping,
preview iframe src); `r4_editor.js` never sent `page_type` on `section.add`.

**Fix:**
- `models.py`: added `StorefrontPage.resolve_page_type(raw)` — the ONE validated PageType input,
  extracted from the legacy editor's own pre-existing `views.py::_resolve_page_type` (which now
  delegates to it) so R4 uses the exact same resolution, not a second copy-pasted branch chain.
- `section_structure_service.py`: `add_section` now takes an explicit, caller-validated `page_type`
  parameter. `_scoped_section` (used by remove/duplicate/move) drops the hardcoded Home filter —
  scoped only by `page__version=draft`, since a `section_id` already uniquely identifies its page;
  requiring a redundant page_type match would add no real safety boundary. Verified this doesn't
  weaken cross-Store scoping (still airtight — dedicated regression test).
- `r4_mutation_service.py`: `_apply_section_add` now requires and validates `mutation["page_type"]`
  against `StorefrontPage.PageType.values`, rejecting with `invalid_page_type` if missing/invalid
  (a mutation is a deliberate action — no silent Home fallback, unlike a page load).
- `r4_views.py::storefront_r4_editor`: resolves `page_type` via `StorefrontPage.resolve_page_type`
  from `?page=`; scopes the "Add Section" library and preview iframe to that page_type; passes
  `page_type`/`page_types` into context.
- `templates/dashboard/storefront_builder/r4/editor.html`: added a page switcher (`<select>`,
  mirroring the legacy editor's own switcher pattern), `data-r4-page-type` on the shell root, fixed
  the previously-hardcoded `?page=home` preview iframe src.
- `r4_editor.js`: `section.add` now reads `page_type` from the shell's `data-r4-page-type` attribute.

Tests: `test_r4_vertical_slice.NonHomePageStructureMutationTests` (6 tests: add/remove/duplicate on
Cart, missing/invalid page_type rejection, cross-Store scoping regression guard) and
`NonHomePageEditorLoadTests` (6 tests: default-to-Home, invalid-defaults-to-Home, Cart page load,
page switcher renders all 6 types, preview iframe targets current page_type, library scoped to
current page_type) — all RED-verified against pre-fix code (stashed and re-ran: 4 failures + 1 error
for the structure-mutation tests; both editor-load-defaulting characterization tests were already
green, protected as regression guards), all GREEN after the fix, 12/12 pass.

## 3D — Collection Index / Collection Detail boundary (Ruling L)

**Finding:** the boundary already holds correctly by construction — `collection_index.html` never
includes `render_rows.html` or consumes `render_items`/`rows`, and both routes already resolve
canonical Global Header/Footer/Appearance via the shared `storefront_shell.html`. No code defect
existed; the audit's finding was about latent risk (a future edit to `collection_index.html` could
easily start consuming those keys, silently leaking Collection Detail's Builder content), not a
live bug.

**Action:** added the explicit code documentation Ruling L requires directly at the
`build_universal_storefront_context` call site in `catalog/views.py::collection_index`, and added
the decisive end-to-end test the audit's structural tests didn't yet cover: publish a marker
section on the shared `PageType.COLLECTION` page, confirm it appears on Collection Detail's
underlying storage but never renders on Collection Index (`CollectionIndexBoundaryTests
.test_editing_collection_detail_section_composition_never_leaks_into_index`), plus an explicit
canonical-shell test (`test_index_uses_canonical_global_header_and_footer`). 5/5 pass (3
pre-existing + 2 new).

## 3E — Listing/Search HTMX fragment context-propagation gap

**Root cause (confirmed exactly as the audit described):** `catalog/views.py::product_list`
returned the HTMX partial (`product_list_results.html`) BEFORE `build_universal_storefront_context`
ran — so the fragment never received `card_settings` (the merchant's `product_listing` section card
override), silently reverting to template defaults on every filter/pagination HTMX swap until the
next full page load.

**Fix:** reordered `product_list` so `build_universal_storefront_context` runs on BOTH the HTMX and
full-page paths through the exact same call (no second fragment renderer, no second context
builder), then added `_product_listing_card_settings(render_items)` — a small helper that extracts
the `product_listing` section's own resolved `settings.card` from the canonical `render_items` list
(the same value the full-page section template already threads into `product_list_results.html`)
and assigns it to `context["card_settings"]` for both paths.

Tests: `test_u5_listing_filter_search.HtmxFragmentCardSettingsPropagationTests` (3 tests: full-page
load applies the override, HTMX listing fragment applies it, HTMX search fragment applies it) — RED
confirmed (stashed the fix, both HTMX tests failed with `style-standard` instead of `style-compact`;
full-page test already passed), GREEN after the fix, 3/3 pass.

## Verification (3A/3B/3D/3E)

- Targeted suites: `test_r4_vertical_slice`, `test_r4_mutation_api`, `test_views`,
  `test_collection_public_views`, `test_u5_listing_filter_search` — **398 tests, 2 failures + 1
  error**, all three matching known pre-existing signatures
  (`test_validate_appearance_config_is_the_validator_boundary`,
  `test_fullscreen_button_is_in_v3_topbar_with_device_and_zoom_controls`,
  `test_fullscreen_state_is_a_pure_css_toggle_not_a_new_route`) — zero new regressions.
- `python manage.py makemigrations --check --dry-run`: no changes detected (3A/3B/3D/3E are pure
  code-path changes — no schema change).
- `git diff --check`: clean.
- Full Phase-3 baseline Run A/B/C re-run verbatim:
  - Run A: **754 tests** (734 baseline + 20 carried forward from Tasks 0-3's own test additions),
    `FAILED (failures=1, skipped=1)` — identical known pre-existing signature.
  - Run B: **121 tests**, `FAILED (failures=2, errors=1)` — identical to baseline.
  - Run C: **77 tests**, `OK` — identical to baseline.
