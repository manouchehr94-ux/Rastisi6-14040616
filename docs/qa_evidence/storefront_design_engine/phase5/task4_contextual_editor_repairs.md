# Phase 5 Task 4 — Contextual Editor Repairs

Single canonical Task-4 report (regenerated after the independent-review
remediation). This is the only Task-4 report; no competing report exists.

## 1. Checkpoint

| Item | Value |
| --- | --- |
| Certified base SHA | `d3b98f2c2637a115a59d77c84b9b5d870719f63f` |
| Base commit subject | `feat(storefront_builder): merchant-data template preview without Draft mutation` |
| Working branch | `kiro/phase5-task4-contextual-editor-repairs` (branched from exactly the certified base SHA) |
| Final code/evidence HEAD | `574310b34fa265269b83025dcd6c570738671db5` (last code+screenshot commit; this report commit is authored directly on top of it) |
| Remote official branch | `feature/phase5-design-expansion` still at `d3b98f2c…` — never modified, never merged into |
| Task 5 started | **NO** |

The branch was never rebased/reset/force-pushed; the certified base SHA is the
first parent of the branch history.

## 2. Commits (in order)

| SHA | Subject |
| --- | --- |
| `4d125e0` | `fix(storefront_builder): label R4 control scope` |
| `534de2e` | `feat(storefront_builder): port section media background editing to R4` |
| `2f8caa2` | `feat(storefront_builder): add R4 device preview controls` |
| `9e0823e` | `fix(storefront_builder): sync R4 sidebar selection with preview` |
| `ccd2ed8` | `docs(phase5): add Task 4 contextual editor repairs report and browser QA evidence` |
| `52e09aa` | `feat(storefront_builder): project R4 background field across all background-aware sections` (remediation R1b) |
| `8706065` | `feat(storefront_builder): make section media editing R4-native` (remediation R1a) |
| `60b330b` | `fix(storefront_builder): per-group Global Design scope indicators` (remediation R2) |
| `7a0be83` | `fix(storefront_builder): process htmx on injected R4 Inspector; refresh Task-4 browser evidence` (remediation) |
| `843a8e6` | `docs(phase5): regenerate Task 4 canonical report after remediation` |
| `29c0f6f` | `fix(storefront_builder): scope R4-inline media context to an explicit marker, not HX-Request` (final review fix) |
| `574310b` | `docs(phase5): add media-context smoke screenshots (R4 inline + legacy full page)` |
| _(this doc commit)_ | `docs(phase5): update Task 4 report after media-context final fix` — authored on top of `574310b`; its own SHA is the branch tip after this commit |

## 3. Scope Completed

### Task 4A — Global vs Section scope labeling (+ remediation R2)

- **Section indicator** (`فقط این بخش`) is emitted generically in the one
  shared schema-driven field renderer (`settings_field.html`), for every
  `field_type`, never by branching on a concrete section type.
- **Global indicator** (`سراسری — کل فروشگاه`): the Global Design panel carries
  a panel-level chip AND, per remediation **R2**, EVERY editable Global Design
  group (`.r4-global-design-group`: Ready Template switch, ظاهر کلی, هدر, فوتر)
  carries its own group-level chip (`data-r4-scope="global-group"`). Generic —
  one marker per group, never duplicated per concrete setting (marker count ==
  group count ≪ control count), no second settings renderer.
- Contextual exclusivity (opening a Section Inspector closes Global Design and
  vice-versa) preserved and pinned by regression tests, verified live
  (`globalDesignClosedWhenSectionOpen: true` at all three viewports).

### Task 4B — Media / Background editing in R4 (+ remediation R1a, R1b)

**Background (schema-driven), R1b — capability-driven, all supported sections.**
The generic `background` picker field is no longer limited to `hero_banner`. A
single canonical projection `_with_background_schema_field` in
`section_registry._finalize_registry` appends the generic `background`
`SettingsField` to EVERY schema-enabled `BACKGROUND_AWARE_SECTION_KEYS` section
(20 sections), mirroring the existing `_with_background` validator wrapper +
`_DERIVED_CAPABILITY_SOURCES` pattern — one source, applied uniformly, no
per-section duplication (the hand-added field on `HERO_BANNER_SCHEMA` was
removed). The 20 schema-enabled background-aware sections: `amazing_offers`,
`best_sellers`, `brand_carousel`, `category_grid`, `collection_tiles`,
`discounted_products`, `faq`, `hero_banner`, `image_slider`, `image_text`,
`multi_banner`, `newest_products`, `newsletter`, `product_section`,
`promo_cards`, `quick_links`, `rich_text`, `testimonials`, `trust_features`,
`video_section`. Saved through the existing `section.update_settings` mutation;
`validate_background_settings` stays the shape authority; write-time
`media_asset_id` ownership is enforced by the shared
`section_data_service.validate_background_asset_ownership` (§7).

