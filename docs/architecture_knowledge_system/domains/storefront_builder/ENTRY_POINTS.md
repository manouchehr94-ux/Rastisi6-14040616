# storefront_builder — Entry Points

```
domain_id: D9
code_baseline: 5883a140
```

> `storefront_builder` has **no `urls.py` of its own**. All its routes are registered in
> `apps/dashboard/urls.py`, which imports `apps.storefront_builder.views` (R3),
> `r4_views` (R4), and `media_views`. Routes are behind the `STOREFRONT_LAYOUT_MANAGE` permission
> (dashboard `staff_required` + `permission_required`).

## R4 (current) routes — `r4_views.py`, under `storefront-builder/r4/`
editor shell, `/mutate/` (→ `r4_mutation_service`), `/design-lab/`, `/sections/<pk>/inspector/`,
`/resources/picker/`, `/history/`, `/publish/`, `/discard/`, `/reset-page/`, `/reset-storefront/`,
`/switch-template/`, `/restore/<pk>/`, `/apply-industry-layout/`. **Dashboard nav routes here by
default** (`r4_editor_enabled=True`).

## R3 (legacy) routes — `views.py`, under `storefront-builder/`
editor, `/preview/`, `/sections/…`, `/containers/…`, `/cells/…`, `/blocks/…`, `/appearance/`,
`/header/`, `/footer/`, `/apply-preset/`, `/publish/`, `/undo|redo/`, `/history/`+`/restore/`,
`/templates/`+`/preview/`, `/apply-industry-layout/`. **Mutation routes are `@_require_legacy_editor_active`
→ Http404 when R4 is enabled** (fail-closed). Shared capabilities (gallery/apply, preview, history,
media) are NOT caught by the guard.

## Media — `media_views.py`
`/sections/<pk>/media/<kind>/…` (list/add/edit/delete for hero/banner) — writes **content** app
placement rows (cross-domain).

## Public rendering (not a builder route)
`catalog.views.home` and `content.views.page_detail` call `render_service.build_render_items` /
`build_universal_storefront_context` (lazy imports) to render the published layout.

## Management commands
`capture_ready_template_previews.py`, `qa_storefront_builder.py`, `qa_storefront_builder_r4.py`.

## Signals / async
None. Publish/mutate side effects are synchronous within `@atomic`.

## Client-side JS (INFERRED)
The R4 editor JS (under `static/`) is inferred to POST to `storefront-builder/r4/mutate/`
(matching `r4_mutation_service`'s single-boundary design). The exact JS→endpoint set was not read
from source (carried as an UNKNOWN from Phase 1).
