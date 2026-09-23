# storefront_builder — Services

```
domain_id: D9
code_baseline: 5883a140
source: apps/storefront_builder/services/ (17 files) + storefront_appearance/ package
```

| Service | Generation | Responsibility | Txn / concurrency |
|---|---|---|---|
| **r4_mutation_service** | R4 (current) | THE single optimistic mutation boundary for the R4 editor: lock StorefrontLayout, resolve active draft, compare `base_revision` (optimistic), dispatch one allowlisted mutation, bump `edit_revision`, record edit history | one `@atomic` per mutation |
| **layout_service** | shared | Canonical draft/publish/restore + header/footer/appearance validators: `get_or_create_draft`, `discard_draft`, **`publish`** (pointer swap, archive previous, fingerprint, `uses_visual_storefront_layout=True`), `restore_version` (always new draft), `_clone_version_content` (+ section-scoped media clone into content models) | `@atomic`; rate-limited |
| **preset_service** | A8/preset | Apply `LayoutPresetDefinition` / A8 Ready Template to a Draft; `reset_section_to_baseline`; granular resets | `@atomic`, validate-before-write; only touches named pages; never writes colors unless no palette chosen |
| **appearance_authority_service** | R4 | Preservation-aware typed/legacy appearance transformation on a Draft; delegates persistence to `storefront_appearance.persistence.persist_store_appearance_manifest` | draft-only (raises `ImmutableStoreAppearanceError` if not draft) |
| **render_service** | shared | Read/render path: `build_render_items(version, store)` → `build_page_render_items(home_page)`; container/appearance render-state resolvers | read-only |
| **container_service** | R4 | container/cell CRUD; `ensure_version_containers`; `clone_page_containers` | `@atomic` |
| **section_structure_service / section_data_service / section_appearance_service / row_service** | mixed | section structure, data-source resolution (+Store-ownership checks), section appearance, legacy 12-col rows | mixed |
| **bootstrap_service** | shared | seed first Draft from legacy home | `@atomic` |
| **edit_history_service** | R4 | Undo/Redo snapshots | draft-only |
| **design_lab_service / golden_reference_service / template_preview_service / page_resolution_service / storefront_context_service** | mixed | design lab, golden reference, previews, page resolution, shared shell context | mixed |

## `storefront_appearance/` typed Design Engine (the R4 appearance layer — M1)
`contracts.py` (typed ComponentDefinition/StoreAppearanceManifest), `families.py`
(`COMPONENT_FAMILIES`), `adapters.py` (builds components FROM the older registries — theme_catalog,
global_region, appearance motion), `registry.py` (`COMPONENT_REGISTRY` assembled at import),
`persistence.py` (`persist_store_appearance_manifest`: writes the typed manifest into
`appearance_config["store_appearance"]` AND **mirrors** selectors back into
`header_config["header_variant"]`, `footer_config["footer_variant"]`/`mobile_nav_variant`,
`appearance_config["motion"]` — the M1 duplication), `validation.py`, `rendering.py`,
`compatibility.py`, `inventory.py`. **This is a typed abstraction that reads the older registries,
not a replacement of them.**

## Canonical mutation authorities
- StorefrontLayoutVersion/sections: `r4_mutation_service` (R4), `layout_service`,
  `container_service`, `preset_service`.
- appearance_config: `appearance_authority_service` / `storefront_appearance.persistence`.
- Legacy `views.py` mutations are fail-closed when R4 is active (GENERATIONS).
