# P5-W3 — Architecture Duplication Audit (Section 31)

**Central law:** ONE CONCEPT = ONE CANONICAL OWNER. This audit proves — with
grep/search evidence, not assertion — that P5-W3 introduced **no** architectural
duplication. Diffs are against the certified base
`e28b563ca614bd2eafea8ec102ad44cd8a56ae82`.

## Required scorecard

| Concept | Count | Owner (reused) |
|---|---|---|
| Candidate engine | **1 (reused)** | `preset_service.resolve_preset_candidate` + the pure `rendering.resolve_store_appearance_manifest_state` |
| Preview renderer | **1** | `render_service.build_page_render_items` / `_build_items_from_sections` |
| Preview route | **1 (reused)** | `views.storefront_preview` (extended with a `?design_lab=` branch, no new route) |
| Draft model | **1** | `StorefrontLayoutVersion` |
| Appearance manifest | **1** | `StoreAppearanceManifest` (exactly one class defined) |
| Component registry | **1** | `COMPONENT_REGISTRY` / `COMPONENT_FAMILIES` |
| Mutation boundary | **1** | `r4_mutation_service.apply_mutation` (one arm added: `design_lab.apply_candidate`) |
| History system | **1** | `edit_history_service` (`record_change`) |
| Theme owner | **1** | `appearance_authority_service.apply_theme` / `clear_theme` (W2) |
| Design-Lab persisted model | **0** | — |
| Design-Lab DB tables | **0** | — |
| Candidate preset registration | **0** | `register_layout_preset` never called from Design Lab |
| localStorage authority | **0** | — |
| Direct Draft JSON writes from JS | **0** | Apply routes through `enqueueMutation` → `mutate/` |
| Per-template Random-Mix engines | **0** | one template-agnostic, registry-driven generator |
| Migrations | **0** | — |

## Evidence

### Candidate engine = 1 reused (no new engine)
`design_lab_service` resolves candidates ONLY through the canonical resolver:
```
apps/storefront_builder/services/design_lab_service.py
  41:  resolve_store_appearance_manifest_state,      # import of the canonical resolver
 241:  return resolve_store_appearance_manifest_state(validated.manifest, version_id=...)
```
`candidate_to_preset` produces an in-memory `LayoutPresetDefinition` for the
canonical `preset_service.resolve_preset_candidate` — no new candidate class/table.

### Candidate is NEVER registered
```
$ grep -n register_layout_preset apps/storefront_builder/services/design_lab_service.py
NONE (candidate never registered)
```
`list_ready_templates()` = **50** (unchanged); `list_layout_presets()` = 55 (unchanged).

### Preview route = 1 (reused), renderer = 1 (reused)
The only URL added by W3 is the **read-only** `design-lab/` computation endpoint
(diff of `apps/dashboard/urls.py` shows a single new `path(`). No new preview
view/route. The candidate preview extends `views.storefront_preview` in place:
```
apps/storefront_builder/views.py
 290:  design_lab_token = request.GET.get("design_lab")
 297:  store_appearance = design_lab_service.resolve_candidate_appearance(draft, candidate)
 302:  items = build_page_render_items(page, store, ..., store_appearance=store_appearance)
```
Same renderer (`build_page_render_items`), same route, transient `ResolvedStoreAppearance`.

### The `design-lab/` endpoint WRITES NOTHING
Searching the endpoint body for any write primitive:
```
$ sed -n '/def storefront_r4_design_lab/,/def _random_design_lab_seed/p' r4_views.py \
    | grep -E 'apply_mutation|\.save\(|persist_store_appearance|record_change|apply_theme|clear_theme'
(only) candidate_apply_mutation(...)   # builds the mutation dict; does NOT apply it
```
It computes transient candidates and returns an opaque token + Persian-labelled
diffs. The `apply_payload` action merely **builds** the `design_lab.apply_candidate`
mutation dict; the real write happens when the client posts it to the canonical
`mutate/` endpoint.

### Mutation boundary = 1; history = 1; theme = 1
```
$ grep -c '^def apply_mutation\b' r4_mutation_service.py            -> 1
$ grep -rl 'def record_change' services/*.py                        -> edit_history_service.py (only)
$ grep -rl '^def clear_theme\b' services/*.py                       -> appearance_authority_service.py (only)
$ grep -rl '^def storefront_preview\b' views.py                     -> views.py (only)
```
`_apply_design_lab_candidate` delegates every state change to existing owners —
`_persist_manifest_selection_updates` (non-theme families) and W2
`apply_theme`/`clear_theme` (theme) — and never calls `record_change`/`.save()`
itself (the single revision advance stays in `apply_mutation` → `record_change`).

### Zero models, zero migrations
```
$ grep -nE 'models\.Model' services/design_lab_service.py            -> NONE
$ git diff --name-only e28b563..HEAD -- '*/migrations/*'              -> NONE
$ grep -E '^\+.*class .*\(.*models\.Model' <full W3 diff>            -> NONE
```

### Zero localStorage authority; no JS draft writes
```
$ grep -nE 'localStorage|sessionStorage' r4_editor.js
NONE (only comment references, 0 API calls)
```
The Design Lab JS holds only the opaque candidate token + transient locked set;
Apply routes through `R4.enqueueMutation(body.mutation)` (the single mutation queue).

### No per-template Random-Mix logic
```
$ grep -nE 'dark_digital|warm_boutique|if.*template.*==|per.template' design_lab_service.py
NONE (generator is template-agnostic, registry-driven)
```
`generate_candidate` iterates `DESIGN_LAB_RANDOMIZABLE_FAMILIES` and picks from
`list_components(family)` — one generator for all templates.

## W3 production footprint (additive, single-owner-preserving)
```
apps/dashboard/urls.py                                   |   5 +
apps/storefront_builder/r4_views.py                      | 199 +   (read-only endpoint + context)
apps/storefront_builder/services/appearance_authority_service.py | 54 +  (apply_component_variant writer)
apps/storefront_builder/services/design_lab_service.py   | 397 +   (NEW — the only new module)
apps/storefront_builder/services/r4_mutation_service.py  |  81 +   (one dispatch arm + handler)
apps/storefront_builder/static/storefront_builder/r4_editor.js | 213 +  (Design Lab controller)
apps/storefront_builder/templates/.../r4/editor.html     |  49 +   (Design Lab panel)
apps/storefront_builder/views.py                         |  20 +   (candidate preview branch)
```
Only `design_lab_service.py` is a new module; every other change **extends an
existing single owner**. No second copy of any canonical concept was created.

## Conclusion
**ARCHITECTURE DUPLICATION GATE: PASS.** No STOP condition from Section 3 was
triggered.
