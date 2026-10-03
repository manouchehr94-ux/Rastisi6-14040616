# W5C — Merge Checkpoint

Recorded per the Independent Architect's "P5-W5C FINAL MERGE + POST-MERGE
CHECKPOINT" directive, immediately after PR #15 was merged into
`feature/phase5-design-expansion`.

## Pull request

- **PR:** #15 — "P5-W5C: Ready Template Preview UX (in-page Desktop/Tablet/
  Mobile, Demo/Merchant)"
- **State:** MERGED / CLOSED

## Anchor SHAs

- **Approved integration base (pre-W5C, official W5B integration HEAD):**
  `3125a3250b1284ba216ac8c125257b7e48aaf0bf`
- **Approved PR head:** `97191d2d666d64dc4bd6426956d966a97372d4cb`
- **Production source head:** `868e0c0badac13b30f0cb9efdd3e3ed5a1d1e9ea`
- **Exact-source full-regression head:** `bfcedb96693602f9ff21e7c8c1b105631608a2b5`
- **Merge commit:** `2943d1247b5a2bfff241b6d644fad957e4fb567b`

All four anchor SHAs are confirmed ancestors of the merge commit
(`git merge-base --is-ancestor <anchor> 2943d1247b5a2bfff241b6d644fad957e4fb567b`
— all four PASS).

## Merge-tree integrity

- `git diff 97191d2d666d64dc4bd6426956d966a97372d4cb..2943d1247b5a2bfff241b6d644fad957e4fb567b`
  → **EMPTY.**
- `git diff bfcedb96693602f9ff21e7c8c1b105631608a2b5..2943d1247b5a2bfff241b6d644fad957e4fb567b -- apps/`
  → **EMPTY.**

The merge introduced no source content beyond exactly what PR #15's
approved head already contained. No production or test source has
changed since the exact-source full-regression head `bfcedb96`.

## Architecture

- Ready Template count: **50**
- Canonical Preview route count: **1** (`dashboard:storefront-builder-template-live-preview`,
  `storefront-builder/templates/<slug:key>/preview/`)
- New preview routes: **0**
- New renderers: **0**
- New mutation types: **0**
- New migrations: **0**
- Preview iframe: **one shared `<iframe>`, reused across retargeting/
  device/data-source changes** (`template_gallery_preview.js`)
- Existing Apply path: **preserved unchanged** (same endpoint, same
  replace-content confirmation, same current-template badge)
- No second Ready Template authority introduced

## Preview lifecycle

- GET-only (`@require_GET`): **PASS** (POST → 405 in both modes, confirmed
  by `PreviewMethodContractTests`)
- Merchant mode POST: **405**
- Demo mode POST: **405**
- Merchant mode, no Draft: **fail-closed 404** (no bootstrap)
- Demo mode, no Draft: **fail-closed 404** (no bootstrap)
- Preview auto-creates a Draft: **NO** (both modes use the non-creating
  `layout_service.get_existing_draft`)
- Merchant Preview mutation: **NO**
- Demo Preview mutation: **NO**

Confirmed by direct source inspection of the merged
`apps/storefront_builder/views.py`: `storefront_template_live_preview`
carries exactly `@require_GET`, `@staff_required`,
`@permission_required(STOREFRONT_LAYOUT_MANAGE)`,
`@xframe_options_sameorigin`; both the Merchant and Demo branches call
`layout_service.get_existing_draft(...)` and raise `Http404` when it
returns `None`. The Golden Reference seeding command
(`apps/stores/management/commands/apply_golden_reference_storefront.py`)
leaves a fresh Draft after Publish via the canonical `layout_service`
lifecycle (`layout_service.get_or_create_draft(store)` as its Step 3,
confirmed present in the merged source).

## UX

- In-page Preview (no more `target="_blank"`/raw-image link): **PASS**
- Merchant/Demo data mode toggle: **PASS**
- Desktop presentation: **PASS**
- Tablet: iframe document `window.innerWidth` = **768** (exact)
- Mobile: iframe document `window.innerWidth` = **390** (exact)
- Escape closes dialog (focus in parent document): **PASS**
- Escape closes dialog (focus inside the same-origin preview iframe):
  **PASS**
- Focus restored to the triggering element on close: **PASS**
- Tab/Shift+Tab focus trap: **PASS**
- 50/50 Ready Template preview triggers wired: **PASS**

## Certification references (NOT re-run at this checkpoint)

- **Browser QA certification:** 28/28 PASS (reference only — see
  `browser_qa.md`'s "Round 2" section). Merchant Draft and Demo Draft both
  confirmed byte-identical before/after across the full session.
- **Full-suite regression certification:** 3531 tests / 30 historical
  failures / 2 historical errors / 1 skip (reference only — see
  `full_suite_identity_comparison.md`'s "Round 2" section). 0 new, 0
  missing, 0 changed failure/error identities against the accepted
  baseline.
- **704-cell Ready Template campaign:** NOT RUN (no renderer/candidate-
  construction architecture touched by this diff or its repair).

## Post-merge lightweight gates (this checkpoint)

Run against the merged, fast-forwarded `feature/phase5-design-expansion`
at `2943d1247b5a2bfff241b6d644fad957e4fb567b`:

- `test_phase5_w5c_ready_template_preview_ux`: **29/29 PASS**
- `test_task2_live_demo_template_preview`: **20/20 PASS** (0
  failures/errors — no new failures relative to the accepted historical
  identity)
- `manage.py check`: **PASS** ("System check identified no issues")
- `manage.py makemigrations --check --dry-run`: **PASS** ("No changes
  detected")
- `git diff --check`: **PASS** (no whitespace errors)

The 3531-test full suite, the 704-cell campaign, and the full Browser QA
session were deliberately **NOT** rerun at this checkpoint, per the
directive — the merge-tree integrity checks above already prove the
merged tree is byte-identical to the already-certified PR head and
exact-source regression head.

## Architectural duplication

**0.** No second preview route, renderer, mutation type, or migration was
introduced by W5C or its repair. R4's own device-switcher
(`r4_editor.js`/`r4_editor.css`) remains untouched throughout.

## W5D

**NOT STARTED.**
