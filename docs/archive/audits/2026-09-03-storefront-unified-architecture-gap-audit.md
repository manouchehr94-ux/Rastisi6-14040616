# RastiSi Storefront — Unified Architecture Gap Audit

**Date:** 2026-09-03
**Scope:** Storefront Builder, Store Appearance / Design Engine, 50 Ready Templates, Direct Preview Editing, Content Hub, Design Lab, Demo Store, Product Detail, campaign/timed-offer presentation, versioning, security, QA.
**Audited commit:** `60e1ee7199fe38328c12a807fa842e7249582907`
**Branch:** `feature/storefront-builder-r4`
**Type:** Discovery / classification only. No product code, migrations, tests, or specs were modified.
**Master specification:** `docs/superpowers/specs/2026-09-03-rastisi-storefront-builder-unified-architecture-design.md` (with the 2026-09-03 product-architecture doc, the 2026-09-01 design-engine doc, and the 2026-08-31 R4 design doc as supporting context).

---

## Authoritative status counts

Derived directly from the 61-row Capability Gap Matrix (§4).

```
TOTAL CAPABILITIES: 61
COMPLETE:        28
PARTIAL:         25
MISSING:          5
LEGACY_CONFLICT:  2
UNKNOWN:          1
NOT_APPLICABLE:   0
```

Sum: 28 + 25 + 5 + 2 + 1 + 0 = 61.

---

## 1. Executive Summary

RastiSi has a strong, correctly-shaped backend foundation for the Unified Architecture, a partially-built merchant experience layer, and a confirmed data-loss conflict in template switching.

The engineering layer is on-spec: a single **Store Appearance engine** (`apps/storefront_builder/storefront_appearance/`) that **adapts existing registries rather than duplicating them**, persists a **typed manifest on the existing Draft**, validates server-side with a **strong security boundary**, and resolves through the **one shared renderer used by both Preview and Public**. The **Draft/Publish/Undo/Redo/stale-write lifecycle is complete and tested**, the **50 Ready Templates are real, registry-validated DNA recipes**, and the **Content-vs-Commerce boundary is cleanly enforced** — the Builder has no write path to price/stock/SKU/ProductImage/orders/promotions. 315 targeted tests were executed against an isolated test database and passed.

