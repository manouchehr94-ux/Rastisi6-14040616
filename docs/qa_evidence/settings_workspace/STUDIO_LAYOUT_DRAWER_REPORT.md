# Studio layout pass — no docked right panel; page structure is an on-demand drawer

Follows `2f1f5e9` (settings workspace overlay). Owner decision: nothing permanently attached to the right edge; with every overlay
closed the storefront Preview owns the whole Studio workspace.

## Behaviour

| State | What the owner sees | Layout cost |
|---|---|---|
| **A — default** | Storefront only. No drawer, no workspace. | The Studio grid is one column (`studio-layout{grid-template-columns:minmax(0,1fr)}`); canvas = full width. |
| **B — «ساختار صفحه»** | A 400 px drawer (`min(400px,92vw)`) slides in from the right (RTL), above the Studio, no backdrop. Title, close, search, section rows, add-section, row layouts, empty cells, header/footer shortcuts. | `position:fixed` → 0 px. |
| **C — settings workspace** | The large overlay built in `2f1f5e9`, unchanged. | `position:fixed` → 0 px. |

* **Mutually exclusive.** Opening settings closes the drawer (and keeps the selected section); opening the drawer closes the workspace; closing settings returns to A (not to the drawer).
* **Select ≠ open.** A row's name only selects (row highlight + Preview highlight + Preview scrolls to it, without touching `R4.selected`); its ⚙ opens the workspace for that same section through the one existing `R4.openSection`. The top-bar «تنظیمات بخش» reopens the selected section (or opens the drawer with a hint when none is selected).
* **Nothing removed.** Every row now carries quick actions wired to the *existing* `data-r4-structure-*` hooks (one sender): move up/down, show/hide, lock, duplicate, remove (same disabled rules as the old Inspector), plus add section, per-row layout & container settings, empty-cell add/move, page reset, header/footer shortcuts. The same section actions also remain in the workspace's Advanced → «مدیریت بخش».
* Global Design and the Ready-Template peek used the same docked column: they now open in the same drawer (and close with ✕/Esc; closing a template peek cancels it, no Draft write).
* **Top-level navigation:** ساختار صفحه · تنظیمات بخش · قالب‌ها · طراحی سراسری (· آزمایشگاه) in the top bar; «نمای عمومی» and «انتشار» in the project bar. Removed duplicates: the stage-toolbar «قالب‌ها» button and the mobile-only panel toggle. (The «قالب‌ها» link inside the drawer's template nudge and the header/footer ⚙ shortcuts are intentional contextual shortcuts.) ≤ 700 px the nav is icon-only (labels as `title`).
* **Keyboard/focus:** Esc closes the active overlay (workspace → focus to «تنظیمات بخش» button; drawer → focus back to the opener); the workspace keeps its focus trap.
* Not built: row drag-and-drop (there was none; ↑/↓ are the move affordance — a non-functional handle would be a dead control).

## Preview geometry — states A / B / C (real Chromium, Rasti Mode Demo draft)

`#r4PreviewFrame` w × h @(x,y), logical viewport, breakpoints (≥1024 / ≥768), section box, canvas width. **All identical across A, B, C and after closing** (Δ = 0 px). Raw: `measure_ABC_*.txt`; images `A_default_*`, `B_drawer_*`, `C_workspace_*`.

| Viewport | A = B = C iframe | @(x,y) | Section | Breakpoints | Canvas |
|---|---|---|---|---|---|
| 1920×1080 | 1440 × 847 | (241,204) | 1378 × 499.25 | true / true | 1860 |
| 1440×900 | **1396** × 667 (was 1094 with the docked column) | (23,204) | 1378 × 499.25 | true / true | 1396 |
| 1280×720 | 1236 × 487 | (23,204) | 1378 × 499.25 | true / true | 1236 |
| 1024×768 | 996 × 535 | (15,204) | 1378 × 499.25 | true / true | 996 |
| 390×844 | 370 × 580 | (11,235) | 1378 × 499.25 | true / true | 370 |

(At 1920 the frame is the 1440 px *desktop device* width, centred in the 1860 px canvas — that is the device-preview model, unchanged; the canvas itself is no longer narrowed.)

## Tests (focused)

* New `test_studio_structure_drawer.py` (9): closed by default, drawer markup/a11y, top-level navigation order and no duplicates, row actions + disabled rules, select-vs-open, one-column grid + fixed 400 px drawer + z-order, mutual exclusion, Escape/focus wiring, «تنظیمات بخش» behaviour, partial-refresh pipeline untouched.
* Opt-in browser (`SFB_BROWSER_TESTS=1`): `test_structure_drawer_and_settings_workspace_float_above_a_full_width_preview` — A/B/C at 1920/1440/1280/1024/390 (geometry equality, default full canvas, never both overlays, selected section survives drawer → settings, Esc + focus return, «تنظیمات بخش» reopens the same section); `test_structure_drawer_keeps_every_structure_capability_and_partial_refresh_still_works` (row actions mutate the draft, filter, open settings from the drawer, fragment refresh path still used); the earlier workspace geometry/live-view/latency tests still pass.
* `test_settings_workspace` grid assertion updated for the single-column Studio.

Templates 52/53 untouched. Not pushed; no PR, merge or deploy.
