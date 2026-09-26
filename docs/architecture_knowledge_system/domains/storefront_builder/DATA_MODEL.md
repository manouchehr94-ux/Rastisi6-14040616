# storefront_builder — Data Model

```
domain_id: D9
code_baseline: 5883a140
source: apps/storefront_builder/models.py (7 models)
known_risks: M12
```

| Model | Key fields / lifecycle | Notes |
|---|---|---|
| **StorefrontLayout** | OneToOne Store; `uses_visual_storefront_layout`; **`r4_editor_enabled` (default True)**; `published_version`/`draft_version` (FK→Version, SET_NULL) | publish = pointer swap; `r4_editor_enabled` gates the active editor generation (see GENERATIONS) |
| **StorefrontLayoutVersion** | `status` (draft/published/archived); `source` (manual/legacy_bootstrap/industry_template/restored); `header_config`/`footer_config`/`appearance_config` (JSON); `content_fingerprint`; `template_provenance`; `template_baseline_snapshot`; `edit_revision` (optimistic token) | immutable-after-publish snapshot of header/footer/appearance + all 6 pages |
| **StorefrontPage** | `page_type` (home/product_detail/listing/collection/search/cart); `page_appearance_overrides` | 6 typed slots; `ensure_version_pages` idempotent. **Distinct from `content.ContentPage` (M3)** |
| **StorefrontSection** | `section_key` (validated vs SECTION_REGISTRY in service); `order`; `is_active`; `settings` (JSON); `stable_id`; legacy `row_key/row_span`; `cell` FK + `cell_order` | DB owner is `page`; a `version=` init-shim resolves to home |
| **StorefrontContainer** | per-page layout container (1–4 cells); `layout_key`; `stable_id` | the newer layout mechanism |
| **StorefrontCell** | slot in a container; `span` (1–12 CheckConstraint); **`section` OneToOne (SET_NULL)** | **M12:** `StorefrontCell.section` (OneToOne, "executing truth today") vs `StorefrontSection.cell` (FK, "parallel/future") vs legacy `row_key/row_span` — three coexisting placement mechanisms |
| **StorefrontEditHistoryEntry** | `sequence`, `is_undone`, before/after JSON | draft-only undo/redo; wiped at publish |

## Config sources (NOT DB models — Python registries; see GENERATIONS M1)
`section_registry.py` (section allowlist — single authoritative), `appearance_registry.py`
(templates + palettes), `palette_pack_64.py` (more palettes), `theme_catalog.py` (occasion themes),
`layout_preset_registry.py` (V2 presets), `a8_ready_templates.py` (50 Ready Templates),
`global_region_registry.py` (header/footer/mobile chrome variants), `variant_contract.py`,
`settings_schema.py` (declarative field-type contract — Strangler), `resource_source.py`
(section data-source contract). Plus the `storefront_appearance/` typed Design-Engine package
(contracts/families/adapters/registry/persistence/rendering/validation/compatibility/inventory).

## Draft/publish pattern (VERIFIED)
One snapshot cycle for the WHOLE storefront (header+footer+appearance+all 6 pages); publish is a
pointer swap; restore always creates a NEW draft (never publishes directly). Modeled on the
catalog IndustryTemplate/StoreTemplateUpdate rollback pattern.
