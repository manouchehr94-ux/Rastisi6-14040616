# Phase 5 Task 6 — Storefront Showcase R4 Facade Design

## 1. Status / approved decision

- **Status:** APPROVED architecture spec. Design only — NOT an implementation plan. No code/tests/migrations/branches are created by this document.
- **Official branch:** `feature/phase5-design-expansion`.
- **Certified checkpoint:** `c0ca174475bf19dd5c3ecac3857da479623e1e7d` (verified: local HEAD == `origin/feature/phase5-design-expansion` == this SHA; the only untracked file before this spec was `docs/qa_evidence/storefront_design_engine/phase5/task6_discovery_report.md`).
- **Approved option:** **Option B** from the Task-6 discovery report — "Storefront Showcase" is a merchant-facing **R4 creation facade** over four EXISTING canonical section types. It is NOT a new persisted section, renderer, schema, resource-source contract, or template family.
- Discovery evidence backing this decision: `docs/qa_evidence/storefront_design_engine/phase5/task6_discovery_report.md`.

## 2. Product goal

Make it easy for a merchant to add one of the four common merchandising sections through a single friendly entry point ("ویترین فروشگاه"), then configure it with the section's own existing, well-tested controls. The convenience is at ADD time; everything after creation is the existing canonical section experience.

## 3. Why Showcase is UX, not a new section

The discovery report established three findings that make a single persisted "Showcase" section architecturally unsafe, and a facade the correct choice:

1. **The four canonical sections have genuinely different schemas, layout enums, source semantics, defaults, and capabilities** — `product_section` (display_mode: carousel/grid/campaign_band; 8 data sources), `category_grid` (display_mode: 11 modes), `brand_carousel` (display_mode: grid/carousel/beauty_tabs; `show_view_all`), `collection_tiles` (`tile_style`: grid/carousel). A single section would have to either invent a second layout taxonomy, dispatch to four canonical owners, or require conditional fields.
2. **R4 SettingsSchema has NO generic conditional-field system** (no `depends_on`/`show_if`/reactive schema switching; `settings_schema.py` `SettingsField` has no such attribute; the inspector renders once and branches only on `field_type`). A content_type-switchable section is therefore not cleanly expressible today.
3. **`section.add` already exists** as the canonical structural mutation, and the four sections already have complete Inspectors. The merchant intent is fully served by choosing the type up front and then using the existing section.

Because the type is chosen BEFORE creation, the conditional-field gap is sidestepped entirely: after creation the normal schema for the selected canonical section renders. Task 6 stays small and introduces no platform-scale schema work.

## 4. Canonical mapping

The chooser maps each merchant-facing choice to exactly ONE existing `section_key`:

| Merchant choice (UX label) | Canonical `section_key` | Description shown |
|---|---|---|
| محصولات (Products) | `product_section` | نمایش محصولات جدید، منتخب، پرفروش یا انتخابی |
| دسته‌بندی‌ها (Categories) | `category_grid` | نمایش دسته‌های فروشگاه |
| کالکشن‌ها (Collections) | `collection_tiles` | نمایش مجموعه‌های فروشگاه |
| برندها (Brands) | `brand_carousel` | نمایش برندهای فروشگاه |

These four keys already exist in `SECTION_REGISTRY` (`apps/storefront_builder/section_registry.py`). The facade adds NO fifth key.

## 5. Merchant flow

1. Merchant clicks **+ افزودن بخش** in the R4 editor (existing "Add Section" affordance).
2. Among the section-library entries, a **"ویترین فروشگاه"** entry point opens a small chooser presenting exactly four options (§4 labels + descriptions).
3. Merchant selects one (e.g. «محصولات»).
4. The facade invokes the SAME canonical `section.add` mutation with the mapped `section_key` (e.g. `product_section`) and the **current `page_type`** the merchant is editing.
5. The facade waits for the existing structural mutation queue to complete, then the existing Structure panel + Preview iframe refresh through their normal paths.
6. **Selection after creation:** if the existing `section.add` mutation response returns the created section's canonical id in a way the current client already consumes, the facade opens/selects that section's normal Inspector automatically. If the current response does NOT expose the created section id safely, the facade simply refreshes the Structure panel and lets the merchant select the new section manually — it MUST NOT invent a "last section" / brittle heuristic lookup. (Implementation must confirm the exact current `section.add` response shape and choose the safe behavior; see §16 and Open Questions.)

