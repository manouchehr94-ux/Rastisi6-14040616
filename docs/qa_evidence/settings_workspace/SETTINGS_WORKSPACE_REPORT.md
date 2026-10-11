# Settings Workspace — large overlay replaces the docked right Inspector

Owner UX correction applied: opening a section's settings launches **one large, premium workspace overlay on every device**.
No 640–720 px modal, no right sidebar form, no desktop/mobile interaction split.

## What changed

| Area | Change |
|---|---|
| Shell (`r4/editor.html`) | The inspector view is gone from the right-edge `context-panel`. `#r4Inspector` now lives in a `position:fixed` overlay (`.rs-workspace`: backdrop + `role="dialog" aria-modal`). The right edge keeps only the lightweight **page-structure navigation** (and Global Design / Template preview). |
| Overlay size (`r4_studio.css`) | Desktop/laptop `min(92vw,1520px)` × `90vh` (measured 92 % × 90 %; capped at 1520 px on large screens), centred, backdrop blur, sticky header + sticky footer, **internal scrolling only** (`.r4-ws-body{overflow-y:auto}`), z-index 40 (below dialogs 50 / resource picker 60). ≤ 850 px the same workspace is `100vw × 100dvh`, no radius. |
| Workspace structure (`section_inspector.html`) | Header (section identity, breadcrumb, **search**, **save state**, close) → primary tabs **محتوا / طراحی / پیشرفته** → two-column responsive card grid → sticky footer. Same markup on every device; only the CSS layout differs. |
| Arrangement engine (`workspace_layout.py`, new) | Display-only: each schema field is placed in a titled card from its **type + key** (generic — no section-key / template-key branch; pinned by a test). Every field appears exactly once for all 38 sections. Design tab: main column **پس‌زمینه · ظاهر و استایل (رنگ‌ها، حاشیه…) ·** side column **چیدمان · پنل کمپین · فاصله‌ها · تایپوگرافی**; Content: **متن و عنوان · آیتم‌ها و رسانه · منبع و نمایش**; Advanced: **رفتار و حرکت · مدیریت بخش** (the section toggle/lock/move/duplicate/remove actions moved here). |
| Conditional UI (`r4_editor.js`) | `syncWorkspaceCards()` hides a card (and an empty column / shows a tab hint) when every control in it is dormant under `visible_when`, so no empty boxes. The `visible_when`, hydrate and mutation code is untouched. |
| Search | Filters rows by label/key across all tabs (dormant rows are never hits), switches to the first tab with matches, shows per-tab match counts. |
| Triggers | Preview click, the section's gear (`data-open-settings`), the structure row's dots button, double-click — all still go through `R4.openSection`. Selected section stays highlighted (Preview highlight + structure row + overlay header). Esc / backdrop / close / footer button close; focus is trapped while open and returns to the opener. The last used tab is remembered across sections. |
| Locked section | Only the *field* areas become `inert`; the lock switch (Advanced → مدیریت بخش) and close stay usable. |
| Mini live view (optional) | **Implemented**, without a second rendering authority — see below. |

## Live mini preview — why it did not need a second renderer

* The aside is a *sibling* of the Inspector body (so re-rendering the Inspector after a display-type change never reloads it) holding one static `<iframe data-r4-ws-live-frame>` with **no src in the markup**.
* On open, r4_editor.js points it at the **same draft preview URL** (`data-rs-draft-src`) — the canonical server-rendered page — and injects CSS **into that frame only** to isolate the open section, then scales it to the column (logical width = the main Preview device width, so the breakpoint matches).
* Updates reuse the **same** fragment the main Preview just received: one shared `swapFragmentIn(frame, fragment)` serves both frames (Alpine destroy/init included); a full refresh of the main Preview reloads it too. No JS storefront renderer exists; the main Preview behind the overlay still updates through the canonical partial-refresh pipeline (measured `path: fragment`).
* Shown only when the viewport is ≥ 1101 px (below that the workspace is a full-screen sheet with no room for a second column). Closed ⇒ `src` removed.
* Cost to know: opening the workspace triggers one extra server render of the draft preview page, and the two same-origin frames share a main thread — measured edit→Preview latency with the live view open is *simple* median 218 ms / p95 239 ms, *structural* 162 / 192 ms (earlier measurement without the second frame: ≈ 131–157 ms medians).

## Preview geometry (acceptance: delta 0 px)

Measured in real Chromium (Playwright) on the Rasti Mode Demo draft, `#r4PreviewFrame` before / while open (content **and** design **and** advanced tabs) / after close. Opt-in test `test_settings_workspace_is_a_large_overlay_that_never_changes_the_preview_geometry` asserts the whole record is identical.

| Viewport | Iframe w × h (before = during = after) | Section w × h | Breakpoint (≥1024 / ≥768) | Δ width | Workspace |
|---|---|---|---|---|---|
| 1920 × 1080 | 1440 × 847 | 1378 × 499.25 | true / true | **0 px** | 1520 × 972 (capped; 90 vh) |
| 1440 × 900 | 1094 × 667 | 1378 × 499.25 | true / true | **0 px** | 1325 × 810 (92 % × 90 %) |
| 1280 × 720 | 934 × 487 | 1378 × 499.25 | true / true | **0 px** | 1178 × 648 (92 % × 90 %) |
| 1024 × 768 | 714 × 535 | 1378 × 499.25 | true / true | **0 px** | 942 × 691 (92 % × 90 %) |
| 390 × 844 (phone) | 370 × 580 | 1378 × 499.25 | true / true | **0 px** | 390 × 844 (full screen) |

(The frame's logical viewport stays the chosen device width — 1440 — scaled into the canvas, so the section geometry in frame px is identical too.) Raw numbers: `measure_*.txt`.

**Superseded:** the remaining right-edge page-structure column was removed in the follow-up pass — see `STUDIO_LAYOUT_DRAWER_REPORT.md` (structure is now an on-demand floating drawer; the Preview spans the full canvas). The geometry table above was measured with that column present; the A/B/C table in the follow-up report is the current measurement.

## Evidence

`closed_*.jpg` (canvas, no settings), `open_<w>_{content,design,advanced}.jpg` for 1920 / 1440 / 1280 / 1024 / 390, `search_1440.jpg`, `locked_1440.jpg`, plus `measure_*.txt`. Owner guide (Persian): `OWNER_QA_GUIDE_FA.md`.

## Tests

* New `tests/test_settings_workspace.py` (14): arrangement engine invariants (every field once for every section, generic source, product-section Design groups, schema-group respected), workspace markup (tabs, two columns, groups order), overlay CSS contract (fixed, 92vw/90vh, internal scroll, phone full-screen, z-order), form not in the right panel, live view reuses the canonical fragment/page, last-tab memory.
* Opt-in browser (`SFB_BROWSER_TESTS=1`): geometry delta-0 at four viewports + size/full-screen assertions; live view follows the same fragment; existing latency/coalescing/Alpine tests updated for the new tabs.
* Intentionally updated: `test_r4_inspector` (tab names `content/design/advanced`, field→tab placement), `test_r4_foundation` (the only other iframe is the static live frame with no `src`), `test_design_studio_media_publish_dirty` (the refresh test asserted a pre-existing, already-stale idiom — it fails on `1d6d6e4` too — now asserts the current single `reloadPreviewFrame()` authority).
* Known pre-existing, unrelated: `test_validate_appearance_config_is_the_validator_boundary` fails on clean HEAD.

Templates 52/53 untouched. Nothing pushed, no PR, no merge, no deploy.
