# Phase 5 Task 6 — Storefront Showcase R4 Facade — Implementation Plan

> Implementation plan for the APPROVED Option B architecture. References the
> approved spec `docs/superpowers/specs/2026-09-14-phase5-task6-storefront-showcase-facade-design.md`
> and the discovery `docs/qa_evidence/storefront_design_engine/phase5/task6_discovery_report.md`.
> TDD throughout: no production code before its RED test is observed failing for
> the expected reason.

## Goal

Add a merchant-facing "ویترین فروشگاه" (Storefront Showcase) **creation facade**
to the R4 editor: a small inline chooser presenting four content types that
each create one EXISTING canonical section via the existing `section.add`
mutation. No new persisted section, renderer, schema, resource-source,
conditional-field framework, PageType, or migration.

Canonical mapping (immutable at add time):
- Products → `product_section`
- Categories → `category_grid`
- Collections → `collection_tiles`
- Brands → `brand_carousel`

## Architecture

- **Server projection (`r4_views.py`):** add `showcase_choices` to the existing
  `storefront_r4_editor` context. It is the four approved keys INTERSECTED with
  the keys already present in the current, page-filtered, server-owned
  `structure_library` (built from `section_registry.list_library_groups(page_type=...)`).
  This reuses the single legality authority — a content type appears in the
  chooser only if its canonical section is already legal on the current page.
  Labels/descriptions are merchant-facing UX copy in this presentation layer;
  no validator/schema/page_type/layout/resource logic is duplicated.
- **Chooser markup (`r4/editor.html`):** an inline `<details>`/`<summary>`
  disclosure next to (not replacing) the existing Add Section control, listing
  the server-projected choices as accessible buttons carrying ONLY the canonical
  `section_key` (no pseudo `storefront_showcase` value).
- **Client wiring (`r4_editor.js`):** one delegated click handler that reads the
  clicked button's canonical `section_key` and calls the existing
  `R4.enqueueStructuralMutation({ type:'section.add', section_key, page_type })`
  (page_type from `shell.dataset.r4PageType`), then collapses the chooser. No
  direct fetch, no new mutation type, no auto-select heuristic.
- **After creation:** the section is a normal canonical section; R4 opens its
  existing Inspector/schema. No Showcase inspector.

## Tech stack

Django (server view/context + tests), Django templates (chooser markup), vanilla
JS (`r4_editor.js` delegated handler), existing R4 QA harness
(`qa_storefront_builder_r4` management command + `tools/storefront_builder_r4_qa/run.mjs`,
playwright-core). No new dependencies.

## Global constraints

- ZERO migrations. `ONE CONCEPT = ONE CANONICAL OWNER`.
- Persisted `storefront_showcase` section key: FORBIDDEN.
- NO production change to: `section_registry.py`, `render_service.py`,
  `resource_source.py`, `models.py`, `services/r4_mutation_service.py`,
  `services/section_structure_service.py`, Ready-Template recipe authorities
  (`a8_ready_templates.py`, `layout_preset_registry.py` DNA, industry templates).
- If any such change appears required → STOP and report
  `TASK 6 BLOCKED — CANONICAL AUTHORITY CHANGE REQUIRED`.

## Exact files (predicted)

Production:
- `apps/storefront_builder/r4_views.py` — add `_SHOWCASE_FACADE` mapping + build
  `showcase_choices` in `storefront_r4_editor`, add to context.
- `apps/storefront_builder/templates/dashboard/storefront_builder/r4/editor.html`
  — inline Showcase chooser markup.
- `apps/storefront_builder/static/storefront_builder/r4_editor.js` — delegated
  Showcase-choice handler reusing `enqueueStructuralMutation`.
- `apps/storefront_builder/static/storefront_builder/r4_editor.css` — ONLY if a
  tiny amount of chooser styling is genuinely required.

Tests:
- `apps/storefront_builder/tests/test_r4_showcase_facade.py` — focused server +
  integration + source-contract tests.

QA (extend existing, do not fork):
- `apps/storefront_builder/management/commands/qa_storefront_builder_r4.py` —
  ensure a default-path MerchantCollection fixture exists (only if missing).
- `tools/storefront_builder_r4_qa/run.mjs` — one Showcase scenario + register in
  `main()`.

Docs/evidence:
- This plan; the approved spec; discovery report; master-plan Task-6 override
  (done); `docs/qa_evidence/storefront_design_engine/phase5/task6_showcase/` QA
  evidence; `.../task6_showcase_implementation_report.md`.

