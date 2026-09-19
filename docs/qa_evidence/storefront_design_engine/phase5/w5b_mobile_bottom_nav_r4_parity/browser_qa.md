# W5B — Browser QA (Real Mobile-Viewport Merchant Journey)

Script: `tools/storefront_builder_r4_qa/w5b_mobile_bottom_nav_r4_parity_qa.mjs`
(reuses the existing `tools/storefront_builder_r4_qa/` conventions — same
Chromium/`playwright-core` resolution, same `--host-resolver-rules=MAP *
127.0.0.1` approach, "Python owns Store-state setup, Node owns only
browser assertions" — no second harness).

Raw console output: `browser_qa_console.txt`. Structured result:
`browser_qa_results.json`.

## Result

**16/16 PASS.** (Steps are numbered per the directive's 18-step journey;
steps 1-9 and 11/13-18 map 1:1 onto the directive's numbering — there is
no step "10" or "12" result line because those are the Undo/Redo actions
themselves, not separate assertions, matching the directive's own
phrasing of "Undo restores previous" / "Redo restores changed" as the
verifiable outcomes.)

## Setup

- Fixture: `/tmp/w5a-evidence/w5b_qa_setup.py` (QA-scratch, not committed,
  matching the W5A-round convention) — creates a Store (`w5b-qa-store`,
  admin host `w5b-qa.rastisi.localhost`) with a Draft explicitly synced to
  `mobile_nav_variant="hidden"`, publishes it, and creates a fresh
  post-publish Draft for the merchant's editing session; also creates a
  second, entirely untouched Store (`w5b-qa-store-2`, admin host
  `w5b-qa-2.rastisi.localhost`) for the step-17 fresh-Draft scenario.
- Django dev server: `127.0.0.1:8765`, started only after the exact-source
  full regression suite process had fully exited (confirmed via `ps`), per
  the SQLite-contention lesson from the W5A round.
- Real login (real form, real CSRF, real session) on both admin hosts —
  session cookies are host-scoped, so the second Store's scenario (step 17)
  performs its own separate login, per the same lesson.

## Journey and results

| # | Step | Result |
|---|---|---|
| 1 | R4 Builder opens | PASS |
| 2 | Global Design panel opens | PASS |
| 3 | "ناوبری پایین موبایل" label present | PASS |
| 4 | Selector options are registry-driven (all 9 present) | PASS |
| 5 | `footer.update` mutation with `mobile_nav_variant` accepted (200, `ok`, revision advanced) | PASS |
| 6 | Save completes — Undo becomes enabled after reload (see note below) | PASS |
| 7 | Preview switched to mobile device mode | PASS |
| 8 | Preview shows the new Bottom Nav variant (`four_item`) | PASS |
| 9 | Footer variant unchanged | PASS |
| 10/11 | Undo restores the previous (`hidden`) Bottom Nav | PASS |
| 12/13 | Redo restores the changed (`four_item`) Bottom Nav | PASS |
| 14 | Public storefront unchanged before Publish | PASS |
| 15 | Publish clicked, editor reloaded | PASS |
| 16 | Public storefront reflects the new Bottom Nav after Publish | PASS |
| 17 | A fresh Draft (second, untouched Store) defaults to `hidden` — mobile Preview shows no Bottom Nav markup | PASS |
| 18 | A stale mutation is rejected (409, `stale_revision`) | PASS |

## Two script-authoring corrections made during this run (script bugs, not production bugs)

Both fixes were to the QA script only; no production code changed as a
result of this section.

1. **Step 6 — Undo-enabled check needed a page reload.** The first run
   showed the mutation succeeding (Preview updated correctly at step 8)
   but the `#r4UndoButton` never became enabled, and the later Undo click
   timed out. Direct source inspection
   (`apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`,
   `{% if not history.can_undo %}disabled{% endif %}`, and
   `r4_editor.js`'s `refreshGlobalDesignAndPreview()`, which only swaps
   `#r4GlobalDesign`'s own `innerHTML`) confirmed this is **pre-existing
   behavior for every Global Design field**, not specific to Bottom
   Navigation: the toolbar's Undo/Redo buttons are rendered server-side
   only and are never toggled by client-side JS after an in-place Global
   Design save — only a full page reload (or the Undo/Redo actions'
   own built-in reload) picks up the fresh `history.can_undo`/`can_redo`
   state. The script now reloads the page after the mutation before
   checking/using Undo, matching how a real merchant would see the same
   state on their next reload. No JS or template change was made or
   needed — W5B's field behaves identically to `footer_variant` and every
   other existing Global Design field in this respect.
2. **Step 13 — Redo check raced the reloaded preview iframe.** Undo/Redo
   each trigger a full top-level page reload on success, which replaces
   the preview `<iframe>` with a brand-new frame; checking its `content()`
   immediately (before that frame finished its own load) intermittently
   raced ahead of the real state. Fixed by polling for the new preview
   frame to reach `domcontentloaded` before reading its content
   (`waitForPreviewFrameReady`), applied consistently after every
   navigation-triggering step (6, 10/11, 12/13).
3. **Step 18 — the "stale" `base_revision` was not actually stale.**
   The original script hardcoded `base_revision: 0`; after Publish (step
   15), the editor is on a brand-new post-publish Draft whose own
   revision genuinely starts at 0, so `0` was the *correct* current
   revision, not a stale one — the mutation was accepted (200) instead of
   rejected. Fixed by reading the real current revision
   (`window.RastiSiR4.revision`) from the page, spending it with one
   genuine mutation (advancing the server past it), then replaying that
   now-stale captured revision — which is correctly rejected with `409
   stale_revision`.

## Conclusion

Every step of the required 18-step real mobile-viewport merchant journey
passes against the actual, running R4 Builder — registry-driven options,
independent-field mutation acceptance, sibling Footer-variant isolation,
Undo/Redo round-trip, Draft-Preview/Public lifecycle around Publish, a
second Store's fresh-Draft `hidden` default, and stale-revision rejection
are all demonstrated live, not just via Django `TestCase` assertions.
