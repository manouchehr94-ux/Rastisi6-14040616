# Task 4 — Collection characterization and canonical adapter convergence (V03)

- Starting HEAD: `4b0e092c7dc779d55e9cd41179469e449d0566c7`
- Branch: `feature/storefront-vertical-slice-phase3`

## Production files changed
- `apps/storefront_builder/resource_source.py` — added `collection_resource_source_from_settings` / `collection_resource_source_to_legacy_patch` (mirror of brand adapter: manual→`{collection_ids:[...]}`, auto all_active→`{collection_ids:[]}`); registered `"collection_tiles"` (kind=collection) in `_SECTION_ADAPTERS`. Legacy patch emits only `collection_ids`, never a `source` key.
- `apps/storefront_builder/section_registry.py` — `COLLECTION_TILES_SCHEMA` (title[text], source[resource_source, default collection/auto/all_active], tile_style[choice grid/carousel]); `settings_schema=COLLECTION_TILES_SCHEMA` on the definition; `"collection_tiles"` added to `_RESOURCE_SOURCE_AWARE_SECTION_KEYS`; `"collection_tiles": CollectionTilesSettingsError` in the `_with_resource_source` error-class dict.
- `apps/storefront_builder/services/r4_mutation_service.py` — collection manual-ownership branch in `_validate_resource_source_ownership` (`MerchantCollection.objects.filter(store,pk__in).count()` vs `len(set(manual_ids))` → `R4MutationError("invalid_resource_ownership")`; all_active auto = no-op). SHIPPED ATOMICALLY with the schema exposure.
- `apps/storefront_builder/r4_views.py` — `"collection"` in `_PICKER_UI_KINDS`; `_search_collections` (store-scoped, is_active, name__icontains, ordered by name, cap 20); registered in `_RESOURCE_SEARCHERS`; EXPLICIT `kind=="collection"` branch in `_serialize_picker_item` (label=name, sublabel=slug) BEFORE the brand name_en fall-through; explicit collection branch in `_resolve_selected_items` (all_active + same-store + fail-closed); `_PICKER_COLLECTION_AUTO_RULES` + `_PICKER_AUTO_RULES_BY_KIND` map.

## NOT changed (verified unnecessary)
- render_service.py `_collection_tiles_context` (count semantics `Count("items")` = total membership + manual/auto newest-first ordering PRESERVED), settings_schema.py, views.py legacy (already builds {title,collection_ids,tile_style}; `_validate_universal_selection_ownership` already maps collection_tiles→(MerchantCollection,"collection_ids")), resource_picker.html (generic), r4_editor.js (derives kind from typed source). No migration.

## RED → GREEN (controller-run, authoritative)
- Adapter: `resource_source_from_section_settings('collection_tiles', ...)` raised `unsupported section_key` → after (a), roundtrip `{'collection_ids':[7,3]}` GREEN.
- R4 mutation: valid own-collection `source` POST returned `section_not_schema_enabled` (400) → after (b)+(c), 200 with legacy-shaped `collection_ids` and revision+1.
- Inspector: `collection_tiles` inspector 404 → after (b), 200 (picker-open control present).
- Ownership rejection: foreign/missing collection id via `source` patch → 400 `invalid_resource_ownership`; asserted settings/edit_revision/history count all UNCHANGED (reject runs after schema cleaning, before section.save).

## Semantics preserved
- Count: `item_count` = total `Count("items")` membership; with one active + one inactive member, tile item_count=2 vs visible domain list=1. Manual order preserved & ≠ name-index order; auto newest-first (`-created_at`) ≠ name order.
- Collection dispatched EXPLICITLY in picker serialize/resolve (never hits brand name_en fall-through). Brand tests still pass (no unguarded kind fallthrough).

## Commands + results (controller-run --keepdb)
- `test_r4_resource_source test_r4_resource_picker test_r4_settings_schema test_r4_mutation_api test_render_service catalog.test_collection_service catalog.test_collection_integration`: **Ran 358, OK (skipped=1 pre-existing)**.
- makemigrations --check --dry-run: No changes detected. git diff --check: clean.

## Scope audit
Only the 4 allowed production files + 4 test files. No catalog models/services business change, no new persisted source field, no migration, count meaning unchanged. Confirmed via git.

## Review
Independent semantic_reviewer verdict recorded in ledger.

## Readiness for Task 5
Collection typed mutation gate GREEN; Brand gate unchanged. READY for Collection end-to-end + page integration.