**Media (CRUD), R1a — R4-native, reusing the canonical media authority.** A
merchant now manages a media-bearing section's items (hero slides / banners /
story items) INSIDE the R4 Inspector, not via a passive `target="_blank"` link.
- The Inspector embeds the canonical media manager body
  (`section_media_manager_body.html` = add control + the existing
  `section_media_list_body.html`) inline, wrapped in `[data-r4-media-manager]`,
  for both the schema-driven inspector and the media-only inspector
  (`single_banner`/`story_rail`).
- The existing `storefront_section_media_list`/`_form` views return a body-only
  partial under `HX-Request` (same HX-Request→partial pattern the header/footer
  editors use); a normal GET still returns the unchanged full legacy page. Full
  page and R4 embed share ONE form body partial (`section_media_form_body.html`)
  — no duplicate form.
- `openSection` calls `htmx.process()` on the injected Inspector so the embedded
  manager's add/edit/toggle/delete/reorder controls bind (htmx does not
  auto-process `innerHTML`), reusing the htmx already loaded by `base_admin`.
- **Context boundary (final review fix).** R4-inline context is derived from an
  EXPLICIT marker — the `HX-R4-Inline` request header (`_is_r4_inline`) — never
  from `HX-Request` alone. The legacy full-page media screen also drives
  toggle/delete/move/reorder over htmx (reswapping through the same
  `_media_list_body`), so inferring R4 context from `HX-Request` would have
  leaked the R4-only `hx-target="closest [data-r4-media-manager]"` onto the
  legacy list's Edit link (which has no such ancestor). The R4 manager container
  sets the header via inherited `hx-headers`; the drag-reorder `htmx.ajax` call
  passes it explicitly; a successful R4-inline form POST returns the refreshed
  manager body inline (a redirect would be re-followed without the marker and
  render the legacy full page). The legacy full-page flow is unchanged.
- New public accessor `media_views.media_config_for_kind` mirrors the existing
  `media_kind_for_section_key`/`media_label_for_kind` accessors. The media CRUD
  still re-scopes every request through `_get_scoped_section` (store+draft
  double guard) — tenant isolation unchanged (foreign section = 404, HX or not).
- **No** second media model / view / service / upload path / MediaAsset
  authority: the three canonical `_MEDIA_KINDS` (hero-slides, banners,
  story-items) remain the only media models, and no R4-specific media URL was
  added.

### Task 4C — Device Preview

Desktop / Tablet / Mobile controls in the R4 topbar, ported from the legacy
`sfb-v3-device-switcher`. They only change the presentation width/scale of the
one existing `#r4PreviewFrame` (1200 / 768 / 390, transform-scaled to the
canvas) — no second renderer / preview URL / iframe / `srcdoc`. `aria-pressed`
selected state; UI-only, never persisted, no new POST path. Browser QA confirms
`previewFrameCount: 1` at every viewport.

### Task 4D — Selection Sync

Selecting a Section from the R4 sidebar posts `sfb:setSelection` into the
existing preview iframe (`previewFrame.contentWindow.postMessage(..., window.location.origin)`),
from the single `R4.openSection` entry point. `preview.html` already owns
applying the highlight — not reimplemented. `R4.selected` stays the single
selection state; the inbound preview→R4 contract (`sfb:selectSection` /
`sfb:openSectionSettings`) is preserved.

## 4. Product Owner UX Contract

