# storefront_builder — Change Guide

```
domain_id: D9
code_baseline: 5883a140
open_decisions: DR-6
known_risks: H3, M1, M2, M10, M11, M12
```

> **Before any storefront change:** read [GENERATIONS](GENERATIONS.md). Know that **R4 is current**,
> **R3 is fail-closed legacy**, and **A8/presets are the template layer**. Do not add mutation to
> the R3 `views.py` path — it is fail-closed when `r4_editor_enabled=True` (the default).

## Recipe: Modify storefront appearance
- **READ FIRST:** [GENERATIONS](GENERATIONS.md) (M1!), [SERVICES](SERVICES.md) (storefront_appearance).
- **CANONICAL OWNER:** `appearance_authority_service` / `storefront_appearance.persistence`.
- **⚠️ M1:** appearance/palette/theme live across `appearance_registry.py`, `palette_pack_64.py`,
  `theme_catalog.py`, the typed `COMPONENT_REGISTRY`, AND persisted `appearance_config` mirrored into
  `header_config`/`footer_config`. Persist ONLY via `persist_store_appearance_manifest` to keep them synced.
- **INVARIANTS:** draft-only (ImmutableStoreAppearanceError otherwise); keep manifest↔header/footer mirror in sync.
- **TESTS:** `test_r4_store_appearance_registry.py`, `test_render_service.py`.

## Recipe: Add / change a section type
- **READ FIRST:** `section_registry.py` (single authoritative allowlist), [DATA_MODEL](DATA_MODEL.md).
- **LIKELY CODE:** `section_registry.py` (SectionDefinition + template_name + validate_settings),
  `settings_schema.py` (declarative field types — M10 dual validation), template partial.
- **⚠️ M10:** `settings_schema.clean_schema_patch` runs THEN legacy `SectionDefinition.validate_settings`.
- **⚠️ L3:** if you touch page-type constants, keep the model enum and the registry strings in sync
  (guarded by `PageTypeConstantsMatchModelTests`).

## Recipe: Change layout mutation behavior (R4)
- **READ FIRST:** `r4_mutation_service` (the single optimistic boundary), [FLOWS](FLOWS.md).
- **INVARIANTS:** one allowlisted mutation per request; compare/increment `edit_revision`; record history.
- **REGRESSION RISK:** bypassing `r4_mutation_service` breaks optimistic concurrency + undo/redo.

## Recipe: Change publish / draft / restore
- **READ FIRST:** `layout_service.publish/get_or_create_draft/restore_version`, [STATE_MACHINES](STATE_MACHINES.md).
- **INVARIANTS:** pointer swap; one PUBLISHED per layout; restore → new draft; edit history wiped at publish.

## Recipe: Add / change an A8 Ready Template or layout preset
- **READ FIRST:** `a8_ready_templates.py`, `layout_preset_registry.py`, `preset_service`.
- **INVARIANTS:** presets only touch named pages; never write merchant colors unless no palette chosen.

## Recipe: Change section placement (Container/Cell)
- **⚠️ M12:** three mechanisms coexist. The **executing** truth is `StorefrontCell.section`
  (OneToOne). `StorefrontSection.cell` (FK) is parallel/future; `row_key/row_span` is legacy.
- **LIKELY CODE:** `container_service`, `row_service` (legacy 12-col).

## Recipe: Touch the R3 legacy editor
- **⚠️ It is fail-closed** when `r4_editor_enabled=True`. Changing R3 only affects Stores explicitly
  pinned back for rollback. **DR-6** governs whether R3 is retired at all — do not remove it.

## Recipe: Change footer
- **⚠️ M2 — footer ×3.** A footer change may span `StorefrontLayoutVersion.footer_config` (here),
  `content.FooterSettings` (content domain), and `global_region_registry` footer variant. Read the
  content pack too.

## Blocking-decision reference
| Change | Decision |
|---|---|
| retire R3 legacy editor | **DR-6** |
| consolidate appearance/palette/theme sources | (not a DR yet — M1 documented; would need a new decision) |
