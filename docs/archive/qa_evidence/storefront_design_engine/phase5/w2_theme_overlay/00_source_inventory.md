# P5-W2 Source Inventory — Reversible Theme Overlay

Certified base SHA: `b7d8ac281389870877553f5a308af3e77dcdd7f0`
Implementation branch: `feature/phase5-w2-theme-overlay`
Inspected at HEAD == certified base.

## Canonical Store-Appearance architecture (confirmed)

### `storefront_appearance/contracts.py`
- `ComponentFamilyDefinition` frozen dataclass with fields: `key`, `label_fa`,
  `storage_adapter_key`, `safe_default_component_key`, `renderer_role`,
  `optional`, `capabilities`.
- `_RENDERER_ROLES = {"global_region", "section_variant", "composition", "appearance_token"}`.
  **`appearance_token` already exists** — Theme uses it; `_RENDERER_ROLES` is NOT expanded.
- Optional families require an explicit `off/none/hidden` marker in the safe default
  identity segments (`_OPTIONAL_DEFAULT_MARKERS`). `theme.none.v1` satisfies this.
- `StoreAppearanceManifest(schema_version, selections, settings)` — settings is a frozen
  bounded mapping. Theme intensity lives under `settings["theme"]`.
- `validate_manifest_families(..., require_complete=)` — a complete manifest requires every
  known family, which is exactly why all 50 Ready Templates must carry a `theme` selection.

### `storefront_appearance/families.py`
- `_FAMILY_DEFINITIONS` tuple → `COMPONENT_FAMILIES` dict and
  `DEFAULT_STORE_APPEARANCE_MANIFEST` (safe default per family).
- Existing `motion` family already uses `renderer_role="appearance_token"` — Theme mirrors it.
- **Add point:** append the `theme` optional appearance_token family here. DEFAULT manifest
  then automatically includes `theme -> theme.none.v1`.

### `storefront_appearance/adapters.py`
- `build_existing_component_definitions()` emits every ComponentDefinition from existing
  registries. `resolve_registry_reference(reference)` resolves a symbolic reference to an
  implementation, failing closed (`InvalidStoreAppearanceContract`) on unknown.
- **Add point:** emit Theme ComponentDefinitions from `theme_catalog`, with
  `registry_reference="theme_overlay:<occasion-key>"`; add a `theme_overlay:` branch to
  `resolve_registry_reference()` reading the catalog (unknown key → fail closed).

### `storefront_appearance/registry.py`
- At import: `build_existing_component_definitions()` → `validate_component_catalog` →
  per definition `validate_compatibility_metadata` + `resolve_component_implementation`
  (so every Theme definition MUST resolve through the adapter at import time) →
  `COMPONENT_REGISTRY`. **No manual Theme population here** — canonical path preserved.

### `storefront_appearance/validation.py`
- `ALLOWED_SETTINGS_BY_FAMILY = {family: frozenset() for family in COMPONENT_FAMILIES}`
  (closed empty by default). `_validate_typed_settings` rejects unknown per-family setting keys.
- **Add point:** set `ALLOWED_SETTINGS_BY_FAMILY["theme"] = frozenset({"intensity"})` and add
  a typed intensity-enum check (`subtle`/`balanced`/`strong`).
- `normalize_persisted_manifest(raw)` merges over `DEFAULT_STORE_APPEARANCE_MANIFEST` with
  `require_complete=False` → **old persisted manifests missing `theme` receive `theme.none.v1`
  automatically. Zero migration.**

### `storefront_appearance/rendering.py`
- `resolve_store_appearance_manifest_state(manifest, version_id)` — the single resolver,
  used by both the persisted-version path and the preset candidate-preview path.
- Accessor patterns: `card_settings_for`, `badge_settings_for`, `global_renderer_template`,
  `section_variant_for`. **Add point:** `theme_overlay_state(state)` accessor.

### `storefront_appearance/persistence.py`
- `persist_store_appearance_manifest` stores the full primitive manifest (selections+settings)
  under `appearance_config["store_appearance"]`; Theme settings persist there automatically.
- `_legacy_manifest` builds from `DEFAULT_STORE_APPEARANCE_MANIFEST.selections` → legacy
  versions resolve `theme -> theme.none.v1` with no migration.

### `services/appearance_authority_service.py`
- Canonical preservation-aware family mutations: `apply_header_variant`, `apply_footer_variant`
  use `_manifest_with_family` (replaces exactly one family selection, preserves the rest) and
  `persist_store_appearance_manifest`. **Add point:** `apply_theme(version, occasion_component_key,
  intensity)` and `clear_theme(version)` following the same pattern (selection + `settings["theme"]`).

### `services/r4_mutation_service.py`
- Single optimistic mutation boundary: `apply_mutation(store, actor, base_revision, mutation)` —
  locks active Draft (`_lock_active_draft` → `select_for_update`, compares `edit_revision`,
  `R4StaleRevision`), snapshots history, dispatches ONE allowlisted mutation type via
  `_dispatch_mutation`, records change/increments revision through `edit_history_service.record_change`.
- Existing `appearance.component.update` already sets any family selection (incl. `theme.*`),
  but cannot express intensity or a Clear. **Add point:** two new allowlisted mutation types
  `theme.apply` (selection + intensity) and `theme.clear`, delegating to the authority service.
  Tenant isolation, stale-write, history/undo-redo all reused unchanged.

### `a8_ready_templates.py::_manifest(spec)`
- Builds `selections` for all 50 Ready Templates (no `settings`). **Add point:** add
  `"theme": "theme.none.v1"` to selections so every Ready Template stays complete/valid.

### Rendering to shell (Preview/Public parity)
- `services/storefront_context_service.build_universal_storefront_context` is the ONE public
  + preview context builder; sets `request.storefront_appearance_version`.
- `apps/core/context_processors.py::shop_settings` reads `_global_identity_version(request, store_id)`
  (published version for public, `request.storefront_appearance_version` for preview) and emits
  the `SHOP_*` variables consumed by `templates/base.html`'s `<html>` tag.
  **This is the single parity point** — emitting `SHOP_OCCASION_*` here drives identical Theme
  for Preview and Public by construction.
- `templates/base.html` `<html>` carries `data-sfb-*` attributes and brand CSS vars. Existing
  `--theme-*` vars are palette theme-role vars (collision risk). **Occasion Theme uses a distinct
  namespace: `data-occasion-theme` / `data-occasion-tone` / `data-occasion-intensity` and
  `--occasion-accent` / `--occasion-accent-soft` / `--occasion-motif-opacity`** to remain orthogonal.

### R4 merchant controls
- `r4_views.py::_build_global_design_context(draft)` builds the "طراحی کلی" panel projection.
- `templates/.../r4/editor.html` `#r4GlobalDesign` panel; `data-r4-global-mutation` groups +
  `data-r4-global-field` scalar fields; JS `r4_editor.js` delegates change→enqueueMutation→
  `refreshGlobalDesignAndPreview()`. Template switch/reset use dedicated buttons.
  **Add point:** a Theme section with dedicated `data-r4-theme-*` markers + JS enqueuing
  `theme.apply`/`theme.clear` (needs a dedicated branch because it carries selection+intensity+clear).

## Reversibility (critical)
- Theme owns ONLY `selections["theme"]` and `settings["theme"]`. `clear_theme` resets selection to
  `theme.none.v1` and drops `settings["theme"]`, touching nothing else. `_manifest_with_family`
  preserves all other selections/settings byte-for-byte. **No `template_baseline_snapshot` involvement.**

## No contradiction found
The prompt's expectations match the actual architecture. Proceeding with TDD implementation.
