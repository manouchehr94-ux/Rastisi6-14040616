# storefront_builder — Flows

```
domain_id: D9
code_baseline: 5883a140
source: Phase 1 doc 08 (Flows 10, 11)
```

## Flow: R4 layout edit → publish (Phase 1 Flow 10)
```
R4 editor (JS) → storefront-builder/r4/mutate/ → r4_mutation_service
  @atomic: lock StorefrontLayout; resolve active draft; compare base_revision (optimistic)
  dispatch ONE allowlisted mutation (section/container/appearance) via shared services
  bump edit_revision; record StorefrontEditHistoryEntry

publish → storefront-builder/r4/publish/ → layout_service.publish
  @atomic: ensure containers → delete edit history → compute content_fingerprint
  DRAFT→PUBLISHED (+published_at); previous PUBLISHED→ARCHIVED
  layout.published_version = draft; draft_version = None; uses_visual_storefront_layout = True

restore → r4/restore/<pk>/ → layout_service.restore_version  (clones into a NEW draft; never publishes)
discard → r4/discard/ → layout_service.discard_draft
```
Concurrency: optimistic `edit_revision` token; publish is a pointer swap.

## Flow: Public storefront render (Phase 1 Flow 11)
```
GET / (resolved Store) → catalog.views.home → render_service.build_render_items(published_version, store)
  reads the published StorefrontLayoutVersion; if uses_visual_storefront_layout is False → legacy
  hard-coded home fallback
  → storefront_shell.html + content context processors (footer/menus/social)

content page: GET pages/<slug>/ → content.views.page_detail → build_universal_storefront_context (shell)
```

## Flow: Apply an A8 Ready Template / preset
```
gallery/apply → preset_service.apply_preset (A8 recipe or LayoutPresetDefinition)
  @atomic; validate-before-write; only touches the pages the preset names; writes sections/containers,
  template_provenance, template_baseline_snapshot; never overwrites merchant colors unless no palette chosen
```

## Editor-gate behavior (H3)
Legacy R3 mutation routes → `_require_legacy_editor_active` → Http404 when `r4_editor_enabled=True`
(the default). See [GENERATIONS](GENERATIONS.md).