## Exact interfaces

- Server: `showcase_choices: list[{ "content_type": str, "section_key": str, "label": str, "description": str }]` in approved order (products, categories, collections, brands), filtered to legal `structure_library` keys.
- Facade mapping (presentation-only constant in `r4_views.py`), NOT a registry:
  `product_section / category_grid / collection_tiles / brand_carousel` + UX labels/descriptions.
- Client: buttons `data-r4-showcase-choice` with `data-section-key="<canonical>"`; handler enqueues `section.add`.

## RED → GREEN steps

1. **Docs checkpoint** (this plan + spec + discovery + master-plan override) — commit before any production code.
2. **Server projection** — RED `test_r4_showcase_facade.py` server assertions (choices exposed, order, mapping, legal-library intersection, no `storefront_showcase` in registry, hidden when canonical unavailable) → GREEN by adding `showcase_choices` to the editor context.
3. **Chooser markup** — RED template/source-contract assertions (chooser present, four choices, canonical keys only, no pseudo key, accessible disclosure) → GREEN by adding markup (+ minimal CSS if needed).
4. **Client wiring** — RED source-contract assertions (handler reuses `enqueueStructuralMutation`, `section.add`, key from clicked choice, page_type from shell, no direct fetch, no `storefront_showcase`) → GREEN by adding the delegated handler.
5. **Integration** — RED assertions (mapping creates the right canonical section via the real add path, page_type preserved, canonical Inspector/schema reached, tenant isolation unchanged, no persisted `storefront_showcase`, Ready-Template authority unchanged) → GREEN (mostly already satisfied by reuse; add guards).
6. **R4 browser QA** — extend the existing harness; capture evidence.

## Focused tests (`test_r4_showcase_facade.py`)

- Exactly four choices, approved order, canonical mapping.
- Every emitted `section_key` is in the current legal `structure_library`.
- A choice is omitted if its canonical section is not in the legal library (e.g. simulate by page/hidden).
- `storefront_showcase` not in `SECTION_REGISTRY`.
- Editor context contains `showcase_choices`.
- Integration: adding via each mapping (through the real `section.add` mutation path / `section_structure_service.add_section`) persists the canonical `section_key`, preserves `page_type`, and no `storefront_showcase` row is created.
- Canonical Inspector reached: the created `product_section`'s inspector renders `PRODUCT_SECTION_SCHEMA` fields (source + layout); lightweight equivalents for the other three.
- Tenant isolation: a foreign-store resource-source update on the created section is rejected by the existing `validate_resource_source_ownership` (no bypass).
- Ready-Template guard: no diff to recipe authorities.
- Source-contract (template + JS): chooser markup + handler assertions.

## R4 browser QA

Extend `tools/storefront_builder_r4_qa/run.mjs` with ONE Showcase scenario
(register in `main()`), reusing the existing authenticated-session + SQLite
backup/restore lifecycle. Ensure the default sandbox has ≥1 MerchantCollection
(add to `_prepare_r4_sandbox` only if missing). Light matrix: desktop 1440 +
mobile 390, RTL. Add each of the four types; verify the canonical section
appears in Structure + Preview, its normal Inspector opens with canonical
controls, and (product mode) the preview uses canonical product cards. Evidence
→ `docs/qa_evidence/storefront_design_engine/phase5/task6_showcase/`.

## Architecture gate

`git diff --name-status c0ca174...HEAD` must show NO production change to the
forbidden files (§Global constraints). Prove: no `storefront_showcase` in
registry; no model/renderer/ResourceSource/Ready-Template change; no new
mutation type/endpoint; no conditional-field framework; no new PageType; no
migration.

## Final regression gate

Focused Task-6 tests + relevant regressions: `test_r4_foundation`,
`test_r4_inspector`, `test_r4_mutation_api`, `test_section_registry`,
`test_r4_settings_schema`, `test_r4_resource_source`, `test_r4_resource_picker`,
`test_phase4_task2_resource_source_ownership`, `test_render_service`,
`test_a8_product_card_presentations`. Then `manage.py check`,
`makemigrations --check --dry-run` (NONE), `git diff --check`.

## Commit checkpoints

1. docs (this plan + spec + discovery + master-plan override).
2. RED/GREEN: server projection + chooser markup.
3. RED/GREEN: client wiring.
4. tests/QA: browser QA extension + evidence + implementation report.

No Task 7. No merge into the official branch.

TASK 6 IMPLEMENTATION STARTED: YES (facade only, per approved Option B)