## 6. Immutable content type decision

The Showcase type is chosen **when adding** the section and is thereafter **immutable**. Once created, the section IS the chosen canonical section type (e.g. a real `product_section`). The merchant does NOT later convert Products → Brands, etc. To use a different content type they remove the section and add a new Showcase.

Rationale: the four underlying sections have different schemas, layout enums, source semantics, defaults, and capabilities. Task 6 builds NO conversion/migration logic between section types.

## 7. Architecture boundaries

ONE CONCEPT = ONE CANONICAL OWNER. Task 6 MUST NOT introduce any of:

- new `StorefrontSection`/DB model; new migration
- new section registry or a persisted `storefront_showcase` `section_key`
- new render path / context builder
- new `ResourceSource` contract or a second layout taxonomy
- new Product / Category / Brand / Collection query authority
- new `ProductCardData` / product card implementation
- new cart path / tenant resolver / Draft-Publish lifecycle
- new R4 mutation endpoint or Inspector renderer
- new conditional-field framework
- new Showcase-specific background/media system

**Expected migrations: ZERO.**

## 8. Existing owners reused (unchanged)

- **Structural add:** `r4_mutation_service` `section.add` (dispatched via the existing R4 mutation queue) → `section_structure_service.add_section` (validates `section_key` + `page_type`).
- **Section registry:** the four existing `SectionDefinition`s and their `settings_schema`s (`PRODUCT_SECTION_SCHEMA`, `CATEGORY_GRID_SCHEMA`, `COLLECTION_TILES_SCHEMA`, `BRAND_CAROUSEL_SCHEMA`).
- **Inspector:** `storefront_r4_section_inspector` (`r4_views.py`) + `settings_field.html` + the shared Resource Picker (`storefront_r4_resource_picker`).
- **Selection/source:** `ResourceSource` (`resource_source.py`) + `_SECTION_ADAPTERS` routing (product→product, category→category, brand→brand, collection→collection).
- **Ownership guard:** `section_data_service.validate_resource_source_ownership` (and the R4 mutation-service preflight `_validate_resource_source_ownership`).
- **Render:** `render_service` builders `_product_section_context` / `_category_grid_context` / `_brand_carousel_context` / `_collection_tiles_context`.
- **Product card / Task 5:** `catalog/partials/product_card.html` (+ `product_grid.html`) with Quick View / `sfbOverlay` / `cart:add` / ProductCardData.
- **Preview + Draft/Publish:** `storefront_preview` view + `StorefrontLayoutVersion` lifecycle.

## 9. R4 integration flow

- The chooser is a thin client/UX layer in the R4 editor. It performs NO persistence itself and stores NO resource IDs.
- On selection it dispatches the existing `section.add` mutation (same JSON mutation endpoint + queue used by every other "add section" action today) with `{ type: "section.add", section_key: <mapped>, page_type: <current> }` (exact payload shape to match the current `section.add` contract — implementation must mirror how the editor already adds a section).
- It relies entirely on the existing post-mutation refresh of the Structure panel and Preview iframe. No new preview route, no new mutation type.

## 10. Inspector behavior after creation

There is NO Showcase-specific Inspector. After creation the section is a normal canonical section and R4 opens its existing Inspector:

- `product_section` → `PRODUCT_SECTION_SCHEMA`, existing Resource Picker, existing product layout controls, existing ProductCardData, Task-5 Quick View, existing `cart:add`.
- `category_grid` → `CATEGORY_GRID_SCHEMA`, category ResourceSource, existing category layout choices (11 display modes).
- `collection_tiles` → `COLLECTION_TILES_SCHEMA` (`tile_style`).
- `brand_carousel` → `BRAND_CAROUSEL_SCHEMA` (display_mode + `show_view_all`).

This is the central architecture guarantee: **after creation, the canonical section's own Inspector/schema is used verbatim.**