**ONE SELECTION → ONE CONTEXT → ONLY RELEVANT SETTINGS — confirmed.** The R4
Section Inspector is entirely schema-driven and renders only the selected
section's own schema fields (Basic/Advanced). Header/Footer are edited in Global
Design's own groups; a Section Inspector never mixes them in. Global Design and
the Section Inspector are mutually exclusive (`openSection` → `closeGlobalDesign`,
`openGlobalDesign` → `closeInspector`). Controls expose only simple Persian
labels — no registry keys, model names, JSON, engine terms, or arbitrary CSS.

## 5. Architecture / Duplication Audit

| Gate | Result | Note |
| --- | --- | --- |
| NO SECOND RENDERER | **PASS** | Preview keeps the shared renderer via the single preview iframe; 4C only rescales it. |
| NO SECOND PREVIEW ENGINE | **PASS** | One `#r4PreviewFrame` (QA: `previewFrameCount: 1`). |
| NO SECOND MEDIA AUTHORITY | **PASS** | R1a reuses `media_views` models/CRUD/endpoints inline; only new accessor `media_config_for_kind`; `_MEDIA_KINDS` unchanged (hero-slides/banners/story-items); no R4-specific media URL. |
| NO DUPLICATE MEDIA FORM | **PASS** | Full page and R4 embed share `section_media_form_body.html`. |
| NO SECOND DRAFT/LIFECYCLE | **PASS** | Edits persist through the existing Draft (`section.update_settings`); media via existing media_views persistence. |
| NO SECOND MUTATION BOUNDARY | **PASS** | Section edits route through the single `enqueueMutation`/`sendMutation` queue; media uses existing media endpoints via htmx. POST-endpoint count in `r4_editor.js` stays exactly 3. |
| NO SECOND TENANT RESOLVER | **PASS** | `resolve_store_for_service` / `_get_scoped_section` unchanged. |
| NO SECOND SETTINGS REGISTRY | **PASS** | `background` is a field TYPE in the existing schema; projected by one canonical capability helper. |
| NO SECOND SELECTION AUTHORITY | **PASS** | `R4.selected` single state; `preview.html` owns highlight. |
| NO DUPLICATE BACKGROUND OWNERSHIP VALIDATOR | **PASS** | One canonical `section_data_service.validate_background_asset_ownership`; legacy view + R4 both delegate. |
| TENANT WRITE SAFETY | **PASS** | Foreign `media_asset_id` rejected server-side before persistence (§7). |
| SCOPE CONTROL | **PASS** | Section + per-group Global scope labels; enforced panel exclusivity. |

## 6. Changed Files (generated from `git diff --name-only d3b98f2c..HEAD`)

Production / test code:

```
apps/storefront_builder/media_views.py
apps/storefront_builder/r4_views.py
apps/storefront_builder/section_registry.py
apps/storefront_builder/services/r4_mutation_service.py
apps/storefront_builder/services/section_data_service.py
apps/storefront_builder/settings_schema.py
apps/storefront_builder/static/storefront_builder/r4_editor.css
apps/storefront_builder/static/storefront_builder/r4_editor.js
apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_media_form.html
apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_media_form_body.html
apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_media_list_body.html
apps/storefront_builder/templates/dashboard/storefront_builder/partials/section_media_manager_body.html
apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html
apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/section_inspector.html
apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/section_inspector_media_only.html
apps/storefront_builder/templates/dashboard/storefront_builder/r4/partials/settings_field.html
apps/storefront_builder/tests/test_r4_foundation.py
apps/storefront_builder/tests/test_r4_inspector.py
apps/storefront_builder/tests/test_r4_mutation_api.py
apps/storefront_builder/tests/test_r4_settings_schema.py
apps/storefront_builder/views.py
```

Evidence (committed):

```
docs/qa_evidence/storefront_design_engine/phase5/task4_contextual_editor_repairs.md   (this report)
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/RECOVERY.txt
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/db-restore-proof.json
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/fixture.json
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/metrics.json
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/r4-browser-result.json
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/tenant_negatives.json
docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/shots/  (18 viewport PNGs + 2 media-context smoke PNGs)
```

The 18 viewport screenshots (6 per viewport × 3 viewports):
`<vp>-4A-4D-section-inspector.png`, `<vp>-4A-R2-global-scope.png`,
`<vp>-4B-background-picker.png`, `<vp>-4C-device-mobile.png`,
`<vp>-4C-device-tablet.png`, `<vp>-R1a-media-inline.png`
for `<vp>` ∈ {1440x900, 768x1024, 390x844}. Plus the two media-context smoke
screenshots `smoke-A-r4-media.png` and `smoke-B-legacy-media.png`.

