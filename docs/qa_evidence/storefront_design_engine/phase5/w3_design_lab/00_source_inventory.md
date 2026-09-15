# P5-W3 Design Lab / Random Mix — Source Inventory

**Certified starting checkpoint:** `e28b563ca614bd2eafea8ec102ad44cd8a56ae82`
**Implementation branch:** `feature/phase5-w3-design-lab` (created from the checkpoint above)
**Runtime verified in sandbox:** Python 3.12.13, Django 5.2.17
**Investigated at:** the working tree of the branch, before any production code was written.

This document records the **exact current signatures / owners** of every canonical
primitive P5-W3 must reuse. Line numbers are from the working tree at the checkpoint
and are recorded for orientation only — the source itself is authoritative.

> **Governance note.** Nothing in this inventory conflicts with the authoritative
> W3 architecture (transient candidate = `LayoutPresetDefinition`-equivalent resolved
> through `resolve_preset_candidate`, preview via the existing `storefront_preview`
> route, atomic Apply through `r4_mutation_service.apply_mutation`). No STOP condition
> was triggered. One correction to the plan's assumptions is noted in §A (the plan's
> `candidate_to_preset` -> `resolve_preset_candidate` path is available, but a
> **simpler, already-existing** transient-manifest resolution path
> (`resolve_store_appearance_manifest_state`) covers the appearance-DNA candidate more
> directly and is what W3 uses for preview; see §7/§10).

---

## A. Candidate / Preset primitives

### `LayoutPresetDefinition` — `apps/storefront_builder/layout_preset_registry.py:87`
Frozen dataclass. Relevant fields:
- `key`, `label_fa`, `description_fa`, `version="1"`, `is_ready_template=False`
- `store_appearance: dict | None = None` — the typed `StoreAppearanceManifest` **primitive dict** `{"schema_version":1,"selections":{family:component_key},"settings":{...}}`
- `appearance: dict`, `default_palette_slug`, `header: dict|None`, `footer: dict|None`
- `pages: dict[str, tuple[PresetSectionEntry, ...]]`
- `compatible_families: frozenset[str] | None = None`

### `PresetSectionEntry` — `layout_preset_registry.py:59`
Frozen dataclass: `section_key`, `settings=None`, `row_key=""`, `row_span=12`, `container_settings=None`.

### `register_layout_preset(definition)` — `layout_preset_registry.py:190`
Validates + stores in module dicts `LAYOUT_PRESET_REGISTRY` / `LAYOUT_PRESET_VERSION_REGISTRY`.
**W3 must NEVER call this for a candidate** — a Design Lab candidate is never registered.

### `list_ready_templates()` — `layout_preset_registry.py:221` / `list_layout_presets()` — `:217`
Read helpers. **50 Ready Templates** are expected to remain unchanged.

### `resolve_preset_candidate(draft, preset) -> ResolvedPresetCandidate` — `services/preset_service.py:646`
Read-only counterpart of `apply_preset`. **Writes nothing** (docstring is explicit: no
`draft.save()`, no Section/Container rows, no history, no manifest write, no baseline,
no new version). Raises the exact same `InvalidPresetError` / `LockedSectionsPresentError`
/ `InvalidStoreAppearanceContract` the persisting path raises. When `preset.store_appearance`
is set it validates via `validate_store_appearance_manifest(..., require_complete=True)` and
resolves via `resolve_store_appearance_manifest_state(validated.manifest, version_id=draft.pk)`.

### `resolve_preset_candidate_by_key(draft, key)` — `preset_service.py:689`
Looks up by key (raises `UnknownPresetError`) then delegates.

### `ResolvedPresetCandidate` — `preset_service.py:611`
Frozen dataclass: `preset_key, preset_version, appearance_config, header_config,
footer_config, pages: dict[page_type -> ResolvedPresetCandidatePage],
store_appearance: ResolvedStoreAppearance | None`.

### `ResolvedPresetCandidatePage` — `preset_service.py:595`
Frozen dataclass: `sections: list` (unsaved `pk=None` sections), `container_settings: list`.

**Finding (design decision):** A Design Lab candidate changes only **Store-Appearance DNA
selections/settings** — it never changes page composition. The cheapest canonical way to
resolve an appearance-only candidate into render state is the pure
`resolve_store_appearance_manifest_state(manifest, version_id=draft.pk)` (§7). The
plan's `candidate_to_preset -> resolve_preset_candidate` route is still honored where a
full preset object is conceptually needed, but the appearance manifest resolution used for
Preview goes through the exact same one resolver that `resolve_preset_candidate` itself
calls — never a second implementation.

