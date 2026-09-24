# W5C — Implementation Plan Summary

Full plan: `docs/superpowers/plans/2026-09-19-phase5-w5c-ready-template-preview-ux.md`.
This file is the condensed execution record.

## Product goal

Turn the Gallery's two existing "مشاهده..." preview links (both
`target="_blank"`, forcing a new tab) plus the screenshot thumbnail (a
raw-image link) into ONE in-page, large Preview dialog with Desktop/
Tablet/Mobile presentation and a Merchant/Demo data-source toggle — reusing
the existing canonical live-preview route unmodified in behavior.

## Confirmed gaps closed

| Gap | Fix |
|---|---|
| GAP 1 | Both "مشاهده..." links were `target="_blank"` | converted to in-page dialog triggers (real `href` kept as no-JS fallback) |
| GAP 2 | No Desktop/Tablet/Mobile control existed in the Gallery flow | added, mirroring R4's own 1200/768/390 contract independently |
| GAP 3 | Comparing Demo vs Merchant meant two separate tabs | one dialog, one iframe, a data-source toggle that reuses the same iframe |
| GAP 4 | Screenshot thumbnail linked to the raw image, not any preview | now a preview trigger too (per the directive's explicit §7 requirement) |

## What stayed unchanged (verified, not assumed)

- `storefront_template_gallery()` — zero changes; same context, same
  registry iteration (`layout_preset_registry.list_ready_templates()`,
  confirmed 50 at runtime).
- `preset_service.resolve_preset_candidate()`, `build_candidate_render_items`,
  `build_candidate_container_rows`, `store_appearance_global_renderer_template`
  — the shared candidate renderer, untouched.
- `ready_template_live_preview.html` — untouched; its existing Demo/
  Merchant banner text is exactly what browser QA asserts against.
- The Apply `<form>`, replace-content `confirm()`, current-template
  badge, and `template_preview_service` screenshot-fallback authority —
  all untouched.
- `r4_editor.js`/`r4_editor.css` — not touched at all (see the plan's
  §11 for why an independent reimplementation was chosen over a shared
  extraction).

## The one production-logic change (justified, not scope creep)

`storefront_template_live_preview` gained `@xframe_options_sameorigin`.
Required because the view is now legitimately loaded inside an `<iframe>`
for the first time (the Gallery's new dialog); without it, Django's
global `X-Frame-Options: DENY` default blocks every browser from
rendering it framed at all. Mirrors `storefront_preview`'s own identical,
pre-existing override for the exact same reason. See
`preview_authority_chain.md` for the full justification chain.

## Findings from independent code review, fixed before evidence was finalized

Four real defects were found by the `code-review` skill on the first
implementation pass (not present in the plan's original design, all in
the JS/view layer): the missing X-Frame-Options override (above), an
unconditional `preventDefault()` that broke Ctrl/Cmd/Shift-click "open in
new tab," a redundant iframe reload when re-clicking an already-active
data-source button, and a missing keyboard focus trap inside the dialog.
All four fixed; see `code_review.md` for the complete account.

## Test-fixture / pre-existing-test findings during TDD

One pre-existing test,
`test_ready_template_real_previews.py::GalleryRealScreenshotIntegrationTests
::test_screenshot_image_can_be_opened_larger_via_a_plain_non_mutating_link`,
asserted the OLD "screenshot links to the raw static image" behavior from
an earlier phase ("Mission Step 30"). W5C's own directive explicitly
supersedes this (§7: "clicking the screenshot ... should open the
IN-PAGE preview experience"), so the test was updated — renamed to
`test_screenshot_click_opens_the_non_mutating_in_page_live_preview` — to
assert the new, strictly-better-for-the-merchant contract (the screenshot
now opens the real in-page live preview instead of a static image),
while still confirming the href is a plain, non-mutating GET URL. This is
a legitimate behavior upgrade under direct product-requirement authority,
not a weakened assertion — the test still proves "no mutation, no view
logic," just against the new, richer target.

## Deviation from the plan

None beyond the four code-review fixes (which sharpen the plan's own
accessibility/modal-behavior sections rather than contradict them) and
the one pre-existing test update (which the plan's own non-goals section
did not anticipate needing, since it predates knowledge of that specific
stale assertion).

## Evidence directory index

`starting_state.md`, `implementation_plan_summary.md` (this file),
`tdd_red.txt`, `tdd_green.txt`, `preview_authority_chain.md`,
`non_mutation_proof.md`, `accessibility_review.md`, `focused_tests.txt`,
`browser_qa.md`, `code_review.md`, `full_suite_identity_comparison.md`,
`source_diff.md`, `final_report.md`.