## 11. ResourceSource / tenant isolation

- The chooser itself selects/stores NO resource IDs — content selection happens later, inside the created section's normal Inspector via the existing Resource Picker.
- Source selection remains owned by the existing `ResourceSource` contract and picker; write-time tenant safety remains `section_data_service.validate_resource_source_ownership` (fail-closed, Store-scoped `.exists()`), invoked by the existing settings-save / R4 mutation path when a patch touches `source`.
- Because Task 6 adds NO new selection or persistence path, no new tenant-validation logic is required or permitted. Store isolation is inherited unchanged.

## 12. Page/surface behavior

- Task 6 reuses the R4 page the merchant is currently editing (`page_type`). It adds NO new page type.
- The current `StorefrontPage.PageType` values are exactly: `home`, `product_detail`, `listing`, `collection`, `search`, `cart`. There is NO `brand` and NO `campaign_landing` page type; Task 6 does not invent them.
- The four canonical sections currently inherit `ALL_PAGE_TYPES`; the facade must remain subject to each section's own `page_types` restriction (authoritative). The facade must NOT expand any page-type allowlist. If a section is not legal on the current page, `section.add` already rejects it — the chooser must surface only what is legal on the current page (or rely on the existing add-validation to reject, without inventing new rules).

## 13. Ready Template / DNA impact

Task 6 MUST NOT rewrite the 50 Ready Template recipes. They already use the canonical underlying sections (`layout_preset_registry.py`, `a8_ready_templates.py`, `apps/catalog/industry_templates/`). "Showcase" is purely additive merchant UX. Ready Template DNA remains unchanged. Recipe curation belongs to later approved tasks.

## 14. Task-4 / Task-5 reuse

Because the created section IS a normal canonical section, it automatically inherits:

- **Task 4:** the R4 Inspector, scope labels ("فقط این بخش"), background/media controls where the section is a `BACKGROUND_AWARE_SECTION_KEYS` member, selection sync, device preview — all via the existing `_finalize_registry` capability wiring. No new registration is required by the facade (the four sections already have their capabilities).
- **Task 5 (product mode):** ProductCardData, Quick View, `sfbOverlay`, `cart:add`, canonical mobile behavior — inherited because `product_section` renders through `catalog/partials/product_card.html`.

No Showcase-specific copies of any of these.

## 15. Accessibility / RTL

- The chooser must be keyboard-accessible and screen-reader labeled, following the existing R4 editor "Add Section" library patterns (roles/labels already used there). RTL is the primary direction (Persian UI).
- The chooser introduces no new overlay mechanics beyond what the R4 editor already uses; reuse the existing add-section UI affordance styling and focus behavior.

## 16. Error / stale-write behavior

- The facade reuses the existing R4 structural mutation queue and its conflict/stale-revision handling (base-revision check in the mutation service). It adds NO new conflict logic.
- If `section.add` fails (e.g. section not allowed on this page, revision conflict, rate limit), the facade surfaces the existing error path — no bespoke error handling.
- Auto-select of the created section is best-effort and safe-only: implementation must use the created id ONLY if the current `section.add` response exposes it in a way the client already consumes; otherwise refresh + manual selection. No "last section" heuristic.

## 17. TDD acceptance criteria (future RED tests — not written now)

1. The Showcase chooser exposes exactly the four approved content types (products/categories/collections/brands) — no more, no fewer.
2. Each choice maps to exactly one canonical `section_key`: products→`product_section`, categories→`category_grid`, collections→`collection_tiles`, brands→`brand_carousel`.
3. Choosing a Showcase uses the existing `section.add` mutation (no new mutation type).
4. The current `page_type` is preserved on the created section.
5. **No persisted `storefront_showcase` `section_key` is ever created** (assert the registry has no such key and no section row is persisted with it).
6. After creation, the canonical section's own Inspector/schema is used (e.g. adding a Products Showcase yields a `product_section` whose inspector renders `PRODUCT_SECTION_SCHEMA`).
7. Resource selection remains owned by the existing `ResourceSource` + picker (no new source path).
8. Tenant-crossing resources remain rejected by the existing ownership guard (`validate_resource_source_ownership`) — cross-store id rejected for the created section.
9. Ready Template recipes remain unchanged (no diff to preset/recipe files).
10. Zero migrations (`makemigrations --check` → no changes).

