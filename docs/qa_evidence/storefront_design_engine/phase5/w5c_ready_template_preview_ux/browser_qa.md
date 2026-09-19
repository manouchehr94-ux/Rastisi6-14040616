# W5C — Browser QA (Real Merchant Journey)

Script: `tools/storefront_builder_r4_qa/w5c_ready_template_preview_ux_qa.mjs`
(reuses the existing `tools/storefront_builder_r4_qa/` conventions — same
Chromium/`playwright-core` resolution, same `--host-resolver-rules=MAP *
127.0.0.1` approach, "Python owns Store-state setup + DB-truth
verification, Node owns only browser UI assertions" — no second harness).

Raw console output: `browser_qa_console.txt`. Structured result:
`browser_qa_results.json`. Draft non-mutation proof:
`w5c_draft_before.json` / `w5c_draft_after.json` (byte-identical).

## Result

**25/25 PASS.**

## Setup

- Fixture: `/tmp/w5a-evidence/w5c_qa_setup.py` (QA-scratch, not
  committed) — creates a Store (`w5c-qa-store`, admin host
  `w5c-qa.rastisi.localhost`) with a fresh Draft, and derives the
  expected 50-key registry list plus three representative Ready
  Template keys (early/middle/late in registry order:
  `dense_marketplace` / `mina_community` / `anniversary_mosaic`) directly
  from `layout_preset_registry.list_ready_templates()` — never a second
  hardcoded list.
- The canonical `rasti-mode-demo` Demo Store was seeded via
  `manage.py apply_golden_reference_storefront` (the same command the
  existing Task-2 Django tests use) — see "One real defect found and
  fixed" below for why this was required.
- Django dev server: `127.0.0.1:8765`, started only after the exact-source
  full regression suite process had fully exited (confirmed via `ps`),
  per the established SQLite-contention lesson.
- Real login (real form, real CSRF, real session).
- `/tmp/w5a-evidence/w5c_qa_snapshot.py <draft_pk>` reads the Draft's
  `edit_revision`/`template_provenance`/history-entry count directly from
  the DB — run once immediately before the browser script, once
  immediately after — and the two JSON snapshots are diffed. This is how
  contracts H-K's "no Draft mutation" guarantee is verified live, since
  the browser session itself has no way to read the DB.

## One real defect found and fixed (QA fixture, not production)

The first run failed step 25 ("Preview banner identifies Rasti Mode Demo
data") and the browser console logged: `Refused to display
'http://w5c-qa.rastisi.localhost:8765/' in a frame because it set
'X-Frame-Options' to 'deny'.` Root cause: the QA fixture never seeded the
canonical `rasti-mode-demo` Store, so Demo-mode's `Store.objects.get(slug=
RASTI_MODE_DEMO_STORE_SLUG)` raised `Http404` — and Django's *generic*
404 error page is rendered by the URL resolver's own fallback, not
through `storefront_template_live_preview` itself, so it does NOT carry
that view's `@xframe_options_sameorigin` override; the browser correctly
refused to frame it under the global `DENY` default. This is exactly the
behavior a genuinely-missing Demo Store SHOULD produce — not a
production bug. Fixed by seeding the Demo Store with the same
management command the existing Django test suite already uses
(`apply_golden_reference_storefront`), then re-running cleanly. This also
incidentally re-confirms (live, in a real browser) that a missing Demo
Store fails closed with a real 404 rather than silently rendering broken
content — consistent with the view's own documented contract.

## Journey and results

| # | Step | Result |
|---|---|---|
| 2 | Gallery opens | PASS |
| 3 | Exactly 50 Ready Template cards present | PASS |
| 3b | Every registered key has a wired preview trigger | PASS |
| 4-6 | Representative template chosen, Draft facts recorded (external snapshot) | — |
| 7 | Dialog is visible | PASS |
| 8 | Dialog title contains the template's merchant-facing label | PASS |
| 9 | Exactly one preview iframe exists | PASS |
| 10 | Iframe URL is the canonical live-preview route | PASS |
| 11-12 | Merchant data selected; iframe URL has `data=merchant` | PASS |
| 13 | Preview banner identifies Merchant-data mode | PASS |
| 14 | Draft unchanged (external snapshot, see below) | PASS |
| 15-16 | Desktop: `aria-pressed`, no fixed width/transform (natural presentation) | PASS |
| 17-18 | Tablet: iframe document `window.innerWidth` ≈ 768 | PASS (768 exact) |
| 19-20 | Mobile: iframe document `window.innerWidth` ≈ 390 | PASS (390 exact) |
| 21 | Mobile: non-zero rendered body, no error page | PASS |
| 22-23 | Switch to Demo; same single iframe element reused | PASS |
| 24 | Canonical preview URL now Demo mode (no `data=merchant`) | PASS |
| 25 | Preview banner identifies Rasti Mode Demo data | PASS |
| 26 | Draft still unchanged (external snapshot) | PASS |
| 27 | Switch back to Merchant | PASS |
| 28 | No mutation/history produced (external snapshot, cumulative) | PASS |
| 29-30 | Escape closes; focus returns to the trigger | PASS |
| 31-32 | Open a second, different Ready Template — retargets, not stale | PASS |
| 33 | Close with the Close button | PASS |
| 34 | Existing Apply control(s) remain available (all 50) | PASS |
| — | Accessibility: focus trap (Tab wraps from last to first) | PASS |
| — | Accessibility: Enter on a focused trigger opens the dialog | PASS |
| — | Representative coverage: third ("late") template retargets + loads | PASS |

## Representative device/template coverage (§17)

Per the directive's explicit "do not duplicate W4C" instruction, only one
representative template (`mina_community`, registry-middle) was exercised
across all 3 devices and both data sources. The other two representatives
(`dense_marketplace`, registry-first; `anniversary_mosaic`,
registry-last) only prove successful retargeting and iframe load — no
50×3 device matrix.

## Non-mutation proof (§19)

```
Before: {"edit_revision": 0, "history_count": 0, "pk": 1, "template_provenance": {}}
After:  {"edit_revision": 0, "history_count": 0, "pk": 1, "template_provenance": {}}
```

Byte-identical. Across the entire session — opening, both data-source
switches (merchant→demo→merchant), all three device switches, and
retargeting to two additional templates — the Draft's PK, revision,
provenance, and history-entry count never changed.

## Screenshot evidence

- `screenshots/01-gallery.png` — the Ready Template Gallery with multiple
  cards visible (screenshot thumbnails, palette strips, titles, Apply
  buttons).
- `screenshots/02-preview-desktop.png` — in-page Preview, Desktop mode,
  Merchant data banner visible.
- `screenshots/03-preview-tablet.png` — in-page Preview, Tablet mode.
- `screenshots/04-preview-mobile.png` — in-page Preview, Mobile mode,
  Bottom Navigation icons visible at the bottom of the narrow canvas.
- `screenshots/05-preview-demo-mode.png` — Demo-data mode, visibly
  distinct real content ("کالکشن پاییز و زمستان Rasti Mode") confirming
  genuine Rasti Mode Demo data is rendering, not the merchant's empty
  catalog.

All five were visually reviewed and confirm what the DOM/computed-style
assertions report — including the merchant Store's empty-catalog state
(no products seeded in the QA fixture, correctly rendering an "no
products" empty state rather than an error) versus the Demo Store's real
seeded content.

## Conclusion

Every step of the required merchant journey passes against the actual,
running Gallery and live-preview route — 50/50 Ready Templates wired,
exactly one shared iframe reused across retargeting/device/data-source
changes, real Tablet/Mobile viewport widths inside the iframe's own
document (768/390 exact), a genuine visible difference between Merchant
and Demo data, zero Draft mutation across the whole session (verified
directly against the database, not inferred), and a working keyboard/
focus-trap accessibility contract.