The experience layer is partially present. R4 already supports **section-level click-to-edit** (clicking a section in the preview opens that section's tabbed Inspector) and **immediate autosaved Preview updates with no Apply button**. What remains missing is the depth the Unified Architecture calls the primary experience: **element/child click identity, the ~65–70% contextual panel, parent/child breadcrumb navigation, click-to-edit for header/footer/logo/badge, component-selection UI, Content Hub, and Design Lab**.

The headline conflict is fully substantiated: **switching a Ready Template destroys the merchant's customized page structure and their section-local content/settings by default.** Section titles/subtitles, manual product/brand selections and ordering, rich-text bodies, appearance overrides, merchant-added/duplicated sections, and section-scoped hero slides/banners/stories (CASCADE-deleted) are all rebuilt from the template recipe. Only independent domain records (products, product images, categories, brands, collections, store-global media) survive. Through the R4 mutation path there is not even an automatic checkpoint. This is the inverse of the approved rule, which requires preserving merchant content and customization by default and making re-application of template structure an explicit action.

Two further conflicts: two editor shells coexist (the fuller click-to-edit lives on the legacy shell slated for retirement), and timed-offer countdown timing lives in Appearance rather than Commerce. Header/Footer/Mega-Menu designs already exist and render live — the gap there is registration/selection UX, so a reuse-first approach applies.

**Overall:** evolve a strong foundation; do not rewrite. Reuse the engine, lifecycle, registries, templates, the existing header/footer/mega-menu design assets, and the existing preview bridge. Concentrate new work on the merchant experience and on correcting the template-switch preservation and timed-offer-ownership conflicts — template-switch preservation first, because it is a confirmed merchant-data-loss issue.

---

## 2. Intended Product Model

One shared, versioned, server-validated Store Appearance engine; 50 curated Ready-Template DNAs (recipes, not applications); merchant content and commerce truth kept separate from appearance; Direct Preview Editing (click the visible element → ~65–70% contextual parent/child tabbed panel) as the primary experience, backed by live Preview + autosaved Draft + explicit Publish + Undo/Redo/history/restore; a secondary Content Hub over the same data; Home free, Product Detail guided, other pages theme-driven; Header/Footer/Mega Menu model-first and protected; a Template-DNA → Global → Section → Element → Local override chain where child overrides survive parent changes and customized Home structure and section content are preserved by default (re-applying template structure is an explicit action); a coherent Button/Badge/Tag/Ribbon design language; automatic responsive behavior, automatic image crop, and a single Media Picker; template switching that preserves content and customizations by default; an optional transient Design Lab; a Demo Store on the same renderer; one shared renderer for Preview/Public/Design Lab/Demo; strict typed/registered/tenant-scoped, no-arbitrary-code security; and timed-offer truth owned by Commerce/Promotion, with appearance presenting only.

---

## 3. Current Architecture Map (reality)

`shop_core` Django project; storefront work in `apps/storefront_builder/`.

**Two editor shells coexist (strangler migration), both routed in `apps/dashboard/urls.py`:**

- **Legacy R2/R3:** `storefront-builder/` → `views.storefront_editor`. Full click-to-edit bridge in `templates/storefront_builder/preview.html:84-210` emitting `sfb:openSectionSettings`, `sfb:selectSection`, `sfb:openHeaderSettings`, `sfb:openFooterSettings`, `sfb:openEntityEditor`. Template apply through this shell uses `apply_preset_with_checkpoint` (`views.py:2043`).
- **R4:** `storefront-builder/r4/` → `r4_views.storefront_r4_editor`, feature-gated by `StorefrontLayout.r4_editor_enabled` (default `False`, `models.py:211`). The R4 preview reuses the same `preview.html`; `static/storefront_builder/r4_editor.js:789` listens for `sfb:selectSection`/`sfb:openSectionSettings` → `R4.openSection()` (opens the tabbed Inspector) plus `sfb:sectionCommand`/`sfb:blockCommand` (duplicate/remove/move). It does not handle header/footer/entity messages. Preview updates via an immediate iframe reload after each autosaved mutation; there is no per-edit Apply button. Template apply through the R4 mutation `appearance.template.apply` calls raw `apply_preset` with no checkpoint (`services/r4_mutation_service.py:411`).

**Data model** (`models.py`): `StorefrontLayout` (per-store pointers + `r4_editor_enabled`), `StorefrontLayoutVersion` (immutable-after-publish; draft/published/archived; `edit_revision` optimistic token; `template_provenance`; `template_baseline_snapshot`), `StorefrontPage`, `StorefrontSection` (its `settings` JSON holds all section-local merchant state; reverse relations `hero_slides`/`banners`/`story_items`; `is_locked`; `template_slot_key`), `StorefrontContainer`/`StorefrontCell`, edit-history. `HeroSlide`/`PromotionalBanner`/`StoryRailItem` each carry a `section` FK with `on_delete=models.CASCADE` (`apps/content/models.py:414`).

**Store Appearance engine** (`storefront_appearance/`): 10 component families with `renderer_role` and `safe_default_component_key` (`families.py`); 119 `ComponentDefinition`s synthesized at import time from the existing registries — `global_region_registry`, `section_registry`, `container_service.LAYOUT_PRESETS`, `appearance_registry`, card/badge choices — each carrying a symbolic `registry_reference`, never a renderer path (`adapters.py`); frozen into `COMPONENT_REGISTRY` (`registry.py`); server-side security in `validation.py` (forbidden markers for `<script`/`<style`/`javascript:`/`{{`/`{%`, forbidden setting keys `html`/`css`/`javascript`/`renderer`/`template`/`path`/`raw_json`, a closed empty `ALLOWED_SETTINGS_BY_FAMILY`, registered-key + family enforcement, bounded JSON); `compatibility.py` (hard errors vs advisory warnings/score); manifest persisted at `appearance_config["store_appearance"]` with header/footer/motion mirrored to legacy locations (`persistence.py`); resolved into `ResolvedStoreAppearance` for rendering (`rendering.py`); 78 "advertised" keys plus `recipe_signature`/coverage helpers (`inventory.py`).

**Mutations** (`services/r4_mutation_service.py`): `apply_mutation` (`@transaction.atomic`) → `_lock_active_draft` (store-scoped `select_for_update` on `StorefrontLayout`, resolves the active DRAFT, compares `base_revision` → `R4StaleRevision`/409) → allowlisted `_dispatch_mutation` (`section.update_settings/add/remove/duplicate/move`, `appearance.update`, `header.update`, `footer.update`, `appearance.component.update`, `appearance.manifest.apply`, `appearance.template.apply`) → `edit_history_service.record_change` → `edit_revision += 1`. `apply_history_command` handles undo/redo; `publish_draft` delegates to `layout_service.publish`.

**Rendering** (`services/render_service.py`): `build_page_render_items` overlays resolved appearance in-memory on a `copy(section)`; the persisted Section is never rewritten. Public rendering enters via `apps/catalog/views.py::home` → `storefront_context_service.build_universal_storefront_context`; Preview via `views.storefront_preview`. One renderer, two callers.

**Header / Footer / Mega Menu assets:** real, live, data-driven design partials under `templates/storefront_builder/partials/global_header/` (21 partials, including the shared `_shared/category_mega_menu.html` used by header variants `marketplace_search_first.html:69` and `promo_search_nav.html:76`, plus the lighter `_shared/category_link_row.html`) and `.../global_footer/` (25 partials). The Mega Menu is fed by `apps/catalog/context_processors.py::nav_categories` (real, store-scoped) and is tested (`tests/test_u2a_global_header_system.py:216`). Mega Menu is currently a header-variant capability rather than an independently selectable Store Appearance family (the `mega_menu` family registers only `mega_menu.none.v1`).

**Templates & apply** (`a8_ready_templates.py`, `services/preset_service.py`): 50 `_RecipeSpec`s become `LayoutPresetDefinition`s. `apply_preset` is Draft-only and, for each page the preset covers (Home is always covered — `a8_ready_templates.py:217`), runs `page.containers.all().delete(); page.sections.all().delete(); StorefrontSection.objects.bulk_create(rows)` where `rows` come from `_build_sections_for_page()` (`preset_service.py:258-271`); that builder derives each section's `settings` only from the preset's `entry.settings` or `definition.default_settings()` and never merges the previous `StorefrontSection.settings`.

**Sections:** 36 registered section types; only 4 carry an R4 `settings_schema` (`brand_carousel`, `hero_banner`, `product_section`, `rich_text`); the rest still use legacy validators.

**Demo:** `apps/stores/management/commands/seed_ready_template_fashion_demo.py` seeds the `rasti-mode-demo` store via real models and real services and renders through the public renderer (idempotent, slug-isolated).

---

## 4. Capability Gap Matrix (authoritative, 61 rows)

| # | Capability | Status | Existing implementation | Missing / incorrect part | Evidence |
|---|---|---|---|---|---|
| 1 | Single Builder shell | PARTIAL | R4 shell exists, feature-gated | Two shells; richer click-to-edit on legacy | `dashboard/urls.py:219-251`; `models.py:211` |
| 2 | Draft state + autosave | COMPLETE | mutation queue + save-state indicator | — | `r4_mutation_service.apply_mutation`; `r4_editor.js:133` |
| 3 | Stale-write protection | COMPLETE | `base_revision` compare → 409 | — | `r4_mutation_service._lock_active_draft` |
| 4 | Preview updates after every change | COMPLETE | autosave + immediate iframe reload, no Apply | reload is acceptable per requirement | `r4_editor.js:147-149`; `#r4SaveState` |
| 5 | Publish → Public only | COMPLETE | `publish_draft` → `layout_service.publish` | — | `r4_mutation_service.publish_draft` |
| 6 | Undo / Redo | COMPLETE | `apply_history_command` + edit history | — | `r4_mutation_service.apply_history_command` |
| 7 | Version history / restore Published | COMPLETE | versioned model, RESTORED source, restore→new Draft | — | `models.py` `StorefrontLayoutVersion.Source.RESTORED` |
| 8 | Renderer parity (Preview/Public) | COMPLETE | one `build_page_render_items` for both | — | `render_service.py`; `catalog/views.home`; `views.storefront_preview` |
| 9 | Component registries (reuse, not duplicate) | COMPLETE | adapters synthesize from existing registries | — | `storefront_appearance/adapters.py`; `registry.py` |
| 10 | Appearance/global-region/layout/section registries | COMPLETE | present and wired | — | `appearance_registry.py`, `global_region_registry.py`, `layout_preset_registry.py`, `section_registry.py` |
| 11 | Semantic/versioned component keys | COMPLETE | stable `family.variant.vN` keys | — | `COMPONENT_REGISTRY` keys |
| 12 | Server-side schema validation (no arbitrary code) | COMPLETE | forbidden markers + closed allowlist + registered-key | — | `storefront_appearance/validation.py` |
| 13 | Compatibility metadata | PARTIAL | hard vs advisory scoring | Header↔Mega-Menu path unexercised | `storefront_appearance/compatibility.py` |
| 14 | Safe defaults / deprecation / versioning | COMPLETE | `safe_default_component_key` per family; version keys | — | `families.py`; `contracts.py` |
| 15 | Exactly 50 Ready Templates | COMPLETE | 50 unique recipes, all validate against registry | — | `a8_ready_templates.py`; `tests/test_a8_ready_template_catalog.py` |
| 16 | Template DNA structure + schema version | COMPLETE | typed selections + composition + `schema_version=1` | — | `a8_ready_templates.py::_manifest` |
| 17 | Template diversity gate | PARTIAL | pairwise-unique structural signatures | 2 fonts, 2 badges, 10 repeated compositions; mega menu unused | `storefront_appearance/inventory.py::recipe_signature`; `tests/test_a8_template_diversity.py` |
| 18 | Component coverage matrix | PARTIAL | all 78 advertised components covered (0 exceptions) | 41 of 119 registry components unused; aspirational targets unmet | `tests/test_a8_component_coverage.py` |
| 19 | Template apply = explicit preset, Draft-only | COMPLETE | Draft-only; published version untouched | — | `services/preset_service.py` |
| 20 | Template switch preserves independent domain records (products, product images, categories, brands, collections, store-global media) | COMPLETE | these records are not deleted by apply | — | `preset_service.py` docstring; grep confirms no content-model writes |
| 21 | Template switch preserves section-local merchant state (section titles/subtitles, manual product/brand IDs and ordering, rich-text body, section-scoped media, appearance overrides, merchant-added/duplicated sections) | LEGACY_CONFLICT | wholesale delete+rebuild of covered pages; settings from preset/default only; section-scoped media CASCADE-deleted; R4 path has no checkpoint | destroyed by default (inverse of Unified AC #8) | `preset_service.py:258-271,445-452,840`; `content/models.py:414`; `r4_mutation_service.py:411` |
| 22 | All 50 templates available to all industries | UNKNOWN | templates registered globally | ranking/hiding path not located | `layout_preset_registry.py` |
| 23 | Header library (designs) | PARTIAL | 21 live header partials / 22 registered components | no gallery selection UX | `partials/global_header/*.html`; registry |
| 24 | Footer library (designs) | PARTIAL | 25 live footer partials / 16 registered components | no gallery selection UX | `partials/global_footer/*.html`; registry |
| 25 | Mega Menu | PARTIAL | live `category_mega_menu.html` used by 2 header variants, real data, tested | not an independent selectable R4 family; only `none` registered | `_shared/category_mega_menu.html`; `marketplace_search_first.html:69`; `promo_search_nav.html:76`; `tests/test_u2a_global_header_system.py:216` |
| 26 | Hero library | PARTIAL | 19 registered | no picker UI; several tokens collapse to one variant | registry; `a8_ready_templates.py::_HERO_VARIANTS` |
| 27 | Product Card / Product View | PARTIAL | card 17 / product_view 13 registered | no picker UI | registry |
| 28 | Button/Badge/Tag/Ribbon coherent design language | PARTIAL | global `button_style`/`button_radius`/`radius` tokens; badge family (2) | Tag/Ribbon not distinct families; badge only 2 variants | `appearance_registry.py:89-90`; registry |
| 29 | Mobile Bottom Navigation | PARTIAL | 9 registered, used by templates | no explicit merchant control UI | registry |
| 30 | Motion | PARTIAL | 3 registered | vs aspirational target ~20 | registry |
| 31 | Direct Preview Editing (click visible element → edit) | PARTIAL | section click → tabbed R4 Inspector; duplicate/remove/move from preview | element/child identity, header/footer/logo/badge click-to-edit, ~65–70% panel, breadcrumb | `r4_editor.js:789-821`; `preview.html:84-210`; `tests/test_r4_inspector.py:199-200` |
| 32 | ~65–70% contextual editing panel | MISSING | Inspector is a side aside | no context-aware ~65–70% surface opened from the canvas | `r4/editor.html`; `r4_editor.css` |
| 33 | Parent/child tabs + breadcrumb | PARTIAL | Inspector has tabs (`data-r4-tab`) | no parent/child navigation or breadcrumb | `r4_editor.js:186-191`; `section_inspector.html` |
| 34 | Relevant-only controls per element | PARTIAL | schema-driven Inspector fields | only 4 of 36 sections schema-enabled | `r4_views.py:29-40`; section registry |
| 35 | Provenance language ("using global/template", "make specific") | MISSING | — | no provenance UX for global/template/section sources | grep empty |
| 36 | Local overrides + inheritance chain | PARTIAL | typography-only section override | not full Template→Global→Section→Element→Local; no element layer | `services/section_appearance_service.py` |
| 37 | Child override survives parent change | PARTIAL | unrelated global keys preserved (typography slice) | only proven for typography | `tests/test_r4_appearance_overrides.py:185` |
| 38 | Reset to parent/template | PARTIAL | baseline/page/field/header/footer reset services | field/element-level reset UX not surfaced | `preset_service.py` reset functions |
| 39 | Independent single-component mutation | COMPLETE | `appearance.component.update` changes one family (backend) | — | `r4_mutation_service._apply_appearance_component_update` |
| 40 | Content Hub | MISSING | — | no centralized merchant-facing content surface | grep empty |
| 41 | Content vs Commerce boundary | COMPLETE | no Builder write path to commerce truth | — | grep (zero matches); mutation allowlist |
| 42 | Product-image management shortcut | PARTIAL | image management lives in dashboard app | no in-Builder "manage this product's images" shortcut surfaced | `media_views.py` (content only); `apps/dashboard/` |
| 43 | Product section automatic rules | COMPLETE | newest/discounted/best/most-viewed/by-category/brand/collection | — | `resource_source.py`; `section_data_service.py` |
| 44 | Product section manual selection/order | PARTIAL | Resource Picker UI is Product/Brand only | Category/Collection valid backend but not in picker UI | `r4_views.py::_PICKER_UI_KINDS` |
| 45 | Graceful empty states | COMPLETE | no products → clean empty; no hero → omitted | — | `section_data_service.py`; `apps/content/README.md:184` |
| 46 | Media Picker (unified, reuse, crop, focal, responsive) | PARTIAL | media upload + asset lifecycle exist | no single unified picker with crop/focal across all points | `media_views.py`; `tests/test_media_asset_lifecycle.py` |
| 47 | Home add/remove/reorder/repeat | COMPLETE | structure mutations wired in R4 | — | `section_structure_service.py`; `tests/test_r4_vertical_slice.py` |
| 48 | Product Detail guided customization | MISSING | fixed sections only (product_main/description/related/video) | no curated layouts + controlled-area controls | section registry `product_detail` sections |
| 49 | Other pages theme-driven | COMPLETE | pages inherit global design | — | `a8_ready_templates.py::_common_pages`; render path |
| 50 | Header/Footer protected controls | PARTIAL | patch allowlist = variant only | protection exists, but no gallery/limited-control UX | `r4_mutation_service._apply_header_update/_apply_footer_update` |
| 51 | Design Lab | MISSING | — | no lab surface, transient state, Random Mix, Compare, apply-to-Draft | grep empty |
| 52 | Demo = same models/renderer | COMPLETE | real models + real services + public renderer | — | `seed_ready_template_fashion_demo.py` |
| 53 | Demo completeness (realistic store) | PARTIAL | products/categories/brands/collections/hero/banners/stories/footer | no blog/editorial; no festival/timed-offer domain data | seed command |
| 54 | Demo isolation / idempotence | COMPLETE | slug-scoped, get_or_create, `--reset` slug-only | — | `seed_ready_template_fashion_demo.py:429-451,522-545` |
| 55 | Campaign / festival presentation | PARTIAL | `amazing_offers` section, `campaign_band`, `sale` badge | thin festival visuals; no promotion-linkage model | `section_registry.py:1557-1571` |
| 56 | Timed-offer truth in Commerce | LEGACY_CONFLICT | countdown hours is a section setting | catalog has only `discount_percent`; no `sale_start`/`sale_end` | `catalog/models.py:179,299`; `section_registry.py:1566-1568` |
| 57 | Security: no arbitrary HTML/CSS/JS/JSON/paths | COMPLETE | forbidden markers + closed allowlist | — | `storefront_appearance/validation.py` |
| 58 | Tenant isolation | COMPLETE | store-scoped locks + ownership validation | — | `r4_mutation_service.py` |
| 59 | Registered/versioned/server-validated values only | COMPLETE | manifest = component keys + typed settings | — | `validation.py`; `persistence.py` |
| 60 | Renderer parity across Preview/Demo/Lab/Public | PARTIAL | Preview=Public=Demo one renderer; Lab absent | Lab parity pending Lab | render path |
| 61 | No duplicated impl / dup renderer / runtime FS discovery / dynamic import | COMPLETE | shared implementation, deterministic lookup | — | `adapters.py`; `render_service.py` |

**Status tally (by row number):**

- **COMPLETE (28):** 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 19, 20, 39, 41, 43, 45, 47, 49, 52, 54, 57, 58, 59, 61
- **PARTIAL (25):** 1, 13, 17, 18, 23, 24, 25, 26, 27, 28, 29, 30, 31, 33, 34, 36, 37, 38, 42, 44, 46, 50, 53, 55, 60
- **MISSING (5):** 32, 35, 40, 48, 51
- **LEGACY_CONFLICT (2):** 21, 56
- **UNKNOWN (1):** 22
- **NOT_APPLICABLE (0):** none

Total: 28 + 25 + 5 + 2 + 1 + 0 = 61.

---

## 5. What Is Already Complete (end-to-end)

1. R4 Draft/Publish/Undo/Redo/history/restore lifecycle with a single mutation boundary, transactional locking, tenant scoping, and `base_revision` stale-write rejection (409).
2. One shared renderer for Preview and Public.
3. Store Appearance engine reusing existing registries — no parallel registry stack.
4. Typed appearance manifest persisted on the existing Draft, Draft-only.
5. Server-side security/validation boundary (no arbitrary HTML/CSS/JS/paths).
6. Exactly 50 registry-validated Ready-Template DNA recipes with pairwise-unique structural signatures.
7. Template apply is explicit and Draft-only; the published version is untouched.
8. Template switch preserves independent domain records (products, product images, categories, brands, collections, store-global media).
9. Content-vs-Commerce boundary — no Builder write path to commerce truth.
10. Home section add/remove/reorder/duplicate through shared structure services.
11. Immediate autosaved Preview updates with no Apply button.
12. Demo Store on real models + real services + public renderer, idempotent and slug-isolated.
13. Independent single-component mutation (backend).
14. Tenant isolation; registered/versioned/server-validated values only; no duplicated renderer or dynamic import.

Explicitly not complete: preservation of section-local merchant state on template switch (row 21, LEGACY_CONFLICT).

---

## 6. What Exists But Is Incomplete (Partial)

- **Template switch content preservation is only partial** — independent domain records survive, but section-local content/settings and section-scoped media do not (rows 20/21).
- **Builder shell singularity** — R4 is gated alongside legacy; richer element/entity click-to-edit is on legacy (row 1).
- **Direct Preview Editing** — section-level click-to-edit works; element/child identity, header/footer/logo/badge editing, the ~65–70% panel, and parent/child breadcrumb remain (rows 31, 33).
- **Inheritance/override** — typography-only slice; no element layer or field-level reset UX (rows 36, 37, 38).
- **Header/Footer/Mega Menu** — real designs exist and render live; the gap is registering Mega Menu as a selectable family and building model-first gallery + protected-control UX (rows 23, 24, 25, 50).
- **Component libraries & template diversity** — below aspirational targets; limited fonts/compositions; 41/119 components unused (rows 17, 18, 26, 27, 28, 29, 30).
- **Product section manual selection** — Category/Collection picker UI (row 44).
- **Responsive** — contracts declared; broad Tablet/Mobile QA evidence thin (implicit in QA state).
- **Media Picker** — one unified picker with auto-crop + focal + reuse (row 46).
- **Campaign/festival presentation, demo completeness, product-image shortcut, renderer parity vs Lab** (rows 55, 53, 42, 60).

---

## 7. What Does Not Exist Yet (Missing — the 5 matrix MISSING rows)

1. ~65–70% context-aware editing panel opened from the canvas (row 32).
2. Provenance language UX — "using global/template" / "make specific for this section" (row 35).
3. Content Hub (row 40).
4. Product Detail guided customization — curated layouts + controlled-area controls (row 48).
5. Design Lab — transient state, Random Mix, Compare, per-family locks, apply-to-Draft (row 51).

Element-level click-to-edit, header/footer/logo/badge click-to-edit, component pickers, and registering Mega Menu as a family are the incomplete parts of PARTIAL rows (31, 25, 26, 27, 50); they are real work, but the underlying capability is partially present, so they are not counted as MISSING rows.

---

## 8. Legacy / Architectural Conflicts

1. **Template switch destroys section-local merchant state by default (row 21 — CRITICAL).** `_build_sections_for_page` rebuilds each section's `settings` from the preset entry or `default_settings()` only (`preset_service.py:258-271`) and never merges the prior `StorefrontSection.settings`; `page.sections.all().delete()` runs for every covered page and Home is always covered (`preset_service.py:445-452`; `a8_ready_templates.py:217`); section-scoped `HeroSlide`/`PromotionalBanner`/`StoryRailItem` are CASCADE-deleted with the section (`content/models.py:414`); and the R4 mutation path calls raw `apply_preset` with no checkpoint (`r4_mutation_service.py:411`). The code itself documents that a merchant-created section does not survive (`preset_service.py:840`). Lost: section titles/subtitles, `product_ids`/`brand_ids` manual selections and ordering, `rich_text` body, section media, `appearance_overrides`, and merchant-added/duplicated sections. This is the inverse of Unified AC #8. The legacy view path (`views.py:2043`) at least archives a recoverable checkpoint via `apply_preset_with_checkpoint`, but that is recovery, not preservation, and it is absent from the R4 path.
2. **Timed-offer truth in Appearance (row 56 — HIGH).** Countdown hours is a section setting (`section_registry.py:1566-1568`); the catalog has only `discount_percent` with no `sale_start`/`sale_end` (`catalog/models.py:179`). The Unified Architecture requires timed-offer truth in Commerce/Promotion.

Supporting conflicts tracked under PARTIAL rows rather than as separate LEGACY_CONFLICT rows: two editor shells with the fuller click-to-edit on legacy (row 1); only 4 of 36 sections R4-schema-enabled (row 34); festival modeled via tags/collections rather than a promotion entity (row 55).

---

## 9. Reusable Existing Work

- The entire `storefront_appearance/` engine (contracts, families, adapters, registry, compatibility, validation, persistence, rendering, inventory).
- `services/r4_mutation_service.py` — the single mutation boundary; extend with new mutation types rather than replace.
- `services/render_service.py` + `storefront_context_service` — one renderer for Preview and Public.
- `StorefrontLayout` / `StorefrontLayoutVersion` version model (immutable-after-publish, revision token, restore source).
- Registries: `appearance_registry.py`, `global_region_registry.py`, `layout_preset_registry.py`, `section_registry.py`, `variant_contract.py`, `palette_pack_64.py`.
- `a8_ready_templates.py` + `storefront_appearance/inventory.py` (recipes, signatures, coverage).
- The live header/footer/mega-menu design partials, including `_shared/category_mega_menu.html` and `_shared/category_link_row.html` — adapt these into registered selectable families; do not rebuild.
- The R4 preview↔editor message bridge (`r4_editor.js:789-821` + `preview.html`): the section-level path is done; extend the same bridge for element/global identity rather than reintroducing the legacy shell.
- The `template_baseline_snapshot` + granular reset machinery — the natural mechanism to invert the template-switch default toward preservation.
- Demo seed/refresh/capture tooling; Playwright runners under `tools/`.
- The Content-vs-Commerce boundary (keep the Builder read-only over catalog/commerce).

---

## 10. Code That Should NOT Be Rebuilt

- `storefront_appearance/` (all modules).
- `services/`: `r4_mutation_service`, `layout_service`, `render_service`, `preset_service`, `edit_history_service`, `section_structure_service`, `storefront_context_service`.
- `models.py` version/pointer/revision model.
- The registries listed in §9.
- `a8_ready_templates.py` + `inventory.py`.
- `templates/storefront_builder/partials/global_header/*` and `global_footer/*`, including `_shared/category_mega_menu.html` and `_shared/category_link_row.html` — reuse/adapt.
- The R4 message bridge (`r4_editor.js`) and `preview.html` — extend, do not replace.
- Demo tooling.

---

## 11. UX Gaps (backend capable, not merchant-usable)

- Component selection has no UI (`appearance.component.update` / `appearance.manifest.apply` exist and are validated, but no template or JS emits them).
- Direct Preview Editing is only section-level; no element/child, header/footer/logo/badge click-to-edit, no ~65–70% panel, no parent/child breadcrumb.
- Mega Menu / Header / Footer selection UX absent despite live designs — merchants cannot browse and choose them as a gallery.
- Category/Collection manual selection not exposed in the Resource Picker UI.
- Only 4 of 36 sections are inspector-editable; most sections still require legacy forms.
- No Content Hub UI despite existing content models.
- No in-Builder product-image "manage in catalog" shortcut surfaced.
- No provenance messaging (global vs template vs section source), including the store-global HeroSlide case.
- No warning that switching a template will discard section-local edits.

---

## 12. Data / Domain Ownership Gaps

- Clean where it matters most: the Builder never writes price/stock/SKU/ProductImage/orders/promotions (structurally enforced).
- Template-switch preservation gap: independent domain records survive, but section-local merchant state and section-scoped media are destroyed — the platform effectively asserts ownership over section-local content the merchant authored (rows 20/21).
- Timed-offer ownership is misplaced: countdown timing is a section setting; no Commerce `sale_start`/`sale_end` (row 56).
- Festival/promotion is modeled via tags/collections/`discount_percent` rather than a promotion entity.
- Global-vs-section content provenance (HeroSlide): store-scoped global content can render with no in-context explanation, and there is no provenance mapping to the edit context.

---

## 13. 50 Ready Templates State

- Exactly 50 registered, unique-keyed DNA recipes; all 50 validate cleanly against `COMPONENT_REGISTRY`.
- Diversity: pairwise-unique structural signatures (gate passes), but only 2 fonts, 2 badges, 10 repeated Home compositions, and `mega_menu.none.v1` on all 50.
- Coverage: all 78 advertised components used (0 exceptions), but 41 of 119 registry components unused; aspirational library targets unmet.
- Independent domain content preserved on apply; no demo copy; Draft-only. Section-local content, settings, structure, and section-scoped media are not preserved on switch (rows 20/21). Through the R4 path there is no automatic recovery checkpoint.
- All-industries availability: ranking/hiding path not located (UNKNOWN).
- Visual QA: only 8 of 50 templates have committed previews (`apps/storefront_builder/static/ready_template_previews/`), desktop-only; the real Playwright capture capability exists but is not exercised for all 50.

---

## 14. Component Library State (actual registered counts)

Full `COMPONENT_REGISTRY` = 119; advertised A8 subset = 78 (all covered).

| Family | Registered | Advertised | Live design assets | Aspirational target |
|---|---|---|---|---|
| header | 22 | 12 | 21 partials | ~20 |
| hero | 19 | 13 | — | ~20 |
| footer | 16 | 8 | 25 partials | ~20 |
| layout | 17 | 9 | — | ~20 |
| product_view | 13 | 7 | — | ~15 |
| card | 17 | 16 | — | ~30 |
| motion | 3 | 3 | — | ~20 |
| badge | 2 | 2 | — | ~15 |
| bottom_nav | 9 | 7 | — | ~15 |
| mega_menu | 1 (`none`) | 1 | live `category_mega_menu.html` used by 2 headers + flat `category_link_row.html` | ~20 |

All registered components are renderer-integrated. Only header/footer/motion/palette/font/type_scale are selectable in the current UI. Mega Menu is under-registered, not under-built — a real design exists as a shared, live, tested partial and should be adapted into a selectable family. Header/Footer have ample designs (21/25 partials); the gap is selection UX, not designs.

---

## 15. Demo Store State

Complete: `rasti-mode-demo` seeds via real models and real services and renders through the public renderer; idempotent and slug-isolated. Content includes 1 store, 2 domains, ShopSettings + Vendor, 10 categories, 6 brands, 9 tags, 50 products, real variants, 3 images/product, 10 category covers, 6 collections, 4 hero slides, 6 banners, 10 stories, header/footer menus, and footer settings.

Missing for the complete-realistic-demo goal: blog/editorial content, and a festival/timed-offer representation with real active/expired states (blocked by the missing Commerce timed-offer model). Template Demo vs Template Preset separation is respected — applying a template never copies demo catalog into a merchant store.

---

## 16. Test / QA State

Strong evidence: ~2330 test functions in `apps/storefront_builder/tests/`; 315 targeted tests executed against an isolated test database passed (R4 mutation API, appearance mutations/validation/persistence/rendering/compatibility, A8 catalog/diversity/coverage/contracts/library, vertical slice including stale-409 and locked/removable rules, appearance overrides, responsive rendering, preset service, public homepage integration). Registry/schema/renderer-resolution tests are meaningful, not shallow. The section-level direct-edit wiring is tested (`tests/test_r4_inspector.py:199-200`; `tests/test_views.py:210`). A real R4 Playwright smoke exists (`tools/storefront_builder_r4_qa/run.mjs` via the `qa_storefront_builder_r4` command).

Weak or missing evidence: visual QA for only 8 of 50 templates, desktop-only, with no committed mobile screenshots; thin RTL/accessibility/mobile automation; a prior corrective report (`SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md`) states that runtime/interaction/visual verification was NOT EXECUTED in its sandbox; and no end-to-end evidence for the surfaces that do not exist (Content Hub, Design Lab).

---

## 17. Risks

**CRITICAL**

- Template switch destroys section-local merchant content/settings and section-scoped media by default (row 21); through the R4 path there is no automatic recovery checkpoint. This is a direct merchant-data-loss class.
- Direct Preview Editing depth is missing (rows 31/32/33); the primary UX is only partially built and the fuller version is on the to-be-retired legacy shell.

**HIGH**

- No Content Hub and no component-selection UI — the built engine is largely unreachable by merchants.
- Timed-offer truth located in Appearance (row 56).
- Visual QA for 42 of 50 templates and for mobile is absent.

**MEDIUM**

- Mega Menu / Header / Footer selection UX missing although designs exist (reuse risk if rebuilt instead of adapted).
- Inheritance is typography-only; no element layer or reset UX.
- Only 4 of 36 sections are R4-schema-enabled.
- Design Lab, Product Detail guided customization, and unified Media Picker are absent.
- Library breadth is below aspirational targets.

**LOW**

- 41 unused registry components (mostly safe-defaults).
- All-industries availability unverified (UNKNOWN).
- Blog/editorial demo content missing.

---

## 18. Recommended Implementation Order

No implementation is performed here; these are dependency-aware phases that build on, not rebuild, the existing foundation.

- **Phase 1 — Make template switch preserve merchant content and customization by default (CRITICAL).** Preserve section-local state (settings, manual selections and ordering, rich-text, appearance overrides), merchant-added/duplicated sections, and section-scoped media across a template switch; make re-application of template structure an explicit, confirmed action. Reuse the `template_baseline_snapshot`/reset machinery to invert the default, and ensure the R4 path also checkpoints. This removes a data-loss conflict before UX is layered on the composition model.
- **Phase 2 — Deepen Direct Preview Editing in R4 (CRITICAL).** Extend the existing `r4_editor.js`↔`preview.html` bridge with element/child edit identity, header/footer/logo/badge/entity click-to-edit, the ~65–70% contextual panel, and parent/child breadcrumb, all through `r4_mutation_service`. Reuse legacy patterns; do not reintroduce the legacy shell.
- **Phase 3 — Component-selection UI + register Mega Menu family.** Expose `appearance.component.update` / `appearance.manifest.apply` as galleries; adapt the existing `category_mega_menu.html` into a selectable `mega_menu` family with Header-capability compatibility.
- **Phase 4 — Inheritance and override completion + provenance UX.** Full Template→Global→Section→Element→Local chain, reset-to-parent/template, and "using global/template" / "make specific" messaging.
- **Phase 5 — Shell consolidation.** Reach R4 parity, flip the `r4_editor_enabled` default, and retire the legacy shell in a separate cleanup phase.
- **Phase 6 — Content Hub** over the existing content models.
- **Phase 7 — Commerce timed-offer model + campaign presentation** (move countdown truth to Commerce).
- **Phase 8 — Library breadth + template diversity/coverage** (Motion, Badge/Tag/Ribbon, fonts/compositions, use unused advertised components).
- **Phase 9 — QA at scale + Product Detail guided customization + Design Lab.**

---

## 19. Final Verdict

**A. How much of the Unified Architecture already exists?** The engineering layer is largely present and on-spec; the experience layer is partially present (section-level click-to-edit, a tabbed Inspector, and immediate autosaved preview exist; the deeper element/parent-child/~65–70% experience, component-selection UI, Content Hub, and Design Lab do not). The authoritative view is the matrix: COMPLETE 28, PARTIAL 25, MISSING 5, LEGACY_CONFLICT 2, UNKNOWN 1, NOT_APPLICABLE 0 (61 rows).

**B. What are the largest missing or incorrect pieces?** (1) Template switch must stop destroying merchant content and customization by default (rows 20/21); (2) deeper Direct Preview Editing (element/parent-child + ~65–70% panel + global-region click-to-edit); (3) component-selection UI plus registering the existing Mega Menu design as a family; (4) Content Hub; (5) full inheritance/override + provenance UX; (6) Commerce timed-offer truth; (7) Design Lab; (8) visual QA for 42 of 50 templates and mobile.

**C. Evolve or replace?** Evolve. No backend subsystem needs replacement. The engine, the preview bridge, and the header/footer/mega-menu designs already exist and should be extended or adapted. The only replacement is retiring the legacy shell after R4 reaches parity. The conflicts (template-switch preservation, dual shells, timed-offer ownership) are corrections, not rewrites.

**D. First implementation phase after this audit?** Phase 1 — correct template-switch preservation so switching a Ready Template preserves merchant content and customization by default and makes re-applying template structure an explicit action, including a checkpoint on the R4 path. It is a confirmed merchant-data-loss issue and a prerequisite for building richer editing UX on the composition model. Phase 2, deepening Direct Preview Editing on the existing bridge, follows immediately.

---

## Audit Review Corrections

These are the final accepted corrections applied during review, retained for historical clarity:

1. **Template switch preservation.** Preservation was refined into two capabilities. Independent domain records (products, product images, categories, brands, collections, store-global media) are preserved (row 20, COMPLETE). Section-local merchant state is not: `_build_sections_for_page` (`preset_service.py:258-271`) rebuilds each section's `settings` from the preset entry or `default_settings()` and never merges the previous `StorefrontSection.settings`; `page.sections.all().delete()` runs for covered pages (Home always); section-scoped `HeroSlide`/`PromotionalBanner`/`StoryRailItem` are CASCADE-deleted (`content/models.py:414`); and the R4 `appearance.template.apply` path calls raw `apply_preset` with no checkpoint (`r4_mutation_service.py:411`). This is classified LEGACY_CONFLICT (row 21) and is the first implementation priority.
2. **Direct Preview Editing** is PARTIAL, not missing (row 31). Section-level click-to-edit already works via the `r4_editor.js`↔`preview.html` message bridge; element/child and global-region editing and the ~65–70% contextual experience remain missing.
3. **Mega Menu** is PARTIAL and reusable (row 25). A live, tested `category_mega_menu.html` exists and is used by header variants; it should be adapted into a registered selectable family, not rebuilt. The same reuse-first principle applies to Header and Footer designs.
4. **Live Preview** was separated into (A) preview-updates-after-every-change, which is COMPLETE via immediate iframe reload with autosave and no Apply button (row 4), and (B) Direct Preview Editing, which is the separate PARTIAL capability above.
5. Content Hub, Product Detail guided customization, Design Lab, and provenance UX remain classified exactly as in the matrix (MISSING rows 40, 48, 51, 35).
