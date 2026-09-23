# storefront_builder — State Machines

```
domain_id: D9
code_baseline: 5883a140
```

## StorefrontLayoutVersion.status — GUARDED by service (pointer-swap publish)
```
draft → published → archived
```
- `layout_service.publish` (`@atomic`): ensure containers → delete edit history → compute
  `content_fingerprint` → DRAFT→PUBLISHED (+`published_at`) → previous PUBLISHED→ARCHIVED →
  set `layout.published_version = draft`, `draft_version = None`, `uses_visual_storefront_layout=True`.
- `get_or_create_draft`: creates DRAFT (source=legacy_bootstrap first time, else manual/cloned).
- `restore_version`: clones an old version into a **NEW DRAFT** (never publishes directly).
- `discard_draft`: deletes the draft.

## Editor-generation gate (not a status field, but a mode machine)
```
r4_editor_enabled = True (default)  → R4 is the active write surface; R3 mutations fail-closed (Http404)
r4_editor_enabled = False (pinned)  → R3 is the rollback write surface
```
Enforced by `views.py::_require_legacy_editor_active`. See [GENERATIONS](GENERATIONS.md).

## Optimistic concurrency (R4)
`StorefrontLayoutVersion.edit_revision` is a monotonic token. `r4_mutation_service` compares the
client's `base_revision` before applying a mutation and increments on success — an optimistic lock.

## Appearance immutability guard
`storefront_appearance.persistence.persist_store_appearance_manifest` raises
`ImmutableStoreAppearanceError` if the version is not a DRAFT — published/archived appearance is
immutable.

## Edit history
`StorefrontEditHistoryEntry` (per-draft undo/redo) is bounded and **wiped at publish**.
