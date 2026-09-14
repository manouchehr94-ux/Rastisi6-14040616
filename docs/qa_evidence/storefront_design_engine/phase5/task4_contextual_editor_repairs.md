# Phase 5 Task 4 — Contextual Editor Repairs

Single canonical Task-4 report. This is the only Task-4 report; no competing
report exists elsewhere.

## 1. Checkpoint

| Item | Value |
| --- | --- |
| Certified base SHA | `d3b98f2c2637a115a59d77c84b9b5d870719f63f` |
| Base commit subject | `feat(storefront_builder): merchant-data template preview without Draft mutation` |
| Working branch | `kiro/phase5-task4-contextual-editor-repairs` (branched from exactly the certified base SHA) |
| Final branch HEAD | `9e0823e7264b8431e4c65eba220aec54425740a8` |
| Remote official branch | `feature/phase5-design-expansion` still at `d3b98f2c…` — never modified, never merged into |
| Date/time | 2026-09-14 (UTC) |
| Task 5 started | **NO** |

Git guard at start: `git status` clean, remote official branch confirmed still
on the certified SHA, working branch did not previously exist (local or
remote). No `reset`/`stash`/`clean`/`rebase`/`merge`/force-push was used.

## 2. Scope Completed

### Task 4A — Global vs Section scope labeling

**What changed.** A compact, merchant-facing scope indicator now tells the
merchant whether a control affects only the selected section
(`فقط این بخش`) or the whole storefront (`سراسری — کل فروشگاه`).

- The **section** indicator is emitted generically in the one shared
  schema-driven field renderer, for every `field_type`, never by branching on
  a concrete section type.
- The **global** indicator is added once to the Global Design rendering path
  (the storefront-wide counterpart).
- The canonical contextual-exclusivity rule (opening a Section Inspector closes
  Global Design and vice-versa) is preserved and pinned with regression tests.

**Canonical owners reused.**
- `templates/dashboard/storefront_builder/r4/partials/settings_field.html` —
  the single generic field renderer (branches only on `field.field_type`).
- `templates/dashboard/storefront_builder/r4/editor.html` — the Global Design
  rendering path.
- `static/storefront_builder/r4_editor.js` — the existing `R4.openSection` /
  `openGlobalDesign` mutual-close behavior (unchanged, only pinned by tests).

**RED test.** `Task4ASectionScopeLabelTests`, `Task4AGlobalScopeLabelTests` (in
`test_r4_inspector.py`) initially failed — no `data-r4-scope` markers existed.
**GREEN test.** After adding the generic indicators, all 4A tests pass
(8 tests incl. exclusivity regression).

**Files.** `settings_field.html`, `r4/editor.html`, `r4_editor.css`,
`tests/test_r4_inspector.py`.

### Task 4B — Media / Background editing in R4

**What changed.** A media/background-capable section (`hero_banner`) now
renders a real in-R4 background picker control instead of only a passive
legacy out-link. A new **generic** `background` schema field type is rendered
by the one shared `settings_field.html` renderer (mode / custom color /
palette-role / pattern / media-image), and saves through the **existing**
`section.update_settings` Draft mutation.

**Canonical Media Library reused.** The picker's image options come from
`views._background_picker_context()` (Store-scoped `content.models.MediaAsset`)
and the existing `section_registry.PATTERN_REGISTRY`. No second media library,
upload system, or persistence model was introduced.