---

## B. Store Appearance manifest / registry

### `StoreAppearanceManifest` — `storefront_appearance/contracts.py`
Frozen dataclass: `schema_version:int (==1)`, `selections: Mapping[str,str]` (family->component_key),
`settings: Mapping` (per-family typed settings; only `theme.intensity` currently allowlisted).
Contract-violation exception: **`InvalidStoreAppearanceContract(ValueError)`**.

### `validate_store_appearance_manifest(raw, *, require_complete=True, base_manifest=None)` — `storefront_appearance/validation.py`
Single validation choke point. Rejects unknown families/keys, verifies every `component_key`
exists in `COMPONENT_REGISTRY` with the right `family_key`, runs `evaluate_manifest_compatibility`
(raises on hard errors). Returns `ValidatedStoreAppearance(manifest, compatibility)`.

### `COMPONENT_FAMILIES` — `storefront_appearance/families.py`
Ordered catalog. **Exact family keys, roles, defaults, and option counts (enumerated live):**

| family | role | optional | safe default | # options |
|---|---|---|---|---|
| `header` | global_region | no | `header.legacy_default.v1` | 22 |
| `mega_menu` | global_region | yes | `mega_menu.none.v1` | 1 |
| `hero` | section_variant | no | `hero.legacy_default.v1` | 19 |
| `layout` | composition | no | `layout.legacy_default.v1` | 17 |
| `product_view` | section_variant | no | `product_view.legacy_default.v1` | 13 |
| `card` | section_variant | no | `card.legacy_default.v1` | 17 |
| `badge` | section_variant | yes | `badge.none.v1` | 2 |
| `motion` | appearance_token | no | `motion.subtle.v1` | 3 |
| `footer` | global_region | no | `footer.legacy_default.v1` | 16 |
| `bottom_nav` | global_region | yes | `bottom_nav.hidden.v1` | 9 |
| `theme` | appearance_token | yes | `theme.none.v1` | 8 |

`ComponentFamilyDefinition` fields: `key, label_fa, storage_adapter_key,
safe_default_component_key, renderer_role, optional=False, capabilities=frozenset()`.

### `COMPONENT_REGISTRY` + helpers — `storefront_appearance/registry.py`
`get_component(key)` (`:35`), `require_component(key)` (`:41`, raises `InvalidStoreAppearanceContract`),
`list_components(family_key=None)` (`:48`), `component_counts_by_family()` (`:58`).
`ComponentDefinition` fields: `key, family_key, version:int, label_fa, registry_reference,
capabilities, compatibility, status, deprecated_by`.

**Reading a draft's current family selection:**
`load_store_appearance_manifest(version)` -> `StoreAppearanceManifest`, then
`manifest.selections[family_key]`. Or `resolve_store_appearance_render_state(version)`
-> `ResolvedStoreAppearance` with `.manifest.selections` + `.component(family_key)`.

### Eligible randomized families (W3 design decision)
Design DNA families that (a) have real alternatives and (b) are visually meaningful and
(c) are not commerce truth:
`header, hero, product_view, card, footer, badge, bottom_nav`.
- `theme` is **orthogonal** — only randomized when explicitly requested (§9).
- `mega_menu` excluded from Random Mix (only 1 option — no meaningful alternative).
- `layout`, `motion` excluded from the default Random Mix set (composition/token, kept
  stable so Random Mix changes visible chrome/section DNA; they remain valid canonical
  selections and are never fabricated). This keeps page composition (the merchant's
  Draft content) exactly preserved.

---

## C. Appearance authority (write path)

### `appearance_authority_service` — `services/appearance_authority_service.py`
Public writers present at the checkpoint (all keyword-only `version=`):
- `apply_appearance_patch` (`:113`)
- `apply_store_appearance_manifest` (`:132`) — validate+persist the COMPLETE typed manifest
- `apply_theme` (`:171`) — W2 owner; `theme.none.v1` routes to `clear_theme`
- `clear_theme` (`:215`) — W2 owner; sets `theme.none.v1`, pops `settings["theme"]`, preserves all else; **never touches `template_baseline_snapshot`** (confirmed)
- `apply_header_variant` (`:230`), `apply_footer_variant` (`:253`)
- `apply_ready_template_appearance` (`:289`), `apply_page_appearance_patch` (`:342`), `effective_page_appearance_config` (`:364`)

