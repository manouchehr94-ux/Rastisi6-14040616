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

## Conclusion (round 1)

Every step of the required 18-step real mobile-viewport merchant journey
passes against the actual, running R4 Builder — registry-driven options,
independent-field mutation acceptance, sibling Footer-variant isolation,
Undo/Redo round-trip, Draft-Preview/Public lifecycle around Publish, a
second Store's fresh-Draft `hidden` default, and stale-revision rejection
are all demonstrated live, not just via Django `TestCase` assertions.

---

# Round 2 — Independent Architect browser-evidence repair

The Independent Architect's review of PR #14 accepted the production
implementation (CRITICAL 0, IMPORTANT 1, BLOCKING MINOR 2 — all three
findings against round 1's **browser evidence**, not the production code).
This section documents that repair. Round 1's record above is preserved
unmodified, per the repair directive's explicit instruction not to rewrite
or erase it.

Raw console output: `browser_qa_console_repair.txt`. Structured result:
`browser_qa_results_repair.json`. Screenshots: `screenshots/`.

**Repair scope: QA script + evidence/docs only.** No production file, no
Django test file, and no migration was touched — confirmed by `git diff
--check` and a file-list diff against the pre-repair PR head (see
`final_report.md`).

## The four original defects

1. **Desktop/default viewport incorrectly described as a "real mobile
   viewport."** The script opened both the admin and public browser
   contexts with `browser.newContext({ baseURL: ... })` — no `viewport`,
   `isMobile`, or `deviceScaleFactor`. The storefront's own CSS
   (`apps/storefront_builder/static/css/storefront_builder.css`) makes
   viewport width the ONE thing that gates Bottom Nav visibility:
   ```
   .gmn,.gmn-spacer{display:none}
   @media(max-width:680px){ .gmn{display:block; ...} ... }
   ```
   so a check that never actually ran at `<= 680px` proved nothing about
   mobile rendering, regardless of what markup existed in the DOM.
2. **The Public-after-Publish check proved markup presence, not mobile
   visibility.** `publicAfterHtml.includes('data-mobile-nav="four_item"')`
   is a raw-HTML substring match; it says nothing about `display`,
   bounding box, or the actual browser context's viewport width.
3. **The Footer-sibling assertion was logically too weak.**
   `footerVariantValue === 'legacy_default' || footerVariantValue.length >
   0` — the second clause makes almost any non-empty Footer variant value
   pass, including one that had genuinely changed.
4. **The "registry-driven options" assertion only enforced 3 of the 9
   variants the evidence prose claimed were verified** (`hidden`,
   `four_item`, `floating_dock`), even though the console happened to
   print all 9.

## Fixes applied (QA script only)

1. **Draft Preview mobile viewport**: confirmed by direct source read
   (`r4_editor.js`'s device switcher, `r4_editor.css`) that
   `[data-r4-device="mobile"]` already resizes the SAME `#r4PreviewFrame`
   iframe to a genuine `390px`-wide CSS box (`data-mobile-viewport-width
   ="390"` in `editor.html`) — not a second mechanism. The script now
   explicitly asserts `window.innerWidth <= 680` **inside that iframe's
   own document** after every device-mode switch, rather than trusting
   the topbar button's `aria-pressed` state alone.
   **Public storefront mobile viewport**: the public page is a plain
   top-level page (no iframe/device-switcher wrapper), so its own browser
   context is now opened with a real `viewport: {width: 390, height:
   844}` — a deterministic, unemulated viewport (no UA/branding spoofing),
   per the directive's preferred shape.
2. **Real DOM/computed-style visibility checks**, added as a shared
   `checkMobileNavVisibility()` helper used for both Draft Preview and
   Public: markup presence (`[data-mobile-nav="<variant>"]` exists),
   `getComputedStyle(el).display !== 'none'`, a non-zero
   `boundingBox()`, the `.gmn-bar` nav element's own Playwright
   `isVisible()`, and a rendered `.gmn-item` count (`>= 3`). Applied at
   Draft Preview (step 8), Redo (step 13), and Public-after-Publish (step
   16) — never source-HTML string matching alone. A parallel
   `checkMobileNavAbsent()` helper (no `[data-mobile-nav]` element at all)
   is used for the `hidden` variant's true no-op case (Undo → step 11,
   fresh second-Store Draft → step 17), since
   `.../global_mobile_nav/hidden.html` renders nothing regardless of
   viewport.
3. **Footer-variant before/after comparison**: `footerVariantBefore` is
   now captured right after the registry-options check (step 4b), before
   the Bottom-Nav-only mutation; `footerVariantAfter` is captured right
   after (step 9's data), and the assertion is exact equality
   (`footerVariantBefore === footerVariantAfter`), with both values
   recorded in evidence.
4. **Exact 9-of-9 registry comparison**: the Python fixture
   (`/tmp/w5a-evidence/w5b_qa_setup.py`) now derives the expected variant
   keys directly from `global_region_registry.list_global_variants(
   GLOBAL_MOBILE_NAV_REGION)` — the SAME canonical registry the
   production read-projection uses — and prints them as
   `EXPECTED_MOBILE_NAV_VARIANTS=...`, which is passed into the QA
   manifest's `expected_mobile_nav_variants` array. The script diffs the
   actual selector's option values against that registry-derived list and
   requires `missing = []` AND `unexpected = []` AND `actualCount ===
   expectedCount (9)`. No second hardcoded 9-key list exists anywhere in
   the QA script.

## A fifth defect found BY the strengthened checks themselves

Making the Redo assertion a real visibility check (fix #2 above)
immediately caught a genuine gap in the QA script's own journey, not
previously visible under the old markup-only check: **Undo and Redo each
trigger a full `window.location.reload()`** (confirmed in `r4_editor.js`),
which resets the server-rendered device-switcher state back to `desktop`
— so after Redo's reload, the preview iframe was back at full (>680px)
width, and the Bottom Nav markup, though present in the DOM (server-
rendered unconditionally), was genuinely `display:none` with a zero
bounding box. First run after the fix: `FAIL — 13. ... {"markupPresent":
true,"computedVisible":false,"nonzeroBounds":false,...,"display":"none",
"box":null}`. Fixed by re-clicking `[data-r4-device="mobile"]` (and
waiting for `window.innerWidth <= 680` inside the iframe) after every
reload-triggering action (steps 6, 10/11, 12/13), matching how a real
merchant would need to re-select mobile preview after any full-page
reload. This is exactly the class of false-positive/false-negative the
Architect's directive was concerned about — proof that the repair's
stronger checks are load-bearing, not cosmetic.

## Round-2 result

**23/23 PASS** (round 1's 16 assertions decompose into 23 under the
strengthened checks — the added granularity is 4a/9's before/after
capture plus 8b/8c/8d, 16a/16c/16d/16e as separate named checks per the
directive's required report fields; no round-1 coverage was removed).

| # | Check | Result | Key data |
|---|---|---|---|
| 1 | R4 Builder opens | PASS | |
| 2 | Global Design panel opens | PASS | |
| 3 | Persian label present | PASS | |
| 4 | Selector options match registry EXACTLY (9/9) | PASS | missing=[], unexpected=[] |
| 5 | `footer.update` mutation accepted | PASS | new_revision=1 |
| 6 | Undo enabled after reload | PASS | |
| 7 | Draft Preview REAL mobile viewport | PASS | innerWidth=390 |
| 8a | Draft mobile nav markup | PASS | |
| 8b | Draft mobile nav computed visibility | PASS | display=block |
| 8c | Draft mobile nav nonzero bounds | PASS | 370×64 |
| 8d | Draft nav item count >= 3 | PASS | itemCount=4 |
| 9 | Footer variant preserved (exact before===after) | PASS | legacy_default === legacy_default |
| 11 | Undo restores hidden (no markup at all) | PASS | |
| 13 | Redo restores visible four_item | PASS | display=block, 370×64 |
| 14 | Public unchanged before Publish | PASS | |
| 15 | Publish clicked | PASS | |
| 16a | Public REAL mobile viewport | PASS | innerWidth=390 |
| 16b | Public mobile nav markup after Publish | PASS | |
| 16c | Public mobile nav computed visibility | PASS | display=block |
| 16d | Public mobile nav nonzero bounds | PASS | 370×64 |
| 16e | Public nav item count >= 3 | PASS | itemCount=4 |
| 17 | Fresh Draft hidden, REAL mobile viewport, no markup | PASS | innerWidth=390 |
| 18 | Stale mutation rejected (409) | PASS | stale_revision |

## Screenshot evidence

- `screenshots/01-draft-preview-mobile-four_item.png` — R4 Draft Preview,
  mobile device mode, `four_item` Bottom Nav visibly rendered at the
  bottom of the canvas (4 icons: account/cart/catalog/home).
- `screenshots/02-public-mobile-four_item.png` — Public storefront after
  Publish, real 390×844 viewport, the same `four_item` Bottom Nav visibly
  rendered at the bottom.
- `screenshots/03-fresh-draft-hidden-mobile.png` — a second, untouched
  Store's fresh Draft, mobile device mode: no Bottom Nav bar rendered at
  all (only the editor chrome).

All three were visually reviewed and confirm what the DOM/computed-style
assertions report.

## Round-2 conclusion

The production implementation was already correct — every defect found in
this round was in the QA script's own assertions, not in
`r4_mutation_service.py`, `r4_views.py`, `r4/editor.html`, or any Django
test. With genuine mobile-viewport contexts and real DOM/computed-style
visibility checks, the Bottom Nav is now proven to be actually visible
(not merely present in markup) on both Draft Preview and the Public
storefront after Publish, the `hidden` variant is proven to render no nav
surface at all at a real mobile width (not just "hidden by desktop CSS"),
the Footer variant is proven byte-exact unchanged, and all 9 registered
variants are proven present with zero missing and zero unexpected.
