# P5-W5C — Ready Template Preview UX — Final Report

## STATUS: COMPLETE

## Starting base

- Official integration branch: `feature/phase5-design-expansion`
- Exact HEAD at authorization: `3125a3250b1284ba216ac8c125257b7e48aaf0bf`
  (W5B merge commit `5e5d0180` + W5B post-merge checkpoint)

## Feature branch

`feature/phase5-w5c-ready-template-preview-ux`

## HEAD SHAs

- **Final production source HEAD:** `75b08c53` (`feat(phase5): add
  in-gallery Ready Template device preview`) — no production file
  changed in any commit after this one.
- **Final evidence/branch HEAD:** `a9073391` (`docs(phase5): execute
  W5C browser QA, fix QA-fixture-only bug`)

## Ready Template count

**50 / 50** — `layout_preset_registry.list_ready_templates()`, confirmed
by direct execution and by the browser QA's own card-count assertion
(`cardCount=50, expected=50`). No pagination, no industry filtering, no
hidden templates.

## New preview routes / renderers / mutation types / migrations

**0 / 0 / 0 / 0.** `dashboard:storefront-builder-template-live-preview`
remains the only route; `ready_template_live_preview.html` and the
shared candidate renderer are untouched; `template_gallery_preview.js`
makes zero `fetch`/`XMLHttpRequest`/form-submission calls; `manage.py
makemigrations --check --dry-run` reports "No changes detected" at the
final HEAD.

## Contract checks (TDD, 23 tests across 5 classes + 1 pre-existing test updated)

All 23 new tests PASS, all pre-existing regression guards PASS (24/24
total in the new module, `test_ready_template_real_previews.py`'s
updated test also PASS). Full table and per-contract mapping in
`implementation_plan_summary.md`; RED/GREEN evidence in `tdd_red.txt`/
`tdd_green.txt`.

| Gate | Result |
|---|---|
| IN-PAGE PREVIEW DIALOG | PASS |
| SINGLE IFRAME | PASS |
| CANONICAL LIVE PREVIEW ROUTE | PASS |
| MERCHANT DATA MODE | PASS |
| DEMO DATA MODE | PASS |
| MERCHANT→DEMO SAME IFRAME | PASS |
| DEMO→MERCHANT SAME IFRAME | PASS |
| DESKTOP PREVIEW | PASS (natural width, no fixed width/transform) |
| TABLET PREVIEW | PASS (width 768, exact) |
| MOBILE PREVIEW | PASS (width 390, exact) |
| PREVIEW MUTATES DRAFT | NO (verified against the DB directly, before/after byte-identical) |
| DRAFT ID PRESERVED | PASS |
| EDIT REVISION PRESERVED | PASS |
| TEMPLATE PROVENANCE PRESERVED | PASS |
| HISTORY COUNT PRESERVED | PASS |
| TENANT ISOLATION | PASS |
| INVALID TEMPLATE | 404 |
| STATIC SCREENSHOT FALLBACK | PASS (untouched) |
| CURRENT TEMPLATE BADGE | PASS (untouched) |
| EXISTING APPLY PATH | PRESERVED (byte-for-byte unchanged) |
| REPLACE-CONTENT CONFIRMATION | PRESERVED |
| ESC CLOSE | PASS |
| FOCUS RESTORE | PASS |
| ACCESSIBLE DIALOG | PASS (`role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap) |
| ALL 50 PREVIEW TRIGGERS | PASS |

## Focused/exact-source gates

- Focused sanity sweep (280 tests: Gallery, live-preview Demo/Merchant,
  real screenshots, acceptance batch 3, Ready Template catalog, preset
  service/candidate preview, store resolution, the new W5C suite): 1
  failure, confirmed byte-for-byte identical to the accepted baseline
  identity (`test_header_footer_variant_labels_shown_for_updated_preset`).
- `manage.py check`: **clean, 0 issues.**
- `manage.py makemigrations --check --dry-run`: **"No changes detected."**
- `git diff --check`: **clean.**

## Browser QA

**25/25 PASS** — real merchant journey against the live Gallery
(`browser_qa.md`, `browser_qa_console.txt`, `browser_qa_results.json`,
`screenshots/`): 50/50 cards wired, one shared dialog/iframe reused
across retargeting/device/data-source changes, real Tablet/Mobile
viewport widths inside the iframe's own document (768/390 exact), a
genuine visible Merchant-vs-Demo content difference, keyboard
reachability + focus trap, and Draft non-mutation verified directly
against the database before/after the whole session.

## Independent code review

**CRITICAL: 0. IMPORTANT: 0** (final state, after fixes). First pass
found 4 real defects (missing `@xframe_options_sameorigin`, a
modifier-click regression, a redundant-reload bug, a missing focus trap)
— all fixed; re-review found nothing further. Full account and the
required checklist verification: `code_review.md`.

## Django check

Clean, 0 issues, at final HEAD.

## Full regression (exact-source)

- Command: `python manage.py test apps.storefront_builder.tests --settings=shop_core.settings -v 2`
- **Result: `Ran 3525 tests in 3965.271s` — `FAILED (failures=30, errors=2, skipped=1)`.**
- Baseline: 3502 tests, 30 failures, 2 errors, 1 skipped (accepted W5B
  figure).
- Test count increased by exactly 23 (3502 → 3525), matching the 23 new
  W5C tests, all of which pass.

## Identity-diff counts

- **NEW FAILURE/ERROR IDENTITIES: 0**
- **MISSING UNEXPLAINED HISTORICAL IDENTITIES: 0**
- **CHANGED HISTORICAL FAILURE/ERROR REASONS: 0** (all 32 matched
  failure/error blocks byte-for-byte identical to baseline, including
  full tracebacks — see `full_suite_identity_comparison.md`)

## 704-cell Ready Template campaign

**NOT RUN** — renderer/Ready-Template/candidate-construction architecture
was not touched by this diff (the one production-logic change,
`@xframe_options_sameorigin`, only changes an HTTP response header on an
already-existing, already-non-mutating view), per the directive's policy.

## Architectural duplication count

**0.** `dashboard:storefront-builder-template-live-preview` remains the
sole preview route; the 1200/768/390 device-presentation contract is an
independently-reimplemented design-constant convention (see the plan's
§11), not a shared runtime authority; the Apply path is untouched.

## Source diff

3 production/non-test files, ~106 net lines (`template_gallery.html`
+90/-8, `template_gallery_preview.js` new file +199,`views.py` +8). One
new test file (+411 lines, 23 tests) and one pre-existing test updated
(+26/-11, justified by this phase's own product requirement superseding
an earlier one). Zero migrations. Full breakdown: `source_diff.md`.

## PR

Opened after this report — see the push/PR step following this
document's commit.

## W5D started

**NO.**

## Worktree

**Clean** at final HEAD `a9073391` (confirmed via `git status
--porcelain`).

## Final status

**COMPLETE.** All required gates pass: 24/24 new contract tests (23 in
the new module + the updated pre-existing one), 0 new/missing/changed
regression identities against the accepted baseline, 25/25 browser QA
with live DB-verified non-mutation, 0 CRITICAL/IMPORTANT code-review
findings (after fixing 4 real defects the first pass found), clean
Django check, zero migrations, zero architectural duplication.

STOP. Do not merge. Do not start W5D. Return for Independent Architect
review.
