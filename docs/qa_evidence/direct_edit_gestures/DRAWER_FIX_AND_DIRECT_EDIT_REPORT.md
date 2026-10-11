# Blank-drawer fix + direct editing of the Preview

Follows `0d7556b`. Templates 52/53 untouched. Not pushed; no PR, merge or deploy.

## 1. Intermittent blank white drawer — root cause

Two owners of one fact. The Studio decided "the drawer is open on the Global Design view" (`ui.mode='global'`, `ui.panelVisible=true`) while R4
separately owns the content's visibility (`#r4GlobalDesign.hidden`). `R4.openSection()` calls `closeGlobalDesign()` **before** its Inspector fetch
returns, and the Studio did not listen to `r4:global-closed`. From that moment until the fetch finished — and **for good if the fetch failed or was slow**
(deleted section, server error, SQLite/proxy hiccup) — the drawer stayed open over a view whose only content was hidden: a large white shell.
It was reproduced deterministically with a randomised transition run (structure → global → «تنظیمات بخش»), e.g. seed 7 at transition 44 and seed 2 at 80
(`drawer shown but view global has no content`). A second latent path: a structure refresh could replace the list with a non-structure response.

Audit of the other states (structure, template peek, settings, Escape/backdrop, structure refresh, HTMX/R4 refresh) found no other way to an empty
view; but nothing enforced it, so the invariant below now does.

## 2. State-machine fix (one presentation authority)

* `resolveDrawerView()` is the ONLY thing that decides what the drawer shows: `null` (closed) or exactly one of `structure | global | template-preview`.
  `renderChrome()` derives **everything** from it: `.panel-visible`, `data-rs-drawer`, every `[data-rs-view]` hidden flag (exactly one visible, or none), the
  backdrop (CSS on `data-rs-drawer`), `data-rastisi-panel`. The old split forms (`ui.panelVisible && showPanel ? ui.mode`, the "structure view stays visible in inspector mode" rule) are gone.
* **Defensive invariant:** a requested view with no real content (`drawerViewHasContent`: structure rows/empty-state present; Global Design open in R4 *and* populated; a template actually being peeked)
  drops the request — the drawer closes (global/template modes also reset to the structure mode) instead of rendering a blank shell. The drawer is never shown in `inspector`/`lab` modes (mutual exclusion with the workspace).
* The Studio now follows R4: `r4:global-closed` → leave global mode and close the drawer.
* `R4`'s structure refresh only swaps the list in when the response actually contains it (`[data-rs-structure-scroll]`); new `R4.refreshStructure()` exposes that read-only path for QA.
* **Legacy `data-r4-structure-open` removed** (it was hard-coded `"true"` and had no live consumer): the attribute is gone from `editor.html`, and the dead `#r4StructureToggle` handler in `r4_editor.js` was deleted. `data-rs-drawer` is the single drawer state attribute.
* Focus: the workspace returns focus to the opener, or to the top-bar «تنظیمات بخش» button when the opener was inside the (closed) drawer or the Preview frame.

## 3. Direct editing gestures

| Input | Single click / tap | Double-click | Press-and-hold |
|---|---|---|---|
| Mouse | **selects** (outline, structure row highlighted) — no settings | **opens** the workspace for that exact section | — |
| Touch / pen | tap **selects** | (ignored) | **opens** after **550 ms** |

**Architecture.** The gesture lives in the Preview document (`preview.html`), where the section DOM is. Identity = nearest `[data-section-id]` (never a class name). It talks to the Studio over the existing
origin-restricted channel (`postMessage(..., window.location.origin)`; never `"*"`): `sfb:selectSection` (select) and `sfb:openSectionSettings` (open). In the Studio, select only
records the selection (`r4:section-selected` → structure row), while open emits `r4:direct-edit` (the Studio closes any open drawer first) and then calls the SAME `R4.openSection(id)` the structure drawer's gear uses —
so the existing large workspace, schema-driven Inspector, live mini-preview and 0-px geometry apply unchanged. No second modal or selection authority exists (one `R4.openSection`, one `selectPreviewSection`).
The highlight now persists after the workspace closes (last selected section).