Helpers to mirror: `_manifest_with_family(version, *, family_key, component_key)` (`:144`)
replaces exactly one selection over the current effective manifest;
`_typed_key_for_selector` (`:154`) translates a legacy selector to a typed key.

### **`apply_component_variant` — DOES NOT EXIST YET.**
Section 12 requires W3 to add a generalized `apply_component_variant(draft, family, component_key)`
mirroring `apply_header_variant`/`apply_footer_variant` (Green 1). It will validate the
component belongs to the family, then `_manifest_with_family` + `persist_store_appearance_manifest`.

### `persist_store_appearance_manifest(version, raw)` — `storefront_appearance/persistence.py`
Single validating+persisting primitive. Requires DRAFT status (`ImmutableStoreAppearanceError`),
validates, writes legacy mirrors (header/footer/bottom_nav/motion) + full primitive under
`appearance_config["store_appearance"]`, one `version.save(update_fields=[...])`.

---

## D. Mutation boundary / stale / tenant / history

### `apply_mutation(*, store, actor, base_revision, mutation) -> int` — `services/r4_mutation_service.py:1046`
`@transaction.atomic`. Flow: `_lock_active_draft` -> `snapshot_draft` -> `_dispatch_mutation`
-> `edit_history_service.record_change` (the ONE `edit_revision` advance). Must NOT re-increment.

### `_dispatch_mutation` — `r4_mutation_service.py:937`
Explicit allowlist (no dynamic dispatch). Existing appearance types include
`appearance.component.update`, `appearance.manifest.apply`, `theme.apply`, `theme.clear`.
**W3 adds one arm: `design_lab.apply_candidate`.**

### `_lock_active_draft(*, store, base_revision)` — `r4_mutation_service.py:1018`
THE concurrency + tenant boundary: `StorefrontLayout.objects.select_for_update().get(store=store)`,
requires an active DRAFT, `if draft.edit_revision != base_revision: raise R4StaleRevision(...)`.

### `R4StaleRevision(R4MutationError)` — `:59` / `R4MutationError(ValueError)` — `:55`
`R4StaleRevision.current_revision` carries the fresh revision. HTTP maps to `409`.

### `_require_pinned_appearance_draft(*, draft, mutation)` — `r4_mutation_service.py:506`
Requires `mutation["draft_id"] == draft.pk` (else `draft_not_found`). W3's handler reuses this.

### `_persist_manifest_selection_updates(*, draft, updates, preserve_live_legacy_siblings=False)` — `r4_mutation_service.py:552`
**Already applies multiple family selections atomically** in ONE
`apply_store_appearance_manifest` call. This is the primitive W3's `design_lab.apply_candidate`
handler reuses to apply the whole candidate atomically. Semantic no-op short-circuits.

### `_apply_appearance_component_update` — `r4_mutation_service.py:594` (reference handler to mirror)
Validates `family in COMPONENT_FAMILIES` + `get_component(component_key).family_key == family`,
then `_persist_manifest_selection_updates(updates={family: component_key}, preserve_live_legacy_siblings=True)`.

### `_apply_theme_apply` (`:619`) / `_apply_theme_clear`
Delegate to `appearance_authority_service.apply_theme` / `clear_theme`. **W3's Remove-Theme
Apply reuses `clear_theme` through this exact same boundary** (candidate carrying `theme.none.v1`).

### `edit_history_service` — `services/edit_history_service.py`
`snapshot_draft(draft)` captures `appearance_config` (incl. the `store_appearance` manifest);
`record_change` is the single `edit_revision` advance; `undo`/`redo`/`restore_draft_state`
restore prior/next `appearance_config`. Undo of a Design Lab Apply restores the prior manifest.

### Tenant resolution — `apps/stores/resolution.py`
`resolve_store_for_service(request)` is the HTTP-boundary resolver the R4 views use
(`r4_views.storefront_r4_mutation` -> `apply_mutation(store=...)`). Store identity is never
taken from client input inside the service. A foreign draft_id -> `draft_not_found`.

### HTTP endpoint — `r4_views.storefront_r4_mutation` — `r4_views.py:654`
`@require_POST`, staff+permission gated, r4_editor_enabled gated. Accepts `{base_revision, mutation}`.
**Generic** — W3's `design_lab.apply_candidate` flows through it with NO new endpoint. Maps
`R4StaleRevision`->409, `R4MutationError`->400.

---

## E. Preview / renderer

