# Phase 5 Task 6 — Storefront Showcase R4 Facade — Implementation Report

Single canonical Task-6 implementation report. Approved architecture: Option B —
"Storefront Showcase" is an R4 **creation facade**, not a rendering authority.

## 1. Checkpoint

| Item | Value |
| --- | --- |
| Certified base | `c0ca174475bf19dd5c3ecac3857da479623e1e7d` |
| Official branch | `feature/phase5-design-expansion` (untouched) |
| Working branch | `kiro/phase5-task6-showcase-facade` (from the certified base) |
| Evidence HEAD (before this report commit) | `5a02371ca47aec065a33a844da6cee796867286e` (initial impl) → QA-evidence remediation commit (this report's own commit follows) |
| Migrations added | **ZERO** (`makemigrations --check` → "No changes detected"; no migration files changed) |
| Task 7 started | **NO** |

> **QA-evidence remediation (post-`5a02371`).** A follow-up QA-harness/evidence/
> PR-metadata pass added: a fail-fast when `--showcase` is run without `--phase3`
> (truthful invocation), a narrow Task-6 browser diagnostic gate (page/console/
> request-failure assertions), a fix for a Preview `ERR_ABORTED` (settle before
> the mobile navigation), and truthful evidence wording. **No production facade
> code changed** in this pass. Numbers below reflect the remediated run.

Approved spec: `docs/superpowers/specs/2026-09-14-phase5-task6-storefront-showcase-facade-design.md`.
Implementation plan: `docs/superpowers/plans/2026-09-14-phase5-task6-storefront-showcase-facade-implementation-plan.md`.
Discovery: `docs/qa_evidence/storefront_design_engine/phase5/task6_discovery_report.md`.

## 2. Architecture decision

`SHOWCASE IS AN R4 CREATION FACADE, NOT A RENDERING AUTHORITY.`
`PERSISTED SECTION KEY storefront_showcase: FORBIDDEN` (verified absent — registry still has exactly **36** keys).
`ONE CONCEPT = ONE CANONICAL OWNER.`

A merchant-facing "ویترین فروشگاه" inline chooser in the R4 editor Structure panel presents four content types. Each choice creates ONE EXISTING canonical section via the existing `section.add` mutation:

| Merchant choice | Canonical `section_key` |
| --- | --- |
| محصولات (Products) | `product_section` |
| دسته‌بندی‌ها (Categories) | `category_grid` |
| کالکشن‌ها (Collections) | `collection_tiles` |
| برندها (Brands) | `brand_carousel` |

Type is chosen at add time and is immutable. After creation there is NO Showcase inspector — the created section uses its own canonical `SettingsSchema`/Inspector, Resource Picker, layout controls, ProductCardData, Task-5 Quick View, and `cart:add`.

## 3. How it works (the three thin layers)

- **Server projection** — `r4_views._SHOWCASE_FACADE` (presentation-only tuple of the four content_type → canonical section_key + merchant label/description) and `r4_views._build_showcase_choices(structure_library)`, which emits a choice ONLY if its canonical section is already in the current, server-owned, page-filtered `structure_library` (built from `section_registry.list_library_groups(page_type=...)`). `showcase_choices` is added to the existing `storefront_r4_editor` context. No second legality/registry authority; future changes to a canonical section's `page_types` automatically govern Showcase.
- **Chooser markup** — an inline `<details data-r4-showcase>` disclosure in `r4/editor.html`, placed above (not replacing) the existing Add Section control. Each choice is an accessible `<button data-r4-showcase-choice data-section-key="<canonical>">` (no pseudo key). Rendered only when `showcase_choices` is non-empty.
- **Client wiring** — one delegated handler in `r4_editor.js` reads the clicked button's canonical `section_key` and calls the existing `R4.enqueueStructuralMutation({ type:'section.add', section_key, page_type: shell.dataset.r4PageType })`, then collapses the chooser. No direct `fetch`, no new mutation type, no `storefront_showcase` key, no auto-select heuristic (the merchant selects the new Structure row).

## 4. Exact changed files (`git diff --name-status c0ca174...7929d0f`)

Production:
- M `apps/storefront_builder/r4_views.py` (`_SHOWCASE_FACADE` + `_build_showcase_choices` + `showcase_choices` context)
- M `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html` (inline chooser)
- M `apps/storefront_builder/static/storefront_builder/r4_editor.js` (delegated Showcase-choice handler)
- M `apps/storefront_builder/static/storefront_builder/r4_editor.css` (chooser styling)

Tests:
- A `apps/storefront_builder/tests/test_r4_showcase_facade.py` (30 tests)

QA harness (extended, not forked):
- M `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` (`--showcase` flag, collection fixture, admin-host manifest)
- M `tools/storefront_builder_r4_qa/run.mjs` (`scenario16ShowcaseFacade`, resolver-host launch args)

Docs / evidence:
- A `docs/superpowers/specs/2026-09-14-phase5-task6-storefront-showcase-facade-design.md`
- A `docs/superpowers/plans/2026-09-14-phase5-task6-storefront-showcase-facade-implementation-plan.md`
- M `docs/superpowers/plans/2026-09-11-phase5-design-expansion-implementation-plan.md` (Task-6 APPROVED ARCHITECTURE OVERRIDE)
- A `docs/qa_evidence/storefront_design_engine/phase5/task6_discovery_report.md`
- A `docs/qa_evidence/storefront_design_engine/phase5/task6_showcase/` (3 screenshots + `r4_browser_result.json`)
- A `docs/qa_evidence/storefront_design_engine/phase5/task6_showcase_implementation_report.md` (this report)

**Strong NO-CHANGE confirmed:** `section_registry.py`, `render_service.py`, `resource_source.py`, `models.py`, `services/r4_mutation_service.py`, `services/section_structure_service.py`, `a8_ready_templates.py`, `layout_preset_registry.py`, industry templates — none changed.

## 5. Commits

| SHA | Message |
| --- | --- |
| `e526950` | docs(storefront_builder): approve Task 6 Showcase facade architecture |
| `bbccddf` | feat(storefront_builder): add R4 Storefront Showcase creation facade |
| `7929d0f` | test(qa): add R4 Showcase facade browser scenario + evidence |
| _(remediation)_ | test(qa): certify Task 6 browser invocation + add diagnostic gate (QA/evidence only; no facade change) |

The remediation commit changes only the QA harness (`qa_storefront_builder_r4.py` fail-fast + truthful help/comment; `run.mjs` diagnostic gate + `settlePreviewFrame` before mobile nav), the evidence (`task6_showcase/`), and this report. The four production facade files (`r4_views.py`, `r4/editor.html`, `r4_editor.js`, `r4_editor.css`) are **byte-for-byte unchanged since `5a02371`**.

## 6. TDD RED → GREEN evidence

Each behavior added test-first:
- Server projection: RED (`showcase_choices` absent → 6 failures) → GREEN after adding the context key.
- Chooser markup + client wiring: RED (markup/handler source-contract assertions fail) → GREEN after adding markup + delegated handler.
- Integration + guards: added and observed GREEN via the real `section.add` mutation path.

## 7. Focused test results

`apps/storefront_builder/tests/test_r4_showcase_facade.py` — **30 tests, all PASS**:
- Server projection: exactly four choices in approved order; canonical mapping (products→product_section, categories→category_grid, collections→collection_tiles, brands→brand_carousel); every emitted key is in the legal `structure_library`; a choice is omitted when its canonical section is unavailable; `storefront_showcase` absent from the registry; choices carry only presentation metadata.
- Markup: accessible inline disclosure; button per choice with canonical key; no pseudo key; existing Add Section control preserved.
- Client wiring (source-contract): reuses `enqueueStructuralMutation` + `section.add`; page_type from shell; no direct fetch; no pseudo key.
- Integration (real `section.add`): each mapping creates its canonical `section_key`; `page_type` preserved; no persisted `storefront_showcase`; created `product_section` inspector renders canonical `resource_source` + `display_mode`; the other three reach their inspectors.
- Tenant isolation: a foreign-store resource-source update on a facade-created section is rejected (HTTP 400) by the existing `validate_resource_source_ownership` — no bypass.
- Ready-Template guard: no diff to the recipe/canonical-authority files.

## 8. Regression results

- `test_r4_foundation`, `test_r4_inspector`, `test_r4_mutation_api`, `test_section_registry`, `test_r4_settings_schema` + facade = **562 OK**.
- `test_r4_resource_source`, `test_r4_resource_picker`, `test_phase4_task2_resource_source_ownership`, `test_render_service`, `test_a8_product_card_presentations` = **262 OK** (1 skipped, pre-existing).

## 9. R4 browser QA results

Extended the existing canonical R4 QA harness (`qa_storefront_builder_r4` → `tools/storefront_builder_r4_qa/run.mjs::scenario16ShowcaseFacade`) — authenticated session, SQLite backup/restore, runserver, existing Preview iframe.

### Exact certified invocation (truthful)

```
R4_QA_ONLY_SCENARIO=task6-showcase \
  DJANGO_DEBUG=True \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/opt/playwright/chromium-1232/chrome-linux64/chrome \
  python manage.py qa_storefront_builder_r4 \
    --store-slug rastisi-fashion-test --username r4qa --port <free-port> \
    --phase3 --showcase --report-dir <dir>
```

- **`--phase3` is currently REQUIRED alongside `--showcase`.** The pre-existing `run.mjs` eagerly builds Phase-3-only edit matrices at module import (`FINAL_REMEDIATION_SCALAR_EDITS` reads `manifest.phase3_fixture.final_remediation_families`), so the runner cannot load without `--phase3`. Rather than a broad Phase-3 refactor in Task 6, the command now **fails fast** with a clear `CommandError` if `--showcase` is given without `--phase3`, and the `--showcase` help text states this. `--showcase`-alone is therefore NOT a certified invocation.
- **`R4_QA_ONLY_SCENARIO=task6-showcase`** runs only the Task-6 scenario (scenarios 01–15 SKIP).
- The scenario reaches the editor via the Store's **admin-subdomain host** (`<admin_subdomain>.rastisi.localhost`) mapped to 127.0.0.1 by chromium `--host-resolver-rules` (+ `--no-proxy-server`), because this sandbox has >1 Store and the 127.0.0.1 single-Store compatibility fallback would not resolve.

### Result: `task6-showcase-facade` — **PASS (1/1)**, DB restore byte-identical (match=True).

Verified (desktop 1440 + mobile 390, RTL):
- The "ویترین فروشگاه" chooser shows exactly the four approved choices.
- Adding each type creates the canonical section (exactly one `section.add` mutation each); it appears in Structure + Preview.
- The created section's own canonical Inspector opens; `product_section` shows the canonical source + layout controls, and its Preview renders canonical product cards (`.pcard`) — Task-5 primitive reuse.
- Mobile 390 RTL: chooser reachable, no horizontal overflow, add works.

### Diagnostic gate (narrow, scoped to Task-6 events) — evidence

The scenario asserts, for events introduced during Task-6 execution:

| Metric | Value |
| --- | --- |
| Task-6 new console errors (raw) | 12 |
| — of which KNOWN PRE-EXISTING PHASE-3 FIXTURE NOISE (`qa-broken-nonexistent` broken-media 404s) | 12 |
| **Unexpected / Task-6-relevant console errors** | **0** |
| **Page errors** | **0** |
| **Unexpected request failures** | **0** (the previously-observed Preview `net::ERR_ABORTED` is fixed by `settlePreviewFrame()` before the mobile navigation) |

The 12 console 404s are the intentional Phase-3 broken-media fixtures (`brand_logos/qa-broken-nonexistent.png`, `collection_images/qa-broken-nonexistent.png`), present only because `--phase3` is required. They are matched by the exact existing `isExpectedBrokenImageNoise` classifier (URL contains `qa-broken-nonexistent`) — NOT a generic "ignore 404" rule. The **raw** `r4_browser_result.json` still records all 14 total console errors unsanitized; the gate proves **0 unexpected/Task-6-relevant** console errors.

Evidence: `docs/qa_evidence/storefront_design_engine/phase5/task6_showcase/` — `01_showcase_chooser_desktop.png`, `02_four_canonical_sections_desktop.png`, `03_showcase_mobile_390_rtl.png`, `r4_browser_result.json` (raw), `task6_diagnostics.json` (the gate summary above).

QA-harness notes (all opt-in / additive; the default R4 QA run is byte-for-byte unchanged): the `--showcase` scenario seeds one active `MerchantCollection` (so the Collections choice is legal) and ensures the Store has an `admin_subdomain`.

## 10. Django / static gates

- `manage.py check` → no issues.
- `makemigrations --check --dry-run` → **No changes detected** (ZERO migrations; no migration files changed vs base).
- `git diff --check` → clean.

## 11. Architecture diff gate — PASS

`git diff --name-status c0ca174...HEAD` inspected. Proven:
- `storefront_showcase` NOT in `SECTION_REGISTRY` (36 keys unchanged); `is_valid_section_key('storefront_showcase')` is False.
- No `StorefrontSection`/model change; no renderer change; no `ResourceSource` change; no new mutation endpoint/type; no conditional-field framework; no new PageType; no Ready-Template/DNA change; no migration.
- Production changes limited to R4 creation UX (`r4_views.py`, `r4/editor.html`, `r4_editor.js`, `r4_editor.css`) + QA harness + tests + docs.

## 12. Ready Templates unchanged

Confirmed: `a8_ready_templates.py`, `layout_preset_registry.py`, and `apps/catalog/industry_templates/` are not in the diff. Task 6 is additive merchant UX only; the 50 recipe DNA is untouched.

## 13. Task 7

**Task 7 NOT started.**
