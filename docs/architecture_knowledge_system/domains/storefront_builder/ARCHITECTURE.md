# storefront_builder — Architecture

```
domain_id: D9
code_baseline: 5883a140
```

## Shape
A versioned, draft/publish layout engine with a service layer, a set of Python config registries,
and two editor front-ends (R4 current, R3 legacy) plus a template/preset layer (A8). Routes live in
`dashboard`; rendering is consumed by `catalog`/`content`.

```
R4 editor (JS) ─► r4/mutate/ ─► r4_mutation_service (optimistic edit_revision, one @atomic)
                                     │ dispatches allowlisted mutation
                                     ▼
       layout_service / container_service / preset_service / appearance_authority_service
                                     │ write
                                     ▼
   StorefrontLayoutVersion(draft) ── StorefrontPage(×6) ── StorefrontSection ── Container ── Cell
                                     │
publish ─► layout_service.publish (pointer swap: draft→published, prev→archived)
                                     │
public render ◄─ render_service.build_render_items(published version)  ◄─ catalog.home / content.page_detail
```

## Config registries (source of truth for available options — M1)
Platform-owned frozen Python dicts/dataclasses (git/code-review is their versioning), NOT
DB-versioned. Merchant *selection* is persisted in `StorefrontLayoutVersion.appearance_config` /
`header_config` / `footer_config`. The typed `storefront_appearance` engine re-projects several
registries into a `COMPONENT_REGISTRY` and mirrors selectors into header/footer_config on persist.

## Generational layering (H3 — see GENERATIONS)
R3 legacy (fail-closed) · R4 current (default) · A8 templates + layout presets. Families are retired
(`family_registry.py`/`preset_registry.py` deleted).

## Why it looks this way (design intent — see HISTORICAL_CONTEXT)
The Universal Storefront Builder V2 spec (2026-08) decided to replace coded families with one
universal engine + presets; R4 + A8 are that decision realized. The R3 editor is retained as a
fail-closed rollback under the "single-active-write-surface" policy (DR-6).
