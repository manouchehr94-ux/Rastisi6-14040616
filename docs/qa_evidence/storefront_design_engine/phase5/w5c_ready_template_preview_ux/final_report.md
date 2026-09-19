# P5-W5C — Ready Template Preview UX — Final Report

## STATUS: COMPLETE

**Superseded by round 2 (Independent Architect repair) — see the
section near the end of this document for the current, authoritative
metadata and results.** This document is kept in place rather than
rewritten from scratch so the round-1 record stays intact.

## Starting base

- Official integration branch: `feature/phase5-design-expansion`
- Exact HEAD at authorization: `3125a3250b1284ba216ac8c125257b7e48aaf0bf`
  (W5B merge commit `5e5d0180` + W5B post-merge checkpoint)

## Feature branch

`feature/phase5-w5c-ready-template-preview-ux`

## HEAD SHAs (round 1 — superseded, see round 2 below)

- **Round-1 production source HEAD:** `75b08c53` (`feat(phase5): add
  in-gallery Ready Template device preview`).
- **Round-1 evidence/branch HEAD:** `a9073391` (`docs(phase5): execute
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

**PR #15** — https://github.com/manouchehr94-ux/Rastisi6-14040616/pull/15
— state: **OPEN**, not draft, not merged, `mergeable_state: clean`.
Head `55fd1384`, base `feature/phase5-design-expansion` at exact SHA
`3125a3250b1284ba216ac8c125257b7e48aaf0bf` (unchanged since W5C
authorization).

## W5D started

**NO.**

## Worktree

**Clean** at final HEAD `55fd1384` (confirmed via `git status
--porcelain`).

## Final status (round 1)

**COMPLETE.** All required gates pass: 24/24 new contract tests (23 in
the new module + the updated pre-existing one), 0 new/missing/changed
regression identities against the accepted baseline, 25/25 browser QA
with live DB-verified non-mutation, 0 CRITICAL/IMPORTANT code-review
findings (after fixing 4 real defects the first pass found), clean
Django check, zero migrations, zero architectural duplication.

---

# Round 2 — Independent Architect repair (AUTHORITATIVE)

## P5-W5C INDEPENDENT ARCHITECT REPAIR: COMPLETE

**PR:** #15 — https://github.com/manouchehr94-ux/Rastisi6-14040616/pull/15

**PRE-REPAIR HEAD:** `2ebdc38ea868ceb5eae6a6696560cc4835fe6410`

**FINAL PRODUCTION SOURCE HEAD:** `868e0c0b` (`fix(phase5): W5C repair —
leave a fresh Draft after golden reference publish` — no production
file changed in any commit after this one)

**FINAL EVIDENCE HEAD:** `fb528c8a` (`docs(phase5): record W5C repair
exact-source full regression identity comparison` — this document's own
PR-number-correction commit, added after this report's own commit, is
the true final branch HEAD; see the chat report for that exact SHA,
avoiding the self-referential loop of a document naming its own commit)

**PREVIEW METHOD:** GET-ONLY (`@require_GET` added; a POST now returns a
controlled 405, proven by `PreviewMethodContractTests`)

**MERCHANT POST:** 405 (`test_merchant_preview_post_is_405`)

**DEMO POST:** 405 (`test_demo_preview_post_is_405`)

**DEMO STORE WITHOUT DRAFT:** 404 (`test_demo_preview_without_a_draft_404s_and_creates_nothing`
— and proven to create ZERO `StorefrontLayout`/`StorefrontLayoutVersion`/
history rows, not just a status-code check)

**DEMO DRAFT AUTO-CREATED (by Preview itself):** NO — Demo mode now uses
`get_existing_draft` exactly like Merchant mode; the canonical Demo
Store's Draft is instead ensured by the (also repaired)
`apply_golden_reference_storefront` seeding command, a real
platform/operator action, never by a GET request to Preview.

**SEEDED DEMO PREVIEW MUTATES DEMO DRAFT:** NO — proven twice: at the
Django/DB level (`SeededDemoPreviewNonMutationTests`, including 3
repeated loads) and at the browser level against the REAL seeded Demo
Draft (`w5c_demo_draft_before.json` / `w5c_demo_draft_after.json`,
byte-identical).

**MERCHANT PREVIEW MUTATES MERCHANT DRAFT:** NO — proven at the Django/DB
level (pre-existing + `MerchantPreviewNoBootstrapRegressionTests`) and at
the browser level (`w5c_draft_before_repair.json` /
`w5c_draft_after_repair.json`, byte-identical).

**SINGLE IFRAME:** PASS (unchanged from round 1 — `frameCount:1`
throughout the repaired browser session).

**ESC FROM PARENT DIALOG:** PASS.

**ESC WHILE FOCUS IS INSIDE IFRAME:** PASS — a genuinely separate
browser-QA test: focus verified INSIDE the iframe's own document from
both the parent's and the iframe's own perspective before pressing
Escape.

**FOCUS RESTORE:** PASS (both Escape paths restore focus to the exact
Gallery trigger that opened the dialog).

**TABLET WIDTH:** 768 (exact, measured inside the iframe's own document).

**MOBILE WIDTH:** 390 (exact, measured inside the iframe's own document).

**BROWSER QA:** 28/28 PASS (`browser_qa.md`'s round-2 section,
`browser_qa_console_repair.txt`, `browser_qa_results_repair.json`).

**CODE REVIEW:**
CRITICAL 0
IMPORTANT 0
(Fresh independent pass over the repair diff itself found 1 real
additional defect — Demo Preview was broken out-of-the-box because no
production path created a Demo Draft after `apply_golden_reference_
storefront` publishes — fixed; 2 further findings considered and
documented as deliberate, in-scope-compliant non-changes. See
`code_review.md`'s round-2 section.)

**DJANGO CHECK:** PASS

**MIGRATIONS:** 0

**FULL SUITE EXACT-SOURCE HEAD:** `bfcedb96`

**FULL SUITE TOTAL:** 3531

**HISTORICAL FAILURES:** 30

**HISTORICAL ERRORS:** 2

**SKIPS:** 1

**NEW FAILURE/ERROR IDENTITIES:** 0

**CHANGED HISTORICAL REASONS:** 0

**704 CAMPAIGN:** NOT RUN (no renderer/Ready-Template/candidate-
construction architecture touched by this repair)

**NEW PREVIEW ROUTES:** 0

**NEW RENDERERS:** 0

**ARCHITECTURAL DUPLICATION:** 0

**PR STATE:** OPEN + UNMERGED

**W5D STARTED:** NO

**FINAL WORKTREE CLEAN:** YES

**FINAL STATUS: READY FOR INDEPENDENT ARCHITECT W5C RE-REVIEW**

STOP.

Do not merge.
Do not start W5D.
