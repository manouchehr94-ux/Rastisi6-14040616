# P5-W2 Architecture Duplication Audit

Rule: ONE CONCEPT = ONE CANONICAL OWNER. Verified before opening the PR.

| Concern | Count | Owner |
|---|---|---|
| Theme family | **1** | `storefront_appearance/families.py` — `key="theme"`, `renderer_role="appearance_token"` (existing role; `_RENDERER_ROLES` NOT expanded) |
| Theme catalog | **1** | `apps/storefront_builder/theme_catalog.py` (sole occasion data authority) |
| Theme registry path | canonical | `theme_catalog → adapters.build_existing_component_definitions() → registry.COMPONENT_REGISTRY → rendering.resolve_store_appearance_manifest_state()` |
| Theme resolver | **1** | `storefront_appearance/rendering.theme_overlay_state()` (extends the single `resolve_store_appearance_manifest_state`; no parallel `resolve_theme()`) |
| Theme persistence owner | existing | `services/appearance_authority_service` → `storefront_appearance/persistence.persist_store_appearance_manifest` (no theme-specific persistence service) |
| Draft lifecycle | **1** | existing `StorefrontLayoutVersion` Draft; no theme-specific Draft |
| Mutation boundary | **1** | `services/r4_mutation_service.apply_mutation` (theme.apply/theme.clear dispatch through it) |
| Preview engine | **1** | shared `render_service` + `build_universal_storefront_context`; no editor-only theme render |
| Public renderer | **1** | same shared render pipeline; no public-only theme render |

## Confirmed ABSENT
- `theme_registry.py` competing with `COMPONENT_REGISTRY` — **none** (`find` empty).
- Second Theme manifest — **none** (theme lives in the one appearance manifest JSON).
- Direct JSON writes from UI/JS — **none** (`theme.apply`/`theme.clear` go through
  `R4.enqueueMutation` → mutate endpoint → `apply_mutation` → authority → persistence).
- Theme-specific Draft — **none**.
- Theme-specific publish service — **none** (uses existing `layout_service.publish` / `r4_mutation_service.publish_draft`).
- Theme-specific preview route — **none**.
- Per-template Theme engine / per-template Theme CSS fork — **none**
  (`occasion_theme.css` is one bounded token layer; no `if template == ...`).
- Duplicated occasion metadata — **none** (`adapters.py` contains no occasion
  hexes/labels; it reads `theme_catalog`).
- `template_baseline_snapshot` used for Theme restore — **NO** (the only reference
  in theme code is a comment stating it is deliberately NOT used; `clear_theme`
  resets only `selections["theme"]`/`settings["theme"]`).

## Evidence commands (all confirmed)
```
grep 'key="theme"' families.py                     -> 1
find apps -name theme_catalog.py                    -> apps/storefront_builder/theme_catalog.py (1)
find theme_registry/theme_service/theme_resolver    -> (none)
grep 'def resolve_theme'                             -> none
grep 'def theme_overlay_state'                       -> rendering.py (1)
grep 'def apply_theme|def clear_theme' (non-test)    -> appearance_authority_service.py only
grep 'theme' registry.py                             -> none (auto-built from adapters)
grep occasion hexes/keys in adapters.py              -> none (reads catalog)
```

PASS — no architectural duplication introduced by P5-W2.
