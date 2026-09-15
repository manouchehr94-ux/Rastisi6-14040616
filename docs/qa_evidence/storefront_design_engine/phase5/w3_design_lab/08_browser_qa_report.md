# P5-W3 Design Lab / Random Mix — Browser QA Report (Section 29)

## Harness
Uses the **existing** R4 browser-QA infrastructure conventions
(`tools/storefront_builder_r4_qa/`): the bundled `playwright-core` + the
installed Chromium binary (`/opt/playwright/chromium-1232/chrome-linux64/chrome`,
Chrome for Testing 151), session-cookie auth, and a PASS/FAIL result JSON. The
W3-only scenario script is `tools/storefront_builder_r4_qa/w3_design_lab_qa.mjs`
— a small script alongside the existing runner, **not** a second harness/package
(it reuses the same `playwright-core` and Chromium the R4 runner uses). It drives
the **existing** R4 editor + the Design Lab panel through the **existing**
`storefront_preview` iframe. No second browser harness, no second preview route.

Auth/setup: `_w3_qa_setup.py` seeds the compatibility store (`akhlaghi`) with an
R4-enabled layout on a real Ready Template, an OWNER membership, and a session
cookie. Server: `manage.py runserver 127.0.0.1:8000`. Runner: `_w3_run_browser_qa.sh`
(seed → serve → Playwright → teardown, per template, in one invocation).

## Coverage
- **Templates (materially different):** `dark_digital` (tech/neon —
  `header.floating_compact`, `card.tech_neon`, `hero.media_feature`) and
  `warm_boutique` (`header.compact_menu`, `card.paper_frame`, `hero`/`footer`
  editorial). Two distinct storefront DNAs.
- **Viewports:** desktop 1440×900, tablet 768×1024, mobile 390×844.
- **RTL:** the editor renders `dir="rtl"` on every viewport (verified).

## Result: **PASS** on both templates
`console_errors = 0`, `failed_requests = 0`, RTL = true, Design Lab panel present,
`horizontal_overflow = false` on all three viewports for both templates.
Raw JSON: `browser_qa/<template>/w3_browser_qa_result.json`.
Screenshots: `browser_qa/<template>/screenshots/` (15 per template).

### Scenario results (both templates)
| Scenario | Result | Detail |
|---|---|---|
| A — Full Random Mix | PASS | 7 families change in the candidate; the real Draft is NOT changed until Apply |
| M — Candidate preview renders | PASS | `storefront_preview?design_lab=<token>` returns **HTTP 200** (~52–54 KB) through the existing renderer |
| D — Compare with Base | PASS | server-computed diff panel becomes visible |
| C — Lock (header) never changes | PASS | locked header stays fixed across repeated Random Mix |
| C — other eligible family still changes | PASS | a non-locked family changes while header is locked |
| B — Randomize One | PASS | only the selected family changes (subset of {footer}; "none" is valid when no alt surfaces) |
| E — Return to Original DNA | PASS | candidate returns to the committed Draft base (compare shows no difference) |
| F — Reset Candidate | PASS | candidate discarded; state returns to "this is only a preview" |
| G — Remove Theme (transient) | PASS | remove-theme candidate previewed; no write before Apply |
| H — Explicit Apply | PASS | Apply enabled only with a candidate; state reaches "اعمال شد ✔"; flows through the canonical `design_lab.apply_candidate` mutation |

### Visual / technical checks (every viewport, both templates)
- No horizontal overflow (checked via `scrollWidth > clientWidth`).
- RTL intact (`html[dir="rtl"]`).
- No console errors (0).
- No relevant failed requests (0). *Note:* transient `net::ERR_ABORTED` on the
  preview iframe URL (a superseded navigation when a new candidate reassigns
  `previewFrame.src` before the prior load finishes) is **not** a real failure —
  the candidate preview's success is asserted deterministically via a direct
  same-origin fetch returning **HTTP 200** (scenario M). These superseded
  navigations are explicitly excluded from `failed_requests`.
- Candidate state is visually distinguished from saved state via the
  "این فقط پیش‌نمایش است" indicator until Apply.

### Product-Owner UX gate (Section 30)
The panel answers, in Persian, without exposing component keys / seeds /
manifests: what will change (Compare), what is locked (lock buttons), what is
different from the current design (Compare diff with family labels), whether it
is only a preview or applied (the state text + Apply button enablement), and how
to go back (Return to Original DNA / Reset / Undo after Apply).

### Random Mix is visually meaningful (Section 24)
Full Random Mix changed 7 eligible DNA families per run (header/hero/product_view/
card/footer/badge/bottom_nav), each to a canonical registry alternative, while
page composition and all commerce data were untouched.

## Reproduction
```
python manage.py shell < _w3_qa_setup.py          # seed + session cookie
bash _w3_run_browser_qa.sh                          # both templates, 3 viewports, A–H
```
(The `_w3_*` helper scripts and the SQLite dev DB are QA-only and are NOT committed.)
