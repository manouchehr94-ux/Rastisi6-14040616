# P5-W5 Discovery — Authority Map & Duplication Audit

Status: DISCOVERY ONLY — no production code changed.
Source commit: `81abb435c6421197117f8f570993b64ca485d4af` (official W4C merge checkpoint, `feature/phase5-design-expansion`).
Method: direct source reading/grep against the checkpoint (no reliance on the stale Graphify graph — see note in the main discovery plan).

This document answers RastiSi's central architectural risk for W5: **is there exactly one canonical owner per concept, or has duplication crept in?**

---

## 1. Authority map (concept → canonical file/function → consumers)

| # | Concept | Canonical file/function | Consumers |
|---|---|---|---|
| 1 | Ready Template registry (50 templates) | `apps/storefront_builder/layout_preset_registry.py` (`LAYOUT_PRESET_REGISTRY`, `register_layout_preset()` L190, `list_ready_templates()` L221 — filters `is_ready_template=True`). Populated from `apps/storefront_builder/a8_ready_templates.py::_SPECS` (50 `_RecipeSpec` rows). | `views.py::storefront_template_gallery`/`storefront_apply_layout_preset`, `r4_views.py::storefront_r4_switch_template`, `preset_service.py`, `template_preview_service.py` |
| 2 | Ready Template version history | Same module: `LAYOUT_PRESET_VERSION_REGISTRY` (L157), `get_layout_preset_version()` (L212). Old rows preserved verbatim in `a8_ready_templates.py::_HISTORICAL_SPECS`. | `StorefrontLayoutVersion.template_provenance`/`template_baseline_snapshot` (models.py L286-316) |
| 3 | Component registries (per-family) | Typed facade: `apps/storefront_builder/storefront_appearance/registry.py` (`COMPONENT_REGISTRY`, `get_component()`, `require_component()`) + `families.py` (`COMPONENT_FAMILIES`, 11 families). Wraps 4 raw registries: `section_registry.py`, `global_region_registry.py`, `theme_catalog.py`, `variant_contract.py` — each owns a non-overlapping slice; import-time duplicate-key validation in `contracts.py::validate_family_catalog/validate_component_catalog` and `registry.py::validate_deprecation_chains`. | `r4_mutation_service.py`, `preset_service.py`, `design_lab_service.py`, `r4_views.py` |
| 4 | Store Appearance typed state | `storefront_appearance/contracts.py::StoreAppearanceManifest` (frozen dataclass). Persisted via `storefront_appearance/persistence.py::persist_store_appearance_manifest()` **inside** `StorefrontLayoutVersion.appearance_config[STORE_APPEARANCE_CONFIG_KEY]` — not a second table. | `load_store_appearance_manifest()`, `rendering.py` |
| 5 | Draft | `apps/storefront_builder/models.py::StorefrontLayoutVersion` (`status=DRAFT`), anchored by `StorefrontLayout.draft_version`. Accessor: `services/layout_service.py::get_or_create_draft()`. | Every mutating view/service |
| 6 | Published | Same model, `status=PUBLISHED`, anchored by `StorefrontLayout.published_version`. Immutable once published; publish is an atomic pointer-swap. | `storefront_context_service.py`, public views |
| 7 | Preset Apply (Ready Template → Draft) | `services/preset_service.py::apply_preset()` (L436) — sole low-level write authority. | Legacy `views.py` (`apply_preset_with_checkpoint`), R4 dispatcher (`r4_mutation_service.py::_apply_appearance_template`), Design Lab (`resolve_preset_candidate`) |
| 8 | Individual component mutation | R4 dispatch table: `r4_mutation_service.py::_dispatch_mutation()` (L1053). Shared appearance/header/footer write authority: `services/appearance_authority_service.py` ("the ONE place... instead of independently reconstructing overlapping state"). | Both R4 and legacy R3 views call into `appearance_authority_service` — see Duplicate Finding A |
| 9 | Mutation dispatcher (stale-write boundary) | `r4_mutation_service.py::apply_mutation()` (L1165) — locks Draft, checks `base_revision`, dispatches, records one atomic `edit_revision` bump + history entry. Module docstring: "R3 never calls this module." | R4 editor, Design Lab apply |
| 10 | History | Two intentionally distinct concepts: (a) bounded Undo/Redo interaction stack — `StorefrontEditHistoryEntry` + `edit_history_service.py` (explicitly separate from release history per its own docstring); (b) permanent release history — `StorefrontLayoutVersion` rows with `status=ARCHIVED`. | `views.py::storefront_restore` |
| 11-12 | Undo / Redo | `edit_history_service.py::undo()`/`redo()`. Single shared execution contract: `r4_mutation_service.py::_run_history_command()` — "the ONE Undo/Redo execution contract, shared by every entry point." Legacy `views.py::storefront_undo/storefront_redo` were refactored to delegate to this **same** contract. | R4 + legacy, confirmed converged (not duplicated) |
| 13 | Preview renderer (Draft) | `views.py::storefront_preview` → `render_service.py::build_page_render_items()`/`_build_items_from_sections()`. R4 editor and Design Lab reuse this exact route via iframe + opaque token — no separate renderer. | R4 editor, Design Lab, non-destructive template preview |
| 14 | Public renderer | `services/storefront_context_service.py::build_universal_storefront_context()` — built explicitly to stop a **past** duplicate ("before this phase only `catalog.views.home()` had this logic"). Internally uses the same `render_service.py` primitives as Preview. | `apps/catalog`, `apps/customers`, `apps/content`, `apps/cart`, `apps/dashboard`, `apps/core/context_processors.py` (6 call sites) |
| 15 | Theme (occasion overlay) | `apps/storefront_builder/theme_catalog.py` — docstring: "the SINGLE canonical data authority for the reversible occasion Theme layer... ONE CONCEPT = ONE CANONICAL OWNER." Registered as the `theme` component family. | `storefront_appearance/adapters.py`, `rendering.py::theme_overlay_state`, `design_lab_service.py` (excludes `theme` from randomizable set) |
| 16-17 | Tenant / Store resolution | `apps/stores/resolution.py` — docstring: "the ONLY place in the codebase that decides 'which Store does this HTTP request belong to.'" Key entry points: `resolve_store_for_request()` (middleware), `resolve_store_for_service()` (standard service calls), `resolve_store_for_storefront()` (public, 404/403 on failure), `resolve_store_for_admin_host()` (deliberately separate admin-subdomain resolver). | `apps/stores/middleware.py::StoreResolutionMiddleware`, all storefront_builder views/services |
| 18 | Static Ready Template previews | `apps/storefront_builder/static/ready_template_previews/<key>/v<version>.webp` (+ `.meta.json`). Service: `services/template_preview_service.py::resolve_real_screenshot()`/`build_template_thumbnail_svg()` (SVG fallback). Sole writer: management command `capture_ready_template_previews.py`. Sole reader: Gallery view. | `views.py::storefront_template_gallery` |