Risk tiering for these tests:
- HIGH: #5 (no new key), #8 (tenant isolation), #7 (single source authority).
- MEDIUM: #2/#3/#4/#6 (mapping + reuse of section.add + inspector).
- LOW: #1 (chooser contents), #9/#10 (additive/zero-migration).

## 18. Browser QA acceptance criteria (lightest sufficient — NOT Task-16 scale)

- Open **Add Section** → open the **Showcase chooser** (verify exactly four options).
- Add a **Products Showcase** → verify a `product_section` appears in Structure + Preview and the normal Product Inspector opens/works (and inherits Task-5 Quick View on a rendered card).
- Repeat for **Categories / Collections / Brands** → each yields its canonical section with its normal Inspector.
- Representative viewports **1440** and **390**, **RTL**; Preview updates through the existing iframe.
- Reuse/extend the existing harness `tools/storefront_builder_qa/public_task5_qa.mjs` (or the existing R4 editor QA approach); do NOT fork a new framework, do NOT build a Task-16-scale matrix.

## 19. Expected files (prediction; NO code changed by this spec)

Smallest likely implementation surface — primarily R4 creation UX:

- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html` — the "ویترین فروشگاه" entry + chooser markup (or a small chooser partial under the same `r4/` templates dir).
- `apps/storefront_builder/static/storefront_builder/r4_editor.js` — wire the chooser to the existing `section.add` mutation + existing refresh/selection.
- Possibly `apps/storefront_builder/r4_views.py` — ONLY if the chooser needs a read-only context helper (e.g. to list which of the four are legal on the current page); prefer static client-side mapping if no server data is needed.
- Focused R4 tests (e.g. `apps/storefront_builder/tests/test_r4_*`) for the acceptance criteria in §17.

**Strong expectation — NO production changes to:** `section_registry.py`, `render_service.py`, `resource_source.py`, `models.py`. This spec asserts these are not required because Task 6 is a facade over existing primitives; implementation must not touch them unless current-code evidence proves a genuine requirement (which would be an architectural escalation, not a Task-6 change).

## 20. Explicit non-goals

- No new backend Showcase section / no persisted `storefront_showcase` key.
- No conditional-field / schema-switching framework.
- No section-type conversion or migration between the four types.
- No Ready Template recipe rewrite.
- No new `brand` or `campaign_landing` page type; no page-type allowlist expansion.
- No new renderer, ResourceSource, ProductCard, cart path, tenant resolver, Draft/Publish lifecycle, or R4 mutation endpoint.
- No database migration.
- No start of Task 7 (or any later task).

## 21. Architecture assertions

PERSISTED SECTION KEY `storefront_showcase`: FORBIDDEN

SHOWCASE IS AN R4 CREATION FACADE, NOT A RENDERING AUTHORITY

ONE CONCEPT = ONE CANONICAL OWNER

## 22. Open questions (implementation-level only; do NOT reopen product architecture)

1. **`section.add` response shape:** does the current R4 `section.add` mutation response expose the newly created section's canonical id in a way the editor client already consumes (to auto-open its Inspector)? Implementation must confirm from current code; if not, use refresh + manual selection (no heuristic). Evidence pointer: `r4_mutation_service` `_apply_section_add` / `section_structure_service.add_section` return values and how `r4_editor.js` currently handles the add response.
2. **Chooser entry point placement:** should "ویترین فروشگاه" appear as one entry in the existing section library grouping (`section_registry` library categories) that opens a sub-chooser, or as a distinct editor affordance? Prefer reusing the existing library-grouping metadata if it can present a sub-chooser without a new section key.
3. **Per-page legality display:** should the chooser hide a content type that is not legal on the current `page_type`, or show all four and let the existing `section.add` validation reject? Prefer surfacing only legal options using the existing `is_section_allowed_on_page` check (read-only), with no new rules.

TASK 6 IMPLEMENTATION STARTED: NO