### `storefront_preview(request)` — `views.py` (url name `dashboard:storefront-builder-preview`, `apps/dashboard/urls.py:276`)
Staff+permission gated, `@xframe_options_sameorigin` (embeds in the editor iframe).
Resolves `store_appearance = resolved_store_appearance_for_request(request, draft)` ONCE, then
`items = build_page_render_items(page, store, page_context=..., store_appearance=store_appearance)`.
Has an **existing candidate branch** (`?preview_template=`) that swaps a read-only
`_CandidateAppearanceVersion` stand-in for global tokens — precedent for a transient preview.

### `resolve_store_appearance_manifest_state(manifest, *, version_id)` — `storefront_appearance/rendering.py:67`
**Pure, no-I/O** resolver from a typed manifest to `ResolvedStoreAppearance`. Explicitly
designed so a transient candidate can be resolved without persistence. **This is the seam
W3 uses:** build a candidate `StoreAppearanceManifest`, resolve it here, pass the resulting
`ResolvedStoreAppearance` as `store_appearance=` to `build_page_render_items`. Same renderer,
same route, zero writes.

### `build_page_render_items(page, store, page_context=None, *, global_appearance=None, store_appearance=None)` — `services/render_service.py:781`
The canonical renderer entry. `build_candidate_render_items` (`:1047`) is the existing
unsaved-section wrapper over `_build_items_from_sections`.

### Render-time overlays — `render_service._build_items_from_sections` (`:841`) + `rendering.py`
`section_variant_for` (`:278`), `card_settings_for` (`:164`), `badge_settings_for` (`:177`)
overlay hero/product_view/card/badge **at render time from the manifest `selections`** — the
persisted Section is NOT rewritten. **Implication for W3's write path:** the canonical
persisted state for these families lives in the **manifest `selections`**, so Apply reconciles
by writing `selections[family] = component_key` (via `apply_component_variant` /
`_persist_manifest_selection_updates`) — exactly what makes them persisted rather than
render-time-only. After Apply, persisted manifest and rendered component agree. (An explicit
per-Section `variant_explicit`/`card_style_explicit` local marker suppresses the overlay for
that section — expected and preserved.)

---

## F. R4 editor UI

- View: `r4_views.storefront_r4_editor` (`:483`), template
  `dashboard/storefront_builder/r4/editor.html`, JS `static/storefront_builder/r4_editor.js`.
- Design context builder `_build_global_design_context` (`:361`), theme sub-context
  `_build_theme_design_context` (`:448`). **W3 adds a `design_lab` sub-context** the same way.
- The W2 Theme panel (`data-r4-theme-panel`, `data-r4-theme-apply`, `data-r4-theme-clear`) is
  the exact UI+JS pattern W3 mirrors for the Design Lab panel.
- JS mutation seam: `R4.enqueueMutation(mutation)` -> single queued POST to the mutation
  endpoint; `refreshGlobalDesignAndPreview()` reloads the `#r4PreviewFrame` iframe. W3's
  Preview reloads the same iframe with a `?design_lab=<token>` query param.

---

## G. Test conventions / baselines
- Base test case: `apps/storefront_builder/tests/test_views.py::StorefrontBuilderViewsTestCase`
  (store `akhlaghi`, owner membership, `HTTP_HOST=sfb-test.rastisi.localhost`). Note it pins
  `r4_editor_enabled=False`; the W2 theme R4-endpoint tests flip it back to `True` in `setUp`.
- W2 Theme suite: `apps/storefront_builder/tests/test_w2_theme_overlay.py` — **58 tests**
  (verified). W3 adds no tests to this module, so it must remain 58.
- Settings: `--settings=shop_core.settings`. Runtime Python 3.12.13 / Django 5.2.17.

---

## H. STOP-condition check (Section 3)
None triggered. W3 will:
- reuse `resolve_preset_candidate` / `resolve_store_appearance_manifest_state` (no new candidate engine),
- reuse `storefront_preview` (no new route/renderer),
- reuse `apply_mutation` + `_persist_manifest_selection_updates` (no second mutation/save/history authority),
- reuse W2 `clear_theme` (no duplicate),
- add exactly ONE new service module (`design_lab_service.py`), ONE new
  `apply_component_variant` writer, ONE new mutation arm (`design_lab.apply_candidate`), and
  transient in-memory candidate state (`DesignLabCandidate` frozen dataclass — never persisted).
- **Zero models, zero migrations, zero registered candidates, zero localStorage authority.**
