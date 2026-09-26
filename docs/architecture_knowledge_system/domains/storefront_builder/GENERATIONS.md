# storefront_builder — CURRENT vs LEGACY vs TEMPLATE/PRESET (de-confliction) ★

```
domain_id: D9
code_baseline: 5883a140
open_decisions: DR-6
known_risks: H3
```

> This is the map that resolves the storefront-builder confusion. **A future engineer must be able
> to tell immediately which path is current.** Answer: **R4 is CURRENT; R3 is LEGACY (fail-closed);
> A8 + layout presets are the TEMPLATE/PRESET layer on top of R4.**

## The three generations (H3)

| Generation | What it is | Status at 5883a140 | Code |
|---|---|---|---|
| **R3 (legacy)** | The original editor + the old `row_key/row_span` section layout; the now-**deleted** `family_registry.py`/`preset_registry.py` | **LEGACY — fail-closed** | `views.py` (routes decorated `@_require_legacy_editor_active` → Http404 when R4 active) |
| **R4 (current)** | The canonical merchant editor; Container/Cell layout; `settings_schema` Strangler; typed `storefront_appearance` Design Engine | **CURRENT (default)** | `r4_views.py` + `services/r4_mutation_service.py` |
| **A8 (templates)** | "A8 catalog" of 50 complete Ready Templates composed on the layout-preset system | **CURRENT template layer** | `a8_ready_templates.py` on `layout_preset_registry.py`, applied by `preset_service` |

## How the current path is selected (VERIFIED)
- `StorefrontLayout.r4_editor_enabled` (`models.py:211`) — **default `True`**. Dashboard nav routes
  to R4.
- Legacy R3 mutation routes are decorated with `views.py::_require_legacy_editor_active` (`:65`),
  which **`raise Http404`** when `r4_editor_enabled` is True. So R3 mutation is unreachable unless a
  Store is explicitly pinned back for rollback.
- Removed registries `family_registry.py` / `preset_registry.py` are **confirmed absent** (D5); only
  docstrings/tests still reference them.

## What is shared vs generation-specific
- **Shared (not caught by the legacy guard):** Ready Template gallery/apply, draft preview, history
  browser, media views. `_require_legacy_editor_active` is applied only to a **named list** of R3
  mutation routes, never "everything in views.py."
- **R4-specific:** `r4_views.py`, `r4_mutation_service.py`, Container/Cell mutations, typed appearance.

## Duplicate sources of truth in this domain (documented)
- **M1 — appearance/theme/palette:** `appearance_registry.py` (templates + palettes) +
  `palette_pack_64.py` (more palettes) + `theme_catalog.py` (occasion themes), all re-projected into
  the typed `storefront_appearance` `COMPONENT_REGISTRY`; persisted appearance also **mirrored** into
  `header_config`/`footer_config` by `storefront_appearance.persistence`.
- **M2 — footer ×3:** `StorefrontLayoutVersion.footer_config` + `content.FooterSettings` + `global_region_registry` footer variant.
- **M10 — dual settings validation:** `settings_schema.clean_schema_patch` THEN legacy `SectionDefinition.validate_settings`.
- **M11 — dual placement media:** legacy ImageField + MediaAsset FK on content placements.
- **M12 — dual/parallel section placement:** `StorefrontCell.section` (OneToOne, "executing truth")
  vs `StorefrontSection.cell` (FK, "parallel/future") vs legacy `row_key/row_span`.

## Decision
**DR-6 — legacy-path removal — OPEN.** R3 is retained (fail-closed) as a rollback editor per the
"single-active-write-surface" policy; whether/when to remove it is DR-6. Do not remove.

## Quick answer for common confusion
- "Which editor is live?" → **R4.**
- "Is R3 dead?" → No: routes exist but mutation is **fail-closed** when R4 is enabled (the default).
- "What's a 'template' / 'preset' / 'family'?" → **Families are retired.** A "template" is an **A8
  Ready Template** (a preset composition) applied via `preset_service`; a "preset" is a
  `LayoutPresetDefinition`.