Note: `browser.log` and `runserver.log` exist locally under `task4_browser_qa/`
but are **not committed** (matched by the repo's `*.log` gitignore rule) — they
are intentionally not part of the branch and are not claimed as evidence here.

## 7. Security Evidence (background media ownership)

- Server-side write-time validation: persisting a section
  `background.media_asset_id` is validated by the single canonical
  `section_data_service.validate_background_asset_ownership(*, store, background)`
  before save. In R4 it runs inside
  `r4_mutation_service._apply_section_update_settings` only when the patch
  touches `background`, after schema cleaning but before `section.save()`, so a
  rejection rolls back atomically (no settings/revision/history change).
- Store A cannot persist Store B media IDs — proven by
  `Task4BBackgroundAssetTenantIsolationTests` (own asset accepted; foreign
  rejected; foreign id never stored even as a dangling value).
- One authority, two callers: the legacy `views._validate_background_asset_ownership`
  delegates to the same service helper (mirrors `validate_resource_source_ownership`).
- Media CRUD tenant isolation: `Task4AR4NativeMediaTenantIsolationTests` proves a
  foreign-store section's media list is 404 (HX or not).

## 8. Test Evidence

### Per-item RED → GREEN (remediation)

| Item | RED (before) | GREEN (after) |
| --- | --- | --- |
| R1b background projection | `BackgroundCapabilityProjectionTests` failed (background only on hero_banner) | **Ran 6, OK** |
| R1a R4-native media | `Task4AR4NativeMedia*` inspector/htmx tests failed (target=_blank link; full-page-only form) | inspector + htmx + tenant tests **OK** |
| R1a htmx binding | `Task4AInspectorHtmxProcessedTests` failed (`htmx.process` absent) | **OK** |
| R2 per-group global scope | `Task4R2GlobalGroupScopeLabelTests` failed (only one panel chip) | **Ran 3, OK** |
| Media context boundary (final fix) | `Task4MediaContextBoundaryTests` failed — a legacy full-page htmx toggle wrongly produced the R4-only `hx-target` (R4 context inferred from `HX-Request` alone) | **Ran 5, OK** — legacy htmx toggle stays legacy; only the explicit `HX-R4-Inline` marker preserves inline context |

The original four repairs (4A/4B/4C/4D) RED→GREEN evidence from the initial
implementation remains valid; the remediation only broadened 4A (per-group) and
4B (all background-aware sections + R4-native media) and hardened media binding.

### Focused Task-4 suite (all repairs incl. remediation)

Focused classes across `test_r4_inspector`, `test_r4_mutation_api`,
`test_r4_foundation`, `test_r4_settings_schema` (4A scope, 4A exclusivity, R2
group scope, 4B background inspector/js/mutation/tenant/single-authority,
R1a R4-native media inspector/htmx/tenant/no-duplicate, R1a htmx-process,
media-context boundary (legacy vs R4-inline), 4C device, 4D selection sync,
background capability projection):
**Ran 64 tests … OK.**

Focused media/background subset (incl. all newly added R4-native media tests):
**Ran 34 tests … OK.**

### Required regression modules (`-v 2`)

```
python manage.py test \
  apps.storefront_builder.tests.test_r4_inspector \
  apps.storefront_builder.tests.test_r4_appearance_overrides \
  apps.storefront_builder.tests.test_r4_foundation -v 2
=> Ran 138 tests … OK
```

Combined with `test_r4_mutation_api` + `test_r4_settings_schema`:
**Ran 292 tests … OK.**

## 9. Static / Django Gates

```
python manage.py check                            => System check identified no issues (0 silenced).
python manage.py makemigrations --check --dry-run => No changes detected.
git diff --check                                  => clean
```

No migration is required (background is an existing JSON settings block; media
reuses existing models).

## 10. Browser QA

Reused the same existing browser infrastructure (the identical `playwright-core`
+ installed `chrome` channel the committed R4 QA runner uses), driving the real
running R4 editor at the correct tenant host. Environment note: the committed
`qa_storefront_builder_r4` harness hard-codes the request Host `127.0.0.1`,
which does not resolve a tenant in this multi-store sandbox (single-Store
compatibility fallback fails closed → R4 route 404); a Django test-client
request with the correct tenant Host returns 200 with all Task-4 markup, and the
browser evidence below was captured against that tenant host. No second QA
harness was committed; the ad-hoc capture script was deleted after the run.

Per-viewport confirmation (RTL primary — `document dir = rtl` at all three):

| Check | 1440×900 | 768×1024 | 390×844 |
| --- | --- | --- | --- |
| Section scope label (`فقط این بخش`) | ✅ | ✅ | ✅ |
| Global control scope labels (panel chip + 4 group chips) | ✅ | ✅ | ✅ |
| R4-native media editing (inline manager, no `target="_blank"`, inline add form loads) | ✅ | ✅ | ✅ |
| Background editing (real picker: mode + media) | ✅ | ✅ | ✅ |
| Same single `#r4PreviewFrame` for Desktop/Tablet/Mobile (count = 1; tablet→768px, mobile→390px, `aria-pressed`) | ✅ | ✅ | ✅ |
| Sidebar → iframe selection sync (`sfb:setSelection` posted) | ✅ | ✅ | ✅ |
| Global Design / Section Inspector exclusivity (`globalDesignClosedWhenSectionOpen`) | ✅ | ✅ | ✅ |
| RTL | ✅ | ✅ | ✅ |

**Media-context smoke (final review fix).** Both media workflows verified live
in the same browser infra:

- **A — R4 inline** (`shots/smoke-A-r4-media.png`): open media → add (inline
  form) → cancel back to inline list → toggle (stays inline) → Edit again
  (inline form). Result: `addFormInline: true`, `toggledInline: true`,
  `editInline: true`.
- **B — legacy full page** (`shots/smoke-B-legacy-media.png`): open the
  full-page media list → htmx toggle → click Edit. Result:
  `legacyHasNoR4Target1: true`, `legacyHasNoR4TargetAfterToggle: true` (the
  exact regression — after an htmx toggle the list stays legacy, no R4 target
  leaks), `editNavigatedFullPage: true` (Edit navigates to the full-page form).

Evidence: `docs/qa_evidence/storefront_design_engine/phase5/task4_browser_qa/`
(18 viewport screenshots + 2 media-context smoke screenshots under `shots/`,
plus `r4-browser-result.json`, `db-restore-proof.json` (DB backup/restore
`match: true`), `fixture.json`, `metrics.json`, `tenant_negatives.json`,
`RECOVERY.txt`).

## 11. Known Issues / Deferred Scope

- **Documented exception (R1b).** 8 background-aware families are context/
  media-only with NO `SettingsSchema` to attach a field to, so the R4 schema
  Inspector does not render a background control for them:
  `catalog_product_wall`, `collection_header`, `featured_products`,
  `product_description`, `product_video`, `related_products`, `single_banner`,
  `story_rail`. They render via context/domain logic, not the R4 schema
  inspector; giving them a schema-driven background control is out of Task-4
  scope. (`single_banner`/`story_rail` still get R4-native MEDIA editing via
  the media-only inspector.)
- **Pre-existing base-branch test failures (NOT introduced by Task 4)**, verified
  against a clean worktree at the certified base SHA:
  `test_r4_vertical_slice.AppearanceDomainValidatorReuseTests.test_validate_appearance_config_is_the_validator_boundary`
  and `test_views.FullscreenEditorTests` (1 failure + 1 error). Both fail
  identically on the untouched base and are outside the required Task-4
  regression scope; left as-is.
- **Committed R4 QA harness host binding** cannot resolve a tenant at `127.0.0.1`
  in a multi-store sandbox (see §10). Not changed (QA-tooling change outside
  Task-4 code scope); behaviors proven with the same browser infra at the
  correct tenant host.

**Explicitly NOT implemented (out of Task-4 scope):** Task 5 (any part), Mobile
Nav Drawer, PDT tabs, PDTX, public Modal/Quick View, STRANS, Showcase, Theme
Overlay, Random Mix, final 50-template QA.

## 12. Final Verdict

**TASK 4 STATUS: READY FOR INDEPENDENT REVIEW** — remediation + final
media-context fix complete.

Task 5 was **NOT** started.