**Canonical background settings reused.** `background` remains validated by
`section_registry.validate_background_settings` (applied via the existing
`_with_background` wrapper on the section's `validate_settings`); the schema
layer only shape-guards the dict. No second settings registry.

**Write-time tenant ownership validation.** Enforced server-side **before**
persistence through one shared canonical authority
`section_data_service.validate_background_asset_ownership(*, store, background)`
(raising `BackgroundAssetOwnershipError`), used by **both** the legacy
settings-save view and the R4 mutation path. The legacy inline `MediaAsset`
ownership query was refactored to delegate to it — there is no second
ownership validator. (See §9 for the full security detail.)

- **Store A own asset accepted** — `test_store_can_persist_its_own_media_asset_id`.
- **Store A foreign (Store B) asset rejected** —
  `test_store_cannot_persist_a_foreign_store_media_asset_id`.
- **Rejected write does not corrupt Draft/revision** — same test asserts
  settings unchanged, `edit_revision` unchanged, history-entry count unchanged;
  `test_foreign_asset_is_never_even_stored_as_a_dangling_id` asserts the foreign
  id is never persisted (not even as a dangling value that would later
  fail-close at render).

**RED → GREEN evidence.** The 4B inspector/mutation tests initially failed
(no `background` field type; foreign `media_asset_id` **persisted** — the exact
vulnerability the security correction closes). After implementation all 15 4B
tests pass (see §6).

**Exact files changed.** `settings_schema.py`, `r4_views.py`,
`settings_field.html`, `section_registry.py`, `r4_editor.js`, `r4_editor.css`,
`services/section_data_service.py`, `services/r4_mutation_service.py`,
`views.py`, `tests/test_r4_settings_schema.py`, `tests/test_r4_inspector.py`,
`tests/test_r4_mutation_api.py`.

### Task 4C — Device Preview

**What changed.** Desktop / Tablet / Mobile preview controls were added to the
R4 topbar, ported from the legacy `sfb-v3-device-switcher` pattern.

- **Desktop** — natural fill of the preview canvas (no scaling).
- **Tablet** — the same iframe is width-clamped to 768px and transform-scaled
  to fit the canvas.
- **Mobile** — the same iframe is width-clamped to 390px and transform-scaled.

**The SAME `#r4PreviewFrame` is used.** The switcher only changes the
presentation width/scale of the one existing preview iframe (rendered at the
real device pixel width — 1200/768/390 — and CSS-transform-scaled). Confirmed
in browser QA: `previewFrameCount: 1` at every viewport.

**No second preview/renderer.** No new iframe, preview URL, `srcdoc`, or fake
HTML. State is UI-only (in-memory `currentDevice`) — never persisted to
Store/Draft/database and never routed through the mutation queue. Selected
state uses `aria-pressed`.

**RED → GREEN evidence.** `R4DevicePreviewMarkupTests` /
`R4DevicePreviewJsContractTests` (in `test_r4_foundation.py`) initially failed
(no switcher markup / no resize wiring). After implementation all 6 4C tests
pass.

**Files.** `r4/editor.html`, `r4_editor.js`, `r4_editor.css`,
`tests/test_r4_foundation.py`.

### Task 4D — Selection Sync

**What changed.** When a Section is selected from the R4 sidebar/structure UI,
R4 now posts the canonical selection into the existing preview iframe.

- **Sidebar → `sfb:setSelection`** — a new `syncPreviewSelection()` helper posts
  `previewFrame.contentWindow.postMessage({type:'sfb:setSelection', sectionId:
  R4.selected}, window.location.origin)`. It is called from `R4.openSection`,
  the single selection entry point that a sidebar-row click routes through.
- **Preview → existing `sfb:selectSection` / `sfb:openSectionSettings`** — the
  inbound preview→R4 contract is preserved unchanged; both still route to
  `R4.openSection`.
- **Same section highlighted** — `preview.html` already owns applying the
  incoming `sfb:setSelection` as its highlight; that logic was **not**
  reimplemented in R4.
- **No second selection authority** — `R4.selected` stays the single selection
  state; R4 posts it, it does not maintain a parallel copy.

**RED → GREEN evidence.** `Task4DSelectionSyncJsContractTests` /
`Task4DPreviewStillOwnsHighlightTests` (in `test_r4_inspector.py`) initially
failed (`sfb:setSelection` was never posted by `r4_editor.js`). After
implementation all 6 4D tests pass, and browser QA shows the posted message
(see §6/§8).

**Files.** `r4_editor.js`, `tests/test_r4_inspector.py`.

## 3. Product Owner UX Contract

**ONE SELECTION → ONE CONTEXT → ONLY RELEVANT SETTINGS — confirmed.**

The R4 Section Inspector is entirely schema-driven: the inspector view
(`storefront_r4_section_inspector`) renders **only** the fields declared by the
selected section's own `SettingsSchema` (split into Basic/Advanced), so:

- **Header selected → Header controls only** — the Header is edited in Global
  Design's header group; a section inspector never mixes header controls in.
- **Hero selected → Hero controls only** — `hero_banner`'s schema fields only.
- **Collection selected → Collection controls only** — the collection section's
  own schema/resource-source fields only.
- **Footer selected → Footer controls only** — footer editing lives in Global
  Design's footer group, separate from any Section Inspector.
- **Global Design remains separate from the Section Inspector** — `R4.openSection`
  calls `closeGlobalDesign()`, and `openGlobalDesign()` calls `closeInspector()`;
  the two panels are never shown mixed. Pinned by
  `Task4AContextualExclusivityContractTests` and verified live in browser QA
  (`globalDesignClosedWhenSectionOpen: true` at all three viewports).

No mixed inspector. Merchant-facing controls expose only simple Persian labels
— no registry keys, model names, JSON, engine terminology, or arbitrary CSS
(asserted by `test_scope_indicator_exposes_no_implementation_terminology` and
the background picker's option-only design).

## 4. Architecture / Duplication Audit

| Gate | Result | Canonical owner reused |
| --- | --- | --- |
| NO SECOND RENDERER | **PASS** | Preview keeps using the shared `render_service` via the single `storefront-builder-preview` iframe; 4C only rescales it. |
| NO SECOND PREVIEW ENGINE | **PASS** | One `#r4PreviewFrame` iframe (browser QA: `previewFrameCount: 1`); no new URL/`srcdoc`/iframe. |
| NO SECOND MEDIA AUTHORITY | **PASS** | 4B reuses the existing Media Library (`media_views` / `content.models.MediaAsset`) via `views._background_picker_context()`; no new upload/library. |
| NO SECOND DRAFT/LIFECYCLE | **PASS** | All edits persist through the existing Draft (`section.update_settings` mutation); no new lifecycle/model. |
| NO SECOND MUTATION BOUNDARY | **PASS** | All 4A/4B edits route through the single `R4.enqueueMutation`/`sendMutation` queue and `r4_mutation_service.apply_mutation`; POST-endpoint count stays exactly 3. |
| NO SECOND TENANT RESOLVER | **PASS** | Store resolution stays `resolve_store_for_service`; the R4 mutation path locks the active Draft as before. |
| NO SECOND SETTINGS REGISTRY | **PASS** | `background` is a new field TYPE in the existing `settings_schema.ALLOWED_FIELD_TYPES` + `section_registry` schema; validated by the existing `validate_background_settings`. |
| NO SECOND SELECTION AUTHORITY | **PASS** | `R4.selected` remains the single selection state; `preview.html` still owns highlight application. |
| NO DUPLICATE BACKGROUND OWNERSHIP VALIDATOR | **PASS** | One canonical `section_data_service.validate_background_asset_ownership`; the legacy view delegates to it (no inline second query). |
| TENANT WRITE SAFETY | **PASS** | Foreign `media_asset_id` rejected server-side before persistence (§9), proven by tenant-isolation tests. |
| SCOPE CONTROL | **PASS** | Section vs Global scope labels + enforced panel exclusivity (§3). |

## 5. Changed Files

Every changed file (vs the certified base):

```
apps/storefront_builder/r4_views.py
apps/storefront_builder/section_registry.py
apps/storefront_builder/services/r4_mutation_service.py
apps/storefront_builder/services/section_data_service.py
apps/storefront_builder/settings_schema.py
apps/storefront_builder/static/storefront_builder/r4_editor.css
apps/storefront_builder/static/storefront_builder/r4_editor.js
apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html
apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/settings_field.html
apps/storefront_builder/tests/test_r4_foundation.py
apps/storefront_builder/tests/test_r4_inspector.py
apps/storefront_builder/tests/test_r4_mutation_api.py
apps/storefront_builder/tests/test_r4_settings_schema.py
apps/storefront_builder/views.py
```

Plus this report and the browser-QA evidence under
`docs/qa_evidence/storefront_design_engine/phase5/`.

Commits produced during Task 4 (on the working branch only):

| SHA | Subject | Purpose |
| --- | --- | --- |
| `4d125e0` | `fix(storefront_builder): label R4 control scope` | Task 4A — section/global scope indicators + exclusivity regression. |
| `534de2e` | `feat(storefront_builder): port section media background editing to R4` | Task 4B — generic background picker + shared write-time tenant ownership authority. |
| `2f8caa2` | `feat(storefront_builder): add R4 device preview controls` | Task 4C — Desktop/Tablet/Mobile switcher rescaling the one preview iframe. |
| `9e0823e` | `fix(storefront_builder): sync R4 sidebar selection with preview` | Task 4D — post `sfb:setSelection` into the existing preview iframe. |

(An evidence commit adding this report + the QA screenshots is applied on top of
the four above, on the same working branch.)

## 6. Test Evidence

Runner: `python manage.py test …` (Django 5.2, SQLite, in-memory test DB).

### Per-repair RED → GREEN

| Repair | RED (before impl) | GREEN (after impl) |
| --- | --- | --- |
| 4A | `Task4ASectionScopeLabelTests` + `Task4AGlobalScopeLabelTests` — **FAILED (failures=4, errors=1)** (no `data-r4-scope` markers) | 4A classes (incl. `Task4AContextualExclusivityContractTests`) — **Ran 8, OK** |
| 4B | `Task4BBackground*` inspector/mutation — **FAILED (failures=7, errors=1)** (no `background` field type); tenant-isolation — **FAILED (failures=3)** (foreign id persisted) | 4B inspector+js+mutation+tenant-isolation+single-authority — **Ran 15, OK** |
| 4C | `R4DevicePreviewMarkupTests` + `R4DevicePreviewJsContractTests` — **FAILED (failures=2)** (no switcher markup/wiring) | 4C classes — **Ran 6, OK** |
| 4D | `Task4DSelectionSyncJsContractTests` + `Task4DPreviewStillOwnsHighlightTests` — **FAILED (failures=2, errors=1)** (`sfb:setSelection` never posted) | 4D classes — **Ran 6, OK** |

Focused Task-4 test count (all four repairs together):

```
python manage.py test \
  apps.storefront_builder.tests.test_r4_inspector.Task4ASectionScopeLabelTests \
  apps.storefront_builder.tests.test_r4_inspector.Task4AGlobalScopeLabelTests \
  apps.storefront_builder.tests.test_r4_inspector.Task4AContextualExclusivityContractTests \
  apps.storefront_builder.tests.test_r4_inspector.Task4BBackgroundFieldInspectorTests \
  apps.storefront_builder.tests.test_r4_inspector.Task4BBackgroundJsContractTests \
  apps.storefront_builder.tests.test_r4_mutation_api.Task4BBackgroundMutationTests \
  apps.storefront_builder.tests.test_r4_mutation_api.Task4BBackgroundAssetTenantIsolationTests \
  apps.storefront_builder.tests.test_r4_mutation_api.Task4BBackgroundOwnershipSingleAuthorityTests \
  apps.storefront_builder.tests.test_r4_foundation.R4DevicePreviewMarkupTests \
  apps.storefront_builder.tests.test_r4_foundation.R4DevicePreviewJsContractTests \
  apps.storefront_builder.tests.test_r4_inspector.Task4DSelectionSyncJsContractTests \
  apps.storefront_builder.tests.test_r4_inspector.Task4DPreviewStillOwnsHighlightTests
=> Ran 35 tests … OK
```

Breakdown: 4A = 8, 4B = 15, 4C = 6, 4D = 6 → **35 focused tests, all OK.**

### Final regression suite (the plan's required Task-4 regression scope)

```
python manage.py test \
  apps.storefront_builder.tests.test_r4_inspector \
  apps.storefront_builder.tests.test_r4_appearance_overrides \
  apps.storefront_builder.tests.test_r4_foundation -v 2
=> Ran 125 tests … OK
```

Baseline (certified base SHA, same three modules) was **Ran 98 tests, OK**; the
+27 delta is the new Task-4 tests. Also green together:
`test_r4_mutation_api` + `test_r4_settings_schema` added (combined 5-module run
= **263 tests, OK**).

## 7. Static / Django Gates

```
python manage.py check                       => System check identified no issues (0 silenced).
python manage.py makemigrations --check --dry-run => No changes detected.
git diff --check                             => clean (no whitespace/conflict markers)
```

- Django check: **clean.**
- Migrations: **none** (Task 4 needs no migration — the `background` block is an
  existing JSON settings block; no model/schema DB change).
- diff check: **clean.**

## 8. Browser QA

Environment note: the committed R4 QA harness (`qa_storefront_builder_r4` →
`tools/storefront_builder_r4_qa/run.mjs`) was executed first. It ran end-to-end
(browser launched, DB backup/restore verified — `db-restore-proof.json` shows
`match: true`), but every scenario failed because the harness hard-codes the
request Host `127.0.0.1` in its manifest, which does not resolve to a tenant in
this multi-store sandbox (two Stores exist, so the single-Store compatibility
fallback fails closed) — the R4 route returns 404. **This is an
environment host→tenant-resolution limitation of the sandbox, not a defect in
the Task-4 code:** a Django test-client request with the correct tenant Host
(`rastisi-fashion-test.rastisi.localhost`) returns **200** with all Task-4
markup present.

Evidence was therefore captured using the **same** existing browser
infrastructure (the identical `playwright-core` + installed `chrome` channel the
committed runner uses), driving the real running R4 editor with Chrome's
`--host-resolver-rules` mapping the tenant hostname to `127.0.0.1` plus the
session cookie. No second QA harness was committed; the ad-hoc capture scripts
were deleted after the run.

Per-viewport confirmation (RTL is primary — `document dir = rtl` at all three):

| Check | 1440×900 | 768×1024 | 390×844 |
| --- | --- | --- | --- |
| Scope label (global `سراسری — کل فروشگاه`; section `فقط این بخش`) | ✅ | ✅ | ✅ |
| Contextual Inspector (Global Design closed when a Section is open) | ✅ | ✅ | ✅ |
| Media/background flow (real picker on `hero_banner`: mode+color+pattern+media) | ✅ | ✅ | ✅ |
| Desktop/Tablet/Mobile preview control (same `#r4PreviewFrame`, count = 1; tablet→768px, mobile→390px, `aria-pressed` toggles + transform scale) | ✅ | ✅ | ✅ |
| Sidebar → iframe selection (`sfb:setSelection` posted with the selected sectionId) | ✅ | ✅ | ✅ |
| RTL | ✅ | ✅ | ✅ |

Evidence paths:

- Screenshots (5 per viewport × 3 viewports = 15):
  `docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/shots/`
  (`<viewport>-4A-global-scope.png`, `<viewport>-4A-4B-4D-section-inspector.png`,
  `<viewport>-4B-background-picker.png`, `<viewport>-4C-device-tablet.png`,
  `<viewport>-4C-device-mobile.png`).
- Committed-harness run artifacts (host-blocker + DB-safety proof):
  `…/task4_browser_qa/` (`r4-browser-result.json`, `db-restore-proof.json`,
  `browser.log`, `runserver.log`, `tenant_negatives.json`).

## 9. Security Evidence (Task 4B correction)

- **Server-side write-time tenant validation exists.** Persisting a section
  `background.media_asset_id` is validated by
  `section_data_service.validate_background_asset_ownership(*, store, background)`
  before the section settings are saved. In the R4 path this runs inside
  `r4_mutation_service._apply_section_update_settings` only when the mutation's
  raw patch touches `background`, after schema cleaning but before
  `section.save()`, so a rejection rolls back atomically (no settings/revision/
  history change).
- **Store A cannot persist Store B MediaAsset IDs.** Proven by
  `test_store_cannot_persist_a_foreign_store_media_asset_id` and
  `test_foreign_asset_is_never_even_stored_as_a_dangling_id`.
- **Client-side filtering is not the security boundary.** The picker only
  *offers* the merchant's own Store-scoped assets, but the authoritative check
  is the server-side ownership validation above — a crafted POST of a foreign id
  straight to the mutation endpoint is rejected.
- **Render-time fail-closed is defense-in-depth, not the only protection.**
  `content.services.resolve_background_media_url` still fail-closes a
  foreign/deleted id to `None` at render, but Task 4B does not rely on it as the
  isolation boundary for writes — the write is rejected up front.
- **No duplicate media/ownership authority.** The legacy
  `views._validate_background_asset_ownership` was refactored to *delegate* to
  the same canonical `section_data_service` helper; the R4 path delegates to it
  too. One authority, two callers — mirroring the existing
  `validate_resource_source_ownership` pattern.

## 10. Known Issues / Deferred Scope

- **Pre-existing base-branch test failures (NOT introduced by Task 4).**
  Verified by running the same tests against a clean `git worktree` at the
  certified base SHA:
  - `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
    (`validate_appearance_config` called twice, not once, on the
    `appearance.update` path — untouched by Task 4).
  - `test_views.FullscreenEditorTests` (1 failure + 1 error) — legacy editor
    topbar fullscreen/device/zoom controls.
  Both fail identically on the untouched base and live in modules outside the
  required Task-4 regression scope; left as-is (out of scope, not a regression).
- **Committed R4 QA harness host binding.** The harness cannot resolve a tenant
  at `127.0.0.1` in a multi-store sandbox (see §8). Not changed (would be a QA
  tooling change outside Task-4 code scope); behaviors were proven with the same
  browser infra at the correct tenant host.

**Explicitly NOT implemented (out of Task-4 scope):**

- Task 5 (any part)
- Mobile Navigation Drawer
- PDP Tabs expansion (Product Tabs/Accordion)
- Trust/Delivery expansion (PDTX)
- public Modal / Quick View
- carousel transition expansion (STRANS)
- Storefront Showcase section
- Theme Overlay production implementation
- Random Mix production implementation
- final 50-template QA

Future UX direction recorded (per the plan, NOT part of Task 4): the eventual
"Preview/Publish shows only the storefront with minimal chrome" direction is a
later requirement and was intentionally not built here.

## 11. Final Verdict

**TASK 4 STATUS: READY FOR INDEPENDENT REVIEW**

Task 5 was **NOT** started.