---

## 2. Duplicate / parallel authorities found

**Total: 2 findings, both flagged as W5 architectural prerequisites for a Product Owner decision — neither is silent/accidental duplication, both are documented, intentional states, but both need an explicit W5 disposition.**

### W5 ARCHITECTURAL PREREQUISITE — DUPLICATE FOUND #1: Editor/Mutation entry-point surface (R3 vs R4)

- **A**: `apps/storefront_builder/views.py` ("R3", legacy) — routes under `storefront-builder/...`
- **B**: `apps/storefront_builder/r4_views.py` + `services/r4_mutation_service.py` ("R4", current default) — routes under `storefront-builder/r4/...`
- Both are **live and simultaneously wired** into `apps/dashboard/urls.py` (R3 at L219, L275-329; R4 at L220-274).
- Gated per-Store by `StorefrontLayout.r4_editor_enabled` (models.py L211-220, **default `True`**), whose own help_text says: "R4 is now the default canonical merchant editor... this flag exists only so an individual Store can be pinned back to the legacy editor if a regression is found, never to gate normal access."
- When the flag is `True` (default), the legacy `editor.html` collapses to a "go to R4" redirect card for most features, **except** two capabilities with no R4 equivalent that remain reachable: (a) restore/history browser, (b) internal industry-vertical layout preset installer. Both are explicitly marked "CANONICAL KEEP" in `docs/qa_evidence/storefront_appearance_convergence/phase4/legacy_disposition.md`, not competing editors.
- Underlying low-level services (container_service, row_service, section_data_service, appearance_authority_service, layout_service, edit_history_service, preset_service) **are shared** — business logic itself is not duplicated.
- **What is duplicated**: the transaction/safety boundary. R4 mutations go through the single optimistic-concurrency dispatcher (`base_revision` stale-write check, atomic `edit_revision` bump). R3's per-action views write directly to the Draft (`draft.save()`) with **no base_revision/stale-write protection**, and remain server-side reachable via direct POST regardless of the UI flag (only the UI is gated for most legacy endpoints, not the endpoint itself).
- **Verdict**: a live, intentionally-flagged, well-documented rollback mechanism — not accidental dead code. But two structurally different mutation-safety guarantees coexist against the same Draft depending on a per-Store flag. **W5 should make an explicit decision**: formally retire the R3 write surface (keep only the two CANONICAL KEEP legacy-only capabilities, ported into R4 or left as documented exceptions), or keep it permanently as a safety valve with its gap acknowledged.