**Long-press contract.** 550 ms (`LONG_PRESS_MS`). Cancelled by: movement > 10 px (`LONG_PRESS_SLOP`), a scroll, `pointerup`/`pointercancel`/`touchend`/`touchcancel`/`dragstart`, window blur.
A soft ring appears after 140 ms while holding (`.sfb-rsec-hold`); an accepted gesture pulses once (`.sfb-rsec-ack`) as the workspace loads. The release that ends an accepted hold does not also "tap-select".
`contextmenu` is suppressed for touch/pen on non-interactive section surface (no browser menu); a double-click's second press does not start a word selection.

**Protected interactive selectors (never hijacked — events pass straight to the storefront):** `a[href]`, `button`, `input`, `select`, `textarea`, `label`, `summary`, `option`, `video`, `audio`, `iframe`; `contenteditable`;
`[role=button|link|tab|menuitem|checkbox|radio|switch|slider|spinbutton|textbox|combobox|option|searchbox]`; any element with `onclick`, Alpine `@click…` or `x-on:click…` (quantity controls, carousel arrows, product-card actions, add-to-cart);
`[data-no-edit-gesture]`. Links still cannot navigate the Preview away (the existing embedded-navigation guard), but they select the section and never open settings.
Builder toolbar buttons (⚙, move, duplicate, …) are buttons, so they now reach their own handlers instead of being swallowed.

**R4-host detail.** `[data-admin-edit-kind]` elements (hero slides, category tiles, product cards …) are ordinary section surface inside `#r4PreviewFrame` (the entity editor message is implemented only by the legacy editor, so it was a dead zone there); the legacy host keeps its entity-editor behaviour.
**Studio chrome.** Mouse single-click no longer parks the section tool-strip on the selected section (it shows on hover); touch keeps it. Hint (bottom bar): «یک‌بار کلیک برای انتخاب؛ دوبار کلیک برای تنظیمات» / touch: «لمس برای انتخاب؛ نگه‌داشتن برای تنظیمات» (by `(pointer: coarse)`).

## 4. Tests

* `test_studio_direct_edit_browser.py` (opt-in, real Chromium, 6 tests): single click selects but does not open; double-click opens the exact section (and another one), drawer closed, **Preview frame box identical**, Escape closes, focus returns to «تنظیمات بخش»; button and link are not hijacked (double-click opens nothing, Preview not navigated);
  touch: short tap selects, early release / movement / scroll cancel, a 300 ms-in hold shows the cue and a real hold opens the exact section with unchanged geometry, touch hint wording; touch hold on a storefront button is not hijacked;
  **defensive invariant** (emptied structure list, Global Design closed under the Studio, a refresh that returns an error page, repeated real refreshes — drawer never blank, content intact);
  **110 randomised transitions** (structure / global / settings / row gear / row select / close / Escape / backdrop / section double-click / rapid toggles) + structure refreshes + 3 template-peek round trips: after **every** one — visible drawer ⇒ exactly one visible view with content, closed drawer ⇒ no visible area/class/backdrop, never drawer + workspace, Preview box unchanged, no JS exception.
* `test_studio_drawer_state_and_gestures.py` (static contract, 10): single authority, invariant, `r4:global-closed`, refresh guard, legacy attribute gone, gesture constants/cancellations, protected selectors, canonical routing, hint wording, entity-surface rule.
* Existing opt-in browser tests that opened settings with a single click now double-click (the intended new gesture).
* Sandbox stress (separate from CI): 5 seeds × 150 transitions on the real SQLite dev DB — before the fix 2 of 5 seeds hit the blank state; after the fix seeds 7 and 2 (the failing ones) and others: 0 violations.

## 5. Manual QA (Rasti Mode Demo / Template 51) — `manual_qa_results.json` + images

1. single-click product band → selected only (`ws:false`, row `8548`) — `1_single_click_selected_only.jpg`
2. double-click same band → workspace for `8548` — `2_double_click_band_settings.jpg`
3. Escape → closed, selection kept
4. double-click hero (non-link surface) → «اسلایدر اصلی» settings (`8542`) — `4_…hero…jpg`
5. double-click category section (non-tile surface) → «گرید دسته‌بندی» (`8543`) — `5_…category…jpg`
6. touch emulation: hold cue visible at 300 ms, release after 800 ms → settings for `8548` — `6_long_press_*.jpg`
7. double-click on a carousel arrow and on a product link → nothing opens, Preview stays at `/preview/` — `7_button_link_not_hijacked.jpg`
8. Structure drawer toggled 40× → 0 blank/invalid states — `8_structure_drawer.jpg`
