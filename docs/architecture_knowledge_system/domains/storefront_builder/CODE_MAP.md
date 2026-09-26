# storefront_builder — Code Map

```
domain_id: D9
code_baseline: 5883a140
```

```
apps/storefront_builder/
├── models.py                     7 models (Layout, LayoutVersion, Page, Section, Container, Cell, EditHistoryEntry)
│                                 · r4_editor_enabled ~:211 (default True)
├── views.py                      R3 LEGACY editor; _require_legacy_editor_active ~:65 (Http404 when R4)
├── r4_views.py                   R4 CURRENT editor (shell, /mutate/, /publish/, ...)
├── media_views.py                placement media add/edit/delete (writes content models)
│                                 (NO urls.py — routes live in apps/dashboard/urls.py)
├── section_registry.py           single authoritative section allowlist
├── appearance_registry.py        appearance templates + palettes         ┐
├── palette_pack_64.py            more curated palettes                    │ M1 duplication
├── theme_catalog.py              occasion themes                          │
├── global_region_registry.py     header/footer/mobile chrome variants     ┘ (footer also M2)
├── layout_preset_registry.py     V2 layout presets (replaces deleted preset_registry)
├── a8_ready_templates.py         50 A8 Ready Templates (preset compositions)
├── variant_contract.py           per-section variant contract
├── settings_schema.py            declarative field-type contract (Strangler — M10)
├── resource_source.py            section data-source contract
├── storefront_appearance/        typed Design Engine (contracts, families, adapters, registry,
│                                 persistence[mirror -> header/footer_config], rendering, validation,
│                                 compatibility, inventory)
├── services/                     17 files: layout_service, r4_mutation_service, preset_service,
│                                 appearance_authority_service, render_service, container_service,
│                                 section_structure_service, section_data_service, bootstrap_service,
│                                 edit_history_service, design_lab_service, golden_reference_service,
│                                 template_preview_service, page_resolution_service, row_service, ...
├── management/commands/          capture_ready_template_previews, qa_storefront_builder(_r4)
├── migrations/
└── tests/                        ~61k LOC (test_r4_*, test_render_service, test_storefront_page, ...)

# DELETED (confirmed absent — D5): family_registry.py, preset_registry.py
```

## Where to look
| Concern | File |
|---|---|
| Which editor is current | `models.py` (r4_editor_enabled) + `views.py::_require_legacy_editor_active` |
| R4 mutation | `services/r4_mutation_service.py` |
| Publish/draft/restore | `services/layout_service.py` |
| Appearance (typed) | `storefront_appearance/persistence.py` |
| Section allowlist | `section_registry.py` |
| Ready Templates / presets | `a8_ready_templates.py`, `layout_preset_registry.py`, `services/preset_service.py` |
| Render | `services/render_service.py` |
