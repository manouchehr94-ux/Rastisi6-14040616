# P5-W3 Design Lab / Random Mix — Browser QA Report (Section 29)

> **Updated after independent Architect review of PR #9.** The scenarios now
> assert **DATA/behaviour** (server-authoritative candidate/base selections and
> diffs), not merely panel visibility, per the review's Browser QA Repair.

## Harness
Uses the **existing** R4 browser-QA infrastructure conventions
(`tools/storefront_builder_r4_qa/`): the bundled `playwright-core` + the
installed Chromium binary (`/opt/playwright/chromium-1232/chrome-linux64/chrome`,
Chrome for Testing 151), session-cookie auth, and a PASS/FAIL result JSON. The
W3-only scenario script is `tools/storefront_builder_r4_qa/w3_design_lab_qa.mjs`
— a small script alongside the existing runner, **not** a second harness. It
drives the **existing** R4 editor + the Design Lab panel through the **existing**
`storefront_preview` iframe, and reads server-authoritative state from the
read-only `/design-lab/` endpoint so assertions are on real data.

Auth/setup: `_w3_qa_setup.py` seeds the compatibility store (`akhlaghi`) on a
real Ready Template with R4 enabled + a session cookie; runner `_w3_run_browser_qa.sh`
(seed → serve → Playwright → teardown, per template, one invocation).

## Coverage
- **Templates (materially different):** `dark_digital` and `warm_boutique`.
- **Viewports:** desktop 1440×900, tablet 768×1024, mobile 390×844.
- **RTL:** `dir="rtl"` verified on every viewport.

## Result: **PASS** on both templates
`console_errors = 0`, `failed_requests = 0`, RTL = true, Design Lab panel present,
`horizontal_overflow = false` on all three viewports for both templates. 16
screenshots per template (incl. the new stale scenario).
Raw JSON: `browser_qa/<template>/w3_browser_qa_result.json`.

### Scenario results (both templates) — DATA-asserted
| Scenario | Result | Assertion (server-authoritative data) |
|---|---|---|
| A — Full Random Mix | PASS | 7 families differ from Base in the candidate; the real Draft is NOT written |
| M — Candidate preview renders | PASS | `storefront_preview?design_lab=<token>` returns **HTTP 200** (~53–56 KB) via the existing renderer |
| D — Compare with Base (**real diff**) | PASS | ≥1 changed family whose `base_label != candidate_label` (e.g. header "شناور فشرده" → "بازارگاهی…") — NOT "panel visible" |
| E — Return to Original DNA (**exact restore**) | PASS | after Random Mix→B then Return, candidate selections equal Base **A family-by-family** and the diff is empty |
| B — Chained Randomize One | PASS | Random Mix→B, Randomize footer→C: every non-footer family in C equals B; **footer changes** (real alternative) |
| C — Lock (**current candidate**) | PASS | Randomize header→H1, Lock, Random Mix ×N: header stays **H1** (current candidate), never reverts to committed Draft H0 |
| F — Reset Candidate | PASS | reset candidate equals the committed Draft (empty diff) |
| G — Remove Theme (transient) | PASS | candidate `theme == theme.none.v1`; no write before Apply |
| H — Explicit Apply | PASS | Apply enabled only with a candidate; the Draft `edit_revision` advances **0→1** only after the explicit Apply (via the canonical `mutate/` endpoint) |
| STALE — real-flow stale apply | PASS | a candidate generated at revision N, after a real intervening canonical edit, is **rejected 409 `stale_candidate`** by `apply_payload`; no write |

### Visual / technical checks (every viewport, both templates)
- No horizontal overflow; RTL intact; 0 console errors; 0 relevant failed requests.
  *Note:* the stale scenario deliberately triggers a 409 (proving stale rejection);
  the browser logs any 409 as a generic console "Failed to load resource" — that
  expected 409 is explicitly excluded from the console-error count. The candidate
  preview's success is asserted deterministically via a same-origin fetch → HTTP 200.
- Candidate state is visually distinguished from saved state (the "این فقط
  پیش‌نمایش است" indicator) until Apply.

### Product-Owner UX gate (Section 30)
The panel answers, in Persian, without exposing component keys/seeds/manifests:
what will change (Compare, with real base→candidate labels), what is locked (lock
buttons, which preserve the current candidate value), what differs from the
current design (Compare diff), whether it is only a preview or applied (state text
+ revision advance), and how to go back (Return to Original DNA / Reset / Undo).

### Random Mix is visually meaningful (Section 24)
Full Random Mix changed 7 eligible DNA families per run, each to a canonical
registry alternative, while page composition and commerce data are untouched.

## Reproduction
```
python manage.py shell < _w3_qa_setup.py     # seed + session cookie
bash _w3_run_browser_qa.sh                     # both templates, 3 viewports, A–H + stale
```
(The `_w3_*` helper scripts and the SQLite dev DB are QA-only and NOT committed.)