### W5 ARCHITECTURAL PREREQUISITE — DUPLICATE FOUND #2: Two independently-selectable "Template" concepts

- **A**: `apps/storefront_builder/appearance_registry.py::TEMPLATE_REGISTRY` — 10 pure style-token bundles (modern/marketplace/minimal/boutique/luxury/tech/editorial/compact/playful/glass — font, radius, density, motion, card_shadow, hero_style, etc.), selected via `appearance_config["template_slug"]`.
- **B**: `layout_preset_registry.py` + `a8_ready_templates.py` — the 50 Ready Templates (the subject of this entire W5 discovery).
- Both are actively wired into the **same** R4 Inspector payload and the **same** `appearance.update` mutation (`r4_mutation_service.py` L845-848, L887-888, comment: "exact R3 precedence") — not a legacy leftover.
- Several fields a Ready Template's recipe sets (font/density/width/radius, via `_RecipeSpec`) are the **same fields** the 10-item `TEMPLATE_REGISTRY` can independently override afterward via `template_slug` — with no coupling or warning between the two pickers.
- This is architecturally coherent (disjoint `appearance_config` sub-keys, neither corrupts the other), but the **shared name "Template" for two unrelated, overlapping-scope registries is a real merchant- and PO-facing confusion risk**.
- **Recommendation for W5**: rename one concept (e.g. the 10-item `appearance_registry` set → "Style Pack") to remove the naming collision before exposing both more prominently in a merchant-facing IA.

---

## 3. Explicitly ruled out (checked, not found)

- **Legacy `family_registry.py` / `preset_registry.py`**: confirmed deleted — importing either raises `ModuleNotFoundError`, proven by a dedicated regression test (`test_phase7_family_retirement.py::RegistryModulesAreGoneTests`). Not a live duplicate.
- **Second Draft-shaped state**: grepped `apps/stores/models.py`, `apps/dashboard/models.py`, `apps/core/models.py` for any second `draft_config`/`appearance_json`/`builder_state`-style field — none found.
- **Second Preset-Apply implementation**: `preset_service.apply_preset()` is reached identically by R3, R4, and Design Lab; none reimplements it.
- **Second Undo/Redo stack**: legacy explicitly delegates to the same `_run_history_command` contract R4 uses — a **resolved** past risk, not a current duplicate.
- **Second public/preview renderer**: `build_universal_storefront_context()` was built specifically to remove a prior duplicate (was only in `catalog.views.home()`); now the single shared entry point across 6 views, itself delegating to the same `render_service.py` primitives Preview uses.
- **Second tenant/Store resolver**: single authority in `apps/stores/resolution.py`; the admin-subdomain resolver is a deliberately separate, non-overlapping concern (different host shape), not a duplicate.
- **"Theme" naming collision**: `apps/core/theme_presets.py` (`ThemePreset`, 6 flat color-scheme presets — a legacy `ShopSettings` color picker) shares the word "Theme" with `theme_catalog.py` (the occasion-overlay system) but has **zero code coupling** to it — confirmed a naming collision only, not an architectural duplicate. Worth a note, not a W5 action item.
- **Design Lab having its own parallel state model**: `design_lab_service.py` explicitly documents it owns "exactly one new concept: the transient candidate. No model, no migration, no registered preset, no DB row, no localStorage authority" — confirmed by grep; reuses the canonical preset resolver, write authority, mutation dispatcher, preview route, and component registry verbatim.

---

## 4. Key files for W5 planning attention

- `apps/dashboard/urls.py` (L219-329) — the dual-routing evidence for Finding #1
- `apps/storefront_builder/models.py` (L211-220) — the `r4_editor_enabled` flag
- `apps/storefront_builder/templates/dashboard/storefront_builder/editor.html` (L1-39) — conditional legacy-shell logic
- `apps/storefront_builder/services/r4_mutation_service.py` — the dispatcher and its "R3 never calls this module" boundary
- `apps/storefront_builder/appearance_registry.py` vs `layout_preset_registry.py` — the two "Template" registries for Finding #2
